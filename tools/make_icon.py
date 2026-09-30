"""Render the app logo to an .ico file (used by the exe build)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def make_icon(dest: Path) -> Path:
    from PySide6.QtGui import QGuiApplication

    from kmuted.ui.icons import render_logo

    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841 - needed for QPixmap
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not render_logo(256).save(str(dest), "ICO"):
        raise RuntimeError(f"could not write {dest}")
    return dest


if __name__ == "__main__":
    print(make_icon(Path(sys.argv[1] if len(sys.argv) > 1 else "build/kmuted.ico")))
