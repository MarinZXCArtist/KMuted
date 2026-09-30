"""Entry point: logging, single instance, tray icon, main window."""

from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import sys
import traceback

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from kmuted import APP_NAME, __version__, paths, winapi
from kmuted.audio import devices
from kmuted.config import load_config, save_config

log = logging.getLogger("kmuted")

INSTANCE_KEY = "KMuted-single-instance-v1"


def setup_logging(verbose: bool) -> None:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        file_handler = logging.handlers.RotatingFileHandler(paths.log_path(), maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except OSError:
        pass
    if sys.stderr is not None:  # windowed exe has no console
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        root.addHandler(console)


def _already_running() -> bool:
    """If another KMuted runs, ask it to show its window and return True."""
    socket = QLocalSocket()
    socket.connectToServer(INSTANCE_KEY)
    if socket.waitForConnected(300):
        socket.write(b"show")
        socket.flush()
        socket.waitForBytesWritten(300)
        socket.disconnectFromServer()
        return True
    return False


def _listen_for_instances(on_show) -> QLocalServer:
    QLocalServer.removeServer(INSTANCE_KEY)
    server = QLocalServer()
    server.listen(INSTANCE_KEY)

    def accept() -> None:
        conn = server.nextPendingConnection()
        if conn is not None:
            conn.readyRead.connect(lambda: (conn.readAll(), on_show()))
            conn.disconnected.connect(conn.deleteLater)

    server.newConnection.connect(accept)
    return server


def build_tray(app: QApplication, window, controller) -> QSystemTrayIcon | None:
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return None
    from kmuted.ui.icons import tray_icon

    tray = QSystemTrayIcon(tray_icon(), app)
    tray.setToolTip(f"{APP_NAME} — озвучка в микрофон")
    menu = QMenu()
    show = QAction("Открыть KMuted", menu)
    show.triggered.connect(window.show_and_raise)
    write = QAction("Написать фразу…", menu)
    write.triggered.connect(controller.open_input)
    hotkeys = QAction("Горячие клавиши", menu)
    hotkeys.setCheckable(True)
    hotkeys.setChecked(controller.config.general.hotkeys_enabled)
    hotkeys.toggled.connect(lambda on: on != controller.config.general.hotkeys_enabled and controller.set_hotkeys_enabled(on))
    controller.hotkeys_toggled.connect(hotkeys.setChecked)
    stop = QAction("Остановить речь", menu)
    stop.triggered.connect(controller.stop)
    quit_action = QAction("Выход", menu)

    def quit_app() -> None:
        window.quitting = True
        app.quit()

    quit_action.triggered.connect(quit_app)
    for action in (show, write, hotkeys, stop):
        menu.addAction(action)
    menu.addSeparator()
    menu.addAction(quit_action)
    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: window.show_and_raise()
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick)
        else None
    )
    idle_icon, busy_icon = tray_icon(False), tray_icon(True)
    controller.speaking_changed.connect(lambda on: tray.setIcon(busy_icon if on else idle_icon))
    tray.show()
    tray._menu = menu  # keep a reference
    return tray


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kmuted", description="KMuted — озвучка текста в микрофон")
    parser.add_argument("--minimized", action="store_true", help="запустить свёрнутым в трей")
    parser.add_argument("--no-hotkeys", action="store_true", help="не перехватывать глобальные клавиши")
    parser.add_argument("--no-audio", action="store_true", help="не открывать звуковые устройства")
    parser.add_argument("--verbose", action="store_true", help="подробный лог")
    args = parser.parse_args(argv)

    setup_logging(args.verbose)
    log.info("KMuted %s starting (Python %s, %s)", __version__, sys.version.split()[0], sys.platform)

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setQuitOnLastWindowClosed(False)

    if _already_running():
        log.info("another instance is running — asked it to show up")
        return 0

    from kmuted.controller import Controller
    from kmuted.ui.main_window import MainWindow
    from kmuted.ui.theme import apply_theme

    apply_theme(app)
    config = load_config()
    if not args.no_audio and not config.audio.mic_device:
        cable = devices.guess_virtual_cable()  # first run: pick VB-Cable automatically
        if cable:
            log.info("auto-selected virtual cable: %s", cable)
            config.audio.mic_device = cable
            save_config(config)
    controller = Controller(config, enable_hotkeys=not args.no_hotkeys, enable_audio=not args.no_audio)
    window = MainWindow(controller)
    window.tray = build_tray(app, window, controller)
    server = _listen_for_instances(window.show_and_raise)  # noqa: F841 - keep alive

    def excepthook(exc_type, exc, tb) -> None:
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        log.error("unhandled exception:\n%s", text)
        controller.error.emit(f"Внутренняя ошибка: {exc}. Подробности в {paths.log_path()}")

    sys.excepthook = excepthook

    if not window.tray:
        window.quitting = True  # without a tray, closing the window must quit
        app.setQuitOnLastWindowClosed(True)
    if not ((args.minimized or config.general.start_minimized) and window.tray):
        window.show()
    else:
        QTimer.singleShot(3000, winapi.trim_memory)

    if not args.no_audio and not config.audio.mic_device:
        window.show_and_raise()  # the home page shows the setup checklist

    app.aboutToQuit.connect(controller.shutdown)
    code = app.exec()
    log.info("bye")
    logging.shutdown()
    # Settings are saved by now. Don't wait for a speech request that may
    # still be talking to a server (up to tens of seconds): exit right away.
    os._exit(code)
