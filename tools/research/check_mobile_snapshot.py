"""Check updater-directory acceptance without widening snapshot file or write scope."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mobile_snapshot import (extract_snapshot, extract_snapshot_stream, package_files_at, validate_path,
                             verify_snapshot)


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


def _archive(path: Path) -> None:
    with tarfile.open(path, "w") as output:
        for name, payload in (("packages/1/1.info", json.dumps({"version": "test"}).encode()),
                              ("packages/1/1.db", bytes(range(256)) * 1200), ("packages/1/1_0.db", b""),
                              ("Watchdog/PatchList.db", b"x" * 5000)):
            member = tarfile.TarInfo(name)
            member.size = len(payload)
            output.addfile(member, io.BytesIO(payload))


def _piped(archive: Path, target: Path, limit: int, cut: int | None = None) -> dict:
    """Feed <archive> (its first <cut> bytes) through an OS pipe, as the privileged tar does."""
    read_end, write_end = os.pipe()
    data = archive.read_bytes()[:cut]

    def writer():
        with open(write_end, "wb", closefd=True) as sink:
            try:
                sink.write(data)
            except OSError:
                pass  # the reader refused the stream and closed its end

    thread = threading.Thread(target=writer)
    thread.start()
    try:
        with open(read_end, "rb", buffering=0, closefd=True) as stream:
            return extract_snapshot_stream(stream, target, maximum_bytes=limit)
    finally:
        thread.join()


class SnapshotStream(unittest.TestCase):
    """The snapshot read from a pipe instead of an archive file (lab notebook, 2026-10-18)."""

    def test_stream_equals_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "input.tar"
            _archive(archive)
            expected = extract_snapshot(archive, root / "from-file")
            result = _piped(archive, root / "from-pipe", archive.stat().st_size)
            self.assertEqual(result["manifest"], expected)
            # The identity covers the whole stream, the tar's end padding included.
            self.assertEqual(result["bytes"], archive.stat().st_size)
            self.assertEqual(result["sha256"], hashlib.sha256(archive.read_bytes()).hexdigest())
            self.assertEqual(verify_snapshot(root / "from-pipe"), expected)

    def test_short_or_oversized_stream_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "input.tar"
            _archive(archive)
            size = archive.stat().st_size
            for cut, limit in ((size // 2, size), (700, size), (None, size - 1)):
                with self.assertRaises((ValueError, tarfile.TarError)):
                    _piped(archive, root / "snapshot", limit, cut)
                self.assertFalse((root / "snapshot").exists())

    def test_files_at_from_manifest(self):
        manifest = {"files": {"packages/1/1.db": {"sha256": "a"}, "packages/1/1_0.db": {"sha256": "b"},
                              "packages/10/10.db": {"sha256": "a"}, "packages/1/1.info": {"sha256": "a"},
                              "packages/builtin/Globalindex/GlobalIndexPrime.data": {"sha256": "a"},
                              "Watchdog/PatchList.db": {"sha256": "a"}}}
        self.assertEqual(package_files_at(manifest, {"a"}), ["1/1.db", "10/10.db"])
        self.assertEqual(package_files_at(manifest, set()), [])


if __name__ == "__main__":
    unittest.main()
