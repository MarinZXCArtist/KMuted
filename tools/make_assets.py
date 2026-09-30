"""Draw the built-in artwork: assets/banner.jpg and assets/wheel_center.png.

    python tools/make_assets.py

Everything is painted with Qt (no downloads, no stock images), so it can be
re-generated or tweaked at any time. Your own pictures with the same names in
%APPDATA%/KMuted/assets still take priority (see assets/README.md).
"""

from __future__ import annotations

import math
import os
import random
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QBrush,
    QColor,
    QFont,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"

VIOLET = QColor("#7c5cff")
PINK = QColor("#ec4899")
CYAN = QColor("#22d3ee")
BLUE = QColor("#3b82f6")


def _alpha(color: QColor, a: int) -> QColor:
    c = QColor(color)
    c.setAlpha(max(0, min(255, a)))
    return c


def _glow(p: QPainter, x: float, y: float, r: float, color: QColor, a: int) -> None:
    g = QRadialGradient(x, y, r)
    g.setColorAt(0.0, _alpha(color, a))
    g.setColorAt(0.45, _alpha(color, a // 3))
    g.setColorAt(1.0, _alpha(color, 0))
    p.fillRect(QRectF(x - r, y - r, 2 * r, 2 * r), g)


def _wave_path(w: float, h: float, x0: float, x1: float, cy: float, amp: float, phase: float, freq: float) -> QPainterPath:
    path = QPainterPath()
    steps = 420
    for i in range(steps + 1):
        t = i / steps
        x = x0 + (x1 - x0) * t
        env = math.sin(math.pi * min(1.0, t * 1.15)) ** 1.6  # grows in, fades out
        y = cy + amp * env * (
            0.62 * math.sin(2 * math.pi * (freq * t) + phase)
            + 0.28 * math.sin(2 * math.pi * (freq * 2.3 * t) + phase * 1.7)
            + 0.10 * math.sin(2 * math.pi * (freq * 5.1 * t) + phase * 0.4)
        )
        if i == 0:
            path.moveTo(x, y)
        else:
            path.lineTo(x, y)
    return path


def _stroke_glow(p: QPainter, path: QPainterPath, grad: QLinearGradient, width: float, strength: float) -> None:
    for w_mul, alpha in ((7.0, 0.07), (3.6, 0.16), (1.8, 0.45), (1.0, 1.0)):
        g = QLinearGradient(grad.start(), grad.finalStop())
        for pos, color in grad.stops():
            g.setColorAt(pos, _alpha(color, int(color.alpha() * alpha * strength)))
        pen = QPen(QBrush(g), width * w_mul)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)


def _bubble(p: QPainter, rect: QRectF, text: str, color: QColor, tail_left: bool, font: QFont) -> None:
    path = QPainterPath()
    path.addRoundedRect(rect, rect.height() / 2, rect.height() / 2)
    tail = QPainterPath()
    tx = rect.left() + rect.height() * 0.7 if tail_left else rect.right() - rect.height() * 0.7
    d = -1 if tail_left else 1
    tail.moveTo(tx - 10 * d, rect.bottom() - 4)
    tail.lineTo(tx - 2 * d, rect.bottom() + 16)
    tail.lineTo(tx + 12 * d, rect.bottom() - 4)
    path = path.united(tail)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(18, 16, 40, 225))  # dark glass under the tint
    p.drawPath(path)
    fill = QLinearGradient(rect.topLeft(), rect.bottomRight())
    fill.setColorAt(0, _alpha(color, 90))
    fill.setColorAt(1, _alpha(color, 35))
    p.setPen(QPen(_alpha(color, 190), 2))
    p.setBrush(fill)
    p.drawPath(path)
    p.setFont(font)
    p.setPen(QColor(255, 255, 255, 235))
    p.drawText(rect, Qt.AlignCenter, text)


