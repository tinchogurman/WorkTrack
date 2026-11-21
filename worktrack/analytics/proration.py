"""Split a session across the local calendar days it touches.

History keeps each session as one record; daily/weekly/monthly totals use
these per-day shares. Day boundaries are local midnights (not UTC).

`tz=None` means the operating system's local time zone; tests pass an
explicit ZoneInfo so results do not depend on the machine.
"""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta, timezone, tzinfo


def to_local(value: datetime, tz: tzinfo | None) -> datetime:
    return value.astimezone(tz) if tz is not None else value.astimezone()


def local_midnight(day: date, tz: tzinfo | None) -> datetime:
    """Aware datetime of 00:00 local time on `day`."""
    if tz is None:
        return datetime.combine(day, time()).astimezone()
    return datetime.combine(day, time(), tzinfo=tz)


def allocate(total: int, weights: list[float]) -> list[int]:
    """Distribute integer `total` proportionally to `weights` (largest remainder).

    The result always sums exactly to `total`.
    """
    weight_sum = sum(weights)
    if total <= 0 or weight_sum <= 0:
        return [0] * len(weights)
    raw = [total * w / weight_sum for w in weights]
    shares = [math.floor(x) for x in raw]
    missing = total - sum(shares)
    by_remainder = sorted(range(len(raw)), key=lambda i: (raw[i] - shares[i], -i), reverse=True)
    for i in by_remainder[:missing]:
        shares[i] += 1
    return shares


def split_by_day(
    start: datetime,
    end: datetime,
    worked_seconds: int | None = None,
    tz: tzinfo | None = None,
) -> list[tuple[date, int]]:
    """Return [(local_date, seconds)] for the interval [start, end).

    `worked_seconds` (default: end - start) is spread proportionally to the
    elapsed time inside each day, so a session whose worked time is lower than
    its elapsed time (e.g. a discounted suspension) is still split fairly.
    Days with a zero share are omitted.
    """
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("split_by_day requires aware datetimes")
    # Arithmetic between datetimes sharing a tzinfo object is wall-clock based
    # in Python (ignores DST shifts); doing it in UTC gives real elapsed time.
    first_day = to_local(start, tz).date()
    start, end = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
    if end <= start:
        return []
    elapsed_total = (end - start).total_seconds()
    worked = int(round(elapsed_total)) if worked_seconds is None else int(worked_seconds)

    days: list[date] = []
    weights: list[float] = []
    cursor = start
    day = first_day
    while cursor < end:
        next_midnight = local_midnight(day + timedelta(days=1), tz).astimezone(timezone.utc)
        segment_end = min(end, next_midnight)
        if segment_end > cursor:
            days.append(day)
            weights.append((segment_end - cursor).total_seconds())
            cursor = segment_end
        day += timedelta(days=1)

    shares = allocate(worked, weights)
    return [(d, s) for d, s in zip(days, shares) if s > 0]
