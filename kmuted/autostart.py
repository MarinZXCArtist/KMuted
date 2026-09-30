"""Start KMuted with Windows (per-user Run key)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_NAME = "KMuted"


def command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimized'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{exe}" -m kmuted --minimized'


def is_enabled() -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, _NAME)
            return True
    except OSError:
        return False


def set_enabled(enabled: bool) -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            if enabled:
                winreg.SetValueEx(key, _NAME, 0, winreg.REG_SZ, command())
            else:
                try:
                    winreg.DeleteValue(key, _NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        log.exception("autostart registry update failed")
        return False
