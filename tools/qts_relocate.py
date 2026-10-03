"""Read a QtsVFS shard's chunk payloads, and grow it: append slots and repoint or extend its B-tree.

Shard layout (reverse engineered from Android 1.3.0.4 packages):
  header   +0x08 u32 data end, +0x0C u32 file size, +0x30 u32 offset of the active page table
  page table  6 x u32 header, then entries [logical, active physical, spare physical, ...] x 6 u32.
               Header words 1 and 2 are both the row count. A logical page owns the physical pair
               (L, L + 0x1000) -- one active, one holding the superseded copy -- and both copies carry
               the same content and the same self word, so the pair is transparent to a reader that
               goes through the table. A logical id is the page's own offset, so a page added at the end
               of the file takes an id equal to that offset. The root is the *logical* page named at
               +0x10, translated through the table like any other. Measured on the dump's 278 packages:
               268 have one row, and the rest up to 54; header words 3 and 4 vary with the shape and the
               row's last three words are not understood (see below).
  B-tree pages (0x1000 bytes): keys u32[510], values u32[510], tail [self logical id, ?, next logical
               id, type<<16 | count]. kind: leaf type 3 maps low 32 bits of a chunk's hash1 -> slot
               offset; internal type 2 stores each child's lower bound in the keys and the child's
               logical id in the values, the first bound being 0. A leaf's `next` chains the leaves in
               key order and is 0xffffffff at the end.
  slot     +0 u32 self offset, +4 i32 -1, +8 u32 slot size, +12 u64 hash1, +20 u32 flags,
           +24 u32 payload length + 4, +28 u32 raw size, +32 payload,
           trailer at align4(32 + payload): u64 file hash, u32 reserved, u32 chunk id (16 bytes)
Relocating never changes keys, so the B-tree ordering stays valid. Appending a record does add a key,
which is inserted into the leaf the search reaches; a full leaf supports only the measured root split
described below, and other full shapes are reported. Appending a *slot* is the same
operation for a chunk the shard does not hold yet, which is how an asset is copied in from a package
that already carries it (``qts_insert.add_assets``): the slot's own hash1, flags, file hash and chunk id
come from that package, so the key inserted is the one the game derives.

Splitting a full leaf is implemented for one shape: a tree whose root is also its only leaf, grown into
two leaves plus an internal root by ``split_root_leaf``. That is the shape packages 1 and 1050016095
need, and it is the shape Tencent's own builder produces -- package 1's index splits from one leaf of
404 keys into two of 351 plus an internal root at a new logical page 0x5000 -- and the split reproduces
a builder-made tree's *page table byte for byte* (``artifacts/device-run/leaf_split_check.py``). Three
of the page-table row's six words and the tail's second word take values that are consistent for a
given shape and derivable from nothing visible, so they are written by pattern from two independent
Tencent-built trees of that same three-row shape; a shape that has not been measured is reported as
``TreeFull`` rather than guessed at. A leaf that fills while the root is already internal is therefore
still refused, which is what growing a shard past two leaves needs.
"""
from __future__ import annotations

import math
import struct
from pathlib import Path

PAGE = 0x1000
KEYS_PER_PAGE = 510
LEAF_TYPE = 3
FILE_GROWTH = 0x4000
# A chunk size is a whole number of these; write_assets rounds a re-cut chunk size up to one.
CHUNK_ALIGN = 0x1000
# Entry compression ids that hold LZ4 block data. 1 is what the packages this patch has always read
# use; 9 is the same LZ4 block data behind a 12-byte-longer entry descriptor, written by whatever
# updater produced the newer override packages (packages 19, 20 and 21 carry it). Measured on those
# three: every sampled chunk of both ids decodes to exactly its declared size, while codec 4 (Oodle)
# refuses LZ4 outright. Treating 9 as unknown left 1285 of package 21's entries unreadable.
LZ4_CODECS = (1, 9)
# A chunk whose payload opens with this is a Zstandard frame, whatever its entry declares: the framing
# is per chunk, and one asset can mix them (7CCE483D88B236CF is an LZ4 chunk followed by a zstd one).
# Twelve assets of package 21 are framed this way, and codec 4 is the id they are *not* stored under
# as often as not, so the payload, not the entry, is what says how to read it.
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"