def make_banner(path: Path, w: int = 1800, h: int = 450) -> None:
    rnd = random.Random(7)
    img = QImage(w, h, QImage.Format_RGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)

    base = QLinearGradient(0, 0, w, h)
    base.setColorAt(0.0, QColor("#120d2b"))
    base.setColorAt(0.5, QColor("#191640"))
    base.setColorAt(1.0, QColor("#0a1f30"))
    p.fillRect(0, 0, w, h, base)
    _glow(p, w * 0.80, h * 0.10, h * 1.25, VIOLET, 150)
    _glow(p, w * 0.58, h * 1.05, h * 0.95, PINK, 120)
    _glow(p, w * 1.02, h * 0.85, h * 0.85, CYAN, 110)
    _glow(p, w * 0.30, h * 0.30, h * 0.9, BLUE, 45)

    # stars
    p.setPen(Qt.NoPen)
    for _ in range(260):
        x, y = rnd.random() * w, rnd.random() * h
        r = rnd.choice((0.8, 1.0, 1.2, 1.6, 2.2))
        p.setBrush(QColor(255, 255, 255, rnd.randint(18, 90)))
        p.drawEllipse(QPointF(x, y), r, r)

    # synthwave floor grid, fading out to the left (drawn on its own layer)
    horizon = h * 0.62
    layer = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
    layer.fill(Qt.transparent)
    lp = QPainter(layer)
    lp.setRenderHint(QPainter.Antialiasing)
    vx = w * 0.74
    for i in range(-26, 27):
        fade = 1 - abs(i) / 27
        lp.setPen(QPen(_alpha(VIOLET, int(80 * fade)), 1.4))
        lp.drawLine(QPointF(vx + i * 12, horizon), QPointF(vx + i * 110, h))
    for k in range(1, 12):
        t = (k / 12) ** 2.1
        y = horizon + (h - horizon) * t
        lp.setPen(QPen(_alpha(PINK, int(20 + 60 * t)), 1.2))
        lp.drawLine(QPointF(0, y), QPointF(w, y))
    glow = QLinearGradient(0, horizon - 30, 0, horizon + 30)
    glow.setColorAt(0, _alpha(PINK, 0))
    glow.setColorAt(0.5, _alpha(PINK, 70))
    glow.setColorAt(1, _alpha(PINK, 0))
    lp.fillRect(QRectF(0, horizon - 30, w, 60), glow)
    mask = QLinearGradient(w * 0.30, 0, w * 0.62, 0)
    mask.setColorAt(0, QColor(0, 0, 0, 0))
    mask.setColorAt(1, QColor(0, 0, 0, 255))
    lp.setCompositionMode(QPainter.CompositionMode_DestinationIn)
    lp.fillRect(0, 0, w, h, mask)
    lp.end()
    p.drawImage(0, 0, layer)

    # equalizer with reflection
    bars = 38
    x0, x1 = w * 0.55, w * 0.985
    step = (x1 - x0) / bars
    for i in range(bars):
        t = i / (bars - 1)
        level = 0.18 + 0.82 * abs(math.sin(i * 0.55) * math.cos(i * 0.21 + 0.6)) * math.sin(math.pi * (0.1 + 0.85 * t))
        bh = level * h * 0.44
        x = x0 + i * step
        rect = QRectF(x, horizon - bh, step * 0.56, bh)
        g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        g.setColorAt(0, _alpha(CYAN, 210))
        g.setColorAt(0.5, _alpha(VIOLET, 190))
        g.setColorAt(1, _alpha(PINK, 150))
        p.setBrush(g)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(rect, step * 0.28, step * 0.28)
        refl = QRectF(x, horizon + 4, step * 0.56, bh * 0.45)
        rg = QLinearGradient(refl.topLeft(), refl.bottomLeft())
        rg.setColorAt(0, _alpha(PINK, 70))
        rg.setColorAt(1, _alpha(PINK, 0))
        p.setBrush(rg)
        p.drawRoundedRect(refl, step * 0.28, step * 0.28)

    # glowing voice waves across the banner
    for k, (amp, phase, freq, width, strength) in enumerate(
        ((h * 0.22, 0.0, 3.2, 3.0, 1.0), (h * 0.16, 1.3, 2.6, 2.2, 0.75), (h * 0.12, 2.4, 4.1, 1.6, 0.6), (h * 0.26, 3.6, 1.9, 1.4, 0.45))
    ):
        wave = _wave_path(w, h, w * 0.30, w * 1.02, h * 0.47 + k * 3, amp, phase, freq)
        grad = QLinearGradient(w * 0.3, 0, w, 0)
        grad.setColorAt(0.0, _alpha(VIOLET, 0))
        grad.setColorAt(0.25, _alpha(VIOLET, 230))
        grad.setColorAt(0.6, _alpha(PINK, 230))
        grad.setColorAt(1.0, _alpha(CYAN, 230))
        _stroke_glow(p, wave, grad, width, strength)

    # "text -> voice in another language" chat bubbles
    font = QFont("Segoe UI")
    font.setPixelSize(26)
    font.setWeight(QFont.DemiBold)
    _bubble(p, QRectF(w * 0.63, h * 0.10, 250, 56), "Привет всем!", VIOLET, True, font)
    _bubble(p, QRectF(w * 0.80, h * 0.24, 280, 56), "Hello everyone!", CYAN, False, font)
    arrow = QPainterPath()
    ax, ay = w * 0.63 + 262, h * 0.10 + 40
    arrow.moveTo(ax, ay)
    arrow.cubicTo(ax + 40, ay + 4, ax + 60, ay + 20, w * 0.80 - 14, h * 0.24 + 26)
    pen = QPen(QColor(255, 255, 255, 150), 2.4, Qt.DashLine)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawPath(arrow)
    end = QPointF(w * 0.80 - 14, h * 0.24 + 26)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 255, 255, 190))
    p.drawEllipse(end, 5, 5)

    # vignette (left stays dark for the title text)
    left = QLinearGradient(0, 0, w * 0.5, 0)
    left.setColorAt(0, QColor(10, 10, 20, 170))
    left.setColorAt(1, QColor(10, 10, 20, 0))
    p.fillRect(0, 0, w, h, left)
    p.end()
    if not img.save(str(path), "JPG", 90):
        raise SystemExit(f"could not write {path}")


