"""Read a QtsVFS shard's chunk payloads, and grow it: append slots and repoint or extend its B-tree.

Shard layout (reverse engineered from Android 1.3.0.4 packages):
  header   +0x08 u32 data end, +0x0C u32 file size, +0x30 u32 offset of the active page table
  page table  6 x u32 header [capacity, rows, rows, root row, 5, capacity], then rows
               [logical, active physical, spare physical, parent | black << 31, left, right] x 6 u32:
               a red-black tree over the rows in logical order (``_red_black``; all 814 tables of the
               1.6.0.1 and 1.7.0.1 layers, 1 to 82 rows). A logical page owns the physical pair
               (L, L + 0x1000) -- one active, one holding the superseded copy -- so the pair is
               transparent to a reader that goes through the table. A logical id is the page's own
               offset, and new ones come from +0x18, which Tencent's trees advance by one pair per page
               and set to 0xffffffff once the region before the page table is used up. The root is the
               *logical* page named at +0x10, translated through the table like any other.
  B-tree pages (0x1000 bytes): keys u32[510], values u32[510], tail [self logical id, ?, next logical
               id, type<<16 | count]. kind: leaf type 3 maps low 32 bits of a chunk's hash1 -> slot
               offset; internal type 2 stores each child's lower bound in the keys and the child's
               logical id in the values, the first bound being 0. A leaf's `next` chains the leaves in
               key order and is 0xffffffff at the end.
  slot     +0 u32 self offset, +4 i32 -1, +8 u32 slot size, +12 u64 hash1, +20 u32 flags,
           +24 u32 payload length + 4, +28 u32 raw size, +32 payload,
           trailer at align4(32 + payload): u64 file hash, u32 reserved, u32 chunk id (16 bytes)
Relocating never changes keys, so the B-tree ordering stays valid. Appending a record does add a key,
which is inserted into the leaf the search reaches; a full leaf is split in the two shapes described
below, and other full shapes are reported. Appending a *slot* is the same
operation for a chunk the shard does not hold yet, which is how an asset is copied in from a package
that already carries it (``qts_insert.add_assets``): the slot's own hash1, flags, file hash and chunk id
come from that package, so the key inserted is the one the game derives.

Splitting a full leaf is implemented for the one tree shape Tencent's packages have, an internal root
over leaves. ``split_root_leaf`` grows a tree whose root is also its only leaf into two leaves plus an
internal root, reproducing a builder-made tree's page table byte for byte (package 1's index: one leaf
of 404 keys into two of 351 plus an internal root at logical 0x5000). ``split_leaf`` splits a full leaf
under that root into two, which is what package 1 needs from data 1.7.0.1; its 4-row result equals
package 4's Tencent-built page table byte for byte. A second internal level is reported as ``TreeFull``
rather than guessed at (``tools/research/check_btree_split.py``).
"""
from __future__ import annotations

import math
import struct
from pathlib import Path

PAGE = 0x1000
KEYS_PER_PAGE = 510
LEAF_TYPE = 3
FILE_GROWTH = 0x4000
# Bound comparison memory and keep scattered metadata edits from rewriting payloads.
WRITE_BLOCK = 64 * 1024
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
    """A B-tree leaf holds KEYS_PER_PAGE keys, and the tree is in a shape this code does not split."""


def _red_black(count: int) -> tuple[int, list[tuple[int, int, int]]]:
    """(root, [(parent | black << 31, left, right)]) of a red-black tree of rows 0..count-1, inserted in order.

    The textbook insert (fix-up by recolouring and rotation); the rows arrive in increasing key order,
    so each new one starts as the rightmost leaf. NIL is 0xffffffff, which also reads as black.
    """
    nil = 0xFFFFFFFF
    parent, left, right, black = [nil] * count, [nil] * count, [nil] * count, [False] * count
    root = nil

    def rotate(x: int, down: list[int], up: list[int]) -> None:
        # rotate(x, right, left) is a left rotation; the mirror swaps the two lists.
        nonlocal root
        y = down[x]
        down[x] = up[y]
        if up[y] != nil:
            parent[up[y]] = x
        parent[y] = parent[x]
        if parent[x] == nil:
            root = y
        elif x == left[parent[x]]:
            left[parent[x]] = y
        else:
            right[parent[x]] = y
        up[y] = x
        parent[x] = y

    for z in range(count):
        y, x = nil, root
        while x != nil:
            y, x = x, right[x]
        parent[z] = y
        if y == nil:
            root = z
        else:
            right[y] = z
        while parent[z] != nil and not black[parent[z]]:
            p = parent[z]
            g = parent[p]
            near, far = (left, right) if p == left[g] else (right, left)
            uncle = far[g]
            if uncle != nil and not black[uncle]:
                black[p] = black[uncle] = True
                black[g] = False
                z = g
                continue
            if z == far[p]:
                z = p
                rotate(z, far, near)
                p = parent[z]
                g = parent[p]
            black[p] = True
            black[g] = False
            rotate(g, near, far)
        black[root] = True
    return root, [((parent[i] | (0x80000000 if black[i] else 0)) & nil, left[i], right[i])
                  for i in range(count)]


