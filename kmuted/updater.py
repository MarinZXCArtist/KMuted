"""Updates from GitHub Releases.

The release workflow attaches ``KMuted-Setup-<version>.exe``. The app checks
the latest release at most once a day, and on request:

* an installed / portable ``KMuted.exe`` downloads the installer and runs it
  silently; the installer relaunches KMuted;
* a copy started from the downloaded source ZIP (``run.bat``) downloads the
  release's source, copies it over its own folder and restarts through
  ``run.bat`` (which installs new libraries if requirements changed).
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from kmuted import __version__, paths

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
    source_url: str = ""  # zip of the release's source code


def parse_version(text: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in nums[:4]) or (0,)


def is_newer(candidate: str, current: str = __version__) -> bool:
    return parse_version(candidate) > parse_version(current)


def parse_release(data: dict) -> Release:
    tag = str(data.get("tag_name") or "")
    release = Release(tag.lstrip("vV"), str(data.get("body") or "")[:2000], str(data.get("html_url") or RELEASES_PAGE))
    release.source_url = str(data.get("zipball_url") or "")
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
    return _download(release.installer_url, dest, progress, cancelled)


def download_source(
    release: Release,
    progress: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> Path:
    if not release.source_url:
        raise RuntimeError("no source archive in this release")
    dest = Path(tempfile.mkdtemp(prefix="kmuted_update_")) / f"KMuted-{release.version}.zip"
    return _download(release.source_url, dest, progress, cancelled)


def _download(url: str, dest: Path, progress, cancelled) -> Path:
    request = urllib.request.Request(url, headers={"User-Agent": "KMuted"})
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


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def is_source_copy(root: Path | None = None) -> bool:
    """Started from the downloaded ZIP with run.bat (not a git checkout)."""
    root = root or paths.app_dir()
    return (
        not is_frozen()
        and (root / "run.bat").is_file()
        and (root / "kmuted" / "__init__.py").is_file()
        and not (root / ".git").exists()
    )


def can_self_update() -> bool:
    """Windows builds and ZIP copies can update themselves in one click."""
    return sys.platform == "win32" and (is_frozen() or is_source_copy())


# folders of a source copy that an update must not touch
_KEEP_TOP = {".venv", "data", "dist", "build", ".git"}


def install_source(archive: Path, root: Path | None = None) -> str:
    """Copy the release source from ``archive`` over ``root``; returns its version.

    Only adds and replaces files: the virtual environment, settings in
    ``data`` and anything else of the user's stays as it is.
    """
    root = root or paths.app_dir()
    work = Path(tempfile.mkdtemp(prefix="kmuted_src_"))
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(work)  # strips absolute paths and ".." parts
    tops = [d for d in work.iterdir() if d.is_dir()]
    src = tops[0] if len(tops) == 1 else work
    init = src / "kmuted" / "__init__.py"
    if not init.is_file() or not (src / "run.bat").is_file():
        raise RuntimeError("the archive does not look like KMuted")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', init.read_text(encoding="utf-8"))
    version = match.group(1) if match else ""

    def ignore(folder: str, names: list[str]) -> set[str]:
        skip = {n for n in names if n == "__pycache__"}
        if Path(folder) == src:
            skip |= {n for n in names if n in _KEEP_TOP}
        return skip

    shutil.copytree(src, root, dirs_exist_ok=True, ignore=ignore)
    shutil.rmtree(work, ignore_errors=True)
    return version


def restart_source(root: Path | None = None) -> None:
    """Start the updated copy through run.bat once this process has exited."""
    root = root or paths.app_dir()
    flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    subprocess.Popen(["cmd", "/c", "run.bat", "--restart"], cwd=str(root), creationflags=flags, close_fds=True)


def run_installer(path: Path) -> None:
    """Silent install over the current version; the installer restarts KMuted."""
    subprocess.Popen(
        [str(path), "/SP-", "/SILENT", "/NOCANCEL", "/CLOSEAPPLICATIONS", "/NORESTART"],
        close_fds=True,
    )
