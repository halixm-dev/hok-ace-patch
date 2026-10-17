"""Check same-call prime slot reuse without weakening appended-asset read-back."""
from __future__ import annotations

import struct
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.append(str(ROOT / "resources/runtime"))
import qts_insert
from wxq_patch import qtsvfs


class AppendSourceSlots(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=ROOT / ".scratch/staging-performance")
        self.addCleanup(temp.cleanup)
        self.target = Path(temp.name) / "target"
        index = Path(temp.name) / "source.db"
        data = bytearray(80)
        struct.pack_into("<I", data, 12, 7)
        index.write_bytes(data)
        self.source_slots = {42: {0: SimpleNamespace(chunk_id=0, slot_offset=100)}}
        self.source = SimpleNamespace(index_path=index, entries={42: SimpleNamespace(
            chunk_size=4096, compression=4, entry_offset=0, entry_size=80, head_size=32)},
            build_slot_map=Mock(return_value=self.source_slots))
        self.checked_slots = {42: {0: SimpleNamespace(chunk_id=0, slot_offset=900)}}
        self.staged = SimpleNamespace(build_slot_map=Mock(return_value=self.checked_slots))
        self.writer = Mock()
        self.raw = b"translated"

    def run_append(self, *, supplied=True, encoded=b"payload", checked=None):
        with patch.object(qts_insert, "Shard", return_value=self.writer), \
                patch.object(qtsvfs, "QtsPackage", return_value=self.staged), \
                patch.object(qts_insert, "_encode", return_value=encoded), \
                patch.object(qts_insert, "read_raw", return_value=self.raw if checked is None else checked) as read:
            result = qts_insert.add_assets("1", self.target, [{"file_hash": 42, "raw": self.raw}],
                                           self.source, lambda _: None,
                                           **({"source_slots": self.source_slots} if supplied else {}))
        return result, read

    def test_supplied_source_map_avoids_scan_and_keeps_fresh_readback(self):
        result, read = self.run_append()
        self.assertEqual(result, ["000000000000002A"])
        self.source.build_slot_map.assert_not_called()
        self.writer.append_slot.assert_called_once_with(self.source_slots[42][0], b"payload", len(self.raw))
        self.staged.build_slot_map.assert_called_once_with()
        read.assert_called_once_with(self.staged, self.checked_slots, 42)

    def test_direct_call_still_builds_its_source_map(self):
        self.run_append(supplied=False)
        self.source.build_slot_map.assert_called_once_with()
        self.staged.build_slot_map.assert_called_once_with()

    def test_readback_mismatch_still_fails(self):
        with self.assertRaisesRegex(RuntimeError, "read-back differs"):
            self.run_append(checked=b"wrong")
        self.staged.build_slot_map.assert_called_once_with()

    def test_encoder_refusal_still_skips_asset(self):
        result, read = self.run_append(encoded=None)
        self.assertEqual(result, [])
        self.writer.append_slot.assert_not_called()
        self.writer.append_record.assert_not_called()
        read.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
