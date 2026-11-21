"""Decide what to do with a detected interruption: keep, discount, or adjust."""

from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QButtonGroup,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from worktrack.core.models import Interruption
from worktrack.core.timeutils import format_hms, format_local_datetime, seconds_between
from worktrack.services.context import AppServices
from worktrack.ui.errors import user_message
from worktrack.ui.widgets import qdatetime_to_utc, qt_datetime_format, section_title, utc_to_qdatetime

log = logging.getLogger(__name__)

SOURCES = {
    "power_event": "suspensión/reanudación informada por Windows",
    "heartbeat_gap": "la aplicación dejó de recibir actividad (equipo suspendido o congelado)",
}


def _dt_edit(value) -> QDateTimeEdit:
    edit = QDateTimeEdit(utc_to_qdatetime(value))
    edit.setDisplayFormat(qt_datetime_format())
    edit.setCalendarPopup(True)
    return edit


class InterruptionDialog(QDialog):
    """Closing the dialog without applying keeps the time (nothing is discounted)."""

    def __init__(
        self,
        services: AppServices,
        interruption: Interruption,
        *,
        preselect: str = "keep",
        intro: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.services = services
        self.item = interruption
        self.choice: str | None = None
        self.setWindowTitle("WorkTrack: posible interrupción")
        self.setMinimumWidth(560)

        i = interruption
        layout = QVBoxLayout(self)
        layout.addWidget(section_title("Posible interrupción durante la sesión"))
        if intro:
            intro_label = QLabel(intro)
            intro_label.setWordWrap(True)
            layout.addWidget(intro_label)
        text = QLabel(
            f"Entre <b>{format_local_datetime(i.start_time)}</b> y <b>{format_local_datetime(i.end_time)}</b> "
            f"(<b>{format_hms(i.seconds)}</b>) {SOURCES.get(i.source, '')}.<br>"
            "Ese tiempo <b>se sigue contando</b> en la sesión hasta que decidas descontarlo."
        )
        text.setWordWrap(True)
        layout.addWidget(text)

        self.opt_keep = QRadioButton("Conservar el tiempo (no descontar nada)")
        self.opt_discount = QRadioButton(f"Descontar el intervalo detectado ({format_hms(i.seconds)})")
        self.opt_adjust = QRadioButton("Descontar otro tramo:")
        group = QButtonGroup(self)
        for n, opt in enumerate((self.opt_keep, self.opt_discount, self.opt_adjust)):
            group.addButton(opt, n)
        self.from_edit = _dt_edit(i.start_time)
        self.to_edit = _dt_edit(i.end_time)
        adjust_row = QHBoxLayout()
        adjust_row.addWidget(self.opt_adjust)
        adjust_row.addWidget(self.from_edit)
        adjust_row.addWidget(QLabel("a"))
        adjust_row.addWidget(self.to_edit)
        adjust_row.addStretch()
        layout.addWidget(self.opt_keep)
        layout.addWidget(self.opt_discount)
        layout.addLayout(adjust_row)

        self.preview = QLabel()
        layout.addWidget(self.preview)
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

        {"keep": self.opt_keep, "discount": self.opt_discount, "adjust": self.opt_adjust}.get(
            preselect, self.opt_keep
        ).setChecked(True)
        group.idToggled.connect(self._update_preview)
        for edit in (self.from_edit, self.to_edit):
            edit.dateTimeChanged.connect(self._on_range_edited)
        self._update_preview()

    def _on_range_edited(self, *_args) -> None:
        self.opt_adjust.setChecked(True)
        self._update_preview()

    def _update_preview(self, *_args) -> None:
        if self.opt_keep.isChecked():
            self.preview.setText("No se descuenta nada.")
        elif self.opt_discount.isChecked():
            self.preview.setText(f"Se descontarán {format_hms(self.item.seconds)}.")
        else:
            seconds = seconds_between(
                qdatetime_to_utc(self.from_edit.dateTime()), qdatetime_to_utc(self.to_edit.dateTime())
            )
            self.preview.setText(f"Se descontarán {format_hms(seconds)}." if seconds > 0 else "")

    def _apply(self) -> None:
        service = self.services.interruptions
        try:
            if self.opt_keep.isChecked():
                service.keep(self.item.id)
                self.choice = "kept"
            elif self.opt_discount.isChecked():
                service.discount(self.item.id)
                self.choice = "discounted"
            else:
                service.adjust(
                    self.item.id,
                    qdatetime_to_utc(self.from_edit.dateTime()),
                    qdatetime_to_utc(self.to_edit.dateTime()),
                )
                self.choice = "adjusted"
        except Exception as exc:  # noqa: BLE001
            self.error.setText(user_message(exc))
            return
        self.accept()

    def reject(self) -> None:
        """Window closed without choosing: keep the time (never discount silently)."""
        try:
            self.services.interruptions.keep(self.item.id)
            self.choice = "kept"
        except Exception:  # noqa: BLE001
            log.exception("Could not mark interruption as kept")
        super().reject()


def resolve_pending(services: AppServices, entry_id: int, intro: str, parent: QWidget | None = None) -> None:
    """Ask about every pending interruption of an entry (used before Stop / after recovery)."""
    for item in services.interruptions.pending_for_entry(entry_id):
        InterruptionDialog(services, item, intro=intro, parent=parent).exec()
