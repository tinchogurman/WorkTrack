"""Plain data objects shared across layers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Project:
    id: int
    name: str
    color: str
    archived: bool
    created_at: datetime


@dataclass(frozen=True)
class Task:
    id: int
    project_id: int
    name: str
    description: str | None
    archived: bool
    created_at: datetime


@dataclass(frozen=True)
class TimeEntry:
    id: int
    project_id: int
    task_id: int
    start_time: datetime
    end_time: datetime | None
    duration_seconds: int | None
    description: str | None
    last_heartbeat: datetime | None
    created_at: datetime

    @property
    def is_active(self) -> bool:
        return self.end_time is None


@dataclass(frozen=True)
class EntryView:
    """A time entry joined with its project and task (for history and lists)."""

    entry: TimeEntry
    project_name: str
    project_color: str
    project_archived: bool
    task_name: str
