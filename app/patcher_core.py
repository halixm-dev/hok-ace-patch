"""Patch workflow: device detection, temporary data-access APK, translation build and install."""
from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import subprocess
import threading
import sys
import tarfile
import time
import zipfile
import uuid
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

PACKAGE = "com.tencent.tmgp.osgame"
REMOTE_TMP = "/data/local/tmp/hokace"
MIN_FREE_BYTES = 8 * 1024**3
NO_WINDOW = 0x08000000 if os.name == "nt" else 0
# The name the game is listed under once patched. Writing it is cosmetic, so a manifest this cannot
# be written into is logged and the run continues.
APP_NAME = "Honor of Kings: ACE"

PROJECT = Path(__file__).resolve().parents[1]
BUNDLE = Path(getattr(sys, "_MEIPASS", PROJECT / "resources"))
if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(PROJECT / "tools"))  # the exe gets these via PyInstaller --paths
# Only the chosen working folder and language are remembered here (a few bytes); the ~8 GB of game
# data goes to whatever folder the user picks.
SETTINGS = Path(os.environ.get("APPDATA", Path.home())) / "HOKAceEnglishPatcher" / "settings.json"

# Translation runtime (compiled wxq_patch modules) ships as data; append so our stdlib wins.
sys.path.append(str(BUNDLE / "runtime"))

import apk_tools  # noqa: E402
import languages  # noqa: E402
import pristine_delta  # noqa: E402
from axml_label import set_label  # noqa: E402
from axml_set_debuggable import is_debuggable, patch as make_debuggable_manifest  # noqa: E402
from qts_builder import find_builder_dir  # noqa: E402
from patch_summary import count_translated, count_untranslated_graphics, count_untranslated_text  # noqa: E402
from patch_session import RunStore, SessionError, OwnedRun, ApkJournal, Operation, RESOLVED  # noqa: E402
from run_artifacts import (ArtifactError, identity_key, tree_manifest, file_identity, read_record,
                           verify_manifest, windows_producer_identity)  # noqa: E402
from device_transaction import DeviceTransaction, ShellTransport, _publish, _durable_copy
from windows_checkpoints import Checkpoints, PreparedApks, owned_attempt, active_delta_identity, reuse_completed  # noqa: E402

# The session's copy of the override layer, where build_patch reads it.
LAYER = Path("game") / "WXQ_Data" / "Package" / "builtin"
# The delta of an install being written; it becomes the delta once the last write succeeds.
PENDING_DELTA = "delta.pending.bin"
# In the working folder: the pristine delta and the staged-hash record; never pruned.
KEEP_DIR = "pristine"
# Written into a session once its layer copy matches the phone; a later run copies unchanged files from it.
PULL_RECORD = "pull.json"
# Phone paths a partial pull accepts; anything else falls back to the full pull. Also keeps them shell-safe.
LAYER_NAME = re.compile(r"[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*")
# Characters of file names per `tar` command, well under adb's command length on old devices.
PULL_BATCH_CHARS = 3000
PLAY_PROTECT_HINT = "If Google Play Protect shows a pop-up on the phone, tap 'More details' -> 'Install anyway'."

# (key, label) in display order. The label names the step in the log; the UI shows the shared string
# `step_<key>` in the interface language.
STEPS = [
    ("device", "Connect phone"),
    ("apk", "Prepare game APK"),
    ("access", "Unlock data access"),
    ("pull", "Read language data"),
    ("translate", "Build translation"),
    ("install", "Install translation"),
    ("restore", "Restore game"),
]


UI_STRINGS = json.loads((BUNDLE / "ui" / "strings.json").read_text(encoding="utf-8"))["strings"]
# The language choice in ① also sets the interface language (DESIGN.md, Wording and language).
_interface_language = languages.DEFAULT_LANGUAGE


def set_interface_language(code: str) -> None:
    global _interface_language
    _interface_language = languages.get(code).code


def _render(key: str, language: str, values: dict[str, object]) -> str:
    text = UI_STRINGS[key][language]
    for name, value in values.items():
        text = text.replace("{" + name + "}", str(value))
    return text


def ui_text(key: str, **values: object) -> str:
    """The shared interface string <key> (resources/ui/strings.json) in the interface language."""
    return _render(key, _interface_language, values)


def build_patch(*args: object, **kwargs: object) -> dict:
    """Load the translation engine only for a fresh staging operation."""
    from build_device_patch import build_patch as build
    return build(*args, **kwargs)


class PatchError(Exception):
    """Expected failure meant for the user: shared strings <keys>, joined by blank lines.

    ``str()`` is the English text, for the log, which stays raw; ``shown()`` is the interface language.
    """

    def __init__(self, *keys: str, **values: object) -> None:
        self.keys, self.values = keys, values
        super().__init__(self._text("en"))

    def _text(self, language: str) -> str:
        return "\n\n".join(_render(key, language, self.values) for key in self.keys)

    def shown(self) -> str:
        return self._text(_interface_language)


def _session_error(error: SessionError) -> PatchError:
    """Keep the shared-string keys explicit at the user-facing boundary."""
    match error.key:
        case "error_run_busy":
            return PatchError("error_run_busy", detail=error.detail)
        case "error_run_missing":
            return PatchError("error_run_missing", detail=error.detail)
        case "error_run_ambiguous":
            return PatchError("error_run_ambiguous", detail=error.detail)
        case "error_run_target":
            return PatchError("error_run_target", detail=error.detail)
        case "error_run_retry":
            return PatchError("error_run_retry", detail=error.detail)
        case _:
            return PatchError("error_run_state", detail=error.detail)


def default_work_dir() -> Path:
    """Folder next to the exe, so the data lands on whatever drive the user put the patcher on."""
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    return base / "HOK ACE Patcher Data"


def _load_settings() -> dict:
    try:
        settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return settings if isinstance(settings, dict) else {}


def _save_settings(**changes) -> None:
    try:
        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS.write_text(json.dumps({**_load_settings(), **changes}), encoding="utf-8")
    except OSError:
        pass  # the choice still applies for this session


def load_work_dir() -> Path:
    try:
        return Path(_load_settings()["work_dir"])
    except (KeyError, TypeError):
        return default_work_dir()


def save_work_dir(path: Path) -> None:
    _save_settings(work_dir=str(path))


def load_language() -> str:
    code = _load_settings().get("language")
    return code if code in languages.LANGUAGES else languages.DEFAULT_LANGUAGE


def save_language(code: str) -> None:
    _save_settings(language=languages.get(code).code)


# `Patcher.run`'s summary key when a recovery-only run found no saved record left to resume.
NOTHING_TO_RECOVER = "nothing_to_recover"


def run_store() -> RunStore:
    """Durable registry shares the settings directory, never its best-effort writer."""
    try:
        return RunStore(SETTINGS.parent)
    except SessionError as error:
        raise _session_error(error) from error


def discover_pending_runs(work: Path | None = None) -> list[dict]:
    """Read before fresh space/game checks. No phone command or automatic dispatch."""
    try:
        return run_store().discover(work)
    except SessionError as error:
        raise _session_error(error) from error


def free_space(path: Path) -> int | None:
    """Free bytes on the drive holding <path> (or its nearest existing parent)."""
    probe = path
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    try:
        return shutil.disk_usage(probe).free
    except OSError:
        return None


def check_work_dir(path: Path) -> None:
    """Raise PatchError unless <path> is writable and has room for the game data."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-test"
        probe.write_bytes(b"ok")
        probe.unlink()
    except OSError as error:
        raise PatchError("error_work_dir_unusable", path=path, error=error) from error
    free = shutil.disk_usage(path).free
    if free < MIN_FREE_BYTES:
        raise PatchError("error_work_dir_full", path=path, free=f"{free / 1024**3:.1f}")


def parse_device_hashes(output: str) -> dict[str, str] | None:
    """`sha256sum` output run in the phone's `packages/`, as {`<package id>/<file>`: SHA-256}.

    None when any line is not a plain digest and layer path, so the caller falls back to the full pull.
    """
    hashes: dict[str, str] = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        digest, _, name = line.partition("  ")
        name = name.removeprefix("./")
        if (len(digest) != 64 or digest.strip("0123456789abcdef") or not LAYER_NAME.fullmatch(name)
                or {".", ".."} & set(name.split("/")) or name in hashes):
            return None
        hashes[name] = digest
    return hashes or None


def reusable_files(device: dict[str, str], sources: list[Path]) -> tuple[dict[str, Path], list[str]]:
    """Split <device> into the files some <sources> folder holds at the same SHA-256, and the rest."""
    found: dict[str, Path] = {}
    missing = []
    for name, digest in sorted(device.items()):
        for source in sources:
            path = source / name
            if path.is_file() and pristine_delta.sha256_file(path) == digest:
                found[name] = path
                break
        else:
            missing.append(name)
    return found, missing


def holds_delta(work: Path) -> bool:
    """Whether <work> keeps a pristine delta, so a translated phone can be repatched without a clear."""
    return (work / KEEP_DIR / pristine_delta.DELTA_NAME).is_file()


def apk_manifest(apk: Path) -> bytes:
    """The APK's binary AndroidManifest.xml."""
    with zipfile.ZipFile(apk) as archive:
        return archive.read("AndroidManifest.xml")


class Ui(Protocol):
    def log(self, line: str) -> None: ...
    def set_step(self, key: str, state: str, detail: str = "") -> None: ...
    def set_device(self, text: str, connected: bool) -> None: ...
    def ask(self, title: str, message: str, danger: bool = True) -> bool: ...
    def wait_user(self, title: str, message: str) -> None: ...


