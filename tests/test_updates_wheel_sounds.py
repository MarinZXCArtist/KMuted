import sys
import zipfile
from pathlib import Path

import numpy as np
import soundfile as sf

from kmuted import updater


def _make_release_zip(path: Path) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        top = "MarinZXCArtist-KMuted-abc1234/"
        zf.writestr(top + "run.bat", "@echo off\r\n")
        zf.writestr(top + "kmuted/__init__.py", '__version__ = "9.9.9"\n')
        zf.writestr(top + "kmuted/new_module.py", "X = 1\n")
        zf.writestr(top + ".venv/should_not_copy.txt", "no")
        zf.writestr(top + "data/config.json", "{}")
        zf.writestr(top + "kmuted/__pycache__/junk.pyc", "x")
    return path


def test_install_source_replaces_code_and_keeps_user_files(tmp_path):
    root = tmp_path / "KMuted"
    (root / "kmuted").mkdir(parents=True)
    (root / ".venv").mkdir()
    (root / "data").mkdir()
    (root / "run.bat").write_text("old")
    (root / "kmuted" / "__init__.py").write_text('__version__ = "0.4.0"\n')
    (root / ".venv" / "keep.txt").write_text("my env")
    (root / "data" / "config.json").write_text('{"mine": true}')
    assert updater.is_source_copy(root)

    version = updater.install_source(_make_release_zip(tmp_path / "rel.zip"), root)
    assert version == "9.9.9"
    assert '"9.9.9"' in (root / "kmuted" / "__init__.py").read_text()
    assert (root / "kmuted" / "new_module.py").exists()
    assert (root / ".venv" / "keep.txt").read_text() == "my env"
    assert not (root / ".venv" / "should_not_copy.txt").exists()
    assert (root / "data" / "config.json").read_text() == '{"mine": true}'
    assert not (root / "kmuted" / "__pycache__").exists()


def test_git_checkouts_are_not_source_copies(tmp_path):
    (tmp_path / "kmuted").mkdir()
    (tmp_path / "kmuted" / "__init__.py").write_text("")
    (tmp_path / "run.bat").write_text("")
    (tmp_path / ".git").mkdir()
    assert not updater.is_source_copy(tmp_path)


def test_release_has_source_zip():
    rel = updater.parse_release({"tag_name": "v0.4.1", "zipball_url": "https://api.github.com/zip", "assets": []})
    assert rel.version == "0.4.1" and rel.source_url == "https://api.github.com/zip"


def test_release_notes_from_changelog():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    import release_notes

    assert release_notes.notes("0.4.1").startswith("- ")
    assert release_notes.notes("0.0.0-nope") == "KMuted 0.0.0-nope"


def _wav(path: Path) -> str:
    sf.write(path, np.zeros(1600, dtype=np.float32), 16000)
    return str(path)


def test_sound_files_go_into_wheel_sectors(qapp, tmp_path):
    from kmuted import config as cfgmod
    from kmuted.controller import Controller
    from kmuted.ui.page_wheels import WheelsPage

    c = Controller(cfgmod.default_config(), enable_hotkeys=False, enable_audio=False)
    try:
        page = WheelsPage(c)
        wheel = c.config.wheels[0]
        wheel.slots = wheel.slots[:4]
        wheel.slots[2].text = ""  # one empty sector
        page.refresh_list(select=0)
        files = [_wav(tmp_path / f"meme{i}.wav") for i in range(3)]
        page.put_sound_files(files, start_row=0)
        ids = [s.sound_id for s in wheel.slots]
        assert ids[0] and ids[2]  # dropped on sector 1, then the empty sector 3
        assert len(wheel.slots) == 5 and ids[4]  # no more empty sectors: the wheel grew
        assert len(c.config.sounds) == 3
        assert c.slot_caption(wheel.slots[0]) == "♪\u00a0meme0"

        page.add_sound_wheel()
        sound_wheel = c.config.wheels[-1]
        assert [s.sound_id for s in sound_wheel.slots[:3]] == [x.id for x in c.config.sounds]
        assert len(sound_wheel.slots) == 4  # padded to the minimum
    finally:
        c.shutdown()
