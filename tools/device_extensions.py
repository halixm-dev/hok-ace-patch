"""The passes that extend a patch beyond what the in-place stager could write.

* The catalog's texture edits are ported onto the device's ASTC textures. Changed textures are packed
  as raw Oodle blocks into the staged copy of their package under <output>. A package is never
  re-laid-out: new chunks would need lookup keys only the game's own builder can derive, so every
  asset keeps its chunk count and each changed chunk is appended to the shard and repointed in its
  B-tree by ``qts_relocate.Shard``.
* Text tables the stager could not fit are appended instead of being dropped (``relocate_text``).
  The per-mode card dictionaries keep their original chunk size by gaining chunks under measured
  native keys; ``repair_card_dictionaries`` also repairs an earlier patch's already-English copies.
  Strings the catalog has no table for are translated in place (``extra_text``).

A texture the codec cannot handle — an unreadable footprint, or a device revision whose geometry no
longer matches the catalog's record — is skipped, never raised. ``port_graphics`` reports those skips
and ``extend_graphics`` returns them in a list of their own, so a package whose every texture was
skipped is visible in the run's summary even though it contributes no output directory.
"""
from __future__ import annotations

import math
import shutil
from dataclasses import replace
from pathlib import Path

from qts_relocate import Shard, chunk_size_for

# The client reads a card dictionary only at its original 307200-byte chunk size: enlarging the chunk
# makes every label that dictionary feeds a raw `#XXXX...#` ref (device-measured on the Talent Card
# grid, then reported on Diamond Frenzy's Effect Cards). Each game mode carries its own copy, under
# its own ref prefix. A translation that outgrows the chunks therefore gets new ones, whose native
# keys (chunk hash1 by chunk index) were minted offline with the user-authorized Tencent-builder
# diagnostic: a throwaway one-asset build per dictionary reproduced every key the device already
# carries, the Talent keys included, before its new ones were taken. Normal runs need no DLL.
NATIVE_CHUNK_SIZE = 307200
NATIVE_CHUNK_KEYS = {
    0xC059EA43719099F1: (0x15A33357ECBFA5CC, 0x29157589AC92F155),  # #BE08 Talent Card, device-verified
    0x28D9F8B02CAA94E2: (0xDF3E388D824BA647, 0x106CE6E96D181721, 0xF1334A1AFDEF7A42),  # #23F7 Diamond Frenzy
    0xA336359CD92A858E: (0xEEDD3A39A715583D, 0x3703FE65783D648C, 0x7636E7F15BF9A4FA),  # #8E55
    0x666DC40230B31A30: (0x48E6394509FDD6AB, 0x379743B433B99DE1),  # #A40D
    0xF628F40CE23D983E: (0x50E3487DFFE72C54, 0x876D20F0AA4E7DC5),  # #0977
    0x42E8DB43608C2FF1: (0x87F061C69DD6E272, 0xDFC5B1EECDF2E589),  # #9344
    0x9BE81CD52C660467: (0xF9779D71928E5099, 0xBBD69700ACFCD33E),  # #BF5A
    0x27BBF8CDFFFA177F: (0x240D4B90C7A9FF1D, 0xCE2F0DC5C6A90FEE),  # #75CA
    0xC4E32B49AE8B7FFB: (0x53B319290B67B270, 0x3D3674505997D563),  # #1632
    0x5EB61A0269CD8550: (0xA3FC1EBFF30A1BE4, 0xADF8F4F47197142E),  # #31CF
    0x04F21C6735D0D555: (0x984A9068A9C3B0F0, 0xDF4EA49367E1E315),  # #BCDE
}


def _native_slots(file_hash: int, entry, chunks: dict, raw_size: int) -> dict | None:
    """Verified slot templates for a dictionary in NATIVE_CHUNK_KEYS, or None for an unmeasured layout."""
    keys = NATIVE_CHUNK_KEYS[file_hash]
    needed = math.ceil(raw_size / NATIVE_CHUNK_SIZE)
    if (entry.compression != 1 or not chunks or not 1 <= needed <= len(keys)
            or set(chunks) != set(range(len(chunks))) or len(chunks) > needed
            or any(slot.hash1 != keys[i] or slot.header_flags != 16
                   or slot.reserved != 0 for i, slot in chunks.items())):
        return None
    result = dict(chunks)
    for chunk_id in range(len(chunks), needed):
        result[chunk_id] = replace(chunks[0], chunk_id=chunk_id, hash1=keys[chunk_id])
    return result


