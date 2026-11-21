"""Split a session across the local calendar days it touches.

History keeps each session as one record; daily/weekly/monthly totals use
these per-day shares. Day boundaries are local midnights (not UTC).

`tz=None` means the operating system's local time zone; tests pass an
explicit ZoneInfo so results do not depend on the machine.
"""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta, timezone, tzinfo

from worktrack.core.intervals import subtract


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
    exclude: list[tuple[datetime, datetime]] | None = None,
) -> list[tuple[date, int]]:
    """Return [(local_date, seconds)] for the interval [start, end).

    `exclude`: ranges removed exactly before splitting (discounted
    interruptions), so a discounted night of suspension takes nothing from
    the days it covers. `worked_seconds` (default: the remaining time) is then
    spread proportionally over what is left, which keeps the per-day sum equal
    to the stored duration. Days with a zero share are omitted.
    """
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("split_by_day requires aware datetimes")
    # Arithmetic between datetimes sharing a tzinfo object is wall-clock based
    # in Python (ignores DST shifts); doing it in UTC gives real elapsed time.
    start, end = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
    if end <= start:
        return []
    pieces = [(start, end)]
    if exclude:
        utc = [(s.astimezone(timezone.utc), e.astimezone(timezone.utc)) for s, e in exclude]
        pieces = subtract(start, end, utc) or [(start, end)]  # never drop worked time
    elapsed_total = sum((e - s).total_seconds() for s, e in pieces)
    worked = int(round(elapsed_total)) if worked_seconds is None else int(worked_seconds)

    weight_by_day: dict[date, float] = {}
    for piece_start, piece_end in pieces:
        cursor = piece_start
        day = to_local(piece_start, tz).date()
        while cursor < piece_end:
            next_midnight = local_midnight(day + timedelta(days=1), tz).astimezone(timezone.utc)
            segment_end = min(piece_end, next_midnight)
            if segment_end > cursor:
                weight_by_day[day] = weight_by_day.get(day, 0.0) + (segment_end - cursor).total_seconds()
                cursor = segment_end
            day += timedelta(days=1)

    days = sorted(weight_by_day)
    shares = allocate(worked, [weight_by_day[d] for d in days])
    return [(d, s) for d, s in zip(days, shares) if s > 0]
