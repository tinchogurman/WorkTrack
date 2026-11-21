"""Time conversions and formatting.

Storage format: UTC, fixed width 'YYYY-MM-DDTHH:MM:SSZ' (sorts lexically).
Display: local time zone of the operating system.
"""

from __future__ import annotations

from datetime import datetime, timezone

DB_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def to_db(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("Naive datetimes are not allowed; use aware datetimes")
    return value.astimezone(timezone.utc).strftime(DB_FORMAT)


def from_db(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.strptime(value, DB_FORMAT).replace(tzinfo=timezone.utc)


def to_local(value: datetime) -> datetime:
    """Aware datetime -> aware datetime in the system's local time zone."""
    return value.astimezone()


def local_naive_to_utc(value: datetime) -> datetime:
    """Naive wall-clock time (as typed by the user) -> aware UTC, second precision."""
    if value.tzinfo is not None:
        raise ValueError("Expected a naive local datetime")
    return value.astimezone(timezone.utc).replace(microsecond=0)


def seconds_between(start: datetime, end: datetime) -> int:
    return int((end - start).total_seconds())


def format_hms(seconds: int | float) -> str:
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def decimal_hours(seconds: int | float) -> float:
    return round(max(0, seconds) / 3600, 2)


def format_decimal_hours(seconds: int | float) -> str:
    """1h30m -> '1,50' (comma decimal separator, as used for billing)."""
    return f"{decimal_hours(seconds):.2f}".replace(".", ",")


def format_local_date(value: datetime) -> str:
    return to_local(value).strftime("%d/%m/%Y")


_clock_12h = False  # display preference (Settings); exports always use 24 h


def set_time_format(fmt: str) -> None:
    global _clock_12h
    _clock_12h = fmt == "12h"


def is_12h() -> bool:
    return _clock_12h


def format_clock(value: datetime) -> str:
    """Wall-clock time of an (already local) datetime, honoring the 12/24 h preference."""
    if not _clock_12h:
        return f"{value.hour:02d}:{value.minute:02d}:{value.second:02d}"
    hour = value.hour % 12 or 12
    suffix = "a. m." if value.hour < 12 else "p. m."
    return f"{hour:02d}:{value.minute:02d}:{value.second:02d} {suffix}"


def format_local_time(value: datetime) -> str:
    return format_clock(to_local(value))


def format_local_end_time(start: datetime, end: datetime) -> str:
    """End time, marked '(+N)' when it falls N local days after the start."""
    days = (to_local(end).date() - to_local(start).date()).days
    text = format_local_time(end)
    return f"{text} (+{days})" if days > 0 else text


def format_local_datetime(value: datetime) -> str:
    local = to_local(value)
    return f"{local:%d/%m/%Y} {format_clock(local)}"
