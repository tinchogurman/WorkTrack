"""Show errors to the user. Domain errors are shown as-is; anything else is
logged with its traceback and replaced by a generic message (never raw SQL)."""

from __future__ import annotations

import logging
import sqlite3

from PySide6.QtWidgets import QMessageBox, QWidget

from worktrack.core.errors import WorkTrackError
from worktrack.db.errors import translate

log = logging.getLogger(__name__)

GENERIC = (
    "Ocurrió un error inesperado y la operación no se completó.\n"
    "El detalle quedó registrado en el archivo de log."
)


def user_message(exc: BaseException) -> str:
    if isinstance(exc, WorkTrackError):
        return exc.message
    if isinstance(exc, sqlite3.IntegrityError):  # safety net: should be translated earlier
        log.warning("Untranslated integrity error: %s", exc)
        return translate(exc).message
    if isinstance(exc, sqlite3.OperationalError) and "locked" in str(exc).lower():
        log.error("Database locked: %s", exc)
        return "La base de datos está ocupada. Intentá de nuevo en unos segundos."
    log.error("Unexpected error", exc_info=(type(exc), exc, exc.__traceback__))
    return GENERIC


def show_error(parent: QWidget | None, exc: BaseException, title: str = "WorkTrack") -> None:
    message = user_message(exc)
    if isinstance(exc, WorkTrackError):
        QMessageBox.warning(parent, title, message)
    else:
        QMessageBox.critical(parent, title, message)


def confirm(parent: QWidget | None, title: str, text: str, yes: str = "Sí", no: str = "Cancelar") -> bool:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Question)
    box.setWindowTitle(title)
    box.setText(text)
    yes_btn = box.addButton(yes, QMessageBox.AcceptRole)
    no_btn = box.addButton(no, QMessageBox.RejectRole)
    box.setDefaultButton(no_btn)
    box.exec()
    return box.clickedButton() is yes_btn
