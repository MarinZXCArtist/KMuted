"""Build dist/KMuted/KMuted.exe (+ a zip) with PyInstaller.

    python tools/build_exe.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
DIST = ROOT / "dist"


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from kmuted import __version__

    icon = BUILD / "kmuted.ico"
    subprocess.run([sys.executable, str(ROOT / "tools" / "make_icon.py"), str(icon)], check=True)

    args = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        "KMuted",
        "--icon",
        str(icon),
        "--paths",
        str(ROOT),
        # user artwork (assets/README.md) bundled into the exe
        "--add-data",
        f"{ROOT / 'assets'}{os.pathsep}assets",
        # Piper ships espeak-ng data files next to its code
        "--collect-data",
        "piper",
        "--collect-binaries",
        "piper",
        "--hidden-import",
        "win32timezone",
        "--exclude-module",
        "tkinter",
        "--exclude-module",
        "matplotlib",
        "--exclude-module",
        "IPython",
        str(ROOT / "run_kmuted.py"),
    ]
    subprocess.run(args, check=True, cwd=ROOT)

    app_dir = DIST / "KMuted"
    for extra in ("README.md", "start_rvc_server.bat"):
        if (ROOT / extra).exists():
            shutil.copy2(ROOT / extra, app_dir / extra)
    archive = shutil.make_archive(str(DIST / f"KMuted-{__version__}-windows"), "zip", DIST, "KMuted")
    print(f"\nГотово: {app_dir / 'KMuted.exe'}\nАрхив:  {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
