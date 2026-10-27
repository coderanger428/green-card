"""
Spread remaining daily cap evenly across the rest of the Tokyo day.

Queue is FIFO. There are no region send windows. After each send, wait

    remaining_seconds_until_midnight / remaining_cap

so a 50/day cap runs all day (~29 min apart at midnight, faster if you
start late). If the minimum drip delay would miss the cap, the interval
shrinks so leftover cap is not wasted at midnight.
"""

from __future__ import annotations

import os
import random
from datetime import datetime, timedelta

from core.db import TOKYO_TZ, current_tokyo_datetime

DRIP_DELAY_MIN = int(os.environ.get("MAIL_DRIP_DELAY_MIN", "30"))
DRIP_JITTER = 0.15


def _as_tokyo(when: datetime | None = None) -> datetime:
    if when is None:
        return current_tokyo_datetime()
    if when.tzinfo is None:
        return when.replace(tzinfo=TOKYO_TZ)
    return when.astimezone(TOKYO_TZ)


def next_tokyo_midnight(when: datetime | None = None) -> datetime:
    tokyo = _as_tokyo(when)
    return (tokyo + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def remaining_tokyo_day_sec(when: datetime | None = None) -> float:
    tokyo = _as_tokyo(when)
    return max(1.0, (next_tokyo_midnight(tokyo) - tokyo).total_seconds())


def paced_interval_sec(
    remaining_cap: int,
    remaining_sec: float,
    *,
    min_sec: float | None = None,
) -> float:
    """Seconds between sends so `remaining_cap` finishes by midnight."""
    floor = float(DRIP_DELAY_MIN if min_sec is None else min_sec)
    left = max(0, int(remaining_cap))
    horizon = max(1.0, float(remaining_sec))
    if left <= 0:
        return horizon
    raw = horizon / left
    if floor * left > horizon:
        return max(1.0, raw)
    return max(floor, raw)


def paced_delay_sec(
    remaining_cap: int,
    remaining_sec: float,
    *,
    min_sec: float | None = None,
    jitter: bool = True,
) -> float:
    """Sleep after a send: paced interval, optional jitter, never past midnight."""
    horizon = max(1.0, float(remaining_sec))
    delay = paced_interval_sec(remaining_cap, horizon, min_sec=min_sec)
    if jitter:
        delay *= random.uniform(1.0 - DRIP_JITTER, 1.0 + DRIP_JITTER)
    return max(1.0, min(delay, horizon))
