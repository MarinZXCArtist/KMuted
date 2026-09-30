"""Microsoft Edge neural voices (free, needs internet).

High-quality voices in ~80 languages including Russian (Дмитрий,
Светлана) and "Multilingual" voices that can read Russian text too.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging

import numpy as np

from kmuted import paths
from kmuted.audio.dsp import Clip
from kmuted.config import VoiceProfile
from kmuted.tts.base import TTSEngine, TTSError, VoiceInfo
from kmuted.i18n import tr

log = logging.getLogger(__name__)

# Used when the voice list can't be downloaded.
FALLBACK_VOICES = [
    VoiceInfo("ru-RU-DmitryNeural", "Dmitry", "ru-RU", "Male"),
    VoiceInfo("ru-RU-SvetlanaNeural", "Svetlana", "ru-RU", "Female"),
    VoiceInfo("uk-UA-OstapNeural", "Ostap", "uk-UA", "Male"),
    VoiceInfo("uk-UA-PolinaNeural", "Polina", "uk-UA", "Female"),
    VoiceInfo("en-US-AndrewMultilingualNeural", "Andrew Multilingual", "en-US", "Male"),
    VoiceInfo("en-US-BrianMultilingualNeural", "Brian Multilingual", "en-US", "Male"),
    VoiceInfo("en-US-AvaMultilingualNeural", "Ava Multilingual", "en-US", "Female"),
    VoiceInfo("en-US-EmmaMultilingualNeural", "Emma Multilingual", "en-US", "Female"),
    VoiceInfo("de-DE-FlorianMultilingualNeural", "Florian Multilingual", "de-DE", "Male"),
    VoiceInfo("de-DE-SeraphinaMultilingualNeural", "Seraphina Multilingual", "de-DE", "Female"),
    VoiceInfo("fr-FR-RemyMultilingualNeural", "Remy Multilingual", "fr-FR", "Male"),
    VoiceInfo("fr-FR-VivienneMultilingualNeural", "Vivienne Multilingual", "fr-FR", "Female"),
    VoiceInfo("en-US-GuyNeural", "Guy", "en-US", "Male"),
    VoiceInfo("en-US-JennyNeural", "Jenny", "en-US", "Female"),
    VoiceInfo("en-GB-RyanNeural", "Ryan", "en-GB", "Male"),
    VoiceInfo("kk-KZ-DauletNeural", "Daulet", "kk-KZ", "Male"),
    VoiceInfo("kk-KZ-AigulNeural", "Aigul", "kk-KZ", "Female"),
]


def decode_audio_bytes(data: bytes) -> tuple[np.ndarray, int]:
    """MP3/WAV/OGG bytes -> (float32 samples, rate)."""
    errors = []
    try:
        import soundfile as sf

        samples, rate = sf.read(io.BytesIO(data), dtype="float32", always_2d=False)
        return samples, int(rate)
    except Exception as exc:
        errors.append(f"soundfile: {exc}")
    try:
        import miniaudio

        decoded = miniaudio.decode(data, output_format=miniaudio.SampleFormat.FLOAT32, nchannels=1)
        return np.frombuffer(decoded.samples, dtype=np.float32).copy(), decoded.sample_rate
    except Exception as exc:
        errors.append(f"miniaudio: {exc}")
    raise TTSError(tr("Не удалось декодировать аудио (") + "; ".join(errors) + tr("). Обновите пакет soundfile."))


def _friendly_name(short_name: str) -> str:
    # "ru-RU-DmitryNeural" -> "Dmitry"; "en-US-AndrewMultilingualNeural" -> "Andrew Multilingual"
    name = short_name.split("-", 2)[-1].removesuffix("Neural")
    return name.replace("Multilingual", " Multilingual").strip()


class EdgeEngine(TTSEngine):
    key = "edge"
    title = "Edge (онлайн, нейросетевые)"
    description = "Бесплатные нейросетевые голоса Microsoft. Нужен интернет."

    def __init__(self) -> None:
        self._voices: list[VoiceInfo] | None = None
        self._cache_file = paths.data_dir() / "edge_voices.json"

    def availability(self) -> str:
        try:
            import edge_tts  # noqa: F401
        except ImportError:
            return tr("Не установлен пакет edge-tts (pip install edge-tts)")
        return ""

    def list_voices(self, refresh: bool = False) -> list[VoiceInfo]:
        if self._voices is not None and not refresh:
            return self._voices
        voices = None
        if refresh or not self._cache_file.exists():
            voices = self._download_list()
        if voices is None:
            voices = self._load_cached_list()
        self._voices = voices or list(FALLBACK_VOICES)
        return self._voices

    def _download_list(self) -> list[VoiceInfo] | None:
        try:
            import edge_tts

            raw = asyncio.run(edge_tts.list_voices())
        except Exception as exc:
            log.warning("edge voice list download failed: %s", exc)
            return None
        items = [
            {"id": v["ShortName"], "language": v.get("Locale", ""), "gender": v.get("Gender", "")}
            for v in raw
            if v.get("ShortName")
        ]
        try:
            self._cache_file.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
        return self._from_items(items)

    def _load_cached_list(self) -> list[VoiceInfo] | None:
        try:
            items = json.loads(self._cache_file.read_text(encoding="utf-8"))
            return self._from_items(items)
        except (OSError, ValueError, KeyError, TypeError):
            return None

    @staticmethod
    def _from_items(items: list[dict]) -> list[VoiceInfo]:
        voices = [VoiceInfo(i["id"], _friendly_name(i["id"]), i.get("language", ""), i.get("gender", "")) for i in items]
        # Russian first, then multilingual voices (they read Russian too), then the rest
        def order(v: VoiceInfo):
            return (not v.language.startswith("ru"), "Multilingual" not in v.id, v.language, v.name)

        return sorted(voices, key=order)

    def synthesize(self, text: str, profile: VoiceProfile) -> Clip:
        try:
            import edge_tts
        except ImportError as exc:
            raise TTSError(tr("Не установлен пакет edge-tts")) from exc

        voice = profile.voice or "ru-RU-DmitryNeural"

        async def run() -> bytes:
            communicate = edge_tts.Communicate(
                text,
                voice,
                rate=f"{profile.rate:+d}%",
                pitch=f"{profile.pitch:+d}Hz",
                connect_timeout=8,
                receive_timeout=30,
            )
            audio = bytearray()
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio":
                    audio.extend(chunk["data"])
            return bytes(audio)

        try:
            data = asyncio.run(run())
        except Exception as exc:
            raise TTSError(tr("Edge TTS: {error}. Проверьте интернет или выберите офлайн-голос.", error=exc or type(exc).__name__)) from exc
        if not data:
            raise TTSError(tr("Edge TTS вернул пустой ответ (возможно, неверное имя голоса)"))
        samples, rate = decode_audio_bytes(data)
        return Clip(samples, rate)
