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
from typing import Callable

import numpy as np

from kmuted.audio import devices
from kmuted.audio.dsp import Clip, resample
from kmuted.i18n import tr

log = logging.getLogger(__name__)

# Generous buffers: Python callbacks share the GIL with the UI, and speech
# doesn't need lower latency than this.
STREAM_LATENCY_S = 0.06


class _Voice:
    """One playing clip, resampled block by block (no full-length copies)."""

    __slots__ = ("src", "scale", "ratio", "pos", "gain", "delay", "tag")

    def __init__(self, samples: np.ndarray, src_rate: int, dst_rate: int, gain: float = 1.0,
                 delay_frames: int = 0, tag: str = "") -> None:
        samples = np.asarray(samples).reshape(-1)
        if samples.dtype == np.int16:
            self.scale = 1.0 / 32768.0
        else:
            samples = samples.astype(np.float32, copy=False)
            self.scale = 1.0
        self.src = samples
        self.ratio = float(src_rate) / float(dst_rate)
        self.pos = 0.0
        self.gain = gain
        self.delay = int(delay_frames)
        self.tag = tag

    @property
    def done(self) -> bool:
        return self.delay <= 0 and self.pos >= len(self.src)

    def render_into(self, out: np.ndarray, offset: int = 0) -> int:
        """Add up to ``len(out) - offset`` frames into mono ``out``; returns frames used."""
        room = len(out) - offset
        used = 0
        if self.delay > 0:
            skip = min(self.delay, room)
            self.delay -= skip
            used += skip
            room -= skip
        n_src = len(self.src)
        if room <= 0 or self.pos >= n_src:
            return used
        count = min(room, int(np.ceil((n_src - self.pos) / self.ratio)))
        idx = self.pos + np.arange(count, dtype=np.float64) * self.ratio
        i0 = idx.astype(np.int64)
        np.minimum(i0, n_src - 1, out=i0)
        frac = (idx - i0).astype(np.float32)
        i1 = np.minimum(i0 + 1, n_src - 1)
        a = self.src[i0].astype(np.float32)
        b = self.src[i1].astype(np.float32)
        chunk = (a + (b - a) * frac) * (self.scale * self.gain)
        start = offset + used
        out[start : start + count] += chunk
        self.pos += count * self.ratio
        return used + count


