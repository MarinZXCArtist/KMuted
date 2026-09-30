"""Every binding in one place: actions, voices, phrases, wheels, sounds."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QLineEdit, QScrollArea, QVBoxLayout, QWidget

from kmuted.actions import ACTIONS, attr
from kmuted.i18n import tr
from kmuted.ui import theme
from kmuted.ui.components import SectionTitle, SettingRow, ToggleSwitch, page_header
from kmuted.ui.icons import icon
from kmuted.ui.widgets import HotkeyEdit

_GROUP_ORDER = ["Речь", "Звуки", "Голоса", "Звук", "Приложение"]


class HotkeysPage(QWidget):
    def __init__(self, controller) -> None:
        super().__init__()
        self.controller = controller
        self._rows: list[tuple[SettingRow, str, str, str]] = []  # row, owner key, base subtitle, search text

        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Найти действие или клавишу…"))
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icon("search", theme.FAINT, 16), QLineEdit.LeadingPosition)
        self.search.setFixedWidth(260)
        self.search.textChanged.connect(self._filter)

        self.body = QVBoxLayout()
        self.body.setSpacing(8)
        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(28, 24, 28, 20)
        cl.setSpacing(8)
        cl.addWidget(
            page_header(
                tr("Горячие клавиши"),
                tr("Бинды на всё: действия, голоса, фразы, колёса и звуки. Можно клавиши, сочетания и боковые кнопки мыши."),
                self.search,
            )
        )
        cl.addLayout(self.body)
        cl.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._rebuild_timer = QTimer(self)
        self._rebuild_timer.setSingleShot(True)
        self._rebuild_timer.setInterval(120)
        self._rebuild_timer.timeout.connect(self.rebuild)
        controller.config_changed.connect(self._on_config_changed)
        controller.hotkeys_toggled.connect(self._on_toggled)
        self.rebuild()

    def _on_config_changed(self, section: str) -> None:
        if section in ("phrases", "wheels", "sounds", "voices"):
            self._rebuild_timer.start()  # items added / removed / renamed on other pages
        elif section == "general":
            self._update_conflicts()

    def _on_toggled(self, enabled: bool) -> None:
        self.master.blockSignals(True)
        self.master.setChecked(enabled)
        self.master.blockSignals(False)
        self.master.update()

    # ------------------------------------------------------------ build

    def rebuild(self) -> None:
        while self.body.count():
            item = self.body.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self._rows.clear()
        c = self.controller
        g = c.config.general

        self.master = ToggleSwitch(g.hotkeys_enabled)
        self.master.toggled.connect(lambda on: on != g.hotkeys_enabled and c.set_hotkeys_enabled(on))
        status = tr("Перехват клавиш работает") if c.hotkeys.running else (c.hotkeys.error or tr("Перехват клавиш выключен"))
        self.body.addWidget(SettingRow(tr("Горячие клавиши включены"), status, self.master, "zap"))
        note = QLabel(
            tr("Клавиши не блокируются для игры — выбирайте сочетания, которые игра не использует "
               "(Alt+цифры, F-клавиши, боковые кнопки мыши). Если игра запущена от администратора, "
               "запустите KMuted тоже от администратора.")
        )
        note.setObjectName("hint")
        note.setWordWrap(True)
        note.setContentsMargins(6, 2, 6, 4)
        self.body.addWidget(note)

        groups: dict[str, list] = {}
        for action in ACTIONS:
            groups.setdefault(action.group, []).append(action)
        for group in _GROUP_ORDER:
            actions = groups.get(group, [])
            if not actions:
                continue
            self._section(tr(group))
            for action in actions:
                combo = getattr(g, attr(action.key))
                self._add_row(
                    tr(action.title), tr(action.description), action.icon, combo, f"general:{attr(action.key)}",
                    lambda v, a=action: self._set_general(attr(a.key), v),
                )

        if c.config.voices:
            self._section(tr("Переключить голос"))
            for voice in c.config.voices:
                self._add_row(voice.name, tr("Сделать этот голос основным"), "voices", voice.hotkey, f"voice:{voice.id}",
                              lambda v, x=voice: self._set_item(x, "voices", v))
        if c.config.wheels:
            self._section(tr("Колёса"))
            for wheel in c.config.wheels:
                self._add_row(wheel.name, tr("Зажать — выбрать мышью — отпустить"), "wheel", wheel.hotkey, f"wheel:{wheel.id}",
                              lambda v, x=wheel: self._set_item(x, "wheels", v))
        if c.config.phrases:
            self._section(tr("Фразы"))
            for phrase in c.config.phrases:
                self._add_row(_short(phrase.text), tr("Сказать фразу"), "phrases", phrase.hotkey, f"phrase:{phrase.id}",
                              lambda v, x=phrase: self._set_item(x, "phrases", v))
        if c.config.sounds:
            self._section(tr("Звуки"))
            for sound in c.config.sounds:
                self._add_row(sound.name, tr("Проиграть звук"), "volume", sound.hotkey, f"sound:{sound.id}",
                              lambda v, x=sound: self._set_item(x, "sounds", v))
        self._update_conflicts()
        self._filter(self.search.text())

    def _section(self, title: str) -> None:
        label = SectionTitle(title)
        self.body.addWidget(label)
        self._rows.append((label, "", "", title.lower()))

    def _add_row(self, title: str, subtitle: str, icon_name: str, combo: str, owner: str, setter) -> None:
        edit = HotkeyEdit(combo)
        edit.setFixedWidth(260)
        edit.changed.connect(setter)
        row = SettingRow(title, subtitle, edit, icon_name)
        self.body.addWidget(row)
        self._rows.append((row, owner, subtitle, f"{title} {subtitle} {combo}".lower()))

    # ------------------------------------------------------------ edits

    def _set_general(self, name: str, combo: str) -> None:
        setattr(self.controller.config.general, name, combo)
        self.controller.edited("general")
        self._update_conflicts()

    def _set_item(self, item, section: str, combo: str) -> None:
        item.hotkey = combo
        self._rebuild_timer.stop()
        self.controller.edited(section)
        self._rebuild_timer.stop()  # keep the widgets: just refresh warnings
        self._update_conflicts()

    def _update_conflicts(self) -> None:
        owners = self.controller.hotkey_owners()
        for row, owner, base, _text in self._rows:
            if not owner or not isinstance(row, SettingRow):
                continue
            combo = row.control.combo() if isinstance(row.control, HotkeyEdit) else ""
            others = [name for key, name in owners.get(combo, []) if key != owner] if combo else []
            if others:
                row.subtitle.setText(f"<span style='color:{theme.WARNING}'>⚠ {tr('Уже занято')}: {', '.join(others)}</span>")
            else:
                row.subtitle.setText(base)

    def _filter(self, text: str) -> None:
        query = text.strip().lower()
        for widget, _owner, _base, haystack in self._rows:
            widget.setVisible(not query or (not isinstance(widget, SectionTitle) and query in haystack))


def _short(text: str, limit: int = 48) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
