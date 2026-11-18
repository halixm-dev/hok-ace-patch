"""Run-owned Windows file transaction, independent of the translation engine.

Recovery bytes are the actual pre-action layer, never reconstructed pristine input.
Each device operation locks the same inode as Android's GameFileLock. A complete
manifest audit, normal APK audit and commit-last delta publication gate completion.
The caller holds OwnedRun until all child processes exit. No method grants consent.
"""
from __future__ import annotations

import json
import hashlib
import os
import re
import shlex
import shutil
import uuid
from pathlib import Path
from typing import Callable, Protocol

from patch_session import OwnedRun, SessionError
from run_artifacts import (canonical_bytes, file_identity, read_record, relative_path,
                           tree_manifest, validate_manifest, verify_manifest, replace_file, safe_file)

PACKAGE = "com.tencent.tmgp.osgame"
ROOT = "files/QtsVFSCache"
MAX_FILES = 8192
RESERVE_BYTES = 512 * 1024 * 1024
PHASES = {"prepared", "applying", "rollback", "rolled_back", "payload_verified", "finalizing", "finalized"}


def _path(name: str) -> str:
    relative_path(name)
    if (len(name) > 512 or not re.fullmatch(r"(?:packages/[0-9]+|Watchdog)/[A-Za-z0-9_./-]+", name)
            or any(part.startswith(".hok-") for part in name.split("/"))):
        raise SessionError("error_run_state", "Unsafe game path")
    return name


