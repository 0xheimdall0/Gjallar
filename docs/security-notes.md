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

### Rotating VAPID keys is an outage, not a config change

A browser binds each push subscription to the public key that created it. Change
the pair and every existing subscription becomes not merely invalid but
*obstructive*: `pushManager.subscribe()` refuses to replace it, with an error
that names neither the cause nor the fix.

So key rotation has an operational cost — every device must reopen the app and
re-enable notifications, and until it does it silently receives nothing. The
client handles the mechanics (it drops a subscription whose key no longer
matches before subscribing again), but nothing can spare the user the round
trip.

If the private key ever leaks, that is the recovery path, and it is worth
knowing in advance rather than discovering it mid-incident.

### The VAPID private key is a signing credential

It authenticates *this server* to push services. Leaking it lets someone send
notifications that appear to come from Gjallar to every device subscribed to it.
It lives in `.env`, never in the repository, and is generated once —
regenerating invalidates every existing subscription, since browsers bind a
subscription to the public key it was created with.

### Claim on first use

A setup wizard that cannot create the admin token isn't solving setup — the user
is back to editing `.env`. So an unconfigured instance will provision itself:
`POST /api/setup/claim` generates the admin token and a VAPID pair, writes them
to `backend/.env`, and returns the admin token once.

That is trust on first use: whoever reaches an unclaimed instance takes
ownership of it. Grafana, Jellyfin and Home Assistant all work this way. Two
guards make it acceptable here:

1. **It stops working permanently once a token exists** — `409` thereafter.
2. **Loopback clients only**, unless `SIGNAL_SETUP_ALLOW_REMOTE=true`. Setup has
   to happen on the machine Gjallar runs on, not from anywhere that can reach
   it.

Every claim, and every refused claim, is logged at `WARNING` with the client
address.

Residual risk worth stating plainly: behind a reverse proxy that forwards to
`127.0.0.1` — `tailscale serve`, for instance — the loopback check sees the
proxy, not the real client. On a private tailnet that means "anyone on my
tailnet", which is an acceptable trust boundary for this application but is not
the same as "only me".

### Deleting a source deletes its history

`DELETE /api/sources/{id}` cascades, because `events.source_id` and
`heartbeats.source_id` are declared `ON DELETE CASCADE`. Removing a machine
removes every event it ever filed.

That is why revoke and delete are separate operations. Revoking disables the
credential and keeps the record — the right answer for a stolen laptop, where
the history is evidence. Deleting is for cleaning up a test source. The
interface spells out the difference in the confirmation dialog rather than
relying on the user knowing the schema.

### Admin token in `localStorage` — a knowing tradeoff

The admin token is a bearer credential in JavaScript-readable storage, so any
XSS in the UI hands it over. The stronger option is an httpOnly cookie the JS
cannot read.

Accepted for now because this is a single-user self-hosted app and the XSS
surface is small and actively defended. Recorded here rather than glossed over:
the mitigation is escaping plus CSP, not the storage choice.

## Closed in the hardening pass

Each was found during development, written down when found, and fixed later —
not discovered by an audit at the end.

| # | Issue | What was done |
|---|---|---|
| 1 | Token length not checked before argon2 hashing | `verify_token` rejects anything that isn't exactly 47 characters before hashing. Measured: 20 requests carrying a 1 MB "token" now cost 151 ms in total, against roughly a second of argon2 work before. The token *format* is public, so an early length rejection leaks nothing. |
| 2 | No rate limiting on ingest | Sliding-window limiter, 120 events per source per minute, returning `429` with `Retry-After`. Uses `time.monotonic()` so NTP corrections can't distort the window. |
| 3 | `SIGNAL_MAX_PAYLOAD_BYTES` configured but never enforced | Middleware returns `413` when `Content-Length` exceeds the limit. Partial — see open item 1 below. |
| 4 | No Content-Security-Policy | Strict CSP plus `X-Content-Type-Options`, `Referrer-Policy` and `Permissions-Policy` on every response. `/docs` is exempt because Swagger loads from a CDN, and that route only exists when `SIGNAL_DEBUG=true`. |
| 5 | No retention or purge job | Daily scheduled delete of events older than `SIGNAL_RETENTION_DAYS`. The `received_at < ?` string comparison works because timestamps are ISO-8601, so lexicographic order is chronological order. |
| 6 | Failures logged nowhere | Module loggers throughout. Rejected tokens log the 12-character prefix only, never the token. Push delivery logs both success and failure with the push service's status and response body. Third-party loggers are pinned to `WARNING` so the output stays readable. |

