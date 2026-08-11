import hmac
import json
import logging
import secrets
import sqlite3
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    status,
)
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles

from . import __version__, config
from .auth import TOKEN_PREFIX_LENGTH, generate_token, hash_token, verify_token
from .config import settings
from .db import get_db, init_db, utc_now
from .heartbeats import check_heartbeats, record_heartbeat_event
from .models import (
    EventIdList,
    EventIn,
    EventOut,
    EventPage,
    EventRead,
    HeartbeatOut,
    HeartbeatPing,
    PushSubscriptionIn,
    Severity,
    SourceCreate,
    SourceCreated,
    SourceOut,
)
from .push import notify_event
from .ratelimit import enforce_rate_limit
from .retention import purge_old_events
from .vapid import generate_vapid_pair

scheduler = BackgroundScheduler(daemon=True)

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
for noisy in ("asyncio", "httpx", "httpcore", "apscheduler.executors.default"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler.add_job(
        check_heartbeats,
        "interval",
        seconds=60,
        id="heartbeat-check",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        purge_old_events,
        "interval",
        hours=24,
        id="retention-purge",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)

app = FastAPI(
    title="Signal inbox",
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    openapi_url="/openapi.json"if settings.debug else None,
    redoc_url=None
)

_bearer = HTTPBearer(auto_error=False)

def require_source(
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
        db: sqlite3.Connection = Depends(get_db),
) -> sqlite3.Row:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing token.",
        headers={"WWW-Authenticate": "Bearer"}
    )

    if credentials is None:
        logger.info("ingest rejected: no bearer token")
        raise unauthorized

    source = verify_token(db, credentials.credentials)
    if source is None:
        logger.warning(
            "ingest rejected: bad token, prefix=%s",
            credentials.credentials[:12],
        )
        raise unauthorized

    return source

@app.get("/api/health")
def health(db: sqlite3.Connection = Depends(get_db)) -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "events": db.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
    }

@app.post("/api/events", response_model=EventOut, status_code=201)
def create_event(
    event: EventIn,
    background: BackgroundTasks,
    source: sqlite3.Row = Depends(require_source),
    db: sqlite3.Connection = Depends(get_db)
) -> EventOut:
    enforce_rate_limit(source["id"])
    received_at = utc_now()
    cursor = db.execute(
        "INSERT INTO events"
        " (source_id, title, message, severity, tags, metadata, link, received_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            source["id"],
            event.title,
            event.message,
            event.severity,
            json.dumps(event.tags),
            json.dumps(event.metadata) if event.metadata is not None else None,
            event.link,
            received_at
        )
    )
    db.commit()
    background.add_task(
        notify_event,
        {
            "id": cursor.lastrowid,
            "title": event.title,
            "message": event.message,
            "severity": event.severity,
            "source": source["name"],
        }
    )
    return EventOut(id=cursor.lastrowid, received_at=received_at)

