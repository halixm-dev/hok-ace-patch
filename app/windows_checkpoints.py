"""Windows commit-last checkpoints around the unchanged staging primitive.

Receipts never authorize dispatch. The owner supplies immutable intent, and core
reconciles live input before consuming one. Snapshot validation deliberately uses
its saved producer: translation-engine changes invalidate staging, not pulled bytes.
"""
from __future__ import annotations

import shutil
import uuid
import hashlib
import zipfile
import time
from datetime import datetime
from pathlib import Path

from device_transaction import _publish, _durable_copy
from patch_session import ApkJournal, OwnedRun, SessionError
from run_artifacts import (ArtifactError, RECEIPT_NAME, file_identity, identity_key,
                           make_input_identity, publish_receipt, read_record,
                           tree_manifest, verify_manifest, verify_receipt, installed_state_key)


def active_delta_identity(keep: Path) -> dict:
    """Explicit absence and fresh full hashes, never a cached finalization flag."""
    from run_artifacts import _safe_file
    import pristine_delta
    # lstat-backed guards cover explicit absence as well as readable files.
    current = keep
    while not current.exists():
        try:
            info = current.lstat()
        except FileNotFoundError:
            info = None
        if info is not None and (current.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400):
            raise ArtifactError("Linked absent delta path")
        current = current.parent
    _safe_file(current, directory=True)
    for name in ("delta.bin", "delta.pending.bin", "staged-hashes.json", "restore-refused.json", "redownload.json"):
        path = keep / name
        try:
            info = path.lstat()
        except FileNotFoundError:
            info = None
        if info is not None and (path.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400):
            raise ArtifactError("Linked pristine knowledge")
        if path.exists():
            file_identity(path)
    if (keep / "delta.bin").exists():
        pristine_delta.read(keep / "delta.bin")
    return {name: file_identity(keep / name) if (keep / name).exists() else None
            for name in ("delta.bin", "delta.pending.bin", "staged-hashes.json", "restore-refused.json", "redownload.json")}


