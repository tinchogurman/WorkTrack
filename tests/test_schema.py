"""Integrity rules enforced by SQLite itself, bypassing the business layer."""

from __future__ import annotations

import sqlite3

import pytest

from worktrack.core.errors import (
    ActiveSessionExistsError,
    DuplicateNameError,
    InUseError,
    TaskProjectMismatchError,
    ValidationError,
)
from worktrack.db.connection import connect, transaction
from worktrack.db.errors import integrity_errors, translate
from worktrack.db.migrations import SCHEMA_VERSION, SchemaTooNewError, current_version, migrate
from worktrack.db.schema import EXPECTED_TABLES

NOW = "2026-03-10T13:00:00Z"


def add_project(conn, name="P1", color="#22c55e"):
    return conn.execute(
        "INSERT INTO projects (name, color, created_at) VALUES (?, ?, ?)", (name, color, NOW)
    ).lastrowid


def add_task(conn, project_id, name="T1"):
    return conn.execute(
        "INSERT INTO tasks (project_id, name, created_at) VALUES (?, ?, ?)",
        (project_id, name, NOW),
    ).lastrowid


def add_entry(conn, project_id, task_id, start, end=None, duration=None):
    return conn.execute(
        "INSERT INTO time_entries (project_id, task_id, start_time, end_time, duration_seconds,"
        " created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (project_id, task_id, start, end, duration, NOW),
    ).lastrowid


@pytest.fixture
def pt(conn):
    pid = add_project(conn)
    return pid, add_task(conn, pid)


def test_foreign_keys_enabled_on_every_connection(db_file, conn):
    other = connect(db_file)
    try:
        assert other.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        other.close()


def test_schema_created_and_versioned(conn):
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert EXPECTED_TABLES <= tables
    assert current_version(conn) == SCHEMA_VERSION


def test_migrate_is_idempotent(conn):
    assert migrate(conn) == SCHEMA_VERSION


def test_refuses_newer_schema(conn):
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    with pytest.raises(SchemaTooNewError):
        migrate(conn)


# --- single active session (acceptance 5b) -----------------------------------

def test_second_active_session_rejected_by_database(conn, pt):
    pid, tid = pt
    add_entry(conn, pid, tid, "2026-03-10T10:00:00Z")
    with pytest.raises(sqlite3.IntegrityError, match="ux_single_active"):
        add_entry(conn, pid, tid, "2026-03-10T11:00:00Z")
    assert conn.execute("SELECT COUNT(*) FROM time_entries WHERE end_time IS NULL").fetchone()[0] == 1


def test_second_active_rejected_even_with_other_project(conn, pt):
    pid, tid = pt
    pid2 = add_project(conn, "P2")
    tid2 = add_task(conn, pid2)
    add_entry(conn, pid, tid, "2026-03-10T10:00:00Z")
    with pytest.raises(sqlite3.IntegrityError):
        add_entry(conn, pid2, tid2, "2026-03-10T11:00:00Z")


def test_reopening_a_finished_session_while_another_is_active_fails(conn, pt):
    pid, tid = pt
    done = add_entry(conn, pid, tid, "2026-03-10T08:00:00Z", "2026-03-10T09:00:00Z", 3600)
    add_entry(conn, pid, tid, "2026-03-10T10:00:00Z")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "UPDATE time_entries SET end_time = NULL, duration_seconds = NULL WHERE id = ?", (done,)
        )


def test_many_finished_sessions_allowed(conn, pt):
    pid, tid = pt
    add_entry(conn, pid, tid, "2026-03-10T08:00:00Z", "2026-03-10T09:00:00Z", 3600)
    add_entry(conn, pid, tid, "2026-03-10T09:00:00Z", "2026-03-10T10:00:00Z", 3600)
    add_entry(conn, pid, tid, "2026-03-10T10:00:00Z")


def test_active_index_translates_to_clear_error(conn, pt):
    pid, tid = pt
    add_entry(conn, pid, tid, "2026-03-10T10:00:00Z")
    with pytest.raises(ActiveSessionExistsError):
        with integrity_errors():
            add_entry(conn, pid, tid, "2026-03-10T11:00:00Z")


# --- task belongs to project -------------------------------------------------

def test_task_from_other_project_rejected(conn, pt):
    pid, tid = pt
    pid2 = add_project(conn, "P2")
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        add_entry(conn, pid2, tid, "2026-03-10T08:00:00Z", "2026-03-10T09:00:00Z", 3600)


def test_cannot_move_entry_to_other_project_keeping_task(conn, pt):
    pid, tid = pt
    pid2 = add_project(conn, "P2")
    eid = add_entry(conn, pid, tid, "2026-03-10T08:00:00Z", "2026-03-10T09:00:00Z", 3600)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE time_entries SET project_id = ? WHERE id = ?", (pid2, eid))


def test_cannot_move_task_with_entries_to_other_project(conn, pt):
    pid, tid = pt
    pid2 = add_project(conn, "P2")
    add_entry(conn, pid, tid, "2026-03-10T08:00:00Z", "2026-03-10T09:00:00Z", 3600)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE tasks SET project_id = ? WHERE id = ?", (pid2, tid))


