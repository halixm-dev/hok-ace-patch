"""The Windows patcher's game APKs: copy the installed one, prepare the normal and access APKs, sign, install.

`ApkPreparation` is mixed into `patcher_core.Patcher`, its methods moved there verbatim. They use the
patcher's `adb`, `ui`, `run_owner`, `apk_journal`, `remove` and `_prepared_access`, and its `log`, `step`,
`done`, `event`, `control_boundary`, `producer_identity`, `_access_plan`, `recover_first_setup` and
`finish_setup_update`. `patcher_core` re-exports `APP_NAME` and `apk_manifest`.
"""
from __future__ import annotations

import hashlib
import os
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import apk_tools
from adb_device import PACKAGE
from axml_label import set_label
from axml_set_debuggable import is_debuggable, patch as make_debuggable_manifest
from device_transaction import _publish, _durable_copy
from patch_session import ApkJournal, Operation
from run_artifacts import ArtifactError, identity_key
from ui_strings import BUNDLE, PatchError, ui_text
from windows_checkpoints import PreparedApks

# The name the game is listed under once patched. Writing it is cosmetic, so a manifest this cannot
# be written into is logged and the run continues.
APP_NAME = "Honor of Kings: ACE"


def apk_manifest(apk: Path) -> bytes:
    """The APK's binary AndroidManifest.xml."""
    with zipfile.ZipFile(apk) as archive:
        return archive.read("AndroidManifest.xml")


