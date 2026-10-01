"""Soundboard files: import into the sounds folder, decode, cache."""

from __future__ import annotations

import filecmp
import logging
import shutil
import threading
from collections import OrderedDict
from pathlib import Path

import numpy as np

from kmuted import paths
from kmuted.config import Sound
from kmuted.i18n import tr

log = logging.getLogger(__name__)

AUDIO_EXTS = (".mp3", ".wav", ".ogg", ".flac", ".opus", ".aiff", ".aif")
CACHE_BYTES = 48 * 1024 * 1024
MAX_SECONDS = 15 * 60


class SoundError(RuntimeError):
    pass


def resolve_path(sound: Sound) -> Path:
    path = Path(sound.file)
    return path if path.is_absolute() else paths.sounds_dir() / path


def import_file(src: str | Path) -> str:
    """Copy ``src`` into the sounds folder; returns the stored file name."""
    src = Path(src)
    if src.suffix.lower() not in AUDIO_EXTS:
        raise SoundError(tr("Формат {ext} не поддерживается. Подойдут: {exts}", ext=src.suffix, exts=", ".join(AUDIO_EXTS)))
    folder = paths.sounds_dir()
    if src.parent.resolve() == folder.resolve():
        return src.name
    dest = folder / src.name
    n = 1
    while dest.exists():
        if filecmp.cmp(src, dest, shallow=False):
            return dest.name  # the same file was added before: no second copy
        dest = folder / f"{src.stem} ({n}){src.suffix}"
        n += 1
    shutil.copy2(src, dest)
    return dest.name


def import_sounds(sounds: list[Sound], files) -> tuple[list[Sound], list[str]]:
    """Add audio files to the soundboard list ``sounds`` (in place).

    Returns the sounds for ``files`` (existing entries are reused) and the
    error messages of files that could not be added.
    """
    result: list[Sound] = []
    errors: list[str] = []
    for src in files:
        try:
            stored = import_file(src)
        except (SoundError, OSError) as exc:
            errors.append(str(exc))
            continue
        sound = next((x for x in sounds if x.file == stored), None)
        if sound is None:
            sound = Sound(name=nice_name(stored), file=stored)
            sounds.append(sound)
        result.append(sound)
    return result, errors


def nice_name(file_name: str) -> str:
    stem = Path(file_name).stem
    return stem.replace("_", " ").replace("-", " ").strip()[:40] or file_name


class SoundLibrary:
    """Decodes files once and keeps them as mono int16 (half the RAM)."""

    def __init__(self) -> None:
        self._cache: OrderedDict[str, tuple[np.ndarray, int]] = OrderedDict()
        self._bytes = 0
        self._lock = threading.Lock()

    def load(self, sound: Sound) -> tuple[np.ndarray, int]:
        path = resolve_path(sound)
        key = f"{path}|{path.stat().st_mtime if path.exists() else 0}"
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None:
                self._cache.move_to_end(key)
                return hit
        pcm, rate = self._decode(path)
        with self._lock:
            self._cache[key] = (pcm, rate)
            self._bytes += pcm.nbytes
            while self._bytes > CACHE_BYTES and len(self._cache) > 1:
                _k, (old, _r) = self._cache.popitem(last=False)
                self._bytes -= old.nbytes
        return pcm, rate

    @staticmethod
    def _decode(path: Path) -> tuple[np.ndarray, int]:
        if not path.exists():
            raise SoundError(tr("Файл не найден: {path}", path=path))
        try:
            import soundfile as sf

            info = sf.info(str(path))
            if info.duration > MAX_SECONDS:
                raise SoundError(tr("Файл слишком длинный ({min} мин). Максимум — 15 минут.", min=int(info.duration // 60)))
            data, rate = sf.read(str(path), dtype="int16", always_2d=True)
        except SoundError:
            raise
        except Exception as exc:
            raise SoundError(tr("Не удалось открыть «{name}»: {error}", name=path.name, error=exc)) from exc
        mono = data.mean(axis=1).astype(np.int16) if data.shape[1] > 1 else data[:, 0].copy()
        return mono, int(rate)

    def duration(self, sound: Sound) -> float:
        try:
            import soundfile as sf

            return float(sf.info(str(resolve_path(sound))).duration)
        except Exception:
            return 0.0

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._bytes = 0
