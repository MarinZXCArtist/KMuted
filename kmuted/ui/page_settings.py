"""General settings: hotkeys, wheel behaviour, app behaviour, RVC server."""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from kmuted import __version__, paths
from kmuted.config import WHEEL_HOLD, WHEEL_TOGGLE
from kmuted.ui import theme
from kmuted.ui.components import SectionTitle, SettingRow, ToggleSwitch, make_button, page_header
from kmuted.ui.widgets import HotkeyEdit, ValueSlider, run_in_background

_HOTKEYS = [
    ("input_hotkey", "Окно ввода текста", "Поле по центру экрана: пишете, Enter — звучит", "keyboard"),
    ("stop_hotkey", "Остановить речь", "Мгновенно обрывает озвучку и очищает очередь", "stop"),
    ("next_voice_hotkey", "Следующий голос", "Переключает основной голос по кругу", "voices"),
    ("toggle_hotkeys_hotkey", "Пауза горячих клавиш", "Включает и выключает все остальные клавиши", "power"),
]


class SettingsPage(QWidget):
    def __init__(self, controller) -> None:
        super().__init__()
        self.controller = controller
        self._loading = False

        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(28, 24, 28, 20)
        lay.setSpacing(8)
        lay.addWidget(page_header("Настройки", "Горячие клавиши, поведение окон и приложения."))

        # hotkeys
        lay.addWidget(SectionTitle("Горячие клавиши"))
        self.hotkeys_enabled = ToggleSwitch()
        self.hotkeys_enabled.toggled.connect(self._toggle_hotkeys)
        self.hook_row = SettingRow("Горячие клавиши включены", "", self.hotkeys_enabled, "zap")
        lay.addWidget(self.hook_row)
        self.hotkey_edits: dict[str, HotkeyEdit] = {}
        self.hotkey_rows: dict[str, SettingRow] = {}
        self._hotkey_tips: dict[str, str] = {}
        for attr, title, tip, icon_name in _HOTKEYS:
            edit = HotkeyEdit()
            edit.setFixedWidth(260)
            edit.changed.connect(lambda combo, a=attr: self._set_hotkey(a, combo))
            row = SettingRow(title, tip, edit, icon_name)
            lay.addWidget(row)
            self.hotkey_edits[attr] = edit
            self.hotkey_rows[attr] = row
            self._hotkey_tips[attr] = tip
        note = QLabel(
            "Клавиши не блокируются для игры — выбирайте сочетания, которые игра не использует "
            "(Alt+цифры, F-клавиши, боковые кнопки мыши). Если игра запущена от администратора, "
            "запустите KMuted тоже от администратора — иначе Windows не передаст ему нажатия."
        )
        note.setObjectName("hint")
        note.setWordWrap(True)
        note.setContentsMargins(6, 4, 6, 0)
        lay.addWidget(note)

        # wheel
        lay.addWidget(SectionTitle("Колесо фраз"))
        modes = QWidget()
        ml = QVBoxLayout(modes)
        ml.setContentsMargins(0, 0, 0, 0)
        self.wheel_hold = QRadioButton("Зажать → навести → отпустить")
        self.wheel_toggle = QRadioButton("Нажать → навести → нажать ещё раз")
        group = QButtonGroup(modes)
        group.addButton(self.wheel_hold)
        group.addButton(self.wheel_toggle)
        ml.addWidget(self.wheel_hold)
        ml.addWidget(self.wheel_toggle)
        self.wheel_hold.toggled.connect(lambda on: on and self._set("wheel_mode", WHEEL_HOLD))
        self.wheel_toggle.toggled.connect(lambda on: on and self._set("wheel_mode", WHEEL_TOGGLE))
        lay.addWidget(SettingRow("Как выбирать фразу", "Первый вариант быстрее в играх; во втором Esc — отмена", modes, "wheel"))
        self.deadzone = ValueSlider(10, 200, 40, lambda v: f"{v} px")
        self.deadzone.setFixedWidth(260)
        self.deadzone.valueChanged.connect(lambda v: self._set("wheel_deadzone", v))
        lay.addWidget(
            SettingRow("Мёртвая зона", "Насколько сдвинуть мышь для выбора. Отпустили в центре — отмена", self.deadzone, "mouse")
        )

        # input overlay
        lay.addWidget(SectionTitle("Окно ввода"))
        self.keep_open = ToggleSwitch()
        self.keep_open.toggled.connect(lambda v: self._set("input_keep_open", v))
        lay.addWidget(SettingRow("Не закрывать после отправки", "Удобно, когда пишете несколько фраз подряд", self.keep_open, "send"))
        self.restore_focus = ToggleSwitch()
        self.restore_focus.toggled.connect(lambda v: self._set("input_restore_focus", v))
        lay.addWidget(
            SettingRow(
                "Возвращать фокус в игру",
                "Окно и колесо видны поверх игр в режиме «Оконный» / «Без рамки»",
                self.restore_focus,
                "gamepad",
            )
        )

        # app
        lay.addWidget(SectionTitle("Приложение"))
        self.start_minimized = ToggleSwitch()
        self.start_minimized.toggled.connect(lambda v: self._set("start_minimized", v))
        lay.addWidget(SettingRow("Запускать свёрнутым в трей", "", self.start_minimized, "download"))
        self.close_to_tray = ToggleSwitch()
        self.close_to_tray.toggled.connect(lambda v: self._set("close_to_tray", v))
        lay.addWidget(
            SettingRow("Крестик сворачивает в трей", "KMuted продолжает работать и слушать горячие клавиши", self.close_to_tray, "x")
        )
        buttons = QWidget()
        bl = QHBoxLayout(buttons)
        bl.setContentsMargins(0, 0, 0, 0)
        folder = make_button("Папка настроек", "folder")
        folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths.data_dir()))))
        clear = make_button("Очистить кэш", "trash")
        clear.clicked.connect(self._clear_cache)
        bl.addWidget(folder)
        bl.addWidget(clear)
        lay.addWidget(SettingRow("Данные", "Настройки, кэш озвучки, голоса и свои картинки (папка assets)", buttons, "folder"))

        # rvc
        lay.addWidget(SectionTitle("RVC-сервер (свои голоса)"))
        rvc = QWidget()
        rl = QHBoxLayout(rvc)
        rl.setContentsMargins(0, 0, 0, 0)
        self.rvc_url = QLineEdit()
        self.rvc_url.setFixedWidth(230)
        self.rvc_url.editingFinished.connect(lambda: self._set("rvc_server_url", self.rvc_url.text().strip()))
        check = make_button("Проверить", "refresh")
        check.clicked.connect(self._check_rvc)
        rl.addWidget(self.rvc_url)
        rl.addWidget(check)
        self.rvc_row = SettingRow("Адрес сервера", "Запускается файлом start_rvc_server.bat", rvc, "wand")
        lay.addWidget(self.rvc_row)

        about = QLabel(
            f"KMuted {__version__} · говорите в войсе текстом · "
            "<a href='https://github.com/MarinZXCArtist/KMuted'>GitHub</a>"
        )
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

        controller.hotkeys_toggled.connect(self._on_hotkeys_toggled)
        controller.config_changed.connect(lambda s: s in ("phrases", "wheels") and self._update_warnings())
        self.load()

    # ------------------------------------------------------------ data

    def load(self) -> None:
        g = self.controller.config.general
        self._loading = True
        self.hotkeys_enabled.setChecked(g.hotkeys_enabled)
        for attr, edit in self.hotkey_edits.items():
            edit.set_combo(getattr(g, attr))
        self.wheel_hold.setChecked(g.wheel_mode == WHEEL_HOLD)
        self.wheel_toggle.setChecked(g.wheel_mode == WHEEL_TOGGLE)
        self.deadzone.setValue(g.wheel_deadzone)
        self.keep_open.setChecked(g.input_keep_open)
        self.restore_focus.setChecked(g.input_restore_focus)
        self.start_minimized.setChecked(g.start_minimized)
        self.close_to_tray.setChecked(g.close_to_tray)
        self.rvc_url.setText(g.rvc_server_url)
        self._loading = False
        self._update_warnings()
        error = self.controller.hotkeys_error()
        row = self.hook_row
        if error:
            row.subtitle.setText(f"<span style='color:{theme.DANGER}'>{error}</span>")
        elif self.controller.hotkeys.running:
            row.subtitle.setText(f"<span style='color:{theme.SUCCESS}'>● Перехват клавиш работает</span>")
        else:
            row.subtitle.setText("Перехват клавиш выключен (запуск с --no-hotkeys)")
        row.subtitle.setVisible(True)

    def _set(self, attr: str, value) -> None:
        if self._loading:
            return
        g = self.controller.config.general
        if getattr(g, attr) == value:
            return
        setattr(g, attr, value)
        self.controller.edited("general")

    def _set_hotkey(self, attr: str, combo: str) -> None:
        self._set(attr, combo)
        self._update_warnings()

    def _update_warnings(self) -> None:
        g = self.controller.config.general
        for attr, row in self.hotkey_rows.items():
            text = self.controller.hotkey_conflict(getattr(g, attr), f"general:{attr}")
            if text:
                row.subtitle.setText(f"<span style='color:{theme.WARNING}'>{text}</span>")
            else:
                row.subtitle.setText(self._hotkey_tips[attr])

    def _toggle_hotkeys(self, enabled: bool) -> None:
        if not self._loading and enabled != self.controller.config.general.hotkeys_enabled:
            self.controller.set_hotkeys_enabled(enabled)

    def _on_hotkeys_toggled(self, enabled: bool) -> None:
        self._loading = True
        self.hotkeys_enabled.setChecked(enabled)
        self._loading = False

    def _clear_cache(self) -> None:
        self.controller.speech.clear_cache()
        self.controller.notify.emit("Кэш озвучки очищен", "success")
        self.controller.prewarm()

    def _check_rvc(self) -> None:
        self._set("rvc_server_url", self.rvc_url.text().strip())
        self.rvc_row.subtitle.setText("Проверяю…")

        def done(models, error) -> None:
            if error is not None:
                self.rvc_row.subtitle.setText(f"<span style='color:{theme.DANGER}'>{error}</span>")
            else:
                self.rvc_row.subtitle.setText(
                    f"<span style='color:{theme.SUCCESS}'>● Сервер работает, моделей: {len(models)}</span>"
                )

        run_in_background(self.controller.speech.rvc.list_models, done)