def _package_output(package, output: Path) -> Path:
    """Staged copy of <package> under <output>, created from the game dump if absent."""
    target = output / package.package_id
    if not target.exists():
        target.mkdir(parents=True)
        for path in [package.index_path, *package.shard_paths]:
            shutil.copy2(path, target / path.name)
    return target


def _read_chunks(slots: dict) -> list[tuple[object, bytes]]:
    """The compressed payload of each chunk of one asset, in chunk order."""
    chunks = []
    for chunk_id in sorted(slots):
        slot = slots[chunk_id]
        with open(slot.shard_path, "rb") as handle:
            handle.seek(slot.payload_offset)
            chunks.append((slot, handle.read(slot.compressed_size)))
    return chunks


def write_assets(package_dir: Path, jobs: dict[int, bytes]) -> tuple[list[str], list[str]]:
    """Write new raw bytes for assets of the staged package at <package_dir>.

    Assets keep their chunk count and are re-cut when necessary, except the card dictionaries in
    NATIVE_CHUNK_KEYS: their measured native keys let them gain chunks and keep the original chunk
    size. Returns (written hashes, refused hashes).
    """
    import lz4.block
    import mobile_graphics as mg
    from wxq_patch.qtsvfs import QtsPackage

    package = QtsPackage(package_dir)
    slots = package.build_slot_map()
    shard = Shard(package.shard_paths[0])
    index = bytearray(package.index_path.read_bytes())
    written, refused = [], []
    for file_hash, raw in jobs.items():
        entry = package.entries[file_hash]
        original_slots = slots.get(file_hash, {})
        chunk_count = len(original_slots)
        chunk_size = chunk_size_for(len(raw), entry.chunk_size, chunk_count) if chunk_count else None
        templates = original_slots
        if file_hash in NATIVE_CHUNK_KEYS:
            templates = _native_slots(file_hash, entry, original_slots, len(raw))
            chunk_size = NATIVE_CHUNK_SIZE if templates is not None else None
        if entry.compression not in (1, 4) or chunk_size is None:
            refused.append(f"{file_hash:016X}")
            continue
        for chunk_id, start in enumerate(range(0, len(raw), chunk_size)):
            piece = raw[start:start + chunk_size]
            if entry.compression == 1:
                payload = lz4.block.compress(piece, mode="high_compression", compression=12, store_size=False)
            else:
                payload = mg.oodle_stored(piece)
            if chunk_id in original_slots:
                shard.relocate(original_slots[chunk_id], payload, len(piece))
            else:
                shard.append_slot(templates[chunk_id], payload, len(piece))
        # Descriptor (32 bytes at entry+28) keeps its integrity token; only the raw length changes.
        index[entry.entry_offset + 28 + 16:entry.entry_offset + 28 + 20] = len(raw).to_bytes(4, "little")
        # u32 chunk size sits just before the file hash (qtsvfs.parse_index: entry + head_size + 28 - 4).
        size_at = entry.entry_offset + entry.head_size + 24
        index[size_at:size_at + 4] = chunk_size.to_bytes(4, "little")
        written.append(f"{file_hash:016X}")
    shard.save()
    package.index_path.write_bytes(bytes(index))
    native = [h for h in jobs if h in NATIVE_CHUNK_KEYS and f"{h:016X}" in written]
    if native:
        from qts_relocate import read_raw

        checked = QtsPackage(package_dir)
        checked_slots = checked.build_slot_map()
        for file_hash in native:
            if read_raw(checked, checked_slots, file_hash) != jobs[file_hash]:
                raise RuntimeError(f"card dictionary {file_hash:016X} failed read-back after staging")
    return written, refused


def relocate_text(package, output: Path, dropped: dict[int, Path], log) -> tuple[list[str], list[str]]:
    """Append text tables the in-place stager could not fit; return (written, refused) hashes.

    The staged copy under <output> is what grows, so a package that staged nothing at all still ends
    up with the tables the stager could not fit -- built on the device's own copy of it.
    """
    written, refused = write_assets(_package_output(package, output),
                                    {h: path.read_bytes() for h, path in dropped.items()})
    log(f"package {package.package_id}: {len(written)} text tables moved to new space at the end of the package"
        + (f", {len(refused)} refused" if refused else ""))
    return written, refused


