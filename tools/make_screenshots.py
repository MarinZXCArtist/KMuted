"""Screenshots for the README: docs/screenshots/<ru|en>/*.png

    python tools/make_screenshots.py          # both languages
    python tools/make_screenshots.py en

Runs the real UI off-screen with sample phrases, game profiles and a stub
translator (no network, no sound device, nothing touches your settings).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"

SAMPLES = {
    "ru": {
        "typed": "Ребята, я на точке B, нужна помощь!",
        "history": ["Ребята, я на точке B, нужна помощь!", "Спасибо за игру!", "Секунду, я отойду."],
        "target": "en",
        "translations": {
            "Ребята, я на точке B, нужна помощь!": "Guys, I'm on B, need backup!",
            "го на бэ, у них никого": "Push B, they've got nobody there!",
        },
        "test": "го на бэ, у них никого",
        "cs_phrases": [("Рашим B!", "alt+5"), ("Снайпер на миде", "alt+6")],
    },
    "en": {
        "typed": "Guys, I'm on B, need backup!",
        "history": ["Guys, I'm on B, need backup!", "GG, well played!", "One sec, be right back."],
        "target": "es",
        "translations": {
            "Guys, I'm on B, need backup!": "¡Chicos, estoy en B, necesito refuerzos!",
            "push B, they have nobody": "¡Vamos a B, no tienen a nadie!",
        },
        "test": "push B, they have nobody",
        "cs_phrases": [("Rush B!", "alt+5"), ("Sniper mid", "alt+6")],
    },
}


def shoot(lang: str) -> None:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["KMUTED_HOME"] = tempfile.mkdtemp(prefix="kmuted-shots-")
    sys.path.insert(0, str(ROOT))
    from types import SimpleNamespace

    from PySide6.QtWidgets import QApplication

    from kmuted import i18n

    i18n.set_language(lang)
    from kmuted import processes
    from kmuted.config import GameProfile, Phrase, Sound, default_config
    from kmuted.controller import Controller
    from kmuted.hotkeys.listener import GlobalHotkeys
    from kmuted.ui import theme
    from kmuted.ui.main_window import PAGES, MainWindow

    sample = SAMPLES[lang]
    out = OUT / lang
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)

    cfg = default_config()
    cfg.history = list(sample["history"])
    cfg.sounds = [Sound(name=n, file=f"{n}.mp3", hotkey=h) for n, h in (("Airhorn", "alt+f1"), ("Bruh", "alt+f2"), ("Vine boom", ""))]
    cs = GameProfile(name="Counter-Strike 2", processes=["cs2.exe"], translate="on", target=sample["target"])
    dota = GameProfile(name="Dota 2", processes=["dota2.exe"], voice_id=cfg.voices[1].id)
    cfg.profiles = [cs, dota]
    for text, key in sample["cs_phrases"]:
        cfg.phrases.append(Phrase(text=text, hotkey=key, profiles=[cs.id]))
    cfg.translate.target = sample["target"]
    cfg.translate.enabled = True

    # pretend: virtual cable connected, hotkeys running, CS2 running
    c = Controller(cfg, enable_hotkeys=False, enable_audio=False)
    c._prewarm_timer.stop()
    c.audio.mic = SimpleNamespace(alive=True, mixer=None, device=SimpleNamespace(name="CABLE Input (VB-Audio Virtual Cable)"))
    GlobalHotkeys.running = property(lambda self: True)
    processes.snapshot = lambda: ({"cs2.exe"}, "cs2.exe")
    c.translator.run = lambda job: sample["translations"].get(job.text, job.text)

    c._poll_profiles()  # before the window exists: no toast on the screenshots
    w = MainWindow(c)
    w.resize(1280, 800)
    w.show()

    def pump(sec: float) -> None:
        end = time.time() + sec
        while time.time() < end:
            app.processEvents()

    def page(icon_name: str) -> int:
        return next(i for i, (name, _t, _c) in enumerate(PAGES) if name == icon_name)

    pump(0.5)
    for name, icon_name in (("home", "home"), ("phrases", "phrases"), ("translate", "translate"), ("profiles", "gamepad")):
        w.nav.set_current(page(icon_name))
        pump(0.5)
        if name == "translate":
            tp = w.page(page("translate"))
            tp.test_edit.setText(sample["test"])
            tp._test_translate()
            pump(0.4)
        w._refresh_status_card()
        w.grab().save(str(out / f"{name}.png"))

    c.open_input()
    c.input_overlay.edit.setText(sample["typed"])
    pump(1.3)
    c.input_overlay.grab().save(str(out / "input.png"))
    c.input_overlay.close_overlay()
    pump(0.2)

    wheel = cfg.wheels[0]
    c._wheel_pressed(wheel.id, wheel.hotkey)
    for _ in range(12):
        c.wheel_overlay.add_delta(12, -8)
        pump(0.02)
    pump(0.4)
    c.wheel_overlay.grab().save(str(out / "wheel.png"))
    c._wheel_close()

    c.audio.mic = None
    c.shutdown()
    w.quitting = True
    w.close()
    print("written:", out)


def main() -> None:
    langs = sys.argv[1:] or list(SAMPLES)
    if len(langs) == 1:
        shoot(langs[0])
        return
    for lang in langs:  # one process per language: the UI language is set at start
        subprocess.run([sys.executable, __file__, lang], check=True)


if __name__ == "__main__":
    main()
