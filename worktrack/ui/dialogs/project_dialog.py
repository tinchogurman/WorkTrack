"""Create/edit a project (name + color)."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from worktrack.services.project_service import PALETTE
from worktrack.ui.errors import user_message


class ProjectDialog(QDialog):
    """`on_save(name, color)` performs the change; errors keep the dialog open."""

    def __init__(
        self,
        on_save: Callable[[str, str], object],
        *,
        name: str = "",
        color: str = PALETTE[0],
        title: str = "Nuevo proyecto",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)
        self._on_save = on_save
        self._color = color

        self.name_edit = QLineEdit(name)
        self.name_edit.setMaxLength(100)
        self.name_edit.setPlaceholderText("Ej.: Data Engineering")

        swatches = QHBoxLayout()
        swatches.setSpacing(6)
        for c in PALETTE:
            btn = QPushButton()
            btn.setFixedSize(26, 26)
            btn.setToolTip(c)
            btn.setStyleSheet(f"background: {c}; border-radius: 13px; border: 1px solid #00000040;")
            btn.clicked.connect(lambda _=False, c=c: self._set_color(c))
            swatches.addWidget(btn)
        other = QPushButton("Otro…")
        other.clicked.connect(self._pick_color)
        swatches.addWidget(other)
        swatches.addStretch()

        self.preview = QLabel()
        self.preview.setFixedSize(60, 22)

        form = QFormLayout()
        form.addRow("Nombre", self.name_edit)
        form.addRow("Color", swatches)
        form.addRow("Seleccionado", self.preview)

        self.error = QLabel()
        self.error.setObjectName("ErrorLabel")
        self.error.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Guardar")
        buttons.button(QDialogButtonBox.Save).setProperty("variant", "primary")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.error)
        layout.addWidget(buttons)
        self._set_color(color)

    def _set_color(self, color: str) -> None:
        self._color = color.upper()
        self.preview.setStyleSheet(f"background: {self._color}; border-radius: 4px;")
        self.preview.setToolTip(self._color)

    def _pick_color(self) -> None:
        chosen = QColorDialog.getColor(QColor(self._color), self, "Color del proyecto")
        if chosen.isValid():
            self._set_color(chosen.name())

    def _save(self) -> None:
        try:
            self._on_save(self.name_edit.text(), self._color)
        except Exception as exc:  # noqa: BLE001
            self.error.setText(user_message(exc))
            return
        self.accept()
