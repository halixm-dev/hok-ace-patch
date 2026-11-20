"""Build the per-install catalog the runtime engine reads for one PC edition game and one language.

The engine (`wxq_patch.adaptive.run`) installs a catalog into the PC edition as it stands: each text
table and catalog edit at the PC offsets the catalog records. Four things in that catalog do not fit
an installed game as they are, so this module writes a per-install copy with them fixed:

- **Regioned atlases** (`sprite_table.REGION_SPRITE_ASSETS`): the PC edition re-packs these atlases
  as the mobile edition does, so each is ported at the installed game's own sprite table in package
  `19`, with this repo's art (`resources/sprites/`), and re-encoded as BC7
  (`mobile_graphics.port_atlas(codec="bc7")`). The port replaces the catalog entry: its payload,
  `patch_ranges` and all three hashes describe exactly the blocks this installation needs. A missing
  table or a moved or resized region refuses the atlas (ADR 0006), and a refused atlas is **dropped**
  from the copy, never left for the engine to apply at the catalog's PC offsets. The Secret Technique
  title atlas has no catalog entry; its labels are drawn (`label_atlas`) after its title sprites are
  re-laid (`card_titles.relayout`), and the assets the relayout moves go in as whole-file entries.
- **Repo-drawn label textures** (`mobile_graphics.LABEL_TEXTURES`): standalone labels the catalog has
  no entry for. Each gets a new package-`19` entry whose payload is this repo's art for the language
  (`label_texture(codec="rgba32")`); one at another size is refused and left out, like a refused atlas.
- **Re-drawn payloads** of a language other than English (`catalog_id/<HASH>.blocks`): the catalog
  records the English payload's hashes, and the engine verifies each texture against
  `patched_sha256`, so these are re-hashed from the installed original. An entry whose installed
  source matches neither the catalog's `source_sha256` nor this patcher's last result (<previous>)
  is left for the engine to skip.
- **Lua** (`extra_text.SCRIPT_ASSETS`): the Lua label and the nine Lua edits, each a whole-file entry
  with no `patch_ranges`, rewritten by `extra_text.rewrite_script`. The PC edition keeps them in
  package `extra_text.SCRIPT_PC_PACKAGE`; a script it lacks is found by a logged scan of every index.

Text tables stay as the catalog has them: the terminology table and the catalog supplement apply as
the engine loads the copy (`engine_hooks`' `load_catalog`), and resource tokens are expanded after its
scan (`engine_hooks`' `scan`). No append, no card-dictionary chunk gain and no config bin: those are
the mobile edition's, and the allowlist is per edition.

**The stage** is `<work>/pc/<game id>/<catalog folder name>/`, named after the language's catalog
folder because `languages.for_catalog` reads the language from that name. Every payload of the bundle
is hard-linked into it (copied only when the working folder is on another drive), with the language's
own payloads over the English ones, and only `catalog.json.gz`, the overrides and the stage record
`pc_stage.json` are written. It is built in a sibling folder and swapped in whole.

**The cache**: the stage record holds the patcher `version`, the language, the bundled catalog's hash
and, for every game asset the build read, the hashes the stage is valid for — the one it read and
the one its entry installs. A later build whose inputs all still match one of those reuses the stage
without decoding or encoding an atlas, so Check, and an Install with nothing changed, cost only the
reads. The record also stamps the size and modification time of every file in the packages it read;
while those all match, the check reads no asset at all (re-reading package `19` alone walks every
chunk of a 2.3 GB package, about a minute). Game ids are the engine's own (`engine_hooks.game_id`).
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

ATLAS_PACKAGE = "19"  # the PC edition's UI atlases and their sprite tables (fork, 2026-11-18)
STAGE_RECORD = "pc_stage.json"
STAGE_SCHEMA = 1
BUNDLE_SKIP = {"catalog.json.gz", "previews"}  # review renders; the engine never reads them


@dataclass
class Stage:
    """The result of `build`: the catalog folder to hand the engine, and what went into it."""

    catalog: Path
    language: str
    cached: bool
    # The hash each overridden asset has once the engine installs this stage (state file, ticket 02).
    patched: dict[str, str] = field(default_factory=dict)
    # Regioned atlases refused at this installation's sprite table and label textures refused at their size,
    # each dropped from the copy.
    skipped: list[str] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _builtin(game: Path) -> Path:
    return Path(game) / "WXQ_Data" / "Package" / "builtin"


class _Reader:
    """Opens only the packages a build names, once each, and hashes every asset it hands out."""

    def __init__(self, game: Path, log) -> None:
        self.game, self.log = Path(game), log
        self.packages: dict[str, object | None] = {}
        self.inputs: dict[str, str] = {}  # asset name -> sha256 of the bytes read
        self.where: dict[str, str] = {}  # asset name -> the package it was read from

    def package(self, package_id: str):
        if package_id not in self.packages:
            from wxq_patch.qtsvfs import QtsPackage

            folder = _builtin(self.game) / str(package_id)
            try:
                self.packages[package_id] = (QtsPackage(folder) if (folder / f"{package_id}.db").is_file()
                                             else None)
            except Exception as error:  # noqa: BLE001 - an unreadable index holds nothing to edit
                self.log(f"package {package_id}: index does not read ({error}); left alone")
                self.packages[package_id] = None
        return self.packages[package_id]

    def has(self, package_id: str, asset: int) -> bool:
        package = self.package(package_id)
        return package is not None and asset in package.entries

    def read(self, package_id: str, asset: int) -> bytes | None:
        if not self.has(package_id, asset):
            return None
        raw = self.package(package_id).extract(asset)
        self.inputs[f"{asset:016X}"] = _sha(raw)
        self.where[f"{asset:016X}"] = package_id
        return raw

    def holder(self, asset: int, preferred: str) -> str | None:
        """The package holding <asset>: <preferred>, else the first index a full scan finds it in."""
        if self.has(preferred, asset):
            return preferred
        root = _builtin(self.game)
        for folder in sorted(root.iterdir()) if root.is_dir() else ():
            if folder.name != preferred and folder.name.isdigit() and self.has(folder.name, asset):
                self.log(f"{asset:016X} is not in package {preferred}: found by a scan of every index "
                         f"in package {folder.name}")
                return folder.name
        return None


def build(game: Path, resources: Path, language: str, work: Path, *, version: str,
          previous: dict[str, str] | None = None, log=print) -> Stage:
    """The per-install catalog for <game> (the PC edition's root, holding `WXQ_Data`) in <language>.

    <resources> is the bundle (`resources/` from source); <version> is the patcher's `VERSION`.
    <previous> maps an asset name to the hash this patcher's last verified install left it at (the
    state file's patched hashes); it only lets a re-drawn payload already in place be recognized.
    Never writes into <game> or <resources>.
    """
    import languages
    from engine_hooks import game_id, install

    install()  # the loader the Lua pass reads the catalog through: supplement and glossary
    started = time.perf_counter()
    previous = previous or {}
    bundle = languages.catalog_dir(resources, language)
    english = languages.catalog_dir(resources, languages.DEFAULT_LANGUAGE)
    stage = Path(work) / "pc" / game_id(game) / bundle.name
    catalog_hash = _sha((bundle / "catalog.json.gz").read_bytes())
    reader = _Reader(game, log)
    timings: dict[str, float] = {}

    cached = _cached(stage, reader, version, language, catalog_hash)
    timings["inputs"] = time.perf_counter() - started
    if cached is not None:
        log(f"PC catalog: {bundle.name} stage reused ({len(cached['patched'])} assets patched)")
        return Stage(stage, language, True, dict(cached["patched"]), list(cached["skipped"]),
                     {**timings, "total": time.perf_counter() - started})

    with gzip.open(bundle / "catalog.json.gz", "rt", encoding="utf-8") as handle:
        data = json.load(handle)
    entries = {item["hash"].upper(): item for item in data["graphics"]}
    overrides: dict[str, bytes] = {}
    patched: dict[str, str] = {}
    valid: dict[str, set[str]] = {}

    mark = time.perf_counter()
    skipped = _regioned_atlases(reader, bundle, data, entries, overrides, patched, valid, log)
    skipped += _label_textures(reader, bundle, data, overrides, patched, valid, log)
    timings["atlases"] = time.perf_counter() - mark
    mark = time.perf_counter()
    if bundle != english:
        _redrawn_payloads(reader, bundle, entries, previous, patched, valid, log)
    timings["redrawn"] = time.perf_counter() - mark
    mark = time.perf_counter()
    _scripts(reader, bundle, data, overrides, patched, valid, log)
    timings["scripts"] = time.perf_counter() - mark

    mark = time.perf_counter()
    inputs = {name: sorted({digest} | valid.get(name, set())) for name, digest in reader.inputs.items()}
    record = {"schema": STAGE_SCHEMA, "version": version, "language": language, "catalog": catalog_hash,
              "inputs": inputs, "packages": reader.where, "patched": patched, "skipped": skipped,
              "stamps": _stamps(game, set(reader.where.values()))}
    linked, copied = _write_stage(stage, bundle, english, data, overrides, record)
    timings["stage"] = time.perf_counter() - mark
    timings["total"] = time.perf_counter() - started
    log(f"PC catalog: {bundle.name} stage built: {len(patched)} assets patched, {len(overrides)} payloads "
        f"written, {linked} payloads linked, "
        f"{copied} copied" + (f", {len(skipped)} textures refused" if skipped else ""))
    return Stage(stage, language, False, patched, skipped, timings)


def _cached(stage: Path, reader: _Reader, version: str, language: str, catalog_hash: str) -> dict | None:
    """The stage record when the stage at <stage> still fits every input it was built from, else None."""
    try:
        record = json.loads((stage / STAGE_RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (record.get("schema") != STAGE_SCHEMA or record.get("version") != version
            or record.get("language") != language or record.get("catalog") != catalog_hash
            or not (stage / "catalog.json.gz").is_file()):
        return None
    packages = record.get("packages", {})
    stamps = record.get("stamps")
    if stamps and stamps == _stamps(reader.game, set(packages.values())):
        return record  # no package file the stage read from has changed since: nothing to re-read
    for name, hashes in record.get("inputs", {}).items():
        raw = reader.read(packages.get(name, ""), int(name, 16))
        if raw is None or _sha(raw) not in hashes:
            return None
    # Every asset is unchanged although a package file moved (an update elsewhere in the package):
    # record the files as they are now, so the next check reads nothing again.
    record["stamps"] = _stamps(reader.game, set(packages.values()))
    (stage / STAGE_RECORD).write_text(json.dumps(record, indent=1), encoding="utf-8")
    return record


def _stamps(game: Path, package_ids: set[str]) -> dict[str, list[int]]:
    """Size and modification time of every file in the packages <package_ids>, by relative path.

    A shortcut for the cache, not its key: while these match, the assets the stage was built from are
    the same bytes, so a cache check reads nothing. When any differs, every input asset is re-read and
    re-hashed, and a stage whose assets are all unchanged is still reused.

    The engine rewrites a package's shards in place at the same size and modification time; only the
    package's index (`<id>.db`) gets a new time (2026-11-20). An engine install or restore always
    rewrites the index with its shards, so the index's stamp is what moves.
    """
    root = _builtin(game)
    stamps: dict[str, list[int]] = {}
    for package_id in sorted(package_ids):
        folder = root / package_id
        for path in sorted(folder.iterdir()) if folder.is_dir() else ():
            if path.is_file():
                status = path.stat()
                stamps[f"{package_id}/{path.name}"] = [status.st_size, status.st_mtime_ns]
    return stamps


def _set_entry(entry: dict, source: bytes, result: bytes, ranges: list[list[int]] | None,
               payload_name: str, overrides: dict[str, bytes], patched: dict[str, str],
               valid: dict[str, set[str]]) -> None:
    """Point <entry> at <result>: whole-file when <ranges> is None, else the given block runs."""
    name = entry["hash"].upper()
    if ranges is None:
        payload = result
        entry.pop("patch_ranges", None)
    else:
        payload = b"".join(result[offset:offset + length] for offset, length in ranges)
        entry["patch_ranges"] = ranges
    entry["source_sha256"] = _sha(source)
    entry["patched_sha256"] = _sha(result)
    entry["payload_sha256"] = _sha(payload)
    entry["payload"] = payload_name
    overrides[payload_name] = payload
    patched[name] = entry["patched_sha256"]
    valid.setdefault(name, set()).add(entry["patched_sha256"])


def _already(entry: dict, source: bytes, patched: dict[str, str], valid: dict[str, set[str]]) -> None:
    """Mark <entry> as already installed: the engine counts a source at `patched_sha256` as done."""
    name = entry["hash"].upper()
    entry["patched_sha256"] = _sha(source)
    patched[name] = entry["patched_sha256"]
    valid.setdefault(name, set()).add(entry["patched_sha256"])


def block_runs(old: bytes, new: bytes) -> list[list[int]]:
    """``[offset, length]`` runs of the 16-byte blocks that differ between two same-size textures."""
    runs: list[list[int]] = []
    for offset in range(0, len(new), 16):
        if new[offset:offset + 16] != old[offset:offset + 16]:
            if runs and runs[-1][0] + runs[-1][1] == offset:
                runs[-1][1] += 16
            else:
                runs.append([offset, 16])
    return runs


def _regioned_atlases(reader: _Reader, bundle: Path, data: dict, entries: dict, overrides: dict,
                      patched: dict, valid: dict, log) -> list[str]:
    """Port every regioned atlas at the installed sprite table; returns the atlases refused."""
    import mobile_graphics as mg
    from sprite_table import REGION_SPRITE_ASSETS, sprite_rects

    refused: list[str] = []
    for atlas, table_asset in REGION_SPRITE_ASSETS.items():
        name = f"{atlas:016X}"
        entry = entries.get(name)
        source = reader.read(ATLAS_PACKAGE, atlas)
        if source is None:
            continue  # not in this installation: nothing to port, and the engine finds nothing either
        table = reader.read(ATLAS_PACKAGE, table_asset)
        if entry is not None:
            width, height = int(entry["width"]), int(entry["height"])
            sprites = sprite_rects(table, width, height) if table else None
            result = mg.port_atlas(source, entry, bundle, sprites, codec="bc7") if sprites else None
        elif atlas in mg.LABEL_ATLASES:
            result, entry = _title_atlas(reader, bundle, data, source, table, overrides, patched, valid, log)
        else:
            continue
        if result is None or len(result) != len(source):
            refused.append(name)
            if entry is not None and entry in data["graphics"]:
                data["graphics"].remove(entry)  # never left to land at the catalog's PC offsets
            log(f"{name}: refused at this installation's sprite table; dropped from the PC catalog")
        elif result == source:
            _already(entry, source, patched, valid)
        else:
            _set_entry(entry, source, result, block_runs(source, result), f"{name}.pc.blocks",
                       overrides, patched, valid)
    return refused


def _title_atlas(reader: _Reader, bundle: Path, data: dict, source: bytes, table: bytes | None,
                 overrides: dict, patched: dict, valid: dict, log) -> tuple[bytes | None, dict]:
    """The Secret Technique title atlas: its relayout as whole-file entries, then its labels drawn.

    Returns the drawn atlas (None when refused) and its new catalog entry. The relayout's entries are
    added only when the atlas itself is drawn, as on the mobile edition.
    """
    import card_titles
    import mobile_graphics as mg
    from sprite_table import REGION_SPRITE_ASSETS, sprite_rects

    atlas = card_titles.TITLE_ATLAS
    width, height = mg.LABEL_ATLASES[atlas]
    entry = {"hash": f"{atlas:016X}", "package": ATLAS_PACKAGE, "format": "bc7", "width": width,
             "height": height, "label": "Secret Technique titles"}
    layout = card_titles.load_layout(bundle)
    moved: dict[int, bytes] = {}
    sources: dict[int, bytes] = {}
    if layout is not None and table:
        def read(asset: int) -> bytes | None:
            raw = reader.read(ATLAS_PACKAGE, asset)
            if raw is not None:
                sources[asset] = raw
            return raw

        jobs = card_titles.relayout(read, layout)
        if jobs is None:
            log(f"package {ATLAS_PACKAGE}: the Secret Technique title layout does not match this "
                "installation; its titles stay as they are")
            return None, entry
        moved = jobs
        table = jobs.get(REGION_SPRITE_ASSETS[atlas], table)
    sprites = sprite_rects(table, width, height) if table else None
    result = mg.label_atlas(source, entry["hash"], bundle, sprites, codec="bc7") if sprites else None
    if result is None or len(result) != len(source):
        return None, entry
    for asset, new in sorted(moved.items()):
        moved_entry = {"hash": f"{asset:016X}", "package": ATLAS_PACKAGE,
                       "label": "Secret Technique title layout"}
        _set_entry(moved_entry, sources[asset], new, None, f"{asset:016X}.pc.asset", overrides, patched, valid)
        data["graphics"].append(moved_entry)
    data["graphics"].append(entry)
    return result, entry


def _label_textures(reader: _Reader, bundle: Path, data: dict, overrides: dict, patched: dict,
                    valid: dict, log) -> list[str]:
    """Add an entry for each standalone label this repo draws (``LABEL_TEXTURES``); returns those refused.

    The catalog has no entry for these, so each gets a new one in package `19`, its payload this
    repo's art for the language as RGBA32 rows. A texture this installation lacks gets no entry; one at
    another size is refused and left out.
    """
    import mobile_graphics as mg

    refused: list[str] = []
    for texture, (width, height, _name) in mg.LABEL_TEXTURES.items():
        name = f"{texture:016X}"
        source = reader.read(ATLAS_PACKAGE, texture)
        if source is None:
            continue
        result = mg.label_texture(source, name, bundle, codec="rgba32")
        if result is None:
            refused.append(name)
            log(f"{name}: not a {width}x{height} RGBA32 label in this installation; left out of the PC "
                "catalog")
            continue
        entry = {"hash": name, "package": ATLAS_PACKAGE, "format": "rgba32", "width": width,
                 "height": height, "label": "repo-drawn label"}
        data["graphics"].append(entry)
        if result == source:
            _already(entry, source, patched, valid)
        else:
            _set_entry(entry, source, result, block_runs(source, result), f"{name}.pc.blocks",
                       overrides, patched, valid)
    return refused


def _redrawn_payloads(reader: _Reader, bundle: Path, entries: dict, previous: dict[str, str],
                      patched: dict, valid: dict, log) -> None:
    """Re-hash every entry whose payload this language re-draws, from the installed original."""
    from sprite_table import REGION_SPRITE_ASSETS

    for name, entry in entries.items():
        if int(name, 16) in REGION_SPRITE_ASSETS or not entry.get("payload", "").endswith(".blocks"):
            continue
        own = bundle / entry["payload"]
        if not own.is_file():
            continue  # the English payload: the catalog's hashes already fit
        payload = own.read_bytes()
        if _sha(payload) == entry.get("payload_sha256"):
            continue
        source = reader.read(str(entry.get("package") or ""), int(name, 16))
        if source is None:
            continue
        entry["payload_sha256"] = _sha(payload)
        digest = _sha(source)
        if digest == previous.get(name):
            _already(entry, source, patched, valid)
            continue
        if digest != entry.get("source_sha256"):
            log(f"{name}: installed source matches neither the catalog nor the last install; the engine "
                "skips it")
            continue
        result = bytearray(source)
        cursor = 0
        for offset, length in entry["patch_ranges"]:
            result[offset:offset + length] = payload[cursor:cursor + length]
            cursor += length
        entry["patched_sha256"] = _sha(bytes(result))
        patched[name] = entry["patched_sha256"]
        valid.setdefault(name, set()).add(entry["patched_sha256"])


def _scripts(reader: _Reader, bundle: Path, data: dict, overrides: dict, patched: dict, valid: dict,
             log) -> None:
    """Add each Lua script `extra_text.rewrite_script` changes as a whole-file entry."""
    import extra_text
    from wxq_patch import adaptive

    catalog = None
    for asset in sorted(extra_text.SCRIPT_ASSETS):
        package_id = reader.holder(asset, extra_text.SCRIPT_PC_PACKAGE)
        if package_id is None:
            log(f"{asset:016X}: Lua script not in this installation")
            continue
        source = reader.read(package_id, asset)
        if catalog is None:
            catalog = adaptive.load_catalog(bundle)
        new = extra_text.rewrite_script(asset, source, catalog)
        if new is None or new == source:
            continue  # already carries this patcher's edit, or the literal is not there
        entry = {"hash": f"{asset:016X}", "package": package_id, "label": "Lua script"}
        _set_entry(entry, source, new, None, f"{asset:016X}.pc.lua", overrides, patched, valid)
        data["graphics"].append(entry)


def _link(source: Path, target: Path) -> bool:
    """Hard-link <source> to <target>, or copy it when the two are on different drives; True if linked."""
    try:
        os.link(source, target)
        return True
    except OSError:
        shutil.copy2(source, target)
        return False


def _write_stage(stage: Path, bundle: Path, english: Path, data: dict, overrides: dict[str, bytes],
                 record: dict) -> tuple[int, int]:
    """Write the stage beside <stage> and swap it in; returns the payloads (linked, copied)."""
    building = stage.with_name(stage.name + ".building")
    shutil.rmtree(building, ignore_errors=True)
    building.mkdir(parents=True)
    files: dict[str, Path] = {}
    for folder in (english, bundle) if bundle != english else (bundle,):
        for path in folder.iterdir():
            if path.is_file() and path.name not in BUNDLE_SKIP:
                files[path.name] = path  # the language's own payload wins over the English one
    linked = copied = 0
    for name, path in sorted(files.items()):
        if name in overrides:
            continue
        if _link(path, building / name):
            linked += 1
        else:
            copied += 1
    for name, payload in overrides.items():
        (building / name).write_bytes(payload)
    with gzip.open(building / "catalog.json.gz", "wt", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False)
    (building / STAGE_RECORD).write_text(json.dumps(record, indent=1), encoding="utf-8")
    old = stage.with_name(stage.name + ".old")
    shutil.rmtree(old, ignore_errors=True)
    if stage.exists():
        stage.rename(old)
    building.rename(stage)
    shutil.rmtree(old, ignore_errors=True)
    return linked, copied


def main() -> int:
    """`python tools/pc_catalog.py --game <PC root> --resources resources --language en --work <dir>`."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("--game", type=Path, required=True)
    parser.add_argument("--resources", type=Path, default=Path(__file__).resolve().parents[1] / "resources")
    parser.add_argument("--language", default="en")
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, default=None)
    args = parser.parse_args()
    sys.path.append(str(args.runtime or args.resources / "runtime"))
    version = (args.resources.parent / "VERSION").read_text(encoding="utf-8").strip()
    stage = build(args.game, args.resources, args.language, args.work, version=version)
    print(json.dumps({"catalog": str(stage.catalog), "cached": stage.cached, "patched": len(stage.patched),
                      "skipped": stage.skipped, "timings": {k: round(v, 2) for k, v in stage.timings.items()}},
                     indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
