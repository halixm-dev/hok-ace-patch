"""Second patch pass: port the catalog's texture edits onto the device's ASTC textures.

Changed textures are written into the staged copy of their package under <output>, packed as raw
Oodle blocks. A package is never re-laid-out: new chunks would need lookup keys only the game's own
builder can derive, so every asset keeps its chunk count and each changed chunk is appended to the
shard and repointed in its B-tree by ``qts_relocate.Shard``.

The text passes the reference implementation also carries — relocated text tables and the extra-text
/ romanised-name coverage — are not part of this pass.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from qts_relocate import Shard


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


def port_graphics(package, catalog, catalog_dir: Path, output: Path, log) -> int:
    """Apply every catalog texture edit that exists in <package>; return textures written."""
    import mobile_graphics as mg
    from wxq_patch.qtsvfs import QtsPackage

    wanted = [file_hash for file_hash in package.entries if file_hash in catalog.graphics]
    if not wanted:
        return 0
    source_slots = package.build_slot_map()
    pending: list[tuple[int, list, bytes]] = []
    unsupported = 0
    for file_hash in wanted:
        chunks = _read_chunks(source_slots.get(file_hash, {}))
        raw = b"".join(mg.oodle_decompress(payload, slot.uncompressed_size) for slot, payload in chunks)
        new = mg.english_raw(raw, catalog.graphics[file_hash], catalog_dir)
        if new is None or len(new) != len(raw):
            unsupported += 1
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
        + (f", {unsupported} skipped (format not supported)" if unsupported else ""))
    return written


def extend_graphics(game: Path, catalog_dir: Path, output: Path, log) -> list[dict]:
    """Apply texture edits across every discovered package; return summary entries.

    Packages are discovered afresh rather than taken from the text scan's plans: a texture-heavy
    package usually stages no text at all, so the scan never lists it.
    """
    from wxq_patch import adaptive

    catalog = adaptive.load_catalog(catalog_dir)
    packages, _skipped = adaptive.discover(game, catalog)
    reports = []
    for package in packages:
        count = port_graphics(package, catalog, catalog_dir, output, log)
        if count:
            reports.append({
                "package_id": package.package_id,
                "mode": "graphics",
                "stage_report": {"status": "relocated", "replacement_count": count},
            })
    return reports
