"""Check writable-shard memory bounds, saved bytes, and buffer lifetime offline."""
from __future__ import annotations

import struct
import sys
import tempfile
import tracemalloc
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from qts_relocate import FILE_GROWTH, Shard

SIZE = 4 * 1024 * 1024


def fixture(path: Path, size: int = SIZE) -> None:
    data = bytearray(size)
    struct.pack_into("<II", data, 8, size, size)
    struct.pack_into("<I", data, 0x30, 0x8000)
    struct.pack_into("<6I", data, 0x8000, 0x20, 1, 1, 1, 0, 0x20)
    struct.pack_into("<6I", data, 0x8018, 0x1000, 0x2000, 0x1000, 0, 0, 0)
    struct.pack_into("<4I", data, 0x2FF0, 0x1000, 0, 0xFFFFFFFF, 3 << 16)
    sentinel = b"read and write payload sentinel!!"
    data[-len(sentinel):] = sentinel
    path.write_bytes(data)


class ShardIO(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / ".scratch/staging-performance")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "1_0.db"
        fixture(self.path)

    def test_load_does_not_duplicate_the_whole_file(self) -> None:
        tracemalloc.start()
        try:
            shard = Shard(self.path)
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        self.assertEqual(shard.data, self.path.read_bytes())
        self.assertLess(peak, SIZE * 1.25, f"load peak: {peak} bytes")

    def test_save_does_not_duplicate_the_whole_file(self) -> None:
        shard = Shard(self.path)
        tracemalloc.start()
        try:
            shard.save()
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        self.assertLess(peak, 256 * 1024, f"save temporary peak: {peak} bytes")

    def test_save_matches_legacy_bytes_with_growth_and_extra_tail(self) -> None:
        shard = Shard(self.path)
        shard.data_end += 7
        size = SIZE + FILE_GROWTH
        shard.data.extend(b"x" * (FILE_GROWTH + 20))
        expected = bytearray(shard.data[:size])
        struct.pack_into("<II", expected, 8, shard.data_end, size)
        shard.save()
        self.assertEqual(self.path.read_bytes(), expected)
        shard.data.extend(b"more")  # save must release every exported buffer

    def test_save_twice_then_reload(self) -> None:
        shard = Shard(self.path)
        shard.save()
        shard.data[-1] = 19
        shard.save()
        self.assertEqual(Shard(self.path).data, shard.data)

    def test_failed_save_releases_the_buffer(self) -> None:
        shard = Shard(self.path)
        with patch.object(Path, "open", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                shard.save()
        shard.data.extend(b"more")

    def test_short_reads_and_changed_file_size(self) -> None:
        original = Path.open

        class Reader:
            def __init__(self, handle, delta):
                self.handle, self.delta = handle, delta

            def __enter__(self):
                self.handle.__enter__()
                return self

            def __exit__(self, *args):
                return self.handle.__exit__(*args)

            def seek(self, offset, whence=0):
                position = self.handle.seek(offset, whence)
                return position + self.delta if whence == 2 else position

            def read(self, size):
                return self.handle.read(size)

            def readinto(self, buffer):
                return self.handle.readinto(buffer[:4096])

        for delta, error in ((0, None), (1, "shrank"), (-1, "grew")):
            with self.subTest(delta=delta), patch.object(
                Path, "open", lambda path, *a, **kw: Reader(original(path, *a, **kw), delta)
            ):
                if error:
                    with self.assertRaisesRegex(RuntimeError, error):
                        Shard(self.path)
                else:
                    self.assertEqual(len(Shard(self.path).data), SIZE)

    def test_save_pads_to_the_declared_growth_size(self) -> None:
        shard = Shard(self.path)
        shard.data_end += 7
        shard.save()
        saved = self.path.read_bytes()
        self.assertEqual(len(saved), SIZE + FILE_GROWTH)
        self.assertEqual(saved[SIZE:], bytes(FILE_GROWTH))
        self.assertEqual(struct.unpack_from("<II", saved, 8), (SIZE + 7, SIZE + FILE_GROWTH))


if __name__ == "__main__":
    unittest.main(verbosity=2)
