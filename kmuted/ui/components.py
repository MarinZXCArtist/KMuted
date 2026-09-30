"""Custom painted, lightly animated building blocks.

Animations are short (≤ 250 ms) and timers only run while something is
actually moving, so the app idles at ~0 % CPU.
"""

from __future__ import annotations

import math
import random

from PySide6.QtCore import (
    QEasingCurve,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from kmuted.hotkeys.keys import MODIFIERS, key_display, parse_combo
from kmuted.ui import theme
from kmuted.ui.icons import icon, icon_pixmap
from kmuted.i18n import tr

# --- buttons -------------------------------------------------------------------------


def make_button(text: str = "", icon_name: str | None = None, kind: str = "", tooltip: str = "") -> QPushButton:
    btn = QPushButton(text)
    if kind:
        btn.setObjectName(kind)
    if icon_name:
        color = "white" if kind == "primary" else (theme.DANGER if kind == "danger" else theme.TEXT)
        btn.setIcon(icon(icon_name, color, 16))
        btn.setIconSize(QSize(16, 16))
    if tooltip:
        btn.setToolTip(tooltip)
    btn.setCursor(Qt.PointingHandCursor)
    return btn


def icon_button(icon_name: str, tooltip: str = "", color: str = theme.MUTED, size: int = 16) -> QToolButton:
    btn = QToolButton()
    btn.setObjectName("ghost")
    btn.setIcon(icon(icon_name, color, size, hover_color=theme.TEXT))
    btn.setIconSize(QSize(size, size))
    btn.setToolTip(tooltip)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setStyleSheet("padding: 6px;")
    return btn


# --- toggle switch ---------------------------------------------------------------------


class ToggleSwitch(QAbstractButton):
    """iOS/Windows 11 style switch with a sliding knob."""

    def __init__(self, checked: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(44, 24)
        self._pos = 1.0 if checked else 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)
        self.toggled.connect(self._animate)

    def _on_anim(self, value) -> None:
        self._pos = float(value)
        self.update()

    def _animate(self, checked: bool) -> None:
        self._anim.stop()
        if not self.isVisible():  # nothing to watch: jump straight there
            self._pos = 1.0 if checked else 0.0
            self.update()
            return
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def showEvent(self, event) -> None:  # noqa: N802
        # state may have changed with signals blocked while hidden
        self._pos = 1.0 if self.isChecked() else 0.0
        super().showEvent(event)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(44, 24)

    def paintEvent(self, _event) -> None:  # noqa: N802
        if self._anim.state() != QVariantAnimation.Running:
            self._pos = 1.0 if self.isChecked() else 0.0  # e.g. set with signals blocked
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        off = QColor(theme.SURFACE_3)
        on = QColor(theme.ACCENT)
        t = self._pos
        track = QColor(
            round(off.red() + (on.red() - off.red()) * t),
            round(off.green() + (on.green() - off.green()) * t),
            round(off.blue() + (on.blue() - off.blue()) * t),
        )
        if not self.isEnabled():
            track.setAlpha(110)
        p.setPen(QPen(QColor(theme.BORDER_2) if t < 0.5 else track, 1))
        p.setBrush(track)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 6
        x = r.left() + 3 + (r.width() - d - 6) * t
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("white") if self.isEnabled() else QColor(theme.FAINT))
        p.drawEllipse(QRectF(x, r.top() + 3, d, d))
        p.end()


# --- keycaps ---------------------------------------------------------------------------


def combo_parts(combo: str) -> list[str]:
    parsed = parse_combo(combo or "")
    if parsed is None:
        return []
    mods, key = parsed
    return [key_display(m) for m in MODIFIERS if m in mods] + [key_display(key)]


