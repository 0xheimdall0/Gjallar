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