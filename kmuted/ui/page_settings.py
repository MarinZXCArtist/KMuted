"""General settings: language, look, overlays, app behaviour, packs, updates."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from kmuted import __version__, autostart, paths, presets, updater
from kmuted.config import WHEEL_HOLD, WHEEL_TOGGLE
from kmuted.i18n import LANGUAGES, language, tr
from kmuted.ui import theme
from kmuted.ui.components import SectionTitle, SettingRow, ToggleSwitch, make_button, page_header
from kmuted.ui.widgets import ValueSlider, run_in_background

_PART_NAMES = {"phrases": "Фразы", "wheels": "Колёса", "sounds": "Звуки", "voices": "Голоса"}


def _swatch(color: str) -> QPixmap:
    pm = QPixmap(16, 16)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(1, 1, 14, 14)
    p.end()
    return pm


class PackDialog(QDialog):
    """Choose what to export / import."""

    def __init__(self, title: str, counts: dict[str, int] | None, importing: bool, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(10)
        head = QLabel(title)
        head.setObjectName("h2")
        lay.addWidget(head)
        self.checks: dict[str, QCheckBox] = {}
        for part in presets.PARTS:
            n = counts.get(part, 0) if counts is not None else None
            label = tr(_PART_NAMES[part]) + (f"  ({n})" if n is not None else "")
            box = QCheckBox(label)
            box.setChecked(part != "voices" and (n is None or n > 0))
            box.setEnabled(n is None or n > 0)
            lay.addWidget(box)
            self.checks[part] = box
        self.replace = QCheckBox(tr("Заменить мои фразы/колёса/звуки (иначе — добавить к ним)"))
        self.replace.setVisible(importing)
        lay.addWidget(self.replace)
        if importing:
            note = QLabel(tr("Горячие клавиши, которые у вас уже заняты, при импорте снимаются."))
            note.setObjectName("hint")
            note.setWordWrap(True)
            lay.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok = buttons.button(QDialogButtonBox.Ok)
        ok.setText(tr("Импортировать") if importing else tr("Сохранить набор"))
        ok.setObjectName("primary")
        buttons.button(QDialogButtonBox.Cancel).setText(tr("Отмена"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def parts(self) -> set[str]:
        return {p for p, box in self.checks.items() if box.isChecked() and box.isEnabled()}


class SettingsPage(QWidget):
    def __init__(self, controller) -> None:
        super().__init__()
        self.controller = controller
        self._loading = False

        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(28, 24, 28, 20)
        lay.setSpacing(8)
        lay.addWidget(page_header(tr("Настройки"), tr("Язык, внешний вид, окна поверх игр, обновления и наборы.")))

        # --- look -------------------------------------------------------------
        lay.addWidget(SectionTitle(tr("Внешний вид")))
        self.lang = QComboBox()
        self.lang.addItem(tr("Автоматически"), "")
        for code, name in LANGUAGES.items():
            self.lang.addItem(name, code)
        self.lang.setFixedWidth(220)
        self.lang.currentIndexChanged.connect(self._language_changed)
        lay.addWidget(SettingRow(tr("Язык интерфейса"), "Русский / English — " + tr("применится после перезапуска"), self.lang, "globe"))
        self.accent = QComboBox()
        for key, (color, *_rest) in theme.ACCENTS.items():
            self.accent.addItem(_swatch(color), tr(theme.ACCENT_NAMES[key]), key)
        self.accent.setFixedWidth(220)
        self.accent.currentIndexChanged.connect(self._accent_changed)
        lay.addWidget(SettingRow(tr("Цвет акцента"), tr("Кнопки, подсветка, колесо"), self.accent, "sparkles"))

        # --- overlays -----------------------------------------------------------
        lay.addWidget(SectionTitle(tr("Окна поверх игры")))
        self.position = QComboBox()
        for key, name in (("top", "Сверху"), ("center", "По центру"), ("bottom", "Снизу")):
            self.position.addItem(tr(name), key)
        self.position.setFixedWidth(220)
        self.position.currentIndexChanged.connect(lambda _i: self._set("input_position", self.position.currentData()))
        lay.addWidget(SettingRow(tr("Где появляется окно ввода"), tr("Выберите место, где оно не мешает игре"), self.position, "keyboard"))
        self.keep_open = ToggleSwitch()
        self.keep_open.toggled.connect(lambda v: self._set("input_keep_open", v))
        lay.addWidget(SettingRow(tr("Не закрывать после отправки"), tr("Удобно, когда пишете несколько фраз подряд"), self.keep_open, "send"))
        self.restore_focus = ToggleSwitch()
        self.restore_focus.toggled.connect(lambda v: self._set("input_restore_focus", v))
        lay.addWidget(
            SettingRow(tr("Возвращать фокус в игру"), tr("Окна видны поверх игр в режиме «Оконный» / «Без рамки»"), self.restore_focus, "gamepad")
        )
        modes = QWidget()
        ml = QVBoxLayout(modes)
        ml.setContentsMargins(0, 0, 0, 0)
        self.wheel_hold = QRadioButton(tr("Зажать → навести → отпустить"))
        self.wheel_toggle = QRadioButton(tr("Нажать → навести → нажать ещё раз"))
        group = QButtonGroup(modes)
        group.addButton(self.wheel_hold)
        group.addButton(self.wheel_toggle)
        ml.addWidget(self.wheel_hold)
        ml.addWidget(self.wheel_toggle)
        self.wheel_hold.toggled.connect(lambda on: on and self._set("wheel_mode", WHEEL_HOLD))
        self.wheel_toggle.toggled.connect(lambda on: on and self._set("wheel_mode", WHEEL_TOGGLE))
        lay.addWidget(SettingRow(tr("Колесо: как выбирать"), tr("Первый вариант быстрее в играх; во втором Esc — отмена"), modes, "wheel"))
        self.wheel_scale = ValueSlider(60, 150, 100, lambda v: f"{v}%")
        self.wheel_scale.setFixedWidth(260)
        self.wheel_scale.valueChanged.connect(lambda v: self._set("wheel_scale", v))
        lay.addWidget(SettingRow(tr("Колесо: размер"), "", self.wheel_scale, "wheel"))
        self.deadzone = ValueSlider(10, 200, 40, lambda v: f"{v} px")
        self.deadzone.setFixedWidth(260)
        self.deadzone.valueChanged.connect(lambda v: self._set("wheel_deadzone", v))
        lay.addWidget(SettingRow(tr("Колесо: мёртвая зона"), tr("Насколько сдвинуть мышь для выбора. Отпустили в центре — отмена"), self.deadzone, "mouse"))

        # --- app ------------------------------------------------------------------
        lay.addWidget(SectionTitle(tr("Приложение")))
        self.autostart = ToggleSwitch()
        self.autostart.toggled.connect(self._autostart_changed)
        lay.addWidget(SettingRow(tr("Запускать вместе с Windows"), tr("KMuted стартует свёрнутым в трей"), self.autostart, "power"))
        self.start_minimized = ToggleSwitch()
        self.start_minimized.toggled.connect(lambda v: self._set("start_minimized", v))
        lay.addWidget(SettingRow(tr("Запускать свёрнутым в трей"), "", self.start_minimized, "download"))
        self.close_to_tray = ToggleSwitch()
        self.close_to_tray.toggled.connect(lambda v: self._set("close_to_tray", v))
        lay.addWidget(SettingRow(tr("Крестик сворачивает в трей"), tr("KMuted продолжает работать и слушать горячие клавиши"), self.close_to_tray, "x"))

        # --- updates ----------------------------------------------------------------
        lay.addWidget(SectionTitle(tr("Обновления")))
        self.check_updates = ToggleSwitch()
        self.check_updates.toggled.connect(lambda v: self._set("check_updates", v))
        lay.addWidget(SettingRow(tr("Проверять обновления автоматически"), tr("Раз в день, через GitHub Releases"), self.check_updates, "refresh"))
        upd = QWidget()
        ul = QHBoxLayout(upd)
        ul.setContentsMargins(0, 0, 0, 0)
        self.check_btn = make_button(tr("Проверить"), "refresh")
        self.install_btn = make_button(tr("Обновить"), "download", "primary")
        self.install_btn.hide()
        self.skip_btn = make_button(tr("Пропустить"), "x", "ghost")
        self.skip_btn.hide()
        ul.addWidget(self.check_btn)
        ul.addWidget(self.skip_btn)
        ul.addWidget(self.install_btn)
        self.update_row = SettingRow(tr("Версия {v}", v=__version__), tr("Нажмите «Проверить»"), upd, "sparkles")
        lay.addWidget(self.update_row)
        self.update_progress = QProgressBar()
        self.update_progress.hide()
        lay.addWidget(self.update_progress)

        # --- packs --------------------------------------------------------------------
        lay.addWidget(SectionTitle(tr("Наборы")))
        packs = QWidget()
        pl = QHBoxLayout(packs)
        pl.setContentsMargins(0, 0, 0, 0)
        export = make_button(tr("Экспорт…"), "download")
        export.clicked.connect(self._export)
        imp = make_button(tr("Импорт…"), "folder")
        imp.clicked.connect(self._import)
        pl.addWidget(export)
        pl.addWidget(imp)
        lay.addWidget(
            SettingRow(tr("Поделиться с друзьями"), tr("Фразы, колёса, звуки и голоса в одном файле .kmuted"), packs, "copy")
        )

        # --- data -----------------------------------------------------------------------
        lay.addWidget(SectionTitle(tr("Данные")))
        buttons = QWidget()
        bl = QHBoxLayout(buttons)
        bl.setContentsMargins(0, 0, 0, 0)
        folder = make_button(tr("Папка настроек"), "folder")
        folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths.data_dir()))))
        clear = make_button(tr("Очистить кэш"), "trash")
        clear.clicked.connect(self._clear_cache)
        bl.addWidget(folder)
        bl.addWidget(clear)
        lay.addWidget(SettingRow(tr("Файлы KMuted"), tr("Настройки, кэш озвучки, звуки, голоса и свои картинки (папка assets)"), buttons, "folder"))
        rvc = QWidget()
        rl = QHBoxLayout(rvc)
        rl.setContentsMargins(0, 0, 0, 0)
        self.rvc_url = QLineEdit()
        self.rvc_url.setFixedWidth(230)
        self.rvc_url.editingFinished.connect(lambda: self._set("rvc_server_url", self.rvc_url.text().strip()))
        check = make_button(tr("Проверить"), "refresh")
        check.clicked.connect(self._check_rvc)
        rl.addWidget(self.rvc_url)
        rl.addWidget(check)
        self.rvc_row = SettingRow(tr("RVC-сервер (свои голоса)"), tr("Запускается файлом start_rvc_server.bat"), rvc, "wand")
        lay.addWidget(self.rvc_row)

        about = QLabel(f"KMuted {__version__} · <a href='https://github.com/{updater.REPO}'>GitHub</a>")
        about.setObjectName("hint")
        about.setOpenExternalLinks(True)
        about.setContentsMargins(6, 14, 0, 0)
        lay.addWidget(about)
        lay.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        updates = getattr(controller, "updates", None)
        if updates is not None:
            self.check_btn.clicked.connect(lambda: updates.check(manual=True))
            self.install_btn.clicked.connect(updates.install)
            self.skip_btn.clicked.connect(self._skip_update)
            updates.state_changed.connect(self._on_update_state)
            updates.available.connect(self._on_update_available)
            updates.progress.connect(self._on_update_progress)
            if updates.release is not None:
                self._on_update_available(updates.release)
        self.load()

    # ------------------------------------------------------------ data

    def load(self) -> None:
        g = self.controller.config.general
        self._loading = True
        self.lang.setCurrentIndex(max(0, self.lang.findData(g.language)))
        self.accent.setCurrentIndex(max(0, self.accent.findData(g.accent)))
        self.position.setCurrentIndex(max(0, self.position.findData(g.input_position)))
        self.keep_open.setChecked(g.input_keep_open)
        self.restore_focus.setChecked(g.input_restore_focus)
        self.wheel_hold.setChecked(g.wheel_mode == WHEEL_HOLD)
        self.wheel_toggle.setChecked(g.wheel_mode == WHEEL_TOGGLE)
        self.wheel_scale.setValue(g.wheel_scale)
        self.deadzone.setValue(g.wheel_deadzone)
        self.autostart.setChecked(autostart.is_enabled())
        self.autostart.setEnabled(sys.platform == "win32")
        self.start_minimized.setChecked(g.start_minimized)
        self.close_to_tray.setChecked(g.close_to_tray)
        self.check_updates.setChecked(g.check_updates)
        self.rvc_url.setText(g.rvc_server_url)
        self._loading = False

    def _set(self, attr: str, value) -> None:
        if self._loading:
            return
        g = self.controller.config.general
        if getattr(g, attr) == value:
            return
        setattr(g, attr, value)
        self.controller.edited("general")

    def _ask_restart(self) -> None:
        answer = QMessageBox.question(
            self,
            "KMuted",
            tr("Чтобы применить, KMuted перезапустится (пара секунд). Перезапустить сейчас?"),
        )
        if answer == QMessageBox.Yes:
            self.controller.request_restart()

    def _language_changed(self) -> None:
        if self._loading:
            return
        code = self.lang.currentData()
        self.controller.config.general.language = code
        self.controller.save_now()
        from kmuted import i18n

        if i18n.resolve(code) != language():
            self._ask_restart()

    def _accent_changed(self) -> None:
        if self._loading:
            return
        self.controller.config.general.accent = self.accent.currentData()
        self.controller.save_now()
        self._ask_restart()

    def _autostart_changed(self, enabled: bool) -> None:
        if self._loading:
            return
        if not autostart.set_enabled(enabled):
            self.controller.error.emit(tr("Не удалось изменить автозапуск"))

    # ------------------------------------------------------------ updates

    def _on_update_state(self, text: str) -> None:
        self.update_row.subtitle.setText(text)
        self.update_row.subtitle.show()
        if not self.controller.updates.busy:
            self.update_progress.hide()

    def _on_update_available(self, release) -> None:
        self.update_row.subtitle.setText(
            f"<span style='color:{theme.ACCENT_2}'>{tr('Доступна версия {v}', v=release.version)}</span>"
        )
        self.install_btn.setText(tr("Обновить до {v}", v=release.version) if updater.can_self_update() else tr("Открыть страницу загрузки"))
        self.install_btn.show()
        self.skip_btn.show()

    def _on_update_progress(self, value: int) -> None:
        self.update_progress.show()
        if value < 0:
            self.update_progress.setMaximum(0)
        else:
            self.update_progress.setMaximum(100)
            self.update_progress.setValue(value)

    def _skip_update(self) -> None:
        self.controller.updates.skip()
        self.install_btn.hide()
        self.skip_btn.hide()
        self.update_row.subtitle.setText(tr("Эта версия пропущена"))

    # ------------------------------------------------------------ packs

    def _export(self) -> None:
        dlg = PackDialog(tr("Экспорт набора"), None, importing=False, parent=self)
        if dlg.exec() != QDialog.Accepted or not dlg.parts():
            return
        path, _ = QFileDialog.getSaveFileName(self, tr("Сохранить набор"), "KMuted-pack.kmuted", "KMuted (*.kmuted)")
        if not path:
            return
        try:
            info = presets.export_pack(self.controller.config, path, dlg.parts())
        except (OSError, presets.PackError) as exc:
            self.controller.error.emit(tr("Не удалось сохранить набор: {error}", error=exc))
            return
        summary = ", ".join(f"{tr(_PART_NAMES[p])}: {n}" for p, n in info.counts.items() if n)
        self.controller.notify.emit(tr("Набор сохранён ({summary})", summary=summary), "success")

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("Открыть набор"), "", "KMuted (*.kmuted)")
        if not path:
            return
        try:
            info = presets.read_pack(path)
        except (OSError, presets.PackError) as exc:
            self.controller.error.emit(str(exc))
            return
        title = tr("Импорт «{name}»", name=info.name) if info.name else tr("Импорт набора")
        dlg = PackDialog(title, info.counts, importing=True, parent=self)
        if dlg.exec() != QDialog.Accepted or not dlg.parts():
            return
        try:
            stats = presets.import_pack(self.controller.config, path, dlg.parts(), dlg.replace.isChecked())
        except (OSError, presets.PackError) as exc:
            self.controller.error.emit(str(exc))
            return
        for section in ("voices", "sounds", "phrases", "wheels"):
            self.controller.edited(section)
        summary = ", ".join(f"{tr(_PART_NAMES[p])}: {stats[p]}" for p in presets.PARTS if stats.get(p))
        self.controller.notify.emit(tr("Импортировано: {summary}", summary=summary or "0"), "success")
        if stats.get("hotkeys_dropped"):
            self.controller.notify.emit(tr("Снято занятых горячих клавиш: {n}", n=stats["hotkeys_dropped"]), "warning")

    # ------------------------------------------------------------ misc

    def _clear_cache(self) -> None:
        self.controller.speech.clear_cache()
        self.controller.sounds.clear()
        self.controller.notify.emit(tr("Кэш озвучки очищен"), "success")
        self.controller.prewarm()

    def _check_rvc(self) -> None:
        self._set("rvc_server_url", self.rvc_url.text().strip())
        self.rvc_row.subtitle.setText(tr("Проверяю…"))

        def done(models, error) -> None:
            if error is not None:
                self.rvc_row.subtitle.setText(f"<span style='color:{theme.DANGER}'>{error}</span>")
            else:
                self.rvc_row.subtitle.setText(
                    f"<span style='color:{theme.SUCCESS}'>● {tr('Сервер работает, моделей: {n}', n=len(models))}</span>"
                )

        run_in_background(self.controller.speech.rvc.list_models, done)
