"""Acceptance 5d: a suspension during an active session is detected and is
NOT discounted without the user's confirmation."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta

import pytest

from worktrack.analytics.periods import Period
from worktrack.core.errors import ValidationError
from worktrack.db.connection import connect
from worktrack.db.migrations import SCHEMA_VERSION, migrate
from worktrack.db.schema import SCHEMA_V1
from worktrack.services.context import AppServices
from worktrack.services.entry_service import EntryDraft

from conftest import BA

MIN = 60
H = 3600


@pytest.fixture
def running(services, project, clock):
    """Session started at 14:00; heartbeats until 15:00; machine sleeps until 18:00."""
    clock.set(datetime(2026, 3, 10, 14, 0, tzinfo=BA))
    entry = services.timer.start(project.id, "ETL")
    for _ in range(120):  # every 30 s for one hour
        clock.advance(seconds=30)
        services.timer.heartbeat()
    clock.set(datetime(2026, 3, 10, 18, 0, tzinfo=BA))  # resume after 3 h asleep
    return entry


def beat(services):
    b = services.timer.heartbeat()
    return services.interruptions.check_heartbeat(b.previous, b.current)


def test_suspension_detected_with_bounds(services, running):
    found = beat(services)
    assert found is not None and found.is_pending and found.source == "heartbeat_gap"
    assert found.start_time == datetime(2026, 3, 10, 15, 0, tzinfo=BA)
    assert found.end_time == datetime(2026, 3, 10, 18, 0, tzinfo=BA)
    assert found.seconds == 3 * H


def test_not_discounted_without_confirmation(services, running):
    beat(services)
    active = services.timer.get_active()
    assert services.timer.elapsed_seconds(active) == 4 * H  # still counts the 3 h
    done = services.timer.stop()
    assert done.duration_seconds == 4 * H
    assert services.interruptions.pending_for_entry(done.id)[0].is_pending


def test_regular_heartbeats_and_short_gaps_ignored(services, project, clock):
    services.timer.start(project.id, "ETL")
    clock.advance(seconds=30)
    assert beat(services) is None
    clock.advance(minutes=4, seconds=59)
    assert beat(services) is None
    assert services.interruptions.list_for_entry(services.timer.get_active().id) == []


def test_keep(services, running):
    found = beat(services)
    kept = services.interruptions.keep(found.id)
    assert kept.status == "kept" and kept.discounted_interval is None
    assert services.timer.stop().duration_seconds == 4 * H


def test_discount_detected_interval(services, running, clock):
    found = beat(services)
    services.interruptions.discount(found.id)
    active = services.timer.get_active()
    assert services.timer.elapsed_seconds(active) == 1 * H  # live stopwatch reflects it
    clock.advance(minutes=30)
    done = services.timer.stop()
    assert done.duration_seconds == int(1.5 * H)
    assert (done.end_time - done.start_time) == timedelta(hours=4, minutes=30)  # elapsed kept


def test_adjust_manual_range(services, running):
    found = beat(services)
    start = datetime(2026, 3, 10, 15, 30, tzinfo=BA)
    end = datetime(2026, 3, 10, 17, 30, tzinfo=BA)
    adjusted = services.interruptions.adjust(found.id, start, end)
    assert adjusted.status == "adjusted" and adjusted.discounted_interval == (start, end)
    assert services.timer.stop().duration_seconds == 2 * H


def test_adjust_validation(services, running):
    found = beat(services)
    with pytest.raises(ValidationError, match="posterior"):
        services.interruptions.adjust(found.id, found.end_time, found.start_time)
    with pytest.raises(ValidationError, match="dentro de la sesión"):
        services.interruptions.adjust(found.id, found.start_time - timedelta(hours=2), found.end_time)
    assert services.interruptions.pending_for_entry(found.entry_id)  # unchanged


def test_decision_after_stop_recomputes_duration(services, running):
    found = beat(services)
    done = services.timer.stop()
    assert done.duration_seconds == 4 * H
    services.interruptions.discount(found.id)
    assert services.entries.get_view(done.id).entry.duration_seconds == 1 * H
    services.interruptions.keep(found.id)  # change of mind
    assert services.entries.get_view(done.id).entry.duration_seconds == 4 * H


def test_power_events_refine_heartbeat_detection(services, running):
    found = beat(services)  # 15:00 -> 18:00 (last heartbeat based)
    exact = services.interruptions.record_power_gap(
        datetime(2026, 3, 10, 15, 0, 20, tzinfo=BA), datetime(2026, 3, 10, 17, 59, 50, tzinfo=BA)
    )
    assert exact.id == found.id and exact.source == "power_event"
    assert exact.start_time.second == 20
    assert len(services.interruptions.list_for_entry(found.entry_id)) == 1


def test_power_event_first_then_heartbeat_no_duplicate(services, running):
    services.interruptions.record_power_gap(
        datetime(2026, 3, 10, 15, 0, 10, tzinfo=BA), datetime(2026, 3, 10, 18, 0, tzinfo=BA)
    )
    assert beat(services) is None
    assert len(services.interruptions.list_for_entry(services.timer.get_active().id)) == 1


def test_power_gap_clipped_to_session_and_ignored_when_idle(services, project, clock):
    assert services.interruptions.record_power_gap(clock.now() - timedelta(hours=1), clock.now()) is None
    services.timer.start(project.id, "X")
    clock.advance(hours=1)
    found = services.interruptions.record_power_gap(clock.now() - timedelta(hours=5), clock.now())
    assert found.seconds == H  # clipped to the session start


def test_edit_entry_keeps_discount(services, running, clock):
    found = beat(services)
    services.interruptions.discount(found.id)
    done = services.timer.stop()  # 14:00-18:00, 3 h discounted -> 1 h
    view = services.entries.get_view(done.id)
    draft = EntryDraft(view.entry.project_id, "ETL", done.start_time - timedelta(hours=1), done.end_time)
    assert services.entries.validate(draft, done.id) == 2 * H  # 13:00-18:00 minus 3 h
    assert services.entries.update_entry(done.id, draft).duration_seconds == 2 * H
    # shrinking the range clips the discount: 14:00-16:00 -> 1 h worked, 1 h discounted
    draft2 = EntryDraft(view.entry.project_id, "ETL", done.start_time, done.start_time + timedelta(hours=2))
    assert services.entries.update_entry(done.id, draft2).duration_seconds == 1 * H


def test_exact_proration_excludes_discounted_night(services, project, clock):
    clock.set(datetime(2026, 3, 10, 22, 0, tzinfo=BA))
    services.timer.start(project.id, "Deploy")
    clock.set(datetime(2026, 3, 10, 23, 30, tzinfo=BA))
    services.timer.heartbeat()
    clock.set(datetime(2026, 3, 11, 7, 30, tzinfo=BA))  # slept overnight
    found = beat(services)
    services.interruptions.discount(found.id)
    clock.set(datetime(2026, 3, 11, 8, 0, tzinfo=BA))
    done = services.timer.stop()
    assert done.duration_seconds == 2 * H
    d = services.analytics.dashboard(Period.custom(date(2026, 3, 10), date(2026, 3, 11)))
    per_day = dict(zip(d.per_day["date"], d.per_day["seconds"]))
    # exact: 22:00-23:30 on day 1, 07:30-08:00 on day 2 (not a proportional split)
    assert per_day == {date(2026, 3, 10): int(1.5 * H), date(2026, 3, 11): 30 * MIN}


def test_delete_entry_cascades(services, running):
    found = beat(services)
    done = services.timer.stop()
    services.entries.delete_entry(done.id)
    assert services.interruptions.repo.get(found.id) is None


def test_database_rejects_inconsistent_interruptions(services, running):
    found = beat(services)
    with pytest.raises(sqlite3.IntegrityError):
        services.conn.execute("UPDATE session_interruptions SET status = 'discounted' WHERE id = ?", (found.id,))
    with pytest.raises(sqlite3.IntegrityError):
        services.conn.execute(
            "UPDATE session_interruptions SET end_time = start_time WHERE id = ?", (found.id,)
        )


def test_migration_from_v1(tmp_path, clock):
    path = tmp_path / "v1.db"
    conn = connect(path)
    conn.executescript(f"BEGIN; {SCHEMA_V1} PRAGMA user_version = 1; COMMIT;")
    conn.execute("INSERT INTO projects (name, color, created_at) VALUES ('P', '#112233', '2026-01-01T00:00:00Z')")
    conn.close()
    app = AppServices.open(path, clock, BA)
    try:
        assert app.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 2
        assert [p.name for p in app.projects.list_projects()] == ["P"]
        assert migrate(app.conn) == 2
    finally:
        app.close()
