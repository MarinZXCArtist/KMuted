"""Common interface for speech engines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from kmuted.audio.dsp import Clip
from kmuted.config import VoiceProfile


class TTSError(RuntimeError):
    """User-facing synthesis error (message is shown as is)."""


@dataclass(frozen=True)
class VoiceInfo:
    id: str  # what goes into VoiceProfile.voice
    name: str  # display name
    language: str = ""  # e.g. "ru-RU"
    gender: str = ""
    extra: str = ""  # e.g. model quality, "онлайн"

    @property
    def label(self) -> str:
        parts = [self.name]
        meta = ", ".join(p for p in (self.language, self.gender, self.extra) if p)
        if meta:
            parts.append(f"({meta})")
        return " ".join(parts)


class TTSEngine(ABC):
    key: str = ""
    title: str = ""
    description: str = ""

    def availability(self) -> str:
        """Empty string if usable, otherwise a reason for the user."""
        return ""

    @abstractmethod
    def list_voices(self, refresh: bool = False) -> list[VoiceInfo]: ...

    @abstractmethod
    def synthesize(self, text: str, profile: VoiceProfile) -> Clip: ...
