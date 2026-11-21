"""Acceptance 5e: backup, restore, and a safety backup taken before restoring."""

from __future__ import annotations

import sqlite3
from datetime import timedelta

import pytest

from worktrack.core.errors import ValidationError
from worktrack.db.migrations import SCHEMA_VERSION
from worktrack.services.backup_service import InvalidBackupError
from worktrack.services.entry_service import EntryDraft


def add_entry(services, project, hours_ago, task="T"):
    now = services.clock.now()
    return services.entries.add_manual(
        EntryDraft(project.id, task, now - timedelta(hours=hours_ago), now - timedelta(hours=hours_ago - 1))
    )


def test_backup_is_consistent_copy(services, project, tmp_path):
    add_entry(services, project, 5)
    path = services.backups.create_backup()
    assert path.parent == services.backups_dir and path.name.startswith("worktrack_")
    info = services.backups.validate(path)
    assert (info.projects, info.entries, info.schema_version) == (1, 1, SCHEMA_VERSION)
    assert not info.has_active_session
    # a single self-contained file (not WAL)
    conn = sqlite3.connect(path)
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    conn.close()


def test_backup_names_do_not_collide(services):
    a = services.backups.create_backup()
    b = services.backups.create_backup()
    assert a != b and a.exists() and b.exists()
    assert len(services.backups.list_backups()) == 2


def test_restore_roundtrip_with_safety_backup(services, project, other_project):
    add_entry(services, project, 5, "Antes")
    backup = services.backups.create_backup()

    # changes after the backup
    add_entry(services, other_project, 3, "Después")
    services.projects.create_project("Nuevo", "#123456")
    assert len(services.entries.list_entries()) == 2

    result = services.backups.restore(backup)

    # current state == backup
    views = services.entries.list_entries()
    assert [v.task_name for v in views] == ["Antes"]
    assert "Nuevo" not in [p.name for p in services.projects.list_projects()]
    # the safety backup was taken BEFORE restoring and holds the replaced state
    assert result.safety_backup.name.startswith("pre-restore_")
    safety = services.backups.validate(result.safety_backup)
    assert safety.entries == 2 and safety.projects == 3
    # the reopened connection still enforces integrity
    assert services.conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_restore_refused_with_active_session(services, project):
    backup = services.backups.create_backup()
    services.timer.start(project.id, "En curso")
    with pytest.raises(ValidationError, match="sesión en curso"):
        services.backups.restore(backup)
    assert services.timer.get_active() is not None
    assert not any(b.path.name.startswith("pre-restore") for b in services.backups.list_backups())


def test_restored_backup_with_active_session_triggers_recovery(services, project, clock):
    services.timer.start(project.id, "En curso")
    clock.advance(minutes=10)
    services.timer.heartbeat()
    backup = services.backups.create_backup()
    assert services.backups.validate(backup).has_active_session
    services.timer.stop()
    services.backups.restore(backup)
    assert services.recovery.check() is not None


def test_invalid_files_rejected(services, tmp_path):
    text = tmp_path / "nota.db"
    text.write_text("esto no es una base", encoding="utf-8")
    with pytest.raises(InvalidBackupError, match="SQLite"):
        services.backups.validate(text)

    other = tmp_path / "otra.db"
    conn = sqlite3.connect(other)
    conn.execute("CREATE TABLE cosas (id INTEGER)")
    conn.commit()
    conn.close()
    with pytest.raises(InvalidBackupError, match="faltan tablas"):
        services.backups.validate(other)

    with pytest.raises(InvalidBackupError, match="no existe"):
        services.backups.validate(tmp_path / "nada.db")


def test_newer_schema_rejected(services):
    backup = services.backups.create_backup()
    conn = sqlite3.connect(backup)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    conn.commit()
    conn.close()
    with pytest.raises(InvalidBackupError, match="más nueva"):
        services.backups.restore(backup)


def test_corrupted_backup_rejected_and_nothing_changes(services, project):
    add_entry(services, project, 5)
    backup = services.backups.create_backup()
    data = bytearray(backup.read_bytes())
    for i in range(4096 + 100, min(len(data), 4096 * 3)):  # damage pages after the header
        data[i] = 0xFF
    backup.write_bytes(bytes(data))
    with pytest.raises(InvalidBackupError):
        services.backups.restore(backup)
    assert len(services.entries.list_entries()) == 1


def test_cannot_restore_live_database(services):
    with pytest.raises(InvalidBackupError, match="en uso"):
        services.backups.restore(services.db_path)


def test_failed_copy_rolls_back(services, project, monkeypatch):
    add_entry(services, project, 5)
    backup = services.backups.create_backup()
    add_entry(services, project, 3, "Posterior")

    import worktrack.services.backup_service as bs

    real_copy = bs._copy_database
    calls = {"n": 0}

    def flaky(source, target):
        calls["n"] += 1
        if calls["n"] == 1:
            raise sqlite3.OperationalError("disk I/O error")
        real_copy(source, target)

    monkeypatch.setattr(bs, "_copy_database", flaky)
    with pytest.raises(bs.RestoreError, match="estado anterior"):
        services.backups.restore(backup)
    assert len(services.entries.list_entries()) == 2  # previous state kept
