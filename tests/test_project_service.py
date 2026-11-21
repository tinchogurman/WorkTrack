from __future__ import annotations

from datetime import timedelta

import pytest

from worktrack.core.errors import DuplicateNameError, InUseError, NotFoundError, ValidationError
from worktrack.services.entry_service import EntryDraft


def test_create_and_list_projects(services):
    services.projects.create_project("Zeta", "#112233")
    services.projects.create_project("alfa", "#aabbcc")
    projects = services.projects.list_projects()
    assert [p.name for p in projects] == ["alfa", "Zeta"]
    assert projects[0].color == "#AABBCC"


@pytest.mark.parametrize("name", ["", "   ", "x" * 101])
def test_invalid_project_names(services, name):
    with pytest.raises(ValidationError):
        services.projects.create_project(name, "#112233")


@pytest.mark.parametrize("color", ["", "red", "#12345", "#GGGGGG", "112233"])
def test_invalid_colors(services, color):
    with pytest.raises(ValidationError):
        services.projects.create_project("P", color)


def test_duplicate_project_name_case_insensitive(services, project):
    with pytest.raises(DuplicateNameError):
        services.projects.create_project("data engineering", "#112233")


def test_update_project(services, project, other_project):
    updated = services.projects.update_project(project.id, "DE", "#000000")
    assert (updated.name, updated.color) == ("DE", "#000000")
    with pytest.raises(DuplicateNameError):
        services.projects.update_project(project.id, other_project.name, "#000000")
    # renaming to itself with different case is fine
    services.projects.update_project(project.id, "de", "#000000")


def test_archive_and_unarchive(services, project):
    services.projects.set_project_archived(project.id, True)
    assert services.projects.list_projects() == []
    assert [p.archived for p in services.projects.list_projects(include_archived=True)] == [True]
    services.projects.set_project_archived(project.id, False)
    assert len(services.projects.list_projects()) == 1


def test_delete_project_without_sessions_removes_tasks_too(services, project):
    services.projects.create_task(project.id, "T1")
    services.projects.delete_project(project.id)
    assert services.projects.list_projects(include_archived=True) == []
    with pytest.raises(NotFoundError):
        services.projects.get_project(project.id)


def test_delete_project_with_sessions_blocked(services, project, clock):
    services.timer.start(project.id, "T1")
    clock.advance(seconds=5)
    services.timer.stop()
    with pytest.raises(InUseError, match="archivarlo"):
        services.projects.delete_project(project.id)
    assert services.projects.get_project(project.id)


def test_tasks_crud(services, project, other_project):
    task = services.projects.create_task(project.id, "Review", "PRs")
    assert task.description == "PRs"
    services.projects.create_task(other_project.id, "Review")  # same name, other project: ok
    with pytest.raises(DuplicateNameError):
        services.projects.create_task(project.id, "REVIEW")
    updated = services.projects.update_task(task.id, "Code review", None)
    assert updated.name == "Code review" and updated.description is None
    services.projects.set_task_archived(task.id, True)
    assert services.projects.list_tasks(project.id) == []
    assert len(services.projects.list_tasks(project.id, include_archived=True)) == 1
    services.projects.delete_task(task.id)
    assert services.projects.list_tasks(project.id, include_archived=True) == []


def test_delete_task_with_sessions_blocked(services, project, clock):
    now = clock.now()
    entry = services.entries.add_manual(
        EntryDraft(project.id, "T1", now - timedelta(hours=1), now)
    )
    with pytest.raises(InUseError, match="archivarla"):
        services.projects.delete_task(entry.task_id)


def test_cannot_create_task_in_archived_project(services, project):
    services.projects.set_project_archived(project.id, True)
    with pytest.raises(ValidationError):
        services.projects.create_task(project.id, "X")


def test_suggest_color_skips_used(services):
    first = services.projects.suggest_color()
    services.projects.create_project("A", first)
    assert services.projects.suggest_color() != first