class Shard:
    def __init__(self, path: Path):
        self.path = path
        with path.open("rb") as handle:
            self.data = bytearray(handle.seek(0, 2))
            handle.seek(0)
            with memoryview(self.data) as buffer:
                position = 0
                while position < len(buffer):
                    count = handle.readinto(buffer[position:])
                    if not count:
                        raise RuntimeError(f"{path.name}: shard shrank while reading")
                    position += count
            if handle.read(1):
                raise RuntimeError(f"{path.name}: shard grew while reading")
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

    def _write_table(self, rows: list[tuple[int, int, int]]) -> None:
        """Write the active page table's rows ``(logical, active, spare)`` and their red-black words.

        The table is a red-black tree over its rows, ordered by logical id: a row's last three words are
        its parent (bit 31 set when the row is black), left and right row index, NIL being 0xffffffff,
        and header word 3 is the root's row index. Rows are kept in logical order, which is also the
        order the pages were allocated in, so the words are the tree that inserting the rows one by one
        in that order builds (``_red_black``). Measured on every page table of the 1.6.0.1 and 1.7.0.1
        layers, 814 of them with 1 to 82 rows: every word equals it. Header words 0, 4 and 5 (the
        capacity, 5 and the capacity again) are kept.
        """
        table, _ = self._table()
        if 24 + len(rows) * 24 > self._u32(0x34):
            raise TreeFull(f"{self.path.name}: the page table has no room for {len(rows)} rows")
        rows = sorted(rows)
        root, links = _red_black(len(rows))
        for i, (row, link) in enumerate(zip(rows, links)):
            struct.pack_into("<6I", self.data, table + 24 + i * 24, *row, *link)
        struct.pack_into("<3I", self.data, table + 4, len(rows), len(rows), root)

    def _rows(self) -> list[tuple[int, int, int]]:
        table, count = self._table()
        return [struct.unpack_from("<3I", self.data, table + 24 + i * 24) for i in range(count)]

    def _allocate_pages(self, count: int) -> int:
        """Take <count> logical pages (a physical pair each) from `+0x18`; return the first id.

        New pages come from the region the format reserves between the pages in use and the page table,
        so no byte of the file moves. Tencent's trees advance `+0x18` by one pair per page and set it to
        0xffffffff once the region is used up; what it holds when exactly one pair is left is not
        measured, so an allocation that would leave less than a whole pair free is refused.
        """
        first = self._u32(0x18)
        limit = min(self._u32(0x30), self._u32(0x38))
        following = first + 2 * PAGE * count
        if first == 0xFFFFFFFF or following + 2 * PAGE > limit:
            raise TreeFull(f"{self.path.name}: no room for {count} more B-tree page(s) before the "
                           f"page table (next free {first:#x}, table at {limit:#x})")
        for logical, *physical in self._rows():
            if any(first <= page < following for page in (logical, *physical)):
                raise TreeFull(f"{self.path.name}: page {logical:#x} already sits in the free region")
        struct.pack_into("<I", self.data, 0x18, following)
        return first

    def split_root_leaf(self) -> None:
        """Grow a tree whose root is also its only leaf into two leaves and an internal root.

        The keys are halved: the lower half stays in the root's own logical page, the upper half takes
        the next free logical page, and the one after that becomes the internal root -- the shape
        Tencent's builder produces for the same tree. Both new pages come from `_allocate_pages`.

        Both copies of every logical page are written identically. Which copy the table calls active is
        unobservable either way, and it is set to match a builder-made tree of this shape. The table
        rows reproduce two independent Tencent-built trees of the same three-row shape (package 1's
        index and package 4's) byte for byte. Raises TreeFull for a root that is already internal or a
        table with more than the one row.
        """
        root_logical = self._u32(0x10)
        root = self._active_page(root_logical)
        tail = struct.unpack_from("<4I", self.data, root + PAGE - 16)
        _, rows = self._table()
        if tail[3] >> 16 != LEAF_TYPE or rows != 1:
            raise TreeFull(f"{self.path.name}: only a single-leaf tree can be split "
                           f"(root type {tail[3] >> 16}, {rows} table rows)")

        count = tail[3] & 0xFFFF
        keys = struct.unpack_from(f"<{count}I", self.data, root)
        values = struct.unpack_from(f"<{count}I", self.data, root + KEYS_PER_PAGE * 4)
        half = count // 2
        leaf_logical = self._allocate_pages(2)
        root_page = leaf_logical + 2 * PAGE

        for offset in (root_logical, root_logical + PAGE):
            self._write_page(offset, keys[:half], values[:half], root_logical, leaf_logical, LEAF_TYPE)
        for offset in (leaf_logical, leaf_logical + PAGE):
            self._write_page(offset, keys[half:], values[half:], leaf_logical, 0xFFFFFFFF, LEAF_TYPE)
        for offset in (root_page, root_page + PAGE):
            self._write_page(offset, (0, keys[half]), (root_logical, leaf_logical), root_page,
                             0xFFFFFFFF, 2)
        self._write_table([(root_logical, root_logical + PAGE, root_logical),
                           (leaf_logical, leaf_logical + PAGE, leaf_logical),
                           (root_page, root_page, root_page + PAGE)])
        struct.pack_into("<II", self.data, 0x10, root_page, self._u32(0x14))
        self.leaves = self._active_leaf_pages()

    def split_leaf(self, leaf_logical: int) -> None:
        """Split a full leaf whose parent is the internal root, growing the tree by one leaf.

        Every multi-leaf tree in Tencent's packages (50 of them, 2 to 81 leaves) is one internal root
        over leaves, which is the shape this keeps. The lower half of the keys stays in <leaf_logical>,
        the upper half takes a new logical page from `_allocate_pages`, chained between the leaf and its
        old successor -- as Tencent's trees show, where a later page sits between two earlier ones in key
        order (package 13's `0x7000` between `0x1000` and `0x3000`). The root gains the new page's
        lowest key as its bound, and the table gains its row. A root that is itself full, which would
        need a second internal level no package has, is refused.

        Device verdict 2026-10-22, pass: package 1 on data 1.7.0.1, split from two leaves to three,
        loads, and its appended Chessplayer Card text reads English (lab notebook).
        """
        root_logical = self._u32(0x10)
        root = self._active_page(root_logical)
        root_tail = self._u32(root + PAGE - 4)
        root_count = root_tail & 0xFFFF
        if root_tail >> 16 != 2:
            raise TreeFull(f"{self.path.name}: the root is not an internal page")
        if root_count >= KEYS_PER_PAGE:
            raise TreeFull(f"{self.path.name}: the internal root is full; a second level is not measured")
        bounds = struct.unpack_from(f"<{root_count}I", self.data, root)
        children = struct.unpack_from(f"<{root_count}I", self.data, root + KEYS_PER_PAGE * 4)
        if leaf_logical not in children:
            raise TreeFull(f"{self.path.name}: leaf {leaf_logical:#x} is not a child of the root")
        for child in children:
            if self._u32(self._active_page(child) + PAGE - 4) >> 16 != LEAF_TYPE:
                raise TreeFull(f"{self.path.name}: the root has a non-leaf child; deeper trees are not measured")

        leaf = self._active_page(leaf_logical)
        self_id, _, next_id, tail = struct.unpack_from("<4I", self.data, leaf + PAGE - 16)
        count = tail & 0xFFFF
        keys = struct.unpack_from(f"<{count}I", self.data, leaf)
        values = struct.unpack_from(f"<{count}I", self.data, leaf + KEYS_PER_PAGE * 4)
        half = count // 2
        new_logical = self._allocate_pages(1)

        for offset in (leaf_logical, leaf_logical + PAGE):
            self._write_page(offset, keys[:half], values[:half], leaf_logical, new_logical, LEAF_TYPE)
        for offset in (new_logical, new_logical + PAGE):
            self._write_page(offset, keys[half:], values[half:], new_logical, next_id, LEAF_TYPE)
        at = children.index(leaf_logical) + 1
        bounds = bounds[:at] + (keys[half],) + bounds[at:]
        children = children[:at] + (new_logical,) + children[at:]
        for offset in (root_logical, root_logical + PAGE):
            self._write_page(offset, bounds, children, root_logical, 0xFFFFFFFF, 2)
        self._write_table(self._rows() + [(new_logical, new_logical + PAGE, new_logical)])
        self.leaves = self._active_leaf_pages()

    def insert_key(self, key: int, value: int) -> None:
        """Add <key> -> <value> to the leaf the B-tree search reaches.

        The root page is at +0x10. Internal pages are type 2 and hold each child's lowest key, so the
        child to follow is the last one whose lowest key is not above <key>. A leaf that is already
        full is split -- by `split_root_leaf` when it is also the root, by `split_leaf` when its parent
        is the root -- and the insert retried; any deeper shape is reported.
        """
        while True:
            logical = self._u32(0x10)
            page = self._active_page(logical)
            depth = 0
            while True:
                tail = self._u32(page + PAGE - 4)
                count = tail & 0xFFFF
                keys = struct.unpack_from(f"<{count}I", self.data, page)
                if tail >> 16 == LEAF_TYPE:
                    break
                child = max((i for i, low in enumerate(keys) if low <= key), default=0)
                logical = self._u32(page + (KEYS_PER_PAGE + child) * 4)
                page = self._active_page(logical)
                depth += 1
            if count < KEYS_PER_PAGE:
                break
            if depth == 0:
                self.split_root_leaf()
            elif depth == 1:
                self.split_leaf(logical)
            else:
                raise TreeFull(f"{self.path.name}: a full leaf {depth} levels down is not measured")
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
        try:
            handle = self.path.open("r+b")
        except FileNotFoundError:
            handle = self.path.open("w+b")
        with handle, memoryview(self.data) as buffer:
            for start in range(0, size, WRITE_BLOCK):
                end = min(start + WRITE_BLOCK, size)
                previous = handle.read(end - start)
                # bytearray equality uses a fast byte comparison; the temporary
                # slice is bounded to WRITE_BLOCK, never the whole shard.
                if self.data[start:end] != previous:
                    handle.seek(start)
                    with buffer[start:end] as block:
                        if handle.write(block) != len(block):
                            raise OSError(f"{self.path.name}: short shard write at {start:#x}")
            if handle.seek(0, 2) != size:
                handle.truncate(size)


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


