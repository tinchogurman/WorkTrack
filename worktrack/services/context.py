"""Wires the database connection, clock and services together."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import tzinfo
from pathlib import Path

from worktrack.core.clock import Clock, SystemClock
from worktrack.db.connection import connect
from worktrack.db.migrations import migrate
from worktrack.services.analytics_service import AnalyticsService
from worktrack.services.backup_service import BackupService
from worktrack.services.entry_service import EntryService
from worktrack.services.project_service import ProjectService
from worktrack.services.recovery_service import RecoveryService
from worktrack.services.report_service import ReportService
from worktrack.services.timer_service import TimerService


@dataclass
class AppServices:
    conn: sqlite3.Connection
    clock: Clock
    projects: ProjectService
    timer: TimerService
    entries: EntryService
    recovery: RecoveryService
    analytics: AnalyticsService
    reports: ReportService
    db_path: Path
    tz: tzinfo | None = None  # None = operating system local time zone
    backups: BackupService = field(init=False)
    backups_dir: Path | None = None

    @classmethod
    def open(
        cls,
        db_file: Path | str,
        clock: Clock | None = None,
        tz: tzinfo | None = None,
        backups_dir: Path | None = None,
    ) -> "AppServices":
        conn = connect(db_file)
        try:
            migrate(conn)
        except Exception:
            conn.close()
            raise
        clock = clock or SystemClock()
        projects = ProjectService(conn, clock)
        timer = TimerService(conn, clock, projects)
        app = cls(
            conn=conn,
            clock=clock,
            projects=projects,
            timer=timer,
            entries=EntryService(conn, clock, projects, tz),
            recovery=RecoveryService(timer),
            analytics=AnalyticsService(conn, clock, tz),
            reports=ReportService(conn, clock, tz),
            db_path=Path(db_file),
            tz=tz,
            backups_dir=backups_dir,
        )
        if backups_dir is None:
            from worktrack.paths import backups_dir as default_backups_dir

            app.backups_dir = default_backups_dir()
        app.backups = BackupService(app, app.backups_dir)
        return app

    def reopen(self) -> None:
        """Re-open the database in place (after a restore). Views keep their
        reference to this container, so they see the new services."""
        fresh = AppServices.open(self.db_path, self.clock, self.tz, self.backups_dir)
        self.__dict__.update(fresh.__dict__)
        self.backups.app = self

    def close(self) -> None:
        self.conn.close()
