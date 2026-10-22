"""Check the shard B-tree splits: synthetic cases always, Tencent's own trees on request.

    .venv\\Scripts\\python.exe tools\\research\\check_btree_split.py
    .venv\\Scripts\\python.exe tools\\research\\check_btree_split.py --game <game dir> [--game <another>]

The synthetic cases build a one-leaf shard in the layout Tencent's packages use (pages from 0x1000, page
table at 0x1a000) and append keys until the tree has split its root and then leaves under that root.
After every split the tree must hold the invariants below, every key ever inserted must be found by a
search from the root, and its value must be the one inserted. A full internal root and a used-up page
region raise TreeFull rather than write.

With `--game` (a layer, `<dir>/WXQ_Data/Package/builtin` inside it) every shard there must hold the same
invariants. That is the measurement the split is written against: on the 1.6.0.1 and 1.7.0.1 layers
all 814 shards (1 to 82 page-table rows, up to 81 leaves under one internal root) pass, which is what
says the table's last three row words are the red-black tree `qts_relocate._red_black` builds.

Invariants:
1. page-table rows sorted by logical id; their last three words and header words 1-3 equal
   `_red_black(rows)`
2. the root (+0x10) is a leaf with one row, or an internal page whose children are all leaves
3. the root's bounds start at 0 and each later bound is that child's lowest key
4. leaves chain by `next` in bound order, the last 0xffffffff; keys sorted within and across leaves
5. each page's self word is its logical id and its tail word 1 is 0xffffffff
6. every row is a page reached from the root
7. `+0x18` lies past every logical page in the region before the page table, or is 0xffffffff
"""
from __future__ import annotations

import argparse
import random
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from qts_relocate import KEYS_PER_PAGE, LEAF_TYPE, PAGE, Shard, TreeFull, _red_black  # noqa: E402

NIL = 0xFFFFFFFF
TABLE = 0x1A000
TABLE_SIZE = 0x318
DATA = 0x1B000


def problems(data: bytes) -> list[str]:
    """The invariants a shard's tree breaks, as their numbers and a word on where."""
    def u32(offset: int) -> int:
        return struct.unpack_from("<I", data, offset)[0]

    bad = []
    table = u32(0x30)
    head = struct.unpack_from("<6I", data, table)
    rows = [struct.unpack_from("<6I", data, table + 24 + 24 * i) for i in range(head[1])]
    if [row[0] for row in rows] != sorted({row[0] for row in rows}):
        bad.append("1 rows out of order")
    root_row, links = _red_black(len(rows))
    if head[2] != len(rows) or head[3] != root_row or [tuple(row[3:]) for row in rows] != links:
        bad.append("1 red-black words")
    active = {row[0]: row[1] for row in rows}

    def page(logical: int):
        offset = active[logical]
        tail = struct.unpack_from("<4I", data, offset + PAGE - 16)
        count = tail[3] & 0xFFFF
        if tail[0] != logical or tail[1] != NIL:
            bad.append(f"5 tail of {logical:#x}")
        return (tail, struct.unpack_from(f"<{count}I", data, offset),
                struct.unpack_from(f"<{count}I", data, offset + KEYS_PER_PAGE * 4))

    root = u32(0x10)
    tail, bounds, children = page(root)
    reached = {root}
    if tail[3] >> 16 == LEAF_TYPE:
        if len(rows) != 1:
            bad.append("2 leaf root over several rows")
        if list(bounds) != sorted(bounds):
            bad.append("4 keys out of order")
    elif tail[3] >> 16 != 2:
        bad.append("2 root type")
    else:
        if bounds[0] != 0 or list(bounds) != sorted(set(bounds)):
            bad.append("3 bounds")
        last = -1
        for i, child in enumerate(children):
            reached.add(child)
            child_tail, keys, _ = page(child)
            if child_tail[3] >> 16 != LEAF_TYPE:
                bad.append("2 child not a leaf")
                continue
            if child_tail[2] != (children[i + 1] if i + 1 < len(children) else NIL):
                bad.append(f"4 chain at {child:#x}")
            if i and keys and keys[0] != bounds[i]:
                bad.append(f"3 bound {i}")
            if list(keys) != sorted(keys) or (keys and keys[0] < last):
                bad.append(f"4 order in {child:#x}")
            if keys:
                last = keys[-1]
    if reached != set(active):
        bad.append("6 rows the root does not reach")
    free = u32(0x18)
    if free != NIL and any(free <= row[0] < min(u32(0x30), u32(0x38)) for row in rows):
        bad.append("7 +0x18")
    return bad


def search(shard: Shard, key: int) -> list[int]:
    """Values under <key>, found by walking down from the root as the game does."""
    page = shard._active_page(shard._u32(0x10))
    while True:
        tail = shard._u32(page + PAGE - 4)
        count = tail & 0xFFFF
        keys = struct.unpack_from(f"<{count}I", shard.data, page)
        values = struct.unpack_from(f"<{count}I", shard.data, page + KEYS_PER_PAGE * 4)
        if tail >> 16 == LEAF_TYPE:
            return [value for k, value in zip(keys, values) if k == key]
        child = max((i for i, low in enumerate(keys) if low <= key), default=0)
        page = shard._active_page(values[child])


