"""Wires the database connection, clock and services together."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from worktrack.core.clock import Clock, SystemClock
from worktrack.db.connection import connect
from worktrack.db.migrations import migrate
from worktrack.services.entry_service import EntryService
from worktrack.services.project_service import ProjectService
from worktrack.services.recovery_service import RecoveryService
from worktrack.services.timer_service import TimerService


@dataclass
class AppServices:
    conn: sqlite3.Connection
    clock: Clock
    projects: ProjectService
    timer: TimerService
    entries: EntryService
    recovery: RecoveryService

    @classmethod
    def open(cls, db_file: Path | str, clock: Clock | None = None) -> "AppServices":
        conn = connect(db_file)
        try:
            migrate(conn)
        except Exception:
            conn.close()
            raise
        clock = clock or SystemClock()
        projects = ProjectService(conn, clock)
        timer = TimerService(conn, clock, projects)
        return cls(
            conn=conn,
            clock=clock,
            projects=projects,
            timer=timer,
            entries=EntryService(conn, clock, projects),
            recovery=RecoveryService(timer),
        )

    def close(self) -> None:
        self.conn.close()
