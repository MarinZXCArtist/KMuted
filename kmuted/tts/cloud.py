"""Cloud voice services (need an API key from the provider).

All talk plain HTTPS through ``urllib`` — no extra dependencies. Prices and
free limits change; the descriptions below only point the user in the right
direction and link to the provider's own pages.
"""

from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable
from xml.sax.saxutils import escape

from kmuted.audio.dsp import Clip
from kmuted.config import CloudSettings, VoiceProfile
from kmuted.i18n import tr
from kmuted.tts.base import TTSEngine, TTSError, VoiceInfo
from kmuted.tts.edge import decode_audio_bytes

log = logging.getLogger(__name__)

TIMEOUT = 30


def _http(method: str, url: str, headers: dict | None = None, body: bytes | None = None, timeout: float = TIMEOUT) -> bytes:
    request = urllib.request.Request(url, data=body, headers={"User-Agent": "KMuted", **(headers or {})}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        if exc.code in (401, 403):
            raise TTSError(tr("Сервис отклонил ключ API (код {code}). Проверьте ключ в настройках голосов.", code=exc.code)) from exc
        if exc.code == 429:
            raise TTSError(tr("Лимит запросов или символов исчерпан (код 429).")) from exc
        raise TTSError(tr("Ошибка сервиса ({code}): {detail}", code=exc.code, detail=detail)) from exc
    except (urllib.error.URLError, OSError) as exc:
        raise TTSError(tr("Нет связи с сервисом: {error}", error=exc)) from exc


def _json(method: str, url: str, payload=None, headers: dict | None = None) -> dict:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    hdrs = {"Content-Type": "application/json", **(headers or {})} if body else dict(headers or {})
    raw = _http(method, url, hdrs, body)
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise TTSError(tr("Сервис вернул непонятный ответ")) from exc


class CloudEngine(TTSEngine):
    """Base: holds a getter for the current :class:`CloudSettings`."""

    key_field = ""
    signup_url = ""
    pricing = ""  # short hint shown in the UI
    models: tuple[tuple[str, str], ...] = ()  # (id, label)

    def __init__(self, settings: Callable[[], CloudSettings]) -> None:
        self._settings = settings
        self._voices: list[VoiceInfo] | None = None

    @property
    def api_key(self) -> str:
        return getattr(self._settings(), self.key_field, "").strip()

    def availability(self) -> str:
        if not self.api_key:
            return tr("Нужен ключ API — вставьте его ниже")
        return ""

    def _need_key(self) -> None:
        if not self.api_key:
            raise TTSError(tr("Для «{name}» нужен ключ API (вкладка «Голоса»)", name=self.title))

    def list_voices(self, refresh: bool = False) -> list[VoiceInfo]:
        if self._voices is not None and not refresh:
            return self._voices
        if not self.api_key:
            return self.fallback_voices()
        self._voices = self.fetch_voices()
        return self._voices

    def fallback_voices(self) -> list[VoiceInfo]:
        return []

    def fetch_voices(self) -> list[VoiceInfo]:
        return self.fallback_voices()

    def forget(self) -> None:
        self._voices = None


class ElevenLabsEngine(CloudEngine):
    key = "elevenlabs"
    title = "ElevenLabs (облако)"
    description = "Самые живые голоса и ваши собственные голоса из аккаунта ElevenLabs. Платно, есть бесплатный месячный лимит."
    key_field = "elevenlabs_key"
    signup_url = "https://elevenlabs.io/app/settings/api-keys"
    pricing = "Бесплатный лимит символов в месяц, дальше — подписка"
    models = (
        ("eleven_multilingual_v2", "Multilingual v2 — лучшее качество"),
        ("eleven_flash_v2_5", "Flash v2.5 — быстрее и дешевле"),
        ("eleven_turbo_v2_5", "Turbo v2.5 — быстро"),
        ("eleven_v3", "v3 — самый выразительный"),
    )
    BASE = "https://api.elevenlabs.io/v1"

    def fetch_voices(self) -> list[VoiceInfo]:
        data = _json("GET", f"{self.BASE}/voices", headers={"xi-api-key": self.api_key})
        voices = []
        for v in data.get("voices", []):
            labels = v.get("labels") or {}
            extra = tr("ваш голос") if v.get("category") in ("cloned", "generated", "professional") else ""
            voices.append(VoiceInfo(v.get("voice_id", ""), v.get("name", "?"), labels.get("accent", ""), labels.get("gender", ""), extra))
        voices.sort(key=lambda x: (not x.extra, x.name))
        return voices

    def synthesize(self, text: str, profile: VoiceProfile) -> Clip:
        self._need_key()
        if not profile.voice:
            raise TTSError(tr("Выберите голос ElevenLabs"))
        speed = max(0.7, min(1.2, 1.0 + profile.rate / 100.0))
        payload = {
            "text": text,
            "model_id": profile.model or self.models[0][0],
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "speed": speed},
        }
        url = f"{self.BASE}/text-to-speech/{urllib.parse.quote(profile.voice)}?output_format=mp3_44100_128"
        audio = _http("POST", url, {"xi-api-key": self.api_key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
                      json.dumps(payload).encode("utf-8"))
        samples, rate = decode_audio_bytes(audio)
        return Clip(samples, rate)


class OpenAIEngine(CloudEngine):
    key = "openai"
    title = "OpenAI (облако)"
    description = "Естественные многоязычные голоса. Недорого, оплата за использование."
    key_field = "openai_key"
    signup_url = "https://platform.openai.com/api-keys"
    pricing = "Оплата за символы, без подписки"
    models = (
        ("gpt-4o-mini-tts", "gpt-4o-mini-tts — живые интонации"),
        ("tts-1", "tts-1 — быстро и дёшево"),
        ("tts-1-hd", "tts-1-hd — выше качество"),
    )
    VOICES = ("alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer", "verse")

    def fallback_voices(self) -> list[VoiceInfo]:
        return [VoiceInfo(v, v.capitalize(), "multi") for v in self.VOICES]

    def synthesize(self, text: str, profile: VoiceProfile) -> Clip:
        self._need_key()
        payload = {
            "model": profile.model or self.models[0][0],
            "voice": profile.voice or "alloy",
            "input": text,
            "response_format": "mp3",
            "speed": max(0.25, min(4.0, 1.0 + profile.rate / 100.0)),
        }
        audio = _http(
            "POST",
            "https://api.openai.com/v1/audio/speech",
            {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json.dumps(payload).encode("utf-8"),
        )
        samples, rate = decode_audio_bytes(audio)
        return Clip(samples, rate)


class AzureEngine(CloudEngine):
    key = "azure"
    title = "Microsoft Azure (облако)"
    description = "Те же нейроголоса, что в Edge, но официально и стабильно. Бесплатный тариф F0 с месячным лимитом символов."
    key_field = "azure_key"
    signup_url = "https://portal.azure.com/#create/Microsoft.CognitiveServicesSpeechServices"
    pricing = "Бесплатный тариф F0 (лимит символов в месяц)"

    def _base(self) -> str:
        region = (self._settings().azure_region or "westeurope").strip()
        return f"https://{region}.tts.speech.microsoft.com"

    def fetch_voices(self) -> list[VoiceInfo]:
        raw = _http("GET", f"{self._base()}/cognitiveservices/voices/list", {"Ocp-Apim-Subscription-Key": self.api_key})
        try:
            items = json.loads(raw)
        except ValueError as exc:
            raise TTSError(tr("Сервис вернул непонятный ответ")) from exc
        voices = [VoiceInfo(v["ShortName"], v.get("LocalName") or v.get("DisplayName", ""), v.get("Locale", ""), v.get("Gender", "")) for v in items]
        voices.sort(key=lambda v: (not v.language.startswith("ru"), v.language, v.name))
        return voices

    def fallback_voices(self) -> list[VoiceInfo]:
        return [VoiceInfo("ru-RU-DmitryNeural", "Дмитрий", "ru-RU", "Male"), VoiceInfo("ru-RU-SvetlanaNeural", "Светлана", "ru-RU", "Female")]

    def synthesize(self, text: str, profile: VoiceProfile) -> Clip:
        self._need_key()
        voice = profile.voice or "ru-RU-DmitryNeural"
        lang = "-".join(voice.split("-")[:2])
        ssml = (
            f"<speak version='1.0' xml:lang='{lang}'><voice name='{escape(voice)}'>"
            f"<prosody rate='{profile.rate:+d}%' pitch='{profile.pitch:+d}Hz'>{escape(text)}</prosody></voice></speak>"
        )
        audio = _http(
            "POST",
            f"{self._base()}/cognitiveservices/v1",
            {
                "Ocp-Apim-Subscription-Key": self.api_key,
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
            },
            ssml.encode("utf-8"),
        )
        samples, rate = decode_audio_bytes(audio)
        return Clip(samples, rate)


class GoogleEngine(CloudEngine):
    key = "google"
    title = "Google Cloud (облако)"
    description = "Голоса WaveNet / Neural2 / Chirp. Есть бесплатный месячный лимит символов."
    key_field = "google_key"
    signup_url = "https://console.cloud.google.com/apis/library/texttospeech.googleapis.com"
    pricing = "Бесплатный месячный лимит, дальше оплата за символы"
    BASE = "https://texttospeech.googleapis.com/v1"

    def fetch_voices(self) -> list[VoiceInfo]:
        data = _json("GET", f"{self.BASE}/voices?key={urllib.parse.quote(self.api_key)}")
        voices = []
        for v in data.get("voices", []):
            langs = v.get("languageCodes") or [""]
            voices.append(VoiceInfo(v.get("name", ""), v.get("name", ""), langs[0], (v.get("ssmlGender") or "").title()))
        voices.sort(key=lambda v: (not v.language.startswith("ru"), v.language, v.name))
        return voices

    def fallback_voices(self) -> list[VoiceInfo]:
        return [VoiceInfo("ru-RU-Wavenet-D", "ru-RU-Wavenet-D", "ru-RU", "Male"), VoiceInfo("ru-RU-Wavenet-A", "ru-RU-Wavenet-A", "ru-RU", "Female")]

    def synthesize(self, text: str, profile: VoiceProfile) -> Clip:
        self._need_key()
        name = profile.voice or "ru-RU-Wavenet-D"
        payload = {
            "input": {"text": text},
            "voice": {"languageCode": "-".join(name.split("-")[:2]), "name": name},
            "audioConfig": {
                "audioEncoding": "MP3",
                "speakingRate": max(0.25, min(4.0, 1.0 + profile.rate / 100.0)),
                "pitch": max(-20.0, min(20.0, profile.pitch / 2.5)),
            },
        }
        data = _json("POST", f"{self.BASE}/text:synthesize?key={urllib.parse.quote(self.api_key)}", payload)
        try:
            audio = base64.b64decode(data["audioContent"])
        except (KeyError, ValueError) as exc:
            raise TTSError(tr("Сервис вернул непонятный ответ")) from exc
        samples, rate = decode_audio_bytes(audio)
        return Clip(samples, rate)


class YandexEngine(CloudEngine):
    key = "yandex"
    title = "Yandex SpeechKit (облако)"
    description = "Лучшие русские голоса (Алёна, Филипп, Захар…). Оплата за символы, новым аккаунтам дают стартовый грант."
    key_field = "yandex_key"
    signup_url = "https://yandex.cloud/ru/docs/speechkit/quickstart"
    pricing = "Оплата за символы, стартовый грант Yandex Cloud"
    VOICES = (
        ("alena", "Алёна", "Female"), ("filipp", "Филипп", "Male"), ("ermil", "Ермил", "Male"),
        ("jane", "Джейн", "Female"), ("madirus", "Мадирус", "Male"), ("omazh", "Омаж", "Female"),
        ("zahar", "Захар", "Male"), ("dasha", "Даша", "Female"), ("julia", "Юлия", "Female"),
        ("lera", "Лера", "Female"), ("masha", "Маша", "Female"), ("marina", "Марина", "Female"),
        ("alexander", "Александр", "Male"), ("kirill", "Кирилл", "Male"), ("anton", "Антон", "Male"),
        ("john", "John", "Male"),
    )

    def fallback_voices(self) -> list[VoiceInfo]:
        return [VoiceInfo(v, name, "en-US" if v == "john" else "ru-RU", g) for v, name, g in self.VOICES]

    def synthesize(self, text: str, profile: VoiceProfile) -> Clip:
        self._need_key()
        voice = profile.voice or "alena"
        form = urllib.parse.urlencode(
            {
                "text": text,
                "lang": "en-US" if voice == "john" else "ru-RU",
                "voice": voice,
                "format": "mp3",
                "speed": f"{max(0.1, min(3.0, 1.0 + profile.rate / 100.0)):.2f}",
            }
        ).encode("utf-8")
        audio = _http(
            "POST",
            "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize",
            {"Authorization": f"Api-Key {self.api_key}", "Content-Type": "application/x-www-form-urlencoded"},
            form,
        )
        samples, rate = decode_audio_bytes(audio)
        return Clip(samples, rate)


CLOUD_CLASSES = (ElevenLabsEngine, OpenAIEngine, AzureEngine, GoogleEngine, YandexEngine)
