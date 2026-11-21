"""Data access for tasks. Parameterized SQL only, no business rules."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from worktrack.core.models import Task
from worktrack.core.timeutils import from_db, to_db


def _to_task(row: sqlite3.Row) -> Task:
    return Task(
        id=row["id"],
        project_id=row["project_id"],
        name=row["name"],
        description=row["description"],
        archived=bool(row["archived"]),
        created_at=from_db(row["created_at"]),
    )


class TaskRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def list_for_project(self, project_id: int, include_archived: bool = False) -> list[Task]:
        sql = "SELECT * FROM tasks WHERE project_id = ?"
        if not include_archived:
            sql += " AND archived = 0"
        sql += " ORDER BY archived, name COLLATE NOCASE"
        return [_to_task(r) for r in self.conn.execute(sql, (project_id,))]

    def get(self, task_id: int) -> Task | None:
        row = self.conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return _to_task(row) if row else None

    def find_by_name(self, project_id: int, name: str) -> Task | None:
        # `name` is declared COLLATE NOCASE, so this match is case-insensitive.
        row = self.conn.execute(
            "SELECT * FROM tasks WHERE project_id = ? AND name = ?", (project_id, name)
        ).fetchone()
        return _to_task(row) if row else None

    def create(
        self, project_id: int, name: str, description: str | None, created_at: datetime
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO tasks (project_id, name, description, created_at) VALUES (?, ?, ?, ?)",
            (project_id, name, description, to_db(created_at)),
        )
        return cur.lastrowid

    def update(self, task_id: int, name: str, description: str | None) -> None:
        self.conn.execute(
            "UPDATE tasks SET name = ?, description = ? WHERE id = ?", (name, description, task_id)
        )

    def set_archived(self, task_id: int, archived: bool) -> None:
        self.conn.execute("UPDATE tasks SET archived = ? WHERE id = ?", (int(archived), task_id))

    def delete(self, task_id: int) -> None:
        self.conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))

    def delete_for_project(self, project_id: int) -> None:
        self.conn.execute("DELETE FROM tasks WHERE project_id = ?", (project_id,))

    def count_entries(self, task_id: int) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM time_entries WHERE task_id = ?", (task_id,)
        ).fetchone()[0]
