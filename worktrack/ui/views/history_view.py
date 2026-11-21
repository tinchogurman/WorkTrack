"""History: sortable, filterable table of sessions; add, edit and delete.

The date filter includes every session that overlaps the period (whole
records: a session from 23:00 to 01:00 appears when filtering either day).
"""

from __future__ import annotations

from PySide6.QtCore import QSortFilterProxyModel, Qt
from PySide6.QtGui import QBrush, QColor, QKeySequence, QShortcut, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from worktrack.core.errors import ValidationError
from worktrack.core.models import EntryView
from worktrack.core.timeutils import (
    format_decimal_hours,
    format_hms,
    format_local_date,
    format_local_end_time,
    format_local_time,
    to_db,
)
from worktrack.services.context import AppServices
from worktrack.ui import theme
from worktrack.ui.dialogs.entry_dialog import EntryDialog
from worktrack.ui.errors import confirm, show_error
from worktrack.ui.filters import PeriodPicker, ProjectTaskFilter
from worktrack.ui.icons import color_dot
from worktrack.ui.signals import AppSignals
from worktrack.ui.widgets import muted, page_title

COLUMNS = ["Fecha", "Proyecto", "Tarea", "Inicio", "Fin", "Duración", "Descripción"]
SORT_ROLE = Qt.UserRole + 1
ID_ROLE = Qt.UserRole + 2


def _item(text: str, sort_value=None) -> QStandardItem:
    item = QStandardItem(text)
    item.setEditable(False)
    item.setData(sort_value if sort_value is not None else text.casefold(), SORT_ROLE)
    return item


