"""Private synthetic Windows transaction probes; never execute ADB or mutate a game.

Authored during Pass 1. Run during Pass 2 with Python 3.12. The fixtures separate
upload/live/temp/Watchdog bytes and use real run journals, shell-protocol generation,
pristine delta bytes and retained manifests. No translation engine run is needed.
"""
from __future__ import annotations

import shutil
import json
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app"))
import patcher_core
import pristine_delta
import device_transaction
from device_transaction import DeviceTransaction, ShellTransport, _publish
from patch_session import RunStore, SessionError
from run_artifacts import tree_manifest, file_identity
from _windows_fake_device import FakeAdb, Faults


def _write(root: Path, values: dict[str, bytes]) -> None:
    for name, data in values.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


class FileTransactions(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="file-transaction-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.work = self.root / "work"; self.work.mkdir()
        self.phone = self.root / "phone"
        _write(self.phone, {"1/1.db": b"already translated before action", "1/1_0.db": b"unchanged",
                            "2/2.db": b"earlier translation"})
        self.adb = FakeAdb(self.phone)
        _write(self.adb.watchdog, {"nested/History.db": b"pre-action watchdog", "empty-marker": b""})
        self.store = RunStore(self.root / "state")
        self.target = {"serial": self.adb.serial, "android_user": 0, "package": patcher_core.PACKAGE}
        self.owner = self.store.claim(self.work, self.target)
        self.addCleanup(self.owner.close)
        action = getattr(self, "action", "translate")
        self.owner.authorize(action, "en")
        self.owner.update(lifecycle="preparing", children={"data_session": str(uuid.uuid4())})
        self.session = self.work / "sessions" / self.owner.record["children"]["data_session"]
        self.session.mkdir(parents=True)
        self.transport = ShellTransport(self.adb, reserve_bytes=1)
        self.before = self.transport.inventory(self.session.name)
        shutil.copytree(self.phone, self.session / "recovery/packages")
        shutil.copytree(self.adb.watchdog, self.session / "recovery/Watchdog")
        _publish(self.session / "recovery-manifest.json", {**self.before, "target": self.target})
        self.staged = self.session / "staged"
        _write(self.staged, {"1/1.db": b"new-language", "1/1_0.db": b"unchanged", "2/2.db": b"new-second-language"})
        delta = pristine_delta.make(self.phone, self.staged)
        self.material = self.session / "delta-material"; self.material.mkdir()
        metadata = {}
        if action == "remove":
            old = self.work / "pristine/delta.bin"
            old.parent.mkdir()
            pristine_delta.write(pristine_delta.make(self.staged, self.phone), old)
            metadata["old-delta.bin"] = old
            delta = pristine_delta.Delta((), {})
        pristine_delta.write(delta, self.material / "pending.bin")
        pristine_delta.record_staged_hashes(self.material / "hashes.json", delta.staged_hashes)
        self.tx = DeviceTransaction(self.owner, self.transport)
        self.tx.prepare({"1/1.db": self.staged / "1/1.db", "2/2.db": self.staged / "2/2.db"},
                        {**metadata, "pending-delta.bin": self.material / "pending.bin", "new-hashes.json": self.material / "hashes.json"},
                        remove_delta=action == "remove")

    def test_each_temp_boundary_keeps_live_original(self) -> None:
        for cut in ("before_upload", "after_upload", "before_temp_copy", "after_temp_copy",
                    "before_temp_hash", "after_temp_hash", "before_rename"):
            with self.subTest(cut=cut):
                # Independent fresh run/budget for each interruption point.
                case = FileTransactions("runTest"); case.setUp()
                try:
                    case.adb.faults = Faults({cut: 1})
                    with self.assertRaises((patcher_core.PatchError, SessionError)):
                        case.tx.apply()
                    originals = {name.removeprefix("packages/"): value
                                 for name, value in case.before["files"].items() if name.startswith("packages/")}
                    # A cut may leave this session's own temp beside the target. The strict
                    # inventory skips only that owned name; every live game file is untouched.
                    raw = tree_manifest(case.phone)
                    strays = {name for name in raw if name not in originals}
                    self.assertTrue(all(name.rsplit("/", 1)[-1].startswith(f".hok-{case.session.name}-")
                                        and name.endswith(".tmp") for name in strays), strays)
                    self.assertEqual({name: raw[name] for name in raw if name not in strays}, originals)
                    self.assertEqual(case.transport.inventory(case.session.name), case.before)
                    self.assertEqual(case.adb.faults.bytes["live_copy"], 0)
                    # Recovery removes the owned temp; no stray file outlives rollback.
                    case.tx.rollback()
                    self.assertEqual(tree_manifest(case.phone), originals)
                finally:
                    case.doCleanups()

    def test_partial_temp_copy_preserves_live_original(self) -> None:
        self.adb.partial_temp_copy = 3
        with self.assertRaises(patcher_core.PatchError):
            self.tx.apply()
        self.assertEqual((self.phone / "1/1.db").read_bytes(), b"already translated before action")
        self.adb.partial_temp_copy = None
        self.tx.rollback()
        self.assertEqual(self.transport.inventory(self.session.name), self.before)

    def test_post_rename_lost_reply_is_reconciled(self) -> None:
        self.adb.faults = Faults({"after_rename": 1})
        self.tx.apply()
        self.assertEqual(self.tx.record["phase"], "payload_verified")
        self.assertEqual(self.adb.faults.calls["before_rename"], 2)
        self.assertEqual(self.adb.faults.bytes["live_copy"], 0)
        self.assertEqual(self.adb.install_attempts, 0)

    def test_between_file_and_repeated_rollback_interruptions(self) -> None:
        self.adb.faults = Faults({"before_temp_copy": 2})
        with self.assertRaises(patcher_core.PatchError):
            self.tx.apply()
        self.adb.faults = Faults({"after_temp_copy": 1})
        with self.assertRaises(patcher_core.PatchError):
            self.tx.rollback()
        self.adb.faults = Faults()
        reopened = DeviceTransaction(self.owner, self.transport)
        reopened.rollback()
        self.assertEqual(self.transport.inventory(self.session.name), self.before)
        self.assertEqual((self.phone / "1/1.db").read_bytes(), b"already translated before action")

    def test_watchdog_restoration_can_be_interrupted_and_repeated(self) -> None:
        self.tx.apply()
        self.adb.faults = Faults({"before_temp_copy": 3})
        with self.assertRaises(patcher_core.PatchError):
            self.tx.rollback()
        last_write = [json.loads(command.split("\n", 1)[0].removeprefix("# hok-file-transaction "))
                      for command in self.adb.commands if command.startswith("# hok-file-transaction ")
                      and '"operation":"write"' in command][ -1 ]
        self.assertEqual(last_write["name"], "Watchdog/empty-marker")
        self.adb.faults = Faults()
        DeviceTransaction(self.owner, self.transport).rollback()
        self.assertEqual(self.transport.inventory(self.session.name), self.before)

    def test_external_change_blocks_rollback_and_full_audit(self) -> None:
        self.tx.apply()
        (self.phone / "1/1_0.db").write_bytes(b"game update")
        for operation in (self.tx.audit, self.tx.rollback):
            with self.assertRaises(SessionError):
                operation()
        self.assertEqual((self.phone / "1/1_0.db").read_bytes(), b"game update")

    def test_corrupt_post_rename_readback_blocks_success(self) -> None:
        original = self.adb.rename
        def corrupt(source: Path, target: Path) -> None:
            original(source, target)
            target.write_bytes(b"corrupt live bytes")
        with patch.object(self.adb, "rename", side_effect=corrupt):
            with self.assertRaises((SessionError, patcher_core.PatchError)):
                self.tx.apply()
        self.assertNotEqual(self.tx.record["phase"], "payload_verified")
        with self.assertRaises(SessionError):
            self.tx.rollback()

    def test_lost_journal_ack_and_finalization_repeat(self) -> None:
        self.tx.apply()
        normal_calls = []
        original = device_transaction._publish
        def cut_final(path: Path, value: dict) -> None:
            if value.get("phase") == "finalized":
                raise OSError("power cut before final receipt")
            original(path, value)
        with patch.object(device_transaction, "_publish", side_effect=cut_final):
            with self.assertRaises(OSError):
                self.tx.finalize(self.work / "pristine", lambda: normal_calls.append("audit"))
        reopened = DeviceTransaction(self.owner, self.transport)
        self.assertEqual(reopened.record["phase"], "finalizing")
        reopened.finalize(self.work / "pristine", lambda: normal_calls.append("audit"))
        reopened.finalize(self.work / "pristine", lambda: normal_calls.append("audit"))
        self.assertEqual(len(normal_calls), 3)
        self.assertEqual(file_identity(self.work / "pristine/delta.bin"), reopened.record["metadata"]["pending-delta.bin"])
        self.assertEqual(file_identity(self.work / "pristine/staged-hashes.json"), reopened.record["metadata"]["new-hashes.json"])

    def test_normal_failure_keeps_pending_and_blocks_finalization(self) -> None:
        self.tx.apply()
        def fail_normal() -> None:
            raise SessionError("error_normal_recovery", "fixture")
        with self.assertRaises(SessionError):
            self.tx.finalize(self.work / "pristine", fail_normal)
        self.assertEqual(self.tx.record["phase"], "payload_verified")
        self.assertTrue((self.session / "transaction-meta/pending-delta.bin").is_file())
        self.assertFalse((self.work / "pristine/delta.bin").exists())

    def test_staged_corruption_does_not_destroy_originals_recovery(self) -> None:
        self.tx.apply()
        (self.staged / "1/1.db").write_bytes(b"lost staging")
        with self.assertRaises((ValueError, SessionError)):
            self.tx.audit()
        self.tx.rollback()
        self.assertEqual(self.transport.inventory(self.session.name), self.before)

    def test_retry_budget_survives_rollback_and_reopen(self) -> None:
        self.tx.apply(); self.tx.rollback()
        reopened = DeviceTransaction(self.owner, self.transport)
        reopened.reapply(); reopened.rollback()
        with self.assertRaises(SessionError):
            DeviceTransaction(self.owner, self.transport).reapply()
        self.assertEqual(self.owner.record["retry"]["files_apply"]["attempts"], 2)

    def test_stop_restores_actual_pre_action_translation(self) -> None:
        self.tx.apply(); self.owner.stop(); self.tx.rollback()
        self.assertEqual(self.transport.inventory(self.session.name), self.before)
        self.assertTrue(self.owner.record["stop_requested"])
        with self.assertRaises(SessionError):
            self.tx.reapply()

    def test_remove_recovers_after_delta_retired_before_hash_publication(self) -> None:
        case = FileTransactions("runTest"); case.action = "remove"; case.setUp()
        try:
            case.tx.apply()
            old = case.tx.record["metadata"]["old-delta.bin"]
            copy = device_transaction._durable_copy
            def cut_hashes(source: Path, target: Path) -> None:
                if target.name == "staged-hashes.json":
                    raise OSError("cut after delta retirement")
                copy(source, target)
            with patch.object(device_transaction, "_durable_copy", side_effect=cut_hashes):
                with self.assertRaises(OSError):
                    case.tx.finalize(case.work / "pristine", lambda: None)
            self.assertFalse((case.work / "pristine/delta.bin").exists())
            self.assertEqual(file_identity(case.session / "transaction-meta/old-delta.bin"), old)
            reopened = DeviceTransaction(case.owner, case.transport)
            reopened.finalize(case.work / "pristine", lambda: None)
            self.assertEqual(reopened.record["phase"], "finalized")
            self.assertFalse((case.work / "pristine/delta.bin").exists())
        finally:
            case.doCleanups()

    def test_changed_only_snapshot_keeps_watchdog_and_previous_translation(self) -> None:
        # Independent snapshot child, with no full backup tar. This is the same
        # capture seam called by a successful incremental pull before reconstruction.
        session_id = str(uuid.uuid4())
        self.owner.update(children={"data_session": session_id})
        session = self.work / "sessions" / session_id
        shutil.copytree(self.phone, session / patcher_core.LAYER)
        class Ui:
            def log(self, message: str) -> None: pass
        patcher = patcher_core.Patcher(Ui(), self.work)
        patcher.run_owner, patcher.adb = self.owner, self.adb
        with patch.object(shutil, "disk_usage", return_value=type("Usage", (), {"free": 20 * 1024**3})()):
            patcher.preserve_recovery_snapshot(session)
        self.assertFalse((session / "device-backup.tar").exists())
        self.assertEqual(tree_manifest(session / "recovery"), self.before["files"])
        (session / patcher_core.LAYER / "1/1.db").write_bytes(b"reconstructed pristine")
        self.assertEqual((session / "recovery/packages/1/1.db").read_bytes(), b"already translated before action")

    def test_created_file_remove_and_rollback_use_explicit_deletion(self) -> None:
        # A planned removal is explicit; absent staged bytes are never guessed.
        self.tx.path.unlink()
        shutil.rmtree(self.session / "transaction-meta")
        tx = DeviceTransaction(self.owner, self.transport)
        pristine_delta.write(pristine_delta.Delta((), {}), self.material / "empty.bin")
        tx.prepare({"1/1.db": None}, {"pending-delta.bin": self.material / "empty.bin",
                                    "new-hashes.json": self.material / "hashes.json"}, remove_delta=True)
        tx.apply()
        self.assertFalse((self.phone / "1/1.db").exists())
        tx.rollback()
        self.assertEqual(self.transport.inventory(self.session.name), self.before)

    def test_unrelated_valid_delta_refuses_before_file_mutation(self) -> None:
        self.tx.path.unlink()
        shutil.rmtree(self.session / "transaction-meta")
        tx = DeviceTransaction(self.owner, self.transport)
        with self.assertRaises(SessionError):
            tx.prepare({"1/1.db": None}, {"pending-delta.bin": self.material / "pending.bin",
                                        "new-hashes.json": self.material / "hashes.json"})
        self.assertEqual(self.transport.inventory(self.session.name), self.before)
        self.assertEqual(self.adb.faults.bytes["temp_copy"], 0)


if __name__ == "__main__":
    unittest.main()
