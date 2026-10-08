"""Check updater-directory acceptance without widening snapshot file or write scope."""
from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mobile_snapshot import extract_snapshot, validate_path, verify_snapshot


class SnapshotDirectories(unittest.TestCase):
    def test_measured_directories(self):
        for group in ("Merge", "CleanCopy"):
            for suffix in ("", "/0", "/1060000000", "/4294967295"):
                validate_path(f"packages/builtin/{group}{suffix}", directory=True)

    def test_no_updater_files(self):
        for path in ("packages/builtin/Merge", "packages/builtin/Merge/1", "packages/builtin/Merge/1/1.db",
                     "packages/builtin/CleanCopy/1060000000/1060000000.db"):
            with self.assertRaises(ValueError):
                validate_path(path)

    def test_no_arbitrary_directories(self):
        for suffix in ("/../1", "/-1", "/4294967296", "/abc", "/1/nested", "/00000000000"):
            with self.assertRaises(ValueError):
                validate_path("packages/builtin/Merge" + suffix, directory=True)
        with self.assertRaises(ValueError):
            validate_path("packages/builtin/Unknown", directory=True)

    def test_round_trip_and_tamper(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "input.tar"
            with tarfile.open(archive, "w") as output:
                for name in ("packages", "packages/1", "packages/builtin", "packages/builtin/Merge",
                             "packages/builtin/Merge/2", "packages/builtin/CleanCopy",
                             "packages/builtin/CleanCopy/1060000000", "Watchdog"):
                    member = tarfile.TarInfo(name)
                    member.type = tarfile.DIRTYPE
                    output.addfile(member)
                payload = json.dumps({"version": "test"}).encode()
                member = tarfile.TarInfo("packages/1/1.info")
                member.size = len(payload)
                output.addfile(member, io.BytesIO(payload))
            target = root / "snapshot"
            manifest = extract_snapshot(archive, target)
            self.assertEqual(manifest, verify_snapshot(target))
            self.assertTrue((target / "packages/builtin/CleanCopy/1060000000").is_dir())
            (target / "packages/1/1.info").write_text("changed", encoding="utf-8")
            with self.assertRaises(ValueError):
                verify_snapshot(target)

    def test_links_still_refused(self):
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                archive = root / "input.tar"
                with tarfile.open(archive, "w") as output:
                    member = tarfile.TarInfo("packages/1/1.db")
                    member.type = kind
                    member.linkname = "packages/1/1.info"
                    output.addfile(member)
                with self.assertRaises(ValueError):
                    extract_snapshot(archive, root / "snapshot")
                self.assertFalse((root / "snapshot").exists())


if __name__ == "__main__":
    unittest.main()
