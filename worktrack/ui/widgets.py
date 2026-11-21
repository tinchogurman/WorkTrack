"""Reusable widgets: project picker, task picker, cards, datetime helpers."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QDate, QDateTime, Qt, QTime
from PySide6.QtWidgets import QComboBox, QCompleter, QFrame, QLabel

from worktrack.core.models import Project, Task
from worktrack.core.timeutils import local_naive_to_utc, to_local
from worktrack.ui.icons import color_dot


class Card(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")


def page_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("PageTitle")
    return label


def section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("SectionTitle")
    return label


def muted(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setObjectName("Muted")
    return label


class ProjectCombo(QComboBox):
    """Projects with a color dot; item data is the project id."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(200)

    def set_projects(self, projects: list[Project], select_id: int | None = None) -> None:
        current = select_id if select_id is not None else self.current_project_id()
        self.blockSignals(True)
        self.clear()
        for project in projects:
            label = project.name + ("  (archivado)" if project.archived else "")
            self.addItem(color_dot(project.color), label, project.id)
        index = self.findData(current) if current is not None else -1
        self.setCurrentIndex(index if index >= 0 else (0 if self.count() else -1))
        self.blockSignals(False)

    def current_project_id(self) -> int | None:
        data = self.currentData()
        return int(data) if data is not None else None


class TaskCombo(QComboBox):
    """Editable: choose an existing task or type a new one."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.setMinimumWidth(240)
        self.lineEdit().setPlaceholderText("Tarea: elegí o escribí una nueva")
        self.lineEdit().setClearButtonEnabled(True)

    def set_tasks(self, tasks: list[Task], keep_text: bool = True) -> None:
        text = self.currentText()
        self.blockSignals(True)
        self.clear()
        for task in tasks:
            self.addItem(task.name, task.id)
        completer = QCompleter([t.name for t in tasks], self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self.setCompleter(completer)
        self.setCurrentIndex(-1)
        self.setEditText(text if keep_text else "")
        self.blockSignals(False)

    def task_name(self) -> str:
        return self.currentText().strip()


def utc_to_qdatetime(value: datetime) -> QDateTime:
    local = to_local(value)
    return QDateTime(QDate(local.year, local.month, local.day), QTime(local.hour, local.minute, local.second))


def qdatetime_to_utc(value: QDateTime) -> datetime:
    d, t = value.date(), value.time()
    naive = datetime(d.year(), d.month(), d.day(), t.hour(), t.minute(), t.second())
    return local_naive_to_utc(naive)
