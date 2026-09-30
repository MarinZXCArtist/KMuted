"""Logo, line icons and user-provided artwork.

Icons are small inline SVGs (Lucide-style, 24×24, stroke = currentColor),
so the repo needs no binary files and they stay sharp at any DPI.

Any picture can be replaced without touching code: drop a file into an
``assets`` folder (next to KMuted.exe, in the repo root, or in the settings
folder) — see ``assets/README.md`` for the names.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtSvg import QSvgRenderer

from kmuted import paths
from kmuted.ui import theme

_IMAGE_EXTS = (".svg", ".png", ".webp", ".jpg", ".jpeg", ".ico")

_SVG = {
    "home": '<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 22V12h6v10"/>',
    "phrases": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/><path d="M8 9h8"/><path d="M8 13h5"/>',
    "wheel": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/><path d="M12 3v6"/><path d="M12 15v6"/><path d="M3 12h6"/><path d="M15 12h6"/>',
    "voices": '<path d="M2 10v3"/><path d="M6 6v11"/><path d="M10 3v18"/><path d="M14 8v7"/><path d="M18 5v13"/><path d="M22 10v3"/>',
    "audio": '<path d="M3 14h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-7a9 9 0 0 1 18 0v7a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3"/>',
    "settings": '<path d="M21 4h-7"/><path d="M10 4H3"/><path d="M21 12h-9"/><path d="M8 12H3"/><path d="M21 20h-5"/><path d="M12 20H3"/><path d="M14 2v4"/><path d="M8 10v4"/><path d="M16 18v4"/>',
    "play": '<polygon points="6 3 20 12 6 21 6 3"/>',
    "stop": '<rect width="14" height="14" x="5" y="5" rx="2"/>',
    "plus": '<path d="M5 12h14"/><path d="M12 5v14"/>',
    "edit": '<path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>',
    "trash": '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>',
    "up": '<path d="m18 15-6-6-6 6"/>',
    "down": '<path d="m6 9 6 6 6-6"/>',
    "keyboard": '<rect width="20" height="16" x="2" y="4" rx="2"/><path d="M6 8h.01"/><path d="M10 8h.01"/><path d="M14 8h.01"/><path d="M18 8h.01"/><path d="M8 12h.01"/><path d="M12 12h.01"/><path d="M16 12h.01"/><path d="M7 16h10"/>',
    "mic": '<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><path d="M12 19v3"/>',
    "refresh": '<path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/>',
    "folder": '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
    "sparkles": '<path d="M12 3l1.9 5.8L20 11l-6.1 2.2L12 19l-1.9-5.8L4 11l6.1-2.2z"/><path d="M20 3v4"/><path d="M22 5h-4"/>',
    "check": '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    "alert": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    "x": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    "zap": '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
    "volume": '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>',
    "globe": '<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/>',
    "cpu": '<rect width="16" height="16" x="4" y="4" rx="2"/><rect width="6" height="6" x="9" y="9" rx="1"/><path d="M15 2v2"/><path d="M15 20v2"/><path d="M2 15h2"/><path d="M2 9h2"/><path d="M20 15h2"/><path d="M20 9h2"/><path d="M9 2v2"/><path d="M9 20v2"/>',
    "windows": '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 12h18"/><path d="M12 3v18"/>',
    "wand": '<path d="m21.64 3.64-1.28-1.28a1.21 1.21 0 0 0-1.72 0L2.36 18.64a1.21 1.21 0 0 0 0 1.72l1.28 1.28a1.2 1.2 0 0 0 1.72 0L21.64 5.36a1.2 1.2 0 0 0 0-1.72"/><path d="m14 7 3 3"/><path d="M5 6v4"/><path d="M19 14v4"/><path d="M3 8h4"/><path d="M17 16h4"/>',
    "copy": '<rect width="14" height="14" x="8" y="8" rx="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
    "star": '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>',
    "history": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "send": '<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>',
    "link": '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    "power": '<path d="M12 2v10"/><path d="M18.4 6.6a9 9 0 1 1-12.79 0"/>',
    "gamepad": '<path d="M6 12h4"/><path d="M8 10v4"/><path d="M15 13h.01"/><path d="M18 11h.01"/><rect width="20" height="12" x="2" y="6" rx="2"/>',
    "translate": '<path d="m5 8 6 6"/><path d="m4 14 6-6 2-3"/><path d="M2 5h12"/><path d="M7 2h1"/><path d="m22 22-5-10-5 10"/><path d="M14 18h6"/>',
    "swap": '<path d="m16 3 4 4-4 4"/><path d="M20 7H4"/><path d="m8 21-4-4 4-4"/><path d="M4 17h16"/>',
    "key": '<circle cx="7.5" cy="15.5" r="5.5"/><path d="m21 2-9.6 9.6"/><path d="m15.5 7.5 3 3L22 7l-3-3"/>',
    "mouse": '<rect x="5" y="2" width="14" height="20" rx="7"/><path d="M12 6v4"/>',
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "eye": '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/>',
    "headset": '<path d="M3 11h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-5Zm0 0a9 9 0 1 1 18 0m0 0v5a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3Z"/><path d="M21 16v2a4 4 0 0 1-4 4h-5"/>',
    "radio": '<circle cx="12" cy="12" r="2"/><path d="M16.24 7.76a6 6 0 0 1 0 8.49"/><path d="M7.76 16.24a6 6 0 0 1 0-8.49"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/><path d="M4.93 19.07a10 10 0 0 1 0-14.14"/>',
    "discord": '<path d="M8 12h.01"/><path d="M16 12h.01"/><path d="M7.5 17.5 6 20c-2-.5-4-1.5-4-1.5 0-5 1-9 3-12 2-1 4-1.5 4-1.5l.5 1.5h5L15 5s2 .5 4 1.5c2 3 3 7 3 12 0 0-2 1-4 1.5l-1.5-2.5"/><path d="M7 16c3 1.5 7 1.5 10 0"/>',
}


# --- user artwork ------------------------------------------------------------------


def asset_dirs() -> list[Path]:
    """Where to look for replacement pictures, highest priority first."""
    dirs = [paths.data_dir() / "assets", paths.app_dir() / "assets"]
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        dirs.append(Path(bundle) / "assets")
    return dirs


@lru_cache(maxsize=64)
def find_asset(name: str) -> Path | None:
    """``find_asset("logo")`` -> first existing logo.svg/png/... or None."""
    for base in asset_dirs():
        for ext in _IMAGE_EXTS:
            candidate = base / f"{name}{ext}"
            if candidate.is_file():
                return candidate
    return None


def load_asset_pixmap(name: str, size: QSize | None = None) -> QPixmap | None:
    path = find_asset(name)
    if path is None:
        return None
    if path.suffix == ".svg" and size is not None:
        return _render_svg(path.read_bytes(), size.width(), size.height())
    pm = QPixmap(str(path))
    if pm.isNull():
        return None
    if size is not None:
        pm = pm.scaled(size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    return pm


# --- icons -------------------------------------------------------------------------


def _render_svg(data: bytes, width: int, height: int) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(data))
    pm = QPixmap(width, height)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    renderer.render(p, QRectF(0, 0, width, height))
    p.end()
    return pm


@lru_cache(maxsize=256)
def icon_pixmap(name: str, color: str = theme.TEXT, size: int = 18, stroke: float = 2.0, dpr: float = 2.0) -> QPixmap:
    px = max(1, round(size * dpr))
    override = find_asset(f"icons/{name}")
    if override is not None:
        if override.suffix == ".svg":
            data = override.read_bytes().replace(b"currentColor", color.encode())
            pm = _render_svg(data, px, px)
        else:
            pm = QPixmap(str(override)).scaled(px, px, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    else:
        body = _SVG.get(name, _SVG["info"])
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" '
            f'stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
        )
        pm = _render_svg(svg.encode(), px, px)
    pm.setDevicePixelRatio(dpr)
    return pm


def icon(name: str, color: str = theme.TEXT, size: int = 18, hover_color: str | None = None) -> QIcon:
    ic = QIcon()
    ic.addPixmap(icon_pixmap(name, color, size), QIcon.Normal, QIcon.Off)
    ic.addPixmap(icon_pixmap(name, theme.FAINT, size), QIcon.Disabled, QIcon.Off)
    if hover_color:
        ic.addPixmap(icon_pixmap(name, hover_color, size), QIcon.Active, QIcon.Off)
    return ic


# --- logo --------------------------------------------------------------------------


def render_logo(size: int, speaking: bool = False) -> QPixmap:
    custom = load_asset_pixmap("logo", QSize(size, size))
    if custom is not None and not speaking:
        return custom
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    if custom is not None:  # speaking: user logo with a cyan ring
        p.drawPixmap(0, 0, custom)
        p.setPen(QPen(QColor(theme.ACCENT_2), max(2.0, size / 16)))
        p.setBrush(Qt.NoBrush)
        m = size / 16
        p.drawRoundedRect(QRectF(m, m, size - 2 * m, size - 2 * m), size / 4, size / 4)
        p.end()
        return pm
    s = size / 64.0

    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0, QColor(theme.ACCENT))
    grad.setColorAt(1, QColor(theme.ACCENT_2) if speaking else QColor(theme.BLUE))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(grad))
    p.drawRoundedRect(QRectF(2 * s, 2 * s, 60 * s, 60 * s), 17 * s, 17 * s)

    # soft highlight
    shine = QLinearGradient(0, 0, 0, size)
    shine.setColorAt(0, QColor(255, 255, 255, 60))
    shine.setColorAt(0.5, QColor(255, 255, 255, 0))
    p.setBrush(QBrush(shine))
    p.drawRoundedRect(QRectF(2 * s, 2 * s, 60 * s, 60 * s), 17 * s, 17 * s)

    bubble = QPainterPath()
    bubble.addRoundedRect(QRectF(11 * s, 13 * s, 42 * s, 30 * s), 10 * s, 10 * s)
    tail = QPainterPath()
    tail.moveTo(QPointF(20 * s, 40 * s))
    tail.lineTo(QPointF(16 * s, 52 * s))
    tail.lineTo(QPointF(30 * s, 42 * s))
    tail.closeSubpath()
    p.setBrush(QColor("white"))
    p.drawPath(bubble.united(tail))

    p.setPen(QPen(QColor(theme.ACCENT), 4.2 * s, Qt.SolidLine, Qt.RoundCap))
    for x, h in ((21, 6), (27, 12), (33, 16), (39, 10), (45, 5)):
        p.drawLine(QPointF(x * s, (28 - h / 2) * s), QPointF(x * s, (28 + h / 2) * s))
    p.end()
    return pm


def app_icon(speaking: bool = False) -> QIcon:
    ic = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(render_logo(size, speaking))
    return ic


def tray_icon(speaking: bool = False) -> QIcon:
    custom = find_asset("tray")
    if custom is not None and not speaking:
        return QIcon(str(custom))
    return app_icon(speaking)
