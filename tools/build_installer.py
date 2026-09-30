"""Build dist/KMuted-Setup-<version>.exe with Inno Setup 6.

    python tools/build_installer.py            # builds the exe first
    python tools/build_installer.py --no-exe   # reuse dist/KMuted
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def find_iscc() -> str:
    found = shutil.which("iscc") or shutil.which("ISCC")
    if found:
        return found
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
        if base:
            for sub in ("Inno Setup 6", r"Programs\Inno Setup 6"):
                candidate = Path(base) / sub / "ISCC.exe"
                if candidate.exists():
                    return str(candidate)
    raise SystemExit("Inno Setup 6 не найден. Установите его: https://jrsoftware.org/isdl.php")


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from kmuted import __version__

    if "--no-exe" not in sys.argv:
        subprocess.run([sys.executable, str(ROOT / "tools" / "build_exe.py")], check=True)
    subprocess.run([sys.executable, str(ROOT / "tools" / "make_installer_art.py"), str(ROOT / "build")], check=True)
    if not (ROOT / "build" / "kmuted.ico").exists():
        subprocess.run([sys.executable, str(ROOT / "tools" / "make_icon.py"), str(ROOT / "build" / "kmuted.ico")], check=True)
    subprocess.run([find_iscc(), f"/DMyAppVersion={__version__}", str(ROOT / "installer" / "kmuted.iss")], check=True)
    print(f"\nГотово: {ROOT / 'dist' / f'KMuted-Setup-{__version__}.exe'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
