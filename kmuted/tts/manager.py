"""Speech pipeline: engine -> optional RVC -> cleanup, with caching.

Quick phrases and wheel phrases are synthesized ahead of time and kept in
memory and on disk, so pressing their hotkey plays instantly even with an
online voice.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Iterable

import numpy as np
import soundfile as sf

from kmuted import paths
from kmuted.audio.dsp import Clip, apply_gain, prepare_clip
from kmuted.config import CloudSettings, VoiceProfile
from kmuted.tts.base import TTSEngine, TTSError
from kmuted.tts.cloud import CLOUD_CLASSES
from kmuted.tts.edge import EdgeEngine
from kmuted.tts.piper_engine import PiperEngine
from kmuted.tts.rvc import RVCClient
from kmuted.tts.sapi import SapiEngine
from kmuted.i18n import tr

log = logging.getLogger(__name__)

MEMORY_CACHE_BYTES = 24 * 1024 * 1024  # ~9 minutes of 24 kHz speech
DISK_CACHE_FILES = 600
FAILED_RETRY_S = 120.0  # don't hammer an offline service while prewarming


class _Cached:
    """Clip stored as int16 — half the RAM of float32."""

    __slots__ = ("pcm", "rate")

    def __init__(self, clip: Clip) -> None:
        self.pcm = np.clip(clip.samples * 32767.0, -32768, 32767).astype(np.int16)
        self.rate = clip.sample_rate

    @property
    def nbytes(self) -> int:
        return self.pcm.nbytes

    def clip(self) -> Clip:
        return Clip(self.pcm.astype(np.float32) / 32767.0, self.rate)


def cache_key(text: str, profile: VoiceProfile) -> str:
    raw = json.dumps([text, list(profile.cache_key())], ensure_ascii=False, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


class SpeechService:
    def __init__(
        self,
        rvc_url: str = "http://127.0.0.1:5050",
        engines: dict[str, TTSEngine] | None = None,
        cloud: CloudSettings | None = None,
    ) -> None:
        self._cloud = cloud or CloudSettings()
        if engines is None:
            local = [EdgeEngine(), SapiEngine(), PiperEngine()]
            remote = [cls(lambda: self._cloud) for cls in CLOUD_CLASSES]
            engines = {e.key: e for e in local + remote}
        self.engines: dict[str, TTSEngine] = engines
        self.rvc = RVCClient(rvc_url)
        self._memory: OrderedDict[str, _Cached] = OrderedDict()
        self._memory_bytes = 0
        self._failed: dict[str, float] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="tts")
        self._warm_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tts-warm")
        self._disk = paths.cache_dir()
        self._prune_disk()

    # --- public API ------------------------------------------------------------

    def submit(self, text: str, profile: VoiceProfile, persist: bool = False) -> Future:
        snapshot = dataclasses.replace(profile)
        return self._pool.submit(self.synthesize, text, snapshot, persist)

    def submit_call(self, fn, *args) -> Future:
        """Run ``fn`` on the speech workers (translation + synthesis jobs)."""
        return self._pool.submit(fn, *args)

    def prewarm(self, items: Iterable[tuple[str, VoiceProfile]]) -> None:
        """Synthesize fixed phrases in the background (errors are ignored)."""
        now = time.monotonic()
        seen = set()
        for text, profile in items:
            text = text.strip()
            key = cache_key(text, profile)
            if not text or key in seen or self._memory_has(key):
                continue
            if now - self._failed.get(key, -FAILED_RETRY_S) < FAILED_RETRY_S:
                continue
            seen.add(key)
            snapshot = dataclasses.replace(profile)
            self._warm_pool.submit(self._warm_one, text, snapshot)

    def synthesize(self, text: str, profile: VoiceProfile, persist: bool = False) -> Clip:
        text = text.strip()
        if not text:
            raise TTSError(tr("Пустой текст"))
        key = cache_key(text, profile)
        clip = self._memory_get(key) or self._disk_get(key)
        if clip is None:
            clip = self._render(text, profile)
            self._memory_put(key, clip)
            if persist:
                self._disk_put(key, clip)
        elif persist:
            self._disk_put(key, clip)
        return Clip(apply_gain(clip.samples, profile.volume), clip.sample_rate)

    def set_cloud(self, cloud: CloudSettings) -> None:
        """New API keys: forget cached voice lists of cloud engines."""
        self._cloud = cloud
        for engine in self.engines.values():
            forget = getattr(engine, "forget", None)
            if forget:
                forget()

    def clear_cache(self) -> None:
        with self._lock:
            self._memory.clear()
            self._memory_bytes = 0
            self._failed.clear()
        for f in self._disk.glob("*.wav"):
            f.unlink(missing_ok=True)

    def shutdown(self) -> None:
        self._warm_pool.shutdown(wait=False, cancel_futures=True)
        self._pool.shutdown(wait=False, cancel_futures=True)

    # --- internals ---------------------------------------------------------------

    def _render(self, text: str, profile: VoiceProfile) -> Clip:
        engine = self.engines.get(profile.engine)
        if engine is None:
            raise TTSError(tr("Неизвестный движок: {name}", name=profile.engine))
        reason = engine.availability()
        if reason:
            raise TTSError(reason)
        clip = engine.synthesize(text, profile)
        if profile.rvc_enabled and profile.rvc_model:
            clip = self.rvc.convert(prepare_clip(clip), profile.rvc_model, profile.rvc_pitch, profile.rvc_method)
        clip = prepare_clip(clip)
        if len(clip.samples) == 0:
            raise TTSError(tr("Голос вернул тишину"))
        return clip

    def _warm_one(self, text: str, profile: VoiceProfile) -> None:
        try:
            self.synthesize(text, profile, persist=True)
        except Exception as exc:
            self._failed[cache_key(text, profile)] = time.monotonic()
            log.debug("prewarm failed for %r: %s", text, exc)

    def _memory_has(self, key: str) -> bool:
        with self._lock:
            return key in self._memory

    def _memory_get(self, key: str) -> Clip | None:
        with self._lock:
            cached = self._memory.get(key)
            if cached is None:
                return None
            self._memory.move_to_end(key)
        return cached.clip()

    def _memory_put(self, key: str, clip: Clip) -> None:
        cached = _Cached(clip)
        with self._lock:
            old = self._memory.pop(key, None)
            if old is not None:
                self._memory_bytes -= old.nbytes
            self._memory[key] = cached
            self._memory_bytes += cached.nbytes
            while self._memory_bytes > MEMORY_CACHE_BYTES and len(self._memory) > 1:
                _key, dropped = self._memory.popitem(last=False)
                self._memory_bytes -= dropped.nbytes

    def _disk_get(self, key: str) -> Clip | None:
        path = self._disk / f"{key}.wav"
        if not path.exists():
            return None
        try:
            samples, rate = sf.read(path, dtype="float32", always_2d=False)
        except Exception:
            path.unlink(missing_ok=True)
            return None
        clip = Clip(samples, int(rate))
        self._memory_put(key, clip)
        return clip

    def _disk_put(self, key: str, clip: Clip) -> None:
        path = self._disk / f"{key}.wav"
        if path.exists():
            return
        try:
            sf.write(path, clip.samples, clip.sample_rate, subtype="PCM_16")
        except Exception as exc:
            log.debug("cache write failed: %s", exc)

    def _prune_disk(self) -> None:
        try:
            files = sorted(self._disk.glob("*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)
        except OSError:
            return
        for old in files[DISK_CACHE_FILES:]:
            old.unlink(missing_ok=True)
