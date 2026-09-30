"""Piper — fast offline neural TTS with downloadable/custom voice models.

A voice is a pair of files: ``name.onnx`` + ``name.onnx.json``. Put them
into the voices folder (or download from the built-in catalog); community
trained models work the same way.
"""

from __future__ import annotations

import json
import logging
import threading
from collections import OrderedDict
from pathlib import Path

import numpy as np

from kmuted import paths
from kmuted.audio.dsp import Clip
from kmuted.config import VoiceProfile
from kmuted.tts.base import TTSEngine, TTSError, VoiceInfo

log = logging.getLogger(__name__)

SENTENCE_PAUSE_S = 0.12
MAX_LOADED_MODELS = 2  # each model is 20-120 MB of RAM


def rate_to_length_scale(rate: int) -> float:
    """Percent speed-up (-50..100) -> Piper length_scale (2.0..0.5)."""
    return 1.0 / max(0.25, 1.0 + rate / 100.0)


def model_info(model: Path) -> VoiceInfo:
    lang = quality = ""
    speakers = 1
    try:
        cfg = json.loads(Path(f"{model}.json").read_text(encoding="utf-8"))
        lang = (cfg.get("language") or {}).get("code", "") or cfg.get("espeak", {}).get("voice", "")
        quality = (cfg.get("audio") or {}).get("quality", "")
        speakers = int(cfg.get("num_speakers") or 1)
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    extra = quality
    if speakers > 1:
        extra = f"{quality}, голосов: {speakers}".strip(", ")
    return VoiceInfo(str(model), model.stem, lang.replace("_", "-"), "", extra)


class PiperEngine(TTSEngine):
    key = "piper"
    title = "Piper (офлайн, свои модели)"
    description = "Офлайн нейросетевые голоса. Можно скачать из каталога или добавить свои .onnx модели."

    def __init__(self) -> None:
        self._models: OrderedDict[str, object] = OrderedDict()
        self._lock = threading.Lock()  # espeak phonemizer is not thread-safe

    def availability(self) -> str:
        try:
            import piper  # noqa: F401
        except ImportError:
            return "Не установлен пакет piper-tts (pip install piper-tts)"
        return ""

    @staticmethod
    def voices_dir() -> Path:
        return paths.piper_voices_dir()

    def list_voices(self, refresh: bool = False) -> list[VoiceInfo]:
        found = []
        for model in sorted(self.voices_dir().rglob("*.onnx")):
            if Path(f"{model}.json").exists():
                found.append(model_info(model))
        found.sort(key=lambda v: (not v.language.startswith("ru"), v.name))
        return found

    def _load(self, model_path: str):
        voice = self._models.get(model_path)
        if voice is not None:
            self._models.move_to_end(model_path)
            return voice
        path = Path(model_path)
        if not path.exists():
            raise TTSError(f"Файл модели Piper не найден: {model_path}")
        if not Path(f"{path}.json").exists():
            raise TTSError(f"Рядом с моделью нет файла настроек {path.name}.json")
        try:
            from piper import PiperVoice
        except ImportError as exc:
            raise TTSError("Не установлен пакет piper-tts") from exc
        try:
            voice = PiperVoice.load(str(path))
        except Exception as exc:
            raise TTSError(f"Не удалось загрузить модель Piper: {exc}") from exc
        self._models[model_path] = voice
        while len(self._models) > MAX_LOADED_MODELS:
            self._models.popitem(last=False)
        return voice

    def synthesize(self, text: str, profile: VoiceProfile) -> Clip:
        if not profile.voice:
            raise TTSError("Для голоса Piper не выбрана модель")
        with self._lock:
            voice = self._load(profile.voice)
            num_speakers = getattr(voice.config, "num_speakers", 1) or 1
            speaker_id = profile.speaker if num_speakers > 1 else None
            if speaker_id is not None and not 0 <= speaker_id < num_speakers:
                speaker_id = 0
            length_scale = rate_to_length_scale(profile.rate)
            try:
                return self._synthesize(voice, text, speaker_id, length_scale)
            except TTSError:
                raise
            except Exception as exc:
                raise TTSError(f"Piper: {exc}") from exc

    @staticmethod
    def _synthesize(voice, text: str, speaker_id, length_scale: float) -> Clip:
        rate = int(voice.config.sample_rate)
        pause = np.zeros(int(rate * SENTENCE_PAUSE_S), dtype=np.float32)
        parts: list[np.ndarray] = []
        try:
            from piper import SynthesisConfig
        except ImportError:  # piper-tts < 1.3
            SynthesisConfig = None

        if SynthesisConfig is not None:
            syn = SynthesisConfig(speaker_id=speaker_id, length_scale=length_scale)
            for chunk in voice.synthesize(text, syn_config=syn):
                if parts:
                    parts.append(pause)
                parts.append(np.asarray(chunk.audio_float_array, dtype=np.float32).reshape(-1))
                rate = int(chunk.sample_rate)
        else:
            raw = b"".join(voice.synthesize_stream_raw(text, speaker_id=speaker_id, length_scale=length_scale))
            parts.append(np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0)
        if not parts:
            raise TTSError("Piper не смог произнести этот текст (язык модели не совпадает с текстом?)")
        return Clip(np.concatenate(parts), rate)
