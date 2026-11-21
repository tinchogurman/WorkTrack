"""User preferences, stored as JSON in %APPDATA%\\WorkTrack\\settings.json.

Kept outside the database on purpose: restoring a backup does not change
preferences. A missing or damaged file falls back to defaults (never crashes).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

log = logging.getLogger(__name__)

TIME_FORMATS = ("24h", "12h")


@dataclass
class Settings:
    start_minimized: bool = False
    minimize_to_tray: bool = True
    confirm_exit_with_active: bool = True
    time_format: str = "24h"
    export_dir: str = ""  # empty = the user's Documents folder

    def validated(self) -> "Settings":
        if self.time_format not in TIME_FORMATS:
            self.time_format = "24h"
        return self


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> Settings:
        defaults = Settings()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return defaults
        except (OSError, ValueError) as exc:
            log.warning("Settings file unreadable (%s); using defaults", exc)
            return defaults
        if not isinstance(raw, dict):
            log.warning("Settings file has unexpected content; using defaults")
            return defaults
        values = {}
        for f in fields(Settings):
            value = raw.get(f.name, getattr(defaults, f.name))
            expected = type(getattr(defaults, f.name))
            values[f.name] = value if isinstance(value, expected) else getattr(defaults, f.name)
        return Settings(**values).validated()

    def save(self, settings: Settings) -> None:
        """Atomic write: a crash mid-save never leaves a truncated file."""
        settings.validated()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(asdict(settings), indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)
        log.info("Settings saved")
