"""Windows durable authorization and ownership; discovery never dispatches phone work.

Lock order: work root, stable device lock, then short-lived registry lock. Discovery
holds only the registry lock. Windows exclusive inherited handles pin ownership while
an ADB child survives its parent. No PID/age heuristic can break a live owner.
"""
from __future__ import annotations

import copy
import hashlib
import os
import re
import stat
import uuid
import threading
from functools import wraps
from datetime import datetime, timezone
from pathlib import Path

from run_artifacts import (ArtifactError, canonical_bytes, identity_key, read_record, sync_file,
                           _replace, _sync_directory)

SCHEMA = 1
PACKAGE = "com.tencent.tmgp.osgame"
MAX_ROOTS = 128
MAX_RECORD = 256 * 1024
LIFECYCLES = {"authorized", "preparing", "waiting", "snapshot", "building", "staged",
              "applying", "payload_verified", "normal_verified", "finalized", "cancelled", "attention"}
RESOLVED = {"finalized", "cancelled"}
TRANSITIONS = {
    "authorized": {"preparing"}, "preparing": {"snapshot"}, "snapshot": {"building"},
    "building": {"staged"}, "staged": {"applying"}, "applying": {"payload_verified"},
    "payload_verified": {"normal_verified"}, "normal_verified": {"finalized", "cancelled"},
    "waiting": LIFECYCLES - RESOLVED, "attention": LIFECYCLES - RESOLVED,
}
# Explicit reconciliation edges; core must prove the indicated checkpoint or
# pre-mutation/rolled-back consistency before moving this progress projection.
TRANSITIONS["authorized"].add("normal_verified")
TRANSITIONS["preparing"].add("normal_verified")
TRANSITIONS["snapshot"].update({"preparing", "staged", "normal_verified"})
TRANSITIONS["building"].update({"preparing", "snapshot", "normal_verified"})
TRANSITIONS["staged"].update({"preparing", "snapshot", "normal_verified"})
TRANSITIONS["applying"].update({"preparing", "staged", "normal_verified"})
TRANSITIONS["payload_verified"].update({"preparing", "staged"})
TRANSITIONS["normal_verified"].update({"preparing", "staged"})


class SessionError(ValueError):
    """Keyed actionable error, translated by the core boundary."""
    def __init__(self, key: str, detail: object = "") -> None:
        self.key, self.detail = key, str(detail)
        super().__init__(f"{key}: {detail}")


def validate_apk_identity(value: dict) -> dict:
    """Require complete byte/package/version/signer/debug evidence."""
    if (not isinstance(value, dict) or set(value) != {"size", "sha256", "package", "version", "signers", "debuggable"}
            or type(value["size"]) is not int or not 0 < value["size"] <= 4 * 1024**3
            or not isinstance(value["sha256"], str) or not re.fullmatch("[0-9a-f]{64}", value["sha256"])
            or value["package"] != PACKAGE or type(value["version"]) is not int or value["version"] < 0
            or type(value["debuggable"]) is not bool or not isinstance(value["signers"], list)
            or not 1 <= len(value["signers"]) <= 16
            or any(not isinstance(v, str) or not re.fullmatch("[0-9a-f]{64}", v) for v in value["signers"])
            or value["signers"] != sorted(set(value["signers"]))):
        raise SessionError("error_run_state", "APK identity")
    return value


