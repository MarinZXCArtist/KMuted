"""Settings model and JSON persistence.

Everything the user configures lives in one ``config.json``. Loading is
tolerant: unknown keys are dropped and missing ones get defaults, so old
config files keep working after updates.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import typing
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kmuted import paths
from kmuted.hotkeys.keys import normalize_combo

log = logging.getLogger(__name__)

CONFIG_VERSION = 1
WHEEL_MIN_SLOTS = 4
WHEEL_MAX_SLOTS = 12
HISTORY_LIMIT = 50

ENGINE_EDGE = "edge"
ENGINE_SAPI = "sapi"
ENGINE_PIPER = "piper"
ENGINES = (ENGINE_EDGE, ENGINE_SAPI, ENGINE_PIPER)

PLAYBACK_QUEUE = "queue"
PLAYBACK_INTERRUPT = "interrupt"

WHEEL_HOLD = "hold"
WHEEL_TOGGLE = "toggle"


def new_id() -> str:
    return uuid.uuid4().hex[:10]


@dataclass
class VoiceProfile:
    """A named voice: engine + voice + tuning (+ optional RVC conversion)."""

    id: str = field(default_factory=new_id)
    name: str = "Голос"
    engine: str = ENGINE_EDGE
    # Edge: ShortName ("ru-RU-DmitryNeural"); SAPI: token id; Piper: .onnx path.
    voice: str = "ru-RU-DmitryNeural"
    rate: int = 0  # percent, -50..100
    pitch: int = 0  # Hz-like offset, -50..50 (Edge, SAPI)
    volume: int = 100  # percent gain, 0..200
    speaker: int = 0  # Piper multi-speaker models
    rvc_enabled: bool = False
    rvc_model: str = ""
    rvc_pitch: int = 0  # semitones
    rvc_method: str = "rmvpe"

    def cache_key(self) -> tuple:
        return (
            self.engine,
            self.voice,
            self.rate,
            self.pitch,
            self.speaker,
            self.rvc_enabled and self.rvc_model,
            self.rvc_enabled and self.rvc_pitch,
            self.rvc_enabled and self.rvc_method,
        )


@dataclass
class Phrase:
    """Quick phrase: one hotkey says one fixed text."""

    id: str = field(default_factory=new_id)
    text: str = ""
    hotkey: str = ""
    voice_id: str = ""  # "" = active voice


@dataclass
class WheelSlot:
    text: str = ""
    label: str = ""  # short caption on the wheel; falls back to text
    voice_id: str = ""

    @property
    def caption(self) -> str:
        return (self.label or self.text).strip()


@dataclass
class Wheel:
    """Radial menu of phrases opened by one hotkey."""

    id: str = field(default_factory=new_id)
    name: str = "Колесо"
    hotkey: str = ""
    slots: list[WheelSlot] = field(default_factory=lambda: [WheelSlot() for _ in range(8)])


@dataclass
class AudioSettings:
    mic_device: str = ""  # output device of the virtual cable, e.g. "CABLE Input"
    mic_volume: int = 100
    monitor_enabled: bool = True
    monitor_device: str = ""  # "" = system default output
    monitor_volume: int = 60
    passthrough_enabled: bool = False  # also send the real microphone to the cable
    passthrough_device: str = ""
    passthrough_volume: int = 100
    ptt_key: str = ""  # key held while speaking (game push-to-talk)
    ptt_delay_ms: int = 150
    ptt_tail_ms: int = 250
    playback_mode: str = PLAYBACK_QUEUE


@dataclass
class GeneralSettings:
    active_voice_id: str = ""
    hotkeys_enabled: bool = True
    input_hotkey: str = "alt+t"
    stop_hotkey: str = "alt+s"
    toggle_hotkeys_hotkey: str = ""
    next_voice_hotkey: str = ""
    wheel_mode: str = WHEEL_HOLD
    wheel_deadzone: int = 40
    input_keep_open: bool = False
    input_restore_focus: bool = True
    start_minimized: bool = False
    close_to_tray: bool = True
    rvc_server_url: str = "http://127.0.0.1:5050"


@dataclass
class Config:
    version: int = CONFIG_VERSION
    general: GeneralSettings = field(default_factory=GeneralSettings)
    audio: AudioSettings = field(default_factory=AudioSettings)
    voices: list[VoiceProfile] = field(default_factory=list)
    phrases: list[Phrase] = field(default_factory=list)
    wheels: list[Wheel] = field(default_factory=list)
    history: list[str] = field(default_factory=list)

    # --- lookups -----------------------------------------------------------

    def voice_by_id(self, voice_id: str) -> VoiceProfile | None:
        return next((v for v in self.voices if v.id == voice_id), None)

    def active_voice(self) -> VoiceProfile:
        voice = self.voice_by_id(self.general.active_voice_id)
        if voice is None:
            if not self.voices:
                self.voices.append(VoiceProfile(name="Дмитрий (Edge)"))
            voice = self.voices[0]
            self.general.active_voice_id = voice.id
        return voice

    def resolve_voice(self, voice_id: str = "") -> VoiceProfile:
        return (voice_id and self.voice_by_id(voice_id)) or self.active_voice()

    def add_history(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        if text in self.history:
            self.history.remove(text)
        self.history.insert(0, text)
        del self.history[HISTORY_LIMIT:]

    def normalize(self) -> "Config":
        """Fix values that could break the app (after load or edits)."""
        g = self.general
        for name in ("input_hotkey", "stop_hotkey", "toggle_hotkeys_hotkey", "next_voice_hotkey"):
            setattr(g, name, normalize_combo(getattr(g, name)))
        if g.wheel_mode not in (WHEEL_HOLD, WHEEL_TOGGLE):
            g.wheel_mode = WHEEL_HOLD
        g.wheel_deadzone = _clamp(g.wheel_deadzone, 10, 200)

        a = self.audio
        a.mic_volume = _clamp(a.mic_volume, 0, 200)
        a.monitor_volume = _clamp(a.monitor_volume, 0, 200)
        a.passthrough_volume = _clamp(a.passthrough_volume, 0, 200)
        a.ptt_delay_ms = _clamp(a.ptt_delay_ms, 0, 2000)
        a.ptt_tail_ms = _clamp(a.ptt_tail_ms, 0, 3000)
        if a.playback_mode not in (PLAYBACK_QUEUE, PLAYBACK_INTERRUPT):
            a.playback_mode = PLAYBACK_QUEUE

        for v in self.voices:
            if v.engine not in ENGINES:
                v.engine = ENGINE_EDGE
            v.rate = _clamp(v.rate, -50, 100)
            v.pitch = _clamp(v.pitch, -50, 50)
            v.volume = _clamp(v.volume, 0, 200)
            v.rvc_pitch = _clamp(v.rvc_pitch, -24, 24)
        for p in self.phrases:
            p.hotkey = normalize_combo(p.hotkey)
        for w in self.wheels:
            w.hotkey = normalize_combo(w.hotkey)
            if len(w.slots) < WHEEL_MIN_SLOTS:
                w.slots += [WheelSlot() for _ in range(WHEEL_MIN_SLOTS - len(w.slots))]
            del w.slots[WHEEL_MAX_SLOTS:]
        del self.history[HISTORY_LIMIT:]
        self.active_voice()
        return self


def _clamp(value: Any, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return lo


# --- (de)serialization ------------------------------------------------------


def to_dict(obj: Any) -> Any:
    return dataclasses.asdict(obj)


def from_dict(cls: type, data: Any) -> Any:
    """Build dataclass ``cls`` from ``data``, ignoring junk, keeping defaults."""
    if not isinstance(data, dict):
        return cls()
    hints = typing.get_type_hints(cls)
    kwargs = {}
    for f in dataclasses.fields(cls):
        if f.name not in data:
            continue
        value = _convert(hints[f.name], data[f.name])
        if value is not _INVALID:
            kwargs[f.name] = value
    return cls(**kwargs)


_INVALID = object()


def _convert(tp: Any, value: Any) -> Any:
    origin = typing.get_origin(tp)
    if dataclasses.is_dataclass(tp):
        return from_dict(tp, value) if isinstance(value, dict) else _INVALID
    if origin is list:
        if not isinstance(value, list):
            return _INVALID
        (item_tp,) = typing.get_args(tp)
        items = [_convert(item_tp, item) for item in value]
        return [item for item in items if item is not _INVALID]
    if tp is bool:
        return value if isinstance(value, bool) else _INVALID
    if tp is int:
        if isinstance(value, bool):
            return _INVALID
        try:
            return int(value)
        except (TypeError, ValueError):
            return _INVALID
    if tp is float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return _INVALID
    if tp is str:
        return value if isinstance(value, str) else _INVALID
    return value


# --- defaults ---------------------------------------------------------------


def default_config() -> Config:
    dmitry = VoiceProfile(name="Дмитрий (Edge)", engine=ENGINE_EDGE, voice="ru-RU-DmitryNeural")
    svetlana = VoiceProfile(name="Светлана (Edge)", engine=ENGINE_EDGE, voice="ru-RU-SvetlanaNeural")
    voices = [dmitry, svetlana]
    if os.name == "nt":
        voices.append(VoiceProfile(name="Windows (офлайн)", engine=ENGINE_SAPI, voice=""))

    phrases = [
        Phrase(text="Привет всем!", hotkey="alt+1"),
        Phrase(text="Спасибо!", hotkey="alt+2"),
        Phrase(text="Секунду, я отойду.", hotkey="alt+3"),
        Phrase(text="Я не могу говорить в микрофон, пишу через озвучку.", hotkey="alt+4"),
    ]
    wheel = Wheel(
        name="Основное",
        hotkey="alt+q",
        slots=[
            WheelSlot(text="Да", label="Да"),
            WheelSlot(text="Внимание, враг рядом!", label="Враг!"),
            WheelSlot(text="Иду к вам.", label="Иду"),
            WheelSlot(text="Нужна помощь!", label="Помощь"),
            WheelSlot(text="Нет", label="Нет"),
            WheelSlot(text="Отступаем!", label="Отход"),
            WheelSlot(text="Спасибо!", label="Спасибо"),
            WheelSlot(text="Хорошая игра!", label="GG"),
        ],
    )
    cfg = Config(voices=voices, phrases=phrases, wheels=[wheel])
    cfg.general.active_voice_id = dmitry.id
    return cfg.normalize()


# --- file I/O ---------------------------------------------------------------


def load_config(path: Path | None = None) -> Config:
    path = path or paths.config_path()
    if not path.exists():
        cfg = default_config()
        save_config(cfg, path)
        return cfg
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.error("Config is unreadable (%s), starting with defaults", exc)
        backup = path.with_suffix(".broken.json")
        try:
            path.replace(backup)
        except OSError:
            pass
        cfg = default_config()
        save_config(cfg, path)
        return cfg
    return from_dict(Config, data).normalize()


def save_config(cfg: Config, path: Path | None = None) -> None:
    path = path or paths.config_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(to_dict(cfg), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
