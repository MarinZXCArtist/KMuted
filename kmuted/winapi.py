"""Windows focus helpers for the overlays (no-ops on other systems).

Windows won't let a background app take keyboard focus just like that.
The typing overlay needs it, so we attach to the foreground thread's input
queue for a moment — the standard workaround used by launchers.
"""

from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    _user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    _user32.BringWindowToTop.argtypes = [wintypes.HWND]
    _user32.SetFocus.argtypes = [wintypes.HWND]
    _user32.IsWindow.argtypes = [wintypes.HWND]
    _user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_void_p]

_VK_MENU = 0x12
_KEYEVENTF_KEYUP = 0x0002
_SW_SHOW = 5


def foreground_window() -> int:
    if not IS_WINDOWS:
        return 0
    return int(_user32.GetForegroundWindow() or 0)


def force_foreground(hwnd: int) -> bool:
    """Bring ``hwnd`` to the front and give it keyboard focus."""
    if not IS_WINDOWS or not hwnd:
        return False
    try:
        if _user32.SetForegroundWindow(hwnd) and foreground_window() == hwnd:
            return True
        fg = _user32.GetForegroundWindow()
        fg_thread = _user32.GetWindowThreadProcessId(fg, None) if fg else 0
        our_thread = _kernel32.GetCurrentThreadId()
        attached = bool(fg_thread and fg_thread != our_thread and _user32.AttachThreadInput(fg_thread, our_thread, True))
        try:
            _user32.ShowWindow(hwnd, _SW_SHOW)
            _user32.BringWindowToTop(hwnd)
            _user32.SetForegroundWindow(hwnd)
            _user32.SetFocus(hwnd)
        finally:
            if attached:
                _user32.AttachThreadInput(fg_thread, our_thread, False)
        if foreground_window() == hwnd:
            return True
        # Last resort: a synthetic Alt tap unlocks SetForegroundWindow.
        _user32.keybd_event(_VK_MENU, 0, 0, None)
        _user32.keybd_event(_VK_MENU, 0, _KEYEVENTF_KEYUP, None)
        _user32.SetForegroundWindow(hwnd)
        return foreground_window() == hwnd
    except Exception:
        log.exception("force_foreground failed")
        return False


def restore_foreground(hwnd: int) -> None:
    if IS_WINDOWS and hwnd and _user32.IsWindow(hwnd):
        try:
            _user32.SetForegroundWindow(hwnd)
        except Exception:
            pass