class MixerCore:
    """Speech queue + overlapping sounds + live passthrough, mixed per block.

    * speech plays one clip after another (a queue);
    * sounds (soundboard) play on top of speech and of each other;
    * the real microphone can be mixed in (passthrough).

    Pure numpy and thread-safe; the sounddevice callback calls
    :meth:`render`. ``on_start``/``on_idle`` fire (from the audio thread)
    when content starts playing and when everything has finished.
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
        self.muted = False  # content muted (passthrough still flows)
        self.level = 0.0  # peak of the last rendered block (for meters)
        self._on_start = on_start
        self._on_idle = on_idle
        self._lock = threading.Lock()
        self._queue: deque[_Voice] = deque()
        self._sounds: list[_Voice] = []
        self._busy = False
        self._pt: deque[np.ndarray] = deque()
        self._pt_len = 0

    # --- content -------------------------------------------------------------

    def enqueue(self, clip: Clip, lead_ms: int = 0, gain: float = 1.0) -> None:
        """Queue speech after whatever speech is already playing."""
        if len(clip.samples) == 0:
            return
        delay = int(self.sample_rate * lead_ms / 1000) if lead_ms > 0 else 0
        self._add(_Voice(clip.samples, clip.sample_rate, self.sample_rate, gain, delay), queue=True)

    def play_sound(self, samples: np.ndarray, sample_rate: int, tag: str, gain: float = 1.0,
                   lead_ms: int = 0, restart: bool = True) -> None:
        """Play a sound on top of everything else (soundboard)."""
        if len(samples) == 0:
            return
        delay = int(self.sample_rate * lead_ms / 1000) if lead_ms > 0 else 0
        voice = _Voice(samples, sample_rate, self.sample_rate, gain, delay, tag)
        with self._lock:
            if restart and tag:
                self._sounds = [v for v in self._sounds if v.tag != tag]
        self._add(voice, queue=False)

    def _add(self, voice: _Voice, queue: bool) -> None:
        start = False
        with self._lock:
            (self._queue.append if queue else self._sounds.append)(voice)
            if not self._busy:
                self._busy = start = True
        if start and self._on_start:
            self._on_start()

    def stop_sounds(self, tag: str | None = None) -> None:
        with self._lock:
            self._sounds = [] if tag is None else [v for v in self._sounds if v.tag != tag]
        self._maybe_idle()

    def clear_speech(self) -> None:
        with self._lock:
            self._queue.clear()
        self._maybe_idle()

    def clear(self) -> None:
        with self._lock:
            self._queue.clear()
            self._sounds = []
        self._maybe_idle()

    def playing_tags(self) -> set[str]:
        with self._lock:
            return {v.tag for v in self._sounds}

    def _maybe_idle(self) -> None:
        with self._lock:
            idle = self._busy and not self._queue and not self._sounds
            if idle:
                self._busy = False
        if idle and self._on_idle:
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
        mono = np.zeros(frames, dtype=np.float32)
        went_idle = False
        with self._lock:
            filled = 0
            while filled < frames and self._queue:
                voice = self._queue[0]
                filled += voice.render_into(mono, filled)
                if voice.done:
                    self._queue.popleft()
                else:
                    break
            for voice in self._sounds:
                voice.render_into(mono)
            if self._sounds:
                self._sounds = [v for v in self._sounds if not v.done]
            if self.muted:
                mono[:] = 0.0
            elif self.gain != 1.0:
                mono *= self.gain
            if self._busy and not self._queue and not self._sounds:
                self._busy = False
                went_idle = True
            live = self._take_passthrough(frames)
        if live is not None:
            mono += live * self.passthrough_gain
        np.clip(mono, -1.0, 1.0, out=mono)
        self.level = float(np.max(np.abs(mono))) if frames else 0.0
        out = np.repeat(mono[:, None], self.channels, axis=1) if self.channels > 1 else mono[:, None]
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
            raise devices.AudioUnavailable(tr("Не удалось открыть «{name}»: ", name=label) + "; ".join(errors or [tr("устройство не найдено")]))
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


class InputTap:
    """Reads a real microphone: feeds the mic sink (passthrough) and/or a level meter."""

    def __init__(
        self,
        candidates: list[devices.DeviceInfo],
        mixer: MixerCore | None = None,
        label: str = "passthrough",
    ) -> None:
        sd = devices.get_sd()
        self.stream = None
        self.level = 0.0
        self.device: devices.DeviceInfo | None = None
        errors = []
        for dev in candidates:
            rates = [int(dev.default_samplerate)]
            if mixer is not None:
                rates.insert(0, mixer.sample_rate)
            for rate in rates:
                try:
                    self.stream = self._open(sd, dev, rate, mixer)
                    self.device = dev
                    log.info("%s <- %s [%s, %d Hz]", label, dev.name, dev.hostapi, rate)
                    return
                except Exception as exc:
                    errors.append(f"{dev.hostapi}@{rate}: {exc}")
        raise devices.AudioUnavailable(tr("Не удалось открыть микрофон: ") + "; ".join(errors or [tr("устройство не найдено")]))

    def _open(self, sd, dev: devices.DeviceInfo, rate: int, mixer: MixerCore | None):
        target = mixer.sample_rate if mixer is not None else rate

        def callback(indata, frames, _time, status):
            block = indata[:, 0]
            self.level = float(np.max(np.abs(block))) if frames else 0.0
            if mixer is None:
                return
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


PassthroughInput = InputTap  # backwards-compatible name


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
        self.passthrough: InputTap | None = None
        self.meter: InputTap | None = None  # mic level meter while the Audio page is open
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
            self.errors["mic"] = tr("Виртуальный микрофон не выбран")
            return
        try:
            self.mic = OutputSink(
                devices.find_candidates(s.mic_device, "output"),
                tr("виртуальный микрофон"),
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
                self.errors["monitor"] = tr("Наушники совпадают с виртуальным микрофоном — прослушка отключена")
                return
            self.monitor = OutputSink(candidates, tr("наушники"))
        except devices.AudioUnavailable as exc:
            self.errors["monitor"] = str(exc)

    def _open_passthrough(self, s) -> None:
        self._close_passthrough()
        if s.passthrough_enabled and self.meter is not None:
            self.meter.close()  # passthrough reports the level itself
            self.meter = None
        self.errors.pop("passthrough", None)
        if not (s.passthrough_enabled and self.mic):
            return
        try:
            self.passthrough = InputTap(self._input_candidates(s.passthrough_device), self.mic.mixer)
        except Exception as exc:
            self.errors["passthrough"] = str(exc)

    def _close_passthrough(self) -> None:
        if self.passthrough:
            self.passthrough.close()
            self.passthrough = None
        if self.mic and self.mic.mixer:
            self.mic.mixer.clear_passthrough()

    def _input_candidates(self, name: str) -> list[devices.DeviceInfo]:
        if name:
            return devices.find_candidates(name, "input")
        sd = devices.get_sd()
        return devices.find_candidates(sd.query_devices(kind="input")["name"], "input")

    def _apply_volumes(self, s) -> None:
        if self.mic and self.mic.mixer:
            self.mic.mixer.gain = s.mic_volume / 100.0
            self.mic.mixer.muted = bool(getattr(s, "mic_muted", False))
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

    def play_sound(self, samples, sample_rate: int, tag: str, gain: float = 1.0, lead_ms: int = 0,
                   monitor_only: bool = False, restart: bool = True) -> bool:
        """Soundboard: plays on top of speech. Returns False if nothing to play into."""
        with self._lock:
            self._recover()
            sent = False
            if self.mic and not monitor_only:
                self.mic.mixer.play_sound(samples, sample_rate, tag, gain, lead_ms, restart)
                sent = True
            if self.monitor:
                self.monitor.mixer.play_sound(samples, sample_rate, tag, gain, lead_ms, restart)
                sent = True
            return sent

    def stop_sounds(self, tag: str | None = None) -> None:
        with self._lock:
            for sink in (self.mic, self.monitor):
                if sink and sink.mixer:
                    sink.mixer.stop_sounds(tag)

    def playing_sounds(self) -> set[str]:
        sink = self.mic or self.monitor
        return sink.mixer.playing_tags() if sink and sink.mixer else set()

    def stop_speech(self) -> None:
        with self._lock:
            for sink in (self.mic, self.monitor):
                if sink and sink.mixer:
                    sink.mixer.clear_speech()

    # --- meters ------------------------------------------------------------

    @property
    def output_level(self) -> float:
        """Peak going into the virtual mic (what others hear)."""
        return self.mic.mixer.level if self.mic and self.mic.mixer and self.mic.alive else 0.0

    @property
    def input_level(self) -> float:
        """Peak of the real microphone (passthrough stream or the meter)."""
        tap = self.passthrough or self.meter
        return tap.level if tap is not None else 0.0

    def start_meter(self) -> str:
        """Open the real mic just for the level meter (if passthrough is off)."""
        with self._lock:
            if self.passthrough is not None or self.meter is not None or self._settings is None:
                return ""
            try:
                self.meter = InputTap(self._input_candidates(self._settings.passthrough_device), None, "meter")
            except Exception as exc:
                return str(exc)
            return ""

    def stop_meter(self) -> None:
        with self._lock:
            if self.meter is not None:
                self.meter.close()
                self.meter = None

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
            if self.meter is not None:
                self.meter.close()
                self.meter = None
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
