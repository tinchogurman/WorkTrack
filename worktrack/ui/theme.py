"""Dark theme (Fusion style + palette + stylesheet)."""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

BG = "#14161B"
SIDEBAR = "#0E1014"
SURFACE = "#1B1E25"
SURFACE_2 = "#232730"
BORDER = "#2D323D"
TEXT = "#E7E9EE"
MUTED = "#8C94A3"
ACCENT = "#6E8BFF"
GREEN = "#22C55E"
GREEN_HOVER = "#2FD46B"
GREEN_PRESSED = "#16A34A"
RED = "#EF4444"
RED_HOVER = "#F25C5C"
RED_PRESSED = "#DC2626"
WARNING = "#F59E0B"

STYLESHEET = f"""
* {{ outline: none; }}
QWidget {{ background: {BG}; color: {TEXT}; font-size: 10pt; }}
QToolTip {{ background: {SURFACE_2}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px; }}

#Sidebar {{ background: {SIDEBAR}; border-right: 1px solid {BORDER}; }}
#Sidebar QLabel#AppTitle {{ background: transparent; font-size: 15pt; font-weight: 600; padding: 18px 16px 14px 18px; }}
#Sidebar QListWidget {{ background: transparent; border: none; font-size: 11pt; }}
#Sidebar QListWidget::item {{ padding: 10px 14px; margin: 2px 8px; border-radius: 6px; color: {MUTED}; }}
#Sidebar QListWidget::item:hover {{ background: {SURFACE}; color: {TEXT}; }}
#Sidebar QListWidget::item:selected {{ background: {SURFACE_2}; color: {TEXT}; }}
#Sidebar QListWidget::item:disabled {{ color: #4A505C; }}
#Sidebar QLabel#SidebarStatus {{ background: transparent; color: {MUTED}; padding: 12px 18px; }}

QLabel#PageTitle {{ font-size: 18pt; font-weight: 600; background: transparent; }}
QLabel#SectionTitle {{ font-size: 12pt; font-weight: 600; background: transparent; }}
QLabel#Muted, QLabel[muted="true"] {{ color: {MUTED}; background: transparent; }}
QLabel#ErrorLabel {{ color: {RED}; background: transparent; }}
QLabel#OkLabel {{ color: {GREEN}; background: transparent; }}

QFrame#Card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; }}
QFrame#Card QLabel {{ background: transparent; }}

QLabel#TimerDisplay {{
    font-family: "Segoe UI", sans-serif; font-size: 64pt; font-weight: 300;
    background: transparent; color: {MUTED}; letter-spacing: 2px;
}}
QLabel#TimerDisplay[running="true"] {{ color: {TEXT}; }}
QLabel#StatusLine {{ background: transparent; color: {MUTED}; font-size: 11pt; }}

QLineEdit, QComboBox, QDateTimeEdit, QDateEdit, QTimeEdit, QPlainTextEdit, QSpinBox {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 6px;
    padding: 6px 8px; selection-background-color: {ACCENT};
}}
QLineEdit:focus, QComboBox:focus, QDateTimeEdit:focus, QPlainTextEdit:focus {{ border: 1px solid {ACCENT}; }}
QLineEdit:disabled, QComboBox:disabled {{ color: {MUTED}; background: {SURFACE}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: {SURFACE_2}; border: 1px solid {BORDER}; selection-background-color: {ACCENT}; }}

QPushButton {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 6px;
    padding: 7px 14px;
}}
QPushButton:hover {{ background: #2B303B; }}
QPushButton:pressed {{ background: #1F232B; }}
QPushButton:focus {{ border: 1px solid {ACCENT}; }}
QPushButton:disabled {{ color: #5A606B; background: {SURFACE}; }}
QPushButton[variant="primary"] {{ background: {ACCENT}; border: none; color: white; font-weight: 600; }}
QPushButton[variant="primary"]:hover {{ background: #839CFF; }}
QPushButton[variant="danger"] {{ color: {RED}; }}

QPushButton#PlayButton, QPushButton#StopButton {{
    min-width: 140px; min-height: 48px; border-radius: 24px; border: none;
    font-size: 13pt; font-weight: 700; color: white;
}}
QPushButton#PlayButton {{ background: {GREEN}; }}
QPushButton#PlayButton:hover {{ background: {GREEN_HOVER}; }}
QPushButton#PlayButton:pressed {{ background: {GREEN_PRESSED}; }}
QPushButton#StopButton {{ background: {RED}; }}
QPushButton#StopButton:hover {{ background: {RED_HOVER}; }}
QPushButton#StopButton:pressed {{ background: {RED_PRESSED}; }}
QPushButton#PlayButton:disabled, QPushButton#StopButton:disabled {{ background: {SURFACE_2}; color: #5A606B; }}
QPushButton#PlayButton:focus, QPushButton#StopButton:focus {{ border: 2px solid white; }}

QTableView, QTableWidget, QListWidget {{
    background: {SURFACE}; alternate-background-color: #1F232B; border: 1px solid {BORDER};
    border-radius: 8px; gridline-color: transparent;
    selection-background-color: #34405E; selection-color: {TEXT};
}}
QTableView::item, QTableWidget::item {{ padding: 6px; border: none; }}
QListWidget::item {{ padding: 7px 8px; }}
QHeaderView {{ background: {SURFACE}; border: none; }}
QHeaderView::section {{
    background: {SURFACE}; color: {MUTED}; border: none; border-bottom: 1px solid {BORDER};
    padding: 8px 6px; font-weight: 600;
}}
QTableCornerButton::section {{ background: {SURFACE}; border: none; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #3A404C; border-radius: 4px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #3A404C; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}

QCheckBox, QRadioButton {{ background: transparent; spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 14px; height: 14px; border: 1px solid #4A5160; background: {SURFACE_2};
}}
QCheckBox::indicator {{ border-radius: 3px; }}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {ACCENT}; border: 3px solid {SURFACE_2}; outline: 1px solid {ACCENT};
}}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {ACCENT}; }}
QSplitter::handle {{ background: {BG}; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{
    background: transparent; color: {MUTED}; padding: 8px 14px; margin-right: 4px;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}
QMessageBox, QDialog {{ background: {BG}; }}
QCalendarWidget QWidget {{ alternate-background-color: {SURFACE_2}; }}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    palette = QPalette()
    roles = {
        QPalette.Window: BG,
        QPalette.WindowText: TEXT,
        QPalette.Base: SURFACE_2,
        QPalette.AlternateBase: SURFACE,
        QPalette.Text: TEXT,
        QPalette.Button: SURFACE_2,
        QPalette.ButtonText: TEXT,
        QPalette.Highlight: ACCENT,
        QPalette.HighlightedText: "#FFFFFF",
        QPalette.ToolTipBase: SURFACE_2,
        QPalette.ToolTipText: TEXT,
        QPalette.PlaceholderText: MUTED,
        QPalette.Link: ACCENT,
    }
    for role, color in roles.items():
        palette.setColor(role, QColor(color))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor("#5A606B"))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#5A606B"))
    palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor("#5A606B"))
    app.setPalette(palette)
    app.setStyleSheet(STYLESHEET)


def repolish(widget) -> None:
    """Re-apply the stylesheet after changing a dynamic property."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
