"""Private synthetic Windows Stop/Close/UI control probes, authored for Pass 2.

No Tk window, ADB process, game, pipeline or immutable external fixture is opened.
Thread barriers exercise production control seams rather than timing sleeps.
"""
from __future__ import annotations

import copy
import queue
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "app"), str(ROOT / "tools"), str(ROOT / "tools/research")]
import hok_patcher
import patcher_core
from patch_session import RunStore, SessionError
from check_windows_repatch import Ui


class WindowsControls(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="windows-controls-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()  # TEMP can be an 8.3 short path; RunStore wants the long one
        self.work = self.base / "work"
        self.work.mkdir()
        self.store = RunStore(self.base / "state")
        self.target = {"serial": "controls-private-phone", "android_user": 0,
                       "package": patcher_core.PACKAGE}
        self.owner = self.store.claim(self.work, self.target)
        self.addCleanup(lambda: self.owner.close())
        self.saved = self.owner.authorize("translate", "en")
        self.owner.update(lifecycle="preparing")
        with patch.object(patcher_core, "run_store", return_value=self.store):
            self.patcher = patcher_core.Patcher(Ui(), self.work)
        self.patcher.run_owner = self.owner
        self.patcher.adb = SimpleNamespace(serial=self.target["serial"])

    def threaded(self, callback):
        errors = []
        def run():
            try:
                callback()
            except BaseException as error:
                errors.append(error)
        thread = threading.Thread(target=run, daemon=False)
        thread.start()
        return thread, errors

    def join(self, thread) -> None:
        thread.join(5)
        self.assertFalse(thread.is_alive(), "Control seam deadlocked")

    def test_stop_serializes_whole_retry_read_modify_write(self) -> None:
        self.owner.begin_attempt("build_private")
        entered, release = threading.Event(), threading.Event()
        real_update = self.owner.update
        def update(**changes):
            if "retry" in changes:
                entered.set()
                if not release.wait(5):
                    raise AssertionError("Probe release missing")
            return real_update(**changes)
        with patch.object(self.owner, "update", side_effect=update):
            worker, worker_errors = self.threaded(lambda: self.owner.record_failure("build_private", "cut"))
            self.assertTrue(entered.wait(5))
            controller, control_errors = self.threaded(lambda: self.patcher.request_control(stop=True))
            release.set()
            self.join(worker)
            self.join(controller)
        self.assertEqual(worker_errors + control_errors, [])
        saved = self.store.load(self.work)
        self.assertTrue(saved["stop_requested"])
        self.assertFalse(saved["continuation"])
        self.assertEqual(saved["retry"]["build_private"]["failures"], 1)
        self.assertEqual(saved, self.owner.record)

    def test_preclaim_stop_is_persisted_before_dispatch(self) -> None:
        self.patcher.run_owner = None
        self.patcher.queue_control(stop=True)
        self.patcher.run_owner = self.owner
        mutation = Mock()
        with self.assertRaises(patcher_core.PatchError):
            self.patcher.control_boundary()
            mutation()
        mutation.assert_not_called()
        self.assertTrue(self.store.load(self.work)["stop_requested"])

    def test_close_preserves_continuation_and_cannot_answer_readiness(self) -> None:
        self.assertTrue(self.patcher.request_control(close=True))
        saved = self.store.load(self.work)
        self.assertTrue(saved["continuation"])
        self.assertFalse(saved["stop_requested"])
        self.assertTrue(saved["close_preserves_continuation"])
        with self.assertRaises(patcher_core.PatchError) as caught:
            self.patcher.control_boundary()
        self.assertEqual(caught.exception.keys, ("error_close_preserved",))

    def test_cancelled_ui_wait_persists_stop_without_control_save_thread(self) -> None:
        ui = SimpleNamespace(messages=queue.Queue(), ui_cancel=threading.Event(),
                             stopping=True, patcher=self.patcher)
        answer = Mock(return_value=True)
        worker, errors = self.threaded(lambda: hok_patcher.App._on_ui(ui, answer))
        kind, callback = ui.messages.get(timeout=5)
        self.assertEqual(kind, "call")
        # Deliberately never run request_control/control-save thread. Worker must persist.
        self.patcher.queue_control(stop=True)
        ui.ui_cancel.set()
        self.join(worker)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].keys, ("error_cancelled",))
        self.assertTrue(self.store.load(self.work)["stop_requested"])
        callback()  # Stale queued UI callback must not show a dialog/grant consent.
        answer.assert_not_called()

    def test_cancelled_download_wait_cannot_answer_close_as_ready(self) -> None:
        ui = SimpleNamespace(messages=queue.Queue(), ui_cancel=threading.Event(),
                             stopping=False, patcher=self.patcher)
        answer = Mock(return_value=True)
        worker, errors = self.threaded(lambda: hok_patcher.App._on_ui(ui, answer))
        _, callback = ui.messages.get(timeout=5)
        self.patcher.queue_control(close=True)
        ui.ui_cancel.set()
        self.join(worker)
        callback()
        answer.assert_not_called()
        self.assertEqual(errors[0].keys, ("error_close_preserved",))
        self.assertTrue(self.store.load(self.work)["continuation"])
        self.assertTrue(self.store.load(self.work)["close_preserves_continuation"])

    def test_failed_control_save_cannot_acknowledge_stopping_or_close(self) -> None:
        ui = SimpleNamespace(messages=queue.Queue(), closing=True, busy=True, stopping=True,
                             stop_saved=False, log=Mock(), operation_line=Mock(),
                             show_start=Mock(), after=Mock(), pump=Mock())
        ui.messages.put(("control", OSError("private read-only journal")))
        hok_patcher.App.pump(ui)
        self.assertFalse(ui.stop_saved)
        self.assertFalse(ui.closing)
        ui.operation_line.configure.assert_called_with(text=patcher_core.ui_text("control_save_failed"))

    def test_ui_callback_exception_releases_waiter(self) -> None:
        ui = SimpleNamespace(messages=queue.Queue(), ui_cancel=threading.Event(),
                             stopping=False, patcher=self.patcher)
        worker, errors = self.threaded(lambda: hok_patcher.App._on_ui(ui, Mock(side_effect=ValueError("private"))))
        _, callback = ui.messages.get(timeout=5)
        callback()
        self.join(worker)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], ValueError)

    def test_unrelated_pending_attempt_cannot_authorize_infinite_read_retry(self) -> None:
        self.owner.begin_attempt("build_private")
        read = Mock(side_effect=patcher_core.PatchError("error_read_failed", output="private disconnected read"))
        self.patcher._continue_authorized = read
        self.patcher._wait_saved_device = Mock()
        self.patcher._recover_failed_dispatch = Mock()
        self.patcher._interrupt.wait = Mock()
        with self.assertRaises(patcher_core.PatchError):
            self.patcher._dispatch()
        self.assertEqual(read.call_count, 2)
        saved = copy.deepcopy(self.owner.record)
        guards = [item for key, item in saved["retry"].items() if key.startswith("control_reconcile_")]
        self.assertEqual(len(guards), 1)
        self.assertEqual(guards[0]["attempts"], 2)
        self.assertTrue(guards[0]["exhausted"])
        self.assertEqual(saved["retry"]["build_private"]["attempts"], 1)
        self.owner.close()
        self.owner = self.store.claim(self.work, self.target, run_id=self.saved["run_id"])
        self.patcher.run_owner = self.owner
        with self.assertRaises(patcher_core.PatchError):
            self.patcher._dispatch()
        self.assertEqual(read.call_count, 3)  # Audit-only reopen, no automatic send/rearm.
        self.assertEqual(self.owner.record["retry"], saved["retry"])
        with self.assertRaises(SessionError):
            self.owner.begin_attempt("fresh_mutation")

    def test_explicit_retry_rearms_guards_without_revoking_stop(self) -> None:
        self.owner.begin_attempt("control_reconcile_private", safety_recovery=True)
        self.owner.begin_attempt("control_reconcile_private", safety_recovery=True)
        self.owner.stop()
        self.patcher.explicit_retry = True
        self.patcher._wait_saved_device = Mock()
        def repair():
            self.assertTrue(self.owner.record["stop_requested"])
            self.assertFalse(self.owner.record["continuation"])
            self.assertNotIn("control_reconcile_private", self.owner.record["retry"])
            with self.assertRaises(SessionError):
                self.owner.begin_attempt("uninstall_private", destructive=True)
            return {"repaired": True}
        self.patcher._continue_authorized = repair
        self.assertEqual(self.patcher._dispatch(), {"repaired": True})
        self.assertTrue(self.store.load(self.work)["stop_requested"])

    def test_same_app_retry_keeps_unsaved_stop_before_replacement_worker(self) -> None:
        ui = SimpleNamespace(busy=False, closing=False, worker_thread=None, pending_stop=True,
                             pending_work=True, removing=False, ui_cancel=threading.Event(),
                             progress=Mock(), work_dir=self.work, language="en", folder_button=Mock(),
                             stop_button=Mock(), show_language_card=Mock(), show_start=Mock(), worker=Mock())
        replacement = Mock()
        def launch(**kwargs):
            # Thread creation must happen only after the old unsaved Stop is queued.
            replacement.queue_control.assert_called_once_with(stop=True)
            self.assertTrue(ui.stopping)
            return Mock()
        with patch.object(hok_patcher, "Patcher", return_value=replacement), \
                patch.object(hok_patcher, "_style_button"), \
                patch.object(hok_patcher.threading, "Thread", side_effect=launch):
            hok_patcher.App.start(ui)
        self.assertTrue(ui.pending_stop)
        self.assertFalse(ui.stop_saved)
        ui.worker_thread.start.assert_called_once()

    def test_startup_idle_without_saved_authorization_never_dispatches(self) -> None:
        ui = SimpleNamespace(busy=False, closing=False, work_dir=self.work,
                             pending_work=False, start=Mock(), finish=Mock())
        with patch.object(hok_patcher, "discover_pending_runs", return_value=[]):
            hok_patcher.App.discover_saved_work(ui)
        ui.start.assert_not_called()
        ui.finish.assert_not_called()

    def test_repeat_close_queues_one_control_and_never_kills_shared_adb(self) -> None:
        ui = SimpleNamespace(closing=False, busy=True, stop_button=Mock(),
                             _request_control=Mock(), _cancel_dialogs=Mock(), show_start=Mock())
        with patch.object(hok_patcher, "_style_button"), patch.object(patcher_core.Adb, "kill_server") as kill:
            hok_patcher.App.close(ui)
            hok_patcher.App.close(ui)
        ui._request_control.assert_called_once_with(close=True)
        ui._cancel_dialogs.assert_called_once()
        kill.assert_not_called()

    def test_worker_cannot_upgrade_unverified_return_to_success(self) -> None:
        ui = SimpleNamespace(patcher=SimpleNamespace(run=Mock(return_value={}),
                                                     outcome={"state": "attention"}, remove=False),
                             messages=queue.Queue())
        hok_patcher.App.worker(ui)
        kind, (result, error) = ui.messages.get_nowait()
        self.assertEqual((kind, result), ("done", "failed"))
        self.assertEqual(error.keys, ("error_run_state",))

    def test_pump_preserves_measured_bytes_and_operation_detail(self) -> None:
        ui = SimpleNamespace(messages=queue.Queue(), progress=Mock(), operation_line=Mock(),
                             step_detail="private indivisible operation", busy=True, closing=False,
                             show_start=Mock(), after=Mock(), pump=Mock())
        ui.messages.put(("event", {"state": "working", "next_action": "read_game_data", "bytes_done": 4096}))
        hok_patcher.App.pump(ui)
        ui.operation_line.configure.assert_called_with(text=patcher_core.ui_text("progress_bytes_read", done=hok_patcher._size(4096)))
        ui.progress.configure.assert_called_with(mode="indeterminate")
        ui.messages.put(("event", {"state": "restoring", "next_action": "install_game_app", "detail": "private restore"}))
        hok_patcher.App.pump(ui)
        ui.operation_line.configure.assert_called_with(text="private restore")