def paint_keycaps(p: QPainter, rect: QRectF, parts: list[str], font: QFont, align_left: bool = True, dim: bool = False) -> float:
    """Draw ``[Ctrl] + [F1]`` style caps; returns the width used."""
    fm = QFontMetrics(font)
    p.setFont(font)
    h = min(rect.height(), fm.height() + 8)
    widths = [max(h, fm.horizontalAdvance(t) + 14) for t in parts]
    plus_w = fm.horizontalAdvance("+") + 8
    total = sum(widths) + plus_w * max(0, len(parts) - 1)
    x = rect.left() if align_left else rect.right() - total
    y = rect.center().y() - h / 2
    for i, (text, w) in enumerate(zip(parts, widths, strict=True)):
        cap = QRectF(x, y, w, h)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 90))
        p.drawRoundedRect(cap.translated(0, 2), 6, 6)
        grad = QLinearGradient(cap.topLeft(), cap.bottomLeft())
        grad.setColorAt(0, QColor("#353a52"))
        grad.setColorAt(1, QColor("#2a2e42"))
        p.setBrush(grad)
        p.setPen(QPen(QColor("#474d6b"), 1))
        p.drawRoundedRect(cap, 6, 6)
        p.setPen(QColor(theme.MUTED if dim else theme.TEXT))
        p.drawText(cap, Qt.AlignCenter, text)
        x += w
        if i < len(parts) - 1:
            p.setPen(QColor(theme.FAINT))
            p.drawText(QRectF(x, y, plus_w, h), Qt.AlignCenter, "+")
            x += plus_w
    return total


class Keycaps(QWidget):
    def __init__(self, combo: str = "", empty_text: str = "", parent=None) -> None:
        super().__init__(parent)
        self._parts: list[str] = []
        self._empty = empty_text
        f = QFont(self.font())
        f.setPointSizeF(8.8)
        f.setWeight(QFont.DemiBold)
        self._font = f
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.set_combo(combo)

    def set_combo(self, combo: str) -> None:
        self._parts = combo_parts(combo)
        fm = QFontMetrics(self._font)
        if self._parts:
            h = fm.height() + 8
            w = sum(max(h, fm.horizontalAdvance(t) + 14) for t in self._parts)
            w += (fm.horizontalAdvance("+") + 8) * (len(self._parts) - 1)
        else:
            w = fm.horizontalAdvance(self._empty) + 4
        self.setFixedSize(int(w) + 2, fm.height() + 12)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self._parts:
            paint_keycaps(p, QRectF(self.rect()).adjusted(0, 0, 0, -2), self._parts, self._font)
        elif self._empty:
            p.setPen(QColor(theme.FAINT))
            p.setFont(self._font)
            p.drawText(self.rect(), Qt.AlignVCenter | Qt.AlignLeft, self._empty)
        p.end()


# --- cards & rows ----------------------------------------------------------------------


def card(object_name: str = "card") -> QFrame:
    frame = QFrame()
    frame.setObjectName(object_name)
    return frame


def divider() -> QFrame:
    line = QFrame()
    line.setObjectName("divider")
    return line


class IconBadge(QLabel):
    """Rounded square with an icon — used at the start of setting rows."""

    def __init__(self, icon_name: str, color: str = theme.ACCENT, size: int = 36) -> None:
        super().__init__()
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        self.setPixmap(icon_pixmap(icon_name, color, int(size * 0.5)))
        c = QColor(color)
        self.setStyleSheet(
            f"background: rgba({c.red()},{c.green()},{c.blue()},0.14);"
            f"border: 1px solid rgba({c.red()},{c.green()},{c.blue()},0.35); border-radius: {size // 3}px;"
        )


class SettingRow(QFrame):
    """[icon] Title / subtitle ............ [control] — Windows 11 settings style."""

    def __init__(self, title: str, subtitle: str = "", control: QWidget | None = None, icon_name: str | None = None) -> None:
        super().__init__()
        self.setObjectName("cardHover")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(14)
        if icon_name:
            lay.addWidget(IconBadge(icon_name))
        text = QVBoxLayout()
        text.setSpacing(2)
        self.title = QLabel(title)
        self.title.setObjectName("h3")
        text.addWidget(self.title)
        self.subtitle = QLabel(subtitle)
        self.subtitle.setObjectName("hint")
        self.subtitle.setWordWrap(True)
        self.subtitle.setVisible(bool(subtitle))
        text.addWidget(self.subtitle)
        lay.addLayout(text, 1)
        if control is not None:
            lay.addWidget(control, 0, Qt.AlignVCenter)
        self.control = control