class ApkJournal:
    """Run-owned immutable recovery APKs and commit-before-dispatch install/setup intents.

    A loose normal.apk conveys no authority. The run child UUID binds this journal,
    its exact target and one consumed destructive consent scope. Callers hold OwnedRun.
    """
    def __init__(self, owner: OwnedRun, *, create: bool = False) -> None:
        self.owner = owner
        child = owner.record["children"].get("apk_session")
        if child is None:
            if not create:
                raise SessionError("error_run_state", "missing APK journal")
            child = str(uuid.uuid4())
            owner.update(children={**owner.record["children"], "apk_session": child})
        self.directory = owner.root / "sessions" / child
        if create:
            self.directory.mkdir(parents=True, exist_ok=True)
        exact_root(self.directory)
        self.path = self.directory / "apk-journal.json"
        if not self.path.exists() and create:
            self.save({"schema": 1, "run_id": owner.run_id, "target": owner.target,
                       "apks": {}, "installs": {}, "setup": None})
        self.record = self.load()

    def load(self) -> dict:
        value = _read(self.path)
        if (set(value) != {"schema", "run_id", "target", "apks", "installs", "setup"}
                or type(value["schema"]) is not int or value["schema"] != 1
                or value["run_id"] != self.owner.run_id or value["target"] != self.owner.target
                or not isinstance(value["apks"], dict) or set(value["apks"]) - {"source", "normal", "access"}
                or not isinstance(value["installs"], dict) or len(value["installs"]) > 32):
            raise SessionError("error_run_state", self.path)
        for identity in value["apks"].values():
            validate_apk_identity(identity)
        if "access" in value["apks"] and ("normal" not in value["apks"] or not value["apks"]["access"]["debuggable"]):
            raise SessionError("error_run_state", "access APK without normal recovery")
        if "normal" in value["apks"] and value["apks"]["normal"]["debuggable"]:
            raise SessionError("error_run_state", "normal APK is debuggable")
        for key, item in value["installs"].items():
            if (not isinstance(key, str) or not isinstance(item, dict)
                    or set(item) != {"role", "expected", "outcome"}
                    or item["role"] not in {"normal", "access"}
                    or item["expected"] != value["apks"].get(item["role"])
                    or item["outcome"] not in {"intent", "verified", "attention"}):
                raise SessionError("error_run_state", "APK install intent")
        setup = value["setup"]
        if setup is not None:
            approval = (self.owner.record["consents"].get(setup.get("consent"))
                        if isinstance(setup, dict) and isinstance(setup.get("consent"), str) else None)
            if (not isinstance(setup, dict) or set(setup) != {"consent", "source", "normal", "consequence", "phase"}
                    or not {"source", "normal"} <= set(value["apks"])
                    or not _uuid(setup["consent"]) or setup["source"] != value["apks"].get("source")
                    or setup["normal"] != value["apks"].get("normal")
                    or setup["consequence"] != "delete_local_game_data_scan_login"
                    or setup["phase"] not in {"prepared", "uninstall_intent", "install_intent", "waiting_update", "ready"}
                    or not isinstance(approval, dict)
                    or set(approval) != {"id", "source", "normal", "consequence", "approved_at", "plan_digest", "consumed"}
                    or approval["id"] != setup["consent"]
                    or approval["source"] != setup["source"] or approval["normal"] != setup["normal"]
                    or approval["consequence"] != setup["consequence"]
                    or approval["plan_digest"] != identity_key({"source": setup["source"], "normal": setup["normal"],
                                                                "consequence": setup["consequence"]})
                    or approval["consumed"] not in {"approved", "uninstall_intent", "normal_verified"}):
                raise SessionError("error_run_state", "first setup consent")
            try:
                if datetime.fromisoformat(approval["approved_at"]).tzinfo is None:
                    raise ValueError("missing approval timezone")
            except (ValueError, TypeError) as error:
                raise SessionError("error_run_state", "approval timestamp") from error
            if setup["phase"] != "prepared":
                attempt = self.owner.record["retry"].get("uninstall_" + setup["consent"])
                if (approval["consumed"] == "approved" or attempt is None or attempt["attempts"] != 1):
                    raise SessionError("error_run_state", "missing consumed uninstall scope")
        return value

    def save(self, value: dict) -> None:
        _write(self.path, value)
        self.record = self.load()

    def update(self, **changes: object) -> None:
        current = self.load()
        if "apks" in changes:
            for role, identity in changes["apks"].items():
                validate_apk_identity(identity)
                if role in current["apks"] and current["apks"][role] != identity:
                    raise SessionError("error_run_state", "immutable APK identity changed")
                sync_file(self.apk(role))
        self.save({**current, **changes})

    def apk(self, role: str) -> Path:
        if role not in {"source", "normal", "access"}:
            raise SessionError("error_run_state", role)
        path = self.directory / (role + ".apk")
        exact_root(path.parent)
        try:
            info = path.lstat()
        except FileNotFoundError:
            return path
        if (stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or getattr(info, "st_file_attributes", 0) & 0x400):
            raise SessionError("error_run_state", path)
        return path


