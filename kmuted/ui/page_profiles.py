"""Game profiles: own phrases, wheels and sounds switch on while a game runs."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from kmuted import processes
from kmuted import translate as tl
from kmuted.config import PROFILE_AUTO, PROFILE_NONE, GameProfile
from kmuted.hotkeys.keys import format_combo
from kmuted.i18n import plural, tr
from kmuted.ui import theme
from kmuted.ui.components import EmptyState, IconBadge, ToggleSwitch, icon_button, make_button, page_header
from kmuted.ui.icons import icon
from kmuted.ui.profile_widgets import PALETTE, profile_cover

RUNNING_POLL_MS = 3000


def _short(text: str, limit: int = 60) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


class ProfileDialog(QDialog):
    def __init__(self, controller, profile: GameProfile, is_new: bool, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.profile = profile
        self.setWindowTitle(tr("Профиль игры"))
        self.setMinimumSize(760, 640)
        cfg = controller.config

        title = QLabel(tr("Новый профиль игры") if is_new else tr("Профиль игры"))
        title.setObjectName("h2")

        self.name = QLineEdit(profile.name)
        self.name.setPlaceholderText(tr("Название, например: CS2"))
        self.color = QComboBox()
        self.color.addItem(tr("Авто"), "")
        for c in PALETTE:
            pm = profile_cover(GameProfile(name="", color=c), 14)
            self.color.addItem(pm, c, c)
        idx = self.color.findData(profile.color)
        self.color.setCurrentIndex(max(0, idx))
        name_row = QHBoxLayout()
        name_row.addWidget(self.name, 1)
        name_row.addWidget(self.color)

        # --- programs ------------------------------------------------------------
        self.exe_list = QListWidget()
        self.exe_list.setFixedHeight(92)
        for exe in profile.processes:
            self._add_exe_item(exe)
        self.exe_edit = QLineEdit()
        self.exe_edit.setPlaceholderText(tr("Впишите имя файла, например cs2.exe, и нажмите Enter"))
        self.exe_edit.returnPressed.connect(self._add_typed)
        presets = make_button(tr("Популярные игры"), "star")
        preset_menu = QMenu(presets)
        for game, exes in processes.GAME_PRESETS:
            action = preset_menu.addAction(game)
            action.triggered.connect(lambda _c=False, g=game, e=exes: self._add_preset(g, e))
        presets.setMenu(preset_menu)
        running = make_button(tr("Из запущенных"), "zap")
        self._running_menu = QMenu(running)
        self._running_menu.aboutToShow.connect(self._fill_running)
        running.setMenu(self._running_menu)
        browse = make_button(tr("Указать .exe…"), "folder")
        browse.clicked.connect(self._browse)
        remove = make_button("", "trash", tooltip=tr("Убрать выбранную программу"))
        remove.clicked.connect(self._remove_selected)
        type_row = QHBoxLayout()
        type_row.setSpacing(6)
        type_row.addWidget(self.exe_edit, 1)
        type_row.addWidget(remove)
        exe_tools = QHBoxLayout()
        exe_tools.setSpacing(6)
        exe_tools.addWidget(presets)
        exe_tools.addWidget(running)
        exe_tools.addWidget(browse)
        exe_tools.addStretch(1)
        exe_box = QVBoxLayout()
        exe_box.setSpacing(6)
        exe_box.addWidget(self.exe_list)
        exe_box.addLayout(type_row)
        exe_box.addLayout(exe_tools)

        # --- overrides -----------------------------------------------------------
        self.voice = QComboBox()
        self.voice.addItem(tr("Не менять"), "")
        for v in cfg.voices:
            self.voice.addItem(v.name, v.id)
        self.voice.setCurrentIndex(max(0, self.voice.findData(profile.voice_id)))
        self.translate = QComboBox()
        for key, label in (("", tr("Как обычно")), ("on", tr("Включить перевод")), ("off", tr("Выключить перевод"))):
            self.translate.addItem(label, key)
        self.translate.setCurrentIndex(max(0, self.translate.findData(profile.translate)))
        self.target = QComboBox()
        self.target.addItem(tr("Язык как обычно"), "")
        for code, _n in tl.LANGUAGES:
            self.target.addItem(f"{tl.language_name(code)}  ·  {code.upper()}", code)
        self.target.setCurrentIndex(max(0, self.target.findData(profile.target)))
        tr_row = QHBoxLayout()
        tr_row.addWidget(self.translate, 1)
        tr_row.addWidget(self.target, 1)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignTop)
        form.addRow(tr("Название"), name_row)
        form.addRow(tr("Файлы .exe"), exe_box)
        form.addRow(tr("Голос в игре"), self.voice)
        form.addRow(tr("Перевод в игре"), tr_row)

        # --- what belongs to the game ----------------------------------------------
        what = QLabel(tr("Что работает в этой игре"))
        what.setObjectName("h3")
        what_hint = QLabel(
            tr("Отмеченное работает только в играх, где оно отмечено. Всё без отметок работает везде. "
               "Если клавиша занята и общей фразой, и фразой игры — в игре сработает фраза игры.")
        )
        what_hint.setObjectName("hint")
        what_hint.setWordWrap(True)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        self.lists: dict[str, QListWidget] = {}
        columns = (
            ("phrases", tr("Фразы"), cfg.phrases, lambda x: _short(x.text, 28)),
            ("wheels", tr("Колёса"), cfg.wheels, lambda x: x.name),
            ("sounds", tr("Звуки"), cfg.sounds, lambda x: x.name),
        )
        for col, (key, label, items, caption) in enumerate(columns):
            head = QLabel(label)
            head.setObjectName("eyebrow")
            lst = QListWidget()
            lst.setMinimumHeight(150)
            for item in items:
                text = caption(item) or "—"
                if item.hotkey:
                    text += f"   [{format_combo(item.hotkey)}]"
                others = [p.name for p in cfg.profiles if p.id in item.profiles and p.id != profile.id]
                if not item.profiles:
                    text += "  · " + tr("везде")
                elif others:
                    text += "  · " + ", ".join(others)
                row = QListWidgetItem(text)
                row.setFlags(row.flags() | Qt.ItemIsUserCheckable)
                row.setCheckState(Qt.Checked if profile.id in item.profiles else Qt.Unchecked)
                row.setData(Qt.UserRole, item.id)
                lst.addItem(row)
            if not items:
                empty = QListWidgetItem(tr("пусто"))
                empty.setFlags(Qt.NoItemFlags)
                lst.addItem(empty)
            grid.addWidget(head, 0, col)
            grid.addWidget(lst, 1, col)
            self.lists[key] = lst

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok = buttons.button(QDialogButtonBox.Ok)
        ok.setText(tr("Сохранить"))
        ok.setObjectName("primary")
        ok.setIcon(icon("check", "white", 16))
        buttons.button(QDialogButtonBox.Cancel).setText(tr("Отмена"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.warning = QLabel()
        self.warning.setStyleSheet(f"color: {theme.WARNING};")
        self.warning.hide()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(12)
        lay.addWidget(title)
        lay.addLayout(form)
        lay.addWidget(what)
        lay.addWidget(what_hint)
        lay.addLayout(grid, 1)
        lay.addWidget(self.warning)
        lay.addWidget(buttons)

    # --- programs ------------------------------------------------------------------

    def _exes(self) -> list[str]:
        return [self.exe_list.item(i).text() for i in range(self.exe_list.count())]

    def _add_exe_item(self, exe: str) -> None:
        exe = exe.strip().strip('"').replace("/", "\\").rsplit("\\", 1)[-1].lower()
        if not exe or exe in self._exes():
            return
        if "." not in exe:
            exe += ".exe"
        item = QListWidgetItem(icon("gamepad", theme.MUTED, 14), exe)
        self.exe_list.addItem(item)

    def _add_typed(self) -> None:
        self._add_exe_item(self.exe_edit.text())
        self.exe_edit.clear()

    def _add_preset(self, game: str, exes) -> None:
        for exe in exes:
            self._add_exe_item(exe)
        if not self.name.text().strip() or self.name.text().strip() == tr("Игра"):
            self.name.setText(game)

    def _fill_running(self) -> None:
        self._running_menu.clear()
        try:
            programs = processes.windowed_programs()
        except Exception:
            programs = []
        if not programs:
            empty = self._running_menu.addAction(tr("Ничего не найдено — запустите игру"))
            empty.setEnabled(False)
            return
        for exe, title in programs[:60]:
            label = f"{_short(title, 40)}  —  {exe}" if title else exe
            action = self._running_menu.addAction(label)
            action.triggered.connect(lambda _c=False, e=exe, t=title: self._add_running(e, t))

    def _add_running(self, exe: str, title: str) -> None:
        self._add_exe_item(exe)
        if title and (not self.name.text().strip() or self.name.text().strip() == tr("Игра")):
            self.name.setText(_short(title, 30))

    def _browse(self) -> None:
        path, _f = QFileDialog.getOpenFileName(self, tr("Файл игры"), "", tr("Программы (*.exe);;Все файлы (*)"))
        if path:
            self._add_exe_item(Path(path).name)
            if not self.name.text().strip() or self.name.text().strip() == tr("Игра"):
                self.name.setText(Path(path).stem)

    def _remove_selected(self) -> None:
        for item in self.exe_list.selectedItems():
            self.exe_list.takeItem(self.exe_list.row(item))

    # --- save -------------------------------------------------------------------------

    def accept(self) -> None:
        if self.exe_edit.text().strip():
            self._add_typed()
        name = self.name.text().strip()
        if not name:
            self.name.setFocus()
            return
        p = self.profile
        p.name = name
        p.color = self.color.currentData() or ""
        p.processes = self._exes()
        p.voice_id = self.voice.currentData() or ""
        p.translate = self.translate.currentData() or ""
        p.target = self.target.currentData() or ""
        cfg = self.controller.config
        for key, items in (("phrases", cfg.phrases), ("wheels", cfg.wheels), ("sounds", cfg.sounds)):
            lst = self.lists[key]
            checked = {
                lst.item(i).data(Qt.UserRole)
                for i in range(lst.count())
                if lst.item(i).data(Qt.UserRole) and lst.item(i).checkState() == Qt.Checked
            }
            for item in items:
                if item.id in checked and p.id not in item.profiles:
                    item.profiles.append(p.id)
                elif item.id not in checked and p.id in item.profiles:
                    item.profiles.remove(p.id)
        super().accept()


class ProfileCard(QFrame):
    edit_requested = Signal()
    remove_requested = Signal()
    toggled = Signal(bool)

    def __init__(self, controller, profile: GameProfile, running: bool) -> None:
        super().__init__()
        self.setObjectName("cardHover")
        self.setCursor(Qt.PointingHandCursor)
        cfg = controller.config
        active = controller.active_profile_id == profile.id
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(14)
        cover = QLabel()
        cover.setPixmap(profile_cover(profile, 56, active))
        lay.addWidget(cover)

        col = QVBoxLayout()
        col.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(8)
        name = QLabel(profile.name)
        name.setObjectName("h3")
        top.addWidget(name)
        if active:
            state = QLabel(tr("активен"))
            state.setObjectName("chipOk")
        elif running:
            state = QLabel(tr("игра запущена"))
            state.setObjectName("chip")
        else:
            state = None
        if state is not None:
            top.addWidget(state)
        top.addStretch(1)
        col.addLayout(top)

        exes = ", ".join(profile.processes) or tr("программа не указана — включается только вручную")
        progs = QLabel(exes)
        progs.setObjectName("hint")
        progs.setToolTip(exes)
        col.addWidget(progs)

        bits = [
            plural(sum(profile.id in x.profiles for x in cfg.phrases), "фраза", "фразы", "фраз"),
            plural(sum(profile.id in x.profiles for x in cfg.wheels), "колесо", "колеса", "колёс"),
            plural(sum(profile.id in x.profiles for x in cfg.sounds), "звук", "звука", "звуков"),
        ]
        voice = cfg.voice_by_id(profile.voice_id)
        if voice is not None:
            bits.append(tr("голос: {name}", name=voice.name))
        if profile.translate == "on":
            bits.append(tr("перевод: {lang}", lang=(profile.target or cfg.translate.target).upper()))
        elif profile.translate == "off":
            bits.append(tr("без перевода"))
        elif profile.target:
            bits.append(tr("язык: {lang}", lang=profile.target.upper()))
        meta = QLabel("  ·  ".join(bits))
        meta.setObjectName("muted")
        col.addWidget(meta)
        lay.addLayout(col, 1)

        self.actions = QWidget()
        al = QHBoxLayout(self.actions)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(0)
        edit = icon_button("edit", tr("Изменить"))
        edit.clicked.connect(self.edit_requested)
        remove = icon_button("trash", tr("Удалить"), theme.DANGER, 15)
        remove.clicked.connect(self.remove_requested)
        al.addWidget(edit)
        al.addWidget(remove)
        self.actions.setVisible(False)
        lay.addWidget(self.actions)
        switch = ToggleSwitch(profile.enabled)
        switch.setToolTip(tr("Включать автоматически"))
        switch.toggled.connect(self.toggled)
        lay.addWidget(switch, 0, Qt.AlignVCenter)

    def enterEvent(self, event) -> None:  # noqa: N802
        self.actions.setVisible(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.actions.setVisible(False)
        super().leaveEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.edit_requested.emit()
        super().mouseDoubleClickEvent(event)


class ProfilesPage(QWidget):
    def __init__(self, controller) -> None:
        super().__init__()
        self.controller = controller
        self._running: set[str] = set()

        add = make_button(tr("Новый профиль"), "plus", "primary")
        add.clicked.connect(self.add)

        self.status_card = QFrame()
        self.status_card.setObjectName("card")
        sl = QHBoxLayout(self.status_card)
        sl.setContentsMargins(18, 14, 18, 14)
        sl.setSpacing(14)
        self.status_icon = IconBadge("gamepad", theme.ACCENT, 44)
        sl.addWidget(self.status_icon)
        text = QVBoxLayout()
        text.setSpacing(2)
        self.status_title = QLabel()
        self.status_title.setObjectName("h2")
        self.status_hint = QLabel()
        self.status_hint.setObjectName("hint")
        self.status_hint.setWordWrap(True)
        text.addWidget(self.status_title)
        text.addWidget(self.status_hint)
        sl.addLayout(text, 1)
        mode_col = QVBoxLayout()
        mode_col.setSpacing(4)
        mode_label = QLabel(tr("Режим"))
        mode_label.setObjectName("hint")
        self.mode = QComboBox()
        self.mode.setFixedWidth(260)
        self.mode.currentIndexChanged.connect(self._mode_changed)
        mode_col.addWidget(mode_label)
        mode_col.addWidget(self.mode)
        sl.addLayout(mode_col)

        self.list_box = QVBoxLayout()
        self.list_box.setSpacing(8)
        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(0, 0, 8, 0)
        hl.setSpacing(10)
        hl.addWidget(self.status_card)
        hl.addLayout(self.list_box)
        how = QLabel(
            tr("Как это работает: KMuted раз в пару секунд смотрит, какие программы запущены. Когда запущена игра "
               "из профиля — включаются её фразы, колёса и звуки (вместе с общими), её голос и настройки перевода. "
               "Закрыли игру — всё возвращается. В игру ничего не внедряется, античит это не касается.")
        )
        how.setObjectName("hint")
        how.setWordWrap(True)
        how.setContentsMargins(6, 6, 6, 0)
        hl.addWidget(how)
        hl.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(holder)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 12)
        lay.setSpacing(12)
        lay.addWidget(
            page_header(
                tr("Профили игр"),
                tr("Свой набор фраз, колёс и звуков для каждой игры — включается сам, когда игра запущена."),
                add,
            )
        )
        lay.addWidget(scroll, 1)

        self._poll = QTimer(self)  # "game running" marks, only while the page is visible
        self._poll.setInterval(RUNNING_POLL_MS)
        self._poll.timeout.connect(self._scan)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(120)
        self._refresh_timer.timeout.connect(self.refresh)
        controller.config_changed.connect(self._on_config_changed)
        controller.profile_changed.connect(lambda _pid: self._refresh_timer.start())
        self.refresh()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._scan()
        self._poll.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        self._poll.stop()
        super().hideEvent(event)

    def _scan(self) -> None:
        try:
            running, _front = processes.snapshot()
        except Exception:
            running = set()
        wanted = {exe for p in self.controller.config.profiles for exe in p.processes}
        found = running & wanted
        if found != self._running:
            self._running = found
            self.refresh()

    def _on_config_changed(self, section: str) -> None:
        if section in ("profiles", "phrases", "wheels", "sounds", "voices", "translate"):
            self._refresh_timer.start()

    # ------------------------------------------------------------ view

    def refresh(self) -> None:
        c = self.controller
        cfg = c.config
        self._fill_mode()
        prof = c.active_profile()
        mode = cfg.general.profile_mode
        if prof is not None:
            self.status_title.setText(tr("Сейчас: {name}", name=prof.name))
            if mode not in (PROFILE_AUTO, PROFILE_NONE):
                self.status_hint.setText(tr("Включён вручную. Работают бинды этой игры и общие."))
            else:
                self.status_hint.setText(tr("Включился сам: игра запущена. Работают бинды этой игры и общие."))
        else:
            self.status_title.setText(tr("Сейчас: обычный режим"))
            if mode == PROFILE_NONE:
                self.status_hint.setText(tr("Профили выключены — работают только общие бинды."))
            elif cfg.profiles:
                self.status_hint.setText(tr("Ни одна игра из профилей не запущена. Работают общие бинды."))
            else:
                self.status_hint.setText(tr("Создайте профиль — и бинды будут переключаться сами."))

        while self.list_box.count():
            item = self.list_box.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        if not cfg.profiles:
            add = make_button(tr("Создать первый профиль"), "plus", "primary")
            add.clicked.connect(self.add)
            self.list_box.addWidget(
                EmptyState(
                    "gamepad",
                    tr("Профилей пока нет"),
                    tr("Например: в CS2 — коллауты на Alt+1…4 и колесо с «rush B», в Dota — свои фразы "
                       "и перевод на английский. Выберите игру из списка популярных или из запущенных программ."),
                    add,
                )
            )
            return
        for profile in cfg.profiles:
            running = bool(self._running.intersection(profile.processes))
            card = ProfileCard(c, profile, running)
            card.edit_requested.connect(lambda p=profile: self.edit(p))
            card.remove_requested.connect(lambda p=profile: self.remove(p))
            card.toggled.connect(lambda on, p=profile: self._set_enabled(p, on))
            self.list_box.addWidget(card)

    def _fill_mode(self) -> None:
        cfg = self.controller.config
        self.mode.blockSignals(True)
        self.mode.clear()
        self.mode.addItem(icon("zap", theme.MUTED, 14), tr("Автоматически по игре"), PROFILE_AUTO)
        self.mode.addItem(icon("power", theme.MUTED, 14), tr("Выключены"), PROFILE_NONE)
        for p in cfg.profiles:
            self.mode.addItem(profile_cover(p, 16), tr("Всегда «{name}»", name=p.name), p.id)
        self.mode.setCurrentIndex(max(0, self.mode.findData(cfg.general.profile_mode)))
        self.mode.blockSignals(False)

    # ------------------------------------------------------------ edits

    def _mode_changed(self) -> None:
        mode = self.mode.currentData()
        if mode and mode != self.controller.config.general.profile_mode:
            self.controller.set_profile_mode(mode)

    def add(self) -> None:
        profile = GameProfile(name=tr("Игра"))
        dlg = ProfileDialog(self.controller, profile, True, self)
        if dlg.exec() == QDialog.Accepted:
            self.controller.config.profiles.append(profile)
            self.controller.edited("profiles")
            self._scan()
            self.controller.notify.emit(tr("Профиль «{name}» создан", name=profile.name), "success")

    def edit(self, profile: GameProfile) -> None:
        dlg = ProfileDialog(self.controller, profile, False, self)
        if dlg.exec() == QDialog.Accepted:
            self.controller.edited("profiles")
            self._scan()

    def remove(self, profile: GameProfile) -> None:
        cfg = self.controller.config
        if profile not in cfg.profiles:
            return
        cfg.profiles.remove(profile)
        for item in [*cfg.phrases, *cfg.wheels, *cfg.sounds]:
            if profile.id in item.profiles:
                item.profiles.remove(profile.id)  # what was only for this game now works everywhere
        if cfg.general.profile_mode == profile.id:
            cfg.general.profile_mode = PROFILE_AUTO
        self.controller.edited("profiles")
        self.controller.notify.emit(tr("Профиль удалён; его фразы теперь работают везде"), "info")

    def _set_enabled(self, profile: GameProfile, on: bool) -> None:
        if profile.enabled != on:
            profile.enabled = on
            self.controller.edited("profiles")