class HistoryView(QWidget):
    def __init__(self, services: AppServices, signals: AppSignals, parent=None) -> None:
        super().__init__(parent)
        self.services = services
        self.signals = signals
        self._build()
        signals.entries_changed.connect(self.refresh)
        signals.session_state_changed.connect(self.refresh)
        signals.projects_changed.connect(self._on_projects_changed)
        self.refresh()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)
        root.addWidget(page_title("History"))

        bar = QHBoxLayout()
        self.add_btn = QPushButton("+ Agregar sesión")
        self.add_btn.setProperty("variant", "primary")
        self.add_btn.setToolTip("Registrar una sesión que olvidaste cronometrar (Ctrl+N)")
        self.add_btn.clicked.connect(self.add_entry)
        self.edit_btn = QPushButton("Editar")
        self.edit_btn.setToolTip("Editar la sesión seleccionada (Enter / doble clic)")
        self.edit_btn.clicked.connect(self.edit_entry)
        self.delete_btn = QPushButton("Eliminar")
        self.delete_btn.setProperty("variant", "danger")
        self.delete_btn.setToolTip("Eliminar la sesión seleccionada (Supr)")
        self.delete_btn.clicked.connect(self.delete_entry)
        for b in (self.add_btn, self.edit_btn, self.delete_btn):
            bar.addWidget(b)
        bar.addStretch()
        self.summary = muted()
        bar.addWidget(self.summary)
        root.addLayout(bar)

        filters = QHBoxLayout()
        self.period_picker = PeriodPicker(
            self.services.analytics.today,
            ["all", "today", "week", "month", "last30", "year", "custom"],
            default="last30",
        )
        self.period_picker.changed.connect(self.refresh)
        self.project_filter = ProjectTaskFilter(self.services)
        self.project_filter.changed.connect(self.refresh)
        clear_btn = QPushButton("Limpiar filtros")
        clear_btn.clicked.connect(self.clear_filters)
        filters.addWidget(self.period_picker)
        filters.addSpacing(12)
        filters.addWidget(self.project_filter)
        filters.addWidget(clear_btn)
        filters.addStretch()
        root.addLayout(filters)
        self.filter_error = QLabel()
        self.filter_error.setObjectName("ErrorLabel")
        self.filter_error.hide()
        root.addWidget(self.filter_error)

        self.model = QStandardItemModel(0, len(COLUMNS), self)
        self.model.setHorizontalHeaderLabels(COLUMNS)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setSortRole(SORT_ROLE)

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.DescendingOrder)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(len(COLUMNS) - 1, QHeaderView.Stretch)
        header.setHighlightSections(False)
        self.table.doubleClicked.connect(lambda _: self.edit_entry())
        self.table.selectionModel().selectionChanged.connect(self._update_buttons)
        root.addWidget(self.table, 1)

        QShortcut(QKeySequence.Delete, self.table, self.delete_entry, context=Qt.WidgetShortcut)
        QShortcut(QKeySequence(Qt.Key_Return), self.table, self.edit_entry, context=Qt.WidgetShortcut)
        QShortcut(QKeySequence.New, self, self.add_entry, context=Qt.WidgetWithChildrenShortcut)

    # --- data --------------------------------------------------------------
    def clear_filters(self) -> None:
        for widget in (self.project_filter, self.period_picker):
            widget.blockSignals(True)
        self.project_filter.clear()
        self.period_picker.set_preset("all")
        for widget in (self.project_filter, self.period_picker):
            widget.blockSignals(False)
        self.refresh()

    def _on_projects_changed(self) -> None:
        self.project_filter.blockSignals(True)
        self.project_filter.reload()
        self.project_filter.blockSignals(False)
        self.refresh()

    def refresh(self) -> None:
        selected = self.selected_id()
        self.period_picker.refresh_relative()  # "Hoy" stays correct after midnight
        try:
            period = self.period_picker.period()
        except ValueError as exc:
            self.filter_error.setText(str(exc))
            self.filter_error.show()
            return
        self.filter_error.hide()
        try:
            views = self.services.entries.search(
                period, self.project_filter.project_id(), self.project_filter.task_id()
            )
        except Exception as exc:  # noqa: BLE001
            show_error(self, exc)
            return
        self.table.setSortingEnabled(False)
        self.model.removeRows(0, self.model.rowCount())
        total = 0
        for view in views:
            self.model.appendRow(self._row(view))
            total += view.entry.duration_seconds or 0
        self.table.setSortingEnabled(True)
        self.summary.setText(
            f"{len(views)} sesiones  ·  {format_hms(total)} ({format_decimal_hours(total)} h)"
        )
        self.summary.setToolTip(
            "Suma de las sesiones listadas completas (las que cruzan el borde del filtro "
            "cuentan enteras; los totales prorrateados están en Dashboard y Reports)."
        )
        if selected is not None:
            self._select(selected)
        self._update_buttons()

    def _row(self, view: EntryView) -> list[QStandardItem]:
        e = view.entry
        start_key = to_db(e.start_time)
        project_label = view.project_name + ("  (archivado)" if view.project_archived else "")
        project = _item(project_label)
        project.setIcon(color_dot(view.project_color))
        if e.is_active:
            end_item = _item("En curso", "9999")
            end_item.setForeground(QBrush(QColor(theme.GREEN)))
            duration = _item("—", -1)
        else:
            end_item = _item(format_local_end_time(e.start_time, e.end_time), to_db(e.end_time))
            if e.end_time.astimezone().date() != e.start_time.astimezone().date():
                end_item.setToolTip(f"Termina el {format_local_date(e.end_time)}")
            duration = _item(format_hms(e.duration_seconds), e.duration_seconds)
        duration.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row = [
            _item(format_local_date(e.start_time), start_key),
            project,
            _item(view.task_name),
            _item(format_local_time(e.start_time), start_key),
            end_item,
            duration,
            _item(e.description or ""),
        ]
        row[0].setData(e.id, ID_ROLE)
        if view.entry.description:
            row[-1].setToolTip(view.entry.description)
        return row

    def selected_id(self) -> int | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        source = self.proxy.mapToSource(rows[0])
        return self.model.item(source.row(), 0).data(ID_ROLE)

    def _select(self, entry_id: int) -> None:
        for row in range(self.model.rowCount()):
            if self.model.item(row, 0).data(ID_ROLE) == entry_id:
                index = self.proxy.mapFromSource(self.model.index(row, 0))
                self.table.selectRow(index.row())
                return

    def _update_buttons(self, *_args) -> None:
        has = self.selected_id() is not None
        self.edit_btn.setEnabled(has)
        self.delete_btn.setEnabled(has)

    # --- actions -----------------------------------------------------------
    def add_entry(self) -> None:
        if not self.services.projects.list_projects():
            show_error(self, _NoProjects())
            return
        dialog = EntryDialog(self.services, parent=self)
        if dialog.exec():
            self.signals.projects_changed.emit()  # a task may have been created
            self.signals.entries_changed.emit()
            self._select(dialog.saved.id)

    def edit_entry(self) -> None:
        entry_id = self.selected_id()
        if entry_id is None:
            return
        try:
            view = self.services.entries.get_view(entry_id)
            if view.entry.is_active:
                raise _ActiveNotEditable()
        except Exception as exc:  # noqa: BLE001
            show_error(self, exc)
            return
        dialog = EntryDialog(self.services, view, parent=self)
        if dialog.exec():
            self.signals.projects_changed.emit()
            self.signals.entries_changed.emit()

    def delete_entry(self) -> None:
        entry_id = self.selected_id()
        if entry_id is None:
            return
        try:
            view = self.services.entries.get_view(entry_id)
        except Exception as exc:  # noqa: BLE001
            show_error(self, exc)
            return
        e = view.entry
        if e.is_active:
            show_error(self, _ActiveNotEditable())
            return
        if not confirm(
            self,
            "Eliminar sesión",
            f"¿Eliminar esta sesión?\n\n{view.project_name} / {view.task_name}\n"
            f"{format_local_date(e.start_time)}  {format_local_time(e.start_time)} – "
            f"{format_local_time(e.end_time)}  ({format_hms(e.duration_seconds)})\n\n"
            "Esta acción no se puede deshacer.",
            yes="Eliminar",
        ):
            return
        try:
            self.services.entries.delete_entry(entry_id)
        except Exception as exc:  # noqa: BLE001
            show_error(self, exc)
            return
        self.signals.entries_changed.emit()


class _ActiveNotEditable(ValidationError):
    def __init__(self) -> None:
        super().__init__("La sesión está en curso. Detenela desde Timer antes de editarla o eliminarla.")


class _NoProjects(ValidationError):
    def __init__(self) -> None:
        super().__init__("Primero creá un proyecto en Projects.")