def exact_root(path: Path) -> Path:
    """Require absolute canonical spelling and reject linked/reparse ancestors."""
    if not path.is_absolute() or ".." in path.parts or path != path.absolute():
        raise SessionError("error_run_state", path)
    for part in (*reversed(path.parents), path):
        if part.exists() or part.is_symlink():
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise SessionError("error_run_state", part)
    if path.exists() and not path.is_dir():
        raise SessionError("error_run_state", path)
    if path.resolve() != path:
        raise SessionError("error_run_state", path)
    return path


def _read(path: Path) -> dict:
    try:
        if path.stat().st_size > MAX_RECORD:
            raise ValueError("record too large")
        return read_record(path)
    except (OSError, ValueError) as error:
        raise SessionError("error_run_state", f"{path}: {error}") from error


def _write(path: Path, value: dict) -> None:
    try:
        exact_root(path.parent)
        if path.exists():
            _read(path)
        data = canonical_bytes(value)
        if len(data) > MAX_RECORD:
            raise ValueError("record too large")
        temp = path.with_name(path.name + "." + str(uuid.uuid4()) + ".tmp")
        with temp.open("xb") as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        _replace(temp, path)
        if _read(path) != value:
            raise ValueError("journal read-back mismatch")
    except (OSError, ValueError) as error:
        raise SessionError("error_run_state", f"{path}: {error}") from error


class FileLock:
    """Nonblocking OS ownership, with Windows inheritable exclusive-share handle."""
    def __init__(self, path: Path, owner: dict) -> None:
        exact_root(path.parent)
        if path.exists() and (path.is_symlink() or path.stat().st_nlink != 1
                            or getattr(path.lstat(), "st_file_attributes", 0) & 0x400):
            raise SessionError("error_run_state", path)
        self.path, self.handle, self.stream = path, None, None
        try:
            if os.name == "nt":
                import ctypes
                from ctypes import wintypes
                kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                create = kernel.CreateFileW
                create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                   ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
                create.restype = wintypes.HANDLE
                handle = create(str(path), 0xC0000000, 0, None, 4, 0x80, None)
                if handle == wintypes.HANDLE(-1).value:
                    raise ctypes.WinError(ctypes.get_last_error())
                self.handle = handle
                os.set_handle_inheritable(handle, True)
                import msvcrt
                # fd owns the handle; close only once through the stream.
                self.stream = os.fdopen(msvcrt.open_osfhandle(handle, os.O_RDWR | os.O_BINARY), "r+b")
            else:
                import fcntl
                self.stream = path.open("a+b")
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.stream.seek(0); self.stream.truncate()
            self.stream.write(canonical_bytes(owner)); self.stream.flush(); os.fsync(self.stream.fileno())
        except OSError as error:
            self.close()
            raise SessionError("error_run_busy", path) from error

    def close(self) -> None:
        if self.stream is not None:
            self.stream.close(); self.stream = None
        elif self.handle is not None and os.name == "nt":
            import ctypes
            close = ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle
            close.argtypes = [ctypes.c_void_p]
            close(self.handle)
        self.handle = None

    def __enter__(self) -> FileLock:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _uuid(value: object) -> bool:
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value
    except ValueError:
        return False


