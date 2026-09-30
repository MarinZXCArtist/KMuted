from kmuted import cable
from kmuted.hotkeys.ptt import PushToTalk


def test_ptt_keeps_key_held_when_unchanged():
    ptt = PushToTalk()
    released = []
    ptt._key_name = "v"
    ptt._target = object()
    ptt._down = True
    ptt.release = lambda: released.append(True)  # type: ignore[method-assign]
    ptt.set_key("v")
    assert released == [] and ptt.is_down


def test_pick_setup_prefers_x64(tmp_path):
    (tmp_path / "VBCABLE_Setup.exe").write_bytes(b"")
    (tmp_path / "VBCABLE_Setup_x64.exe").write_bytes(b"")
    assert cable.pick_setup(tmp_path).name == "VBCABLE_Setup_x64.exe"
    assert cable.pick_setup(tmp_path / "missing") is None


def test_audio_engine_does_not_reopen_on_volume_change(monkeypatch):
    from kmuted.audio import engine as eng
    from kmuted.config import AudioSettings

    opened = []

    class FakeSink:
        def __init__(self, candidates, label, on_start=None, on_idle=None):
            opened.append(label)
            self.mixer = eng.MixerCore(1000, 1)
            self.device = None

        alive = True

        def close(self):
            pass

    monkeypatch.setattr(eng, "OutputSink", FakeSink)
    monkeypatch.setattr(eng.devices, "find_candidates", lambda name, kind: [])
    monkeypatch.setattr(eng.devices, "default_output_candidates", lambda: [])
    audio = eng.AudioEngine()
    settings = AudioSettings(mic_device="CABLE Input", monitor_enabled=True)
    audio.configure(settings)
    assert opened == ["виртуальный микрофон", "наушники"]
    settings.mic_volume = 50
    settings.monitor_volume = 30
    audio.configure(settings)
    assert opened == ["виртуальный микрофон", "наушники"]
    assert audio.mic.mixer.gain == 0.5 and audio.monitor.mixer.gain == 0.3


def test_components_render(qapp):
    from kmuted.ui.components import Keycaps, ToggleSwitch, combo_parts
    from kmuted.ui.icons import icon, icon_pixmap, render_logo

    assert combo_parts("ctrl+shift+f1") == ["Ctrl", "Shift", "F1"]
    assert combo_parts("") == []
    switch = ToggleSwitch()
    switch.setChecked(True)
    assert not switch.grab().isNull()
    caps = Keycaps("alt+t")
    assert caps.width() > 20
    assert not icon_pixmap("mic", "#ffffff", 18).isNull()
    assert not icon("play").isNull()
    assert not render_logo(64).isNull()
