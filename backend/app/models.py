from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["debug", "info", "warn", "error", "critical"]

class EventIn(BaseModel):
    model_config = {"extra": "forbid"}

    title: str = Field(min_length=1, max_length=200)
    message: str | None = Field(default=None, max_length=8000)
    severity: Severity = Field(default="info")
    tags: list[str] = Field(default_factory=list, max_length=20)
    metadata: dict | None = None
    link: str | None = Field(default=None, max_length=2000)

class EventOut(BaseModel):
    id: int
    received_at: str

class EventRead(BaseModel):
    id: int
    source: str
    title: str
    message: str | None
    severity: Severity
    tags: list[str]
    metadata: dict | None
    link: str | None
    received_at: str 
    read_at: str | None

class EventIdList(BaseModel):
    """Body for bulk deletion."""

    model_config = {"extra": "forbid"}

    # Capped so a single request can't try to delete the entire table, and
    # typed as int so anything else is rejected before it reaches SQL.
    ids: list[int] = Field(min_length=1, max_length=500)


class EventPage(BaseModel):
    events: list[EventRead]
    next_before: int | None
    unread_count: int = 0

class PushSubscriptionIn(BaseModel):
    model_config = {"extra": "forbid"}

    endpoint: str = Field(min_length=1, max_length=2000)
    p256dh: str = Field(min_length=1, max_length=200)
    auth: str = Field(min_length=1, max_length=200)
    label: str | None = Field(default=None, max_length=100)
    min_severity: Severity = "warn"

class HeartbeatPing(BaseModel):
    model_config = {"extra": "forbid"}
    expected_interval_seconds: int | None = Field(default=None, gt=0, le=31_536_000)
    grace_seconds: int | None = Field(default=None, ge=0, le=86_400)

class HeartbeatOut(BaseModel):
    id: int
    name: str
    source: str
    state: str
    expected_interval_seconds: int
    grace_seconds: int
    last_ping_at: str | None
    paused: bool

class SourceCreate(BaseModel):
    model_config = {"extra": "forbid"}

    # Letters, digits, spaces and mild punctuation. The point of the pattern is
    # to exclude control characters — a newline in a source name would let a
    # caller forge extra lines in the log file — not to be fussy about spelling.
    name: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9 _.()\[\]#/@:+-]+$",
    )
    description: str | None = Field(default=None, max_length=200)

class SourceCreated(BaseModel):
    name: str
    token: str

class SourceOut(BaseModel):
    id: int
    name: str
    description: str | None
    created_at: str
    last_seen_at: str | None
    revoked: bool

