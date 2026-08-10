import time
from collections import defaultdict, deque

from fastapi import HTTPException

WINDOW_SECONDS = 60
MAX_EVENTS_PER_WINDOW = 120
_recent: dict[int, deque[float]] = defaultdict(deque)

def enforce_rate_limit(source_id: int) -> None:
    now = time.monotonic()
    seen = _recent[source_id]

    while seen and now - seen[0] > WINDOW_SECONDS:
        seen.popleft()

    if len(seen) >= MAX_EVENTS_PER_WINDOW:
        raise HTTPException(
            status_code=429,
            detail="Too many events from this source.",
            headers={"Retry-After": str(WINDOW_SECONDS)},
        )

    seen.append(now)