class Adb:
    def __init__(self, work: Path, *, serial: str | None = None, android_user: int | None = None,
                 owner: OwnedRun | None = None) -> None:
        self.serial, self.android_user, self.owner = serial, android_user, owner
        self.boundary = None
        self.progress = None
        target = work / "adb"
        target.mkdir(parents=True, exist_ok=True)
        # Run adb from a persistent folder so its background server never locks the PyInstaller temp dir.
        for item in (BUNDLE / "adb").iterdir():
            if not (target / item.name).exists() or (target / item.name).stat().st_size != item.stat().st_size:
                shutil.copy2(item, target / item.name)
        self.exe = str(target / "adb.exe")

    def bind(self, serial: str, android_user: int | None = None) -> None:
        if (not re.fullmatch(r"[A-Za-z0-9_.:-]{1,256}", serial)
                or self.serial is not None and self.serial != serial
                or self.android_user is not None and android_user is not None and self.android_user != android_user):
            raise PatchError("error_run_target", detail=serial)
        self.serial = serial
        if android_user is not None:
            self.android_user = android_user

    def _argv(self, args: tuple[str, ...]) -> list[str]:
        if args and args[0] in {"start-server", "devices"} and len(args) == 1:
            return [self.exe, *args]
        if not self.serial or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,256}", self.serial):
            raise PatchError("error_run_target", detail="Select the saved phone first")
        if not args or args[0] not in {"shell", "exec-out", "pull", "push", "install", "uninstall",
                                         "reconnect", "get-state", "get-serialno", "wait-for-device"}:
            raise PatchError("error_run_target", detail="Unsafe ADB target override")
        return [self.exe, "-s", self.serial, *args]

    def _process_options(self) -> dict:
        return self.owner.subprocess_options() if self.owner is not None else {}

    def assert_target(self) -> int:
        """Refuse Android-user switching before any device mutation."""
        value = self.shell("am get-current-user").strip()
        if not value.isdecimal():
            raise PatchError("error_run_target", detail="Cannot verify Android user")
        user = int(value)
        if self.android_user is not None and user != self.android_user:
            raise PatchError("error_run_target", detail=f"Android user {user}")
        self.android_user = user
        # run-as and the shared package paths used here target Android's owner user.
        if user != 0:
            raise PatchError("error_run_target", detail="Use the phone's owner profile (user 0)")
        return user

    def run(self, *args: str, check: bool = True) -> str:
        if self.boundary is not None:
            self.boundary()
        if args and args[0] in {"push", "install", "uninstall", "reconnect"}:
            self.assert_target()
        result = subprocess.run(self._argv(args), capture_output=True, text=True, encoding="utf-8",
                                errors="replace", creationflags=NO_WINDOW, timeout=180, **self._process_options())
        output = (result.stdout + result.stderr).strip()
        if check and result.returncode != 0:
            raise PatchError("error_adb_failed", command=" ".join(args), output=output)
        return output

    def shell(self, command: str, check: bool = True) -> str:
        if command != "am get-current-user":
            self.assert_target()
        return self.run("shell", command, check=check)

    def exec_out(self, command: str) -> str:
        self.assert_target()
        return self.run("exec-out", command)

    def exec_out_to_file(self, command: str, target: Path) -> None:
        if self.boundary is not None:
            self.boundary()
        self.assert_target()
        with target.open("wb") as out:
            result = subprocess.run(self._argv(("exec-out", command)), stdout=out, stderr=subprocess.PIPE,
                                    creationflags=NO_WINDOW, timeout=180, **self._process_options())
        if self.progress is not None:
            self.progress(target.stat().st_size)
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace")
            raise PatchError("error_read_failed", output=stderr)

    def installed_identity(self) -> dict | None:
        """Independently read installed bytes, with path/hash stability across the pull."""
        self.assert_target()
        listed = self.shell(f"pm list packages --user 0 {PACKAGE}").strip()
        if listed == "":
            return None
        if listed != f"package:{PACKAGE}":
            raise PatchError("error_apk_identity", detail="Package enumeration is ambiguous")
        path_output = self.shell(f"pm path {PACKAGE}").strip()
        match = re.fullmatch(r"package:(/data/app/[A-Za-z0-9_./=+~-]+\.apk)", path_output)
        if match is None or ".." in match[1].split("/"):
            raise PatchError("error_apk_identity", detail="Cannot verify a single installed APK")
        remote = match[1]
        before = self.shell(f"sha256sum '{remote}'").split()
        if len(before) != 2 or not re.fullmatch("[0-9a-f]{64}", before[0]):
            raise PatchError("error_apk_identity", detail="Installed APK hash unavailable")
        with tempfile.TemporaryDirectory(prefix="apk-audit-", dir=Path(self.exe).parent) as temporary:
            local = Path(temporary) / "observed.apk"
            self.run("pull", remote, str(local))
            try:
                identity = apk_tools.apk_identity(local)
            except (OSError, ValueError, KeyError, IndexError, zipfile.BadZipFile) as error:
                raise PatchError("error_apk_identity", detail=error) from error
        after = self.shell(f"sha256sum '{remote}'").split()
        if (before != after or identity["sha256"] != before[0]
                or self.shell(f"pm path {PACKAGE}").strip() != path_output or identity["package"] != PACKAGE):
            raise PatchError("error_apk_identity", detail="Installed APK changed during observation")
        return identity

    def install(self, apk: Path) -> None:
        """Reconcile commit-before-lost-reply; transport Success alone is never proof."""
        self.assert_target()
        try:
            expected = apk_tools.apk_identity(apk)
        except (OSError, ValueError, KeyError, IndexError, zipfile.BadZipFile) as error:
            raise PatchError("error_apk_identity", detail=error) from error
        failure = None
        try:
            output = self.run("install", "-r", str(apk), check=False)
        except (OSError, PatchError) as error:
            failure, output = error, str(error)
        if self.installed_identity() == expected:
            return
        if "INSTALL_FAILED_VERIFICATION_FAILURE" in output:
            raise PatchError("error_play_protect_blocked") from failure
        raise PatchError("error_install_failed", output=output) from failure

    @staticmethod
    def kill_server(work: Path) -> None:
        adb = work / "adb" / "adb.exe"
        if adb.exists():
            subprocess.run([str(adb), "kill-server"], creationflags=NO_WINDOW, capture_output=True)


