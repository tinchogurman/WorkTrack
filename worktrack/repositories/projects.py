"""Data access for projects. Parameterized SQL only, no business rules."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from worktrack.core.models import Project
from worktrack.core.timeutils import from_db, to_db


def _to_project(row: sqlite3.Row) -> Project:
    return Project(
        id=row["id"],
        name=row["name"],
        color=row["color"],
        archived=bool(row["archived"]),
        created_at=from_db(row["created_at"]),
    )


class ProjectRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def list(self, include_archived: bool = False) -> list[Project]:
        sql = "SELECT * FROM projects"
        if not include_archived:
            sql += " WHERE archived = 0"
        sql += " ORDER BY archived, name COLLATE NOCASE"
        return [_to_project(r) for r in self.conn.execute(sql)]

    def get(self, project_id: int) -> Project | None:
        row = self.conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return _to_project(row) if row else None

    def find_by_name(self, name: str) -> Project | None:
        row = self.conn.execute("SELECT * FROM projects WHERE name = ?", (name,)).fetchone()
        return _to_project(row) if row else None

    def create(self, name: str, color: str, created_at: datetime) -> int:
        cur = self.conn.execute(
            "INSERT INTO projects (name, color, created_at) VALUES (?, ?, ?)",
            (name, color, to_db(created_at)),
        )
        return cur.lastrowid

    def update(self, project_id: int, name: str, color: str) -> None:
        self.conn.execute(
            "UPDATE projects SET name = ?, color = ? WHERE id = ?", (name, color, project_id)
        )

    def set_archived(self, project_id: int, archived: bool) -> None:
        self.conn.execute(
            "UPDATE projects SET archived = ? WHERE id = ?", (int(archived), project_id)
        )

    def delete(self, project_id: int) -> None:
        self.conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))

    def count_entries(self, project_id: int) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM time_entries WHERE project_id = ?", (project_id,)
        ).fetchone()[0]
