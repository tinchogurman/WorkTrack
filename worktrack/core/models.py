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
class Interruption:
    """A suspected break inside a session (suspend/resume or a long heartbeat gap)."""

    id: int
    entry_id: int
    start_time: datetime
    end_time: datetime
    source: str  # 'heartbeat_gap' | 'power_event'
    status: str  # 'pending' | 'kept' | 'discounted' | 'adjusted'
    discount_start: datetime | None
    discount_end: datetime | None
    created_at: datetime
    resolved_at: datetime | None

    @property
    def seconds(self) -> int:
        return int((self.end_time - self.start_time).total_seconds())

    @property
    def is_pending(self) -> bool:
        return self.status == "pending"

    @property
    def discounted_interval(self) -> tuple[datetime, datetime] | None:
        if self.discount_start is None or self.discount_end is None:
            return None
        return self.discount_start, self.discount_end


@dataclass(frozen=True)
class EntryView:
    """A time entry joined with its project and task (for history and lists)."""

    entry: TimeEntry
    project_name: str
    project_color: str
    project_archived: bool
    task_name: str
