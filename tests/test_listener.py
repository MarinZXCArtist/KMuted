from kmuted.hotkeys.listener import GlobalHotkeys


def make():
    events = []
    hk = GlobalHotkeys(on_press=lambda c: events.append(("down", c)), on_release=lambda c: events.append(("up", c)))
    hk._win = None  # use tracked modifiers, not the real keyboard state
    return hk, events


def test_exact_modifier_match_and_release():
    hk, events = make()
    hk.set_bindings({"alt+q", "q", "mouse5"})
    hk.key_down("alt")
    hk.key_down("q")
    hk.key_down("q")  # auto-repeat is ignored
    hk.key_up("alt")  # modifier released first...
    hk.key_up("q")  # ...release still maps to the combo that fired
    assert events == [("down", "alt+q"), ("up", "alt+q")]

    events.clear()
    hk.key_down("q")
    hk.key_up("q")
    hk.key_down("ctrl")
    hk.key_down("q")  # ctrl+q is not bound
    hk.key_up("q")
    hk.key_up("ctrl")
    assert events == [("down", "q"), ("up", "q")]


def test_mouse_buttons_and_unbound_keys():
    hk, events = make()
    hk.set_bindings({"mouse5"})
    hk.key_down("mouse5")
    hk.key_up("mouse5")
    hk.key_down("mouse4")
    hk.key_up("mouse4")
    hk.key_down(None)
    assert events == [("down", "mouse5"), ("up", "mouse5")]


def test_callback_errors_do_not_break_tracking():
    def boom(_c):
        raise RuntimeError("x")

    hk = GlobalHotkeys(on_press=boom, on_release=boom)
    hk._win = None
    hk.set_bindings({"f1"})
    hk.key_down("f1")
    hk.key_up("f1")
    assert hk._pressed == set()


def test_mouse_delta_fallback_accumulates():
    hk, _ = make()
    hk._mouse_move(100, 100)  # tracking off: ignored
    hk.set_mouse_tracking(True)
    hk._mouse_move(100, 100)
    hk._mouse_move(110, 95)
    hk._mouse_move(130, 90)
    assert hk.take_mouse_delta() == (30, -10)
    assert hk.take_mouse_delta() == (0, 0)
    hk._mouse_move(140, 90, injected=True)
    assert hk.take_mouse_delta() == (0, 0)


def test_injected_ptt_key_is_ignored():
    hk, events = make()
    hk.set_bindings({"v"})
    hk.ignore_injected(["v"])
    key = type("K", (), {"vk": 0x56, "char": "v"})()
    hk._kb_press(key, True)
    hk._kb_release(key, True)
    assert events == []


def test_missed_key_up_does_not_block_next_press():
    hk, events = make()
    hk.set_bindings({"alt+t"})
    hk.key_down("alt", now=0.0)
    hk.key_down("t", now=0.0)  # key-up of "t" gets lost (e.g. UAC prompt)
    hk.key_down("t", now=0.4)  # auto-repeat: ignored
    hk.key_down("t", now=5.0)  # much later: a real new press
    assert events == [("down", "alt+t"), ("down", "alt+t")]


def test_mouse_buttons_never_count_as_repeat():
    hk, events = make()
    hk.set_bindings({"mouse5"})
    hk.key_down("mouse5", now=0.0)
    hk.key_down("mouse5", now=0.1)  # previous release was missed
    assert events == [("down", "mouse5"), ("down", "mouse5")]


def test_key_is_down_unknown_without_windows():
    hk, _ = make()
    assert hk.key_is_down("q") is None
