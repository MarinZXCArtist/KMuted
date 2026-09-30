"""Updates from GitHub Releases.

The release workflow attaches ``KMuted-Setup-<version>.exe``. The app checks
the latest release at most once a day, and on request downloads the
installer and runs it in silent mode; the installer relaunches KMuted.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from kmuted import __version__

log = logging.getLogger(__name__)

REPO = "MarinZXCArtist/KMuted"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"


@dataclass
class Release:
    version: str
    notes: str
    page_url: str
    installer_url: str = ""
    installer_name: str = ""


def parse_version(text: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in nums[:4]) or (0,)


def is_newer(candidate: str, current: str = __version__) -> bool:
    return parse_version(candidate) > parse_version(current)


def parse_release(data: dict) -> Release:
    tag = str(data.get("tag_name") or "")
    release = Release(tag.lstrip("vV"), str(data.get("body") or "")[:2000], str(data.get("html_url") or RELEASES_PAGE))
    for asset in data.get("assets") or []:
        name = str(asset.get("name") or "")
        if name.lower().endswith(".exe") and "setup" in name.lower():
            release.installer_url = str(asset.get("browser_download_url") or "")
            release.installer_name = name
            break
    return release


def check_latest(timeout: float = 10) -> Release | None:
    """The latest release if it is newer than this build, else None."""
    request = urllib.request.Request(LATEST_URL, headers={"User-Agent": "KMuted", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        release = parse_release(json.load(response))
    return release if release.version and is_newer(release.version) else None


def download_installer(
    release: Release,
    progress: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> Path:
    if not release.installer_url:
        raise RuntimeError("no installer in this release")
    dest = Path(tempfile.mkdtemp(prefix="kmuted_update_")) / (release.installer_name or "KMuted-Setup.exe")
    request = urllib.request.Request(release.installer_url, headers={"User-Agent": "KMuted"})
    with urllib.request.urlopen(request, timeout=60) as response, open(dest, "wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while True:
            if cancelled and cancelled():
                raise InterruptedError
            chunk = response.read(256 * 1024)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    return dest


def can_self_update() -> bool:
    """Only installed Windows builds can replace themselves."""
    return sys.platform == "win32" and bool(getattr(sys, "frozen", False))


def run_installer(path: Path) -> None:
    """Silent install over the current version; the installer restarts KMuted."""
    subprocess.Popen(
        [str(path), "/SP-", "/SILENT", "/NOCANCEL", "/CLOSEAPPLICATIONS", "/NORESTART"],
        close_fds=True,
    )
