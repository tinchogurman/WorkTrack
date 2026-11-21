"""Reports: day / week / month / custom range, project and task filters,
on-screen preview and export to Excel or CSV."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, QStandardPaths, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from worktrack.analytics.periods import Period, fmt_date
from worktrack.core.timeutils import format_clock, format_decimal_hours, format_hms
from worktrack.services.context import AppServices
from worktrack.services.exporters import default_filename, export_csv, export_xlsx
from worktrack.services.report_service import Report
from worktrack.ui.errors import show_error
from worktrack.ui.filters import ProjectTaskFilter
from worktrack.ui.icons import color_dot
from worktrack.ui.signals import AppSignals
from worktrack.ui.views.dashboard_view import KpiTile
from worktrack.ui.widgets import muted, page_title

log = logging.getLogger(__name__)

KINDS = [("day", "Día"), ("week", "Semana"), ("month", "Mes"), ("range", "Rango personalizado")]
WEEKDAYS_ES = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def _qdate(d: date) -> QDate:
    return QDate(d.year, d.month, d.day)


def _pydate(q: QDate) -> date:
    return date(q.year(), q.month(), q.day())


def _date_edit() -> QDateEdit:
    edit = QDateEdit()
    edit.setCalendarPopup(True)
    edit.setDisplayFormat("dd/MM/yyyy")
    return edit


def _item(text: str, align_right: bool = False) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    if align_right:
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return item


class ReportsView(QWidget):
    def __init__(self, services: AppServices, signals: AppSignals, parent=None) -> None:
        super().__init__(parent)
        self.services = services
        self.report: Report | None = None
        self._dirty = True
        self._last_dir: Path | None = None
        self._build()
        signals.entries_changed.connect(self._mark_dirty)
        signals.session_state_changed.connect(self._mark_dirty)
        signals.projects_changed.connect(self._on_projects_changed)

    # --- layout ------------------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)
        root.addWidget(page_title("Reports"))

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.kind = QComboBox()
        for key, label in KINDS:
            self.kind.addItem(label, key)
        self.kind.setCurrentIndex(2)  # Mes
        today = self.services.analytics.today()
        self.ref_date = _date_edit()
        self.ref_date.setDate(_qdate(today))
        self.from_date = _date_edit()
        self.from_date.setDate(_qdate(today.replace(day=1)))
        self.to_date = _date_edit()
        self.to_date.setDate(_qdate(today))
        self.ref_label = QLabel("Fecha")
        self.from_label = QLabel("Desde")
        self.to_label = QLabel("Hasta")
        controls.addWidget(QLabel("Reporte por"))
        controls.addWidget(self.kind)
        for w in (self.ref_label, self.ref_date, self.from_label, self.from_date, self.to_label, self.to_date):
            controls.addWidget(w)
        controls.addSpacing(12)
        self.filter = ProjectTaskFilter(self.services)
        controls.addWidget(self.filter)
        controls.addStretch()
        root.addLayout(controls)

        self.kind.currentIndexChanged.connect(self._on_kind)
        for edit in (self.ref_date, self.from_date, self.to_date):
            edit.dateChanged.connect(self.generate)
        self.filter.changed.connect(self.generate)
        self._on_kind(regenerate=False)

        header = QHBoxLayout()
        self.period_label = QLabel()
        self.period_label.setObjectName("SectionTitle")
        header.addWidget(self.period_label)
        header.addStretch()
        self.export_xlsx_btn = QPushButton("Exportar Excel")
        self.export_xlsx_btn.setProperty("variant", "primary")
        self.export_xlsx_btn.clicked.connect(lambda: self.export("xlsx"))
        self.export_csv_btn = QPushButton("Exportar CSV")
        self.export_csv_btn.clicked.connect(lambda: self.export("csv"))
        header.addWidget(self.export_xlsx_btn)
        header.addWidget(self.export_csv_btn)
        root.addLayout(header)
        self.error = QLabel()
        self.error.setObjectName("ErrorLabel")
        self.error.hide()
        root.addWidget(self.error)

        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        self.kpi_total = KpiTile("Total de horas")
        self.kpi_sessions = KpiTile("Sesiones")
        self.kpi_days = KpiTile("Días con actividad")
        for t in (self.kpi_total, self.kpi_sessions, self.kpi_days):
            tiles.addWidget(t)
        root.addLayout(tiles)

        self.tabs = QTabWidget()
        self.table_project = self._table(["Proyecto", "Duración", "Horas", "%"])
        self.table_task = self._table(["Proyecto", "Tarea", "Duración", "Horas", "%"])
        self.table_day = self._table(["Fecha", "Día", "Duración", "Horas"])
        self.table_week = self._table(["Semana", "Duración", "Horas"])
        self.table_sessions = self._table(
            ["Fecha", "Proyecto", "Tarea", "Inicio", "Fin", "Duración", "Horas", "En el período", "Descripción"]
        )
        self.tabs.addTab(self.table_project, "Por proyecto")
        self.tabs.addTab(self.table_task, "Por tarea")
        self.tabs.addTab(self.table_day, "Por día")
        self.tabs.addTab(self.table_week, "Por semana")
        self.tabs.addTab(self.table_sessions, "Sesiones")
        root.addWidget(self.tabs, 1)
        note = muted(
            "Solo sesiones finalizadas. Los totales reparten entre días las sesiones que cruzan la "
            "medianoche; la pestaña Sesiones muestra cada sesión completa y la parte que cae en el período."
        )
        note.setWordWrap(True)
        root.addWidget(note)

    @staticmethod
    def _table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        # only a free-text last column (Descripción) stretches; numbers stay next to their labels
        header.setStretchLastSection(headers[-1] == "Descripción")
        return table

    # --- period --------------------------------------------------------------
    def _on_kind(self, *_args, regenerate: bool = True) -> None:
        is_range = self.kind.currentData() == "range"
        for w in (self.ref_label, self.ref_date):
            w.setVisible(not is_range)
        for w in (self.from_label, self.from_date, self.to_label, self.to_date):
            w.setVisible(is_range)
        if regenerate:
            self.generate()

    def period(self) -> Period:
        kind = self.kind.currentData()
        if kind == "range":
            return Period.custom(_pydate(self.from_date.date()), _pydate(self.to_date.date()))
        ref = _pydate(self.ref_date.date())
        return {"day": Period.day, "week": Period.week, "month": Period.month}[kind](ref)

    # --- data --------------------------------------------------------------
    def _mark_dirty(self) -> None:
        self._dirty = True
        if self.isVisible():
            self.generate()

    def _on_projects_changed(self) -> None:
        self.filter.blockSignals(True)
        self.filter.reload()
        self.filter.blockSignals(False)
        self._mark_dirty()

    def showEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().showEvent(event)
        if self._dirty:
            self.generate()

    def generate(self) -> None:
        try:
            period = self.period()
        except ValueError as exc:
            self.error.setText(str(exc))
            self.error.show()
            return
        self.error.hide()
        try:
            report = self.services.reports.build(period, self.filter.project_id(), self.filter.task_id())
        except Exception as exc:  # noqa: BLE001
            show_error(self, exc)
            return
        self.report = report
        self._dirty = False
        self._fill(report)

    def _fill(self, r: Report) -> None:
        p = r.period
        filters = []
        if r.project_filter != "Todos":
            filters.append(r.project_filter)
        if r.task_filter != "Todas":
            filters.append(r.task_filter)
        suffix = f"  ·  {' / '.join(filters)}" if filters else ""
        self.period_label.setText(f"{p.label}  ({fmt_date(p.start)} – {fmt_date(p.end)}){suffix}")
        self.kpi_total.set(format_hms(r.total_seconds), f"{format_decimal_hours(r.total_seconds)} h")
        self.kpi_sessions.set(str(r.sessions))
        self.kpi_days.set(str(r.days_active), f"de {p.days} días del período")
        has_data = r.sessions > 0
        self.export_xlsx_btn.setEnabled(has_data)
        self.export_csv_btn.setEnabled(has_data)

        def fill(table: QTableWidget, rows: list[list[QTableWidgetItem]]) -> None:
            table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                for j, item in enumerate(row):
                    table.setItem(i, j, item)

        fill(self.table_project, [
            [QTableWidgetItem(color_dot(x.color), x.project), _item(format_hms(x.seconds), True),
             _item(format_decimal_hours(x.seconds), True), _item(f"{x.share:.0%}", True)]
            for x in r.per_project.itertuples()
        ])
        fill(self.table_task, [
            [QTableWidgetItem(color_dot(x.color), x.project), _item(x.task), _item(format_hms(x.seconds), True),
             _item(format_decimal_hours(x.seconds), True), _item(f"{x.share:.0%}", True)]
            for x in r.per_task.itertuples()
        ])
        fill(self.table_day, [
            [_item(fmt_date(x.date)), _item(WEEKDAYS_ES[x.date.weekday()]),
             _item(format_hms(x.seconds), True), _item(format_decimal_hours(x.seconds), True)]
            for x in r.per_day.itertuples()
        ])
        fill(self.table_week, [
            [_item(x.label), _item(format_hms(x.seconds), True), _item(format_decimal_hours(x.seconds), True)]
            for x in r.per_week.itertuples()
        ])
        fill(self.table_sessions, [
            [_item(d.start.strftime("%d/%m/%Y")), _item(d.project), _item(d.task),
             _item(f"{d.start:%d/%m/%Y} {format_clock(d.start)}"),
             _item(f"{d.end:%d/%m/%Y} {format_clock(d.end)}"),
             _item(format_hms(d.duration_seconds), True),
             _item(format_decimal_hours(d.duration_seconds), True),
             _item(format_hms(d.in_period_seconds), True), _item(d.description)]
            for d in r.details
        ])

    # --- export ------------------------------------------------------------
    def _default_dir(self) -> Path:
        if self._last_dir and self._last_dir.is_dir():
            return self._last_dir
        docs = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        return Path(docs) if docs else Path.home()

    def export(self, kind: str) -> None:
        if self.report is None:
            return
        suggested = self._default_dir() / default_filename(self.report, kind)
        filters = "Excel (*.xlsx)" if kind == "xlsx" else "CSV (*.csv)"
        path, _ = QFileDialog.getSaveFileName(self, "Exportar reporte", str(suggested), filters)
        if not path:
            return
        target = Path(path)
        if target.suffix.lower() != f".{kind}":
            target = target.with_suffix(f".{kind}")
        try:
            saved = (export_xlsx if kind == "xlsx" else export_csv)(self.report, target)
        except Exception as exc:  # noqa: BLE001
            show_error(self, exc)
            return
        self._last_dir = saved.parent
        QMessageBox.information(self, "WorkTrack", f"Reporte exportado:\n{saved}")
