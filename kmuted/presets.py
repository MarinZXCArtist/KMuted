"""Share packs of phrases, wheels, sounds and voices as one ``.kmuted`` file.

A pack is a zip: ``manifest.json`` + the sound files under ``sounds/``.
Imported items get fresh ids; hotkeys that clash with yours are dropped
(unless you choose to replace everything).
"""

from __future__ import annotations

import dataclasses
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from kmuted import __version__, paths
from kmuted.audio.sounds import AUDIO_EXTS, resolve_path
from kmuted.config import Config, Phrase, Sound, VoiceProfile, Wheel, from_dict, new_id
from kmuted.i18n import tr

PACK_EXT = ".kmuted"
FORMAT = 1
MAX_PACK_BYTES = 500 * 1024 * 1024
PARTS = ("phrases", "wheels", "sounds", "voices")


class PackError(RuntimeError):
    pass


@dataclass
class PackInfo:
    name: str = ""
    version: str = ""
    counts: dict[str, int] = field(default_factory=dict)


def export_pack(cfg: Config, path: str | Path, parts: set[str], name: str = "") -> PackInfo:
    path = Path(path)
    if path.suffix != PACK_EXT:
        path = path.with_suffix(PACK_EXT)
    manifest: dict = {"format": FORMAT, "app": "KMuted", "version": __version__, "name": name or path.stem}
    files: dict[str, Path] = {}
    if "phrases" in parts:
        manifest["phrases"] = [dataclasses.asdict(p) for p in cfg.phrases]
    if "wheels" in parts:
        manifest["wheels"] = [dataclasses.asdict(w) for w in cfg.wheels]
    if "voices" in parts:
        voices = []
        for v in cfg.voices:
            data = dataclasses.asdict(v)
            if v.engine == "piper" and v.voice:
                data["voice"] = Path(v.voice).name  # local paths don't travel
            voices.append(data)
        manifest["voices"] = voices
    if "sounds" in parts:
        sounds = []
        for s in cfg.sounds:
            src = resolve_path(s)
            if not src.exists():
                continue
            arc = f"sounds/{s.id}{src.suffix.lower()}"
            files[arc] = src
            data = dataclasses.asdict(s)
            data["file"] = arc
            sounds.append(data)
        manifest["sounds"] = sounds
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for arc, src in files.items():
            zf.write(src, arc, compress_type=zipfile.ZIP_STORED)  # audio is already compressed
    return PackInfo(manifest["name"], __version__, {p: len(manifest.get(p, [])) for p in PARTS})


def _read_manifest(zf: zipfile.ZipFile) -> dict:
    total = sum(info.file_size for info in zf.infolist())
    if total > MAX_PACK_BYTES:
        raise PackError(tr("Набор слишком большой"))
    try:
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
    except (KeyError, ValueError) as exc:
        raise PackError(tr("Это не набор KMuted (нет manifest.json)")) from exc
    if not isinstance(manifest, dict) or manifest.get("app") != "KMuted":
        raise PackError(tr("Это не набор KMuted"))
    if int(manifest.get("format", 0)) > FORMAT:
        raise PackError(tr("Набор сделан в более новой версии KMuted — обновите программу"))
    return manifest


def read_pack(path: str | Path) -> PackInfo:
    try:
        with zipfile.ZipFile(path) as zf:
            m = _read_manifest(zf)
    except zipfile.BadZipFile as exc:
        raise PackError(tr("Файл повреждён или это не набор KMuted")) from exc
    return PackInfo(str(m.get("name", "")), str(m.get("version", "")), {p: len(m.get(p, []) or []) for p in PARTS})


def import_pack(cfg: Config, path: str | Path, parts: set[str], replace: bool = False) -> dict[str, int]:
    """Merge (or replace) the chosen parts; returns counts incl. dropped hotkeys."""
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise PackError(tr("Файл повреждён или это не набор KMuted")) from exc
    with zf:
        m = _read_manifest(zf)
        stats = {p: 0 for p in PARTS}
        stats["hotkeys_dropped"] = 0
        voice_ids: dict[str, str] = {}
        sound_ids: dict[str, str] = {}

        if replace:
            for part in parts:
                if part == "voices":
                    continue  # never leave the user without a voice; imported ones are appended
                getattr(cfg, part).clear()
        taken = _taken_hotkeys(cfg)

        def claim(combo: str) -> str:
            if not combo:
                return ""
            if combo in taken:
                stats["hotkeys_dropped"] += 1
                return ""
            taken.add(combo)
            return combo

        if "voices" in parts:
            for raw in m.get("voices", []) or []:
                voice = from_dict(VoiceProfile, raw)
                old = voice.id
                voice.id = new_id()
                if voice.engine == "piper" and voice.voice and not Path(voice.voice).is_absolute():
                    voice.voice = str(paths.piper_voices_dir() / voice.voice)
                voice.hotkey = claim(voice.hotkey)
                voice_ids[old] = voice.id
                cfg.voices.append(voice)
                stats["voices"] += 1

        if "sounds" in parts:
            names = set(zf.namelist())
            for raw in m.get("sounds", []) or []:
                sound = from_dict(Sound, raw)
                arc = str(PurePosixPath(sound.file))
                if arc not in names or not arc.startswith("sounds/"):
                    continue
                suffix = PurePosixPath(arc).suffix.lower()
                if suffix not in AUDIO_EXTS:
                    continue
                old = sound.id
                sound.id = new_id()
                dest = _unique(paths.sounds_dir(), _safe_stem(sound.name or sound.id), suffix)
                with zf.open(arc) as src, open(dest, "wb") as out:
                    out.write(src.read())
                sound.file = dest.name
                sound.hotkey = claim(sound.hotkey)
                sound_ids[old] = sound.id
                cfg.sounds.append(sound)
                stats["sounds"] += 1

        if "phrases" in parts:
            for raw in m.get("phrases", []) or []:
                phrase = from_dict(Phrase, raw)
                if not phrase.text.strip():
                    continue
                phrase.id = new_id()
                phrase.voice_id = voice_ids.get(phrase.voice_id, "")
                phrase.hotkey = claim(phrase.hotkey)
                cfg.phrases.append(phrase)
                stats["phrases"] += 1

        if "wheels" in parts:
            for raw in m.get("wheels", []) or []:
                wheel = from_dict(Wheel, raw)
                wheel.id = new_id()
                wheel.hotkey = claim(wheel.hotkey)
                for slot in wheel.slots:
                    slot.voice_id = voice_ids.get(slot.voice_id, "")
                    slot.sound_id = sound_ids.get(slot.sound_id, "")
                cfg.wheels.append(wheel)
                stats["wheels"] += 1
    cfg.normalize()
    return stats


def _taken_hotkeys(cfg: Config) -> set[str]:
    from kmuted.actions import ACTION_KEYS, attr

    taken = {getattr(cfg.general, attr(k)) for k in ACTION_KEYS}
    for group in (cfg.phrases, cfg.wheels, cfg.sounds, cfg.voices):
        taken.update(item.hotkey for item in group)
    taken.discard("")
    return taken


def _safe_stem(name: str) -> str:
    keep = "".join(ch if ch.isalnum() or ch in " -_()" else "_" for ch in name).strip()
    return keep[:60] or "sound"


def _unique(folder: Path, stem: str, suffix: str) -> Path:
    dest = folder / f"{stem}{suffix}"
    n = 1
    while dest.exists():
        dest = folder / f"{stem} ({n}){suffix}"
        n += 1
    return dest
