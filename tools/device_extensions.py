"""The passes that extend a patch beyond what the in-place stager could write.

* The catalog's texture edits are ported onto the device's ASTC textures. Changed textures are packed
  as raw Oodle blocks into the staged copy of their package under <output>. A package is never
  re-laid-out: new chunks would need lookup keys only the game's own builder can derive, so every
  asset keeps its chunk count and each changed chunk is appended to the shard and repointed in its
  B-tree by ``qts_relocate.Shard``.
* Text tables the stager could not fit are appended instead of being dropped (``relocate_text``).
  The Talent Card dictionary keeps its original chunk size using a measured native second-chunk
  key; ``repair_talent_dictionary`` also repairs an earlier patch's already-English copy.
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

# Native identity keys measured offline with the authorized Tencent-builder diagnostic, then
# device-tested on 1.4.0.2. Enlarging this dictionary's chunk makes every Talent Card label a raw
# ref. Keep 307200-byte chunks and append the measured second slot; normal runs need no DLL.
TALENT_DICTIONARY = 0xC059EA43719099F1
TALENT_CHUNK_SIZE = 307200
TALENT_CHUNK_KEYS = (0x15A33357ECBFA5CC, 0x29157589AC92F155)


def _talent_slots(entry, chunks: dict, raw_size: int) -> dict | None:
    """Verified slot templates for this dictionary, or None for an unmeasured layout."""
    needed = math.ceil(raw_size / TALENT_CHUNK_SIZE)
    if (entry.compression != 1 or needed not in (1, 2)
            or set(chunks) not in ({0}, {0, 1}) or len(chunks) > needed
            or any(slot.hash1 != TALENT_CHUNK_KEYS[i] or slot.header_flags != 16
                   or slot.reserved != 0 for i, slot in chunks.items())):
        return None
    result = dict(chunks)
    if needed == 2 and 1 not in result:
        result[1] = replace(chunks[0], chunk_id=1, hash1=TALENT_CHUNK_KEYS[1])
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

    Assets keep their chunk count and are re-cut when necessary, except the Talent Card dictionary:
    its measured native second-chunk key lets it keep the original chunk size. Returns
    (written hashes, refused hashes).
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
        if file_hash == TALENT_DICTIONARY:
            templates = _talent_slots(entry, original_slots, len(raw))
            chunk_size = TALENT_CHUNK_SIZE if templates is not None else None
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
    if f"{TALENT_DICTIONARY:016X}" in written:
        from qts_relocate import read_raw

        checked = QtsPackage(package_dir)
        if read_raw(checked, checked.build_slot_map(), TALENT_DICTIONARY) != jobs[TALENT_DICTIONARY]:
            raise RuntimeError("Talent Card dictionary failed read-back after staging")
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


def repair_talent_dictionary(game: Path, catalog, output: Path, log,
                             skip: set[str] = frozenset()) -> tuple[list[dict], list[dict]]:
    """Repair an earlier patch's enlarged dictionary even when its strings are already English."""
    from wxq_patch import adaptive
    from wxq_patch.qtsvfs import QtsPackage
    from qts_relocate import read_raw

    if TALENT_DICTIONARY not in catalog.known:
        return [], []
    discovered, _skipped = adaptive.discover(game, catalog)
    reports, skipped = [], []
    for source in discovered:
        if source.package_id in skip or TALENT_DICTIONARY not in source.entries:
            continue
        staged = output / source.package_id
        package = QtsPackage(staged) if staged.exists() else source
        entry = package.entries[TALENT_DICTIONARY]
        if entry.chunk_size == TALENT_CHUNK_SIZE:
            continue
        slots = package.build_slot_map()
        raw = read_raw(package, slots, TALENT_DICTIONARY)
        if raw is None or _talent_slots(entry, slots.get(TALENT_DICTIONARY, {}), len(raw)) is None:
            skipped.append({"package_id": source.package_id, "mode": "relocated-text",
                            "considered_count": 1, "dropped_count": 1,
                            "dropped": [f"{TALENT_DICTIONARY:016X}"]})
            log(f"package {source.package_id}: Talent Card dictionary layout is unmeasured; repair skipped")
            continue
        written, refused = write_assets(_package_output(source, output), {TALENT_DICTIONARY: raw})
        if refused:
            raise RuntimeError("Verified Talent Card dictionary repair was refused")
        reports.append({"package_id": source.package_id, "mode": "relocated-text",
                        "stage_report": {"status": "repaired", "replacement_count": len(written)}})
        log(f"package {source.package_id}: repaired Talent Card dictionary chunk layout")
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
    Talent Card dictionary through that pass too: it uses a measured second-chunk key and restores
    the original chunk size. Returns the pruned directory and the excluded hashes.
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
        if entry and file_hash in slots and (file_hash == TALENT_DICTIONARY
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
    """
    import mobile_graphics as mg
    from wxq_patch.qtsvfs import QtsPackage

    wanted = [file_hash for file_hash in package.entries if file_hash in catalog.graphics]
    if not wanted:
        return {"considered": 0, "written": 0, "skipped": []}
    source_slots = package.build_slot_map()
    pending: list[tuple[int, list, bytes]] = []
    skipped: list[str] = []
    for file_hash in wanted:
        chunks = _read_chunks(source_slots.get(file_hash, {}))
        raw = b"".join(mg.oodle_decompress(payload, slot.uncompressed_size) for slot, payload in chunks)
        new = mg.english_raw(raw, catalog.graphics[file_hash], catalog_dir)
        if new is None or len(new) != len(raw):
            skipped.append(f"{file_hash:016X}")
        elif new != raw:  # equal means already English (patcher re-run)
            pending.append((file_hash, chunks, new))
    written = len(pending)
    if pending:
        # Only copy the (large) package when something actually changes.
        target = QtsPackage(_package_output(package, output))
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

    reports += extend_text(game, catalog, output, log, skip, candidates=candidates)
    return reports, skipped
