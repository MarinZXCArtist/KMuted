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
CLOUD_ENGINES = ("elevenlabs", "openai", "azure", "google", "yandex", "polly")
FREE_ENGINES = (ENGINE_EDGE, ENGINE_SAPI, ENGINE_PIPER)
ENGINES = FREE_ENGINES + CLOUD_ENGINES

PLAYBACK_QUEUE = "queue"
PLAYBACK_INTERRUPT = "interrupt"

WHEEL_HOLD = "hold"
WHEEL_TOGGLE = "toggle"

TRANSLATORS = ("google", "mymemory", "deepl", "claude", "openai")
TRANSLATE_STYLES = ("natural", "gaming", "polite", "short")
PROFILE_AUTO = "auto"  # GeneralSettings.profile_mode: "auto", "none" or a profile id
PROFILE_NONE = "none"


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
    hotkey: str = ""  # switch to this voice
    model: str = ""  # cloud providers: model id (empty = provider default)

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
            self.model,
        )


@dataclass
class Phrase:
    """Quick phrase: one hotkey says one fixed text."""

    id: str = field(default_factory=new_id)
    text: str = ""
    hotkey: str = ""
    voice_id: str = ""  # "" = active voice
    profiles: list[str] = field(default_factory=list)  # game profile ids; empty = everywhere


@dataclass
class Sound:
    """Soundboard entry: an audio file on a hotkey."""

    id: str = field(default_factory=new_id)
    name: str = ""
    file: str = ""  # file name inside the sounds folder, or an absolute path
    hotkey: str = ""
    volume: int = 100  # percent, 0..200
    restart: bool = True  # pressing again restarts instead of layering
    profiles: list[str] = field(default_factory=list)


@dataclass
class WheelSlot:
    text: str = ""
    label: str = ""  # short caption on the wheel; falls back to text
    voice_id: str = ""
    sound_id: str = ""  # if set, the slot plays this sound instead of speaking

    @property
    def caption(self) -> str:
        return (self.label or self.text).strip()

    @property
    def filled(self) -> bool:
        return bool(self.text.strip() or self.sound_id)


@dataclass
class Wheel:
    """Radial menu of phrases opened by one hotkey."""

    id: str = field(default_factory=new_id)
    name: str = "Колесо"
    hotkey: str = ""
    slots: list[WheelSlot] = field(default_factory=lambda: [WheelSlot() for _ in range(8)])
    profiles: list[str] = field(default_factory=list)


@dataclass
class GameProfile:
    """Bindings that switch on by themselves while a game is running."""

    id: str = field(default_factory=new_id)
    name: str = "Игра"
    processes: list[str] = field(default_factory=list)  # exe names, lower case: "cs2.exe"
    enabled: bool = True
    color: str = ""  # cover color, "" = derived from the name
    voice_id: str = ""  # "" = keep the current voice
    translate: str = ""  # "" = as set globally, "on", "off"
    target: str = ""  # translation language override, "" = global


@dataclass
class AudioSettings:
    mic_device: str = ""  # output device of the virtual cable, e.g. "CABLE Input"
    mic_volume: int = 100
    mic_muted: bool = False  # hotkey-toggled: KMuted stays silent in the mic
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
    language: str = ""  # "" = auto (installer choice / system language)
    accent: str = "violet"
    hotkeys_enabled: bool = True
    # global actions (see kmuted/actions.py)
    input_hotkey: str = "alt+t"
    repeat_hotkey: str = "alt+r"
    stop_hotkey: str = "alt+s"
    stop_sounds_hotkey: str = ""
    next_voice_hotkey: str = ""
    prev_voice_hotkey: str = ""
    mute_hotkey: str = ""
    monitor_hotkey: str = ""
    passthrough_hotkey: str = ""
    volume_up_hotkey: str = ""
    volume_down_hotkey: str = ""
    toggle_hotkeys_hotkey: str = ""
    show_window_hotkey: str = ""
    translate_hotkey: str = ""
    next_language_hotkey: str = ""
    next_profile_hotkey: str = ""
    profile_mode: str = PROFILE_AUTO
    voice_before_profile: str = ""  # restored when the game profile switches off
    input_position: str = "center"  # top / center / bottom
    wheel_scale: int = 100  # percent
    check_updates: bool = True
    last_update_check: float = 0.0
    skipped_version: str = ""
    wheel_mode: str = WHEEL_HOLD
    wheel_deadzone: int = 40
    input_keep_open: bool = False
    input_restore_focus: bool = True
    start_minimized: bool = False
    close_to_tray: bool = True
    tray_hint_shown: bool = False
    rvc_server_url: str = "http://127.0.0.1:5050"


