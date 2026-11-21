"""Schema versioning via PRAGMA user_version."""

from __future__ import annotations

import logging
import sqlite3

from worktrack.db.schema import SCHEMA_V1

log = logging.getLogger(__name__)

# MIGRATIONS[i] upgrades schema version i -> i + 1.
MIGRATIONS: list[str] = [SCHEMA_V1]
SCHEMA_VERSION = len(MIGRATIONS)


class SchemaTooNewError(RuntimeError):
    pass


def current_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def migrate(conn: sqlite3.Connection) -> int:
    version = current_version(conn)
    if version > SCHEMA_VERSION:
        raise SchemaTooNewError(
            f"La base de datos pertenece a una versión más nueva de WorkTrack "
            f"(esquema {version}; esta versión soporta hasta {SCHEMA_VERSION})."
        )
    while version < SCHEMA_VERSION:
        target = version + 1
        log.info("Migrating database schema %s -> %s", version, target)
        # The whole upgrade, version bump included, is a single transaction.
        conn.executescript(
            f"BEGIN IMMEDIATE;\n{MIGRATIONS[version]}\nPRAGMA user_version = {target};\nCOMMIT;"
        )
        version = target
    return version
