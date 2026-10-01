import io
import json

import numpy as np
import soundfile as sf

from kmuted import voice_presets
from kmuted.config import CloudSettings, VoiceProfile
from kmuted.tts import cloud
from kmuted.tts.base import VoiceInfo


def test_sigv4_matches_aws_documentation_example():
    # https://docs.aws.amazon.com/IAM/latest/UserGuide/create-signed-request.html (IAM ListUsers example)
    headers = cloud.aws_sigv4_headers(
        "GET",
        "https://iam.amazonaws.com/?Action=ListUsers&Version=2010-05-08",
        "us-east-1",
        "iam",
        "AKIDEXAMPLE",
        "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY",
        b"",
        "application/x-www-form-urlencoded; charset=utf-8",
        "20150830T123600Z",
    )
    assert headers["Authorization"] == (
        "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20150830/us-east-1/iam/aws4_request, "
        "SignedHeaders=content-type;host;x-amz-date, "
        "Signature=5d672d79c15b13162d9279b0855cfba6789a8edb4c82c400e06b5924a6f2b5d7"
    )
    assert headers["X-Amz-Date"] == "20150830T123600Z"


def _wav_bytes() -> bytes:
    buf = io.BytesIO()
    sf.write(buf, np.zeros(2205, dtype=np.float32), 22050, format="WAV")
    return buf.getvalue()


def test_polly_request(monkeypatch):
    seen = {}

    def fake_http(method, url, headers=None, body=None, timeout=30):
        seen.update(method=method, url=url, headers=headers, body=json.loads(body))
        return _wav_bytes()

    monkeypatch.setattr(cloud, "_http", fake_http)
    settings = CloudSettings(polly_key_id="AKID", polly_secret="secret", polly_region="eu-central-1")
    engine = cloud.PollyEngine(lambda: settings)
    assert engine.availability() == ""
    clip = engine.synthesize("Привет & пока", VoiceProfile(engine="polly", voice="Maxim", rate=12, pitch=10))
    assert clip.sample_rate == 22050
    assert seen["method"] == "POST" and seen["url"] == "https://polly.eu-central-1.amazonaws.com/v1/speech"
    assert seen["headers"]["Authorization"].startswith("AWS4-HMAC-SHA256 Credential=AKID/")
    assert "/eu-central-1/polly/aws4_request" in seen["headers"]["Authorization"]
    body = seen["body"]
    assert body["VoiceId"] == "Maxim" and body["Engine"] == "standard" and body["TextType"] == "ssml"
    assert body["Text"] == '<speak><prosody rate="112%" pitch="+5%">Привет &amp; пока</prosody></speak>'


def test_polly_needs_both_keys():
    settings = CloudSettings(polly_key_id="AKID")
    engine = cloud.PollyEngine(lambda: settings)
    assert engine.availability()
    assert [v.id for v in engine.list_voices()] == ["Maxim", "Tatyana"]


def test_kava_preset_prefers_installed_ivona():
    kava = next(p for p in voice_presets.PRESETS if p.key == "kava")
    installed = [VoiceInfo("HKLM\\...\\Irina", "Microsoft Irina"), VoiceInfo("HKLM\\...\\IVONA 2 Voice Maxim22", "IVONA 2 Maxim")]
    profile, offline = voice_presets.build(kava, "Кава (Максим)", installed)
    assert offline and profile.engine == "sapi" and profile.voice.endswith("Maxim22") and profile.rate == kava.rate

    profile, offline = voice_presets.build(kava, "Кава (Максим)", installed[:1])
    assert not offline
    assert (profile.engine, profile.voice, profile.model) == ("polly", "Maxim", "standard")
