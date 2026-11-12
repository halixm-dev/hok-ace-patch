"""Check package Re-download after the recovery log's unreachable-slot failure, offline.

    .venv/Scripts/python.exe tools/research/check_unreachable_redownload.py

The tiny shard uses the existing synthetic B-tree fixture. Staging is narrowed to
the real Shard.relocate call that fails in port_graphics; no game APK is installed.
The original updater/older-patcher history is unknown and is not simulated here.
Snapshot verification, refused-build cleanup, scope binding and deletion plans are real.
Pre-review tests replace only the synthetic package-index reader and candidate enumeration;
current B-tree reads, combined planning and the file-delta rebuild remain real.
"""
from __future__ import annotations

import io
import json
import shutil
import struct
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "android/app/src/main/python"))
sys.path.append(str(ROOT / "resources/runtime"))
from check_btree_split import DATA, one_leaf_shard
from mobile_snapshot import extract_snapshot, verify_snapshot
from qts_relocate import KEYS_PER_PAGE, Shard
import hashlib

def file_identity(path):
    return {"size": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
import android_bridge as bridge

SYMPTOM = "15_0.db: slot 0x1dd2c4 (key DD242E3E) not in the B-tree"
REFUSAL = "A game package could not be patched safely"


class UnreachableRedownload(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="hok-unreachable-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.engine, self.session, self.keep = [self.root / name for name in ("engine", "session", "keep")]
        for path in (self.engine, self.session, self.keep):
            path.mkdir()
        (self.engine / "code.bin").write_bytes(b"synthetic engine identity")
        self.apk = self.root / "normal.apk"
        self.apk.write_bytes(b"synthetic verified APK: never parsed or installed")
        shard = self.root / "fixture.db"
        one_leaf_shard(shard, [0xDD242E3E])
        data = {"packages/1/1.info": b'{"version":"fixture"}',
                "packages/1/1.db": b"synthetic index, not parsed",
                "packages/15/15.db": b"synthetic index, not parsed",
                "packages/15/15_0.db": shard.read_bytes(),
                "packages/15/15.info": b"fixture version",
                "packages/19/19.db": b"unrelated package",
                "Watchdog/BrokenList.db": b""}
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w") as tar:
            for name, body in data.items():
                member = tarfile.TarInfo(name)
                member.size = len(body)
                tar.addfile(member, io.BytesIO(body))
        archive.seek(0)
        extract_snapshot(archive, self.session / "snapshot")
        preparation = patch.object(bridge, "_prepare", lambda root: None)
        preparation.start()
        self.addCleanup(preparation.stop)
        candidates = patch.object(bridge, "_graphics_candidates", return_value=set())
        candidates.start()
        self.addCleanup(candidates.stop)

    def stage(self, root: Path, session: Path, *args, **kwargs) -> str:
        """Exercise the actual failing relocation, in the staged package's copy."""
        package = getattr(self, "output_package", "15")
        target = session / "out" / package
        shutil.copytree(session / "snapshot/packages/15", target)
        slot = SimpleNamespace(hash1=0x7F3EE20EDD242E3E, slot_offset=0x1DD2C4,
                               header_flags=16, file_hash=0x0111F5872C9B2275,
                               reserved=0, chunk_id=0)
        if package != "15":
            (target / "15_0.db").rename(target / f"{package}_0.db")
        Shard(target / f"{package}_0.db").relocate(slot, b"fixture texture", 15)
        raise AssertionError("The broken slot unexpectedly relocated")

    def fail_build(self) -> Exception:
        with patch.object(bridge, "_build_scratch", self.stage):
            try:
                bridge.build_snapshot(str(self.engine), str(self.session), str(self.apk),
                    file_identity(self.apk)["sha256"], "en", str(self.keep))
            except Exception as error:
                bridge.clear_build(str(self.session))
                return error
        raise AssertionError("Broken build unexpectedly succeeded")

    def plan(self, name: str = "first") -> dict:
        bridge.review_redownload(str(self.engine), str(self.session), str(self.keep))
        record = json.loads((self.session / "redownload-review.json").read_text())
        scope = record["scope"]
        return {"packages": scope["summary"]["packages"], "files": {"packages/" + name: item for name, item in scope["files"].items()}}

    def test_logged_failure_offers_only_its_package_without_deleting(self) -> None:
        before = verify_snapshot(self.session / "snapshot")
        error = self.fail_build()
        self.assertIsInstance(error, bridge.PatchError, str(error))
        self.assertIn(REFUSAL, str(error))
        self.assertIn(SYMPTOM, str(error.__cause__))
        # Resetting the failed attempt must not lose the measured refusal.
        bridge.clear_build(str(self.session))
        plan = self.plan()
        self.assertEqual(set(plan["packages"]), {"15"})
        self.assertEqual(set(plan["files"]), {"packages/15/15.db", "packages/15/15_0.db", "packages/15/15.info"})
        self.assertEqual(verify_snapshot(self.session / "snapshot"), before)
        self.assertFalse((self.keep / bridge.REDOWNLOAD_NAME).exists())

    def test_healthy_session_has_no_plan(self) -> None:
        with self.assertRaisesRegex(bridge.PatchError, "No game files hold a translation"):
            self.plan()

    @contextmanager
    def inspect(self, mixed: dict[str, str] | None = None):
        """Only the synthetic index reader is replaced; actual B-tree metadata and planning stay real."""
        from wxq_patch import qtsvfs
        asset = 0x0111F5872C9B2275
        owner = self

        class Package:
            def __init__(self, directory):
                self.package_dir = directory
                self.entries = {asset: object()} if directory.name in getattr(owner, "graphics_packages", {"15"}) else {}

            def build_slot_map(self):
                slot = SimpleNamespace(hash1=0x7F3EE20EDD242E3E,
                    slot_offset=getattr(owner, "slot_offset", 0x1DD2C4),
                    shard_path=self.package_dir / f"{self.package_dir.name}_0.db", chunk_id=0)
                return {asset: {0: slot}}

        Package.build_slot_map._btree_aware = True
        with patch.object(bridge, "_mixed_packages", return_value=mixed or {}), \
             patch.object(bridge, "_graphics_candidates", return_value={asset}), \
             patch.object(qtsvfs, "QtsPackage", Package):
            yield

    def snapshot_file(self, name: str, body: bytes) -> None:
        snapshot = self.session / "snapshot"
        path = snapshot / name
        path.write_bytes(body)
        marker = snapshot / "manifest.json"
        manifest = json.loads(marker.read_text(encoding="utf-8"))
        identity = file_identity(path)
        manifest["files"][name] = {"bytes": identity["size"], "sha256": identity["sha256"]}
        manifest["bytes"] = sum(item["bytes"] for item in manifest["files"].values())
        marker.write_text(json.dumps(manifest), encoding="utf-8")
        verify_snapshot(snapshot)

    def test_mixed_refusal_also_finds_broken_graphics_before_any_build(self) -> None:
        """A mixed refusal must not hide the exact unreachable graphics-slot problem until round two."""
        before = verify_snapshot(self.session / "snapshot")
        with self.inspect({"19": "mixed fixture"}):
            plan = self.plan()
        self.assertEqual(set(plan["packages"]), {"15", "19"})
        self.assertEqual(set(plan["files"]), {"packages/15/15.db", "packages/15/15_0.db",
            "packages/15/15.info", "packages/19/19.db"})
        self.assertEqual(verify_snapshot(self.session / "snapshot"), before)
        self.assertFalse((self.session / bridge.PACKAGE_REFUSED_NAME).exists())
        self.assertFalse((self.keep / bridge.REDOWNLOAD_NAME).exists())

    def test_every_broken_texture_package_joins_one_plan(self) -> None:
        self.graphics_packages = {"1", "15"}
        body = (self.session / "snapshot/packages/15/15_0.db").read_bytes()
        self.snapshot_file("packages/1/1_0.db", body)
        with self.inspect({"19": "mixed fixture"}):
            self.assertEqual(set(self.plan()["packages"]), {"1", "15", "19"})

    def test_live_texture_slot_is_not_deleted(self) -> None:
        self.slot_offset = DATA
        with self.inspect({"19": "mixed fixture"}):
            self.assertEqual(set(self.plan()["packages"]), {"19"})

    def test_package_already_selected_for_deletion_is_not_scanned_again(self) -> None:
        self.snapshot_file("packages/15/15_0.db", b"truncated B-tree")
        with self.inspect({"15": "mixed fixture", "19": "mixed fixture"}):
            self.assertEqual(set(self.plan()["packages"]), {"15", "19"})

    def test_delta_rebuild_clears_the_slot_problem_without_extra_deletion(self) -> None:
        import pristine_delta
        packages = self.session / "snapshot/packages"
        pristine = self.root / "pristine"
        staged = self.root / "staged"
        for root in (pristine, staged):
            shutil.copytree(packages / "15", root / "15")
        shard = pristine / "15/15_0.db"
        data = bytearray(shard.read_bytes())
        struct.pack_into("<I", data, 0x1000 + KEYS_PER_PAGE * 4, 0x1DD2C4)
        shard.write_bytes(data)
        delta = pristine_delta.make(pristine, staged)
        pristine_delta.write(delta, self.keep / pristine_delta.DELTA_NAME)
        before = verify_snapshot(self.session / "snapshot")
        with self.inspect({"19": "mixed fixture"}):
            self.assertEqual(set(self.plan()["packages"]), {"19"})
        self.assertEqual(verify_snapshot(self.session / "snapshot"), before)
        self.assertEqual(list(self.session.glob("redownload-inspection-*")), [])

    def test_unreadable_tree_never_silently_approves_a_partial_plan(self) -> None:
        self.snapshot_file("packages/15/15_0.db", b"truncated B-tree")
        with self.inspect({"19": "mixed fixture"}), self.assertRaisesRegex(
                bridge.PatchError, "inspection could not finish package 15"):
            self.plan()
        self.assertFalse((self.session / "staged-hashes.json").exists())

    def test_failed_mixed_inspection_does_not_offer_only_the_known_btree_failure(self) -> None:
        self.fail_build()
        with patch.object(bridge, "_mixed_packages", side_effect=RuntimeError("fixture mixed inspection failed")), \
             self.assertRaisesRegex(RuntimeError, "fixture mixed inspection failed"):
            self.plan()
        self.assertFalse((self.session / "staged-hashes.json").exists())

    def test_approved_review_rechecks_exact_scope(self) -> None:
        with self.inspect({"19": "mixed fixture"}):
            self.plan()
        record = json.loads((self.session / "redownload-review.json").read_text())
        summary = json.loads(bridge.check_redownload_review(str(self.engine), str(self.session), str(self.keep), record["digest"]))
        self.assertEqual(set(summary["packages"]), {"15", "19"})
        with self.assertRaisesRegex(bridge.PatchError, "plan changed"):
            bridge.check_redownload_review(str(self.engine), str(self.session), str(self.keep), "0" * 64)

    def test_changed_review_files_refuse_deletion(self) -> None:
        with self.inspect({"19": "mixed fixture"}):
            self.plan()
        record = json.loads((self.session / "redownload-review.json").read_text())
        (self.session / "staged-hashes.json").write_text('{}')
        with self.assertRaisesRegex(bridge.PatchError, "plan differs"):
            bridge.check_redownload_review(str(self.engine), str(self.session), str(self.keep), record["digest"])

    def test_changed_kept_records_refuse_deletion(self) -> None:
        with self.inspect({"19": "mixed fixture"}):
            self.plan()
        record = json.loads((self.session / "redownload-review.json").read_text())
        (self.keep / bridge.RESTORE_REFUSED_NAME).write_text('{"packages": ["19"]}')
        with self.assertRaisesRegex(bridge.PatchError, "plan changed"):
            bridge.check_redownload_review(str(self.engine), str(self.session), str(self.keep), record["digest"])

    def test_changed_engine_invalidates_failure(self) -> None:
        self.fail_build()
        (self.engine / "code.bin").write_bytes(b"different engine")
        with self.assertRaisesRegex(bridge.PatchError, "No game files hold a translation"):
            self.plan()

    def test_changed_delta_records_invalidate_failure(self) -> None:
        self.fail_build()
        (self.keep / bridge.RESTORE_REFUSED_NAME).write_text('{"packages": []}', encoding="utf-8")
        with self.assertRaisesRegex(bridge.PatchError, "No game files hold a translation"):
            self.plan()

    def test_changed_snapshot_invalidates_failure(self) -> None:
        self.fail_build()
        snapshot = self.session / "snapshot"
        path = snapshot / "packages/15/15.info"
        path.write_bytes(b"new fixture version")
        marker = snapshot / "manifest.json"
        manifest = json.loads(marker.read_text(encoding="utf-8"))
        identity = file_identity(path)
        manifest["files"]["packages/15/15.info"] = {"bytes": identity["size"], "sha256": identity["sha256"]}
        manifest["bytes"] = sum(item["bytes"] for item in manifest["files"].values())
        marker.write_text(json.dumps(manifest), encoding="utf-8")
        verify_snapshot(snapshot)
        with self.assertRaisesRegex(bridge.PatchError, "No game files hold a translation"):
            self.plan()

    def test_lookalike_log_message_never_authorizes_a_plan(self) -> None:
        with patch.object(self, "stage", side_effect=RuntimeError(SYMPTOM)):
            error = self.fail_build()
        self.assertIs(type(error), RuntimeError)
        with self.assertRaisesRegex(bridge.PatchError, "No game files hold a translation"):
            self.plan()

    def test_broken_refusal_record_never_authorizes_a_plan(self) -> None:
        self.fail_build()
        (self.session / bridge.PACKAGE_REFUSED_NAME).write_text('{"packages": {"19": "wrong package"}}', encoding="utf-8")
        with self.assertRaisesRegex(bridge.PatchError, "No game files hold a translation"):
            self.plan()

    def test_package_absent_from_snapshot_never_gets_a_plan(self) -> None:
        self.output_package = "21"
        error = self.fail_build()
        self.assertNotIsInstance(error, bridge.PatchError)
        with self.assertRaisesRegex(bridge.PatchError, "No game files hold a translation"):
            self.plan()


if __name__ == "__main__":
    unittest.main()
