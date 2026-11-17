"""Offline interruption probes; expected failures document unfixed production gaps.

Run with Python 3.12. No external fixture, subprocess, adb or phone is used.
Remove an expectedFailure only when its owning ticket implements the required guarantee.
"""
from __future__ import annotations

import tempfile
import json
import os
import struct
import zipfile
from datetime import datetime, timezone
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from check_windows_repatch import ENGLISH, PRISTINE, PRISTINE_SUMMARY, Repatch, Ui, _write
import patcher_core
from patcher_core import PatchError, Patcher
from _windows_fake_device import FakeAdb, Faults
from patch_session import RunStore, SessionError, ApkJournal, Operation


class DurableRuns(unittest.TestCase):
    """Host-only ownership and persistence probes; subprocesses never invoke ADB."""
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="windows-runs-")
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.work = self.base / "work"; self.work.mkdir()
        self.other = self.base / "other"; self.other.mkdir()
        self.store = RunStore(self.base / "state")
        self.target = {"serial": "phone-a", "android_user": 0, "package": patcher_core.PACKAGE}

    def test_discovery_without_installed_game_and_selected_root(self) -> None:
        with self.store.claim(self.work, self.target) as owner:
            saved = owner.authorize("first_setup", "en")
        candidate, = self.store.discover(self.other)
        self.assertEqual(candidate["record"], saved)
        self.assertEqual(candidate["plan"], "reconcile_setup")
        self.assertEqual(candidate["root"], str(self.work))

    def test_stop_and_exhaustion_survive_claim(self) -> None:
        with self.store.claim(self.work, self.target) as owner:
            run = owner.authorize("translate", "id")
            self.assertEqual(owner.begin_attempt("pull"), 1)
            owner.record_failure("pull", "disconnect")
            self.assertEqual(owner.begin_attempt("pull"), 2)
            owner.record_failure("pull", "disconnect")
            owner.stop()
        with self.store.claim(self.work, self.target, run_id=run["run_id"]) as owner:
            self.assertTrue(owner.record["stop_requested"])
            self.assertTrue(owner.record["retry"]["pull"]["exhausted"])
            with self.assertRaises(SessionError):
                owner.begin_attempt("pull")
            with self.assertRaises(SessionError):
                owner.update(stop_requested=False, continuation=True)

    def test_registry_torn_missing_drive_and_conflicting_identity(self) -> None:
        with self.store.claim(self.work, self.target) as owner:
            owner.authorize("translate", "en")
        registry = self.store.registry.read_bytes()
        self.store.registry.write_bytes(b'{"schema":')
        with self.assertRaises(SessionError):
            self.store.discover(self.other)
        self.store.registry.write_bytes(registry)
        moved = self.base / "unavailable-work"
        self.work.rename(moved)
        with self.assertRaises(SessionError):
            self.store.discover(self.other)
        moved.rename(self.work)
        data = json.loads(registry)
        data["roots"].append(data["roots"][0])
        self.store.registry.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(SessionError):
            self.store.discover(self.other)

    def test_success_after_retry_retains_counts_without_pause(self) -> None:
        with self.store.claim(self.work, self.target) as owner:
            run = owner.authorize("translate", "en")
            owner.begin_attempt("pull"); owner.record_failure("pull", "disconnect")
            owner.begin_attempt("pull")
            owner.complete_attempt("pull", reconciled_success=True)
        with self.store.claim(self.work, self.target, run_id=run["run_id"]) as owner:
            self.assertEqual(owner.record["retry"]["pull"]["attempts"], 2)
            candidate, = self.store.discover(self.other)
            self.assertEqual(candidate["plan"], "prepare")
            with self.assertRaises(SessionError):
                owner.begin_attempt("pull")

    def test_attempt_records_failure_then_completes_within_budget(self) -> None:
        with self.store.claim(self.work, self.target) as owner:
            run = owner.authorize("translate", "en")
            with self.assertRaises(OSError):
                with owner.attempt(Operation("snapshot_a")) as number:
                    self.assertEqual(number, 1)
                    raise OSError("cut")
            item = owner.record["retry"]["snapshot_a"]
            self.assertEqual((item["attempts"], item["failures"], item["last_failure"], item["completed"]),
                             (1, 1, "OSError", False))
            with owner.attempt(Operation("snapshot_a"), failure="unused") as number:
                self.assertEqual(number, 2)
            self.assertTrue(owner.record["retry"]["snapshot_a"]["completed"])
            # A retained checkpoint that fails verification re-opens the key, but
            # its budget is already spent: no third attempt, and no work runs.
            ran = []
            with self.assertRaises(SessionError):
                with owner.attempt(Operation("snapshot_a"), retained_invalid=True):
                    ran.append(True)
            self.assertEqual(ran, [])
        with self.store.claim(self.work, self.target, run_id=run["run_id"]) as owner:
            self.assertEqual(owner.record["retry"]["snapshot_a"]["last_failure"], "retained_checkpoint_invalid")

    def test_attempt_named_failure_and_destructive_budget(self) -> None:
        with self.store.claim(self.work, self.target) as owner:
            owner.authorize("translate", "en")
            with self.assertRaises(PatchError):
                with owner.attempt(Operation("apk_x", safety=True), failure="install_unconfirmed"):
                    raise PatchError("error_apk_identity")
            self.assertEqual(owner.record["retry"]["apk_x"]["last_failure"], "install_unconfirmed")
            with self.assertRaises(RuntimeError):
                with owner.attempt(Operation("uninstall_c", destructive=True)):
                    raise RuntimeError("ambiguous reply")
            with self.assertRaises(SessionError):
                with owner.attempt(Operation("uninstall_c", destructive=True)):
                    pass

    def test_rearm_idempotent_skips_destructive_and_keeps_stop(self) -> None:
        with self.store.claim(self.work, self.target) as owner:
            owner.authorize("translate", "en")
            for key in ("build_a", "uninstall_c"):
                owner.begin_attempt(key); owner.record_failure(key, "cut")
                owner.begin_attempt(key); owner.record_failure(key, "cut")
            owner.stop()
            self.assertEqual(owner.rearm_idempotent(), ["build_a"])
            self.assertNotIn("build_a", owner.record["retry"])
            self.assertTrue(owner.record["retry"]["uninstall_c"]["exhausted"])
            self.assertTrue(owner.record["stop_requested"])

    def test_complete_observed_ignores_unstarted_keys(self) -> None:
        with self.store.claim(self.work, self.target) as owner:
            owner.authorize("translate", "en")
            owner.complete_observed("prepare_never")
            self.assertNotIn("prepare_never", owner.record["retry"])
            owner.begin_attempt("prepare_lost_reply")
            owner.complete_observed("prepare_lost_reply")
            self.assertTrue(owner.record["retry"]["prepare_lost_reply"]["completed"])

    def test_owned_pending_correlates_but_foreign_pending_blocks(self) -> None:
        import uuid
        session_id = str(uuid.uuid4())
        with self.store.claim(self.work, self.target) as owner:
            owner.authorize("translate", "en")
            owner.update(children={"data_session": session_id})
        pending = self.work / "sessions" / session_id / "delta.pending.bin"
        pending.parent.mkdir(); pending.write_bytes(b"owned")
        candidate, = self.store.discover(self.other)
        self.assertEqual(candidate["pending_sessions"], [str(pending.parent)])
        foreign = self.work / "sessions" / "foreign" / "delta.pending.bin"
        foreign.parent.mkdir(); foreign.write_bytes(b"unknown")
        with self.assertRaises(SessionError):
            self.store.discover(self.other)

    def test_idle_and_legacy_do_not_create_authorization(self) -> None:
        self.assertEqual(self.store.discover(self.work), [])
        pending = self.work / "sessions" / "old" / "delta.pending.bin"
        pending.parent.mkdir(parents=True); pending.write_bytes(b"legacy")
        candidate, = self.store.discover(self.work)
        self.assertEqual(candidate["kind"], "legacy_safety")
        self.assertFalse((self.work / "sessions" / "run-intent.json").exists())

    def test_process_locks_same_root_and_same_phone(self) -> None:
        script = """
import sys
from pathlib import Path
from patch_session import RunStore, SessionError, ApkJournal
store = RunStore(Path(sys.argv[1]))
target = {'serial':'phone-a','android_user':0,'package':'com.tencent.tmgp.osgame'}
try:
    with store.claim(Path(sys.argv[2]), target):
        sys.exit(9)
except SessionError as error:
    sys.exit(0 if error.key == 'error_run_busy' else 8)
"""
        environment = dict(os.environ)
        environment["PYTHONPATH"] = os.pathsep.join([str(patcher_core.PROJECT / "app"), str(patcher_core.PROJECT / "tools")])
        with self.store.claim(self.work, self.target):
            for root in (self.work, self.other):
                result = subprocess.run([sys.executable, "-c", script, str(self.store.state_dir), str(root)],
                                        env=environment, capture_output=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))

    def test_all_device_argv_bind_saved_serial_and_profile(self) -> None:
        adb = object.__new__(patcher_core.Adb)
        adb.exe, adb.serial, adb.android_user, adb.owner = "fake-adb", "phone-a", 0, None
        for operation in (("shell", "id"), ("pull", "source", "dest"), ("push", "source", "dest"),
                          ("install", "normal.apk"), ("uninstall", patcher_core.PACKAGE),
                          ("reconnect",), ("exec-out", "identity")):
            self.assertEqual(adb._argv(operation)[1:3], ["-s", "phone-a"])
        with self.assertRaises(PatchError):
            adb.bind("phone-b")
        for override in ("-s", "-d", "-e", "-t", "--one-device", "-H", "-P"):
            with self.assertRaises(PatchError):
                adb._argv((override, "other"))
        with patch.object(adb, "shell", return_value="10"):
            with self.assertRaises(PatchError):
                adb.assert_target()

    @unittest.skipUnless(os.name == "nt", "Windows inherited exclusive-share handles")
    def test_child_keeps_locks_after_parent_process_dies(self) -> None:
        script = """
import os, subprocess, sys
from pathlib import Path
from patch_session import RunStore
target = {'serial':'phone-a','android_user':0,'package':'com.tencent.tmgp.osgame'}
owner = RunStore(Path(sys.argv[1])).claim(Path(sys.argv[2]), target)
child = subprocess.Popen([sys.executable, '-c', 'import sys; sys.stdin.buffer.read(1)'],
                         stdin=sys.stdin, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         **owner.subprocess_options())
print(child.pid, flush=True)
os._exit(0)
"""
        environment = dict(os.environ)
        environment["PYTHONPATH"] = os.pathsep.join([str(patcher_core.PROJECT / "app"), str(patcher_core.PROJECT / "tools")])
        parent = subprocess.Popen([sys.executable, "-c", script, str(self.store.state_dir), str(self.work)],
                                  env=environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE)
        try:
            pid = parent.stdout.readline().strip()
            parent.wait(timeout=20)
            self.assertTrue(pid.isdigit(), parent.stderr.read().decode(errors="replace"))
            for root in (self.work, self.other):
                with self.assertRaises(SessionError) as caught:
                    self.store.claim(root, self.target)
                self.assertEqual(caught.exception.key, "error_run_busy")
        finally:
            # Opening the grandchild before releasing it keeps its exit observable.
            waiter = _open_process(int(pid)) if os.name == "nt" and pid.isdigit() else None
            parent.stdin.write(b"x"); parent.stdin.flush(); parent.stdin.close()
            parent.stdout.close(); parent.stderr.close()
            if parent.poll() is None:
                parent.terminate(); parent.wait(timeout=10)
            # The grandchild holds the inherited locks by design; teardown must wait
            # for it to exit before the temporary state directory is removed.
            if waiter is not None:
                _wait_process(waiter, 20)