class WindowsControlRecovery(unittest.TestCase):
    """Real coordinator/transaction with tiny signed APKs and synthetic phone bytes."""
    def fixture(self):
        from check_windows_checkpoints import CheckpointContinuation
        case = CheckpointContinuation("test_snapshot_reopen_has_zero_transfer_and_one_build")
        # A failing manual setUp must still release its run locks before temp cleanup.
        self.addCleanup(case.doCleanups)
        case.setUp()
        case.patcher._wait_saved_device = Mock()  # Fake phone is always explicitly present.
        # Patcher.run binds the control boundary to its Adb before each dispatch. Unbind
        # afterwards so the probe's own phone observations are not the worker's commands.
        dispatch = case.patcher._dispatch
        def bound_dispatch(*args, **kwargs):
            case.patcher._bind_control()
            try:
                return dispatch(*args, **kwargs)
            finally:
                case.adb.boundary = None
        case.patcher._dispatch = bound_dispatch
        return case

    def test_stop_during_build_preserves_snapshot_and_stays_cancelled(self) -> None:
        case = self.fixture()
        build = case.patcher.build_translation
        def interrupted(session):
            build(session)
            case.patcher.request_control(stop=True)
            case.patcher._build_progress("private build boundary")
        case.patcher.build_translation = interrupted
        with self.assertRaises(patcher_core.PatchError) as caught:
            case.patcher._dispatch()
        self.assertEqual(caught.exception.keys, ("error_cancelled",))
        self.assertEqual(case.owner.record["lifecycle"], "cancelled")
        self.assertTrue(case.owner.record["stop_requested"])
        self.assertFalse(case.adb.installed_identity()["debuggable"])
        self.assertTrue((case.session / "recovery-manifest.json").is_file())
        case.reopen()
        self.assertFalse(case.owner.record["continuation"])
        self.assertNotEqual(case.patcher.outcome["state"], "verified_complete")

    def test_close_during_build_preserves_authorization_and_normal(self) -> None:
        case = self.fixture()
        build = case.patcher.build_translation
        def interrupted(session):
            build(session)
            case.patcher.request_control(close=True)
            case.patcher._build_progress("private build boundary")
        case.patcher.build_translation = interrupted
        with self.assertRaises(patcher_core.PatchError) as caught:
            case.patcher._dispatch()
        self.assertEqual(caught.exception.keys, ("error_close_preserved",))
        saved = case.store.load(case.work)
        self.assertTrue(saved["continuation"])
        self.assertFalse(saved["stop_requested"])
        self.assertTrue(saved["close_preserves_continuation"])
        self.assertFalse(case.adb.installed_identity()["debuggable"])
        self.assertNotEqual(case.patcher.outcome["state"], "verified_complete")

    def test_close_between_file_commits_rolls_back_before_exit(self) -> None:
        from run_artifacts import tree_manifest
        case = self.fixture()
        case.stage()
        original = tree_manifest(case.session / "recovery/packages")
        hit = case.adb.faults.hit
        once = []
        def close_after_rename(name):
            hit(name)
            if name == "after_rename" and not once:
                once.append(True)
                case.patcher.request_control(close=True)
                case.patcher.control_boundary()
        case.adb.faults.hit = close_after_rename
        with self.assertRaises(patcher_core.PatchError):
            case.patcher._dispatch()
        self.assertTrue(once)
        self.assertEqual(tree_manifest(case.phone), original)
        self.assertEqual(case.patcher.file_transaction.record["phase"], "rolled_back")
        self.assertFalse(case.adb.installed_identity()["debuggable"])
        self.assertTrue(case.store.load(case.work)["continuation"])
        self.assertNotEqual(case.patcher.outcome["state"], "verified_complete")

    def test_stop_queued_at_finalize_return_publishes_cancelled_without_saver(self) -> None:
        from run_artifacts import read_record
        case = self.fixture()
        root = case.stage()
        case.owner.update(lifecycle="applying")
        case.patcher._apply_checkpoint(case.session, root)
        tx = case.patcher.file_transaction
        finalize = tx.finalize
        def queue_after_metadata(*args, **kwargs):
            finalize(*args, **kwargs)
            # Saver thread is deliberately absent: only the monotonic UI flag exists.
            case.patcher.queue_control(stop=True)
        tx.finalize = queue_after_metadata
        tx.rollback = Mock(side_effect=AssertionError("Finalized transaction must finish forward"))
        with self.assertRaises(patcher_core.PatchError) as caught:
            case.patcher._finish_transaction(case.summary)
        self.assertEqual(caught.exception.keys, ("error_cancelled",))
        self.assertTrue(case.store.load(case.work)["stop_requested"])
        self.assertFalse(case.store.load(case.work)["continuation"])
        self.assertEqual(tx.record["phase"], "finalized")
        self.assertEqual(case.owner.record["lifecycle"], "cancelled")
        self.assertEqual(read_record(case.session / "completion-receipt.json")["outcome"], "stopped_consistent")
        self.assertEqual(case.patcher.outcome["state"], "cancelled")
        self.assertNotEqual(case.patcher.outcome["next_action"], "open_game")
        self.assertFalse(case.adb.installed_identity()["debuggable"])
        tx.rollback.assert_not_called()

    def test_stop_during_normal_install_cannot_become_open_game(self) -> None:
        case = self.fixture()
        case.stage()
        install = case.adb.install
        def stop_when_normal(apk):
            install(apk)
            if apk == case.journal.apk("normal"):
                case.patcher.request_control(stop=True)
        case.adb.install = stop_when_normal
        with self.assertRaises(patcher_core.PatchError):
            case.patcher._dispatch()
        self.assertTrue(case.store.load(case.work)["stop_requested"])
        self.assertEqual(case.owner.record["lifecycle"], "cancelled")
        self.assertFalse(case.adb.installed_identity()["debuggable"])
        self.assertNotEqual(case.patcher.outcome["state"], "verified_complete")


