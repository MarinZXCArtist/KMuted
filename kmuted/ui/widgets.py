"""Reusable widgets."""

from __future__ import annotations

import sys
import threading
import weakref
from typing import Any, Callable

from PySide6.QtCore import QObject, QRectF, Qt, Signal, Slot
from PySide6.QtGui import QFont, QPainter
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from kmuted.hotkeys.keys import MODIFIERS, VK_NAMES, format_combo, make_combo
from kmuted.ui.components import combo_parts, icon_button, page_header, paint_keycaps  # noqa: F401
from kmuted.i18n import tr

# --- background work ---------------------------------------------------------


class _Relay(QObject):
    finished = Signal(object, object)

    def __init__(self, callback: Callable[[Any, BaseException | None], None]) -> None:
        super().__init__()
        self._callback = callback
        self.finished.connect(self._deliver, Qt.QueuedConnection)

    @Slot(object, object)
    def _deliver(self, result, error) -> None:
        try:
            self._callback(result, error)
        finally:
            _RELAYS.discard(self)
            self.deleteLater()


_RELAYS: set[_Relay] = set()


def run_in_background(fn: Callable[[], Any], on_done: Callable[[Any, BaseException | None], None]) -> None:
    """Run ``fn`` in a thread, then call ``on_done(result, error)`` in the UI thread."""
    relay = _Relay(on_done)
    _RELAYS.add(relay)

    def worker() -> None:
        try:
            result, error = fn(), None
        except BaseException as exc:  # noqa: BLE001 - reported to the UI
            result, error = None, exc
        relay.finished.emit(result, error)

    threading.Thread(target=worker, daemon=True).start()


# --- hotkey capture ------------------------------------------------------------

_QT_KEY_NAMES: dict[int, str] = {}


def _build_qt_key_names() -> None:
    k = Qt.Key
    for i in range(26):
        _QT_KEY_NAMES[int(k.Key_A) + i] = chr(ord("a") + i)
    for i in range(10):
        _QT_KEY_NAMES[int(k.Key_0) + i] = str(i)
    for i in range(24):
        _QT_KEY_NAMES[int(k.Key_F1) + i] = f"f{i + 1}"
    simple = {
        k.Key_Space: "space",
        k.Key_Return: "enter",
        k.Key_Enter: "enter",
        k.Key_Tab: "tab",
        k.Key_Backspace: "backspace",
        k.Key_Insert: "insert",
        k.Key_Delete: "delete",
        k.Key_Home: "home",
        k.Key_End: "end",
        k.Key_PageUp: "pageup",
        k.Key_PageDown: "pagedown",
        k.Key_Up: "up",
        k.Key_Down: "down",
        k.Key_Left: "left",
        k.Key_Right: "right",
        k.Key_CapsLock: "capslock",
        k.Key_NumLock: "numlock",
        k.Key_ScrollLock: "scrolllock",
        k.Key_Print: "printscreen",
        k.Key_Pause: "pause",
        k.Key_Menu: "menu",
        k.Key_Minus: "minus",
        k.Key_Equal: "equals",
        k.Key_Comma: "comma",
        k.Key_Period: "period",
        k.Key_Slash: "slash",
        k.Key_Backslash: "backslash",
        k.Key_Semicolon: "semicolon",
        k.Key_Apostrophe: "quote",
        k.Key_QuoteLeft: "grave",
        k.Key_BracketLeft: "lbracket",
        k.Key_BracketRight: "rbracket",
        k.Key_Control: "ctrl",
        k.Key_Shift: "shift",
        k.Key_Alt: "alt",
        k.Key_AltGr: "alt",
        k.Key_Meta: "win",
        k.Key_MediaPlay: "media_play",
        k.Key_MediaTogglePlayPause: "media_play",
        k.Key_MediaNext: "media_next",
        k.Key_MediaPrevious: "media_prev",
        k.Key_MediaStop: "media_stop",
    }
    for key, name in simple.items():
        _QT_KEY_NAMES[int(key)] = name


