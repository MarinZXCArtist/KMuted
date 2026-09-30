"""Relative mouse movement via Windows Raw Input.

Shooters hide the cursor and lock it in place, so cursor coordinates say
nothing about where the player moves the mouse. Raw Input reports the
physical movement itself; with ``RIDEV_INPUTSINK`` we get it while the
game keeps focus. Used only while the phrase wheel is open.
"""

from __future__ import annotations

import ctypes
import logging
import sys

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"

WM_INPUT = 0x00FF
RID_INPUT = 0x10000003
RIM_TYPEMOUSE = 0
RIDEV_REMOVE = 0x00000001
RIDEV_INPUTSINK = 0x00000100
MOUSE_MOVE_ABSOLUTE = 0x01

if IS_WINDOWS:
    from ctypes import wintypes

    class RAWINPUTDEVICE(ctypes.Structure):
        _fields_ = [
            ("usUsagePage", wintypes.USHORT),
            ("usUsage", wintypes.USHORT),
            ("dwFlags", wintypes.DWORD),
            ("hwndTarget", wintypes.HWND),
        ]

    class RAWINPUTHEADER(ctypes.Structure):
        _fields_ = [
            ("dwType", wintypes.DWORD),
            ("dwSize", wintypes.DWORD),
            ("hDevice", wintypes.HANDLE),
            ("wParam", wintypes.WPARAM),
        ]

    class RAWMOUSE(ctypes.Structure):
        _fields_ = [
            ("usFlags", wintypes.USHORT),
            ("ulButtons", wintypes.ULONG),  # union of ulButtons / (usButtonFlags, usButtonData)
            ("ulRawButtons", wintypes.ULONG),
            ("lLastX", wintypes.LONG),
            ("lLastY", wintypes.LONG),
            ("ulExtraInformation", wintypes.ULONG),
        ]

    class _RAWDATA(ctypes.Union):
        _fields_ = [("mouse", RAWMOUSE), ("_pad", ctypes.c_byte * 64)]

    class RAWINPUT(ctypes.Structure):
        _fields_ = [("header", RAWINPUTHEADER), ("data", _RAWDATA)]

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _user32.RegisterRawInputDevices.argtypes = [ctypes.POINTER(RAWINPUTDEVICE), wintypes.UINT, wintypes.UINT]
    _user32.RegisterRawInputDevices.restype = wintypes.BOOL
    _user32.GetRawInputData.argtypes = [
        wintypes.HANDLE,
        wintypes.UINT,
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.UINT),
        wintypes.UINT,
    ]
    _user32.GetRawInputData.restype = wintypes.UINT


class RawMouse(QAbstractNativeEventFilter):
    """Accumulates relative mouse motion while started (Windows only)."""

    def __init__(self) -> None:
        super().__init__()
        self._dx = 0
        self._dy = 0
        self._installed = False
        self.active = False
        self.relative_seen = False  # False on tablets/RDP (absolute devices)

    def start(self, hwnd: int) -> bool:
        self._dx = self._dy = 0
        self.relative_seen = False
        if not IS_WINDOWS or not hwnd:
            return False
        device = RAWINPUTDEVICE(0x01, 0x02, RIDEV_INPUTSINK, hwnd)  # generic desktop / mouse
        if not _user32.RegisterRawInputDevices(ctypes.byref(device), 1, ctypes.sizeof(device)):
            log.warning("RegisterRawInputDevices failed: %s", ctypes.get_last_error())
            return False
        if not self._installed:
            QCoreApplication.instance().installNativeEventFilter(self)
            self._installed = True
        self.active = True
        return True

    def stop(self) -> None:
        if not (IS_WINDOWS and self.active):
            return
        self.active = False
        device = RAWINPUTDEVICE(0x01, 0x02, RIDEV_REMOVE, None)
        _user32.RegisterRawInputDevices(ctypes.byref(device), 1, ctypes.sizeof(device))

    def take_delta(self) -> tuple[int, int]:
        dx, dy = self._dx, self._dy
        self._dx = self._dy = 0
        return dx, dy

    def nativeEventFilter(self, event_type, message):  # noqa: N802 - Qt API
        if self.active and bytes(event_type) == b"windows_generic_MSG":
            try:
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_INPUT:
                    self._read(msg.lParam)
            except Exception:
                log.debug("raw input parse failed", exc_info=True)
        return False, 0

    def _read(self, handle) -> None:
        data = RAWINPUT()
        size = wintypes.UINT(ctypes.sizeof(data))
        got = _user32.GetRawInputData(handle, RID_INPUT, ctypes.byref(data), ctypes.byref(size), ctypes.sizeof(RAWINPUTHEADER))
        if got in (0, 0xFFFFFFFF) or data.header.dwType != RIM_TYPEMOUSE:
            return
        mouse = data.data.mouse
        if mouse.usFlags & MOUSE_MOVE_ABSOLUTE:
            return
        self.relative_seen = True
        self._dx += mouse.lLastX
        self._dy += mouse.lLastY
