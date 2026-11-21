"""Application bootstrap: logging, single instance, database, recovery, main window."""

from __future__ import annotations

import logging
import sys

from PySide6.QtCore import QLockFile
from PySide6.QtWidgets import QApplication, QMessageBox

from worktrack import APP_NAME, __version__
from worktrack.db.migrations import SchemaTooNewError
from worktrack.logging_setup import setup_logging
from worktrack.paths import db_path, lock_path, logs_dir
from worktrack.services.context import AppServices
from worktrack.ui.dialogs.recovery_dialog import RecoveryDialog
from worktrack.ui.errors import GENERIC, user_message
from worktrack.ui.icons import app_icon
from worktrack.ui.main_window import MainWindow
from worktrack.ui.theme import apply_theme

log = logging.getLogger("worktrack")


def _install_excepthook() -> None:
    def hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        log.critical("Unhandled exception", exc_info=(exc_type, exc, tb))
        if QApplication.instance() is not None:
            QMessageBox.critical(None, APP_NAME, GENERIC)

    sys.excepthook = hook


def main(argv: list[str] | None = None) -> int:
    log_file = setup_logging(logs_dir())
    _install_excepthook()
    log.info("Starting %s %s (db=%s)", APP_NAME, __version__, db_path())

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(app_icon())
    apply_theme(app)

    # Single instance: a second window would mistake the running session for an orphan.
    lock = QLockFile(str(lock_path()))
    lock.setStaleLockTime(0)  # only stale if the owning process is gone
    if not lock.tryLock(200):
        log.info("Another instance is running; exiting")
        QMessageBox.information(None, APP_NAME, "WorkTrack ya está abierto.")
        return 0

    try:
        services = AppServices.open(db_path())
    except SchemaTooNewError as exc:
        log.error("%s", exc)
        QMessageBox.critical(None, APP_NAME, str(exc))
        return 1
    except Exception as exc:  # noqa: BLE001
        log.exception("Could not open the database")
        QMessageBox.critical(
            None,
            APP_NAME,
            f"No se pudo abrir la base de datos.\n\n{user_message(exc)}\n\nLog: {log_file}",
        )
        return 1

    try:
        info = services.recovery.check()
        if info is not None:
            dialog = RecoveryDialog(services.recovery, info)
            dialog.exec()
            log.info("Recovery choice: %s", dialog.choice)

        window = MainWindow(services)
        window.show()
        code = app.exec()
    finally:
        services.close()
        lock.unlock()
        log.info("Exited")
    return code
