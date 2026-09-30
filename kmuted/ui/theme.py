"""Design tokens and the app-wide stylesheet."""

from __future__ import annotations

import sys

from PySide6.QtGui import QColor, QFont, QPalette, QPixmapCache
from PySide6.QtWidgets import QApplication

# --- palette -------------------------------------------------------------------
BG = "#0e0f15"
BG_2 = "#12131b"
SURFACE = "#171923"
SURFACE_2 = "#1e2130"
SURFACE_3 = "#282c3e"
HOVER = "#30354a"
BORDER = "#272b3d"
BORDER_2 = "#353a52"
TEXT = "#eceef6"
MUTED = "#8b91a8"
FAINT = "#5c6278"
ACCENT = "#7c5cff"
ACCENT_HOVER = "#8f74ff"
ACCENT_DEEP = "#5b3fe0"
ACCENT_2 = "#22d3ee"
BLUE = "#5b8cff"
DANGER = "#ff5c7a"
SUCCESS = "#3ddc97"
WARNING = "#ffb454"

# accent palettes: (accent, hover, deep, gradient end, highlight)
ACCENTS = {
    "violet": ("#7c5cff", "#8f74ff", "#5b3fe0", "#5b8cff", "#22d3ee"),
    "blue": ("#3b82f6", "#5b9bff", "#2563eb", "#22d3ee", "#22d3ee"),
    "cyan": ("#06b6d4", "#22d3ee", "#0891b2", "#3b82f6", "#a78bfa"),
    "pink": ("#ec4899", "#f472b6", "#db2777", "#a855f7", "#22d3ee"),
    "green": ("#10b981", "#34d399", "#059669", "#22d3ee", "#a3e635"),
    "orange": ("#f97316", "#fb923c", "#ea580c", "#f43f5e", "#facc15"),
    "red": ("#ef4444", "#f87171", "#dc2626", "#f97316", "#fbbf24"),
}
ACCENT_NAMES = {
    "violet": "Фиолетовый",
    "blue": "Синий",
    "cyan": "Бирюзовый",
    "pink": "Розовый",
    "green": "Зелёный",
    "orange": "Оранжевый",
    "red": "Красный",
}


def set_accent(name: str) -> None:
    global ACCENT, ACCENT_HOVER, ACCENT_DEEP, BLUE, ACCENT_2
    ACCENT, ACCENT_HOVER, ACCENT_DEEP, BLUE, ACCENT_2 = ACCENTS.get(name, ACCENTS["violet"])


RADIUS = 12
FONT_FAMILY = "Segoe UI Variable Text" if sys.platform == "win32" else "Segoe UI"


