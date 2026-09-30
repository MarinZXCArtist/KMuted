import json
import types
from concurrent.futures import Future

import numpy as np
import pytest

from kmuted import config as cfgmod
from kmuted import translate as tl
from kmuted.audio.dsp import Clip
from kmuted.config import CloudSettings, LanguageVoice, TranslateSettings, VoiceProfile


def _translator(tmp_path, **settings):
    return tl.Translator(TranslateSettings(**settings), CloudSettings(deepl_key="k:fx", anthropic_key="sk", openai_key="ok"),
                         cache_file=tmp_path / "tr.json")


def test_google_free_parses_chunks(monkeypatch, tmp_path):
    calls = []

    def fake_http(method, url, headers=None, body=None):
        calls.append(url)
        return json.dumps([[["Hello everyone! ", "Привет всем! ", None], ["Let's go.", "Погнали.", None]], None, "ru"]).encode()

    monkeypatch.setattr(tl, "_http", fake_http)
    tr_ = _translator(tmp_path)
    job = tr_.job("Привет всем! Погнали.", "en")
    assert tr_.run(job) == "Hello everyone! Let's go."
    assert "sl=auto" in calls[0] and "tl=en" in calls[0] and "client=gtx" in calls[0]
    # second time comes from the cache
    assert tr_.run(job) == "Hello everyone! Let's go."
    assert len(calls) == 1


def test_google_rate_limit_message(monkeypatch, tmp_path):
    def fake_http(method, url, headers=None, body=None):
        raise tl.TranslateError("429", code=429)

    monkeypatch.setattr(tl, "_http", fake_http)
    with pytest.raises(tl.TranslateError, match="Google"):
        _translator(tmp_path).run(tl.Job("привет", "google", "auto", "en"))


def test_mymemory_quota_is_an_error(monkeypatch, tmp_path):
    reply = {"responseData": {"translatedText": "MYMEMORY WARNING: YOU USED ALL AVAILABLE FREE TRANSLATIONS"}, "responseStatus": 429}
    monkeypatch.setattr(tl, "_http", lambda *a, **k: json.dumps(reply).encode())
    with pytest.raises(tl.TranslateError, match="MyMemory"):
        _translator(tmp_path, provider="mymemory").run(tl.Job("привет", "mymemory", "auto", "en"))


def test_deepl_free_host_target_and_formality(monkeypatch, tmp_path):
    seen = {}

    def fake_http(method, url, headers=None, body=None):
        seen.update(url=url, headers=headers, body=json.loads(body))
        return json.dumps({"translations": [{"text": "Could you help me, please?"}]}).encode()

    monkeypatch.setattr(tl, "_http", fake_http)
    tr_ = _translator(tmp_path, provider="deepl", style="polite", source="ru")
    assert tr_.run(tr_.job("Помоги мне", "en")) == "Could you help me, please?"
    assert seen["url"] == "https://api-free.deepl.com/v2/translate"
    assert seen["headers"]["Authorization"] == "DeepL-Auth-Key k:fx"
    assert seen["body"] == {"text": ["Помоги мне"], "target_lang": "EN-US", "source_lang": "RU", "formality": "prefer_more"}


def test_openai_reply_is_cleaned(monkeypatch, tmp_path):
    reply = {"choices": [{"message": {"content": '"<message>Push B!</message>"'}}]}
    monkeypatch.setattr(tl, "_http", lambda *a, **k: json.dumps(reply).encode())
    tr_ = _translator(tmp_path, provider="openai")
    assert tr_.run(tr_.job("го на б", "en")) == "Push B!"


class _Block:
    def __init__(self, kind, text=""):
        self.type = kind
        self.text = text


