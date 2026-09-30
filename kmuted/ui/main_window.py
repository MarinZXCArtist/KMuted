"""Main window: sidebar navigation, pages, quick-say bar, status bar."""

from __future__ import annotations

from PySide6.QtCore import QSize, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from kmuted import __version__
from kmuted.hotkeys.keys import format_combo
from kmuted.ui import theme
from kmuted.ui.icons import app_icon, render_logo
from kmuted.ui.page_audio import AudioPage
from kmuted.ui.page_phrases import PhrasesPage
from kmuted.ui.page_settings import SettingsPage
from kmuted.ui.page_voices import VoicesPage
from kmuted.ui.page_wheels import WheelsPage
from kmuted.ui.widgets import fill_voice_combo

PAGES = [
    ("💬", "Фразы"),
    ("🎡", "Колёса"),
    ("🗣", "Голоса"),
    ("🎧", "Звук"),
    ("⚙", "Настройки"),
]


class MainWindow(QMainWindow):
    def __init__(self, controller) -> None:
        super().__init__()
        self.controller = controller
        self.quitting = False
        self._tray_hint_shown = False
        self.setWindowTitle("KMuted")
        self.setWindowIcon(app_icon())
        self.resize(1240, 800)
        self.setMinimumSize(QSize(900, 600))

        # sidebar
        brand = QWidget()
        bl = QHBoxLayout(brand)
        bl.setContentsMargins(16, 16, 16, 8)
        logo = QLabel()
        logo.setPixmap(render_logo(36))
        name = QLabel(f"<b style='font-size:15pt'>KMuted</b><br><span style='color:{theme.MUTED}'>v{__version__}</span>")
        bl.addWidget(logo)
        bl.addWidget(name, 1)

        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        for icon, title in PAGES:
            self.nav.addItem(QListWidgetItem(f"{icon}   {title}"))
        self.nav.setFixedWidth(210)

        self.hotkey_hint = QLabel()
        self.hotkey_hint.setObjectName("hint")
        self.hotkey_hint.setWordWrap(True)
        self.hotkey_hint.setContentsMargins(16, 8, 16, 16)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(210)
        sidebar.setStyleSheet(
            f"QFrame#sidebar {{ background: {theme.SURFACE}; border-right: 1px solid {theme.BORDER}; }}"
            f"QFrame#sidebar QWidget {{ background: {theme.SURFACE}; }}"
        )
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)
        sl.addWidget(brand)
        sl.addWidget(self.nav, 1)
        sl.addWidget(self.hotkey_hint)

        # pages
        self.stack = QStackedWidget()
        self.pages = [
            PhrasesPage(controller),
            WheelsPage(controller),
            VoicesPage(controller),
            AudioPage(controller),
            SettingsPage(controller),
        ]
        for page in self.pages:
            self.stack.addWidget(page)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

        # quick say bar
        self.voice_combo = QComboBox()
        self.voice_combo.setMinimumWidth(180)
        self.voice_combo.setToolTip("Основной голос")
        self.voice_combo.currentIndexChanged.connect(self._voice_picked)
        self.quick = QLineEdit()
        self.quick.setPlaceholderText("Напишите и нажмите Enter — прозвучит в микрофоне")
        self.quick.returnPressed.connect(self._quick_say)
        say = QPushButton("Сказать")
        say.setObjectName("primary")
        say.clicked.connect(self._quick_say)
        stop = QPushButton("■ Стоп")
        stop.clicked.connect(controller.stop)
        bar = QFrame()
        bar.setObjectName("card")
        barl = QHBoxLayout(bar)
        barl.setContentsMargins(10, 8, 10, 8)
        barl.addWidget(self.voice_combo)
        barl.addWidget(self.quick, 1)
        barl.addWidget(say)
        barl.addWidget(stop)
        bar_holder = QWidget()
        bhl = QVBoxLayout(bar_holder)
        bhl.setContentsMargins(24, 4, 24, 12)
        bhl.addWidget(bar)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(self.stack, 1)
        rl.addWidget(bar_holder)

        central = QWidget()
        cl = QHBoxLayout(central)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(sidebar)
        cl.addWidget(right, 1)
        self.setCentralWidget(central)

        # status bar
        status = QStatusBar()
        self.status_label = QLabel("Готово")
        self.mic_label = QLabel()
        self.speaking_label = QLabel()
        status.addWidget(self.status_label, 1)
        status.addPermanentWidget(self.speaking_label)
        status.addPermanentWidget(self.mic_label)
        self.setStatusBar(status)
        self._error_timer = QTimer(self)
        self._error_timer.setSingleShot(True)
        self._error_timer.timeout.connect(lambda: self.status_label.setStyleSheet(""))

        controller.status.connect(self._on_status)
        controller.audio_status.connect(self.mic_label.setText)
        controller.error.connect(self._on_error)
        controller.speaking_changed.connect(self._on_speaking)
        controller.config_changed.connect(self._on_config_changed)
        controller.hotkeys_toggled.connect(lambda _e: self._update_hotkey_hint())
        self._refresh_voices()
        self._update_hotkey_hint()
        self.mic_label.setText(controller.audio_summary())

    # ------------------------------------------------------------ reactions

    def _on_status(self, text: str) -> None:
        self.status_label.setText(text)

    def _on_error(self, text: str) -> None:
        self.status_label.setText(f"⚠ {text}")
        self.status_label.setStyleSheet(f"color: {theme.DANGER};")
        self._error_timer.start(8000)

    def _on_speaking(self, speaking: bool) -> None:
        self.speaking_label.setText("🔴 В эфире" if speaking else "")
        self.speaking_label.setStyleSheet(f"color: {theme.ACCENT_2}; font-weight: 600;" if speaking else "")

    def _on_config_changed(self, section: str) -> None:
        if section in ("voices", "general"):
            self._refresh_voices()
        self._update_hotkey_hint()

    def _refresh_voices(self) -> None:
        cfg = self.controller.config
        fill_voice_combo(self.voice_combo, cfg.voices, cfg.active_voice().id, include_default=False)

    def _voice_picked(self) -> None:
        voice_id = self.voice_combo.currentData()
        if voice_id and voice_id != self.controller.config.general.active_voice_id:
            self.controller.set_active_voice(voice_id)

    def _quick_say(self) -> None:
        text = self.quick.text().strip()
        if text:
            self.controller.config.add_history(text)
            self.controller.edited("history")
            self.controller.say(text)
            self.quick.clear()

    def _update_hotkey_hint(self) -> None:
        g = self.controller.config.general
        lines = []
        if g.input_hotkey:
            lines.append(f"<b>{format_combo(g.input_hotkey)}</b> — написать")
        for w in self.controller.config.wheels[:3]:
            if w.hotkey:
                lines.append(f"<b>{format_combo(w.hotkey)}</b> — колесо «{w.name}»")
        if g.stop_hotkey:
            lines.append(f"<b>{format_combo(g.stop_hotkey)}</b> — стоп")
        if not g.hotkeys_enabled:
            lines.insert(0, f"<span style='color:{theme.WARNING}'>Горячие клавиши на паузе</span>")
        self.hotkey_hint.setText("<br>".join(lines))

    # ------------------------------------------------------------ window

    def closeEvent(self, event) -> None:  # noqa: N802
        if not self.quitting and self.controller.config.general.close_to_tray and self._has_tray():
            event.ignore()
            self.hide()
            if not self._tray_hint_shown:
                self._tray_hint_shown = True
                self.tray.showMessage("KMuted работает в трее", "Горячие клавиши активны. Выход — через меню значка.")
            return
        event.accept()

    def _has_tray(self) -> bool:
        return getattr(self, "tray", None) is not None and self.tray.isVisible()

    def show_and_raise(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()
