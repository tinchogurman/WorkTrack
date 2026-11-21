"""Add or edit a finished session. Shows the resulting duration live, before saving."""

from __future__ import annotations

from datetime import timedelta

from PySide6.QtWidgets import (
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from worktrack.core.models import EntryView
from worktrack.core.timeutils import format_decimal_hours, format_hms
from worktrack.services.context import AppServices
from worktrack.services.entry_service import LONG_SESSION_SECONDS, EntryDraft
from worktrack.ui.errors import user_message
from worktrack.ui.widgets import ProjectCombo, TaskCombo, qdatetime_to_utc, utc_to_qdatetime

DT_FORMAT = "dd/MM/yyyy HH:mm:ss"


def _datetime_edit() -> QDateTimeEdit:
    edit = QDateTimeEdit()
    edit.setDisplayFormat(DT_FORMAT)
    edit.setCalendarPopup(True)
    return edit


class EntryDialog(QDialog):
    def __init__(self, services: AppServices, view: EntryView | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services
        self.view = view
        self.entry_id = view.entry.id if view else None
        self.setWindowTitle("Editar sesión" if view else "Agregar sesión manual")
        self.setMinimumWidth(480)
        self.saved = None

        self.project_combo = ProjectCombo()
        self.task_combo = TaskCombo()
        self.start_edit = _datetime_edit()
        self.end_edit = _datetime_edit()
        self.description_edit = QLineEdit()
        self.description_edit.setMaxLength(1000)
        self.description_edit.setPlaceholderText("Notas opcionales")

        projects = services.projects.list_projects()
        if view and view.project_archived:
            # keep the entry's own (archived) project selectable
            projects = [services.projects.get_project(view.entry.project_id), *projects]
        self.project_combo.set_projects(projects, view.entry.project_id if view else None)
        self._load_tasks()

        if view:
            self.task_combo.setEditText(view.task_name)
            self.start_edit.setDateTime(utc_to_qdatetime(view.entry.start_time))
            self.end_edit.setDateTime(utc_to_qdatetime(view.entry.end_time))
            self.description_edit.setText(view.entry.description or "")
        else:
            now = services.clock.now()
            self.end_edit.setDateTime(utc_to_qdatetime(now))
            self.start_edit.setDateTime(utc_to_qdatetime(now - timedelta(hours=1)))

        form = QFormLayout()
        form.addRow("Proyecto", self.project_combo)
        form.addRow("Tarea", self.task_combo)
        form.addRow("Inicio", self.start_edit)
        form.addRow("Fin", self.end_edit)
        form.addRow("Descripción", self.description_edit)

        self.duration_label = QLabel()
        self.duration_label.setWordWrap(True)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.save_button = self.buttons.button(QDialogButtonBox.Save)
        self.save_button.setText("Guardar")
        self.save_button.setProperty("variant", "primary")
        self.buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        self.buttons.accepted.connect(self._save)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.duration_label)
        layout.addWidget(self.buttons)

        self.project_combo.currentIndexChanged.connect(self._on_project_changed)
        self.task_combo.editTextChanged.connect(self._validate)
        self.start_edit.dateTimeChanged.connect(self._validate)
        self.end_edit.dateTimeChanged.connect(self._validate)
        self.description_edit.textChanged.connect(self._validate)
        self._validate()

    def _load_tasks(self) -> None:
        pid = self.project_combo.current_project_id()
        tasks = self.services.projects.list_tasks(pid) if pid is not None else []
        self.task_combo.set_tasks(tasks)

    def _on_project_changed(self) -> None:
        self._load_tasks()
        self.task_combo.setEditText("")
        self._validate()

    def draft(self) -> EntryDraft | None:
        pid = self.project_combo.current_project_id()
        if pid is None:
            return None
        return EntryDraft(
            project_id=pid,
            task_name=self.task_combo.task_name(),
            start=qdatetime_to_utc(self.start_edit.dateTime()),
            end=qdatetime_to_utc(self.end_edit.dateTime()),
            description=self.description_edit.text(),
        )

    def _validate(self) -> int | None:
        draft = self.draft()
        if draft is None:
            return self._show_error("Elegí un proyecto (o creá uno en Projects).")
        try:
            seconds = self.services.entries.validate(draft, self.entry_id)
        except Exception as exc:  # noqa: BLE001
            return self._show_error(user_message(exc))
        self.duration_label.setObjectName("OkLabel")
        self.duration_label.setText(
            f"Duración resultante: {format_hms(seconds)}  ({format_decimal_hours(seconds)} h)"
        )
        self._repolish_label()
        self.save_button.setEnabled(True)
        return seconds

    def _show_error(self, message: str) -> None:
        self.duration_label.setObjectName("ErrorLabel")
        self.duration_label.setText(message)
        self._repolish_label()
        self.save_button.setEnabled(False)
        return None

    def _repolish_label(self) -> None:
        self.duration_label.style().unpolish(self.duration_label)
        self.duration_label.style().polish(self.duration_label)

    def _save(self) -> None:
        seconds = self._validate()
        if seconds is None:
            return
        if seconds > LONG_SESSION_SECONDS:
            answer = QMessageBox.question(
                self,
                "Sesión larga",
                f"La sesión dura {format_hms(seconds)}. ¿Es correcto?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        draft = self.draft()
        try:
            if self.entry_id is None:
                self.saved = self.services.entries.add_manual(draft)
            else:
                self.saved = self.services.entries.update_entry(self.entry_id, draft)
        except Exception as exc:  # noqa: BLE001
            self._show_error(user_message(exc))
            return
        self.accept()
