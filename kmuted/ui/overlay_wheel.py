"""Radial phrase wheel shown over the game while its hotkey is held."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QCursor, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

from kmuted.rawinput import RawMouse
from kmuted.ui import theme

MAX_VECTOR = 160.0  # virtual stick radius (px of mouse travel)


def sector_for_vector(dx: float, dy: float, count: int, deadzone: float) -> int:
    """Slot index for a mouse vector (screen coords, 0 = up, clockwise); -1 = none."""
    if count <= 0 or math.hypot(dx, dy) < deadzone:
        return -1
    angle = math.degrees(math.atan2(dx, -dy)) % 360.0
    step = 360.0 / count
    return int(((angle + step / 2) % 360.0) // step)


def clamp_vector(dx: float, dy: float, limit: float = MAX_VECTOR) -> tuple[float, float]:
    length = math.hypot(dx, dy)
    if length <= limit or length == 0:
        return dx, dy
    k = limit / length
    return dx * k, dy * k


def _sector_path(center: QPointF, r_in: float, r_out: float, start_deg: float, span_deg: float) -> QPainterPath:
    """Ring sector. Angles are Qt-style (0 = 3 o'clock, counter-clockwise)."""
    outer = QRectF(center.x() - r_out, center.y() - r_out, 2 * r_out, 2 * r_out)
    inner = QRectF(center.x() - r_in, center.y() - r_in, 2 * r_in, 2 * r_in)
    path = QPainterPath()
    path.arcMoveTo(outer, start_deg)
    path.arcTo(outer, start_deg, span_deg)
    path.arcTo(inner, start_deg + span_deg, -span_deg)
    path.closeSubpath()
    return path


def _elide_lines(text: str, fm: QFontMetrics, width: int, max_lines: int = 2) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if fm.horizontalAdvance(candidate) <= width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = fm.elidedText(lines[-1] + " …", Qt.ElideRight, width)
    return [fm.elidedText(line, Qt.ElideRight, width) for line in lines]


def paint_wheel(
    p: QPainter,
    rect: QRectF,
    captions: list[str],
    selected: int,
    title: str = "",
    center_text: str = "",
    pointer: tuple[float, float] | None = None,
) -> None:
    p.setRenderHint(QPainter.Antialiasing)
    n = max(1, len(captions))
    size = min(rect.width(), rect.height())
    center = rect.center()
    r_out = size / 2 - 6
    r_in = r_out * 0.38
    step = 360.0 / n

    # backdrop
    glow = QRadialGradient(center, r_out + 6)
    glow.setColorAt(0.0, QColor(20, 21, 28, 235))
    glow.setColorAt(0.93, QColor(20, 21, 28, 230))
    glow.setColorAt(1.0, QColor(124, 92, 255, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(glow)
    p.drawEllipse(center, r_out + 6, r_out + 6)

    label_font = QFont(p.font())
    label_font.setPointSizeF(max(8.0, size / 42))
    label_font.setWeight(QFont.DemiBold)
    fm = QFontMetrics(label_font)

    for i, caption in enumerate(captions):
        # our slot i is centered at i*step clockwise from 12 o'clock
        qt_center = 90.0 - i * step
        path = _sector_path(center, r_in, r_out, qt_center - step / 2 + 0.8, step - 1.6)
        empty = not caption
        if i == selected:
            fill = QColor(theme.ACCENT)
            fill.setAlpha(235)
        elif empty:
            fill = QColor(40, 43, 58, 150)
        else:
            fill = QColor(46, 50, 67, 225)
        p.setBrush(fill)
        p.setPen(QPen(QColor(theme.ACCENT_2) if i == selected else QColor(70, 75, 100, 200), 1.4))
        p.drawPath(path)

        # caption
        mid = math.radians(i * step)
        r_mid = (r_in + r_out) / 2
        cx = center.x() + math.sin(mid) * r_mid
        cy = center.y() - math.cos(mid) * r_mid
        text = caption or "—"
        p.setFont(label_font)
        p.setPen(QColor("white") if i == selected else (QColor(theme.MUTED) if empty else QColor(theme.TEXT)))
        chord = 2 * r_mid * math.sin(math.radians(min(step, 120) / 2))
        max_w = int(min(chord * 0.92, (r_out - r_in) * 1.25))
        lines = _elide_lines(text, fm, max_w)
        line_h = fm.height()
        top = cy - line_h * len(lines) / 2
        for k, line in enumerate(lines):
            p.drawText(QRectF(cx - max_w / 2, top + k * line_h, max_w, line_h), Qt.AlignCenter, line)

        # slot number
        num_font = QFont(label_font)
        num_font.setPointSizeF(label_font.pointSizeF() * 0.7)
        p.setFont(num_font)
        p.setPen(QColor(255, 255, 255, 110))
        rn = r_out - fm.height() * 0.55
        p.drawText(
            QRectF(center.x() + math.sin(mid) * rn - 12, center.y() - math.cos(mid) * rn - 9, 24, 18),
            Qt.AlignCenter,
            str(i + 1),
        )

    # hub
    p.setPen(QPen(QColor(theme.BORDER), 1.5))
    p.setBrush(QColor(24, 25, 34, 245))
    p.drawEllipse(center, r_in - 5, r_in - 5)

    hub_w = int((r_in - 12) * 1.7)
    body = QFont(p.font())
    body.setPointSizeF(max(8.0, size / 48))
    p.setFont(body)
    bfm = QFontMetrics(body)
    if center_text:
        p.setPen(QColor(theme.TEXT))
        lines = _elide_lines(center_text, bfm, hub_w, 3)
    else:
        p.setPen(QColor(theme.MUTED))
        lines = _elide_lines(title, bfm, hub_w, 2) if title else []
    top = center.y() - bfm.height() * len(lines) / 2
    for k, line in enumerate(lines):
        p.drawText(QRectF(center.x() - hub_w / 2, top + k * bfm.height(), hub_w, bfm.height()), Qt.AlignCenter, line)

    # direction pointer
    if pointer is not None:
        px, py = pointer
        length = math.hypot(px, py)
        if length > 1:
            reach = min(1.0, length / MAX_VECTOR) * (r_in - 10)
            tip = QPointF(center.x() + px / length * reach, center.y() + py / length * reach)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.ACCENT_2))
            p.drawEllipse(tip, 5, 5)


class WheelOverlay(QWidget):
    """Frameless, click-through, never takes focus from the game."""

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowTransparentForInput
            | Qt.WindowDoesNotAcceptFocus
            | Qt.NoDropShadowWindowHint,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.NoFocus)
        self.slots = []
        self.title = ""
        self.hint = ""
        self.deadzone = 40.0
        self.vector = (0.0, 0.0)
        self.selected = -1
        self.raw = RawMouse()

    def open(self, title: str, slots, deadzone: float, hint: str = "") -> None:
        self.slots = list(slots)
        self.title = title
        self.hint = hint
        self.deadzone = deadzone
        self.vector = (0.0, 0.0)
        self.selected = -1
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        geo = screen.geometry()
        side = int(min(geo.width(), geo.height()) * 0.5)
        side = max(360, min(side, 620))
        self.setGeometry(geo.center().x() - side // 2, geo.center().y() - side // 2, side, side)
        self.show()
        self.raise_()
        self.raw.start(int(self.winId()))
        self.update()

    def hideEvent(self, event) -> None:  # noqa: N802
        self.raw.stop()
        super().hideEvent(event)

    def add_delta(self, dx: float, dy: float) -> None:
        if not dx and not dy:
            return
        vx, vy = clamp_vector(self.vector[0] + dx, self.vector[1] + dy)
        self.vector = (vx, vy)
        idx = sector_for_vector(vx, vy, len(self.slots), self.deadzone)
        if idx >= 0 and not self.slots[idx].caption:
            idx = -1  # empty slot = cancel
        if idx != self.selected:
            self.selected = idx
        self.update()

    def selected_slot(self):
        if 0 <= self.selected < len(self.slots):
            slot = self.slots[self.selected]
            return slot if slot.text.strip() else None
        return None

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        slot = self.selected_slot()
        center = slot.text if slot else ""
        hint = f"{self.title} — {self.hint}" if self.hint else self.title
        paint_wheel(
            p,
            QRectF(self.rect()),
            [s.caption for s in self.slots],
            self.selected,
            title=hint,
            center_text=center,
            pointer=self.vector,
        )
        p.end()


class WheelPreview(QWidget):
    """Static wheel drawing for the editor."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.captions: list[str] = []
        self.title = ""
        self.highlight = -1
        self.setMinimumSize(260, 260)

    def set_wheel(self, title: str, captions: list[str], highlight: int = -1) -> None:
        self.title, self.captions, self.highlight = title, captions, highlight
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        side = min(self.width(), self.height())
        rect = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        paint_wheel(p, rect, self.captions, self.highlight, title=self.title)
        p.end()
