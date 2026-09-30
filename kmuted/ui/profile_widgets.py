"""Small pieces shared by pages that deal with game profiles."""

from __future__ import annotations

import hashlib

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QLabel, QMenu, QPushButton

from kmuted.i18n import tr
from kmuted.ui import theme
from kmuted.ui.icons import icon

PALETTE = ["#7c5cff", "#ec4899", "#f97316", "#22c55e", "#06b6d4", "#3b82f6", "#eab308", "#ef4444", "#14b8a6", "#a855f7"]


def profile_color(profile) -> str:
    if profile.color:
        return profile.color
    digest = hashlib.md5(profile.name.strip().lower().encode("utf-8")).digest()
    return PALETTE[digest[0] % len(PALETTE)]


def initials(name: str) -> str:
    words = [w for w in name.replace(":", " ").replace("-", " ").split() if w[:1].isalnum()]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[1][0]).upper()


def profile_cover(profile, size: int = 56, active: bool = False) -> QPixmap:
    """Generated game "cover": color gradient, soft rings, initials."""
    ratio = 2.0
    pm = QPixmap(int(size * ratio), int(size * ratio))
    pm.setDevicePixelRatio(ratio)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    rect = QRectF(0.5, 0.5, size - 1, size - 1)
    radius = size * 0.26
    base = QColor(profile_color(profile))
    grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
    grad.setColorAt(0.0, base.lighter(135))
    grad.setColorAt(1.0, base.darker(190))
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    p.fillPath(path, grad)
    p.setClipPath(path)
    ring = QColor(255, 255, 255, 34)
    p.setPen(QPen(ring, size * 0.05))
    p.setBrush(Qt.NoBrush)
    for k in (0.55, 0.85, 1.15):
        r = size * k
        p.drawEllipse(QRectF(size * 0.78 - r / 2, size * 0.2 - r / 2, r, r))
    p.setClipping(False)
    label = initials(profile.name) if profile.name.strip() else ""
    font = QFont()
    font.setPixelSize(int(size * 0.36))
    font.setWeight(QFont.Black)
    p.setFont(font)
    p.setPen(QColor(0, 0, 0, 70))
    p.drawText(rect.translated(0, size * 0.03), Qt.AlignCenter, label)
    p.setPen(QColor("white"))
    p.drawText(rect, Qt.AlignCenter, label)
    if active:
        p.setPen(QPen(QColor(theme.SUCCESS), size * 0.06))
        p.drawRoundedRect(rect.adjusted(size * 0.03, size * 0.03, -size * 0.03, -size * 0.03), radius, radius)
    p.end()
    return pm


def profile_chips(controller, item) -> list[QLabel]:
    """"🎮 CS2" chips for a phrase/wheel/sound that only works in some games."""
    chips = []
    for pid in item.profiles:
        prof = controller.config.profile_by_id(pid)
        if prof is None:
            continue
        chip = QLabel(f"🎮 {prof.name}")
        chip.setObjectName("chipGame")
        chip.setToolTip(tr("Работает только в этой игре"))
        chips.append(chip)
    return chips


class ProfileScopeButton(QPushButton):
    """Where a phrase/wheel/sound works: everywhere or only in chosen games."""

    changed = Signal()

    def __init__(self, controller, selected: list[str], parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._selected = [pid for pid in selected if controller.config.profile_by_id(pid)]
        self.setIcon(icon("gamepad", theme.MUTED, 16))
        self.setMinimumWidth(220)
        self._menu = QMenu(self)
        self._menu.aboutToShow.connect(self._fill)
        self.setMenu(self._menu)
        self._update_text()

    def profiles(self) -> list[str]:
        return list(self._selected)

    def set_selected(self, selected: list[str]) -> None:
        self._selected = [pid for pid in selected if self.controller.config.profile_by_id(pid)]
        self._update_text()

    def _fill(self) -> None:
        self._menu.clear()
        every = self._menu.addAction(tr("Везде — в любой игре и без неё"))
        every.setCheckable(True)
        every.setChecked(not self._selected)
        every.triggered.connect(self._set_everywhere)
        self._menu.addSeparator()
        for prof in self.controller.config.profiles:
            action = self._menu.addAction(prof.name)
            action.setCheckable(True)
            action.setChecked(prof.id in self._selected)
            action.triggered.connect(lambda checked, pid=prof.id: self._toggle(pid, checked))

    def _set_everywhere(self) -> None:
        self._selected = []
        self._update_text()
        self.changed.emit()

    def _toggle(self, pid: str, checked: bool) -> None:
        if checked and pid not in self._selected:
            self._selected.append(pid)
        elif not checked and pid in self._selected:
            self._selected.remove(pid)
        self._update_text()
        self.changed.emit()

    def _update_text(self) -> None:
        profiles = self.controller.config.profiles
        self.setEnabled(bool(profiles))
        names = [p.name for p in profiles if p.id in self._selected]
        if not profiles:
            self.setText(tr("Везде"))
            self.setToolTip(tr("Создайте профиль игры на вкладке «Профили игр», чтобы привязать к игре"))
        elif not names:
            self.setText(tr("Везде"))
            self.setToolTip(tr("Работает в любой игре и без неё"))
        else:
            text = tr("Только: {names}", names=", ".join(names))
            self.setText(self.fontMetrics().elidedText(text, Qt.ElideRight, 260))
            self.setToolTip(text)