def repair_card_dictionaries(game: Path, catalog, output: Path, log,
                             skip: set[str] = frozenset()) -> tuple[list[dict], list[dict]]:
    """Repair an earlier patch's enlarged card dictionaries even when their strings are already English."""
    from wxq_patch import adaptive
    from wxq_patch.qtsvfs import QtsPackage
    from qts_relocate import read_raw

    wanted = [h for h in NATIVE_CHUNK_KEYS if h in catalog.known]
    if not wanted:
        return [], []
    discovered, _skipped = adaptive.discover(game, catalog)
    reports, skipped = [], []
    for source in discovered:
        if source.package_id in skip:
            continue
        staged = output / source.package_id
        package = QtsPackage(staged) if staged.exists() else source
        needs_repair = [file_hash for file_hash in wanted
                        if (entry := package.entries.get(file_hash)) is not None
                        and entry.chunk_size != NATIVE_CHUNK_SIZE]
        if not needs_repair:
            continue
        slots = package.build_slot_map()
        jobs, unmeasured = {}, []
        for file_hash in needs_repair:
            entry = package.entries[file_hash]
            raw = read_raw(package, slots, file_hash)
            if raw is None or _native_slots(file_hash, entry, slots.get(file_hash, {}), len(raw)) is None:
                unmeasured.append(f"{file_hash:016X}")
            else:
                jobs[file_hash] = raw
        if unmeasured:
            skipped.append({"package_id": source.package_id, "mode": "relocated-text",
                            "considered_count": len(unmeasured) + len(jobs), "dropped_count": len(unmeasured),
                            "dropped": unmeasured})
            log(f"package {source.package_id}: {len(unmeasured)} card dictionary layouts are unmeasured;"
                f" repair skipped ({', '.join(unmeasured)})")
        if not jobs:
            continue
        written, refused = write_assets(_package_output(source, output), jobs)
        if refused:
            raise RuntimeError(f"Verified card dictionary repair was refused: {', '.join(refused)}")
        reports.append({"package_id": source.package_id, "mode": "relocated-text",
                        "stage_report": {"status": "repaired", "replacement_count": len(written)}})
        log(f"package {source.package_id}: repaired {len(written)} card dictionary chunk layouts")
    return reports, skipped


def relocate_assets(package, output: Path, jobs: dict[int, bytes], log) -> int:
    """Write non-catalog translations for <package> into its staged copy under <output>."""
    written, refused = write_assets(_package_output(package, output), jobs)
    log(f"package {package.package_id}: {len(written)} extra assets translated"
        + (f", {len(refused)} refused" if refused else ""))
    return len(written)


def exclude_extra_chunks(package, replacements: Path, work: Path, log) -> tuple[Path, list[str]]:
    """Copy <replacements> without the tables that would need more chunks than the original has.

    New chunks need native lookup keys, and the stock stager would invent random ones. These tables
    are handled later by ``relocate_text``, usually by enlarging the chunk size. Always route the
    card dictionaries in NATIVE_CHUNK_KEYS through that pass too: they gain chunks under measured
    native keys and keep the original chunk size. Returns the pruned directory and the excluded hashes.
    """
    slots = package.build_slot_map()
    target = work / "safe-replacements" / package.package_id
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    excluded = []
    for path in replacements.glob("*.assets"):
        file_hash = int(path.stem, 16)
        entry = package.entries.get(file_hash)
        if entry and file_hash in slots and (file_hash in NATIVE_CHUNK_KEYS
                or math.ceil(path.stat().st_size / entry.chunk_size) > len(slots[file_hash])):
            excluded.append(path.stem.upper())
            continue
        shutil.copy2(path, target / path.name)
    if excluded:
        log(f"package {package.package_id}: {len(excluded)} tables outgrow their chunks; relocating them later")
    return target, excluded