_build_qt_key_names()
_KEYPAD = {
    int(Qt.Key.Key_Asterisk): "nummul",
    int(Qt.Key.Key_Plus): "numadd",
    int(Qt.Key.Key_Minus): "numsub",
    int(Qt.Key.Key_Period): "numdec",
    int(Qt.Key.Key_Comma): "numdec",
    int(Qt.Key.Key_Slash): "numdiv",
}


def key_name_from_event(event) -> str | None:
    """Canonical key name for a QKeyEvent (layout-independent on Windows)."""
    if sys.platform == "win32":
        vk = event.nativeVirtualKey()
        if vk in VK_NAMES:
            return VK_NAMES[vk]
    key = int(event.key())
    if event.modifiers() & Qt.KeypadModifier:
        if int(Qt.Key.Key_0) <= key <= int(Qt.Key.Key_9):
            return f"num{key - int(Qt.Key.Key_0)}"
        if key in _KEYPAD:
            return _KEYPAD[key]
    return _QT_KEY_NAMES.get(key)


def modifiers_from_qt(mods) -> set[str]:
    out = set()
    if mods & Qt.ControlModifier:
        out.add("ctrl")
    if mods & Qt.ShiftModifier:
        out.add("shift")
    if mods & Qt.AltModifier:
        out.add("alt")
    if mods & Qt.MetaModifier:
        out.add("win")
    return out


