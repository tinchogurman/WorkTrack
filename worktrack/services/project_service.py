"""Business rules for projects and tasks."""

from __future__ import annotations

import logging
import re
import sqlite3

from worktrack.core.clock import Clock
from worktrack.core.errors import DuplicateNameError, InUseError, NotFoundError, ValidationError
from worktrack.core.models import Project, Task
from worktrack.db.connection import transaction
from worktrack.db.errors import integrity_errors
from worktrack.repositories.entries import EntryRepository
from worktrack.repositories.projects import ProjectRepository
from worktrack.repositories.tasks import TaskRepository

log = logging.getLogger(__name__)

NAME_MAX_LEN = 100
DESCRIPTION_MAX_LEN = 1000
COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

# Default palette offered in the UI (readable on a dark background).
PALETTE = [
    "#22C55E", "#3B82F6", "#F59E0B", "#EF4444", "#A855F7",
    "#06B6D4", "#EC4899", "#84CC16", "#F97316", "#64748B",
]


def clean_name(value: str | None, what: str) -> str:
    name = " ".join((value or "").split())
    if not name:
        raise ValidationError(f"El nombre de {what} no puede estar vacío.")
    if len(name) > NAME_MAX_LEN:
        raise ValidationError(f"El nombre de {what} no puede superar {NAME_MAX_LEN} caracteres.")
    return name


def clean_optional_text(value: str | None, max_len: int = DESCRIPTION_MAX_LEN) -> str | None:
    text = (value or "").strip()
    if len(text) > max_len:
        raise ValidationError(f"La descripción no puede superar {max_len} caracteres.")
    return text or None


def clean_color(value: str | None) -> str:
    color = (value or "").strip()
    if not COLOR_RE.match(color):
        raise ValidationError("El color debe tener el formato #RRGGBB.")
    return color.upper()


