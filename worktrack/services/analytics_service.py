"""Dashboard data. The running session counts up to "now"."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, tzinfo

import pandas as pd

from worktrack.analytics import aggregations as agg
from worktrack.analytics.dataset import build_segments
from worktrack.analytics.periods import Period, add_months, month_start
from worktrack.analytics.proration import to_local
from worktrack.core.clock import Clock
from worktrack.repositories.entries import EntryRepository
from worktrack.repositories.interruptions import InterruptionRepository

MONTHLY_TREND_MONTHS = 12


@dataclass(frozen=True)
class DashboardData:
    period: Period
    today_seconds: int
    week_seconds: int
    month_seconds: int
    total_seconds: int
    sessions: int
    days_active: int
    average_daily_seconds: float
    top_project: agg.TopProject | None
    per_day: pd.DataFrame
    per_week: pd.DataFrame
    per_project: pd.DataFrame
    per_task: pd.DataFrame
    per_month: pd.DataFrame  # last 12 months ending at the period's month
    has_active: bool


class AnalyticsService:
    def __init__(self, conn: sqlite3.Connection, clock: Clock, tz: tzinfo | None = None) -> None:
        self.clock = clock
        self.tz = tz
        self.entries = EntryRepository(conn)
        self.interruptions = InterruptionRepository(conn)

    def today(self) -> date:
        return to_local(self.clock.now(), self.tz).date()

    def segments(
        self,
        period: Period,
        *,
        include_active: bool = True,
        project_id: int | None = None,
        task_id: int | None = None,
    ) -> pd.DataFrame:
        start, end = period.bounds(self.tz)
        now = self.clock.now()
        views = self.entries.list_views_in_range(
            start, end, now, project_id=project_id, task_id=task_id, include_active=include_active
        )
        discounts = self.interruptions.discounts_for_entries([v.entry.id for v in views])
        return build_segments(views, period, now, self.tz, discounts)

    def dashboard(self, period: Period) -> DashboardData:
        today = self.today()
        week, month = Period.week(today), Period.month(today)
        trend = Period.custom(
            add_months(month_start(period.end), -(MONTHLY_TREND_MONTHS - 1)), Period.month(period.end).end
        )
        # One query covering everything shown, then slice by date.
        span = Period.custom(
            min(period.start, week.start, month.start, trend.start),
            max(period.end, week.end, month.end, trend.end),
        )
        seg = self.segments(span)

        def within(p: Period) -> pd.DataFrame:
            if not len(seg):
                return seg
            return seg[seg["date"].map(p.contains)]

        current = within(period)
        return DashboardData(
            period=period,
            today_seconds=agg.total_seconds(within(Period.day(today))),
            week_seconds=agg.total_seconds(within(week)),
            month_seconds=agg.total_seconds(within(month)),
            total_seconds=agg.total_seconds(current),
            sessions=agg.session_count(current),
            days_active=agg.days_active(current),
            average_daily_seconds=agg.average_daily_seconds(current),
            top_project=agg.top_project(current),
            per_day=agg.by_day(current, period),
            per_week=agg.by_week(current, period),
            per_project=agg.by_project(current),
            per_task=agg.by_task(current, top=10),
            per_month=agg.by_month(within(trend), trend),
            has_active=bool(len(seg)) and bool(seg["active"].any()),
        )
