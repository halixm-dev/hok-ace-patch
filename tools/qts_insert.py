"""Add new files to an existing QtsVFS package in place.

The record and its slots come from a package that already carries the asset - the APK's prime copy -
rather than from Tencent's own builder. That record holds every key the game derives (entry key, chunk
hash1), and beside them a descriptor token that depends on the content the record describes; nothing
checks that token, which ``tools/research/key_derivation_probe.py --stager`` measures on a phone-pushed
run, so a record that no longer matches its bytes is exactly what the in-place stager writes. The
chunking is inherited too, because a chunk index that does not exist yet would need a key only the game
derives: the chunk count is kept and the chunk size adjusted instead.

The payload is re-encoded the way ``device_extensions.write_assets`` encodes one - LZ4, or Oodle stored
blocks, because Python has no Oodle compressor - so an appended asset is larger than the builder's own
copy of it. The read-back below is what proves it still decodes.

The appended record is linked into both B-trees (``qts_relocate.Shard.append_slot`` / ``append_record``).
The target's existing asset records stay in place. Appended records gain one key per tree; tree pages
are updated, with only the measured single-root-leaf split supported. The appended asset is read back
through ``QtsPackage`` before this returns: that is
the only check this path has, because a record linked under the wrong key is invisible until the game
fails to find it.
"""
from __future__ import annotations

import struct
from pathlib import Path

from qts_relocate import Shard, chunk_size_for, read_raw

# Where write_assets writes them: the raw length sits 16 bytes into the 32-byte descriptor at entry+28,
# and the chunk size just before the file hash, at entry.head_size + 24.
RAW_LENGTH_AT = 28 + 16
CHUNK_SIZE_AT = 24


def _encode(piece: bytes, compression: int) -> bytes | None:
    """<piece> in the framing the entry's compression id expects, or None when it cannot be written.

    An unknown id, and an LZ4 block whose length lands exactly on the piece's, are both refusals. A
    chunk whose stored and decompressed sizes agree is how this format says *stored* -- that is the
    first thing ``qts_relocate.read_raw`` tests -- so an LZ4 block of that length would read back as
    the LZ4 bytes themselves. Tencent's own chunks are always LZ4-smaller or Oodle; a piece small or
    incompressible enough to hit this cannot be written without becoming ambiguous.
    """
    if compression == 1:
        import lz4.block

        payload = lz4.block.compress(piece, mode="high_compression", compression=12, store_size=False)
        return None if len(payload) == len(piece) else payload
    if compression == 4:
        import mobile_graphics as mg

        return mg.oodle_stored(piece)
    return None


def add_assets(package_id: str, target: Path, assets: list[dict], source, log) -> list[str]:
    """Add <assets> [{file_hash, raw}] to the single-shard package at <target>.

    <target> is a directory holding <package_id>.db and <package_id>_0.db; both are written in place.
    <source> is a ``QtsPackage`` that already carries every asset, and is only read.

    Returns the hashes written. An asset this pass cannot encode is left out and named in the log
    rather than failing the package: one rewrite that cannot be expressed must not cost the other
    ones, and a silently dropped one would revert that asset to the APK's revision with nothing said.
    """
    from wxq_patch.qtsvfs import QtsPackage

    source_slots = source.build_slot_map()
    source_index = source.index_path.read_bytes()
    index = Shard(target / f"{package_id}.db")
    shard = Shard(target / f"{package_id}_0.db")
    written: list[str] = []
    refused: list[str] = []
    for asset in assets:
        file_hash, raw = asset["file_hash"], asset["raw"]
        entry = source.entries[file_hash]
        slots = source_slots[file_hash]
        chunk_size = chunk_size_for(len(raw), entry.chunk_size, len(slots))
        encoded: list[tuple[int, bytes, bytes]] = []
        if chunk_size is not None:
            for chunk_id, start in enumerate(range(0, len(raw), chunk_size)):
                piece = raw[start:start + chunk_size]
                payload = _encode(piece, entry.compression)
                if payload is None:
                    break
                encoded.append((chunk_id, piece, payload))
        if len(encoded) != len(slots):
            refused.append(f"{file_hash:016X}")
            continue
        for chunk_id, piece, payload in encoded:
            shard.append_slot(slots[chunk_id], payload, len(piece))
        record = bytearray(source_index[entry.entry_offset:entry.entry_offset + entry.entry_size])
        struct.pack_into("<I", record, RAW_LENGTH_AT, len(raw))
        struct.pack_into("<I", record, entry.head_size + CHUNK_SIZE_AT, chunk_size)
        index.append_record(bytes(record), struct.unpack_from("<I", record, 12)[0])
        written.append(f"{file_hash:016X}")
    shard.save()
    index.save()

    staged = QtsPackage(target)
    slots = staged.build_slot_map()
    for asset in assets:
        if f"{asset['file_hash']:016X}" in written:
            if read_raw(staged, slots, asset["file_hash"]) != asset["raw"]:
                raise RuntimeError(f"package {package_id}: read-back differs for "
                                   f"{asset['file_hash']:016X}")
    log(f"package {package_id}: {len(written)} translated assets added from the APK"
        + (f"; {len(refused)} could not be encoded and stay in Chinese ({', '.join(refused)})"
           if refused else ""))
    return written
