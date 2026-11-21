"""The stopwatch.

Elapsed time is always computed from the persisted start timestamp
(now - start_time); there is no incrementing counter. A session is written
to SQLite the moment it starts. While it runs, a periodic heartbeat stores
the last moment the app was known to be alive, used for crash recovery (and,
in phase 3, to detect suspend/resume gaps).
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from worktrack.core.clock import Clock
from worktrack.core.errors import (
    ActiveSessionExistsError,
    NoActiveSessionError,
    OverlapError,
    TaskProjectMismatchError,
    ValidationError,
)
from worktrack.core.models import EntryView, TimeEntry
from worktrack.core.timeutils import seconds_between
from worktrack.db.connection import transaction
from worktrack.db.errors import integrity_errors
from worktrack.core.intervals import clipped_total
from worktrack.repositories.entries import EntryRepository
from worktrack.repositories.interruptions import InterruptionRepository
from worktrack.services.project_service import ProjectService, clean_optional_text

log = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_SECONDS = 30


@dataclass(frozen=True)
class Heartbeat:
    previous: datetime | None
    current: datetime


class TimerService:
    def __init__(self, conn: sqlite3.Connection, clock: Clock, projects: ProjectService) -> None:
        self.conn = conn
        self.clock = clock
        self.projects = projects
        self.entries = EntryRepository(conn)
        self.interruptions = InterruptionRepository(conn)

    def get_active(self) -> TimeEntry | None:
        return self.entries.get_active()

    def get_active_view(self) -> EntryView | None:
        return self.entries.get_active_view()

    def worked_seconds(self, entry: TimeEntry, until: datetime) -> int:
        """Elapsed time from the start to `until` minus discounted interruptions."""
        if until <= entry.start_time:
            return 0
        discounts = self.interruptions.discounts_for_entries([entry.id]).get(entry.id, [])
        elapsed = seconds_between(entry.start_time, until)
        return max(0, elapsed - clipped_total(discounts, entry.start_time, until))

    def elapsed_seconds(self, entry: TimeEntry) -> int:
        """Worked seconds of a running session up to now (shown by the stopwatch)."""
        return self.worked_seconds(entry, self.clock.now())

    def start(self, project_id: int, task_name: str, description: str | None = None) -> TimeEntry:
        description = clean_optional_text(description)
        with integrity_errors(fk_error=TaskProjectMismatchError()), transaction(self.conn):
            if self.entries.get_active() is not None:
                raise ActiveSessionExistsError()
            project = self.projects.get_project(project_id)
            if project.archived:
                raise ValidationError("El proyecto está archivado. Elegí un proyecto activo.")
            task = self.projects.resolve_task_in_tx(project_id, task_name)
            if task.project_id != project_id:  # defensive: also enforced by the DB
                raise TaskProjectMismatchError()
            now = self.clock.now()
            if self.entries.exists_after(now):
                raise OverlapError(
                    "Hay sesiones registradas con horario posterior a la hora actual del sistema. "
                    "Revisá el reloj de Windows o corregí esas sesiones en History."
                )
            entry_id = self.entries.insert(
                project_id=project_id,
                task_id=task.id,
                start=now,
                end=None,
                duration_seconds=None,
                description=description,
                last_heartbeat=now,
                created_at=now,
            )
        log.info("Session started id=%s project=%s task=%s", entry_id, project_id, task.id)
        return self.entries.get(entry_id)

    def stop(self) -> TimeEntry:
        return self.finish_active_at(self.clock.now(), reason="stop")

    def finish_active_at(self, end: datetime, *, reason: str) -> TimeEntry:
        """Close the active session at `end` (start <= end <= now)."""
        with integrity_errors(), transaction(self.conn):
            active = self.entries.get_active()
            if active is None:
                raise NoActiveSessionError()
            now = self.clock.now()
            if end > now:
                raise ValidationError("La hora de fin no puede estar en el futuro.")
            if end < active.start_time:
                if reason == "stop":
                    # System clock moved backwards: never store a negative duration.
                    log.warning("Clock is before session start; clamping end to start")
                    end = active.start_time
                else:
                    raise ValidationError(
                        "La hora de fin no puede ser anterior al inicio de la sesión."
                    )
            duration = self.worked_seconds(active, end)
            self.entries.finish(active.id, end, duration)
        log.info("Session finished id=%s reason=%s duration=%ss", active.id, reason, duration)
        return self.entries.get(active.id)

    def update_active_description(self, description: str | None) -> None:
        description = clean_optional_text(description)
        with integrity_errors(), transaction(self.conn):
            active = self.entries.get_active()
            if active is None:
                raise NoActiveSessionError()
            self.entries.update_description(active.id, description)

    def heartbeat(self) -> Heartbeat | None:
        """Record that the app is alive. Returns previous/current beat (None if idle)."""
        with transaction(self.conn):
            active = self.entries.get_active()
            if active is None:
                return None
            now = self.clock.now()
            self.entries.set_heartbeat(active.id, now)
        return Heartbeat(previous=active.last_heartbeat, current=now)
