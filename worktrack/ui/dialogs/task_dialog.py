"""Create/edit a task (name + optional description)."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from worktrack.ui.errors import user_message


class TaskDialog(QDialog):
    def __init__(
        self,
        on_save: Callable[[str, str], object],
        *,
        project_name: str,
        name: str = "",
        description: str = "",
        title: str = "Nueva tarea",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)
        self._on_save = on_save

        self.name_edit = QLineEdit(name)
        self.name_edit.setMaxLength(100)
        self.description_edit = QPlainTextEdit(description)
        self.description_edit.setFixedHeight(90)

        form = QFormLayout()
        form.addRow("Proyecto", QLabel(project_name))
        form.addRow("Nombre", self.name_edit)
        form.addRow("Descripción", self.description_edit)

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

    def _save(self) -> None:
        try:
            self._on_save(self.name_edit.text(), self.description_edit.toPlainText())
        except Exception as exc:  # noqa: BLE001
            self.error.setText(user_message(exc))
            return
        self.accept()
