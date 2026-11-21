"""Main window: side navigation + stacked sections."""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from worktrack import APP_NAME
from worktrack.services.context import AppServices
from worktrack.settings import Settings, SettingsStore
from worktrack.ui.tray import TrayIcon
from worktrack.ui.icons import app_icon
from worktrack.ui.signals import AppSignals
from worktrack.ui.views.dashboard_view import DashboardView
from worktrack.ui.views.history_view import HistoryView
from worktrack.ui.views.projects_view import ProjectsView
from worktrack.ui.views.reports_view import ReportsView
from worktrack.ui.views.timer_view import TimerView
from worktrack.ui.widgets import muted, page_title

log = logging.getLogger(__name__)

# (label, available, phase)
SECTIONS = [
    ("Timer", True, None),
    ("Dashboard", True, None),
    ("Projects", True, None),
    ("History", True, None),
    ("Reports", True, None),
    ("Settings", False, 3),
]


def _placeholder(name: str, phase: int) -> QWidget:
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(28, 24, 28, 24)
    v.addWidget(page_title(name))
    v.addWidget(muted(f"Disponible en la Fase {phase}."))
    v.addStretch()
    return w


class MainWindow(QMainWindow):
    def __init__(
        self,
        services: AppServices,
        settings: Settings | None = None,
        settings_store: SettingsStore | None = None,
        use_tray: bool = True,
    ) -> None:
        super().__init__()
        self.services = services
        self.settings = settings or Settings()
        self.settings_store = settings_store
        self.signals = AppSignals(self)
        self._icon_active: bool | None = None
        self._tray_hint_shown = False
        self._quitting = False
        self.setWindowTitle(APP_NAME)
        self.resize(1100, 720)
        self.setMinimumSize(860, 560)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(200)
        sv = QVBoxLayout(sidebar)
        sv.setContentsMargins(0, 0, 0, 0)
        title = QLabel(APP_NAME)
        title.setObjectName("AppTitle")
        sv.addWidget(title)
        self.nav = QListWidget()
        self.nav.setFocusPolicy(Qt.StrongFocus)
        sv.addWidget(self.nav, 1)
        self.sidebar_status = QLabel("")
        self.sidebar_status.setObjectName("SidebarStatus")
        self.sidebar_status.setWordWrap(True)
        sv.addWidget(self.sidebar_status)

        self.stack = QStackedWidget()
        self.timer_view = TimerView(services, self.signals)
        self.projects_view = ProjectsView(services, self.signals)
        self.history_view = HistoryView(services, self.signals)
        self.dashboard_view = DashboardView(services, self.signals)
        self.reports_view = ReportsView(services, self.signals)
        built = {
            "Timer": self.timer_view,
            "Dashboard": self.dashboard_view,
            "Projects": self.projects_view,
            "History": self.history_view,
            "Reports": self.reports_view,
        }

        for i, (name, available, phase) in enumerate(SECTIONS):
            item = QListWidgetItem(name)
            if not available:
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled & ~Qt.ItemIsSelectable)
                item.setToolTip(f"Disponible en la Fase {phase}")
            else:
                item.setToolTip(f"{name} (Ctrl+{i + 1})")
            self.nav.addItem(item)
            self.stack.addWidget(built.get(name) or _placeholder(name, phase))
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

        layout.addWidget(sidebar)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        for i in range(len(SECTIONS)):
            QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self, lambda i=i: self.go_to(i))
        QShortcut(QKeySequence("Ctrl+Space"), self, self.timer_view.toggle)

        self.tray: TrayIcon | None = None
        if use_tray and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = TrayIcon(self)
            self.tray.show()
            self.timer_view.interruption_detected.connect(self._notify_interruption)

        self.timer_view.elapsed_changed.connect(self._on_elapsed)
        self.timer_view.go_to_projects.connect(lambda: self.go_to(2))
        self.signals.session_state_changed.connect(self._on_session_state)
        self._on_session_state()

    # --- tray ----------------------------------------------------------------
    def minimizes_to_tray(self) -> bool:
        return self.tray is not None and self.settings.minimize_to_tray

    def show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def hide_to_tray(self) -> None:
        self.hide()
        if self.tray is not None and not self._tray_hint_shown:
            self._tray_hint_shown = True
            self.tray.showMessage(
                APP_NAME, "WorkTrack sigue funcionando en la bandeja del sistema.",
                QSystemTrayIcon.Information, 4000,
            )

    def stop_from_tray(self) -> None:
        self.timer_view.stop()

    def quit_from_tray(self) -> None:
        self.close()  # same confirmation flow as the window's X

    def _notify_interruption(self, message: str) -> None:
        if self.tray is not None:
            self.tray.showMessage(f"{APP_NAME}: posible interrupción", message, QSystemTrayIcon.Warning, 10000)

    def changeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange and self.isMinimized() and self.minimizes_to_tray():
            QTimer.singleShot(0, self.hide_to_tray)

    def apply_settings(self, settings: Settings) -> None:
        self.settings = settings

    def shutdown(self) -> None:
        """Stop every periodic timer (before the database connection is closed)."""
        for timer in self.findChildren(QTimer):
            timer.stop()

    def go_to(self, index: int) -> None:
        if SECTIONS[index][1]:
            self.nav.setCurrentRow(index)

    def _on_elapsed(self, text: str) -> None:
        self.setWindowTitle(f"▶ {text} — {APP_NAME}" if text else APP_NAME)
        if text:
            self.sidebar_status.setText(f"● En curso\n{text}")
        if self.tray is not None:
            self.tray.set_state(bool(text), text)

    def _on_session_state(self) -> None:
        running = self.timer_view.is_running()
        if running != self._icon_active:
            self.setWindowIcon(app_icon(active=running))
            self._icon_active = running
        self.sidebar_status.setStyleSheet(
            "color: #22C55E; background: transparent;" if running else ""
        )
        if not running:
            self.sidebar_status.setText("Sin sesión activa")
            self.setWindowTitle(APP_NAME)
            if self.tray is not None:
                self.tray.set_state(False, "")

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if not self._confirm_exit():
            event.ignore()
            return
        event.accept()
        self._quitting = True
        if self.tray is not None:
            self.tray.hide()
        if not QApplication.quitOnLastWindowClosed():  # tray mode keeps the app alive otherwise
            QApplication.quit()

    def _confirm_exit(self) -> bool:
        """True if the app may exit. Handles a running session per the settings."""
        if not self.timer_view.is_running():
            return True
        if not self.settings.confirm_exit_with_active:
            # Preference: no question; stop and save now (pending interruptions stay
            # counted, never discounted without asking).
            self.timer_view.stop(ask_interruptions=False)
            return not self.timer_view.is_running()
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle("Salir de WorkTrack")
        box.setText("Hay una sesión en curso.")
        box.setInformativeText(
            "Podés detenerla y guardarla ahora, o salir dejándola abierta: al volver a "
            "abrir WorkTrack vas a poder continuarla o finalizarla."
        )
        stop_btn = box.addButton("Detener y salir", QMessageBox.AcceptRole)
        keep_btn = box.addButton("Salir y dejarla en curso", QMessageBox.DestructiveRole)
        cancel_btn = box.addButton("Cancelar", QMessageBox.RejectRole)
        box.setDefaultButton(stop_btn)
        box.setEscapeButton(cancel_btn)
        box.exec()
        clicked = box.clickedButton()
        if clicked is stop_btn:
            self.timer_view.stop()
            return not self.timer_view.is_running()  # False if stopping failed
        if clicked is keep_btn:
            try:
                self.services.timer.heartbeat()  # last-seen = moment of exit
            except Exception:
                log.exception("Final heartbeat failed")
            log.info("Exiting with an active session left open")
            return True
        return False