def rgba(hex_color: str, alpha: float) -> str:
    c = QColor(hex_color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"


def build_qss() -> str:
    return f"""
* {{ outline: 0; }}
QMainWindow, QDialog {{ background: {BG}; }}
QWidget {{ color: {TEXT}; font-size: 10pt; }}
QToolTip {{
    background: {SURFACE_2}; color: {TEXT};
    border: 1px solid {BORDER_2}; border-radius: 6px; padding: 5px 8px;
}}

QLabel {{ background: transparent; }}
QLabel#h1 {{ font-size: 20pt; font-weight: 700; }}
QLabel#h2 {{ font-size: 13pt; font-weight: 650; }}
QLabel#h3 {{ font-size: 10.5pt; font-weight: 650; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#hint {{ color: {MUTED}; font-size: 9pt; }}
QLabel#eyebrow {{ color: {ACCENT_2}; font-size: 8.5pt; font-weight: 700; letter-spacing: 1px; }}
QLabel#chip {{
    background: {SURFACE_3}; border: 1px solid {BORDER_2};
    border-radius: 10px; padding: 3px 10px; color: {TEXT}; font-size: 9pt;
}}
QLabel#chipOk {{
    background: {rgba(SUCCESS, 0.12)}; border: 1px solid {rgba(SUCCESS, 0.45)};
    border-radius: 10px; padding: 3px 10px; color: {SUCCESS}; font-size: 9pt; font-weight: 600;
}}
QLabel#chipWarn {{
    background: {rgba(WARNING, 0.12)}; border: 1px solid {rgba(WARNING, 0.45)};
    border-radius: 10px; padding: 3px 10px; color: {WARNING}; font-size: 9pt; font-weight: 600;
}}

QFrame#card {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: {RADIUS + 2}px;
}}
QFrame#cardHover {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: {RADIUS}px;
}}
QFrame#cardHover:hover {{ border: 1px solid {BORDER_2}; background: #1a1d29; }}
QFrame#cardSelected {{
    background: {rgba(ACCENT, 0.10)}; border: 1px solid {rgba(ACCENT, 0.7)}; border-radius: {RADIUS}px;
}}
QFrame#info {{
    background: {rgba(ACCENT, 0.08)}; border: 1px solid {rgba(ACCENT, 0.35)}; border-radius: {RADIUS}px;
}}
QFrame#warn {{
    background: {rgba(WARNING, 0.08)}; border: 1px solid {rgba(WARNING, 0.4)}; border-radius: {RADIUS}px;
}}
QFrame#divider {{ background: {BORDER}; max-height: 1px; min-height: 1px; border: none; }}

QListWidget, QTableWidget, QTreeWidget {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: {RADIUS}px;
    alternate-background-color: {SURFACE_2}; gridline-color: {BORDER};
}}
QListWidget::item {{ padding: 8px 10px; border-radius: 8px; margin: 1px 4px; }}
QListWidget::item:hover {{ background: {SURFACE_2}; }}
QListWidget::item:selected, QTableWidget::item:selected {{
    background: {rgba(ACCENT, 0.28)}; color: {TEXT};
}}
QTableWidget::item {{ padding: 4px 6px; }}
QHeaderView::section {{
    background: {SURFACE_2}; color: {MUTED}; border: none;
    border-bottom: 1px solid {BORDER}; padding: 7px 8px; font-weight: 600;
}}
QTableCornerButton::section {{ background: {SURFACE_2}; border: none; }}

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {SURFACE_2}; border: 1px solid {BORDER_2}; border-radius: 10px;
    padding: 7px 10px; selection-background-color: {ACCENT};
}}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QPlainTextEdit:hover {{ border-color: #444a66; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border: 1px solid {ACCENT};
}}
QLineEdit#search {{ padding-left: 34px; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE_2}; border: 1px solid {BORDER_2}; border-radius: 8px;
    selection-background-color: {ACCENT}; padding: 4px;
}}
QSpinBox::up-button, QSpinBox::down-button {{ width: 18px; border: none; background: transparent; }}

QPushButton, QToolButton {{
    background: {SURFACE_3}; border: 1px solid {BORDER_2}; border-radius: 10px;
    padding: 8px 16px; color: {TEXT};
}}
QPushButton:hover, QToolButton:hover {{ background: {HOVER}; border-color: #454b69; }}
QPushButton:pressed, QToolButton:pressed {{ background: {SURFACE_2}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {FAINT}; background: {SURFACE_2}; border-color: {BORDER}; }}
QPushButton#primary {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {ACCENT}, stop:1 {BLUE});
    border: none; color: white; font-weight: 600; padding: 9px 18px;
}}
QPushButton#primary:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {ACCENT_HOVER}, stop:1 #739cff);
}}
QPushButton#primary:pressed {{ background: {ACCENT_DEEP}; }}
QPushButton#primary:disabled {{ background: {SURFACE_3}; color: {FAINT}; }}
QPushButton#ghost, QToolButton#ghost {{ background: transparent; border: 1px solid transparent; }}
QPushButton#ghost:hover, QToolButton#ghost:hover {{ background: {SURFACE_3}; border-color: {BORDER_2}; }}
QPushButton#danger {{ color: {DANGER}; }}
QPushButton#danger:hover {{ background: {rgba(DANGER, 0.12)}; border-color: {rgba(DANGER, 0.5)}; }}
QPushButton#hotkey {{
    background: {SURFACE_2}; border: 1px solid {BORDER_2}; text-align: left; padding: 5px 10px;
    min-height: 26px;
}}
QPushButton#hotkey:hover {{ border-color: #454b69; }}
QPushButton#hotkey[capturing="true"] {{ border: 1px solid {ACCENT_2}; color: {ACCENT_2}; }}

QCheckBox, QRadioButton {{ background: transparent; spacing: 9px; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 18px; height: 18px; border: 1px solid {BORDER_2}; background: {SURFACE_2};
}}
QCheckBox::indicator {{ border-radius: 6px; }}
QRadioButton::indicator {{ border-radius: 10px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border: 1px solid {ACCENT}; }}
QRadioButton::indicator:checked {{
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
        stop:0 white, stop:0.35 white, stop:0.45 {ACCENT}, stop:1 {ACCENT});
    border: 1px solid {ACCENT};
}}

QSlider::groove:horizontal {{ height: 6px; background: {SURFACE_3}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT}, stop:1 {ACCENT_2});
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: white; width: 16px; height: 16px; margin: -5px 0; border-radius: 8px;
}}
QSlider::handle:horizontal:hover {{ background: #dcd5ff; }}

QGroupBox {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: {RADIUS + 2}px;
    margin-top: 16px; padding: 16px 14px 14px 14px; font-weight: 600;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 16px; padding: 0 6px; color: {MUTED}; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {SURFACE_3}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {HOVER}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {SURFACE_3}; border-radius: 4px; min-width: 30px; }}

QProgressBar {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 6px;
    text-align: center; height: 14px; color: {TEXT};
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT}, stop:1 {ACCENT_2});
    border-radius: 5px;
}}

QStatusBar {{ background: {BG_2}; border-top: 1px solid {BORDER}; color: {MUTED}; }}
QStatusBar QLabel {{ color: {MUTED}; padding: 0 6px; }}
QStatusBar::item {{ border: none; }}
QMenu {{ background: {SURFACE_2}; border: 1px solid {BORDER_2}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 7px 22px 7px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {ACCENT}; color: white; }}
QMenu::separator {{ height: 1px; background: {BORDER_2}; margin: 5px 8px; }}
QDialogButtonBox QPushButton {{ min-width: 90px; }}
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
    palette.setColor(QPalette.PlaceholderText, QColor(FAINT))
    palette.setColor(QPalette.ToolTipBase, QColor(SURFACE_2))
    palette.setColor(QPalette.ToolTipText, QColor(TEXT))
    palette.setColor(QPalette.Link, QColor(ACCENT_2))
    palette.setColor(QPalette.LinkVisited, QColor(ACCENT_2))
    app.setPalette(palette)
    font = QFont(FONT_FAMILY)
    font.setPointSizeF(10)
    font.setHintingPreference(QFont.PreferNoHinting)
    app.setFont(font)
    app.setStyleSheet(build_qss())
    QPixmapCache.setCacheLimit(4096)  # KB; keeps icon caches small