def _publish(path: Path, value: dict) -> None:
    """Large manifests use bounded artifact JSON rather than the small run record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Inspect ancestors before creating the exclusive temporary sibling.
    safe_file(path.parent, directory=True)
    if path.exists():
        safe_file(path)
    temp = path.with_name(path.name + "." + str(uuid.uuid4()) + ".tmp")
    with temp.open("xb") as stream:
        stream.write(canonical_bytes(value)); stream.flush(); os.fsync(stream.fileno())
    replace_file(temp, path)
    if read_record(path) != value:
        raise SessionError("error_run_state", "Transaction journal read-back")


def _durable_copy(source: Path, target: Path) -> None:
    expected = file_identity(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    safe_file(target.parent, directory=True)
    if target.exists():
        safe_file(target)
    temporary = target.with_name(target.name + "." + str(uuid.uuid4()) + ".tmp")
    with source.open("rb") as incoming, temporary.open("xb") as outgoing:
        shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
        outgoing.flush(); os.fsync(outgoing.fileno())
    if file_identity(temporary) != expected:
        raise SessionError("error_run_state", "Retained copy differs")
    replace_file(temporary, target)


class FileTransport(Protocol):
    def inventory(self, session: str) -> dict: ...
    def write(self, session: str, name: str, source: Path, before: dict | None, after: dict) -> None: ...
    def remove(self, session: str, name: str, before: dict) -> None: ...
    def clear_temp(self, session: str, name: str) -> None: ...
    def directories(self, session: str, names: list[str]) -> None: ...


class ShellTransport:
    """Small fixed shell protocol. Uploads never share a path with live files."""
    def __init__(self, adb: object, *, reserve_bytes: int = RESERVE_BYTES) -> None:
        self.adb, self.reserve_bytes = adb, reserve_bytes

    def bind_target(self, target: dict) -> None:
        if (getattr(self.adb, "serial", None) != target["serial"]
                or getattr(self.adb, "android_user", None) != target["android_user"]
                or target["package"] != PACKAGE or target["android_user"] != 0):
            raise SessionError("error_run_target", "File transport target differs")

    def _locked(self, session: str, operation: str, payload: dict, body: str) -> str:
        if str(uuid.UUID(session)) != session:
            raise SessionError("error_run_state", "Invalid transaction session")
        lock = ROOT + "/.hok-ace-patcher.lock"
        script = (f"[ ! -L files ] && [ ! -L {ROOT} ] && [ ! -L {lock} ] || exit 1; "
                  f"{{ [ ! -e {lock} ] || [ -f {lock} ]; }} || exit 1; "
                  f"exec 9>> {lock} || exit 1; /system/bin/flock -x 9 9>&9 || exit 1; "
                  "exec /system/bin/sh -c " + shlex.quote(body) + " 9>&9")
        # Structured comment is also understood by the strict offline fake. The
        # real shell executes only the fixed validated script below it.
        marker = json.dumps({"operation": operation, "session": session, **payload}, separators=(",", ":"))
        return self.adb.shell("# hok-file-transaction " + marker + "\nrun-as " + PACKAGE + " sh -c " + shlex.quote(script))

    @staticmethod
    def _guards(name: str) -> str:
        _path(name)
        parts = (ROOT + "/" + name).split("/")
        return " && ".join(f"[ ! -L {'/'.join(parts[:i])} ]" for i in range(1, len(parts) + 1)) + " || exit 1; "

    @staticmethod
    def _matches(path: str, identity: dict | None) -> str:
        if identity is None:
            return f"[ ! -e {path} ] && [ ! -L {path} ]"
        validate_manifest({"file": identity})
        return (f"[ -f {path} ] && [ ! -L {path} ] && [ $(stat -c %s {path}) = {identity['size']} ] "
                f"&& [ $(sha256sum {path} | cut -d ' ' -f 1) = {identity['sha256']} ]")

    def inventory(self, session: str) -> dict:
        body = (f"cd {ROOT} || exit 1; "
                "for r in packages Watchdog; do [ ! -L $r ] || exit 1; "
                "[ ! -e $r ] || [ -d $r ] || exit 1; done; "
                "[ -d packages ] || exit 1; "
                "set -- packages; [ ! -d Watchdog ] || set -- packages Watchdog; "
                "paths=$(find \"$@\" -print) || exit 1; "
                "printf '%s\\n' \"$paths\" | while IFS= read -r p; do "
                "[ ! -L \"$p\" ] || exit 1; "
                "if [ -d \"$p\" ]; then printf 'D %s\\n' \"$p\" || exit 1; "
                "elif [ -f \"$p\" ]; then "
                "links=$(stat -c %h \"$p\") && [ \"$links\" = 1 ] || exit 1; "
                "h=$(sha256sum \"$p\") && n=$(stat -c %s \"$p\") || exit 1; "
                "printf 'F %s %s %s\\n' \"${h%% *}\" \"$n\" \"$p\" || exit 1; "
                "else exit 1; fi; done")
        output = self._locked(session, "inventory", {}, body)
        files, directories = {}, []
        for line in output.splitlines():
            if line.startswith("D "):
                name = line[2:]; relative_path(name)
                if name not in {"packages", "Watchdog"}:
                    _path(name + "/placeholder")
                if name in directories:
                    raise SessionError("error_run_state", "Duplicate directory")
                directories.append(name)
            else:
                fields = line.split(" ")
                if len(fields) != 4 or fields[0] != "F" or not fields[2].isdecimal():
                    raise SessionError("error_run_state", "Unreadable live manifest")
                name = fields[3]
                # Only our exact temporary basenames can be ignored, never another run's.
                if name.rsplit("/", 1)[-1].startswith(f".hok-{session}-") and name.endswith(".tmp"):
                    continue
                _path(name)
                if name in files:
                    raise SessionError("error_run_state", "Duplicate file")
                files[name] = {"sha256": fields[1], "size": int(fields[2])}
        validate_manifest(files)
        if not files or len(files) > MAX_FILES or len(directories) > MAX_FILES:
            raise SessionError("error_run_state", "Incomplete live manifest")
        return {"files": files, "directories": sorted(directories)}

    @staticmethod
    def _temp(session: str, name: str) -> str:
        _path(name)
        parent, base = name.rsplit("/", 1)
        return f"{ROOT}/{parent}/.hok-{session}-{base}.tmp"

    def write(self, session: str, name: str, source: Path, before: dict | None, after: dict) -> None:
        if file_identity(source) != after:
            raise SessionError("error_run_state", "Write source changed")
        validate_manifest({"file": after})
        target = ROOT + "/" + _path(name)
        temp = self._temp(session, name)
        upload = f"/data/local/tmp/hokace/{session}/{uuid.uuid4()}.upload"
        upload_guards = " && ".join(f"[ ! -L {p} ] && {{ [ ! -e {p} ] || [ -d {p} ]; }}"
                                    for p in ("/data", "/data/local", "/data/local/tmp", "/data/local/tmp/hokace",
                                              f"/data/local/tmp/hokace/{session}"))
        # Upload setup runs as shell, since run-as cannot create shell-owned /data/local/tmp.
        # Use the same fixed marker protocol but do not claim a private game lock here.
        prep = (upload_guards + f" && [ ! -e {upload} ] && [ ! -L {upload} ] && "
                f"mkdir -p /data/local/tmp/hokace/{session} && chmod 755 /data/local/tmp/hokace /data/local/tmp/hokace/{session}")
        marker = json.dumps({"operation": "upload_prepare", "session": session, "upload": upload}, separators=(",", ":"))
        self.adb.shell("# hok-file-upload " + marker + "\n" + prep)
        self.adb.run("push", str(source), upload)
        self.adb.shell(f"[ ! -L {upload} ] && [ -f {upload} ] && chmod 644 {upload}")
        # df reserve includes one full destination temp plus installer/rollback reserve.
        body = (self._guards(name) + upload_guards + " || exit 1; "
                + self._matches(upload, after) + " || exit 1; " + f"[ ! -L {temp} ] || exit 1; "
                + self._matches(target, before) + " || exit 1; "
                f"avail=$(df -k {ROOT} | tail -1 | awk '{{print $4}}'); "
                f"[ \"$avail\" -ge {(after['size'] + self.reserve_bytes + 1023) // 1024} ] || exit 1; "
                f"[ ! -e {temp} ] || [ -f {temp} ] || exit 1; "
                f"mkdir -p {target.rsplit('/', 1)[0]} && cp {upload} {temp} && " + self._matches(temp, after) + f" && sync {temp} && "
                + self._matches(target, before) + f" && mv -f {temp} {target} && sync {target.rsplit('/', 1)[0]} && "
                + self._matches(target, after) + " || exit 1")
        self._locked(session, "write", {"name": name, "before": before, "after": after, "upload": upload}, body)
        self.adb.shell(f"rm -f {upload}")

    def remove(self, session: str, name: str, before: dict) -> None:
        target = ROOT + "/" + _path(name)
        self._locked(session, "remove", {"name": name, "before": before}, self._guards(name)
                     + self._matches(target, before) + f" && rm -f {target} && sync {target.rsplit('/', 1)[0]} || exit 1")

    def clear_temp(self, session: str, name: str) -> None:
        temp = self._temp(session, name)
        self._locked(session, "clear_temp", {"name": name}, self._guards(name)
                     + f"[ ! -L {temp} ] && {{ [ ! -e {temp} ] || [ -f {temp} ]; }} && rm -f {temp} || exit 1")

    def directories(self, session: str, names: list[str]) -> None:
        for name in names:
            if name not in {"packages", "Watchdog"}:
                _path(name + "/placeholder")
            guard = (f"[ ! -L {ROOT}/packages ] || exit 1; " if name == "packages"
                     else self._guards(name + "/placeholder"))
            self._locked(session, "directory", {"name": name}, guard
                         + f"mkdir -p {ROOT}/{name} && sync {ROOT}/{name} || exit 1")


class DeviceTransaction:
    """Explicit apply/reconcile/rollback/finalize seams for the continuation worker."""
    def __init__(self, owner: OwnedRun, transport: FileTransport) -> None:
        self.owner, self.transport = owner, transport
        if isinstance(transport, ShellTransport):
            transport.bind_target(owner.target)
        self.session = owner.record["children"].get("data_session")
        if self.session is None:
            raise SessionError("error_run_state", "Missing data session authority")
        self.directory = owner.root / "sessions" / self.session
        self.path = self.directory / "file-transaction.json"
        self.originals = self.directory / "recovery"
        self.record: dict | None = None
        if self.path.exists():
            self.record = read_record(self.path)
            self._validate()

    def _validate(self) -> None:
        r = self.record
        if (not isinstance(r, dict) or set(r) != {"schema", "run_id", "target", "session", "phase", "original",
                "directories", "expected", "sources", "intents", "metadata", "remove_delta", "cycle"}
                or r["schema"] != 1 or r["run_id"] != self.owner.run_id or r["target"] != self.owner.target
                or r["session"] != self.session or r["phase"] not in PHASES or type(r["remove_delta"]) is not bool
                or type(r["cycle"]) is not int or not 0 <= r["cycle"] <= 32):
            raise SessionError("error_run_state", "Invalid file transaction")
        for manifest in (r["original"], r["expected"]):
            validate_manifest(manifest)
            if len(manifest) > MAX_FILES:
                raise SessionError("error_run_state", "Too many transaction files")
            for name in manifest:
                _path(name)
        if (not isinstance(r["sources"], dict) or not isinstance(r["intents"], dict)
                or not isinstance(r["directories"], list) or len(r["directories"]) > MAX_FILES
                or set(r["intents"]) - (set(r["original"]) | set(r["expected"]))):
            raise SessionError("error_run_state", "Invalid transaction file set")
        for name, source in r["sources"].items():
            _path(name); relative_path(source)
            if name not in r["expected"]:
                raise SessionError("error_run_state", "Unbound staged source")
        for name in r["directories"]:
            if name not in {"packages", "Watchdog"}:
                _path(name + "/placeholder")
        for name, intent in r["intents"].items():
            if (not isinstance(intent, dict) or set(intent) != {"direction", "before", "after", "ack"}
                    or intent["direction"] not in {"apply", "rollback"} or type(intent["ack"]) is not bool):
                raise SessionError("error_run_state", "Invalid write intent")
            for identity in (intent["before"], intent["after"]):
                if identity is not None:
                    validate_manifest({"file": identity})
            allowed = (r["original"].get(name), r["expected"].get(name))
            if intent["before"] not in allowed or intent["after"] not in allowed:
                raise SessionError("error_run_state", "Write intent exceeds transaction")
        validate_manifest(r["metadata"])
        if (set(r["metadata"]) - {"old-delta.bin", "old-pending.bin", "pending-delta.bin", "old-hashes.json", "new-hashes.json", "result-binding.json"}
                or not {"pending-delta.bin", "new-hashes.json"} <= set(r["metadata"])):
            raise SessionError("error_run_state", "Unexpected retained metadata")

    def _save(self, **changes: object) -> None:
        self.record.update(changes)
        self._validate()
        _publish(self.path, self.record)

    def prepare(self, outputs: dict[str, Path | None], metadata: dict[str, Path], *, remove_delta: bool = False,
                initial_cycle: int = 0) -> None:
        if self.record is not None:
            raise SessionError("error_run_state", "Transaction already prepared")
        if type(initial_cycle) is not int or not 0 <= initial_cycle <= 32:
            raise SessionError("error_run_state", "Invalid retained operation cycle")
        if not {"pending-delta.bin", "new-hashes.json"} <= set(metadata):
            raise SessionError("error_run_state", "Missing finalization material")
        # The staging owner supplies a delta in the unchanged shared format, even
        # for Remove (an empty delta). Recovery/finalization itself needs no engine.
        import pristine_delta
        try:
            pending = pristine_delta.read(metadata["pending-delta.bin"])
        except (OSError, ValueError, pristine_delta.DeltaError) as error:
            raise SessionError("error_run_state", "Invalid pending delta") from error
        if bool(pending.files) == remove_delta:
            raise SessionError("error_run_state", "Delta operation differs from payload")
        hashes = read_record(metadata["new-hashes.json"])
        if (set(hashes) != {"schema", "sha256"} or hashes["schema"] != pristine_delta.SCHEMA
                or not isinstance(hashes["sha256"], list)
                or any(not isinstance(value, str) or not re.fullmatch("[0-9a-f]{64}", value) for value in hashes["sha256"])
                or not pending.staged_hashes <= set(hashes["sha256"])):
            raise SessionError("error_run_state", "Invalid staged-hash record")
        keep = self.owner.root / "pristine"
        for live_name, role in (("delta.bin", "old-delta.bin"), ("delta.pending.bin", "old-pending.bin"),
                                ("staged-hashes.json", "old-hashes.json")):
            live = keep / live_name
            if live.exists() != (role in metadata) or live.exists() and file_identity(live) != file_identity(metadata[role]):
                raise SessionError("error_run_state", "Old delta metadata differs")
        snapshot = read_record(self.directory / "recovery-manifest.json")
        if set(snapshot) != {"files", "directories", "target"} or snapshot["target"] != self.owner.target:
            raise SessionError("error_run_state", "Unbound recovery material")
        verify_manifest(self.originals, snapshot["files"])
        if self.transport.inventory(self.session) != {"files": snapshot["files"], "directories": snapshot["directories"]}:
            raise SessionError("error_files_changed", "Phone changed after snapshot")
        expected = dict(snapshot["files"])
        sources = {}
        for name, path in outputs.items():
            name = "packages/" + name
            _path(name)
            if path is None:
                if name not in snapshot["files"]:
                    raise SessionError("error_run_state", "Deletion lacks pre-action bytes")
                expected.pop(name)
                continue
            sources[name] = path.relative_to(self.directory).as_posix()
            expected[name] = file_identity(path)
        if any(expected.get(name) != item for name, item in snapshot["files"].items()) or set(expected) != set(snapshot["files"]):
            expected = {name: item for name, item in expected.items() if not name.startswith("Watchdog/")}
        for entry in pending.files:
            if expected.get("packages/" + entry.path) != {"size": entry.staged_size, "sha256": entry.staged_sha256}:
                raise SessionError("error_run_state", "Pending delta differs from expected output")
        retained = self.directory / "transaction-meta"
        retained.mkdir(exist_ok=True)
        for name, source in metadata.items():
            relative_path(name)
            _durable_copy(source, retained / name)
        self.record = {"schema": 1, "run_id": self.owner.run_id, "target": self.owner.target,
                       "session": self.session, "phase": "prepared", "original": snapshot["files"],
                       "directories": snapshot["directories"], "expected": expected, "sources": sources,
                       "intents": {}, "metadata": tree_manifest(retained), "remove_delta": remove_delta, "cycle": initial_cycle}
        self._save()
        self._reserve_retry_slots()

    def _reserve_retry_slots(self) -> None:
        """Refuse before mutation if the bounded run journal cannot keep rollback budgets."""
        keys = {"files_apply"}
        for name in set(self.record["original"]) | set(self.record["expected"]):
            if self.record["original"].get(name) != self.record["expected"].get(name):
                for direction in ("apply", "rollback"):
                    keys.add("files_" + str(self.record["cycle"]) + "_" + direction + "_" + hashlib.sha256(name.encode()).hexdigest()[:24])
        if len(set(self.owner.record["retry"]) | keys) > 256:
            raise SessionError("error_run_state", "Too many writes for retained retry journal")

    def verify_material(self, *, outputs: bool = True) -> None:
        self._validate()
        verify_manifest(self.originals, self.record["original"])
        verify_manifest(self.directory / "transaction-meta", self.record["metadata"])
        for name, source in (self.record["sources"].items() if outputs else ()):
            if file_identity(self.directory / source) != self.record["expected"][name]:
                raise SessionError("error_run_state", "Staged output changed")

    def reconcile(self) -> dict[str, str]:
        """Read-only classification; unexpected external bytes block every mutation."""
        self.verify_material(outputs=False)
        live = self.transport.inventory(self.session)["files"]
        if set(live) - (set(self.record["original"]) | set(self.record["expected"])):
            raise SessionError("error_files_changed", "Unexpected phone files")
        result = {}
        for name in set(self.record["original"]) | set(self.record["expected"]):
            old, new, actual = self.record["original"].get(name), self.record["expected"].get(name), live.get(name)
            state = "before" if actual == old else "after" if actual == new else "absent" if actual is None else "other"
            # Absence is allowed only for planned creation/deletion, never truncation.
            if state in {"other", "absent"}:
                raise SessionError("error_files_changed", f"External change: {name}")
            # An after-state requires persisted intent, unless both byte identities match.
            if actual != old and name not in self.record["intents"]:
                raise SessionError("error_files_changed", f"Unjournalled change: {name}")
            result[name] = state
        return result

    def _change(self, name: str, desired: dict | None, source: Path | None, direction: str) -> None:
        actual = self.transport.inventory(self.session)["files"].get(name)
        if actual == desired:
            intent = self.record["intents"].get(name)
            if intent is not None and intent["direction"] == direction and intent["after"] == desired and not intent["ack"]:
                key = "files_" + str(self.record["cycle"]) + "_" + direction + "_" + hashlib.sha256(name.encode()).hexdigest()[:24]
                self.owner.complete_observed(key)
                self._save(intents={**self.record["intents"], name: {**intent, "ack": True}})
            return
        key = "files_" + str(self.record["cycle"]) + "_" + direction + "_" + hashlib.sha256(name.encode()).hexdigest()[:24]
        self._save(intents={**self.record["intents"], name: {"direction": direction, "before": actual,
                                                            "after": desired, "ack": False}})
        self.owner.begin_attempt(key, safety_recovery=direction == "rollback")
        try:
            self.transport.clear_temp(self.session, name)
            if desired is None:
                self.transport.remove(self.session, name, actual)
            else:
                self.transport.write(self.session, name, source, actual, desired)
        except Exception:
            # A reply can be lost after rename. Reconciliation is authoritative.
            if self.transport.inventory(self.session)["files"].get(name) != desired:
                self.owner.record_failure(key, "file operation interrupted")
                raise
        if self.transport.inventory(self.session)["files"].get(name) != desired:
            raise SessionError("error_files_changed", "Live read-back differs")
        self.owner.complete_attempt(key, reconciled_success=True)
        self._save(intents={**self.record["intents"], name: {**self.record["intents"][name], "ack": True}})

    def apply(self) -> None:
        if self.record["phase"] not in {"prepared", "payload_verified"}:
            raise SessionError("error_run_state", "Cannot apply transaction phase")
        self.reconcile()
        self.verify_material()
        self._reserve_retry_slots()
        if self.record["phase"] == "payload_verified":
            self.audit()
            return
        # One initial layer apply plus one automatic retry across all cycles and
        # reopens. Cycle numbers never reset this logical operation's budget.
        self.owner.begin_attempt("files_apply")
        self._save(phase="applying")
        for name in sorted(set(self.record["original"]) | set(self.record["expected"]), key=lambda item: (item.startswith("Watchdog/"), item)):
            if self.owner.record["stop_requested"]:
                raise SessionError("error_run_state", "Stop requested; rollback required")
            self.reconcile()
            desired = self.record["expected"].get(name)
            source = self.directory / self.record["sources"][name] if name in self.record["sources"] else self.originals / name
            self._change(name, desired, source, "apply")
            self.transport.clear_temp(self.session, name)
        self.audit()
        self._save(phase="payload_verified")

    def reapply(self) -> None:
        """New bounded cycle only after a fully audited rollback, never on reopen.

        The coordinator calls this once when it deliberately continues valid staged
        work. Ordinary apply/reconcile never increments the durable cycle or budget.
        """
        if self.record["phase"] != "rolled_back" or self.owner.winding_down:
            raise SessionError("error_run_state", "Reapply requires verified rollback and continuation")
        self.reconcile()
        if self.transport.inventory(self.session)["files"] != self.record["original"]:
            raise SessionError("error_files_changed", "Reapply source differs")
        budget = self.owner.record["retry"].get("files_apply", {})
        if budget.get("attempts", 0) >= 2 or budget.get("completed"):
            raise SessionError("error_run_retry", "files_apply")
        self._save(phase="prepared", cycle=self.record["cycle"] + 1, intents={})
        self.apply()

    def audit(self) -> None:
        self.verify_material()
        if self.transport.inventory(self.session)["files"] != self.record["expected"]:
            raise SessionError("error_files_changed", "Complete applied layer differs")

    def rollback(self) -> None:
        if self.record["phase"] in {"finalizing", "finalized"}:
            raise SessionError("error_run_state", "Finalization must reconcile forward")
        self.reconcile()
        self._save(phase="rollback")
        self.transport.directories(self.session, self.record["directories"])
        for name in sorted(set(self.record["original"]) | set(self.record["expected"]), key=lambda item: (item.startswith("Watchdog/"), item)):
            self.reconcile()
            self._change(name, self.record["original"].get(name), self.originals / name, "rollback")
            self.transport.clear_temp(self.session, name)
        live = self.transport.inventory(self.session)
        if live["files"] != self.record["original"] or not set(self.record["directories"]) <= set(live["directories"]):
            raise SessionError("error_files_changed", "Rollback layer differs")
        self._save(phase="rolled_back")

    def finalize(self, keep: Path, verify_normal: Callable[[], None]) -> None:
        """Audit via access, then callback restores/audits normal before promotion.

        The callback may install normal after this method's full live-layer audit;
        a nondebuggable normal APK cannot perform a subsequent run-as inventory.
        Reopened finalization must establish access again before calling this API.
        """
        if self.record["phase"] not in {"payload_verified", "finalizing", "finalized"}:
            raise SessionError("error_run_state", "Payload is not verified")
        if self.owner.record["stop_requested"] and self.record["phase"] == "payload_verified":
            raise SessionError("error_run_state", "Stop requires rollback before finalization")
        self.audit()
        verify_normal()
        if self.owner.record["stop_requested"] and self.record["phase"] == "payload_verified":
            raise SessionError("error_run_state", "Stop during normal install requires rollback")
        metadata = self.directory / "transaction-meta"
        if keep != self.owner.root / "pristine":
            raise SessionError("error_run_state", "Wrong delta destination")
        safe_file(keep.parent, directory=True)
        if keep.exists():
            safe_file(keep, directory=True)
        else:
            keep.mkdir()
        # Do not overwrite a delta another action/external actor changed. After
        # finalization intent either the pinned old or pinned new state can exist.
        for name, role, new_role in (("delta.bin", "old-delta.bin", "pending-delta.bin"),
                                    ("staged-hashes.json", "old-hashes.json", "new-hashes.json"),
                                    ("delta.pending.bin", "old-pending.bin", "old-pending.bin")):
            path = keep / name
            actual = file_identity(path) if path.exists() else None
            old = self.record["metadata"].get(role)
            new = None if name == "delta.bin" and self.record["remove_delta"] else self.record["metadata"].get(new_role)
            allowed = [old] if self.record["phase"] == "payload_verified" else [old, new]
            if name == "delta.pending.bin" and self.record["phase"] in {"finalizing", "finalized"}:
                allowed.append(None)
            if actual not in allowed:
                raise SessionError("error_files_changed", "Delta metadata changed externally")
        if self.record["phase"] == "finalized":
            self._verify_final_metadata(keep)
            if not self.owner.record["retry"]["files_apply"]["completed"]:
                self.owner.complete_attempt("files_apply", reconciled_success=True)
            return
        self._save(phase="finalizing")
        # Pending stays retained in the session across deletion/promotion interruption.
        if self.record["remove_delta"]:
            if (keep / "delta.bin").exists():
                replace_file(keep / "delta.bin", self.directory / "removed-delta.bin")
        else:
            _durable_copy(metadata / "pending-delta.bin", keep / "delta.bin")
        _durable_copy(metadata / "new-hashes.json", keep / "staged-hashes.json")
        if (keep / "delta.pending.bin").exists():
            replace_file(keep / "delta.pending.bin", self.directory / "retired-pending.bin")
        from run_artifacts import sync_directory
        sync_directory(keep)
        self._verify_final_metadata(keep)
        self._save(phase="finalized")
        self.owner.complete_attempt("files_apply", reconciled_success=True)

    def _verify_final_metadata(self, keep: Path) -> None:
        if file_identity(keep / "staged-hashes.json") != self.record["metadata"]["new-hashes.json"]:
            raise SessionError("error_run_state", "Staged-hash publication differs")
        if (keep / "delta.pending.bin").exists():
            raise SessionError("error_run_state", "Pending delta was not retired")
        if self.record["remove_delta"]:
            if (keep / "delta.bin").exists():
                raise SessionError("error_run_state", "Delta removal did not persist")
        elif file_identity(keep / "delta.bin") != self.record["metadata"]["pending-delta.bin"]:
            raise SessionError("error_run_state", "Delta publication differs")