def reuse_completed(checkpoint: Checkpoints, identity: dict, apks: dict) -> tuple[dict, Path] | None:
    """Adopt verified output into a fresh owned attempt; no old authorization is consumed.

    The current snapshot was audited against live bytes. The caller keeps access
    open and uses the usual transaction, installed-normal audit and finalization.
    Missing or incompatible optional cache is a miss, never recovery authority.
    """
    import apk_tools
    from device_transaction import DeviceTransaction
    owner = checkpoint.owner
    if owner.record["action"] != "translate":
        return None  # Remove invalidates translation reuse; do not invent repeat-deletion authority.
    started = time.monotonic()
    delta = active_delta_identity(owner.root / "pristine")
    wanted = installed_state_key(identity, files=identity["game"]["files"], installed=apks["normal"], delta=delta)
    for directory in (owner.root / "sessions").iterdir():
        marker = directory / "completion-receipt.json"
        if not directory.is_dir() or directory == checkpoint.session or not marker.exists():
            continue
        try:
            if (directory / "cache-invalidated.json").exists():
                continue
            complete = read_record(marker)
            if (complete.get("schema") != 2 or complete.get("outcome") != "verified_complete"
                    or complete.get("target") != owner.target or complete.get("installed_key") != wanted
                    or complete.get("action") != owner.record["action"]
                    or complete.get("language") != owner.record["language"]):
                continue
            terminal = read_record(directory / "session-retention.json")
            if (terminal.get("schema") != 1 or terminal.get("lifecycle") != "finalized"
                    or terminal.get("run_id") != complete["run_id"] or terminal.get("target") != owner.target):
                continue
            tx = read_record(directory / "file-transaction.json")
            if (tx.get("phase") != "finalized" or tx["run_id"] != complete["run_id"]
                    or tx["expected"] != complete["files"] or tx["target"] != owner.target):
                raise ArtifactError("Completion differs from finalized transaction")
            verify_manifest(directory / "transaction-meta", tx["metadata"])
            binding = read_record(directory / "transaction-meta/result-binding.json")
            from run_artifacts import relative_path
            root = directory / relative_path(binding["root"])
            stage = verify_receipt(root, stage="staged")
            if read_record(root / "deletions.json").get("paths"):
                continue  # Already-absent creations have no current deletion pre-action proof.
            if (file_identity(root / RECEIPT_NAME) != binding["receipt"]
                    or binding["receipt"] != complete["build_receipt"]
                    or file_identity(root / "device_patch_summary.json") != binding["summary"]
                    or stage["run_id"] != complete["run_id"]
                    or stage["identity"] != complete["identity"]
                    or read_record(root / "expected-layer.json") != {"schema": 1, "files": tx["expected"]}
                    or read_record(root / "device_patch_summary.json") != complete["result"]):
                raise ArtifactError("Completion provenance differs")
            if installed_state_key(stage["identity"], files=tx["expected"], installed=complete["normal"], delta=delta) != wanted:
                continue
            # Re-read original source/prime/prepared APKs, not just the normalized currently installed APK.
            if str(uuid.UUID(complete["apk_session"])) != complete["apk_session"]:
                raise ArtifactError("Unsafe APK lineage")
            apk_directory = owner.root / "sessions" / complete["apk_session"]
            apk_paths = {"source": "source.apk", "normal": "normal.apk", "access": "access.apk"}
            for role, name in apk_paths.items():
                if apk_tools.apk_identity(apk_directory / name) != stage["identity"]["apks"][role]:
                    raise ArtifactError("Original APK provenance changed")
            if stage["identity"]["apks"]["normal"] != apks["normal"]:
                continue  # Prime content must be the same actual APK used by this build.
            before = PreparedApks.content(apk_directory / "source.apk")
            after = PreparedApks.content(apk_directory / "normal.apk")
            before["AndroidManifest.xml"] = after["AndroidManifest.xml"]
            if before != after:
                raise ArtifactError("Original source relationship differs")
            # Derive final metadata from immutable transaction material; saved hashes alone cannot attest it.
            probe = object.__new__(DeviceTransaction)
            probe.record = tx
            probe.directory = directory
            probe._verify_final_metadata(owner.root / "pristine")
        except (ArtifactError, SessionError, OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile):
            continue
        copy_bytes = sum(item["size"] for item in stage["artifacts"].values())
        largest = max((item["size"] for item in stage["artifacts"].values()), default=0)
        reserve = copy_bytes + largest + apks["normal"]["size"] * 2 + 512 * 1024**2
        if shutil.disk_usage(owner.root).free < reserve:
            return None  # No allocation; ordinary work performs its own exact budget/refusal.
        attempt = owned_attempt(owner, checkpoint.session, "build")
        result = attempt / "committed"
        result.mkdir()
        for name in stage["artifacts"]:
            if name in {"expected-output-manifest.json", "attempt-owner.json", "reuse-provenance.json"}:
                continue
            _durable_copy(root / name, result / name)
        _publish(result / "reuse-provenance.json", {"schema": 1, "kind": "completed-install-output-copy",
                 "run_id": complete["run_id"], "completion": file_identity(marker),
                 "input_key": stage["input_key"], "result": file_identity(root / "device_patch_summary.json")})
        _publish(attempt / "completion-reuse-metrics.json", {"schema": 1, "copied_bytes": copy_bytes,
                 # Canonical records hold no floats; whole milliseconds, as on Android.
                 "validation_and_copy_ms": round((time.monotonic() - started) * 1000),
                 "pristine_reconstruction_calls": 0, "translation_build_calls": 0})
        checkpoint.publish_build(result, identity, remove=owner.record["action"] == "remove")
        return complete["result"], result
    return None