def _open_process(pid: int) -> int | None:
    import ctypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    return handle or None


def _wait_process(handle: int, seconds: float) -> None:
    import ctypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    try:
        if kernel.WaitForSingleObject(handle, int(seconds * 1000)) != 0:
            raise AssertionError("Lock-holding child did not exit")
    finally:
        kernel.CloseHandle(handle)


def signed_fixture(directory: Path, *, debug: bool = False, official: bool = False) -> Path:
    """Small real binary manifest + v2 RSA APK; fixture keys live only in memory."""
    import apk_tools
    from axml_set_debuggable import build_string_pool
    strings = ["label", "debuggable", "versionCode", "http://schemas.android.com/apk/res/android",
               "manifest", "application", "package", patcher_core.PACKAGE, "Fixture Game", "android"]
    no = 0xffffffff
    def node(kind: int, extension: bytes) -> bytes:
        return struct.pack("<HHIII", kind, 16, 16 + len(extension), 1, no) + extension
    def attribute(ns: int, name: int, kind: int, value: int) -> bytes:
        return struct.pack("<IIIHBBI", ns, name, no, 8, 0, kind, value)
    def element(name: int, attrs: list[bytes]) -> bytes:
        return node(0x102, struct.pack("<IIHHHHHH", no, name, 20, 20, len(attrs), 0, 0, 0) + b"".join(attrs))
    chunks = [build_string_pool(strings, 0x100),
              struct.pack("<HHIIII", 0x180, 8, 20, 0x01010001, 0x0101000f, 0x0101021b),
              node(0x100, struct.pack("<II", 9, 3)),
              element(4, [attribute(3, 2, 0x10, 1), attribute(no, 6, 3, 7)]),
              element(5, [attribute(3, 0, 3, 8), attribute(3, 1, 0x12, 0xffffffff if debug else 0)]),
              node(0x103, struct.pack("<II", no, 5)), node(0x103, struct.pack("<II", no, 4)),
              node(0x101, struct.pack("<II", 9, 3))]
    body = b"".join(chunks)
    unsigned = directory / (str(__import__("uuid").uuid4()) + ".unsigned")
    with zipfile.ZipFile(unsigned, "w") as archive:
        archive.writestr("AndroidManifest.xml", struct.pack("<HHI", 3, 8, len(body) + 8) + body)
        archive.writestr("assets/game.dat", b"fixture game code and prime data")
    key = (patcher_core.BUNDLE / "key/key.pk8").read_bytes()
    cert = (patcher_core.BUNDLE / "key/cert.der").read_bytes()
    if official:
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization, hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Offline official-source fixture")])
        certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(private.public_key())
                       .serial_number(1).not_valid_before(datetime(2025, 1, 1, tzinfo=timezone.utc))
                       .not_valid_after(datetime(2030, 1, 1, tzinfo=timezone.utc)).sign(private, hashes.SHA256()))
        key = private.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        cert = certificate.public_bytes(serialization.Encoding.DER)
    target = unsigned.with_suffix(".apk")
    apk_tools.sign_v2(unsigned, target, key, cert)
    return target


