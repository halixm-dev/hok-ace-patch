"""Offline regression checks for skipped scans and retained eligible work."""
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
import extra_text
from wxq_patch import adaptive, qtsvfs


ASSET = next(iter(extra_text.CANDIDATE_ASSETS))
SCRIPT = next(iter(extra_text.SCRIPT_LABELS))
CARD = next(iter(device.NATIVE_CHUNK_KEYS))


def package(entries: dict) -> SimpleNamespace:
    return SimpleNamespace(package_id="1", entries=entries,
                           build_slot_map=Mock(return_value={h: {} for h in entries}))


class ScanGuards(unittest.TestCase):
    def test_ineligible_scripts_never_scan(self) -> None:
        for entries, skip in (({}, set()), ({SCRIPT: SimpleNamespace(compression=9)}, set()),
                              ({SCRIPT: SimpleNamespace(compression=1)}, {SCRIPT})):
            source = package(entries)
            self.assertEqual(extra_text.plan_scripts(source, skip), {})
            source.build_slot_map.assert_not_called()

    def test_eligible_script_still_reads_and_rewrites(self) -> None:
        source = package({SCRIPT: SimpleNamespace(compression=1)})
        raw = 'name = "通用"'.encode()
        with patch("qts_relocate.read_raw", return_value=raw):
            self.assertEqual(extra_text.plan_scripts(source, set()), {SCRIPT: raw})
        source.build_slot_map.assert_called_once()
        catalog = SimpleNamespace(unique={"通用": "Universal"})
        self.assertEqual(extra_text.rewrite_script(SCRIPT, raw, catalog), b'name = "Universal"')

    def test_missing_script_chunks_still_skip(self) -> None:
        source = package({SCRIPT: SimpleNamespace(compression=4)})
        source.build_slot_map.return_value = {}
        with patch("qts_relocate.read_raw") as read:
            self.assertEqual(extra_text.plan_scripts(source, set()), {})
            read.assert_not_called()

    def test_config_gates_prevent_scans(self) -> None:
        for entries, skip, candidates in (
            ({ASSET: SimpleNamespace(compression=1)}, set(), frozenset()),
            ({}, set(), frozenset({ASSET})),
            ({ASSET: SimpleNamespace(compression=1)}, {ASSET}, frozenset({ASSET})),
            ({ASSET: SimpleNamespace(compression=9)}, set(), frozenset({ASSET})),
        ):
            source = package(entries)
            self.assertEqual(extra_text.plan_package(source, SimpleNamespace(unique={}), skip,
                                                    candidates=candidates), {})
            source.build_slot_map.assert_not_called()

    def test_allowlisted_and_cycle_config_still_translate(self) -> None:
        raw = b"\x0a\x06" + "道具".encode()
        catalog = SimpleNamespace(unique={"道具": "Props"})
        for allowed, candidates in ((frozenset({ASSET}), frozenset()),
                                    (frozenset(), frozenset({ASSET}))):
            source = package({ASSET: SimpleNamespace(compression=4)})
            with patch.object(extra_text, "SAFE_ASSETS", allowed), \
                    patch("qts_relocate.read_raw", return_value=raw):
                self.assertEqual(extra_text.plan_package(source, catalog, set(),
                                                        candidates=candidates),
                                 {ASSET: b"\x0a\x05Props"})
            source.build_slot_map.assert_called_once()

    def check_repair(self, source_size: int, staged_size: int | None,
                     *, unreadable: bool = False) -> tuple:
        source = package({CARD: SimpleNamespace(chunk_size=source_size)})
        staged = package({CARD: SimpleNamespace(chunk_size=staged_size)})
        catalog = SimpleNamespace(known={CARD})
        with tempfile.TemporaryDirectory(dir=ROOT / ".scratch/staging-performance") as folder:
            output = Path(folder)
            if staged_size is not None:
                (output / "1").mkdir()
            with patch.object(adaptive, "discover", return_value=([source], [])), \
                    patch.object(qtsvfs, "QtsPackage", return_value=staged), \
                    patch("qts_relocate.read_raw", return_value=None if unreadable else b"table"), \
                    patch.object(device, "_native_slots", return_value={}), \
                    patch.object(device, "_package_output", return_value=output / "1"), \
                    patch.object(device, "write_assets", return_value=([f"{CARD:016X}"], [])) as write:
                result = device.repair_card_dictionaries(Path(folder), catalog, output, lambda _: None)
        return result, source, staged, write

    def test_native_card_never_scans(self) -> None:
        result, source, _, write = self.check_repair(device.NATIVE_CHUNK_SIZE, None)
        self.assertEqual(result, ([], []))
        source.build_slot_map.assert_not_called()
        write.assert_not_called()

    def test_staged_native_card_wins_over_old_source_size(self) -> None:
        result, source, staged, write = self.check_repair(614400, device.NATIVE_CHUNK_SIZE)
        self.assertEqual(result, ([], []))
        source.build_slot_map.assert_not_called()
        staged.build_slot_map.assert_not_called()
        write.assert_not_called()

    def test_staged_oversized_card_is_still_repaired(self) -> None:
        result, source, staged, write = self.check_repair(device.NATIVE_CHUNK_SIZE, 614400)
        source.build_slot_map.assert_not_called()
        staged.build_slot_map.assert_called_once()
        write.assert_called_once()
        self.assertEqual(result[0][0]["stage_report"]["status"], "repaired")

    def test_unreadable_card_is_still_reported(self) -> None:
        result, source, _, write = self.check_repair(614400, None, unreadable=True)
        source.build_slot_map.assert_called_once()
        write.assert_not_called()
        self.assertEqual(result[1][0]["dropped"], [f"{CARD:016X}"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
