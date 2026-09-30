"""Dark theme shared by the main window and overlays."""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

BG = "#14151b"
SURFACE = "#1c1e27"
SURFACE_2 = "#252836"
SURFACE_3 = "#2e3243"
BORDER = "#343850"
TEXT = "#e9eaf2"
MUTED = "#9197ad"
ACCENT = "#7c5cff"
ACCENT_HOVER = "#8f74ff"
ACCENT_2 = "#22d3ee"
DANGER = "#ff5c7a"
SUCCESS = "#3ddc97"
WARNING = "#ffb454"

QSS = f"""
QWidget {{
    background: {BG};
    color: {TEXT};
    font-size: 10pt;
}}
QToolTip {{
    background: {SURFACE_2};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 4px 6px;
}}
QLabel {{ background: transparent; }}
QLabel#h1 {{ font-size: 17pt; font-weight: 600; }}
QLabel#h2 {{ font-size: 12pt; font-weight: 600; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#hint {{ color: {MUTED}; font-size: 9pt; }}

QFrame#card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QFrame#info {{
    background: rgba(124, 92, 255, 0.10);
    border: 1px solid rgba(124, 92, 255, 0.45);
    border-radius: 10px;
}}
QFrame#warn {{
    background: rgba(255, 180, 84, 0.10);
    border: 1px solid rgba(255, 180, 84, 0.5);
    border-radius: 10px;
}}

QListWidget#nav {{
    background: {SURFACE};
    border: none;
    padding: 10px 8px;
    outline: 0;
    font-size: 11pt;
}}
QListWidget#nav::item {{
    padding: 10px 12px;
    margin: 2px 0;
    border-radius: 8px;
}}
QListWidget#nav::item:hover {{ background: {SURFACE_2}; }}
QListWidget#nav::item:selected {{ background: {ACCENT}; color: white; }}

QListWidget, QTableWidget, QTreeWidget {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    alternate-background-color: {SURFACE_2};
    gridline-color: {BORDER};
    outline: 0;
}}
QListWidget::item {{ padding: 7px 8px; border-radius: 6px; }}
QListWidget::item:selected, QTableWidget::item:selected {{
    background: rgba(124, 92, 255, 0.35);
    color: {TEXT};
}}
QTableWidget::item {{ padding: 4px 6px; }}
QHeaderView::section {{
    background: {SURFACE_2};
    color: {MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 6px 8px;
    font-weight: 600;
}}
QTableCornerButton::section {{ background: {SURFACE_2}; border: none; }}

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px 8px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border: 1px solid {ACCENT};
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT};
    outline: 0;
}}

QPushButton, QToolButton {{
    background: {SURFACE_3};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 7px 14px;
}}
QPushButton:hover, QToolButton:hover {{ background: #383d52; }}
QPushButton:pressed, QToolButton:pressed {{ background: {SURFACE_2}; }}
QPushButton:disabled, QToolButton:disabled {{ color: #5d6275; background: {SURFACE_2}; }}
QPushButton#primary {{
    background: {ACCENT};
    border: 1px solid {ACCENT};
    color: white;
    font-weight: 600;
}}
QPushButton#primary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#danger {{ color: {DANGER}; }}
QPushButton#hotkey {{
    background: {SURFACE_2};
    font-family: "Consolas", "Cascadia Mono", monospace;
    text-align: left;
    padding: 6px 10px;
}}
QPushButton#hotkey[capturing="true"] {{
    border: 1px solid {ACCENT_2};
    color: {ACCENT_2};
}}

QCheckBox, QRadioButton {{ background: transparent; spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 18px; height: 18px;
    border: 1px solid {BORDER};
    background: {SURFACE_2};
}}
QCheckBox::indicator {{ border-radius: 5px; }}
QRadioButton::indicator {{ border-radius: 9px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {ACCENT};
    border: 1px solid {ACCENT};
}}

QSlider::groove:horizontal {{ height: 6px; background: {SURFACE_3}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 3px; }}
QSlider::handle:horizontal {{
    background: white; width: 16px; height: 16px; margin: -5px 0; border-radius: 8px;
}}

QGroupBox {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 12px;
    margin-top: 14px;
    padding: 14px 12px 12px 12px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: {MUTED};
}}
QGroupBox QWidget {{ background: transparent; }}
QGroupBox QLineEdit, QGroupBox QComboBox, QGroupBox QSpinBox, QGroupBox QPlainTextEdit {{
    background: {SURFACE_2};
}}
QGroupBox QPushButton, QGroupBox QToolButton {{ background: {SURFACE_3}; }}
QGroupBox QPushButton#primary {{ background: {ACCENT}; }}
QGroupBox QPushButton#hotkey {{ background: {SURFACE_2}; }}

QScrollArea {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {SURFACE_3}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {SURFACE_3}; border-radius: 4px; min-width: 30px; }}

QProgressBar {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 6px;
    text-align: center;
    height: 16px;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 5px; }}

QStatusBar {{ background: {SURFACE}; border-top: 1px solid {BORDER}; color: {MUTED}; }}
QStatusBar QLabel {{ color: {MUTED}; padding: 0 6px; }}
QMenu {{ background: {SURFACE_2}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 20px; border-radius: 6px; }}
QMenu::item:selected {{ background: {ACCENT}; }}
QDialog {{ background: {BG}; }}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(BG))
    palette.setColor(QPalette.WindowText, QColor(TEXT))
    palette.setColor(QPalette.Base, QColor(SURFACE_2))
    palette.setColor(QPalette.AlternateBase, QColor(SURFACE))
    palette.setColor(QPalette.Text, QColor(TEXT))
    palette.setColor(QPalette.Button, QColor(SURFACE_3))
    palette.setColor(QPalette.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.Highlight, QColor(ACCENT))
    palette.setColor(QPalette.HighlightedText, QColor("white"))
    palette.setColor(QPalette.PlaceholderText, QColor(MUTED))
    palette.setColor(QPalette.Link, QColor(ACCENT_2))
    palette.setColor(QPalette.LinkVisited, QColor(ACCENT_2))
    palette.setColor(QPalette.ToolTipBase, QColor(SURFACE_2))
    palette.setColor(QPalette.ToolTipText, QColor(TEXT))
    app.setPalette(palette)
    font = QFont("Segoe UI")
    font.setPointSize(10)
    app.setFont(font)
    app.setStyleSheet(QSS)
