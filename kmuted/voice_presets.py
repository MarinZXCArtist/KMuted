"""Ready-made voices added with one click (Voices page → «Готовые голоса»).

The classic IVONA voices can't be shipped with KMuted (they are commercial),
so a preset uses the same voice wherever the user already has it: an IVONA
voice installed in Windows (offline), otherwise Amazon Polly, which is where
IVONA's voices live today.
"""

from __future__ import annotations

from dataclasses import dataclass

from kmuted.config import ENGINE_SAPI, VoiceProfile
from kmuted.tts.base import VoiceInfo


@dataclass(frozen=True)
class VoicePreset:
    key: str
    name: str  # profile name (Russian source, shown through tr())
    description: str
    sapi_match: tuple[str, ...]  # substrings of an installed Windows voice name
    polly_voice: str
    rate: int = 0
    pitch: int = 0


PRESETS: list[VoicePreset] = [
    VoicePreset(
        "kava",
        "Кава (Максим)",
        "Голос IVONA «Максим» с ускорением, как в роликах Кавы про Rust",
        ("maxim", "максим"),
        "Maxim",
        rate=12,
    ),
    VoicePreset("maxim", "Максим (IVONA)", "Классический «Максим» без изменений", ("maxim", "максим"), "Maxim"),
    VoicePreset("tatyana", "Татьяна (IVONA)", "Классическая женская пара «Максима»", ("tatyana", "татьяна"), "Tatyana"),
]


def find_installed(preset: VoicePreset, sapi_voices: list[VoiceInfo]) -> VoiceInfo | None:
    """An installed Windows voice that is this preset's voice (e.g. «IVONA 2 Maxim»)."""
    for voice in sapi_voices:
        name = f"{voice.name} {voice.id}".lower()
        if any(part in name for part in preset.sapi_match):
            return voice
    return None


def build(preset: VoicePreset, name: str, sapi_voices: list[VoiceInfo]) -> tuple[VoiceProfile, bool]:
    """The voice profile for ``preset`` and whether it uses an installed (offline) voice."""
    installed = find_installed(preset, sapi_voices)
    if installed is not None:
        profile = VoiceProfile(name=name, engine=ENGINE_SAPI, voice=installed.id, rate=preset.rate, pitch=preset.pitch)
        return profile, True
    profile = VoiceProfile(name=name, engine="polly", voice=preset.polly_voice, model="standard", rate=preset.rate, pitch=preset.pitch)
    return profile, False
