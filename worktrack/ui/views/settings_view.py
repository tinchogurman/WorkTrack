"""Settings: preferences (saved immediately), backups and restore, data folders."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QStandardPaths, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from worktrack import APP_NAME, __version__
from worktrack.core.timeutils import set_time_format
from worktrack.paths import data_dir, logs_dir
from worktrack.services.context import AppServices
from worktrack.settings import Settings, SettingsStore
from worktrack.ui.dialogs.recovery_dialog import run_recovery
from worktrack.ui.errors import confirm, show_error, user_message
from worktrack.ui.signals import AppSignals
from worktrack.ui.widgets import Card, muted, page_title, section_title

log = logging.getLogger(__name__)


def documents_dir() -> Path:
    docs = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
    return Path(docs) if docs else Path.home()


def open_folder(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def wrapping(label: QLabel) -> QLabel:
    """Let long text (paths, notes) wrap instead of widening the page."""
    label.setWordWrap(True)
    label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
    label.setMinimumWidth(100)
    return label


def _size(n: int) -> str:
    return f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} MB"


class SettingsView(QWidget):
    settings_changed = Signal(object)  # Settings

    def __init__(
        self,
        services: AppServices,
        signals: AppSignals,
        settings: Settings,
        store: SettingsStore,
        tray_available: bool,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.services = services
        self.signals = signals
        self.settings = settings
        self.store = store
        self.tray_available = tray_available
        self._loading = False
        self._build()
        self._load()
        self.refresh_backups()

    # --- layout ------------------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        root = QVBoxLayout(content)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)
        root.addWidget(page_title("Settings"))

        # Preferences
        prefs = Card()
        pl = QVBoxLayout(prefs)
        pl.setContentsMargins(18, 14, 18, 14)
        head = QHBoxLayout()
        head.addWidget(section_title("Preferencias"))
        head.addStretch()
        self.saved_label = muted("")
        head.addWidget(self.saved_label)
        pl.addLayout(head)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        self.start_minimized = QCheckBox("Iniciar minimizado")
        self.minimize_to_tray = QCheckBox("Al minimizar, enviar a la bandeja del sistema")
        if not self.tray_available:
            self.minimize_to_tray.setEnabled(False)
            self.minimize_to_tray.setToolTip("La bandeja del sistema no está disponible")
        self.confirm_exit = QCheckBox("Preguntar antes de salir si hay una sesión en curso")
        self.confirm_exit.setToolTip(
            "Si está desactivado, al salir la sesión en curso se detiene y se guarda automáticamente."
        )
        self.time_format = QComboBox()
        self.time_format.addItem("24 horas (15:30:00)", "24h")
        self.time_format.addItem("12 horas (03:30:00 p. m.)", "12h")
        self.export_dir = QLineEdit()
        self.export_dir.setReadOnly(True)
        self.export_dir.setMinimumWidth(120)
        self.export_dir.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        choose = QPushButton("Elegir…")
        choose.clicked.connect(self._choose_export_dir)
        reset = QPushButton("Usar Documentos")
        reset.clicked.connect(self._reset_export_dir)
        export_row = QHBoxLayout()
        export_row.addWidget(self.export_dir, 1)
        export_row.addWidget(choose)
        export_row.addWidget(reset)
        form.addRow("", self.start_minimized)
        form.addRow("", self.minimize_to_tray)
        form.addRow("", self.confirm_exit)
        form.addRow("Formato horario", self.time_format)
        form.addRow("Carpeta de exportación", export_row)
        pl.addLayout(form)
        pl.addWidget(wrapping(muted(
            "El formato horario se aplica a la pantalla; los archivos exportados usan 24 horas."
        )))
        root.addWidget(prefs)
        for box in (self.start_minimized, self.minimize_to_tray, self.confirm_exit):
            box.toggled.connect(self._save)
        self.time_format.currentIndexChanged.connect(self._save)

        # Backups
        backups = Card()
        bl = QVBoxLayout(backups)
        bl.setContentsMargins(18, 14, 18, 14)
        bl.addWidget(section_title("Copias de seguridad"))
        self.backups_path = wrapping(muted(""))
        self.backups_path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bl.addWidget(self.backups_path)
        buttons = QHBoxLayout()
        self.backup_btn = QPushButton("Crear backup ahora")
        self.backup_btn.setProperty("variant", "primary")
        self.backup_btn.clicked.connect(self.create_backup)
        self.restore_selected_btn = QPushButton("Restaurar seleccionado…")
        self.restore_selected_btn.clicked.connect(self.restore_selected)
        self.restore_file_btn = QPushButton("Restaurar desde archivo…")
        self.restore_file_btn.clicked.connect(self.restore_from_file)
        open_backups = QPushButton("Abrir carpeta")
        open_backups.clicked.connect(lambda: open_folder(self.services.backups.backups_dir))
        for b in (self.backup_btn, self.restore_selected_btn, self.restore_file_btn, open_backups):
            buttons.addWidget(b)
        buttons.addStretch()
        bl.addLayout(buttons)
        self.backup_table = QTableWidget(0, 3)
        self.backup_table.setHorizontalHeaderLabels(["Archivo", "Fecha", "Tamaño"])
        self.backup_table.verticalHeader().setVisible(False)
        self.backup_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.backup_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.backup_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.backup_table.setAlternatingRowColors(True)
        self.backup_table.setShowGrid(False)
        self.backup_table.setMinimumHeight(180)
        header = self.backup_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        self.backup_table.itemSelectionChanged.connect(self._update_backup_buttons)
        bl.addWidget(self.backup_table)
        bl.addWidget(wrapping(muted(
            "Los backups se generan con la API de backup de SQLite (copias consistentes). Antes de "
            "restaurar se valida el archivo y se crea automáticamente un backup del estado actual "
            "(pre-restore_…). No se puede restaurar con una sesión en curso."
        )))
        root.addWidget(backups)

        # Data
        data = Card()
        dl = QVBoxLayout(data)
        dl.setContentsMargins(18, 14, 18, 14)
        dl.addWidget(section_title("Datos"))
        data_row = QHBoxLayout()
        data_label = wrapping(muted(f"Base de datos y configuración: {data_dir()}"))
        data_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        data_row.addWidget(data_label, 1)
        open_data = QPushButton("Abrir carpeta de datos")
        open_data.clicked.connect(lambda: open_folder(data_dir()))
        open_logs = QPushButton("Abrir logs")
        open_logs.clicked.connect(lambda: open_folder(logs_dir()))
        data_row.addWidget(open_data)
        data_row.addWidget(open_logs)
        dl.addLayout(data_row)
        dl.addWidget(muted(f"{APP_NAME} {__version__}"))
        root.addWidget(data)
        root.addStretch()

    # --- preferences -------------------------------------------------------
    def _load(self) -> None:
        self._loading = True
        s = self.settings
        self.start_minimized.setChecked(s.start_minimized)
        self.minimize_to_tray.setChecked(s.minimize_to_tray)
        self.confirm_exit.setChecked(s.confirm_exit_with_active)
        self.time_format.setCurrentIndex(max(0, self.time_format.findData(s.time_format)))
        self._show_export_dir()
        self._loading = False

    def _show_export_dir(self) -> None:
        current = self.settings.export_dir
        self.export_dir.setText(current or f"{documents_dir()}  (predeterminada)")

    def _choose_export_dir(self) -> None:
        start = self.settings.export_dir or str(documents_dir())
        chosen = QFileDialog.getExistingDirectory(self, "Carpeta de exportación", start)
        if chosen:
            self.settings.export_dir = chosen
            self._show_export_dir()
            self._save()

    def _reset_export_dir(self) -> None:
        self.settings.export_dir = ""
        self._show_export_dir()
        self._save()

    def _save(self, *_args) -> None:
        if self._loading:
            return
        s = self.settings
        s.start_minimized = self.start_minimized.isChecked()
        s.minimize_to_tray = self.minimize_to_tray.isChecked()
        s.confirm_exit_with_active = self.confirm_exit.isChecked()
        s.time_format = self.time_format.currentData()
        try:
            self.store.save(s)
        except OSError as exc:
            log.error("Could not save settings: %s", exc)
            self.saved_label.setText("No se pudo guardar la configuración")
            return
        set_time_format(s.time_format)
        self.saved_label.setText("Cambios guardados ✓")
        self.settings_changed.emit(s)
        self.signals.entries_changed.emit()  # re-render times with the new format

    # --- backups -----------------------------------------------------------
    def refresh_backups(self) -> None:
        self.backups_path.setText(f"Carpeta: {self.services.backups.backups_dir}")
        files = self.services.backups.list_backups()
        self.backup_table.setRowCount(len(files))
        for row, f in enumerate(files):
            name = QTableWidgetItem(f.path.name)
            name.setData(Qt.UserRole, str(f.path))
            self.backup_table.setItem(row, 0, name)
            self.backup_table.setItem(row, 1, QTableWidgetItem(f.modified.strftime("%d/%m/%Y %H:%M:%S")))
            size = QTableWidgetItem(_size(f.size))
            size.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.backup_table.setItem(row, 2, size)
        self._update_backup_buttons()

    def _update_backup_buttons(self) -> None:
        self.restore_selected_btn.setEnabled(bool(self.backup_table.selectedItems()))

    def create_backup(self) -> None:
        try:
            path = self.services.backups.create_backup()
        except Exception as exc:  # noqa: BLE001
            show_error(self, exc)
            return
        self.refresh_backups()
        QMessageBox.information(self, APP_NAME, f"Backup creado:\n{path}")

    def restore_selected(self) -> None:
        items = self.backup_table.selectedItems()
        if items:
            self.restore(Path(self.backup_table.item(items[0].row(), 0).data(Qt.UserRole)))

    def restore_from_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Restaurar backup", str(self.services.backups.backups_dir), "Base de datos (*.db *.sqlite);;Todos (*)"
        )
        if path:
            self.restore(Path(path))

    def restore(self, path: Path) -> None:
        backups = self.services.backups
        if self.services.timer.get_active() is not None:
            QMessageBox.warning(
                self, APP_NAME, "Hay una sesión en curso. Detenela desde Timer antes de restaurar un backup."
            )
            return
        try:
            info = backups.validate(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, APP_NAME, f"No se puede restaurar este archivo.\n\n{user_message(exc)}")
            return
        active_note = "\n\nEl backup contiene una sesión en curso: al terminar se te preguntará qué hacer." if info.has_active_session else ""
        if not confirm(
            self,
            "Restaurar backup",
            f"¿Reemplazar TODOS los datos actuales por los del backup?\n\n{path.name}\n"
            f"{info.projects} proyectos · {info.tasks} tareas · {info.entries} sesiones\n\n"
            "Antes se creará automáticamente un backup del estado actual."
            f"{active_note}",
            yes="Restaurar",
        ):
            return
        main_window = self.window()
        if hasattr(main_window, "shutdown"):
            main_window.shutdown()  # no timer may touch the DB while it is replaced
        try:
            result = backups.restore(path)
        except Exception as exc:  # noqa: BLE001
            show_error(self, exc)
            self._after_restore(main_window)
            return
        self._after_restore(main_window)
        QMessageBox.information(
            self,
            APP_NAME,
            f"Backup restaurado.\n\nEl estado anterior se guardó en:\n{result.safety_backup}",
        )
        run_recovery(self.services, self)
        self._after_restore(main_window)

    def _after_restore(self, main_window) -> None:
        if hasattr(main_window, "restart_timers"):
            main_window.restart_timers()
        self.refresh_backups()
        for signal in (self.signals.projects_changed, self.signals.entries_changed, self.signals.session_state_changed):
            signal.emit()