class ProjectService:
    def __init__(self, conn: sqlite3.Connection, clock: Clock) -> None:
        self.conn = conn
        self.clock = clock
        self.projects = ProjectRepository(conn)
        self.tasks = TaskRepository(conn)
        self.entries = EntryRepository(conn)

    # --- projects ----------------------------------------------------------
    def list_projects(self, include_archived: bool = False) -> list[Project]:
        return self.projects.list(include_archived)

    def get_project(self, project_id: int) -> Project:
        project = self.projects.get(project_id)
        if project is None:
            raise NotFoundError("El proyecto no existe.")
        return project

    def suggest_color(self) -> str:
        used = {p.color.upper() for p in self.projects.list(include_archived=True)}
        for color in PALETTE:
            if color not in used:
                return color
        return PALETTE[len(used) % len(PALETTE)]

    def create_project(self, name: str, color: str) -> Project:
        name, color = clean_name(name, "el proyecto"), clean_color(color)
        with integrity_errors(), transaction(self.conn):
            if self.projects.find_by_name(name):
                raise DuplicateNameError(f"Ya existe un proyecto llamado «{name}».")
            project_id = self.projects.create(name, color, self.clock.now())
        log.info("Project created id=%s", project_id)
        return self.get_project(project_id)

    def update_project(self, project_id: int, name: str, color: str) -> Project:
        name, color = clean_name(name, "el proyecto"), clean_color(color)
        with integrity_errors(), transaction(self.conn):
            self.get_project(project_id)
            other = self.projects.find_by_name(name)
            if other and other.id != project_id:
                raise DuplicateNameError(f"Ya existe un proyecto llamado «{name}».")
            self.projects.update(project_id, name, color)
        return self.get_project(project_id)

    def set_project_archived(self, project_id: int, archived: bool) -> Project:
        with integrity_errors(), transaction(self.conn):
            self.get_project(project_id)
            active = self.entries.get_active()
            if archived and active and active.project_id == project_id:
                raise ValidationError(
                    "No se puede archivar un proyecto con una sesión en curso. Detenela primero."
                )
            self.projects.set_archived(project_id, archived)
        log.info("Project id=%s archived=%s", project_id, archived)
        return self.get_project(project_id)

    def delete_project(self, project_id: int) -> None:
        """Physical delete, only when no sessions reference the project (its tasks go too)."""
        restrict = InUseError(
            "El proyecto tiene sesiones registradas y no se puede eliminar. Podés archivarlo."
        )
        with integrity_errors(fk_error=restrict), transaction(self.conn):
            self.get_project(project_id)
            count = self.projects.count_entries(project_id)
            if count:
                raise InUseError(
                    f"El proyecto tiene {count} sesión(es) registrada(s) y no se puede eliminar. "
                    "Podés archivarlo."
                )
            self.tasks.delete_for_project(project_id)
            self.projects.delete(project_id)
        log.info("Project deleted id=%s", project_id)

    # --- tasks -------------------------------------------------------------
    def list_tasks(self, project_id: int, include_archived: bool = False) -> list[Task]:
        return self.tasks.list_for_project(project_id, include_archived)

    def get_task(self, task_id: int) -> Task:
        task = self.tasks.get(task_id)
        if task is None:
            raise NotFoundError("La tarea no existe.")
        return task

    def create_task(self, project_id: int, name: str, description: str | None = None) -> Task:
        name = clean_name(name, "la tarea")
        description = clean_optional_text(description)
        with integrity_errors(), transaction(self.conn):
            project = self.get_project(project_id)
            if project.archived:
                raise ValidationError("No se pueden crear tareas en un proyecto archivado.")
            if self.tasks.find_by_name(project_id, name):
                raise DuplicateNameError(f"Ya existe la tarea «{name}» en este proyecto.")
            task_id = self.tasks.create(project_id, name, description, self.clock.now())
        return self.get_task(task_id)

    def update_task(self, task_id: int, name: str, description: str | None) -> Task:
        name = clean_name(name, "la tarea")
        description = clean_optional_text(description)
        with integrity_errors(), transaction(self.conn):
            task = self.get_task(task_id)
            other = self.tasks.find_by_name(task.project_id, name)
            if other and other.id != task_id:
                raise DuplicateNameError(f"Ya existe la tarea «{name}» en este proyecto.")
            self.tasks.update(task_id, name, description)
        return self.get_task(task_id)

    def set_task_archived(self, task_id: int, archived: bool) -> Task:
        with integrity_errors(), transaction(self.conn):
            self.get_task(task_id)
            active = self.entries.get_active()
            if archived and active and active.task_id == task_id:
                raise ValidationError(
                    "No se puede archivar una tarea con una sesión en curso. Detenela primero."
                )
            self.tasks.set_archived(task_id, archived)
        return self.get_task(task_id)

    def delete_task(self, task_id: int) -> None:
        restrict = InUseError(
            "La tarea tiene sesiones registradas y no se puede eliminar. Podés archivarla."
        )
        with integrity_errors(fk_error=restrict), transaction(self.conn):
            self.get_task(task_id)
            count = self.tasks.count_entries(task_id)
            if count:
                raise InUseError(
                    f"La tarea tiene {count} sesión(es) registrada(s) y no se puede eliminar. "
                    "Podés archivarla."
                )
            self.tasks.delete(task_id)
        log.info("Task deleted id=%s", task_id)

    # --- helpers for other services (run inside the caller's transaction) --
    def resolve_task_in_tx(
        self, project_id: int, task_name: str, *, keep_task_id: int | None = None
    ) -> Task:
        """Find the task by name in the project, creating it if it does not exist.

        `keep_task_id`: when editing an entry, its current task is accepted even
        if archived (historical data stays editable).
        """
        name = clean_name(task_name, "la tarea")
        project = self.get_project(project_id)
        task = self.tasks.find_by_name(project_id, name)
        if task is not None:
            if task.archived and task.id != keep_task_id:
                raise ValidationError(
                    f"La tarea «{task.name}» está archivada. Desarchivala en Projects para usarla."
                )
            return task
        if project.archived:
            raise ValidationError("No se pueden crear tareas en un proyecto archivado.")
        task_id = self.tasks.create(project_id, name, None, self.clock.now())
        log.info("Task created on the fly id=%s project=%s", task_id, project_id)
        return self.tasks.get(task_id)