class PreparedApks:
    """Commit-last, bounded preparation proofs; never mutation authorization.

    The journal's APK files remain immutable recovery material. Each role gets one
    receipt after its complete source, manifest-only content and output are read
    back. Missing producer evidence disables reuse, not fresh preparation/recovery.
    """
    def __init__(self, owner: OwnedRun, journal: ApkJournal, producer: dict | None) -> None:
        self.owner, self.journal, self.producer = owner, journal, producer

    @staticmethod
    def content(path: Path) -> dict:
        """Hash every unsigned entry; v1 signature records alone may disappear."""
        import apk_tools
        file_identity(path)  # Reject links/reparse points before opening the ZIP.
        result = {}
        with zipfile.ZipFile(path) as archive:
            if len(archive.infolist()) > 100000:
                raise ArtifactError("APK inventory exceeds preparation limit")
            seen = set()
            for item in archive.infolist():
                if item.filename in seen:
                    raise ArtifactError("Duplicate APK entry")
                seen.add(item.filename)
                upper = item.filename.upper()
                if upper.startswith("META-INF/") and upper.endswith(apk_tools.SIGNATURE_SUFFIXES):
                    continue
                digest = hashlib.sha256()
                with archive.open(item) as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(block)
                result[item.filename] = {"size": item.file_size, "sha256": digest.hexdigest()}
        return result

    def identity(self, role: str, manifest: bytes) -> dict:
        if role not in {"normal", "access"}:
            raise ArtifactError("Unknown preparation role")
        from patcher_core import BUNDLE
        self.journal.record = self.journal.load()
        source_role = "source" if role == "normal" else "normal"
        source = self.journal.apk(source_role)
        import apk_tools
        observed = apk_tools.apk_identity(source)
        if observed != self.journal.record["apks"].get(source_role):
            raise ArtifactError("Preparation source differs from pinned journal")
        return make_input_identity(
            target={"device": self.owner.target["serial"], "android_user": self.owner.target["android_user"],
                    "package": self.owner.target["package"], "provider": "adb"},
            request={"action": self.owner.record["action"], "language": self.owner.record["language"],
                     "options": {"role": role, "manifest": {"size": len(manifest),
                                 "sha256": hashlib.sha256(manifest).hexdigest()},
                                 "signing_key": file_identity(BUNDLE / "key/key.pk8"),
                                 "certificate": file_identity(BUNDLE / "key/cert.der")}},
            game={"files": {}, "readiness": "preparation-only"}, apks={source_role: observed},
            delta=None, translation={"scope": "manifest-only-preparation"}, producer=self.producer)

    def publish(self, role: str, manifest: bytes) -> None:
        if self.producer is None:
            return
        import apk_tools
        source = self.journal.apk("source" if role == "normal" else "normal")
        target = self.journal.apk(role)
        identity = self.identity(role, manifest)
        before, after = self.content(source), self.content(target)
        before["AndroidManifest.xml"] = {"size": len(manifest), "sha256": hashlib.sha256(manifest).hexdigest()}
        if before != after:
            raise ArtifactError("Prepared APK changed more than its manifest")
        output = apk_tools.apk_identity(target)
        if output != self.journal.record["apks"].get(role):
            raise ArtifactError("Prepared output differs from pinned journal")
        path = self.journal.directory / (role + "-preparation-receipt.json")
        if path.exists():
            raise ArtifactError("Preparation receipt is immutable")
        _publish(path, {"schema": 1, "committed": True, "run_id": self.owner.run_id,
                       "identity": identity, "input_key": identity_key(identity),
                       "output": output, "content_key": identity_key(after)})
        self.verify(role, manifest)

    def verify(self, role: str, manifest: bytes) -> Path:
        try:
            return self._verify(role, manifest)
        except (OSError, ValueError, KeyError, IndexError, TypeError, zipfile.BadZipFile) as error:
            raise ArtifactError("Prepared APK proof is unreadable") from error

    def _verify(self, role: str, manifest: bytes) -> Path:
        import apk_tools
        record = read_record(self.journal.directory / (role + "-preparation-receipt.json"))
        identity = self.identity(role, manifest)  # Complete current producer is mandatory.
        target = self.journal.apk(role)
        before = self.content(self.journal.apk("source" if role == "normal" else "normal"))
        before["AndroidManifest.xml"] = {"size": len(manifest), "sha256": hashlib.sha256(manifest).hexdigest()}
        after = self.content(target)
        if (set(record) != {"schema", "committed", "run_id", "identity", "input_key", "output", "content_key"}
                or type(record["schema"]) is not int or record["schema"] != 1
                or record["committed"] is not True or record["run_id"] != self.owner.run_id
                or record["identity"] != identity or record["input_key"] != identity_key(identity)
                or record["output"] != self.journal.record["apks"].get(role)
                or apk_tools.apk_identity(target) != record["output"]
                or before != after or identity_key(after) != record["content_key"]):
            raise ArtifactError("Prepared APK receipt changed or is incomplete")
        return target