def validate(record: dict, root: Path) -> dict:
    fields = {"schema", "run_id", "action", "language", "provider", "target", "work_root",
              "authorized_at", "authorization_source", "lifecycle", "continuation", "stop_requested",
              "close_preserves_continuation", "children", "retry", "consents", "revision"}
    if (set(record) != fields or type(record["schema"]) is not int or record["schema"] != SCHEMA
            or not _uuid(record["run_id"]) or record["work_root"] != str(root)
            or record["action"] not in {"translate", "remove", "first_setup", "redownload"}
            or record["language"] not in {"en", "id"} or record["provider"] != "adb"
            or record["lifecycle"] not in LIFECYCLES
            or record["authorization_source"] != "explicit_start"
            or not isinstance(record["authorized_at"], str)):
        raise SessionError("error_run_state", root)
    try:
        moment = datetime.fromisoformat(record["authorized_at"])
        if moment.tzinfo is None:
            raise ValueError("missing timezone")
    except ValueError as error:
        raise SessionError("error_run_state", root) from error
    target = record["target"]
    if (not isinstance(target, dict) or set(target) != {"serial", "android_user", "package"}
            or not isinstance(target["serial"], str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,256}", target["serial"])
            or type(target["android_user"]) is not int or target["android_user"] < 0
            or target["package"] != PACKAGE):
        raise SessionError("error_run_state", "target")
    for key in ("continuation", "stop_requested", "close_preserves_continuation"):
        if type(record[key]) is not bool:
            raise SessionError("error_run_state", key)
    if record["stop_requested"] and record["continuation"]:
        raise SessionError("error_run_state", "Stop contradicts continuation")
    if type(record["revision"]) is not int or record["revision"] < 0:
        raise SessionError("error_run_state", "revision")
    if (not isinstance(record["children"], dict) or len(record["children"]) > 64
            or any(not isinstance(k, str) or not _uuid(v) for k, v in record["children"].items())
            or not isinstance(record["consents"], dict) or len(record["consents"]) > 64
            or not isinstance(record["retry"], dict) or len(record["retry"]) > 256):
        raise SessionError("error_run_state", "children/consents/retry")
    for key, retry in record["retry"].items():
        if (not isinstance(key, str) or not 1 <= len(key) <= 256 or not isinstance(retry, dict)
                or set(retry) != {"attempts", "failures", "last_failure", "exhausted", "waiting", "completed"}
                or type(retry["attempts"]) is not int or not 0 <= retry["attempts"] <= 2
                or type(retry["failures"]) is not int or not 0 <= retry["failures"] <= retry["attempts"]
                or type(retry["exhausted"]) is not bool
                or type(retry["completed"]) is not bool
                or retry["completed"] and retry["attempts"] == 0
                or retry["exhausted"] != (retry["attempts"] >= 2)
                or any(v is not None and not isinstance(v, str) for v in (retry["last_failure"], retry["waiting"]))):
            raise SessionError("error_run_state", "retry")
    canonical_bytes(record)
    return record


