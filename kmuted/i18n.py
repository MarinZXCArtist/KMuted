"""Interface language (Russian / English).

Russian text in the code is the source of truth; ``tr("…")`` returns the
English version from :mod:`kmuted.i18n_en` when English is active.
Placeholders use ``str.format``: ``tr("Голос: {name}", name=voice)``.
"""

from __future__ import annotations

import locale
import logging

from kmuted import paths

log = logging.getLogger(__name__)

LANGUAGES = {"ru": "Русский", "en": "English"}
_RU_FAMILY = {"ru", "uk", "be", "kk", "ky", "uz", "tg", "hy", "az", "ka"}
_current = "ru"


def set_language(code: str) -> str:
    global _current
    _current = code if code in LANGUAGES else "ru"
    return _current


def language() -> str:
    return _current


def tr(source: str, /, **kwargs) -> str:
    text = source
    if _current == "en":
        from kmuted.i18n_en import EN

        text = EN.get(source, source)
    return text.format(**kwargs) if kwargs else text


def plural(n: int, one: str, few: str, many: str) -> str:
    """"1 фраза", "3 фразы", "5 фраз" (Russian forms are the source; see tr)."""
    if _current == "en":
        return f"{n} {tr(one) if n == 1 else tr(many)}"
    if n % 10 == 1 and n % 100 != 11:
        form = one
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        form = few
    else:
        form = many
    return f"{n} {form}"


def installer_choice() -> str:
    """Language picked in the installer (written next to the settings)."""
    hint = paths.data_dir() / "language.txt"
    try:
        code = hint.read_text(encoding="utf-8").strip().lower()
    except OSError:
        return ""
    return code if code in LANGUAGES else ""


def system_language() -> str:
    code = ""
    try:
        from PySide6.QtCore import QLocale

        code = QLocale.system().name().split("_")[0].lower()
    except Exception:
        try:
            code = (locale.getlocale()[0] or "").split("_")[0].lower()
        except Exception:
            code = ""
    return "ru" if code in _RU_FAMILY else "en"


def resolve(configured: str) -> str:
    """Setting -> installer choice -> system language."""
    if configured in LANGUAGES:
        return configured
    return installer_choice() or system_language()
