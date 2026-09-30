"""RVC voice conversion — the custom voices used by AI voice changers.

RVC models (``model.pth`` + optional ``*.index``) need PyTorch, which is
huge and picky about versions, so KMuted doesn't load them itself. It
talks to a local `rvc-python <https://github.com/daswer123/rvc-python>`_
server instead (see ``start_rvc_server.bat``). Pipeline:

    text -> TTS voice -> RVC server (your model) -> virtual microphone

Models live in ``<data>/voices/rvc/<ModelName>/model.pth``; the server is
started with that folder as ``--models_dir``.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import threading
import urllib.error
import urllib.request

import soundfile as sf

from kmuted.audio.dsp import Clip
from kmuted.tts.base import TTSError

log = logging.getLogger(__name__)


class RVCClient:
    def __init__(self, base_url: str = "http://127.0.0.1:5050") -> None:
        self.base_url = base_url.rstrip("/")
        self._lock = threading.Lock()
        self._loaded_model: str | None = None
        self._params: dict | None = None

    def set_url(self, url: str) -> None:
        url = (url or "").rstrip("/")
        if url != self.base_url:
            self.base_url = url
            self._loaded_model = None
            self._params = None

    # --- HTTP ----------------------------------------------------------------

    def _request(self, method: str, path: str, payload: dict | None = None, timeout: float = 120):
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read(), response.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            try:
                detail = json.loads(detail).get("detail", detail)
            except (ValueError, AttributeError):
                pass
            raise TTSError(f"RVC сервер: {detail}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise TTSError(
                f"RVC сервер не отвечает ({self.base_url}). Запустите start_rvc_server.bat. ({exc})"
            ) from exc

    def list_models(self) -> list[str]:
        body, _ = self._request("GET", "/models", timeout=5)
        try:
            return sorted(json.loads(body).get("models", []))
        except (ValueError, AttributeError) as exc:
            raise TTSError("RVC сервер вернул некорректный список моделей") from exc

    def is_online(self) -> bool:
        try:
            self._request("GET", "/models", timeout=2)
            return True
        except TTSError:
            return False

    # --- conversion ----------------------------------------------------------

    def convert(self, clip: Clip, model: str, pitch: int = 0, method: str = "rmvpe") -> Clip:
        if not model:
            raise TTSError("Не выбрана RVC-модель")
        wav = io.BytesIO()
        sf.write(wav, clip.samples, clip.sample_rate, format="WAV", subtype="PCM_16")
        payload = {"audio_data": base64.b64encode(wav.getvalue()).decode("ascii")}
        # The server holds one model at a time: serialize load+convert.
        with self._lock:
            self._prepare(model, pitch, method)
            try:
                body, _ = self._request("POST", "/convert", payload)
            except TTSError as exc:
                if "No model loaded" not in str(exc):
                    raise
                self._loaded_model = None  # server restarted — load again
                self._prepare(model, pitch, method)
                body, _ = self._request("POST", "/convert", payload)
        try:
            samples, rate = sf.read(io.BytesIO(body), dtype="float32", always_2d=False)
        except Exception as exc:
            raise TTSError(f"RVC сервер вернул не WAV: {exc}") from exc
        return Clip(samples, int(rate))

    def _prepare(self, model: str, pitch: int, method: str) -> None:
        if self._loaded_model != model:
            self._request("POST", "/models/" + urllib.request.quote(model, safe=""), timeout=180)
            self._loaded_model = model
            self._params = None
        params = {"f0up_key": int(pitch), "f0method": method or "rmvpe"}
        if self._params != params:
            self._request("POST", "/params", {"params": params}, timeout=10)
            self._params = params
