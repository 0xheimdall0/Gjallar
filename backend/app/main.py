import json
import sqlite3
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from . import __version__
from .auth import verify_token
from .config import settings
from .db import get_db, init_db, utc_now
from .models import EventIn, EventOut

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

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
    return EventOut(id=cursor.lastrowid, received_at=received_at)