from __future__ import annotations

from datetime import timedelta

import pytest

from worktrack.core.errors import NotFoundError, OverlapError, ValidationError
from worktrack.services.entry_service import EntryDraft

H = timedelta(hours=1)


def draft(project, start, end, task="Manual", desc=None):
    return EntryDraft(project.id, task, start, end, desc)


@pytest.fixture
def now(clock):
    return clock.now()


def test_add_manual_entry(services, project, now):
    entry = services.entries.add_manual(draft(project, now - 3 * H, now - 2 * H, desc="olvidé"))
    assert entry.duration_seconds == 3600
    assert entry.description == "olvidé"
    views = services.entries.list_entries()
    assert len(views) == 1 and views[0].task_name == "Manual"


@pytest.mark.parametrize("delta", [timedelta(0), -timedelta(minutes=1)])
def test_end_must_be_after_start(services, project, now, delta):
    with pytest.raises(ValidationError, match="posterior"):
        services.entries.add_manual(draft(project, now - H, now - H + delta))


def test_end_in_future_rejected(services, project, now):
    with pytest.raises(ValidationError, match="futuro"):
        services.entries.add_manual(draft(project, now - H, now + timedelta(seconds=1)))


def test_naive_datetimes_rejected(services, project, now):
    with pytest.raises(ValidationError):
        services.entries.add_manual(
            draft(project, (now - H).replace(tzinfo=None), now.replace(tzinfo=None))
        )


# --- overlaps ----------------------------------------------------------------

def test_overlap_rejected(services, project, now):
    services.entries.add_manual(draft(project, now - 3 * H, now - 2 * H))
    with pytest.raises(OverlapError, match="superpone"):
        services.entries.add_manual(draft(project, now - 2.5 * H, now - 1.5 * H))


def test_contained_and_containing_overlaps_rejected(services, project, now):
    services.entries.add_manual(draft(project, now - 3 * H, now - 2 * H))
    with pytest.raises(OverlapError):
        services.entries.add_manual(draft(project, now - 2.8 * H, now - 2.2 * H))
    with pytest.raises(OverlapError):
        services.entries.add_manual(draft(project, now - 4 * H, now - 1 * H))


def test_overlap_applies_across_projects(services, project, other_project, now):
    services.entries.add_manual(draft(project, now - 3 * H, now - 2 * H))
    with pytest.raises(OverlapError):
        services.entries.add_manual(draft(other_project, now - 2.5 * H, now - 1.5 * H))


def test_contiguous_sessions_are_not_overlap(services, project, now):
    services.entries.add_manual(draft(project, now - 3 * H, now - 2 * H))
    services.entries.add_manual(draft(project, now - 2 * H, now - 1 * H))  # starts at previous end
    services.entries.add_manual(draft(project, now - 4 * H, now - 3 * H))  # ends at first start
    assert len(services.entries.list_entries()) == 3


def test_active_session_overlaps_from_start_to_now(services, project, clock):
    start = clock.now()
    services.timer.start(project.id, "ETL")
    clock.advance(hours=2)
    now = clock.now()
    # inside [start, now] -> overlap
    with pytest.raises(OverlapError, match="en curso"):
        services.entries.add_manual(draft(project, start + 0.5 * H, start + H))
    # crossing the active start -> overlap
    with pytest.raises(OverlapError):
        services.entries.add_manual(draft(project, start - H, start + timedelta(seconds=1)))
    # ending at "now" -> overlap
    with pytest.raises(OverlapError):
        services.entries.add_manual(draft(project, now - timedelta(minutes=5), now))


def test_contiguous_with_active_session_start_is_allowed(services, project, clock):
    start = clock.now()
    services.timer.start(project.id, "ETL")
    clock.advance(hours=1)
    services.entries.add_manual(draft(project, start - H, start))
    assert len(services.entries.list_entries()) == 2


