import json
import sqlite3
from pywebpush import WebPushException, webpush
from .config import settings
from .db import connect, utc_now

SEVERITY_ORDER = {"debug": 0, "info": 1, "warn": 2, "error": 3, "critical": 4}

MAX_FAILURES = 5

BODY_PREVIEW_CHARS = 120

def _send(conn: sqlite3.Connection, sub: sqlite3.Row, payload: dict) -> None:
    try:
        webpush(
            subscription_info={
                "endpoint": sub["endpoint"],
                "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
            },
            data=json.dumps(payload),
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_subject},
            ttl=3600,
        )
    except WebPushException as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status in (404, 410):
            conn.execute("DELETE FROM push_subscriptions WHERE id = ?", (sub["id"],))
        else:
            conn.execute(
                "UPDATE push_subscriptions SET failure_count = failure_count + 1 WHERE id = ?",
                (sub["id"],)
            )
            conn.execute(
                "DELETE FROM push_subscriptions WHERE failure_count >= ?",
                (MAX_FAILURES,)
            )
        conn.commit()
        return
    conn.execute(
        "UPDATE push_subscriptions SET last_success_at = ?, failure_count = 0 WHERE id = ?",
        (utc_now(), sub["id"],)
    )
    conn.commit()

def _preview(message: str | None) -> str:
    if not message:
        return ""
    if len(message) <= BODY_PREVIEW_CHARS:
        return message
    return message[: BODY_PREVIEW_CHARS - 1] + "-"

def notify_event(event: dict) -> None:
    if not settings.vapid_private_key:
        return
    conn = connect()
    try:
        level = SEVERITY_ORDER[event["severity"]]
        subs = conn.execute("SELECT * FROM push_subscriptions").fetchall()

        for sub in subs:
            if SEVERITY_ORDER[sub["min_severity"]] > level:
                continue

            payload = {
                "id": event["id"],
                "title": f"{event['source']}: {event['title']}",
                "body": _preview(event["message"]),
                "severity": event["severity"],
                "source": event["source"],
            }

            _send(conn, sub, payload)
    finally:
        conn.close()
