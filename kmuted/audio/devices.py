"""Audio device discovery (PortAudio via sounddevice)."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass

log = logging.getLogger(__name__)

# Output side of popular virtual audio cables. The *input* of the cable is
# where we play; games/Discord then pick the cable's *output* as a mic.
VIRTUAL_CABLE_HINTS = (
    "cable input",
    "cable-a input",
    "cable-b input",
    "voicemeeter input",
    "voicemeeter aux input",
    "vb-audio",
    "virtual cable",
    "virtual audio",
)

_HOSTAPI_PREFERENCE_WIN = ("Windows WASAPI", "Windows DirectSound", "MME")


class AudioUnavailable(RuntimeError):
    pass


def get_sd():
    try:
        import sounddevice as sd
    except Exception as exc:  # PortAudio missing, etc.
        raise AudioUnavailable(f"Звуковая библиотека недоступна: {exc}") from exc
    return sd


@dataclass(frozen=True)
class DeviceInfo:
    index: int
    name: str
    hostapi: str
    max_input: int
    max_output: int
    default_samplerate: float


def _all_devices(sd) -> list[DeviceInfo]:
    hostapis = sd.query_hostapis()
    result = []
    for i, dev in enumerate(sd.query_devices()):
        result.append(
            DeviceInfo(
                index=i,
                name=dev["name"],
                hostapi=hostapis[dev["hostapi"]]["name"],
                max_input=dev["max_input_channels"],
                max_output=dev["max_output_channels"],
                default_samplerate=dev["default_samplerate"],
            )
        )
    return result


def _hostapi_order(sd) -> list[str]:
    names = [api["name"] for api in sd.query_hostapis()]
    if sys.platform == "win32":
        preferred = [n for n in _HOSTAPI_PREFERENCE_WIN if n in names]
        return preferred + [n for n in names if n not in preferred]
    try:
        default = names[sd.default.hostapi]
    except Exception:
        default = names[0] if names else ""
    return [default] + [n for n in names if n != default]


def list_devices(kind: str = "output") -> list[DeviceInfo]:
    """Devices of the preferred host API only (Windows lists each device 3-4 times)."""
    sd = get_sd()
    devices = _all_devices(sd)
    order = _hostapi_order(sd)
    if not order:
        return []
    api = order[0]
    return [d for d in devices if d.hostapi == api and _has(d, kind)]


def _has(dev: DeviceInfo, kind: str) -> bool:
    return (dev.max_output if kind == "output" else dev.max_input) > 0


def find_candidates(name: str, kind: str = "output") -> list[DeviceInfo]:
    """Devices matching ``name`` ordered by host API preference.

    Returns several candidates so the caller can fall back to another host
    API if opening the first one fails. MME truncates names to 31 chars,
    hence the prefix match.
    """
    sd = get_sd()
    if not name:
        return []
    devices = [d for d in _all_devices(sd) if _has(d, kind)]
    order = {api: i for i, api in enumerate(_hostapi_order(sd))}
    wanted = name.lower()

    def score(d: DeviceInfo) -> int | None:
        dn = d.name.lower()
        if dn == wanted:
            return 0
        if len(dn) >= 20 and wanted.startswith(dn):
            return 1
        if wanted in dn or dn in wanted:
            return 2
        return None

    scored = [(s, order.get(d.hostapi, 99), d) for d in devices if (s := score(d)) is not None]
    scored.sort(key=lambda t: (t[1], t[0]))
    return [d for _, _, d in scored]


def default_output_candidates() -> list[DeviceInfo]:
    sd = get_sd()
    try:
        idx = sd.default.device[1]
    except Exception:
        idx = -1
    if idx is None or idx < 0:
        try:
            info = sd.query_devices(kind="output")
            return find_candidates(info["name"], "output")
        except Exception:
            return []
    dev = _all_devices(sd)[idx]
    return [dev] + [d for d in find_candidates(dev.name, "output") if d.index != dev.index]


def guess_virtual_cable() -> str:
    """Name of the first output that looks like a virtual cable, or ""."""
    try:
        outputs = list_devices("output")
    except AudioUnavailable:
        return ""
    for hint in VIRTUAL_CABLE_HINTS:
        for dev in outputs:
            if hint in dev.name.lower():
                return dev.name
    return ""


def is_virtual_cable(name: str) -> bool:
    lower = name.lower()
    return any(h in lower for h in VIRTUAL_CABLE_HINTS)
