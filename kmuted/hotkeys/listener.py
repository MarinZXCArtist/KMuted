"""System-wide hotkeys (works while a game or Discord has focus).

Built on pynput's low-level hooks. Keys are *not* suppressed: the game
still sees them, so prefer combos or mouse side buttons it doesn't use.

Callbacks fire on the hook threads; the app forwards them to the Qt
thread with signals. Callbacks must be quick — a slow low-level hook
makes Windows drop it.
"""

from __future__ import annotations

import logging
import sys
import threading
from typing import Callable, Iterable

from kmuted.hotkeys.keys import (
    MODIFIERS,
    make_combo,
    name_from_pynput_button,
    name_from_pynput_key,
)

log = logging.getLogger(__name__)

_IS_WINDOWS = sys.platform == "win32"


class _WinApi:
    """Tiny ctypes helpers used from inside the hooks."""

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        self._ctypes = ctypes
        self._point = wintypes.POINT
        self._user32 = ctypes.windll.user32

    def cursor_pos(self) -> tuple[int, int] | None:
        pt = self._point()
        if self._user32.GetCursorPos(self._ctypes.byref(pt)):
            return pt.x, pt.y
        return None

    def modifiers_down(self) -> set[str]:
        state = self._user32.GetAsyncKeyState
        mods = set()
        if state(0x11) & 0x8000:
            mods.add("ctrl")
        if state(0x10) & 0x8000:
            mods.add("shift")
        if state(0x12) & 0x8000:
            mods.add("alt")
        if (state(0x5B) | state(0x5C)) & 0x8000:
            mods.add("win")
        return mods


class GlobalHotkeys:
    """Tracks pressed keys and reports bound combos being pressed/released.

    ``on_press(combo)`` fires when the main key of a bound combo goes down
    with exactly that set of modifiers. ``on_release(combo)`` fires when
    that main key goes up (used for hold-to-open wheels).
    """

    def __init__(
        self,
        on_press: Callable[[str], None],
        on_release: Callable[[str], None],
    ) -> None:
        self._on_press = on_press
        self._on_release = on_release
        self._lock = threading.Lock()
        self._bindings: frozenset[str] = frozenset()
        self._pressed: set[str] = set()
        self._active: dict[str, str] = {}  # main key -> combo it triggered
        self._ignored_injected: set[str] = set()
        self._track_mouse = False
        self._mouse_delta = [0.0, 0.0]
        self._last_mouse: tuple[int, int] | None = None
        self._kb_listener = None
        self._mouse_listener = None
        self._win = _WinApi() if _IS_WINDOWS else None
        self.error: str = ""

    # --- lifecycle ---------------------------------------------------------

    def start(self) -> bool:
        try:
            from pynput import keyboard, mouse
        except Exception as exc:  # no X server, unsupported platform...
            self.error = f"Глобальные горячие клавиши недоступны: {exc}"
            log.warning(self.error)
            return False
        try:
            self._kb_listener = keyboard.Listener(on_press=self._kb_press, on_release=self._kb_release)
            self._mouse_listener = mouse.Listener(on_click=self._mouse_click, on_move=self._mouse_move)
            self._kb_listener.daemon = True
            self._mouse_listener.daemon = True
            self._kb_listener.start()
            self._mouse_listener.start()
        except Exception as exc:
            self.error = f"Не удалось запустить перехват клавиш: {exc}"
            log.exception("hotkey listener failed")
            self.stop()
            return False
        self.error = ""
        return True

    def stop(self) -> None:
        for listener in (self._kb_listener, self._mouse_listener):
            if listener is not None:
                try:
                    listener.stop()
                except Exception:
                    pass
        self._kb_listener = self._mouse_listener = None

    @property
    def running(self) -> bool:
        return self._kb_listener is not None

    # --- configuration -----------------------------------------------------

    def set_bindings(self, combos: Iterable[str]) -> None:
        with self._lock:
            self._bindings = frozenset(c for c in combos if c)

    def ignore_injected(self, names: Iterable[str]) -> None:
        """Skip synthetic events for these keys (our own push-to-talk presses)."""
        with self._lock:
            self._ignored_injected = set(names)

    def set_mouse_tracking(self, enabled: bool) -> None:
        with self._lock:
            self._track_mouse = enabled
            self._mouse_delta = [0.0, 0.0]
            self._last_mouse = None

    def take_mouse_delta(self) -> tuple[float, float]:
        with self._lock:
            dx, dy = self._mouse_delta
            self._mouse_delta = [0.0, 0.0]
        return dx, dy

    # --- event core (also driven directly by tests) ------------------------

    def key_down(self, name: str | None) -> None:
        if not name:
            return
        with self._lock:
            if name in self._pressed:  # auto-repeat
                return
            self._pressed.add(name)
            if name in MODIFIERS and not self._bound_as_key(name):
                return
            mods = self._current_modifiers()
            combo = make_combo(mods, name)
            if combo not in self._bindings:
                return
            self._active[name] = combo
        self._safe(self._on_press, combo)

    def key_up(self, name: str | None) -> None:
        if not name:
            return
        with self._lock:
            self._pressed.discard(name)
            combo = self._active.pop(name, None)
        if combo:
            self._safe(self._on_release, combo)

    def _bound_as_key(self, name: str) -> bool:
        return name in self._bindings

    def _current_modifiers(self) -> set[str]:
        if self._win is not None:
            try:
                return self._win.modifiers_down()
            except Exception:
                pass
        return {m for m in MODIFIERS if m in self._pressed}

    @staticmethod
    def _safe(fn: Callable[[str], None], combo: str) -> None:
        try:
            fn(combo)
        except Exception:
            log.exception("hotkey callback failed")

    # --- pynput callbacks ----------------------------------------------------

    def _skip_injected(self, name: str | None, injected: bool) -> bool:
        return injected and name in self._ignored_injected

    def _kb_press(self, key, injected: bool = False) -> None:
        name = name_from_pynput_key(key)
        if not self._skip_injected(name, injected):
            self.key_down(name)

    def _kb_release(self, key, injected: bool = False) -> None:
        name = name_from_pynput_key(key)
        if not self._skip_injected(name, injected):
            self.key_up(name)

    def _mouse_click(self, x, y, button, pressed, injected: bool = False) -> None:
        name = name_from_pynput_button(button)
        if name is None or self._skip_injected(name, injected):
            return
        if pressed:
            self.key_down(name)
        else:
            self.key_up(name)

    def _mouse_move(self, x, y, injected: bool = False) -> None:
        if not self._track_mouse or injected:
            return
        # Games re-center a hidden cursor every frame, so consecutive
        # positions are meaningless. Inside the Windows hook the cursor has
        # not moved yet, so "new point - current cursor" is the real delta.
        origin = None
        if self._win is not None:
            try:
                origin = self._win.cursor_pos()
            except Exception:
                origin = None
        with self._lock:
            if origin is None:
                origin = self._last_mouse
                self._last_mouse = (x, y)
            if origin is not None:
                self._mouse_delta[0] += x - origin[0]
                self._mouse_delta[1] += y - origin[1]