class ApkPreparation:
    def find_installed_apk(self) -> str:
        self.adb.assert_target()
        output = self.adb.shell(f"pm path {PACKAGE}", check=False)
        paths = [line[len("package:"):].strip() for line in output.splitlines() if line.startswith("package:")]
        if not paths:
            raise PatchError("error_game_not_installed")
        if len(paths) > 1:
            raise PatchError("error_split_apks")
        return paths[0]

    def manifest_to_install(self, manifest: bytes) -> bytes:
        """The manifest of the APK we install: no debug flag, and the game named in English.

        Only the first is load-bearing (the game dies during startup under a debuggable build) and only
        the second is optional: a manifest the rename cannot read keeps the game's own name rather than
        failing the run, because the translation is what the user is here for. Both are reported, so a
        run that did not rename the app says so.
        """
        if is_debuggable(manifest):
            self.log("The cached APK carries the debug flag; rebuilding it without it.")
            manifest = make_debuggable_manifest(manifest, debuggable=False)
        try:
            named = set_label(manifest, APP_NAME)
        except ValueError as error:
            self.log(f"  leaving the app name as it is: {error}")
            return manifest
        if named != manifest:
            self.log(f"  naming the app {APP_NAME!r}")
        return named

    def prepare_normal_apk(self, remote_path: str) -> None:
        self.step("apk", "copying the APK from the phone (~2 GB)")
        if self.run_owner is None:
            raise PatchError("error_run_state", detail="APK preparation requires owned authorization")
        self.apk_journal = ApkJournal(self.run_owner, create=True)
        journal = self.apk_journal
        # Every preparation starts from independently observed content. No size/mtime cache.
        source_identity = self.adb.installed_identity()
        if source_identity is None or source_identity["debuggable"]:
            raise PatchError("error_apk_identity", detail="Recover the saved normal APK before preparation")
        _publish(journal.directory / "preparation-source.json", {"schema": 1, "run_id": self.run_owner.run_id,
                 "target": self.run_owner.target, "source": source_identity})
        source = journal.apk("source")
        if source.exists():
            raise PatchError("error_run_pending", detail=journal.directory)
        candidate = getattr(self, "_preparation_candidate", None)
        self._preparation_candidate = None
        cached_normal = None
        if candidate is not None and candidate.record["apks"].get("source") == source_identity:
            try:
                cached_normal = PreparedApks(self.run_owner, candidate, self.producer_identity()).verify(
                    "normal", self.manifest_to_install(apk_manifest(candidate.apk("source"))))
            except (ArtifactError, OSError, ValueError):
                pass
        if cached_normal is not None:
            _durable_copy(candidate.apk("source"), source)
        else:
            self.adb.run("pull", remote_path, str(source))
        if (self.local_apk_identity(source) != source_identity
                or self.adb.installed_identity() != source_identity):
            raise PatchError("error_apk_identity", detail="Source APK changed during preparation")
        cert = (BUNDLE / "key" / "cert.der").read_bytes()
        installed_source_requires_conversion = source_identity["signers"] != [hashlib.sha256(cert).hexdigest()]
        if self.remove and installed_source_requires_conversion:
            raise PatchError("error_official_nothing_to_remove")
        manifest = apk_manifest(source)
        wanted = self.manifest_to_install(manifest)
        normal = journal.apk("normal")
        if cached_normal is not None:
            _durable_copy(cached_normal, normal)
        elif not installed_source_requires_conversion and wanted == manifest:
            _durable_copy(source, normal)
        else:
            self.build_signed(source, normal, {"AndroidManifest.xml": wanted})
        identity = self.local_apk_identity(normal)
        prepared_normal_is_signed = identity["signers"] == [hashlib.sha256(cert).hexdigest()]
        if (identity["debuggable"] or identity["package"] != source_identity["package"]
                or identity["version"] != source_identity["version"]
                or not prepared_normal_is_signed):
            raise PatchError("error_apk_identity", detail="Prepared normal APK identity mismatch")
        self.normal_apk = normal
        journal.update(apks={"source": source_identity, "normal": identity})
        PreparedApks(self.run_owner, journal, self.producer_identity()).publish("normal", wanted)
        if not installed_source_requires_conversion:
            self.done("apk", "signature matches")
            return
        self._convert_installed_source(source_identity, identity)

    def _convert_installed_source(self, source_identity: dict, identity: dict) -> None:
        """A signed local normal never proves the phone has converted its signer."""
        journal = self.apk_journal
        self.verify_prepared("normal")
        if (journal.record["apks"].get("source") != source_identity
                or journal.record["apks"].get("normal") != identity):
            raise PatchError("error_apk_identity", detail="Conversion differs from pinned preparation")

        # The immutable recovery file is verified and pinned BEFORE exact data-loss consent.
        if not self.ui.ask(ui_text("reinstall_required_title"), ui_text("reinstall_required")):
            raise PatchError("error_cancelled")
        consent = str(uuid.uuid4())
        plan = {"source": source_identity, "normal": identity,
                "consequence": "delete_local_game_data_scan_login"}
        approval = {**plan, "id": consent, "approved_at": datetime.now(timezone.utc).isoformat(),
                    "plan_digest": identity_key(plan), "consumed": "approved"}
        self.run_owner.update(consents={**self.run_owner.record["consents"], consent: approval})
        setup = {"consent": consent, "source": source_identity, "normal": identity,
                 "consequence": approval["consequence"], "phase": "prepared"}
        journal.update(setup=setup)
        if self.adb.installed_identity() != source_identity:
            raise PatchError("error_apk_identity", detail="Game changed after setup approval")
        self.verify_prepared("normal")
        self.run_owner.begin_attempt("uninstall_" + consent, destructive=True)
        self.run_owner.update(consents={**self.run_owner.record["consents"], consent: {**approval, "consumed": "uninstall_intent"}})
        journal.update(setup={**setup, "phase": "uninstall_intent"})
        try:
            self.adb.run("uninstall", PACKAGE, check=False)
        finally:
            # Never dispatch uninstall again, including after an ambiguous transport reply.
            self.recover_first_setup()
        self.finish_setup_update()
        self.done("apk", "reinstalled")

    @staticmethod
    def local_apk_identity(path: Path) -> dict:
        try:
            return apk_tools.apk_identity(path)
        except (OSError, ValueError, KeyError, IndexError, zipfile.BadZipFile) as error:
            raise PatchError("error_apk_identity", detail=error) from error

    def verify_prepared(self, role: str) -> Path:
        journal = self.apk_journal
        if journal is None:
            raise PatchError("error_apk_identity", detail="Missing owned APK journal")
        journal.record = journal.load()
        path = journal.apk(role)
        if self.local_apk_identity(path) != journal.record["apks"].get(role):
            raise PatchError("error_apk_identity", detail=path)
        return path

    def install_prepared(self, role: str, operation: str, *, safety_recovery: bool = False) -> None:
        """Persist before dispatch; audit on both sides of uncertainty and before retries."""
        path = self.verify_prepared(role)
        journal, owner = self.apk_journal, self.run_owner
        access_plan = self._access_plan()
        if role == "normal" and access_plan is not None and operation != "setup_normal":
            operation = access_plan["normal"]
        expected = journal.record["apks"][role]
        key = "apk_" + operation
        installs = journal.record["installs"]
        previous = installs.get(key)
        if previous is not None and previous["expected"] != expected:
            raise PatchError("error_apk_identity", detail="Install intent identity changed")
        observed = self.adb.installed_identity()
        if observed == expected:
            journal.update(installs={**installs, key: {"role": role, "expected": expected, "outcome": "verified"}})
            owner.complete_observed(key)
            return
        allowed = list(journal.record["apks"].values())
        setup = journal.record["setup"]
        if ((observed is not None and observed not in allowed)
                or observed is None and (setup is None or setup["phase"] != "install_intent" or role != "normal")):
            raise PatchError("error_apk_identity", detail="Installed APK is outside the saved operation")
        if previous is not None and previous["outcome"] == "verified":
            raise PatchError("error_apk_identity", detail="A verified installation was externally replaced")
        operation = Operation(key, safety=role == "normal" or safety_recovery)
        with owner.attempt(operation, failure="install_unconfirmed"):
            journal.update(installs={**installs, key: {"role": role, "expected": expected, "outcome": "intent"}})
            self.event("restoring" if role == "normal" else "working", "install_game_app",
                       detail=ui_text("normal_install_progress") if role == "normal" else ui_text("access_install_progress"))
            try:
                try:
                    self.adb.install(path)
                except (PatchError, OSError):
                    # An installer reply can be lost after commit. Observe before retrying.
                    if self.adb.installed_identity() != expected:
                        raise
                if self.adb.installed_identity() != expected:
                    raise PatchError("error_apk_identity", detail="Installed APK differs from prepared bytes")
                journal.update(installs={**journal.record["installs"], key: {
                    "role": role, "expected": expected, "outcome": "verified"}})
            except (PatchError, OSError) as error:
                owner.update(lifecycle="attention")
                journal.update(installs={**journal.record["installs"], key: {
                    "role": role, "expected": expected, "outcome": "attention"}})
                if role == "normal":
                    raise PatchError("error_normal_recovery", detail=path) from error
                raise PatchError("error_apk_identity", detail=path) from error

    def build_signed(self, source: Path, target: Path, replacements: dict[str, bytes]) -> None:
        from run_artifacts import safe_file
        unsigned = target.with_suffix(".unsigned")
        try:
            safe_file(source)
            safe_file(target.parent, directory=True)
            for output in (target, unsigned):
                try:
                    output.lstat()  # includes dangling symlinks and reparse points
                except FileNotFoundError:
                    continue
                raise PatchError("error_run_state", detail="Signing output already exists; retained for diagnosis")
        except (OSError, ArtifactError) as error:
            raise PatchError("error_run_state", detail=error) from error
        if set(replacements) != {"AndroidManifest.xml"}:
            raise PatchError("error_apk_identity", detail="Only manifest rewriting is permitted")
        last = [0.0]

        def progress(done, total):
            self.control_boundary()
            self.event("working", "prepare_apk", items_done=done, items_total=total)
            if time.time() - last[0] > 5:
                last[0] = time.time()
                self.log(f"  building APK {done * 100 // total}%")

        apk_tools.rewrite_apk(source, unsigned, replacements, progress)
        self.log("  signing APK...")
        apk_tools.sign_v2(unsigned, target, (BUNDLE / "key" / "key.pk8").read_bytes(),
                          (BUNDLE / "key" / "cert.der").read_bytes())
        with target.open("rb+") as signed:
            signed.flush()
            os.fsync(signed.fileno())
        unsigned.unlink()

    def prepare_debuggable_apk(self) -> Path:
        self.step("access", "preparing the temporary access APK")
        normal = self.verify_prepared("normal")
        target = self.apk_journal.apk("access")
        if "access" in self.apk_journal.record["apks"] and self._prepared_access != target:
            try:
                self._prepared_access = PreparedApks(self.run_owner, self.apk_journal, self.producer_identity()).verify(
                    "access", make_debuggable_manifest(apk_manifest(normal)))
            except (ArtifactError, OSError, ValueError) as error:
                raise PatchError("error_run_pending", detail=self.apk_journal.directory) from error
        # Fresh owned preparation; a saved descriptor is always rehashed before use.
        if "access" not in self.apk_journal.record["apks"]:
            if target.exists():
                raise PatchError("error_run_state", detail="Uncommitted access output retained")
            manifest = make_debuggable_manifest(apk_manifest(normal))
            self.build_signed(normal, target, {"AndroidManifest.xml": manifest})
            identity = self.local_apk_identity(target)
            expected = self.apk_journal.record["apks"]["normal"]
            if (not identity["debuggable"] or any(identity[k] != expected[k]
                    for k in ("package", "version", "signers"))):
                raise PatchError("error_apk_identity", detail="Access APK identity mismatch")
            self.apk_journal.update(apks={**self.apk_journal.record["apks"], "access": identity})
            PreparedApks(self.run_owner, self.apk_journal, self.producer_identity()).publish("access", manifest)
            self._prepared_access = target
        self.verify_prepared("access")
        self.ui.set_step("access", "active", "installing the access APK (check the phone for a pop-up)")
        return target
