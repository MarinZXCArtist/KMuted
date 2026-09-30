"""Canonical key names and hotkey combos.

A combo is stored as a lowercase string: modifiers in a fixed order, then
one main key, joined with ``+`` — e.g. ``"ctrl+shift+f1"``, ``"mouse5"``,
``"alt+numadd"``. Names never contain ``+`` themselves, so parsing is a
plain split.

Windows virtual-key codes are the source of truth: both the global hook
(pynput) and the hotkey editor (Qt ``nativeVirtualKey``) report them, so
a combo recorded in the UI matches what the hook later sees regardless of
keyboard layout.
"""

from __future__ import annotations

import sys

MODIFIERS = ("ctrl", "shift", "alt", "win")
MOUSE_BUTTONS = ("mouse3", "mouse4", "mouse5")

# Windows virtual-key code -> canonical name
VK_NAMES: dict[int, str] = {
    0x08: "backspace",
    0x09: "tab",
    0x0C: "clear",
    0x0D: "enter",
    0x10: "shift",
    0x11: "ctrl",
    0x12: "alt",
    0x13: "pause",
    0x14: "capslock",
    0x1B: "esc",
    0x20: "space",
    0x21: "pageup",
    0x22: "pagedown",
    0x23: "end",
    0x24: "home",
    0x25: "left",
    0x26: "up",
    0x27: "right",
    0x28: "down",
    0x2C: "printscreen",
    0x2D: "insert",
    0x2E: "delete",
    0x5B: "win",
    0x5C: "win",
    0x5D: "menu",
    0x6A: "nummul",
    0x6B: "numadd",
    0x6D: "numsub",
    0x6E: "numdec",
    0x6F: "numdiv",
    0x90: "numlock",
    0x91: "scrolllock",
    0xA0: "shift",
    0xA1: "shift",
    0xA2: "ctrl",
    0xA3: "ctrl",
    0xA4: "alt",
    0xA5: "alt",
    0xAD: "volume_mute",
    0xAE: "volume_down",
    0xAF: "volume_up",
    0xB0: "media_next",
    0xB1: "media_prev",
    0xB2: "media_stop",
    0xB3: "media_play",
    0xBA: "semicolon",
    0xBB: "equals",
    0xBC: "comma",
    0xBD: "minus",
    0xBE: "period",
    0xBF: "slash",
    0xC0: "grave",
    0xDB: "lbracket",
    0xDC: "backslash",
    0xDD: "rbracket",
    0xDE: "quote",
    0xE2: "oem102",
}
VK_NAMES.update({0x30 + i: str(i) for i in range(10)})
VK_NAMES.update({0x41 + i: chr(ord("a") + i) for i in range(26)})
VK_NAMES.update({0x60 + i: f"num{i}" for i in range(10)})
VK_NAMES.update({0x70 + i: f"f{i + 1}" for i in range(24)})

# canonical name -> preferred Windows vk (used to simulate push-to-talk)
NAME_TO_VK: dict[str, int] = {}
for _vk, _name in VK_NAMES.items():
    NAME_TO_VK.setdefault(_name, _vk)
NAME_TO_VK.update({"shift": 0xA0, "ctrl": 0xA2, "alt": 0xA4, "win": 0x5B})

_DISPLAY = {
    "ctrl": "Ctrl",
    "shift": "Shift",
    "alt": "Alt",
    "win": "Win",
    "esc": "Esc",
    "enter": "Enter",
    "space": "Пробел",
    "backspace": "Backspace",
    "tab": "Tab",
    "capslock": "CapsLock",
    "pageup": "PgUp",
    "pagedown": "PgDn",
    "printscreen": "PrtSc",
    "scrolllock": "ScrollLock",
    "numlock": "NumLock",
    "insert": "Ins",
    "delete": "Del",
    "home": "Home",
    "end": "End",
    "up": "↑",
    "down": "↓",
    "left": "←",
    "right": "→",
    "menu": "Menu",
    "pause": "Pause",
    "nummul": "Num *",
    "numadd": "Num +",
    "numsub": "Num -",
    "numdec": "Num .",
    "numdiv": "Num /",
    "semicolon": ";",
    "equals": "=",
    "comma": ",",
    "minus": "-",
    "period": ".",
    "slash": "/",
    "grave": "`",
    "lbracket": "[",
    "rbracket": "]",
    "backslash": "\\",
    "quote": "'",
    "mouse3": "Колесо мыши (клик)",
    "mouse4": "Мышь 4 (назад)",
    "mouse5": "Мышь 5 (вперёд)",
    "media_play": "Play/Pause",
    "media_next": "Next track",
    "media_prev": "Prev track",
    "media_stop": "Stop",
}

# aliases accepted when parsing hand-written combos
_ALIASES = {
    "control": "ctrl",
    "ctl": "ctrl",
    "lctrl": "ctrl",
    "rctrl": "ctrl",
    "lshift": "shift",
    "rshift": "shift",
    "lalt": "alt",
    "ralt": "alt",
    "altgr": "alt",
    "meta": "win",
    "cmd": "win",
    "super": "win",
    "return": "enter",
    "escape": "esc",
    "del": "delete",
    "ins": "insert",
    "pgup": "pageup",
    "pgdn": "pagedown",
    "caps": "capslock",
    "xbutton1": "mouse4",
    "xbutton2": "mouse5",
    "middle": "mouse3",
    "mbutton": "mouse3",
}