class RecoveryUi(Ui):
    def ask(self, *args: object, **kwargs: object) -> bool:
        return False

    def wait_user(self, *args: object, **kwargs: object) -> None:
        raise PatchError("error_setup_update")


class Transport(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="windows-recovery-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.phone = self.root / "phone"
        _write(self.phone, {"1/1.db": b"original"})

    def test_upload_does_not_write_live(self) -> None:
        adb = FakeAdb(self.phone)
        host = self.root / "host.db"; host.write_bytes(b"replacement")
        adb.run("push", str(host), "/data/local/tmp/hokace/1/1.db")
        self.assertEqual((self.phone / "1/1.db").read_bytes(), b"original")
        self.assertEqual(adb.faults.bytes["upload"], len(b"replacement"))

    def test_temp_cut_keeps_live_and_rename_reply_loss_commits(self) -> None:
        adb = FakeAdb(self.phone, faults=Faults({"after_temp_copy": 1, "after_rename": 1}))
        host = self.root / "host.db"; host.write_bytes(b"replacement")
        target = self.phone / "1/1.db"; temporary = target.with_suffix(".tmp")
        with self.assertRaises(PatchError):
            adb.copy(host, temporary, temporary=True)
        self.assertEqual(target.read_bytes(), b"original")
        self.assertEqual(temporary.read_bytes(), b"replacement")
        with self.assertRaises(PatchError):
            adb.rename(temporary, target)
        self.assertEqual(target.read_bytes(), b"replacement")
        self.assertFalse(temporary.exists())
        self.assertEqual(adb.faults.calls["before_acknowledgment"], 0)

    def test_installer_commits_then_loses_reply(self) -> None:
        adb = FakeAdb(self.phone, faults=Faults({"after_install_commit": 1}))
        apk = self.root / "normal.apk"; apk.write_bytes(b"normal-apk")
        with self.assertRaises(PatchError):
            adb.install(apk)
        self.assertEqual(adb.installed, apk.read_bytes())
        self.assertEqual(adb.install_attempts, 1)

    def test_hooks_bracket_journal_and_finalization(self) -> None:
        faults = Faults({"before_journal_write": 1})
        path = self.root / "journal.json"
        with self.assertRaises(PatchError):
            faults.operation("journal_write", lambda: path.write_text("{}"))
        self.assertFalse(path.exists())
        faults.operation("finalization", lambda: path.write_text("{}"))
        self.assertEqual(faults.calls["after_finalization"], 1)

    def owned_apks(self, *, setup: bool = False):
        store = RunStore(self.root / "state")
        target = {"serial": "fixture-phone", "android_user": 0, "package": patcher_core.PACKAGE}
        owner = store.claim(self.root, target)
        owner.authorize("translate", "en")
        owner.update(lifecycle="preparing")
        self.addCleanup(owner.close)
        journal = ApkJournal(owner, create=True)
        for role, debug, official in [("source", False, True), ("normal", False, False), ("access", True, False)]:
            path = signed_fixture(self.root, debug=debug, official=official)
            path.replace(journal.apk(role))
        identities = {role: patcher_core.apk_tools.apk_identity(journal.apk(role)) for role in ("source", "normal", "access")}
        journal.update(apks=identities)
        if setup:
            consent = str(__import__("uuid").uuid4())
            plan = {"source": identities["source"], "normal": identities["normal"],
                    "consequence": "delete_local_game_data_scan_login"}
            owner.update(consents={consent: {**plan, "id": consent, "approved_at": datetime.now(timezone.utc).isoformat(),
                          "plan_digest": patcher_core.identity_key(plan), "consumed": "uninstall_intent"}})
            owner.begin_attempt("uninstall_" + consent, destructive=True)
            journal.update(setup={**plan, "consent": consent, "phase": "uninstall_intent"})
        patcher = Patcher(RecoveryUi(), self.root, "en")
        patcher.run_store, patcher.run_owner, patcher.apk_journal = store, owner, journal
        patcher.normal_apk = journal.apk("normal")
        patcher.adb = FakeAdb(self.phone)
        patcher.adb.installed = journal.apk("access").read_bytes()
        return patcher, owner, journal

    def test_current_normal_restore_must_block_false_success(self) -> None:
        patcher, owner, journal = self.owned_apks()
        patcher.debuggable_installed = True
        patcher.adb.faults = Faults({"before_install_commit": 1})
        with self.assertRaises(PatchError):
            patcher.restore_normal_apk()
        self.assertTrue(patcher.debuggable_installed)
        self.assertEqual(owner.record["lifecycle"], "attention")
        self.assertEqual(journal.load()["installs"]["apk_final_normal"]["outcome"], "attention")

    def test_current_first_setup_gap_must_restore_missing_game(self) -> None:
        patcher, owner, journal = self.owned_apks(setup=True)
        adb = patcher.adb
        adb.installed = None
        owner.close()
        # Free space is below fresh-build minimum; only recovery space is required.
        with patch.object(patcher_core, "Adb", return_value=adb), \
                patch.object(patcher_core, "run_store", return_value=patcher.run_store), \
                patch.object(patcher_core, "free_space", return_value=128 * 1024**2), \
                patch.object(patcher_core, "check_work_dir", side_effect=AssertionError("fresh space check")):
            with self.assertRaises(PatchError) as error:
                patcher.run()
        self.assertEqual(error.exception.keys, ("error_setup_update",))
        self.assertEqual(adb.installed, journal.apk("normal").read_bytes())
        self.assertEqual(adb.uninstall_attempts, 0)

    def test_ambiguous_install_is_audited_before_retry(self) -> None:
        patcher, owner, journal = self.owned_apks()
        patcher.adb.faults = Faults({"after_install_commit": 1})
        patcher.restore_normal_apk()
        self.assertEqual(patcher.adb.install_attempts, 1)
        self.assertTrue(owner.record["retry"]["apk_final_normal"]["completed"])
        self.assertEqual(journal.load()["installs"]["apk_final_normal"]["outcome"], "verified")

    def test_unrelated_app_and_tampered_saved_apk_refuse(self) -> None:
        patcher, owner, journal = self.owned_apks(setup=True)
        foreign = signed_fixture(self.root, official=True)
        patcher.adb.installed = foreign.read_bytes()
        with self.assertRaises(PatchError):
            patcher.recover_first_setup()
        self.assertEqual(patcher.adb.install_attempts, 0)
        self.assertEqual(patcher.adb.uninstall_attempts, 0)
        journal.apk("normal").write_bytes(journal.apk("access").read_bytes())
        with self.assertRaises(PatchError):
            patcher.verify_prepared("normal")

    def test_original_still_present_requires_new_consent(self) -> None:
        patcher, owner, journal = self.owned_apks(setup=True)
        patcher.adb.installed = journal.apk("source").read_bytes()
        with self.assertRaises(PatchError) as error:
            patcher.recover_first_setup()
        self.assertEqual(error.exception.keys, ("error_setup_consent",))
        self.assertEqual(patcher.adb.uninstall_attempts, 0)

    def test_loose_normal_apk_is_not_recovery_authorization(self) -> None:
        normal = signed_fixture(self.root)
        normal.replace(self.root / "normal.apk")
        patcher = Patcher(RecoveryUi(), self.root, "en")
        patcher.adb = FakeAdb(self.phone)
        patcher.adb.installed = None
        with self.assertRaises(PatchError):
            patcher.verify_prepared("normal")
        self.assertEqual(patcher.adb.install_attempts, 0)

    def test_fresh_preparation_binds_official_and_patcher_signed_sources(self) -> None:
        for official in (False, True):
            with self.subTest(official=official), tempfile.TemporaryDirectory(dir=self.root) as temporary:
                work = Path(temporary)
                store = RunStore(work / "state")
                target = {"serial": "fixture-phone", "android_user": 0, "package": patcher_core.PACKAGE}
                with store.claim(work, target) as owner:
                    owner.authorize("translate", "en")
                    owner.update(lifecycle="preparing")
                    patcher = Patcher(RecoveryUi(), work, "en")
                    patcher.run_store, patcher.run_owner = store, owner
                    patcher.adb = FakeAdb(self.phone)
                    patcher.adb.installed = signed_fixture(work, official=official).read_bytes()
                    with patch.object(patcher.ui, "ask", return_value=True), \
                            patch.object(patcher.ui, "wait_user", create=True):
                        patcher.prepare_normal_apk("/data/app/fixture/base.apk")
                    self.assertFalse(patcher.local_apk_identity(patcher.normal_apk)["debuggable"])
                    self.assertEqual(patcher.adb.uninstall_attempts, int(official))
                    self.assertEqual(patcher.apk_journal.record["setup"] is not None, official)
                    access = patcher.prepare_debuggable_apk()
                    self.assertTrue(patcher.local_apk_identity(access)["debuggable"])

    def test_adb_success_text_does_not_prove_installed_bytes(self) -> None:
        patcher, owner, journal = self.owned_apks()
        # Use the real install verifier over the strict fake's command grammar.
        patcher_core.Adb.install(patcher.adb, journal.apk("normal"))
        self.assertEqual(patcher.adb.installed_identity(), journal.record["apks"]["normal"])
        for wrong in (journal.apk("access").read_bytes(), journal.apk("source").read_bytes(),
                      journal.apk("normal").read_bytes() + b"tampered"):
            patcher.adb.install_override = wrong
            with self.assertRaises(PatchError):
                patcher_core.Adb.install(patcher.adb, journal.apk("normal"))


class CurrentLayerGaps(Repatch):
    """Run only new gaps here; baseline Repatch remains available in its own command."""
    def test_current_wrong_device_must_refuse_session_reuse(self) -> None:
        session = self.session()
        (session / patcher_core.PULL_RECORD).write_text(json.dumps({"target": {
            "serial": "phone-a", "android_user": 0, "package": patcher_core.PACKAGE}}), encoding="utf-8")
        patcher = self.patcher()
        patcher.adb = FakeAdb(self.phone, serial="phone-b")
        self.assertIsNone(patcher.previous_session(self.work / "sessions" / "next"))

    def test_current_direct_copy_cut_must_preserve_live_original(self) -> None:
        from check_windows_file_transaction import FileTransactions
        case = FileTransactions("test_partial_temp_copy_preserves_live_original")
        case.setUp()
        try:
            case.test_partial_temp_copy_preserves_live_original()
        finally:
            case.doCleanups()


def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str) -> unittest.TestSuite:
    suite = loader.loadTestsFromTestCase(Transport)
    suite.addTests(loader.loadTestsFromTestCase(DurableRuns))
    from check_windows_file_transaction import FileTransactions
    suite.addTests(loader.loadTestsFromTestCase(FileTransactions))
    from check_windows_controls import WindowsControls, WindowsControlRecovery
    suite.addTests(loader.loadTestsFromTestCase(WindowsControls))
    suite.addTests(loader.loadTestsFromTestCase(WindowsControlRecovery))
    from check_windows_checkpoints import CheckpointContinuation
    suite.addTests(loader.loadTestsFromTestCase(CheckpointContinuation))
    from check_windows_signing import SigningReuse
    suite.addTests(loader.loadTestsFromTestCase(SigningReuse))
    for name in ("test_current_wrong_device_must_refuse_session_reuse",
                 "test_current_direct_copy_cut_must_preserve_live_original"):
        suite.addTest(CurrentLayerGaps(name))
    return suite


if __name__ == "__main__":
    unittest.main()
