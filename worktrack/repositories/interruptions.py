"""Data access for session interruptions. Parameterized SQL only."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime

from worktrack.core.models import Interruption
from worktrack.core.timeutils import from_db, to_db

CHUNK = 500


def _to_interruption(row: sqlite3.Row) -> Interruption:
    return Interruption(
        id=row["id"],
        entry_id=row["entry_id"],
        start_time=from_db(row["start_time"]),
        end_time=from_db(row["end_time"]),
        source=row["source"],
        status=row["status"],
        discount_start=from_db(row["discount_start"]),
        discount_end=from_db(row["discount_end"]),
        created_at=from_db(row["created_at"]),
        resolved_at=from_db(row["resolved_at"]),
    )


class InterruptionRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def get(self, interruption_id: int) -> Interruption | None:
        row = self.conn.execute(
            "SELECT * FROM session_interruptions WHERE id = ?", (interruption_id,)
        ).fetchone()
        return _to_interruption(row) if row else None

    def list_for_entry(self, entry_id: int) -> list[Interruption]:
        rows = self.conn.execute(
            "SELECT * FROM session_interruptions WHERE entry_id = ? ORDER BY start_time", (entry_id,)
        )
        return [_to_interruption(r) for r in rows]

    def insert(
        self, entry_id: int, start: datetime, end: datetime, source: str, created_at: datetime
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO session_interruptions (entry_id, start_time, end_time, source, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (entry_id, to_db(start), to_db(end), source, to_db(created_at)),
        )
        return cur.lastrowid

    def update_bounds(self, interruption_id: int, start: datetime, end: datetime, source: str) -> None:
        self.conn.execute(
            "UPDATE session_interruptions SET start_time = ?, end_time = ?, source = ? WHERE id = ?",
            (to_db(start), to_db(end), source, interruption_id),
        )

    def resolve(
        self,
        interruption_id: int,
        status: str,
        discount: tuple[datetime, datetime] | None,
        resolved_at: datetime,
    ) -> None:
        ds, de = (to_db(discount[0]), to_db(discount[1])) if discount else (None, None)
        self.conn.execute(
            "UPDATE session_interruptions SET status = ?, discount_start = ?, discount_end = ?,"
            " resolved_at = ? WHERE id = ?",
            (status, ds, de, to_db(resolved_at), interruption_id),
        )

    def discounts_for_entries(self, entry_ids: list[int]) -> dict[int, list[tuple[datetime, datetime]]]:
        """Discounted ranges per entry (only 'discounted' / 'adjusted')."""
        result: dict[int, list[tuple[datetime, datetime]]] = defaultdict(list)
        ids = list(dict.fromkeys(entry_ids))
        for i in range(0, len(ids), CHUNK):
            chunk = ids[i : i + CHUNK]
            marks = ",".join("?" * len(chunk))
            rows = self.conn.execute(
                "SELECT entry_id, discount_start, discount_end FROM session_interruptions"
                f" WHERE discount_start IS NOT NULL AND entry_id IN ({marks})"
                " ORDER BY discount_start",
                chunk,
            )
            for r in rows:
                result[r["entry_id"]].append((from_db(r["discount_start"]), from_db(r["discount_end"])))
        return dict(result)
