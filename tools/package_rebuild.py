"""Rebuild override packages whose translatable content partly lives only in the APK.

On Android the game data has two layers: the APK's built-in (prime) packages, and the downloaded
override packages under files/QtsVFSCache, which hold only what changed since the APK was built. The
game reads override first. Measured on 1.4.0.1, package 1 (text tables) keeps 2492 of its 2873 assets
- 298 of them catalog tables that translate, 51095 records, the chessplayer names among them - only in
the APK, package 1050016095 keeps 71 of the catalog's textures there, and package 21 keeps
`7B4CC5DF48336D2D`, the wide Central Plains panel its Card Info view draws. The in-place stager can
only rewrite assets that already sit in the override package, and the texture pass reads the same
layer, so neither ever saw those.

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
#
# 21 is the package that would carry the wide Central Plains panel (`7B4CC5DF48336D2D`, only in the
# APK), and it is deliberately absent. Its rebuild works - 4863 assets, 48.7 MB, the panel translated,
# and the game mounts it - but on the phone it costs a card: the Factionless hero Yixing then draws as
# the game's grey placeholder, art and faction bar missing, while Tencent's own copy of the package
# draws it correctly. The cost of laying a package out is the *override* copy's size, not the APK's
# (4866 assets, about 40 MB, against the APK's 511 MB), so cost is not the reason to leave 21 alone.
REBUILD_PACKAGES = ("1", "1050016095")


def extract_prime(apk: Path, package_ids, target: Path, index_only: bool = False) -> dict[str, Path]:
    """Copy the APK's built-in packages <package_ids> to <target>/<id>/; return the folders found.

    QtsPackage derives the index filename from the directory name, so each package's files have to
    sit in a folder named exactly after its id.

    <package_ids> None copies every package of the APK, which is what the scan for prime-only content
    needs. <index_only> copies just <id>.db: enough to list a package's entries, without pulling the
    hundreds of MB of shards that most of them hold.
    """
    found = {}
    with zipfile.ZipFile(apk) as archive:
        for info in archive.infolist():
            if not info.filename.startswith(PRIME_PREFIX) or info.is_dir():
                continue
            package_id, _, name = info.filename[len(PRIME_PREFIX):].partition("/")
            if package_ids is not None and package_id not in package_ids:
                continue
            if "/" in name or not name.endswith(".db"):
                continue
            if index_only and name != f"{package_id}.db":
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
    transform.tables = set(catalog.known)
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
    without_bytes: list[int] = []
    device_entries = device.entries if device else {}
    for file_hash, entry in device_entries.items():
        if file_hash in device_slots:
            raw = read_raw(device, device_slots, file_hash)
        elif file_hash in prime_slots:
            # Listed in the override index without data (flag word set): the bytes are the APK's.
            raw = read_raw(prime, prime_slots, file_hash)
        else:
            # Listed in the override index with no bytes in either layer. Nothing can carry it into
            # the rebuilt package, and the game cannot read it from the original either - an index
            # entry pointing at nothing - so leaving it out changes nothing it can load.
            without_bytes.append(file_hash)
            continue
        if not raw:
            # Bytes that exist but will not decode: the builder cannot store a zero-byte file either,
            # so the package takes the in-place path rather than failing here.
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
        new = transform(file_hash, raw) if raw else None
        graphics = file_hash in transform.graphics
        considered += graphics
        if not new:
            # Falsy covers both "no change" and empty bytes; the builder cannot store an empty file,
            # and the device-entry loop above treats the same condition as unreadable.
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
        + (f", {len(without_bytes)} entries hold no bytes in either layer" if without_bytes else "")
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
        "entries_without_bytes": sorted(f"{file_hash:016X}" for file_hash in without_bytes),
    }


def add_prime_only(game: Path, apk: Path, transform, builder, work: Path, output: Path,
                   skip: set[str], log) -> tuple[list[dict], list[dict]]:
    """Insert translated catalog assets that only exist in the APK into the override package.

    A package whose catalog content exists only in the APK cannot be patched in place, and rebuilding
    it whole lays the container out again, which changes its index shape and every shard offset. These
    records are appended instead (``qts_insert.add_assets``), so the package keeps the shape the game
    already reads and gains one translated asset.

    <skip> holds the packages a rebuild replaced whole: their staged copy no longer matches the
    device's container, and the rebuild already carried the prime-only assets into it.

    Returns (entries for packages that gained something, entries for packages that could not be
    appended to). The second list is not a result -- no output directory stands behind it -- but it
    names the assets that stay Chinese, which the summary cannot say any other way. Each of its
    entries carries the assets the pass would have written and how many of those are textures, so a
    caller can report what stays Chinese as images and as tables rather than as one total.
    """
    from device_extensions import _package_output
    from qts_builder import entry_flag
    from qts_insert import add_assets
    from qts_relocate import TreeFull, read_raw
    from wxq_patch.qtsvfs import QtsPackage

    root = game / "WXQ_Data" / "Package" / "builtin"
    indexes = extract_prime(apk, None, work / "prime-index", index_only=True)
    entries: list[dict] = []
    skipped: list[dict] = []

    def texture_count(hashes) -> int:
        return sum(file_hash in transform.graphics for file_hash in hashes)

    def note(package_id: str, reason: str, assets: int, textures: int) -> None:
        skipped.append({"package_id": package_id, "mode": "added-from-apk", "reason": reason,
                        "assets": assets, "textures": textures})
        log(f"package {package_id}: {assets} translated assets stay in Chinese ({reason})")

    for package_id, index_dir in sorted(indexes.items()):
        device_dir = root / package_id
        if package_id in skip or not (device_dir / f"{package_id}_0.db").is_file():
            continue
        try:
            wanted = set(QtsPackage(index_dir).entries)
        except Exception:  # noqa: BLE001 - an index that will not read lists nothing to add
            continue
        wanted &= transform.graphics | transform.tables
        if not wanted:
            continue
        try:
            device = QtsPackage(device_dir)
        except Exception as error:  # noqa: BLE001 - a package that will not read is not ours to patch
            log(f"package {package_id}: device package will not read ({error}); nothing appended")
            continue
        wanted -= set(device.entries)
        if not wanted:
            continue
        # A staged copy an earlier pass or an earlier run made holds the same assets, and appending a
        # record it already has would index the same B-tree key twice. Only what it still lacks is
        # worth appending; an asset that is already there is not a result of this run.
        staged_dir = output / package_id
        if staged_dir.is_dir():
            try:
                wanted -= set(QtsPackage(staged_dir).entries)
            except Exception as error:  # noqa: BLE001 - someone else's staged copy: leave it alone
                log(f"package {package_id}: staged copy will not read ({error}); nothing appended")
                continue
            if not wanted:
                continue
        try:
            prime_dir = extract_prime(apk, {package_id}, work / "prime")[package_id]
        except KeyError:
            log(f"package {package_id}: the APK index lists it but the package is not there")
            continue

        prime = QtsPackage(prime_dir)
        slots = prime.build_slot_map()
        prime_index = prime.index_path.read_bytes()
        assets = []
        for file_hash in sorted(wanted):
            raw = read_raw(prime, slots, file_hash) if file_hash in slots else None
            new = transform(file_hash, raw) if raw else None
            if new is None:
                continue
            entry = prime.entries[file_hash]
            assets.append({"file_hash": file_hash, "raw": new, "chunk_size": entry.chunk_size,
                           "flag": entry_flag(prime_index, entry)})
        if not assets:
            continue
        textures = texture_count(a["file_hash"] for a in assets)
        if len(device.shard_paths) != 1:
            # add_assets writes <id>_0.db by name, so a package split over several shards is not
            # something to guess at. Named after the transform, because the count in the summary has
            # to be what this pass would have written, not what it hoped to.
            note(package_id, f"its device copy has {len(device.shard_paths)} shards", len(assets), textures)
            continue

        created = not staged_dir.is_dir()
        target = _package_output(device, output)
        try:
            add_assets(package_id, target, assets, builder, work, log)
        except TreeFull as error:
            # The staged copy holds an untouched copy of the package; the installer pushes by
            # directory, so it must not stay there looking like a result.
            if created:
                shutil.rmtree(target, ignore_errors=True)
            note(package_id, str(error), len(assets), textures)
            continue
        entries.append({
            "package_id": package_id,
            "mode": "added-from-apk",
            "source_package": str(prime_dir),
            "fit_summary": None,
            "stage_report": {"status": "verified", "replacement_count": len(assets)},
            "assets": len(assets),
            "textures": textures,
        })
    return entries, skipped