def require_admin(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> None:
    if config.admin_token() is None:
        raise HTTPException(503, "Admin token not configured on the server.")
    if credentials is None:
        raise HTTPException(401, "Missing token.", headers={"WWW-Authenticate": "Bearer"})
    if not hmac.compare_digest(credentials.credentials, config.admin_token()):
        logger.warning("admin auth rejected")
        raise HTTPException(401, "Credentials don't match.")

@app.get("/api/events", response_model=EventPage)
def list_events(
    _: None = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    before: int | None = Query(default=None, description="Return events with id < this."),
    source: str | None = None,
    severity: Severity | None = None,
    tag: str | None = None,
    q: str | None = Query(default=None, max_length=200),
    unread: bool = False
) -> EventPage:
    where: list[str] = []
    params: list = []

    if before is not None:
        where.append("e.id < ?")
        params.append(before)

    if source is not None:
        where.append("s.name = ?")
        params.append(source)

    if severity is not None:
        where.append("e.severity = ?")
        params.append(severity)

    if tag is not None:
        where.append("EXISTS (SELECT 1 FROM json_each(e.tags) WHERE json_each.value = ?)")
        params.append(tag)

    if q is not None:
        where.append("(e.title LIKE ? OR e.message LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%"])

    if unread:
        where.append("e.read_at IS NULL")

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    # The only interpolation is where_sql, built from string literals above;
    # every user value travels as a bound parameter.
    rows = db.execute(
        f"""
        SELECT e.*, s.name AS source_name
        FROM events e
        JOIN sources s ON s.id = e.source_id
        {where_sql}
        ORDER BY e.id DESC
        LIMIT ?
        """,  # noqa: S608
        (*params, limit)
    ).fetchall()

    events = [
        EventRead(
            id=r["id"],
            source=r["source_name"],
            title=r["title"],
            message=r["message"],
            severity=r["severity"],
            tags=json.loads(r["tags"]),
            metadata=json.loads(r["metadata"]) if r["metadata"] else None,
            link=r["link"],
            received_at=r["received_at"],
            read_at=r["read_at"],
        )
        for r in rows
    ]

    next_before = events[-1].id if len(events) == limit else None

    # Cheap thanks to idx_unread_events, the partial index that only covers
    # rows where read_at IS NULL.
    unread_count = db.execute(
        "SELECT COUNT(*) AS n FROM events WHERE read_at IS NULL"
    ).fetchone()["n"]

    return EventPage(
        events=events,
        next_before=next_before,
        unread_count=unread_count,
    )


@app.post("/api/events/read-all", status_code=204)
def mark_all_events_read(
    _: None = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
) -> None:
    """Mark every unread event as read."""
    db.execute("UPDATE events SET read_at = ? WHERE read_at IS NULL", (utc_now(),))
    db.commit()


@app.post("/api/events/{event_id}/read", status_code=204)
def set_event_read(
    event_id: int,
    read: bool = True,
    _: None = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
) -> None:
    """Mark one event read (default) or unread (?read=false)."""
    cursor = db.execute(
        "UPDATE events SET read_at = ? WHERE id = ?",
        (utc_now() if read else None, event_id),
    )
    db.commit()

    if cursor.rowcount == 0:
        raise HTTPException(404, "No such event")

@app.get("/api/push/key")
def push_key(_: None = Depends(require_admin)) -> dict:
    if not config.vapid_public_key():
        raise HTTPException(503, "Push is not configured on the server.")
    return {"public_key": config.vapid_public_key()}

@app.post("/api/push/subscribe", status_code=201)
def push_subscribe(
    subscription: PushSubscriptionIn,
    _: None = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
) -> dict:
    db.execute(
        "INSERT INTO push_subscriptions (endpoint, p256dh, auth, label, min_severity, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(endpoint) DO UPDATE SET"
        "   p256dh = excluded.p256dh,"
        "   auth = excluded.auth,"
        "   label = excluded.label,"
        "   min_severity = excluded.min_severity",
        (
            subscription.endpoint,
            subscription.p256dh,
            subscription.auth,
            subscription.label,
            subscription.min_severity,
            utc_now(),
        )
    )
    db.commit()
    return {"ok": True}

@app.post("/api/heartbeats/{name}/ping", status_code=204)
def heartbeat_ping(
    name: str,
    ping: HeartbeatPing,
    background: BackgroundTasks,
    source: sqlite3.Row = Depends(require_source),
    db: sqlite3.Connection = Depends(get_db),
) -> None:
    now = utc_now()
    existing = db.execute(
        "SELECT * FROM heartbeats WHERE source_id = ? AND name = ?",
        (source["id"], name),
    ).fetchone()

    if existing is None:
        if ping.expected_interval_seconds is None:
            raise HTTPException(
                400, "First ping must include expected_interval_seconds to register the heartbeat."
            )
        db.execute(
            "INSERT INTO heartbeats"
            " (source_id, name, expected_interval_seconds, grace_seconds,"
            "  last_ping_at, state, created_at)"
            " VALUES (?, ?, ?, ?, ?, 'ok', ?)",
            (
                source["id"],
                name,
                ping.expected_interval_seconds,
                ping.grace_seconds if ping.grace_seconds is not None else 300,
                now,
                now,
            )
        )
        db.commit()
        return

    was_down = existing["state"] == "down"
    db.execute(
        "UPDATE heartbeats SET"
        "   last_ping_at = ?,"
        "   state = 'ok',"
        "   alerted_at = NULL,"
        "   expected_interval_seconds = COALESCE(?, expected_interval_seconds),"
        "   grace_seconds = COALESCE(?, grace_seconds)"
        " WHERE id = ?",
        (now, ping.expected_interval_seconds, ping.grace_seconds, existing["id"]),
    )
    db.commit()

    if was_down:
        background.add_task(
            record_heartbeat_event,
            source["id"],
            source["name"],
            f"{name} is reporting again",
            "info",
        )

