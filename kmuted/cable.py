"""Helping the user get VB-Audio Virtual Cable installed.

KMuted can't ship the driver (it's VB-Audio's donationware), but it can
fetch the official package from vb-audio.com on request and start its
installer — so setup is two clicks instead of a hunt through a website.
"""

from __future__ import annotations

import logging
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

CABLE_PAGE = "https://vb-audio.com/Cable/"
# Official download links, newest first; the page is the fallback.
CABLE_ZIPS = (
    "https://download.vb-audio.com/Download_CABLE/VBCABLE_Driver_Pack45.zip",
    "https://download.vb-audio.com/Download_CABLE/VBCABLE_Driver_Pack43.zip",
)


def download_installer(
    progress: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> Path:
    """Download + unpack the driver pack; returns the setup .exe path."""
    target = Path(tempfile.mkdtemp(prefix="kmuted_vbcable_"))
    errors = []
    for url in CABLE_ZIPS:
        archive = target / "vbcable.zip"
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "KMuted"})
            with urllib.request.urlopen(request, timeout=30) as response, open(archive, "wb") as out:
                total = int(response.headers.get("Content-Length") or 0)
                done = 0
                while True:
                    if cancelled and cancelled():
                        raise InterruptedError("Загрузка отменена")
                    chunk = response.read(128 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(target)
            setup = pick_setup(target)
            if setup is None:
                raise FileNotFoundError("в архиве нет установщика")
            return setup
        except InterruptedError:
            raise
        except Exception as exc:
            errors.append(f"{url.rsplit('/', 1)[-1]}: {exc}")
            log.warning("VB-Cable download failed from %s: %s", url, exc)
    raise RuntimeError("; ".join(errors))


def pick_setup(folder: Path) -> Path | None:
    exes = list(folder.rglob("VBCABLE_Setup*.exe"))
    if not exes:
        return None
    x64 = [e for e in exes if "x64" in e.name.lower()]
    return (x64 or exes)[0]


def run_installer(setup: Path) -> bool:
    """Start the installer elevated (Windows shows the UAC prompt)."""
    if sys.platform != "win32":
        return False
    import ctypes

    result = ctypes.windll.shell32.ShellExecuteW(None, "runas", str(setup), None, str(setup.parent), 1)
    return int(result) > 32