KNOWN_KEYS = set(VK_NAMES.values()) | set(MOUSE_BUTTONS)


def canonical_key(name: str) -> str:
    name = name.strip().lower().replace(" ", "")
    return _ALIASES.get(name, name)


def parse_combo(combo: str) -> tuple[frozenset[str], str] | None:
    """``"Ctrl+Shift+F1"`` -> (``{"ctrl", "shift"}``, ``"f1"``); None if invalid."""
    if not combo:
        return None
    parts = [canonical_key(p) for p in combo.split("+") if p.strip()]
    if not parts:
        return None
    mods = [p for p in parts if p in MODIFIERS]
    keys = [p for p in parts if p not in MODIFIERS]
    if len(keys) > 1:
        return None
    if not keys:
        # a lone modifier is a valid *key* (e.g. push-to-talk on Alt)
        if len(mods) == 1:
            return frozenset(), mods[0]
        return None
    main = keys[0]
    if main not in KNOWN_KEYS:
        return None
    return frozenset(mods), main


def make_combo(mods: frozenset[str] | set[str], key: str) -> str:
    ordered = [m for m in MODIFIERS if m in mods and m != key]
    return "+".join(ordered + [key])


def normalize_combo(combo: str) -> str:
    parsed = parse_combo(combo or "")
    if parsed is None:
        return ""
    return make_combo(*parsed)


def key_display(name: str) -> str:
    if name in _DISPLAY:
        return _DISPLAY[name]
    if name.startswith("num") and name[3:].isdigit():
        return f"Num {name[3:]}"
    return name.upper() if len(name) <= 3 else name.capitalize()


def format_combo(combo: str) -> str:
    """Human readable form: ``"ctrl+shift+f1"`` -> ``"Ctrl + Shift + F1"``."""
    parsed = parse_combo(combo or "")
    if parsed is None:
        return ""
    mods, key = parsed
    ordered = [m for m in MODIFIERS if m in mods]
    return " + ".join(key_display(k) for k in ordered + [key])


# --- pynput adapters --------------------------------------------------------

# pynput ``Key`` enum member name -> canonical name (non-Windows fallback)
_PYNPUT_SPECIAL = {
    "ctrl": "ctrl",
    "ctrl_l": "ctrl",
    "ctrl_r": "ctrl",
    "shift": "shift",
    "shift_l": "shift",
    "shift_r": "shift",
    "alt": "alt",
    "alt_l": "alt",
    "alt_r": "alt",
    "alt_gr": "alt",
    "cmd": "win",
    "cmd_l": "win",
    "cmd_r": "win",
    "enter": "enter",
    "esc": "esc",
    "tab": "tab",
    "space": "space",
    "backspace": "backspace",
    "delete": "delete",
    "insert": "insert",
    "home": "home",
    "end": "end",
    "page_up": "pageup",
    "page_down": "pagedown",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "caps_lock": "capslock",
    "num_lock": "numlock",
    "scroll_lock": "scrolllock",
    "print_screen": "printscreen",
    "pause": "pause",
    "menu": "menu",
    "media_play_pause": "media_play",
    "media_next": "media_next",
    "media_previous": "media_prev",
    "media_volume_mute": "volume_mute",
    "media_volume_down": "volume_down",
    "media_volume_up": "volume_up",
}
_PYNPUT_SPECIAL.update({f"f{i}": f"f{i}" for i in range(1, 25)})

_CHAR_NAMES = {
    ";": "semicolon",
    "=": "equals",
    ",": "comma",
    "-": "minus",
    ".": "period",
    "/": "slash",
    "`": "grave",
    "[": "lbracket",
    "]": "rbracket",
    "\\": "backslash",
    "'": "quote",
    " ": "space",
}


def name_from_pynput_key(key: object, windows: bool | None = None) -> str | None:
    """Canonical name for a pynput ``Key``/``KeyCode`` (duck-typed)."""
    if windows is None:
        windows = sys.platform == "win32"
    value = getattr(key, "value", None)  # Key enum member -> KeyCode
    keycode = value if value is not None and hasattr(value, "vk") else key
    vk = getattr(keycode, "vk", None)
    if windows and vk is not None and vk in VK_NAMES:
        return VK_NAMES[vk]
    enum_name = getattr(key, "name", None)
    if value is not None and enum_name:
        return _PYNPUT_SPECIAL.get(enum_name)
    char = getattr(keycode, "char", None)
    if char:
        char = char.lower()
        if char.isascii() and char.isalnum() and len(char) == 1:
            return char
        return _CHAR_NAMES.get(char)
    if vk is not None and 0xFFB0 <= vk <= 0xFFB9:  # X11 keypad digits
        return f"num{vk - 0xFFB0}"
    return None


def name_from_pynput_button(button: object) -> str | None:
    return {"middle": "mouse3", "x1": "mouse4", "x2": "mouse5"}.get(getattr(button, "name", ""))
