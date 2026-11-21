"""Calendar periods in local time. Weeks run Monday to Sunday (ISO)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta, tzinfo

from worktrack.analytics.proration import local_midnight

MONTHS_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def month_start(day: date) -> date:
    return day.replace(day=1)


def add_months(day: date, months: int) -> date:
    """First day of the month `months` away from `day`'s month."""
    index = day.year * 12 + (day.month - 1) + months
    return date(index // 12, index % 12 + 1, 1)


def month_end(day: date) -> date:
    return add_months(day, 1) - timedelta(days=1)


def fmt_date(day: date) -> str:
    return day.strftime("%d/%m/%Y")


def week_label(start: date) -> str:
    end = start + timedelta(days=6)
    return f"Sem {start.isocalendar().week} ({start:%d/%m}–{end:%d/%m})"


def month_label(day: date) -> str:
    return f"{MONTHS_ES[day.month - 1]} {day.year}"


@dataclass(frozen=True)
class Period:
    """Inclusive range of local calendar days."""

    start: date
    end: date
    label: str

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError("El fin del período no puede ser anterior al inicio.")

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def iter_days(self) -> Iterator[date]:
        for i in range(self.days):
            yield self.start + timedelta(days=i)

    def contains(self, day: date) -> bool:
        return self.start <= day <= self.end

    def bounds(self, tz: tzinfo | None = None) -> tuple[datetime, datetime]:
        """Aware [start, end) instants: local midnight of start to local midnight after end."""
        return local_midnight(self.start, tz), local_midnight(self.end + timedelta(days=1), tz)

    # --- constructors ------------------------------------------------------
    @classmethod
    def day(cls, day: date) -> "Period":
        return cls(day, day, fmt_date(day))

    @classmethod
    def week(cls, day: date) -> "Period":
        start = week_start(day)
        return cls(start, start + timedelta(days=6), week_label(start))

    @classmethod
    def month(cls, day: date) -> "Period":
        return cls(month_start(day), month_end(day), month_label(day))

    @classmethod
    def year(cls, day: date) -> "Period":
        return cls(date(day.year, 1, 1), date(day.year, 12, 31), str(day.year))

    @classmethod
    def last_days(cls, today: date, n: int) -> "Period":
        return cls(today - timedelta(days=n - 1), today, f"Últimos {n} días")

    @classmethod
    def custom(cls, start: date, end: date) -> "Period":
        if end < start:
            raise ValueError("La fecha 'hasta' no puede ser anterior a 'desde'.")
        return cls(start, end, f"{fmt_date(start)} – {fmt_date(end)}")
