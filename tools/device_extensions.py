"""Second patch pass: port the catalog's texture edits onto the device's ASTC textures.

Changed textures are written into the staged copy of their package under <output>, packed as raw
Oodle blocks. A package is never re-laid-out: new chunks would need lookup keys only the game's own
builder can derive, so every asset keeps its chunk count and each changed chunk is appended to the
shard and repointed in its B-tree by ``qts_relocate.Shard``.

A texture the codec cannot handle — an unreadable footprint, or a device revision whose geometry no
longer matches the catalog's record — is skipped, never raised. ``port_graphics`` reports those skips
and ``extend_graphics`` returns them in a list of their own, so a package whose every texture was
skipped is visible in the run's summary even though it contributes no output directory.

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


def extend_graphics(game: Path, catalog_dir: Path, output: Path, log) -> tuple[list[dict], list[dict]]:
    """Apply texture edits across every discovered package.

    Packages are discovered afresh rather than taken from the text scan's plans: a texture-heavy
    package usually stages no text at all, so the scan never lists it.

    Returns two lists: the summary entries for packages that wrote something, and the entries for
    packages whose every edit was skipped. The second list is kept out of ``packages`` on purpose --
    it has no output directory behind it, and the installer pushes by directory, so a skipped-only
    package must not look like a result.
    """
    from wxq_patch import adaptive

    catalog = adaptive.load_catalog(catalog_dir)
    packages, _skipped = adaptive.discover(game, catalog)
    reports = []
    skipped = []
    for package in packages:
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
    return reports, skipped
