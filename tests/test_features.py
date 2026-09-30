import io
import random
import zipfile
from datetime import datetime

import numpy as np
import pytest
import soundfile as sf

from kmuted import config as cfgmod
from kmuted import i18n, keystore, presets, textvars, updater
from kmuted.audio import sounds as soundlib
from kmuted.config import Sound, VoiceProfile, Wheel, WheelSlot


@pytest.fixture(autouse=True)
def russian():
    i18n.set_language("ru")
    yield
    i18n.set_language("ru")


# --- i18n ----------------------------------------------------------------------------


def test_every_ui_string_has_english():
    import os
    import sys
    from pathlib import Path

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    import i18n_strings

    from kmuted.i18n_en import EN

    missing = sorted(s for s in i18n_strings.all_strings() if s not in EN)
    assert missing == []


def test_tr_switches_language_and_formats():
    assert i18n.tr("Голос: {name}", name="A") == "Голос: A"
    i18n.set_language("en")
    assert i18n.tr("Голос: {name}", name="A") == "Voice: A"
    assert i18n.tr("никогда не переводилось") == "никогда не переводилось"
    assert i18n.tr("Синтез: «{text}»…", text="x") == "Synthesizing: “x”…"


def test_default_config_follows_language():
    i18n.set_language("en")
    cfg = cfgmod.default_config()
    assert cfg.phrases[0].text == "Hi everyone!"
    assert cfg.active_voice().voice.startswith("en-US")
    assert cfg.wheels[0].slots[1].label == "Enemy!"


def test_resolve_prefers_setting_then_installer(tmp_path, monkeypatch):
    from kmuted import paths

    monkeypatch.setattr(paths, "data_dir", lambda: tmp_path)
    assert i18n.resolve("en") == "en"
    (tmp_path / "language.txt").write_text("en", encoding="utf-8")
    assert i18n.resolve("") == "en"


# --- text variables --------------------------------------------------------------------


def test_text_variables():
    now = datetime(2026, 9, 30, 14, 5)
    rng = random.Random(1)
    assert textvars.expand("Время {время}", now=now) == "Время 14:05"
    assert textvars.expand("{дата}, {день}", now=now) == "30 сентября, среда"
    assert textvars.expand("copy: {буфер}", clipboard=" hello ") == "copy: hello"
    assert textvars.expand("{случайно:а|б}", rng=rng) in ("а", "б")
    assert 1 <= int(textvars.expand("{число:1-3}", rng=rng)) <= 3
    assert textvars.expand("{непонятно}") == "{непонятно}"
    assert textvars.has_vars("hi {time}") and not textvars.has_vars("hi")
    i18n.set_language("en")
    assert textvars.expand("{date}", now=now) == "September 30"


# --- keystore -----------------------------------------------------------------------------


def test_keystore_roundtrip_and_config(tmp_path):
    assert keystore.unprotect(keystore.protect("sk-secret")) == "sk-secret"
    assert keystore.protect("") == "" and keystore.unprotect("") == ""
    assert keystore.mask("sk-1234567890") == "sk-1…7890"
    cfg = cfgmod.default_config()
    cfg.cloud.openai_key = "sk-test"
    path = tmp_path / "config.json"
    cfgmod.save_config(cfg, path)
    assert '"openai_key": "sk-test"' not in path.read_text(encoding="utf-8")
    assert cfgmod.load_config(path).cloud.openai_key == "sk-test"


# --- updater ----------------------------------------------------------------------------------


def test_updater_versions_and_release_parsing():
    assert updater.is_newer("0.10.0", "0.9.9")
    assert not updater.is_newer("v0.2.0", "0.2.0")
    rel = updater.parse_release(
        {
            "tag_name": "v1.2.3",
            "html_url": "https://example/rel",
            "body": "notes",
            "assets": [
                {"name": "KMuted-1.2.3-windows.zip", "browser_download_url": "zip"},
                {"name": "KMuted-Setup-1.2.3.exe", "browser_download_url": "exe"},
            ],
        }
    )
    assert rel.version == "1.2.3" and rel.installer_url == "exe"


# --- sounds & packs ----------------------------------------------------------------------------


def _wav(path, seconds=0.2, rate=16000):
    t = np.linspace(0, seconds, int(rate * seconds), endpoint=False)
    sf.write(path, (np.sin(2 * np.pi * 440 * t) * 0.3).astype(np.float32), rate)
    return path


