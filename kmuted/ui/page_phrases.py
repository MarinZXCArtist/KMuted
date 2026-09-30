"""Quick phrases: one hotkey — one phrase. Shown as cards."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from kmuted.config import Phrase
from kmuted.i18n import language
from kmuted.textvars import VARIABLES
from kmuted.ui import theme
from kmuted.ui.components import EmptyState, Keycaps, icon_button, make_button, page_header
from kmuted.ui.icons import icon
from kmuted.ui.profile_widgets import ProfileScopeButton, profile_chips
from kmuted.ui.widgets import HotkeyEdit, fill_voice_combo
from kmuted.i18n import tr


class PhraseDialog(QDialog):
    def __init__(self, controller, phrase: Phrase, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Фраза"))
        self.setMinimumWidth(520)
        self.controller = controller
        self.phrase = phrase

        title = QLabel(tr("Новая фраза") if not phrase.text else tr("Изменить фразу"))
        title.setObjectName("h2")
        self.text = QPlainTextEdit(phrase.text)
        self.text.setPlaceholderText(tr("Что сказать, например: «Спасибо за игру!»"))
        self.text.setFixedHeight(96)
        self.hotkey = HotkeyEdit(phrase.hotkey)
        self.voice = QComboBox()
        fill_voice_combo(self.voice, controller.config.voices, phrase.voice_id)
        self.warning = QLabel()
        self.warning.setStyleSheet(f"color: {theme.WARNING};")
        self.warning.setWordWrap(True)
        self.hotkey.changed.connect(self._check_conflict)
        self.scope = ProfileScopeButton(controller, phrase.profiles)
        self.scope.changed.connect(lambda: self._check_conflict(self.hotkey.combo()))
        vars_hint = QLabel(
            tr("Можно вставлять: {vars}", vars="  ".join(f"<b>{{{names[0] if language() == 'ru' else names[1]}}}</b>" for names, _d in VARIABLES))
        )
        vars_hint.setObjectName("hint")
        vars_hint.setWordWrap(True)
        vars_hint.setToolTip("\n".join(f"{{{n[0]}}} / {{{n[1]}}} — {tr(d)}" for n, d in VARIABLES))

        test = make_button(tr("Прослушать"), "headset")
        test.setToolTip(tr("Только в ваши наушники"))
        test.clicked.connect(self._preview)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.addRow(tr("Текст"), self.text)
        form.addRow("", vars_hint)
        form.addRow(tr("Горячая клавиша"), self.hotkey)
        form.addRow(tr("Голос"), self.voice)
        form.addRow(tr("Где работает"), self.scope)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok = buttons.button(QDialogButtonBox.Ok)
        ok.setText(tr("Сохранить"))
        ok.setObjectName("primary")
        ok.setIcon(icon("check", "white", 16))
        buttons.button(QDialogButtonBox.Cancel).setText(tr("Отмена"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        bottom = QHBoxLayout()
        bottom.addWidget(test)
        bottom.addStretch(1)
        bottom.addWidget(buttons)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(12)
        lay.addWidget(title)
        lay.addLayout(form)
        lay.addWidget(self.warning)
        lay.addLayout(bottom)
        self._check_conflict(phrase.hotkey)

    def _check_conflict(self, combo: str) -> None:
        text = self.controller.hotkey_conflict(combo, f"phrase:{self.phrase.id}", tuple(self.scope.profiles()))
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
        self.phrase.profiles = self.scope.profiles()
        super().accept()


class PhraseCard(QFrame):
    play_requested = Signal()
    edit_requested = Signal()
    remove_requested = Signal()
    move_requested = Signal(int)

    def __init__(self, phrase: Phrase, voice_name: str, conflict: str, chips: list | None = None) -> None:
        super().__init__()
        self.setObjectName("cardHover")
        self.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 10, 10)
        lay.setSpacing(12)

        play = icon_button("play", tr("Сказать в микрофон"), theme.ACCENT_2, 16)
        play.setFixedSize(38, 38)
        play.setStyleSheet(
            f"QToolButton {{ padding: 0px; background: {theme.rgba(theme.ACCENT_2, 0.12)}; border: 1px solid "
            f"{theme.rgba(theme.ACCENT_2, 0.35)}; border-radius: 19px; }}"
            f"QToolButton:hover {{ background: {theme.rgba(theme.ACCENT_2, 0.25)}; }}"
        )
        play.clicked.connect(self.play_requested)
        lay.addWidget(play)

        col = QVBoxLayout()
        col.setSpacing(4)
        text = QLabel(phrase.text)
        text.setWordWrap(True)
        text.setStyleSheet("font-size: 10.5pt; font-weight: 600;")
        text.setToolTip(phrase.text)
        text.setMaximumHeight(text.fontMetrics().lineSpacing() * 2 + 4)
        col.addWidget(text)
        meta = QHBoxLayout()
        meta.setSpacing(6)
        chip = QLabel(voice_name)
        chip.setObjectName("chip")
        meta.addWidget(chip)
        for extra in chips or []:
            meta.addWidget(extra)
        if conflict:
            warn = QLabel(tr("клавиша занята"))
            warn.setObjectName("chipWarn")
            warn.setToolTip(conflict)
            meta.addWidget(warn)
        meta.addStretch(1)
        col.addLayout(meta)
        lay.addLayout(col, 1)

        lay.addWidget(Keycaps(phrase.hotkey, tr("без клавиши")), 0, Qt.AlignVCenter)

        self.actions = QWidget()
        al = QHBoxLayout(self.actions)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(0)
        for name, tip, signal, arg in (
            ("up", tr("Выше"), self.move_requested, -1),
            ("down", tr("Ниже"), self.move_requested, 1),
            ("edit", tr("Изменить"), self.edit_requested, None),
            ("trash", tr("Удалить"), self.remove_requested, None),
        ):
            btn = icon_button(name, tip, theme.DANGER if name == "trash" else theme.MUTED, 15)
            btn.clicked.connect(lambda _c=False, s=signal, a=arg: s.emit(a) if a is not None else s.emit())
            al.addWidget(btn)
        self.actions.setVisible(False)
        lay.addWidget(self.actions)

    def enterEvent(self, event) -> None:  # noqa: N802
        self.actions.setVisible(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.actions.setVisible(False)
        super().leaveEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.edit_requested.emit()
        super().mouseDoubleClickEvent(event)


class PhrasesPage(QWidget):
    def __init__(self, controller) -> None:
        super().__init__()
        self.controller = controller

        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Поиск по фразам…"))
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icon("search", theme.FAINT, 16), QLineEdit.LeadingPosition)
        self.search.setFixedWidth(260)
        self.search.textChanged.connect(lambda _t: self.refresh())
        add = make_button(tr("Добавить фразу"), "plus", "primary")
        add.clicked.connect(self.add)
        tools = QWidget()
        tl = QHBoxLayout(tools)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(self.search)
        tl.addWidget(add)

        self.list_box = QVBoxLayout()
        self.list_box.setSpacing(8)
        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(0, 0, 8, 0)
        hl.addLayout(self.list_box)
        hl.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(holder)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 12)
        lay.setSpacing(12)
        lay.addWidget(
            page_header(
                tr("Быстрые фразы"),
                tr("Нажали горячую клавишу — фраза сразу звучит в микрофоне. Озвучиваются заранее, поэтому без задержки."),
                tools,
            )
        )
        lay.addWidget(scroll, 1)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(120)
        self._refresh_timer.timeout.connect(self.refresh)
        controller.config_changed.connect(self._on_config_changed)
        self.refresh()

    def _on_config_changed(self, section: str) -> None:
        if section == "phrases":
            self.refresh()  # our own edit: show it right away
        elif section in ("voices", "general", "wheels", "profiles"):
            self._refresh_timer.start()

    def refresh(self) -> None:
        while self.list_box.count():
            item = self.list_box.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        cfg = self.controller.config
        query = self.search.text().strip().lower()
        shown = [p for p in cfg.phrases if not query or query in p.text.lower()]
        if not cfg.phrases:
            add = make_button(tr("Добавить первую фразу"), "plus", "primary")
            add.clicked.connect(self.add)
            self.list_box.addWidget(
                EmptyState("phrases", tr("Фраз пока нет"), tr("Добавьте фразы, которые часто говорите, и повесьте их на клавиши."), add)
            )
            return
        if not shown:
            self.list_box.addWidget(EmptyState("search", tr("Ничего не найдено"), tr("Нет фраз с «{query}».", query=query)))
            return
        for phrase in shown:
            voice = cfg.voice_by_id(phrase.voice_id)
            conflict = self.controller.hotkey_conflict(phrase.hotkey, f"phrase:{phrase.id}")
            chips = profile_chips(self.controller, phrase)
            card = PhraseCard(phrase, voice.name if voice else tr("голос по умолчанию"), conflict, chips)
            card.play_requested.connect(lambda p=phrase: self.controller.say(p.text, p.voice_id, persist=True, phrase=True))
            card.edit_requested.connect(lambda p=phrase: self.edit_phrase(p))
            card.remove_requested.connect(lambda p=phrase: self.remove_phrase(p))
            card.move_requested.connect(lambda step, p=phrase: self.move_phrase(p, step))
            self.list_box.addWidget(card)

    def add(self) -> None:
        phrase = Phrase()
        dlg = PhraseDialog(self.controller, phrase, self)
        if dlg.exec() == QDialog.Accepted:
            self.controller.config.phrases.append(phrase)
            self.controller.edited("phrases")

    def edit_phrase(self, phrase: Phrase) -> None:
        dlg = PhraseDialog(self.controller, phrase, self)
        if dlg.exec() == QDialog.Accepted:
            self.controller.edited("phrases")

    def remove_phrase(self, phrase: Phrase) -> None:
        phrases = self.controller.config.phrases
        if phrase in phrases:
            phrases.remove(phrase)
            self.controller.edited("phrases")
            self.controller.notify.emit(tr("Фраза удалена"), "info")

    def move_phrase(self, phrase: Phrase, step: int) -> None:
        phrases = self.controller.config.phrases
        i = phrases.index(phrase)
        j = i + step
        if 0 <= j < len(phrases):
            phrases[i], phrases[j] = phrases[j], phrases[i]
            self.controller.edited("phrases")
