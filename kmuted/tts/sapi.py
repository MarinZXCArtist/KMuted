"""Windows built-in voices via SAPI 5 (offline).

Lists classic SAPI voices and, when possible, the newer "OneCore" voices
(Microsoft Irina/Pavel/Svetlana etc. installed with language packs).
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from xml.sax.saxutils import escape

from kmuted.audio.dsp import Clip
from kmuted.config import VoiceProfile
from kmuted.tts.base import TTSEngine, TTSError, VoiceInfo
from kmuted.i18n import tr

log = logging.getLogger(__name__)

_CATEGORIES = (
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices",
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices",
)
SSFM_CREATE_FOR_WRITE = 3
SVSF_IS_XML = 8
SVSF_IS_NOT_XML = 16

# LCID (hex, as SAPI stores it) -> locale, for the most relevant languages
_LCIDS = {
    "419": "ru-RU",
    "422": "uk-UA",
    "423": "be-BY",
    "409": "en-US",
    "809": "en-GB",
    "407": "de-DE",
    "40c": "fr-FR",
    "c0a": "es-ES",
    "410": "it-IT",
    "415": "pl-PL",
    "43f": "kk-KZ",
}


class SapiEngine(TTSEngine):
    key = "sapi"
    title = "Windows (офлайн)"
    description = "Голоса, установленные в Windows. Работают без интернета."

    def __init__(self) -> None:
        self._voices: list[VoiceInfo] | None = None

    def availability(self) -> str:
        if sys.platform != "win32":
            return tr("Голоса Windows доступны только в Windows")
        try:
            import win32com.client  # noqa: F401
        except ImportError:
            return tr("Не установлен пакет pywin32")
        return ""

    def _tokens(self):
        import win32com.client

        seen = set()
        for category_id in _CATEGORIES:
            try:
                category = win32com.client.Dispatch("SAPI.SpObjectTokenCategory")
                category.SetId(category_id, False)
                tokens = category.EnumerateTokens()
            except Exception as exc:
                log.debug("SAPI category %s unavailable: %s", category_id, exc)
                continue
            for i in range(tokens.Count):
                token = tokens.Item(i)
                try:
                    desc = token.GetDescription()
                except Exception:
                    continue
                if desc in seen:
                    continue
                seen.add(desc)
                yield token, desc

    def list_voices(self, refresh: bool = False) -> list[VoiceInfo]:
        if self._voices is not None and not refresh:
            return self._voices
        if self.availability():
            return []
        import pythoncom

        pythoncom.CoInitialize()
        try:
            voices = self._collect_voices()
        except Exception as exc:
            log.warning("SAPI voice list failed: %s", exc)
            voices = []
        finally:
            pythoncom.CoUninitialize()
        voices.sort(key=lambda v: (not v.language.startswith("ru"), v.name))
        self._voices = voices
        return voices

    def _collect_voices(self) -> list[VoiceInfo]:
        # COM objects must be released before CoUninitialize, so they live
        # only inside this helper.
        voices = []
        for token, desc in self._tokens():
            lang = gender = ""
            try:
                lcid = (token.GetAttribute("Language") or "").split(";")[0].lower()
                lang = _LCIDS.get(lcid, lcid)
                gender = token.GetAttribute("Gender") or ""
            except Exception:
                pass
            voices.append(VoiceInfo(token.Id, desc, lang, gender))
        return voices

    def _speak_to_file(self, text: str, profile: VoiceProfile, wav_path: str) -> None:
        import win32com.client

        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        if profile.voice:
            for token, _desc in self._tokens():
                if token.Id == profile.voice:
                    speaker.Voice = token
                    break
        speaker.Rate = max(-10, min(10, round(profile.rate / 10)))
        stream = win32com.client.Dispatch("SAPI.SpFileStream")
        stream.Open(wav_path, SSFM_CREATE_FOR_WRITE, False)
        try:
            speaker.AudioOutputStream = stream
            pitch = max(-10, min(10, round(profile.pitch / 5)))
            if pitch:
                speaker.Speak(f'<pitch absmiddle="{pitch}">{escape(text)}</pitch>', SVSF_IS_XML)
            else:
                speaker.Speak(text, SVSF_IS_NOT_XML)
        finally:
            stream.Close()

    def synthesize(self, text: str, profile: VoiceProfile) -> Clip:
        reason = self.availability()
        if reason:
            raise TTSError(reason)
        import pythoncom
        import soundfile as sf

        fd, wav_path = tempfile.mkstemp(prefix="kmuted_", suffix=".wav")
        os.close(fd)
        pythoncom.CoInitialize()
        try:
            self._speak_to_file(text, profile, wav_path)
            samples, rate = sf.read(wav_path, dtype="float32", always_2d=False)
        except Exception as exc:
            raise TTSError(tr("Голос Windows: {error}", error=exc)) from exc
        finally:
            pythoncom.CoUninitialize()
            try:
                os.remove(wav_path)
            except OSError:
                pass
        return Clip(samples, int(rate))