class RunStore:
    """Registry is mandatory dispatch evidence; settings.json remains independent."""
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = exact_root(state_dir)
        self.registry = state_dir / "unfinished-runs.json"

    def _registry(self) -> dict:
        if not self.registry.exists():
            return {"schema": SCHEMA, "roots": []}
        data = _read(self.registry)
        if (set(data) != {"schema", "roots"} or type(data["schema"]) is not int or data["schema"] != SCHEMA
                or not isinstance(data["roots"], list) or len(data["roots"]) > MAX_ROOTS):
            raise SessionError("error_run_state", self.registry)
        seen = set()
        for item in data["roots"]:
            if (not isinstance(item, dict) or set(item) != {"root", "run_id"}
                    or not isinstance(item["root"], str) or not _uuid(item["run_id"])):
                raise SessionError("error_run_state", self.registry)
            root = exact_root(Path(item["root"]))
            key = os.path.normcase(str(root))
            if key in seen:
                raise SessionError("error_run_ambiguous", self.registry)
            seen.add(key)
        return data

    def _registry_lock(self) -> FileLock:
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            return FileLock(self.state_dir / "registry.lock", {"pid": os.getpid()})
        except OSError as error:
            raise SessionError("error_run_state", self.state_dir) from error

    def load(self, root: Path) -> dict:
        root = exact_root(root)
        if not root.is_dir():
            raise SessionError("error_run_missing", root)
        try:
            return validate(_read(root / "sessions" / "run-intent.json"), root)
        except (TypeError, KeyError, AttributeError, ArtifactError) as error:
            raise SessionError("error_run_state", root) from error

    def discover(self, selected_root: Path | None = None) -> list[dict]:
        """Find pending setup before game/space checks; unknown/missing roots block."""
        with self._registry_lock():
            index = self._registry()
            roots = {str(exact_root(selected_root))} if selected_root is not None else set()
            roots.update(item["root"] for item in index["roots"])
            indexed = {item["root"]: item["run_id"] for item in index["roots"]}
            candidates = []
            devices = set()
            for name in sorted(roots):
                root = Path(name)
                intent = root / "sessions" / "run-intent.json"
                if name in indexed or intent.exists():
                    record = self.load(root)
                    if name in indexed and indexed[name] != record["run_id"]:
                        raise SessionError("error_run_ambiguous", root)
                    if record["lifecycle"] not in RESOLVED:
                        device = record["target"]["serial"]
                        if device in devices:
                            raise SessionError("error_run_ambiguous", device)
                        devices.add(device)
                        candidates.append({"kind": "authorized", "root": name, "record": record,
                                           "plan": next_action(record)})
                if root.exists():
                    for pending in sorted((root / "sessions").glob("*/delta.pending.bin")):
                        exact_root(pending.parent)
                        if pending.is_symlink() or getattr(pending.lstat(), "st_file_attributes", 0) & 0x400:
                            raise SessionError("error_run_state", pending)
                        own = next((candidate for candidate in candidates
                                    if candidate["kind"] == "authorized" and candidate["root"] == name
                                    and pending.parent.name in candidate["record"]["children"].values()), None)
                        if own is not None:
                            own.setdefault("pending_sessions", []).append(str(pending.parent))
                            continue  # Correlated mutation material still requires journal reconciliation.
                        candidates.append({"kind": "legacy_safety", "root": name,
                                           "session": str(pending.parent), "plan": "safety_attention"})
            if len(candidates) > 1:
                raise SessionError("error_run_ambiguous", "multiple unresolved actions")
            return candidates

    def claim(self, root: Path, target: dict, *, run_id: str | None = None) -> OwnedRun:
        return OwnedRun(self, root, target, run_id=run_id)


def next_action(record: dict) -> str:
    """A plan is a coordinator hint, never permission or proof for mutation."""
    if record["lifecycle"] in RESOLVED:
        return "resolved"
    if record["stop_requested"] or not record["continuation"]:
        return "restore_then_cancel"
    if record["lifecycle"] == "attention":
        return "attention"
    if any(item["exhausted"] and not item["completed"] for item in record["retry"].values()):
        return "retry_required"
    if record["lifecycle"] == "waiting":
        return "wait"
    if record["action"] in {"first_setup", "redownload"}:
        return "reconcile_setup"
    return {"authorized": "prepare", "preparing": "reconcile_preparation", "snapshot": "verify_snapshot",
            "building": "restart_build", "staged": "verify_stage", "applying": "reconcile_files",
            "payload_verified": "restore_normal", "normal_verified": "finalize"}[record["lifecycle"]]


def _serialized(method):
    """Serialize complete owner read/modify/write operations, including control requests."""
    @wraps(method)
    def call(self, *args, **kwargs):
        with self._mutex:
            return method(self, *args, **kwargs)
    return call


