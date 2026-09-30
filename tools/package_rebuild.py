"""Rebuild override packages whose translatable content partly lives only in the APK.

On Android the game data has two layers: the APK's built-in (prime) packages, and the downloaded
override packages under files/QtsVFSCache, which hold only what changed since the APK was built. The
game reads override first. Measured on 1.4.0.1, package 1 (text tables) keeps 2492 of its 2873 assets
- 298 of them catalog tables that translate, 51095 records, the chessplayer names among them - only in
the APK, and package 1050016095 keeps 71 of the catalog's textures there. The in-place stager can only
rewrite assets that already sit in the override package, and the texture pass reads the same layer, so
neither ever saw those.

A rebuilt override package holds every asset of the original override package (translated where the
transform changes it, byte-identical otherwise) plus the prime-only assets the transform changes.
Prime-only assets that need no change are left out, so the game keeps reading them from the APK rather
than carrying a second copy of each.
"""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

PRIME_PREFIX = "assets/bin/Data/Package/builtin/"
# The packages measured to keep translatable content that the override package lacks. Every other
# package keeps the in-place path: everything it needs is already downloaded, and a rebuild lays the
# whole container out again, which means recompressing hundreds of MB for nothing.
REBUILD_PACKAGES = ("1", "1050016095")


def extract_prime(apk: Path, package_ids, target: Path) -> dict[str, Path]:
    """Copy the APK's built-in packages <package_ids> to <target>/<id>/; return the folders found.

    QtsPackage derives the index filename from the directory name, so each package's files have to
    sit in a folder named exactly after its id.
    """
    found = {}
    with zipfile.ZipFile(apk) as archive:
        for info in archive.infolist():
            if not info.filename.startswith(PRIME_PREFIX) or info.is_dir():
                continue
            package_id, _, name = info.filename[len(PRIME_PREFIX):].partition("/")
            if package_id not in package_ids or "/" in name or not name.endswith(".db"):
                continue
            folder = target / package_id
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / name
            if not path.exists() or path.stat().st_size != info.file_size:
                with archive.open(info) as source, path.open("wb") as out:
                    shutil.copyfileobj(source, out, 1 << 20)
            found[package_id] = folder
    return found


def make_transform(catalog, catalog_dir: Path, log, refused: set[int]):
    """Build the per-asset decision both layers share.

    ``transform(file_hash, raw) -> translated bytes, or None when the asset needs no change``.

    <refused> receives the file hash of every catalog texture this device copy cannot take - the
    codec returned nothing, or an image whose geometry no longer matches the catalog's record. The
    caller must read it per package, because "left alone" and "refused" are the same return value:
    a texture that is already English is done, while one the codec refused is a skip, and only the
    second belongs in the run's report.
    """
    import extra_text
    import mobile_graphics as mg
    import pb_text
    from resource_tokens import expand_tokens
    from wxq_patch import adaptive

    def transform(file_hash: int, raw: bytes) -> bytes | None:
        if file_hash in catalog.known:
            try:
                new, counts = adaptive.translate_table(raw, file_hash, catalog)
            except Exception as error:  # noqa: BLE001 - not a language table after all
                log(f"  {file_hash:016X}: table not translated ({error})")
                return None
            if not counts.get("translated"):
                return None
            # translate_table keeps the catalog's {Energy}-style tokens, so a rebuilt table needs the
            # same expansion the in-place staging path applies to its replacements.
            return expand_tokens(bytes(new), log)
        if file_hash in catalog.graphics:
            new = mg.english_raw(raw, catalog.graphics[file_hash], catalog_dir)
            if new is None or len(new) != len(raw):
                refused.add(file_hash)
                return None
            return new if new != raw else None
        if file_hash in extra_text.SAFE_ASSETS and pb_text.CJK.search(raw.decode("utf-8", "ignore")):
            try:
                new, changed = pb_text.rewrite(raw, extra_text.translator_for(file_hash, catalog))
            except pb_text.NotMessage:
                return None
            return expand_tokens(new, log) if changed else None
        return None

    transform.graphics = set(catalog.graphics)
    return transform


