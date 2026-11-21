"""PyQtGraph bar charts styled for the dark theme, with hover tooltips.

Values are hours (floats). Recessive axes and grid; one value axis; thin bars;
horizontal bars carry direct labels so identity never relies on color alone.
"""

from __future__ import annotations

import pyqtgraph as pg
from PySide6.QtGui import QCursor, QFont
from PySide6.QtWidgets import QToolTip

from worktrack.ui import theme

SERIES_BLUE = "#3987E5"  # single-series hue (time charts)
AXIS = "#5B6270"
GRID_ALPHA = 0.12

pg.setConfigOptions(antialias=True, background=theme.SURFACE, foreground=theme.MUTED)


class BarChart(pg.PlotWidget):
    def __init__(self, horizontal: bool = False, parent=None) -> None:
        super().__init__(parent=parent)
        self.horizontal = horizontal
        self._tooltips: list[str] = []
        self._values: list[float] = []
        self._items: list = []
        item = self.getPlotItem()
        item.setMouseEnabled(x=False, y=False)
        item.hideButtons()
        item.setMenuEnabled(False)
        item.layout.setContentsMargins(4, 8, 12, 4)
        font = QFont("Segoe UI", 8)
        for name in ("left", "bottom"):
            axis = item.getAxis(name)
            axis.setPen(pg.mkPen(AXIS))
            axis.setTextPen(pg.mkPen(theme.MUTED))
            axis.setTickFont(font)
        value_axis = "bottom" if horizontal else "left"
        item.showGrid(x=horizontal, y=not horizontal, alpha=GRID_ALPHA)
        item.getAxis(value_axis).setLabel("horas", color=theme.MUTED)
        self.setMinimumHeight(200)
        self.scene().sigMouseMoved.connect(self._on_hover)

    def set_data(
        self,
        labels: list[str],
        values: list[float],
        colors: list[str] | str = SERIES_BLUE,
        tooltips: list[str] | None = None,
        value_labels: list[str] | None = None,
        max_ticks: int = 16,
    ) -> None:
        item = self.getPlotItem()
        for old in self._items:
            item.removeItem(old)
        self._items = []
        self._values = list(values)
        self._tooltips = tooltips or [f"{lab}: {val:.2f} h" for lab, val in zip(labels, values)]
        n = len(values)
        if n == 0 or max(values, default=0) <= 0:
            empty = pg.TextItem("Sin datos en el período", color=theme.MUTED, anchor=(0.5, 0.5))
            item.addItem(empty)
            empty.setPos(0.5, 0.5)
            item.setXRange(0, 1)
            item.setYRange(0, 1)
            item.getAxis("left").setTicks([[]])
            item.getAxis("bottom").setTicks([[]])
            self._items.append(empty)
            self._values = []
            return

        brushes = [pg.mkBrush(c) for c in (colors if isinstance(colors, list) else [colors] * n)]
        top = max(values)
        if self.horizontal:
            ys = [n - 1 - i for i in range(n)]  # first item on top
            bars = pg.BarGraphItem(x0=[0] * n, y=ys, height=0.55, width=values, brushes=brushes, pen=None)
            item.getAxis("left").setTicks([[(y, lab) for y, lab in zip(ys, labels)]])
            item.getAxis("bottom").setTicks(None)
            texts = value_labels or [f"{v:.2f} h" for v in values]
            for y, v, text in zip(ys, values, texts):
                label = pg.TextItem(text, color=theme.TEXT, anchor=(0, 0.5))
                label.setPos(v + top * 0.015, y)
                item.addItem(label)
                self._items.append(label)
            item.setXRange(0, top * 1.55, padding=0)  # room for the value labels
            item.setYRange(-0.6, n - 0.4, padding=0)
        else:
            xs = list(range(n))
            bars = pg.BarGraphItem(x=xs, height=values, width=0.62, brushes=brushes, pen=None)
            step = max(1, -(-n // max_ticks))  # ceil: thin out crowded labels
            item.getAxis("bottom").setTicks([[(x, labels[x]) for x in xs[::step]]])
            item.getAxis("left").setTicks(None)
            item.setXRange(-0.6, n - 0.4, padding=0)
            item.setYRange(0, top * 1.12, padding=0)
        item.addItem(bars)
        self._items.append(bars)

    def _on_hover(self, pos) -> None:
        if not self._values:
            return
        view = self.getPlotItem().vb
        if not view.sceneBoundingRect().contains(pos):
            QToolTip.hideText()
            return
        point = view.mapSceneToView(pos)
        n = len(self._values)
        if self.horizontal:
            index = n - 1 - round(point.y())
            inside = abs(point.y() - round(point.y())) <= 0.4
        else:
            index = round(point.x())
            inside = abs(point.x() - index) <= 0.4
        if inside and 0 <= index < n:
            QToolTip.showText(QCursor.pos(), self._tooltips[index], self)
        else:
            QToolTip.hideText()
