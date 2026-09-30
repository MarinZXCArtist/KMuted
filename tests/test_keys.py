from types import SimpleNamespace

import pytest

from kmuted.hotkeys import keys


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Ctrl+Shift+F1", "ctrl+shift+f1"),
        ("shift + ctrl + a", "ctrl+shift+a"),
        ("alt+numadd", "alt+numadd"),
        ("XButton2", "mouse5"),
        ("Control+Return", "ctrl+enter"),
        ("alt", "alt"),
        ("", ""),
        ("ctrl+a+b", ""),
        ("ctrl+shift", ""),
        ("ctrl+nosuchkey", ""),
    ],
)
def test_normalize(raw, expected):
    assert keys.normalize_combo(raw) == expected


def test_format():
    assert keys.format_combo("ctrl+shift+f1") == "Ctrl + Shift + F1"
    assert keys.format_combo("alt+num5") == "Alt + Num 5"
    assert keys.format_combo("mouse4").startswith("Мышь 4")
    assert keys.format_combo("") == ""


def test_vk_table_covers_basics():
    assert keys.VK_NAMES[0x41] == "a"
    assert keys.VK_NAMES[0x70] == "f1"
    assert keys.VK_NAMES[0x60] == "num0"
    assert keys.NAME_TO_VK["ctrl"] == 0xA2
    assert keys.NAME_TO_VK["a"] == 0x41


def test_pynput_names_windows():
    # KeyCode for Ctrl+A on Windows: char is a control char, vk is still 'A'
    kc = SimpleNamespace(vk=0x41, char="\x01")
    assert keys.name_from_pynput_key(kc, windows=True) == "a"
    # Key enum member: .value is a KeyCode
    member = SimpleNamespace(name="ctrl_l", value=SimpleNamespace(vk=0xA2, char=None))
    assert keys.name_from_pynput_key(member, windows=True) == "ctrl"
    # Russian layout: char is Cyrillic, vk decides
    assert keys.name_from_pynput_key(SimpleNamespace(vk=0x51, char="й"), windows=True) == "q"


def test_pynput_names_other_platforms():
    member = SimpleNamespace(name="page_up", value=SimpleNamespace(vk=0xFF55, char=None))
    assert keys.name_from_pynput_key(member, windows=False) == "pageup"
    assert keys.name_from_pynput_key(SimpleNamespace(vk=0x61, char="A"), windows=False) == "a"
    assert keys.name_from_pynput_key(SimpleNamespace(vk=None, char="-"), windows=False) == "minus"
    assert keys.name_from_pynput_key(SimpleNamespace(vk=0xFFB3, char=None), windows=False) == "num3"
    assert keys.name_from_pynput_key(SimpleNamespace(vk=None, char=None), windows=False) is None


def test_pynput_buttons():
    assert keys.name_from_pynput_button(SimpleNamespace(name="x1")) == "mouse4"
    assert keys.name_from_pynput_button(SimpleNamespace(name="x2")) == "mouse5"
    assert keys.name_from_pynput_button(SimpleNamespace(name="left")) is None