class OwnedRun:
    """Hold across all worker mutations. Release only after its ADB child has exited."""
    def __init__(self, store: RunStore, root: Path, target: dict, *, run_id: str | None) -> None:
        self._mutex = threading.RLock()
        self.store, self.root = store, exact_root(root)
        if not root.is_dir():
            raise SessionError("error_run_missing", root)
        self.target, self.run_id = copy.deepcopy(target), run_id or str(uuid.uuid4())
        # Validate target before it can name or acquire an ownership record.
        validate(self._new("translate", "en"), self.root)
        self.locks: list[FileLock] = []
        try:
            store.state_dir.mkdir(parents=True, exist_ok=True)
            owner = {"pid": os.getpid(), "run_id": self.run_id, "target": target}
            self.locks.append(FileLock(root / ".patch-owner.lock", owner))
            device_key = hashlib.sha256(target["serial"].encode()).hexdigest()
            self.locks.append(FileLock(store.state_dir / f"device-{device_key}.lock", owner))
            if run_id is not None:
                self.record = store.load(root)
                if self.record["run_id"] != run_id or self.record["target"] != target:
                    raise SessionError("error_run_target", target)
                self._index()
            else:
                self.record = None
        except BaseException:
            self.close(); raise

    def _new(self, action: str, language: str) -> dict:
        return {"schema": SCHEMA, "run_id": self.run_id, "action": action, "language": language,
                "provider": "adb", "target": self.target, "work_root": str(self.root),
                "authorized_at": datetime.now(timezone.utc).isoformat(), "authorization_source": "explicit_start",
                "lifecycle": "authorized", "continuation": True, "stop_requested": False,
                "close_preserves_continuation": False, "children": {}, "retry": {}, "consents": {}, "revision": 0}

    def _index(self) -> None:
        with self.store._registry_lock():
            index = self.store._registry()
            others = [item for item in index["roots"] if item["root"] != str(self.root)]
            for item in others:
                other = self.store.load(Path(item["root"]))
                if other["lifecycle"] not in RESOLVED and other["target"]["serial"] == self.target["serial"]:
                    raise SessionError("error_run_ambiguous", self.target["serial"])
            same = [item for item in index["roots"] if item["root"] == str(self.root)]
            if same and same[0]["run_id"] != self.run_id:
                prior = self.store.load(self.root)
                if prior["lifecycle"] not in RESOLVED:
                    raise SessionError("error_run_ambiguous", self.root)
            index["roots"] = others + [{"root": str(self.root), "run_id": self.run_id}]
            if len(index["roots"]) > MAX_ROOTS:
                raise SessionError("error_run_state", "registry full")
            _write(self.store.registry, index)

    @_serialized
    def authorize(self, action: str, language: str) -> dict:
        if self.record is not None:
            raise SessionError("error_run_state", "already authorized")
        path = self.root / "sessions" / "run-intent.json"
        if path.exists() and self.store.load(self.root)["lifecycle"] not in RESOLVED:
            raise SessionError("error_run_ambiguous", self.root)
        record = validate(self._new(action, language), self.root)
        # Index first: a crash before intent publication leaves a blocking missing record.
        self._index()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            _sync_directory(self.root)
        except OSError as error:
            raise SessionError("error_run_state", path.parent) from error
        _write(path, record)
        self.record = record
        return copy.deepcopy(record)

    @_serialized
    def update(self, **changes: object) -> dict:
        if not self.locks or self.record is None:
            raise SessionError("error_run_state", "ownership/authorization required")
        if set(changes) - {"lifecycle", "continuation", "stop_requested", "close_preserves_continuation",
                           "children", "retry", "consents"}:
            raise SessionError("error_run_target", "immutable intent")
        current = self.store.load(self.root)
        if current != self.record:
            raise SessionError("error_run_state", "journal changed outside owner")
        proposed = copy.deepcopy(current)
        proposed.update(changes)
        before, after = current["lifecycle"], proposed["lifecycle"]
        if after != before and (before in RESOLVED or after not in TRANSITIONS.get(before, set()) | {"waiting", "attention"}):
            raise SessionError("error_run_state", f"invalid transition {before}/{after}")
        if current["stop_requested"] and (not proposed["stop_requested"] or proposed["continuation"]):
            raise SessionError("error_run_state", "Stop cannot be revoked")
        proposed["revision"] += 1
        validate(proposed, self.root)
        _write(self.root / "sessions" / "run-intent.json", proposed)
        self.record = proposed
        return copy.deepcopy(proposed)

    @_serialized
    def stop(self) -> dict:
        return self.update(continuation=False, stop_requested=True)

    @_serialized
    def preserve_close(self) -> dict:
        return self.update(close_preserves_continuation=True)

    @_serialized
    def begin_attempt(self, key: str, *, destructive: bool = False, safety_recovery: bool = False) -> int:
        if (getattr(self, "dispatch_read_only", False) and not safety_recovery
                and not key.startswith("control_reconcile_")):
            raise SessionError("error_run_retry", "Reconciliation budget exhausted; Retry required")
        # Safety repair is explicit caller proof from a verified mutation journal,
        # never fresh patch authorization and never permission to uninstall.
        prohibited = {"resolved"} if safety_recovery and not destructive else {"resolved", "restore_then_cancel", "attention"}
        if self.record is None or next_action(self.record) in prohibited:
            raise SessionError("error_run_state", "dispatch prohibited")
        retry = copy.deepcopy(self.record["retry"])
        item = retry.setdefault(key, {"attempts": 0, "failures": 0, "last_failure": None,
                                      "exhausted": False, "waiting": None, "completed": False})
        if item["completed"] or item["attempts"] >= (1 if destructive else 2):
            raise SessionError("error_run_retry", key)
        item["attempts"] += 1
        item["exhausted"], item["waiting"] = item["attempts"] >= 2, None
        self.update(retry=retry)
        return item["attempts"]

    @_serialized
    def record_failure(self, key: str, failure: str) -> None:
        retry = copy.deepcopy(self.record["retry"])
        item = retry[key]
        item["failures"] = min(item["attempts"], item["failures"] + 1)
        item["last_failure"] = failure
        self.update(retry=retry)

    @_serialized
    def complete_attempt(self, key: str, *, reconciled_success: bool) -> None:
        """Call only after consumer-boundary outcome verification; retain used budget."""
        if not reconciled_success:
            raise SessionError("error_run_state", "success requires reconciliation")
        retry = copy.deepcopy(self.record["retry"])
        retry[key]["completed"] = True
        retry[key]["waiting"] = None
        self.update(retry=retry)

    @_serialized
    def invalidate_checkpoint(self, key: str, *, retained_proof_invalid: bool) -> None:
        """Allow the remaining attempt after retained output failed verification.

        Unlike explicit Retry/rearm this preserves every used attempt and failure.
        Caller has already reconciled mutation journals and rejected the receipt.
        """
        if not retained_proof_invalid or self.record["stop_requested"]:
            raise SessionError("error_run_retry", key)
        retry = copy.deepcopy(self.record["retry"])
        item = retry.get(key)
        if item is not None and item["completed"]:
            item["completed"] = False
            item["last_failure"] = "retained_checkpoint_invalid"
            self.update(retry=retry)

    @_serialized
    def wait(self, key: str, reason: str) -> None:
        retry = copy.deepcopy(self.record["retry"])
        item = retry.setdefault(key, {"attempts": 0, "failures": 0, "last_failure": None,
                                      "exhausted": False, "waiting": None, "completed": False})
        item["waiting"] = reason
        self.update(retry=retry, lifecycle="waiting")

    @_serialized
    def rearm(self, key: str, *, safe_idempotent: bool, explicit_retry: bool,
              safety_recovery: bool = False) -> None:
        if (not safe_idempotent or not explicit_retry
                or self.record["stop_requested"] and not safety_recovery):
            raise SessionError("error_run_retry", key)
        retry = copy.deepcopy(self.record["retry"])
        retry.pop(key, None)
        self.update(retry=retry)

    @_serialized
    def subprocess_options(self) -> dict:
        if os.name != "nt":
            return {"pass_fds": tuple(lock.stream.fileno() for lock in self.locks)}
        import subprocess
        startup = subprocess.STARTUPINFO()
        startup.lpAttributeList = {"handle_list": [lock.handle for lock in self.locks]}
        return {"startupinfo": startup, "close_fds": True}

    @_serialized
    def close(self) -> None:
        for lock in reversed(self.locks):
            lock.close()
        self.locks.clear()

    def __enter__(self) -> OwnedRun:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