def owned_attempt(owner: OwnedRun, session: Path, kind: str) -> Path:
    """Persist every attempt UUID before creating any attempt-local bytes."""
    from run_artifacts import _safe_file
    if kind not in {"prepared", "snapshot", "build"}:
        raise ArtifactError("Unknown attempt stage")
    _safe_file(session, directory=True)
    if not session.resolve(strict=True).is_relative_to((owner.root / "sessions").resolve(strict=True)):
        raise ArtifactError("Attempt escaped owned sessions")
    token = str(uuid.uuid4())
    owner.update(children={**owner.record["children"], kind + "_attempt": token})
    parent = session / (kind + "-attempts")
    parent.mkdir(exist_ok=True)
    result = parent / token
    result.mkdir()
    _publish(result / "attempt-owner.json", {"schema": 1, "run_id": owner.run_id, "stage": kind})
    return result


class Checkpoints:
    """Retained snapshot/build descriptors scoped to one authorized data session."""
    def __init__(self, owner: OwnedRun, session: Path) -> None:
        self.owner, self.session = owner, session
        if session != owner.root / "sessions" / owner.record["children"].get("data_session", ""):
            raise SessionError("error_run_state", "Checkpoint session is not owned")

    def snapshot(self) -> dict:
        record = read_record(self.session / "recovery-manifest.json")
        if set(record) != {"files", "directories", "target"} or record["target"] != self.owner.target:
            raise ArtifactError("Snapshot target changed")
        verify_manifest(self.session / "recovery", record["files"])
        return record

    def identity(self, apks: dict, producer: dict, *, snapshot_only: bool = False) -> dict:
        snapshot = self.snapshot()
        keep = self.owner.root / "pristine"
        delta = {name: file_identity(keep / name) for name in
                 ("delta.bin", "delta.pending.bin", "staged-hashes.json") if (keep / name).exists()}
        return make_input_identity(
            target={"device": self.owner.target["serial"], "android_user": self.owner.target["android_user"],
                    "package": self.owner.target["package"], "provider": "adb"},
            request={"action": self.owner.record["action"], "language": self.owner.record["language"],
                     "options": {"fit_only": False, "cycle_assets": [], "normal_manifest": "saved-intent"}},
            game={"files": snapshot["files"], "readiness": read_record(self.session / "pull.json")["data_version"],
                  "directories": snapshot["directories"]},
            apks=apks, delta=None if snapshot_only else delta or None,
            translation={"scope": "snapshot" if snapshot_only else "complete-producer"}, producer=producer)

    def publish_snapshot(self, apks: dict, producer: dict | None) -> None:
        if producer is None:
            return  # Ordinary verified processing still uses the independently retained originals.
        root = owned_attempt(self.owner, self.session, "snapshot")
        _durable_copy(self.session / "recovery-manifest.json", root / "source-manifest.json")
        _durable_copy(self.session / "pull.json", root / "pull.json")
        publish_receipt(root, identity=self.identity(apks, producer, snapshot_only=True),
                        run_id=self.owner.run_id, stage="snapshot")

    def verify_snapshot(self, apks: dict, live: dict) -> dict:
        if (self.session / "cache-invalidated.json").exists():
            raise ArtifactError("Resolved cache was invalidated")
        child = self.owner.record["children"].get("snapshot_attempt")
        if child is None:
            raise ArtifactError("No committed snapshot receipt")
        root = self.session / "snapshot-attempts" / child
        receipt = verify_receipt(root, stage="snapshot")
        if receipt["run_id"] != self.owner.run_id:
            raise ArtifactError("Snapshot owner changed")
        # Reconcile transport evidence, not the current translation producer.
        identity = self.identity(apks, receipt["identity"]["producer"], snapshot_only=True)
        if receipt["input_key"] != identity_key(identity):
            raise ArtifactError("Snapshot inputs changed")
        saved = self.snapshot()
        if (read_record(root / "source-manifest.json") != saved
                or read_record(root / "pull.json") != read_record(self.session / "pull.json")
                or live != {"files": saved["files"], "directories": saved["directories"]}):
            raise ArtifactError("Live snapshot source changed")
        return receipt

    def reset_pristine_input(self) -> None:
        """Only mutable reconstruction is discarded; actual originals remain immutable."""
        from patcher_core import LAYER
        target = self.session / LAYER
        if target.exists():
            resolved = target.resolve(strict=True)
            if (not resolved.is_relative_to(self.session.resolve(strict=True))
                    or resolved == self.session.resolve(strict=True)):
                raise ArtifactError("Pristine input escaped its owned session")
            # tree_manifest rejects symlink/junction escapes before recursive removal.
            tree_manifest(target)
            shutil.rmtree(target)
        shutil.copytree(self.session / "recovery" / "packages", target)

    def build_root(self) -> Path | None:
        child = self.owner.record["children"].get("build_attempt")
        return self.session / "build-attempts" / child / "committed" if child else None

    def publish_build(self, root: Path, identity: dict, *, remove: bool) -> dict:
        refs = {"summary": "device_patch_summary.json", "delta": None if remove else "delta.pending.bin",
                "manifest": "expected-output-manifest.json"}
        artifacts = tree_manifest(root, exclude=frozenset({RECEIPT_NAME, refs["manifest"]}))
        files = {name: item for name, item in artifacts.items()
                 if name not in {refs["summary"], refs["delta"], "attempt-owner.json"}}
        _publish(root / refs["manifest"], {"schema": 1, "files": files})
        return publish_receipt(root, identity=identity, run_id=self.owner.run_id,
                               stage="staged", references=refs)

    def verify_build(self, identity: dict) -> tuple[dict, Path]:
        if (self.session / "cache-invalidated.json").exists():
            raise ArtifactError("Resolved cache was invalidated")
        root = self.build_root()
        if root is None:
            raise ArtifactError("No completed build")
        receipt = verify_receipt(root, identity=identity, stage="staged")
        if receipt["run_id"] != self.owner.run_id:
            raise ArtifactError("Build owner changed")
        return read_record(root / "device_patch_summary.json"), root