@dataclass
class CloudSettings:
    """API keys of paid/freemium voice services (stored encrypted on Windows)."""

    elevenlabs_key: str = ""
    openai_key: str = ""
    azure_key: str = ""
    azure_region: str = "westeurope"
    google_key: str = ""
    yandex_key: str = ""
    polly_key_id: str = ""  # Amazon Polly (AWS access key ID + secret)
    polly_secret: str = ""
    polly_region: str = "eu-central-1"
    deepl_key: str = ""  # translation
    anthropic_key: str = ""  # translation with Claude
    prewarm_paid: bool = False  # pre-synthesize phrases with paid voices (costs credits)


@dataclass
class LanguageVoice:
    lang: str = ""
    voice_id: str = ""


@dataclass
class TranslateSettings:
    """Translate what the user writes before it is spoken."""

    enabled: bool = False
    provider: str = "google"
    source: str = "auto"
    target: str = "en"
    favorites: list[str] = field(default_factory=lambda: ["en", "de", "es", "fr"])  # cycled by a hotkey
    style: str = "natural"
    instructions: str = ""  # extra wishes for AI translators
    phrases: bool = True  # also quick phrases and wheels
    preview: bool = True  # live translation under the input box
    auto_voice: bool = True  # pick a voice that speaks the target language
    voices: list[LanguageVoice] = field(default_factory=list)
    claude_model: str = "claude-opus-5-5"
    openai_model: str = "gpt-4.1-mini"
    email: str = ""  # MyMemory: raises the free daily limit


@dataclass
class Config:
    version: int = CONFIG_VERSION
    general: GeneralSettings = field(default_factory=GeneralSettings)
    audio: AudioSettings = field(default_factory=AudioSettings)
    cloud: CloudSettings = field(default_factory=CloudSettings)
    translate: TranslateSettings = field(default_factory=TranslateSettings)
    voices: list[VoiceProfile] = field(default_factory=list)
    phrases: list[Phrase] = field(default_factory=list)
    wheels: list[Wheel] = field(default_factory=list)
    sounds: list[Sound] = field(default_factory=list)
    profiles: list[GameProfile] = field(default_factory=list)
    history: list[str] = field(default_factory=list)

    # --- lookups -----------------------------------------------------------

    def voice_by_id(self, voice_id: str) -> VoiceProfile | None:
        return next((v for v in self.voices if v.id == voice_id), None)

    def sound_by_id(self, sound_id: str) -> Sound | None:
        return next((x for x in self.sounds if x.id == sound_id), None)

    def profile_by_id(self, profile_id: str) -> GameProfile | None:
        return next((x for x in self.profiles if x.id == profile_id), None)

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
        from kmuted.actions import ACTION_KEYS, attr

        for key in ACTION_KEYS:
            setattr(g, attr(key), normalize_combo(getattr(g, attr(key))))
        if g.input_position not in ("top", "center", "bottom"):
            g.input_position = "center"
        g.wheel_scale = _clamp(g.wheel_scale, 60, 150)
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
            v.hotkey = normalize_combo(v.hotkey)
            if v.engine not in ENGINES:
                v.engine = ENGINE_EDGE
            v.rate = _clamp(v.rate, -50, 100)
            v.pitch = _clamp(v.pitch, -50, 50)
            v.volume = _clamp(v.volume, 0, 200)
            v.rvc_pitch = _clamp(v.rvc_pitch, -24, 24)
        for p in self.phrases:
            p.hotkey = normalize_combo(p.hotkey)
        for snd in self.sounds:
            snd.hotkey = normalize_combo(snd.hotkey)
            snd.volume = _clamp(snd.volume, 0, 200)
        for w in self.wheels:
            w.hotkey = normalize_combo(w.hotkey)
            if len(w.slots) < WHEEL_MIN_SLOTS:
                w.slots += [WheelSlot() for _ in range(WHEEL_MIN_SLOTS - len(w.slots))]
            del w.slots[WHEEL_MAX_SLOTS:]
        del self.history[HISTORY_LIMIT:]

        seen_ids = set()
        for prof in self.profiles:
            if prof.id in seen_ids:
                prof.id = new_id()
            seen_ids.add(prof.id)
            names = []
            for name in prof.processes:
                name = name.strip().strip('"').replace("/", "\\").rsplit("\\", 1)[-1].lower()
                if name and name not in names:
                    names.append(name)
            prof.processes = names
            if prof.translate not in ("", "on", "off"):
                prof.translate = ""
        valid = {p.id for p in self.profiles}
        for item in [*self.phrases, *self.wheels, *self.sounds]:
            item.profiles = [pid for pid in dict.fromkeys(item.profiles) if pid in valid]
        if g.profile_mode not in (PROFILE_AUTO, PROFILE_NONE) and g.profile_mode not in valid:
            g.profile_mode = PROFILE_AUTO

        t = self.translate
        if t.provider not in TRANSLATORS:
            t.provider = "google"
        if t.style not in TRANSLATE_STYLES:
            t.style = "natural"
        t.source = (t.source or "auto").lower()
        t.target = (t.target or "en").lower()
        t.favorites = [code.lower() for code in dict.fromkeys(t.favorites) if code]
        t.instructions = t.instructions[:500]
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


