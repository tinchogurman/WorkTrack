"""Reusable filter widgets: period picker and project/task filter."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from PySide6.QtCore import QDate, Signal
from PySide6.QtWidgets import QComboBox, QDateEdit, QHBoxLayout, QLabel, QWidget

from worktrack.analytics.periods import Period
from worktrack.services.context import AppServices
from worktrack.ui.icons import color_dot

# preset key -> (label, builder(today) -> Period | None)
PRESETS: dict[str, tuple[str, Callable[[date], Period | None]]] = {
    "all": ("Todo", lambda today: None),
    "today": ("Hoy", Period.day),
    "week": ("Esta semana", Period.week),
    "month": ("Este mes", Period.month),
    "last30": ("Últimos 30 días", lambda today: Period.last_days(today, 30)),
    "year": ("Este año", Period.year),
    "custom": ("Personalizado", lambda today: None),
}


def _qdate(d: date) -> QDate:
    return QDate(d.year, d.month, d.day)


def _pydate(q: QDate) -> date:
    return date(q.year(), q.month(), q.day())


class PeriodPicker(QWidget):
    """Preset combo + from/to dates (editable only with "Personalizado")."""

    changed = Signal()

    def __init__(self, today: Callable[[], date], presets: list[str], default: str, parent=None) -> None:
        super().__init__(parent)
        self._today = today
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.preset = QComboBox()
        for key in presets:
            self.preset.addItem(PRESETS[key][0], key)
        longest = max(self.preset.fontMetrics().horizontalAdvance(PRESETS[k][0]) for k in presets)
        self.preset.setMinimumWidth(longest + 48)  # text + stylesheet padding + arrow
        self.from_edit = QDateEdit()
        self.to_edit = QDateEdit()
        for edit in (self.from_edit, self.to_edit):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("dd/MM/yyyy")
        layout.addWidget(self.preset)
        layout.addWidget(QLabel("Desde"))
        layout.addWidget(self.from_edit)
        layout.addWidget(QLabel("Hasta"))
        layout.addWidget(self.to_edit)

        self.preset.setCurrentIndex(max(0, self.preset.findData(default)))
        self._apply_preset()
        self.preset.currentIndexChanged.connect(self._on_preset)
        self.from_edit.dateChanged.connect(self._on_date)
        self.to_edit.dateChanged.connect(self._on_date)

    def preset_key(self) -> str:
        return self.preset.currentData()

    def set_preset(self, key: str) -> None:
        self.preset.setCurrentIndex(self.preset.findData(key))

    def _apply_preset(self) -> None:
        key = self.preset_key()
        custom = key == "custom"
        self.from_edit.setEnabled(custom)
        self.to_edit.setEnabled(custom)
        period = PRESETS[key][1](self._today())
        if period is not None:
            for edit, value in ((self.from_edit, period.start), (self.to_edit, period.end)):
                edit.blockSignals(True)
                edit.setDate(_qdate(value))
                edit.blockSignals(False)
        elif key == "all":
            self.from_edit.setEnabled(False)
            self.to_edit.setEnabled(False)

    def _on_preset(self) -> None:
        self._apply_preset()
        self.changed.emit()

    def _on_date(self) -> None:
        if self.preset_key() == "custom":
            self.changed.emit()

    def refresh_relative(self) -> None:
        """Recompute relative presets (e.g. after midnight)."""
        if self.preset_key() not in ("custom", "all"):
            self._apply_preset()

    def period(self) -> Period | None:
        """None means "Todo". Raises ValueError if 'Hasta' is before 'Desde'."""
        key = self.preset_key()
        if key == "all":
            return None
        if key == "custom":
            return Period.custom(_pydate(self.from_edit.date()), _pydate(self.to_edit.date()))
        return PRESETS[key][1](self._today())


class ProjectTaskFilter(QWidget):
    """'Todos' or one project (archived included), then 'Todas' or one of its tasks."""

    changed = Signal()

    def __init__(self, services: AppServices, parent=None) -> None:
        super().__init__(parent)
        self.services = services
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.project_combo = QComboBox()
        self.project_combo.setMinimumWidth(180)
        self.task_combo = QComboBox()
        self.task_combo.setMinimumWidth(160)
        layout.addWidget(QLabel("Proyecto"))
        layout.addWidget(self.project_combo)
        layout.addWidget(QLabel("Tarea"))
        layout.addWidget(self.task_combo)
        self.reload()
        self.project_combo.currentIndexChanged.connect(self._on_project)
        self.task_combo.currentIndexChanged.connect(self.changed)

    def reload(self) -> None:
        """Refresh options keeping the current selection when it still exists."""
        current_project, current_task = self.project_id(), self.task_id()
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        self.project_combo.addItem("Todos", None)
        for p in self.services.projects.list_projects(include_archived=True):
            self.project_combo.addItem(color_dot(p.color), p.name + ("  (archivado)" if p.archived else ""), p.id)
        index = self.project_combo.findData(current_project)
        self.project_combo.setCurrentIndex(index if index >= 0 else 0)
        self.project_combo.blockSignals(False)
        self._load_tasks(current_task)

    def _load_tasks(self, select: int | None = None) -> None:
        self.task_combo.blockSignals(True)
        self.task_combo.clear()
        self.task_combo.addItem("Todas", None)
        pid = self.project_id()
        if pid is not None:
            for t in self.services.projects.list_tasks(pid, include_archived=True):
                self.task_combo.addItem(t.name + ("  (archivada)" if t.archived else ""), t.id)
        index = self.task_combo.findData(select)
        self.task_combo.setCurrentIndex(index if index >= 0 else 0)
        self.task_combo.setEnabled(pid is not None)
        self.task_combo.blockSignals(False)

    def _on_project(self) -> None:
        self._load_tasks()
        self.changed.emit()

    def project_id(self) -> int | None:
        return self.project_combo.currentData() if self.project_combo.count() else None

    def task_id(self) -> int | None:
        return self.task_combo.currentData() if self.task_combo.count() else None

    def project_label(self) -> str:
        return self.project_combo.currentText().replace("  (archivado)", "")

    def clear(self) -> None:
        self.project_combo.setCurrentIndex(0)