class Patcher:
    def __init__(self, ui: Ui, work: Path, language: str = languages.DEFAULT_LANGUAGE, *, remove: bool = False, retry: bool = False,
                 recovery_only: bool = False):
        """<remove> writes the pristine bytes back instead of a translation (Remove translation).

        <recovery_only> (the attention state's recovery button) resumes only a saved record; when none
        remains it returns `NOTHING_TO_RECOVER` before any preparation, APK work or game write.
        """
        self.ui = ui
        self.explicit_retry = retry
        self.recovery_only = recovery_only
        self._control_lock = threading.RLock()
        self._interrupt = threading.Event()
        self._stop_requested = False
        self._close_requested = False
        self._recovering = False
        self.work = work
        self.language = languages.get(language)
        self.remove = remove
        self.log = ui.log
        self.adb: Adb | None = None
        self.normal_apk: Path | None = None
        self.debuggable_installed = False
        self.current: str | None = None
        self.data_version = ""
        self.keep = work / KEEP_DIR
        # Files a game update replaced that `restore_pristine` took as the new pristine.
        self.replaced: list[str] = []
        self.run_store = run_store()
        self.pending_candidates: list[dict] = []
        self.run_owner: OwnedRun | None = None
        self.apk_journal: ApkJournal | None = None
        self._prepared_access: Path | None = None
        self.file_transaction: DeviceTransaction | None = None
        self.outcome: dict = {"state": "working", "next_action": "prepare"}
        self._producer: dict | None = None
        self._producer_checked = False
        self._active_build: Path | None = None
        self._restored: list[str] | None = None

    def queue_control(self, *, stop: bool = False, close: bool = False) -> None:
        # Monotonic flags: this UI-thread seam performs no disk IO or owner locking.
        if stop:
            self._stop_requested = True
        if close:
            self._close_requested = True
        self._interrupt.set()

    def request_control(self, *, stop: bool = False, close: bool = False) -> bool:
        """Queue pre-claim controls; acknowledge only a durable owned intent write.

        UI invokes this on a short control thread, never blocking Tk on fsync.
        Stop is irreversible. Close never grants readiness, consent or Stop.
        """
        self.queue_control(stop=stop, close=close)
        with self._control_lock:
            return self._persist_control()

    def _persist_control(self) -> bool:
        owner = self.run_owner
        if owner is None:
            return False
        with owner._mutex:
            if not owner.locks or owner.record is None or owner.record["lifecycle"] in RESOLVED:
                return False
            if self._stop_requested and not owner.record["stop_requested"]:
                owner.stop()
            if self._close_requested and not owner.record["close_preserves_continuation"]:
                owner.preserve_close()
            return True

    def control_boundary(self) -> None:
        if self._recovering:
            return
        with self._control_lock:
            self._persist_control()
            if self._stop_requested:
                raise PatchError("error_cancelled")
            if self._close_requested:
                raise PatchError("error_close_preserved")

    def _bind_control(self) -> None:
        self.adb.boundary = self.control_boundary
        self.adb.progress = lambda size: self.event("working", "read_game_data", bytes_done=size)
        with self._control_lock:
            self._persist_control()

    def _wait_saved_device(self) -> None:
        """Connection waiting spends no mutation attempts and never switches serial."""
        if self.adb.serial is None:
            return
        delay = 1
        while True:
            self.control_boundary()
            rows = [line.split() for line in self.adb.run("devices").splitlines()[1:]]
            if [self.adb.serial, "device"] in rows:
                return
            self.event("waiting", "connect_saved_phone", reason="usb_access")
            self._interrupt.wait(delay)
            delay = min(5, delay + 1)

    def _dispatch(self, fresh: bool = False) -> dict:
        """Retry only eligible transport failures; journal reconciliation always runs first."""
        owner = self.run_owner
        if self.explicit_retry:
            owner.rearm_idempotent()  # Never a destructive setup.
            self.explicit_retry = False
        while True:
            guard = None
            guard_started = False
            try:
                self.control_boundary()
                self._wait_saved_device()
                # A stable guard follows actual logical-operation progress. An unrelated
                # pending build cannot authorize infinite failing identity-read dispatches.
                progress = {key: {field: item[field] for field in ("attempts", "completed")}
                            for key, item in owner.record["retry"].items()
                            if not key.startswith("control_reconcile_")}
                guard = "control_reconcile_" + identity_key(progress)
                prior = owner.record["retry"].get(guard, {})
                owner.dispatch_read_only = bool(prior.get("exhausted") or prior.get("completed"))
                if not owner.dispatch_read_only:
                    owner.begin_attempt(guard, safety_recovery=True)
                    guard_started = True
                # Exhaustion blocks new non-safety sends at OwnedRun.begin_attempt;
                # journal reconciliation/verified completion still get their audit.
                result = self._run_authorized() if fresh else self._continue_authorized()
                if guard_started:
                    owner.complete_attempt(guard, reconciled_success=True)
                return result
            except Exception as error:
                with self._control_lock:
                    self._persist_control()
                self._recovering = True
                recovery_error = None
                try:
                    self._recover_failed_dispatch()
                except Exception as cleanup_error:
                    recovery_error = cleanup_error
                finally:
                    self._recovering = False
                failure = recovery_error or error
                if self._stop_requested or self._close_requested:
                    raise failure
                transient = False
                cause = failure
                seen = set()
                while cause is not None and id(cause) not in seen:
                    seen.add(id(cause))
                    keys = set(cause.keys) if isinstance(cause, PatchError) else set()
                    transient |= bool(keys & {"error_adb_failed", "error_read_failed", "error_install_failed",
                                              "error_normal_recovery"}) or isinstance(cause, subprocess.TimeoutExpired)
                    cause = cause.__cause__
                if guard_started and not owner.record["retry"][guard]["completed"]:
                    owner.record_failure(guard, "transport_reconciliation" if transient else "dispatch_failed")
                if (not transient or guard is None or owner.dispatch_read_only
                        or owner.record["retry"].get(guard, {}).get("exhausted")):
                    raise failure
                self.event("continuing", "reconcile", reason="transient_retry")
                self._interrupt.wait(2)
                fresh = False

    def discover_runs(self) -> list[dict]:
        self.pending_candidates = discover_pending_runs(self.work)
        return self.pending_candidates

    def claim_run(self, target: dict, *, run_id: str | None = None) -> OwnedRun:
        """Coordinator seam; keep ownership until every device child has exited."""
        try:
            self.run_owner = self.run_store.claim(self.work, target, run_id=run_id)
        except SessionError as error:
            raise _session_error(error) from error
        try:
            if self.adb is not None:
                self.adb.bind(target["serial"], target["android_user"])
                self.adb.owner = self.run_owner
        except BaseException:
            self.run_owner.close()
            raise
        return self.run_owner

    def event(self, state: str, next_action: str, **detail: object) -> None:
        """Structured core projection for 07/13; never dispatch authority."""
        self.outcome = {"state": state, "next_action": next_action, **detail}
        callback = getattr(self.ui, "run_event", None)
        if callback is not None:
            callback(dict(self.outcome))

    def producer_identity(self) -> dict | None:
        if not self._producer_checked:
            self._producer = windows_producer_identity(PROJECT)
            self._producer_checked = True
        return self._producer

    def _nothing_to_recover(self) -> dict:
        self.event("nothing_to_recover", "none")
        return {NOTHING_TO_RECOVER: True}

    def run(self) -> dict:
        # Discovery/claim precedes fresh capacity and installed-game checks.
        if not self.discover_runs() and self.recovery_only:
            # The saved record resolved after the screen was drawn: a recovery click never starts fresh.
            return self._nothing_to_recover()
        if self.pending_candidates:
            candidate = self.pending_candidates[0]
            if candidate["kind"] != "authorized":
                raise PatchError("error_run_pending", detail=candidate["root"])
            saved = candidate["record"]
            self.work = Path(candidate["root"])
            self.keep = self.work / KEEP_DIR
            self.language = languages.get(saved["language"])
            self.remove = saved["action"] == "remove"
            self.adb = Adb(self.work, serial=saved["target"]["serial"],
                           android_user=saved["target"]["android_user"])
            with self.claim_run(saved["target"], run_id=saved["run_id"]) as owner:
                if self.recovery_only and owner.record["lifecycle"] in RESOLVED:
                    # Re-read under the owner and device locks: resolved between discovery and claim.
                    return self._nothing_to_recover()
                try:
                    self._bind_control()
                    self.event("continuing", "reconcile", run_id=saved["run_id"])
                    return self._dispatch()
                except Exception as error:
                    if isinstance(error, SessionError):
                        raise _session_error(error) from error
                    raise
        check_work_dir(self.work)
        self.log(f"Working folder: {self.work}")
        self.log("Removing the translation" if self.remove else f"Language: {self.language.name}")
        self.adb = Adb(self.work)
        self._bind_control()
        self.wait_for_device()
        target = {"serial": self.adb.serial, "android_user": self.adb.android_user, "package": PACKAGE}
        with self.claim_run(target) as owner:
            try:
                owner.authorize("remove" if self.remove else "translate", self.language.code)
                self._bind_control()
                owner.update(lifecycle="preparing")
                return self._dispatch(fresh=True)
            except Exception as error:
                if isinstance(error, SessionError):
                    raise _session_error(error) from error
                raise

    def _phase(self, phase: str) -> None:
        """Lifecycle is a projection of independently verified checkpoint progress."""
        owner = self.run_owner
        if owner.record["lifecycle"] != phase:
            owner.update(lifecycle=phase)

    def _session(self) -> Path | None:
        child = self.run_owner.record["children"].get("data_session")
        return self.work / "sessions" / child if child else None

    def _transaction(self) -> DeviceTransaction:
        normal = self.verify_prepared("normal")
        return DeviceTransaction(self.run_owner, ShellTransport(
            self.adb, reserve_bytes=normal.stat().st_size + 512 * 1024**2))

    def _access_plan(self) -> dict | None:
        path = self.apk_journal.directory / "access-plan.json"
        if not path.exists():
            return None
        plan = read_record(path)
        if (set(plan) != {"schema", "run_id", "target", "scope", "cycle", "access", "normal"}
                or plan["schema"] != 1 or plan["run_id"] != self.run_owner.run_id
                or plan["target"] != self.run_owner.target or not re.fullmatch("[0-9a-f]{32}", plan["scope"])
                or type(plan["cycle"]) is not int or not 1 <= plan["cycle"] <= 2
                or plan["access"] != "access_" + plan["scope"] + "_" + str(plan["cycle"])
                or plan["normal"] != "normal_" + plan["scope"] + "_" + str(plan["cycle"])):
            raise PatchError("error_run_state", detail="Invalid saved access cycle")
        return plan

    def _ensure_access(self, operation: str, *, recovery: bool = False) -> None:
        """Persist stable per-operation cycles; safety scopes do not spend work retries."""
        self.normal_apk = self.verify_prepared("normal")
        owner, journal = self.run_owner, self.apk_journal
        expected = journal.record["apks"].get("access")
        observed = self.adb.installed_identity()
        plan = self._access_plan()
        reuse = False
        if plan is not None:
            old = journal.record["installs"].get("apk_" + plan["access"])
            if observed == expected or old is None or old["outcome"] != "verified":
                reuse = True  # Intent/lost-reply retry retains exactly the same scope.
            else:
                if "apk_" + plan["normal"] not in journal.record["installs"]:
                    raise PatchError("error_apk_identity", detail="Access was externally replaced")
                self.install_prepared("normal", plan["normal"], safety_recovery=True)
        if not reuse:
            # Stable operation name includes the persisted file cycle for recovery.
            # Reopen never invents a new scope to bypass exhausted install budgets.
            binding = {"operation": operation if recovery else "ordinary_work",
                       "session": owner.record["children"].get("data_session") if recovery else None,
                       "apk_session": owner.record["children"]["apk_session"]}
            scope = identity_key(binding)[:32]
            cycle = owner.begin_attempt("access_cycles_" + scope, safety_recovery=recovery)
            plan = {"schema": 1, "run_id": owner.run_id, "target": owner.target,
                    "scope": scope, "cycle": cycle, "access": "access_" + scope + "_" + str(cycle),
                    "normal": "normal_" + scope + "_" + str(cycle)}
            _publish(journal.directory / "access-plan.json", plan)
        if expected is None:
            self.prepare_debuggable_apk()
        elif not recovery and self._prepared_access is None:
            try:
                self._prepared_access = PreparedApks(owner, journal, self.producer_identity()).verify(
                    "access", make_debuggable_manifest(apk_manifest(self.normal_apk)))
            except (ArtifactError, OSError, ValueError):
                pass  # Fresh verified generation remains possible; recovery files stay pinned.
        if expected is not None and not recovery and self._prepared_access is None:
            session = self._session() or journal.directory
            key = "regenerate_" + plan["scope"] + "_" + str(plan["cycle"])
            with owner.attempt(Operation(key), retained_invalid=True):
                attempt = owned_attempt(owner, session, "prepared")
                target = attempt / "access.apk"
                self.build_signed(self.normal_apk, target,
                                  {"AndroidManifest.xml": make_debuggable_manifest(apk_manifest(self.normal_apk))})
                if self.local_apk_identity(target) != expected:
                    raise PatchError("error_apk_identity", detail="Fresh preparation changed; saved APKs remain pinned")
                self._prepared_access = self.verify_prepared("access")
        self.adb.shell(f"am force-stop {PACKAGE}")
        self.debuggable_installed = True
        self.install_prepared("access", plan["access"], safety_recovery=recovery)

    def _continue_authorized(self) -> dict:
        """Reconcile journals before producer discovery, retries or expensive stages."""
        owner = self.run_owner
        if "apk_session" not in owner.record["children"]:
            if owner.record["stop_requested"]:
                observed = self.adb.installed_identity()
                if observed is None or observed["debuggable"]:
                    raise PatchError("error_apk_identity", detail="Cannot verify the unchanged normal game")
                self._cancel_consistent()
            self._phase("preparing")
            check_work_dir(self.work)
            return self._run_authorized()
        self.apk_journal = ApkJournal(owner)
        if "normal" not in self.apk_journal.record["apks"]:
            return self._restart_preparation()
        self.normal_apk = self.verify_prepared("normal")
        setup = self.apk_journal.record["setup"]
        apks = self.apk_journal.record["apks"]
        if (setup is None and "source" in apks
                and apks["source"]["signers"] != apks["normal"]["signers"]
                and self.adb.installed_identity() == apks["source"]):
            # Death after pinning signed normal, before setup consent. The local
            # output proves no conversion; preserve source and ask scoped consent anew.
            if owner.record["stop_requested"] or not owner.record["continuation"]:
                self._cancel_consistent()
            try:
                PreparedApks(owner, self.apk_journal, self.producer_identity()).verify(
                    "normal", self.manifest_to_install(apk_manifest(self.apk_journal.apk("source"))))
            except (ArtifactError, OSError, ValueError):
                return self._restart_preparation()
            self._convert_installed_source(apks["source"], apks["normal"])
        if setup is not None and setup["phase"] != "ready":
            if setup["phase"] == "prepared" and owner.record["stop_requested"]:
                self._cancel_consistent()
            self.recover_first_setup()
            if owner.record["stop_requested"]:
                self._cancel_consistent()
            self.event("waiting", "downloads_finished")
            self.finish_setup_update()
        if ("access" not in self.apk_journal.record["apks"]
                and self.apk_journal.apk("access").exists()):
            return self._restart_preparation()
        if "access" in self.apk_journal.record["apks"]:
            self.verify_prepared("access")
            owner.complete_observed("prepare_" + identity_key(self.apk_journal.record["apks"]["source"]))
        session = self._session()
        tx = self._transaction() if session and (session / "file-transaction.json").exists() else None
        if tx is not None:
            self.file_transaction = tx
            phase = tx.record["phase"]
            if phase in {"payload_verified", "finalizing", "finalized"} and not (
                    owner.record["stop_requested"] and phase == "payload_verified"):
                # No engine loading/build/snapshot/payload write on final-install-only recovery.
                return self._finish_transaction(self._saved_result(session))
            self._ensure_access("recovery_access_" + str(tx.record["cycle"]), recovery=True)
            if phase != "rolled_back":
                tx.rollback()
            if owner.record["stop_requested"] or not owner.record["continuation"]:
                self.install_prepared("normal", "cancel_normal_" + str(tx.record["cycle"]), safety_recovery=True)
                self.debuggable_installed = False
                self._cancel_consistent()
            checkpoint = Checkpoints(owner, session)
            try:
                producer = self.producer_identity()
                if producer is None:
                    raise ArtifactError("Complete producer unavailable")
                result, _ = checkpoint.verify_build(checkpoint.identity(self.apk_journal.record["apks"], producer))
            except (ArtifactError, OSError):
                # Rollback is already complete. Retire the old transaction intact;
                # the new child gets a fresh immutable snapshot, never old originals.
                replacement = None
                if producer is not None:
                    # Engine-only invalidation retains the independently verified
                    # source snapshot; a new child owns new staging/transaction ids.
                    live = ShellTransport(self.adb).inventory(session.name)
                    checkpoint.verify_snapshot(self.apk_journal.record["apks"], live)
                    replacement = self._fork_snapshot(session)
                self.install_prepared("normal", "restage_normal_" + str(tx.record["cycle"]), safety_recovery=True)
                self.debuggable_installed = False
                if replacement is None:
                    self._retire_session(session)
                return self._resume_stages(replacement)
            self._phase("staged")
            self._phase("applying")
            self.event("continuing", "apply_stage", reused="staged")
            tx.reapply()
            return self._finish_transaction(result)
        if owner.record["stop_requested"] or not owner.record["continuation"]:
            observed = self.adb.installed_identity()
            if observed == self.apk_journal.record["apks"].get("access"):
                self.install_prepared("normal", "cancel_before_apply", safety_recovery=True)
            else:
                self.verify_normal_installed()
            self._cancel_consistent()
        return self._resume_stages(session)

    def _retire_session(self, session: Path) -> None:
        owner = self.run_owner
        children = dict(owner.record["children"])
        # Keep the old transaction referenced until the action resolves.
        children["retired_" + session.name] = session.name
        for name in ("data_session", "snapshot_attempt", "build_attempt"):
            children.pop(name, None)
        owner.update(children=children)
        self.file_transaction = None
        self._active_build = None

    def _run_authorized(self) -> dict:
        source = self.adb.installed_identity()
        if source is None or source["debuggable"]:
            raise PatchError("error_apk_identity", detail="Fresh preparation requires the normal game")
        with self.run_owner.attempt(Operation("prepare_" + identity_key(source))):
            self.prepare_normal_apk(self.find_installed_apk())
            self.prepare_debuggable_apk()
        return self._resume_stages(None)

    def _fork_snapshot(self, previous: Path) -> Path:
        """New owned mutable generation; actual saved originals are copied, not linked."""
        from run_artifacts import _safe_file
        source = Checkpoints(self.run_owner, previous).snapshot()
        needed = sum(item["size"] for item in source["files"].values()) * 3 + MIN_FREE_BYTES
        available = free_space(self.work)
        if available is None or available < needed:
            raise PatchError("error_work_dir_full", path=self.work, free=f"{(available or 0) / 1024**3:.1f}")
        self._retire_session(previous)
        token = str(uuid.uuid4())
        self.run_owner.update(children={**self.run_owner.record["children"], "data_session": token})
        target = self.work / "sessions" / token
        _safe_file(target.parent, directory=True)
        target.mkdir()
        shutil.copytree(previous / "recovery", target / "recovery")
        _durable_copy(previous / "recovery-manifest.json", target / "recovery-manifest.json")
        _durable_copy(previous / PULL_RECORD, target / PULL_RECORD)
        Checkpoints(self.run_owner, target).publish_snapshot(self.apk_journal.record["apks"], self.producer_identity())
        return target

    def _restart_preparation(self) -> dict:
        """Restart only provably pre-mutation incomplete preparation in a new child."""
        journal, owner = self.apk_journal, self.run_owner
        saved = journal.record
        setup = saved["setup"]
        if (any(item["role"] != "normal" or item["outcome"] != "verified" for item in saved["installs"].values())
                or "data_session" in owner.record["children"]
                or setup is not None and setup["phase"] != "ready"
                or any(key.startswith("uninstall_") and value["attempts"]
                       for key, value in owner.record["retry"].items()) and setup is None):
            raise PatchError("error_run_state", detail="Incomplete preparation has mutation evidence")
        source_record = read_record(journal.directory / "preparation-source.json")
        if (set(source_record) != {"schema", "run_id", "target", "source"} or source_record["schema"] != 1
                or source_record["run_id"] != owner.run_id or source_record["target"] != owner.target):
            raise PatchError("error_run_state", detail="Missing exact preparation source")
        expected = saved["apks"].get("normal") if setup is not None else source_record["source"]
        observed = self.adb.installed_identity()
        if observed != expected or observed is None or observed["debuggable"]:
            raise PatchError("error_apk_identity", detail="Preparation source changed")
        if owner.record["stop_requested"]:
            self._cancel_consistent()
        children = dict(owner.record["children"])
        old = children.pop("apk_session")
        children["retired_apk_" + old] = old
        owner.update(children=children)
        self.apk_journal = None
        self._prepared_access = None
        # Only this exact retired, pre-mutation generation may supply preparation.
        # No directory scan, timestamp selection or recovery-file replacement.
        self._preparation_candidate = journal
        self._phase("preparing")
        return self._run_authorized()

    def _resume_stages(self, session: Path | None) -> dict:
        self._phase("preparing")
        # Existing access install is audited first; after a restored normal APK,
        # use a stable distinct install scope for the remaining file-apply cycle.
        operation = "access_initial" if session is None else "access_resume"
        self._ensure_access(operation)
        if session is not None:
            try:
                checkpoint = Checkpoints(self.run_owner, session)
                live = ShellTransport(self.adb).inventory(session.name)
                checkpoint.verify_snapshot(self.apk_journal.record["apks"], live)
                snapshot_key = "snapshot_" + identity_key({"live": live, "apks": self.apk_journal.record["apks"]})
                self.run_owner.complete_observed(snapshot_key)
                self.data_version = read_record(session / PULL_RECORD)["data_version"]
                self.event("continuing", "verify_stage", reused="snapshot")
            except (ArtifactError, OSError, KeyError):
                self._retire_session(session)
                session = None
        if session is None:
            check_work_dir(self.work)
            self._phase("preparing")
            scope = identity_key({"live": ShellTransport(self.adb).inventory(str(uuid.uuid4())),
                                  "apks": self.apk_journal.record["apks"]})
            with self.run_owner.attempt(Operation("snapshot_" + scope), retained_invalid=True):
                session = self.pull_game_data()
        checkpoint = Checkpoints(self.run_owner, session)
        self._phase("snapshot")
        producer = self.producer_identity()
        identity = checkpoint.identity(self.apk_journal.record["apks"], producer) if producer else None
        # Only a fresh Start's own snapshot can enter this path. Interrupted STAGED
        # reuse remains independent, and Stop is checked before adopting any bytes.
        self.control_boundary()
        if identity is not None and checkpoint.build_root() is None:
            live = ShellTransport(self.adb).inventory(session.name)
            if live["files"] != identity["game"]["files"]:
                self.log("  Game files changed before the completion audit")
                raise PatchError("error_files_changed")
            copied = reuse_completed(checkpoint, identity, self.apk_journal.record["apks"])
            if copied is not None:
                self.event("continuing", "apply_stage", reused="verified_completion_output_copy")
            self.control_boundary()
        try:
            if identity is None:
                raise ArtifactError("Complete producer unavailable")
            result, root = checkpoint.verify_build(identity)
            self.run_owner.complete_observed("build_" + identity_key(identity))
            self._active_build = root
            self.event("continuing", "apply_stage", reused="staged")
        except (ArtifactError, OSError):
            size = sum(item["size"] for item in checkpoint.snapshot()["files"].values())
            available = free_space(self.work)
            # Actual free space already excludes retained cache/APKs/originals.
            # Reserve separate reconstruction, staging/scratch and normal/rollback.
            needed = size * 3 + self.verify_prepared("normal").stat().st_size * 2 + 512 * 1024**2
            if available is None or available < needed:
                raise PatchError("error_work_dir_full", path=self.work, free=f"{(available or 0) / 1024**3:.1f}")
            checkpoint.reset_pristine_input()
            restored = self.restore_pristine(session)
            self._restored = restored
            # Bootstrap can publish a legacy delta; bind the resulting pristine evidence.
            identity = checkpoint.identity(self.apk_journal.record["apks"], producer) if producer else None
            self._phase("building")
            build_key = "build_" + (identity_key(identity) if identity else identity_key({
                "snapshot": checkpoint.snapshot(), "producer": None, "action": self.run_owner.record["action"],
                "language": self.language.code}))
            with self.run_owner.attempt(Operation(build_key), retained_invalid=True):
                if self.remove:
                    if restored is None:
                        raise PatchError("error_no_record_to_remove", "use_other_patcher")
                    result, staged = {"packages": [], "removed": restored}, None
                    self._active_build = owned_attempt(self.run_owner, session, "build")
                else:
                    result, staged = self.build_translation(session)
                    if restored is None or self.replaced:
                        self.check_first_delta(result)
                root = self._publish_payload(session, result, staged, restored or [], identity)
        self._phase("staged")
        self._phase("applying")
        self._apply_checkpoint(session, root)
        return self._finish_transaction(result)

    def _saved_result(self, session: Path) -> dict:
        root = Checkpoints(self.run_owner, session).build_root()
        if root is None:
            raise PatchError("error_run_state", detail="Missing saved result")
        tx = self.file_transaction
        tx.verify_material(outputs=False)
        binding = read_record(tx.directory / "transaction-meta" / "result-binding.json")
        if (set(binding) != {"schema", "summary", "receipt", "root"} or binding["schema"] != 1
                or binding["root"] != root.relative_to(session).as_posix()
                or binding["summary"] != file_identity(root / "device_patch_summary.json")):
            raise PatchError("error_run_state", detail="Saved result differs from transaction")
        if binding["receipt"] is not None:
            from run_artifacts import verify_receipt
            receipt = verify_receipt(root, stage="staged")  # Saved producer, no engine load.
            if (receipt["run_id"] != self.run_owner.run_id
                    or file_identity(root / "build-receipt.json") != binding["receipt"]):
                raise PatchError("error_run_state", detail="Saved build receipt differs")
        return read_record(root / "device_patch_summary.json")

    def _recover_failed_dispatch(self) -> None:
        """Safety only; keep verified payload for final-install-only recovery."""
        owner, tx = self.run_owner, self.file_transaction
        if owner is None or owner.record is None or owner.record["lifecycle"] in RESOLVED:
            return
        # The failed operation's attempt was already recorded by OwnedRun.attempt.
        if self.apk_journal is None and "apk_session" in owner.record["children"]:
            self.apk_journal = ApkJournal(owner)
            if "normal" in self.apk_journal.record["apks"]:
                self.normal_apk = self.verify_prepared("normal")
            session = self._session()
            if session and (session / "file-transaction.json").exists():
                self.file_transaction = tx = self._transaction()
        if self.apk_journal is None:
            if owner.record["stop_requested"]:
                self._cancel_consistent()
            return  # No APK/file dispatch was possible without this journal.
        try:
            if tx is not None and tx.record["phase"] in {"finalizing", "finalized"}:
                self._finish_transaction(self._saved_result(tx.directory))
                return
            rollback = tx is not None and (tx.record["phase"] in {"prepared", "applying", "rollback"}
                or owner.record["stop_requested"] and tx.record["phase"] == "payload_verified")
            if rollback:
                self._ensure_access("stop_repair" if owner.record["stop_requested"] else
                                    "rollback_" + str(tx.record["cycle"]), recovery=True)
                tx.rollback()
            observed = self.adb.installed_identity()
            if ("access" in self.apk_journal.record["apks"]
                    and observed == self.apk_journal.record["apks"]["access"]):
                self.debuggable_installed = True
            if self.debuggable_installed:
                self.restore_normal_apk(operation="failure_cleanup")
            if owner.record["stop_requested"] and (tx is None or tx.record["phase"] == "rolled_back"):
                self._cancel_consistent()
            self.event("attention", "recover_saved_action", run_id=owner.run_id)
        except PatchError as error:
            if error.keys == ("error_cancelled",):
                raise
            owner.update(lifecycle="attention")
            self.event("attention", "restore_normal", run_id=owner.run_id)
            raise
        except Exception:
            owner.update(lifecycle="attention")
            self.event("attention", "recover_saved_action", run_id=owner.run_id)
            raise

    def _finish_transaction(self, result: dict) -> dict:
        tx = self.file_transaction
        # run-as inventory requires access. A resumed normal install needs an
        # explicitly bounded access/audit/normal cycle, never cached live proof.
        if self.adb.installed_identity() != self.apk_journal.record["apks"].get("access"):
            self._ensure_access("final_audit", recovery=True)
        if self.run_owner.record["lifecycle"] != "normal_verified":
            self._phase("payload_verified")
        if self.run_owner.record["stop_requested"] and tx.record["phase"] == "payload_verified":
            self._ensure_access("stop_access_" + str(tx.record["cycle"]), recovery=True)
            tx.rollback()
            self.install_prepared("normal", "stop_normal_" + str(tx.record["cycle"]), safety_recovery=True)
            self.debuggable_installed = False
            self._cancel_consistent()
        def ensure_normal() -> None:
            self.restore_normal_apk(operation="final_normal_" + str(tx.record["cycle"]))
            self.verify_normal_installed()
            self._phase("normal_verified")

        # finalize audits live bytes while access is installed, THEN invokes the
        # normal restoration callback, THEN promotes metadata. No post-normal run-as.
        tx.finalize(self.keep, ensure_normal)
        # Metadata promotion has no ADB boundary. Flush a UI-queued Stop here
        # before choosing the terminal receipt, even if its saver has not run.
        # Finalization already committed: finish forward, never roll it back.
        build_root = Checkpoints(self.run_owner, tx.directory).build_root()
        identity = None
        if (build_root / "build-receipt.json").exists():
            from run_artifacts import verify_receipt
            identity = verify_receipt(build_root, stage="staged")["identity"]
        from run_artifacts import installed_state_key
        delta = active_delta_identity(self.keep)
        receipt = {"schema": 2, "run_id": self.run_owner.run_id, "target": self.run_owner.target,
                   "action": self.run_owner.record["action"], "language": self.language.code,
                   "outcome": None, "files": tx.record["expected"],
                   "normal": self.apk_journal.record["apks"]["normal"],
                   "metadata": tx.record["metadata"], "result": result,
                   "identity": identity, "delta": delta,
                   "apk_session": self.run_owner.record["children"]["apk_session"],
                   "installed_key": installed_state_key(identity, files=tx.record["expected"],
                        installed=self.apk_journal.record["apks"]["normal"], delta=delta) if identity is not None else None,
                   "build_receipt": file_identity(Checkpoints(self.run_owner, tx.directory).build_root() / "build-receipt.json")
                   if (Checkpoints(self.run_owner, tx.directory).build_root() / "build-receipt.json").exists() else None}
        # Hashing above does not block Stop. This short durable section is the
        # completion linearization point shared with the UI control saver.
        with self._control_lock:
            self._persist_control()
            stopped = self.run_owner.record["stop_requested"]
            receipt["outcome"] = "stopped_consistent" if stopped else "verified_complete"
            _publish(tx.directory / "completion-receipt.json", receipt)
            if read_record(tx.directory / "completion-receipt.json") != receipt:
                raise PatchError("error_run_state", detail="Completion publication differs")
            # queue_control is intentionally lock-free. A Stop arriving during
            # the candidate record fsync wins before the terminal transition.
            self._persist_control()
            if not stopped and self.run_owner.record["stop_requested"]:
                stopped = True
                receipt["outcome"] = "stopped_consistent"
                _publish(tx.directory / "completion-receipt.json", receipt)
            self._phase("cancelled" if stopped else "finalized")
            self._publish_retention(tx.directory)
        if stopped:
            self.event("cancelled", "idle", finalization_finished=True, run_id=self.run_owner.run_id)
            raise PatchError("error_cancelled")
        self.event("verified_complete", "open_game", run_id=self.run_owner.run_id)
        self.prune_old_sessions(self.work, keep=tx.directory, owner=self.run_owner)
        return result

    def _cancel_consistent(self) -> None:
        # Layer proof comes from no transaction or its completed rollback. APK proof
        # is checked again here so an exception/Stop path cannot resolve unknown bytes.
        tx = self.file_transaction
        observed = self.adb.installed_identity()
        trusted = observed is not None and not observed["debuggable"]
        if self.apk_journal is not None:
            saved = self.apk_journal.record
            normal = saved["apks"].get("normal")
            pre_mutation = (not saved["installs"] and (saved["setup"] is None or saved["setup"]["phase"] == "prepared")
                and not any(key.startswith("uninstall_") and item["attempts"]
                            for key, item in self.run_owner.record["retry"].items()))
            source = saved["apks"].get("source")
            marker = self.apk_journal.directory / "preparation-source.json"
            if source is None and marker.exists():
                source = read_record(marker).get("source")
            trusted &= observed == normal or pre_mutation and observed == source
        elif "apk_session" in self.run_owner.record["children"]:
            trusted = False
        if not trusted or tx is not None and tx.record["phase"] != "rolled_back":
            self.run_owner.update(lifecycle="attention")
            raise PatchError("error_apk_identity", detail="Cannot prove stopped game consistency")
        self._phase("normal_verified")
        self._phase("cancelled")
        if self.apk_journal is not None:
            self._publish_retention(self._session() or self.apk_journal.directory)
        self.event("cancelled", "idle", run_id=self.run_owner.run_id)
        raise PatchError("error_cancelled")

    def _publish_retention(self, directory: Path) -> None:
        owner = self.run_owner
        children = owner.record["children"]
        references = sorted({children[name] for name in ("apk_session", "data_session") if name in children})
        _publish(directory / "session-retention.json", {"schema": 1, "run_id": owner.run_id,
                 "target": owner.target, "lifecycle": owner.record["lifecycle"], "references": references,
                 "resolved_at": datetime.now(timezone.utc).isoformat()})
        for key, child in children.items():
            if not key.startswith("retired_"):
                continue
            old = self.work / "sessions" / child
            if old.is_dir():
                _publish(old / "session-retention.json", {"schema": 1, "run_id": owner.run_id,
                         "target": owner.target, "lifecycle": "cancelled", "references": [child],
                         "resolved_at": owner.record["authorized_at"]})

    # ---------- stepper helpers ----------
    def step(self, key: str, detail: str = "") -> None:
        self.control_boundary()
        if self.current and self.current != key:
            self.ui.set_step(self.current, "done")
        self.current = key
        self.ui.set_step(key, "active", detail)
        label = dict(STEPS)[key]
        self.log(f"\n== {label}{' - ' + detail if detail else ''}")

    def done(self, key: str, detail: str = "") -> None:
        self.ui.set_step(key, "done", detail)
        if self.current == key:
            self.current = None

    def skip(self, key: str, detail: str) -> None:
        self.ui.set_step(key, "skipped", detail)

    # ---------- workflow ----------
    def wait_for_device(self) -> None:
        self.step("device", "waiting for USB connection")
        self.adb.run("start-server", check=False)
        hinted = set()
        while True:
            lines = [l.split() for l in self.adb.run("devices").splitlines()[1:] if l.strip()]
            states = [parts[1] for parts in lines if len(parts) >= 2]
            if states.count("device") == 1 and len(states) == 1:
                selected = lines[0][0]
                self.adb.bind(selected)
                self.adb.assert_target()
                brand = self.adb.shell("getprop ro.product.brand", check=False)
                model = self.adb.shell("getprop ro.product.model", check=False)
                release = self.adb.shell("getprop ro.build.version.release", check=False)
                name = f"{brand} {model}".strip()
                self.ui.set_device(ui_text("device_connected", name=name, release=release), True)
                self.log(f"Phone detected: {name} (Android {release})")
                self.done("device", name)
                return
            if len(states) > 1:
                hint = ui_text("device_one_phone_only")
            elif "unauthorized" in states:
                hint = ui_text("device_allow_usb_debugging")
            else:
                hint = ui_text("device_connect_usb")
            if hint not in hinted:
                self.log(f"Waiting for one authorised phone; adb reports {states or 'no device'}")
                self.ui.set_device(hint, False)
                hinted.add(hint)
            self._interrupt.wait(2)
            self.control_boundary()

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

    def recover_first_setup(self) -> None:
        """Safety repair only: no uninstall and no translation. Caller owns saved run."""
        journal = self.apk_journal
        journal.record = journal.load()
        setup = journal.record["setup"]
        if setup is None:
            raise PatchError("error_run_state", detail="No first setup intent")
        self.normal_apk = self.verify_prepared("normal")
        observed = self.adb.installed_identity()
        if observed == setup["source"]:
            self.run_owner.update(lifecycle="attention")
            raise PatchError("error_setup_consent")
        if setup["phase"] == "prepared":
            raise PatchError("error_run_state", detail="Setup has no uninstall intent")
        if observed is not None and observed != setup["normal"]:
            self.run_owner.update(lifecycle="attention")
            raise PatchError("error_apk_identity", detail="An unrelated APK is installed")
        if setup["phase"] == "ready" and observed == setup["normal"]:
            return
        if observed is None:
            if setup["phase"] not in {"uninstall_intent", "install_intent"}:
                raise PatchError("error_apk_identity", detail="Game absence is outside the saved setup install gap")
            # Recovery needs one observed-copy allocation, not the fresh 8 GiB budget.
            available = free_space(journal.directory)
            if available is None or available < setup["normal"]["size"] + 64 * 1024**2:
                raise PatchError("error_setup_space", path=journal.directory)
            journal.update(setup={**setup, "phase": "install_intent"})
        self.install_prepared("normal", "setup_normal")
        consent = setup["consent"]
        self.run_owner.update(consents={**self.run_owner.record["consents"], consent: {
            **self.run_owner.record["consents"][consent], "consumed": "normal_verified"}})
        journal.update(setup={**setup, "phase": "waiting_update"})
        self.run_owner.update(lifecycle="waiting")

    def finish_setup_update(self) -> None:
        self.ui.wait_user(ui_text("download_game_data_title"), ui_text("download_game_data"))
        if self.adb.installed_identity() != self.apk_journal.record["setup"]["normal"]:
            raise PatchError("error_apk_identity", detail="Normal game changed during setup downloads")
        self.adb.shell(f"am force-stop {PACKAGE}")
        self.apk_journal.update(setup={**self.apk_journal.record["setup"], "phase": "ready"})
        self.run_owner.update(lifecycle="preparing")

    def build_signed(self, source: Path, target: Path, replacements: dict[str, bytes]) -> None:
        from run_artifacts import _safe_file
        unsigned = target.with_suffix(".unsigned")
        try:
            _safe_file(source)
            _safe_file(target.parent, directory=True)
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

    def pull_game_data(self) -> Path:
        self.step("pull", "~2 GB")
        info = self.adb.shell(f"run-as {PACKAGE} cat files/QtsVFSCache/packages/1/1.info", check=False)
        if '"version"' not in info:
            raise PatchError("error_game_data_missing")
        self.log(f"Game data version: {info.strip()}")
        self.data_version = info.strip()
        session_id = str(uuid.uuid4()) if self.run_owner is not None else datetime.now().strftime("%Y%m%d-%H%M%S")
        if self.run_owner is not None:
            self.run_owner.update(children={**self.run_owner.record["children"], "data_session": session_id})
        session = self.work / "sessions" / session_id
        session.mkdir(parents=True)
        previous = self.previous_session(session)
        record = None
        if previous:
            try:
                record = self.pull_changed(session, previous)
            except (OSError, tarfile.TarError, PatchError) as error:
                self.log(f"  the partial pull failed ({error}): pulling everything")
        if record is None:
            shutil.rmtree(session / LAYER, ignore_errors=True)
            for part in session.glob("pull-*.tar"):
                part.unlink()
            self.ui.set_step("pull", "active", "~2 GB")
            record = self.pull_everything(session)
        (session / PULL_RECORD).write_text(json.dumps({"data_version": self.data_version,
                                           "target": {"serial": self.adb.serial,
                                                      "android_user": self.adb.android_user,
                                                      "package": PACKAGE}, **record}, indent=1),
                                           encoding="utf-8")
        self.preserve_recovery_snapshot(session)
        if self.apk_journal is not None:
            Checkpoints(self.run_owner, session).publish_snapshot(self.apk_journal.record["apks"], self.producer_identity())
        self.done("pull", info.strip())
        return session

    def preserve_recovery_snapshot(self, session: Path) -> None:
        """Pin actual phone bytes before restore_pristine can change the build input.

        Changed-only pulls have no backup tar. Watchdog is therefore always pulled
        explicitly, and the exact live set is checked on both sides of that pull.
        Missing/unsafe/inconsistent source evidence refuses before any game write.
        """
        if self.run_owner is None or session != self.run_owner.root / "sessions" / self.run_owner.record["children"].get("data_session", ""):
            raise PatchError("error_run_state", detail="Snapshot lacks run ownership")
        marker = session / "recovery-manifest.json"
        recovery = session / "recovery"
        transport = ShellTransport(self.adb)
        transport.bind_target(self.run_owner.target)
        child = session.name
        try:
            if marker.exists():
                saved = read_record(marker)
                if saved.get("target") != self.run_owner.target:
                    raise SessionError("error_run_state", "Snapshot target differs")
                verify_manifest(recovery, saved["files"])
                return
            if recovery.exists():
                raise SessionError("error_run_state", "Incomplete recovery snapshot must restart")
            before = transport.inventory(child)
            source = {"packages/" + name: item for name, item in tree_manifest(session / LAYER).items()}
            if source != {name: item for name, item in before["files"].items() if name.startswith("packages/")}:
                raise SessionError("error_files_changed", "Pulled layer does not match phone")
            needed = sum(item["size"] for item in before["files"].values()) + MIN_FREE_BYTES
            free = shutil.disk_usage(session).free
            if free < needed:
                raise PatchError("error_work_dir_full", path=self.work, free=f"{free / 1024**3:.1f}")
            recovery.mkdir()
            shutil.copytree(session / LAYER, recovery / "packages")
            watchdog = session / "watchdog-backup.tar"
            # Missing Watchdog is represented by no files/directories in the live manifest.
            if "Watchdog" in before["directories"]:
                self.adb.exec_out_to_file(f"run-as {PACKAGE} tar -cf - -C files/QtsVFSCache Watchdog", watchdog)
                with tarfile.open(watchdog) as archive:
                    members = archive.getmembers()
                    if any((not item.isfile() and not item.isdir()) or not
                           (item.name == "Watchdog" or item.name.startswith("Watchdog/"))
                           or ".." in Path(item.name).parts for item in members):
                        raise SessionError("error_run_state", "Unsafe Watchdog backup")
                    archive.extractall(recovery, members=members, filter="data")
            verify_manifest(recovery, before["files"])
            if transport.inventory(child) != before:
                raise SessionError("error_files_changed", "Phone changed during recovery snapshot")
            # Flush every retained original before committing its manifest.
            for name in before["files"]:
                with (recovery / name).open("rb+") as stream:
                    stream.flush(); os.fsync(stream.fileno())
            _publish(marker, {**before, "target": self.run_owner.target})
        except (SessionError, ValueError, OSError, tarfile.TarError) as error:
            if isinstance(error, SessionError):
                raise _session_error(error) from error
            raise PatchError("error_run_state", detail=error) from error

    def pull_everything(self, session: Path) -> dict:
        """Pull the whole override layer, and the Watchdog folder, as one tar kept as the session's backup."""
        backup = session / "device-backup.tar"
        self.adb.exec_out_to_file(f"run-as {PACKAGE} tar -cf - -C files/QtsVFSCache packages Watchdog", backup)
        game = session / LAYER.parent
        game.mkdir(parents=True, exist_ok=True)  # a failed partial pull leaves it behind
        # Extract straight into builtin/: renaming the folder afterwards fails at random on Windows,
        # while a scanner still holds some of the 2 GB of files just written (seen 2026-10-17).
        with tarfile.open(backup) as tar:
            members = [m for m in tar.getmembers() if m.name.startswith("packages/") and m.isfile()]
            for member in members:
                member.name = "builtin/" + member.name.removeprefix("packages/")
            tar.extractall(game, members=members, filter="data")
        layer = session / LAYER
        hashes = {name: pristine_delta.sha256_file(layer / name)
                  for name in (member.name.removeprefix("builtin/") for member in members)}
        return {"mode": "full", "files": len(members), "pulled_bytes": backup.stat().st_size, "sha256": hashes}

    def previous_session(self, session: Path) -> Path | None:
        """The newest other session whose layer copy matched the phone when it was pulled."""
        candidates = (path for path in (self.work / "sessions").iterdir() if path.is_dir())
        # UUID ownership names have no chronological ordering. Timestamp chooses
        # candidates only; every reused byte still has to match the live hash.
        for old in sorted(candidates, key=lambda path: (path / PULL_RECORD).stat().st_mtime_ns
                          if (path / PULL_RECORD).is_file() else 0, reverse=True):
            if old != session and (old / PULL_RECORD).is_file() and (old / LAYER).is_dir():
                try:
                    target = json.loads((old / PULL_RECORD).read_text(encoding="utf-8")).get("target")
                except (OSError, ValueError):
                    continue
                if target == {"serial": self.adb.serial, "android_user": self.adb.android_user, "package": PACKAGE}:
                    return old
        return None

    def pull_changed(self, session: Path, previous: Path) -> dict | None:
        """Pull only the files the phone holds at bytes <previous> has no copy of; None to pull everything.

        The phone hashes its layer, each file another session holds at that SHA-256 is copied from it, and
        the rest is pulled and checked against the phone's hash. The session's layer then holds exactly
        the phone's bytes, so every later step reads what a full pull would have given it. This session
        keeps no backup tar, which only a full pull writes.
        """
        self.ui.set_step("pull", "active", "comparing with the last run")
        output = self.adb.exec_out(f"run-as {PACKAGE} sh -c "
                                   f"'cd files/QtsVFSCache/packages && find . -type f -exec sha256sum {{}} +'")
        device = parse_device_hashes(output)
        if not device or "1/1.info" not in device:
            self.log("  the phone's file hashes did not read: pulling everything")
            return None
        found, missing = reusable_files(device, [previous / "staged", previous / LAYER])
        layer = session / LAYER
        for name, source in found.items():
            (layer / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, layer / name)
        self.log(f"  {len(found)} of {len(device)} files unchanged since {previous.name}; "
                 f"pulling {len(missing)}")
        batches: list[list[str]] = []
        for name in missing:
            if not batches or sum(len(item) + 1 for item in batches[-1]) + len(name) > PULL_BATCH_CHARS:
                batches.append([])
            batches[-1].append(name)
        pulled_bytes = 0
        for index, batch in enumerate(batches):
            part = session / f"pull-{index}.tar"
            self.adb.exec_out_to_file(f"run-as {PACKAGE} tar -cf - -C files/QtsVFSCache/packages "
                                      + " ".join(batch), part)
            wanted = set(batch)
            with tarfile.open(part) as tar:
                members = [m for m in tar.getmembers() if m.isfile() and m.name.removeprefix("./") in wanted]
                for member in members:
                    member.name = member.name.removeprefix("./")
                tar.extractall(layer, members=members, filter="data")
            pulled_bytes += part.stat().st_size
            part.unlink()
        for name in missing:
            path = layer / name
            if not path.is_file() or pristine_delta.sha256_file(path) != device[name]:
                self.log(f"  {name} did not arrive as the phone holds it: pulling everything")
                return None
        self.log(f"  pulled {pulled_bytes / 1e6:.1f} MB instead of the whole layer")
        return {"mode": "changed", "files": len(device), "pulled_files": len(missing),
                "pulled_bytes": pulled_bytes, "copied_from": previous.name, "sha256": device}

    # ---------- pristine delta ----------
    def _read_delta(self, name: str) -> pristine_delta.Delta | None:
        path = self.keep / name
        if not path.is_file():
            return None
        try:
            return pristine_delta.read(path)
        except pristine_delta.DeltaError as error:
            raise PatchError("error_delta_damaged", "clear_game_data", error=error) from error

    def restore_pristine(self, session: Path) -> list[str] | None:
        """Rebuild the pristine layer in the session's copy, before anything is built or written.

        Returns the files rebuilt from the pristine delta, or None when this patcher holds no delta for
        the phone and the layer may be the pristine one (`check_first_delta` decides after the build).
        Raises PatchError, with nothing written to the game data, when the layer can be neither.
        """
        self.preserve_recovery_snapshot(session)
        layer = session / LAYER
        delta = self._read_delta(pristine_delta.DELTA_NAME)
        pending = self._read_delta(PENDING_DELTA)
        if delta is None and pending is None:
            delta = self.bootstrap_delta(session)
        known = pristine_delta.load_staged_hashes(self.keep / pristine_delta.STAGED_HASHES_NAME)
        translated = pristine_delta.files_at(layer, known)  # read before the rebuild changes them
        if delta is None and pending is None:
            if translated:
                self.log("  this phone holds files this patcher wrote, but no record of their original bytes")
                raise PatchError("error_cannot_rebuild", "clear_game_data")
            self.log("  no pristine delta for this phone: building from the files as pulled")
            return None
        report = pristine_delta.rebuild(layer, delta or pending, layer, fallback=pending if delta else None)
        if not report.complete and not translated:
            # Nothing this patcher wrote is left, as after clearing the game's data and downloading a
            # newer version: the delta describes a layer that is gone. The text signal decides instead.
            self.log(f"  the pristine delta no longer matches ({len(report.unmatched)} file(s) differ) and no "
                     f"file holds this patcher's translation: building from the files as pulled")
            return None
        if not report.complete:
            for name, state in sorted(report.unmatched.items()):
                self.log(f"  {name}: {state} since the last install")
            accepted, restorable, refused = pristine_delta.accept_replaced(layer, delta or pending, report,
                                                                           fallback=pending if delta else None)
            # Asset restore (ADR 0008) is the Android patcher's alone for now: here a restorable package
            # is refused like any other.
            refused = {**restorable, **refused}
            for package, reason in refused.items():
                self.log(f"  package {package} cannot be read as untranslated: {reason}")
            if refused:
                self.log(f"  cannot rebuild from the pristine delta: {len(report.unmatched)} file(s) changed")
                raise PatchError("error_files_changed", "clear_game_data")
            # The update's bytes stand as the new pristine; the text pass must still read them as such.
            self.replaced = accepted
            self.log(f"  {len(accepted)} file(s) the game update replaced hold none of this patcher's "
                     "translation: building from them as the update left them")
        leftover = [name for name in translated if name not in report.rebuilt]
        if leftover:
            self.log(f"  still translated after the rebuild: {', '.join(leftover)}")
            raise PatchError("error_uncovered_files", "clear_game_data")
        self.log(f"  rebuilt {len(report.rebuilt)} files from the pristine delta"
                 + (f" ({len(report.pristine)} already untranslated)" if report.pristine else ""))
        return report.rebuilt

    def check_first_delta(self, summary: dict) -> None:
        """Refuse a first install, or a build over files an update replaced, the text pass did not read as pristine."""
        reason = pristine_delta.text_not_pristine(summary)
        if reason:
            self.log(f"  not the pristine layer: {reason}")
            if self.replaced:
                raise PatchError("error_update_kept_translation", "clear_game_data")
            raise PatchError("error_translated_elsewhere", "clear_game_data", "use_other_patcher")

    def bootstrap_delta(self, session: Path) -> pristine_delta.Delta | None:
        """Make a first delta from a kept session, so a phone patched before deltas existed needs no clear.

        A kept session qualifies when the phone's files equal its staged output and its backup reads as
        pristine: no file at a staged hash this patcher recorded, and a text pass that read the pristine
        text. Tried once per run, newest session first.
        """
        layer = session / LAYER
        known = pristine_delta.load_staged_hashes(self.keep / pristine_delta.STAGED_HASHES_NAME)
        for old in sorted((self.work / "sessions").iterdir(), reverse=True):
            staged, backup = old / "staged", old / "device-backup.tar"
            if old == session or not (staged / "device_patch_summary.json").is_file() or not backup.is_file():
                continue
            names = pristine_delta.package_files(staged)
            if not names or not all((layer / name).is_file() and pristine_delta.sha256_file(layer / name)
                                    == pristine_delta.sha256_file(staged / name) for name in names):
                continue
            try:
                summary = json.loads((staged / "device_patch_summary.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if pristine_delta.text_not_pristine(summary):
                continue
            original = session / "bootstrap"
            shutil.rmtree(original, ignore_errors=True)
            wanted = {f"packages/{name}" for name in names}
            try:
                with tarfile.open(backup) as tar:
                    members = [m for m in tar.getmembers() if m.name in wanted and m.isfile()]
                    tar.extractall(original, members=members, filter="data")
                source = original / "packages"
                if len(members) != len(names) or pristine_delta.files_at(source, known):
                    continue
                delta = pristine_delta.make(source, staged, info={**self._delta_info(),
                                                                  "bootstrapped_from": old.name})
            except (OSError, tarfile.TarError):
                continue
            finally:
                shutil.rmtree(original, ignore_errors=True)
            pristine_delta.write(delta, self.keep / pristine_delta.DELTA_NAME)
            pristine_delta.record_staged_hashes(self.keep / pristine_delta.STAGED_HASHES_NAME,
                                                delta.staged_hashes)
            self.log(f"  made a pristine delta from the kept session {old.name}")
            return delta
        return None

    def write_back_pristine(self, session: Path, restored: list[str] | None) -> dict:
        """Remove translation: write every rebuilt pristine file back, with no new patch.

        Goes through the same push as an install, which then deletes the delta: the phone's files are
        pristine, and the next patch run is a first install that makes a fresh one. Refuses, before
        anything is written, when the layer cannot be rebuilt or this patcher has no record of a
        translation on it.
        """
        if restored is None:
            raise PatchError("error_no_record_to_remove", "use_other_patcher")
        self.skip("translate", "removing the translation")
        self.push_translation(session, None, restored)
        return {"packages": [], "removed": restored}

    def _delta_info(self) -> dict:
        return {"patcher": "windows", "language": self.language.code, "data_version": self.data_version,
                "made": datetime.now().isoformat(timespec="seconds")}

    def build_translation(self, session: Path) -> tuple[dict, Path | None]:
        self.step("translate", "1-3 minutes")
        self._active_build = owned_attempt(self.run_owner, session, "build")
        staged = self._active_build / "payload"
        # The prime layer half the game's text lives in is inside the APK, and the append pass is what
        # carries it into a downloaded package. That needs the APK, not the package builder: the builder
        # is only for laying a package out whole, which no package asks for. Only a source run finds
        # resources/qtsvfs; the exe does not bundle it, and still translates everything the catalog covers.
        builder_dir = find_builder_dir([BUNDLE / "qtsvfs"])
        catalog = languages.catalog_dir(BUNDLE, self.language.code)
        summary = build_patch(session / "game", catalog, self._active_build / "scratch", staged,
                              apk=self.normal_apk, builder_dir=builder_dir,
                              log=self._build_progress)
        text, images = count_translated(summary)
        dropped_text = count_untranslated_text(summary)
        skipped = count_untranslated_graphics(summary)
        untranslated = []
        if dropped_text:
            untranslated.append(f"{dropped_text} text table{'s' if dropped_text != 1 else ''}")
        if skipped:
            untranslated.append(f"{skipped} image{'s' if skipped != 1 else ''}")
        if not summary["packages"]:
            self.log("Nothing new to translate (the game is probably already patched).")
        detail = f"{text} text tables, {images} images"
        if untranslated:
            detail += ", " + " and ".join(untranslated) + " left in Chinese"
        # "already installed" claims there is nothing to report, so a run that installs nothing and
        # still lost tables or images names them instead.
        self.done("translate", detail if (text or images or dropped_text or skipped) else "already installed")
        return summary, staged if summary["packages"] else None

    def _build_progress(self, line: object) -> None:
        self.control_boundary()
        self.log("  " + str(line))
        self.event("working", "build_translation", detail=str(line))

    def _publish_payload(self, session: Path, summary: dict, staged: Path | None,
                         restored: list[str], identity: dict | None) -> Path:
        """Finish restored outputs/delta before publishing a separate build receipt."""
        attempt = self._active_build
        root = attempt / "committed"
        root.mkdir()
        outputs = root / "payload"
        outputs.mkdir()
        names = pristine_delta.package_files(staged) if staged else []
        # Move only finished payload files inside this owned attempt. Scratch is
        # deliberately outside the immutable receipt's exact artifact set.
        for name in names:
            target = outputs / name
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged / name, target)
        delta = (pristine_delta.make(session / LAYER, outputs, info=self._delta_info(), fingerprint=True)
                 if names else pristine_delta.Delta((), self._delta_info()))
        if not self.remove:
            pristine_delta.write(delta, root / PENDING_DELTA)
        deletions = []
        for name in restored:
            if name in names:
                continue
            source = session / LAYER / name
            if source.exists():
                _durable_copy(source, outputs / name)
            else:
                original = file_identity(session / "recovery" / "packages" / name)
                candidates = [self._read_delta(pristine_delta.DELTA_NAME), self._read_delta(PENDING_DELTA)]
                if not any((entry := saved.entry(name)) is not None and entry.created
                           and original == {"size": entry.staged_size, "sha256": entry.staged_sha256}
                           for saved in candidates if saved is not None):
                    self.log(f"  {name}: removing it is not proven by a saved delta")
                    raise PatchError("error_files_changed")
                deletions.append(name)
        original = Checkpoints(self.run_owner, session).snapshot()["files"]
        expected = dict(original)
        payload = tree_manifest(outputs)
        for name, item in payload.items():
            expected["packages/" + name] = item
        for name in deletions:
            expected.pop("packages/" + name)
        if expected != original:
            expected = {name: item for name, item in expected.items() if not name.startswith("Watchdog/")}
        _publish(root / "deletions.json", {"schema": 1, "paths": sorted(deletions)})
        _publish(root / "expected-layer.json", {"schema": 1, "files": expected})
        _publish(root / "device_patch_summary.json", summary)
        if identity is not None and (self.remove or bool(delta.files)):
            Checkpoints(self.run_owner, session).publish_build(root, identity, remove=self.remove)
        else:
            # No complete producer or no translated entries: verified fresh apply
            # remains available, but this is explicitly not a reusable STAGED receipt.
            _publish(root / "fresh-only.json", {"schema": 1, "reusable": False})
        return root

    def _apply_checkpoint(self, session: Path, root: Path) -> None:
        """Consumer-boundary validation also covers fresh-only ordinary processing."""
        payload = root / "payload"
        files = {name: payload / name for name in tree_manifest(payload)}
        deletions = read_record(root / "deletions.json")
        if (set(deletions) != {"schema", "paths"} or deletions["schema"] != 1
                or not isinstance(deletions["paths"], list)
                or len(set(deletions["paths"])) != len(deletions["paths"])):
            raise PatchError("error_run_state", detail="Malformed deletion plan")
        from run_artifacts import relative_path
        for name in deletions["paths"]:
            relative_path(name)
            if name in files:
                raise PatchError("error_run_state", detail="Contradictory output plan")
            files[name] = None
        material = session / "delta-material"
        material.mkdir(exist_ok=True)
        if self.remove:
            pending = material / PENDING_DELTA
            pristine_delta.write(pristine_delta.Delta((), self._delta_info()), pending)
        else:
            pending = root / PENDING_DELTA
        delta = pristine_delta.read(pending)
        record = material / pristine_delta.STAGED_HASHES_NAME
        old_record = self.keep / pristine_delta.STAGED_HASHES_NAME
        if old_record.exists():
            _durable_copy(old_record, record)
        pristine_delta.record_staged_hashes(record, delta.staged_hashes)
        result_binding = material / "result-binding.json"
        _publish(result_binding, {"schema": 1, "summary": file_identity(root / "device_patch_summary.json"),
                 "receipt": file_identity(root / "build-receipt.json") if (root / "build-receipt.json").exists() else None,
                 "root": root.relative_to(session).as_posix()})
        metadata = {"pending-delta.bin": pending, "new-hashes.json": record, "result-binding.json": result_binding}
        for name, role in ((pristine_delta.DELTA_NAME, "old-delta.bin"), (PENDING_DELTA, "old-pending.bin"),
                           (pristine_delta.STAGED_HASHES_NAME, "old-hashes.json")):
            if (self.keep / name).exists():
                metadata[role] = self.keep / name
        tx = self._transaction()
        previous_cycles = []
        for key, child in self.run_owner.record["children"].items():
            if not key.startswith("retired_"):
                continue
            old = self.work / "sessions" / child / "file-transaction.json"
            if old.exists():
                saved = read_record(old)
                if saved.get("run_id") != self.run_owner.run_id or saved.get("phase") != "rolled_back":
                    raise PatchError("error_run_state", detail="Retired file action is unresolved")
                previous_cycles.append(saved["cycle"])
        tx.prepare(files, metadata, remove_delta=not bool(delta.files),
                   initial_cycle=max(previous_cycles) + 1 if previous_cycles else 0)
        self.file_transaction = tx
        expected = read_record(root / "expected-layer.json")
        if expected != {"schema": 1, "files": tx.record["expected"]}:
            raise PatchError("error_run_state", detail="Complete output manifest differs")
        tx.apply()
        self.done("install")

    def push_translation(self, session: Path, staged: Path | None, restored: list[str]) -> None:
        """Write the staged files, and the rebuilt pristine copy of any file this build no longer stages.

        The transaction keeps recovery originals and old/pending delta material before
        the first write. Finalization follows the normal APK audit, never copy replies.
        """
        self.step("install")
        files = {name: staged / name for name in pristine_delta.package_files(staged)} if staged else {}
        untranslated = [name for name in restored if name not in files]
        for name in untranslated:
            # A delta-created shard is absent from reconstructed pristine input.
            # Its recorded pre-action bytes remain in recovery for rollback.
            path = session / LAYER / name
            if not path.exists():
                candidates = [self._read_delta(pristine_delta.DELTA_NAME), self._read_delta(PENDING_DELTA)]
                original = file_identity(session / "recovery" / "packages" / name)
                if not any((entry := saved.entry(name)) is not None and entry.created
                           and original == {"size": entry.staged_size, "sha256": entry.staged_sha256}
                           for saved in candidates if saved is not None):
                    self.log(f"  {name}: no pristine source, and no saved delta created it")
                    raise PatchError("error_files_changed")
            files[name] = path if path.exists() else None
        if untranslated:
            self.log(f"  {len(untranslated)} file(s) go back to their "
                     f"original bytes: {', '.join(untranslated)}")
        delta = (pristine_delta.make(session / LAYER, staged, info=self._delta_info(), fingerprint=True)
                 if staged else pristine_delta.Delta((), self._delta_info()))
        if self.run_owner is None:
            raise PatchError("error_run_state", detail="File mutation requires durable authorization")
        normal = self.verify_prepared("normal")
        tx = DeviceTransaction(self.run_owner, ShellTransport(self.adb, reserve_bytes=normal.stat().st_size + 512 * 1024**2))
        if tx.directory != session:
            raise PatchError("error_run_state", detail="Wrong transaction session")
        material = session / "delta-material"
        material.mkdir(exist_ok=True)
        pristine_delta.write(delta, material / PENDING_DELTA)
        staged_record = material / pristine_delta.STAGED_HASHES_NAME
        old_record = self.keep / pristine_delta.STAGED_HASHES_NAME
        if old_record.exists():
            _durable_copy(old_record, staged_record)
        pristine_delta.record_staged_hashes(staged_record, delta.staged_hashes)
        metadata = {"pending-delta.bin": material / PENDING_DELTA, "new-hashes.json": staged_record}
        if (self.keep / pristine_delta.DELTA_NAME).exists():
            metadata["old-delta.bin"] = self.keep / pristine_delta.DELTA_NAME
        if (self.keep / PENDING_DELTA).exists():
            metadata["old-pending.bin"] = self.keep / PENDING_DELTA
        if old_record.exists():
            metadata["old-hashes.json"] = old_record
        try:
            tx.prepare(files, metadata, remove_delta=not bool(delta.files))
            self.file_transaction = tx
            tx.apply()
        except SessionError as error:
            raise _session_error(error) from error
        # A file the phone already holds at these bytes (the pull recorded every file's SHA-256) is not
        # written again, as on a re-run of the same language and catalog.
        phone = self._pulled_hashes(session)
        unchanged = sorted(name for name, path in files.items()
                           if path is not None and name in phone and phone[name] == pristine_delta.sha256_file(path))
        if unchanged:
            self.log(f"  {len(unchanged)} file(s) already on the phone at these bytes: {', '.join(unchanged)}")
        self.done("install")

    def verify_normal_installed(self) -> None:
        """Finalization boundary; a prior install reply is insufficient."""
        self.verify_prepared("normal")
        if self.adb.installed_identity() != self.apk_journal.record["apks"]["normal"]:
            raise PatchError("error_normal_recovery", detail=self.normal_apk)

    @staticmethod
    def _pulled_hashes(session: Path) -> dict[str, str]:
        """The SHA-256 of every file the phone held when <session> was pulled; empty when not recorded."""
        try:
            hashes = json.loads((session / PULL_RECORD).read_text(encoding="utf-8")).get("sha256")
        except (OSError, ValueError):
            return {}
        return hashes if isinstance(hashes, dict) else {}

    def restore_normal_apk(self, *, operation: str = "final_normal") -> None:
        self.step("restore", "check the phone for a Play Protect pop-up")
        self.log(PLAY_PROTECT_HINT)
        try:
            self.install_prepared("normal", operation)
        except (PatchError, SessionError, OSError) as error:
            if self.run_owner is not None:
                self.run_owner.update(lifecycle="attention")
            self.ui.set_step("restore", "error")
            self.current = None
            raise PatchError("error_normal_recovery", detail=self.normal_apk) from error
        self.debuggable_installed = False
        self.done("restore")

    @staticmethod
    def prune_old_sessions(work: Path, keep: Path, *, owner: OwnedRun | None = None) -> None:
        """Reference-aware cleanup under ownership; unknown/legacy material stays pinned."""
        if owner is None or owner.root != work:
            return
        from windows_checkpoints import prune_sessions
        try:
            prune_sessions(owner, keep)
        except (OSError, ValueError, TypeError, KeyError):
            # Optional cache cleanup must never destroy evidence or fail a verified install.
            return
