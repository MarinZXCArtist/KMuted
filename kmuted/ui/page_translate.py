"""Translation before speech: write in your language, the others hear theirs."""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from kmuted import translate as tl
from kmuted.i18n import tr
from kmuted.ui import theme
from kmuted.ui.components import IconBadge, SectionTitle, SettingRow, ToggleSwitch, icon_button, make_button, page_header
from kmuted.ui.icons import icon


def _lang_combo(include_auto: bool = False) -> QComboBox:
    combo = QComboBox()
    if include_auto:
        combo.addItem(icon("sparkles", theme.ACCENT_2, 14), tl.language_name("auto"), "auto")
    for code, _name in tl.LANGUAGES:
        combo.addItem(f"{tl.language_name(code)}  ·  {code.upper()}", code)
    combo.setMaxVisibleItems(16)
    return combo


def _select(combo: QComboBox, data) -> None:
    combo.blockSignals(True)
    idx = combo.findData(data)
    combo.setCurrentIndex(max(0, idx))
    combo.blockSignals(False)


class TranslatePage(QWidget):
    def __init__(self, controller) -> None:
        super().__init__()
        self.controller = controller
        self._voice_rows: list[QWidget] = []

        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(28, 24, 28, 20)
        lay.setSpacing(8)
        lay.addWidget(
            page_header(
                tr("Перевод"),
                tr("Пишите на своём языке — в войс прозвучит перевод. Для игр с иностранцами: "
                   "текст из окна ввода, фразы и колёса переводятся перед озвучкой."),
            )
        )
        lay.addWidget(self._build_main_card())

        lay.addWidget(SectionTitle(tr("Переводчик")))
        self.provider = QComboBox()
        for cls in tl.PROVIDER_CLASSES:
            prov = tl.PROVIDERS[cls.key]
            glyph = icon("sparkles", theme.ACCENT_2, 14) if prov.ai else icon("globe", theme.MUTED, 14)
            self.provider.addItem(glyph, f"{tr(prov.title)}  —  {tr(prov.pricing)}", prov.key)
        self.provider.setFixedWidth(330)
        self.provider.currentIndexChanged.connect(self._provider_changed)
        self.provider_row = SettingRow(tr("Сервис перевода"), "", self.provider, "translate")
        lay.addWidget(self.provider_row)

        self.key_card = QFrame()
        self.key_card.setObjectName("cardHover")
        kl = QHBoxLayout(self.key_card)
        kl.setContentsMargins(16, 12, 16, 12)
        kl.setSpacing(10)
        kl.addWidget(IconBadge("key"))
        self.key_title = QLabel()
        self.key_title.setObjectName("h3")
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText(tr("Вставьте ключ API"))
        self.key_edit.editingFinished.connect(self._key_changed)
        show = icon_button("eye", tr("Показать / скрыть"))
        show.clicked.connect(
            lambda: self.key_edit.setEchoMode(QLineEdit.Normal if self.key_edit.echoMode() == QLineEdit.Password else QLineEdit.Password)
        )
        self.get_key = make_button(tr("Получить ключ"), "link", "ghost")
        self.get_key.clicked.connect(self._open_signup)
        kl.addWidget(self.key_title)
        kl.addWidget(self.key_edit, 1)
        kl.addWidget(show)
        kl.addWidget(self.get_key)
        lay.addWidget(self.key_card)

        self.model = QComboBox()
        self.model.setFixedWidth(330)
        self.model.currentIndexChanged.connect(self._model_changed)
        self.model_row = SettingRow(tr("Модель"), tr("Качество против скорости и цены"), self.model, "cpu")
        lay.addWidget(self.model_row)

        self.style = QComboBox()
        for key, title in tl.STYLES:
            self.style.addItem(tr(title), key)
        self.style.setFixedWidth(330)
        self.style.currentIndexChanged.connect(lambda: self._set("style", self.style.currentData()))
        self.style_row = SettingRow(tr("Стиль"), "", self.style, "wand")
        lay.addWidget(self.style_row)

        self.instructions = QLineEdit()
        self.instructions.setPlaceholderText(tr("Например: названия карт не переводить, обращаться на «ты»"))
        self.instructions.setMaxLength(500)
        self.instructions.setFixedWidth(330)
        self.instructions.editingFinished.connect(lambda: self._set("instructions", self.instructions.text().strip()))
        self.instructions_row = SettingRow(tr("Пожелания для ИИ"), tr("Свои правила перевода, если нужно"), self.instructions, "phrases")
        lay.addWidget(self.instructions_row)

        self.email = QLineEdit()
        self.email.setPlaceholderText("name@example.com")
        self.email.setFixedWidth(330)
        self.email.editingFinished.connect(lambda: self._set("email", self.email.text().strip()))
        self.email_row = SettingRow(
            tr("E-mail для MyMemory"), tr("Необязательно: поднимает бесплатный лимит до 50 000 символов в день"), self.email, "info"
        )
        lay.addWidget(self.email_row)

        lay.addWidget(SectionTitle(tr("Как звучит")))
        self.phrases = ToggleSwitch()
        self.phrases.toggled.connect(lambda on: self._set("phrases", on))
        lay.addWidget(SettingRow(tr("Переводить фразы и колёса"), tr("Иначе переводится только текст из окна ввода"), self.phrases, "phrases"))
        self.preview = ToggleSwitch()
        self.preview.toggled.connect(lambda on: self._set("preview", on))
        lay.addWidget(
            SettingRow(tr("Перевод в окне ввода"), tr("Показывать перевод под текстом, пока вы пишете — видно, что услышат"), self.preview, "eye")
        )
        self.auto_voice = ToggleSwitch()
        self.auto_voice.toggled.connect(lambda on: self._set("auto_voice", on))
        lay.addWidget(
            SettingRow(
                tr("Голос под язык перевода"),
                tr("Если голос говорит только на своём языке, взять голос Edge нужного языка — тот же пол, скорость и RVC. "
                   "Multilingual- и облачные голоса говорят на любом языке сами."),
                self.auto_voice,
                "voices",
            )
        )
        self.voices_card = QFrame()
        self.voices_card.setObjectName("card")
        self.voices_lay = QVBoxLayout(self.voices_card)
        self.voices_lay.setContentsMargins(16, 12, 16, 12)
        self.voices_lay.setSpacing(8)
        head = QHBoxLayout()
        vt = QLabel(tr("Свой голос для языка"))
        vt.setObjectName("h3")
        add_voice = make_button(tr("Добавить"), "plus", "ghost")
        add_voice.clicked.connect(self._add_lang_voice)
        head.addWidget(vt)
        head.addStretch(1)
        head.addWidget(add_voice)
        self.voices_lay.addLayout(head)
        self.voices_hint = QLabel(tr("Например: немецкий — всегда голос «Florian», английский — ваш голос ElevenLabs."))
        self.voices_hint.setObjectName("hint")
        self.voices_hint.setWordWrap(True)
        self.voices_lay.addWidget(self.voices_hint)
        self.voices_list = QVBoxLayout()
        self.voices_list.setSpacing(6)
        self.voices_lay.addLayout(self.voices_list)
        lay.addWidget(self.voices_card)

        lay.addWidget(SectionTitle(tr("Быстрое переключение")))
        fav = QFrame()
        fav.setObjectName("card")
        fl = QVBoxLayout(fav)
        fl.setContentsMargins(16, 12, 16, 14)
        fl.setSpacing(10)
        note = QLabel(
            tr("Отмеченные языки переключаются по кругу клавишей «Следующий язык перевода» и Ctrl+L в окне ввода.")
        )
        note.setObjectName("hint")
        note.setWordWrap(True)
        fl.addWidget(note)
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        self.fav_buttons: dict[str, QPushButton] = {}
        for i, (code, _name) in enumerate(tl.LANGUAGES):
            btn = QPushButton(f"{code.upper()} · {tl.language_name(code)}")
            btn.setObjectName("toggleChip")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.toggled.connect(self._favorites_changed)
            grid.addWidget(btn, i // 5, i % 5)
            self.fav_buttons[code] = btn
        fl.addLayout(grid)
        lay.addWidget(fav)

        lay.addWidget(SectionTitle(tr("Попробовать")))
        test = QFrame()
        test.setObjectName("card")
        tl_ = QVBoxLayout(test)
        tl_.setContentsMargins(16, 14, 16, 14)
        tl_.setSpacing(10)
        row = QHBoxLayout()
        self.test_edit = QLineEdit()
        self.test_edit.setPlaceholderText(tr("Напишите фразу, например: «го на бэ, у них никого»"))
        self.test_edit.returnPressed.connect(self._test_translate)
        go = make_button(tr("Перевести"), "translate", "primary")
        go.clicked.connect(self._test_translate)
        self.say_btn = make_button(tr("Сказать"), "send")
        self.say_btn.clicked.connect(self._test_say)
        row.addWidget(self.test_edit, 1)
        row.addWidget(go)
        row.addWidget(self.say_btn)
        tl_.addLayout(row)
        self.test_result = QLabel(tr("Здесь появится перевод."))
        self.test_result.setObjectName("muted")
        self.test_result.setWordWrap(True)
        self.test_result.setTextInteractionFlags(Qt.TextSelectableByMouse)
        tl_.addWidget(self.test_result)
        lay.addWidget(test)
        lay.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        controller.config_changed.connect(self._on_config_changed)
        controller.profile_changed.connect(lambda _pid: self._refresh_status())
        self.load()

    # ------------------------------------------------------------ building

    def _build_main_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(14)

        top = QHBoxLayout()
        top.setSpacing(14)
        top.addWidget(IconBadge("translate", theme.BLUE, 44))
        text = QVBoxLayout()
        text.setSpacing(2)
        title = QLabel(tr("Переводить перед озвучкой"))
        title.setObjectName("h2")
        self.status = QLabel()
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)
        text.addWidget(title)
        text.addWidget(self.status)
        top.addLayout(text, 1)
        self.enabled = ToggleSwitch()
        self.enabled.toggled.connect(self._enabled_toggled)
        top.addWidget(self.enabled, 0, Qt.AlignVCenter)
        lay.addLayout(top)

        langs = QHBoxLayout()
        langs.setSpacing(10)
        src_col = QVBoxLayout()
        src_col.setSpacing(4)
        src_label = QLabel(tr("Я пишу на"))
        src_label.setObjectName("hint")
        self.source = _lang_combo(include_auto=True)
        self.source.currentIndexChanged.connect(lambda: self._set("source", self.source.currentData()))
        src_col.addWidget(src_label)
        src_col.addWidget(self.source)
        swap = icon_button("swap", tr("Поменять местами"), theme.TEXT, 18)
        swap.clicked.connect(self._swap)
        tgt_col = QVBoxLayout()
        tgt_col.setSpacing(4)
        tgt_label = QLabel(tr("Другие слышат"))
        tgt_label.setObjectName("hint")
        self.target = _lang_combo()
        self.target.currentIndexChanged.connect(lambda: self._set("target", self.target.currentData()))
        tgt_col.addWidget(tgt_label)
        tgt_col.addWidget(self.target)
        langs.addLayout(src_col, 1)
        langs.addWidget(swap, 0, Qt.AlignBottom)
        langs.addLayout(tgt_col, 1)
        lay.addLayout(langs)

        tip = QLabel(
            tr("Совет: начните сообщение со знака «=», чтобы сказать его без перевода (=gg wp). "
               "Горячие клавиши «Перевод вкл/выкл» и «Следующий язык» — на вкладке «Горячие клавиши».")
        )
        tip.setObjectName("hint")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        return card

    # ------------------------------------------------------------ state

    def load(self) -> None:
        t = self.controller.config.translate
        self.enabled.blockSignals(True)
        self.enabled.setChecked(t.enabled)
        self.enabled.blockSignals(False)
        _select(self.source, t.source)
        _select(self.target, t.target)
        _select(self.provider, t.provider)
        _select(self.style, t.style)
        self.instructions.setText(t.instructions)
        self.email.setText(t.email)
        for switch, value in ((self.phrases, t.phrases), (self.preview, t.preview), (self.auto_voice, t.auto_voice)):
            switch.blockSignals(True)
            switch.setChecked(value)
            switch.blockSignals(False)
        for code, btn in self.fav_buttons.items():
            btn.blockSignals(True)
            btn.setChecked(code in t.favorites)
            btn.blockSignals(False)
        self._update_provider_ui()
        self._rebuild_voice_rows()
        self._refresh_status()

    def _on_config_changed(self, section: str) -> None:
        if section == "translate":
            t = self.controller.config.translate
            self.enabled.blockSignals(True)
            self.enabled.setChecked(t.enabled)
            self.enabled.blockSignals(False)
            self.enabled.update()
            _select(self.target, t.target)
            self._refresh_status()
        elif section == "voices":
            self._rebuild_voice_rows()
        elif section == "profiles":
            self._refresh_status()

    def _refresh_status(self) -> None:
        c = self.controller
        t = c.config.translate
        prov = tl.PROVIDERS.get(t.provider, tl.PROVIDERS["google"])
        target = c.translation_target()
        if target:
            text = tr("Включён: {label} · {provider}", label=tl.short_label(t.source, target), provider=tr(prov.title))
            problem = c.translator.availability()
            if problem:
                text += f"<br><span style='color:{theme.WARNING}'>⚠ {problem}</span>"
        else:
            text = tr("Выключен — говорю ровно то, что вы пишете.")
        prof = c.active_profile()
        if prof is not None and (prof.translate or prof.target):
            text += "<br>" + tr("Сейчас действует профиль «{name}» — у него свои настройки перевода.", name=prof.name)
        self.status.setText(text)

    def _set(self, name: str, value) -> None:
        t = self.controller.config.translate
        if getattr(t, name) == value:
            return
        setattr(t, name, value)
        self.controller.edited("translate")
        if name in ("provider", "source", "target"):
            self._refresh_status()

    def _enabled_toggled(self, on: bool) -> None:
        self._set("enabled", on)
        self._refresh_status()

    def _swap(self) -> None:
        t = self.controller.config.translate
        if t.source == "auto":
            self.controller.notify.emit(tr("Сначала выберите язык, на котором пишете (не «Автоопределение»)."), "info")
            return
        t.source, t.target = t.target, t.source
        _select(self.source, t.source)
        _select(self.target, t.target)
        self.controller.edited("translate")
        self._refresh_status()

    def _favorites_changed(self) -> None:
        codes = [code for code, btn in self.fav_buttons.items() if btn.isChecked()]
        self._set("favorites", codes)

    # ------------------------------------------------------------ provider

    def _provider_changed(self) -> None:
        self._set("provider", self.provider.currentData())
        self._update_provider_ui()

    def _update_provider_ui(self) -> None:
        t = self.controller.config.translate
        prov = tl.PROVIDERS.get(t.provider, tl.PROVIDERS["google"])
        self.provider_row.subtitle.setText(tr(prov.description))
        self.provider_row.subtitle.setVisible(True)
        self.key_card.setVisible(bool(prov.key_field))
        if prov.key_field:
            self.key_title.setText(tr("Ключ {name}", name=tr(prov.title)))
            self.key_edit.blockSignals(True)
            self.key_edit.setText(getattr(self.controller.config.cloud, prov.key_field, ""))
            self.key_edit.blockSignals(False)
            if prov.key == "openai":
                self.key_edit.setToolTip(tr("Тот же ключ, что и у голосов OpenAI"))
            else:
                self.key_edit.setToolTip("")
        self.get_key.setVisible(bool(prov.signup_url) and bool(prov.key_field))
        self.model_row.setVisible(bool(prov.models))
        if prov.models:
            current = t.claude_model if prov.key == "claude" else t.openai_model
            self.model.blockSignals(True)
            self.model.clear()
            for model_id, label in prov.models:
                self.model.addItem(tr(label), model_id)
            idx = self.model.findData(current)
            self.model.setCurrentIndex(max(0, idx))
            self.model.blockSignals(False)
        styled = prov.ai or prov.key == "deepl"
        self.style_row.setVisible(styled)
        self.style_row.subtitle.setText(
            tr("ИИ-переводчик подстраивает под это тон и слова") if prov.ai else tr("DeepL меняет только вежливость обращения")
        )
        self.instructions_row.setVisible(prov.ai)
        self.email_row.setVisible(prov.key == "mymemory")

    def _key_changed(self) -> None:
        prov = tl.PROVIDERS.get(self.controller.config.translate.provider)
        if prov is None or not prov.key_field:
            return
        value = self.key_edit.text().strip()
        cloud = self.controller.config.cloud
        if getattr(cloud, prov.key_field) != value:
            setattr(cloud, prov.key_field, value)
            self.controller.edited("cloud")
            self._refresh_status()

    def _model_changed(self) -> None:
        prov = tl.PROVIDERS.get(self.controller.config.translate.provider)
        if prov is not None and prov.key in ("claude", "openai"):
            self._set(f"{prov.key}_model", self.model.currentData())

    def _open_signup(self) -> None:
        prov = tl.PROVIDERS.get(self.controller.config.translate.provider)
        if prov is not None and prov.signup_url:
            QDesktopServices.openUrl(QUrl(prov.signup_url))

    # ------------------------------------------------------------ voices per language

    def _rebuild_voice_rows(self) -> None:
        for row in self._voice_rows:
            row.deleteLater()
        self._voice_rows.clear()
        cfg = self.controller.config
        for item in cfg.translate.voices:
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(8)
            lang = _lang_combo()
            _select(lang, item.lang)
            lang.currentIndexChanged.connect(lambda _i, it=item, cb=lang: self._lang_voice_set(it, "lang", cb.currentData()))
            arrow = QLabel("→")
            arrow.setObjectName("muted")
            voice = QComboBox()
            for v in cfg.voices:
                voice.addItem(v.name, v.id)
            _select(voice, item.voice_id)
            voice.currentIndexChanged.connect(lambda _i, it=item, cb=voice: self._lang_voice_set(it, "voice_id", cb.currentData()))
            remove = icon_button("trash", tr("Удалить"))
            remove.clicked.connect(lambda _c=False, it=item: self._remove_lang_voice(it))
            rl.addWidget(lang, 1)
            rl.addWidget(arrow)
            rl.addWidget(voice, 1)
            rl.addWidget(remove)
            self.voices_list.addWidget(row)
            self._voice_rows.append(row)
        self.voices_hint.setVisible(not cfg.translate.voices)

    def _add_lang_voice(self) -> None:
        from kmuted.config import LanguageVoice

        cfg = self.controller.config
        used = {v.lang for v in cfg.translate.voices}
        lang = next((code for code in [cfg.translate.target, *tl.LANGUAGE_CODES] if code not in used), "en")
        cfg.translate.voices.append(LanguageVoice(lang=lang, voice_id=cfg.active_voice().id))
        self.controller.edited("translate")
        self._rebuild_voice_rows()

    def _lang_voice_set(self, item, name: str, value) -> None:
        setattr(item, name, value)
        self.controller.edited("translate")

    def _remove_lang_voice(self, item) -> None:
        voices = self.controller.config.translate.voices
        if item in voices:
            voices.remove(item)
            self.controller.edited("translate")
            self._rebuild_voice_rows()

    # ------------------------------------------------------------ test

    def _test_target(self) -> str:
        return self.controller.translation_target() or self.controller.config.translate.target

    def _test_translate(self) -> None:
        text = self.test_edit.text().strip()
        if not text:
            return
        target = self._test_target()
        self.test_result.setText(tr("Перевожу…"))
        self.test_result.setStyleSheet(f"color: {theme.MUTED};")

        def done(result: str, error: str) -> None:
            try:
                if error:
                    self.test_result.setText("⚠ " + error)
                    self.test_result.setStyleSheet(f"color: {theme.WARNING};")
                else:
                    self.test_result.setText(f"<b>{target.upper()}:</b> {_escape(result)}")
                    self.test_result.setStyleSheet(f"color: {theme.TEXT};")
            except RuntimeError:
                pass  # page closed meanwhile

        self.controller.translate_async(text, target, done)

    def _test_say(self) -> None:
        text = self.test_edit.text().strip()
        if not text:
            return
        if not self.controller.translation_target():
            self.controller.notify.emit(tr("Перевод выключен — фраза прозвучит как написана."), "info")
        self.controller.say(text)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
