"""The passes that extend a patch beyond what the in-place stager could write.

* The catalog's texture edits are ported onto the device's ASTC textures. Changed textures are packed
  as raw Oodle blocks into the staged copy of their package under <output>. A package is never
  re-laid-out: new chunks would need lookup keys only the game's own builder can derive, so every
  asset keeps its chunk count and each changed chunk is appended to the shard and repointed in its
  B-tree by ``qts_relocate.Shard``.
* Text tables the stager could not fit are appended the same way instead of being dropped
  (``relocate_text``), and the strings the catalog has no table for are translated in place
  (``extra_text``).

A texture the codec cannot handle — an unreadable footprint, or a device revision whose geometry no
longer matches the catalog's record — is skipped, never raised. ``port_graphics`` reports those skips
and ``extend_graphics`` returns them in a list of their own, so a package whose every texture was
skipped is visible in the run's summary even though it contributes no output directory.
"""
from __future__ import annotations

import math
import shutil
from pathlib import Path

from qts_relocate import Shard

# Chunk sizes are aligned to this in the game's own packages, so a grown chunk keeps the shape.
CHUNK_ALIGN = 0x1000


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


def _chunk_size_for(length: int, chunk_size: int, chunk_count: int) -> int | None:
    """Chunk size that splits <length> bytes into exactly <chunk_count> chunks."""
    if math.ceil(length / chunk_size) == chunk_count:
        return chunk_size
    for candidate in (
        (math.ceil(length / chunk_count) + CHUNK_ALIGN - 1) // CHUNK_ALIGN * CHUNK_ALIGN,
        math.ceil(length / chunk_count),
    ):
        if candidate and math.ceil(length / candidate) == chunk_count:
            return candidate
    return None


def write_assets(package_dir: Path, jobs: dict[int, bytes]) -> tuple[list[str], list[str]]:
    """Write new raw bytes for assets of the staged package at <package_dir>.

    New chunks would need lookup keys only the game's own builder can derive, so every asset keeps
    its chunk count; when the raw size changes, the entry's chunk size is adjusted instead and the
    chunks are re-cut to that size. Returns (written hashes, refused hashes).
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
        chunk_count = len(slots.get(file_hash, {}))
        chunk_size = _chunk_size_for(len(raw), entry.chunk_size, chunk_count) if chunk_count else None
        if entry.compression not in (1, 4) or chunk_size is None:
            refused.append(f"{file_hash:016X}")
            continue
        for chunk_id, start in enumerate(range(0, len(raw), chunk_size)):
            piece = raw[start:start + chunk_size]
            if entry.compression == 1:
                payload = lz4.block.compress(piece, mode="high_compression", compression=12, store_size=False)
            else:
                payload = mg.oodle_stored(piece)
            shard.relocate(slots[file_hash][chunk_id], payload, len(piece))
        # Descriptor (32 bytes at entry+28) keeps its integrity token; only the raw length changes.
        index[entry.entry_offset + 28 + 16:entry.entry_offset + 28 + 20] = len(raw).to_bytes(4, "little")
        # u32 chunk size sits just before the file hash (qtsvfs.parse_index: entry + head_size + 28 - 4).
        size_at = entry.entry_offset + entry.head_size + 24
        index[size_at:size_at + 4] = chunk_size.to_bytes(4, "little")
        written.append(f"{file_hash:016X}")
    shard.save()
    package.index_path.write_bytes(bytes(index))
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


def relocate_assets(package, output: Path, jobs: dict[int, bytes], log) -> int:
    """Write non-catalog translations for <package> into its staged copy under <output>."""
    written, refused = write_assets(_package_output(package, output), jobs)
    log(f"package {package.package_id}: {len(written)} extra assets translated"
        + (f", {len(refused)} refused" if refused else ""))
    return len(written)


def exclude_extra_chunks(package, replacements: Path, work: Path, log) -> tuple[Path, list[str]]:
    """Copy <replacements> without the tables that would need more chunks than the original has.

    New chunks need lookup keys the game derives itself (the PC patcher asks the native QtsVFS
    builder for them), and the stock stager would invent random ones. These tables are handled later
    by ``relocate_text``, which keeps the chunk count and enlarges the chunk size instead. Returns
    the pruned directory and the excluded hashes.
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
        if entry and file_hash in slots and math.ceil(path.stat().st_size / entry.chunk_size) > len(slots[file_hash]):
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
                    skip: set[str] = frozenset()) -> tuple[list[dict], list[dict]]:
    """Run the texture pass and the extra-text pass over every discovered package.

    Packages are discovered afresh rather than taken from the text scan's plans: a texture-heavy
    package usually stages no text at all, so the scan never lists it.

    <skip> holds the packages a rebuild already replaced whole; this pass builds on the device's own
    container, so touching one of those would apply edits to a package that no longer matches it.

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

    reports += extend_text(game, catalog, output, log, skip)
    return reports, skipped