class SectionTitle(QLabel):
    def __init__(self, text: str) -> None:
        super().__init__(text.upper())
        self.setObjectName("eyebrow")
        self.setContentsMargins(4, 14, 0, 2)


def page_header(title: str, subtitle: str = "", right: QWidget | None = None) -> QWidget:
    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 8)
    col = QVBoxLayout()
    col.setSpacing(4)
    h = QLabel(title)
    h.setObjectName("h1")
    col.addWidget(h)
    if subtitle:
        s = QLabel(subtitle)
        s.setObjectName("muted")
        s.setWordWrap(True)
        col.addWidget(s)
    row.addLayout(col, 1)
    if right is not None:
        row.addWidget(right, 0, Qt.AlignBottom)
    return box


class EmptyState(QWidget):
    def __init__(self, icon_name: str, title: str, text: str, action: QWidget | None = None) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 40, 20, 40)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignCenter)
        pic = QLabel()
        pic.setPixmap(icon_pixmap(icon_name, theme.ACCENT, 44, 1.6))
        pic.setAlignment(Qt.AlignCenter)
        t = QLabel(title)
        t.setObjectName("h2")
        t.setAlignment(Qt.AlignCenter)
        d = QLabel(text)
        d.setObjectName("muted")
        d.setAlignment(Qt.AlignCenter)
        d.setWordWrap(True)
        lay.addWidget(pic)
        lay.addWidget(t)
        lay.addWidget(d)
        if action is not None:
            lay.addWidget(action, 0, Qt.AlignCenter)


# --- equalizer ("on air") ------------------------------------------------------------


class Equalizer(QWidget):
    """Little bouncing bars; the timer runs only while active."""

    def __init__(self, bars: int = 5, parent=None) -> None:
        super().__init__(parent)
        self._levels = [0.2] * bars
        self._targets = [0.2] * bars
        self._active = False
        self._timer = QTimer(self)
        self._timer.setInterval(55)
        self._timer.timeout.connect(self._step)
        self.setFixedSize(6 * bars + 2, 18)

    def set_active(self, active: bool) -> None:
        self._active = active
        if active and not self._timer.isActive():
            self._timer.start()
        self.update()

    def _step(self) -> None:
        done = True
        for i, level in enumerate(self._levels):
            if self._active and random.random() < 0.35:
                self._targets[i] = random.uniform(0.25, 1.0)
            elif not self._active:
                self._targets[i] = 0.2
            self._levels[i] = level + (self._targets[i] - level) * 0.45
            done &= abs(self._levels[i] - self._targets[i]) < 0.02
        if not self._active and done:
            self._timer.stop()
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        h = self.height()
        for i, level in enumerate(self._levels):
            bh = max(3.0, level * h)
            grad = QLinearGradient(0, h, 0, 0)
            grad.setColorAt(0, QColor(theme.ACCENT))
            grad.setColorAt(1, QColor(theme.ACCENT_2))
            p.setPen(Qt.NoPen)
            p.setBrush(grad if self._active else QColor(theme.FAINT))
            p.drawRoundedRect(QRectF(1 + i * 6, (h - bh) / 2, 4, bh), 2, 2)
        p.end()


