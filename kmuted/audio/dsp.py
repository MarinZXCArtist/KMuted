"""Small numpy helpers for speech clips."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Clip:
    """Mono float32 audio in [-1, 1]."""

    samples: np.ndarray
    sample_rate: int

    @property
    def duration(self) -> float:
        return len(self.samples) / float(self.sample_rate or 1)


def to_mono_float(data: np.ndarray) -> np.ndarray:
    data = np.asarray(data)
    if data.dtype.kind == "i":
        data = data.astype(np.float32) / float(np.iinfo(data.dtype).max)
    elif data.dtype.kind == "u":
        info = np.iinfo(data.dtype)
        data = (data.astype(np.float32) - (info.max + 1) / 2) / ((info.max + 1) / 2)
    data = data.astype(np.float32, copy=False)
    if data.ndim == 2:
        data = data.mean(axis=1)
    return np.ascontiguousarray(data.reshape(-1), dtype=np.float32)


def resample(samples: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    """Linear-interpolation resampler — plenty for speech."""
    if sr_from == sr_to or len(samples) == 0:
        return samples.astype(np.float32, copy=False)
    n_out = max(1, int(round(len(samples) * sr_to / sr_from)))
    src_pos = np.arange(n_out, dtype=np.float64) * (sr_from / sr_to)
    return np.interp(src_pos, np.arange(len(samples)), samples).astype(np.float32)


def to_channels(mono: np.ndarray, channels: int) -> np.ndarray:
    """(n,) mono -> (n, channels) interleavable frame block."""
    mono = mono.reshape(-1, 1)
    return np.repeat(mono, channels, axis=1) if channels > 1 else mono


def trim_silence(samples: np.ndarray, sample_rate: int, threshold_db: float = -45.0, keep_ms: int = 30) -> np.ndarray:
    """Cut leading/trailing near-silence so speech starts right away."""
    if len(samples) == 0:
        return samples
    threshold = 10 ** (threshold_db / 20.0)
    loud = np.flatnonzero(np.abs(samples) > threshold)
    if len(loud) == 0:
        return samples[:0]
    keep = int(sample_rate * keep_ms / 1000)
    start = max(0, loud[0] - keep)
    end = min(len(samples), loud[-1] + keep + 1)
    return samples[start:end]


def fade_edges(samples: np.ndarray, sample_rate: int, ms: int = 5) -> np.ndarray:
    """Short fade in/out to avoid clicks."""
    n = min(len(samples) // 2, int(sample_rate * ms / 1000))
    if n <= 0:
        return samples
    out = samples.copy()
    ramp = np.linspace(0.0, 1.0, n, dtype=np.float32)
    out[:n] *= ramp
    out[-n:] *= ramp[::-1]
    return out


def apply_gain(samples: np.ndarray, percent: int) -> np.ndarray:
    if percent == 100:
        return samples
    return (samples * (percent / 100.0)).astype(np.float32)


def silence(sample_rate: int, ms: int) -> np.ndarray:
    return np.zeros(int(sample_rate * ms / 1000), dtype=np.float32)


def prepare_clip(clip: Clip) -> Clip:
    """Standard post-processing after synthesis."""
    samples = to_mono_float(clip.samples)
    samples = trim_silence(samples, clip.sample_rate)
    samples = fade_edges(samples, clip.sample_rate)
    peak = float(np.max(np.abs(samples))) if len(samples) else 0.0
    if peak > 1.0:
        samples = samples / peak
    return Clip(samples, clip.sample_rate)