def test_active_range_grows_with_time(services, project, clock):
    """A slot free when the session started is occupied once 'now' passes it."""
    services.timer.start(project.id, "ETL")
    clock.advance(minutes=30)
    with pytest.raises(OverlapError):
        services.entries.add_manual(draft(project, clock.now() - timedelta(minutes=10), clock.now()))


def test_edit_does_not_overlap_with_itself(services, project, now):
    entry = services.entries.add_manual(draft(project, now - 3 * H, now - 2 * H))
    updated = services.entries.update_entry(entry.id, draft(project, now - 3 * H, now - 1.5 * H))
    assert updated.duration_seconds == int(1.5 * 3600)


def test_edit_into_other_session_rejected(services, project, now):
    a = services.entries.add_manual(draft(project, now - 3 * H, now - 2 * H))
    services.entries.add_manual(draft(project, now - 2 * H, now - 1 * H))
    with pytest.raises(OverlapError):
        services.entries.update_entry(a.id, draft(project, now - 3 * H, now - 1.5 * H))


# --- edit / delete -----------------------------------------------------------

def test_edit_recalculates_duration(services, project, now):
    entry = services.entries.add_manual(draft(project, now - 3 * H, now - 2 * H))
    new_start, new_end = now - 5 * H, now - 4 * H + timedelta(minutes=30)
    duration = services.entries.validate(draft(project, new_start, new_end), entry.id)
    assert duration == 5400  # preview shown in the dialog before saving
    updated = services.entries.update_entry(entry.id, draft(project, new_start, new_end, "Otra", "x"))
    assert updated.duration_seconds == 5400
    assert updated.end_time - updated.start_time == timedelta(seconds=5400)
    assert services.entries.get_view(entry.id).task_name == "Otra"


def test_edit_can_move_to_other_project(services, project, other_project, now):
    entry = services.entries.add_manual(draft(project, now - 3 * H, now - 2 * H))
    updated = services.entries.update_entry(
        entry.id, draft(other_project, now - 3 * H, now - 2 * H, task="Refactor")
    )
    view = services.entries.get_view(updated.id)
    assert view.project_name == "Desarrollo Python" and view.task_name == "Refactor"


def test_active_session_not_editable_nor_deletable(services, project, clock):
    entry = services.timer.start(project.id, "ETL")
    clock.advance(hours=1)
    with pytest.raises(ValidationError, match="en curso"):
        services.entries.update_entry(entry.id, draft(project, clock.now() - H, clock.now()))
    with pytest.raises(ValidationError, match="en curso"):
        services.entries.delete_entry(entry.id)


def test_delete_entry(services, project, now):
    entry = services.entries.add_manual(draft(project, now - 3 * H, now - 2 * H))
    services.entries.delete_entry(entry.id)
    assert services.entries.list_entries() == []
    with pytest.raises(NotFoundError):
        services.entries.delete_entry(entry.id)


def test_archived_project_history_kept_and_editable(services, project, other_project, now):
    entry = services.entries.add_manual(draft(project, now - 3 * H, now - 2 * H))
    services.projects.set_project_archived(project.id, True)
    views = services.entries.list_entries()
    assert len(views) == 1 and views[0].project_archived
    # editing an existing entry of an archived project is allowed (same task)
    services.entries.update_entry(entry.id, draft(project, now - 3 * H, now - 2.5 * H, desc="fix"))
    # but new entries cannot use it, and new tasks cannot be created in it
    with pytest.raises(ValidationError, match="archivado"):
        services.entries.add_manual(draft(project, now - 6 * H, now - 5 * H))
    with pytest.raises(ValidationError, match="archivado"):
        services.entries.update_entry(entry.id, draft(project, now - 3 * H, now - 2 * H, task="Nueva"))


def test_failed_manual_add_leaves_no_task(services, project, now):
    services.entries.add_manual(draft(project, now - 3 * H, now - 2 * H))
    with pytest.raises(OverlapError):
        services.entries.add_manual(draft(project, now - 2.5 * H, now - H, task="Fantasma"))
    assert "Fantasma" not in [t.name for t in services.projects.list_tasks(project.id)]
