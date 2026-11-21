"""History: manual entries, edits and deletes with consistency validation.

Overlap rule: intervals are half-open [start, end). Contiguous sessions
(one ends exactly when the next starts) do not overlap. The active session
occupies [its start, now].
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone, tzinfo

from worktrack.analytics.periods import Period
from worktrack.core.clock import Clock
from worktrack.core.errors import NotFoundError, OverlapError, TaskProjectMismatchError, ValidationError
from worktrack.core.models import EntryView, TimeEntry
from worktrack.core.timeutils import format_local_datetime, format_local_time, seconds_between
from worktrack.db.connection import transaction
from worktrack.db.errors import integrity_errors
from worktrack.core.intervals import clipped_total
from worktrack.repositories.entries import EntryRepository
from worktrack.repositories.interruptions import InterruptionRepository
from worktrack.services.project_service import ProjectService, clean_name, clean_optional_text

log = logging.getLogger(__name__)

LONG_SESSION_SECONDS = 12 * 3600  # UI asks for confirmation above this
ALL_TIME = (
    datetime(1970, 1, 1, tzinfo=timezone.utc),
    datetime(9999, 12, 31, tzinfo=timezone.utc),
)


@dataclass(frozen=True)
class EntryDraft:
    project_id: int
    task_name: str
    start: datetime  # aware
    end: datetime  # aware
    description: str | None = None


def describe_entry(view: EntryView) -> str:
    e = view.entry
    end = format_local_time(e.end_time) if e.end_time else "en curso"
    return f"{view.project_name} / {view.task_name}, {format_local_datetime(e.start_time)} – {end}"


class EntryService:
    def __init__(
        self, conn: sqlite3.Connection, clock: Clock, projects: ProjectService, tz: tzinfo | None = None
    ) -> None:
        self.conn = conn
        self.clock = clock
        self.projects = projects
        self.tz = tz
        self.entries = EntryRepository(conn)
        self.interruptions = InterruptionRepository(conn)

    # --- reads -------------------------------------------------------------
    def list_entries(
        self, start_from: datetime | None = None, start_before: datetime | None = None
    ) -> list[EntryView]:
        return self.entries.list_views(start_from, start_before)

    def search(
        self,
        period: Period | None = None,
        project_id: int | None = None,
        task_id: int | None = None,
    ) -> list[EntryView]:
        """History filter. Sessions that overlap the period are included whole
        (a session from 23:00 to 01:00 shows up when filtering either day)."""
        if period is None:
            start, end = ALL_TIME
        else:
            start, end = period.bounds(self.tz)
        return self.entries.list_views_in_range(
            start, end, self.clock.now(), project_id=project_id, task_id=task_id
        )

    def get_view(self, entry_id: int) -> EntryView:
        view = self.entries.get_view(entry_id)
        if view is None:
            raise NotFoundError("La sesión no existe (quizás fue eliminada).")
        return view

    # --- validation --------------------------------------------------------
    def validate(self, draft: EntryDraft, entry_id: int | None = None) -> int:
        """Validate a manual/edited session; return its duration in seconds.

        Does not write anything. Raises a WorkTrackError with a clear message.
        """
        existing = self._editable(entry_id) if entry_id is not None else None
        start, end = self._check_times(draft)
        project = self.projects.get_project(draft.project_id)
        same_project = existing is not None and existing.project_id == project.id
        if project.archived and not same_project:
            raise ValidationError("El proyecto está archivado. Elegí un proyecto activo.")
        name = clean_name(draft.task_name, "la tarea")
        task = self.projects.tasks.find_by_name(project.id, name)
        if task is None and project.archived:
            raise ValidationError("No se pueden crear tareas en un proyecto archivado.")
        if task is not None and task.archived and (existing is None or existing.task_id != task.id):
            raise ValidationError(
                f"La tarea «{task.name}» está archivada. Desarchivala en Projects para usarla."
            )
        clean_optional_text(draft.description)
        self._check_overlap(start, end, entry_id)
        return seconds_between(start, end) - self.discounted_seconds(entry_id, start, end)

    def discounted_seconds(self, entry_id: int | None, start: datetime, end: datetime) -> int:
        """Seconds of the entry's discounted interruptions that fall inside [start, end)."""
        if entry_id is None:
            return 0
        discounts = self.interruptions.discounts_for_entries([entry_id]).get(entry_id, [])
        return clipped_total(discounts, start, end)

    def _editable(self, entry_id: int) -> TimeEntry:
        entry = self.entries.get(entry_id)
        if entry is None:
            raise NotFoundError("La sesión no existe (quizás fue eliminada).")
        if entry.is_active:
            raise ValidationError(
                "La sesión está en curso. Detenela desde Timer antes de editarla o eliminarla."
            )
        return entry

    def _check_times(self, draft: EntryDraft) -> tuple[datetime, datetime]:
        if draft.start.tzinfo is None or draft.end.tzinfo is None:
            raise ValidationError("Fecha u hora inválida.")
        start = draft.start.replace(microsecond=0)
        end = draft.end.replace(microsecond=0)
        if end <= start:
            raise ValidationError("La hora de fin debe ser posterior a la de inicio.")
        if end > self.clock.now():
            raise ValidationError("La sesión no puede terminar en el futuro.")
        return start, end

    def _check_overlap(self, start: datetime, end: datetime, exclude_id: int | None) -> None:
        clashes = self.entries.find_overlapping(start, end, self.clock.now(), exclude_id)
        if clashes:
            first = clashes[0]
            extra = f" (y {len(clashes) - 1} más)" if len(clashes) > 1 else ""
            raise OverlapError(f"Se superpone con otra sesión: {describe_entry(first)}{extra}.")

    # --- writes ------------------------------------------------------------
    def add_manual(self, draft: EntryDraft) -> TimeEntry:
        with integrity_errors(fk_error=TaskProjectMismatchError()), transaction(self.conn):
            duration = self.validate(draft)
            task = self.projects.resolve_task_in_tx(draft.project_id, draft.task_name)
            now = self.clock.now()
            entry_id = self.entries.insert(
                project_id=draft.project_id,
                task_id=task.id,
                start=draft.start.replace(microsecond=0),
                end=draft.end.replace(microsecond=0),
                duration_seconds=duration,
                description=clean_optional_text(draft.description),
                last_heartbeat=None,
                created_at=now,
            )
        log.info("Manual entry added id=%s duration=%ss", entry_id, duration)
        return self.entries.get(entry_id)

    def update_entry(self, entry_id: int, draft: EntryDraft) -> TimeEntry:
        """Edit a finished session. duration_seconds is recalculated as
        end - start minus any discounted interruption inside the new range."""
        with integrity_errors(fk_error=TaskProjectMismatchError()), transaction(self.conn):
            existing = self._editable(entry_id)
            duration = self.validate(draft, entry_id)
            task = self.projects.resolve_task_in_tx(
                draft.project_id, draft.task_name, keep_task_id=existing.task_id
            )
            self.entries.update(
                entry_id,
                project_id=draft.project_id,
                task_id=task.id,
                start=draft.start.replace(microsecond=0),
                end=draft.end.replace(microsecond=0),
                duration_seconds=duration,
                description=clean_optional_text(draft.description),
            )
        log.info("Entry updated id=%s duration=%ss", entry_id, duration)
        return self.entries.get(entry_id)

    def delete_entry(self, entry_id: int) -> None:
        with integrity_errors(), transaction(self.conn):
            self._editable(entry_id)
            self.entries.delete(entry_id)
        log.info("Entry deleted id=%s", entry_id)
