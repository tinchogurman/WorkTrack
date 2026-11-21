"""Totals over per-day segments (see dataset.build_segments).

Every function takes the segments DataFrame; day/week/month series include
empty buckets (0 seconds) so charts and tables show the whole period.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from worktrack.analytics.periods import Period, add_months, month_label, month_start, week_label, week_start


def total_seconds(seg: pd.DataFrame) -> int:
    return int(seg["seconds"].sum()) if len(seg) else 0


def session_count(seg: pd.DataFrame) -> int:
    return int(seg["entry_id"].nunique()) if len(seg) else 0


def days_active(seg: pd.DataFrame) -> int:
    if not len(seg):
        return 0
    per_day = seg.groupby("date")["seconds"].sum()
    return int((per_day > 0).sum())


def average_daily_seconds(seg: pd.DataFrame) -> float:
    """Total divided by days with recorded activity (0 when there are none)."""
    days = days_active(seg)
    return total_seconds(seg) / days if days else 0.0


def by_day(seg: pd.DataFrame, period: Period) -> pd.DataFrame:
    totals = seg.groupby("date")["seconds"].sum() if len(seg) else pd.Series(dtype="int64")
    days = list(period.iter_days())
    return pd.DataFrame({"date": days, "seconds": [int(totals.get(d, 0)) for d in days]})


def by_week(seg: pd.DataFrame, period: Period) -> pd.DataFrame:
    if len(seg):
        totals = seg.assign(week=seg["date"].map(week_start)).groupby("week")["seconds"].sum()
    else:
        totals = pd.Series(dtype="int64")
    weeks = sorted({week_start(d) for d in period.iter_days()})
    return pd.DataFrame({
        "week": weeks,
        "label": [week_label(w) for w in weeks],
        "seconds": [int(totals.get(w, 0)) for w in weeks],
    })


def by_month(seg: pd.DataFrame, period: Period) -> pd.DataFrame:
    if len(seg):
        totals = seg.assign(month=seg["date"].map(month_start)).groupby("month")["seconds"].sum()
    else:
        totals = pd.Series(dtype="int64")
    months, current = [], month_start(period.start)
    while current <= period.end:
        months.append(current)
        current = add_months(current, 1)
    return pd.DataFrame({
        "month": months,
        "label": [month_label(m) for m in months],
        "seconds": [int(totals.get(m, 0)) for m in months],
    })


def _with_share(frame: pd.DataFrame) -> pd.DataFrame:
    total = frame["seconds"].sum()
    frame["share"] = frame["seconds"] / total if total else 0.0
    return frame.reset_index(drop=True)


def by_project(seg: pd.DataFrame) -> pd.DataFrame:
    if not len(seg):
        return pd.DataFrame(columns=["project_id", "project", "color", "seconds", "share"])
    frame = (
        seg.groupby(["project_id", "project", "color"], as_index=False)["seconds"].sum()
        .sort_values(["seconds", "project"], ascending=[False, True])
    )
    return _with_share(frame)


def by_task(seg: pd.DataFrame, top: int | None = None) -> pd.DataFrame:
    """Per task (task names repeat across projects, so the project is part of the key).

    With `top`, the rest is grouped into a single "Otras" row.
    """
    columns = ["project", "task", "color", "seconds", "share"]
    if not len(seg):
        return pd.DataFrame(columns=columns)
    frame = (
        seg.groupby(["task_id", "project", "task", "color"], as_index=False)["seconds"].sum()
        .sort_values(["seconds", "task"], ascending=[False, True])
    )
    frame = frame[["project", "task", "color", "seconds"]]
    if top is not None and len(frame) > top:
        rest = int(frame["seconds"].iloc[top:].sum())
        frame = pd.concat(
            [frame.iloc[:top], pd.DataFrame([{"project": "", "task": "Otras", "color": "#64748B", "seconds": rest}])],
            ignore_index=True,
        )
    return _with_share(frame)


@dataclass(frozen=True)
class TopProject:
    name: str
    color: str
    seconds: int
    share: float


def top_project(seg: pd.DataFrame) -> TopProject | None:
    frame = by_project(seg)
    if frame.empty:
        return None
    row = frame.iloc[0]
    return TopProject(row["project"], row["color"], int(row["seconds"]), float(row["share"]))