class WindowsRecoveryOnly(unittest.TestCase):
    """Ticket 13: the attention state's recovery button never starts a fresh patch."""
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="windows-recovery-only-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()  # TEMP can be an 8.3 short path; RunStore wants the long one
        self.work = self.base / "work"
        self.work.mkdir()
        self.store = RunStore(self.base / "state")
        self.target = {"serial": "recovery-only-private-phone", "android_user": 0,
                       "package": patcher_core.PACKAGE}

    def guarded(self, patcher) -> list:
        """Every fresh-run entry point fails the probe if reached."""
        refuse = AssertionError("Recovery-only run reached fresh preparation")
        return [patch.object(patcher_core, "check_work_dir", side_effect=refuse),
                patch.object(patcher, "wait_for_device", side_effect=refuse),
                patch.object(patcher, "_dispatch", side_effect=refuse)]

    def test_nothing_saved_returns_without_preparation(self) -> None:
        with patch.object(patcher_core, "run_store", return_value=self.store):
            patcher = patcher_core.Patcher(Ui(), self.work, recovery_only=True)
            guards = self.guarded(patcher)
            with guards[0], guards[1], guards[2], \
                    patch.object(patcher_core, "Adb", side_effect=AssertionError("No ADB for nothing to recover")):
                summary = patcher.run()
        self.assertEqual(summary, {patcher_core.NOTHING_TO_RECOVER: True})
        self.assertEqual(patcher.outcome["state"], "nothing_to_recover")
        self.assertIsNone(patcher.run_owner)
        self.assertEqual(self.store.discover(self.work), [])

    def test_record_resolved_between_discovery_and_claim_is_not_resumed(self) -> None:
        owner = self.store.claim(self.work, self.target)
        owner.authorize("translate", "en")
        owner.update(lifecycle="preparing")
        stale = self.store.discover(self.work)
        self.assertEqual(len(stale), 1)
        # Another owner resolves the run after the screen was drawn.
        owner.update(lifecycle="normal_verified")
        owner.update(lifecycle="cancelled")
        owner.close()
        with patch.object(patcher_core, "run_store", return_value=self.store):
            patcher = patcher_core.Patcher(Ui(), self.work, recovery_only=True)
        def discover_stale():
            patcher.pending_candidates = copy.deepcopy(stale)
            return patcher.pending_candidates
        guards = self.guarded(patcher)
        with guards[0], guards[1], guards[2], patch.object(patcher, "discover_runs", side_effect=discover_stale), \
                patch.object(patcher_core, "Adb", return_value=Mock()):
            summary = patcher.run()
        self.assertEqual(summary, {patcher_core.NOTHING_TO_RECOVER: True})
        self.assertEqual(self.store.load(self.work)["lifecycle"], "cancelled")

    def test_recover_button_dispatches_recovery_only(self) -> None:
        ui = SimpleNamespace(busy=False, closing=False, work_dir=self.work, start=Mock())
        saved = [{"kind": "authorized", "root": str(self.work), "record": {"action": "remove"}}]
        with patch.object(hok_patcher, "discover_pending_runs", return_value=saved):
            hok_patcher.App.recover(ui)
        ui.start.assert_called_once_with(remove=True, recovery_only=True)

    def test_worker_reports_nothing_to_recover_not_success(self) -> None:
        ui = SimpleNamespace(patcher=SimpleNamespace(run=Mock(return_value={patcher_core.NOTHING_TO_RECOVER: True}),
                                                     outcome={"state": "nothing_to_recover"}, remove=False),
                             messages=queue.Queue())
        hok_patcher.App.worker(ui)
        self.assertEqual(ui.messages.get_nowait(), ("done", (patcher_core.NOTHING_TO_RECOVER, None)))


if __name__ == "__main__":
    unittest.main()
