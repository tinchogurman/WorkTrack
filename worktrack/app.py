"""Application bootstrap: logging, settings, single instance, database,
crash recovery, main window, tray and power events."""

from __future__ import annotations

import logging
import sys

from PySide6.QtCore import QLockFile
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from worktrack import APP_NAME, __version__
from worktrack.core.timeutils import set_time_format
from worktrack.db.migrations import SchemaTooNewError
from worktrack.logging_setup import setup_logging
from worktrack.paths import db_path, lock_path, logs_dir, settings_path
from worktrack.services.context import AppServices
from worktrack.settings import SettingsStore
from worktrack.ui.dialogs.interruption_dialog import resolve_pending
from worktrack.ui.dialogs.recovery_dialog import RecoveryDialog
from worktrack.ui.errors import GENERIC, user_message
from worktrack.ui.icons import app_icon
from worktrack.ui.main_window import MainWindow
from worktrack.ui.power_events import install_power_monitor
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


def _recover(services: AppServices) -> None:
    info = services.recovery.check()
    if info is None:
        return
    entry_id = info.view.entry.id
    dialog = RecoveryDialog(services.recovery, info)
    dialog.exec()
    log.info("Recovery choice: %s", dialog.choice)
    if dialog.choice and dialog.choice.startswith("finish"):
        # The session is closed now: settle interruptions detected before the crash.
        resolve_pending(services, entry_id, "La sesión recuperada tenía un intervalo sin resolver.")


def main(argv: list[str] | None = None) -> int:
    log_file = setup_logging(logs_dir())
    _install_excepthook()
    log.info("Starting %s %s (db=%s)", APP_NAME, __version__, db_path())

    store = SettingsStore(settings_path())
    settings = store.load()
    set_time_format(settings.time_format)

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(app_icon())
    apply_theme(app)
    tray_available = QSystemTrayIcon.isSystemTrayAvailable()
    # With a tray icon the app keeps running while its window is hidden.
    app.setQuitOnLastWindowClosed(not tray_available)

    # Single instance: a second window would mistake the running session for an orphan.
    lock = QLockFile(str(lock_path()))
    lock.setStaleLockTime(0)  # only stale if the owning process is gone
    if not lock.tryLock(200):
        log.info("Another instance is running; exiting")
        QMessageBox.information(None, APP_NAME, "WorkTrack ya está abierto (revisá la bandeja del sistema).")
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

    window = None
    try:
        _recover(services)

        window = MainWindow(services, settings, store)
        power = install_power_monitor(app)
        if power is not None:
            power.suspended.connect(window.timer_view.on_suspend)
            power.resumed.connect(window.timer_view.on_resume)

        if settings.start_minimized and window.minimizes_to_tray():
            window.hide_to_tray()
        elif settings.start_minimized:
            window.showMinimized()
        else:
            window.show()
        code = app.exec()
    finally:
        if window is not None:
            window.shutdown()
        services.close()
        lock.unlock()
        log.info("Exited")
    return code