def prune_sessions(owner: OwnedRun, keep: Path) -> list[Path]:
    """Remove only proven resolved optional groups; unknown material stays pinned.

    One newest resolved cache group per exact device target is retained, alongside
    all references from the current unresolved intent. Caller holds both OS locks.
    """
    from patch_session import RESOLVED, validate
    if not owner.locks:
        raise SessionError("error_run_state", "Cleanup requires ownership")
    root = owner.root / "sessions"
    record = validate(read_record(root / "run-intent.json"), owner.root)
    pinned = {keep.name}
    if record["lifecycle"] not in RESOLVED:
        pinned.update(record["children"].values())
    groups = []
    for directory in root.iterdir():
        if not directory.is_dir():
            continue
        marker = directory / "session-retention.json"
        if not marker.exists():
            pinned.add(directory.name)  # Legacy/unknown state cannot grant deletion.
            continue
        value = read_record(marker)
        if (set(value) != {"schema", "run_id", "target", "lifecycle", "references", "resolved_at"}
                or value["schema"] != 1 or value["lifecycle"] not in RESOLVED
                or not isinstance(value["references"], list) or not value["references"]):
            raise ArtifactError("Unknown retention record")
        for name in (value["run_id"], *value["references"]):
            if not isinstance(name, str) or str(uuid.UUID(name)) != name:
                raise ArtifactError("Unsafe retention reference")
        if directory.name not in value["references"] or not isinstance(value["resolved_at"], str):
            raise ArtifactError("Unbound retention group")
        target = value["target"]
        if (not isinstance(target, dict) or set(target) != {"serial", "android_user", "package"}
                or not isinstance(target["serial"], str) or not target["serial"]
                or type(target["android_user"]) is not int or target["android_user"] != 0
                or target["package"] != "com.tencent.tmgp.osgame"
                or datetime.fromisoformat(value["resolved_at"]).tzinfo is None):
            raise ArtifactError("Unbound retention target/time")
        members = set(value["references"])
        # Every group's independently readable APK/file journal must agree. An
        # incomplete outcome pins the whole group even if retention says resolved.
        unresolved = False
        for name in members:
            member = root / name
            for filename in ("apk-journal.json", "file-transaction.json"):
                path = member / filename
                if not path.exists():
                    continue
                journal = read_record(path)
                if journal.get("run_id") != value["run_id"] or journal.get("target") != value["target"]:
                    raise ArtifactError("Retention journal binding differs")
                if filename == "file-transaction.json":
                    unresolved |= journal.get("phase") not in {"finalized", "rolled_back"}
                else:
                    setup = journal.get("setup")
                    unresolved |= setup is not None and setup.get("phase") not in {"ready", "waiting_update", "prepared"}
                    unresolved |= any(item.get("outcome") != "verified" for item in journal.get("installs", {}).values())
        if unresolved:
            pinned.update(members)
        groups.append((value["resolved_at"], identity_key(value["target"]), directory, members))
        # A member without its own retention marker belongs to this proven group,
        # rather than being unconditionally considered unknown.
    known_members = set().union(*(group[3] for group in groups)) if groups else set()
    # Remove unknown-directory pins only for members of a validated resolved group;
    # retain explicit unresolved/current/keep references separately.
    protected = {keep.name}
    if record["lifecycle"] not in RESOLVED:
        protected.update(record["children"].values())
    for _, _, _, members in groups:
        for name in members:
            if name not in protected and name in known_members:
                pinned.discard(name)
    # Re-pin unresolved groups after removing the conservative unknown pins.
    for _, _, directory, members in groups:
        for name in members:
            path = root / name / "file-transaction.json"
            if path.exists() and read_record(path).get("phase") not in {"finalized", "rolled_back"}:
                pinned.update(members)
            apk = root / name / "apk-journal.json"
            if apk.exists():
                value = read_record(apk)
                if (any(item.get("outcome") != "verified" for item in value.get("installs", {}).values())
                        or value.get("setup") is not None and value["setup"].get("phase") not in {"ready", "waiting_update", "prepared"}):
                    pinned.update(members)
    newest = set()
    deleted = []
    for _, target, directory, members in sorted(groups, key=lambda group: group[0], reverse=True):
        if target not in newest:
            newest.add(target)
            pinned.update(members)
            continue
        if members & pinned:
            continue
        _publish(directory / "cache-invalidated.json", {"schema": 1, "reusable": False})
        for name in sorted(members):
            path = root / name
            if not path.exists():
                continue
            resolved = path.resolve(strict=True)
            if resolved.parent != root.resolve(strict=True):
                raise ArtifactError("Cleanup escaped the owned sessions directory")
            tree_manifest(path)  # Refuse links, reparse points and shared writable bodies.
            shutil.rmtree(path)
            deleted.append(path)
    return deleted
