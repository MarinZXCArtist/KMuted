"""Quick phrases: one hotkey — one phrase."""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kmuted.config import Phrase
from kmuted.hotkeys.keys import format_combo
from kmuted.ui import theme
from kmuted.ui.widgets import HotkeyEdit, fill_voice_combo, page_header


class PhraseDialog(QDialog):
    def __init__(self, controller, phrase: Phrase, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Фраза")
        self.setMinimumWidth(480)
        self.controller = controller
        self.phrase = phrase

        self.text = QPlainTextEdit(phrase.text)
        self.text.setPlaceholderText("Что сказать, например: «Спасибо за игру!»")
        self.text.setFixedHeight(90)
        self.hotkey = HotkeyEdit(phrase.hotkey)
        self.voice = QComboBox()
        fill_voice_combo(self.voice, controller.config.voices, phrase.voice_id)
        self.warning = QLabel()
        self.warning.setStyleSheet(f"color: {theme.WARNING};")
        self.warning.setWordWrap(True)
        self.hotkey.changed.connect(self._check_conflict)

        test = QPushButton("▶ Прослушать")
        test.clicked.connect(self._preview)

        form = QFormLayout()
        form.setSpacing(10)
        form.addRow("Текст", self.text)
        form.addRow("Горячая клавиша", self.hotkey)
        form.addRow("Голос", self.voice)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Сохранить")
        buttons.button(QDialogButtonBox.Ok).setObjectName("primary")
        buttons.button(QDialogButtonBox.Cancel).setText("Отмена")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        bottom = QHBoxLayout()
        bottom.addWidget(test)
        bottom.addStretch(1)
        bottom.addWidget(buttons)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.warning)
        lay.addLayout(bottom)
        self._check_conflict(phrase.hotkey)

    def _check_conflict(self, combo: str) -> None:
        text = self.controller.hotkey_conflict(combo, f"phrase:{self.phrase.id}")
        self.warning.setText(text)
        self.warning.setVisible(bool(text))

    def _preview(self) -> None:
        profile = self.controller.config.resolve_voice(self.voice.currentData())
        self.controller.preview(self.text.toPlainText(), profile)

    def accept(self) -> None:
        if not self.text.toPlainText().strip():
            self.text.setFocus()
            return
        self.phrase.text = self.text.toPlainText().strip()
        self.phrase.hotkey = self.hotkey.combo()
        self.phrase.voice_id = self.voice.currentData() or ""
        super().accept()


class PhrasesPage(QWidget):
    def __init__(self, controller) -> None:
        super().__init__()
        self.controller = controller
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Фраза", "Горячая клавиша", "Голос", ""])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(3, 130)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.doubleClicked.connect(lambda _i: self.edit_selected())

        add = QPushButton("+ Добавить фразу")
        add.setObjectName("primary")
        add.clicked.connect(self.add)
        edit = QPushButton("Изменить")
        edit.clicked.connect(self.edit_selected)
        remove = QPushButton("Удалить")
        remove.setObjectName("danger")
        remove.clicked.connect(self.remove_selected)
        up = QPushButton("↑")
        up.setToolTip("Выше")
        up.clicked.connect(lambda: self.move_selected(-1))
        down = QPushButton("↓")
        down.setToolTip("Ниже")
        down.clicked.connect(lambda: self.move_selected(+1))

        buttons = QHBoxLayout()
        buttons.addWidget(add)
        buttons.addWidget(edit)
        buttons.addWidget(remove)
        buttons.addStretch(1)
        buttons.addWidget(up)
        buttons.addWidget(down)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.addWidget(
            page_header(
                "Быстрые фразы",
                "Свои фразы на горячих клавишах: нажали — фраза сразу звучит в микрофоне. "
                "Фразы озвучиваются заранее, поэтому играют без задержки.",
            )
        )
        lay.addLayout(buttons)
        lay.addWidget(self.table, 1)

        controller.config_changed.connect(self._on_config_changed)
        self.refresh()

    def _on_config_changed(self, section: str) -> None:
        if section in ("voices", "general", "wheels"):
            self.refresh()

    def refresh(self) -> None:
        cfg = self.controller.config
        owners = self.controller.hotkey_owners()
        selected = self.table.currentRow()
        self.table.setRowCount(len(cfg.phrases))
        for row, phrase in enumerate(cfg.phrases):
            text_item = QTableWidgetItem(phrase.text)
            text_item.setToolTip(phrase.text)
            key_item = QTableWidgetItem(format_combo(phrase.hotkey) or "—")
            if phrase.hotkey and len(owners.get(phrase.hotkey, [])) > 1:
                key_item.setForeground(QColor(theme.WARNING))
                names = ", ".join(name for _key, name in owners[phrase.hotkey])
                key_item.setToolTip("Эта клавиша назначена несколько раз: " + names)
            voice = cfg.voice_by_id(phrase.voice_id)
            voice_item = QTableWidgetItem(voice.name if voice else "по умолчанию")
            self.table.setItem(row, 0, text_item)
            self.table.setItem(row, 1, key_item)
            self.table.setItem(row, 2, voice_item)
            play = QPushButton("▶ Сказать")
            play.setToolTip("Сказать в микрофон")
            play.setStyleSheet("padding: 4px 10px;")
            play.clicked.connect(lambda _c=False, p=phrase: self.controller.say(p.text, p.voice_id, persist=True))
            holder = QWidget()
            hl = QHBoxLayout(holder)
            hl.setContentsMargins(4, 2, 4, 2)
            hl.addWidget(play)
            self.table.setCellWidget(row, 3, holder)
        if cfg.phrases:
            self.table.selectRow(max(0, min(selected, len(cfg.phrases) - 1)))

    def _selected(self) -> int:
        row = self.table.currentRow()
        return row if 0 <= row < len(self.controller.config.phrases) else -1

    def add(self) -> None:
        phrase = Phrase()
        dlg = PhraseDialog(self.controller, phrase, self)
        if dlg.exec() == QDialog.Accepted:
            self.controller.config.phrases.append(phrase)
            self.controller.edited("phrases")
            self.refresh()
            self.table.selectRow(len(self.controller.config.phrases) - 1)

    def edit_selected(self) -> None:
        row = self._selected()
        if row < 0:
            return
        dlg = PhraseDialog(self.controller, self.controller.config.phrases[row], self)
        if dlg.exec() == QDialog.Accepted:
            self.controller.edited("phrases")
            self.refresh()

    def remove_selected(self) -> None:
        row = self._selected()
        if row < 0:
            return
        del self.controller.config.phrases[row]
        self.controller.edited("phrases")
        self.refresh()

    def move_selected(self, step: int) -> None:
        row = self._selected()
        phrases = self.controller.config.phrases
        target = row + step
        if row < 0 or not 0 <= target < len(phrases):
            return
        phrases[row], phrases[target] = phrases[target], phrases[row]
        self.controller.edited("phrases")
        self.refresh()
        self.table.selectRow(target)
