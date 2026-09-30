import base64
import io
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np
import pytest
import soundfile as sf

from kmuted.audio.dsp import Clip
from kmuted.config import VoiceProfile
from kmuted.tts import piper_catalog
from kmuted.tts.base import TTSEngine, TTSError, VoiceInfo
from kmuted.tts.manager import SpeechService
from kmuted.tts.piper_engine import rate_to_length_scale
from kmuted.tts.rvc import RVCClient


class FakeEngine(TTSEngine):
    key = "edge"
    title = "fake"

    def __init__(self):
        self.calls = 0

    def list_voices(self, refresh=False):
        return [VoiceInfo("v", "V")]

    def synthesize(self, text, profile):
        self.calls += 1
        tone = np.sin(np.linspace(0, 200, 8000)).astype(np.float32) * 0.5
        return Clip(np.concatenate([np.zeros(800, np.float32), tone, np.zeros(800, np.float32)]), 16000)


@pytest.fixture
def service():
    engine = FakeEngine()
    svc = SpeechService(engines={"edge": engine})
    svc.clear_cache()
    yield svc, engine
    svc.shutdown()


def test_cache_and_volume(service):
    svc, engine = service
    profile = VoiceProfile(volume=100)
    a = svc.synthesize("привет", profile)
    loud = svc.synthesize("привет", VoiceProfile(id=profile.id, volume=200))
    assert engine.calls == 1  # volume is applied after the cache
    assert np.isclose(np.max(np.abs(loud.samples)), 2 * np.max(np.abs(a.samples)), rtol=1e-3)
    assert len(a.samples) < 8000 + 1600  # silence trimmed
    svc.synthesize("привет", VoiceProfile(rate=20))
    assert engine.calls == 2


def test_persist_and_disk_hit(service):
    svc, engine = service
    svc.synthesize("фраза", VoiceProfile(), persist=True)
    svc._memory.clear()
    svc.synthesize("фраза", VoiceProfile())
    assert engine.calls == 1


def test_submit_and_prewarm(service):
    svc, engine = service
    fut = svc.submit("раз", VoiceProfile())
    assert isinstance(fut.result(timeout=5), Clip)
    svc.prewarm([("два", VoiceProfile()), ("  ", VoiceProfile())])
    svc._warm_pool.submit(lambda: None).result(timeout=5)
    assert engine.calls == 2


def test_errors(service):
    svc, _ = service
    with pytest.raises(TTSError):
        svc.synthesize("  ", VoiceProfile())
    with pytest.raises(TTSError):
        svc.synthesize("x", VoiceProfile(engine="piper"))


def test_piper_rate_mapping():
    assert rate_to_length_scale(0) == 1.0
    assert rate_to_length_scale(100) == 0.5
    assert rate_to_length_scale(-50) == 2.0


def test_piper_catalog_parsing():
    data = {
        "ru_RU-irina-medium": {
            "name": "irina",
            "language": {"code": "ru_RU", "name_native": "Русский", "country_english": "Russia"},
            "quality": "medium",
            "num_speakers": 1,
            "files": {
                "ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx": {"size_bytes": 63_000_000},
                "ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx.json": {"size_bytes": 5000},
                "ru/ru_RU/irina/medium/MODEL_CARD": {},
            },
        },
        "en_US-amy-low": {"name": "amy", "language": {"code": "en_US"}, "quality": "low", "files": {}},
        "broken": None,
    }
    voices = piper_catalog.parse_catalog(data)
    assert [v.key for v in voices] == ["ru_RU-irina-medium", "en_US-amy-low"]
    irina = voices[0]
    assert irina.model_path.endswith("ru_RU-irina-medium.onnx")
    assert irina.language_name == "Русский (Russia)"
    assert round(irina.size_mb) == 63
    assert voices[1].model_path == "en/en_US/amy/low/en_US-amy-low.onnx"
    assert all(v.model_path.endswith(".onnx") for v in piper_catalog.fallback_catalog())


class _FakeRVC(BaseHTTPRequestHandler):
    state = {"model": None, "params": None, "loads": 0}

    def log_message(self, *args):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._json(200, {"models": ["Alice", "Bob"]})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length) or b"{}")
        if self.path.startswith("/models/"):
            self.state["model"] = self.path.rsplit("/", 1)[-1]
            self.state["loads"] += 1
            return self._json(200, {"message": "ok"})
        if self.path == "/params":
            self.state["params"] = payload["params"]
            return self._json(200, {"message": "ok"})
        if self.path == "/convert":
            if not self.state["model"]:
                return self._json(400, {"detail": "No model loaded. Please load a model first."})
            data, rate = sf.read(io.BytesIO(base64.b64decode(payload["audio_data"])), dtype="float32")
            out = io.BytesIO()
            sf.write(out, data * 0.5, rate, format="WAV")
            body = out.getvalue()
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)


def test_rvc_client_roundtrip():
    server = HTTPServer(("127.0.0.1", 0), _FakeRVC)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        client = RVCClient(f"http://127.0.0.1:{server.server_port}")
        assert client.list_models() == ["Alice", "Bob"]
        clip = Clip(np.full(1600, 0.4, dtype=np.float32), 16000)
        out = client.convert(clip, "Alice", pitch=12)
        assert out.sample_rate == 16000 and np.allclose(out.samples, 0.2, atol=1e-3)
        assert _FakeRVC.state["params"] == {"f0up_key": 12, "f0method": "rmvpe"}
        client.convert(clip, "Alice", pitch=12)
        assert _FakeRVC.state["loads"] == 1  # model stays loaded
        _FakeRVC.state["model"] = None  # server restarted
        client.convert(clip, "Alice", pitch=12)
        assert _FakeRVC.state["loads"] == 2
    finally:
        server.shutdown()


def test_rvc_client_offline():
    client = RVCClient("http://127.0.0.1:9")
    assert not client.is_online()
    with pytest.raises(TTSError):
        client.list_models()


def test_memory_cache_is_int16_and_bounded(service, monkeypatch):
    from kmuted.tts import manager

    svc, engine = service
    monkeypatch.setattr(manager, "MEMORY_CACHE_BYTES", 40_000)
    for i in range(10):
        svc.synthesize(f"фраза {i}", VoiceProfile())
    assert svc._memory_bytes <= 40_000 or len(svc._memory) == 1
    cached = next(iter(svc._memory.values()))
    assert cached.pcm.dtype == np.int16
    # round trip keeps the signal
    clip = svc.synthesize("фраза 9", VoiceProfile())
    assert clip.samples.dtype == np.float32 and np.max(np.abs(clip.samples)) > 0.4


def test_failed_prewarm_is_not_retried_immediately(service):
    svc, _ = service

    class Broken(FakeEngine):
        def synthesize(self, text, profile):
            self.calls += 1
            raise TTSError("offline")

    broken = Broken()
    svc.engines["edge"] = broken
    svc.prewarm([("раз", VoiceProfile())])
    svc._warm_pool.submit(lambda: None).result(timeout=5)
    svc.prewarm([("раз", VoiceProfile())])
    svc._warm_pool.submit(lambda: None).result(timeout=5)
    assert broken.calls == 1