# (text, caption) of the starter wheel; translated when the config is created
DEFAULT_WHEEL = [
    ("Да", "Да"),
    ("Внимание, враг рядом!", "Враг!"),
    ("Иду к вам.", "Иду"),
    ("Нужна помощь!", "Помощь"),
    ("Нет", "Нет"),
    ("Отступаем!", "Отход"),
    ("Спасибо!", "Спасибо"),
    ("Хорошая игра!", "GG"),
]


def default_config() -> Config:
    """Starter voices, phrases and a wheel in the current UI language."""
    from kmuted.i18n import language, tr

    if language() == "en":
        first = VoiceProfile(name="Andrew (Edge)", engine=ENGINE_EDGE, voice="en-US-AndrewMultilingualNeural")
        second = VoiceProfile(name="Emma (Edge)", engine=ENGINE_EDGE, voice="en-US-EmmaMultilingualNeural")
    else:
        first = VoiceProfile(name="Дмитрий (Edge)", engine=ENGINE_EDGE, voice="ru-RU-DmitryNeural")
        second = VoiceProfile(name="Светлана (Edge)", engine=ENGINE_EDGE, voice="ru-RU-SvetlanaNeural")
    voices = [first, second]
    if os.name == "nt":
        voices.append(VoiceProfile(name=tr("Windows (офлайн)"), engine=ENGINE_SAPI, voice=""))

    phrases = [
        Phrase(text=tr("Привет всем!"), hotkey="alt+1"),
        Phrase(text=tr("Спасибо!"), hotkey="alt+2"),
        Phrase(text=tr("Секунду, я отойду."), hotkey="alt+3"),
        Phrase(text=tr("Я не могу говорить в микрофон, пишу через озвучку."), hotkey="alt+4"),
    ]
    wheel = Wheel(
        name=tr("Основное"),
        hotkey="alt+q",
        slots=[WheelSlot(text=tr(text), label=tr(label)) for text, label in DEFAULT_WHEEL],
    )
    cfg = Config(voices=voices, phrases=phrases, wheels=[wheel])
    cfg.general.active_voice_id = first.id
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
    return _decrypt_keys(from_dict(Config, data)).normalize()


KEY_FIELDS = (
    "elevenlabs_key", "openai_key", "azure_key", "google_key", "yandex_key",
    "polly_key_id", "polly_secret", "deepl_key", "anthropic_key",
)


def save_config(cfg: Config, path: Path | None = None) -> None:
    from kmuted import keystore

    path = path or paths.config_path()
    data = to_dict(cfg)
    for name in KEY_FIELDS:  # API keys are encrypted at rest
        data["cloud"][name] = keystore.protect(data["cloud"][name])
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _decrypt_keys(cfg: Config) -> Config:
    from kmuted import keystore

    for name in KEY_FIELDS:
        setattr(cfg.cloud, name, keystore.unprotect(getattr(cfg.cloud, name)))
    return cfg
