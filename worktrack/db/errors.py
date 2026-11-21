"""Translate raw sqlite3.IntegrityError messages into user-facing domain errors.

Services also validate beforehand with specific messages; this is the safety
net that guarantees the UI never shows a raw SQLite error.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from worktrack.core.errors import (
    ActiveSessionExistsError,
    DuplicateNameError,
    IntegrityViolation,
    ValidationError,
    WorkTrackError,
)

log = logging.getLogger(__name__)

CHECK_MESSAGES = {
    "ck_projects_name": "El nombre del proyecto no puede estar vacío.",
    "ck_projects_color": "El color del proyecto no es válido (formato #RRGGBB).",
    "ck_tasks_name": "El nombre de la tarea no puede estar vacío.",
    "ck_entries_end_after_start": "La hora de fin no puede ser anterior a la de inicio.",
    "ck_entries_duration_nonnegative": "La duración no puede ser negativa.",
    "ck_entries_duration_iff_ended": "Una sesión finalizada debe tener duración, y una activa no.",
    "ck_entries_duration_le_elapsed": "La duración no puede superar el tiempo entre inicio y fin.",
}

UNIQUE_MESSAGES = {
    "projects.name": "Ya existe un proyecto con ese nombre.",
    "tasks.project_id, tasks.name": "Ya existe una tarea con ese nombre en este proyecto.",
}


def translate(exc: sqlite3.IntegrityError, fk_error: WorkTrackError | None = None) -> WorkTrackError:
    msg = str(exc)
    if "ux_single_active" in msg:
        return ActiveSessionExistsError()
    if msg.startswith("UNIQUE constraint failed"):
        for key, text in UNIQUE_MESSAGES.items():
            if key in msg:
                return DuplicateNameError(text)
        return IntegrityViolation("Ya existe un registro con esos datos.")
    if msg.startswith("FOREIGN KEY constraint failed"):
        return fk_error or IntegrityViolation(
            "La operación hace referencia a datos inexistentes o en uso."
        )
    if msg.startswith("CHECK constraint failed"):
        for name, text in CHECK_MESSAGES.items():
            if name in msg:
                return ValidationError(text)
        return ValidationError("Algún dato no tiene un formato válido.")
    if msg.startswith("NOT NULL constraint failed"):
        return ValidationError("Falta completar un dato obligatorio.")
    return IntegrityViolation("La operación no se pudo completar porque dejaría datos inconsistentes.")


@contextmanager
def integrity_errors(fk_error: WorkTrackError | None = None) -> Iterator[None]:
    """Re-raise sqlite IntegrityError as a clear domain error (raw text goes to the log).

    `fk_error` gives context to an otherwise generic "FOREIGN KEY constraint
    failed": a task/project mismatch on insert, or RESTRICT on delete.
    """
    try:
        yield
    except sqlite3.IntegrityError as exc:
        translated = translate(exc, fk_error)
        log.warning("Integrity error translated: %r -> %s", str(exc), translated.message)
        raise translated from exc
