"""System tray icon: shows whether a session is running; open / stop / quit."""

from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from worktrack import APP_NAME
from worktrack.ui.icons import app_icon


class TrayIcon(QSystemTrayIcon):
    def __init__(self, window) -> None:
        super().__init__(app_icon(active=False), window)
        self.window = window
        self._running: bool | None = None
        menu = QMenu()
        self.open_action = QAction("Abrir WorkTrack", menu)
        self.open_action.triggered.connect(window.show_from_tray)
        self.stop_action = QAction("Detener sesión", menu)
        self.stop_action.triggered.connect(window.stop_from_tray)
        self.quit_action = QAction("Salir", menu)
        self.quit_action.triggered.connect(window.quit_from_tray)
        menu.addAction(self.open_action)
        menu.addAction(self.stop_action)
        menu.addSeparator()
        menu.addAction(self.quit_action)
        self.setContextMenu(menu)
        self._menu = menu  # keep a reference
        self.activated.connect(self._on_activated)
        self.set_state(False, "")

    def _on_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.window.show_from_tray()

    def set_state(self, running: bool, detail: str) -> None:
        if running != self._running:
            self.setIcon(app_icon(active=running))
            self._running = running
        self.stop_action.setEnabled(running)
        self.stop_action.setText(f"Detener sesión ({detail.split(' · ')[-1]})" if running and detail else "Detener sesión")
        tooltip = f"{APP_NAME} — ▶ {detail}" if running else f"{APP_NAME} — sin sesión activa"
        self.setToolTip(tooltip[:120])  # Windows limits tray tooltips to 127 characters
