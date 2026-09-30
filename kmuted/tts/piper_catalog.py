"""Catalog of official Piper voices (huggingface.co/rhasspy/piper-voices)."""

from __future__ import annotations

import json
import logging
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
VOICES_JSON = BASE_URL + "voices.json?download=true"
_KEY_RE = re.compile(r"^(?P<family>[^-_]+)_(?P<region>[^-]+)-(?P<name>[^-]+)-(?P<quality>.+)$")
_USER_AGENT = {"User-Agent": "KMuted"}


@dataclass(frozen=True)
class CatalogVoice:
    key: str  # "ru_RU-irina-medium"
    language: str  # "ru_RU"
    language_name: str  # "Русский (Russia)"
    name: str
    quality: str
    num_speakers: int
    size_bytes: int
    model_path: str  # path inside the repo
    config_path: str

    @property
    def size_mb(self) -> float:
        return self.size_bytes / 1_000_000


def _default_paths(key: str) -> tuple[str, str]:
    m = _KEY_RE.match(key)
    if not m:
        raise ValueError(f"bad voice key {key!r}")
    lang = f"{m['family']}_{m['region']}"
    base = f"{m['family']}/{lang}/{m['name']}/{m['quality']}/{key}"
    return f"{base}.onnx", f"{base}.onnx.json"


# Shown when voices.json can't be fetched.
FALLBACK = [
    ("ru_RU-irina-medium", "Русский"),
    ("ru_RU-denis-medium", "Русский"),
    ("ru_RU-dmitri-medium", "Русский"),
    ("ru_RU-ruslan-medium", "Русский"),
    ("uk_UA-ukrainian_tts-medium", "Українська"),
    ("en_US-lessac-medium", "English"),
    ("en_US-ryan-high", "English"),
    ("en_GB-alan-medium", "English"),
]


def fallback_catalog() -> list[CatalogVoice]:
    out = []
    for key, lang_name in FALLBACK:
        model, cfg = _default_paths(key)
        m = _KEY_RE.match(key)
        out.append(CatalogVoice(key, f"{m['family']}_{m['region']}", lang_name, m["name"], m["quality"], 1, 0, model, cfg))
    return out


def parse_catalog(data: dict) -> list[CatalogVoice]:
    voices = []
    for key, item in data.items():
        try:
            lang = item.get("language") or {}
            files = item.get("files") or {}
            model = next((p for p in files if p.endswith(".onnx")), None)
            cfg = next((p for p in files if p.endswith(".onnx.json")), None)
            if not model or not cfg:
                model, cfg = _default_paths(key)
            native = lang.get("name_native") or lang.get("name_english") or ""
            country = lang.get("country_english") or ""
            voices.append(
                CatalogVoice(
                    key=key,
                    language=lang.get("code", ""),
                    language_name=f"{native} ({country})" if country else native,
                    name=item.get("name", key),
                    quality=item.get("quality", ""),
                    num_speakers=int(item.get("num_speakers") or 1),
                    size_bytes=int((files.get(model) or {}).get("size_bytes") or 0),
                    model_path=model,
                    config_path=cfg,
                )
            )
        except (AttributeError, TypeError, ValueError) as exc:
            log.debug("skip catalog entry %s: %s", key, exc)
    voices.sort(key=lambda v: (not v.language.startswith("ru"), v.language, v.name, v.quality))
    return voices


def fetch_catalog(timeout: float = 20) -> list[CatalogVoice]:
    request = urllib.request.Request(VOICES_JSON, headers=_USER_AGENT)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return parse_catalog(json.load(response))


def download_voice(
    voice: CatalogVoice,
    dest_dir: Path,
    progress: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> Path:
    """Download model + config into ``dest_dir``; returns the .onnx path."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    model_dest = dest_dir / f"{voice.key}.onnx"
    config_dest = dest_dir / f"{voice.key}.onnx.json"
    _download(BASE_URL + voice.config_path + "?download=true", config_dest, None, cancelled)
    _download(BASE_URL + voice.model_path + "?download=true", model_dest, progress, cancelled)
    return model_dest


def _download(url: str, dest: Path, progress, cancelled) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    request = urllib.request.Request(url, headers=_USER_AGENT)
    try:
        with urllib.request.urlopen(request, timeout=30) as response, open(tmp, "wb") as out:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            while True:
                if cancelled and cancelled():
                    raise InterruptedError("Загрузка отменена")
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
        tmp.replace(dest)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
