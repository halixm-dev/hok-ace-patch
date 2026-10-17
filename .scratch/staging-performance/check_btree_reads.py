"""Check bounded B-tree reads, live-slot selection, and legacy equivalence offline."""
from __future__ import annotations

import struct
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.append(str(ROOT / "resources/runtime"))
import qts_relocate as relocate
from wxq_patch import qtsvfs


def read_tree(path: Path) -> dict[int, set[int]]:
    reader = getattr(relocate, "_read_btree_offsets", None)
    return reader(path) if reader else relocate.btree_offsets(relocate.Shard(path))


class TreeReads(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / ".scratch/staging-performance")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "1_0.db"
        data = bytearray(1024 * 1024)
        struct.pack_into("<II", data, 8, len(data), len(data))
        struct.pack_into("<I", data, 0x30, 0x8000)
        struct.pack_into("<6I", data, 0x8000, 0x20, 3, 3, 1, 0, 0x20)
        # Two active leaves, an internal page, and stale physical leaf copies.
        for i, (logical, active, kind, keys, values) in enumerate((
            (0x1000, 0x2000, 3, (7, 9), (0x10000, 0x11000)),
            (0x3000, 0x4000, 3, (7, 11), (0x12000, 0x13000)),
            (0x5000, 0x5000, 2, (0, 9), (0x1000, 0x3000)),
        )):
            struct.pack_into("<6I", data, 0x8018 + i * 24, logical, active, logical, 0, 0, 0)
            for page in {logical, active}:
                struct.pack_into("<2I", data, page, *keys)
                struct.pack_into("<2I", data, page + 510 * 4, *values)
                struct.pack_into("<4I", data, page + 4096 - 16,
                                 logical, 0, 0xFFFFFFFF, (kind << 16) | 2)
        self.path.write_bytes(data)

    def test_active_pages_and_duplicate_keys_match_legacy(self) -> None:
        expected = {7: {0x10000, 0x12000}, 9: {0x11000}, 11: {0x13000}}
        self.assertEqual(relocate.btree_offsets(relocate.Shard(self.path)), expected)
        self.assertEqual(read_tree(self.path), expected)

    def test_does_not_read_payload(self) -> None:
        original = Path.open
        reads = []

        class Reader:
            def __init__(self, handle):
                self.handle = handle

            def __enter__(self):
                self.handle.__enter__()
                return self

            def __exit__(self, *args):
                return self.handle.__exit__(*args)

            def seek(self, *args):
                return self.handle.seek(*args)

            def read(self, *args):
                value = self.handle.read(*args)
                reads.append(len(value))
                return value

        with patch.object(Path, "open", lambda path, *a, **kw: Reader(original(path, *a, **kw))):
            read_tree(self.path)
        self.assertLess(sum(reads), 32768, f"read {sum(reads)} bytes for a tiny tree")

    def test_fresh_read_after_page_write(self) -> None:
        read_tree(self.path)
        with self.path.open("r+b") as handle:
            handle.seek(0x2000 + 510 * 4)
            handle.write(struct.pack("<I", 0x14000))
        self.assertEqual(read_tree(self.path)[7], {0x14000, 0x12000})

    def test_no_leaf_is_refused(self) -> None:
        with self.path.open("r+b") as handle:
            handle.seek(0x8004)
            handle.write(struct.pack("<I", 0))
        with self.assertRaises(RuntimeError):
            read_tree(self.path)

    def test_truncated_tree_is_refused(self) -> None:
        self.path.write_bytes(self.path.read_bytes()[:0x8020])
        with self.assertRaises(struct.error):
            read_tree(self.path)

    def test_wrong_logical_self_id_is_ignored(self) -> None:
        with self.path.open("r+b") as handle:
            handle.seek(0x2000 + 4096 - 16)
            handle.write(struct.pack("<I", 0xDEAD))
        self.assertEqual(read_tree(self.path), {7: {0x12000}, 11: {0x13000}})

    def test_unreadable_tree_keeps_original_map(self) -> None:
        original = {42: {0: SimpleNamespace(slot_offset=123, hash1=7)}}

        class Package:
            shard_paths = [self.path]

            def build_slot_map(self):
                return original

        self.path.write_bytes(b"truncated")
        with patch.object(qtsvfs, "QtsPackage", Package):
            relocate.install_btree_slot_map()
            self.assertIs(Package().build_slot_map(), original)

    def test_installed_map_still_selects_live_relocated_slot(self) -> None:
        old = SimpleNamespace(slot_offset=0x9999, hash1=7, file_hash=42, chunk_id=0)
        live = SimpleNamespace(slot_offset=0x12000, hash1=7, file_hash=42, chunk_id=0)

        class Package:
            shard_paths = [self.path]

            def build_slot_map(self):
                return {42: {0: old}}

        with patch.object(qtsvfs, "QtsPackage", Package), patch.object(
            qtsvfs, "iter_chunk_slots", return_value=iter([old, live])
        ):
            relocate.install_btree_slot_map()
            self.assertIs(Package().build_slot_map()[42][0], live)


if __name__ == "__main__":
    unittest.main(verbosity=2)
