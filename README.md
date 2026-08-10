# Gjallar — Heimdall's Signal Inbox

A self-hosted inbox for machine signals. Any script, cron job or service sends a
one-line HTTP request and the event lands in a searchable timeline on your phone
and desktop. Built with **FastAPI** and **SQLite** on the back, an installable
**Svelte PWA** on the front, and secured with **Argon2**-hashed API tokens.

Unlike ordinary alerting, Gjallar also watches for **silence**: register a
heartbeat for a source, and if the expected ping never arrives, that absence
becomes an alert. It catches the backup script that died six weeks ago and never
said a word.

```bash
curl -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"title":"Backup finished","severity":"info","message":"412 GB, 3m21s"}' \
     https://gjallar.example.com/api/events
```

> ⚠️ **Disclaimer:** Gjallar is a personal/learning project, still in
> development. It has **not** been independently security-audited. Do not expose
> it to the internet without TLS in front of it, and treat the tokens it issues
> as real credentials.

Named after Gjallarhorn — the horn Heimdall sounds when something is coming.

---

## Status

| Done | In progress / planned |
|---|---|
| Database schema — sources, events, heartbeats, subscriptions | Heartbeats and silence detection |
| Source token authentication (Argon2, prefix lookup, revocation) | Security hardening pass |
| Event ingest endpoint with schema validation | Docker packaging and deployment |
| Read API — filters, tag search, full-text search, pagination | |
| Svelte timeline UI | |
| Installable PWA with Web Push notifications | |

## Features

- **One-line ingest** — any script that can run `curl` can report to Gjallar. No client library, no SDK, no agent to install.
- **Timeline** — every event from every machine in one place, newest first, with severity, source, tags and free-text message.
- **Filtering & search** — by source, by severity, by tag, by full-text match on title or message, or unread only.
- **Cursor pagination** — pages are requested by last-seen id, so events arriving mid-scroll are never silently skipped.
- **Installable PWA** — add it to your phone's home screen or your desktop; it opens in its own window and works offline for anything already loaded.
- **Web Push notifications** — events reach you with the app closed. Each device sets its own severity floor, so the phone can stay quiet while the desktop shows everything, and `critical` alerts stay on screen until acknowledged.
- **Heartbeats (planned)** — declare that a source must check in every *N* seconds with a grace period; silence past that becomes an alert.
- **Two credential types**
  - *Source tokens* — write-only, one per machine or script, individually revocable.
  - *Admin token* — read-only, used by the UI.
- **Admin CLI** — create, list and revoke sources without touching the database.
- **Single container** — FastAPI serves both the API and the built frontend. One SQLite file, no Redis, no message queue.

## Security model

- **Tokens are never stored.** Only an Argon2id hash is kept; the first 12 characters are stored in the clear as an indexed lookup key, which is not sufficient to authenticate.
- **Unknown tokens cost the same as wrong ones.** A prefix that matches nothing is still verified against a dummy hash, so response timing does not reveal which prefixes exist.
- **Write and read credentials are separate.** A compromised backup script cannot read your timeline; a compromised browser session cannot forge events.
- **Event identity comes from the token**, never from the request body — a source cannot file events as another source.
- **Every query uses bound parameters.** Dynamic `WHERE` clauses are assembled only from string literals in the source; user values always go through placeholders.
- **Output is escaped by default.** Event text is attacker-controlled and rendered in a browser; Svelte interpolation escapes it, and `{@html}` is never used.
- **Tokens are shown once and cannot be recovered.** Lose one, revoke it and issue another.
- **Push payloads are encrypted for the device.** Web Push encrypts the body with keys the browser generated, so the push service relays ciphertext it cannot read. It still sees timing, size and endpoint, so payloads carry a short preview rather than full event text.
- **Dead push endpoints are pruned.** A `404`/`410` from the push service deletes the subscription; repeated other failures retire it after five attempts.

Full threat model, decisions taken and known open weaknesses:
[docs/security-notes.md](docs/security-notes.md).

## Requirements

- **Python 3.11+** and **Node 18+** to run from source.
- Nothing else — no database server, no cache, no broker.

## Quick start

```bash
git clone https://github.com/0xheimdall0/Gjallar.git
cd Gjallar
```

**Backend**, from `backend/`:

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows
# source .venv/bin/activate       # macOS / Linux

pip install -r requirements.txt
copy .env.example .env            # then set SIGNAL_ADMIN_TOKEN

