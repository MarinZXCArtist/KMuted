"""Checks GitHub Releases in the background and installs updates on request."""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication

from kmuted import updater
from kmuted.i18n import tr
from kmuted.ui.widgets import run_in_background

CHECK_EVERY_S = 20 * 3600


class _Relay(QObject):
    progress = Signal(int, int)
    done = Signal(object, object)


class UpdateService(QObject):
    available = Signal(object)  # updater.Release
    state_changed = Signal(str)  # human readable status
    progress = Signal(int)  # 0..100, -1 = unknown

    def __init__(self, controller) -> None:
        super().__init__()
        self.controller = controller
        self.release: updater.Release | None = None
        self.busy = False
        self._cancel = threading.Event()

    def schedule_startup_check(self, delay_ms: int = 8000) -> None:
        QTimer.singleShot(delay_ms, lambda: self.check(manual=False))

    def check(self, manual: bool = True) -> None:
        g = self.controller.config.general
        if self.busy:
            return
        if not manual and (not g.check_updates or time.time() - g.last_update_check < CHECK_EVERY_S):
            return
        self.busy = True
        self.state_changed.emit(tr("Проверяю обновления…"))

        def done(release, error) -> None:
            self.busy = False
            g.last_update_check = time.time()
            self.controller.edited("updates")
            if error is not None:
                self.state_changed.emit(tr("Не удалось проверить: {error}", error=error))
                if manual:
                    self.controller.notify.emit(tr("Не удалось проверить обновления"), "warning")
                return
            if release is None:
                self.state_changed.emit(tr("У вас последняя версия"))
                if manual:
                    self.controller.notify.emit(tr("У вас последняя версия KMuted"), "success")
                return
            self.release = release
            self.state_changed.emit(tr("Доступна версия {v}", v=release.version))
            self.available.emit(release)
            if manual or release.version != g.skipped_version:
                self.controller.notify.emit(tr("Вышла версия {v} — нажмите «Обновить» на главной", v=release.version), "info")

        run_in_background(updater.check_latest, done)

    def skip(self) -> None:
        if self.release is not None:
            self.controller.config.general.skipped_version = self.release.version
            self.controller.edited("updates")

    def install(self) -> None:
        release = self.release
        if release is None or self.busy:
            return
        frozen = updater.is_frozen()
        usable = release.installer_url if frozen else release.source_url
        if not updater.can_self_update() or not usable:
            QDesktopServices.openUrl(QUrl(release.page_url))
            return
        self.busy = True
        self._cancel.clear()
        self.state_changed.emit(tr("Скачиваю обновление…"))
        relay = _Relay(self)
        relay.progress.connect(lambda done, total: self.progress.emit(int(done * 100 / total) if total else -1))
        relay.done.connect(self._installer_ready if frozen else self._source_ready)

        def work() -> None:
            try:
                if frozen:
                    result = updater.download_installer(release, relay.progress.emit, self._cancel.is_set)
                else:  # a copy from the ZIP: replace the files right here
                    archive = updater.download_source(release, relay.progress.emit, self._cancel.is_set)
                    result = updater.install_source(archive)
                relay.done.emit(result, None)
            except Exception as exc:  # noqa: BLE001 - shown to the user
                relay.done.emit(None, exc)

        threading.Thread(target=work, daemon=True).start()

    def _source_ready(self, version, error) -> None:
        self.busy = False
        if error is not None:
            self.state_changed.emit(tr("Обновление не удалось: {error}", error=error))
            self.controller.error.emit(tr("Не удалось обновить KMuted: {error}", error=error))
            return
        self.state_changed.emit(tr("Обновлено до {v} — перезапускаю…", v=version or self.release.version))
        self.controller.save_now()
        updater.restart_source()
        QTimer.singleShot(300, QApplication.instance().quit)

    def cancel(self) -> None:
        self._cancel.set()

    def _installer_ready(self, path, error) -> None:
        self.busy = False
        if error is not None:
            self.state_changed.emit(tr("Загрузка не удалась: {error}", error=error))
            self.controller.error.emit(tr("Не удалось скачать обновление"))
            return
        self.state_changed.emit(tr("Устанавливаю… KMuted перезапустится сам"))
        self.controller.save_now()
        updater.run_installer(path)
        QTimer.singleShot(300, QApplication.instance().quit)
