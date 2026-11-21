"""Icons drawn at runtime (no binary assets needed)."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF

from worktrack.ui import theme


def color_dot(color: str, size: int = 12) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(QRectF(1, 1, size - 2, size - 2))
    painter.end()
    return QIcon(pixmap)


def app_icon(active: bool = False) -> QIcon:
    """Round clock-like badge; green with a play triangle when a session runs."""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.GREEN if active else theme.ACCENT))
        p.drawEllipse(QRectF(size * 0.04, size * 0.04, size * 0.92, size * 0.92))
        p.setBrush(QColor("#FFFFFF"))
        if active:
            tri = QPolygonF([
                QPointF(size * 0.40, size * 0.30),
                QPointF(size * 0.40, size * 0.70),
                QPointF(size * 0.72, size * 0.50),
            ])
            p.drawPolygon(tri)
        else:
            pen_w = max(1.5, size * 0.09)
            p.setBrush(Qt.NoBrush)
            pen = QPen(QColor("#FFFFFF"), pen_w, Qt.SolidLine, Qt.RoundCap)
            p.setPen(pen)
            c = size / 2
            p.drawLine(QPointF(c, c), QPointF(c, size * 0.26))
            p.drawLine(QPointF(c, c), QPointF(size * 0.70, c))
        p.end()
        icon.addPixmap(pixmap)
    return icon
