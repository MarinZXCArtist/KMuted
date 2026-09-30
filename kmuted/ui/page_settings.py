"""General settings: hotkeys, wheel behaviour, app behaviour, RVC server."""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from kmuted import __version__, paths
from kmuted.config import WHEEL_HOLD, WHEEL_TOGGLE
from kmuted.ui import theme
from kmuted.ui.widgets import HotkeyEdit, ValueSlider, page_header, run_in_background

_HOTKEYS = [
    ("input_hotkey", "Окно ввода текста", "Открывает поле по центру экрана: пишете — Enter — звучит."),
    ("stop_hotkey", "Остановить речь", "Мгновенно обрывает озвучку и очищает очередь."),
    ("next_voice_hotkey", "Следующий голос", "Переключает основной голос по кругу."),
    ("toggle_hotkeys_hotkey", "Пауза горячих клавиш", "Включает/выключает все остальные горячие клавиши."),
]


class SettingsPage(QWidget):
    def __init__(self, controller) -> None:
        super().__init__()
        self.controller = controller
        self._loading = False

        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.setSpacing(12)
        lay.addWidget(page_header("Настройки"))
        lay.addWidget(self._hotkeys_group())
        lay.addWidget(self._wheel_group())
        lay.addWidget(self._input_group())
        lay.addWidget(self._app_group())
        lay.addWidget(self._rvc_group())
        about = QLabel(
            f"KMuted {__version__} · говорите в войсе текстом · "
            "<a href='https://github.com/MarinZXCArtist/KMuted'>GitHub</a>"
        )
        about.setObjectName("hint")
        about.setOpenExternalLinks(True)
        lay.addWidget(about)
        lay.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        controller.hotkeys_toggled.connect(self._on_hotkeys_toggled)
        self.load()

    # ------------------------------------------------------------ groups

    def _hotkeys_group(self) -> QGroupBox:
        box = QGroupBox("Горячие клавиши")
        form = QFormLayout(box)
        form.setSpacing(8)
        self.hotkeys_enabled = QCheckBox("Горячие клавиши включены")
        self.hotkeys_enabled.toggled.connect(self._toggle_hotkeys)
        form.addRow(self.hotkeys_enabled)
        self.hotkey_edits: dict[str, HotkeyEdit] = {}
        self.hotkey_warnings: dict[str, QLabel] = {}
        for attr, title, tip in _HOTKEYS:
            edit = HotkeyEdit()
            edit.setToolTip(tip)
            edit.changed.connect(lambda combo, a=attr: self._set_hotkey(a, combo))
            warn = QLabel()
            warn.setStyleSheet(f"color: {theme.WARNING};")
            warn.hide()
            col = QVBoxLayout()
            col.setSpacing(2)
            col.addWidget(edit)
            col.addWidget(warn)
            form.addRow(title, col)
            self.hotkey_edits[attr] = edit
            self.hotkey_warnings[attr] = warn
        self.hook_status = QLabel()
        self.hook_status.setWordWrap(True)
        self.hook_status.setObjectName("hint")
        form.addRow(self.hook_status)
        note = QLabel(
            "Клавиши не блокируются для игры — выбирайте сочетания, которые игра не использует "
            "(например Alt+цифры или боковые кнопки мыши). Если игра запущена от администратора, "
            "запустите KMuted тоже от администратора, иначе Windows не передаст ему нажатия."
        )
        note.setObjectName("hint")
        note.setWordWrap(True)
        form.addRow(note)
        return box

    def _wheel_group(self) -> QGroupBox:
        box = QGroupBox("Колесо фраз")
        self.wheel_hold = QRadioButton("Зажать клавишу → навести → отпустить (быстро, для игр)")
        self.wheel_toggle = QRadioButton("Нажать → навести → нажать ещё раз (Esc — отмена)")
        group = QButtonGroup(box)
        group.addButton(self.wheel_hold)
        group.addButton(self.wheel_toggle)
        self.wheel_hold.toggled.connect(lambda on: on and self._set("wheel_mode", WHEEL_HOLD))
        self.wheel_toggle.toggled.connect(lambda on: on and self._set("wheel_mode", WHEEL_TOGGLE))
        self.deadzone = ValueSlider(10, 200, 40, lambda v: f"{v} px")
        self.deadzone.valueChanged.connect(lambda v: self._set("wheel_deadzone", v))
        form = QFormLayout(box)
        form.addRow(self.wheel_hold)
        form.addRow(self.wheel_toggle)
        form.addRow("Мёртвая зона", self.deadzone)
        hint = QLabel("Насколько сдвинуть мышь, чтобы выбрать фразу. Отпустили в центре — ничего не скажется.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        form.addRow(hint)
        return box

    def _input_group(self) -> QGroupBox:
        box = QGroupBox("Окно ввода")
        self.keep_open = QCheckBox("Не закрывать после отправки (для переписки подряд)")
        self.keep_open.toggled.connect(lambda v: self._set("input_keep_open", v))
        self.restore_focus = QCheckBox("Возвращать фокус в игру после закрытия")
        self.restore_focus.toggled.connect(lambda v: self._set("input_restore_focus", v))
        lay = QVBoxLayout(box)
        lay.addWidget(self.keep_open)
        lay.addWidget(self.restore_focus)
        hint = QLabel(
            "Окно ввода и колесо видны поверх игр в режиме «Оконный» или «Без рамки». "
            "В эксклюзивном полноэкранном режиме Windows не показывает чужие окна."
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        return box

    def _app_group(self) -> QGroupBox:
        box = QGroupBox("Приложение")
        self.start_minimized = QCheckBox("Запускать свёрнутым в трей")
        self.start_minimized.toggled.connect(lambda v: self._set("start_minimized", v))
        self.close_to_tray = QCheckBox("Крестик сворачивает в трей (KMuted продолжает работать)")
        self.close_to_tray.toggled.connect(lambda v: self._set("close_to_tray", v))
        folder = QPushButton("Открыть папку настроек")
        folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths.data_dir()))))
        clear = QPushButton("Очистить кэш озвучки")
        clear.clicked.connect(self._clear_cache)
        row = QHBoxLayout()
        row.addWidget(folder)
        row.addWidget(clear)
        row.addStretch(1)
        lay = QVBoxLayout(box)
        lay.addWidget(self.start_minimized)
        lay.addWidget(self.close_to_tray)
        lay.addLayout(row)
        return box

    def _rvc_group(self) -> QGroupBox:
        box = QGroupBox("RVC-сервер (свои голоса)")
        self.rvc_url = QLineEdit()
        self.rvc_url.editingFinished.connect(lambda: self._set("rvc_server_url", self.rvc_url.text().strip()))
        check = QPushButton("Проверить")
        check.clicked.connect(self._check_rvc)
        self.rvc_status = QLabel()
        self.rvc_status.setObjectName("hint")
        row = QHBoxLayout()
        row.addWidget(self.rvc_url, 1)
        row.addWidget(check)
        form = QFormLayout(box)
        form.addRow("Адрес", row)
        form.addRow("", self.rvc_status)
        return box

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
        if error:
            self.hook_status.setText(f"<span style='color:{theme.DANGER}'>{error}</span>")
        elif self.controller.hotkeys.running:
            self.hook_status.setText("🟢 Перехват клавиш работает")
        else:
            self.hook_status.setText("Перехват клавиш выключен (запуск с --no-hotkeys)")

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
        for attr, warn in self.hotkey_warnings.items():
            text = self.controller.hotkey_conflict(getattr(g, attr), f"general:{attr}")
            warn.setText(text)
            warn.setVisible(bool(text))

    def _toggle_hotkeys(self, enabled: bool) -> None:
        if not self._loading and enabled != self.controller.config.general.hotkeys_enabled:
            self.controller.set_hotkeys_enabled(enabled)

    def _on_hotkeys_toggled(self, enabled: bool) -> None:
        self._loading = True
        self.hotkeys_enabled.setChecked(enabled)
        self._loading = False

    def _clear_cache(self) -> None:
        self.controller.speech.clear_cache()
        self.controller.status.emit("Кэш озвучки очищен")
        self.controller.prewarm()

    def _check_rvc(self) -> None:
        self._set("rvc_server_url", self.rvc_url.text().strip())
        self.rvc_status.setText("Проверяю…")

        def done(models, error) -> None:
            if error is not None:
                self.rvc_status.setText(f"🔴 {error}")
            else:
                self.rvc_status.setText(f"🟢 Сервер работает, моделей: {len(models)}")

        run_in_background(self.controller.speech.rvc.list_models, done)
