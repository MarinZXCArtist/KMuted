"""Radial phrase wheel shown over the game while its hotkey is held."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import (
    QColor,
    QConicalGradient,
    QCursor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from kmuted.rawinput import RawMouse
from kmuted.ui import theme
from kmuted.ui.icons import load_asset_pixmap

MAX_VECTOR = 160.0  # virtual stick radius (px of mouse travel)
_ART: dict[str, object] = {}


def _wheel_art():
    """User picture for the wheel hub (``assets/wheel_center.*``), loaded once."""
    if "hub" not in _ART:
        _ART["hub"] = load_asset_pixmap("wheel_center")
    return _ART["hub"]


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
    # Split on plain spaces only: a no-break space keeps "♪ name" together,
    # unless that word is too wide — then the note goes on its own line.
    words: list[str] = []
    for word in text.split(" "):
        if "\u00a0" in word and fm.horizontalAdvance(word) > width:
            words.extend(part for part in word.split("\u00a0") if part)
        elif word:
            words.append(word)
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


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
        round(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


def paint_wheel(
    p: QPainter,
    rect: QRectF,
    captions: list[str],
    selected: int,
    title: str = "",
    center_text: str = "",
    pointer: tuple[float, float] | None = None,
    highlights: list[float] | None = None,
    scale: float = 1.0,
) -> None:
    """Draw the wheel. ``highlights`` (0..1 per slot) animate the selection."""
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    n = max(1, len(captions))
    if highlights is None or len(highlights) != len(captions):
        highlights = [1.0 if i == selected else 0.0 for i in range(len(captions))]
    size = min(rect.width(), rect.height())
    center = rect.center()
    if scale != 1.0:
        p.translate(center)
        p.scale(scale, scale)
        p.translate(-center)
    grow = size * 0.028
    r_out = size / 2 - grow - 8
    r_in = r_out * 0.38
    step = 360.0 / n

    # backdrop: dark disc with a soft colored rim
    glow = QRadialGradient(center, r_out + grow + 8)
    glow.setColorAt(0.0, QColor(16, 17, 24, 238))
    glow.setColorAt(0.9, QColor(16, 17, 24, 232))
    glow.setColorAt(1.0, QColor(124, 92, 255, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(glow)
    p.drawEllipse(center, r_out + grow + 8, r_out + grow + 8)
    rim = QConicalGradient(center, 90)
    rim.setColorAt(0.0, QColor(124, 92, 255, 160))
    rim.setColorAt(0.5, QColor(34, 211, 238, 120))
    rim.setColorAt(1.0, QColor(124, 92, 255, 160))
    p.setPen(QPen(rim, 1.6))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(center, r_out + 3, r_out + 3)

    label_font = QFont(p.font())
    label_font.setPointSizeF(max(8.0, size / 40))
    label_font.setWeight(QFont.DemiBold)
    fm = QFontMetrics(label_font)
    base = QColor(40, 44, 60, 228)
    empty_c = QColor(32, 35, 48, 150)
    accent = QColor(theme.ACCENT)

    for i, caption in enumerate(captions):
        h = highlights[i]
        qt_center = 90.0 - i * step
        outer = r_out + grow * h
        path = _sector_path(center, r_in, outer, qt_center - step / 2 + 0.9, step - 1.8)
        empty = not caption
        if empty:
            p.setBrush(empty_c)
        else:
            mid = math.radians(i * step)
            far = QPointF(center.x() + math.sin(mid) * outer, center.y() - math.cos(mid) * outer)
            grad = QLinearGradient(center, far)
            grad.setColorAt(0, _mix(base, QColor(theme.ACCENT_DEEP), h))
            grad.setColorAt(1, _mix(QColor(48, 53, 72, 232), accent, h))
            p.setBrush(grad)
        edge = _mix(QColor(70, 76, 102, 190), QColor(theme.ACCENT_2), h)
        p.setPen(QPen(edge, 1.2 + 0.8 * h))
        p.drawPath(path)

        mid = math.radians(i * step)
        r_mid = (r_in + outer) / 2
        cx = center.x() + math.sin(mid) * r_mid
        cy = center.y() - math.cos(mid) * r_mid
        p.setFont(label_font)
        if empty:
            p.setPen(QColor(theme.FAINT))
        else:
            p.setPen(_mix(QColor(theme.TEXT), QColor("white"), h))
        chord = 2 * r_mid * math.sin(math.radians(min(step, 120) / 2))
        max_w = int(min(chord * 0.9, (outer - r_in) * 1.25))
        lines = _elide_lines(caption or "—", fm, max_w)
        line_h = fm.height()
        top = cy - line_h * len(lines) / 2
        for k, line in enumerate(lines):
            p.drawText(QRectF(cx - max_w / 2, top + k * line_h, max_w, line_h), Qt.AlignCenter, line)

        num_font = QFont(label_font)
        num_font.setPointSizeF(label_font.pointSizeF() * 0.66)
        p.setFont(num_font)
        p.setPen(QColor(255, 255, 255, 90 + int(100 * h)))
        rn = outer - fm.height() * 0.5
        p.drawText(
            QRectF(center.x() + math.sin(mid) * rn - 12, center.y() - math.cos(mid) * rn - 9, 24, 18),
            Qt.AlignCenter,
            str(i + 1),
        )

    # hub
    hub_r = r_in - 6
    hub = QRadialGradient(center, hub_r)
    hub.setColorAt(0, QColor(30, 32, 44, 250))
    hub.setColorAt(1, QColor(20, 21, 30, 250))
    p.setPen(QPen(QColor(theme.BORDER_2), 1.4))
    p.setBrush(hub)
    p.drawEllipse(center, hub_r, hub_r)
    art = _wheel_art() if not center_text else None
    if art is not None and not art.isNull():
        side = int(hub_r * 1.3)
        clip = QPainterPath()
        clip.addEllipse(center, hub_r - 4, hub_r - 4)
        p.save()
        p.setClipPath(clip)
        scaled = art.scaled(side, side, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        p.setOpacity(0.35)
        p.drawPixmap(int(center.x() - scaled.width() / 2), int(center.y() - scaled.height() / 2), scaled)
        p.restore()

    hub_w = int((hub_r - 8) * 1.7)
    body = QFont(p.font())
    body.setPointSizeF(max(8.0, size / 46))
    p.setFont(body)
    bfm = QFontMetrics(body)
    if center_text:
        body.setWeight(QFont.DemiBold)
        p.setFont(body)
        bfm = QFontMetrics(body)
        p.setPen(QColor("white"))
        lines = _elide_lines(center_text, bfm, hub_w, 3)
    else:
        p.setPen(QColor(theme.MUTED))
        lines = _elide_lines(title, bfm, hub_w, 3) if title else []
    top = center.y() - bfm.height() * len(lines) / 2
    for k, line in enumerate(lines):
        p.drawText(QRectF(center.x() - hub_w / 2, top + k * bfm.height(), hub_w, bfm.height()), Qt.AlignCenter, line)

    # direction pointer on the hub rim
    if pointer is not None:
        px, py = pointer
        length = math.hypot(px, py)
        if length > 1:
            reach = min(1.0, length / MAX_VECTOR) * (hub_r - 6)
            tip = QPointF(center.x() + px / length * reach, center.y() + py / length * reach)
            halo = QRadialGradient(tip, 12)
            halo.setColorAt(0, QColor(34, 211, 238, 150))
            halo.setColorAt(1, QColor(34, 211, 238, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(halo)
            p.drawEllipse(tip, 12, 12)
            p.setBrush(QColor(theme.ACCENT_2))
            p.drawEllipse(tip, 4.5, 4.5)


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
        self.captions: list[str] = []
        self.title = ""
        self.hint = ""
        self.scale_percent = 100
        self.deadzone = 40.0
        self.vector = (0.0, 0.0)
        self.selected = -1
        self.raw = RawMouse()
        self._hl: list[float] = []
        self._scale = 1.0
        self._intro = QVariantAnimation(self)
        self._intro.setDuration(140)
        self._intro.setStartValue(0.0)
        self._intro.setEndValue(1.0)
        self._intro.valueChanged.connect(self._on_intro)
        self._outro = QVariantAnimation(self)
        self._outro.setDuration(90)
        self._outro.setStartValue(1.0)
        self._outro.setEndValue(0.0)
        self._outro.valueChanged.connect(lambda v: self.setWindowOpacity(float(v)))
        self._outro.finished.connect(self.hide)
        self._ease = QTimer(self)  # runs only while the highlight is moving
        self._ease.setInterval(16)
        self._ease.timeout.connect(self._ease_step)

    def open(self, title: str, slots, deadzone: float, hint: str = "", captions: list[str] | None = None) -> None:
        self._outro.stop()
        self.slots = list(slots)
        self.captions = list(captions) if captions is not None else [s.caption for s in self.slots]
        self.title = title
        self.hint = hint
        self.deadzone = deadzone
        self.vector = (0.0, 0.0)
        self.selected = -1
        self._hl = [0.0] * len(self.slots)
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        geo = screen.geometry()
        side = int(min(geo.width(), geo.height()) * 0.52 * self.scale_percent / 100)
        side = max(300, min(side, int(min(geo.width(), geo.height()) * 0.9)))
        self.setGeometry(geo.center().x() - side // 2, geo.center().y() - side // 2, side, side)
        self.setWindowOpacity(0.0)
        self._scale = 0.88
        self.show()
        self.raise_()
        self.raw.start(int(self.winId()))
        self._intro.start()

    def close_animated(self) -> None:
        if not self.isVisible() or self._outro.state() == QVariantAnimation.Running:
            return
        self._intro.stop()
        self._ease.stop()
        self.raw.stop()
        self._outro.start()

    def _on_intro(self, value) -> None:
        t = float(value)
        eased = 1 - (1 - t) ** 3
        self.setWindowOpacity(eased)
        self._scale = 0.88 + 0.12 * eased
        self.update()

    def hideEvent(self, event) -> None:  # noqa: N802
        self.raw.stop()
        self._ease.stop()
        self._intro.stop()
        super().hideEvent(event)

    def add_delta(self, dx: float, dy: float) -> None:
        if not dx and not dy:
            return
        vx, vy = clamp_vector(self.vector[0] + dx, self.vector[1] + dy)
        self.vector = (vx, vy)
        idx = sector_for_vector(vx, vy, len(self.slots), self.deadzone)
        if idx >= 0 and not (self.captions[idx] and self.slots[idx].filled):
            idx = -1  # empty slot = cancel
        if idx != self.selected:
            self.selected = idx
            if self.isVisible() and not self._ease.isActive():
                self._ease.start()
            elif not self.isVisible():  # no animation to watch
                self._hl = [1.0 if i == idx else 0.0 for i in range(len(self.slots))]
        self.update()

    def _ease_step(self) -> None:
        moving = False
        for i, h in enumerate(self._hl):
            target = 1.0 if i == self.selected else 0.0
            nh = h + (target - h) * 0.35
            if abs(nh - target) < 0.02:
                nh = target
            else:
                moving = True
            self._hl[i] = nh
        if not moving:
            self._ease.stop()
        self.update()

    def selected_slot(self):
        if 0 <= self.selected < len(self.slots):
            slot = self.slots[self.selected]
            return slot if slot.filled else None
        return None

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        slot = self.selected_slot()
        center = (self.captions[self.selected] if slot.sound_id else slot.text.strip() or self.captions[self.selected]) if slot else ""
        hint = f"{self.title} — {self.hint}" if self.hint else self.title
        paint_wheel(
            p,
            QRectF(self.rect()),
            self.captions,
            self.selected,
            title=hint,
            center_text=center,
            pointer=self.vector,
            highlights=self._hl,
            scale=self._scale,
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
