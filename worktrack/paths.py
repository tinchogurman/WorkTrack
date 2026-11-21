"""Filesystem locations for user data (database, logs, backups).

Data lives in %APPDATA%\\WorkTrack, never inside the repository or the
executable. Set WORKTRACK_DATA_DIR to override (used by tests).
"""

from __future__ import annotations

import os
from pathlib import Path

from worktrack import APP_NAME

DB_FILENAME = "worktrack.db"


def data_dir() -> Path:
    override = os.environ.get("WORKTRACK_DATA_DIR")
    if override:
        base = Path(override)
    else:
        appdata = os.environ.get("APPDATA")
        root = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        base = root / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def db_path() -> Path:
    return data_dir() / DB_FILENAME


def logs_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def lock_path() -> Path:
    return data_dir() / "worktrack.lock"
