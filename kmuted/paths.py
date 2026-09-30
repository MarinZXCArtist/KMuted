"""Where KMuted keeps its settings, cache and voice models."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from kmuted import APP_NAME


def app_dir() -> Path:
    """Folder with the executable (frozen build) or the project root."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """Settings folder.

    Priority: ``KMUTED_HOME`` env var, then a ``data`` folder next to the
    executable (portable mode), then the per-user config folder.
    """
    override = os.environ.get("KMUTED_HOME")
    if override:
        base = Path(override)
    elif getattr(sys, "frozen", False) and (app_dir() / "data").is_dir():
        base = app_dir() / "data"
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home()) / APP_NAME
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "kmuted"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _subdir(*parts: str) -> Path:
    path = data_dir().joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return data_dir() / "config.json"


def log_path() -> Path:
    return data_dir() / "kmuted.log"


def cache_dir() -> Path:
    return _subdir("cache")


def piper_voices_dir() -> Path:
    return _subdir("voices", "piper")


def rvc_models_dir() -> Path:
    return _subdir("voices", "rvc")