class StatusDot(QWidget):
    """Colored dot with a soft pulsing halo (pulse only when ``pulse``)."""

    def __init__(self, color: str = theme.SUCCESS, parent=None) -> None:
        super().__init__(parent)
        self._color = QColor(color)
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)
        self.setFixedSize(14, 14)

    def set_state(self, color: str, pulse: bool = False) -> None:
        self._color = QColor(color)
        if pulse and not self._timer.isActive():
            self._timer.start()
        elif not pulse:
            self._timer.stop()
            self._phase = 0.0
        self.update()

    def _tick(self) -> None:
        self._phase = (self._phase + 0.06) % 1.0
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QRectF(self.rect()).center()
        if self._timer.isActive():
            halo = QColor(self._color)
            halo.setAlphaF(0.45 * (1 - self._phase))
            p.setPen(Qt.NoPen)
            p.setBrush(halo)
            r = 3 + 4 * self._phase
            p.drawEllipse(c, r, r)
        p.setPen(Qt.NoPen)
        p.setBrush(self._color)
        p.drawEllipse(c, 3.5, 3.5)
        p.end()


# --- navigation ------------------------------------------------------------------------


class NavButton(QAbstractButton):
    def __init__(self, icon_name: str, text: str, parent=None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.icon_name = icon_name
        self.label = text
        self.badge = ""
        self.setFixedHeight(42)
        self._hover = False

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0, 2, 0, -2)
        if self._hover and not self.isChecked():
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 12))
            p.drawRoundedRect(r, 10, 10)
        color = "white" if self.isChecked() else (theme.TEXT if self._hover else theme.MUTED)
        p.drawPixmap(QRectF(16, r.center().y() - 9, 18, 18).toRect(), icon_pixmap(self.icon_name, color, 18))
        f = QFont(self.font())
        f.setPointSizeF(10.5)
        f.setWeight(QFont.DemiBold if self.isChecked() else QFont.Medium)
        p.setFont(f)
        p.setPen(QColor(color))
        p.drawText(QRectF(46, r.top(), r.width() - 56, r.height()), Qt.AlignVCenter | Qt.AlignLeft, self.label)
        if self.badge:
            bw = QFontMetrics(f).horizontalAdvance(self.badge) + 12
            br = QRectF(r.right() - bw - 10, r.center().y() - 9, bw, 18)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.WARNING))
            p.drawRoundedRect(br, 9, 9)
            p.setPen(QColor("#1b1405"))
            p.drawText(br, Qt.AlignCenter, self.badge)
        p.end()


