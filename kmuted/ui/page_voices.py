"""Voice profiles: engine, voice, tuning, custom RVC models."""

from __future__ import annotations

import dataclasses
import shutil
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from kmuted import paths
from kmuted.config import ENGINE_EDGE, ENGINE_PIPER, ENGINE_SAPI, VoiceProfile, new_id
from kmuted.tts.base import VoiceInfo
from kmuted.ui import theme
from kmuted.ui.components import ToggleSwitch, icon_button, make_button
from kmuted.ui.icons import icon
from kmuted.ui.piper_dialog import PiperDownloadDialog
from kmuted.ui.widgets import InfoBox, ValueSlider, page_header, run_in_background

ALL_LANGS = "*"
_ENGINE_ICON = {"edge": "globe", "sapi": "windows", "piper": "cpu"}
RVC_METHODS = [
    ("rmvpe", "rmvpe — лучшее качество"),
    ("harvest", "harvest — медленно, мягко"),
    ("crepe", "crepe — точно, нужна видеокарта"),
    ("pm", "pm — быстро, грубо"),
]


def _signed(suffix: str):
    return lambda v: f"{v:+d}{suffix}" if v else f"0{suffix}"


class VoicesPage(QWidget):
    def __init__(self, controller) -> None:
        super().__init__()
        self.controller = controller
        self._loading = False
        self._voice_lists: dict[str, list[VoiceInfo]] = {}
        self._loading_engines: set[str] = set()

        # --- left: profiles ---
        self.list = QListWidget()
        self.list.setFixedWidth(230)
        self.list.currentRowChanged.connect(lambda _r: self._load_profile())
        add = make_button("Новый голос", "plus", "primary")
        add.clicked.connect(self.add_profile)
        dup = make_button("Копия", "copy")
        dup.clicked.connect(self.duplicate_profile)
        remove = make_button("Удалить", "trash", "danger")
        remove.clicked.connect(self.remove_profile)
        self.make_active = make_button("Сделать основным", "star")
        self.make_active.clicked.connect(self._make_active)
        row1 = QHBoxLayout()
        row1.addWidget(dup)
        row1.addWidget(remove)
        left = QVBoxLayout()
        left.addWidget(add)
        left.addWidget(self.list, 1)
        left.addWidget(self.make_active)
        left.addLayout(row1)

        # --- right: editor ---
        editor = QWidget()
        ed = QVBoxLayout(editor)
        ed.setContentsMargins(0, 0, 8, 0)
        ed.setSpacing(12)
        ed.addWidget(self._build_main_group())
        ed.addWidget(self._build_tuning_group())
        ed.addWidget(self._build_rvc_group())
        ed.addWidget(self._build_test_group())
        ed.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(editor)

        body = QHBoxLayout()
        body.setSpacing(16)
        body.addLayout(left)
        body.addWidget(scroll, 1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 12)
        lay.addWidget(
            page_header(
                "Голоса",
                "Создайте несколько голосов и переключайтесь между ними (Tab в окне ввода). "
                "★ — голос по умолчанию.",
            )
        )
        lay.addLayout(body, 1)
        controller.config_changed.connect(self._on_config_changed)
        self.refresh_list()

    def _on_config_changed(self, section: str) -> None:
        if section == "general":  # active voice may have changed elsewhere
            self.refresh_list()

    # ------------------------------------------------------------------ build

    def _build_main_group(self) -> QGroupBox:
        box = QGroupBox("Голос")
        self.name = QLineEdit()
        self.name.editingFinished.connect(self._name_changed)

        self.engine = QComboBox()
        for key, engine in self.controller.speech.engines.items():
            self.engine.addItem(engine.title, key)
        self.engine.currentIndexChanged.connect(self._engine_changed)
        self.engine_note = QLabel()
        self.engine_note.setObjectName("hint")
        self.engine_note.setWordWrap(True)

        self.lang = QComboBox()
        self.lang.setMinimumWidth(120)
        self.lang.currentIndexChanged.connect(self._fill_voice_combo)
        self.voice = QComboBox()
        self.voice.setMinimumWidth(260)
        self.voice.currentIndexChanged.connect(self._voice_changed)
        refresh = icon_button("refresh", "Обновить список голосов")
        refresh.clicked.connect(lambda: self._request_voices(self._profile_engine(), refresh=True))
        voice_row = QHBoxLayout()
        voice_row.addWidget(self.lang)
        voice_row.addWidget(self.voice, 1)
        voice_row.addWidget(refresh)

        self.piper_row = QWidget()
        pr = QHBoxLayout(self.piper_row)
        pr.setContentsMargins(0, 0, 0, 0)
        dl = make_button("Скачать голоса…", "download")
        dl.clicked.connect(self._open_piper_download)
        add_file = make_button("Своя модель .onnx…", "plus")
        add_file.clicked.connect(self._add_piper_file)
        folder = make_button("Папка", "folder")
        folder.clicked.connect(lambda: _open_folder(paths.piper_voices_dir()))
        pr.addWidget(dl)
        pr.addWidget(add_file)
        pr.addWidget(folder)
        pr.addStretch(1)

        self.speaker = QSpinBox()
        self.speaker.setRange(0, 999)
        self.speaker.valueChanged.connect(lambda v: self._set("speaker", v))
        self.speaker_label = QLabel("Номер диктора")

        form = QFormLayout(box)
        form.setSpacing(10)
        form.addRow("Название", self.name)
        form.addRow("Движок", self.engine)
        form.addRow("", self.engine_note)
        form.addRow("Голос", voice_row)
        form.addRow("", self.piper_row)
        form.addRow(self.speaker_label, self.speaker)
        return box

    def _build_tuning_group(self) -> QGroupBox:
        box = QGroupBox("Звучание")
        self.rate = ValueSlider(-50, 100, 0, _signed("%"))
        self.rate.valueChanged.connect(lambda v: self._set("rate", v))
        self.pitch = ValueSlider(-50, 50, 0, _signed(" Гц"))
        self.pitch.valueChanged.connect(lambda v: self._set("pitch", v))
        self.volume = ValueSlider(0, 200, 100, lambda v: f"{v}%")
        self.volume.valueChanged.connect(lambda v: self._set("volume", v))
        self.pitch_label = QLabel("Высота")
        form = QFormLayout(box)
        form.setSpacing(10)
        form.addRow("Скорость", self.rate)
        form.addRow(self.pitch_label, self.pitch)
        form.addRow("Громкость", self.volume)
        return box

    def _build_rvc_group(self) -> QGroupBox:
        box = QGroupBox("Свой голос через RVC (модели из войс-ченджеров)")
        self.rvc_enabled = ToggleSwitch()
        self.rvc_enabled.toggled.connect(self._rvc_toggled)
        rvc_row = QHBoxLayout()
        rvc_row.setSpacing(10)
        rvc_row.addWidget(self.rvc_enabled)
        rvc_row.addWidget(QLabel("Пропускать озвучку через RVC-модель"), 1)
        self.rvc_model = QComboBox()
        self.rvc_model.setEditable(True)
        self.rvc_model.setMinimumWidth(220)
        self.rvc_model.currentTextChanged.connect(lambda t: self._set("rvc_model", t.strip()))
        rvc_refresh = icon_button("refresh", "Спросить у RVC-сервера список моделей")
        rvc_refresh.clicked.connect(self._refresh_rvc_models)
        model_row = QHBoxLayout()
        model_row.addWidget(self.rvc_model, 1)
        model_row.addWidget(rvc_refresh)
        self.rvc_pitch = QSpinBox()
        self.rvc_pitch.setRange(-24, 24)
        self.rvc_pitch.setSuffix(" полутонов")
        self.rvc_pitch.setToolTip("Мужской голос → женская модель: +12. Женский → мужская: −12.")
        self.rvc_pitch.valueChanged.connect(lambda v: self._set("rvc_pitch", v))
        self.rvc_method = QComboBox()
        for key, title in RVC_METHODS:
            self.rvc_method.addItem(title, key)
        self.rvc_method.currentIndexChanged.connect(lambda _i: self._set("rvc_method", self.rvc_method.currentData()))
        self.rvc_status = QLabel("")
        self.rvc_status.setObjectName("hint")
        folder = make_button("Папка моделей", "folder")
        folder.clicked.connect(lambda: _open_folder(paths.rvc_models_dir()))
        status_row = QHBoxLayout()
        status_row.addWidget(self.rvc_status, 1)
        status_row.addWidget(folder)

        info = InfoBox(
            "RVC-модели (<b>.pth</b> + <b>.index</b>) — те же голоса, что используют AI войс-ченджеры. "
            "Положите каждую модель в отдельную папку внутри «Папки моделей» и запустите "
            "<b>start_rvc_server.bat</b> (нужна Python&nbsp;3.10, первая установка скачивает ~2&nbsp;ГБ). "
            "Цепочка: текст → выбранный выше голос → ваша RVC-модель → микрофон. "
            "Используйте только модели, на которые у вас есть права."
        )

        self.rvc_fields = [self.rvc_model, rvc_refresh, self.rvc_pitch, self.rvc_method]
        form = QFormLayout(box)
        form.setSpacing(10)
        form.addRow(rvc_row)
        form.addRow("Модель", model_row)
        form.addRow("Сдвиг тона", self.rvc_pitch)
        form.addRow("Метод", self.rvc_method)
        form.addRow(status_row)
        form.addRow(info)
        return box

    def _build_test_group(self) -> QGroupBox:
        box = QGroupBox("Проверка")
        self.test_text = QLineEdit("Привет! Это мой голос в KMuted.")
        listen = make_button("Прослушать", "headset")
        listen.setToolTip("Только в наушники — другие не услышат")
        listen.clicked.connect(self._preview)
        say = make_button("Сказать в микрофон", "mic", "primary")
        say.clicked.connect(self._say)
        row = QHBoxLayout()
        row.addWidget(self.test_text, 1)
        row.addWidget(listen)
        row.addWidget(say)
        lay = QVBoxLayout(box)
        lay.addLayout(row)
        return box

    # ------------------------------------------------------------------ list

    def _profile(self) -> VoiceProfile | None:
        row = self.list.currentRow()
        voices = self.controller.config.voices
        return voices[row] if 0 <= row < len(voices) else None

    def _profile_engine(self) -> str:
        p = self._profile()
        return p.engine if p else ENGINE_EDGE

    def refresh_list(self, select: int | None = None) -> None:
        cfg = self.controller.config
        current = self.list.currentRow() if select is None else select
        active = cfg.active_voice().id
        self.list.blockSignals(True)
        self.list.clear()
        for v in cfg.voices:
            engine = self.controller.speech.engines.get(v.engine)
            star = "★ " if v.id == active else ""
            rvc = " + RVC" if v.rvc_enabled and v.rvc_model else ""
            engine_title = engine.title.split(" (")[0] if engine else v.engine
            color = theme.ACCENT_2 if v.id == active else theme.MUTED
            item = QListWidgetItem(icon(_ENGINE_ICON.get(v.engine, "voices"), color, 18), f"{star}{v.name}\n{engine_title}{rvc}")
            self.list.addItem(item)
        self.list.blockSignals(False)
        if cfg.voices:
            self.list.setCurrentRow(max(0, min(current if current >= 0 else 0, len(cfg.voices) - 1)))
        self._load_profile()

    def _load_profile(self) -> None:
        p = self._profile()
        if p is None:
            return
        self._loading = True
        self.name.setText(p.name)
        self.engine.setCurrentIndex(max(0, self.engine.findData(p.engine)))
        self.rate.setValue(p.rate)
        self.pitch.setValue(p.pitch)
        self.volume.setValue(p.volume)
        self.speaker.setValue(p.speaker)
        self.rvc_enabled.setChecked(p.rvc_enabled)
        if self.rvc_model.findText(p.rvc_model) < 0 and p.rvc_model:
            self.rvc_model.addItem(p.rvc_model)
        self.rvc_model.setCurrentText(p.rvc_model)
        self.rvc_pitch.setValue(p.rvc_pitch)
        self.rvc_method.setCurrentIndex(max(0, self.rvc_method.findData(p.rvc_method)))
        self.make_active.setEnabled(p.id != self.controller.config.active_voice().id)
        self._loading = False
        self._update_engine_ui()
        self._request_voices(p.engine)

    def _update_engine_ui(self) -> None:
        p = self._profile()
        engine_key = p.engine if p else ENGINE_EDGE
        engine = self.controller.speech.engines.get(engine_key)
        reason = engine.availability() if engine else "нет движка"
        note = engine.description if engine else ""
        if reason:
            note = f"<span style='color:{theme.WARNING}'>⚠ {reason}</span>"
        self.engine_note.setText(note)
        is_piper = engine_key == ENGINE_PIPER
        self.piper_row.setVisible(is_piper)
        self.speaker.setVisible(is_piper)
        self.speaker_label.setVisible(is_piper)
        self.pitch.setEnabled(engine_key in (ENGINE_EDGE, ENGINE_SAPI))
        self.pitch_label.setEnabled(self.pitch.isEnabled())
        for w in self.rvc_fields:
            w.setEnabled(bool(p and p.rvc_enabled))

    # ------------------------------------------------------------------ voices

    def _request_voices(self, engine_key: str, refresh: bool = False) -> None:
        if engine_key in self._voice_lists and not refresh:
            self._fill_lang_combo()
            return
        if engine_key in self._loading_engines:
            return
        engine = self.controller.speech.engines.get(engine_key)
        if engine is None:
            return
        self._loading_engines.add(engine_key)
        self.voice.clear()
        self.voice.addItem("Загрузка списка голосов…", None)

        def done(result, error) -> None:
            self._loading_engines.discard(engine_key)
            self._voice_lists[engine_key] = result or []
            if error is not None:
                self.controller.error.emit(f"Не удалось получить список голосов: {error}")
            if self._profile_engine() == engine_key:
                self._fill_lang_combo()

        run_in_background(lambda: engine.list_voices(refresh=refresh), done)

    def _fill_lang_combo(self) -> None:
        p = self._profile()
        voices = self._voice_lists.get(self._profile_engine(), [])
        langs = sorted({v.language for v in voices if v.language}, key=lambda code: (not code.startswith("ru"), code))
        current = next((v.language for v in voices if p and v.id == p.voice), None)
        wanted = self.lang.currentData() if self.lang.count() else None
        self.lang.blockSignals(True)
        self.lang.clear()
        self.lang.addItem("Все языки", ALL_LANGS)
        for lang in langs:
            self.lang.addItem(lang, lang)
        target = current or wanted or ("ru-RU" if "ru-RU" in langs else ALL_LANGS)
        idx = self.lang.findData(target)
        self.lang.setCurrentIndex(idx if idx >= 0 else 0)
        self.lang.setVisible(len(langs) > 1)
        self.lang.blockSignals(False)
        self._fill_voice_combo()

    def _fill_voice_combo(self) -> None:
        p = self._profile()
        engine_key = self._profile_engine()
        voices = self._voice_lists.get(engine_key, [])
        lang = self.lang.currentData() or ALL_LANGS
        shown = [v for v in voices if lang == ALL_LANGS or v.language == lang]
        self.voice.blockSignals(True)
        self.voice.clear()
        if engine_key == ENGINE_SAPI:
            self.voice.addItem("Голос Windows по умолчанию", "")
        for v in shown:
            self.voice.addItem(v.label, v.id)
        if p and p.voice and self.voice.findData(p.voice) < 0:
            label = Path(p.voice).name if engine_key == ENGINE_PIPER else p.voice
            self.voice.addItem(f"{label} (текущий)", p.voice)
        if not self.voice.count():
            hint = "Нет голосов — скачайте или добавьте модель" if engine_key == ENGINE_PIPER else "Голоса не найдены"
            self.voice.addItem(hint, None)
        idx = self.voice.findData(p.voice) if p else -1
        self.voice.setCurrentIndex(max(0, idx))
        self.voice.blockSignals(False)
        # a fresh profile without a voice picks the first one available
        if p and not p.voice and engine_key != ENGINE_SAPI and self.voice.currentData():
            self._voice_changed()

    # ------------------------------------------------------------------ edits

    def _set(self, attr: str, value) -> None:
        p = self._profile()
        if p is None or self._loading or getattr(p, attr) == value:
            return
        setattr(p, attr, value)
        self.controller.edited("voices")

    def _name_changed(self) -> None:
        p = self._profile()
        if p is None or self._loading:
            return
        name = self.name.text().strip() or "Голос"
        if name != p.name:
            p.name = name
            self.controller.edited("voices")
            self.refresh_list()

    def _engine_changed(self) -> None:
        p = self._profile()
        key = self.engine.currentData()
        if p is None or self._loading or key == p.engine:
            return
        p.engine = key
        p.voice = ""
        self.controller.edited("voices")
        self.refresh_list()

    def _voice_changed(self) -> None:
        p = self._profile()
        data = self.voice.currentData()
        if p is None or self._loading or data is None:
            return
        if data != p.voice:
            p.voice = data
            self.controller.edited("voices")

    def _rvc_toggled(self, checked: bool) -> None:
        self._set("rvc_enabled", checked)
        self._update_engine_ui()
        if checked and self.rvc_model.count() == 0:
            self._refresh_rvc_models()
        if not self._loading:
            self.refresh_list()

    def _refresh_rvc_models(self) -> None:
        self.rvc_status.setText("Проверяю RVC-сервер…")

        def done(models, error) -> None:
            if error is not None:
                self.rvc_status.setText(f"🔴 {error}")
                return
            current = self.rvc_model.currentText()
            self.rvc_model.blockSignals(True)
            self.rvc_model.clear()
            self.rvc_model.addItems(models)
            self.rvc_model.setCurrentText(current)
            self.rvc_model.blockSignals(False)
            self.rvc_status.setText(f"🟢 Сервер работает, моделей: {len(models)}")

        run_in_background(self.controller.speech.rvc.list_models, done)

    # ------------------------------------------------------------------ actions

    def add_profile(self) -> None:
        voices = self.controller.config.voices
        voices.append(VoiceProfile(name=f"Голос {len(voices) + 1}"))
        self.controller.edited("voices")
        self.refresh_list(select=len(voices) - 1)
        self.name.setFocus()
        self.name.selectAll()

    def duplicate_profile(self) -> None:
        p = self._profile()
        if p is None:
            return
        copy = dataclasses.replace(p, id=new_id(), name=f"{p.name} (копия)")
        voices = self.controller.config.voices
        voices.insert(voices.index(p) + 1, copy)
        self.controller.edited("voices")
        self.refresh_list(select=voices.index(copy))

    def remove_profile(self) -> None:
        p = self._profile()
        voices = self.controller.config.voices
        if p is None:
            return
        if len(voices) == 1:
            QMessageBox.information(self, "KMuted", "Должен остаться хотя бы один голос.")
            return
        row = voices.index(p)
        voices.remove(p)
        if self.controller.config.general.active_voice_id == p.id:
            self.controller.config.general.active_voice_id = voices[0].id
        self.controller.edited("voices")
        self.refresh_list(select=max(0, row - 1))

    def _make_active(self) -> None:
        p = self._profile()
        if p is not None:
            self.controller.set_active_voice(p.id)
            self.refresh_list()

    def _preview(self) -> None:
        p = self._profile()
        if p is not None:
            self.controller.preview(self.test_text.text(), p)

    def _say(self) -> None:
        p = self._profile()
        if p is not None:
            self.controller.say(self.test_text.text(), p.id)

    def _open_piper_download(self) -> None:
        dlg = PiperDownloadDialog(self)
        dlg.downloaded.connect(self._piper_model_added)
        dlg.exec()

    def _add_piper_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Модель Piper", "", "Модель Piper (*.onnx)")
        if not path:
            return
        src = Path(path)
        cfg = Path(f"{src}.json")
        if not cfg.exists():
            QMessageBox.warning(self, "KMuted", f"Рядом с моделью нужен файл настроек {src.name}.json")
            return
        dest_dir = paths.piper_voices_dir()
        dest = dest_dir / src.name
        try:
            if src.resolve() != dest.resolve():
                shutil.copy2(src, dest)
                shutil.copy2(cfg, dest_dir / cfg.name)
        except OSError as exc:
            QMessageBox.warning(self, "KMuted", f"Не удалось скопировать модель: {exc}")
            return
        self._piper_model_added(str(dest))

    def _piper_model_added(self, path: str) -> None:
        p = self._profile()
        self._voice_lists.pop(ENGINE_PIPER, None)
        if p is not None and p.engine == ENGINE_PIPER:
            p.voice = path
            self.controller.edited("voices")
        self._request_voices(ENGINE_PIPER)


def _open_folder(path: Path) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
