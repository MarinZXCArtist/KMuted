"""Playback into the virtual microphone and the user's headphones.

Two long-lived output streams ("sinks"):

* **mic** — the virtual cable input; whatever plays here is what others
  hear. Optionally the real microphone is mixed in (passthrough).
* **monitor** — your headphones, so you hear what was said.

Keeping the streams open avoids device-open latency on every phrase.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable

import numpy as np

from kmuted.audio import devices
from kmuted.audio.dsp import Clip, resample, silence, to_channels

log = logging.getLogger(__name__)

# Generous buffers: Python callbacks share the GIL with the UI, and speech
# doesn't need lower latency than this.
STREAM_LATENCY_S = 0.06


@dataclass
class _Item:
    frames: np.ndarray  # (n, channels)
    pos: int = 0


class MixerCore:
    """Sequential clip queue + live passthrough, rendered in audio callbacks.

    Pure numpy and thread-safe; the sounddevice callback just calls
    :meth:`render`. ``on_start``/``on_idle`` fire (from the audio thread)
    when the clip queue goes from empty to busy and back.
    """

    PASSTHROUGH_MAX_S = 0.25
    PASSTHROUGH_TARGET_S = 0.06

    def __init__(
        self,
        sample_rate: int,
        channels: int,
        on_start: Callable[[], None] | None = None,
        on_idle: Callable[[], None] | None = None,
    ) -> None:
        self.sample_rate = int(sample_rate)
        self.channels = int(channels)
        self.gain = 1.0
        self.passthrough_gain = 1.0
        self._on_start = on_start
        self._on_idle = on_idle
        self._lock = threading.Lock()
        self._queue: deque[_Item] = deque()
        self._busy = False
        self._pt: deque[np.ndarray] = deque()
        self._pt_len = 0

    # --- clips -------------------------------------------------------------

    def enqueue(self, clip: Clip, lead_ms: int = 0) -> None:
        mono = resample(clip.samples, clip.sample_rate, self.sample_rate)
        if lead_ms > 0:
            mono = np.concatenate([silence(self.sample_rate, lead_ms), mono])
        if len(mono) == 0:
            return
        item = _Item(to_channels(mono, self.channels))
        start = False
        with self._lock:
            self._queue.append(item)
            if not self._busy:
                self._busy = start = True
        if start and self._on_start:
            self._on_start()

    def clear(self) -> None:
        with self._lock:
            self._queue.clear()
            was_busy, self._busy = self._busy, False
        if was_busy and self._on_idle:
            self._on_idle()

    @property
    def busy(self) -> bool:
        return self._busy

    # --- passthrough -------------------------------------------------------

    def push_passthrough(self, mono: np.ndarray) -> None:
        with self._lock:
            self._pt.append(np.asarray(mono, dtype=np.float32).reshape(-1))
            self._pt_len += len(self._pt[-1])
            limit = int(self.sample_rate * self.PASSTHROUGH_MAX_S)
            if self._pt_len > limit:  # clock drift / stall: drop old audio
                self._drop_passthrough(self._pt_len - int(self.sample_rate * self.PASSTHROUGH_TARGET_S))

    def clear_passthrough(self) -> None:
        with self._lock:
            self._pt.clear()
            self._pt_len = 0

    def _drop_passthrough(self, n: int) -> None:
        while n > 0 and self._pt:
            head = self._pt[0]
            if len(head) <= n:
                n -= len(head)
                self._pt_len -= len(head)
                self._pt.popleft()
            else:
                self._pt[0] = head[n:]
                self._pt_len -= n
                n = 0

    def _take_passthrough(self, frames: int) -> np.ndarray | None:
        if self._pt_len < frames:
            return None
        out = np.empty(frames, dtype=np.float32)
        filled = 0
        while filled < frames:
            head = self._pt[0]
            take = min(len(head), frames - filled)
            out[filled : filled + take] = head[:take]
            filled += take
            if take == len(head):
                self._pt.popleft()
            else:
                self._pt[0] = head[take:]
        self._pt_len -= frames
        return out

    # --- rendering ---------------------------------------------------------

    def render(self, frames: int) -> np.ndarray:
        out = np.zeros((frames, self.channels), dtype=np.float32)
        went_idle = False
        with self._lock:
            filled = 0
            while filled < frames and self._queue:
                item = self._queue[0]
                take = min(frames - filled, len(item.frames) - item.pos)
                out[filled : filled + take] = item.frames[item.pos : item.pos + take]
                item.pos += take
                filled += take
                if item.pos >= len(item.frames):
                    self._queue.popleft()
            if self.gain != 1.0:
                out *= self.gain
            if self._busy and not self._queue:
                self._busy = False
                went_idle = True
            live = self._take_passthrough(frames)
        if live is not None:
            out += (live * self.passthrough_gain)[:, None]
        np.clip(out, -1.0, 1.0, out=out)
        if went_idle and self._on_idle:
            self._on_idle()
        return out


class OutputSink:
    """A running sounddevice OutputStream fed by a :class:`MixerCore`."""

    def __init__(
        self,
        candidates: list[devices.DeviceInfo],
        label: str,
        on_start: Callable[[], None] | None = None,
        on_idle: Callable[[], None] | None = None,
    ) -> None:
        sd = devices.get_sd()
        self.label = label
        self.device: devices.DeviceInfo | None = None
        self.stream = None
        self.mixer: MixerCore | None = None
        errors = []
        for dev in candidates:
            try:
                self._open(sd, dev, on_start, on_idle)
                self.device = dev
                break
            except Exception as exc:
                errors.append(f"{dev.hostapi}: {exc}")
                log.warning("cannot open %s on %s: %s", dev.name, dev.hostapi, exc)
        if self.stream is None:
            raise devices.AudioUnavailable(f"Не удалось открыть «{label}»: " + "; ".join(errors or ["устройство не найдено"]))
        log.info("%s -> %s [%s, %d Hz]", label, self.device.name, self.device.hostapi, self.mixer.sample_rate)

    def _open(self, sd, dev: devices.DeviceInfo, on_start, on_idle) -> None:
        rate = int(dev.default_samplerate) or 48000
        channels = max(1, min(2, dev.max_output))
        extra = None
        if dev.hostapi == "Windows WASAPI":
            try:
                extra = sd.WasapiSettings(auto_convert=True)
            except TypeError:
                extra = None
        mixer = MixerCore(rate, channels, on_start, on_idle)

        def callback(outdata, frames, _time, status):  # audio thread
            outdata[:] = mixer.render(frames)

        stream = sd.OutputStream(
            device=dev.index,
            samplerate=rate,
            channels=channels,
            dtype="float32",
            latency=STREAM_LATENCY_S,
            callback=callback,
            extra_settings=extra,
        )
        stream.start()
        self.stream, self.mixer = stream, mixer

    @property
    def alive(self) -> bool:
        try:
            return bool(self.stream is not None and self.stream.active)
        except Exception:
            return False

    def close(self) -> None:
        if self.stream is not None:
            try:
                self.stream.abort()
                self.stream.close()
            except Exception:
                pass
            self.stream = None


class PassthroughInput:
    """Feeds the real microphone into the mic sink."""

    def __init__(self, candidates: list[devices.DeviceInfo], mixer: MixerCore) -> None:
        sd = devices.get_sd()
        self.stream = None
        errors = []
        for dev in candidates:
            for rate in (mixer.sample_rate, int(dev.default_samplerate)):
                try:
                    self.stream = self._open(sd, dev, rate, mixer)
                    log.info("passthrough <- %s [%s, %d Hz]", dev.name, dev.hostapi, rate)
                    return
                except Exception as exc:
                    errors.append(f"{dev.hostapi}@{rate}: {exc}")
        raise devices.AudioUnavailable("Не удалось открыть микрофон: " + "; ".join(errors or ["устройство не найдено"]))

    @staticmethod
    def _open(sd, dev: devices.DeviceInfo, rate: int, mixer: MixerCore):
        target = mixer.sample_rate

        def callback(indata, frames, _time, status):
            block = indata[:, 0]
            if rate != target:
                block = resample(block, rate, target)
            mixer.push_passthrough(block.copy())

        extra = None
        if dev.hostapi == "Windows WASAPI":
            try:
                extra = sd.WasapiSettings(auto_convert=True)
            except TypeError:
                extra = None
        stream = sd.InputStream(
            device=dev.index,
            samplerate=rate,
            channels=1,
            dtype="float32",
            latency=STREAM_LATENCY_S,
            callback=callback,
            extra_settings=extra,
        )
        stream.start()
        return stream

    def close(self) -> None:
        if self.stream is not None:
            try:
                self.stream.abort()
                self.stream.close()
            except Exception:
                pass
            self.stream = None


class AudioEngine:
    """Owns the sinks; the rest of the app just calls :meth:`play`."""

    def __init__(
        self,
        on_mic_start: Callable[[], None] | None = None,
        on_mic_idle: Callable[[], None] | None = None,
    ) -> None:
        self._on_mic_start = on_mic_start
        self._on_mic_idle = on_mic_idle
        self._lock = threading.RLock()
        self.mic: OutputSink | None = None
        self.monitor: OutputSink | None = None
        self.passthrough: PassthroughInput | None = None
        self._settings = None
        self._keys: dict[str, tuple] = {}
        self._last_retry = 0.0
        self.errors: dict[str, str] = {}

    # --- configuration -----------------------------------------------------

    def configure(self, settings) -> None:
        """Apply :class:`AudioSettings`; reopens only what changed."""
        with self._lock:
            self._settings = settings
            mic_key = (settings.mic_device,)
            mon_key = (settings.monitor_enabled, settings.monitor_device, settings.mic_device)
            pt_key = (settings.passthrough_enabled, settings.passthrough_device, mic_key)
            mic_dead = self.mic is not None and not self.mic.alive
            if self._keys.get("mic") != mic_key or mic_dead:
                self._close_passthrough()
                self._open_mic(settings)
                self._keys["mic"] = mic_key
                self._keys.pop("pt", None)
            if self._keys.get("monitor") != mon_key or (self.monitor and not self.monitor.alive):
                self._open_monitor(settings)
                self._keys["monitor"] = mon_key
            if self._keys.get("pt") != pt_key:
                self._open_passthrough(settings)
                self._keys["pt"] = pt_key
            self._apply_volumes(settings)

    def _open_mic(self, s) -> None:
        if self.mic:
            self.mic.close()
            self.mic = None
        self.errors.pop("mic", None)
        if not s.mic_device:
            self.errors["mic"] = "Виртуальный микрофон не выбран"
            return
        try:
            self.mic = OutputSink(
                devices.find_candidates(s.mic_device, "output"),
                "виртуальный микрофон",
                on_start=self._mic_started,
                on_idle=self._mic_idle,
            )
        except devices.AudioUnavailable as exc:
            self.errors["mic"] = str(exc)

    def _open_monitor(self, s) -> None:
        if self.monitor:
            self.monitor.close()
            self.monitor = None
        self.errors.pop("monitor", None)
        if not s.monitor_enabled:
            return
        try:
            if s.monitor_device:
                candidates = devices.find_candidates(s.monitor_device, "output")
            else:
                candidates = devices.default_output_candidates()
            if self.mic and self.mic.device and any(c.name == self.mic.device.name for c in candidates[:1]):
                self.errors["monitor"] = "Наушники совпадают с виртуальным микрофоном — прослушка отключена"
                return
            self.monitor = OutputSink(candidates, "наушники")
        except devices.AudioUnavailable as exc:
            self.errors["monitor"] = str(exc)

    def _open_passthrough(self, s) -> None:
        self._close_passthrough()
        self.errors.pop("passthrough", None)
        if not (s.passthrough_enabled and self.mic):
            return
        try:
            if s.passthrough_device:
                candidates = devices.find_candidates(s.passthrough_device, "input")
            else:
                sd = devices.get_sd()
                name = sd.query_devices(kind="input")["name"]
                candidates = devices.find_candidates(name, "input")
            self.passthrough = PassthroughInput(candidates, self.mic.mixer)
        except Exception as exc:
            self.errors["passthrough"] = str(exc)

    def _close_passthrough(self) -> None:
        if self.passthrough:
            self.passthrough.close()
            self.passthrough = None
        if self.mic and self.mic.mixer:
            self.mic.mixer.clear_passthrough()

    def _apply_volumes(self, s) -> None:
        if self.mic and self.mic.mixer:
            self.mic.mixer.gain = s.mic_volume / 100.0
            self.mic.mixer.passthrough_gain = s.passthrough_volume / 100.0
        if self.monitor and self.monitor.mixer:
            self.monitor.mixer.gain = s.monitor_volume / 100.0

    # --- playback ----------------------------------------------------------

    def play(self, clip: Clip, lead_ms: int = 0, monitor_only: bool = False) -> bool:
        """Queue ``clip``; returns False if it could not go anywhere."""
        with self._lock:
            self._recover()
            sent = False
            if self.mic and not monitor_only:
                self.mic.mixer.enqueue(clip, lead_ms)
                sent = True
            if self.monitor:
                self.monitor.mixer.enqueue(clip, lead_ms)
                sent = True
            return sent

    def _recover(self) -> None:
        """Reopen devices that died or were missing (e.g. cable re-plugged)."""
        s = self._settings
        if s is None:
            return
        dead = (self.mic and not self.mic.alive) or (self.monitor and not self.monitor.alive)
        missing = (s.mic_device and self.mic is None) or (s.monitor_enabled and self.monitor is None)
        if dead or (missing and time.monotonic() - self._last_retry > 5.0):
            self._last_retry = time.monotonic()
            self._keys.clear()
            self.configure(s)

    def retry(self) -> None:
        """Force reopening all devices (after "refresh devices")."""
        with self._lock:
            self._keys.clear()
            if self._settings is not None:
                self.configure(self._settings)

    def stop(self) -> None:
        with self._lock:
            for sink in (self.mic, self.monitor):
                if sink and sink.mixer:
                    sink.mixer.clear()

    @property
    def mic_ready(self) -> bool:
        return bool(self.mic and self.mic.alive)

    @property
    def mic_busy(self) -> bool:
        return bool(self.mic and self.mic.mixer and self.mic.mixer.busy)

    def close(self) -> None:
        with self._lock:
            self._close_passthrough()
            for sink in (self.mic, self.monitor):
                if sink:
                    sink.close()
            self.mic = self.monitor = None
            self._keys.clear()

    # --- callbacks from the audio thread ------------------------------------

    def _mic_started(self) -> None:
        if self._on_mic_start:
            self._on_mic_start()

    def _mic_idle(self) -> None:
        if self._on_mic_idle:
            self._on_mic_idle()
