"""App icon, drawn in code so the repo has no binary assets."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap

from kmuted.ui import theme


def render_logo(size: int, speaking: bool = False) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 64.0

    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0, QColor(theme.ACCENT))
    grad.setColorAt(1, QColor(theme.ACCENT_2) if speaking else QColor("#4b3bb8"))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(grad))
    p.drawRoundedRect(QRectF(2 * s, 2 * s, 60 * s, 60 * s), 16 * s, 16 * s)

    # speech bubble
    bubble = QPainterPath()
    bubble.addRoundedRect(QRectF(11 * s, 13 * s, 42 * s, 30 * s), 10 * s, 10 * s)
    tail = QPainterPath()
    tail.moveTo(QPointF(20 * s, 40 * s))
    tail.lineTo(QPointF(16 * s, 52 * s))
    tail.lineTo(QPointF(30 * s, 42 * s))
    tail.closeSubpath()
    p.setBrush(QColor("white"))
    p.drawPath(bubble.united(tail))

    # sound bars
    p.setPen(QPen(QColor(theme.ACCENT), 4.2 * s, Qt.SolidLine, Qt.RoundCap))
    for x, h in ((21, 6), (27, 12), (33, 16), (39, 10), (45, 5)):
        p.drawLine(QPointF(x * s, (28 - h / 2) * s), QPointF(x * s, (28 + h / 2) * s))
    p.end()
    return pm


def app_icon(speaking: bool = False) -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(render_logo(size, speaking))
    return icon
