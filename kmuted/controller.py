"""The glue: hotkeys -> overlays -> speech synthesis -> audio output."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QAbstractSpinBox, QApplication, QLineEdit, QPlainTextEdit, QTextEdit

from kmuted import config as cfgmod
from kmuted.audio import devices
from kmuted.audio.dsp import Clip
from kmuted.audio.engine import AudioEngine
from kmuted.config import Config, VoiceProfile
from kmuted.hotkeys.keys import format_combo, parse_combo
from kmuted.hotkeys.listener import GlobalHotkeys
from kmuted.hotkeys.ptt import PushToTalk
from kmuted.tts.base import TTSError
from kmuted.tts.manager import SpeechService
from kmuted.ui.overlay_input import InputOverlay
from kmuted.ui.overlay_wheel import WheelOverlay
from kmuted.ui.widgets import HotkeyEdit

log = logging.getLogger(__name__)

STALE_REQUEST_S = 30.0
WHEEL_TOGGLE_TIMEOUT_MS = 15000


@dataclass
class _Request:
    text: str
    monitor_only: bool
    started: float
    clip: Clip | None = None
    done: bool = False


class Controller(QObject):
    # public, for the UI
    status = Signal(str)
    audio_status = Signal(str)
    error = Signal(str)
    notify = Signal(str, str)  # text, kind (info/success/warning) — shown as a toast
    speaking_changed = Signal(bool)
    config_changed = Signal(str)  # section: phrases/wheels/voices/audio/general
    hotkeys_toggled = Signal(bool)
    show_window_requested = Signal()

    # internal cross-thread plumbing
    _hotkey_down = Signal(str)
    _hotkey_up = Signal(str)
    _synth_done = Signal(int, object)
    _mic_state = Signal(bool)

    def __init__(self, config: Config, *, enable_hotkeys: bool = True, enable_audio: bool = True) -> None:
        super().__init__()
        self.config = config
        self.speech = SpeechService(config.general.rvc_server_url)
        self.audio = AudioEngine(on_mic_start=lambda: self._mic_state.emit(True), on_mic_idle=lambda: self._mic_state.emit(False))
        self.ptt = PushToTalk()
        self.hotkeys = GlobalHotkeys(on_press=self._hotkey_down.emit, on_release=self._hotkey_up.emit)
        self.input_overlay = InputOverlay()
        self.wheel_overlay = WheelOverlay()
        self._audio_enabled = enable_audio
        self._actions: dict[str, tuple] = {}
        self._requests: dict[int, _Request] = {}
        self._seq = 0
        self._next_play = 1
        self._speaking = False
        self._wheel = None
        self._wheel_combo = ""
        self._wheel_key = ""
        self._wheel_released_ticks = 0
        self._last_cursor = None

        self._hotkey_down.connect(self._on_hotkey_down, Qt.QueuedConnection)
        self._hotkey_up.connect(self._on_hotkey_up, Qt.QueuedConnection)
        self._synth_done.connect(self._on_synth_done, Qt.QueuedConnection)
        self._mic_state.connect(self._on_mic_state, Qt.QueuedConnection)

        self.input_overlay.submitted.connect(self._on_input_submitted)
        self.input_overlay.cycle_voice.connect(self._on_overlay_cycle_voice)

        self._save_timer = self._single_shot(400, self.save_now)
        self._prewarm_timer = self._single_shot(1200, self.prewarm)
        self._ptt_release_timer = self._single_shot(250, self.ptt.release)
        self._wheel_timeout = self._single_shot(WHEEL_TOGGLE_TIMEOUT_MS, self._wheel_close)
        self._wheel_tick_timer = QTimer(self)
        self._wheel_tick_timer.setInterval(16)
        self._wheel_tick_timer.timeout.connect(self._wheel_tick)

        self.apply_general()
        if enable_audio:
            self.apply_audio()
        if enable_hotkeys:
            self.hotkeys.start()
        self.rebind_hotkeys()
        self._prewarm_timer.start()

    def _single_shot(self, ms: int, slot) -> QTimer:
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(ms)
        timer.timeout.connect(slot)
        return timer

    # --- config ---------------------------------------------------------------

    def edited(self, section: str) -> None:
        """Pages call this after changing ``self.config``."""
        self._save_timer.start()
        if section in ("phrases", "wheels", "general"):
            self.rebind_hotkeys()
        if section == "audio":
            self.apply_audio()
        if section == "general":
            self.apply_general()
        if section in ("phrases", "wheels", "voices", "general"):
            self._prewarm_timer.start()
        self.config_changed.emit(section)

    def save_now(self) -> None:
        try:
            cfgmod.save_config(self.config)
        except OSError as exc:
            self.error.emit(f"Не удалось сохранить настройки: {exc}")

    def apply_general(self) -> None:
        g = self.config.general
        self.input_overlay.keep_open = g.input_keep_open
        self.input_overlay.restore_focus = g.input_restore_focus
        self.speech.rvc.set_url(g.rvc_server_url)

    def apply_audio(self) -> None:
        if not self._audio_enabled:
            return
        a = self.config.audio
        self.ptt.set_key(a.ptt_key)
        self.hotkeys.ignore_injected([self.ptt.key_name] if self.ptt.key_name else [])
        self._ptt_release_timer.setInterval(max(0, a.ptt_tail_ms))
        try:
            self.audio.configure(a)
        except devices.AudioUnavailable as exc:
            self.audio.errors["mic"] = str(exc)
        except Exception as exc:  # never let a device problem crash the app
            log.exception("audio configure failed")
            self.audio.errors["mic"] = f"Ошибка звука: {exc}"
        self.audio_status.emit(self.audio_summary())

    def detect_cable(self) -> str:
        """Find a virtual cable and select it if none is chosen; returns its name."""
        name = devices.guess_virtual_cable()
        if name and self.config.audio.mic_device != name and not self.audio.mic_ready:
            self.config.audio.mic_device = name
            self.edited("audio")
        elif name:
            self.audio.retry()
            self.audio_status.emit(self.audio_summary())
        return name

    def refresh_audio(self) -> None:
        """Re-scan devices and reopen streams (after plugging something in)."""
        if self._audio_enabled:
            self.audio.retry()
            self.audio_status.emit(self.audio_summary())

    def audio_summary(self) -> str:
        if not self._audio_enabled:
            return "Звук отключён"
        if self.audio.mic_ready:
            return f"🎙 Микрофон: {self.audio.mic.device.name}"
        return "⚠ " + self.audio.errors.get("mic", "Виртуальный микрофон не настроен")

    # --- voices ---------------------------------------------------------------

    def set_active_voice(self, voice_id: str) -> None:
        if self.config.voice_by_id(voice_id):
            self.config.general.active_voice_id = voice_id
            self.input_overlay.set_voice_name(self.config.active_voice().name)
            self.edited("general")

    def cycle_voice(self, step: int = 1) -> VoiceProfile:
        voices = self.config.voices
        current = self.config.active_voice()
        idx = voices.index(current)
        nxt = voices[(idx + step) % len(voices)]
        self.set_active_voice(nxt.id)
        self.notify.emit(f"Голос: {nxt.name}", "info")
        return nxt

    # --- speaking -------------------------------------------------------------

    def say(self, text: str, voice_id: str = "", persist: bool = False) -> None:
        """Synthesize and play through the virtual mic (and headphones)."""
        text = text.strip()
        if not text:
            return
        profile = self.config.resolve_voice(voice_id)
        if self.config.audio.playback_mode == cfgmod.PLAYBACK_INTERRUPT:
            self._drop_pending()
            self.audio.stop()
        self._enqueue(text, profile, persist, monitor_only=False)

    def preview(self, text: str, profile: VoiceProfile) -> None:
        """Play only in the headphones (voice editor test)."""
        if text.strip():
            self._enqueue(text.strip(), profile, False, monitor_only=True)

    def stop(self) -> None:
        self._drop_pending()
        self.audio.stop()
        self.ptt.release()
        self.status.emit("Остановлено")

    def _enqueue(self, text: str, profile: VoiceProfile, persist: bool, monitor_only: bool) -> None:
        self._skip_stale()
        self._seq += 1
        seq = self._seq
        self._requests[seq] = _Request(text, monitor_only, time.monotonic())
        future = self.speech.submit(text, profile, persist=persist)
        future.add_done_callback(lambda f, seq=seq: self._synth_done.emit(seq, f))
        self.status.emit(f"Синтез: «{_short(text)}»…")

    def _drop_pending(self) -> None:
        self._requests.clear()
        self._next_play = self._seq + 1

    def _skip_stale(self) -> None:
        now = time.monotonic()
        while self._next_play <= self._seq:
            req = self._requests.get(self._next_play)
            if req is None or (not req.done and now - req.started > STALE_REQUEST_S):
                self._requests.pop(self._next_play, None)
                self._next_play += 1
            else:
                break

    @Slot(int, object)
    def _on_synth_done(self, seq: int, future) -> None:
        req = self._requests.get(seq)
        if req is None:
            return  # dropped by stop/interrupt
        req.done = True
        try:
            req.clip = future.result()
        except TTSError as exc:
            self.error.emit(str(exc))
        except Exception as exc:
            log.exception("synthesis failed")
            self.error.emit(f"Ошибка синтеза: {exc}")
        # play in request order, even if a later phrase finished first
        while self._next_play in self._requests and self._requests[self._next_play].done:
            ready = self._requests.pop(self._next_play)
            self._next_play += 1
            if ready.clip is not None:
                self._play(ready)

    def _play(self, req: _Request) -> None:
        if not self._audio_enabled:
            self.status.emit(f"(звук отключён) «{_short(req.text)}»")
            return
        lead = 0
        if not req.monitor_only and self.ptt.enabled and self.audio.mic_ready:
            self._ptt_release_timer.stop()
            if not self.ptt.is_down:
                self.ptt.press()
                lead = self.config.audio.ptt_delay_ms
        if self.audio.play(req.clip, lead_ms=lead, monitor_only=req.monitor_only):
            where = "в наушники" if req.monitor_only or not self.audio.mic_ready else "в микрофон"
            self.status.emit(f"▶ {where}: «{_short(req.text)}»")
        else:
            self.error.emit("Некуда выводить звук: выберите виртуальный микрофон на вкладке «Звук».")

    @Slot(bool)
    def _on_mic_state(self, busy: bool) -> None:
        if busy:
            self._ptt_release_timer.stop()
        elif self.ptt.is_down:
            self._ptt_release_timer.start()
        if busy != self._speaking:
            self._speaking = busy
            self.speaking_changed.emit(busy)

    # --- hotkeys --------------------------------------------------------------

    def hotkey_owners(self) -> dict[str, list[tuple[str, str]]]:
        """combo -> [(owner key, human name)] for everything bound to it."""
        g = self.config.general
        owners: dict[str, list[tuple[str, str]]] = {}

        def add(combo: str, key: str, name: str) -> None:
            if combo:
                owners.setdefault(combo, []).append((key, name))

        add(g.input_hotkey, "general:input_hotkey", "Окно ввода")
        add(g.stop_hotkey, "general:stop_hotkey", "Стоп")
        add(g.toggle_hotkeys_hotkey, "general:toggle_hotkeys_hotkey", "Вкл/выкл горячие клавиши")
        add(g.next_voice_hotkey, "general:next_voice_hotkey", "Следующий голос")
        for w in self.config.wheels:
            add(w.hotkey, f"wheel:{w.id}", f"Колесо «{w.name}»")
        for p in self.config.phrases:
            add(p.hotkey, f"phrase:{p.id}", f"Фраза «{_short(p.text, 24)}»")
        return owners

    def hotkey_conflict(self, combo: str, owner_key: str) -> str:
        """Warning text if ``combo`` is already used by someone else."""
        if not combo:
            return ""
        others = [name for key, name in self.hotkey_owners().get(combo, []) if key != owner_key]
        if not others:
            return ""
        return f"⚠ {format_combo(combo)} уже занято: {', '.join(others)}"

    def rebind_hotkeys(self) -> None:
        g = self.config.general
        actions: dict[str, tuple] = {}

        def add(combo: str, action: tuple) -> None:
            if combo and combo not in actions:
                actions[combo] = action

        add(g.toggle_hotkeys_hotkey, ("toggle",))
        add(g.input_hotkey, ("input",))
        add(g.stop_hotkey, ("stop",))
        add(g.next_voice_hotkey, ("next_voice",))
        for w in self.config.wheels:
            add(w.hotkey, ("wheel", w.id))
        for p in self.config.phrases:
            add(p.hotkey, ("phrase", p.id))
        self._actions = actions
        bindings = set(actions)
        if self._wheel is not None and self.config.general.wheel_mode == cfgmod.WHEEL_TOGGLE:
            bindings.add("esc")
        self.hotkeys.set_bindings(bindings)

    def set_hotkeys_enabled(self, enabled: bool) -> None:
        self.config.general.hotkeys_enabled = enabled
        self._save_timer.start()
        self.hotkeys_toggled.emit(enabled)
        self.notify.emit(
            "Горячие клавиши включены" if enabled else "Горячие клавиши на паузе",
            "success" if enabled else "warning",
        )

    def hotkeys_error(self) -> str:
        return self.hotkeys.error

    def _typing_in_app(self) -> bool:
        if HotkeyEdit.any_capturing():
            return True
        if QApplication.activeWindow() is None:
            return False
        focus = QApplication.focusWidget()
        return isinstance(focus, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox))

    @Slot(str)
    def _on_hotkey_down(self, combo: str) -> None:
        if combo == "esc" and self._wheel is not None:
            self._wheel_close()
            return
        action = self._actions.get(combo)
        if action is None:
            return
        if action[0] == "toggle":
            self.set_hotkeys_enabled(not self.config.general.hotkeys_enabled)
            return
        if not self.config.general.hotkeys_enabled or self._typing_in_app():
            return
        kind = action[0]
        if kind == "input":
            self.open_input()
        elif kind == "stop":
            self.stop()
        elif kind == "next_voice":
            self.cycle_voice(+1)
        elif kind == "phrase":
            phrase = next((p for p in self.config.phrases if p.id == action[1]), None)
            if phrase:
                self.say(phrase.text, phrase.voice_id, persist=True)
        elif kind == "wheel":
            self._wheel_pressed(action[1], combo)

    @Slot(str)
    def _on_hotkey_up(self, combo: str) -> None:
        if (
            self._wheel is not None
            and combo == self._wheel_combo
            and self.config.general.wheel_mode == cfgmod.WHEEL_HOLD
        ):
            self._wheel_confirm()

    # --- input overlay ----------------------------------------------------------

    def open_input(self) -> None:
        if self._wheel is not None:
            self._wheel_close()
        self.input_overlay.open(self.config.active_voice().name, self.config.history)

    def _on_input_submitted(self, text: str, _keep_open: bool) -> None:
        self.config.add_history(text)
        self.edited("history")
        self.say(text)

    def _on_overlay_cycle_voice(self, step: int) -> None:
        voice = self.cycle_voice(step)
        self.input_overlay.set_voice_name(voice.name)

    # --- wheel ------------------------------------------------------------------

    def _wheel_pressed(self, wheel_id: str, combo: str) -> None:
        toggle = self.config.general.wheel_mode == cfgmod.WHEEL_TOGGLE
        if self._wheel is not None:
            same = self._wheel.id == wheel_id
            if toggle and same:
                self._wheel_confirm()
                return
            self._wheel_close()
        wheel = next((w for w in self.config.wheels if w.id == wheel_id), None)
        if wheel is None or not any(s.text.strip() for s in wheel.slots):
            self.status.emit("Колесо пустое — добавьте фразы на вкладке «Колёса»")
            return
        if self.input_overlay.isVisible():
            self.input_overlay.close_overlay(restore=False)
        self._wheel = wheel
        self._wheel_combo = combo
        parsed = parse_combo(combo)
        self._wheel_key = parsed[1] if parsed else ""
        self._wheel_released_ticks = 0
        hint = "нажмите ещё раз, чтобы сказать" if toggle else "отпустите, чтобы сказать"
        self.wheel_overlay.open(wheel.name, wheel.slots, self.config.general.wheel_deadzone, hint)
        self.hotkeys.set_mouse_tracking(True)
        self._last_cursor = QCursor.pos()
        self._wheel_tick_timer.start()
        if toggle:
            self._wheel_timeout.start()
            self.rebind_hotkeys()

    def _wheel_tick(self) -> None:
        # Best source first: Raw Input (real mouse motion, works with a
        # locked cursor), then the low-level hook, then the visible cursor.
        pos = QCursor.pos()
        last = self._last_cursor or pos
        self._last_cursor = pos
        hook = self.hotkeys.take_mouse_delta() if self.hotkeys.running else None
        raw = self.wheel_overlay.raw
        if raw.active and raw.relative_seen:
            dx, dy = raw.take_delta()
        elif hook is not None:
            dx, dy = hook
        else:
            dx, dy = pos.x() - last.x(), pos.y() - last.y()
        self.wheel_overlay.add_delta(dx, dy)
        # Safety net for hold mode: if the key-up event got lost (e.g. an
        # elevated window had focus), notice the key is physically up.
        if self.config.general.wheel_mode == cfgmod.WHEEL_HOLD and self._wheel_key:
            if self.hotkeys.key_is_down(self._wheel_key) is False:
                self._wheel_released_ticks += 1
                if self._wheel_released_ticks >= 4:
                    self._wheel_confirm()
            else:
                self._wheel_released_ticks = 0

    def _wheel_confirm(self) -> None:
        slot = self.wheel_overlay.selected_slot()
        self._wheel_close()
        if slot is not None:
            self.say(slot.text, slot.voice_id, persist=True)

    def _wheel_close(self) -> None:
        was_toggle = self._wheel is not None and self.config.general.wheel_mode == cfgmod.WHEEL_TOGGLE
        self._wheel = None
        self._wheel_combo = ""
        self._wheel_tick_timer.stop()
        self._wheel_timeout.stop()
        self.hotkeys.set_mouse_tracking(False)
        self.wheel_overlay.close_animated()
        if was_toggle:
            self.rebind_hotkeys()

    # --- warm-up ------------------------------------------------------------------

    def prewarm(self) -> None:
        items = []
        for p in self.config.phrases:
            items.append((p.text, self.config.resolve_voice(p.voice_id)))
        for w in self.config.wheels:
            for s in w.slots:
                if s.text.strip():
                    items.append((s.text, self.config.resolve_voice(s.voice_id)))
        self.speech.prewarm(items)

    # --- shutdown -------------------------------------------------------------------

    def shutdown(self) -> None:
        self._save_timer.stop()
        self.save_now()
        self.ptt.release()
        self.hotkeys.stop()
        self.audio.close()
        self.speech.shutdown()
        self.input_overlay.hide()
        self.wheel_overlay.hide()


def _short(text: str, limit: int = 40) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def describe_combo(combo: str) -> str:
    return format_combo(combo) or "—"