uvicorn app.main:app --reload --port 8002
```

Generate the admin token the UI will use:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Generate the VAPID key pair that signs push messages, and put both lines plus a
contact address into `.env`:

```bash
python generate_vapid.py
# SIGNAL_VAPID_PRIVATE_KEY=...
# SIGNAL_VAPID_PUBLIC_KEY=...
# SIGNAL_VAPID_SUBJECT=mailto:you@example.com
```

Run it once. Regenerating the pair invalidates every existing subscription,
because browsers bind a subscription to the public key it was created with.

Issue a token to a machine (printed once, unrecoverable):

```bash
python manage.py create-source nas "Home NAS"
python manage.py list-sources
python manage.py revoke-source nas
```

**Frontend**, from `frontend/`:

```bash
npm install
npm run dev
```

Open <http://localhost:5173>. Vite proxies `/api/*` to the backend, so the
browser only ever sees one origin and no CORS configuration is required.

## API

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/api/health` | none | liveness check; touches the database |
| `POST` | `/api/events` | source token | file an event |
| `GET` | `/api/events` | admin token | timeline, filters, pagination |
| `GET` | `/api/push/key` | admin token | VAPID public key for subscribing |
| `POST` | `/api/push/subscribe` | admin token | register this device for notifications |

`POST /api/events` accepts `title` (required), `message`, `severity`
(`debug` / `info` / `warn` / `error` / `critical`), `tags`, `metadata` and `link`.

`GET /api/events` accepts `limit`, `before`, `source`, `severity`, `tag`, `q`
and `unread`.

## Preview

### Timeline
![Timeline](docs/screenshot.png)

## Usage

1. Start the backend, set an admin token in `.env`, and open the UI.
2. Paste the admin token into the field at the top and save it.
3. Issue a source token per machine with `manage.py create-source`.
4. Add one `curl` line to any script you want to hear from.
5. Click **Enable notifications** to register the device for push.
6. Filter by severity, source or tag when something needs finding.

## Troubleshooting

**Notifications never arrive.** Check, in this order:

1. **Operating-system focus modes.** Windows Focus Assist / Do Not Disturb
   suppresses notifications silently. The push service still returns `201`,
   because `201` means *accepted for delivery*, not *displayed*. This is the
   single most likely cause and the easiest to overlook.
2. **The push service is reachable.** Push is the one part of Gjallar you cannot
   self-host: the message travels via Google (Chrome and other Chromium
   browsers), Mozilla (Firefox) or Apple (Safari). Some corporate and campus
   networks block those endpoints, and the failure surfaces as
   `Registration failed - push service error` at subscribe time. Try a different
   browser or network to confirm.
3. **Brave blocks push by default.** Brave ships with Google's push service
   disabled as a privacy measure, so subscription fails outright. Enable it at
   `brave://settings/privacy` → *Use Google services for push messaging*, then
   restart the browser. Note the tradeoff this asks of the user: it opens a
   connection to Google's infrastructure, which then sees push metadata for
   every subscribed site. Someone self-hosting a monitoring tool to avoid third
   parties may reasonably decline — a real limitation of Web Push, not of this
   application.
4. **The subscription is current.** Unregistering the service worker or clearing
   site data invalidates the subscription; re-enable notifications to create a
   new one. Stale rows are pruned when the push service reports them gone.

**Push works on desktop but not on the phone.** Notifications require a secure
context. `localhost` counts; a LAN IP over plain HTTP does not. Serve the app
over HTTPS. On iOS, the app must additionally be installed to the home screen —
Safari does not deliver push to a normal tab.

**Code changes to the service worker don't take effect.** A service worker with
an open client is replaced only after every tab for that origin closes. During
development, unregister it (`about:debugging` in Firefox, DevTools → Application
in Chrome) and hard-reload.

## Architecture

```
scripts / servers ──POST──> FastAPI ──> SQLite
                               │
                               ├─> Web Push ──> phone / desktop
                               └─> Svelte PWA (timeline)

             scheduler ──> heartbeat checker (looks for silence)
```

```
backend/
  app/
    config.py     environment-driven settings, loaded once
    db.py         SQLite connections and helpers
    schema.sql    the whole data model, idempotent DDL
    auth.py       token generation and verification
    push.py       Web Push delivery and subscription pruning
    models.py     request/response schemas
    main.py       FastAPI application and routes
  manage.py       admin CLI
  generate_vapid.py  one-shot VAPID key generator
frontend/
  src/
    App.svelte    timeline, filters, token entry
    sw.js         service worker: precache, push, notification click
    lib/
      api.js      the only module that talks to the backend
      push.js     permission prompt and subscription registration
      EventCard.svelte
docs/             notes and write-ups
```

## Files created

- `backend/data/signal.db` — the SQLite database (plus its `-wal` and `-shm` sidecars).
- `backend/.env` — local configuration, including the admin token.

Both are git-ignored.

## License

Released under the [MIT License](LICENSE).