@app.get("/api/heartbeats", response_model=list[HeartbeatOut])
def list_heartbeats(
    _: None = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
) -> list[HeartbeatOut]:
    rows = db.execute(
        "SELECT h.*, s.name AS source_name FROM heartbeats h"
        " JOIN sources s ON s.id = h.source_id ORDER BY h.state = 'ok', s.name, h.name"
    ).fetchall()

    return [
        HeartbeatOut(
            id=r["id"],
            name=r["name"],
            source=r["source_name"],
            state=r["state"],
            expected_interval_seconds=r["expected_interval_seconds"],
            grace_seconds=r["grace_seconds"],
            last_ping_at=r["last_ping_at"],
            paused=bool(r["paused"]),
        )
        for r in rows
    ]

@app.middleware("http")
async def limit_payload_size(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH"}:
        declared = request.headers.get("content-length")
        if declared is not None and int(declared) > settings.max_payload:
            return JSONResponse(
                {"detail": "Payload too long."},
                status_code=413,
            )
    return await call_next(request)

CSP_PRODUCTION = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'none'; "
    "object-src 'none'"
)

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    if not request.url.path.startswith("/docs"):
        response.headers["Content-Security-Policy"] = CSP_PRODUCTION

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    return response

@app.get("/api/setup/status")
def setup_status(db: sqlite3.Connection = Depends(get_db)) -> dict:
    configured = config.is_configured()

    source_count = 0
    if configured:
        source_count = db.execute(
            "SELECT COUNT(*) AS n FROM sources WHERE revoked_at IS NULL"
        ).fetchone()["n"]

    return {
        "configured": configured,
        "push_configured": config.vapid_public_key() is not None,
        "source_count": source_count,
    }

@app.post("/api/setup/claim")
def setup_claim(request: Request) -> dict:
    if config.is_configured():
        raise HTTPException(409, "Gjallar is already configured.")

    client = request.client.host if request.client else ""
    if client not in {"127.0.0.1", "::1"} and not settings.setup_allow_remote:
        logger.warning("setup claim refused from %s.", client)
        raise HTTPException(403, "Setup must be completed from the machine running Gjallar.")

    admin = secrets.token_urlsafe(32)
    private_key, public_key = generate_vapid_pair()

    config.persist_env(
        {
            "SIGNAL_ADMIN_TOKEN": admin,
            "SIGNAL_VAPID_PUBLIC_KEY": public_key,
            "SIGNAL_VAPID_PRIVATE_KEY": private_key,
        }
    )

    logger.warning("Gjallar claimed from %s. Admin token generated.", client)
    return {"admin_token": admin}