class _FakeAnthropic:
    last = {}
    reply = None

    def __init__(self, api_key, timeout, max_retries):
        _FakeAnthropic.last["init"] = dict(api_key=api_key)
        self.beta = types.SimpleNamespace(messages=types.SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        _FakeAnthropic.last["kwargs"] = kwargs
        return _FakeAnthropic.reply


def test_claude_request_shape_and_refusal(monkeypatch, tmp_path):
    anthropic = pytest.importorskip("anthropic")
    monkeypatch.setattr(anthropic, "Anthropic", _FakeAnthropic)
    tr_ = _translator(tmp_path, provider="claude", style="gaming")
    _FakeAnthropic.reply = types.SimpleNamespace(
        stop_reason="end_turn", content=[_Block("thinking"), _Block("text", "Rush B, they're empty!")]
    )
    assert tr_.run(tr_.job("го на б, их нет", "en")) == "Rush B, they're empty!"
    kw = _FakeAnthropic.last["kwargs"]
    assert kw["model"] == "claude-opus-5-5"
    assert kw["betas"] == ["server-side-fallback-2026-07-01"] and kw["fallbacks"] == "default"
    assert kw["output_config"] == {"effort": "low"}
    assert "English" in kw["system"] and "gamer" in kw["system"]
    assert kw["messages"] == [{"role": "user", "content": "<message>го на б, их нет</message>"}]
    assert _FakeAnthropic.last["init"]["api_key"] == "sk"

    _FakeAnthropic.reply = types.SimpleNamespace(stop_reason="refusal", content=[])
    with pytest.raises(tl.TranslateError):
        tr_.run(tr_.job("другое", "en"))


def test_claude_haiku_skips_effort_and_fallbacks(monkeypatch, tmp_path):
    anthropic = pytest.importorskip("anthropic")
    monkeypatch.setattr(anthropic, "Anthropic", _FakeAnthropic)
    tr_ = _translator(tmp_path, provider="claude", claude_model="claude-haiku-4-5")
    _FakeAnthropic.reply = types.SimpleNamespace(stop_reason="end_turn", content=[_Block("text", "Hi")])
    tr_.run(tr_.job("привет", "en"))
    kw = _FakeAnthropic.last["kwargs"]
    assert kw["model"] == "claude-haiku-4-5"
    assert "output_config" not in kw and "fallbacks" not in kw


def test_missing_key_is_reported(tmp_path):
    tr_ = tl.Translator(TranslateSettings(provider="deepl"), CloudSettings(), cache_file=tmp_path / "x.json")
    assert tr_.availability()
    with pytest.raises(tl.TranslateError):
        tr_.run(tr_.job("привет", "en"))


def test_cache_survives_restart(monkeypatch, tmp_path):
    monkeypatch.setattr(tl, "_http", lambda *a, **k: json.dumps([[["Hi", "Привет"]]]).encode())
    first = _translator(tmp_path)
    job = first.job("Привет", "en")
    first.run(job)
    first.save()
    second = _translator(tmp_path)
    assert second.cached(job) == "Hi"
    # AI style is part of the key for AI translators only
    assert tl.Job("a", "google", "auto", "en", style="gaming").cache_key() == tl.Job("a", "google", "auto", "en").cache_key()
    assert tl.Job("a", "claude", "auto", "en", style="gaming").cache_key() != tl.Job("a", "claude", "auto", "en").cache_key()


def test_voice_helpers():
    assert tl.is_female_voice("ru-RU-SvetlanaNeural") and not tl.is_female_voice("ru-RU-DmitryNeural")
    assert tl.voice_language(VoiceProfile(engine="edge", voice="ru-RU-DmitryNeural")) == "ru"
    assert tl.voice_language(VoiceProfile(engine="edge", voice="en-US-AndrewMultilingualNeural")) == ""
    assert tl.edge_voice_for("de", True) == "de-DE-KatjaNeural"
    assert tl.short_label("ru", "en") == "RU → EN"


# --- controller -----------------------------------------------------------------------------


@pytest.fixture
def controller(qapp, tmp_path):
    from kmuted.controller import Controller

    cfg = cfgmod.default_config()
    c = Controller(cfg, enable_hotkeys=False, enable_audio=False)
    c._prewarm_timer.stop()
    c.translator = tl.Translator(cfg.translate, cfg.cloud, cache_file=tmp_path / "t.json")
    c.played = []
    c._play = lambda req: c.played.append(req.text)
    yield c
    c.shutdown()


def _pump(qapp, times=8):
    for _ in range(times):
        qapp.processEvents()


def _sync_speech(c, spoken):
    def synthesize(text, profile, persist=False):
        spoken.append((text, profile.voice))
        return Clip(np.ones(10, np.float32), 1000)

    def submit_call(fn, *args):
        fut = Future()
        try:
            fut.set_result(fn(*args))
        except Exception as exc:  # noqa: BLE001
            fut.set_exception(exc)
        return fut

    c.speech.synthesize = synthesize
    c.speech.submit_call = submit_call
    c.speech.submit = lambda text, profile, persist=False: submit_call(synthesize, text, profile, persist)


def test_say_translates_and_switches_voice(controller, qapp):
    c = controller
    spoken = []
    _sync_speech(c, spoken)
    c.config.translate.enabled = True
    c.config.translate.target = "en"
    c.config.general.active_voice_id = c.config.voices[0].id  # Dmitry (ru)
    c.translator.run = lambda job: {"Привет": "Hi"}.get(job.text, "?")
    c.say("Привет")
    _pump(qapp)
    assert spoken == [("Hi", "en-US-AndrewMultilingualNeural")]
    assert c.played == ["Hi"]

    spoken.clear()
    c.say("=gg wp")  # "=" — say as typed
    _pump(qapp)
    assert spoken == [("gg wp", "ru-RU-DmitryNeural")]


def test_phrases_follow_their_setting_and_language_voice_wins(controller, qapp):
    c = controller
    spoken = []
    _sync_speech(c, spoken)
    t = c.config.translate
    t.enabled, t.target, t.phrases = True, "de", False
    c.translator.run = lambda job: "Hallo"
    c.say("Привет", phrase=True)
    _pump(qapp)
    assert spoken[-1][0] == "Привет"
    t.phrases = True
    t.voices = [LanguageVoice("de", c.config.voices[1].id)]
    c.say("Привет", phrase=True)
    _pump(qapp)
    assert spoken[-1] == ("Hallo", c.config.voices[1].voice)


def test_failed_translation_speaks_original(controller, qapp):
    c = controller
    spoken, notes = [], []
    _sync_speech(c, spoken)
    c.notify.connect(lambda text, kind: notes.append(kind))
    c.config.translate.enabled = True

    def boom(job):
        raise tl.TranslateError("нет сети")

    c.translator.run = boom
    c.say("Привет")
    _pump(qapp)
    assert spoken[0][0] == "Привет" and spoken[0][1] == "ru-RU-DmitryNeural"
    assert "warning" in notes


def test_toggle_and_cycle_language(controller, qapp):
    c = controller
    t = c.config.translate
    t.favorites = ["en", "de"]
    assert c.translation_target() == ""
    c.toggle_translation()
    assert t.enabled and c.translation_target() == "en"
    assert c.cycle_language() == "de" and t.target == "de"
    assert c.cycle_language() == "en"
    t.source = "en"
    assert c.translation_target() == ""  # same language: nothing to do

