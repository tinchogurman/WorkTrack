"""Dashboard: KPIs and charts computed from SQLite (sessions split per local day)."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from worktrack.core.timeutils import format_decimal_hours, format_hms
from worktrack.services.analytics_service import DashboardData
from worktrack.services.context import AppServices
from worktrack.ui.charts import BarChart
from worktrack.ui.errors import show_error
from worktrack.ui.filters import PeriodPicker
from worktrack.ui.signals import AppSignals
from worktrack.ui.widgets import Card, muted, page_title, section_title

WEEKDAYS_ES = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MONTHS_SHORT = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def hours(seconds: float) -> float:
    return seconds / 3600


def hms_dec(seconds: float) -> str:
    return f"{format_hms(seconds)}  ({format_decimal_hours(seconds)} h)"


class KpiTile(Card):
    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(2)
        self.title = muted(title)
        self.value = QLabel("—")
        self.value.setStyleSheet("font-size: 18pt; font-weight: 600; background: transparent;")
        self.value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.detail = muted("")
        layout.addWidget(self.title)
        layout.addWidget(self.value)
        layout.addWidget(self.detail)

    def set(self, value: str, detail: str = "", color: str | None = None) -> None:
        self.value.setText(value)
        dot =f"<span style='color:{color}'>●</span> " if color else ""
        self.detail.setText(dot + detail if detail else "")


class ChartCard(Card):
    def __init__(self, title: str, chart: BarChart, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 10)
        layout.addWidget(section_title(title))
        layout.addWidget(chart, 1)
        self.chart = chart


class DashboardView(QWidget):
    def __init__(self, services: AppServices, signals: AppSignals, parent=None) -> None:
        super().__init__(parent)
        self.services = services
        self.data: DashboardData | None = None
        self._dirty = True
        self._build()
        signals.entries_changed.connect(self._mark_dirty)
        signals.projects_changed.connect(self._mark_dirty)
        signals.session_state_changed.connect(self._mark_dirty)
        self._live = QTimer(self)
        self._live.setInterval(60_000)  # running session: keep "Hoy" current
        self._live.timeout.connect(self._live_tick)
        self._live.start()

    # --- layout ------------------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        root = QVBoxLayout(content)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        header = QHBoxLayout()
        header.addWidget(page_title("Dashboard"))
        header.addStretch()
        self.period_picker = PeriodPicker(
            self.services.analytics.today, ["week", "month", "last30", "year", "custom"], default="month"
        )
        self.period_picker.changed.connect(self.refresh)
        header.addWidget(self.period_picker)
        root.addLayout(header)
        self.error = QLabel()
        self.error.setObjectName("ErrorLabel")
        self.error.hide()
        root.addWidget(self.error)

        tiles = QGridLayout()
        tiles.setSpacing(12)
        self.kpi_today = KpiTile("Hoy")
        self.kpi_week = KpiTile("Esta semana")
        self.kpi_month = KpiTile("Este mes")
        self.kpi_total = KpiTile("Total del período")
        self.kpi_sessions = KpiTile("Sesiones del período")
        self.kpi_average = KpiTile("Promedio diario")
        self.kpi_top = KpiTile("Proyecto con mayor dedicación")
        tiles.addWidget(self.kpi_today, 0, 0)
        tiles.addWidget(self.kpi_week, 0, 1)
        tiles.addWidget(self.kpi_month, 0, 2)
        tiles.addWidget(self.kpi_total, 1, 0)
        tiles.addWidget(self.kpi_sessions, 1, 1)
        tiles.addWidget(self.kpi_average, 1, 2)
        tiles.addWidget(self.kpi_top, 0, 3, 2, 1)
        for col in range(4):
            tiles.setColumnStretch(col, 1)
        root.addLayout(tiles)

        self.chart_day = BarChart()
        self.chart_week = BarChart()
        self.chart_month = BarChart()
        self.chart_project = BarChart(horizontal=True)
        self.chart_task = BarChart(horizontal=True)
        grid = QGridLayout()
        grid.setSpacing(12)
        grid.addWidget(ChartCard("Horas por día", self.chart_day), 0, 0, 1, 2)
        grid.addWidget(ChartCard("Horas por semana", self.chart_week), 1, 0)
        grid.addWidget(ChartCard("Evolución mensual (12 meses)", self.chart_month), 1, 1)
        grid.addWidget(ChartCard("Distribución por proyecto", self.chart_project), 2, 0)
        grid.addWidget(ChartCard("Distribución por tarea (10 principales)", self.chart_task), 2, 1)
        for chart, height in (
            (self.chart_day, 220), (self.chart_week, 220), (self.chart_month, 220),
            (self.chart_project, 260), (self.chart_task, 260),
        ):
            chart.setFixedHeight(height)
        root.addLayout(grid)
        note = muted(
            "Las sesiones que cruzan la medianoche se reparten entre los días correspondientes. "
            "La sesión en curso se cuenta hasta este momento."
        )
        note.setWordWrap(True)
        root.addWidget(note)
        root.addStretch()
        self.content = content

    # --- refresh -----------------------------------------------------------
    def _mark_dirty(self) -> None:
        self._dirty = True
        if self.isVisible():
            self.refresh()

    def _live_tick(self) -> None:
        if self.isVisible() and (self.data is None or self.data.has_active):
            self.refresh()

    def showEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().showEvent(event)
        if self._dirty:
            self.refresh()

    def refresh(self) -> None:
        self.period_picker.refresh_relative()
        try:
            period = self.period_picker.period()
        except ValueError as exc:
            self.error.setText(str(exc))
            self.error.show()
            return
        self.error.hide()
        try:
            data = self.services.analytics.dashboard(period)
        except Exception as exc:  # noqa: BLE001
            show_error(self, exc)
            return
        self.data = data
        self._dirty = False
        self._fill_kpis(data)
        self._fill_charts(data)

    def _fill_kpis(self, d: DashboardData) -> None:
        self.kpi_today.set(format_hms(d.today_seconds), f"{format_decimal_hours(d.today_seconds)} h")
        self.kpi_week.set(format_hms(d.week_seconds), f"{format_decimal_hours(d.week_seconds)} h")
        self.kpi_month.set(format_hms(d.month_seconds), f"{format_decimal_hours(d.month_seconds)} h")
        self.kpi_total.set(format_hms(d.total_seconds), f"{format_decimal_hours(d.total_seconds)} h · {d.period.label}")
        self.kpi_sessions.set(str(d.sessions), f"{d.days_active} días con actividad")
        self.kpi_average.set(
            format_hms(d.average_daily_seconds),
            f"{format_decimal_hours(d.average_daily_seconds)} h por día trabajado",
        )
        if d.top_project:
            t = d.top_project
            self.kpi_top.set(t.name, f"{format_hms(t.seconds)} · {t.share:.0%} del período", t.color)
            self.kpi_top.value.setWordWrap(True)
        else:
            self.kpi_top.set("—", "Sin sesiones en el período")

    def _fill_charts(self, d: DashboardData) -> None:
        days = list(d.per_day["date"])
        secs = list(d.per_day["seconds"])
        self.chart_day.set_data(
            [f"{x:%d/%m}" for x in days],
            [hours(s) for s in secs],
            tooltips=[f"{WEEKDAYS_ES[x.weekday()]} {x:%d/%m/%Y}: {hms_dec(s)}" for x, s in zip(days, secs)],
        )
        w = d.per_week
        self.chart_week.set_data(
            [lab.split(" (")[0] for lab in w["label"]],
            [hours(s) for s in w["seconds"]],
            tooltips=[f"{lab}: {hms_dec(s)}" for lab, s in zip(w["label"], w["seconds"])],
        )
        m = d.per_month
        self.chart_month.set_data(
            [
                MONTHS_SHORT[x.month - 1] + (f" {x:%y}" if i == 0 or x.month == 1 else "")
                for i, x in enumerate(m["month"])
            ],
            [hours(s) for s in m["seconds"]],
            tooltips=[f"{lab}: {hms_dec(s)}" for lab, s in zip(m["label"], m["seconds"])],
        )
        p = d.per_project
        self.chart_project.set_data(
            list(p["project"]),
            [hours(s) for s in p["seconds"]],
            colors=list(p["color"]),
            tooltips=[f"{n}: {hms_dec(s)} · {sh:.0%}" for n, s, sh in zip(p["project"], p["seconds"], p["share"])],
            value_labels=[f"{format_decimal_hours(s)} h · {sh:.0%}" for s, sh in zip(p["seconds"], p["share"])],
        )
        t = d.per_task
        names = [f"{task} ({proj})" if proj else task for task, proj in zip(t["task"], t["project"])]
        self.chart_task.set_data(
            names,
            [hours(s) for s in t["seconds"]],
            colors=list(t["color"]),
            tooltips=[f"{n}: {hms_dec(s)} · {sh:.0%}" for n, s, sh in zip(names, t["seconds"], t["share"])],
            value_labels=[f"{format_decimal_hours(s)} h · {sh:.0%}" for s, sh in zip(t["seconds"], t["share"])],
        )
