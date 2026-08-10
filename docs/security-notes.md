# Security notes

Running notes on the threat model, the decisions taken and why, and the
weaknesses still open. Written as I build, not reconstructed afterwards.

## Threat model

Gjallar ingests arbitrary attacker-controllable text over HTTP and renders it in
a browser. Two assets matter:

1. **The event timeline** — reveals what runs on my network, when, and how it
   fails. Useful reconnaissance.
2. **The tokens themselves** — a source token allows forging events; the admin
   token allows reading everything.

Assumed attacker: anyone who can reach the ingest endpoint. Once deployed that
is the public internet, since scripts need to reach it from outside the LAN.

## Decisions taken

### Two credential types, not one

Source tokens are write-only credentials handed to machines. The admin token is
read-only and used by the UI. Separating them means a compromised backup script
cannot read the timeline, and a compromised browser session cannot forge events.

### Tokens hashed with argon2, never stored in plain text

argon2id via `argon2-cffi` with library default parameters. Chosen over SHA-256
because fast hashes are the wrong tool for secrets: a GPU does billions of
SHA-256 guesses per second, while argon2 is deliberately slow and memory-hard.

The encoded hash carries its own salt and parameters, so no separate salt column
is needed and parameters can be raised later without invalidating old hashes.

### Prefix lookup, with constant-time behaviour for unknown prefixes

Storing only a hash creates a lookup problem: which source does an incoming
token belong to? The first 12 characters are stored in the clear, indexed and
unique, narrowing the search to one row. The prefix is not a secret and is not
sufficient to authenticate.

When no row matches, the code still verifies against a dummy hash before
returning. Without this, an unknown prefix returns in microseconds while a known
one takes ~50 ms, turning the endpoint into an oracle for enumerating valid
prefixes. Measured after the fix: 108.7 ms known vs 107.7 ms unknown — within
noise.

### Identity comes from the token, never from the request body

`source_id` on an inserted event is taken from the authenticated source row. If
it were accepted from the JSON body, any valid token could file events
attributed to any other source.

### Bound parameters everywhere; dynamic SQL built only from literals

The timeline's `WHERE` clause is assembled at runtime, which is normally where
injection appears. The rule applied: SQL *structure* is interpolated only from
string literals in the source; every user-supplied *value* goes through a `?`
placeholder.

An early draft of `verify_token` had the prefix marker written directly into the
query text. Had it been built with an f-string instead of a placeholder, a token
beginning `sig_' OR 1=1--` would have returned the first row in the table —
authentication bypass. It failed loudly instead, because the value was bound.

### Constant-time comparison for the admin token

`hmac.compare_digest`, not `==`. String comparison short-circuits at the first
differing byte, leaking the token one character at a time over enough requests.
Source tokens don't need this because argon2 handles it internally; the admin
token is a plain string comparison, so it's on me.

### Output escaping in the UI

Event messages are attacker-controlled text rendered in a browser — the obvious
stored-XSS surface. Svelte escapes `{...}` interpolation by default, so a
message containing `<script>alert(1)</script>` is displayed, not executed. The
protection disappears the moment `{@html ...}` is used, so it is never used.
A strict CSP is still to be added as defence in depth.

### Push payloads are minimised, and the push service is untrusted

Web Push cannot be self-hosted. Messages travel through a service run by the
browser vendor — Mozilla for Firefox, Google for Chrome, Apple for Safari — so
that third party is part of the delivery path whether I like it or not.

The payload itself is encrypted with keys the browser generated at subscription
time (`p256dh` and `auth`), so the relay carries ciphertext it cannot read. It
does still learn metadata: which endpoint, at what time, of roughly what size.
A steady trickle of pushes at 03:00 says "this person runs nightly backups"
without revealing a single word of content.

So payloads carry a 120-character preview rather than full event text. That also
happens to be necessary — push services cap the encrypted payload at around
4 KB — but the reason to prefer it is that the less that leaves the network, the
less there is to leak.

`userVisibleOnly: true` is set on every subscription. Chrome requires it, and it
is the right default regardless: it forbids silent background pushes, so the
server cannot wake the client without the user seeing something.

### The VAPID private key is a signing credential

It authenticates *this server* to push services. Leaking it lets someone send
notifications that appear to come from Gjallar to every device subscribed to it.
It lives in `.env`, never in the repository, and is generated once —
regenerating invalidates every existing subscription, since browsers bind a
subscription to the public key it was created with.

### Admin token in `localStorage` — a knowing tradeoff

The admin token is a bearer credential in JavaScript-readable storage, so any
XSS in the UI hands it over. The stronger option is an httpOnly cookie the JS
cannot read.

Accepted for now because this is a single-user self-hosted app and the XSS
surface is small and actively defended. Recorded here rather than glossed over:
the mitigation is escaping plus CSP, not the storage choice.

## Open weaknesses

Found while building, not yet fixed. Scheduled for the hardening pass.

| # | Issue | Impact | Fix |
|---|---|---|---|
| 1 | Token length is not checked before argon2 hashing | A multi-megabyte "token" burns real CPU per request — cheap DoS | Reject anything that isn't exactly the expected token length before hashing |
| 2 | No rate limiting on ingest | One runaway script can fill the disk | Per-source rate limit and a payload size cap |
| 3 | `SIGNAL_MAX_PAYLOAD_BYTES` is configured but not enforced | Setting exists, does nothing | Enforce in middleware |
| 4 | No Content-Security-Policy header | XSS defence relies solely on escaping | Strict CSP, no inline scripts |
| 5 | No retention or purge job | `events` grows without bound | Scheduled delete beyond `SIGNAL_RETENTION_DAYS` |
| 6 | Search uses `LIKE '%…%'` | Cannot use an index; full scan | Acceptable at current scale; FTS5 if it matters |
| 7 | Errors are not logged, only returned | No audit trail of failed auth attempts | Structured logging of 401s with source prefix |
| 8 | `push._send` discards the reason for every failure | Delivery can stop working with no trace; diagnosing it required writing a separate script | Log status and body on every failure path |
| 9 | Push failures inside a background task are invisible | An exception after the response is sent surfaces only in the server's stdout | Wrap the task, log, and record a failure count |
| 10 | Notification delivery is unverifiable end to end | `201` from the push service means *accepted*, not *displayed* — an OS focus mode silently suppresses everything | Accept as a platform limit; document it, and rely on the timeline as the source of truth |

## Incident worth recording

Push appeared completely broken for about an hour. The server reported `HTTP 201`
from Mozilla on every attempt, the subscription row existed, the service worker
was registered and active, and no error appeared anywhere in the stack.

The cause was Windows Do Not Disturb. Every layer I could observe was reporting
success, and the notification was being discarded silently at the very last step,
by a component outside the application entirely.

That is precisely the failure mode Gjallar is built to catch, and it happened to
Gjallar. The generalisation is worth keeping: **a success code from a delivery
service is not evidence that a human was informed.** Any alerting design that
treats "the API accepted it" as "the alert landed" has an untested assumption at
its core — which is the argument for heartbeats, since silence is the only signal
that survives when every acknowledgement lies.

## To verify before deployment

- [ ] `foreign_keys = ON` is set on every connection, not just at schema load
- [ ] Admin token is not the default and not committed
- [ ] `SIGNAL_DEBUG=false` in production, so `/docs` and `/openapi.json` are off
- [ ] TLS terminated in front of the app; no plain-HTTP listener exposed
- [ ] `SIGNAL_VAPID_PRIVATE_KEY` set, secret, and not the one from any example
- [ ] Push tested from a device that is *not* on the development machine
- [ ] `git log -p` reviewed for accidentally committed secrets
