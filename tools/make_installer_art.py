"""Render the installer side banner and header images (BMP) from the logo."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def make_art(out_dir: Path) -> None:
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QLinearGradient, QPainter, QRadialGradient

    from kmuted.ui import theme
    from kmuted.ui.icons import render_logo

    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841
    out_dir.mkdir(parents=True, exist_ok=True)

    # side banner (164x314 at 100 %; rendered at 2x for sharp HiDPI scaling)
    w, h = 328, 628
    img = QImage(w, h, QImage.Format_RGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    grad = QLinearGradient(0, 0, w, h)
    grad.setColorAt(0, QColor("#2a1d6b"))
    grad.setColorAt(0.55, QColor("#161a3a"))
    grad.setColorAt(1, QColor("#0e0f15"))
    p.fillRect(img.rect(), grad)
    for cx, cy, r, color in ((0.2, 0.15, 0.9, theme.ACCENT), (0.9, 0.85, 0.7, theme.ACCENT_2)):
        glow = QRadialGradient(w * cx, h * cy, w * r)
        c = QColor(color)
        c.setAlpha(90)
        glow.setColorAt(0, c)
        c.setAlpha(0)
        glow.setColorAt(1, c)
        p.fillRect(img.rect(), glow)
    p.setPen(Qt.NoPen)
    for i in range(18):
        x = 30 + i * 16
        bar = (0.2 + 0.8 * abs(((i * 37) % 11) / 10 - 0.5) * 2) * 120
        p.setBrush(QColor(255, 255, 255, 28))
        p.drawRoundedRect(QRectF(x, h * 0.78 - bar / 2, 8, bar), 4, 4)
    logo = render_logo(160)
    p.drawPixmap((w - 160) // 2, 150, logo)
    f = QFont("Segoe UI")
    f.setPixelSize(52)
    f.setWeight(QFont.Bold)
    p.setFont(f)
    p.setPen(QColor("white"))
    p.drawText(QRectF(0, 330, w, 70), Qt.AlignCenter, "KMuted")
    f.setPixelSize(22)
    f.setWeight(QFont.Normal)
    p.setFont(f)
    p.setPen(QColor(255, 255, 255, 170))
    p.drawText(QRectF(0, 395, w, 40), Qt.AlignCenter, "text → voice → mic")
    p.end()
    img.scaled(164, 314, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).save(str(out_dir / "wizard.bmp"), "BMP")

    small = QImage(110, 116, QImage.Format_RGB32)
    small.fill(QColor("white"))
    p = QPainter(small)
    p.setRenderHint(QPainter.Antialiasing)
    p.drawPixmap(7, 10, render_logo(96))
    p.end()
    small.scaled(55, 58, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).save(str(out_dir / "wizard_small.bmp"), "BMP")


if __name__ == "__main__":
    make_art(Path(sys.argv[1] if len(sys.argv) > 1 else "build"))