A linter pass with `ruff` (including the `S` security rules) found one genuine
bug the tests had not: a `logger.warning` in `push._send` referenced `status`
one statement before it was assigned, so any push failure would have raised
`UnboundLocalError` *inside the exception handler* and replaced the real error
with a misleading one. The logging added to make failures visible would itself
have failed. Config lives in `backend/ruff.toml`, with FastAPI's `Depends`
markers exempted from B008 — those warnings are the linter misreading the
framework, not a defect.

## Open weaknesses

Known, deliberate, and documented rather than overlooked.

| # | Issue | Impact | Fix when it matters |
|---|---|---|---|
| 1 | The payload cap trusts `Content-Length` | A chunked request sends no `Content-Length` and streams past the check | Count bytes while reading the stream |
| 2 | Search uses `LIKE '%…%'` | Cannot use an index; full table scan | Acceptable at current scale; SQLite FTS5 if it stops being |
| 3 | Logging is unstructured text | Fine to read, awkward to query or ship to a SIEM | JSON formatter and a `security` logger namespace |
| 4 | The scheduler lives in the application process | Running uvicorn with more than one worker would give each its own scheduler, so one outage would produce several alerts | Single process is the documented deployment; otherwise move the job out or take a lock in the database |
| 5 | Notification delivery is unverifiable end to end | `201` from a push service means *accepted*, not *displayed* — see the incident below | Platform limit. The timeline, not the notification, is the source of truth |
| 6 | Setup claim trusts the client address | Behind a proxy forwarding from `127.0.0.1`, the loopback guard sees the proxy, so anyone on the tailnet could claim an unconfigured instance | Acceptable trust boundary here; claim during the first minute of running it |
| 7 | No unit tests | CI now drives the running container through setup, ingest, a forged-token rejection and a heartbeat, which covers the paths that broke before — but there is no unit-level suite | `pytest` covering auth failure modes, ingest validation and the heartbeat state machine |

## Incident: authentication bypass on token mismatch

Found while cleaning up linter findings, not by the linter itself.

`verify_token` looked like this:

```python
    try:
        _hasher.verify(row["token_hash"], token)
    except (VerifyMismatchError, VerificationError):
        pass

    conn.execute("UPDATE sources SET last_seen_at = ? WHERE id = ?", ...)
    return row
```

A failed verification was swallowed and execution fell through to `return row`.
**Any token with a correct 12-character prefix authenticated, whatever followed
it** — and the prefix is stored in the clear and printed in the logs on every
rejected request. The impact is event forgery: writing to any source's timeline,
including fake heartbeat recoveries that would suppress a real outage alert.

It was introduced when a `return None` became a `pass` during an edit. Every
integration test still passed, because they all used correct tokens; the earlier
adversarial test that would have caught it was written before the regression.

Two things this changes:

- **Failure paths need tests as much as success paths.** The check now lives in
  the test set: correct token authenticates, right-prefix-wrong-key is rejected,
  unknown prefix is rejected.
- **`except: pass` deserves suspicion in any security-relevant function.** Ruff's
  `S110` and `BLE001` flagged the *shape* of this code without understanding the
  consequence. They were right for the wrong reason — which was enough, because
  they made me read it.

## Incident: the alert that was never displayed

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
- [ ] TLS terminated in front of the app; no plain-HTTP listener exposed.
      Until this is done, both token types cross the network in plaintext —
      fine on localhost, unacceptable anywhere else
- [ ] Single uvicorn process (see open item 4), or the scheduler moved out
- [ ] `ruff check .` clean, or every remaining finding triaged in writing
- [ ] `SIGNAL_VAPID_PRIVATE_KEY` set, secret, and not the one from any example
- [ ] Push tested from a device that is *not* on the development machine
- [ ] `git log -p` reviewed for accidentally committed secrets
