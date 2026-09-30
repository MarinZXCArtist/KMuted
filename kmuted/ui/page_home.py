"""Home: status at a glance, setup checklist, recent phrases, cheat sheet."""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QLinearGradient, QPainter, QPainterPath, QRadialGradient
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from kmuted import cable, winapi
from kmuted.ui import theme
from kmuted.ui.components import (
    IconBadge,
    Keycaps,
    StatusDot,
    ToggleSwitch,
    card,
    icon_button,
    make_button,
)
from kmuted.ui.icons import icon, icon_pixmap, load_asset_pixmap

ENGINE_NAMES = {"edge": "Edge · онлайн", "sapi": "Windows · офлайн", "piper": "Piper · офлайн"}


class Hero(QFrame):
    """Gradient banner (or the user's ``assets/banner.*`` picture)."""

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(190)
        self._banner = None
        self._banner_size = QSize()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        clip = QPainterPath()
        clip.addRoundedRect(r, 18, 18)
        p.setClipPath(clip)

        if self._banner_size != self.size():
            self._banner = load_asset_pixmap("banner", self.size())
            self._banner_size = self.size()
        if self._banner is not None:
            p.drawPixmap(0, 0, self._banner)
            shade = QLinearGradient(0, 0, self.width(), 0)
            shade.setColorAt(0, QColor(14, 15, 21, 235))
            shade.setColorAt(0.6, QColor(14, 15, 21, 150))
            shade.setColorAt(1, QColor(14, 15, 21, 60))
            p.fillRect(r, shade)
        else:
            base = QLinearGradient(0, 0, self.width(), self.height())
            base.setColorAt(0, QColor("#2a1d6b"))
            base.setColorAt(0.55, QColor("#1b2150"))
            base.setColorAt(1, QColor("#0f2a3a"))
            p.fillRect(r, base)
            for cx, cy, rad, color in (
                (0.85, 0.15, 0.55, theme.ACCENT),
                (0.62, 1.05, 0.45, theme.ACCENT_2),
                (1.02, 0.9, 0.35, theme.BLUE),
            ):
                glow = QRadialGradient(self.width() * cx, self.height() * cy, self.height() * rad * 1.6)
                c = QColor(color)
                c.setAlpha(110)
                glow.setColorAt(0, c)
                c.setAlpha(0)
                glow.setColorAt(1, c)
                p.fillRect(r, glow)
            # decorative sound waves on the right
            p.setPen(Qt.NoPen)
            bars = 22
            for i in range(bars):
                x = self.width() * 0.58 + i * 13
                h = (0.25 + 0.75 * abs(((i * 37) % 11) / 10 - 0.5) * 2) * self.height() * 0.42
                p.setBrush(QColor(255, 255, 255, 26 + (i % 3) * 8))
                p.drawRoundedRect(QRectF(x, self.height() * 0.5 - h / 2, 6, h), 3, 3)
        p.setClipping(False)
        p.setPen(QColor(255, 255, 255, 30))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, 18, 18)
        p.end()


class StatusTile(QFrame):
    def __init__(self, icon_name: str, title: str) -> None:
        super().__init__()
        self.setObjectName("cardHover")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(12)
        self.badge = IconBadge(icon_name, theme.ACCENT, 40)
        lay.addWidget(self.badge)
        col = QVBoxLayout()
        col.setSpacing(2)
        head = QHBoxLayout()
        head.setSpacing(6)
        t = QLabel(title)
        t.setObjectName("hint")
        self.dot = StatusDot()
        head.addWidget(t)
        head.addWidget(self.dot)
        head.addStretch(1)
        col.addLayout(head)
        self.value = QLabel("—")
        self.value.setObjectName("h3")
        self.value.setMinimumWidth(10)
        col.addWidget(self.value)
        self.detail = QLabel("")
        self.detail.setObjectName("hint")
        col.addWidget(self.detail)
        lay.addLayout(col, 1)
        self.side = QHBoxLayout()
        lay.addLayout(self.side)

    def set(self, value: str, detail: str, ok: bool, pulse: bool = False) -> None:
        fm = self.value.fontMetrics()
        self.value.setText(fm.elidedText(value, Qt.ElideRight, max(120, self.value.width())))
        self.value.setToolTip(value)
        self.detail.setText(detail)
        self.dot.set_state(theme.SUCCESS if ok else theme.WARNING, pulse=pulse)


class _Relay(QObject):
    progress = Signal(int, int)
    done = Signal(object, object)


