"""Dashboard, reports and history filters over real (temporary) databases."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from worktrack.analytics import aggregations as agg
from worktrack.analytics.periods import Period
from worktrack.core.errors import ValidationError
from worktrack.services.entry_service import EntryDraft

from conftest import BA

H = 3600
# "Now" for these tests: Friday 2026-03-20 18:00 Buenos Aires
NOW = datetime(2026, 3, 20, 18, 0, tzinfo=BA)


def at(day, hour, minute=0):
    return datetime(2026, 3, day, hour, minute, tzinfo=BA)


@pytest.fixture
def svc(services, clock):
    clock.set(NOW)
    return services


def add(svc, project, task, start, end, desc=None):
    return svc.entries.add_manual(EntryDraft(project.id, task, start, end, desc))


@pytest.fixture
def data(svc, project, other_project):
    """Two projects, sessions across days, weeks and a midnight crossing."""
    add(svc, project, "ETL", at(2, 9), at(2, 12))  # Mon wk10: 3h
    add(svc, other_project, "API", at(2, 14), at(2, 15, 30))  # 1.5h
    add(svc, project, "ETL", at(15, 23), at(16, 1))  # Sun 15 -> Mon 16 (week cut)
    add(svc, project, "Review", at(19, 10), at(19, 11))  # 1h
    add(svc, other_project, "API", at(20, 8), at(20, 10))  # today 2h
    return svc


# --- dashboard ---------------------------------------------------------------

def test_dashboard_totals_match_records(data, project, other_project):
    period = Period.month(date(2026, 3, 20))
    d = data.analytics.dashboard(period)
    records = sum(v.entry.duration_seconds for v in data.entries.list_entries())
    assert d.total_seconds == records == (3 + 1.5 + 2 + 1 + 2) * H
    assert d.sessions == 5
    per_project = dict(zip(d.per_project["project"], d.per_project["seconds"]))
    assert per_project == {project.name: 6 * H, other_project.name: int(3.5 * H)}
    assert d.top_project.name == project.name
    assert abs(d.per_project["share"].sum() - 1) < 1e-9
    assert d.per_day["seconds"].sum() == d.total_seconds
    assert d.per_week["seconds"].sum() == d.total_seconds


def test_dashboard_fixed_kpis(data):
    d = data.analytics.dashboard(Period.month(date(2026, 3, 20)))
    assert d.today_seconds == 2 * H
    # week of Mon 16 .. Sun 22: 1h (after midnight on 16) + 1h + 2h
    assert d.week_seconds == 4 * H
    assert d.month_seconds == d.total_seconds


def test_midnight_session_split_in_daily_totals(data):
    d = data.analytics.dashboard(Period.month(date(2026, 3, 20)))
    per_day = dict(zip(d.per_day["date"], d.per_day["seconds"]))
    assert per_day[date(2026, 3, 15)] == H and per_day[date(2026, 3, 16)] == H
    assert len(d.per_day) == 31  # empty days included
    per_week = dict(zip(d.per_week["week"], d.per_week["seconds"]))
    assert per_week[date(2026, 3, 9)] == H  # Sunday part
    assert per_week[date(2026, 3, 16)] == 4 * H


def test_period_clips_crossing_session(data):
    d = data.analytics.dashboard(Period.day(date(2026, 3, 16)))
    assert d.total_seconds == H and d.sessions == 1


def test_average_daily_uses_days_with_activity(data):
    d = data.analytics.dashboard(Period.month(date(2026, 3, 20)))
    # active days: 2, 15, 16, 19, 20
    assert d.days_active == 5
    assert d.average_daily_seconds == pytest.approx(d.total_seconds / 5)


def test_monthly_trend_has_12_months(data):
    d = data.analytics.dashboard(Period.month(date(2026, 3, 20)))
    assert len(d.per_month) == 12
    assert d.per_month["month"].iloc[-1] == date(2026, 3, 1)
    assert d.per_month["seconds"].iloc[-1] == d.total_seconds
    assert d.per_month["seconds"].iloc[:-1].sum() == 0


def test_dashboard_counts_active_session_until_now(svc, project, clock):
    clock.set(at(20, 9))
    svc.timer.start(project.id, "Live")
    clock.set(at(20, 9, 45))
    d = svc.analytics.dashboard(Period.week(date(2026, 3, 20)))
    assert d.today_seconds == 45 * 60 and d.has_active


def test_empty_database(svc):
    d = svc.analytics.dashboard(Period.week(date(2026, 3, 20)))
    assert d.total_seconds == 0 and d.sessions == 0 and d.top_project is None
    assert d.average_daily_seconds == 0 and len(d.per_day) == 7 and d.per_project.empty


def test_task_breakdown_top_and_others(svc, project):
    for i in range(12):
        add(svc, project, f"T{i:02d}", at(1, 0) + timedelta(hours=i), at(1, 0) + timedelta(hours=i, minutes=10 + i))
    seg = svc.analytics.segments(Period.month(date(2026, 3, 1)))
    top = agg.by_task(seg, top=10)
    assert len(top) == 11 and top["task"].iloc[-1] == "Otras"
    assert top["seconds"].sum() == agg.total_seconds(seg)


# --- reports -----------------------------------------------------------------

def test_report_month(data, project):
    r = data.reports.build(Period.month(date(2026, 3, 1)))
    assert r.total_seconds == int(9.5 * H) and r.sessions == 5 and r.days_active == 5
    assert [row.task for row in r.details][:2] == ["ETL", "API"]  # chronological
    assert r.per_day["seconds"].sum() == r.total_seconds
    assert r.project_filter == "Todos"


def test_report_detail_keeps_whole_session_but_totals_are_prorated(data):
    r = data.reports.build(Period.day(date(2026, 3, 16)))
    assert r.total_seconds == H
    (row,) = r.details
    assert row.duration_seconds == 2 * H and row.in_period_seconds == H
    assert row.start.hour == 23 and row.end.hour == 1  # local times


def test_report_filters(data, project, other_project):
    r = data.reports.build(Period.month(date(2026, 3, 1)), project_id=other_project.id)
    assert r.total_seconds == int(3.5 * H) and r.project_filter == other_project.name
    task_id = data.projects.tasks.find_by_name(other_project.id, "API").id
    r2 = data.reports.build(Period.month(date(2026, 3, 1)), project_id=other_project.id, task_id=task_id)
    assert r2.task_filter == "API" and r2.sessions == 2
    with pytest.raises(ValidationError):
        data.reports.build(Period.month(date(2026, 3, 1)), project_id=project.id, task_id=task_id)


def test_report_excludes_active_session(data, project, clock):
    data.timer.start(project.id, "Live")
    clock.advance(hours=1)
    r = data.reports.build(Period.day(date(2026, 3, 20)))
    assert r.total_seconds == 2 * H and r.sessions == 1


def test_report_week_period(data):
    r = data.reports.build(Period.week(date(2026, 3, 18)))
    assert r.total_seconds == 4 * H
    assert list(r.per_week["seconds"]) == [4 * H]


# --- history filters ---------------------------------------------------------

def test_history_filter_by_date_overlap(data):
    for day in (15, 16):
        views = data.entries.search(Period.day(date(2026, 3, day)))
        assert [v.task_name for v in views] == ["ETL"]  # the 23:00-01:00 session in both
    assert len(data.entries.search(Period.day(date(2026, 3, 3)))) == 0
    assert len(data.entries.search()) == 5


def test_history_filter_by_project_and_task(data, project, other_project):
    assert len(data.entries.search(project_id=project.id)) == 3
    etl = data.projects.tasks.find_by_name(project.id, "ETL")
    assert len(data.entries.search(project_id=project.id, task_id=etl.id)) == 2
    combined = data.entries.search(Period.week(date(2026, 3, 18)), project_id=other_project.id)
    assert [v.task_name for v in combined] == ["API"]


def test_history_filter_includes_active(svc, project, clock):
    clock.set(at(20, 9))
    svc.timer.start(project.id, "Live")
    clock.set(at(20, 10))
    assert len(svc.entries.search(Period.day(date(2026, 3, 20)))) == 1