class _KeycapButton(QPushButton):
    """Button that shows its combo as keyboard keycaps."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        f = QFont(self.font())
        f.setPointSizeF(8.8)
        f.setWeight(QFont.DemiBold)
        self._cap_font = f

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if not self.parts or self.text():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        paint_keycaps(p, QRectF(self.rect()).adjusted(8, 3, -8, -4), self.parts, self._cap_font)
        p.end()


class HotkeyEdit(QWidget):
    """Click, then press a key combo (or a mouse side button) to bind it.

    ``single_key`` mode records just one key (modifiers allowed alone) —
    used for the push-to-talk key.
    """

    changed = Signal(str)
    _instances: "weakref.WeakSet[HotkeyEdit]" = weakref.WeakSet()

    @classmethod
    def any_capturing(cls) -> bool:
        """True while some editor listens (global hotkeys pause meanwhile)."""
        alive = []
        for edit in list(cls._instances):
            try:
                alive.append(edit._capturing and edit.isVisible())
            except RuntimeError:  # widget already deleted
                continue
        return any(alive)

    def __init__(self, combo: str = "", single_key: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        HotkeyEdit._instances.add(self)
        self._combo = combo
        self._single = single_key
        self._capturing = False
        self._pending_mod: str | None = None

        self.button = _KeycapButton()
        self.button.setObjectName("hotkey")
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.setMinimumWidth(170)
        self.button.setToolTip(tr("Нажмите и затем нужную клавишу или сочетание (можно боковые кнопки мыши)"))
        self.button.clicked.connect(self.start_capture)
        self.button.installEventFilter(self)

        self.clear_btn = icon_button("x", tr("Убрать горячую клавишу"), size=14)
        self.clear_btn.clicked.connect(lambda: self.set_combo("", emit=True))

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(self.button, 1)
        lay.addWidget(self.clear_btn)
        self._refresh()

    def combo(self) -> str:
        return self._combo

    def set_combo(self, combo: str, emit: bool = False) -> None:
        self._stop_capture()
        self._combo = combo
        self._refresh()
        if emit:
            self.changed.emit(combo)

    def _refresh(self) -> None:
        self.button.setProperty("capturing", self._capturing)
        self.button.style().unpolish(self.button)
        self.button.style().polish(self.button)
        if self._capturing:
            prefix = format_combo(self._pending_mod) + " + …" if self._pending_mod else ""
            self.button.parts = []
            self.button.setText(prefix or tr("Нажмите клавишу…  (Esc — отмена)"))
        else:
            self.button.parts = combo_parts(self._combo)
            self.button.setText("" if self.button.parts else tr("Не назначено"))
        self.button.update()
        self.clear_btn.setVisible(bool(self._combo))

    # --- capture -----------------------------------------------------------

    def start_capture(self) -> None:
        if self._capturing:
            return
        self._capturing = True
        self._pending_mod = None
        self.button.setFocus()
        self.button.grabKeyboard()
        self.button.grabMouse()
        self._refresh()

    def _stop_capture(self) -> None:
        if not self._capturing:
            return
        self._capturing = False
        self._pending_mod = None
        self.button.releaseKeyboard()
        self.button.releaseMouse()
        self._refresh()

    def _commit(self, combo: str) -> None:
        self._stop_capture()
        if combo != self._combo:
            self._combo = combo
            self._refresh()
            self.changed.emit(combo)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt API
        if obj is not self.button or not self._capturing:
            return super().eventFilter(obj, event)
        etype = event.type()
        if etype == event.Type.KeyPress:
            self._on_key_press(event)
            return True
        if etype == event.Type.KeyRelease:
            self._on_key_release(event)
            return True
        if etype == event.Type.MouseButtonPress:
            self._on_mouse(event)
            return True
        if etype in (event.Type.MouseButtonRelease, event.Type.MouseButtonDblClick):
            return True
        if etype == event.Type.FocusOut:
            self._stop_capture()
        return super().eventFilter(obj, event)

    def _on_key_press(self, event) -> None:
        if event.isAutoRepeat():
            return
        name = key_name_from_event(event)
        if name == "esc" and not event.modifiers() & ~Qt.KeypadModifier:
            self._stop_capture()
            return
        if name is None:
            return
        mods = modifiers_from_qt(event.modifiers())
        if name in MODIFIERS:
            self._pending_mod = make_combo(mods, name) if not self._single else name
            self._refresh()
            return
        self._commit(name if self._single else make_combo(mods, name))

    def _on_key_release(self, event) -> None:
        if event.isAutoRepeat():
            return
        name = key_name_from_event(event)
        # a lone modifier released: accept it in single-key mode
        if self._single and name in MODIFIERS and self._pending_mod == name:
            self._commit(name)

    def _on_mouse(self, event) -> None:
        button = event.button()
        names = {
            Qt.MiddleButton: "mouse3",
            Qt.BackButton: "mouse4",
            Qt.ForwardButton: "mouse5",
        }
        if button in names:
            mods = set() if self._single else modifiers_from_qt(event.modifiers())
            self._commit(make_combo(mods, names[button]))
        else:
            self._stop_capture()


# --- small layout helpers --------------------------------------------------


class ValueSlider(QWidget):
    """Horizontal slider with a live value label."""

    valueChanged = Signal(int)  # noqa: N815 - mirror Qt naming

    def __init__(self, lo: int, hi: int, value: int, fmt: Callable[[int], str] = str, parent=None) -> None:
        super().__init__(parent)
        self._fmt = fmt
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(lo, hi)
        self.slider.setValue(value)
        self.label = QLabel(fmt(value))
        self.label.setMinimumWidth(64)
        self.label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.label)
        self.slider.valueChanged.connect(self._changed)

    def _changed(self, value: int) -> None:
        self.label.setText(self._fmt(value))
        self.valueChanged.emit(value)

    def value(self) -> int:
        return self.slider.value()

    def setValue(self, value: int) -> None:  # noqa: N802
        self.slider.setValue(value)


class InfoBox(QFrame):
    def __init__(self, html: str, kind: str = "info", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName(kind)
        self.label = QLabel(html)
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.RichText)
        self.label.setOpenExternalLinks(True)
        self.label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.addWidget(self.label)

    def set_html(self, html: str) -> None:
        self.label.setText(html)


def fill_voice_combo(combo: QComboBox, voices, current_id: str, include_default: bool = True) -> None:
    """Fill a combo with voice profiles; item data = profile id ("" = default)."""
    combo.blockSignals(True)
    combo.clear()
    if include_default:
        combo.addItem(tr("Голос по умолчанию"), "")
    for v in voices:
        combo.addItem(v.name, v.id)
    idx = combo.findData(current_id)
    combo.setCurrentIndex(max(0, idx))
    combo.blockSignals(False)
