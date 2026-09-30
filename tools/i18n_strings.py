"""List every Russian UI string that needs an English translation.

    python tools/i18n_strings.py          # all strings
    python tools/i18n_strings.py --missing  # only those without a translation
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CYR = re.compile(r"[А-Яа-яЁё]")


def literal_tr_strings() -> set[str]:
    found: set[str] = set()
    for path in (ROOT / "kmuted").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "tr"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                found.add(node.args[0].value)
    return found


def indirect_strings() -> set[str]:
    """Strings kept in constants and translated where they are shown."""
    sys.path.insert(0, str(ROOT))
    from kmuted import actions, textvars
    from kmuted.hotkeys import keys
    from kmuted.tts.cloud import CLOUD_CLASSES
    from kmuted.tts.edge import EdgeEngine
    from kmuted.tts.piper_engine import PiperEngine
    from kmuted.tts.sapi import SapiEngine
    from kmuted.ui import page_audio, page_home, page_settings, page_voices, theme

    out: set[str] = set()
    for a in actions.ACTIONS:
        out.update((a.title, a.description, a.group))
    out.update(theme.ACCENT_NAMES.values())
    for cls in (EdgeEngine, SapiEngine, PiperEngine, *CLOUD_CLASSES):
        out.update((cls.title, cls.description))
        out.add(getattr(cls, "pricing", ""))
        out.update(label for _id, label in getattr(cls, "models", ()))
    out.update(label for _k, label in page_voices.RVC_METHODS)
    out.add(page_audio.SETUP_HTML)
    out.update(page_home.ENGINE_NAMES.values())
    out.add(page_home.CLOUD_NAME)
    out.update(page_settings._PART_NAMES.values())
    out.update(("Сверху", "По центру", "Снизу"))
    out.update(d for _n, d in textvars.VARIABLES)
    out.update(keys._DISPLAY.values())
    from kmuted.ui import main_window

    out.update(title for _i, title, _c in main_window.PAGES)
    from kmuted import config

    for text, label in config.DEFAULT_WHEEL:
        out.update((text, label))
    return {s for s in out if s and CYR.search(s)}


def all_strings() -> set[str]:
    return {s for s in literal_tr_strings() if CYR.search(s)} | indirect_strings()


if __name__ == "__main__":
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    strings = sorted(all_strings())
    if "--missing" in sys.argv:
        from kmuted.i18n_en import EN

        strings = [s for s in strings if s not in EN]
    for s in strings:
        print(repr(s))
    print(len(strings), file=sys.stderr)
