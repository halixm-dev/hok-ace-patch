"""Check `tools/research/watchdog_history.py` against the game's own `Watchdog/History.db` files kept in this repo's data.

    .venv\\Scripts\\python.exe tools\\research\\check_watchdog_history.py

Sources: the pristine 1.6.0.1 snapshot's `device-backup.tar` (the 10-16 download: 214 merge events,
10:05:35-10:06:03, lab notebook 2026-10-17 "What the game's updater records") and, when present, the
2026-10-22 stuck-update capture in `D:\\scratch\\hok-update-fail`. A missing source skips its case.
"""
from __future__ import annotations

import sys
import tarfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import watchdog_history  # noqa: E402

SNAPSHOT_1601 = ROOT / "dist" / "HOK ACE Patcher Data" / "pristine" / "20261016-101124" / "device-backup.tar"
STUCK_1022 = Path(r"D:\scratch\hok-update-fail\wd\Watchdog\History.db")


def _from_tar(tar_path: Path, member: str) -> bytes:
    with tarfile.open(tar_path) as tar:
        return tar.extractfile(member).read()


class History1601(unittest.TestCase):
    def setUp(self) -> None:
        if not SNAPSHOT_1601.is_file():
            self.skipTest(f"{SNAPSHOT_1601} not here")
        self.records = watchdog_history.parse(_from_tar(SNAPSHOT_1601, "Watchdog/History.db"))

    def test_merge_events_of_the_download(self) -> None:
        merges = [record for record in self.records if record.merge]
        self.assertEqual(len(merges), 214)
        self.assertEqual(min(r.when for r in merges).replace(microsecond=0), datetime(2026, 10, 16, 10, 5, 35))
        # The notebook's window ends at 10:06:03; the last record reads 10:06:02.506.
        self.assertTrue(datetime(2026, 10, 16, 10, 6, 2) <= max(r.when for r in merges)
                        <= datetime(2026, 10, 16, 10, 6, 3))

    def test_merge_names_its_package(self) -> None:
        packages = {record.package for record in self.records if record.merge}
        self.assertIn("1", packages)
        self.assertTrue(all(name.isdecimal() for name in packages))


class History1022(unittest.TestCase):
    def test_reads_every_record_kind(self) -> None:
        if not STUCK_1022.is_file():
            self.skipTest(f"{STUCK_1022} not here")
        records = watchdog_history.parse(STUCK_1022.read_bytes())
        self.assertIn("package=playerdata", [record.text for record in records])
        self.assertTrue(all(record.when.year == 2026 for record in records))

    def test_after(self) -> None:
        if not SNAPSHOT_1601.is_file():
            self.skipTest(f"{SNAPSHOT_1601} not here")
        records = watchdog_history.parse(_from_tar(SNAPSHOT_1601, "Watchdog/History.db"))
        self.assertEqual(watchdog_history.merges_after(records, datetime(2026, 10, 16, 10, 7)), [])
        self.assertEqual(len(watchdog_history.merges_after(records, datetime(2026, 10, 16, 10, 0))), 214)


class Malformed(unittest.TestCase):
    def test_empty_and_garbage(self) -> None:
        self.assertEqual(watchdog_history.parse(b""), [])
        self.assertEqual(watchdog_history.parse(b"\xff" * 4096), [])


if __name__ == "__main__":
    unittest.main()
