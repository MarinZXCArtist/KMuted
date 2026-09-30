"""Placeholders inside phrases: {время}, {дата}, {буфер}, {случайно:а|б|в}…"""

from __future__ import annotations

import random
import re
from datetime import datetime

from kmuted.i18n import language

_TOKEN = re.compile(r"\{([^{}]+)\}")

_MONTHS_RU = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
              "сентября", "октября", "ноября", "декабря"]
_MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August",
              "September", "October", "November", "December"]
_DAYS_RU = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
_DAYS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# (names, description) — shown in the UI help
VARIABLES = [
    (("время", "time"), "текущее время, например 14:05"),
    (("дата", "date"), "сегодняшняя дата, например 30 сентября"),
    (("день", "day"), "день недели"),
    (("буфер", "clipboard"), "текст из буфера обмена"),
    (("случайно:а|б|в", "random:a|b|c"), "случайный вариант из списка"),
    (("число:1-100", "number:1-100"), "случайное число в диапазоне"),
]


def has_vars(text: str) -> bool:
    return bool(_TOKEN.search(text))


def expand(text: str, now: datetime | None = None, clipboard: str | None = None, rng: random.Random | None = None) -> str:
    if "{" not in text:
        return text
    now = now or datetime.now()
    rng = rng or random
    ru = language() == "ru"

    def repl(match: re.Match) -> str:
        body = match.group(1).strip()
        name, _, arg = body.partition(":")
        name = name.strip().lower()
        if name in ("время", "time"):
            return now.strftime("%H:%M")
        if name in ("дата", "date"):
            return f"{now.day} {_MONTHS_RU[now.month - 1]}" if ru else f"{_MONTHS_EN[now.month - 1]} {now.day}"
        if name in ("день", "day"):
            return (_DAYS_RU if ru else _DAYS_EN)[now.weekday()]
        if name in ("буфер", "clipboard"):
            return (clipboard or "").strip()[:300]
        if name in ("случайно", "random") and arg:
            options = [o.strip() for o in arg.split("|") if o.strip()]
            return rng.choice(options) if options else ""
        if name in ("число", "number") and arg:
            lo, _, hi = arg.partition("-")
            try:
                a, b = int(lo), int(hi or lo)
                return str(rng.randint(min(a, b), max(a, b)))
            except ValueError:
                return match.group(0)
        return match.group(0)  # unknown: leave as typed

    return _TOKEN.sub(repl, text)
