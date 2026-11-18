"""Synthetic Windows checkpoint/count probes, authored for Pass 2 only.

All bytes live in TemporaryDirectory, never a game/phone/immutable control fixture.
The tiny signed APK fixtures exercise real identity parsing. Staging is an explicit
counted synthetic producer; this probe never invokes build_patch or a native codec.
"""
from __future__ import annotations

import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "app"), str(ROOT / "tools")]
import patcher_core
import pristine_delta
from device_transaction import DeviceTransaction, ShellTransport, _publish
from patch_session import ApkJournal, RunStore, SessionError
from run_artifacts import ArtifactError, file_identity, read_record, tree_manifest, verify_receipt
from windows_checkpoints import Checkpoints, owned_attempt, prune_sessions
from _windows_fake_device import FakeAdb, Faults
from check_windows_repatch import PRISTINE, ENGLISH, INDONESIAN, PRISTINE_SUMMARY, Ui, _write


class CheckpointContinuation(unittest.TestCase):
    def setUp(self) -> None:
        from check_windows_recovery import signed_fixture
        self.temporary = tempfile.TemporaryDirectory(prefix="windows-checkpoints-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()  # TEMP can be an 8.3 short path; RunStore wants the long one
        self.work = self.base / "work"; self.work.mkdir()
        self.phone = self.base / "phone"
        _write(self.phone, {**PRISTINE, "1/1.info": b'{"version":"synthetic"}'})
        self.adb = FakeAdb(self.phone)
        self.adb.require_debuggable_run_as = True
        self.target = {"serial": self.adb.serial, "android_user": 0, "package": patcher_core.PACKAGE}
        self.store = RunStore(self.base / "state")
        self.owner = self.store.claim(self.work, self.target)
        self.addCleanup(lambda: self.owner.close())
        self.owner.authorize("remove" if "_remove_" in self._testMethodName else "translate", "en")
        self.owner.update(lifecycle="preparing")
        self.journal = ApkJournal(self.owner, create=True)
        for role, debug in (("source", False), ("normal", False), ("access", True)):
            shutil.copyfile(signed_fixture(self.base, debug=debug), self.journal.apk(role))
        self.journal.update(apks={role: patcher_core.apk_tools.apk_identity(self.journal.apk(role))
                                 for role in ("source", "normal", "access")})
        _publish(self.journal.directory / "preparation-source.json", {"schema": 1,
                 "run_id": self.owner.run_id, "target": self.target, "source": self.journal.record["apks"]["source"]})
        self.adb.installed = self.journal.apk("normal").read_bytes()
        vectors = read_record(ROOT / "tools/research/fixtures/run_artifacts/vectors.json")
        self.producer = copy.deepcopy(vectors["receipt"]["identity"]["producer"])
        with patch.object(patcher_core, "run_store", return_value=self.store):
            self.patcher = patcher_core.Patcher(Ui(), self.work)
        self.patcher.run_owner, self.patcher.run_store = self.owner, self.store
        self.patcher.adb, self.patcher.apk_journal = self.adb, self.journal
        self.patcher.normal_apk = self.journal.apk("normal")
        self.patcher.remove = self.owner.record["action"] == "remove"
        self.patcher._prepared_access = self.journal.apk("access")
        self.patcher._producer, self.patcher._producer_checked = self.producer, True
        self.patcher._ensure_access("fixture-initial")
        self.session = self.work / "sessions" / str(__import__("uuid").uuid4())
        self.owner.update(children={**self.owner.record["children"], "data_session": self.session.name})
        shutil.copytree(self.phone, self.session / patcher_core.LAYER)
        shutil.copytree(self.phone, self.session / "recovery/packages")
        live = ShellTransport(self.adb).inventory(self.session.name)
        _publish(self.session / "recovery-manifest.json", {**live, "target": self.target})
        _publish(self.session / "pull.json", {"data_version": '{"version":"synthetic"}',
                 "target": self.target, "mode": "full", "sha256": {
                     name.removeprefix("packages/"): item["sha256"] for name, item in live["files"].items()}})
        self.patcher.data_version = '{"version":"synthetic"}'
        self.checkpoint = Checkpoints(self.owner, self.session)
        self.checkpoint.publish_snapshot(self.journal.record["apks"], self.producer)
        self.owner.update(lifecycle="snapshot")
        self.builds = 0
        self.outputs = ENGLISH
        self.summary = copy.deepcopy(PRISTINE_SUMMARY)
        real_make = pristine_delta.make
        # These are deliberately unreadable synthetic containers; fingerprinting
        # belongs to the real external controls, not this coordinator fixture.
        self.make_patch = patch.object(pristine_delta, "make", side_effect=lambda *args, **kwargs:
                                      real_make(*args, **{**kwargs, "fingerprint": False}))
        self.make_patch.start(); self.addCleanup(self.make_patch.stop)
        self.patcher.build_translation = self.build
        self.patcher.pull_game_data = Mock(side_effect=AssertionError("snapshot transfer repeated"))

    def build(self, session: Path) -> tuple[dict, Path]:
        self.builds += 1
        attempt = owned_attempt(self.owner, session, "build")
        self.patcher._active_build = attempt
        output = attempt / "payload"
        _write(output, self.outputs)
        return copy.deepcopy(self.summary), output

    def stage(self, restored: list[str] | None = None) -> Path:
        result, output = self.build(self.session)
        identity = self.checkpoint.identity(self.journal.record["apks"], self.producer)
        root = self.patcher._publish_payload(self.session, result, output, restored or [], identity)
        self.owner.update(lifecycle="building")
        self.owner.update(lifecycle="staged")
        return root

    def reopen(self) -> None:
        """Actually release/reclaim durable state; keep only the fake phone process."""
        run_id = self.owner.run_id
        self.owner.close()
        self.owner = self.store.claim(self.work, self.target, run_id=run_id)
        self.patcher.run_owner = self.owner
        self.patcher.apk_journal = self.journal = ApkJournal(self.owner)
        self.patcher.file_transaction = None
        self.patcher._active_build = None
        self.patcher.debuggable_installed = False
        self.checkpoint = Checkpoints(self.owner, self.session)

    def test_snapshot_reopen_has_zero_transfer_and_one_build(self) -> None:
        self.reopen()
        self.patcher._continue_authorized()
        self.patcher.pull_game_data.assert_not_called()
        self.assertEqual(self.builds, 1)
        self.assertEqual(tree_manifest(self.phone), tree_manifest(self.session / "recovery/packages") | {
            name: file_identity(self.patcher._active_build / "committed/payload" / name) for name in ENGLISH})
        self.assertEqual(self.owner.record["lifecycle"], "finalized")
        self.assertFalse(self.adb.installed_identity()["debuggable"])

    def fresh_repeat(self) -> tuple[Path, Path]:
        """Resolve first fixture run, then authorize an independent Start over actual current bytes."""
        old = self.session
        self.stage(); self.patcher._continue_authorized()
        old_apks = self.journal
        self.owner.close()
        self.owner = self.store.claim(self.work, self.target)
        self.owner.authorize("translate", "en"); self.owner.update(lifecycle="preparing")
        self.journal = ApkJournal(self.owner, create=True)
        for role in ("source", "normal", "access"):
            shutil.copyfile(old_apks.apk("normal" if role == "source" else role), self.journal.apk(role))
        self.journal.update(apks={role: patcher_core.apk_tools.apk_identity(self.journal.apk(role))
                                 for role in ("source", "normal", "access")})
        with patch.object(patcher_core, "run_store", return_value=self.store):
            self.patcher = patcher_core.Patcher(Ui(), self.work)
        self.patcher.run_owner, self.patcher.run_store = self.owner, self.store
        self.patcher.adb, self.patcher.apk_journal = self.adb, self.journal
        self.patcher.normal_apk = self.journal.apk("normal")
        self.patcher._prepared_access = self.journal.apk("access")
        self.patcher._producer, self.patcher._producer_checked = self.producer, True
        self.patcher.build_translation = Mock(side_effect=AssertionError("translation build repeated"))
        self.patcher.restore_pristine = Mock(side_effect=AssertionError("pristine reconstruction repeated"))
        self.session = self.work / "sessions" / str(__import__("uuid").uuid4())
        self.owner.update(children={**self.owner.record["children"], "data_session": self.session.name})
        shutil.copytree(self.phone, self.session / "recovery/packages")
        # The first run finalized on the normal APK, so run-as is closed. This manifest
        # stands in for the new run's earlier pull; the run under test installs access itself.
        self.adb.require_debuggable_run_as = False
        try:
            live = ShellTransport(self.adb).inventory(self.session.name)
        finally:
            self.adb.require_debuggable_run_as = True
        _publish(self.session / "recovery-manifest.json", {**live, "target": self.target})
        _publish(self.session / "pull.json", read_record(old / "pull.json"))
        self.checkpoint = Checkpoints(self.owner, self.session)
        self.checkpoint.publish_snapshot(self.journal.record["apks"], self.producer)
        return old, old_apks.directory

    def test_completed_fresh_start_skips_restore_build_but_audits_and_restores_normal(self) -> None:
        old, _ = self.fresh_repeat()
        installs = self.adb.install_attempts
        writes = self.adb.faults.bytes["temp_copy"]
        result = self.patcher._resume_stages(self.session)
        self.assertEqual(result, self.summary)
        self.patcher.restore_pristine.assert_not_called(); self.patcher.build_translation.assert_not_called()
        self.assertGreaterEqual(self.adb.install_attempts - installs, 2)
        self.assertEqual(writes, self.adb.faults.bytes["temp_copy"])
        self.assertFalse(self.adb.installed_identity()["debuggable"])
        self.assertNotEqual(self.session, old)
        self.assertEqual(read_record(self.session / "completion-receipt.json")["outcome"], "verified_complete")

    def test_completed_mutations_decline_without_modifying_old_cache(self) -> None:
        from windows_checkpoints import reuse_completed
        old, apk_dir = self.fresh_repeat()
        identity = self.checkpoint.identity(self.journal.record["apks"], self.producer)
        marker = old / "completion-receipt.json"; baseline = marker.read_bytes()
        for field, value in (("outcome", "stopped_consistent"), ("outcome", "recovered_unconfirmed"),
                             ("installed_key", "0" * 64), ("schema", 99)):
            changed = json.loads(baseline); changed[field] = value; _publish(marker, changed)
            self.assertIsNone(reuse_completed(self.checkpoint, identity, self.journal.record["apks"]))
            marker.write_bytes(baseline)
        for key in ("language", "options"):
            changed = copy.deepcopy(identity)
            changed["request"][key] = "id" if key == "language" else {"fit_only": True}
            self.assertIsNone(reuse_completed(self.checkpoint, changed, self.journal.record["apks"]))
        source = apk_dir / "source.apk"; original = source.read_bytes(); source.write_bytes(b"X" * len(original))
        self.assertIsNone(reuse_completed(self.checkpoint, identity, self.journal.record["apks"]))
        source.write_bytes(original)
        self.assertEqual(marker.read_bytes(), baseline)

    def test_completed_copy_low_space_and_cut_keep_prior_receipt(self) -> None:
        import windows_checkpoints
        old, _ = self.fresh_repeat()
        identity = self.checkpoint.identity(self.journal.record["apks"], self.producer)
        original = (old / "completion-receipt.json").read_bytes()
        with patch.object(windows_checkpoints.shutil, "disk_usage", return_value=Mock(free=0)):
            self.assertIsNone(windows_checkpoints.reuse_completed(self.checkpoint, identity, self.journal.record["apks"]))
        self.assertIsNone(self.checkpoint.build_root())
        with patch.object(windows_checkpoints, "_durable_copy", side_effect=OSError("cut during owned copy")):
            with self.assertRaises(OSError):
                windows_checkpoints.reuse_completed(self.checkpoint, identity, self.journal.record["apks"])
        self.assertFalse((self.checkpoint.build_root() / "build-receipt.json").exists())
        self.assertEqual((old / "completion-receipt.json").read_bytes(), original)

    def test_completed_deletion_declaration_is_a_miss_before_allocation(self) -> None:
        from windows_checkpoints import reuse_completed
        old, _ = self.fresh_repeat()
        binding = read_record(old / "transaction-meta/result-binding.json")
        root = old / binding["root"]
        # A receipt cannot authorize deleting an already-absent formerly created file.
        # A forged/tampered declaration also fails the immutable stage proof.
        _publish(root / "deletions.json", {"schema": 1, "paths": ["1/previous-created.db"]})
        identity = self.checkpoint.identity(self.journal.record["apks"], self.producer)
        self.assertIsNone(reuse_completed(self.checkpoint, identity, self.journal.record["apks"]))
        self.assertIsNone(self.checkpoint.build_root())

    def test_stop_while_completion_hashing_cannot_publish_success(self) -> None:
        root = self.stage(); self.owner.update(lifecycle="applying")
        self.patcher._apply_checkpoint(self.session, root)
        from windows_checkpoints import active_delta_identity
        def stopped_hash(keep: Path) -> dict:
            self.owner.stop()
            return active_delta_identity(keep)
        with patch.object(patcher_core, "active_delta_identity", side_effect=stopped_hash):
            with self.assertRaises(patcher_core.PatchError):
                self.patcher._finish_transaction(self.summary)
        self.assertEqual(self.owner.record["lifecycle"], "cancelled")
        self.assertEqual(read_record(self.session / "completion-receipt.json")["outcome"], "stopped_consistent")
        self.assertNotEqual(self.patcher.outcome["next_action"], "open_game")

    def test_stop_queued_during_candidate_receipt_publication_cannot_publish_success(self) -> None:
        root = self.stage(); self.owner.update(lifecycle="applying")
        self.patcher._apply_checkpoint(self.session, root)
        real_publish = patcher_core._publish
        def publish(path: Path, value: dict) -> None:
            real_publish(path, value)
            if path.name == "completion-receipt.json":
                self.patcher.queue_control(stop=True)
        with patch.object(patcher_core, "_publish", side_effect=publish):
            with self.assertRaises(patcher_core.PatchError):
                self.patcher._finish_transaction(self.summary)
        self.assertEqual(self.owner.record["lifecycle"], "cancelled")
        self.assertEqual(read_record(self.session / "completion-receipt.json")["outcome"], "stopped_consistent")
        self.assertNotEqual(self.patcher.outcome["next_action"], "open_game")

    def test_staged_reopen_build_and_transfer_counts_stay_zero(self) -> None:
        self.stage()
        self.builds = 0
        self.reopen()
        self.patcher._continue_authorized()
        self.assertEqual(self.builds, 0)
        self.patcher.pull_game_data.assert_not_called()
        receipt = read_record(self.session / "completion-receipt.json")
        self.assertEqual(receipt["outcome"], "verified_complete")
        self.assertEqual(receipt["result"], self.summary)

    def test_summary_only_restarts_build_in_fresh_owned_attempt(self) -> None:
        incomplete = owned_attempt(self.owner, self.session, "build")
        _publish(incomplete / "committed/device_patch_summary.json", self.summary)
        self.owner.update(lifecycle="building")
        self.reopen()
        self.patcher._continue_authorized()
        self.assertEqual(self.builds, 1)
        self.assertNotEqual(self.owner.record["children"]["build_attempt"], incomplete.name)
        self.assertTrue((incomplete / "committed/device_patch_summary.json").exists())
        self.patcher.pull_game_data.assert_not_called()

    def test_changed_engine_keeps_snapshot_but_rebuilds_stage(self) -> None:
        self.stage()
        self.builds = 0
        self.producer = copy.deepcopy(self.producer)
        # The fixture producer is the shared Android vector; change its native codec bytes.
        self.producer["components"]["native"]["libcodec.so"]["sha256"] = "a" * 64
        self.patcher._producer = self.producer
        self.reopen()
        self.patcher._continue_authorized()
        self.assertEqual(self.builds, 1)
        self.patcher.pull_game_data.assert_not_called()

    def test_live_game_change_rejects_snapshot_before_apply(self) -> None:
        self.stage()
        (self.phone / "1/1.info").write_bytes(b'{"version":"changed"}')
        with self.assertRaises(AssertionError):  # Fresh snapshot mock, never old stage apply.
            self.patcher._continue_authorized()
        self.assertEqual(self.adb.faults.bytes["live_copy"], 0)
        self.assertEqual(self.builds, 1)

    def test_restored_but_unstaged_file_is_in_committed_output(self) -> None:
        pristine = self.session / patcher_core.LAYER / "15/15_0.db"
        pristine.write_bytes(b"restored pristine dropped by new catalog")
        self.outputs = INDONESIAN
        root = self.stage(["15/15_0.db"])
        receipt = verify_receipt(root, stage="staged")
        self.assertEqual(receipt["artifacts"]["payload/15/15_0.db"], file_identity(pristine))
        self.assertEqual(read_record(root / "expected-layer.json")["files"]["packages/15/15_0.db"], file_identity(pristine))

    def test_incomplete_apply_rolls_back_then_reuses_stage(self) -> None:
        root = self.stage()
        self.owner.update(lifecycle="applying")
        self.adb.partial_temp_copy = 10
        with self.assertRaises(patcher_core.PatchError):
            self.patcher._apply_checkpoint(self.session, root)
        self.adb.partial_temp_copy = None
        self.builds = 0
        self.reopen()
        self.patcher._continue_authorized()
        self.assertEqual(self.builds, 0)
        self.assertEqual(self.patcher.file_transaction.record["cycle"], 1)
        self.assertEqual(self.owner.record["retry"]["files_apply"]["attempts"], 2)

    def test_final_install_only_no_build_transfer_or_payload_writes(self) -> None:
        root = self.stage()
        self.owner.update(lifecycle="applying")
        self.patcher._apply_checkpoint(self.session, root)
        writes = self.adb.faults.bytes["temp_copy"]
        self.builds = 0
        self.reopen()
        self.patcher.producer_identity = Mock(side_effect=AssertionError("engine identity loaded for safety"))
        self.patcher._continue_authorized()
        self.assertEqual(self.builds, 0)
        self.assertEqual(self.adb.faults.bytes["temp_copy"], writes)
        self.patcher.pull_game_data.assert_not_called()
        self.assertEqual(self.owner.record["lifecycle"], "finalized")

    def test_realistic_run_as_requires_access_before_normal_callback(self) -> None:
        root = self.stage()
        self.owner.update(lifecycle="applying")
        self.patcher._apply_checkpoint(self.session, root)
        events = []
        real_inventory = self.patcher.file_transaction.transport.inventory
        real_normal = self.patcher.restore_normal_apk
        def inventory(session: str) -> dict:
            self.assertTrue(self.adb.installed_identity()["debuggable"])
            events.append("live_audit")
            return real_inventory(session)
        def normal(**kwargs) -> None:
            events.append("normal_install")
            real_normal(**kwargs)
        self.patcher.file_transaction.transport.inventory = inventory
        self.patcher.restore_normal_apk = normal
        self.patcher._finish_transaction(self.summary)
        self.assertLess(events.index("live_audit"), events.index("normal_install"))
        self.assertFalse(self.adb.installed_identity()["debuggable"])
        self.assertTrue((self.work / "pristine/delta.bin").exists())

    def test_corrupt_result_cannot_be_published_as_verified_counts(self) -> None:
        root = self.stage()
        self.owner.update(lifecycle="applying")
        self.patcher._apply_checkpoint(self.session, root)
        _publish(root / "device_patch_summary.json", {"packages": [], "counts": {"tables": 999}})
        self.reopen()
        with self.assertRaises((patcher_core.PatchError, ArtifactError)):
            self.patcher._continue_authorized()
        self.assertFalse((self.session / "completion-receipt.json").exists())

    def test_stop_during_normal_install_blocks_first_finalization(self) -> None:
        root = self.stage()
        self.owner.update(lifecycle="applying")
        self.patcher._apply_checkpoint(self.session, root)
        real_normal = self.patcher.restore_normal_apk
        def normal(**kwargs) -> None:
            real_normal(**kwargs)
            self.owner.stop()
        self.patcher.restore_normal_apk = normal
        with self.assertRaises(SessionError):
            self.patcher._finish_transaction(self.summary)
        self.assertEqual(self.patcher.file_transaction.record["phase"], "payload_verified")
        self.assertFalse((self.session / "completion-receipt.json").exists())
        self.assertFalse((self.work / "pristine/delta.bin").exists())

    def test_stop_after_finalization_intent_is_not_verified_complete(self) -> None:
        root = self.stage()
        self.owner.update(lifecycle="applying")
        self.patcher._apply_checkpoint(self.session, root)
        tx = self.patcher.file_transaction
        tx._save(phase="finalizing")  # Cut after durable forward-only intent.
        self.owner.stop()
        with self.assertRaises(patcher_core.PatchError) as caught:
            self.patcher._finish_transaction(self.summary)
        self.assertEqual(caught.exception.keys, ("error_cancelled",))
        self.assertEqual(read_record(self.session / "completion-receipt.json")["outcome"], "stopped_consistent")
        self.assertEqual(self.owner.record["lifecycle"], "cancelled")
        self.assertNotEqual(self.patcher.outcome["next_action"], "open_game")

    def test_checkpoint_invalidation_never_resets_attempt_budget(self) -> None:
        self.owner.begin_attempt("fixture_build")
        self.owner.complete_attempt("fixture_build", reconciled_success=True)
        self.owner.invalidate_checkpoint("fixture_build", retained_proof_invalid=True)
        self.assertEqual(self.owner.begin_attempt("fixture_build"), 2)
        self.owner.complete_attempt("fixture_build", reconciled_success=True)
        self.owner.invalidate_checkpoint("fixture_build", retained_proof_invalid=True)
        with self.assertRaises(SessionError):
            self.owner.begin_attempt("fixture_build")

    def test_cleanup_pins_every_unresolved_reference(self) -> None:
        before = tree_manifest(self.session)
        prune_sessions(self.owner, self.session)
        self.assertEqual(tree_manifest(self.session), before)
        self.assertTrue(self.journal.apk("normal").exists())

    def preparation_gap(self, *, official: bool, committed_normal: bool) -> Path:
        from check_windows_recovery import signed_fixture
        # A separate, deliberately pre-mutation APK generation in the private fixture.
        self.owner.update(lifecycle="preparing", children={})
        self.journal = ApkJournal(self.owner, create=True)
        source = signed_fixture(self.base, official=official)
        shutil.copyfile(source, self.journal.apk("source"))
        apks = {"source": patcher_core.apk_tools.apk_identity(source)}
        if committed_normal:
            shutil.copyfile(signed_fixture(self.base), self.journal.apk("normal"))
            apks["normal"] = patcher_core.apk_tools.apk_identity(self.journal.apk("normal"))
        self.journal.update(apks=apks)
        _publish(self.journal.directory / "preparation-source.json", {"schema": 1,
                 "run_id": self.owner.run_id, "target": self.target, "source": apks["source"]})
        self.adb.installed = source.read_bytes()
        self.patcher.apk_journal = self.journal
        self.patcher.file_transaction = None
        self.patcher.debuggable_installed = False
        return self.journal.directory

    def test_incomplete_normal_preparation_uses_new_child(self) -> None:
        old = self.preparation_gap(official=False, committed_normal=False)
        (old / "normal.apk").write_bytes(b"incomplete untrusted signing output")
        self.patcher._run_authorized = Mock(return_value={"fresh": True})
        self.assertEqual(self.patcher._continue_authorized(), {"fresh": True})
        self.assertIn(old.name, self.owner.record["children"].values())
        self.assertNotIn("apk_session", self.owner.record["children"])
        self.assertEqual((old / "normal.apk").read_bytes(), b"incomplete untrusted signing output")
        self.assertEqual(self.adb.uninstall_attempts, 0)

    def test_signed_output_before_official_setup_requires_new_consent_route(self) -> None:
        self.preparation_gap(official=True, committed_normal=True)
        original = self.adb.installed
        self.patcher._run_authorized = Mock(return_value={"fresh_scoped_preparation": True})
        self.patcher._continue_authorized()
        self.patcher._run_authorized.assert_called_once_with()
        self.assertEqual(self.adb.installed, original)
        self.assertEqual(self.adb.uninstall_attempts, 0)

    def test_stop_before_official_setup_keeps_original_and_cancels(self) -> None:
        self.preparation_gap(official=True, committed_normal=True)
        original = self.adb.installed
        self.owner.stop()
        with self.assertRaises(patcher_core.PatchError) as caught:
            self.patcher._continue_authorized()
        self.assertEqual(caught.exception.keys, ("error_cancelled",))
        self.assertEqual(self.owner.record["lifecycle"], "cancelled")
        self.assertEqual(self.adb.installed, original)
        self.assertEqual(self.adb.uninstall_attempts, 0)

    def test_changed_preparation_source_refuses_before_retiring_material(self) -> None:
        old = self.preparation_gap(official=False, committed_normal=False)
        self.adb.installed = None
        with self.assertRaises(patcher_core.PatchError):
            self.patcher._continue_authorized()
        self.assertEqual(self.owner.record["children"]["apk_session"], old.name)
        self.assertEqual(self.adb.install_attempts, 1)  # Initial fixture access only.

    def test_stop_with_unknown_installed_bytes_never_resolves(self) -> None:
        self.patcher.file_transaction = None
        self.owner.stop()
        self.adb.installed = None
        with self.assertRaises(patcher_core.PatchError):
            self.patcher._recover_failed_dispatch()
        self.assertEqual(self.owner.record["lifecycle"], "attention")
        self.assertTrue(self.owner.record["stop_requested"])
        self.assertFalse(self.owner.record["continuation"])

    def test_safety_access_scope_survives_exhausted_ordinary_cycles(self) -> None:
        # Two legitimate work access/normal cycles do not consume the mandatory Stop scope.
        self.patcher.restore_normal_apk()
        self.patcher._ensure_access("ordinary_again")
        self.patcher.restore_normal_apk()
        self.owner.stop()
        self.patcher._ensure_access("stop_repair", recovery=True)
        self.patcher.restore_normal_apk()
        self.assertFalse(self.adb.installed_identity()["debuggable"])
        plan = self.patcher._access_plan()
        self.assertEqual(self.owner.record["retry"]["access_cycles_" + plan["scope"]]["attempts"], 1)
        self.assertTrue(self.owner.record["stop_requested"])

    def test_cleanup_keeps_newest_resolved_cache_plus_pending(self) -> None:
        import uuid
        old, newest = [self.work / "sessions" / str(uuid.uuid4()) for _ in range(2)]
        for path, moment in ((old, "2026-01-01T00:00:00+00:00"), (newest, "2026-02-01T00:00:00+00:00")):
            path.mkdir()
            _publish(path / "session-retention.json", {"schema": 1, "run_id": str(uuid.uuid4()),
                     "target": self.target, "lifecycle": "cancelled", "references": [path.name], "resolved_at": moment})
            (path / "tiny-cache").write_bytes(b"optional stopped cache")
        removed = prune_sessions(self.owner, self.session)
        self.assertIn(old, removed)
        self.assertFalse(old.exists())
        self.assertTrue(newest.exists())
        self.assertTrue(self.session.exists())
        self.assertTrue(self.journal.apk("normal").exists())

    def test_remove_reopen_reuses_stage_and_retires_delta(self) -> None:
        # Seed a previous translation, with pristine input distinct from saved originals.
        self.assertEqual(self.owner.record["action"], "remove")
        pristine = self.session / patcher_core.LAYER
        _write(self.phone, ENGLISH)
        delta = pristine_delta.make(pristine, self.phone)
        pristine_delta.write(delta, self.work / "pristine/delta.bin")
        pristine_delta.record_staged_hashes(self.work / "pristine/staged-hashes.json", delta.staged_hashes)
        shutil.rmtree(self.session / "recovery/packages")
        shutil.copytree(self.phone, self.session / "recovery/packages")
        live = ShellTransport(self.adb).inventory(self.session.name)
        _publish(self.session / "recovery-manifest.json", {**live, "target": self.target})
        pull = read_record(self.session / "pull.json")
        pull["sha256"] = {name.removeprefix("packages/"): item["sha256"] for name, item in live["files"].items()}
        _publish(self.session / "pull.json", pull)
        self.checkpoint.publish_snapshot(self.journal.record["apks"], self.producer)
        self.patcher._active_build = owned_attempt(self.owner, self.session, "build")
        result = {"packages": [], "removed": sorted(ENGLISH)}
        root = self.patcher._publish_payload(self.session, result, None, sorted(ENGLISH),
                    self.checkpoint.identity(self.journal.record["apks"], self.producer))
        self.assertIsNone(verify_receipt(root, stage="staged")["references"]["delta"])
        self.reopen()
        self.patcher._continue_authorized()
        self.assertEqual(self.builds, 0)
        self.assertFalse((self.work / "pristine/delta.bin").exists())
        for name, value in PRISTINE.items():
            self.assertEqual((self.phone / name).read_bytes(), value)


if __name__ == "__main__":
    unittest.main()
