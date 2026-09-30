def test_main_window_builds_all_pages(qapp):
    from kmuted import config as cfgmod
    from kmuted.controller import Controller
    from kmuted.ui.main_window import MainWindow
    from kmuted.ui.theme import apply_theme

    apply_theme(qapp)
    controller = Controller(cfgmod.default_config(), enable_hotkeys=False, enable_audio=False)
    window = MainWindow(controller)
    window.show()
    for i in range(window.nav.count()):
        window.nav.setCurrentRow(i)
        qapp.processEvents()
        assert not window.grab().isNull()
    # editing through the wheels page updates config and rebinds
    wheels_page = window.pages[1]
    wheels_page.add_wheel()
    assert len(controller.config.wheels) == 2
    wheels_page.remove_wheel()
    assert len(controller.config.wheels) == 1
    window.quitting = True
    window.close()
    controller.shutdown()


def test_hotkey_edit_records_combo(qapp):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    from kmuted.ui.widgets import HotkeyEdit

    edit = HotkeyEdit()
    got = []
    edit.changed.connect(got.append)
    edit.start_capture()
    assert HotkeyEdit.capturing_count == 1
    edit.eventFilter(edit.button, QKeyEvent(QEvent.KeyPress, Qt.Key_Control, Qt.ControlModifier))
    edit.eventFilter(edit.button, QKeyEvent(QEvent.KeyPress, Qt.Key_F5, Qt.ControlModifier))
    assert got == ["ctrl+f5"]
    assert HotkeyEdit.capturing_count == 0

    single = HotkeyEdit(single_key=True)
    single.changed.connect(got.append)
    single.start_capture()
    single.eventFilter(single.button, QKeyEvent(QEvent.KeyPress, Qt.Key_Alt, Qt.AltModifier))
    single.eventFilter(single.button, QKeyEvent(QEvent.KeyRelease, Qt.Key_Alt, Qt.NoModifier))
    assert got[-1] == "alt"
