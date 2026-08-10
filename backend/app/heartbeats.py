import json
import logging
from datetime import datetime, timezone

from .db import connect, parse_utc, utc_now
from .push import notify_event

logger = logging.getLogger(__name__)

def record_heartbeat_event(
    source_id: int,
    source_name: str,
    title: str,
    severity: str,
    message: str | None = None,
) -> None:
    conn = connect()
    try:
        received_at = utc_now()
        cursor = conn.execute(
            "INSERT INTO events (source_id, title, message, severity, tags, received_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (source_id, title, message, severity, json.dumps(["heartbeat"]), received_at)
        )
        conn.commit()
        logger.info("heartbeat event filed: %s [%s]", title, severity)
        event_id = cursor.lastrowid
    finally:
        conn.close()

    notify_event(
        {
            "id": event_id,
            "title": title,
            "message": message,
            "severity": severity,
            "source": source_name,
        }
    )

def check_heartbeats() -> None:
    conn = connect()
    try:
        now = datetime.now(timezone.utc)
        rows = conn.execute(
            "SELECT h.*, s.name AS source_name FROM heartbeats h"
            " JOIN sources s ON s.id = h.source_id WHERE h.paused= 0"
        ).fetchall()

        for hb in rows:
            reference = hb["last_ping_at"] or hb["created_at"]
            elapsed = (now - parse_utc(reference)).total_seconds()
            interval = hb["expected_interval_seconds"]
            deadline = interval + hb["grace_seconds"]

            new_state = ""
            if elapsed <= interval:
                new_state = "ok"
            elif interval < elapsed <= deadline:
                new_state = "late"
            else:
                new_state = "down"

            if new_state == hb["state"]:
                continue

            logger.info(
                "heartbeat %s/%s: %s -> %s (%.0fs since last ping)",
                hb["source_name"], hb["name"], hb["state"], new_state, elapsed,
            )

            conn.execute(
                "UPDATE heartbeats SET state = ? WHERE id = ?",
                (new_state, hb["id"]),
            )

            if new_state == "down" and hb["alerted_at"] is None:
                conn.execute(
                    "UPDATE heartbeats SET alerted_at = ? WHERE id = ?",
                    (utc_now(), hb["id"])
                )
                conn.commit()

                record_heartbeat_event(
                    hb["source_id"],
                    hb["source_name"],
                    f"{hb['name']} has stopped reporting",
                    "critical",
                    f"No ping for {int(elapsed)}s. Expected every {interval}s"
                    f" with {hb['grace_seconds']}s grace.",
                )
            else:
                conn.commit()
    finally:
        conn.close()