def rebuild_package(package_id: str, device_dir: Path, prime_dir: Path, transform, builder, work: Path,
                    output: Path, log, refused: set[int] | None = None) -> dict | None:
    """Stage a rebuilt override package <package_id> into <output>/<id>/; None when nothing changes.

    <refused> is cleared on entry and read at the end, so a caller reusing one transform across
    packages does not have to reset it between them.
    """
    from qts_builder import entry_flag, entry_words, finalize, package_node
    from qts_relocate import read_raw
    from wxq_patch.qtsvfs import QtsPackage

    if refused is None:
        refused = set()
    refused.clear()

    device = QtsPackage(device_dir) if (device_dir / f"{package_id}.db").is_file() else None
    prime = QtsPackage(prime_dir)
    template = package_node(device.index_path) if device else None
    device_index = device.index_path.read_bytes() if device else b""
    prime_index = prime.index_path.read_bytes()
    device_slots = device.build_slot_map() if device and device.shard_paths else {}
    prime_slots = prime.build_slot_map()

    assets, words = [], {}
    translated = added = textures = considered = 0
    device_entries = device.entries if device else {}
    for file_hash, entry in device_entries.items():
        if file_hash in device_slots:
            raw = read_raw(device, device_slots, file_hash)
        elif file_hash in prime_slots:
            # Listed in the override index without data (flag word set): the bytes are the APK's.
            raw = read_raw(prime, prime_slots, file_hash)
        else:
            raw = None
        if raw is None:
            log(f"package {package_id}: cannot read {file_hash:016X}; keeping the in-place patch path")
            return None
        new = transform(file_hash, raw)
        graphics = file_hash in transform.graphics
        considered += graphics
        textures += new is not None and graphics
        translated += new is not None
        assets.append({"file_hash": file_hash, "raw": new or raw, "flag": entry_flag(device_index, entry),
                       "chunk_size": entry.chunk_size})
        words[file_hash] = entry_words(device_index, entry)
    for file_hash, entry in prime.entries.items():
        if file_hash in device_entries or file_hash not in prime_slots:
            continue
        raw = read_raw(prime, prime_slots, file_hash)
        new = transform(file_hash, raw) if raw is not None else None
        graphics = file_hash in transform.graphics
        considered += graphics
        if new is None:
            continue
        added += 1
        textures += graphics
        assets.append({"file_hash": file_hash, "raw": new, "flag": entry_flag(prime_index, entry),
                       "chunk_size": entry.chunk_size})
        words[file_hash] = entry_words(prime_index, entry)
    skipped_textures = sorted(f"{file_hash:016X}" for file_hash in refused)
    if not added and not translated:
        log(f"package {package_id}: nothing to translate")
        return None

    built = builder.build(package_id, assets, work / f"rebuild-{package_id}")
    fixed = finalize(built, package_id, {a["file_hash"] for a in assets}, template, words)

    # Read everything back through the same code path the game data goes through.
    staged = QtsPackage(built)
    slots = staged.build_slot_map()
    for asset in assets:
        if read_raw(staged, slots, asset["file_hash"]) != asset["raw"]:
            raise RuntimeError(f"package {package_id}: read-back differs for {asset['file_hash']:016X}")
    if template is not None and package_node(staged.index_path)[4:] != template[4:]:
        raise RuntimeError(f"package {package_id}: package node was not preserved")

    target = output / package_id
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    for path in built.glob("*.db"):
        shutil.copy2(path, target / path.name)
    log(f"package {package_id}: rebuilt with {len(assets)} assets "
        f"({translated} downloaded assets translated, {added} translated from the APK"
        + (f", {len(skipped_textures)} of {considered} textures skipped" if skipped_textures else "")
        + f"; {fixed['removed_records']} builder records dropped)")
    return {
        "package_id": package_id,
        "mode": "rebuilt",
        "source_package": str(device_dir),
        "fit_summary": None,
        "stage_report": {"status": "rebuilt", "replacement_count": translated + added},
        "assets": len(assets),
        "translated_downloaded": translated,
        "added_from_apk": added,
        "textures": textures,
        "textures_considered": considered,
        "textures_skipped": skipped_textures,
    }
