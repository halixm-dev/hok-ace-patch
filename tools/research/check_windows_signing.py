"""Generated-APK signing/count/byte/time probes for Pass 2; never a real phone.

Run: .venv/Scripts/python.exe tools/research/check_windows_signing.py
Each case prints preparation signing calls/input bytes/seconds when executed.
These are synthetic observations, not game-APK performance claims. No probe runs
on import; fixtures and all writes are private TemporaryDirectory children.
"""
from __future__ import annotations

import copy
import json
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "app"), str(ROOT / "tools"), str(ROOT / "tools/research")]
import patcher_core
from patch_session import ApkJournal, RunStore, SessionError
from run_artifacts import ArtifactError, read_record
from windows_checkpoints import PreparedApks
import windows_checkpoints
from _windows_fake_device import FakeAdb
from check_windows_recovery import RecoveryUi, signed_fixture


class SigningReuse(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="windows-signing-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.work = self.root / "work"; self.work.mkdir()
        self.phone = self.root / "phone"; self.phone.mkdir()
        self.store = RunStore(self.root / "state")
        self.target = {"serial": "fixture-phone", "android_user": 0, "package": patcher_core.PACKAGE}
        self.owner = self.store.claim(self.work, self.target)
        self.addCleanup(lambda: self.owner.close())
        self.owner.authorize("translate", "en")
        self.owner.update(lifecycle="preparing")
        with patch.object(patcher_core, "run_store", return_value=self.store):
            self.patcher = patcher_core.Patcher(RecoveryUi(), self.work)
        self.patcher.run_owner, self.patcher.run_store = self.owner, self.store
        self.patcher.adb = self.adb = FakeAdb(self.phone)
        self.producer = copy.deepcopy(read_record(ROOT / "tools/research/fixtures/run_artifacts/vectors.json")
                                      ["receipt"]["identity"]["producer"])
        self.patcher._producer, self.patcher._producer_checked = self.producer, True
        self.calls: list[dict] = []
        self.real_sign = patcher_core.apk_tools.sign_v2

    def source(self, *, official: bool = False, named: bool = False) -> None:
        path = signed_fixture(self.root, official=official)
        if named:
            unsigned, ready = self.root / "named.unsigned", self.root / "named.apk"
            patcher_core.apk_tools.rewrite_apk(path, unsigned, {"AndroidManifest.xml":
                patcher_core.set_label(patcher_core.apk_manifest(path), patcher_core.APP_NAME)})
            self.real_sign(unsigned, ready, (patcher_core.BUNDLE / "key/key.pk8").read_bytes(),
                           (patcher_core.BUNDLE / "key/cert.der").read_bytes())
            path = ready
        self.adb.installed = path.read_bytes()

    def counted_sign(self, source: Path, target: Path, *args, **kwargs) -> None:
        observation = {"role": target.stem, "input_bytes": source.stat().st_size}
        self.calls.append(observation)
        started = time.perf_counter()
        try:
            self.real_sign(source, target, *args, **kwargs)
        finally:
            observation["seconds"] = time.perf_counter() - started

    def prepare(self, *, consent: bool = True) -> None:
        started = time.perf_counter()
        with patch.object(patcher_core.apk_tools, "sign_v2", side_effect=self.counted_sign), \
                patch.object(self.patcher.ui, "ask", create=True, return_value=consent), \
                patch.object(self.patcher.ui, "wait_user", create=True):
            try:
                self.patcher.prepare_normal_apk("/data/app/fixture/base.apk")
            finally:
                print(json.dumps({"case": self._testMethodName, "preparation_seconds": time.perf_counter() - started,
                                  "signing": self.calls}, sort_keys=True))

    def receipt(self, role: str = "normal") -> PreparedApks:
        return PreparedApks(self.owner, self.patcher.apk_journal, self.patcher.producer_identity())

    def observe(self, name: str, operation):
        first = len(self.calls)
        started = time.perf_counter()
        try:
            return operation()
        finally:
            print(json.dumps({"case": self._testMethodName, "operation": name,
                              "preparation_seconds": time.perf_counter() - started,
                              "signing": self.calls[first:]}, sort_keys=True))

    def normal_manifest(self) -> bytes:
        return self.patcher.manifest_to_install(patcher_core.apk_manifest(self.patcher.apk_journal.apk("source")))

    def reopen(self) -> None:
        run_id = self.owner.run_id
        self.owner.close()
        self.owner = self.store.claim(self.work, self.target, run_id=run_id)
        self.patcher.run_owner = self.owner
        self.patcher.apk_journal = ApkJournal(self.owner)
        self.patcher._prepared_access = None

    def test_official_conversion_signs_normal_once_and_pins_before_consent(self) -> None:
        self.source(official=True)
        original = self.adb.installed_identity()
        self.prepare()
        journal = self.patcher.apk_journal
        self.assertEqual([c["role"] for c in self.calls], ["normal"])
        self.assertEqual(self.adb.uninstall_attempts, 1)
        self.assertEqual(journal.record["setup"]["source"], original)
        self.assertNotEqual(original["signers"], journal.record["apks"]["normal"]["signers"])
        self.assertEqual(self.adb.installed_identity(), journal.record["apks"]["normal"])
        self.receipt().verify("normal", self.normal_manifest())
        self.assertFalse(journal.record["apks"]["normal"]["debuggable"])

    def test_already_signed_named_source_has_zero_signs_or_installs(self) -> None:
        self.source(named=True)
        original = self.adb.installed_identity()
        self.prepare()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.adb.install_attempts, 0)
        self.assertEqual(self.adb.uninstall_attempts, 0)
        self.assertEqual(self.patcher.apk_journal.record["apks"]["normal"], original)
        self.patcher.install_prepared("normal", "no-op")
        self.assertEqual(self.adb.install_attempts, 0)

    def test_rename_failure_still_converts_official_once(self) -> None:
        self.source(official=True)
        with patch.object(patcher_core, "set_label", side_effect=ValueError("fixture rename refusal")):
            self.prepare()
            self.receipt().verify("normal", self.normal_manifest())
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.adb.uninstall_attempts, 1)
        self.assertTrue(any("leaving the app name" in line for line in self.patcher.ui.lines))

    def test_official_before_consent_reopen_reuses_normal_but_still_asks(self) -> None:
        self.source(official=True)
        with self.assertRaises(patcher_core.PatchError):
            self.prepare(consent=False)
        self.assertEqual(self.adb.uninstall_attempts, 0)
        self.assertEqual(len(self.calls), 1)
        self.reopen()
        self.patcher._resume_stages = Mock(return_value={"fixture": "continued"})
        with patch.object(patcher_core.apk_tools, "sign_v2", side_effect=self.counted_sign), \
                patch.object(self.patcher.ui, "ask", create=True, return_value=True) as ask, \
                patch.object(self.patcher.ui, "wait_user", create=True):
            self.observe("reuse-normal-before-consent", self.patcher._continue_authorized)
        ask.assert_called_once()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.adb.uninstall_attempts, 1)

    def test_access_receipt_reopen_skips_signing_and_keeps_manifest_only_content(self) -> None:
        self.source(named=True)
        self.prepare()
        with patch.object(patcher_core.apk_tools, "sign_v2", side_effect=self.counted_sign):
            access = self.patcher.prepare_debuggable_apk()
        self.assertEqual([c["role"] for c in self.calls], ["access"])
        original = access.read_bytes()
        self.reopen()
        with patch.object(patcher_core.apk_tools, "sign_v2", side_effect=AssertionError("resigned cache")):
            self.assertEqual(self.observe("reuse-access", self.patcher.prepare_debuggable_apk).read_bytes(), original)
        normal = self.patcher.apk_journal.record["apks"]["normal"]
        identity = self.patcher.local_apk_identity(access)
        self.assertTrue(identity["debuggable"])
        self.assertEqual(identity["signers"], normal["signers"])
        self.assertNotEqual(access, self.patcher.normal_apk)

    def test_torn_receipt_and_tampered_apk_never_reuse(self) -> None:
        self.source(named=True)
        self.prepare()
        journal = self.patcher.apk_journal
        path = journal.directory / "normal-preparation-receipt.json"
        receipt = path.read_bytes()
        path.write_bytes(b'{"committed":')
        with self.assertRaises(ArtifactError):
            self.receipt().verify("normal", self.normal_manifest())
        path.write_bytes(receipt)
        with journal.apk("normal").open("ab") as stream:
            stream.write(b"tampering")
        with self.assertRaises((ArtifactError, ValueError)):
            self.receipt().verify("normal", self.normal_manifest())

    def test_producer_missing_or_changed_declines_reuse_but_safety_normal_is_available(self) -> None:
        self.source(named=True)
        self.prepare()
        for producer in (None, {**self.producer, "components": {**self.producer["components"],
                "executable": {"size": 1, "sha256": "a" * 64}}}):
            with self.subTest(producer=producer is None), self.assertRaises(ArtifactError):
                PreparedApks(self.owner, self.patcher.apk_journal, producer).verify("normal", self.normal_manifest())
        self.patcher._producer = None
        self.assertEqual(self.patcher.verify_prepared("normal"), self.patcher.normal_apk)

    def test_fresh_without_producer_remains_possible_and_publishes_no_receipt(self) -> None:
        self.source(named=True)
        self.patcher._producer = None
        self.prepare()
        self.assertFalse((self.patcher.apk_journal.directory / "normal-preparation-receipt.json").exists())
        self.patcher.verify_prepared("normal")

    def test_restart_copies_only_exact_receipted_generation_without_signing(self) -> None:
        self.source(named=True)
        self.prepare()
        previous = self.patcher.apk_journal
        saved = {role: previous.apk(role).read_bytes() for role in ("source", "normal")}
        self.reopen()
        def prepare_only():
            self.patcher.prepare_normal_apk("/data/app/fixture/base.apk")
            return {"prepared": True}
        self.patcher._run_authorized = prepare_only
        with patch.object(patcher_core.apk_tools, "sign_v2", side_effect=AssertionError("resigned cache")):
            self.observe("restart-reuse-normal", self.patcher._restart_preparation)
        self.assertNotEqual(previous.directory, self.patcher.apk_journal.directory)
        for role, body in saved.items():
            self.assertEqual(previous.apk(role).read_bytes(), body)
            self.assertEqual(self.patcher.apk_journal.apk(role).read_bytes(), body)
        self.receipt().verify("normal", self.normal_manifest())

    def test_interrupted_signing_output_is_retained_never_overwritten(self) -> None:
        self.source()
        source = self.root / "source.apk"; source.write_bytes(self.adb.installed)
        output = self.root / "output.apk"; output.write_bytes(b"half signed")
        with self.assertRaises(patcher_core.PatchError), \
                patch.object(patcher_core.apk_tools, "sign_v2", side_effect=AssertionError("overwrote output")):
            self.patcher.build_signed(source, output, {"AndroidManifest.xml": patcher_core.apk_manifest(source)})
        self.assertEqual(output.read_bytes(), b"half signed")

    def test_receipt_publication_cut_leaves_output_uncommitted(self) -> None:
        self.source()
        publish = windows_checkpoints._publish
        def cut(path, value):
            if path.name == "normal-preparation-receipt.json":
                raise OSError("injected publication interruption")
            return publish(path, value)
        with patch.object(windows_checkpoints, "_publish", side_effect=cut), self.assertRaises(OSError):
            self.prepare()
        self.patcher.verify_prepared("normal")  # Recovery survives missing optimization metadata.
        with self.assertRaises(ArtifactError):
            self.receipt().verify("normal", self.normal_manifest())
        self.assertEqual(self.adb.uninstall_attempts, 0)

    def test_changed_phone_source_blocks_restart_before_copy_or_sign(self) -> None:
        self.source()
        self.prepare()
        previous = self.patcher.apk_journal
        self.adb.installed = signed_fixture(self.root, official=True).read_bytes()
        self.patcher._run_authorized = Mock(side_effect=AssertionError("changed source accepted"))
        with self.assertRaises(patcher_core.PatchError):
            self.patcher._restart_preparation()
        self.patcher._run_authorized.assert_not_called()
        self.assertTrue(previous.apk("normal").exists())

    def test_tampered_receipt_falls_back_to_fresh_generation(self) -> None:
        self.source()
        self.prepare()
        previous = self.patcher.apk_journal
        path = previous.directory / "normal-preparation-receipt.json"
        path.write_text("{}", encoding="utf-8")
        def prepare_only():
            self.prepare()
            return {"fresh": True}
        self.patcher._run_authorized = prepare_only
        self.patcher._restart_preparation()
        self.assertEqual([item["role"] for item in self.calls], ["normal", "normal"])
        self.assertEqual(path.read_text(encoding="utf-8"), "{}")
        self.assertNotEqual(previous.directory, self.patcher.apk_journal.directory)

    def test_manifest_or_signing_identity_change_invalidates_reuse(self) -> None:
        self.source(named=True)
        self.prepare()
        manifest = self.normal_manifest()
        with self.assertRaises(ArtifactError):
            self.receipt().verify("normal", manifest + b"changed option")
        identity = windows_checkpoints.file_identity
        def different_key(path):
            result = identity(path)
            return {**result, "sha256": "b" * 64} if path.name == "key.pk8" else result
        with patch.object(windows_checkpoints, "file_identity", side_effect=different_key), self.assertRaises(ArtifactError):
            self.receipt().verify("normal", manifest)

    def test_ensure_access_reuses_receipt_with_zero_resigning(self) -> None:
        self.source(named=True)
        self.prepare()
        self.patcher.prepare_debuggable_apk()
        self.reopen()
        with patch.object(patcher_core.apk_tools, "sign_v2", side_effect=AssertionError("cache resigned")):
            self.patcher._ensure_access("fixture-resume")
        self.assertEqual(self.adb.installed_identity(), self.patcher.apk_journal.record["apks"]["access"])
        self.assertEqual(self.adb.install_attempts, 1)

    def test_stop_before_official_consent_cancels_without_producer_or_dialog(self) -> None:
        self.source(official=True)
        with self.assertRaises(patcher_core.PatchError):
            self.prepare(consent=False)
        self.owner.stop()
        self.reopen()
        with patch.object(self.patcher, "producer_identity", side_effect=AssertionError("loaded producer after Stop")), \
                patch.object(self.patcher.ui, "ask", create=True, side_effect=AssertionError("asked after Stop")):
            with self.assertRaises(patcher_core.PatchError) as error:
                self.patcher._continue_authorized()
        self.assertEqual(error.exception.keys, ("error_cancelled",))
        self.assertEqual(self.adb.uninstall_attempts, 0)
        self.assertEqual(self.adb.install_attempts, 0)

    def test_self_consistent_receipt_cannot_bless_nonmanifest_content_changes(self) -> None:
        self.source(named=True)
        self.prepare()
        journal = self.patcher.apk_journal
        output = journal.apk("normal")
        unsigned = self.root / "forged.unsigned"
        patcher_core.apk_tools.rewrite_apk(output, unsigned, {"assets/game.dat": b"wrong content"})
        forged = self.root / "forged.apk"
        self.real_sign(unsigned, forged, (patcher_core.BUNDLE / "key/key.pk8").read_bytes(),
                       (patcher_core.BUNDLE / "key/cert.der").read_bytes())
        shutil.copyfile(forged, output)
        identity = self.patcher.local_apk_identity(output)
        # Corrupt both journal and optimization receipt consistently: consumption
        # must still prove the actual source-to-output manifest-only relationship.
        journal_data = read_record(journal.path)
        journal_data["apks"]["normal"] = identity
        windows_checkpoints._publish(journal.path, journal_data)
        path = journal.directory / "normal-preparation-receipt.json"
        value = read_record(path)
        value["output"] = identity
        value["content_key"] = windows_checkpoints.identity_key(PreparedApks.content(output))
        windows_checkpoints._publish(path, value)
        with self.assertRaises(ArtifactError):
            self.receipt().verify("normal", self.normal_manifest())

    def test_dangling_apk_and_signing_output_links_are_rejected(self) -> None:
        self.source(named=True)
        source = self.root / "fixture-source.apk"; source.write_bytes(self.adb.installed)
        journal = ApkJournal(self.owner, create=True)
        missing = self.root / "must-stay-absent.apk"
        link = journal.directory / "source.apk"
        try:
            link.symlink_to(missing)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"Host does not permit symlink creation: {error}")
        with self.assertRaises(SessionError):
            journal.apk("source")
        for suffix in (".apk", ".unsigned"):
            target = self.root / ("dangling" + suffix)
            target.symlink_to(missing)
            output = self.root / "dangling.apk"
            with self.assertRaises(patcher_core.PatchError), \
                    patch.object(patcher_core.apk_tools, "sign_v2", side_effect=AssertionError("followed link")):
                self.patcher.build_signed(source, output, {"AndroidManifest.xml": patcher_core.apk_manifest(source)})
            self.assertTrue(target.is_symlink())
            target.unlink()
        self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
