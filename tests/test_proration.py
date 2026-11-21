"""Acceptance 5c: sessions crossing midnight are split across local days."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from worktrack.analytics.periods import Period, add_months, week_start
from worktrack.analytics.proration import allocate, split_by_day

BA = ZoneInfo("America/Argentina/Buenos_Aires")  # UTC-3, no DST
MADRID = ZoneInfo("Europe/Madrid")  # has DST


def local(tz, *args):
    return datetime(*args, tzinfo=tz)


def as_dict(parts):
    return {d: s for d, s in parts}


def test_same_day_session():
    parts = split_by_day(local(BA, 2026, 3, 10, 9), local(BA, 2026, 3, 10, 11), tz=BA)
    assert parts == [(date(2026, 3, 10), 7200)]


def test_spec_example_23_to_01():
    parts = split_by_day(local(BA, 2026, 3, 10, 23), local(BA, 2026, 3, 11, 1), tz=BA)
    assert parts == [(date(2026, 3, 10), 3600), (date(2026, 3, 11), 3600)]


def test_cut_is_local_not_utc():
    # 20:00-22:00 in Buenos Aires = 23:00-01:00 UTC: must stay in ONE local day
    start = datetime(2026, 3, 10, 23, 0, tzinfo=timezone.utc)
    parts = split_by_day(start, start + timedelta(hours=2), tz=BA)
    assert parts == [(date(2026, 3, 10), 7200)]
    # and the same instants split in two when viewed from UTC
    assert len(split_by_day(start, start + timedelta(hours=2), tz=timezone.utc)) == 2


def test_more_than_two_days():
    parts = as_dict(split_by_day(local(BA, 2026, 3, 10, 22), local(BA, 2026, 3, 13, 2), tz=BA))
    assert parts == {
        date(2026, 3, 10): 2 * 3600,
        date(2026, 3, 11): 24 * 3600,
        date(2026, 3, 12): 24 * 3600,
        date(2026, 3, 13): 2 * 3600,
    }
    assert sum(parts.values()) == (2 + 24 + 24 + 2) * 3600


def test_boundaries_exactly_at_midnight():
    assert split_by_day(local(BA, 2026, 3, 10, 0), local(BA, 2026, 3, 11, 0), tz=BA) == [
        (date(2026, 3, 10), 86400)
    ]
    assert split_by_day(local(BA, 2026, 3, 10, 23), local(BA, 2026, 3, 11, 0), tz=BA) == [
        (date(2026, 3, 10), 3600)
    ]


def test_zero_length_and_naive():
    t = local(BA, 2026, 3, 10, 10)
    assert split_by_day(t, t, tz=BA) == []
    with pytest.raises(ValueError):
        split_by_day(datetime(2026, 1, 1), datetime(2026, 1, 2), tz=BA)


def test_worked_less_than_elapsed_is_proportional():
    # 3 h elapsed (1 h + 2 h), only 90 min worked -> 30 min + 60 min
    parts = split_by_day(local(BA, 2026, 3, 10, 23), local(BA, 2026, 3, 11, 2), 5400, tz=BA)
    assert parts == [(date(2026, 3, 10), 1800), (date(2026, 3, 11), 3600)]


@pytest.mark.parametrize("worked", [1, 7, 3599, 10_001, 86_399])
def test_sum_is_always_preserved(worked):
    start = local(BA, 2026, 3, 10, 23, 59, 59)
    parts = split_by_day(start, start + timedelta(days=1, seconds=2), worked, tz=BA)
    assert sum(s for _, s in parts) == worked


def test_allocate_largest_remainder():
    assert allocate(10, [1, 1, 1]) == [4, 3, 3]
    assert sum(allocate(7, [0.3, 0.3, 0.4])) == 7
    assert allocate(0, [1, 2]) == [0, 0]


def test_dst_days_have_23_and_25_hours():
    # Madrid: 2026-03-29 has 23 h, 2026-10-25 has 25 h
    spring = as_dict(split_by_day(local(MADRID, 2026, 3, 29, 0), local(MADRID, 2026, 3, 30, 0), tz=MADRID))
    assert spring == {date(2026, 3, 29): 23 * 3600}
    autumn = as_dict(split_by_day(local(MADRID, 2026, 10, 25, 0), local(MADRID, 2026, 10, 26, 0), tz=MADRID))
    assert autumn == {date(2026, 10, 25): 25 * 3600}


# --- week / month / year cuts -----------------------------------------------

def week_totals(parts):
    totals = {}
    for d, s in parts:
        totals[week_start(d)] = totals.get(week_start(d), 0) + s
    return totals


def month_totals(parts):
    totals = {}
    for d, s in parts:
        key = d.replace(day=1)
        totals[key] = totals.get(key, 0) + s
    return totals


def test_week_cut_sunday_to_monday():
    # Sunday 2026-03-15 22:00 -> Monday 2026-03-16 03:00
    parts = split_by_day(local(BA, 2026, 3, 15, 22), local(BA, 2026, 3, 16, 3), tz=BA)
    assert week_totals(parts) == {date(2026, 3, 9): 2 * 3600, date(2026, 3, 16): 3 * 3600}


def test_month_cut():
    parts = split_by_day(local(BA, 2026, 3, 31, 21), local(BA, 2026, 4, 1, 1, 30), tz=BA)
    assert month_totals(parts) == {date(2026, 3, 1): 3 * 3600, date(2026, 4, 1): 5400}


def test_year_cut():
    parts = split_by_day(local(BA, 2026, 12, 31, 23, 30), local(BA, 2027, 1, 1, 0, 45), tz=BA)
    assert month_totals(parts) == {date(2026, 12, 1): 1800, date(2027, 1, 1): 2700}


# --- periods -----------------------------------------------------------------

def test_week_is_monday_to_sunday():
    p = Period.week(date(2026, 11, 20))  # Friday
    assert (p.start, p.end) == (date(2026, 11, 16), date(2026, 11, 22))
    assert p.start.weekday() == 0 and p.days == 7
    assert p.label.startswith("Sem 47")


def test_month_and_year_periods():
    assert (Period.month(date(2026, 2, 14)).start, Period.month(date(2026, 2, 14)).end) == (
        date(2026, 2, 1), date(2026, 2, 28))
    assert Period.month(date(2028, 2, 3)).end == date(2028, 2, 29)
    assert Period.month(date(2026, 11, 20)).label == "noviembre 2026"
    assert Period.year(date(2026, 5, 5)).days == 365
    assert add_months(date(2026, 11, 20), 2) == date(2027, 1, 1)
    assert add_months(date(2026, 1, 31), -1) == date(2025, 12, 1)


def test_period_bounds_are_local_midnights():
    start, end = Period.day(date(2026, 3, 10)).bounds(BA)
    assert start == local(BA, 2026, 3, 10, 0) and end == local(BA, 2026, 3, 11, 0)
    assert start.astimezone(timezone.utc).hour == 3


def test_custom_period_validation():
    with pytest.raises(ValueError):
        Period.custom(date(2026, 3, 10), date(2026, 3, 9))
    assert Period.last_days(date(2026, 3, 10), 30).start == date(2026, 2, 9)
