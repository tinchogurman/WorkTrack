"""Timer: pick project + task, Play/Stop, live HH:MM:SS, today's sessions.

The display is recomputed from the stored start timestamp on every tick
(now - start), so it is correct after being minimized, hidden or asleep.
"""

from __future__ import annotations

import logging
from datetime import timezone

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from worktrack.core.models import EntryView
from worktrack.core.timeutils import format_hms, format_local_time, to_local
from worktrack.services.context import AppServices
from worktrack.services.timer_service import HEARTBEAT_INTERVAL_SECONDS
from worktrack.ui import theme
from worktrack.ui.errors import show_error
from worktrack.ui.icons import color_dot
from worktrack.ui.signals import AppSignals
from worktrack.ui.widgets import Card, ProjectCombo, TaskCombo, muted, page_title, section_title

log = logging.getLogger(__name__)

TODAY_COLUMNS = ["Proyecto", "Tarea", "Inicio", "Fin", "Duración", "Descripción"]


class TimerView(QWidget):
    elapsed_changed = Signal(str)  # "" when idle; used for the window title
    go_to_projects = Signal()

    def __init__(self, services: AppServices, signals: AppSignals, parent=None) -> None:
        super().__init__(parent)
        self.services = services
        self.signals = signals
        self._active: EntryView | None = None
        self._today_completed_seconds = 0
        self._today_date = None

        self._build()

        self._tick = QTimer(self)
        self._tick.setInterval(250)
        self._tick.timeout.connect(self._update_display)
        self._heartbeat = QTimer(self)
        self._heartbeat.setInterval(HEARTBEAT_INTERVAL_SECONDS * 1000)
        self._heartbeat.timeout.connect(self._beat)
        self._day_watch = QTimer(self)
        self._day_watch.setInterval(60_000)
        self._day_watch.timeout.connect(self._check_day_change)
        self._day_watch.start()

        signals.projects_changed.connect(self.refresh_projects)
        signals.entries_changed.connect(self.refresh_today)

        self.refresh_projects()
        self.load_state()

    # --- layout ------------------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(18)
        root.addWidget(page_title("Timer"))

        card = Card()
        grid = QGridLayout(card)
        grid.setContentsMargins(18, 16, 18, 16)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        self.project_combo = ProjectCombo()
        self.project_combo.setToolTip("Proyecto de la sesión")
        self.project_combo.currentIndexChanged.connect(self._on_project_changed)
        self.task_combo = TaskCombo()
        self.task_combo.lineEdit().returnPressed.connect(self._start_from_keyboard)
        self.description_edit = QLineEdit()
        self.description_edit.setPlaceholderText("Descripción (opcional)")
        self.description_edit.setMaxLength(1000)
        self.description_edit.returnPressed.connect(self._start_from_keyboard)
        self.description_edit.editingFinished.connect(self._save_active_description)
        grid.addWidget(muted("Proyecto"), 0, 0)
        grid.addWidget(muted("Tarea"), 0, 1)
        grid.addWidget(self.project_combo, 1, 0)
        grid.addWidget(self.task_combo, 1, 1)
        grid.addWidget(muted("Descripción"), 2, 0, 1, 2)
        grid.addWidget(self.description_edit, 3, 0, 1, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 2)
        self.no_projects_hint = QPushButton("No hay proyectos activos: crear uno en Projects →")
        self.no_projects_hint.clicked.connect(self.go_to_projects)
        grid.addWidget(self.no_projects_hint, 4, 0, 1, 2)
        root.addWidget(card)

        center = QVBoxLayout()
        center.setSpacing(6)
        self.display = QLabel("00:00:00")
        self.display.setObjectName("TimerDisplay")
        self.display.setAlignment(Qt.AlignCenter)
        status_row = QHBoxLayout()
        status_row.addStretch()
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet(f"color: {theme.MUTED}; background: transparent; font-size: 12pt;")
        self.status_line = QLabel("Detenido")
        self.status_line.setObjectName("StatusLine")
        status_row.addWidget(self.status_dot)
        status_row.addWidget(self.status_line)
        status_row.addStretch()

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.play_button = QPushButton("▶  Play")
        self.play_button.setObjectName("PlayButton")
        self.play_button.setToolTip("Iniciar sesión (Ctrl+Espacio)")
        self.play_button.clicked.connect(self.start)
        self.stop_button = QPushButton("■  Stop")
        self.stop_button.setObjectName("StopButton")
        self.stop_button.setToolTip("Detener y guardar (Ctrl+Espacio)")
        self.stop_button.clicked.connect(self.stop)
        buttons.addWidget(self.play_button)
        buttons.addSpacing(16)
        buttons.addWidget(self.stop_button)
        buttons.addStretch()

        center.addWidget(self.display)
        center.addLayout(status_row)
        center.addSpacing(10)
        center.addLayout(buttons)
        root.addLayout(center)

        header = QHBoxLayout()
        header.addWidget(section_title("Sesiones iniciadas hoy"))
        header.addStretch()
        self.today_total = muted("Total: 00:00:00")
        header.addWidget(self.today_total)
        root.addLayout(header)

        self.today_table = QTableWidget(0, len(TODAY_COLUMNS))
        self.today_table.setHorizontalHeaderLabels(TODAY_COLUMNS)
        self.today_table.verticalHeader().setVisible(False)
        self.today_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.today_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.today_table.setAlternatingRowColors(True)
        self.today_table.setShowGrid(False)
        hh = self.today_table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(len(TODAY_COLUMNS) - 1, QHeaderView.Stretch)
        root.addWidget(self.today_table, 1)

    # --- data --------------------------------------------------------------
    def refresh_projects(self) -> None:
        try:
            projects = self.services.projects.list_projects()
        except Exception as exc:  # noqa: BLE001
            show_error(self, exc)
            return
        select = self._active.entry.project_id if self._active else None
        text = self.task_combo.currentText()
        self.project_combo.set_projects(projects, select)
        self.no_projects_hint.setVisible(not projects and self._active is None)
        self._load_tasks()
        if self._active:
            self.task_combo.setEditText(self._active.task_name)
        else:
            self.task_combo.setEditText(text)

    def _on_project_changed(self) -> None:
        self._load_tasks()
        self.task_combo.setEditText("")

    def _load_tasks(self) -> None:
        pid = self.project_combo.current_project_id()
        tasks = self.services.projects.list_tasks(pid) if pid is not None else []
        self.task_combo.set_tasks(tasks)

    def load_state(self) -> None:
        """Re-read the active session from the database and update the UI."""
        self._active = self.services.timer.get_active_view()
        running = self._active is not None
        if running:
            self.project_combo.set_projects(
                self.services.projects.list_projects(), self._active.entry.project_id
            )
            if self.project_combo.current_project_id() != self._active.entry.project_id:
                # project not in the active list (should not happen): show it anyway
                project = self.services.projects.get_project(self._active.entry.project_id)
                self.project_combo.set_projects([project], project.id)
            self._load_tasks()
            self.task_combo.setEditText(self._active.task_name)
            self.description_edit.setText(self._active.entry.description or "")
            self._tick.start()
            self._heartbeat.start()
        else:
            self._tick.stop()
            self._heartbeat.stop()
        self.project_combo.setEnabled(not running)
        self.task_combo.setEnabled(not running)
        self.play_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.no_projects_hint.setVisible(self.project_combo.count() == 0 and not running)
        self.display.setProperty("running", running)
        theme.repolish(self.display)
        self.refresh_today()
        self._update_display()

    def refresh_today(self) -> None:
        now_local = to_local(self.services.clock.now())
        self._today_date = now_local.date()
        midnight = now_local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
        try:
            views = self.services.entries.list_entries(start_from=midnight)
        except Exception as exc:  # noqa: BLE001
            show_error(self, exc)
            return
        self.today_table.setRowCount(len(views))
        self._today_completed_seconds = 0
        for row, view in enumerate(views):
            e = view.entry
            if e.duration_seconds is not None:
                self._today_completed_seconds += e.duration_seconds
            project_item = QTableWidgetItem(color_dot(view.project_color), view.project_name)
            values = [
                project_item,
                QTableWidgetItem(view.task_name),
                QTableWidgetItem(format_local_time(e.start_time)),
                QTableWidgetItem(format_local_time(e.end_time) if e.end_time else "En curso"),
                QTableWidgetItem(format_hms(e.duration_seconds) if e.duration_seconds is not None else "—"),
                QTableWidgetItem(e.description or ""),
            ]
            for col, item in enumerate(values):
                self.today_table.setItem(row, col, item)
        self._update_total()

    def _update_total(self) -> None:
        total = self._today_completed_seconds
        if self._active and self._active.entry.start_time.astimezone().date() == self._today_date:
            total += self.services.timer.elapsed_seconds(self._active.entry)
        self.today_total.setText(f"Total: {format_hms(total)}")

    def _check_day_change(self) -> None:
        if to_local(self.services.clock.now()).date() != self._today_date:
            self.refresh_today()

    # --- actions -----------------------------------------------------------
    def is_running(self) -> bool:
        return self._active is not None

    def toggle(self) -> None:
        if self._active:
            self.stop()
        else:
            self.start()

    def _start_from_keyboard(self) -> None:
        if not self._active:
            self.start()

    def start(self) -> None:
        if self._active:
            return
        project_id = self.project_combo.current_project_id()
        if project_id is None:
            QMessageBox.information(self, "WorkTrack", "Elegí un proyecto (o creá uno en Projects).")
            return
        if not self.task_combo.task_name():
            QMessageBox.information(self, "WorkTrack", "Escribí o elegí una tarea antes de iniciar.")
            self.task_combo.setFocus()
            return
        try:
            self.services.timer.start(
                project_id, self.task_combo.task_name(), self.description_edit.text()
            )
        except Exception as exc:  # noqa: BLE001
            show_error(self, exc)
            self.load_state()  # e.g. a session is already active: show it
            return
        self.load_state()
        self.stop_button.setFocus()
        self.signals.projects_changed.emit()  # the task may have been created
        self.signals.entries_changed.emit()
        self.signals.session_state_changed.emit()

    def stop(self) -> None:
        if not self._active:
            return
        try:
            self._save_active_description()
            self.services.timer.stop()
        except Exception as exc:  # noqa: BLE001
            show_error(self, exc)
            self.load_state()
            return
        self.description_edit.clear()
        self.load_state()
        self.play_button.setFocus()
        self.signals.entries_changed.emit()
        self.signals.session_state_changed.emit()

    def _save_active_description(self) -> None:
        if not self._active:
            return
        text = self.description_edit.text().strip() or None
        if text == self._active.entry.description:
            return
        try:
            self.services.timer.update_active_description(text)
            self._active = self.services.timer.get_active_view()
        except Exception as exc:  # noqa: BLE001
            show_error(self, exc)

    def _beat(self) -> None:
        try:
            self.services.timer.heartbeat()
        except Exception:  # never interrupt the user for a missed heartbeat
            log.exception("Heartbeat failed")

    def _update_display(self) -> None:
        if not self._active:
            self.display.setText("00:00:00")
            self.status_dot.setStyleSheet(f"color: {theme.MUTED}; background: transparent; font-size: 12pt;")
            self.status_line.setText("Detenido")
            self.elapsed_changed.emit("")
            return
        seconds = self.services.timer.elapsed_seconds(self._active.entry)
        text = format_hms(seconds)
        self.display.setText(text)
        dot_color = theme.GREEN if seconds % 2 == 0 else "#1C6B3A"
        self.status_dot.setStyleSheet(f"color: {dot_color}; background: transparent; font-size: 12pt;")
        self.status_line.setText(
            f"En curso desde las {format_local_time(self._active.entry.start_time)}  ·  "
            f"{self._active.project_name} / {self._active.task_name}"
        )
        self._update_total()
        self.elapsed_changed.emit(f"{text} · {self._active.task_name}")