class HomePage(QWidget):
    navigate = Signal(int)  # index of another page

    def __init__(self, controller) -> None:
        super().__init__()
        self.controller = controller
        self._downloading = False
        self._cancel = threading.Event()

        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(28, 24, 28, 20)
        lay.setSpacing(14)
        lay.addWidget(self._build_hero())
        lay.addLayout(self._build_tiles())
        self.setup_card = self._build_setup()
        lay.addWidget(self.setup_card)
        bottom = QHBoxLayout()
        bottom.setSpacing(14)
        bottom.addWidget(self._build_recent(), 3)
        bottom.addWidget(self._build_cheatsheet(), 2)
        lay.addLayout(bottom)
        lay.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        # coalesce bursts (e.g. dragging a slider fires many edits)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(150)
        self._refresh_timer.timeout.connect(self.refresh)
        controller.audio_status.connect(lambda _t: self._refresh_timer.start())
        controller.config_changed.connect(lambda _s: self._refresh_timer.start())
        controller.hotkeys_toggled.connect(lambda _e: self._refresh_timer.start())
        controller.speaking_changed.connect(self._on_speaking)
        self.refresh()

    # ------------------------------------------------------------ build

    def _build_hero(self) -> QWidget:
        hero = Hero()
        lay = QVBoxLayout(hero)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(6)
        eyebrow = QLabel("KMUTED · ГОЛОС ДЛЯ ТЕХ, КТО НЕ МОЖЕТ ГОВОРИТЬ")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("Говорите в войсе — текстом")
        title.setStyleSheet("font-size: 22pt; font-weight: 750; color: white;")
        sub = QLabel("Пишете фразу — друзья в Discord и в игре слышат её голосом. Быстрые фразы и колесо — в один клик.")
        sub.setWordWrap(True)
        sub.setStyleSheet("color: rgba(255,255,255,0.75); font-size: 10.5pt;")
        sub.setMaximumWidth(560)
        lay.addWidget(eyebrow)
        lay.addWidget(title)
        lay.addWidget(sub)
        lay.addStretch(1)
        row = QHBoxLayout()
        row.setSpacing(10)
        write = make_button("Написать фразу", "send", "primary")
        write.clicked.connect(self.controller.open_input)
        self.hero_keys = Keycaps()
        test = make_button("Проверить микрофон", "mic")
        test.clicked.connect(lambda: self.controller.say("Проверка связи. Меня хорошо слышно?"))
        row.addWidget(write)
        row.addWidget(self.hero_keys)
        row.addSpacing(8)
        row.addWidget(test)
        row.addStretch(1)
        lay.addLayout(row)
        return hero

    def _build_tiles(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setSpacing(14)
        self.tile_mic = StatusTile("mic", "Виртуальный микрофон")
        self.tile_voice = StatusTile("voices", "Голос по умолчанию")
        self.tile_keys = StatusTile("keyboard", "Горячие клавиши")
        self.keys_switch = ToggleSwitch()
        self.keys_switch.toggled.connect(self._toggle_hotkeys)
        self.tile_keys.side.addWidget(self.keys_switch, 0, Qt.AlignVCenter)
        voice_btn = icon_button("edit", "Выбрать голос")
        voice_btn.clicked.connect(lambda: self.navigate.emit(3))
        self.tile_voice.side.addWidget(voice_btn, 0, Qt.AlignVCenter)
        mic_btn = icon_button("settings", "Настроить звук")
        mic_btn.clicked.connect(lambda: self.navigate.emit(4))
        self.tile_mic.side.addWidget(mic_btn, 0, Qt.AlignVCenter)
        for i, tile in enumerate((self.tile_mic, self.tile_voice, self.tile_keys)):
            grid.addWidget(tile, 0, i)
        return grid

    def _build_setup(self) -> QFrame:
        box = card("warn")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(10)
        head = QHBoxLayout()
        pic = QLabel()
        pic.setPixmap(icon_pixmap("alert", theme.WARNING, 22))
        t = QLabel("Осталось подключить виртуальный микрофон")
        t.setObjectName("h2")
        head.addWidget(pic)
        head.addWidget(t, 1)
        lay.addLayout(head)
        text = QLabel(
            "Windows не даёт программам говорить в чужой микрофон напрямую, поэтому нужен бесплатный "
            "драйвер <b>VB-Audio Virtual Cable</b>. KMuted играет в <b>CABLE Input</b>, а Discord и игры "
            "слушают <b>CABLE Output</b> как обычный микрофон."
        )
        text.setWordWrap(True)
        text.setObjectName("muted")
        lay.addWidget(text)
        steps = QGridLayout()
        steps.setHorizontalSpacing(12)
        steps.setVerticalSpacing(8)
        self.step_labels = []
        for i, step in enumerate(
            (
                "Установите VB-Audio Virtual Cable (кнопка ниже скачает официальный установщик) и перезагрузите ПК",
                "KMuted сам выберет «CABLE Input» — проверьте кнопкой «Я установил»",
                "В Discord / игре: Настройки → Голос → Устройство ввода → «CABLE Output»",
            ),
            start=1,
        ):
            num = QLabel(str(i))
            num.setFixedSize(24, 24)
            num.setAlignment(Qt.AlignCenter)
            num.setStyleSheet(
                f"background: {theme.rgba(theme.WARNING, 0.18)}; color: {theme.WARNING};"
                "border-radius: 12px; font-weight: 700;"
            )
            lbl = QLabel(step)
            lbl.setWordWrap(True)
            steps.addWidget(num, i, 0, Qt.AlignTop)
            steps.addWidget(lbl, i, 1)
            self.step_labels.append(lbl)
        lay.addLayout(steps)
        self.cable_progress = QProgressBar()
        self.cable_progress.hide()
        lay.addWidget(self.cable_progress)
        row = QHBoxLayout()
        self.install_btn = make_button("Скачать и установить VB-Cable", "download", "primary")
        self.install_btn.clicked.connect(self._install_cable)
        check = make_button("Я установил — проверить", "refresh")
        check.clicked.connect(self._check_cable)
        site = make_button("Сайт VB-Audio", "link", "ghost")
        site.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(cable.CABLE_PAGE)))
        row.addWidget(self.install_btn)
        row.addWidget(check)
        row.addWidget(site)
        row.addStretch(1)
        lay.addLayout(row)
        return box

    def _build_recent(self) -> QFrame:
        box = card()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(6)
        head = QHBoxLayout()
        t = QLabel("Недавнее")
        t.setObjectName("h2")
        head.addWidget(t)
        head.addStretch(1)
        hint = QLabel("нажмите ▶, чтобы сказать снова")
        hint.setObjectName("hint")
        head.addWidget(hint)
        lay.addLayout(head)
        self.recent_box = QVBoxLayout()
        self.recent_box.setSpacing(2)
        lay.addLayout(self.recent_box)
        lay.addStretch(1)
        return box

    def _build_cheatsheet(self) -> QFrame:
        box = card()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(8)
        t = QLabel("Шпаргалка")
        t.setObjectName("h2")
        lay.addWidget(t)
        self.cheat_grid = QGridLayout()
        self.cheat_grid.setHorizontalSpacing(12)
        self.cheat_grid.setVerticalSpacing(8)
        lay.addLayout(self.cheat_grid)
        lay.addStretch(1)
        return box

    # ------------------------------------------------------------ data

    def refresh(self) -> None:
        c = self.controller
        cfg = c.config
        g = cfg.general
        if c.audio.mic_ready:
            self.tile_mic.set(c.audio.mic.device.name, "подключён · другие вас слышат", True)
        elif not c._audio_enabled:
            self.tile_mic.set("Звук отключён", "запуск с --no-audio", False)
        else:
            reason = c.audio.errors.get("mic", "не выбран")
            self.tile_mic.set("Не подключён", reason[:60], False)
        voice = cfg.active_voice()
        extra = " + RVC" if voice.rvc_enabled and voice.rvc_model else ""
        self.tile_voice.set(voice.name, ENGINE_NAMES.get(voice.engine, voice.engine) + extra, True)
        running = c.hotkeys.running
        if not running:
            self.tile_keys.set("Недоступны", c.hotkeys.error[:60] or "запуск с --no-hotkeys", False)
        else:
            self.tile_keys.set("Включены" if g.hotkeys_enabled else "На паузе", "работают поверх игр", g.hotkeys_enabled)
        self.keys_switch.blockSignals(True)
        self.keys_switch.setChecked(g.hotkeys_enabled)
        self.keys_switch.blockSignals(False)
        self.keys_switch.setEnabled(running)
        self.keys_switch.update()
        self.hero_keys.set_combo(g.input_hotkey)
        self.setup_card.setVisible(c._audio_enabled and not c.audio.mic_ready and not cfg.audio.mic_device)
        self._fill_recent()
        self._fill_cheatsheet()

    def _fill_recent(self) -> None:
        _clear_layout(self.recent_box)
        history = self.controller.config.history[:7]
        if not history:
            empty = QLabel("Здесь появятся фразы, которые вы писали в окне ввода.")
            empty.setObjectName("hint")
            empty.setWordWrap(True)
            self.recent_box.addWidget(empty)
            return
        for text in history:
            row = QFrame()
            row.setObjectName("cardHover")
            row.setStyleSheet("QFrame#cardHover { border-color: transparent; background: transparent; }"
                              f"QFrame#cardHover:hover {{ background: {theme.SURFACE_2}; }}")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(8, 4, 4, 4)
            lbl = QLabel(text)
            lbl.setToolTip(text)
            lbl.setMinimumWidth(10)
            lbl.setText(lbl.fontMetrics().elidedText(text, Qt.ElideRight, 420))
            play = icon_button("play", "Сказать снова", theme.ACCENT_2, 14)
            play.clicked.connect(lambda _c=False, t=text: self.controller.say(t))
            rl.addWidget(lbl, 1)
            rl.addWidget(play)
            self.recent_box.addWidget(row)

    def _fill_cheatsheet(self) -> None:
        _clear_layout(self.cheat_grid)
        cfg = self.controller.config
        g = cfg.general
        rows = [(g.input_hotkey, "Окно ввода")]
        rows += [(w.hotkey, f"Колесо «{w.name}» (зажать)") for w in cfg.wheels[:3]]
        rows += [(g.stop_hotkey, "Остановить речь")]
        if g.next_voice_hotkey:
            rows.append((g.next_voice_hotkey, "Следующий голос"))
        bound = sum(1 for p in cfg.phrases if p.hotkey)
        r = 0
        for combo, name in rows:
            if not combo:
                continue
            self.cheat_grid.addWidget(Keycaps(combo), r, 0, Qt.AlignLeft)
            lbl = QLabel(name)
            lbl.setObjectName("muted")
            self.cheat_grid.addWidget(lbl, r, 1)
            r += 1
        more = QLabel(f"+ быстрых фраз на клавишах: {bound}")
        more.setObjectName("hint")
        self.cheat_grid.addWidget(more, r, 0, 1, 2)

    # ------------------------------------------------------------ actions

    def _toggle_hotkeys(self, enabled: bool) -> None:
        if enabled != self.controller.config.general.hotkeys_enabled:
            self.controller.set_hotkeys_enabled(enabled)

    def _on_speaking(self, speaking: bool) -> None:
        if self.controller.audio.mic_ready:
            self.tile_mic.dot.set_state(theme.ACCENT_2 if speaking else theme.SUCCESS, pulse=speaking)

    def _check_cable(self) -> None:
        name = self.controller.detect_cable()
        if name:
            self.controller.notify.emit(f"Найден {name} — готово! Выберите «CABLE Output» микрофоном в Discord.", "success")
        else:
            self.controller.notify.emit("Кабель пока не найден. После установки драйвера нужна перезагрузка ПК.", "warning")
        self.refresh()

    def _install_cable(self) -> None:
        if self._downloading:
            self._cancel.set()
            return
        if not winapi.IS_WINDOWS:
            QDesktopServices.openUrl(QUrl(cable.CABLE_PAGE))
            return
        answer = QMessageBox.question(
            self,
            "VB-Audio Virtual Cable",
            "KMuted скачает официальный установщик с vb-audio.com и запустит его.\n"
            "Windows спросит разрешение (это драйвер). В установщике нажмите «Install Driver», "
            "затем перезагрузите компьютер.\n\nПродолжить?",
        )
        if answer != QMessageBox.Yes:
            return
        self._downloading = True
        self._cancel.clear()
        self.install_btn.setText("Отменить загрузку")
        self.cable_progress.setValue(0)
        self.cable_progress.show()
        relay = _Relay(self)
        relay.progress.connect(self._on_progress, Qt.QueuedConnection)
        relay.done.connect(self._on_downloaded, Qt.QueuedConnection)

        def work() -> None:
            try:
                relay.done.emit(cable.download_installer(relay.progress.emit, self._cancel.is_set), None)
            except Exception as exc:  # noqa: BLE001 - shown to the user
                relay.done.emit(None, exc)

        threading.Thread(target=work, daemon=True).start()

    def _on_progress(self, done: int, total: int) -> None:
        if total:
            self.cable_progress.setMaximum(100)
            self.cable_progress.setValue(int(done * 100 / total))
        else:
            self.cable_progress.setMaximum(0)

    def _on_downloaded(self, setup, error) -> None:
        self._downloading = False
        self.install_btn.setText("Скачать и установить VB-Cable")
        self.install_btn.setIcon(icon("download", "white", 16))
        self.cable_progress.hide()
        if error is not None:
            if not isinstance(error, InterruptedError):
                self.controller.notify.emit("Не удалось скачать — открываю сайт VB-Audio.", "warning")
                QDesktopServices.openUrl(QUrl(cable.CABLE_PAGE))
            return
        if cable.run_installer(setup):
            self.controller.notify.emit("Установщик запущен: «Install Driver», затем перезагрузка ПК.", "info")
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(setup.parent)))


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()
        elif item.layout() is not None:
            _clear_layout(item.layout())
