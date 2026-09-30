"""Audio routing: virtual mic, headphones, live mic passthrough, push-to-talk."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from kmuted.audio import devices
from kmuted.config import PLAYBACK_INTERRUPT, PLAYBACK_QUEUE
from kmuted.ui import theme
from kmuted.ui.widgets import HotkeyEdit, InfoBox, ValueSlider, page_header

SETUP_HTML = (
    "<b>Как это работает.</b> KMuted проигрывает озвучку в <i>виртуальный кабель</i>, "
    "а игра или Discord слушают этот кабель как микрофон — так же, как Soundpad.<br>"
    "1. Установите бесплатный <a href='https://vb-audio.com/Cable/'>VB-Audio Virtual Cable</a> "
    "и перезагрузите ПК.<br>"
    "2. Ниже в «Виртуальный микрофон» выберите <b>CABLE Input</b>.<br>"
    "3. В Discord / игре выберите микрофоном <b>CABLE Output</b>. "
    "В Discord лучше выключить шумоподавление и включить «Режим рации» или низкий порог активации."
)


def _pct(v: int) -> str:
    return f"{v}%"


class AudioPage(QWidget):
    def __init__(self, controller) -> None:
        super().__init__()
        self.controller = controller
        self._loading = False

        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(24, 20, 24, 16)
        lay.setSpacing(12)
        lay.addWidget(page_header("Звук", "Куда выводить озвучку и как её слышать самому."))
        lay.addWidget(InfoBox(SETUP_HTML))
        lay.addWidget(self._mic_group())
        lay.addWidget(self._monitor_group())
        lay.addWidget(self._playback_group())
        lay.addWidget(self._ptt_group())
        lay.addWidget(self._passthrough_group())
        lay.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        controller.audio_status.connect(lambda _t: self._update_status())
        self.reload_devices()

    # ------------------------------------------------------------ groups

    def _mic_group(self) -> QGroupBox:
        box = QGroupBox("Виртуальный микрофон (что слышат другие)")
        self.mic_device = QComboBox()
        self.mic_device.setMinimumWidth(320)
        self.mic_device.currentIndexChanged.connect(lambda _i: self._set("mic_device", self.mic_device.currentData() or ""))
        refresh = QToolButton()
        refresh.setText("⟳")
        refresh.setToolTip("Обновить список устройств")
        refresh.clicked.connect(self.reload_devices)
        auto = QPushButton("Найти кабель")
        auto.clicked.connect(self._auto_detect)
        row = QHBoxLayout()
        row.addWidget(self.mic_device, 1)
        row.addWidget(refresh)
        row.addWidget(auto)
        self.mic_status = QLabel()
        self.mic_status.setWordWrap(True)
        self.mic_volume = ValueSlider(0, 200, 100, _pct)
        self.mic_volume.valueChanged.connect(lambda v: self._set("mic_volume", v))
        test = QPushButton("🎙 Проверить микрофон")
        test.clicked.connect(lambda: self.controller.say("Проверка связи. Меня хорошо слышно?"))
        form = QFormLayout(box)
        form.setSpacing(10)
        form.addRow("Устройство", row)
        form.addRow("", self.mic_status)
        form.addRow("Громкость", self.mic_volume)
        form.addRow("", test)
        return box

    def _monitor_group(self) -> QGroupBox:
        box = QGroupBox("Прослушка (что слышите вы)")
        self.monitor_enabled = QCheckBox("Слышать озвучку в своих наушниках")
        self.monitor_enabled.toggled.connect(lambda v: self._set("monitor_enabled", v))
        self.monitor_device = QComboBox()
        self.monitor_device.currentIndexChanged.connect(
            lambda _i: self._set("monitor_device", self.monitor_device.currentData() or "")
        )
        self.monitor_volume = ValueSlider(0, 200, 60, _pct)
        self.monitor_volume.valueChanged.connect(lambda v: self._set("monitor_volume", v))
        self.monitor_status = QLabel()
        self.monitor_status.setObjectName("hint")
        form = QFormLayout(box)
        form.setSpacing(10)
        form.addRow(self.monitor_enabled)
        form.addRow("Наушники", self.monitor_device)
        form.addRow("Громкость", self.monitor_volume)
        form.addRow("", self.monitor_status)
        return box

    def _playback_group(self) -> QGroupBox:
        box = QGroupBox("Если фраза звучит, а вы запускаете новую")
        self.mode_queue = QRadioButton("Дождаться конца (очередь)")
        self.mode_interrupt = QRadioButton("Прервать и сказать новую")
        group = QButtonGroup(box)
        group.addButton(self.mode_queue)
        group.addButton(self.mode_interrupt)
        self.mode_queue.toggled.connect(
            lambda on: on and self._set("playback_mode", PLAYBACK_QUEUE)
        )
        self.mode_interrupt.toggled.connect(
            lambda on: on and self._set("playback_mode", PLAYBACK_INTERRUPT)
        )
        lay = QVBoxLayout(box)
        lay.addWidget(self.mode_queue)
        lay.addWidget(self.mode_interrupt)
        return box

    def _ptt_group(self) -> QGroupBox:
        box = QGroupBox("Push-to-talk в игре")
        self.ptt_key = HotkeyEdit(single_key=True)
        self.ptt_key.changed.connect(lambda v: self._set("ptt_key", v))
        self.ptt_delay = QSpinBox()
        self.ptt_delay.setRange(0, 2000)
        self.ptt_delay.setSingleStep(50)
        self.ptt_delay.setSuffix(" мс")
        self.ptt_delay.valueChanged.connect(lambda v: self._set("ptt_delay_ms", v))
        self.ptt_tail = QSpinBox()
        self.ptt_tail.setRange(0, 3000)
        self.ptt_tail.setSingleStep(50)
        self.ptt_tail.setSuffix(" мс")
        self.ptt_tail.valueChanged.connect(lambda v: self._set("ptt_tail_ms", v))
        hint = QLabel(
            "Если в игре голос работает по кнопке (например, V или K), укажите её — KMuted сам "
            "зажмёт кнопку, пока говорит. Оставьте пустым, если используете активацию голосом."
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        form = QFormLayout(box)
        form.setSpacing(10)
        form.addRow("Кнопка рации", self.ptt_key)
        form.addRow("Задержка перед речью", self.ptt_delay)
        form.addRow("Держать после речи", self.ptt_tail)
        form.addRow(hint)
        return box

    def _passthrough_group(self) -> QGroupBox:
        box = QGroupBox("Живой микрофон (необязательно)")
        self.pt_enabled = QCheckBox("Смешивать мой настоящий микрофон с озвучкой")
        self.pt_enabled.toggled.connect(lambda v: self._set("passthrough_enabled", v))
        self.pt_device = QComboBox()
        self.pt_device.currentIndexChanged.connect(
            lambda _i: self._set("passthrough_device", self.pt_device.currentData() or "")
        )
        self.pt_volume = ValueSlider(0, 200, 100, _pct)
        self.pt_volume.valueChanged.connect(lambda v: self._set("passthrough_volume", v))
        self.pt_status = QLabel()
        self.pt_status.setObjectName("hint")
        hint = QLabel(
            "Нужно, если иногда говорите голосом: в игре выбран CABLE Output, и без этого "
            "ваш обычный микрофон никто не услышит."
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        form = QFormLayout(box)
        form.setSpacing(10)
        form.addRow(self.pt_enabled)
        form.addRow("Микрофон", self.pt_device)
        form.addRow("Громкость", self.pt_volume)
        form.addRow("", self.pt_status)
        form.addRow(hint)
        return box

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
                mark = "  ✓ виртуальный кабель" if devices.is_virtual_cable(dev.name) else ""
                combo.addItem(dev.name + mark, dev.name)
            if current and combo.findData(current) < 0:
                combo.addItem(f"{current} (не найдено)", current)
            combo.setCurrentIndex(max(0, combo.findData(current)))
            combo.blockSignals(False)

        fill(self.mic_device, outputs, a.mic_device, "— не выбрано —")
        fill(self.monitor_device, [d for d in outputs if not devices.is_virtual_cable(d.name)], a.monitor_device, "Системное устройство по умолчанию")
        fill(self.pt_device, [d for d in inputs if not devices.is_virtual_cable(d.name)], a.passthrough_device, "Системный микрофон по умолчанию")

        self.mic_volume.setValue(a.mic_volume)
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
            self.mic_status.setText(f"<span style='color:{theme.DANGER}'>{error}</span>")
        else:
            self._update_status()

    def _auto_detect(self) -> None:
        name = devices.guess_virtual_cable()
        if not name:
            self.mic_status.setText(
                f"<span style='color:{theme.WARNING}'>Виртуальный кабель не найден. Установите "
                "<a href='https://vb-audio.com/Cable/'>VB-Audio Virtual Cable</a> и перезагрузите ПК.</span>"
            )
            self.mic_status.setOpenExternalLinks(True)
            return
        self.reload_devices()
        idx = self.mic_device.findData(name)
        if idx >= 0:
            self.mic_device.setCurrentIndex(idx)

    def _set(self, attr: str, value) -> None:
        if self._loading:
            return
        a = self.controller.config.audio
        if getattr(a, attr) == value:
            return
        setattr(a, attr, value)
        self.controller.edited("audio")
        self._update_status()

    def _update_status(self) -> None:
        engine = self.controller.audio
        a = self.controller.config.audio
        if engine.mic_ready:
            name = engine.mic.device.name
            ok = devices.is_virtual_cable(name)
            text = f"🟢 Работает: {name} ({engine.mic.device.hostapi}, {engine.mic.mixer.sample_rate} Гц)"
            if not ok:
                text += (
                    f"<br><span style='color:{theme.WARNING}'>Это не похоже на виртуальный кабель — "
                    "другие люди вас не услышат, звук пойдёт в это устройство.</span>"
                )
            self.mic_status.setText(text)
        else:
            reason = engine.errors.get("mic") or "не выбрано"
            self.mic_status.setText(f"<span style='color:{theme.WARNING}'>🔴 {reason}</span>")
        mon_err = engine.errors.get("monitor", "")
        if mon_err:
            self.monitor_status.setText(f"⚠ {mon_err}")
        elif engine.monitor and engine.monitor.device:
            self.monitor_status.setText(f"🟢 {engine.monitor.device.name}")
        else:
            self.monitor_status.setText("выключено" if not a.monitor_enabled else "")
        pt_err = engine.errors.get("passthrough", "")
        if pt_err:
            self.pt_status.setText(f"⚠ {pt_err}")
        elif engine.passthrough:
            self.pt_status.setText("🟢 Микрофон подключён")
        else:
            self.pt_status.setText("")
