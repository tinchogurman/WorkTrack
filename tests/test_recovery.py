"""Acceptance 5: unexpected shutdown with an active session, then reopen."""

from __future__ import annotations

from datetime import timedelta

import pytest

from worktrack.core.errors import NoActiveSessionError, ValidationError
from worktrack.services.context import AppServices


def crash_and_reopen(services, db_file, clock, downtime):
    """Simulate a crash: drop the connection without stopping, reopen later."""
    services.conn.close()
    clock.advance(**downtime)
    return AppServices.open(db_file, clock)


@pytest.fixture
def crashed(services, project, db_file, clock):
    services.timer.start(project.id, "ETL", "antes del corte")
    clock.advance(minutes=10)
    services.timer.heartbeat()  # last moment the app was alive: start + 10 min
    reopened = crash_and_reopen(services, db_file, clock, {"hours": 3})
    yield reopened
    reopened.close()


def test_no_recovery_when_nothing_active(services):
    assert services.recovery.check() is None


def test_recovery_reports_start_and_last_seen(crashed, clock):
    info = crashed.recovery.check()
    assert info is not None
    assert info.view.task_name == "ETL"
    assert info.seconds_to_last_seen == 600
    assert info.unseen_seconds == 3 * 3600
    assert info.seconds_to_now == 600 + 3 * 3600
    assert info.now == clock.now()


def test_history_survives_reopen(services, project, db_file, clock):
    services.timer.start(project.id, "ETL")
    clock.advance(seconds=42)
    services.timer.stop()
    services.close()
    reopened = AppServices.open(db_file, clock)
    try:
        views = reopened.entries.list_entries()
        assert len(views) == 1 and views[0].entry.duration_seconds == 42
    finally:
        reopened.close()


def test_continue_keeps_original_start(crashed, clock):
    original = crashed.timer.get_active()
    entry = crashed.recovery.continue_session()
    assert entry.id == original.id and entry.start_time == original.start_time
    assert entry.last_heartbeat == clock.now()
    assert crashed.recovery.check() is not None  # still running


def test_finish_at_last_seen(crashed):
    entry = crashed.recovery.finish_at_last_seen()
    assert entry.duration_seconds == 600
    assert crashed.timer.get_active() is None


def test_finish_at_custom_time(crashed):
    start = crashed.timer.get_active().start_time
    entry = crashed.recovery.finish_at(start + timedelta(minutes=45))
    assert entry.duration_seconds == 45 * 60


def test_finish_at_invalid_times(crashed, clock):
    start = crashed.timer.get_active().start_time
    with pytest.raises(ValidationError, match="anterior"):
        crashed.recovery.finish_at(start - timedelta(seconds=1))
    with pytest.raises(ValidationError, match="futuro"):
        crashed.recovery.finish_at(clock.now() + timedelta(minutes=1))
    with pytest.raises(ValidationError):
        crashed.recovery.finish_at((start + timedelta(minutes=1)).replace(tzinfo=None))
    assert crashed.timer.get_active() is not None  # nothing was closed


def test_missing_heartbeat_falls_back_to_start(services, project, db_file, clock):
    entry = services.timer.start(project.id, "ETL")
    services.conn.execute("UPDATE time_entries SET last_heartbeat = NULL WHERE id = ?", (entry.id,))
    reopened = crash_and_reopen(services, db_file, clock, {"hours": 1})
    try:
        info = reopened.recovery.check()
        assert info.last_seen == entry.start_time
        assert reopened.recovery.finish_at_last_seen().duration_seconds == 0
    finally:
        reopened.close()


def test_recovery_actions_without_active(services):
    with pytest.raises(NoActiveSessionError):
        services.recovery.continue_session()
    with pytest.raises(NoActiveSessionError):
        services.recovery.finish_at_last_seen()
