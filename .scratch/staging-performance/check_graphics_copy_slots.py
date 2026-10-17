"""Check texture slot reuse only across an immediately created byte-for-byte package copy."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.append(str(ROOT / "resources/runtime"))
import device_extensions as device
import mobile_graphics as graphics
from wxq_patch import qtsvfs


class CopySlots(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / ".scratch/staging-performance")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source/15"
        self.source.mkdir(parents=True)
        self.output = self.root / "out"
        (self.source / "15.db").write_bytes(b"index")
        (self.source / "15_0.db").write_bytes(b"abcdEFGH")
        self.scans = []
        self.moves = []
        self.saves = []
        test = self

        class Package:
            def __init__(self, folder):
                self.package_dir = folder
                self.package_id = "15"
                self.index_path = folder / "15.db"
                self.shard_paths = [folder / "15_0.db"]
                self.entries = {42: None}

            def build_slot_map(self):
                test.scans.append(self.package_dir)
                offset = 100 if self.package_dir == test.source else 900
                return {42: {i: qtsvfs.ChunkSlot(
                    self.shard_paths[0], 42, i, 4, 4, offset + i, 52,
                    i * 4, i * 4 + 4, 7 + i, 16, 0) for i in range(2)}}

        class Shard:
            def __init__(self, path):
                self.path = path

            def relocate(self, slot, payload, size):
                test.moves.append((self.path, slot, payload, size))

            def save(self):
                test.saves.append(self.path)

        self.package_type = Package
        self.shard_type = Shard

    def run_pass(self, new):
        with patch.object(qtsvfs, "QtsPackage", self.package_type), \
                patch.object(device, "Shard", self.shard_type), \
                patch.object(graphics, "catalog_graphics", return_value={42: {"hash": "2A"}}), \
                patch.object(graphics, "oodle_decompress", side_effect=lambda payload, size: payload), \
                patch.object(graphics, "oodle_stored", side_effect=lambda raw: raw), \
                patch.object(graphics, "english_raw", return_value=new):
            return device.port_graphics(self.package_type(self.source), SimpleNamespace(graphics={}),
                                        self.root, self.output, lambda _: None)

    def test_new_copy_reuses_offsets_and_retargets_every_chunk(self):
        self.assertEqual(self.run_pass(b"12345678"), {"considered": 1, "written": 1, "skipped": []})
        self.assertEqual(self.scans, [self.source])
        self.assertEqual([move[1].slot_offset for move in self.moves], [100, 101])
        target = self.output / "15/15_0.db"
        self.assertEqual([move[1].shard_path for move in self.moves], [target, target])
        self.assertEqual([move[2] for move in self.moves], [b"1234", b"5678"])
        self.assertEqual(self.saves, [target])
        self.assertEqual(target.read_bytes(), b"abcdEFGH")

    def test_existing_copy_rescans_current_offsets(self):
        device._package_output(self.package_type(self.source), self.output)
        self.run_pass(b"12345678")
        self.assertEqual(self.scans, [self.source, self.output / "15"])
        self.assertEqual([move[1].slot_offset for move in self.moves], [900, 901])

    def test_already_english_never_copies_or_writes(self):
        self.assertEqual(self.run_pass(b"abcdEFGH")["written"], 0)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.scans, [self.source])
        self.assertFalse(self.moves)

    def test_refused_texture_never_copies_or_writes(self):
        result = self.run_pass(None)
        self.assertEqual(result["skipped"], ["000000000000002A"])
        self.assertFalse(self.output.exists())
        self.assertFalse(self.moves)

    def test_changed_length_still_refuses(self):
        self.assertEqual(self.run_pass(b"short")["written"], 0)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.moves)


if __name__ == "__main__":
    unittest.main(verbosity=2)
