import json

from kmuted import config as cfg


def test_default_config_is_consistent():
    c = cfg.default_config()
    assert c.voices and c.phrases and c.wheels
    assert c.active_voice().id == c.general.active_voice_id
    assert all(p.hotkey for p in c.phrases)
    assert len(c.wheels[0].slots) == 8


def test_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    c = cfg.default_config()
    c.phrases[0].text = "Проверка ё"
    cfg.save_config(c, path)
    loaded = cfg.load_config(path)
    assert loaded == c
    assert "Проверка ё" in path.read_text(encoding="utf-8")


def test_tolerant_loading_drops_junk(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "unknown": 1,
                "general": {"input_hotkey": "Ctrl + Shift + F1", "wheel_mode": "weird", "hotkeys_enabled": "yes"},
                "audio": {"mic_volume": 999, "ptt_delay_ms": "abc"},
                "voices": [{"name": "A", "engine": "nope", "rate": 500}, "garbage"],
                "phrases": [{"text": "hi", "hotkey": "alt+1", "extra": True}],
                "wheels": [{"name": "W", "slots": [{"text": "x"}]}],
            }
        ),
        encoding="utf-8",
    )
    c = cfg.load_config(path)
    assert c.general.input_hotkey == "ctrl+shift+f1"
    assert c.general.wheel_mode == cfg.WHEEL_HOLD
    assert c.general.hotkeys_enabled is True  # bad type -> default
    assert c.audio.mic_volume == 200
    assert c.audio.ptt_delay_ms == cfg.AudioSettings().ptt_delay_ms
    assert len(c.voices) == 1 and c.voices[0].engine == cfg.ENGINE_EDGE and c.voices[0].rate == 100
    assert c.phrases[0].text == "hi"
    assert len(c.wheels[0].slots) == cfg.WHEEL_MIN_SLOTS
    assert c.general.active_voice_id == c.voices[0].id


def test_broken_file_is_backed_up(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{not json", encoding="utf-8")
    c = cfg.load_config(path)
    assert c.voices
    assert (tmp_path / "config.broken.json").exists()
    json.loads(path.read_text(encoding="utf-8"))


def test_history_dedup_and_limit():
    c = cfg.Config()
    for i in range(cfg.HISTORY_LIMIT + 10):
        c.add_history(f"msg {i}")
    c.add_history("msg 5")
    assert c.history[0] == "msg 5"
    assert len(c.history) == cfg.HISTORY_LIMIT
    assert c.history.count("msg 5") == 1
    c.add_history("   ")
    assert c.history[0] == "msg 5"


def test_resolve_voice_falls_back_to_active():
    c = cfg.default_config()
    other = c.voices[1]
    assert c.resolve_voice(other.id) is other
    assert c.resolve_voice("missing") is c.active_voice()
    assert c.resolve_voice("") is c.active_voice()


def test_cache_key_ignores_volume_and_disabled_rvc():
    a = cfg.VoiceProfile(volume=50, rvc_model="m", rvc_enabled=False)
    b = cfg.VoiceProfile(volume=150, rvc_model="other", rvc_enabled=False)
    assert a.cache_key() == b.cache_key()
    b.rvc_enabled = True
    assert a.cache_key() != b.cache_key()
