from __future__ import annotations

from datetime import datetime, timezone

import pytest

from worktrack.core import timeutils as tu


def test_db_roundtrip_is_utc():
    local = datetime(2026, 3, 10, 10, 0, 0).astimezone()  # aware local
    stored = tu.to_db(local)
    assert stored.endswith("Z") and len(stored) == 20
    assert tu.from_db(stored) == local


def test_to_db_rejects_naive():
    with pytest.raises(ValueError):
        tu.to_db(datetime(2026, 1, 1))


def test_local_naive_to_utc_roundtrip():
    naive = datetime(2026, 3, 10, 23, 30, 15, 999)
    utc = tu.local_naive_to_utc(naive)
    assert utc.tzinfo == timezone.utc and utc.microsecond == 0
    assert tu.to_local(utc).replace(tzinfo=None) == naive.replace(microsecond=0)


@pytest.mark.parametrize(
    "seconds, hms, dec",
    [(0, "00:00:00", "0,00"), (5400, "01:30:00", "1,50"), (3599, "00:59:59", "1,00"),
     (100 * 3600 + 61, "100:01:01", "100,02"), (-5, "00:00:00", "0,00")],
)
def test_formatting(seconds, hms, dec):
    assert tu.format_hms(seconds) == hms
    assert tu.format_decimal_hours(seconds) == dec


def test_decimal_hours_billing_example():
    assert tu.decimal_hours(90 * 60) == 1.5
