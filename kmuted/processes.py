"""Which programs are running — for game profiles.

Windows: one ToolHelp snapshot (a few milliseconds, no extra packages).
Elsewhere (development): ``/proc``. Names are lower-case exe names.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"

# never offered in the "running programs" picker
_SYSTEM = {
    "explorer.exe", "textinputhost.exe", "applicationframehost.exe", "systemsettings.exe", "searchhost.exe",
    "startmenuexperiencehost.exe", "shellexperiencehost.exe", "lockapp.exe", "taskmgr.exe", "cmd.exe",
    "conhost.exe", "windowsterminal.exe", "powershell.exe", "pwsh.exe", "nvidia share.exe", "kmuted.exe",
    "python.exe", "pythonw.exe", "widgets.exe", "gamebar.exe", "rtkuwp.exe",
}

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _u32 = ctypes.WinDLL("user32", use_last_error=True)

    class _PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    _k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    _k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    _k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
    _k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _u32.GetForegroundWindow.restype = wintypes.HWND
    _u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _u32.IsWindowVisible.argtypes = [wintypes.HWND]
    _u32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    _u32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    _u32.EnumWindows.argtypes = [_WNDENUMPROC, wintypes.LPARAM]
    _INVALID_HANDLE = wintypes.HANDLE(-1).value


def process_table() -> dict[int, str]:
    """pid -> exe name (lower case)."""
    if IS_WINDOWS:
        return _win_table()
    return _proc_table()


def _win_table() -> dict[int, str]:
    table: dict[int, str] = {}
    snap = _k32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if not snap or snap == _INVALID_HANDLE:
        return table
    try:
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        ok = _k32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            table[int(entry.th32ProcessID)] = entry.szExeFile.lower()
            ok = _k32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        _k32.CloseHandle(snap)
    return table


def _proc_table() -> dict[int, str]:
    table: dict[int, str] = {}
    try:
        entries = os.listdir("/proc")
    except OSError:
        return table
    for name in entries:
        if not name.isdigit():
            continue
        try:
            table[int(name)] = Path("/proc", name, "comm").read_text(encoding="utf-8", errors="replace").strip().lower()
        except OSError:
            continue
    return table


def foreground_pid() -> int:
    if not IS_WINDOWS:
        return 0
    hwnd = _u32.GetForegroundWindow()
    if not hwnd:
        return 0
    pid = wintypes.DWORD(0)
    _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def snapshot() -> tuple[set[str], str]:
    """(names of running programs, name of the program in front)."""
    table = process_table()
    return set(table.values()), table.get(foreground_pid(), "")


def windowed_programs() -> list[tuple[str, str]]:
    """[(exe, window title)] of programs with a visible window, for the picker."""
    table = process_table()
    own = os.getpid()
    found: dict[str, str] = {}
    if IS_WINDOWS:
        titles: list[tuple[int, str]] = []

        def collect(hwnd, _lparam):
            try:
                if _u32.IsWindowVisible(hwnd):
                    length = _u32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        _u32.GetWindowTextW(hwnd, buf, length + 1)
                        pid = wintypes.DWORD(0)
                        _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                        titles.append((int(pid.value), buf.value))
            except Exception:
                pass
            return True

        _u32.EnumWindows(_WNDENUMPROC(collect), 0)
        for pid, title in titles:
            exe = table.get(pid, "")
            if exe and pid != own and exe not in _SYSTEM and exe not in found:
                found[exe] = title
    else:
        for pid, exe in table.items():
            if pid != own and exe and exe not in found:
                found[exe] = ""
    return sorted(found.items(), key=lambda item: item[0])


# Popular games: (name, exe names). Shown in "Add a game".
GAME_PRESETS: list[tuple[str, tuple[str, ...]]] = [
    ("Counter-Strike 2", ("cs2.exe",)),
    ("Dota 2", ("dota2.exe",)),
    ("Valorant", ("valorant-win64-shipping.exe",)),
    ("Fortnite", ("fortniteclient-win64-shipping.exe",)),
    ("Apex Legends", ("r5apex.exe", "r5apex_dx12.exe")),
    ("PUBG: Battlegrounds", ("tslgame.exe",)),
    ("Rust", ("rustclient.exe",)),
    ("GTA V", ("gta5.exe", "gta5_enhanced.exe")),
    ("League of Legends", ("league of legends.exe",)),
    ("Overwatch 2", ("overwatch.exe",)),
    ("Rainbow Six Siege", ("rainbowsix.exe", "rainbowsix_vulkan.exe")),
    ("Escape from Tarkov", ("escapefromtarkov.exe",)),
    ("Marvel Rivals", ("marvel-win64-shipping.exe",)),
    ("Call of Duty", ("cod.exe",)),
    ("Deadlock", ("project8.exe",)),
    ("Rocket League", ("rocketleague.exe",)),
    ("Minecraft", ("javaw.exe", "minecraft.windows.exe")),
    ("Roblox", ("robloxplayerbeta.exe",)),
    ("World of Tanks", ("worldoftanks.exe",)),
    ("Dead by Daylight", ("deadbydaylight-win64-shipping.exe",)),
    ("Among Us", ("among us.exe",)),
    ("Lethal Company", ("lethal company.exe",)),
    ("Phasmophobia", ("phasmophobia.exe",)),
    ("Helldivers 2", ("helldivers2.exe",)),
    ("Sea of Thieves", ("sotgame.exe",)),
    ("Hunt: Showdown", ("huntgame.exe",)),
    ("Warframe", ("warframe.x64.exe",)),
    ("Genshin Impact", ("genshinimpact.exe",)),
]
