"""Sessions -> per-day segments (pandas DataFrame), clipped to a period."""

from __future__ import annotations

from datetime import datetime, tzinfo

import pandas as pd

from worktrack.analytics.periods import Period
from worktrack.analytics.proration import split_by_day
from worktrack.core.models import EntryView

SEGMENT_COLUMNS = [
    "entry_id", "project_id", "project", "color", "task_id", "task", "date", "seconds", "active",
]


def empty_segments() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="int64" if c == "seconds" else "object") for c in SEGMENT_COLUMNS})


def worked_seconds(view: EntryView, now: datetime) -> tuple[datetime, int] | None:
    """(effective end, worked seconds); an active session counts up to `now`."""
    e = view.entry
    if e.end_time is not None:
        return e.end_time, int(e.duration_seconds or 0)
    if now <= e.start_time:
        return None
    return now, int((now - e.start_time).total_seconds())


def build_segments(
    views: list[EntryView], period: Period, now: datetime, tz: tzinfo | None = None
) -> pd.DataFrame:
    rows = []
    for view in views:
        resolved = worked_seconds(view, now)
        if resolved is None:
            continue
        end, worked = resolved
        e = view.entry
        for day, seconds in split_by_day(e.start_time, end, worked, tz):
            if period.contains(day):
                rows.append((
                    e.id, e.project_id, view.project_name, view.project_color,
                    e.task_id, view.task_name, day, seconds, e.is_active,
                ))
    if not rows:
        return empty_segments()
    frame = pd.DataFrame(rows, columns=SEGMENT_COLUMNS)
    frame["seconds"] = frame["seconds"].astype("int64")
    return frame
