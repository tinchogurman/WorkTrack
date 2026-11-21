"""Data access for time entries. Parameterized SQL only, no business rules."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from worktrack.core.models import EntryView, TimeEntry
from worktrack.core.timeutils import from_db, to_db

_VIEW_SQL = """
SELECT e.*, p.name AS project_name, p.color AS project_color,
       p.archived AS project_archived, t.name AS task_name
FROM time_entries e
JOIN projects p ON p.id = e.project_id
JOIN tasks t ON t.id = e.task_id
"""


def _to_entry(row: sqlite3.Row) -> TimeEntry:
    return TimeEntry(
        id=row["id"],
        project_id=row["project_id"],
        task_id=row["task_id"],
        start_time=from_db(row["start_time"]),
        end_time=from_db(row["end_time"]),
        duration_seconds=row["duration_seconds"],
        description=row["description"],
        last_heartbeat=from_db(row["last_heartbeat"]),
        created_at=from_db(row["created_at"]),
    )


def _to_view(row: sqlite3.Row) -> EntryView:
    return EntryView(
        entry=_to_entry(row),
        project_name=row["project_name"],
        project_color=row["project_color"],
        project_archived=bool(row["project_archived"]),
        task_name=row["task_name"],
    )


def _db(value: datetime | None) -> str | None:
    return to_db(value) if value is not None else None


class EntryRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # --- reads -------------------------------------------------------------
    def get(self, entry_id: int) -> TimeEntry | None:
        row = self.conn.execute("SELECT * FROM time_entries WHERE id = ?", (entry_id,)).fetchone()
        return _to_entry(row) if row else None

    def get_view(self, entry_id: int) -> EntryView | None:
        row = self.conn.execute(_VIEW_SQL + " WHERE e.id = ?", (entry_id,)).fetchone()
        return _to_view(row) if row else None

    def get_active(self) -> TimeEntry | None:
        row = self.conn.execute("SELECT * FROM time_entries WHERE end_time IS NULL").fetchone()
        return _to_entry(row) if row else None

    def get_active_view(self) -> EntryView | None:
        row = self.conn.execute(_VIEW_SQL + " WHERE e.end_time IS NULL").fetchone()
        return _to_view(row) if row else None

    def list_views(
        self, start_from: datetime | None = None, start_before: datetime | None = None
    ) -> list[EntryView]:
        sql = _VIEW_SQL + " WHERE (? IS NULL OR e.start_time >= ?) AND (? IS NULL OR e.start_time < ?)"
        sql += " ORDER BY e.start_time DESC, e.id DESC"
        a, b = _db(start_from), _db(start_before)
        return [_to_view(r) for r in self.conn.execute(sql, (a, a, b, b))]

    def list_views_in_range(
        self,
        start: datetime,
        end: datetime,
        now: datetime,
        *,
        project_id: int | None = None,
        task_id: int | None = None,
        include_active: bool = True,
    ) -> list[EntryView]:
        """Sessions that intersect [start, end) (active ones occupy [start, now]).

        A session crossing a range boundary is included (whole record).
        """
        sql = _VIEW_SQL + (
            " WHERE e.start_time < ?"
            " AND (COALESCE(e.end_time, ?) > ? OR e.start_time >= ?)"
            " AND (? IS NULL OR e.project_id = ?)"
            " AND (? IS NULL OR e.task_id = ?)"
        )
        if not include_active:
            sql += " AND e.end_time IS NOT NULL"
        sql += " ORDER BY e.start_time DESC, e.id DESC"
        s, e, n = to_db(start), to_db(end), to_db(now)
        params = (e, n, s, s, project_id, project_id, task_id, task_id)
        return [_to_view(r) for r in self.conn.execute(sql, params)]

    def find_overlapping(
        self, start: datetime, end: datetime, now: datetime, exclude_id: int | None = None
    ) -> list[EntryView]:
        """Entries whose interval intersects the half-open [start, end).

        Touching intervals (one ends exactly when the other starts) do not
        overlap. The active session occupies [its start, now].
        """
        sql = _VIEW_SQL + (
            " WHERE e.start_time < ? AND COALESCE(e.end_time, ?) > ?"
            " AND (? IS NULL OR e.id <> ?)"
            " ORDER BY e.start_time"
        )
        params = (to_db(end), to_db(now), to_db(start), exclude_id, exclude_id)
        return [_to_view(r) for r in self.conn.execute(sql, params)]

    def exists_after(self, moment: datetime) -> bool:
        """True if any entry starts or ends later than `moment` (e.g. clock moved back)."""
        ts = to_db(moment)
        row = self.conn.execute(
            "SELECT 1 FROM time_entries WHERE start_time > ? OR end_time > ? LIMIT 1", (ts, ts)
        ).fetchone()
        return row is not None

    # --- writes ------------------------------------------------------------
    def insert(
        self,
        *,
        project_id: int,
        task_id: int,
        start: datetime,
        end: datetime | None,
        duration_seconds: int | None,
        description: str | None,
        last_heartbeat: datetime | None,
        created_at: datetime,
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO time_entries (project_id, task_id, start_time, end_time,"
            " duration_seconds, description, last_heartbeat, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                project_id,
                task_id,
                to_db(start),
                _db(end),
                duration_seconds,
                description,
                _db(last_heartbeat),
                to_db(created_at),
            ),
        )
        return cur.lastrowid

    def finish(self, entry_id: int, end: datetime, duration_seconds: int) -> None:
        self.conn.execute(
            "UPDATE time_entries SET end_time = ?, duration_seconds = ? WHERE id = ?",
            (to_db(end), duration_seconds, entry_id),
        )

    def update(
        self,
        entry_id: int,
        *,
        project_id: int,
        task_id: int,
        start: datetime,
        end: datetime,
        duration_seconds: int,
        description: str | None,
    ) -> None:
        self.conn.execute(
            "UPDATE time_entries SET project_id = ?, task_id = ?, start_time = ?, end_time = ?,"
            " duration_seconds = ?, description = ? WHERE id = ?",
            (project_id, task_id, to_db(start), to_db(end), duration_seconds, description, entry_id),
        )

    def update_description(self, entry_id: int, description: str | None) -> None:
        self.conn.execute(
            "UPDATE time_entries SET description = ? WHERE id = ?", (description, entry_id)
        )

    def set_heartbeat(self, entry_id: int, moment: datetime) -> None:
        self.conn.execute(
            "UPDATE time_entries SET last_heartbeat = ? WHERE id = ?", (to_db(moment), entry_id)
        )

    def delete(self, entry_id: int) -> None:
        self.conn.execute("DELETE FROM time_entries WHERE id = ?", (entry_id,))