def one_leaf_shard(path: Path, keys: list[int]) -> None:
    """A shard whose tree is one root leaf at logical 0x1000, laid out like Tencent's small packages."""
    data = bytearray(DATA)
    struct.pack_into("<4I", data, 0x08, DATA, DATA, 0x1000, 0x1000)
    struct.pack_into("<2I", data, 0x18, 0x3000, NIL)
    struct.pack_into("<4I", data, 0x30, TABLE, TABLE_SIZE, TABLE, TABLE_SIZE)
    keys = sorted(keys)
    for offset in (0x1000, 0x2000):
        struct.pack_into(f"<{len(keys)}I", data, offset, *keys)
        struct.pack_into(f"<{len(keys)}I", data, offset + KEYS_PER_PAGE * 4, *(DATA for _ in keys))
        struct.pack_into("<4I", data, offset + PAGE - 16, 0x1000, NIL, NIL, LEAF_TYPE << 16 | len(keys))
    struct.pack_into("<6I", data, TABLE, 0x20, 1, 1, 0, 5, 0x20)
    struct.pack_into("<6I", data, TABLE + 24, 0x1000, 0x1000, 0x2000, NIL, NIL, NIL)
    path.write_bytes(bytes(data))


def record(key: int) -> bytes:
    return struct.pack("<IiI", 0, -1, 16) + struct.pack("<I", key)


class Synthetic(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp())
        self.path = self.folder / "0_0.db"
        self.random = random.Random(17)

    def grow(self, shard: Shard, inserted: dict[int, int], count: int) -> None:
        for _ in range(count):
            key = self.random.getrandbits(32)
            while key in inserted:
                key = self.random.getrandbits(32)
            inserted[key] = shard.append_record(record(key), key)

    def assert_sound(self, shard: Shard, inserted: dict[int, int]) -> None:
        self.assertEqual(problems(bytes(shard.data)), [])
        for key, value in inserted.items():
            self.assertEqual(search(shard, key), [value], f"key {key:08X}")

    def test_root_then_leaf_splits(self) -> None:
        start = sorted(self.random.sample(range(1 << 32), KEYS_PER_PAGE))
        one_leaf_shard(self.path, start)
        inserted = {key: DATA for key in start}
        shard = Shard(self.path)
        self.assert_sound(shard, inserted)
        for rows in (3, 4, 5, 6, 7):
            while shard._table()[1] < rows:
                self.grow(shard, inserted, 1)
            self.assert_sound(shard, inserted)
        self.grow(shard, inserted, 400)
        self.assert_sound(shard, inserted)
        shard.save()
        self.assert_sound(Shard(self.path), inserted)

    def test_region_used_up_is_refused(self) -> None:
        one_leaf_shard(self.path, sorted(self.random.sample(range(1 << 32), 100)))
        shard = Shard(self.path)
        inserted: dict[int, int] = {}
        with self.assertRaises(TreeFull):
            self.grow(shard, inserted, 20 * KEYS_PER_PAGE)
        # Every page sits before the table, and +0x18 left the last pair free rather than guess past it.
        self.assertTrue(all(row[0] + 2 * PAGE <= TABLE for row in shard._rows()))
        self.assertEqual(problems(bytes(shard.data)), [])

    def test_a_row_in_the_free_region_is_refused(self) -> None:
        one_leaf_shard(self.path, sorted(self.random.sample(range(1 << 32), KEYS_PER_PAGE)))
        data = bytearray(self.path.read_bytes())
        struct.pack_into("<I", data, 0x18, 0x1000)  # claims the leaf's own page is free
        self.path.write_bytes(bytes(data))
        with self.assertRaises(TreeFull):
            Shard(self.path).append_record(record(1), 1)


def check_game(game: Path) -> int:
    builtin = game / "WXQ_Data" / "Package" / "builtin"
    passing = failing = 0
    for path in sorted(builtin.glob("*/*.db")):
        if path.stat().st_size < 2 * PAGE:
            continue
        bad = problems(path.read_bytes())
        if bad:
            failing += 1
            print(f"  {path.relative_to(builtin)}: {', '.join(bad)}")
        else:
            passing += 1
    print(f"{builtin}: {passing} shards hold every invariant, {failing} do not")
    return failing


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--game", type=Path, action="append", default=[])
    args, rest = parser.parse_known_args()
    result = unittest.main(argv=[sys.argv[0], *rest], exit=False).result
    failing = sum(check_game(game) for game in args.game)
    sys.exit(1 if failing or not result.wasSuccessful() else 0)


if __name__ == "__main__":
    main()