@app.post("/api/events/delete")
def delete_events(
    payload: EventIdList,
    _: None = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Delete many events at once.

    POST rather than DELETE: a request body on DELETE is legal but unevenly
    supported by proxies and HTTP clients.
    """
    # The f-string interpolates only "?,?,?" — placeholders, never values.
    placeholders = ",".join("?" * len(payload.ids))
    cursor = db.execute(
        f"DELETE FROM events WHERE id IN ({placeholders})",  # noqa: S608
        payload.ids,
    )
    db.commit()

    logger.info("bulk deleted %s events", cursor.rowcount)
    return {"deleted": cursor.rowcount}


@app.delete("/api/events/{event_id}", status_code=204)
def delete_event(
    event_id: int,
    _: None = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
) -> None:
    cursor = db.execute("DELETE FROM events WHERE id = ?", (event_id,))
    db.commit()

    if cursor.rowcount == 0:
        raise HTTPException(404, "No such event")


@app.delete("/api/heartbeats/{heartbeat_id}", status_code=204)
def delete_heartbeat(
    heartbeat_id: int,
    _: None = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
) -> None:
    """Stop watching this heartbeat. It reappears if the source pings again."""
    cursor = db.execute("DELETE FROM heartbeats WHERE id = ?", (heartbeat_id,))
    db.commit()

    if cursor.rowcount == 0:
        raise HTTPException(404, "No such heartbeat")

    logger.info("heartbeat %s deleted", heartbeat_id)


@app.post("/api/heartbeats/{heartbeat_id}/pause", status_code=204)
def pause_heartbeat(
    heartbeat_id: int,
    paused: bool = True,
    _: None = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
) -> None:
    """Suspend silence checking — for a machine that is off on purpose.

    Clearing alerted_at means resuming starts from a clean slate rather than
    staying quiet because it alerted before being paused.
    """
    cursor = db.execute(
        "UPDATE heartbeats SET paused = ?, alerted_at = NULL WHERE id = ?",
        (1 if paused else 0, heartbeat_id),
    )
    db.commit()

    if cursor.rowcount == 0:
        raise HTTPException(404, "No such heartbeat")

    logger.info("heartbeat %s %s", heartbeat_id, "paused" if paused else "resumed")


@app.get("/api/sources", response_model=list[SourceOut])
def list_sources(
    _: None = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
) -> list[SourceOut]:
    rows = db.execute(
        "SELECT id, name, description, created_at, last_seen_at, revoked_at"
        " FROM sources ORDER BY name"
    ).fetchall()

    return [
        SourceOut(
            id=r["id"],
            name=r["name"],
            description=r["description"],
            created_at=r["created_at"],
            last_seen_at=r["last_seen_at"],
            revoked=r["revoked_at"] is not None,
        )
        for r in rows
    ]

@app.post("/api/sources/{source_id}/revoke", status_code=204)
def revoke_source(
    source_id: int,
    _: None = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
) -> None:
    """Disable a source's token but keep everything it has already sent."""
    cursor = db.execute(
        "UPDATE sources SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
        (utc_now(), source_id),
    )
    db.commit()

    if cursor.rowcount == 0:
        raise HTTPException(404, "No such active source")

    logger.warning("source %s revoked", source_id)


@app.delete("/api/sources/{source_id}", status_code=204)
def delete_source(
    source_id: int,
    _: None = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
) -> None:
    """Delete a source *and everything it ever sent*.

    events.source_id and heartbeats.source_id are declared ON DELETE CASCADE,
    so this removes the whole history too. Revoking is usually what you want.
    """
    cursor = db.execute("DELETE FROM sources WHERE id = ?", (source_id,))
    db.commit()

    if cursor.rowcount == 0:
        raise HTTPException(404, "No such source")

    logger.warning("source %s deleted, with all its events and heartbeats", source_id)


@app.post("/api/sources", response_model=SourceCreated, status_code=201)
def create_source(
    payload: SourceCreate,
    _: None = Depends(require_admin),
    db: sqlite3.Connection = Depends(get_db),
) -> SourceCreated:
    token = generate_token()
    try:
        db.execute(
            "INSERT INTO sources (name, token_prefix, token_hash, description, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                payload.name,
                token[:TOKEN_PREFIX_LENGTH],
                hash_token(token),
                payload.description,
                utc_now(),
            ),
        )
        db.commit()
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "A source with that name already exists.") from exc

    logger.info("source created: %s", payload.name)
    return SourceCreated(name=payload.name, token=token)

if settings.frontend_dir is not None:
    app.mount(
        "/",
        StaticFiles(directory=settings.frontend_dir, html=True),
        name="frontend",
    )
    logger.info("serving frontend from %s.", settings.frontend_dir)
else:
    logger.info("no frontend build found: API only.")