class NavBar(QWidget):
    """Vertical navigation with a gradient pill that glides to the selection."""

    currentChanged = Signal(int)  # noqa: N815

    def __init__(self, items: list[tuple[str, str]], parent=None) -> None:
        super().__init__(parent)
        self._pill = QWidget(self)
        self._pill.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._pill.setStyleSheet(
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {theme.ACCENT}, stop:1 {theme.BLUE});"
            "border-radius: 10px;"
        )
        self._pill.lower()
        self.buttons: list[NavButton] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(2)
        for i, (icon_name, text) in enumerate(items):
            btn = NavButton(icon_name, text, self)
            btn.clicked.connect(lambda _c=False, idx=i: self.set_current(idx))
            lay.addWidget(btn)
            self.buttons.append(btn)
        self._current = -1
        self._anim = QPropertyAnimation(self._pill, b"geometry", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def current(self) -> int:
        return self._current

    def set_current(self, index: int, animate: bool = True) -> None:
        if not 0 <= index < len(self.buttons):
            return
        changed = index != self._current
        self._current = index
        for i, b in enumerate(self.buttons):
            b.setChecked(i == index)
        target = self._pill_rect(index)
        if animate and self._pill.isVisible() and self._pill.geometry().height() > 0:
            self._anim.stop()
            self._anim.setStartValue(self._pill.geometry())
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self._pill.setGeometry(target)
        if changed:
            self.currentChanged.emit(index)

    def _pill_rect(self, index: int) -> QRect:
        g = self.buttons[index].geometry()
        return QRect(g.left(), g.top() + 2, g.width(), g.height() - 4)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._current >= 0:
            self._anim.stop()
            QTimer.singleShot(0, lambda: self._pill.setGeometry(self._pill_rect(self._current)))

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self._current >= 0:
            QTimer.singleShot(0, lambda: self._pill.setGeometry(self._pill_rect(self._current)))


# --- page transitions ------------------------------------------------------------------


class FadeStack(QStackedWidget):
    """QStackedWidget that fades + slides the new page in (~180 ms)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._group: QParallelAnimationGroup | None = None

    def fade_to(self, index: int) -> None:
        if index == self.currentIndex() or not 0 <= index < self.count():
            return
        if self._group is not None:
            self._group.stop()
            self._cleanup()
        self.setCurrentIndex(index)
        page = self.currentWidget()
        if not self.isVisible():
            return
        effect = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(effect)
        fade = QPropertyAnimation(effect, b"opacity", self)
        fade.setDuration(180)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.OutCubic)
        end = page.pos()
        slide = QPropertyAnimation(page, b"pos", self)
        slide.setDuration(200)
        slide.setStartValue(end + QPoint(0, 14))
        slide.setEndValue(end)
        slide.setEasingCurve(QEasingCurve.OutCubic)
        group = QParallelAnimationGroup(self)
        group.addAnimation(fade)
        group.addAnimation(slide)
        group.finished.connect(self._cleanup)
        self._group = group
        self._page = page
        group.start()

    def _cleanup(self) -> None:
        # the opacity effect renders offscreen: drop it once we're done
        page = getattr(self, "_page", None)
        if page is not None:
            page.setGraphicsEffect(None)
            page.move(0, 0)
        self._group = None


# --- toasts ----------------------------------------------------------------------------


class Toast(QFrame):
    """Small notification that slides in at the bottom-right of ``host``."""

    _ICONS = {"info": "info", "success": "check", "error": "alert", "warning": "alert"}

    @staticmethod
    def _color(kind: str) -> str:
        return {"success": theme.SUCCESS, "error": theme.DANGER, "warning": theme.WARNING}.get(kind, theme.ACCENT)

    def __init__(self, host: QWidget, text: str, kind: str = "info", timeout_ms: int = 3800) -> None:
        super().__init__(host)
        color = self._color(kind)
        self.setObjectName("toast")
        c = QColor(color)
        self.setStyleSheet(
            f"QFrame#toast {{ background: {theme.SURFACE_2}; border: 1px solid rgba({c.red()},{c.green()},{c.blue()},0.55);"
            " border-radius: 12px; }"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 10, 10)
        lay.setSpacing(10)
        pic = QLabel()
        pic.setPixmap(icon_pixmap(self._ICONS.get(kind, "info"), color, 18))
        label = QLabel(text)
        label.setWordWrap(True)
        label.setMaximumWidth(360)
        close = icon_button("x", tr("Закрыть"), size=14)
        close.clicked.connect(self.dismiss)
        lay.addWidget(pic, 0, Qt.AlignTop)
        lay.addWidget(label, 1)
        lay.addWidget(close, 0, Qt.AlignTop)
        self.adjustSize()
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
        self._timeout = timeout_ms
        self._closing = False

    def show_at(self, bottom_right: QPoint, offset: int) -> None:
        self.adjustSize()
        end = QPoint(bottom_right.x() - self.width(), bottom_right.y() - self.height() - offset)
        self.move(end + QPoint(24, 0))
        self.show()
        self.raise_()
        self._anim = QParallelAnimationGroup(self)
        move = QPropertyAnimation(self, b"pos")
        self._move_anim = move
        move.setDuration(220)
        move.setStartValue(end + QPoint(24, 0))
        move.setEndValue(end)
        move.setEasingCurve(QEasingCurve.OutCubic)
        fade = QPropertyAnimation(self._effect, b"opacity")
        fade.setDuration(220)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        self._anim.addAnimation(move)
        self._anim.addAnimation(fade)
        self._anim.start()
        self._timer.start(self._timeout)

    def retarget(self, pos: QPoint) -> None:
        """Move to ``pos`` — also if the slide-in animation is still running."""
        anim = getattr(self, "_move_anim", None)
        if anim is not None and anim.state() == QPropertyAnimation.Running:
            anim.setEndValue(pos)
        else:
            self.move(pos)

    def dismiss(self) -> None:
        if self._closing:
            return
        self._closing = True
        fade = QPropertyAnimation(self._effect, b"opacity", self)
        fade.setDuration(160)
        fade.setStartValue(self._effect.opacity())
        fade.setEndValue(0.0)
        fade.finished.connect(self.deleteLater)
        fade.start()
        self._fade = fade


class ToastHost:
    """Stacks toasts for one window."""

    MAX = 3

    def __init__(self, window: QWidget) -> None:
        self.window = window
        self.toasts: list[Toast] = []
        self._last: tuple[str, float] | None = None

    def show(self, text: str, kind: str = "info") -> None:
        import time

        now = time.monotonic()
        if self._last and self._last[0] == text and now - self._last[1] < 2.0:
            return  # identical message just shown
        self._last = (text, now)
        self.toasts = [t for t in self.toasts if _alive(t)]
        while len(self.toasts) >= self.MAX:
            self.toasts.pop(0).dismiss()
        toast = Toast(self.window, text, kind)
        toast.destroyed.connect(lambda *_: self._relayout())
        self.toasts.append(toast)
        self._relayout(new=toast)

    def _relayout(self, new: Toast | None = None) -> None:
        self.toasts = [t for t in self.toasts if _alive(t)]
        try:
            corner = QPoint(self.window.width() - 24, self.window.height() - 104)
        except RuntimeError:  # window already destroyed (app shutting down)
            return
        offset = 0
        for toast in reversed(self.toasts):
            toast.adjustSize()
            if toast is new:
                toast.show_at(corner, offset)
            else:
                toast.retarget(QPoint(corner.x() - toast.width(), corner.y() - toast.height() - offset))
            offset += toast.height() + 8


def _alive(widget: QWidget) -> bool:
    try:
        widget.objectName()
        return not getattr(widget, "_closing", False)
    except RuntimeError:  # C++ object already deleted
        return False


# --- misc painting helpers -------------------------------------------------------------


def rounded_path(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def ease_towards(value: float, target: float, factor: float = 0.3) -> float:
    return target if math.isclose(value, target, abs_tol=0.01) else value + (target - value) * factor


# --- level meter ---------------------------------------------------------------------


class LevelMeter(QWidget):
    """Horizontal VU bar (dB scale) with a falling peak marker."""

    FLOOR_DB = -60.0

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._level = 0.0  # 0..1 on the dB scale
        self._peak = 0.0
        self.setFixedHeight(12)
        self.setMinimumWidth(160)

    @classmethod
    def to_scale(cls, amplitude: float) -> float:
        if amplitude <= 1e-6:
            return 0.0
        db = 20.0 * math.log10(min(1.0, amplitude))
        return max(0.0, 1.0 - db / cls.FLOOR_DB)

    def push(self, amplitude: float) -> None:
        target = self.to_scale(amplitude)
        # fast attack, slow release
        self._level = target if target > self._level else self._level * 0.82 + target * 0.18
        self._peak = max(target, self._peak - 0.012)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.SURFACE_3))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        if self._level > 0.005:
            fill = QRectF(r.left(), r.top(), max(r.height(), r.width() * self._level), r.height())
            grad = QLinearGradient(r.left(), 0, r.right(), 0)
            grad.setColorAt(0.0, QColor(theme.SUCCESS))
            grad.setColorAt(0.7, QColor(theme.WARNING))
            grad.setColorAt(1.0, QColor(theme.DANGER))
            p.setBrush(grad)
            p.drawRoundedRect(fill, r.height() / 2, r.height() / 2)
        if self._peak > 0.01:
            x = r.left() + r.width() * self._peak
            p.setBrush(QColor("white"))
            p.drawRoundedRect(QRectF(x - 1.5, r.top(), 3, r.height()), 1.5, 1.5)
        p.end()