def test_sound_import_and_decode(tmp_path):
    src = _wav(tmp_path / "boom.wav")
    stored = soundlib.import_file(src)
    again = soundlib.import_file(src)
    assert stored != again  # no overwrite of an existing file
    lib = soundlib.SoundLibrary()
    pcm, rate = lib.load(Sound(file=stored))
    assert pcm.dtype == np.int16 and rate == 16000 and len(pcm) == 3200
    assert lib.load(Sound(file=stored))[0] is pcm  # cached
    with pytest.raises(soundlib.SoundError):
        soundlib.import_file(tmp_path / "notes.txt")
    with pytest.raises(soundlib.SoundError):
        lib.load(Sound(file="missing.wav"))


def test_pack_roundtrip_remaps_ids_and_drops_taken_hotkeys(tmp_path):
    src = _wav(tmp_path / "horn.wav")
    cfg = cfgmod.default_config()
    snd = Sound(name="Horn", file=soundlib.import_file(src), hotkey="alt+f1")
    voice = VoiceProfile(name="Robot", hotkey="alt+f2")
    cfg.sounds.append(snd)
    cfg.voices.append(voice)
    cfg.phrases[0].voice_id = voice.id
    cfg.wheels.append(Wheel(name="SFX", hotkey="alt+w", slots=[WheelSlot(sound_id=snd.id, label="Horn")] + [WheelSlot()] * 3))
    pack = tmp_path / "share.kmuted"
    info = presets.export_pack(cfg, pack, set(presets.PARTS))
    assert info.counts["sounds"] == 1 and zipfile.is_zipfile(pack)

    other = cfgmod.default_config()  # already uses alt+1..4, alt+q, alt+t...
    stats = presets.import_pack(other, pack, set(presets.PARTS))
    assert stats["sounds"] == 1 and stats["voices"] == len(cfg.voices)
    assert stats["hotkeys_dropped"] >= 4  # the starter phrases clash
    imported_sound = other.sounds[-1]
    assert imported_sound.id != snd.id and soundlib.resolve_path(imported_sound).exists()
    sfx = next(w for w in other.wheels if w.name == "SFX")
    assert sfx.slots[0].sound_id == imported_sound.id
    robot = next(v for v in other.voices if v.name == "Robot")
    assert any(p.voice_id == robot.id for p in other.phrases)
    info2 = presets.read_pack(pack)
    assert info2.counts["wheels"] == 2


def test_pack_rejects_foreign_zip(tmp_path):
    bad = tmp_path / "bad.kmuted"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("manifest.json", '{"app": "Other"}')
    with pytest.raises(presets.PackError):
        presets.read_pack(bad)
    (tmp_path / "junk.kmuted").write_bytes(b"not a zip")
    with pytest.raises(presets.PackError):
        presets.read_pack(tmp_path / "junk.kmuted")


# --- cloud engines --------------------------------------------------------------------------------


def _mp3_bytes() -> bytes:
    buf = io.BytesIO()
    sf.write(buf, (np.sin(np.linspace(0, 300, 8000)) * 0.3).astype(np.float32), 16000, format="MP3")
    return buf.getvalue()


def test_elevenlabs_request(monkeypatch):
    from kmuted.tts import cloud

    calls = []

    def fake_http(method, url, headers=None, body=None, timeout=30):
        calls.append((method, url, headers, body))
        return _mp3_bytes()

    monkeypatch.setattr(cloud, "_http", fake_http)
    settings = cfgmod.CloudSettings(elevenlabs_key="xi-key")
    engine = cloud.ElevenLabsEngine(lambda: settings)
    clip = engine.synthesize("привет", VoiceProfile(engine="elevenlabs", voice="VOICE1", rate=10))
    assert len(clip.samples) > 0
    method, url, headers, body = calls[0]
    assert method == "POST" and "/text-to-speech/VOICE1" in url
    assert headers["xi-api-key"] == "xi-key"
    assert b'"model_id": "eleven_multilingual_v2"' in body


def test_cloud_without_key_explains():
    from kmuted.tts import cloud
    from kmuted.tts.base import TTSError

    engine = cloud.OpenAIEngine(lambda: cfgmod.CloudSettings())
    assert engine.availability()
    assert [v.id for v in engine.list_voices()][:2] == ["alloy", "ash"]
    with pytest.raises(TTSError):
        engine.synthesize("hi", VoiceProfile(engine="openai"))