def test_fk_error_translated_with_context(conn, pt):
    pid, tid = pt
    pid2 = add_project(conn, "P2")
    with pytest.raises(TaskProjectMismatchError):
        with integrity_errors(fk_error=TaskProjectMismatchError()):
            add_entry(conn, pid2, tid, "2026-03-10T08:00:00Z", "2026-03-10T09:00:00Z", 3600)


# --- durations ---------------------------------------------------------------

def test_end_before_start_rejected(conn, pt):
    pid, tid = pt
    with pytest.raises(sqlite3.IntegrityError, match="ck_entries_end_after_start"):
        add_entry(conn, pid, tid, "2026-03-10T10:00:00Z", "2026-03-10T09:00:00Z", 0)


def test_negative_duration_rejected(conn, pt):
    pid, tid = pt
    with pytest.raises(sqlite3.IntegrityError, match="ck_entries_duration_nonnegative"):
        add_entry(conn, pid, tid, "2026-03-10T09:00:00Z", "2026-03-10T10:00:00Z", -5)


def test_duration_longer_than_interval_rejected(conn, pt):
    pid, tid = pt
    with pytest.raises(sqlite3.IntegrityError, match="ck_entries_duration_le_elapsed"):
        add_entry(conn, pid, tid, "2026-03-10T09:00:00Z", "2026-03-10T10:00:00Z", 3601)


def test_duration_shorter_than_interval_allowed(conn, pt):
    """Worked time < elapsed time is valid (discounted suspension, future pauses)."""
    pid, tid = pt
    add_entry(conn, pid, tid, "2026-03-10T09:00:00Z", "2026-03-10T10:00:00Z", 1800)


def test_finished_session_requires_duration(conn, pt):
    pid, tid = pt
    with pytest.raises(sqlite3.IntegrityError, match="ck_entries_duration_iff_ended"):
        add_entry(conn, pid, tid, "2026-03-10T09:00:00Z", "2026-03-10T10:00:00Z", None)
    with pytest.raises(sqlite3.IntegrityError, match="ck_entries_duration_iff_ended"):
        add_entry(conn, pid, tid, "2026-03-10T09:00:00Z", None, 60)


def test_bad_timestamp_format_rejected(conn, pt):
    pid, tid = pt
    with pytest.raises(sqlite3.IntegrityError, match="ck_entries_start_format"):
        add_entry(conn, pid, tid, "2026-03-10 09:00:00", "2026-03-10T10:00:00Z", 60)


def test_check_errors_translated(conn, pt):
    pid, tid = pt
    with pytest.raises(ValidationError, match="anterior"):
        with integrity_errors():
            add_entry(conn, pid, tid, "2026-03-10T10:00:00Z", "2026-03-10T09:00:00Z", 0)


# --- ON DELETE RESTRICT ------------------------------------------------------

def test_delete_project_with_entries_restricted(conn, pt):
    pid, tid = pt
    add_entry(conn, pid, tid, "2026-03-10T08:00:00Z", "2026-03-10T09:00:00Z", 3600)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM projects WHERE id = ?", (pid,))


def test_delete_task_with_entries_restricted(conn, pt):
    pid, tid = pt
    add_entry(conn, pid, tid, "2026-03-10T08:00:00Z", "2026-03-10T09:00:00Z", 3600)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM tasks WHERE id = ?", (tid,))


def test_delete_project_with_tasks_restricted(conn, pt):
    pid, _ = pt
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM projects WHERE id = ?", (pid,))


def test_restrict_translated(conn, pt):
    pid, tid = pt
    add_entry(conn, pid, tid, "2026-03-10T08:00:00Z", "2026-03-10T09:00:00Z", 3600)
    with pytest.raises(InUseError):
        with integrity_errors(fk_error=InUseError("en uso")):
            conn.execute("DELETE FROM tasks WHERE id = ?", (tid,))


# --- names and colors --------------------------------------------------------

def test_project_name_unique_case_insensitive(conn):
    add_project(conn, "Data Engineering")
    with pytest.raises(sqlite3.IntegrityError) as info:
        add_project(conn, "data engineering")
    assert isinstance(translate(info.value), DuplicateNameError)


def test_task_name_unique_per_project_only(conn):
    p1, p2 = add_project(conn, "A"), add_project(conn, "B")
    add_task(conn, p1, "Review")
    add_task(conn, p2, "Review")
    with pytest.raises(sqlite3.IntegrityError) as info:
        add_task(conn, p1, "REVIEW")
    assert "tarea" in translate(info.value).message


def test_invalid_color_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError, match="ck_projects_color"):
        add_project(conn, "X", "red")


def test_blank_names_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError, match="ck_projects_name"):
        add_project(conn, "   ")


# --- transactions ------------------------------------------------------------

def test_transaction_rolls_back_on_error(conn):
    with pytest.raises(RuntimeError):
        with transaction(conn):
            add_project(conn, "Temp")
            raise RuntimeError("boom")
    assert conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0


def test_raw_message_never_leaks_through_translation(conn, pt):
    pid, tid = pt
    add_entry(conn, pid, tid, "2026-03-10T10:00:00Z")
    try:
        with integrity_errors():
            add_entry(conn, pid, tid, "2026-03-10T11:00:00Z")
    except ActiveSessionExistsError as exc:
        assert "constraint" not in exc.message.lower()
        assert "UNIQUE" not in exc.message
