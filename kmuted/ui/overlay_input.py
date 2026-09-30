"""Text box that pops up in the middle of the screen: type, Enter — it's said."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QEvent, QPoint, QRectF, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QConicalGradient, QCursor, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from kmuted import winapi
from kmuted.ui import theme
from kmuted.ui.components import Keycaps
from kmuted.ui.icons import render_logo

MAX_CHARS = 500
MARGIN = 26  # room for the painted shadow
RADIUS = 18

_QSS = f"""
QLabel {{ background: transparent; }}
QLabel#ovTitle {{ font-size: 11pt; font-weight: 700; color: {theme.TEXT}; }}
QLabel#ovVoice {{
    background: {theme.rgba(theme.ACCENT, 0.18)};
    border: 1px solid {theme.rgba(theme.ACCENT, 0.55)};
    border-radius: 11px; padding: 3px 11px; color: {theme.TEXT}; font-weight: 600;
}}
QLabel#ovHint {{ color: {theme.MUTED}; font-size: 9pt; }}
QLabel#ovSent {{ color: {theme.SUCCESS}; font-size: 9pt; font-weight: 700; }}
QLineEdit#ovEdit {{
    background: rgba(30, 33, 48, 235);
    border: 1px solid {theme.BORDER_2};
    border-radius: 12px;
    padding: 11px 16px;
    font-size: 15pt;
    color: {theme.TEXT};
    selection-background-color: {theme.ACCENT};
}}
QLineEdit#ovEdit:focus {{ border: 1px solid {theme.rgba(theme.ACCENT_2, 0.8)}; }}
"""


class InputOverlay(QWidget):
    submitted = Signal(str, bool)  # text, keep_open
    cycle_voice = Signal(int)
    closed = Signal()

    def __init__(self) -> None:
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("KMuted")
        self.setStyleSheet(_QSS)
        self._history: list[str] = []
        self._history_pos = -1
        self._draft = ""
        self._prev_hwnd = 0
        self._was_active = False
        self._restore_on_hide = True
        self.restore_focus = True
        self.keep_open = False
        self._angle = 0.0
        self._flash = 0.0
        self._target = QPoint()

        logo = QLabel()
        logo.setPixmap(render_logo(24))
        title = QLabel("Сказать в войс")
        title.setObjectName("ovTitle")
        self.voice_label = QLabel()
        self.voice_label.setObjectName("ovVoice")
        self.voice_label.setToolTip("Tab — сменить голос")
        esc = Keycaps("esc")
        esc.setToolTip("Закрыть")
        header = QHBoxLayout()
        header.setSpacing(10)
        header.addWidget(logo)
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.voice_label)
        header.addWidget(esc)

        self.edit = QLineEdit()
        self.edit.setObjectName("ovEdit")
        self.edit.setMaxLength(MAX_CHARS)
        self.edit.setPlaceholderText("Напишите, что сказать…")
        self.edit.installEventFilter(self)
        self.edit.textChanged.connect(self._update_counter)

        self.hint = QLabel()
        self.hint.setObjectName("ovHint")
        self.sent = QLabel("✓ Отправлено")
        self.sent.setObjectName("ovSent")
        self.sent.hide()
        self.counter = QLabel()
        self.counter.setObjectName("ovHint")
        footer = QHBoxLayout()
        footer.addWidget(self.hint, 1)
        footer.addWidget(self.sent)
        footer.addSpacing(10)
        footer.addWidget(self.counter)

        inner = QVBoxLayout()
        inner.setContentsMargins(20, 16, 20, 14)
        inner.setSpacing(12)
        inner.addLayout(header)
        inner.addWidget(self.edit)
        inner.addLayout(footer)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(MARGIN, MARGIN, MARGIN, MARGIN)
        outer.addLayout(inner)
        self.resize(820, 214)
        self._update_hint()
        self._update_counter()

        # animations: only alive while the box is on screen
        self._spin = QTimer(self)
        self._spin.setInterval(33)
        self._spin.timeout.connect(self._tick)
        self._appear = QVariantAnimation(self)
        self._appear.setDuration(170)
        self._appear.setStartValue(0.0)
        self._appear.setEndValue(1.0)
        self._appear.setEasingCurve(QEasingCurve.OutCubic)
        self._appear.valueChanged.connect(self._on_appear)
        self._vanish = QVariantAnimation(self)
        self._vanish.setDuration(100)
        self._vanish.setStartValue(1.0)
        self._vanish.setEndValue(0.0)
        self._vanish.valueChanged.connect(lambda v: self.setWindowOpacity(float(v)))
        self._vanish.finished.connect(self._finish_close)
        self._sent_timer = QTimer(self)
        self._sent_timer.setSingleShot(True)
        self._sent_timer.timeout.connect(self.sent.hide)

    # --- public ------------------------------------------------------------

    def open(self, voice_name: str, history: list[str]) -> None:
        if self.isVisible() and self._vanish.state() != QVariantAnimation.Running:
            self._grab_focus()  # hotkey pressed again: just take focus back
            return
        self._vanish.stop()
        if not self.isVisible():
            self._prev_hwnd = winapi.foreground_window()
        self._history = list(history)
        self._history_pos = -1
        self._was_active = False
        self.set_voice_name(voice_name)
        self._update_hint()
        self.edit.clear()
        self.sent.hide()

        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        self._target = QPoint(geo.center().x() - self.width() // 2, geo.center().y() - self.height() // 2 - geo.height() // 10)
        self.move(self._target + QPoint(0, 16))
        self.setWindowOpacity(0.0)
        self.show()
        self._spin.start()
        self._appear.start()
        self._grab_focus()
        # Some games fight back for focus right after the hotkey; retry once.
        QTimer.singleShot(90, self._grab_focus)

    def set_voice_name(self, name: str) -> None:
        self.voice_label.setText(name)

    def close_overlay(self, restore: bool = True) -> None:
        if not self.isVisible() or self._vanish.state() == QVariantAnimation.Running:
            return
        self._restore_on_hide = restore
        self._appear.stop()
        self._vanish.setStartValue(self.windowOpacity())
        self._vanish.start()

    # --- internals ---------------------------------------------------------

    def _finish_close(self) -> None:
        self.hide()
        self._spin.stop()
        self.setWindowOpacity(1.0)
        if self._restore_on_hide and self.restore_focus:
            winapi.restore_foreground(self._prev_hwnd)
        self.closed.emit()

    def _on_appear(self, value) -> None:
        t = float(value)
        self.setWindowOpacity(t)
        self.move(self._target + QPoint(0, round(16 * (1 - t))))

    def _tick(self) -> None:
        self._angle = (self._angle + 3.0) % 360.0
        if self._flash > 0:
            self._flash = max(0.0, self._flash - 0.08)
        self.update()

    def _grab_focus(self) -> None:
        if not self.isVisible():
            return
        self.raise_()
        self.activateWindow()
        winapi.force_foreground(int(self.winId()))
        self.edit.setFocus(Qt.ActiveWindowFocusReason)

    def _update_hint(self) -> None:
        enter = "Enter — сказать" + ("" if self.keep_open else " и закрыть")
        self.hint.setText(f"{enter}  ·  Shift+Enter — сказать и писать дальше  ·  ↑↓ история  ·  Tab — голос")

    def _update_counter(self) -> None:
        n = len(self.edit.text())
        self.counter.setText(f"{n}/{MAX_CHARS}")

    def _submit(self, keep_open: bool) -> None:
        text = self.edit.text().strip()
        if text:
            self.submitted.emit(text, keep_open)
            if text in self._history:
                self._history.remove(text)
            self._history.insert(0, text)
            self._flash = 1.0
            if keep_open:
                self.sent.show()
                self._sent_timer.start(1200)
        self._history_pos = -1
        self.edit.clear()
        if not keep_open:
            self.close_overlay()

    def _browse_history(self, step: int) -> None:
        if not self._history:
            return
        if self._history_pos == -1:
            self._draft = self.edit.text()
        pos = max(-1, min(len(self._history) - 1, self._history_pos + step))
        self._history_pos = pos
        self.edit.setText(self._draft if pos == -1 else self._history[pos])
        self.edit.end(False)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        panel = QRectF(self.rect()).adjusted(MARGIN, MARGIN, -MARGIN, -MARGIN)
        # cheap soft shadow: a few translucent rounded rects
        for i in range(8, 0, -1):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 10))
            p.drawRoundedRect(panel.adjusted(-i * 2, -i * 2 + 6, i * 2, i * 2 + 6), RADIUS + i * 2, RADIUS + i * 2)
        path = QPainterPath()
        path.addRoundedRect(panel, RADIUS, RADIUS)
        p.fillPath(path, QColor(18, 19, 27, 246))
        # rotating gradient rim
        rim = QConicalGradient(panel.center(), self._angle)
        a = QColor(theme.ACCENT)
        b = QColor(theme.ACCENT_2)
        c = QColor(theme.BLUE)
        glow = int(90 * self._flash)
        for col in (a, b, c):
            col.setAlpha(min(255, 200 + glow))
        rim.setColorAt(0.0, a)
        rim.setColorAt(0.33, b)
        rim.setColorAt(0.66, c)
        rim.setColorAt(1.0, a)
        p.setPen(QPen(rim, 1.6 + 1.4 * self._flash))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(panel.adjusted(0.8, 0.8, -0.8, -0.8), RADIUS, RADIUS)
        p.end()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self.edit and event.type() == QEvent.KeyPress:
            key = event.key()
            mods = event.modifiers()
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self._submit(keep_open=self.keep_open or bool(mods & Qt.ShiftModifier))
                return True
            if key == Qt.Key_Escape:
                self.close_overlay()
                return True
            if key == Qt.Key_Up:
                self._browse_history(+1)
                return True
            if key == Qt.Key_Down:
                self._browse_history(-1)
                return True
            if key == Qt.Key_Tab:
                self.cycle_voice.emit(+1)
                return True
            if key == Qt.Key_Backtab:
                self.cycle_voice.emit(-1)
                return True
        return super().eventFilter(obj, event)

    def changeEvent(self, event) -> None:  # noqa: N802
        if event.type() == QEvent.ActivationChange:
            if self.isActiveWindow():
                self._was_active = True
            elif self._was_active and self.isVisible():
                # user clicked/alt-tabbed elsewhere: get out of the way
                self.close_overlay(restore=False)
        super().changeEvent(event)
