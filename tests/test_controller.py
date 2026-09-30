from concurrent.futures import Future

import numpy as np
import pytest

from kmuted import config as cfgmod
from kmuted.audio.dsp import Clip


@pytest.fixture
def controller(qapp):
    from kmuted.controller import Controller

    c = Controller(cfgmod.default_config(), enable_hotkeys=False, enable_audio=False)
    c._prewarm_timer.stop()
    played = []
    c._play = lambda req: played.append(req.text)
    c.played = played
    yield c
    c.shutdown()


def _pump(qapp, times=5):
    for _ in range(times):
        qapp.processEvents()


def test_playback_keeps_request_order(controller, qapp):
    futures = {}

    def submit(text, profile, persist=False):
        fut = Future()
        futures[text] = fut
        return fut

    controller.speech.submit = submit
    controller.say("первая")
    controller.say("вторая")
    futures["вторая"].set_result(Clip(np.ones(10, np.float32), 1000))
    _pump(qapp)
    assert controller.played == []  # waits for the first one
    futures["первая"].set_result(Clip(np.ones(10, np.float32), 1000))
    _pump(qapp)
    assert controller.played == ["первая", "вторая"]


def test_failed_request_does_not_block_queue(controller, qapp):
    from kmuted.tts.base import TTSError

    futures = {}
    controller.speech.submit = lambda text, profile, persist=False: futures.setdefault(text, Future())
    errors = []
    controller.error.connect(errors.append)
    controller.say("плохая")
    controller.say("хорошая")
    futures["плохая"].set_exception(TTSError("нет интернета"))
    futures["хорошая"].set_result(Clip(np.ones(10, np.float32), 1000))
    _pump(qapp)
    assert controller.played == ["хорошая"]
    assert errors == ["нет интернета"]


def test_stop_drops_pending(controller, qapp):
    futures = {}
    controller.speech.submit = lambda text, profile, persist=False: futures.setdefault(text, Future())
    controller.say("раз")
    controller.stop()
    futures["раз"].set_result(Clip(np.ones(10, np.float32), 1000))
    _pump(qapp)
    assert controller.played == []


def test_phrase_hotkey_says_phrase(controller, qapp):
    said = []
    controller.say = lambda text, voice_id="", persist=False: said.append(text)
    phrase = controller.config.phrases[0]
    controller._on_hotkey_down(phrase.hotkey)
    assert said == [phrase.text]
    controller.config.general.hotkeys_enabled = False
    controller._on_hotkey_down(phrase.hotkey)
    assert said == [phrase.text]


def test_wheel_hold_flow(controller, qapp):
    said = []
    controller.say = lambda text, voice_id="", persist=False: said.append(text)
    wheel = controller.config.wheels[0]
    controller._on_hotkey_down(wheel.hotkey)
    assert controller.wheel_overlay.isVisible()
    controller.wheel_overlay.add_delta(120, 0)  # right -> slot 2
    controller._on_hotkey_up(wheel.hotkey)
    assert not controller.wheel_overlay.isVisible()
    assert said == [wheel.slots[2].text]

    controller._on_hotkey_down(wheel.hotkey)
    controller.wheel_overlay.add_delta(5, 5)  # inside the dead zone: cancel
    controller._on_hotkey_up(wheel.hotkey)
    assert said == [wheel.slots[2].text]


def test_wheel_toggle_flow(controller, qapp):
    said = []
    controller.say = lambda text, voice_id="", persist=False: said.append(text)
    controller.config.general.wheel_mode = cfgmod.WHEEL_TOGGLE
    wheel = controller.config.wheels[0]
    controller._on_hotkey_down(wheel.hotkey)
    controller._on_hotkey_up(wheel.hotkey)
    assert controller.wheel_overlay.isVisible()
    assert "esc" in controller.hotkeys._bindings
    controller.wheel_overlay.add_delta(0, 120)  # down -> slot 4
    controller._on_hotkey_down(wheel.hotkey)
    assert said == [wheel.slots[4].text]
    assert "esc" not in controller.hotkeys._bindings

    controller._on_hotkey_down(wheel.hotkey)
    controller._on_hotkey_down("esc")
    assert not controller.wheel_overlay.isVisible()
    assert len(said) == 1


def test_conflicts_and_cycle_voice(controller):
    phrase = controller.config.phrases[0]
    assert controller.hotkey_conflict(phrase.hotkey, f"phrase:{phrase.id}") == ""
    assert "уже занято" in controller.hotkey_conflict(phrase.hotkey, "general:input_hotkey")
    first = controller.config.active_voice()
    nxt = controller.cycle_voice(+1)
    assert nxt is not first and controller.config.active_voice() is nxt
