"""Synthetic bridge continuation probes; no phone, real package or game dump is used.

Python 3.12 only. Authored during pass 1; execute in pass 2. The sole synthetic
staging seam replaces _stage_translation/_stage_removal, not receipt/hash/delta checks.
Fingerprinting real package layouts remains the external EN/ID parity gate.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import pristine_delta
import run_artifacts as artifacts
from mobile_snapshot import checkpoint_snapshot, extract_snapshot, verify_snapshot

SPEC = importlib.util.spec_from_file_location("bridge_continuation_probe", ROOT / "android/app/src/main/python/android_bridge.py")
assert SPEC is not None and SPEC.loader is not None
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


class BridgeContinuation(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="hok-bridge-probe-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.engine = self.root / "engine"
        self.engine.mkdir()
        (self.engine / "code.bin").write_bytes(b"synthetic producer, never Android engine bytes")
        self.session = self.root / "session"
        self.session.mkdir()
        self.keep = self.root / "keep"
        self.keep.mkdir()
        self.apk = self.root / "normal.apk"
        self.apk.write_bytes(b"synthetic normal APK; not installed or parsed")
        self.run_id = "91e93575-6767-45f6-8144-80bfa64ece0f"
        data = {"packages/1/1.info": b'{"version":"fixture"}', "packages/1/1.db": b"pristine",
                "packages/1/1_0.db": b"unchanged", "Watchdog/BrokenList.db": b"rollback watchdog"}
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as archive:
            for name, payload in data.items():
                member = tarfile.TarInfo(name)
                member.size = len(payload)
                archive.addfile(member, io.BytesIO(payload))
        stream.seek(0)
        manifest = extract_snapshot(stream, self.session / "snapshot")
        producer = {"schema": 1, "complete": True, "kind": "android", "components": {
            "installed_apks": {"base.apk": artifacts.file_identity(self.apk)},
            "engine": {"manifest_sha256": hashlib.sha256(b"fixture manifest").hexdigest(),
                       "files_key": artifacts.identity_key(artifacts.tree_manifest(self.engine))},
            "native": {"packaged_in_apks": True}, "abi": ["fixture-abi"]}}
        files = {name: {"size": item["bytes"], "sha256": item["sha256"]} for name, item in manifest["files"].items()}
        self.identity = artifacts.make_input_identity(
            target={"device": "fixture", "provider": "root", "android_user": 0, "package": "com.tencent.tmgp.osgame"},
            request={"action": "translate", "language": "en", "options": {}},
            game={"files": files, "readiness": {"fixture_closed_and_downloads_finished": True}},
            apks={"normal": artifacts.file_identity(self.apk), "prepared": {"fixture": True}},
            delta=bridge._delta_identity(self.keep),
            translation={"engine_files_key": producer["components"]["engine"]["files_key"]}, producer=producer)
        checkpoint_snapshot(self.session / "snapshot", identity=self.identity, run_id=self.run_id, publish=True)
        self.prepare = patch.object(bridge, "_prepare", lambda root: None)
        self.prepare.start()
        self.addCleanup(self.prepare.stop)
        self.stage_calls = 0

    def stage(self, engine: str, scratch_root: str, *args) -> str:
        """Clearly scoped synthetic staging seam; actual delta binary/hash checks remain real."""
        self.stage_calls += 1
        scratch = Path(scratch_root)
        bridge._own_legacy_build(scratch)
        output = scratch / "out"
        (output / "1").mkdir(parents=True)
        (output / "1/1.db").write_bytes(b"translated")
        # Restored-but-unstaged output must be part of the full delta and final manifest.
        (output / "1/1_0.db").write_bytes(b"restored pristine body")
        hashes = {name: artifacts.file_identity(output / name)["sha256"] for name in ("1/1.db", "1/1_0.db")}
        summary = {"language": "en", "packages": [], "counts": {}, "pristine": {"restored": ["1/1_0.db"]}}
        (output / "device_patch_summary.json").write_text(json.dumps({"language": "en", "packages": []}), encoding="utf-8")
        (scratch / "staged-hashes.json").write_text(json.dumps(hashes), encoding="utf-8")
        delta = pristine_delta.make(scratch / "snapshot/packages", output, fingerprint=False,
                                    info={"patcher": "android", "fixture_only": True})
        pristine_delta.write(delta, scratch / bridge.SESSION_DELTA)
        return json.dumps(summary)

    def build(self, *, identity: dict | None = None, remove: bool = False) -> dict:
        with patch.object(bridge, "_stage_translation", self.stage), patch.object(bridge, "_stage_removal", self.remove_stage):
            return json.loads(bridge.build_checkpoint(str(self.engine), str(self.session), self.run_id,
                str(self.apk), artifacts.file_identity(self.apk)["sha256"], "en", str(self.keep),
                json.dumps(self.identity if identity is None else identity), remove))

    def remove_stage(self, engine: str, scratch_root: str, *args) -> str:
        summary = json.loads(self.stage(engine, scratch_root))
        pristine_delta.write(pristine_delta.Delta((), {"patcher": "android", "removed": True}),
                             Path(scratch_root) / bridge.SESSION_DELTA)
        summary["removed"] = ["1/1.db", "1/1_0.db"]
        return json.dumps(summary)

    def inspect(self, result: dict, identity: dict | None = None) -> dict:
        with patch.object(bridge, "_stage_translation", side_effect=AssertionError("reuse staged again")):
            return json.loads(bridge.inspect_build_checkpoint(str(self.engine), str(self.session), self.run_id,
                result["attempt"], str(self.apk), str(self.keep), json.dumps(identity or self.identity)))

    def test_complete_reuse_performs_zero_stage_calls(self) -> None:
        result = self.build()
        root = Path(result["result_root"])
        manifest = artifacts.read_record(root / "final-manifest.json")
        self.assertEqual(manifest["files"]["metrics.json"], artifacts.file_identity(root / "metrics.json"))
        before = artifacts.tree_manifest(root)
        reused = self.inspect(result)
        self.assertEqual(self.stage_calls, 1)
        self.assertEqual(reused, result)
        self.assertEqual(before, artifacts.tree_manifest(Path(result["result_root"])))

    def test_build_verifies_source_once_on_each_side_of_staging(self) -> None:
        game_file = self.session / "snapshot/packages/1/1.db"
        original_open = Path.open
        reads = 0

        def count_reads(path, mode="r", *args, **kwargs):
            nonlocal reads
            if path == game_file and mode == "rb":
                reads += 1
            return original_open(path, mode, *args, **kwargs)

        def stage(*args):
            nonlocal reads
            self.assertEqual(reads, 1)
            summary = self.stage(*args)
            reads = 0
            return summary

        apk_sha256 = artifacts.file_identity(self.apk)["sha256"]
        with patch.object(Path, "open", count_reads), patch.object(bridge, "_stage_translation", stage):
            result = json.loads(bridge.build_checkpoint(str(self.engine), str(self.session), self.run_id,
                str(self.apk), apk_sha256, "en", str(self.keep), json.dumps(self.identity)))
        self.assertEqual(reads, 1)
        self.assertTrue(result["reusable"])

    def test_build_does_not_publish_when_source_changes_during_staging(self) -> None:
        game_file = self.session / "snapshot/packages/1/1.db"

        def stage(*args):
            summary = self.stage(*args)
            game_file.write_bytes(b"tampered")  # Same length as the fixture's original "pristine".
            return summary

        with patch.object(bridge, "_stage_translation", stage), self.assertRaisesRegex(ValueError, "Snapshot file changed"):
            bridge.build_checkpoint(str(self.engine), str(self.session), self.run_id, str(self.apk),
                artifacts.file_identity(self.apk)["sha256"], "en", str(self.keep), json.dumps(self.identity))
        self.assertFalse(list((self.session / "build-attempts").rglob(artifacts.RECEIPT_NAME)))

    def phone_output_stage(self, engine: str, scratch_root: str, *args) -> str:
        """Exact run-63ff output layout, synthetic bytes; runtime receipts are not game files."""
        summary = self.stage(engine, scratch_root, *args)
        scratch = Path(scratch_root)
        output = scratch / "out"
        for package in ("10", "1050016095", "15", "19", "20", "21"):
            (output / package).mkdir()
            for name in (f"{package}.db", f"{package}_0.db"):
                (output / package / name).write_bytes(b"synthetic staged " + name.encode())
        hashes = {name: item["sha256"] for name, item in artifacts.tree_manifest(output).items()
                  if name != "device_patch_summary.json"}
        report = {"status": "verified", "package_id": "1", "replacement_count": 1,
                  "verified_unrelated_assets": 0, "batch_builder_invocations": 1,
                  "position_reference_updates": [], "position_reference_insertions": [],
                  "slot_donation_updates": [],
                  "assets": [{"hash": "0123456789ABCDEF", "chunks": 1, "raw_size": 10,
                              "raw_sha256": hashlib.sha256(b"translated").hexdigest()}],
                  "files": [{"name": name, "source_sha256": "0" * 64,
                             "staged_sha256": hashes[f"1/{name}"]}
                            for name in ("1.db", "1_0.db")]}
        (output / "package1_stage_manifest.json").write_text(json.dumps(report), encoding="utf-8")
        (output / "package1_metadata_axwzfeqp").mkdir()
        (scratch / "staged-hashes.json").write_text(json.dumps(hashes), encoding="utf-8")
        pristine_delta.write(pristine_delta.make(scratch / "snapshot/packages", output, fingerprint=False),
                             scratch / bridge.SESSION_DELTA)
        return summary

    def test_phone_runtime_metadata_does_not_enter_staged_payload(self) -> None:
        with patch.object(bridge, "_stage_translation", self.phone_output_stage):
            result = json.loads(bridge.build_checkpoint(str(self.engine), str(self.session), self.run_id,
                str(self.apk), artifacts.file_identity(self.apk)["sha256"], "en", str(self.keep),
                json.dumps(self.identity)))
        self.assertEqual(len(artifacts.read_record(Path(result["hashes_path"]))), 14)
        self.assertEqual(result, self.inspect(result))
        report = Path(result["output_root"]) / "package1_stage_manifest.json"
        self.assertTrue(report.is_file())
        self.assertIn("out/package1_stage_manifest.json", result["receipt"]["artifacts"])

    def test_runtime_metadata_unknown_or_incomplete_output_refuses_publication(self) -> None:
        for mutation in ("root-file", "root-dir", "metadata-body", "metadata-suffix", "metadata-orphan",
                         "report-name", "status", "package", "schema", "asset-hash", "file-path",
                         "nested-package", "empty-package"):
            def bad_stage(engine: str, scratch_root: str, *args) -> str:
                summary = self.phone_output_stage(engine, scratch_root, *args)
                output = Path(scratch_root) / "out"
                report_path = output / "package1_stage_manifest.json"
                report = json.loads(report_path.read_text(encoding="utf-8"))
                if mutation == "root-file":
                    (output / "unexpected.db").write_bytes(b"unknown output")
                elif mutation == "root-dir":
                    (output / "unexpected").mkdir()
                elif mutation == "metadata-body":
                    (output / "package1_metadata_axwzfeqp/payload.db").write_bytes(b"hidden")
                elif mutation == "metadata-suffix":
                    (output / "package1_metadata_wrong").mkdir()
                elif mutation == "metadata-orphan":
                    (output / "package2_metadata_axwzfeqp").mkdir()
                elif mutation == "report-name":
                    report_path.rename(output / "package1_other_manifest.json")
                elif mutation == "status":
                    report["status"] = "incomplete"
                elif mutation == "package":
                    report["package_id"] = "10"
                elif mutation == "schema":
                    report["unknown"] = True
                elif mutation == "asset-hash":
                    report["assets"][0]["raw_sha256"] = "bad"
                elif mutation == "file-path":
                    report["files"][0]["name"] = "../1.db"
                elif mutation == "nested-package":
                    (output / "1/nested").mkdir()
                else:
                    (output / "2").mkdir()
                if mutation != "report-name":
                    report_path.write_text(json.dumps(report), encoding="utf-8")
                return summary
            with self.subTest(mutation=mutation), patch.object(bridge, "_stage_translation", bad_stage):
                with self.assertRaises(artifacts.ArtifactError):
                    bridge.build_checkpoint(str(self.engine), str(self.session), self.run_id,
                        str(self.apk), artifacts.file_identity(self.apk)["sha256"], "en", str(self.keep),
                        json.dumps(self.identity))

    def test_metadata_receipt_tampering_and_final_numeric_changes_refuse_reuse(self) -> None:
        with patch.object(bridge, "_stage_translation", self.phone_output_stage):
            result = json.loads(bridge.build_checkpoint(str(self.engine), str(self.session), self.run_id,
                str(self.apk), artifacts.file_identity(self.apk)["sha256"], "en", str(self.keep),
                json.dumps(self.identity)))
        output = Path(result["output_root"])
        report_path = output / "package1_stage_manifest.json"
        original = report_path.read_bytes()
        report = json.loads(original)
        # Structurally valid historical evidence still must match the committed receipt bytes.
        report["verified_unrelated_assets"] += 1
        report_path.write_text(json.dumps(report), encoding="utf-8")
        with self.assertRaises(artifacts.ArtifactError):
            self.inspect(result)
        report_path.write_bytes(original)
        for mutation in ("tamper", "extra", "empty-unknown-dir", "nonempty-metadata"):
            with self.subTest(mutation=mutation):
                if mutation == "tamper":
                    path = output / "1/1.db"
                    saved = path.read_bytes()
                    path.write_bytes(b"corrupted!")
                elif mutation == "extra":
                    path = output / "1/unexpected.db"
                    path.write_bytes(b"extra numeric-package payload")
                elif mutation == "empty-unknown-dir":
                    path = output / "unexpected"
                    path.mkdir()
                else:
                    path = output / "package1_metadata_axwzfeqp/hidden.db"
                    path.write_bytes(b"hidden payload")
                with self.assertRaises(artifacts.ArtifactError):
                    bridge._verify_final_build(Path(result["result_root"]), remove=False)
                with self.assertRaises(artifacts.ArtifactError):
                    self.inspect(result)
                if mutation == "tamper":
                    path.write_bytes(saved)
                elif path.is_dir():
                    path.rmdir()
                else:
                    path.unlink()
        self.assertEqual(result, self.inspect(result))

    def test_summary_delta_restored_missing_extra_and_tampered_refuse(self) -> None:
        for mutation in ("summary-only", "delta", "restored", "extra", "tamper"):
            with self.subTest(mutation=mutation):
                result = self.build()
                root = Path(result["result_root"])
                if mutation == "summary-only":
                    (root / "build-receipt.json").unlink()
                elif mutation == "delta":
                    (root / bridge.SESSION_DELTA).unlink()
                elif mutation == "restored":
                    (root / "out/1/1_0.db").unlink()
                elif mutation == "extra":
                    (root / "out/1/1_1.db").write_bytes(b"extra")
                else:
                    (root / "out/1/1.db").write_bytes(b"same-size!")
                with self.assertRaises((artifacts.ArtifactError, OSError)):
                    self.inspect(result)

    def test_declared_output_cannot_disappear_from_output_hashes_and_delta(self) -> None:
        def omit_declared(engine: str, scratch_root: str, *args) -> str:
            summary = self.stage(engine, scratch_root, *args)
            scratch = Path(scratch_root)
            (scratch / "out/1/1_0.db").unlink()
            hashes = json.loads((scratch / "staged-hashes.json").read_text(encoding="utf-8"))
            del hashes["1/1_0.db"]
            (scratch / "staged-hashes.json").write_text(json.dumps(hashes), encoding="utf-8")
            # All three byte-level views agree, but the summary still requires restored output.
            pristine_delta.write(pristine_delta.make(scratch / "snapshot/packages", scratch / "out",
                                                       fingerprint=False), scratch / bridge.SESSION_DELTA)
            return summary
        with patch.object(bridge, "_stage_translation", omit_declared), self.assertRaises(artifacts.ArtifactError):
            bridge.build_checkpoint(str(self.engine), str(self.session), self.run_id, str(self.apk),
                artifacts.file_identity(self.apk)["sha256"], "en", str(self.keep), json.dumps(self.identity))
        with patch.object(bridge, "_stage_translation", omit_declared), self.assertRaises(artifacts.ArtifactError):
            bridge.build_checkpoint(str(self.engine), str(self.session), self.run_id, str(self.apk),
                artifacts.file_identity(self.apk)["sha256"], "en", str(self.keep), "null")

    def test_remove_declared_file_cannot_disappear_consistently(self) -> None:
        identity = copy.deepcopy(self.identity)
        identity["request"]["action"] = "remove"
        def omit_removed(engine: str, scratch_root: str, *args) -> str:
            summary = json.loads(self.remove_stage(engine, scratch_root, *args))
            # Isolate the removed-list gate from the translation restored-list gate.
            summary["pristine"] = {"restored": []}
            scratch = Path(scratch_root)
            (scratch / "out/1/1_0.db").unlink()
            hashes = json.loads((scratch / "staged-hashes.json").read_text(encoding="utf-8"))
            del hashes["1/1_0.db"]
            (scratch / "staged-hashes.json").write_text(json.dumps(hashes), encoding="utf-8")
            return json.dumps(summary)
        with patch.object(bridge, "_stage_removal", omit_removed), self.assertRaises(artifacts.ArtifactError):
            bridge.build_checkpoint(str(self.engine), str(self.session), self.run_id, str(self.apk),
                artifacts.file_identity(self.apk)["sha256"], "en", str(self.keep), json.dumps(identity), True)

    def test_changed_source_producer_apk_delta_declines_reuse(self) -> None:
        result = self.build()
        for field in ("game", "producer", "apks", "delta"):
            changed = copy.deepcopy(self.identity)
            if field == "game":
                changed[field]["files"]["packages/1/1.db"]["sha256"] = "f" * 64
            elif field == "producer":
                changed[field]["components"]["installed_apks"]["base.apk"]["sha256"] = "f" * 64
            elif field == "apks":
                changed[field]["normal"]["sha256"] = "f" * 64
            else:
                changed[field]["present"] = True
            with self.subTest(field=field), self.assertRaises(artifacts.ArtifactError):
                self.inspect(result, changed)

    def test_interrupted_build_restarts_only_build_in_new_attempt(self) -> None:
        original = artifacts.tree_manifest(self.session / "snapshot")
        def interrupt(*args) -> str:
            self.stage(*args)
            raise InterruptedError("native stage boundary")
        with patch.object(bridge, "_stage_translation", interrupt), self.assertRaises(InterruptedError):
            bridge.build_checkpoint(str(self.engine), str(self.session), self.run_id, str(self.apk),
                artifacts.file_identity(self.apk)["sha256"], "en", str(self.keep), json.dumps(self.identity))
        failed = next((self.session / "build-attempts").iterdir())
        bridge.reset_checkpoint_attempt(str(self.engine), str(self.session), self.run_id, failed.name)
        self.assertEqual(sorted(entry.name for entry in failed.iterdir()), ["attempt-owner.json"])
        bridge.reset_checkpoint_attempt(str(self.engine), str(self.session), self.run_id, failed.name)
        result = self.build()
        self.assertNotEqual(result["attempt"], failed.name)
        self.assertEqual(original, artifacts.tree_manifest(self.session / "snapshot"))
        self.assertTrue(self.apk.exists())

    def test_publication_interruption_before_after_commit(self) -> None:
        publish = artifacts.publish_receipt
        for boundary in ("artifacts_verified", "artifacts_synced", "receipt_synced", "receipt_committed", "receipt_read_back"):
            def interrupted(*args, **kwargs):
                def hit(point: str) -> None:
                    if point == boundary:
                        raise InterruptedError(point)
                return publish(*args, **kwargs, failpoint=hit)
            before = set((self.session / "build-attempts").iterdir()) if (self.session / "build-attempts").exists() else set()
            with patch.object(artifacts, "publish_receipt", interrupted), self.assertRaises(InterruptedError):
                self.build()
            attempt = next(iter(set((self.session / "build-attempts").iterdir()) - before))
            if boundary in {"receipt_committed", "receipt_read_back"}:
                self.inspect({"attempt": attempt.name})
            else:
                with self.assertRaises(artifacts.ArtifactError):
                    self.inspect({"attempt": attempt.name})

    def test_reset_preserves_published_and_prior_checkpoint(self) -> None:
        result = self.build()
        before = artifacts.tree_manifest(Path(result["result_root"]))
        with self.assertRaises(bridge.PatchError):
            bridge.reset_checkpoint_attempt(str(self.engine), str(self.session), self.run_id, result["attempt"])
        with self.assertRaises((artifacts.ArtifactError, ValueError)):
            bridge.reset_checkpoint_attempt(str(self.engine), str(self.session), "wrong-owner", result["attempt"])
        self.assertEqual(before, artifacts.tree_manifest(Path(result["result_root"])))
        # No ownership of legacy session products: a missing owner record refuses, naming that cause.
        with self.assertRaisesRegex(bridge.PatchError, "No build ownership"):
            bridge.clear_build(str(self.session))
        self.assertTrue((self.session / "snapshot/build-receipt.json").is_file())

    def _killed_attempt(self, *, link: bool = True) -> tuple[Path, Path]:
        """An attempt as `build_checkpoint` leaves it when killed before the scratch's build owner."""
        parent = self.session / "build-attempts"
        parent.mkdir(exist_ok=True)
        attempt = artifacts.create_attempt(parent, run_id=self.run_id, stage="staged")
        scratch = attempt / "scratch"
        scratch.mkdir()
        if link:
            try:
                (scratch / "snapshot").symlink_to(self.session.resolve() / "snapshot", target_is_directory=True)
            except OSError as error:
                self.skipTest("Host cannot create private directory symlink: " + str(error))
        return attempt, scratch

    def reset(self, attempt: Path, run_id: str | None = None) -> str:
        return bridge.reset_checkpoint_attempt(str(self.engine), str(self.session), run_id or self.run_id, attempt.name)

    def test_crash_before_scratch_link_clears_empty_scratch_and_restarts_fresh(self) -> None:
        attempt, scratch = self._killed_attempt(link=False)
        self.assertEqual(self.reset(attempt), "{}")
        self.assertFalse(scratch.exists())
        self.assertTrue((attempt / "attempt-owner.json").is_file())
        result = self.build()
        self.assertNotEqual(result["attempt"], attempt.name)
        self.assertTrue((self.session / "snapshot/Watchdog/BrokenList.db").is_file())

    def test_phone_c3_killed_before_build_owner_clears_link_never_target(self) -> None:
        """Phone f15a72e, 2026-11-12, C3: attempt owner, scratch with only the snapshot link, no build owner."""
        snapshot = artifacts.tree_manifest(self.session / "snapshot")
        attempt, scratch = self._killed_attempt()
        owner = (attempt / "attempt-owner.json").read_bytes()
        self.assertEqual(self.reset(attempt), "{}")
        self.assertFalse(scratch.exists() or scratch.is_symlink())
        self.assertEqual((attempt / "attempt-owner.json").read_bytes(), owner)
        self.assertEqual(snapshot, artifacts.tree_manifest(self.session / "snapshot"))
        self.assertEqual(self.reset(attempt), "{}")  # A repeated reset on the next reopen is a no-op.
        result = self.build()
        self.assertNotEqual(result["attempt"], attempt.name)
        self.assertEqual(snapshot, artifacts.tree_manifest(self.session / "snapshot"))

    def test_scratch_without_build_owner_refuses_anything_unexpected(self) -> None:
        snapshot = artifacts.tree_manifest(self.session / "snapshot")
        outside = self.root / "outside"
        outside.mkdir()
        cases = {
            "extra file": lambda scratch: (scratch / "out").mkdir(),
            "partial owner": lambda scratch: (scratch / "build-owner.json.partial").write_bytes(b"{"),
            "foreign link": lambda scratch: ((scratch / "snapshot").unlink(),
                                             (scratch / "snapshot").symlink_to(outside, target_is_directory=True)),
            "directory, not link": lambda scratch: ((scratch / "snapshot").unlink(), (scratch / "snapshot").mkdir()),
        }
        for name, damage in cases.items():
            with self.subTest(case=name):
                attempt, scratch = self._killed_attempt()
                damage(scratch)
                before = sorted(entry.name for entry in scratch.iterdir())
                with self.assertRaisesRegex(bridge.PatchError, "without ownership"):
                    self.reset(attempt)
                self.assertEqual(before, sorted(entry.name for entry in scratch.iterdir()))
        self.assertEqual(snapshot, artifacts.tree_manifest(self.session / "snapshot"))

    def test_scratch_without_build_owner_requires_attempt_owner(self) -> None:
        attempt, scratch = self._killed_attempt()
        with self.assertRaisesRegex(artifacts.ArtifactError, "Attempt owner differs"):
            self.reset(attempt, "another-run")
        (attempt / "attempt-owner.json").unlink()
        with self.assertRaises(FileNotFoundError):  # Killed before the attempt owner: never adopted.
            self.reset(attempt)
        self.assertTrue((scratch / "snapshot").is_symlink())

    def test_remove_receipt_explicit_null_delta(self) -> None:
        identity = copy.deepcopy(self.identity)
        identity["request"]["action"] = "remove"
        result = self.build(identity=identity, remove=True)
        self.assertIsNone(result["receipt"]["references"]["delta"])
        self.assertEqual(result, self.inspect(result, identity))
        self.assertFalse((self.keep / pristine_delta.DELTA_NAME).exists())

    def test_no_producer_still_checks_final_output(self) -> None:
        def incomplete(*args) -> str:
            summary = self.stage(*args)
            (Path(args[1]) / "out/1/1_0.db").unlink()
            return summary
        with patch.object(bridge, "_stage_translation", incomplete), self.assertRaises(artifacts.ArtifactError):
            bridge.build_checkpoint(str(self.engine), str(self.session), self.run_id, str(self.apk),
                artifacts.file_identity(self.apk)["sha256"], "en", str(self.keep), "null")
        with patch.object(bridge, "_stage_translation", self.stage):
            fresh = json.loads(bridge.build_checkpoint(str(self.engine), str(self.session), self.run_id,
                str(self.apk), artifacts.file_identity(self.apk)["sha256"], "en", str(self.keep), "null"))
        self.assertFalse(fresh["reusable"])
        self.assertIsNone(fresh["receipt"])

    def test_snapshot_owner_source_extra_and_partial_refuse(self) -> None:
        with self.assertRaises(artifacts.ArtifactError):
            checkpoint_snapshot(self.session / "snapshot", identity=self.identity, run_id="wrong")
        (self.session / "snapshot/extra.bin").write_bytes(b"outside manifest")
        with self.assertRaises(artifacts.ArtifactError):
            checkpoint_snapshot(self.session / "snapshot", identity=self.identity, run_id=self.run_id)
        (self.session / "snapshot/extra.bin").unlink()
        (self.session / "snapshot/packages/1/1.db").unlink()
        with self.assertRaises(ValueError):
            verify_snapshot(self.session / "snapshot")

    def test_snapshot_checkpoint_reads_each_game_file_once_per_receipt_audit(self) -> None:
        destination = self.session / "snapshot"
        game_file = destination / "packages/1/1.db"
        original_open = Path.open
        reads = 0

        def count_reads(path, mode="r", *args, **kwargs):
            nonlocal reads
            if path == game_file and mode == "rb":
                reads += 1
            return original_open(path, mode, *args, **kwargs)

        (destination / artifacts.RECEIPT_NAME).unlink()
        with patch.object(Path, "open", count_reads):
            published = checkpoint_snapshot(destination, identity=self.identity, run_id=self.run_id, publish=True)
        self.assertEqual(reads, 3)  # Before publication, just before rename, and the committed read-back.
        reads = 0
        with patch.object(Path, "open", count_reads):
            reused = checkpoint_snapshot(destination, identity=self.identity, run_id=self.run_id)
        self.assertEqual(reads, 1)
        self.assertEqual(reused, published)

    def test_snapshot_checkpoint_refuses_same_size_corruption_before_publication(self) -> None:
        destination = self.session / "snapshot"
        receipt = destination / artifacts.RECEIPT_NAME
        receipt.unlink()
        (destination / "packages/1/1.db").write_bytes(b"tampered")
        with self.assertRaises(artifacts.ArtifactError):
            checkpoint_snapshot(destination, identity=self.identity, run_id=self.run_id, publish=True)
        self.assertFalse(receipt.exists())

    def test_snapshot_publication_interrupted_before_after_commit(self) -> None:
        import shutil
        publish = artifacts.publish_receipt
        for boundary in ("artifacts_verified", "artifacts_synced", "receipt_synced", "receipt_committed", "receipt_read_back"):
            destination = self.root / ("snapshot-" + boundary)
            shutil.copytree(self.session / "snapshot", destination)
            (destination / "build-receipt.json").unlink()
            def interrupted(*args, **kwargs):
                def hit(point: str) -> None:
                    if point == boundary:
                        raise InterruptedError(point)
                return publish(*args, **kwargs, failpoint=hit)
            with patch.object(artifacts, "publish_receipt", interrupted), self.assertRaises(InterruptedError):
                checkpoint_snapshot(destination, identity=self.identity, run_id=self.run_id, publish=True)
            if boundary in {"receipt_committed", "receipt_read_back"}:
                checkpoint_snapshot(destination, identity=self.identity, run_id=self.run_id)
            else:
                with self.assertRaises(artifacts.ArtifactError):
                    checkpoint_snapshot(destination, identity=self.identity, run_id=self.run_id)

    def test_reset_refuses_linked_products_and_preserves_watchdog(self) -> None:
        owner = artifacts.create_attempt(self.session / "build-attempts" if (self.session / "build-attempts").exists()
                                         else self._build_parent(), run_id=self.run_id, stage="staged")
        scratch = owner / "scratch"
        scratch.mkdir()
        bridge._own_legacy_build(scratch)
        outside = self.root / "outside"
        outside.mkdir()
        marker = outside / "important.bin"
        marker.write_bytes(b"unrelated bytes")
        try:
            (scratch / "out").symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest("Host cannot create private directory symlink: " + str(error))
        with self.assertRaises(bridge.PatchError):
            bridge.reset_checkpoint_attempt(str(self.engine), str(self.session), self.run_id, owner.name)
        self.assertEqual(marker.read_bytes(), b"unrelated bytes")
        self.assertEqual((self.session / "snapshot/Watchdog/BrokenList.db").read_bytes(), b"rollback watchdog")

    def _build_parent(self) -> Path:
        parent = self.session / "build-attempts"
        parent.mkdir()
        return parent

    def test_snapshot_attempt_reset_never_adopts_fragments(self) -> None:
        attempt = json.loads(bridge.begin_snapshot_attempt(str(self.engine), str(self.session), self.run_id))
        destination = Path(attempt["destination"])
        destination.mkdir()
        (destination / "partial.bin").write_bytes(b"partial transport")
        bridge.reset_checkpoint_attempt(str(self.engine), str(self.session), self.run_id, attempt["attempt"], "snapshot")
        self.assertFalse(destination.exists())
        self.assertTrue((self.session / "snapshot/build-receipt.json").exists())
        fresh = json.loads(bridge.begin_snapshot_attempt(str(self.engine), str(self.session), self.run_id))
        self.assertNotEqual(attempt["attempt"], fresh["attempt"])

    # Phone f15a72e, 2026-11-12, run 248572aa: after an approved Re-download of package 1 the game
    # downloaded it again, and the next build dropped `redownload.json` mid-build, so build_checkpoint's
    # kept-delta check refused every first build after a Re-download.

    def _kept_after_redownload(self, packages: list[str]) -> dict:
        """The kept folder after a Re-download: delta.bin, staged-hashes.json and redownload.json."""
        translated = self.root / "previous-install"
        (translated / "1").mkdir(parents=True)
        (translated / "1/1.db").write_bytes(b"previous translation")
        delta = pristine_delta.make(self.session / "snapshot/packages", translated, fingerprint=False,
                                    info={"patcher": "android", "fixture_only": True})
        pristine_delta.write(delta, self.keep / pristine_delta.DELTA_NAME)
        pristine_delta.record_staged_hashes(self.keep / pristine_delta.STAGED_HASHES_NAME, delta.staged_hashes)
        (self.keep / bridge.REDOWNLOAD_NAME).write_text(json.dumps({"packages": packages}), encoding="utf-8")
        identity = copy.deepcopy(self.identity)
        identity["delta"] = bridge._delta_identity(self.keep)
        return identity

    def _kept_bytes(self) -> dict:
        return {path.name: path.read_bytes() for path in sorted(self.keep.iterdir())}

    def _real_build(self, identity: dict, during=None) -> dict:
        """The real `build_snapshot` (and its `_refuse_stuck_update`); only restore and the native pass are fixtures."""
        make = pristine_delta.make

        def native_pass(root: Path, scratch: Path, language: str, trusted: Path | None = None) -> str:
            self.stage_calls += 1
            output = scratch / "out"
            (output / "1").mkdir(parents=True)
            (output / "1/1.db").write_bytes(b"translated")
            (output / "device_patch_summary.json").write_text(json.dumps({"language": "en", "packages": []}),
                                                             encoding="utf-8")
            (scratch / "staged-hashes.json").write_text(json.dumps(
                {"1/1.db": artifacts.file_identity(output / "1/1.db")["sha256"]}), encoding="utf-8")
            if during is not None:
                during()
            return json.dumps({"language": "en", "counts": {"tables": 1}, "text_skipped": [], "packages": [
                {"mode": "full", "stage_report": {"replacement_count": 1}}]})

        first = {"mode": "first", "rebuilt": [], "pristine": [], "sha256": {}}
        with patch.object(bridge, "_restore_pristine", lambda *args, **kwargs: first), \
                patch.object(bridge, "_build_scratch", native_pass), \
                patch.object(pristine_delta, "make", lambda *args, **kwargs: make(*args, **{**kwargs, "fingerprint": False})):
            return json.loads(bridge.build_checkpoint(str(self.engine), str(self.session), self.run_id,
                str(self.apk), artifacts.file_identity(self.apk)["sha256"], "en", str(self.keep), json.dumps(identity)))

    def test_phone_f15a72e_build_after_redownload_keeps_record_and_publishes(self) -> None:
        identity = self._kept_after_redownload(["1"])  # package 1 is back: packages/1/1.db is in the snapshot
        record = artifacts.file_identity(self.keep / bridge.REDOWNLOAD_NAME)
        before = self._kept_bytes()
        result = self._real_build(identity)
        # The build only read the kept folder: every record, the Re-download one too, is byte-identical.
        self.assertEqual(before, self._kept_bytes())
        self.assertEqual(result["summary"]["redownload_done"], record)
        self.assertTrue(result["reusable"])
        # A restart reuses the published build with zero staging: the receipt still binds the kept identity.
        self.assertEqual(self.inspect(result, identity), result)
        self.assertEqual(self.stage_calls, 1)
        plan = json.loads(bridge.finalization_plan(str(self.engine), result["result_root"]))
        self.assertEqual(plan["redownload_done"], record)
        # Finalization drops exactly the bytes the build read as done, and nothing else.
        bridge._drop_redownload_done(self.keep, {"size": record["size"], "sha256": "0" * 64})
        self.assertTrue((self.keep / bridge.REDOWNLOAD_NAME).is_file())
        bridge._drop_redownload_done(self.keep, plan["redownload_done"])
        self.assertFalse((self.keep / bridge.REDOWNLOAD_NAME).exists())
        self.assertEqual({name: data for name, data in before.items() if name != bridge.REDOWNLOAD_NAME},
                         self._kept_bytes())
        # Once dropped, the old build no longer matches the kept identity, so it cannot apply as stale...
        with self.assertRaises(artifacts.ArtifactError):
            self.inspect(result, identity)
        # ...and the next build binds the new identity once, with no claim left to drop: no rebuild loop.
        after = copy.deepcopy(self.identity)
        after["delta"] = bridge._delta_identity(self.keep)
        self.assertIsNone(after["delta"]["files"][bridge.REDOWNLOAD_NAME])
        again = self._real_build(after)
        self.assertNotIn("redownload_done", again["summary"])
        self.assertIsNone(json.loads(bridge.finalization_plan(str(self.engine), again["result_root"]))["redownload_done"])
        self.assertEqual(self.inspect(again, after), again)

    def test_redownload_record_still_waiting_refuses_and_is_kept(self) -> None:
        identity = self._kept_after_redownload(["1", "7"])  # package 7 has no .db in the snapshot
        before = self._kept_bytes()
        with self.assertRaisesRegex(bridge.PatchError, bridge.UPDATE_WAITING):
            self._real_build(identity)
        self.assertEqual(before, self._kept_bytes())

    def test_any_kept_change_during_build_still_refuses(self) -> None:
        changes = {
            bridge.REDOWNLOAD_NAME: lambda: (self.keep / bridge.REDOWNLOAD_NAME).unlink(),
            "redownload rewritten": lambda: (self.keep / bridge.REDOWNLOAD_NAME).write_text(
                json.dumps({"packages": ["2"]}), encoding="utf-8"),
            pristine_delta.STAGED_HASHES_NAME: lambda: pristine_delta.record_staged_hashes(
                self.keep / pristine_delta.STAGED_HASHES_NAME, {"f" * 64}),
            bridge.RESTORE_REFUSED_NAME: lambda: (self.keep / bridge.RESTORE_REFUSED_NAME).write_text(
                json.dumps({"packages": ["1"]}), encoding="utf-8"),
            pristine_delta.DELTA_NAME: lambda: (self.keep / pristine_delta.DELTA_NAME).unlink(),
        }
        for label, change in changes.items():
            with self.subTest(change=label):
                for path in self.keep.iterdir():
                    path.unlink()
                identity = self._kept_after_redownload(["1"])
                shutil.rmtree(self.root / "previous-install")
                with self.assertRaisesRegex(bridge.PatchError, "kept delta"):
                    self._real_build(identity, during=change)

    def test_copied_completed_output_never_drops_a_record(self) -> None:
        identity = self._kept_after_redownload(["1"])
        result = self._real_build(identity)
        (Path(result["result_root"]) / "reuse-provenance.json").write_text("{}", encoding="utf-8")
        self.assertIsNone(bridge._redownload_done(Path(result["result_root"])))


if __name__ == "__main__":
    if sys.version_info[:2] != (3, 12):
        raise SystemExit("Python 3.12 required")
    unittest.main()
