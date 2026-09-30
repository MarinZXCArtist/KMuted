"""Download official Piper voices with one click."""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from kmuted import paths
from kmuted.tts import piper_catalog
from kmuted.ui.widgets import run_in_background
from kmuted.i18n import tr


class _Progress(QObject):
    progress = Signal(int, int)
    finished = Signal(object, object)  # path, error


class PiperDownloadDialog(QDialog):
    downloaded = Signal(str)  # .onnx path

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Скачать голоса Piper"))
        self.resize(560, 520)
        self._catalog: list[piper_catalog.CatalogVoice] = []
        self._cancel = threading.Event()
        self._busy = False

        self.lang = QComboBox()
        self.lang.currentIndexChanged.connect(self._fill_list)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _i: self._download())
        self.status = QLabel(tr("Загружаю каталог…"))
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.hide()

        self.download_btn = QPushButton(tr("Скачать"))
        self.download_btn.setObjectName("primary")
        self.download_btn.clicked.connect(self._download)
        close = QPushButton(tr("Закрыть"))
        close.clicked.connect(self.reject)

        top = QHBoxLayout()
        top.addWidget(QLabel(tr("Язык")))
        top.addWidget(self.lang, 1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.download_btn)
        buttons.addWidget(close)

        info = QLabel(
            tr("Голоса из официального каталога Piper (huggingface.co/rhasspy/piper-voices). "
            "Качество: x_low/low — быстрее, medium — оптимально, high — лучше звучит.")
        )
        info.setObjectName("hint")
        info.setWordWrap(True)

        lay = QVBoxLayout(self)
        lay.addWidget(info)
        lay.addLayout(top)
        lay.addWidget(self.list, 1)
        lay.addWidget(self.progress)
        lay.addWidget(self.status)
        lay.addLayout(buttons)

        run_in_background(piper_catalog.fetch_catalog, self._catalog_loaded)

    def _catalog_loaded(self, catalog, error) -> None:
        if error is not None or not catalog:
            self._catalog = piper_catalog.fallback_catalog()
            self.status.setText(tr("Каталог недоступен ({error}), показан сокращённый список.", error=error))
        else:
            self._catalog = catalog
            self.status.setText(tr("Доступно голосов: {n}", n=len(catalog)))
        langs = sorted({(v.language, v.language_name) for v in self._catalog}, key=lambda t: (not t[0].startswith("ru"), t[0]))
        self.lang.blockSignals(True)
        self.lang.clear()
        for code, name in langs:
            self.lang.addItem(f"{name}  [{code}]", code)
        self.lang.blockSignals(False)
        self._fill_list()

    def _fill_list(self) -> None:
        code = self.lang.currentData()
        installed = {p.stem for p in paths.piper_voices_dir().rglob("*.onnx")}
        self.list.clear()
        for voice in self._catalog:
            if code and voice.language != code:
                continue
            size = tr(", {mb} МБ", mb=f"{voice.size_mb:.0f}") if voice.size_bytes else ""
            speakers = tr(", голосов: {n}", n=voice.num_speakers) if voice.num_speakers > 1 else ""
            mark = "✓ " if voice.key in installed else ""
            item = QListWidgetItem(f"{mark}{voice.name} — {voice.quality}{speakers}{size}")
            item.setData(Qt.UserRole, voice)
            self.list.addItem(item)

    def _download(self) -> None:
        item = self.list.currentItem()
        if item is None or self._busy:
            return
        voice: piper_catalog.CatalogVoice = item.data(Qt.UserRole)
        self._busy = True
        self._cancel.clear()
        self.download_btn.setEnabled(False)
        self.progress.setValue(0)
        self.progress.show()
        self.status.setText(tr("Скачиваю {name}…", name=voice.key))

        relay = _Progress(self)
        relay.progress.connect(self._on_progress, Qt.QueuedConnection)
        relay.finished.connect(self._on_finished, Qt.QueuedConnection)

        def work() -> None:
            try:
                path = piper_catalog.download_voice(
                    voice,
                    paths.piper_voices_dir(),
                    progress=relay.progress.emit,
                    cancelled=self._cancel.is_set,
                )
                relay.finished.emit(str(path), None)
            except Exception as exc:  # noqa: BLE001 - shown to the user
                relay.finished.emit(None, exc)

        threading.Thread(target=work, daemon=True).start()

    def _on_progress(self, done: int, total: int) -> None:
        if total:
            self.progress.setMaximum(100)
            self.progress.setValue(int(done * 100 / total))
        else:
            self.progress.setMaximum(0)

    def _on_finished(self, path, error) -> None:
        self._busy = False
        self.download_btn.setEnabled(True)
        self.progress.hide()
        if error is not None:
            self.status.setText(tr("Ошибка загрузки: {error}", error=error))
            return
        self.status.setText(tr("Готово! Голос добавлен в список Piper."))
        self._fill_list()
        self.downloaded.emit(path)

    def reject(self) -> None:
        self._cancel.set()
        super().reject()