def port_graphics(package, catalog, catalog_dir: Path, output: Path, log) -> dict:
    """Apply every catalog texture edit that exists in <package>.

    Returns ``{"considered": n, "written": n, "skipped": [hash, ...]}``. A package whose every edit
    is skipped writes nothing and creates no output directory, but still reports what it skipped:
    a texture the codec refuses is otherwise invisible in the run's summary.
    A newly copied package uses the source's chunk offsets with paths retargeted to the copy;
    an existing staged package gets a fresh slot scan because earlier passes may have relocated it.
    """
    import mobile_graphics as mg
    from qts_relocate import read_raw
    from sprite_table import REGION_SPRITE_ASSETS, sprite_rects
    from wxq_patch.qtsvfs import QtsPackage

    graphics = mg.catalog_graphics(catalog.graphics)
    wanted = [file_hash for file_hash in package.entries if file_hash in graphics]
    if not wanted:
        return {"considered": 0, "written": 0, "skipped": []}
    source_slots = package.build_slot_map()
    pending: list[tuple[int, list, bytes]] = []
    skipped: list[str] = []
    for file_hash in wanted:
        chunks = _read_chunks(source_slots.get(file_hash, {}))
        raw = b"".join(mg.oodle_decompress(payload, slot.uncompressed_size) for slot, payload in chunks)
        graphic = graphics[file_hash]
        # A regioned atlas is ported at the device's own sprite rects, read from this package each run;
        # without them english_raw refuses it rather than port at the PC offsets.
        sprites = None
        sprite_asset = REGION_SPRITE_ASSETS.get(int(graphic["hash"], 16))
        if sprite_asset is not None and sprite_asset in package.entries:
            table = read_raw(package, source_slots, sprite_asset)
            if table:
                sprites = sprite_rects(table, int(graphic["width"]), int(graphic["height"]))
        new = mg.english_raw(raw, graphic, catalog_dir, sprites)
        if new is None or len(new) != len(raw):
            skipped.append(f"{file_hash:016X}")
        elif new != raw:  # equal means already English (patcher re-run)
            pending.append((file_hash, chunks, new))
    written = len(pending)
    if pending:
        # Only copy the (large) package when something actually changes.
        fresh_copy = not (output / package.package_id).exists()
        target = QtsPackage(_package_output(package, output))
        if fresh_copy:
            # _package_output just copied these exact bytes. Offsets stay the same; point
            # each slot at the copy. A pre-existing output may already have relocated chunks
            # and must be scanned afresh instead. Nothing is retained after this write.
            target_slots = {
                file_hash: {slot.chunk_id: replace(slot, shard_path=target.package_dir / slot.shard_path.name)
                            for slot, _payload in chunks}
                for file_hash, chunks, _new in pending
            }
        else:
            target_slots = target.build_slot_map()
        shard = Shard(target.shard_paths[0])
        for file_hash, chunks, new in pending:
            cursor = 0
            for slot, _payload in chunks:
                piece = new[cursor:cursor + slot.uncompressed_size]
                cursor += slot.uncompressed_size
                shard.relocate(target_slots[file_hash][slot.chunk_id], mg.oodle_stored(piece), len(piece))
        shard.save()
    log(f"package {package.package_id}: {written} textures translated"
        + (f", {len(skipped)} of {len(wanted)} skipped ({', '.join(skipped)})" if skipped else ""))
    return {"considered": len(wanted), "written": written, "skipped": skipped}


def extend_graphics(game: Path, catalog_dir: Path, output: Path, log,
                    skip: set[str] = frozenset(),
                    candidates: frozenset[int] = frozenset()) -> tuple[list[dict], list[dict]]:
    """Run the texture pass and the extra-text pass over every discovered package.

    Packages are discovered afresh rather than taken from the text scan's plans: a texture-heavy
    package usually stages no text at all, so the scan never lists it.

    <skip> holds the packages a rebuild already replaced whole; this pass builds on the device's own
    container, so touching one of those would apply edits to a package that no longer matches it.

    <candidates> is the device cycle's enablement for the extra-text pass, which is the only thing
    here that has one.

    Returns two lists: the summary entries for packages that wrote something, and the entries for
    packages whose every texture was skipped. The second list is kept out of ``packages`` on purpose --
    it has no output directory behind it, and the installer pushes by directory, so a skipped-only
    package must not look like a result.
    """
    from wxq_patch import adaptive

    catalog = adaptive.load_catalog(catalog_dir)
    packages, _skipped = adaptive.discover(game, catalog)
    reports = []
    skipped = []
    for package in packages:
        if package.package_id in skip:
            continue
        report = port_graphics(package, catalog, catalog_dir, output, log)
        if report["written"]:
            reports.append({
                "package_id": package.package_id,
                "mode": "graphics",
                "stage_report": {"status": "relocated", "replacement_count": report["written"]},
            })
        elif report["skipped"]:
            skipped.append({
                "package_id": package.package_id,
                "mode": "graphics",
                "skipped_count": len(report["skipped"]),
                "considered_count": report["considered"],
                "skipped": report["skipped"],
            })
    from extra_text import extend_text
    from languages import for_catalog

    reports += extend_text(game, catalog, output, log, skip, candidates=candidates,
                           terms=for_catalog(catalog_dir).resource_terms)
    return reports, skipped
