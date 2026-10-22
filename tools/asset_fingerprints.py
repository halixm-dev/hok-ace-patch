"""SHA-256 of each asset's uncompressed bytes in a package, to tell which assets an install changed.

The pristine delta (`pristine_delta`) restores whole files. After an in-game update rewrites a file
the delta names, the file no longer matches the delta, and what decides whether the update's bytes can
stand in for pristine is whether any asset this patcher wrote is still in it. These fingerprints answer
that, asset by asset, for text tables and textures alike.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import BinaryIO


class UnreadablePackage(Exception):
    """A package whose index or assets will not read."""


def _open(package_dir: Path):
    from qts_relocate import install_btree_slot_map
    from wxq_patch.qtsvfs import QtsPackage

    install_btree_slot_map()
    try:
        package = QtsPackage(package_dir)
        return package, package.build_slot_map()
    except Exception as error:  # noqa: BLE001 - any parse failure means the package will not read
        raise UnreadablePackage(f"{package_dir.name}: {error}") from error


def package_assets(package_dir: Path, wanted: set[str] | None = None) -> dict[str, str | None]:
    """{asset hash (16 hex digits): SHA-256 of its uncompressed bytes, or None when they cannot be read}.

    <wanted> limits it to those asset hashes; an asset the package does not hold is left out.
    """
    from qts_relocate import read_raw

    package, slots = _open(package_dir)
    found: dict[str, str | None] = {}
    for file_hash in package.entries:
        name = f"{file_hash:016X}"
        if wanted is not None and name not in wanted:
            continue
        raw = read_raw(package, slots, file_hash)
        found[name] = hashlib.sha256(raw).hexdigest() if raw is not None else None
    return found


def _stored(package_dir: Path) -> dict[str, tuple]:
    """{asset hash: (compression, every chunk's id, sizes and stored bytes digest)}, read without decoding."""
    package, slots = _open(package_dir)
    found = {}
    handles: dict = {}
    try:
        for file_hash, entry in package.entries.items():
            chunks = []
            for chunk_id, slot in sorted(slots.get(file_hash, {}).items()):
                handle = handles.get(slot.shard_path) or handles.setdefault(slot.shard_path, open(slot.shard_path, "rb"))
                handle.seek(slot.payload_offset)
                chunks.append((chunk_id, slot.uncompressed_size,
                               hashlib.sha256(handle.read(slot.compressed_size)).hexdigest()))
            found[f"{file_hash:016X}"] = (entry.compression, tuple(chunks))
    finally:
        for handle in handles.values():
            handle.close()
    return found


def asset_bodies(package_dir: Path, wanted: set[str]) -> dict[str, tuple[bytes, int, list[tuple[int, bytes]]]]:
    """{asset hash: (index record, its head size, [(raw size, stored payload)] in chunk-id order)} for <wanted>.

    The stored chunks verbatim, as the B-tree reaches them, and the asset's whole index record: what
    `pristine_delta.restore_assets` writes back. An asset the package does not hold is left out.
    """
    package, slots = _open(package_dir)
    index = package.index_path.read_bytes()
    found = {}
    handles: dict[Path, BinaryIO] = {}
    try:
        for file_hash, entry in package.entries.items():
            name = f"{file_hash:016X}"
            if name not in wanted:
                continue
            chunks = []
            for _, slot in sorted(slots.get(file_hash, {}).items()):
                if slot.shard_path not in handles:
                    handles[slot.shard_path] = open(slot.shard_path, "rb")
                handle = handles[slot.shard_path]
                handle.seek(slot.payload_offset)
                chunks.append((slot.uncompressed_size, handle.read(slot.compressed_size)))
            found[name] = (index[entry.entry_offset:entry.entry_offset + entry.entry_size], entry.head_size, chunks)
    finally:
        for handle in handles.values():
            handle.close()
    return found


def changed_assets(pristine_dir: Path, staged_dir: Path) -> dict[str, list[str | None]]:
    """{asset hash: [pristine SHA-256 or None, staged SHA-256]} for every asset whose bytes the install changed.

    An asset the install added has no pristine SHA-256. An asset whose staged bytes cannot be read is
    left out: there is nothing to recognize it by later.
    """
    has_pristine = (pristine_dir / f"{pristine_dir.name}.db").is_file()
    stored_staged = _stored(staged_dir)
    stored_pristine = _stored(pristine_dir) if has_pristine else {}
    # Equal stored chunks are equal bytes, so only the rest is decoded.
    differing = {name for name, stored in stored_staged.items() if stored_pristine.get(name) != stored}
    staged = package_assets(staged_dir, differing)
    pristine = package_assets(pristine_dir, differing) if has_pristine else {}
    return {name: [pristine.get(name), digest] for name, digest in staged.items()
            if digest is not None and pristine.get(name) != digest}
