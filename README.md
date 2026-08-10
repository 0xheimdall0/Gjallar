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
| Database schema — sources, events, heartbeats, subscriptions | Installable PWA with Web Push |
| Source token authentication (Argon2, prefix lookup, revocation) | Heartbeats and silence detection |
| Event ingest endpoint with schema validation | Security hardening pass |
| Read API — filters, tag search, full-text search, pagination | Docker packaging and deployment |
| Svelte timeline UI | |

## Features

- **One-line ingest** — any script that can run `curl` can report to Gjallar. No client library, no SDK, no agent to install.
- **Timeline** — every event from every machine in one place, newest first, with severity, source, tags and free-text message.
- **Filtering & search** — by source, by severity, by tag, by full-text match on title or message, or unread only.
- **Cursor pagination** — pages are requested by last-seen id, so events arriving mid-scroll are never silently skipped.
- **Heartbeats (planned)** — declare that a source must check in every *N* seconds with a grace period; silence past that becomes an alert.
- **Web Push (planned)** — installable to your phone's home screen, with per-device severity thresholds so the phone stays quieter than the desktop.
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
5. Filter by severity, source or tag when something needs finding.

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
    models.py     request/response schemas
    main.py       FastAPI application and routes
  manage.py       admin CLI
frontend/
  src/
    App.svelte    timeline, filters, token entry
    lib/
      api.js      the only module that talks to the backend
      EventCard.svelte
docs/             notes and write-ups
```

## Files created

- `backend/data/signal.db` — the SQLite database (plus its `-wal` and `-shm` sidecars).
- `backend/.env` — local configuration, including the admin token.

Both are git-ignored.

## License

Released under the [MIT License](LICENSE).