def make_wheel_center(path: Path, size: int = 512) -> None:
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    c = QPointF(size / 2, size / 2)
    r = size / 2

    disk = QRadialGradient(c, r)
    disk.setColorAt(0.0, _alpha(VIOLET, 210))
    disk.setColorAt(0.55, _alpha(QColor("#3b1f8f"), 170))
    disk.setColorAt(1.0, _alpha(QColor("#120d2b"), 0))
    p.setPen(Qt.NoPen)
    p.setBrush(disk)
    p.drawEllipse(c, r, r)

    # circular waveform ring
    ring = QPainterPath()
    n = 360
    for i in range(n + 1):
        a = 2 * math.pi * i / n
        rr = r * 0.66 + r * 0.07 * (math.sin(a * 9) * 0.6 + math.sin(a * 23 + 1.1) * 0.4)
        pt = QPointF(c.x() + rr * math.cos(a), c.y() + rr * math.sin(a))
        if i == 0:
            ring.moveTo(pt)
        else:
            ring.lineTo(pt)
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0, CYAN)
    grad.setColorAt(0.5, PINK)
    grad.setColorAt(1, VIOLET)
    _stroke_glow(p, ring, grad, 5, 1.0)

    # dial ticks
    for i in range(48):
        a = 2 * math.pi * i / 48
        inner = r * (0.83 if i % 6 else 0.79)
        outer = r * 0.9
        p.setPen(QPen(QColor(255, 255, 255, 150 if i % 6 == 0 else 60), 4 if i % 6 == 0 else 2, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(c.x() + inner * math.cos(a), c.y() + inner * math.sin(a)),
                   QPointF(c.x() + outer * math.cos(a), c.y() + outer * math.sin(a)))

    # microphone glyph
    p.setPen(QPen(QColor(255, 255, 255, 235), size * 0.035, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(QColor(255, 255, 255, 40))
    body = QRectF(c.x() - r * 0.16, c.y() - r * 0.40, r * 0.32, r * 0.52)
    p.drawRoundedRect(body, r * 0.16, r * 0.16)
    p.setBrush(Qt.NoBrush)
    arc = QRectF(c.x() - r * 0.28, c.y() - r * 0.30, r * 0.56, r * 0.56)
    p.drawArc(arc, 200 * 16, 140 * 16)
    p.drawLine(QPointF(c.x(), c.y() + r * 0.26), QPointF(c.x(), c.y() + r * 0.40))
    p.drawLine(QPointF(c.x() - r * 0.13, c.y() + r * 0.40), QPointF(c.x() + r * 0.13, c.y() + r * 0.40))
    p.end()
    img.save(str(path))


def main() -> None:
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    OUT.mkdir(exist_ok=True)
    make_banner(OUT / "banner.jpg")
    make_wheel_center(OUT / "wheel_center.png")
    print("written:", OUT / "banner.jpg", OUT / "wheel_center.png")
    del app


if __name__ == "__main__":
    main()
