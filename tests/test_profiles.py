import pytest

from kmuted import config as cfgmod
from kmuted.config import GameProfile, Phrase


@pytest.fixture
def controller(qapp):
    from kmuted.controller import Controller

    cfg = cfgmod.default_config()
    c = Controller(cfg, enable_hotkeys=False, enable_audio=False)
    c._prewarm_timer.stop()
    c._profile_timer.stop()
    c.said = []
    c.say = lambda text, voice_id="", persist=False, phrase=False: c.said.append(text)
    yield c
    c.shutdown()


def _two_games(c):
    cs = GameProfile(name="CS2", processes=["cs2.exe"])
    dota = GameProfile(name="Dota 2", processes=["dota2.exe"])
    c.config.profiles = [cs, dota]
    return cs, dota


def test_pick_profile_prefers_the_game_in_front(controller):
    cs, dota = _two_games(controller)
    assert controller.pick_profile({"explorer.exe"}) == ""
    assert controller.pick_profile({"cs2.exe"}) == cs.id
    assert controller.pick_profile({"cs2.exe", "dota2.exe"}, front="dota2.exe") == dota.id
    dota.enabled = False
    assert controller.pick_profile({"dota2.exe"}, front="dota2.exe") == ""


def test_game_bindings_replace_common_ones(controller):
    c = controller
    cs, dota = _two_games(c)
    c.config.phrases = [
        Phrase(text="общая", hotkey="alt+1"),
        Phrase(text="для CS", hotkey="alt+1", profiles=[cs.id]),
        Phrase(text="только Dota", hotkey="alt+2", profiles=[dota.id]),
    ]
    c.rebind_hotkeys()
    c._on_hotkey_down("alt+1")
    c._on_hotkey_down("alt+2")
    assert c.said == ["общая"]  # no game: common phrase, Dota phrase is off

    c._activate_profile(cs.id)
    c._on_hotkey_down("alt+1")
    c._on_hotkey_down("alt+2")
    assert c.said == ["общая", "для CS"]

    c._activate_profile(dota.id)
    c._on_hotkey_down("alt+2")
    assert c.said[-1] == "только Dota"


def test_clashes_respect_scopes(controller):
    c = controller
    cs, dota = _two_games(c)
    common = Phrase(text="a", hotkey="alt+1")
    game = Phrase(text="b", hotkey="alt+1", profiles=[cs.id])
    same_game = Phrase(text="c", hotkey="alt+1", profiles=[cs.id, dota.id])
    c.config.phrases = [common, game]
    assert c.hotkey_clashes("alt+1", f"phrase:{game.id}") == []  # the game one replaces the common one
    c.config.phrases.append(same_game)
    assert len(c.hotkey_clashes("alt+1", f"phrase:{game.id}")) == 1
    c.config.general.input_hotkey = "alt+1"
    assert any("ввода" in name for name in c.hotkey_clashes("alt+1", f"phrase:{game.id}"))
    # an unsaved phrase checked with its planned scope
    assert c.hotkey_conflict("alt+1", "phrase:new", (dota.id,)) != ""


def test_profile_voice_is_restored(controller):
    c = controller
    cs, _dota = _two_games(c)
    mine, game_voice = c.config.voices[0], c.config.voices[1]
    c.set_active_voice(mine.id)
    cs.voice_id = game_voice.id
    c._activate_profile(cs.id)
    assert c.config.active_voice() is game_voice
    assert c.config.general.voice_before_profile == mine.id
    c._activate_profile("")
    assert c.config.active_voice() is mine
    assert c.config.general.voice_before_profile == ""


def test_profile_translation_override(controller):
    c = controller
    cs, _dota = _two_games(c)
    cs.translate, cs.target = "on", "de"
    assert c.translation_target() == ""
    c._activate_profile(cs.id)
    assert c.translation_target() == "de"
    assert c.translation_label().endswith("DE")
    c.toggle_translation()  # flips the profile's own setting
    assert cs.translate == "off" and c.translation_target() == ""


def test_manual_mode_and_cycle(controller):
    c = controller
    cs, dota = _two_games(c)
    c.set_profile_mode(cs.id)
    assert c.active_profile_id == cs.id
    c.cycle_profile_mode()
    assert c.config.general.profile_mode == dota.id and c.active_profile_id == dota.id
    c.cycle_profile_mode()
    assert c.config.general.profile_mode == cfgmod.PROFILE_AUTO
    c.set_profile_mode(cfgmod.PROFILE_NONE)
    assert c.active_profile_id == ""


def test_poll_switches_profiles(controller, monkeypatch):
    from kmuted import processes

    c = controller
    cs, _dota = _two_games(c)
    running = {"names": set()}
    monkeypatch.setattr(processes, "snapshot", lambda: (running["names"], ""))
    c._poll_profiles()
    assert c.active_profile_id == ""
    running["names"] = {"cs2.exe"}
    c._poll_profiles()
    assert c.active_profile_id == cs.id
    running["names"] = set()
    c._poll_profiles()
    assert c.active_profile_id == ""


def test_config_normalizes_profiles(tmp_path):
    cfg = cfgmod.default_config()
    prof = GameProfile(name="CS2", processes=[r"C:\Games\CS2\CS2.EXE", "cs2.exe", ""], translate="maybe")
    cfg.profiles = [prof]
    cfg.phrases[0].profiles = [prof.id, "gone"]
    cfg.general.profile_mode = "gone"
    path = tmp_path / "config.json"
    cfgmod.save_config(cfg.normalize(), path)
    loaded = cfgmod.load_config(path)
    assert loaded.profiles[0].processes == ["cs2.exe"]
    assert loaded.profiles[0].translate == ""
    assert loaded.phrases[0].profiles == [prof.id]
    assert loaded.general.profile_mode == cfgmod.PROFILE_AUTO


def test_process_snapshot_runs():
    from kmuted import processes

    names, _front = processes.snapshot()
    assert isinstance(names, set) and names  # at least this python process


def test_plural_forms():
    from kmuted import i18n

    i18n.set_language("ru")
    assert [i18n.plural(n, "фраза", "фразы", "фраз") for n in (1, 3, 5, 11, 21, 22)] == [
        "1 фраза", "3 фразы", "5 фраз", "11 фраз", "21 фраза", "22 фразы"]
    i18n.set_language("en")
    try:
        assert i18n.plural(1, "фраза", "фразы", "фраз") == "1 phrase"
        assert i18n.plural(4, "фраза", "фразы", "фраз") == "4 phrases"
    finally:
        i18n.set_language("ru")