def _read_btree_offsets(path: Path) -> dict[int, set[int]]:
    """Read live slot offsets without loading or copying the shard's payloads.

    Read the current page table on every call: relocation and append can change
    both the active pages and their values between successive slot-map builds.
    Use the same active-leaf/self-id checks as Shard and btree_offsets.
    """
    offsets: dict[int, set[int]] = {}
    leaves = 0
    with path.open("rb") as handle:
        handle.seek(0x30)
        table = struct.unpack("<I", handle.read(4))[0]
        handle.seek(table + 4)
        rows = struct.unpack("<I", handle.read(4))[0]
        for i in range(rows):
            handle.seek(table + 24 + i * 24)
            logical, active = struct.unpack("<II", handle.read(8))
            handle.seek(active)
            page = handle.read(PAGE)
            self_id, _, _, tail = struct.unpack_from("<4I", page, PAGE - 16)
            if tail >> 16 != LEAF_TYPE or self_id != logical:
                continue
            leaves += 1
            count = tail & 0xFFFF
            keys = struct.unpack_from(f"<{count}I", page)
            values = struct.unpack_from(f"<{count}I", page, KEYS_PER_PAGE * 4)
            for key, value in zip(keys, values):
                offsets.setdefault(key, set()).add(value)
    if not leaves:
        raise RuntimeError(f"{path.name}: no active B-tree leaf pages found")
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
            live = _read_btree_offsets(self.shard_paths[0])
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
