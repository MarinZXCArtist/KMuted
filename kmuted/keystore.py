"""Protect API keys at rest.

On Windows keys are encrypted with DPAPI (bound to the Windows user
account), so a copied config.json is useless on another PC/account.
Elsewhere they are stored as is (marked ``plain:``).
"""

from __future__ import annotations

import base64
import logging
import sys

log = logging.getLogger(__name__)

_PREFIX_DPAPI = "dpapi:"
_PREFIX_PLAIN = "plain:"

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    _crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32")
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]

    def _call(fn, data: bytes) -> bytes:
        buf = ctypes.create_string_buffer(data, len(data))  # must outlive the call
        src = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
        out = _Blob()
        if not fn(ctypes.byref(src), None, None, None, None, 0, ctypes.byref(out)):
            raise OSError(ctypes.get_last_error() or "DPAPI failed")
        try:
            return ctypes.string_at(out.pbData, out.cbData)
        finally:
            _kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))


def protect(value: str) -> str:
    if not value:
        return ""
    if sys.platform == "win32":
        try:
            raw = _call(_crypt32.CryptProtectData, value.encode("utf-8"))
            return _PREFIX_DPAPI + base64.b64encode(raw).decode("ascii")
        except Exception:
            log.warning("DPAPI protect failed; storing key unencrypted")
    return _PREFIX_PLAIN + value


def unprotect(value: str) -> str:
    if not value:
        return ""
    if value.startswith(_PREFIX_PLAIN):
        return value[len(_PREFIX_PLAIN):]
    if value.startswith(_PREFIX_DPAPI):
        if sys.platform != "win32":
            return ""
        try:
            raw = base64.b64decode(value[len(_PREFIX_DPAPI):])
            return _call(_crypt32.CryptUnprotectData, raw).decode("utf-8")
        except Exception:
            log.warning("could not decrypt an API key (other Windows user?)")
            return ""
    return value  # typed by hand into config.json


def mask(value: str) -> str:
    """``sk-abc…xyz`` for display."""
    if len(value) <= 8:
        return "•" * len(value)
    return f"{value[:4]}…{value[-4:]}"
