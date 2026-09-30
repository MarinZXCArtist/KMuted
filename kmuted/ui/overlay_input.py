"""Text box that pops up in the middle of the screen: type, Enter — it's said."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from kmuted import winapi
from kmuted.ui import theme
from kmuted.ui.icons import render_logo

MAX_CHARS = 500

_PANEL_QSS = f"""
QFrame#overlayPanel {{
    background: rgba(22, 23, 31, 245);
    border: 1px solid {theme.ACCENT};
    border-radius: 16px;
}}
QFrame#overlayPanel QLabel {{ background: transparent; }}
QLabel#ovTitle {{ font-size: 11pt; font-weight: 600; color: {theme.TEXT}; }}
QLabel#ovVoice {{
    background: rgba(124, 92, 255, 0.22);
    border: 1px solid rgba(124, 92, 255, 0.6);
    border-radius: 10px;
    padding: 2px 10px;
    color: {theme.TEXT};
}}
QLabel#ovHint {{ color: {theme.MUTED}; font-size: 9pt; }}
QLineEdit#ovEdit {{
    background: {theme.SURFACE_2};
    border: 1px solid {theme.BORDER};
    border-radius: 10px;
    padding: 10px 14px;
    font-size: 15pt;
    color: {theme.TEXT};
}}
QLineEdit#ovEdit:focus {{ border: 1px solid {theme.ACCENT_2}; }}
"""


class InputOverlay(QWidget):
    submitted = Signal(str, bool)  # text, keep_open
    cycle_voice = Signal(int)
    closed = Signal()

    def __init__(self) -> None:
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("KMuted")
        self.setStyleSheet(_PANEL_QSS)
        self._history: list[str] = []
        self._history_pos = -1
        self._draft = ""
        self._prev_hwnd = 0
        self._was_active = False
        self.restore_focus = True
        self.keep_open = False

        panel = QFrame()
        panel.setObjectName("overlayPanel")
        shadow = QGraphicsDropShadowEffect(panel)
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 180))
        panel.setGraphicsEffect(shadow)

        logo = QLabel()
        logo.setPixmap(render_logo(22))
        title = QLabel("Сказать в войс")
        title.setObjectName("ovTitle")
        self.voice_label = QLabel()
        self.voice_label.setObjectName("ovVoice")
        self.voice_label.setToolTip("Tab — сменить голос")
        header = QHBoxLayout()
        header.setSpacing(8)
        header.addWidget(logo)
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.voice_label)

        self.edit = QLineEdit()
        self.edit.setObjectName("ovEdit")
        self.edit.setMaxLength(MAX_CHARS)
        self.edit.setPlaceholderText("Напишите, что сказать…")
        self.edit.installEventFilter(self)
        self.edit.textChanged.connect(self._update_counter)

        self.hint = QLabel()
        self.hint.setObjectName("ovHint")
        self.counter = QLabel()
        self.counter.setObjectName("ovHint")
        footer = QHBoxLayout()
        footer.addWidget(self.hint, 1)
        footer.addWidget(self.counter)

        inner = QVBoxLayout(panel)
        inner.setContentsMargins(18, 14, 18, 12)
        inner.setSpacing(10)
        inner.addLayout(header)
        inner.addWidget(self.edit)
        inner.addLayout(footer)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.addWidget(panel)
        self.resize(760, 190)
        self._update_hint()
        self._update_counter()

    # --- public ------------------------------------------------------------

    def open(self, voice_name: str, history: list[str]) -> None:
        if self.isVisible():  # hotkey pressed again: just take focus back
            self._grab_focus()
            return
        self._prev_hwnd = winapi.foreground_window()
        self._history = list(history)
        self._history_pos = -1
        self._was_active = False
        self.set_voice_name(voice_name)
        self._update_hint()
        self.edit.clear()

        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        self.move(geo.center().x() - self.width() // 2, geo.center().y() - self.height() // 2 - geo.height() // 10)
        self.show()
        self._grab_focus()
        # Some games fight back for focus right after the hotkey; retry once.
        QTimer.singleShot(80, self._grab_focus)

    def set_voice_name(self, name: str) -> None:
        self.voice_label.setText(f"🗣 {name}")

    def close_overlay(self, restore: bool = True) -> None:
        if not self.isVisible():
            return
        self.hide()
        if restore and self.restore_focus:
            winapi.restore_foreground(self._prev_hwnd)
        self.closed.emit()

    # --- internals ---------------------------------------------------------

    def _grab_focus(self) -> None:
        if not self.isVisible():
            return
        self.raise_()
        self.activateWindow()
        winapi.force_foreground(int(self.winId()))
        self.edit.setFocus(Qt.ActiveWindowFocusReason)

    def _update_hint(self) -> None:
        enter = "Enter — сказать" + ("" if self.keep_open else " и закрыть")
        self.hint.setText(f"{enter}  ·  Shift+Enter — сказать и продолжить  ·  ↑↓ история  ·  Tab голос  ·  Esc закрыть")

    def _update_counter(self) -> None:
        self.counter.setText(f"{len(self.edit.text())}/{MAX_CHARS}")

    def _submit(self, keep_open: bool) -> None:
        text = self.edit.text().strip()
        if text:
            self.submitted.emit(text, keep_open)
            if text in self._history:
                self._history.remove(text)
            self._history.insert(0, text)
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