class TreeFull(RuntimeError):
    """A B-tree leaf holds KEYS_PER_PAGE keys, and this code does not split pages."""


class Shard:
    def __init__(self, path: Path):
        self.path = path
        self.data = bytearray(path.read_bytes())
        self.data_end = self._u32(0x08)
        self.leaves = self._active_leaf_pages()
        self.relocated = 0

    def _u32(self, offset: int) -> int:
        return struct.unpack_from("<I", self.data, offset)[0]

    def _active_leaf_pages(self) -> list[int]:
        table = self._u32(0x30)
        count = self._u32(table + 4)
        pages = []
        for i in range(count):
            logical, active = struct.unpack_from("<II", self.data, table + 24 + i * 24)
            tail_type = self._u32(active + PAGE - 4) >> 16
            if tail_type == LEAF_TYPE and self._u32(active + PAGE - 16) == logical:
                pages.append(active)
        if not pages:
            raise RuntimeError(f"{self.path.name}: no active B-tree leaf pages found")
        return pages

    def _repoint(self, key: int, old_offset: int, new_offset: int) -> None:
        hits = 0
        for page in self.leaves:
            count = self._u32(page + PAGE - 4) & 0xFFFF
            keys = struct.unpack_from(f"<{count}I", self.data, page)
            for i, value in enumerate(keys):
                value_at = page + (KEYS_PER_PAGE + i) * 4
                if value == key and self._u32(value_at) == old_offset:
                    struct.pack_into("<I", self.data, value_at, new_offset)
                    hits += 1
        if hits == 0:
            raise RuntimeError(f"{self.path.name}: slot {old_offset:#x} (key {key:08X}) not in the B-tree")

    def _slot_bytes(self, offset: int, slot, payload: bytes, raw_size: int,
                    reserved: int | None = None) -> bytes:
        """One slot record, ready to write at <offset>."""
        trailer = (32 + len(payload) + 3) & ~3
        buffer = bytearray(trailer + 16)
        struct.pack_into("<IiIQIII", buffer, 0, offset, -1, trailer + 16, slot.hash1,
                         slot.header_flags, len(payload) + 4, raw_size)
        buffer[32:32 + len(payload)] = payload
        struct.pack_into("<QII", buffer, trailer, slot.file_hash,
                         slot.reserved if reserved is None else reserved, slot.chunk_id)
        return bytes(buffer)

    def relocate(self, slot, payload: bytes, raw_size: int, reserved: int | None = None) -> int:
        """Append a new slot for <slot>'s chunk holding <payload>; return its offset."""
        offset = (self.data_end + 3) & ~3
        buffer = self._slot_bytes(offset, slot, payload, raw_size, reserved)
        end = offset + len(buffer)
        if len(self.data) < end:
            self.data.extend(b"\0" * (end - len(self.data)))
        self.data[offset:end] = buffer
        self._repoint(slot.hash1 & 0xFFFFFFFF, slot.slot_offset, offset)
        self.data_end = end
        self.relocated += 1
        return offset

    def append_slot(self, slot, payload: bytes, raw_size: int, reserved: int | None = None) -> int:
        """Append a slot for a chunk this shard does not hold yet, keyed as the game keys it.

        <slot> comes from a package that already carries the asset, so it supplies the hash1 the game
        derives beside the file hash, reserved word and chunk id its trailer needs. Unlike
        ``relocate``'s key, this one is new to the shard, so it is inserted rather than repointed.
        """
        return self.append_record(self._slot_bytes(0, slot, payload, raw_size, reserved),
                                  slot.hash1 & 0xFFFFFFFF)

    def _active_page(self, logical: int) -> int:
        """Physical page the page table at +0x30 currently maps <logical> to."""
        table = self._u32(0x30)
        for i in range(self._u32(table + 4)):
            row_logical, active = struct.unpack_from("<II", self.data, table + 24 + i * 24)
            if row_logical == logical:
                return active
        raise RuntimeError(f"{self.path.name}: page {logical:#x} not in the page table")

    def _table(self) -> tuple[int, int]:
        """(the active page table's offset, its rows in use)."""
        table = self._u32(0x30)
        return table, self._u32(table + 4)

    def _write_page(self, offset: int, keys, values, self_id: int, next_id: int, kind: int) -> None:
        """One whole B-tree page: keys, values, then the tail."""
        page = bytearray(PAGE)
        struct.pack_into(f"<{len(keys)}I", page, 0, *keys)
        struct.pack_into(f"<{len(values)}I", page, KEYS_PER_PAGE * 4, *values)
        struct.pack_into("<4I", page, PAGE - 16, self_id, 0xFFFFFFFF, next_id,
                         (kind << 16) | len(keys))
        self.data[offset:offset + PAGE] = page

    def split_root_leaf(self) -> None:
        """Grow a tree whose root is also its only leaf into two leaves and an internal root.

        The keys are halved: the lower half stays in the root's own logical page, the upper half takes
        the next free logical page, and the one after that becomes the internal root -- the shape
        Tencent's builder produces for the same tree. A logical id is the page's own offset, so the two
        new pages come from `+0x18` and are written into the slots the format already reserves between
        the page region and the page table: no byte of the file moves, so nothing the game holds is
        disturbed, and the file does not even grow.

        Both copies of every logical page are written identically. Which copy the table calls active is
        unobservable either way, and it is set to match a builder-made tree of this shape.

        The three page-table row words that are not derivable from anything visible are written by
        pattern from two independent Tencent-built trees of the same three-row shape (package 1's index
        and package 4's, which agree field for field). Raises TreeFull for any shape not measured --
        a root that is already internal, or a table with more than the one row -- so an unmeasured
        layout is reported rather than guessed at.
        """
        root_logical = self._u32(0x10)
        root = self._active_page(root_logical)
        tail = struct.unpack_from("<4I", self.data, root + PAGE - 16)
        table, rows = self._table()
        if tail[3] >> 16 != LEAF_TYPE or rows != 1:
            raise TreeFull(f"{self.path.name}: only a single-leaf tree can be split "
                           f"(root type {tail[3] >> 16}, {rows} table rows)")
        if 24 + (rows + 2) * 24 > self._u32(0x34):
            raise TreeFull(f"{self.path.name}: the page table has no room for the two new pages")

        count = tail[3] & 0xFFFF
        keys = struct.unpack_from(f"<{count}I", self.data, root)
        values = struct.unpack_from(f"<{count}I", self.data, root + KEYS_PER_PAGE * 4)
        half = count // 2
        pages_end = self._u32(0x18)
        leaf_logical = pages_end
        root_page = pages_end + 2 * PAGE

        for offset in (root_logical, root_logical + PAGE):
            self._write_page(offset, keys[:half], values[:half], root_logical, leaf_logical, LEAF_TYPE)
        for offset in (leaf_logical, leaf_logical + PAGE):
            self._write_page(offset, keys[half:], values[half:], leaf_logical, 0xFFFFFFFF, LEAF_TYPE)
        for offset in (root_page, root_page + PAGE):
            self._write_page(offset, (0, keys[half]), (root_logical, leaf_logical), root_page,
                             0xFFFFFFFF, 2)
        struct.pack_into("<6I", self.data, table + 24, root_logical, root_logical + PAGE,
                         root_logical, 1, 0xFFFFFFFF, 0xFFFFFFFF)
        struct.pack_into("<6I", self.data, table + 48, leaf_logical, leaf_logical + PAGE,
                         leaf_logical, 0xFFFFFFFF, 0, 2)
        struct.pack_into("<6I", self.data, table + 72, root_page, root_page, root_page + PAGE,
                         1, 0xFFFFFFFF, 0xFFFFFFFF)
        struct.pack_into("<6I", self.data, table, 0x20, 3, 3, 1, self._u32(table + 16), 0x20)
        struct.pack_into("<II", self.data, 0x10, root_page, self._u32(0x14))
        struct.pack_into("<I", self.data, 0x18, pages_end + 4 * PAGE)
        self.leaves = self._active_leaf_pages()

    def insert_key(self, key: int, value: int) -> None:
        """Add <key> -> <value> to the leaf the B-tree search reaches.

        The root page is at +0x10. Internal pages are type 2 and hold each child's lowest key, so the
        child to follow is the last one whose lowest key is not above <key>. A leaf that is already
        full is split when it is also the root -- growing the tree by one leaf and an internal root --
        and reported otherwise, because splitting a leaf under an existing internal page rewrites the
        pages that page's bounds live in.
        """
        while True:
            page = self._active_page(self._u32(0x10))
            while True:
                tail = self._u32(page + PAGE - 4)
                count = tail & 0xFFFF
                keys = struct.unpack_from(f"<{count}I", self.data, page)
                if tail >> 16 == LEAF_TYPE:
                    break
                child = max((i for i, low in enumerate(keys) if low <= key), default=0)
                page = self._active_page(self._u32(page + (KEYS_PER_PAGE + child) * 4))
            if count < KEYS_PER_PAGE:
                break
            self.split_root_leaf()
        values = struct.unpack_from(f"<{count}I", self.data, page + KEYS_PER_PAGE * 4)
        at = next((i for i, existing in enumerate(keys) if existing > key), count)
        keys = keys[:at] + (key,) + keys[at:]
        values = values[:at] + (value,) + values[at:]
        struct.pack_into(f"<{count + 1}I", self.data, page, *keys)
        struct.pack_into(f"<{count + 1}I", self.data, page + KEYS_PER_PAGE * 4, *values)
        struct.pack_into("<I", self.data, page + PAGE - 4, (tail & 0xFFFF0000) | (count + 1))
        self.leaves = self._active_leaf_pages()

    def append_record(self, record: bytes, key: int) -> int:
        """Append a self-describing record (+0 self offset, +8 size) and index it under <key>."""
        offset = (self.data_end + 3) & ~3
        buffer = bytearray(record)
        struct.pack_into("<I", buffer, 0, offset)
        end = offset + len(buffer)
        if len(self.data) < end:
            self.data.extend(b"\0" * (end - len(self.data)))
        self.data[offset:end] = buffer
        self.data_end = end
        self.insert_key(key, offset)
        return offset

    def save(self) -> None:
        size = max(self._u32(0x0C), (self.data_end + FILE_GROWTH - 1) // FILE_GROWTH * FILE_GROWTH)
        if len(self.data) < size:
            self.data.extend(b"\0" * (size - len(self.data)))
        struct.pack_into("<II", self.data, 0x08, self.data_end, size)
        self.path.write_bytes(bytes(self.data[:size]))


def chunk_size_for(length: int, chunk_size: int, chunk_count: int) -> int | None:
    """Chunk size that splits <length> bytes into exactly <chunk_count> chunks.

    Keeping the count is what lets rewritten bytes land on chunks the package already has: a chunk
    index that does not exist yet would need a lookup key only the game derives. ``write_assets`` and
    ``qts_insert.add_assets`` both re-cut against this for that reason.
    """
    if math.ceil(length / chunk_size) == chunk_count:
        return chunk_size
    for candidate in (
        (math.ceil(length / chunk_count) + CHUNK_ALIGN - 1) // CHUNK_ALIGN * CHUNK_ALIGN,
        math.ceil(length / chunk_count),
    ):
        if candidate and math.ceil(length / candidate) == chunk_count:
            return candidate
    return None


def btree_offsets(shard: Shard) -> dict[int, set[int]]:
    offsets: dict[int, set[int]] = {}
    for page in shard.leaves:
        count = shard._u32(page + PAGE - 4) & 0xFFFF
        for i, key in enumerate(struct.unpack_from(f"<{count}I", shard.data, page)):
            offsets.setdefault(key, set()).add(shard._u32(page + (KEYS_PER_PAGE + i) * 4))
    return offsets


def read_raw(package, slots, file_hash: int) -> bytes | None:
    """The asset's uncompressed bytes, or None when there are none to read.

    None covers both an asset with no chunks at all and a chunk framing we cannot follow. A chunk whose
    compressed and uncompressed sizes match is stored as it is; a payload opening with the Zstandard
    magic is a zstd frame; otherwise the entry's compression id says which codec wrote it, 1 and 9
    being LZ4 and 4 Oodle. A payload that will not decompress returns None rather than raising — the
    caller then leaves the asset alone, which is what the game already shows for it.
    """
    import lz4.block
    import ooz
    import zstandard

    entry = package.entries[file_hash]
    chunks = slots.get(file_hash)
    if not chunks:
        return None
    zstd = None
    raw = bytearray()
    for chunk_id in sorted(chunks):
        slot = chunks[chunk_id]
        with open(slot.shard_path, "rb") as handle:
            handle.seek(slot.payload_offset)
            payload = handle.read(slot.compressed_size)
        try:
            if slot.compressed_size == slot.uncompressed_size:
                raw += payload  # chunk stored uncompressed
            elif payload[:4] == ZSTD_MAGIC:
                if zstd is None:
                    zstd = zstandard.ZstdDecompressor()
                raw += zstd.decompress(payload, max_output_size=slot.uncompressed_size)
            elif entry.compression in LZ4_CODECS:
                raw += lz4.block.decompress(payload, uncompressed_size=slot.uncompressed_size)
            elif entry.compression == 4:
                raw += ooz.decompress(payload, slot.uncompressed_size)
            else:
                return None
        except Exception:  # noqa: BLE001 - unknown framing: leave the asset alone
            return None
    return bytes(raw)


def install_btree_slot_map() -> None:
    """Make QtsPackage.build_slot_map follow the shard B-tree, like the game does.

    The stock scanner walks slot headers and can return a superseded copy of a relocated chunk,
    which would make a patcher re-run read the old Chinese data.
    """
    from wxq_patch import qtsvfs

    if getattr(qtsvfs.QtsPackage.build_slot_map, "_btree_aware", False):
        return
    original = qtsvfs.QtsPackage.build_slot_map

    def build_slot_map(self):
        slot_map = original(self)
        if len(self.shard_paths) != 1:
            return slot_map
        try:
            live = btree_offsets(Shard(self.shard_paths[0]))
        except Exception:
            return slot_map
        stale = [(fh, cid) for fh, chunks in slot_map.items() for cid, slot in chunks.items()
                 if slot.slot_offset not in live.get(slot.hash1 & 0xFFFFFFFF, ())]
        if stale:
            by_offset = {slot.slot_offset: slot for slot in qtsvfs.iter_chunk_slots(self.shard_paths[0])}
            for fh, cid in stale:
                old = slot_map[fh][cid]
                for offset in live.get(old.hash1 & 0xFFFFFFFF, ()):
                    candidate = by_offset.get(offset)
                    if candidate and candidate.file_hash == fh and candidate.chunk_id == cid:
                        slot_map[fh][cid] = candidate
                        break
        return slot_map

    build_slot_map._btree_aware = True
    qtsvfs.QtsPackage.build_slot_map = build_slot_map
