from __future__ import annotations

from datetime import timedelta

import pytest

from worktrack.core.errors import (
    ActiveSessionExistsError,
    NoActiveSessionError,
    OverlapError,
    ValidationError,
)
from worktrack.services.entry_service import EntryDraft
from worktrack.services.context import AppServices


def test_start_persists_immediately(services, project, db_file):
    entry = services.timer.start(project.id, "ETL nightly", "notas")
    assert entry.is_active and entry.end_time is None
    # visible from a brand new connection: written to disk, not only in memory
    other = AppServices.open(db_file, services.clock)
    try:
        active = other.timer.get_active()
        assert active is not None and active.id == entry.id
        assert active.description == "notas"
    finally:
        other.close()


def test_stop_records_exact_duration(services, project, clock):
    entry = services.timer.start(project.id, "ETL")
    clock.advance(seconds=7)
    assert services.timer.elapsed_seconds(services.timer.get_active()) == 7
    done = services.timer.stop()
    assert done.id == entry.id
    assert done.duration_seconds == 7
    assert done.end_time - done.start_time == timedelta(seconds=7)
    assert services.timer.get_active() is None


def test_elapsed_comes_from_timestamps_not_a_counter(services, project, clock):
    """Minimized/no UI ticks for an hour: elapsed is still right."""
    services.timer.start(project.id, "ETL")
    clock.advance(hours=1, seconds=5)
    assert services.timer.elapsed_seconds(services.timer.get_active()) == 3605


def test_cannot_start_two_sessions(services, project, other_project):
    services.timer.start(project.id, "ETL")
    with pytest.raises(ActiveSessionExistsError):
        services.timer.start(other_project.id, "Otra")


def test_change_task_requires_stop_first(services, project, clock):
    services.timer.start(project.id, "A")
    clock.advance(minutes=10)
    services.timer.stop()
    clock.advance(seconds=1)
    second = services.timer.start(project.id, "B")
    assert second.is_active


def test_start_creates_task_on_the_fly_and_reuses_it(services, project, clock):
    first = services.timer.start(project.id, "  Code   review ")
    clock.advance(seconds=5)
    services.timer.stop()
    second = services.timer.start(project.id, "code review")
    assert first.task_id == second.task_id
    assert [t.name for t in services.projects.list_tasks(project.id)] == ["Code review"]


def test_start_requires_task_name(services, project):
    with pytest.raises(ValidationError):
        services.timer.start(project.id, "   ")


def test_archived_project_not_startable(services, project):
    services.projects.set_project_archived(project.id, True)
    with pytest.raises(ValidationError, match="archivado"):
        services.timer.start(project.id, "X")
    assert services.projects.list_projects() == []


def test_archived_task_not_startable(services, project):
    task = services.projects.create_task(project.id, "Vieja")
    services.projects.set_task_archived(task.id, True)
    with pytest.raises(ValidationError, match="archivada"):
        services.timer.start(project.id, "vieja")


def test_stop_without_active(services):
    with pytest.raises(NoActiveSessionError):
        services.timer.stop()


def test_clock_backwards_never_gives_negative_duration(services, project, clock):
    services.timer.start(project.id, "ETL")
    clock.advance(seconds=-30)
    done = services.timer.stop()
    assert done.duration_seconds == 0


def test_cannot_start_if_entries_exist_after_now(services, project, clock):
    services.entries.add_manual(
        EntryDraft(project.id, "X", clock.now() - timedelta(hours=1), clock.now())
    )
    clock.advance(seconds=-600)  # system clock moved back 10 min
    with pytest.raises(OverlapError):
        services.timer.start(project.id, "ETL")


def test_heartbeat_updates_last_seen(services, project, clock):
    assert services.timer.heartbeat() is None
    entry = services.timer.start(project.id, "ETL")
    assert entry.last_heartbeat == entry.start_time
    clock.advance(seconds=30)
    beat = services.timer.heartbeat()
    assert beat.previous == entry.start_time and beat.current == clock.now()
    assert services.timer.get_active().last_heartbeat == clock.now()


def test_update_active_description(services, project):
    services.timer.start(project.id, "ETL")
    services.timer.update_active_description("  revisar logs ")
    assert services.timer.get_active().description == "revisar logs"
    services.timer.update_active_description("")
    assert services.timer.get_active().description is None


def test_cannot_archive_project_or_task_in_use(services, project):
    entry = services.timer.start(project.id, "ETL")
    with pytest.raises(ValidationError):
        services.projects.set_project_archived(project.id, True)
    with pytest.raises(ValidationError):
        services.projects.set_task_archived(entry.task_id, True)


def test_failed_start_leaves_no_orphan_task(services, project):
    services.timer.start(project.id, "ETL")
    with pytest.raises(ActiveSessionExistsError):
        services.timer.start(project.id, "Nueva tarea")
    assert [t.name for t in services.projects.list_tasks(project.id)] == ["ETL"]
