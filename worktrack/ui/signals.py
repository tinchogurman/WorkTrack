"""Application-wide Qt signals so views refresh when data changes elsewhere."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class AppSignals(QObject):
    projects_changed = Signal()  # projects or tasks created/edited/archived/deleted
    entries_changed = Signal()  # time entries created/edited/deleted
    session_state_changed = Signal()  # a session started or stopped
