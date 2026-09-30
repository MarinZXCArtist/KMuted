"""Entry point: logging, single instance, tray icon, main window."""

from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import sys
import time
import traceback

from PySide6.QtCore import QProcess, Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from kmuted import APP_NAME, __version__, i18n, paths, winapi
from kmuted.audio import devices
from kmuted.config import load_config, save_config
from kmuted.i18n import tr

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


def _instance_alive() -> bool:
    socket = QLocalSocket()
    socket.connectToServer(INSTANCE_KEY)
    alive = socket.waitForConnected(300)
    if alive:
        socket.disconnectFromServer()
    return alive


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


def _wait_previous_instance(seconds: float = 8.0) -> None:
    """After a restart the old process may still be shutting down."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and _instance_alive():
        time.sleep(0.2)


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


def restart_app(extra_args: list[str] | None = None) -> None:
    """Start a fresh KMuted (it waits for this one to exit) and quit."""
    args = [a for a in sys.argv[1:] if a not in ("--restart", "--minimized")] + ["--restart"] + (extra_args or [])
    if getattr(sys, "frozen", False):
        QProcess.startDetached(sys.executable, args)
    else:
        QProcess.startDetached(sys.executable, ["-m", "kmuted", *args], os.getcwd())
    QApplication.instance().quit()


def build_tray(app: QApplication, window, controller) -> QSystemTrayIcon | None:
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return None
    from kmuted.ui.icons import tray_icon

    tray = QSystemTrayIcon(tray_icon(), app)
    tray.setToolTip(tr("{app} — озвучка в микрофон", app=APP_NAME))
    menu = QMenu()
    show = QAction(tr("Открыть KMuted"), menu)
    show.triggered.connect(window.show_and_raise)
    write = QAction(tr("Написать фразу…"), menu)
    write.triggered.connect(controller.open_input)
    repeat = QAction(tr("Повторить последнюю фразу"), menu)
    repeat.triggered.connect(controller.repeat_last)
    hotkeys = QAction(tr("Горячие клавиши"), menu)
    hotkeys.setCheckable(True)
    hotkeys.setChecked(controller.config.general.hotkeys_enabled)
    hotkeys.toggled.connect(lambda on: on != controller.config.general.hotkeys_enabled and controller.set_hotkeys_enabled(on))
    controller.hotkeys_toggled.connect(hotkeys.setChecked)
    mute = QAction(tr("Молчать в микрофоне"), menu)
    mute.setCheckable(True)
    mute.setChecked(controller.config.audio.mic_muted)
    mute.toggled.connect(lambda on: on != controller.config.audio.mic_muted and controller.toggle_mute())
    controller.config_changed.connect(lambda _s: mute.setChecked(controller.config.audio.mic_muted))
    translate = QAction(tr("Переводить перед озвучкой"), menu)
    translate.setCheckable(True)

    def sync_translate(*_args) -> None:
        translate.blockSignals(True)
        translate.setChecked(bool(controller.translation_target()))
        label = controller.translation_label()
        translate.setText(tr("Переводить перед озвучкой") + (f"  ({label})" if label else ""))
        translate.blockSignals(False)

    translate.toggled.connect(lambda on: on != bool(controller.translation_target()) and controller.toggle_translation())
    controller.config_changed.connect(sync_translate)
    controller.profile_changed.connect(sync_translate)
    sync_translate()
    stop = QAction(tr("Остановить всё"), menu)
    stop.triggered.connect(controller.stop)
    quit_action = QAction(tr("Выход"), menu)

    def quit_app() -> None:
        window.quitting = True
        app.quit()

    quit_action.triggered.connect(quit_app)
    for action in (show, write, repeat, hotkeys, mute, translate, stop):
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
    parser = argparse.ArgumentParser(prog="kmuted", description="KMuted — text to speech into your microphone")
    parser.add_argument("--minimized", action="store_true", help="запустить свёрнутым в трей")
    parser.add_argument("--no-hotkeys", action="store_true", help="не перехватывать глобальные клавиши")
    parser.add_argument("--no-audio", action="store_true", help="не открывать звуковые устройства")
    parser.add_argument("--verbose", action="store_true", help="подробный лог")
    parser.add_argument("--restart", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    setup_logging(args.verbose)
    log.info("KMuted %s starting (Python %s, %s)", __version__, sys.version.split()[0], sys.platform)

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setQuitOnLastWindowClosed(False)

    if args.restart:
        _wait_previous_instance()
    if _already_running():
        log.info("another instance is running — asked it to show up")
        return 0

    i18n.set_language(i18n.resolve(""))  # a first-run config is created in this language
    config = load_config()
    i18n.set_language(i18n.resolve(config.general.language))

    from kmuted.controller import Controller
    from kmuted.ui import theme
    from kmuted.ui.main_window import MainWindow

    theme.set_accent(config.general.accent)
    theme.apply_theme(app)
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
    controller.restart_requested.connect(restart_app)
    controller.toggle_window_requested.connect(window.toggle_visible)

    def excepthook(exc_type, exc, tb) -> None:
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        log.error("unhandled exception:\n%s", text)
        controller.error.emit(tr("Внутренняя ошибка: {error}. Подробности в {path}", error=exc, path=paths.log_path()))

    sys.excepthook = excepthook

    if not window.tray:
        window.quitting = True  # without a tray, closing the window must quit
        app.setQuitOnLastWindowClosed(True)
    if args.restart or not ((args.minimized or config.general.start_minimized) and window.tray):
        window.show()
    else:
        QTimer.singleShot(3000, winapi.trim_memory)

    if not args.no_audio and not config.audio.mic_device:
        window.show_and_raise()  # the home page shows the setup checklist

    window.start_update_check()
    app.aboutToQuit.connect(controller.shutdown)
    code = app.exec()
    log.info("bye")
    logging.shutdown()
    # Settings are saved by now. Don't wait for a speech request that may
    # still be talking to a server (up to tens of seconds): exit right away.
    os._exit(code)
