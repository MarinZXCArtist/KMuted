"""Audio routing: virtual mic, headphones, live mic passthrough, push-to-talk."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from kmuted.audio import devices
from kmuted.config import PLAYBACK_INTERRUPT, PLAYBACK_QUEUE
from kmuted.ui import theme
from kmuted.ui.components import (
    LevelMeter,
    SectionTitle,
    SettingRow,
    ToggleSwitch,
    icon_button,
    make_button,
    page_header,
)
from kmuted.ui.widgets import HotkeyEdit, InfoBox, ValueSlider
from kmuted.i18n import tr

SETUP_HTML = (
    "<b>Как это работает.</b> KMuted играет озвучку в <i>виртуальный кабель</i>, а игра или Discord "
    "слушают этот кабель как микрофон.<br>"
    "1. Установите бесплатный <a href='https://vb-audio.com/Cable/'>VB-Audio Virtual Cable</a> "
    "(или кнопкой на «Главной») и перезагрузите ПК.<br>"
    "2. Ниже выберите <b>CABLE Input</b> (обычно выбирается сам).<br>"
    "3. В Discord / игре выберите микрофоном <b>CABLE Output</b>. В Discord лучше выключить "
    "шумоподавление и включить «Режим рации» или низкий порог активации."
)


def _pct(v: int) -> str:
    return f"{v}%"


def _width(widget: QWidget, w: int) -> QWidget:
    widget.setFixedWidth(w)
    return widget


class AudioPage(QWidget):
    def __init__(self, controller) -> None:
        super().__init__()
        self.controller = controller
        self._loading = False

        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(28, 24, 28, 20)
        lay.setSpacing(8)
        refresh = make_button(tr("Обновить устройства"), "refresh")
        refresh.clicked.connect(self._refresh_clicked)
        lay.addWidget(page_header(tr("Звук"), tr("Куда идёт озвучка и как её слышать самому."), refresh))
        lay.addWidget(InfoBox(tr(SETUP_HTML)))

        lay.addWidget(SectionTitle(tr("Уровни сейчас")))
        self.out_meter = LevelMeter()
        self.out_meter.setFixedWidth(330)
        lay.addWidget(SettingRow(tr("Что уходит в микрофон"), tr("Озвучка, звуки и живой микрофон — то, что слышат другие"), self.out_meter, "radio"))
        self.in_meter = LevelMeter()
        self.in_meter.setFixedWidth(330)
        self.in_row = SettingRow(tr("Ваш настоящий микрофон"), tr("Проверка: говорите — полоска должна двигаться"), self.in_meter, "mic")
        lay.addWidget(self.in_row)
        self.muted = ToggleSwitch()
        self.muted.toggled.connect(lambda v: self._set("mic_muted", v))
        lay.addWidget(SettingRow(tr("Заглушить KMuted в микрофоне"), tr("Озвучка и звуки звучат только у вас (живой микрофон остаётся)"), self.muted, "power"))

        lay.addWidget(SectionTitle(tr("Что слышат другие")))
        self.mic_device = QComboBox()
        self.mic_device.currentIndexChanged.connect(lambda _i: self._set("mic_device", self.mic_device.currentData() or ""))
        auto = icon_button("sparkles", tr("Найти виртуальный кабель автоматически"), theme.ACCENT_2)
        auto.clicked.connect(self._auto_detect)
        mic_ctrl = QWidget()
        mc = QHBoxLayout(mic_ctrl)
        mc.setContentsMargins(0, 0, 0, 0)
        mc.addWidget(_width(self.mic_device, 330))
        mc.addWidget(auto)
        self.mic_row = SettingRow(tr("Виртуальный микрофон"), "", mic_ctrl, "mic")
        lay.addWidget(self.mic_row)
        self.mic_volume = ValueSlider(0, 200, 100, _pct)
        self.mic_volume.valueChanged.connect(lambda v: self._set("mic_volume", v))
        lay.addWidget(SettingRow(tr("Громкость в микрофоне"), tr("Насколько громко вас слышат другие"), _width(self.mic_volume, 300), "volume"))
        test = make_button(tr("Проверить"), "play")
        test.clicked.connect(lambda: self.controller.say(tr("Проверка связи. Меня хорошо слышно?")))
        lay.addWidget(SettingRow(tr("Проверка"), tr("Скажет тестовую фразу в микрофон"), test, "zap"))

        lay.addWidget(SectionTitle(tr("Что слышите вы")))
        self.monitor_enabled = ToggleSwitch()
        self.monitor_enabled.toggled.connect(lambda v: self._set("monitor_enabled", v))
        self.monitor_row = SettingRow(tr("Прослушка в наушниках"), tr("Слышать то, что говорит KMuted"), self.monitor_enabled, "headset")
        lay.addWidget(self.monitor_row)
        self.monitor_device = QComboBox()
        self.monitor_device.currentIndexChanged.connect(
            lambda _i: self._set("monitor_device", self.monitor_device.currentData() or "")
        )
        lay.addWidget(SettingRow(tr("Наушники"), "", _width(self.monitor_device, 330), "audio"))
        self.monitor_volume = ValueSlider(0, 200, 60, _pct)
        self.monitor_volume.valueChanged.connect(lambda v: self._set("monitor_volume", v))
        lay.addWidget(SettingRow(tr("Громкость прослушки"), "", _width(self.monitor_volume, 300), "volume"))

        lay.addWidget(SectionTitle(tr("Поведение")))
        modes = QWidget()
        ml = QHBoxLayout(modes)
        ml.setContentsMargins(0, 0, 0, 0)
        self.mode_queue = QRadioButton(tr("Очередь"))
        self.mode_interrupt = QRadioButton(tr("Прервать"))
        group = QButtonGroup(modes)
        group.addButton(self.mode_queue)
        group.addButton(self.mode_interrupt)
        ml.addWidget(self.mode_queue)
        ml.addWidget(self.mode_interrupt)
        self.mode_queue.toggled.connect(lambda on: on and self._set("playback_mode", PLAYBACK_QUEUE))
        self.mode_interrupt.toggled.connect(lambda on: on and self._set("playback_mode", PLAYBACK_INTERRUPT))
        lay.addWidget(
            SettingRow(tr("Новая фраза, пока звучит старая"), tr("Дождаться конца или оборвать и сказать новую"), modes, "history")
        )

        self.ptt_key = HotkeyEdit(single_key=True)
        self.ptt_key.changed.connect(lambda v: self._set("ptt_key", v))
        lay.addWidget(
            SettingRow(
                tr("Кнопка рации в игре (push-to-talk)"),
                tr("Если в игре голос по кнопке (V, K…), KMuted сам зажмёт её, пока говорит. Пусто — активация голосом."),
                _width(self.ptt_key, 250),
                "gamepad",
            )
        )
        timing = QWidget()
        tl = QHBoxLayout(timing)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(8)
        self.ptt_delay = QSpinBox()
        self.ptt_delay.setRange(0, 2000)
        self.ptt_delay.setSingleStep(50)
        self.ptt_delay.setSuffix(tr(" мс"))
        self.ptt_delay.setPrefix(tr("до "))
        self.ptt_delay.valueChanged.connect(lambda v: self._set("ptt_delay_ms", v))
        self.ptt_tail = QSpinBox()
        self.ptt_tail.setRange(0, 3000)
        self.ptt_tail.setSingleStep(50)
        self.ptt_tail.setSuffix(tr(" мс"))
        self.ptt_tail.setPrefix(tr("после "))
        self.ptt_tail.valueChanged.connect(lambda v: self._set("ptt_tail_ms", v))
        tl.addWidget(self.ptt_delay)
        tl.addWidget(self.ptt_tail)
        lay.addWidget(SettingRow(tr("Задержки рации"), tr("Пауза перед речью и удержание кнопки после"), timing, "zap"))

        lay.addWidget(SectionTitle(tr("Живой микрофон")))
        self.pt_enabled = ToggleSwitch()
        self.pt_enabled.toggled.connect(lambda v: self._set("passthrough_enabled", v))
        self.pt_row = SettingRow(
            tr("Подмешивать мой настоящий микрофон"),
            tr("Если иногда говорите голосом: без этого ваш обычный микрофон никто не услышит."),
            self.pt_enabled,
            "radio",
        )
        lay.addWidget(self.pt_row)
        self.pt_device = QComboBox()
        self.pt_device.currentIndexChanged.connect(
            lambda _i: self._set("passthrough_device", self.pt_device.currentData() or "")
        )
        lay.addWidget(SettingRow(tr("Микрофон"), "", _width(self.pt_device, 330), "mic"))
        self.pt_volume = ValueSlider(0, 200, 100, _pct)
        self.pt_volume.valueChanged.connect(lambda v: self._set("passthrough_volume", v))
        lay.addWidget(SettingRow(tr("Громкость микрофона"), "", _width(self.pt_volume, 300), "volume"))
        lay.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        controller.audio_status.connect(lambda _t: self._update_status())
        self._meter_timer = QTimer(self)  # runs only while this page is visible
        self._meter_timer.setInterval(33)
        self._meter_timer.timeout.connect(self._tick_meters)
        self.reload_devices()

    # ------------------------------------------------------------ data

    def reload_devices(self) -> None:
        a = self.controller.config.audio
        self._loading = True
        try:
            outputs = devices.list_devices("output")
            inputs = devices.list_devices("input")
            error = ""
        except devices.AudioUnavailable as exc:
            outputs, inputs, error = [], [], str(exc)

        def fill(combo: QComboBox, items, current: str, default_label: str | None) -> None:
            combo.blockSignals(True)
            combo.clear()
            if default_label is not None:
                combo.addItem(default_label, "")
            for dev in items:
                mark = tr("  ✓ кабель") if devices.is_virtual_cable(dev.name) else ""
                combo.addItem(dev.name + mark, dev.name)
                combo.setItemData(combo.count() - 1, dev.name, Qt.ToolTipRole)
            if current and combo.findData(current) < 0:
                combo.addItem(tr("{name} (не найдено)", name=current), current)
            combo.setCurrentIndex(max(0, combo.findData(current)))
            combo.blockSignals(False)

        fill(self.mic_device, outputs, a.mic_device, tr("— не выбрано —"))
        fill(
            self.monitor_device,
            [d for d in outputs if not devices.is_virtual_cable(d.name)],
            a.monitor_device,
            tr("Системное устройство по умолчанию"),
        )
        fill(
            self.pt_device,
            [d for d in inputs if not devices.is_virtual_cable(d.name)],
            a.passthrough_device,
            tr("Системный микрофон по умолчанию"),
        )

        self.mic_volume.setValue(a.mic_volume)
        self.muted.setChecked(a.mic_muted)
        self.monitor_enabled.setChecked(a.monitor_enabled)
        self.monitor_volume.setValue(a.monitor_volume)
        self.mode_queue.setChecked(a.playback_mode == PLAYBACK_QUEUE)
        self.mode_interrupt.setChecked(a.playback_mode == PLAYBACK_INTERRUPT)
        self.ptt_key.set_combo(a.ptt_key)
        self.ptt_delay.setValue(a.ptt_delay_ms)
        self.ptt_tail.setValue(a.ptt_tail_ms)
        self.pt_enabled.setChecked(a.passthrough_enabled)
        self.pt_volume.setValue(a.passthrough_volume)
        self._loading = False
        if error:
            self._status(self.mic_row, error, theme.DANGER)
        else:
            self._update_status()

    def _refresh_clicked(self) -> None:
        self.controller.refresh_audio()
        self.reload_devices()
        self.controller.notify.emit(tr("Список устройств обновлён"), "info")

    def _auto_detect(self) -> None:
        name = self.controller.detect_cable()
        self.reload_devices()
        if name:
            idx = self.mic_device.findData(name)
            if idx >= 0:
                self.mic_device.setCurrentIndex(idx)
            self.controller.notify.emit(tr("Выбран {name}", name=name), "success")
        else:
            self.controller.notify.emit(
                tr("Виртуальный кабель не найден. Установите VB-Audio Virtual Cable (кнопка на «Главной») и перезагрузите ПК."),
                "warning",
            )

    # ------------------------------------------------------------ meters

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self.controller._audio_enabled:
            error = self.controller.audio.start_meter()
            if error:
                self.in_row.subtitle.setText(f"<span style='color:{theme.WARNING}'>{error}</span>")
        self._meter_timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        self._meter_timer.stop()
        self.controller.audio.stop_meter()
        super().hideEvent(event)

    def _tick_meters(self) -> None:
        audio = self.controller.audio
        self.out_meter.push(audio.output_level)
        self.in_meter.push(audio.input_level)

    def _set(self, attr: str, value) -> None:
        if self._loading:
            return
        a = self.controller.config.audio
        if getattr(a, attr) == value:
            return
        setattr(a, attr, value)
        self.controller.edited("audio")
        self._update_status()

    @staticmethod
    def _status(row: SettingRow, text: str, color: str | None = None) -> None:
        row.subtitle.setText(f"<span style='color:{color}'>{text}</span>" if color else text)
        row.subtitle.setVisible(bool(text))

    def _update_status(self) -> None:
        engine = self.controller.audio
        a = self.controller.config.audio
        if engine.mic_ready:
            dev = engine.mic.device
            text = tr("Работает · {api}, {rate} Гц", api=dev.hostapi, rate=engine.mic.mixer.sample_rate)
            if devices.is_virtual_cable(dev.name):
                self._status(self.mic_row, "● " + text, theme.SUCCESS)
            else:
                self._status(
                    self.mic_row,
                    tr("Это не виртуальный кабель — другие люди вас не услышат, звук пойдёт в это устройство."),
                    theme.WARNING,
                )
        else:
            reason = engine.errors.get("mic") or tr("не выбрано")
            self._status(self.mic_row, reason, theme.WARNING)
        mon_err = engine.errors.get("monitor", "")
        if mon_err:
            self._status(self.monitor_row, mon_err, theme.WARNING)
        elif engine.monitor and engine.monitor.device:
            self._status(self.monitor_row, f"● {engine.monitor.device.name}", theme.SUCCESS)
        else:
            self._status(self.monitor_row, tr("Слышать то, что говорит KMuted") if not a.monitor_enabled else "")
        pt_err = engine.errors.get("passthrough", "")
        if pt_err:
            self._status(self.pt_row, pt_err, theme.WARNING)
        elif engine.passthrough:
            self._status(self.pt_row, tr("● Микрофон подключён"), theme.SUCCESS)
        else:
            self._status(self.pt_row, tr("Если иногда говорите голосом: без этого ваш обычный микрофон никто не услышит."))
