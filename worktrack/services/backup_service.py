"""Consistent backups and validated restores.

- Backups use the SQLite online backup API (never a raw file copy of a live DB).
- Restore: refuse while a session is active, validate the file (opens as SQLite,
  integrity_check == ok, expected tables, schema not newer than this app),
  back up the current state, close connections, restore through the backup
  API, reopen (migrating older schemas). If the restore fails, the previous
  state is put back from the automatic backup.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from worktrack.core.errors import ValidationError, WorkTrackError
from worktrack.db.migrations import SCHEMA_VERSION
from worktrack.db.schema import EXPECTED_TABLES

if TYPE_CHECKING:
    from worktrack.services.context import AppServices

log = logging.getLogger(__name__)


class InvalidBackupError(ValidationError):
    pass


class RestoreError(WorkTrackError):
    pass


@dataclass(frozen=True)
class BackupInfo:
    path: Path
    schema_version: int
    projects: int
    tasks: int
    entries: int
    has_active_session: bool


@dataclass(frozen=True)
class BackupFile:
    path: Path
    size: int
    modified: datetime


@dataclass(frozen=True)
class RestoreResult:
    restored_from: Path
    safety_backup: Path
    info: BackupInfo


def _open_readonly(path: Path) -> sqlite3.Connection:
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=5.0)


def _copy_database(source: sqlite3.Connection, target_path: Path) -> None:
    target = sqlite3.connect(str(target_path), timeout=5.0)
    try:
        source.backup(target)
    finally:
        target.close()


class BackupService:
    def __init__(self, app: "AppServices", backups_dir: Path) -> None:
        self.app = app  # container; re-pointed after a reopen
        self.backups_dir = Path(backups_dir)

    # --- create ------------------------------------------------------------
    def _target(self, prefix: str) -> Path:
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        candidate = self.backups_dir / f"{prefix}_{stamp}.db"
        n = 2
        while candidate.exists():
            candidate = self.backups_dir / f"{prefix}_{stamp}_{n}.db"
            n += 1
        return candidate

    def create_backup(self, prefix: str = "worktrack") -> Path:
        target = self._target(prefix)
        dest = sqlite3.connect(str(target))
        try:
            self.app.conn.backup(dest)
            dest.execute("PRAGMA journal_mode = DELETE")  # self-contained single file
        except sqlite3.Error as exc:
            dest.close()
            target.unlink(missing_ok=True)
            log.error("Backup failed: %s", exc)
            raise RestoreError("No se pudo crear la copia de seguridad.") from exc
        dest.close()
        self.validate(target)  # never leave a broken backup unnoticed
        log.info("Backup created: %s", target)
        return target

    def list_backups(self) -> list[BackupFile]:
        if not self.backups_dir.is_dir():
            return []
        files = [
            BackupFile(p, p.stat().st_size, datetime.fromtimestamp(p.stat().st_mtime))
            for p in self.backups_dir.glob("*.db")
            if p.is_file()
        ]
        return sorted(files, key=lambda f: f.modified, reverse=True)

    # --- validate ----------------------------------------------------------
    def validate(self, path: Path | str) -> BackupInfo:
        path = Path(path)
        if not path.is_file():
            raise InvalidBackupError("El archivo de backup no existe.")
        try:
            conn = _open_readonly(path)
        except sqlite3.Error as exc:
            raise InvalidBackupError("No se pudo abrir el archivo como base de datos.") from exc
        try:
            try:
                result = conn.execute("PRAGMA integrity_check").fetchone()[0]
            except sqlite3.DatabaseError as exc:
                raise InvalidBackupError("El archivo no es una base de datos SQLite válida.") from exc
            if result != "ok":
                log.warning("integrity_check failed for %s: %s", path, result)
                raise InvalidBackupError("La base de datos del backup está dañada (integrity_check falló).")
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            missing = EXPECTED_TABLES - tables
            if missing:
                raise InvalidBackupError(
                    "El archivo no es un backup de WorkTrack (faltan tablas: " + ", ".join(sorted(missing)) + ")."
                )
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version < 1:
                raise InvalidBackupError("El archivo no es un backup de WorkTrack (sin versión de esquema).")
            if version > SCHEMA_VERSION:
                raise InvalidBackupError(
                    "El backup es de una versión más nueva de WorkTrack y no se puede restaurar con esta."
                )
            count = lambda table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: E731
            active = conn.execute("SELECT COUNT(*) FROM time_entries WHERE end_time IS NULL").fetchone()[0]
            return BackupInfo(path, version, count("projects"), count("tasks"), count("time_entries"), active > 0)
        finally:
            conn.close()

    # --- restore -----------------------------------------------------------
    def restore(self, path: Path | str) -> RestoreResult:
        source_path = Path(path).resolve()
        db_path = Path(self.app.db_path).resolve()
        if source_path == db_path:
            raise InvalidBackupError("Elegiste la base de datos en uso; elegí un archivo de backup.")
        if self.app.timer.get_active() is not None:
            raise ValidationError(
                "Hay una sesión en curso. Detenela (o finalizala) antes de restaurar un backup."
            )
        info = self.validate(source_path)
        safety = self.create_backup(prefix="pre-restore")
        log.info("Restoring %s (safety backup %s)", source_path, safety)

        self.app.close()
        try:
            source = _open_readonly(source_path)
            try:
                _copy_database(source, db_path)
            finally:
                source.close()
        except Exception as exc:
            log.exception("Restore failed; putting back the previous state")
            try:
                fallback = _open_readonly(safety)
                try:
                    _copy_database(fallback, db_path)
                finally:
                    fallback.close()
            finally:
                self.app.reopen()
            raise RestoreError(
                "No se pudo restaurar el backup. Se mantuvo el estado anterior "
                f"(copia de seguridad en {safety.name})."
            ) from exc
        self.app.reopen()  # also migrates an older schema
        log.info("Restore completed from %s", source_path)
        return RestoreResult(source_path, safety, info)
