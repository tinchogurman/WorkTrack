"""Database schema (version 1).

Integrity rules enforced by SQLite itself (not only by the UI):
- single active session: partial unique index ux_single_active
- task belongs to the entry's project: composite FK -> tasks(id, project_id)
- valid durations: named CHECK constraints
- ON DELETE RESTRICT for projects/tasks referenced by sessions

duration_seconds is *worked* time and may be lower than end - start. This
leaves room for discounting suspensions (phase 3) and a future breaks table
(pause/resume) without changing this table.
"""

TS_GLOB = "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z'"
COLOR_GLOB = "'#[0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f]'"

SCHEMA_V1 = f"""
CREATE TABLE projects (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL COLLATE NOCASE,
    color       TEXT    NOT NULL,
    archived    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL,
    CONSTRAINT uq_projects_name UNIQUE (name),
    CONSTRAINT ck_projects_name CHECK (length(trim(name)) > 0),
    CONSTRAINT ck_projects_color CHECK (color GLOB {COLOR_GLOB}),
    CONSTRAINT ck_projects_archived CHECK (archived IN (0, 1)),
    CONSTRAINT ck_projects_created_at CHECK (created_at GLOB {TS_GLOB})
);

CREATE TABLE tasks (
    id          INTEGER PRIMARY KEY,
    project_id  INTEGER NOT NULL
                REFERENCES projects (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    name        TEXT    NOT NULL COLLATE NOCASE,
    description TEXT,
    archived    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL,
    CONSTRAINT uq_tasks_project_name UNIQUE (project_id, name),
    CONSTRAINT uq_tasks_id_project UNIQUE (id, project_id),
    CONSTRAINT ck_tasks_name CHECK (length(trim(name)) > 0),
    CONSTRAINT ck_tasks_archived CHECK (archived IN (0, 1)),
    CONSTRAINT ck_tasks_created_at CHECK (created_at GLOB {TS_GLOB})
);

CREATE TABLE time_entries (
    id               INTEGER PRIMARY KEY,
    project_id       INTEGER NOT NULL
                     REFERENCES projects (id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    task_id          INTEGER NOT NULL,
    start_time       TEXT    NOT NULL,
    end_time         TEXT,
    duration_seconds INTEGER,
    description      TEXT,
    last_heartbeat   TEXT,
    created_at       TEXT    NOT NULL,
    CONSTRAINT fk_entries_task_project FOREIGN KEY (task_id, project_id)
        REFERENCES tasks (id, project_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT ck_entries_start_format CHECK (start_time GLOB {TS_GLOB}),
    CONSTRAINT ck_entries_end_format CHECK (end_time IS NULL OR end_time GLOB {TS_GLOB}),
    CONSTRAINT ck_entries_heartbeat_format
        CHECK (last_heartbeat IS NULL OR last_heartbeat GLOB {TS_GLOB}),
    CONSTRAINT ck_entries_created_at CHECK (created_at GLOB {TS_GLOB}),
    CONSTRAINT ck_entries_end_after_start CHECK (end_time IS NULL OR end_time >= start_time),
    CONSTRAINT ck_entries_duration_nonnegative
        CHECK (duration_seconds IS NULL OR duration_seconds >= 0),
    CONSTRAINT ck_entries_duration_iff_ended
        CHECK ((end_time IS NULL) = (duration_seconds IS NULL)),
    CONSTRAINT ck_entries_duration_le_elapsed CHECK (
        duration_seconds IS NULL
        OR duration_seconds <= unixepoch(end_time) - unixepoch(start_time)
    )
);

CREATE UNIQUE INDEX ux_single_active ON time_entries ((1)) WHERE end_time IS NULL;
CREATE INDEX ix_tasks_project ON tasks (project_id);
CREATE INDEX ix_entries_start ON time_entries (start_time);
CREATE INDEX ix_entries_project_start ON time_entries (project_id, start_time);
CREATE INDEX ix_entries_task ON time_entries (task_id, project_id);
"""

# Version 2: suspected interruptions (suspend/resume, long gaps between
# heartbeats) detected during a session. Nothing is discounted unless the
# user decides so: 'pending' -> 'kept' | 'discounted' | 'adjusted'.
# The discounted range is stored separately from the detected one (audit),
# and is the basis for a future pause/resume feature.
SCHEMA_V2 = f"""
CREATE TABLE session_interruptions (
    id              INTEGER PRIMARY KEY,
    entry_id        INTEGER NOT NULL
                    REFERENCES time_entries (id) ON DELETE CASCADE ON UPDATE RESTRICT,
    start_time      TEXT    NOT NULL,
    end_time        TEXT    NOT NULL,
    source          TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'pending',
    discount_start  TEXT,
    discount_end    TEXT,
    created_at      TEXT    NOT NULL,
    resolved_at     TEXT,
    CONSTRAINT ck_int_start_format CHECK (start_time GLOB {TS_GLOB}),
    CONSTRAINT ck_int_end_format CHECK (end_time GLOB {TS_GLOB}),
    CONSTRAINT ck_int_created_format CHECK (created_at GLOB {TS_GLOB}),
    CONSTRAINT ck_int_interval CHECK (end_time > start_time),
    CONSTRAINT ck_int_source CHECK (source IN ('heartbeat_gap', 'power_event')),
    CONSTRAINT ck_int_status CHECK (status IN ('pending', 'kept', 'discounted', 'adjusted')),
    CONSTRAINT ck_int_discount_iff_status CHECK (
        (status IN ('discounted', 'adjusted')) = (discount_start IS NOT NULL AND discount_end IS NOT NULL)
    ),
    CONSTRAINT ck_int_discount_interval CHECK (
        discount_start IS NULL OR (
            discount_start GLOB {TS_GLOB} AND discount_end GLOB {TS_GLOB} AND discount_end > discount_start
        )
    )
);

CREATE INDEX ix_interruptions_entry ON session_interruptions (entry_id, status);
"""

EXPECTED_TABLES = frozenset({"projects", "tasks", "time_entries"})
