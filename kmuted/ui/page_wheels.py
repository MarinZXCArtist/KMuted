"""Phrase wheels: hold a key, flick the mouse towards a phrase, release."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kmuted.audio import sounds as soundlib
from kmuted.config import WHEEL_MAX_SLOTS, WHEEL_MIN_SLOTS, Wheel, WheelSlot
from kmuted.hotkeys.keys import format_combo
from kmuted.ui import theme
from kmuted.ui.icons import icon
from kmuted.ui.overlay_wheel import WheelPreview
from kmuted.ui.profile_widgets import ProfileScopeButton
from kmuted.ui.components import make_button
from kmuted.ui.widgets import HotkeyEdit, fill_voice_combo, page_header
from kmuted.i18n import tr

_DIRECTIONS_8 = ["↑", "↗", "→", "↘", "↓", "↙", "←", "↖"]


class WheelsPage(QWidget):
    def __init__(self, controller) -> None:
        super().__init__()
        self.controller = controller
        self._loading = False

        # left: wheel list
        self.list = QListWidget()
        self.list.setFixedWidth(180)
        self.list.currentRowChanged.connect(self._load_wheel)
        add = make_button(tr("Колесо"), "plus", "primary")
        add.clicked.connect(self.add_wheel)
        remove = make_button(tr("Удалить"), "trash", "danger")
        remove.clicked.connect(self.remove_wheel)
        left_buttons = QHBoxLayout()
        left_buttons.addWidget(add)
        left_buttons.addWidget(remove)
        sound_wheel = make_button(tr("Колесо из звуков"), "volume")
        sound_wheel.setToolTip(tr("Новое колесо из ваших звуков, как в Soundpad"))
        sound_wheel.clicked.connect(self.add_sound_wheel)
        left = QVBoxLayout()
        left.addWidget(self.list, 1)
        left.addLayout(left_buttons)
        left.addWidget(sound_wheel)

        # middle: editor
        self.name = QLineEdit()
        self.name.editingFinished.connect(self._name_changed)
        self.hotkey = HotkeyEdit()
        self.hotkey.changed.connect(self._hotkey_changed)
        self.count = QSpinBox()
        self.count.setRange(WHEEL_MIN_SLOTS, WHEEL_MAX_SLOTS)
        self.count.valueChanged.connect(self._count_changed)
        self.scope = ProfileScopeButton(controller, [])
        self.scope.changed.connect(self._scope_changed)
        self.warning = QLabel()
        self.warning.setStyleSheet(f"color: {theme.WARNING};")
        self.warning.hide()

        form = QFormLayout()
        form.setSpacing(8)
        form.addRow(tr("Название"), self.name)
        form.addRow(tr("Горячая клавиша"), self.hotkey)
        form.addRow(tr("Секторов"), self.count)
        form.addRow(tr("Где работает"), self.scope)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["", tr("Надпись"), tr("Что сказать")])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed | QAbstractItemView.AnyKeyPressed
        )
        self.table.setShowGrid(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setColumnWidth(1, 110)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.itemChanged.connect(self._item_changed)
        self.table.currentCellChanged.connect(lambda *_: self._slot_selected())

        self.slot_voice = QComboBox()
        self.slot_voice.currentIndexChanged.connect(self._voice_changed)
        self.slot_sound = QComboBox()
        self.slot_sound.setToolTip(tr("Вместо фразы сектор может проиграть звук из саундборда"))
        self.slot_sound.currentIndexChanged.connect(self._sound_changed)
        self.slot_voice_label = QLabel(tr("Голос сектора"))
        self.slot_file = make_button(tr("Звук из файла…"), "folder")
        self.slot_file.setToolTip(tr("mp3 / wav / ogg в выбранный сектор — как в Soundpad"))
        self.slot_file.clicked.connect(self._pick_sound_file)
        voice_row = QVBoxLayout()
        voice_row.setSpacing(6)
        first = QHBoxLayout()
        first.addWidget(self.slot_voice_label)
        first.addWidget(self.slot_voice, 1)
        second = QHBoxLayout()
        second.addWidget(self.slot_sound, 1)
        second.addWidget(self.slot_file)
        voice_row.addLayout(first)
        voice_row.addLayout(second)

        hint = QLabel(
            tr("Двойной клик по ячейке — редактировать. Пустой сектор на колесе не выбирается. "
            "Надпись — короткий текст на колесе, «Что сказать» — полная фраза. "
            "Звуки: «Звук из файла…» или перетащите mp3/wav прямо на таблицу.")
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)

        middle = QVBoxLayout()
        middle.addLayout(form)
        middle.addWidget(self.warning)
        middle.addWidget(self.table, 1)
        middle.addLayout(voice_row)
        middle.addWidget(hint)

        # right: preview
        self.preview = WheelPreview()
        self.preview.setMinimumSize(280, 280)
        test = make_button(tr("Проиграть выбранный сектор"), "play")
        test.clicked.connect(self._say_selected)
        right_box = QWidget()
        right_box.setFixedWidth(300)
        right = QVBoxLayout(right_box)
        right.setContentsMargins(0, 0, 0, 0)
        right.addWidget(self.preview, 1)
        right.addWidget(test)

        body = QHBoxLayout()
        body.setSpacing(16)
        body.addLayout(left)
        body.addLayout(middle, 1)
        body.addWidget(right_box)

        self.editor_widgets = [self.name, self.hotkey, self.count, self.table, self.slot_voice, self.slot_sound, self.slot_file, test]
        self.setAcceptDrops(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 12)
        lay.addWidget(
            page_header(
                tr("Колёса фраз"),
                tr("Зажмите клавишу колеса, поведите мышью в сторону фразы и отпустите — фраза прозвучит. "
                "Работает поверх игры (в оконном или «оконном без рамки» режиме)."),
            )
        )
        lay.addLayout(body, 1)

        controller.config_changed.connect(self._on_config_changed)
        self.refresh_list()

    # --- data helpers ------------------------------------------------------

    def _wheel(self) -> Wheel | None:
        row = self.list.currentRow()
        wheels = self.controller.config.wheels
        return wheels[row] if 0 <= row < len(wheels) else None

    def _on_config_changed(self, section: str) -> None:
        if section in ("voices", "sounds"):
            self._load_wheel(self.list.currentRow())
        elif section == "profiles":
            self.refresh_list()

    def refresh_list(self, select: int | None = None) -> None:
        wheels = self.controller.config.wheels
        current = self.list.currentRow() if select is None else select
        self.list.blockSignals(True)
        self.list.clear()
        for w in wheels:
            key = format_combo(w.hotkey)
            games = [p.name for p in self.controller.config.profiles if p.id in w.profiles]
            where = f"  ·  🎮 {', '.join(games)}" if games else ""
            item = QListWidgetItem(icon("wheel", theme.ACCENT, 18), f"{w.name}\n{key or tr('без клавиши')}{where}")
            self.list.addItem(item)
        self.list.blockSignals(False)
        if wheels:
            self.list.setCurrentRow(max(0, min(current, len(wheels) - 1)))
        self._load_wheel(self.list.currentRow())

    def _load_wheel(self, _row: int) -> None:
        wheel = self._wheel()
        for w in self.editor_widgets:
            w.setEnabled(wheel is not None)
        if wheel is None:
            self.table.setRowCount(0)
            self.preview.set_wheel("", [])
            return
        self._loading = True
        self.name.setText(wheel.name)
        self.hotkey.set_combo(wheel.hotkey)
        self.count.setValue(len(wheel.slots))
        self.scope.set_selected(wheel.profiles)
        self._fill_table(wheel)
        self._loading = False
        self._check_conflict()
        self._update_preview()

    def _fill_table(self, wheel: Wheel) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(len(wheel.slots))
        directions = _DIRECTIONS_8 if len(wheel.slots) == 8 else None
        for row, slot in enumerate(wheel.slots):
            num = QTableWidgetItem(f"{row + 1} {directions[row]}" if directions else str(row + 1))
            num.setFlags(Qt.ItemIsEnabled)
            num.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, num)
            self.table.setItem(row, 1, QTableWidgetItem(slot.label))
            sound = self.controller.config.sound_by_id(slot.sound_id) if slot.sound_id else None
            if sound is not None:
                what = QTableWidgetItem(f"♪\u00a0{sound.name}")
                what.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                what.setForeground(QColor(theme.ACCENT_2))
                what.setToolTip(tr("Сектор играет звук. Чтобы он говорил фразу, выберите «без звука» ниже."))
            else:
                what = QTableWidgetItem(slot.text)
            self.table.setItem(row, 2, what)
        self.table.blockSignals(False)
        if wheel.slots:
            self.table.setCurrentCell(max(0, min(self.table.currentRow(), len(wheel.slots) - 1)), 2)
        self._slot_selected()

    def _slot_selected(self) -> None:
        wheel = self._wheel()
        row = self.table.currentRow()
        slot = wheel.slots[row] if wheel and 0 <= row < len(wheel.slots) else None
        self.slot_voice.blockSignals(True)
        fill_voice_combo(self.slot_voice, self.controller.config.voices, slot.voice_id if slot else "")
        self.slot_voice.blockSignals(False)
        self.slot_voice.setEnabled(slot is not None and not (slot and slot.sound_id))
        self.slot_sound.blockSignals(True)
        self.slot_sound.clear()
        self.slot_sound.addItem(tr("♪ без звука — говорить фразу"), "")
        for snd in self.controller.config.sounds:
            self.slot_sound.addItem(f"♪ {snd.name}", snd.id)
        self.slot_sound.setCurrentIndex(max(0, self.slot_sound.findData(slot.sound_id if slot else "")))
        self.slot_sound.setEnabled(slot is not None and bool(self.controller.config.sounds))
        self.slot_sound.blockSignals(False)
        self.slot_voice_label.setText(tr("Голос сектора {n}", n=row + 1) if slot else tr("Голос сектора"))
        self._update_preview()

    def _update_preview(self) -> None:
        wheel = self._wheel()
        if wheel is None:
            return
        self.preview.set_wheel(wheel.name, [self.controller.slot_caption(s) for s in wheel.slots], self.table.currentRow())

    def _check_conflict(self) -> None:
        wheel = self._wheel()
        text = self.controller.hotkey_conflict(wheel.hotkey, f"wheel:{wheel.id}") if wheel else ""
        self.warning.setText(text)
        self.warning.setVisible(bool(text))

    def _changed(self) -> None:
        self.controller.edited("wheels")
        self._update_preview()

    # --- editor slots ----------------------------------------------------------

    def _name_changed(self) -> None:
        wheel = self._wheel()
        if wheel is None or self._loading:
            return
        name = self.name.text().strip() or tr("Колесо")
        if name != wheel.name:
            wheel.name = name
            self._changed()
            self.refresh_list()

    def _scope_changed(self) -> None:
        wheel = self._wheel()
        if wheel is None or self._loading:
            return
        wheel.profiles = self.scope.profiles()
        self._changed()
        self._check_conflict()

    def _hotkey_changed(self, combo: str) -> None:
        wheel = self._wheel()
        if wheel is None or self._loading:
            return
        wheel.hotkey = combo
        self._changed()
        self.refresh_list()

    def _count_changed(self, value: int) -> None:
        wheel = self._wheel()
        if wheel is None or self._loading:
            return
        if value > len(wheel.slots):
            wheel.slots += [WheelSlot() for _ in range(value - len(wheel.slots))]
        else:
            del wheel.slots[value:]
        self._fill_table(wheel)
        self._changed()

    def _item_changed(self, item: QTableWidgetItem) -> None:
        wheel = self._wheel()
        if wheel is None or self._loading or not 0 <= item.row() < len(wheel.slots):
            return
        slot = wheel.slots[item.row()]
        value = item.text().strip()
        if item.column() == 1:
            slot.label = value
        elif item.column() == 2:
            slot.text = value
        else:
            return
        self._changed()

    def _sound_changed(self) -> None:
        wheel = self._wheel()
        row = self.table.currentRow()
        if wheel is None or self._loading or not 0 <= row < len(wheel.slots):
            return
        wheel.slots[row].sound_id = self.slot_sound.currentData() or ""
        self.slot_voice.setEnabled(not wheel.slots[row].sound_id)
        self._fill_table(wheel)
        self._changed()

    def _voice_changed(self) -> None:
        wheel = self._wheel()
        row = self.table.currentRow()
        if wheel is None or self._loading or not 0 <= row < len(wheel.slots):
            return
        wheel.slots[row].voice_id = self.slot_voice.currentData() or ""
        self._changed()

    def _say_selected(self) -> None:
        wheel = self._wheel()
        row = self.table.currentRow()
        if not wheel or not 0 <= row < len(wheel.slots):
            return
        slot = wheel.slots[row]
        if slot.sound_id and self.controller.config.sound_by_id(slot.sound_id):
            self.controller.play_sound(slot.sound_id)
        elif slot.text.strip():
            self.controller.say(slot.text, slot.voice_id, persist=True, phrase=True)

    # --- sounds in the wheel --------------------------------------------------------

    def _pick_sound_file(self) -> None:
        exts = " ".join(f"*{e}" for e in soundlib.AUDIO_EXTS)
        files, _f = QFileDialog.getOpenFileNames(self, tr("Звуки для колеса"), "", f"{tr('Аудио')} ({exts})")
        if files:
            self.put_sound_files(files, self.table.currentRow())

    def put_sound_files(self, files: list[str], start_row: int = -1) -> None:
        """Import audio files and put them into sectors, from ``start_row`` on.

        The first file goes to ``start_row`` (or the first empty sector),
        the rest to the next empty sectors; the wheel grows up to 12 sectors.
        """
        wheel = self._wheel()
        if wheel is None:
            return
        cfg = self.controller.config
        sounds, errors = soundlib.import_sounds(cfg.sounds, files)
        if errors:
            self.controller.error.emit(errors[0])
        if not sounds:
            return
        placed = 0
        row = start_row if 0 <= start_row < len(wheel.slots) else -1
        for sound in sounds:
            if row < 0 or placed > 0:
                row = _next_empty(wheel, max(row, 0))
                if row < 0 and len(wheel.slots) < WHEEL_MAX_SLOTS:
                    wheel.slots.append(WheelSlot())
                    row = len(wheel.slots) - 1
                if row < 0:
                    break
            wheel.slots[row].sound_id = sound.id
            wheel.slots[row].label = ""  # the caption becomes the sound's name
            placed += 1
        self.controller.edited("sounds")
        self._loading = True
        self.count.setValue(len(wheel.slots))
        self._loading = False
        self._fill_table(wheel)
        self._changed()
        if placed < len(sounds):
            self.controller.notify.emit(tr("В колесе максимум {n} секторов — лишние звуки добавлены только в «Звуки»", n=WHEEL_MAX_SLOTS), "warning")
        else:
            self.controller.notify.emit(tr("Звуков в колесе: +{n}", n=placed), "success")

    def add_sound_wheel(self) -> None:
        """A Soundpad-style wheel made of the soundboard's sounds."""
        cfg = self.controller.config
        if not cfg.sounds:
            exts = " ".join(f"*{e}" for e in soundlib.AUDIO_EXTS)
            files, _f = QFileDialog.getOpenFileNames(self, tr("Звуки для колеса"), "", f"{tr('Аудио')} ({exts})")
            if not files:
                return
            _sounds, errors = soundlib.import_sounds(cfg.sounds, files)
            if errors:
                self.controller.error.emit(errors[0])
            if not cfg.sounds:
                return
            self.controller.edited("sounds")
        slots = [WheelSlot(sound_id=snd.id) for snd in cfg.sounds[:WHEEL_MAX_SLOTS]]
        slots += [WheelSlot() for _ in range(WHEEL_MIN_SLOTS - len(slots))]
        cfg.wheels.append(Wheel(name=tr("Звуки"), slots=slots))
        self.controller.edited("wheels")
        self.refresh_list(select=len(cfg.wheels) - 1)
        self.controller.notify.emit(tr("Колесо «Звуки» создано — назначьте ему клавишу"), "success")

    # --- drag & drop -------------------------------------------------------------------

    def _dropped_audio(self, event) -> list[str]:
        files = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        return [f for f in files if Path(f).suffix.lower() in soundlib.AUDIO_EXTS]

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls() and self._wheel() is not None:
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        audio = self._dropped_audio(event)
        if not audio:
            if event.mimeData().hasUrls():
                self.controller.error.emit(tr("Это не аудиофайлы. Подойдут mp3, wav, ogg, flac."))
            return
        event.acceptProposedAction()
        viewport = self.table.viewport()
        pos = viewport.mapFrom(self, event.position().toPoint())
        row = self.table.rowAt(pos.y()) if viewport.rect().contains(pos) else self.table.currentRow()
        self.put_sound_files(audio, row)

    # --- list actions ----------------------------------------------------------

    def add_wheel(self) -> None:
        wheels = self.controller.config.wheels
        wheels.append(Wheel(name=tr("Колесо {n}", n=len(wheels) + 1)))
        self.controller.edited("wheels")
        self.refresh_list(select=len(wheels) - 1)
        self.name.setFocus()
        self.name.selectAll()

    def remove_wheel(self) -> None:
        row = self.list.currentRow()
        wheels = self.controller.config.wheels
        if 0 <= row < len(wheels):
            del wheels[row]
            self.controller.edited("wheels")
            self.refresh_list(select=max(0, row - 1))


def _next_empty(wheel: Wheel, start: int) -> int:
    """First empty sector from ``start`` on, wrapping around; -1 if none."""
    n = len(wheel.slots)
    for i in list(range(start, n)) + list(range(0, min(start, n))):
        if not wheel.slots[i].filled:
            return i
    return -1
