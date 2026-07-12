from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone


def smart_random_schedule(
    best_hour: int = 19,
    window_hours: int = 2,
    tz_offset_hours: int = 8,
) -> datetime:
    """Pick a human-like timezone-aware schedule datetime.

    - random hour in [best_hour, best_hour+window_hours)
    - minute from 5-55 excluding 0 and 30
    - second 0-59
    - add random jitter -15..+25 minutes
    - if the time is in the past today, move to tomorrow
    - return timezone-aware datetime with timezone(timedelta(hours=tz_offset_hours))

    No external dependencies.
    """

    tz = timezone(timedelta(hours=tz_offset_hours))
    now = datetime.now(tz)

    hour = random.randint(best_hour, best_hour + window_hours - 1)

    allowed_minutes = [m for m in range(5, 56) if m not in (30,)]
    minute = random.choice(allowed_minutes)
    second = random.randint(0, 59)

    dt = now.replace(hour=hour, minute=minute, second=second, microsecond=0)

    jitter_minutes = random.randint(-15, 25)
    dt = dt + timedelta(minutes=jitter_minutes)

    if dt <= now:
        dt = dt + timedelta(days=1)

    return dt.replace(tzinfo=tz)


def to_delay_ms(publish_at: datetime) -> int:
    """Calculate milliseconds from now to publish_at. Returns max(0, ms)."""

    now_utc = datetime.now(timezone.utc)

    if publish_at.tzinfo is None:
        publish_at = publish_at.replace(tzinfo=timezone.utc)

    delay_ms = (publish_at - now_utc).total_seconds() * 1000.0
    return max(0, int(delay_ms))

