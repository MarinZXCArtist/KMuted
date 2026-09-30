"""Main window: sidebar, animated page switching, composer bar, toasts."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from kmuted import __version__, winapi
from kmuted.i18n import tr
from kmuted.ui import theme
from kmuted.ui.components import Equalizer, FadeStack, NavBar, StatusDot, ToastHost, make_button
from kmuted.ui.icons import app_icon, icon, render_logo
from kmuted.ui.page_audio import AudioPage
from kmuted.ui.page_home import HomePage
from kmuted.ui.page_hotkeys import HotkeysPage
from kmuted.ui.page_phrases import PhrasesPage
from kmuted.ui.page_settings import SettingsPage
from kmuted.ui.page_sounds import SoundsPage
from kmuted.ui.page_voices import VoicesPage
from kmuted.ui.page_wheels import WheelsPage
from kmuted.ui.update_service import UpdateService
from kmuted.ui.widgets import fill_voice_combo

PAGES = [
    ("home", "Главная", HomePage),
    ("phrases", "Фразы", PhrasesPage),
    ("wheel", "Колёса", WheelsPage),
    ("volume", "Звуки", SoundsPage),
    ("voices", "Голоса", VoicesPage),
    ("audio", "Звук", AudioPage),
    ("keyboard", "Горячие клавиши", HotkeysPage),
    ("settings", "Настройки", SettingsPage),
]
PAGE_VOICES = 4
PAGE_AUDIO = 5
PAGE_SETTINGS = 7

_ENGINE_ICON = {"edge": "globe", "sapi": "windows", "piper": "cpu"}  # cloud voices: sparkles


class MainWindow(QMainWindow):
    def __init__(self, controller) -> None:
        super().__init__()
        self.controller = controller
        self.quitting = False
        self.tray = None
        self.setWindowTitle("KMuted")
        self.setWindowIcon(app_icon())
        self.resize(1300, 840)
        self.setMinimumSize(QSize(1000, 660))

        self.updates = UpdateService(controller)
        controller.updates = self.updates
        self.updates.available.connect(self._on_update_available)

        self.toasts = ToastHost(self)
        sidebar = self._build_sidebar()

        # Pages are built the first time they are opened: faster start, less RAM.
        self.stack = FadeStack()
        self._pages: list[QWidget | None] = [None] * len(PAGES)
        for _ in PAGES:
            self.stack.addWidget(QWidget())  # placeholders
        self.nav.currentChanged.connect(self._open_page)
        self.nav.set_current(0, animate=False)
        self._open_page(0)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(self.stack, 1)
        rl.addWidget(self._build_composer())

        central = QWidget()
        central.setObjectName("central")
        central.setStyleSheet(f"QWidget#central {{ background: {theme.BG}; }}")
        cl = QHBoxLayout(central)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(sidebar)
        cl.addWidget(right, 1)
        self.setCentralWidget(central)

        controller.status.connect(self._on_status)
        controller.audio_status.connect(self._on_audio_status)
        controller.error.connect(self._on_error)
        controller.notify.connect(self._on_notify)
        controller.speaking_changed.connect(self._on_speaking)
        controller.config_changed.connect(self._on_config_changed)
        controller.hotkeys_toggled.connect(self._on_hotkeys_toggled)
        self._refresh_voices()
        self._refresh_status_card()

    # ------------------------------------------------------------ building

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(240)
        sidebar.setStyleSheet(f"QFrame#sidebar {{ background: {theme.BG_2}; border-right: 1px solid {theme.BORDER}; }}")
        brand = QHBoxLayout()
        brand.setContentsMargins(20, 20, 16, 12)
        brand.setSpacing(12)
        logo = QLabel()
        logo.setPixmap(render_logo(40))
        name = QLabel(
            "<span style='font-size:15pt; font-weight:750'>KMuted</span><br>"
            f"<span style='color:{theme.MUTED}; font-size:8.5pt'>{tr('голос из текста')} · v{__version__}</span>"
        )
        brand.addWidget(logo)
        brand.addWidget(name, 1)

        self.nav = NavBar([(icon_name, tr(title)) for icon_name, title, _cls in PAGES])

        status = QFrame()
        status.setObjectName("card")
        sl = QVBoxLayout(status)
        sl.setContentsMargins(14, 12, 14, 12)
        sl.setSpacing(8)
        air = QHBoxLayout()
        self.eq = Equalizer()
        self.air_label = QLabel(tr("Тишина"))
        self.air_label.setObjectName("h3")
        air.addWidget(self.eq)
        air.addWidget(self.air_label, 1)
        sl.addLayout(air)
        self.mic_dot, self.mic_label = self._status_line(sl)
        self.keys_dot, self.keys_label = self._status_line(sl)

        lay = QVBoxLayout(sidebar)
        lay.setContentsMargins(0, 0, 0, 14)
        lay.setSpacing(6)
        lay.addLayout(brand)
        lay.addWidget(self.nav)
        lay.addStretch(1)
        holder = QHBoxLayout()
        holder.setContentsMargins(12, 0, 12, 0)
        holder.addWidget(status)
        lay.addLayout(holder)
        return sidebar

    @staticmethod
    def _status_line(layout: QVBoxLayout) -> tuple[StatusDot, QLabel]:
        row = QHBoxLayout()
        row.setSpacing(8)
        dot = StatusDot()
        label = QLabel()
        label.setObjectName("hint")
        row.addWidget(dot)
        row.addWidget(label, 1)
        layout.addLayout(row)
        return dot, label

    def _build_composer(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("card")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(10, 8, 8, 8)
        bl.setSpacing(8)
        self.voice_combo = QComboBox()
        self.voice_combo.setMinimumWidth(190)
        self.voice_combo.setToolTip(tr("Голос по умолчанию"))
        self.voice_combo.currentIndexChanged.connect(self._voice_picked)
        self.quick = QLineEdit()
        self.quick.setPlaceholderText(tr("Напишите что-нибудь и нажмите Enter — прозвучит в микрофоне…  ({время}, {дата} тоже работают)"))
        self.quick.setClearButtonEnabled(True)
        self.quick.returnPressed.connect(self._quick_say)
        self.quick.addAction(icon("send", theme.FAINT, 16), QLineEdit.LeadingPosition)
        say = make_button(tr("Сказать"), "send", "primary")
        say.clicked.connect(self._quick_say)
        repeat = make_button("", "history", tooltip=tr("Повторить последнюю фразу"))
        repeat.clicked.connect(self.controller.repeat_last)
        stop = make_button("", "stop", tooltip=tr("Остановить всё"))
        stop.clicked.connect(self.controller.stop)
        bl.addWidget(self.voice_combo)
        bl.addWidget(self.quick, 1)
        bl.addWidget(say)
        bl.addWidget(repeat)
        bl.addWidget(stop)

        self.status_line = QLabel(tr("Готово"))
        self.status_line.setObjectName("hint")
        self.status_line.setContentsMargins(6, 0, 0, 0)

        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(28, 2, 28, 14)
        hl.setSpacing(6)
        hl.addWidget(self.status_line)
        hl.addWidget(bar)
        return holder

    # ------------------------------------------------------------ pages

    def page(self, index: int) -> QWidget:
        """The page widget at ``index``, created on first use."""
        page = self._pages[index]
        if page is None:
            page = PAGES[index][2](self.controller)
            if isinstance(page, HomePage):
                page.navigate.connect(self.go_to)
            placeholder = self.stack.widget(index)
            self.stack.insertWidget(index, page)
            self.stack.removeWidget(placeholder)
            placeholder.deleteLater()
            self._pages[index] = page
        return page

    def _open_page(self, index: int) -> None:
        self.page(index)
        if self.stack.currentIndex() != index:
            self.stack.fade_to(index)

    def go_to(self, index: int) -> None:
        self.nav.set_current(index)

    # ------------------------------------------------------------ reactions

    def _on_status(self, text: str) -> None:
        self.status_line.setText(text)

    def _on_audio_status(self, _text: str) -> None:
        self._refresh_status_card()

    def _on_error(self, text: str) -> None:
        self.toasts.show(text, "error")

    def _on_notify(self, text: str, kind: str) -> None:
        if self.isVisible():
            self.toasts.show(text, kind)
        elif self.tray is not None and kind in ("warning", "success"):
            self.tray.showMessage("KMuted", text)

    def _on_hotkeys_toggled(self, _enabled: bool) -> None:
        self._refresh_status_card()

    def _on_speaking(self, speaking: bool) -> None:
        self.eq.set_active(speaking)
        self.air_label.setText(tr("В эфире") if speaking else tr("Тишина"))
        self.air_label.setStyleSheet(f"color: {theme.ACCENT_2};" if speaking else "")
        self._refresh_status_card(speaking)

    def _on_update_available(self, release) -> None:
        self.nav.buttons[PAGE_SETTINGS].badge = "1"
        self.nav.buttons[PAGE_SETTINGS].update()

    def _refresh_status_card(self, speaking: bool = False) -> None:
        c = self.controller
        if c.audio.mic_ready:
            name = c.audio.mic.device.name
            muted = c.config.audio.mic_muted
            color = theme.WARNING if muted else (theme.ACCENT_2 if speaking else theme.SUCCESS)
            self.mic_dot.set_state(color, pulse=speaking and not muted)
            label = tr("Микрофон заглушён") if muted else name
            self.mic_label.setText(self.mic_label.fontMetrics().elidedText(label, Qt.ElideRight, 165))
            self.mic_label.setToolTip(name)
            self.nav.buttons[PAGE_AUDIO].badge = ""
        else:
            self.mic_dot.set_state(theme.WARNING)
            self.mic_label.setText(tr("Нет микрофона"))
            self.mic_label.setToolTip(c.audio_summary())
            self.nav.buttons[PAGE_AUDIO].badge = "!" if c._audio_enabled else ""
        self.nav.buttons[PAGE_AUDIO].update()
        enabled = c.config.general.hotkeys_enabled and c.hotkeys.running
        self.keys_dot.set_state(theme.SUCCESS if enabled else theme.WARNING)
        self.keys_label.setText(tr("Клавиши активны") if enabled else tr("Клавиши выключены"))

    def _on_config_changed(self, section: str) -> None:
        if section in ("voices", "general"):
            self._refresh_voices()
        if section in ("general", "audio"):
            self._refresh_status_card()

    def _refresh_voices(self) -> None:
        cfg = self.controller.config
        fill_voice_combo(self.voice_combo, cfg.voices, cfg.active_voice().id, include_default=False)
        for i in range(self.voice_combo.count()):
            voice = cfg.voice_by_id(self.voice_combo.itemData(i))
            if voice is not None:
                self.voice_combo.setItemIcon(i, icon(_ENGINE_ICON.get(voice.engine, "sparkles"), theme.MUTED, 16))

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

    # ------------------------------------------------------------ window

    def start_update_check(self) -> None:
        self.updates.schedule_startup_check()

    def toggle_visible(self) -> None:
        if self.isVisible() and not self.isMinimized() and self.isActiveWindow():
            self.close()  # goes to the tray when enabled
        else:
            self.show_and_raise()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        winapi.style_window(int(self.winId()), theme.BG_2, theme.BORDER)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.toasts._relayout()

    def closeEvent(self, event) -> None:  # noqa: N802
        g = self.controller.config.general
        if not self.quitting and g.close_to_tray and self._has_tray():
            event.ignore()
            self.hide()
            if not g.tray_hint_shown:
                g.tray_hint_shown = True
                self.controller.edited("tray")
                self.tray.showMessage(tr("KMuted работает в трее"), tr("Горячие клавиши активны. Выход — через меню значка."))
            QTimer.singleShot(1500, lambda: None if self.isVisible() else winapi.trim_memory())
            return
        event.accept()
        if not self.quitting:  # closing without a tray means "quit"
            self.quitting = True
            QApplication.quit()

    def _has_tray(self) -> bool:
        return self.tray is not None and self.tray.isVisible()

    def show_and_raise(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()
