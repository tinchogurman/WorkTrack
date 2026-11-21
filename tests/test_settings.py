from __future__ import annotations

import json
from datetime import datetime

import pytest

from worktrack.core import timeutils as tu
from worktrack.settings import Settings, SettingsStore


@pytest.fixture
def store(tmp_path):
    return SettingsStore(tmp_path / "settings.json")


def test_defaults_when_missing(store):
    s = store.load()
    assert s == Settings()
    assert s.minimize_to_tray and s.confirm_exit_with_active and not s.start_minimized
    assert s.time_format == "24h" and s.export_dir == ""


def test_roundtrip(store):
    store.save(Settings(start_minimized=True, minimize_to_tray=False, time_format="12h", export_dir="D:\\Exports"))
    loaded = store.load()
    assert loaded.start_minimized and not loaded.minimize_to_tray
    assert loaded.time_format == "12h" and loaded.export_dir == "D:\\Exports"
    assert not store.path.with_suffix(".json.tmp").exists()


@pytest.mark.parametrize("content", ["{not json", "[1, 2]", ""])
def test_corrupt_file_falls_back_to_defaults(store, content):
    store.path.write_text(content, encoding="utf-8")
    assert store.load() == Settings()


def test_wrong_types_and_unknown_keys(store):
    store.path.write_text(json.dumps({
        "start_minimized": "yes", "time_format": "25h", "minimize_to_tray": False, "other": 1,
    }), encoding="utf-8")
    s = store.load()
    assert s.start_minimized is False  # wrong type -> default
    assert s.time_format == "24h"  # invalid value -> default
    assert s.minimize_to_tray is False  # valid value kept


@pytest.fixture
def restore_format():
    yield
    tu.set_time_format("24h")


def test_12h_display(restore_format):
    t = datetime(2026, 3, 10, 15, 5, 9)
    assert tu.format_clock(t) == "15:05:09"
    tu.set_time_format("12h")
    assert tu.format_clock(t) == "03:05:09 p. m."
    assert tu.format_clock(t.replace(hour=0)) == "12:05:09 a. m."
    assert tu.format_clock(t.replace(hour=12)) == "12:05:09 p. m."
    # durations are never affected
    assert tu.format_hms(15 * 3600) == "15:00:00"
