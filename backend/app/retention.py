import logging
from datetime import UTC, datetime, timedelta

from .config import settings
from .db import connect

logger = logging.getLogger(__name__)

def purge_old_events() -> None:
    cutoff = (
        datetime.now(UTC) - timedelta(days=settings.retention_days)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    conn = connect()
    try:
        cursor = conn.execute("DELETE FROM events WHERE received_at < ?", (cutoff,))
        conn.commit()
        if cursor.rowcount:
            logger.info("purged %s events older than %s", cursor.rowcount, cutoff)
    finally:
        conn.close()
