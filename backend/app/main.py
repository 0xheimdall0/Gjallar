import json
import sqlite3
import hmac
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException, status, Query, BackgroundTasks
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from . import __version__
from .auth import verify_token
from .config import settings
from .db import get_db, init_db, utc_now
from .models import EventIn, EventOut, EventRead, EventPage, PushSubscriptionIn, Severity, HeartbeatPing, HeartbeatOut
from .push import notify_event
from .heartbeats import record_heartbeat_event, check_heartbeats
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler(daemon=True)

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
        raise unauthorized

    source = verify_token(db, credentials.credentials)
    if source is None:
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
    received_at = utc_now()
    cursor = db.execute(
        "INSERT INTO events (source_id, title, message, severity, tags, metadata, link, received_at)"
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
    if settings.admin_token is None:
        raise HTTPException(503, "Admin token not configured on the server.")
    if credentials is None:
        raise HTTPException(401, "Missing token.", headers={"WWW-Authenticate": "Bearer"})
    if not hmac.compare_digest(credentials.credentials, settings.admin_token):
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

    rows = db.execute(
        f"""
        SELECT e.*, s.name AS source_name
        FROM events e
        JOIN sources s ON s.id = e.source_id
        {where_sql}
        ORDER BY e.id DESC
        LIMIT ?
        """,
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

    return EventPage(events=events, next_before=next_before)

@app.get("/api/push/key")
def push_key(_: None = Depends(require_admin)) -> dict:
    if not settings.vapid_public_key:
        raise HTTPException(503, "Push is not configured on the server.")
    return {"public_key": settings.vapid_public_key}

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
            "INSERT INTO heartbeats (source_id, name, expected_interval_seconds, grace_seconds, last_ping_at, state, created_at)"
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