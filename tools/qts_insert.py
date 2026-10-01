"""Add new files to an existing QtsVFS package in place.

Tencent's builder builds a throw-away package holding just the new files; its index record and chunk
slots carry every key the game derives (entry key, chunk hash1, integrity tokens), so nothing here has
to derive one. They are appended to the target package's index and shard and linked into the
respective B-trees (``qts_relocate.Shard.insert_key``). Used where rebuilding the whole package is not
an option: a rebuild lays the container out again, which changes its index shape and every shard
offset, and the game reads override before prime, so a package that keeps its shape keeps working.

The target's own records, page table and tree pages are never rewritten -- it gains bytes at the end
and one key per tree. The appended asset is read back through ``QtsPackage`` before this returns: that
is the only check there is, because a record linked under the wrong key is invisible until the game
fails to find it.
"""
from __future__ import annotations

import struct
from pathlib import Path

from qts_relocate import Shard, read_raw


def add_assets(package_id: str, target: Path, assets: list[dict], builder, work: Path, log) -> None:
    """Add <assets> [{file_hash, raw, flag, chunk_size}] to the single-shard package at <target>.

    <target> is a directory holding <package_id>.db and <package_id>_0.db; both are written in place.
    <builder> is a ``qts_builder.Builder``, whose output is read rather than kept.
    """
    from wxq_patch.qtsvfs import QtsPackage

    mini = QtsPackage(builder.build(package_id, assets, work / f"insert-{package_id}"))
    mini_slots = mini.build_slot_map()
    mini_index = mini.index_path.read_bytes()
    mini_shard = mini.shard_paths[0].read_bytes()

    index = Shard(target / f"{package_id}.db")
    shard = Shard(target / f"{package_id}_0.db")
    for asset in assets:
        file_hash = asset["file_hash"]
        for _chunk_id, slot in sorted(mini_slots[file_hash].items()):
            size = struct.unpack_from("<I", mini_shard, slot.slot_offset + 8)[0]
            shard.append_record(mini_shard[slot.slot_offset:slot.slot_offset + size], slot.hash1 & 0xFFFFFFFF)
        entry = mini.entries[file_hash]
        record = mini_index[entry.entry_offset:entry.entry_offset + entry.entry_size]
        index.append_record(record, struct.unpack_from("<I", record, 12)[0])
    shard.save()
    index.save()

    staged = QtsPackage(target)
    slots = staged.build_slot_map()
    for asset in assets:
        if read_raw(staged, slots, asset["file_hash"]) != asset["raw"]:
            raise RuntimeError(f"package {package_id}: read-back differs for {asset['file_hash']:016X}")
    log(f"package {package_id}: {len(assets)} translated assets added from the APK")
