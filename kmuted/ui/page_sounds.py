"""Soundboard: your own mp3/wav files on hotkeys, played into the mic."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from kmuted.audio import sounds as soundlib
from kmuted.config import Sound
from kmuted.i18n import tr
from kmuted.ui import theme
from kmuted.ui.components import EmptyState, Equalizer, Keycaps, ToggleSwitch, icon_button, make_button, page_header
from kmuted.ui.icons import icon
from kmuted.ui.profile_widgets import ProfileScopeButton
from kmuted.ui.widgets import HotkeyEdit, ValueSlider

TILE_W = 230
TILE_H = 124


def _fmt_duration(seconds: float) -> str:
    if seconds <= 0:
        return ""
    m, s = divmod(int(round(seconds)), 60)
    return f"{m}:{s:02d}"


class SoundDialog(QDialog):
    def __init__(self, controller, sound: Sound, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Звук"))
        self.setMinimumWidth(520)
        self.controller = controller
        self.sound = sound

        title = QLabel(tr("Настройки звука"))
        title.setObjectName("h2")
        self.name = QLineEdit(sound.name)
        self.file = QLineEdit(sound.file)
        self.file.setReadOnly(True)
        replace = make_button(tr("Заменить…"), "folder")
        replace.clicked.connect(self._replace)
        file_row = QHBoxLayout()
        file_row.addWidget(self.file, 1)
        file_row.addWidget(replace)
        self.hotkey = HotkeyEdit(sound.hotkey)
        self.hotkey.changed.connect(self._check_conflict)
        self.scope = ProfileScopeButton(controller, sound.profiles)
        self.scope.changed.connect(lambda: self._check_conflict(self.hotkey.combo()))
        self.volume = ValueSlider(0, 200, sound.volume, lambda v: f"{v}%")
        self.restart = ToggleSwitch(sound.restart)
        restart_row = QHBoxLayout()
        restart_row.addWidget(self.restart)
        restart_row.addWidget(QLabel(tr("Повторное нажатие останавливает звук")), 1)
        self.warning = QLabel()
        self.warning.setStyleSheet(f"color: {theme.WARNING};")
        self.warning.setWordWrap(True)

        form = QFormLayout()
        form.setSpacing(12)
        form.addRow(tr("Название"), self.name)
        form.addRow(tr("Файл"), file_row)
        form.addRow(tr("Горячая клавиша"), self.hotkey)
        form.addRow(tr("Где работает"), self.scope)
        form.addRow(tr("Громкость"), self.volume)
        form.addRow("", restart_row)

        listen = make_button(tr("Прослушать"), "headset")
        listen.clicked.connect(lambda: controller.play_sound(sound.id, monitor_only=True))
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok = buttons.button(QDialogButtonBox.Ok)
        ok.setText(tr("Сохранить"))
        ok.setObjectName("primary")
        buttons.button(QDialogButtonBox.Cancel).setText(tr("Отмена"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        bottom = QHBoxLayout()
        bottom.addWidget(listen)
        bottom.addStretch(1)
        bottom.addWidget(buttons)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(12)
        lay.addWidget(title)
        lay.addLayout(form)
        lay.addWidget(self.warning)
        lay.addLayout(bottom)
        self._check_conflict(sound.hotkey)

    def _check_conflict(self, combo: str) -> None:
        text = self.controller.hotkey_conflict(combo, f"sound:{self.sound.id}", tuple(self.scope.profiles()))
        self.warning.setText(text)
        self.warning.setVisible(bool(text))

    def _replace(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("Файл звука"), "", _file_filter())
        if not path:
            return
        try:
            self.file.setText(soundlib.import_file(path))
        except (soundlib.SoundError, OSError) as exc:
            self.warning.setText(str(exc))
            self.warning.show()

    def accept(self) -> None:
        self.sound.name = self.name.text().strip() or soundlib.nice_name(self.file.text())
        self.sound.file = self.file.text()
        self.sound.hotkey = self.hotkey.combo()
        self.sound.volume = self.volume.value()
        self.sound.restart = self.restart.isChecked()
        self.sound.profiles = self.scope.profiles()
        super().accept()


def _file_filter() -> str:
    exts = " ".join(f"*{e}" for e in soundlib.AUDIO_EXTS)
    return f"{tr('Аудио')} ({exts})"


class SoundTile(QFrame):
    play_requested = Signal()
    edit_requested = Signal()
    remove_requested = Signal()

    def __init__(self, sound: Sound, duration: float, playing: bool) -> None:
        super().__init__()
        self.setObjectName("cardSelected" if playing else "cardHover")
        self.setFixedSize(TILE_W, TILE_H)
        self.setCursor(Qt.PointingHandCursor)
        self.sound = sound
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 10, 10)
        lay.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(10)
        self.play = icon_button("stop" if playing else "play", tr("Остановить") if playing else tr("Играть в микрофон"), theme.ACCENT_2, 16)
        self.play.setFixedSize(40, 40)
        self.play.setStyleSheet(
            f"QToolButton {{ padding: 0px; background: {theme.rgba(theme.ACCENT_2, 0.14)}; border: 1px solid "
            f"{theme.rgba(theme.ACCENT_2, 0.4)}; border-radius: 20px; }}"
            f"QToolButton:hover {{ background: {theme.rgba(theme.ACCENT_2, 0.28)}; }}"
        )
        self.play.clicked.connect(self.play_requested)
        top.addWidget(self.play)
        col = QVBoxLayout()
        col.setSpacing(0)
        name = QLabel()
        name.setStyleSheet("font-weight: 650; font-size: 10.5pt;")
        name.setText(name.fontMetrics().elidedText(sound.name, Qt.ElideRight, TILE_W - 90))
        name.setToolTip(sound.name)
        col.addWidget(name)
        meta = QLabel(_fmt_duration(duration) + (f" · {sound.volume}%" if sound.volume != 100 else ""))
        meta.setObjectName("hint")
        col.addWidget(meta)
        top.addLayout(col, 1)
        if playing:
            eq = Equalizer(4)
            eq.set_active(True)
            top.addWidget(eq, 0, Qt.AlignTop)
        lay.addLayout(top)
        lay.addStretch(1)

        bottom = QHBoxLayout()
        bottom.setSpacing(0)
        bottom.addWidget(Keycaps(sound.hotkey, tr("без клавиши")))
        bottom.addStretch(1)
        self.actions = QWidget()
        al = QHBoxLayout(self.actions)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(0)
        edit = icon_button("edit", tr("Изменить"), theme.MUTED, 15)
        edit.clicked.connect(self.edit_requested)
        trash = icon_button("trash", tr("Удалить"), theme.DANGER, 15)
        trash.clicked.connect(self.remove_requested)
        al.addWidget(edit)
        al.addWidget(trash)
        self.actions.setVisible(False)
        bottom.addWidget(self.actions)
        lay.addLayout(bottom)

    def enterEvent(self, event) -> None:  # noqa: N802
        self.actions.setVisible(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.actions.setVisible(False)
        super().leaveEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.edit_requested.emit()
        super().mouseDoubleClickEvent(event)


class _DropHint(QWidget):
    """Dashed frame shown while files are dragged over the page."""

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QColor(theme.ACCENT)
        c.setAlpha(40)
        p.setBrush(c)
        pen = p.pen()
        pen.setColor(QColor(theme.ACCENT))
        pen.setStyle(Qt.DashLine)
        pen.setWidthF(2)
        p.setPen(pen)
        p.drawRoundedRect(self.rect().adjusted(8, 8, -8, -8), 16, 16)
        f = QFont(self.font())
        f.setPointSizeF(14)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.setPen(QColor(theme.TEXT))
        p.drawText(self.rect(), Qt.AlignCenter, tr("Отпустите, чтобы добавить звуки"))
        p.end()


class SoundsPage(QWidget):
    def __init__(self, controller) -> None:
        super().__init__()
        self.controller = controller
        self.setAcceptDrops(True)
        self._durations: dict[str, float] = {}
        self._columns = 0

        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Поиск звуков…"))
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icon("search", theme.FAINT, 16), QLineEdit.LeadingPosition)
        self.search.setFixedWidth(220)
        self.search.textChanged.connect(lambda _t: self.refresh())
        add = make_button(tr("Добавить звуки"), "plus", "primary")
        add.clicked.connect(self.add_files)
        stop = make_button(tr("Стоп"), "stop", tooltip=tr("Остановить все звуки"))
        stop.clicked.connect(lambda: self.controller.stop_sound(None))
        tools = QWidget()
        tl = QHBoxLayout(tools)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(self.search)
        tl.addWidget(stop)
        tl.addWidget(add)

        self.grid = QGridLayout()
        self.grid.setSpacing(12)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(0, 0, 8, 0)
        hl.addLayout(self.grid)
        hl.addStretch(1)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(holder)

        tip = QLabel(tr("Перетащите сюда mp3 / wav / ogg / flac. Звуки играют поверх речи и тоже нажимают кнопку рации."))
        tip.setObjectName("hint")
        tip.setWordWrap(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 12)
        lay.setSpacing(12)
        lay.addWidget(page_header(tr("Звуки"), tr("Саундборд: ваши звуки и мемы на горячих клавишах — прямо в микрофон."), tools))
        lay.addWidget(tip)
        lay.addWidget(self.scroll, 1)

        self._drop = _DropHint(self)
        self._drop.hide()
        self._relayout = QTimer(self)
        self._relayout.setSingleShot(True)
        self._relayout.setInterval(60)
        self._relayout.timeout.connect(self.refresh)
        controller.sounds_changed.connect(self.refresh)
        controller.config_changed.connect(self._on_config_changed)
        self.refresh()

    def _on_config_changed(self, section: str) -> None:
        if section in ("sounds", "phrases", "wheels", "general", "voices"):
            self._relayout.start()

    def _fit_columns(self) -> int:
        usable = self.width() - 56 - 24  # page margins + scrollbar
        return max(1, usable // (TILE_W + 12))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._drop.setGeometry(self.rect())
        if self._fit_columns() != self._columns:
            self._relayout.start()

    def refresh(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        sounds = self.controller.config.sounds
        query = self.search.text().strip().lower()
        shown = [s for s in sounds if not query or query in s.name.lower()]
        self._columns = self._fit_columns()
        if not sounds:
            add = make_button(tr("Выбрать файлы"), "plus", "primary")
            add.clicked.connect(self.add_files)
            self.grid.addWidget(
                EmptyState("volume", tr("Звуков пока нет"), tr("Добавьте свои звуки и мемы — или просто перетащите файлы в это окно."), add),
                0, 0,
            )
            return
        for i, sound in enumerate(shown):
            if sound.id not in self._durations:
                self._durations[sound.id] = self.controller.sounds.duration(sound)
            tile = SoundTile(sound, self._durations[sound.id], self.controller.is_sound_playing(sound.id))
            tile.play_requested.connect(lambda s=sound: self.controller.play_sound(s.id))
            tile.edit_requested.connect(lambda s=sound: self.edit_sound(s))
            tile.remove_requested.connect(lambda s=sound: self.remove_sound(s))
            self.grid.addWidget(tile, i // self._columns, i % self._columns)

    # --- actions ---------------------------------------------------------------

    def add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, tr("Добавить звуки"), "", _file_filter())
        self.import_paths(paths)

    def import_paths(self, paths: list[str]) -> None:
        sounds = self.controller.config.sounds
        before = len(sounds)
        _added, errors = soundlib.import_sounds(sounds, paths)
        added = len(sounds) - before
        if added:
            self.controller.edited("sounds")
            self.controller.notify.emit(tr("Добавлено звуков: {n}", n=added), "success")
        if errors:
            self.controller.error.emit(errors[0])

    def edit_sound(self, sound: Sound) -> None:
        dlg = SoundDialog(self.controller, sound, self)
        if dlg.exec() == QDialog.Accepted:
            self._durations.pop(sound.id, None)
            self.controller.edited("sounds")

    def remove_sound(self, sound: Sound) -> None:
        if sound in self.controller.config.sounds:
            self.controller.stop_sound(sound.id)
            self.controller.config.sounds.remove(sound)
            for wheel in self.controller.config.wheels:
                for slot in wheel.slots:
                    if slot.sound_id == sound.id:
                        slot.sound_id = ""
            self.controller.edited("sounds")
            self.controller.notify.emit(tr("Звук удалён (файл остался в папке звуков)"), "info")

    # --- drag & drop -------------------------------------------------------------

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._drop.setGeometry(self.rect())
            self._drop.raise_()
            self._drop.show()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self._drop.hide()

    def dropEvent(self, event) -> None:  # noqa: N802
        self._drop.hide()
        files = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        audio = [f for f in files if Path(f).suffix.lower() in soundlib.AUDIO_EXTS]
        if audio:
            event.acceptProposedAction()
            self.import_paths(audio)
        elif files:
            self.controller.error.emit(tr("Это не аудиофайлы. Подойдут mp3, wav, ogg, flac."))

