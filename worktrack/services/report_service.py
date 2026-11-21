"""Reports: totals (prorated by day), breakdowns and session detail.

Only finished sessions are included (reports are used for billing). Totals
by day/week/month use the per-day split; the session detail shows each
session complete plus the part that falls inside the period.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, tzinfo

import pandas as pd

from worktrack.analytics import aggregations as agg
from worktrack.analytics.dataset import build_segments
from worktrack.analytics.periods import Period
from worktrack.analytics.proration import to_local
from worktrack.core.clock import Clock
from worktrack.core.errors import ValidationError
from worktrack.repositories.entries import EntryRepository
from worktrack.repositories.projects import ProjectRepository
from worktrack.repositories.tasks import TaskRepository


@dataclass(frozen=True)
class DetailRow:
    entry_id: int
    project: str
    task: str
    start: datetime  # local, aware
    end: datetime  # local, aware
    duration_seconds: int
    in_period_seconds: int
    description: str


@dataclass(frozen=True)
class Report:
    period: Period
    project_filter: str  # "Todos" or the project name
    task_filter: str  # "Todas" or the task name
    generated_at: datetime  # local
    total_seconds: int
    sessions: int
    days_active: int
    per_project: pd.DataFrame
    per_task: pd.DataFrame
    per_day: pd.DataFrame
    per_week: pd.DataFrame
    details: list[DetailRow]

    @property
    def title(self) -> str:
        return f"Reporte WorkTrack — {self.period.label}"


class ReportService:
    def __init__(self, conn: sqlite3.Connection, clock: Clock, tz: tzinfo | None = None) -> None:
        self.clock = clock
        self.tz = tz
        self.entries = EntryRepository(conn)
        self.projects = ProjectRepository(conn)
        self.tasks = TaskRepository(conn)

    def build(self, period: Period, project_id: int | None = None, task_id: int | None = None) -> Report:
        project_label, task_label = "Todos", "Todas"
        if project_id is not None:
            project = self.projects.get(project_id)
            if project is None:
                raise ValidationError("El proyecto seleccionado ya no existe.")
            project_label = project.name
        if task_id is not None:
            task = self.tasks.get(task_id)
            if task is None or (project_id is not None and task.project_id != project_id):
                raise ValidationError("La tarea seleccionada no pertenece al proyecto.")
            task_label = task.name

        start, end = period.bounds(self.tz)
        now = self.clock.now()
        views = self.entries.list_views_in_range(
            start, end, now, project_id=project_id, task_id=task_id, include_active=False
        )
        views = sorted(views, key=lambda v: (v.entry.start_time, v.entry.id))
        seg = build_segments(views, period, now, self.tz)
        in_period = seg.groupby("entry_id")["seconds"].sum() if len(seg) else pd.Series(dtype="int64")

        details = [
            DetailRow(
                entry_id=v.entry.id,
                project=v.project_name,
                task=v.task_name,
                start=to_local(v.entry.start_time, self.tz),
                end=to_local(v.entry.end_time, self.tz),
                duration_seconds=int(v.entry.duration_seconds or 0),
                in_period_seconds=int(in_period.get(v.entry.id, 0)),
                description=v.entry.description or "",
            )
            for v in views
        ]
        return Report(
            period=period,
            project_filter=project_label,
            task_filter=task_label,
            generated_at=to_local(now, self.tz),
            total_seconds=agg.total_seconds(seg),
            sessions=len(details),
            days_active=agg.days_active(seg),
            per_project=agg.by_project(seg),
            per_task=agg.by_task(seg),
            per_day=agg.by_day(seg, period),
            per_week=agg.by_week(seg, period),
            details=details,
        )
