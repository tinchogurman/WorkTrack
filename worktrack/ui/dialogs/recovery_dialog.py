"""Shown at startup when a session was left open (crash, power loss, kill)."""

from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QButtonGroup,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from worktrack.core.timeutils import format_hms, format_local_datetime, seconds_between
from worktrack.services.recovery_service import RecoveryInfo, RecoveryService
from worktrack.ui.errors import user_message
from worktrack.ui.widgets import qdatetime_to_utc, qt_datetime_format, section_title, utc_to_qdatetime

log = logging.getLogger(__name__)


class RecoveryDialog(QDialog):
    def __init__(self, recovery: RecoveryService, info: RecoveryInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.recovery = recovery
        self.info = info
        self.choice: str | None = None
        self.setWindowTitle("WorkTrack: sesión sin finalizar")
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        layout.addWidget(section_title("WorkTrack se cerró con una sesión en curso"))
        intro = QLabel(
            "La aplicación no se cerró normalmente mientras el cronómetro estaba activo. "
            "Elegí qué hacer con la sesión: el tiempo en que la aplicación no estuvo "
            "funcionando no se cuenta automáticamente."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        view = info.view
        form.addRow("Proyecto / tarea:", QLabel(f"{view.project_name} / {view.task_name}"))
        if view.entry.description:
            form.addRow("Descripción:", QLabel(view.entry.description))
        form.addRow("Activa desde:", QLabel(format_local_datetime(info.started_at)))
        form.addRow(
            "Última vez funcionando:",
            QLabel(f"{format_local_datetime(info.last_seen)}  (a {format_hms(info.seconds_to_last_seen)} del inicio)"),
        )
        form.addRow(
            "Ahora:",
            QLabel(f"{format_local_datetime(info.now)}  (sin la app: {format_hms(info.unseen_seconds)})"),
        )
        layout.addLayout(form)

        self.group = QButtonGroup(self)
        self.opt_last = QRadioButton(
            f"Finalizar en el último momento conocido  →  duración {format_hms(info.seconds_to_last_seen)}"
        )
        self.opt_custom = QRadioButton("Finalizar a una hora indicada:")
        self.opt_continue = QRadioButton(
            f"Continuar la sesión (cuenta todo hasta ahora: {format_hms(info.seconds_to_now)})"
        )
        for i, opt in enumerate((self.opt_last, self.opt_custom, self.opt_continue)):
            self.group.addButton(opt, i)

        self.custom_edit = QDateTimeEdit(utc_to_qdatetime(info.last_seen))
        self.custom_edit.setDisplayFormat(qt_datetime_format())
        self.custom_edit.setCalendarPopup(True)
        self.custom_edit.setMinimumDateTime(utc_to_qdatetime(info.started_at))
        self.custom_edit.setMaximumDateTime(utc_to_qdatetime(info.now))
        self.custom_duration = QLabel()
        custom_row = QHBoxLayout()
        custom_row.addWidget(self.opt_custom)
        custom_row.addWidget(self.custom_edit)
        custom_row.addWidget(self.custom_duration)
        custom_row.addStretch()

        layout.addWidget(self.opt_last)
        layout.addLayout(custom_row)
        layout.addWidget(self.opt_continue)
        self.opt_last.setChecked(True)
        self._update_custom_duration()
        self.custom_edit.dateTimeChanged.connect(self._on_custom_changed)

        self.error = QLabel()
        self.error.setObjectName("ErrorLabel")
        self.error.setWordWrap(True)
        layout.addWidget(self.error)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        ok = buttons.button(QDialogButtonBox.Ok)
        ok.setText("Aplicar")
        ok.setProperty("variant", "primary")
        buttons.accepted.connect(self._apply)
        layout.addWidget(buttons)

    def _on_custom_changed(self, *_args) -> None:
        self.opt_custom.setChecked(True)  # editing the time implies choosing that option
        self._update_custom_duration()

    def _update_custom_duration(self) -> None:
        end = qdatetime_to_utc(self.custom_edit.dateTime())
        seconds = seconds_between(self.info.started_at, end)
        self.custom_duration.setText(f"→ duración {format_hms(seconds)}" if seconds >= 0 else "")

    def _apply(self) -> None:
        try:
            if self.opt_last.isChecked():
                self.recovery.finish_at_last_seen()
                self.choice = "finish_last_seen"
            elif self.opt_custom.isChecked():
                self.recovery.finish_at(qdatetime_to_utc(self.custom_edit.dateTime()))
                self.choice = "finish_custom"
            else:
                self.recovery.continue_session()
                self.choice = "continue"
        except Exception as exc:  # noqa: BLE001
            self.error.setText(user_message(exc))
            return
        self.accept()

    def reject(self) -> None:
        """Closing the window without choosing keeps the session open (non-destructive)."""
        log.info("Recovery dialog dismissed; session left active")
        self.choice = "dismissed"
        super().reject()
