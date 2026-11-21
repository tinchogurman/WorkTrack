"""Main window: side navigation + stacked sections."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from worktrack import APP_NAME
from worktrack.services.context import AppServices
from worktrack.ui.icons import app_icon
from worktrack.ui.signals import AppSignals
from worktrack.ui.views.history_view import HistoryView
from worktrack.ui.views.projects_view import ProjectsView
from worktrack.ui.views.timer_view import TimerView
from worktrack.ui.widgets import muted, page_title

log = logging.getLogger(__name__)

# (label, available, phase)
SECTIONS = [
    ("Timer", True, None),
    ("Dashboard", False, 2),
    ("Projects", True, None),
    ("History", True, None),
    ("Reports", False, 2),
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
    def __init__(self, services: AppServices) -> None:
        super().__init__()
        self.services = services
        self.signals = AppSignals(self)
        self._icon_active: bool | None = None
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
        built = {"Timer": self.timer_view, "Projects": self.projects_view, "History": self.history_view}

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

        self.timer_view.elapsed_changed.connect(self._on_elapsed)
        self.timer_view.go_to_projects.connect(lambda: self.go_to(2))
        self.signals.session_state_changed.connect(self._on_session_state)
        self._on_session_state()

    def go_to(self, index: int) -> None:
        if SECTIONS[index][1]:
            self.nav.setCurrentRow(index)

    def _on_elapsed(self, text: str) -> None:
        self.setWindowTitle(f"▶ {text} — {APP_NAME}" if text else APP_NAME)
        if text:
            self.sidebar_status.setText(f"● En curso\n{text}")

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

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if self.timer_view.is_running():
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
                if self.timer_view.is_running():  # stop failed (error already shown)
                    event.ignore()
                    return
            elif clicked is keep_btn:
                try:
                    self.services.timer.heartbeat()  # last-seen = moment of exit
                except Exception:
                    log.exception("Final heartbeat failed")
                log.info("Exiting with an active session left open")
            else:
                event.ignore()
                return
        event.accept()
