"""Check bounded changed-region saves against the former whole-file writer."""
from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from check_shard_io import ROOT, SIZE, fixture
from qts_relocate import FILE_GROWTH, Shard, btree_offsets


class ChangedWrites(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / ".scratch/staging-performance")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "1_0.db"
        fixture(self.path)

    def save_and_count(self, shard: Shard) -> int:
        original = Path.open
        writes = []

        class File:
            def __init__(self, handle):
                self.handle = handle

            def __enter__(self):
                self.handle.__enter__()
                return self

            def __exit__(self, *args):
                return self.handle.__exit__(*args)

            def __getattr__(self, name):
                return getattr(self.handle, name)

            def write(self, value):
                written = self.handle.write(value)
                writes.append(written)
                return written

        with patch.object(Path, "open", lambda path, *a, **kw: File(original(path, *a, **kw))):
            shard.save()
        return sum(writes)

    def test_unchanged_save_writes_nothing(self) -> None:
        shard = Shard(self.path)
        self.assertEqual(self.save_and_count(shard), 0)

    def test_one_changed_byte_does_not_rewrite_payload(self) -> None:
        shard = Shard(self.path)
        shard.data[-1] = 19
        self.assertLessEqual(self.save_and_count(shard), 65536)
        self.assertEqual(self.path.read_bytes(), shard.data)
        self.assertEqual(self.save_and_count(shard), 0)

    def test_growth_header_and_distant_mutations_match_legacy(self) -> None:
        shard = Shard(self.path)
        shard.data[0x2000] = 19
        shard.data[SIZE // 2] = 33
        shard.data.extend(b"new bytes")
        shard.data_end = SIZE + 9
        size = SIZE + FILE_GROWTH
        expected = shard.data + bytes(size - len(shard.data))
        struct.pack_into("<II", expected, 8, shard.data_end, size)
        self.save_and_count(shard)
        self.assertEqual(self.path.read_bytes(), expected)
        self.assertEqual(self.save_and_count(shard), 0)
        shard.data.extend(b"view was released")

    def test_removed_file_is_recreated(self) -> None:
        shard = Shard(self.path)
        self.path.unlink()
        shard.save()
        self.assertEqual(self.path.read_bytes(), shard.data)

    def test_extra_disk_tail_is_truncated(self) -> None:
        shard = Shard(self.path)
        with self.path.open("ab") as handle:
            handle.write(b"stale disk tail")
        shard.save()
        self.assertEqual(self.path.read_bytes(), shard.data)

    def test_external_same_size_mutation_is_overwritten(self) -> None:
        shard = Shard(self.path)
        with self.path.open("r+b") as handle:
            handle.seek(SIZE // 2)
            handle.write(b"outside change")
        shard.save()
        self.assertEqual(self.path.read_bytes(), shard.data)

    def tree(self) -> Shard:
        with self.path.open("r+b") as handle:
            handle.seek(0x10)
            handle.write(struct.pack("<I", 0x1000))
            handle.seek(0x18)
            handle.write(struct.pack("<I", 0x3000))
            handle.seek(0x34)
            handle.write(struct.pack("<I", 0x1000))
        return Shard(self.path)

    def check_legacy_bytes(self, shard: Shard) -> None:
        size = max(shard._u32(12), (shard.data_end + FILE_GROWTH - 1) // FILE_GROWTH * FILE_GROWTH)
        expected = bytearray(shard.data[:size])
        expected.extend(bytes(max(0, size - len(expected))))
        struct.pack_into("<II", expected, 8, shard.data_end, size)
        shard.save()
        self.assertEqual(self.path.read_bytes(), expected)

    def test_root_split_and_appended_records_match_legacy(self) -> None:
        shard = self.tree()
        offsets = {}
        for key in range(1, 601):
            record = struct.pack("<IiIQ", 0, -1, 32, key) + bytes(12)
            offsets[key] = {shard.append_record(record, key)}
        self.check_legacy_bytes(shard)
        self.assertEqual(btree_offsets(Shard(self.path)), offsets)

    def test_relocation_repoints_only_the_live_slot(self) -> None:
        shard = self.tree()
        slot = SimpleNamespace(hash1=7, header_flags=16, file_hash=42, reserved=0, chunk_id=0)
        slot.slot_offset = shard.append_slot(slot, b"first", 5)
        shard.save()
        new_offset = shard.relocate(slot, b"second", 6)
        self.check_legacy_bytes(shard)
        self.assertEqual(btree_offsets(Shard(self.path))[7], {new_offset})

    def test_write_errors_release_views_even_with_retained_traceback(self) -> None:
        original = Path.open

        class File:
            def __init__(self, handle, short):
                self.handle, self.short = handle, short

            def __enter__(self):
                self.handle.__enter__()
                return self

            def __exit__(self, *args):
                return self.handle.__exit__(*args)

            def __getattr__(self, name):
                return getattr(self.handle, name)

            def write(self, value):
                if self.short:
                    return 0
                raise OSError("disk full")

        for short in (False, True):
            shard = Shard(self.path)
            shard.data[-1] = 19
            retained = None
            with patch.object(Path, "open", lambda path, *a, **kw: File(original(path, *a, **kw), short)):
                try:
                    shard.save()
                except OSError as error:
                    retained = error
            self.assertIsNotNone(retained)
            shard.data.extend(b"released despite traceback")


if __name__ == "__main__":
    unittest.main(verbosity=2)
