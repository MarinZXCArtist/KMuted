"""Holds the game's push-to-talk key while KMuted is speaking."""

from __future__ import annotations

import logging
import sys

from kmuted.hotkeys.keys import NAME_TO_VK, parse_combo

log = logging.getLogger(__name__)

_PYNPUT_KEY_NAMES = {
    "ctrl": "ctrl_l",
    "shift": "shift_l",
    "alt": "alt_l",
    "win": "cmd",
    "pageup": "page_up",
    "pagedown": "page_down",
    "capslock": "caps_lock",
    "numlock": "num_lock",
    "scrolllock": "scroll_lock",
    "printscreen": "print_screen",
}


class PushToTalk:
    def __init__(self) -> None:
        self._key_name = ""
        self._target = None
        self._is_mouse = False
        self._down = False
        self._kb = None
        self._mouse = None

    @property
    def key_name(self) -> str:
        return self._key_name

    @property
    def enabled(self) -> bool:
        return self._target is not None

    @property
    def is_down(self) -> bool:
        return self._down

    def set_key(self, combo: str) -> None:
        self.release()
        parsed = parse_combo(combo or "")
        self._key_name = parsed[1] if parsed else ""
        self._target = None
        if not self._key_name:
            return
        try:
            self._target, self._is_mouse = self._resolve(self._key_name)
        except Exception as exc:
            log.warning("push-to-talk key %s unavailable: %s", self._key_name, exc)
            self._target = None

    @staticmethod
    def _resolve(name: str):
        from pynput import keyboard, mouse

        if name.startswith("mouse"):
            button = {"mouse3": mouse.Button.middle, "mouse4": mouse.Button.x1, "mouse5": mouse.Button.x2}[name]
            return button, True
        if sys.platform == "win32" and name in NAME_TO_VK:
            return keyboard.KeyCode.from_vk(NAME_TO_VK[name]), False
        if len(name) == 1:
            return keyboard.KeyCode.from_char(name), False
        return getattr(keyboard.Key, _PYNPUT_KEY_NAMES.get(name, name)), False

    def press(self) -> None:
        if self._target is None or self._down:
            return
        try:
            self._controller().press(self._target)
            self._down = True
        except Exception:
            log.exception("push-to-talk press failed")

    def release(self) -> None:
        if not self._down:
            return
        self._down = False
        try:
            self._controller().release(self._target)
        except Exception:
            log.exception("push-to-talk release failed")

    def _controller(self):
        if self._is_mouse:
            if self._mouse is None:
                from pynput import mouse

                self._mouse = mouse.Controller()
            return self._mouse
        if self._kb is None:
            from pynput import keyboard

            self._kb = keyboard.Controller()
        return self._kb
