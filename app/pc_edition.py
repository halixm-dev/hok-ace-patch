"""The PC edition's workflow: everything the Windows patcher does for the game on this computer.

The GUI talks to `patcher_core` for a phone and to this module for the PC edition (`WXQ.exe`). The
runtime engine (`wxq_patch.adaptive.run`) writes the files: it installs a catalog into the packages
under `WXQ_Data\\Package\\builtin\\<id>\\`, keeps a receipt of the originals it replaced, verifies
every texture against the catalog's `patched_sha256`, and recovers its own pending files on its next
run. This module owns what goes around it:

- **Finding the game**: the engine's launcher records (`installation.discover_installations`, with no
  drive search) and a folder the player picked, checked by `resolve_game_root` and remembered in the
  patcher's settings file.
- **The process guard**: no job starts while the game (`wxq*.exe`, the engine's own check) or its
  launcher (`王者万象棋.exe`) runs. Processes are listed through `CreateToolhelp32Snapshot`, because
  `tasklist` mangles the launcher's name. A file either holds open fails the engine with WinError 32,
  and an install must not start while the launcher updates (ADR 0002's rule, on the PC edition).
- **The per-install catalog**: `pc_catalog.build`, cached per game and language.
- **The hooks**: `engine_hooks.install(receipts=...)`, so the receipts live in
  `<work>\\pc\\receipts\\<game id>\\`, owned by this patcher alone, and resource tokens are expanded
  after the engine's scan. Nothing is read from the engine's default receipts folder (the upstream PC
  patcher's) or the azydev fork's files.
- **`<work>\\replacements\\`** is emptied before every Install and Check. It is the engine's build
  output and the engine never empties it; a file left there for an asset a game update removed stops
  the next install.
- **The state file** `<work>\\pc\\<game id>\\state.json`: the language installed and, for every file
  the last verified install wrote, the hash it left. Check reads it against the files.
- **Errors**: every failure a player can meet is a `PatchError` with keys from
  `resources/ui/strings.json`.

**Check** (`status`) reports one of four states (`STATES`): installed, not installed, replaced by an
update, partly installed. A game found translated with no receipt of ours (the upstream PC patcher's
or the fork's install) is *foreign*: Install refuses it with the launcher's repair as advice, and
nothing of theirs is imported.

**Install** in another language or from a different patcher version restores from the receipts first.
When a launcher update replaced every translated file, Install checks the updated files and builds a
fresh catalog without carrying over the old patch's texture hashes. A mix of updated and translated
files requires launcher Repair before Install or Remove. A completed restore cancels the earlier
install receipts. The engine keeps them beside its restore receipt until its next run prunes both
(2026-11-20). Each write job cleans up the engine's `<work>\\staged\\` folder, about 4 GB of staged
packages. The receipts hold the originals.

**A job runs in a child process**: the exe re-invoked as
`--pc-job <action> <game> <work> <answer.json> <language>` at low priority, answering through a JSON
file written atomically (`job`). A PC cycle runs the job from source with `--cycle-asset <hash>` after
those five, which turns one `extra_text.CANDIDATE_ASSETS` config bin on for that job (pc-cycle runbook);
the window never passes it. The engine holds the GIL for minutes and would freeze the window.
`--pc-selftest <game copy> <out>` stages both languages against a copy without writing to it.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import shutil
import sys
import time
import traceback
from ctypes import wintypes
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
BUNDLE = Path(getattr(sys, "_MEIPASS", PROJECT / "resources"))
if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(PROJECT / "tools"))  # the exe gets these via PyInstaller --paths
if str(BUNDLE / "runtime") not in sys.path:
    sys.path.append(str(BUNDLE / "runtime"))  # appended, as in patcher_core: the project stdlib wins

import engine_hooks  # noqa: E402
import languages  # noqa: E402
import pc_catalog  # noqa: E402
from ui_strings import PatchError  # noqa: E402

ACTIONS = ("install", "status", "restore")
# Check's four answers, plus the one Install refuses.
INSTALLED, NOT_INSTALLED, REPLACED, PARTLY, FOREIGN = (
    "installed", "not_installed", "replaced_by_update", "partly_installed", "foreign")
STATES = (INSTALLED, NOT_INSTALLED, REPLACED, PARTLY)
STATE_FILE = "state.json"
STATE_SCHEMA = 1
# The engine's own process names (`wxq_patch.installer`), the launcher's, and any other `wxq*.exe`.
LAUNCHER_PROCESS = "王者万象棋.exe"
GAME_PROCESS_PREFIX = "wxq"
SETTINGS_KEY = "pc_game"
BELOW_NORMAL_PRIORITY_CLASS = 0x4000


def _version() -> str:
    for folder in (BUNDLE, PROJECT):
        path = folder / "VERSION"
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()
    return "0"


# ---------------------------------------------------------------------------------------------------
# Finding the game

def find_games(settings: Path | None = None) -> list[Path]:
    """Game roots from the remembered folder and the launcher's records; never a drive search."""
    from wxq_patch import installation

    found: list[Path] = []
    remembered = remembered_game(settings) if settings else None
    if remembered is not None:
        found.append(remembered)
    try:
        records = installation.discover_installations(drives=())
    except OSError:
        records = []
    for record in records:
        path = record.get("path") if isinstance(record, dict) else record
        try:
            root = resolve(Path(path))
        except PatchError:
            continue
        if all(root != known for known in found):
            found.append(root)
    return found


def resolve(folder: Path) -> Path:
    """The game root for a picked folder or `WXQ.exe`, or `PatchError` when it is not the PC edition."""
    from wxq_patch import installation

    try:
        root = installation.resolve_game_root(Path(folder))
    except (OSError, ValueError, RuntimeError):
        root = None
    if not root:
        raise PatchError("pc_game_folder_invalid", path=folder)
    return Path(root)


def remembered_game(settings: Path) -> Path | None:
    try:
        value = json.loads(Path(settings).read_text(encoding="utf-8")).get(SETTINGS_KEY)
        return resolve(Path(value)) if value else None
    except (OSError, ValueError, AttributeError, PatchError):
        return None


def remember_game(settings: Path, game: Path) -> None:
    """Keep <game> in the patcher's settings file beside what the phone target keeps there."""
    try:
        data = json.loads(Path(settings).read_text(encoding="utf-8"))
        data = data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        data = {}
    data[SETTINGS_KEY] = str(game)
    Path(settings).parent.mkdir(parents=True, exist_ok=True)
    Path(settings).write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------------------------------
# The process guard

class _ProcessEntry(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260)]


def running_processes() -> list[str]:
    """Every running process's executable name, through `CreateToolhelp32Snapshot`."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry)]
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = kernel.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if snapshot in (None, wintypes.HANDLE(-1).value):
        raise ctypes.WinError(ctypes.get_last_error())
    names: list[str] = []
    try:
        entry = _ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        more = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            names.append(entry.szExeFile)
            more = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    return names


def blocking_processes(names: list[str] | None = None) -> list[str]:
    """The running game and launcher processes that stop a PC job, by name, sorted."""
    names = running_processes() if names is None else names
    return sorted({name for name in names
                   if name.casefold().startswith(GAME_PROCESS_PREFIX) and name.casefold().endswith(".exe")
                   or name.casefold() == LAUNCHER_PROCESS.casefold()})


def guard() -> None:
    blocking = blocking_processes()
    if blocking:
        raise PatchError("pc_close_game", processes=", ".join(blocking))


# ---------------------------------------------------------------------------------------------------
# Receipts and the state file

TITLE_FILE = Path("WXQ_Data") / "StreamingAssets" / "Config" / "AppTitleName.txt"
GAME_TITLE = "王者万象棋"


def receipts_root(work: Path) -> Path:
    """This patcher's receipts root; each game's receipts go into `<root>/<game id>`."""
    return Path(work) / "pc" / "receipts"


def state_path(work: Path, game: Path) -> Path:
    return Path(work) / "pc" / engine_hooks.game_id(game) / STATE_FILE


def read_state(work: Path, game: Path) -> dict | None:
    try:
        state = json.loads(state_path(work, game).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return state if isinstance(state, dict) and state.get("schema") == STATE_SCHEMA else None


def _write_json(path: Path, value: object) -> None:
    """Write <path> whole or not at all: a sibling temporary file swapped in by `os.replace`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def _sha256(path: Path) -> str | None:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 22), b""):
                digest.update(chunk)
    except FileNotFoundError:
        return None
    return digest.hexdigest()


def _install_receipts(game: Path) -> list[dict]:
    """This patcher's completed install receipts for <game> since its last restore, oldest first.

    Receipt folders are named by their time (`<ns>-<id>`), so they sort in order. A restore leaves the
    install receipts it undid beside its own until the engine's next install or restore prunes them
    (measured 2026-11-20), so a completed restore cancels every install before it.
    """
    folder = receipts_root_for(game)
    receipts: list[dict] = []
    for path in sorted(folder.glob("*/receipt.json")) if folder.is_dir() else ():
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if receipt.get("state") != "complete":
            continue
        if receipt.get("action") == "restore":
            receipts.clear()
        elif receipt.get("action") == "install":
            receipts.append(receipt)
    return receipts


def receipts_root_for(game: Path) -> Path:
    """<game>'s receipts folder, as the hooked engine sees it (`engine_hooks.install` comes first)."""
    from wxq_patch import adaptive

    return Path(adaptive.receipt_root(Path(game)))


def _files_written(receipts: list[dict]) -> dict[str, str | None]:
    """Every file the receipts' installs wrote, with the hash the newest left it at."""
    files: dict[str, str | None] = {}
    for receipt in receipts:
        for item in receipt.get("files", []):
            files[item["relative"]] = item.get("after")
    return files


def _matching(game: Path, files: dict[str, str | None]) -> tuple[list[str], list[str]]:
    """The files of <files> that still hold the recorded hash, and the ones that do not."""
    same, changed = [], []
    for relative, digest in sorted(files.items()):
        path = Path(game) / relative
        live = _sha256(path) if path.is_file() else None
        (same if live == digest else changed).append(relative)
    return same, changed


def title_changed(game: Path) -> bool:
    """Whether the window title file says anything but the game's own title (an earlier fork build)."""
    try:
        text = (Path(game) / TITLE_FILE).read_text(encoding="utf-8-sig").strip()
    except OSError:
        return False
    return text != GAME_TITLE


# ---------------------------------------------------------------------------------------------------
# The jobs

def _empty_replacements(work: Path) -> None:
    """Empty `<work>/replacements/`, the engine's build output; the originals are in the receipts."""
    folder = Path(work) / "replacements"
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True, exist_ok=True)


def _engine(action: str, game: Path, catalog: Path, work: Path) -> dict:
    """`adaptive.run`, with every failure a player can meet turned into a `PatchError`."""
    from wxq_patch import adaptive

    try:
        result = adaptive.run(action, Path(game), Path(catalog), Path(work))
    except PermissionError as error:
        raise PatchError("pc_file_in_use") from error
    except OSError as error:
        if getattr(error, "winerror", None) == 32:
            raise PatchError("pc_file_in_use") from error
        # A full drive: the engine stages whole packages (about 4 GB) in <work> and copies one to %TEMP%
        # to hash it; a failed `shutil` copy carries the WinError only in its text (2026-11-20).
        if getattr(error, "winerror", None) == 112 or "WinError 112" in str(error):
            raise PatchError("pc_disk_full", folder=work) from error
        raise PatchError("pc_engine_failed", detail=error) from error
    except RuntimeError as error:
        text = str(error)
        if text.startswith("No matching restore backup"):
            raise PatchError("pc_no_receipt", "pc_repair_advice") from error
        if text.startswith("Close the game before patching"):
            raise PatchError("pc_close_game", processes=text.partition(":")[2].strip()) from error
        raise PatchError("pc_engine_failed", detail=error) from error
    if not isinstance(result, dict) or result.get("state") == "error":
        detail = result.get("message") if isinstance(result, dict) else result
        raise PatchError("pc_engine_failed", detail=detail)
    return result


def _looks_translated(counts: dict) -> bool:
    """Whether the engine's scan found most known strings already in the target language.

    On the untranslated 2026-11-20 game the scan counts 248321 strings to translate and 32617 already
    English (catalog entries whose text is the same in both); after an install, 0 and 276513.
    """
    return int(counts.get("already_english", 0)) > int(counts.get("translated", 0))


def _bundled_catalog(language: str) -> Path:
    catalog = languages.catalog_dir(BUNDLE, language)
    if not (catalog / "catalog.json.gz").is_file():
        raise PatchError("pc_catalog_missing", language=language)
    return catalog


def _stage(game: Path, work: Path, language: str, state: dict | None, log,
           cycle_assets: frozenset[int] = frozenset()) -> "pc_catalog.Stage":
    _bundled_catalog(language)
    previous = state.get("patched", {}) if state and state.get("language") == language else {}
    return pc_catalog.build(game, BUNDLE, language, work, version=_version(), previous=previous,
                            cycle_assets=cycle_assets, log=log)


def _classify(game: Path, state: dict | None, receipts: list[dict]) -> str:
    """Identify the patch from saved file hashes and the game title."""
    files = (state or {}).get("files") or _files_written(receipts)
    if files:
        same, changed = _matching(game, files)
        if not changed:
            return INSTALLED if state else PARTLY  # receipts with no state: an install cut short
        if same:
            return PARTLY
    if title_changed(game):
        return FOREIGN
    return REPLACED if files else NOT_INSTALLED


def _pending(game: Path) -> bool:
    from wxq_patch import adaptive

    return adaptive.pending_recovery(game)


def _recover_pending(game: Path) -> bool:
    from wxq_patch import adaptive

    if not _pending(game):
        return False
    guard()
    try:
        return bool(adaptive.recover_pending(game))
    except (OSError, RuntimeError, ValueError) as error:
        raise PatchError("pc_engine_failed", detail=error) from error


def check(game: Path, work: Path, language: str, *, log=print, cycle_assets: frozenset[int] = frozenset(),
          quick_status: bool = False) -> dict:
    """Report the game state. The window skips the per-install catalog and coverage report."""
    _empty_replacements(work)
    state = read_state(work, game)
    receipts = _install_receipts(game)
    if _pending(game):
        return {"action": "status", "state": PARTLY, "recoverable": True}
    current = _classify(game, state, receipts)
    recoverable = False
    if current == PARTLY and not (state or {}).get("files"):
        written = _files_written(receipts)
        recoverable = bool(written) and not _matching(game, written)[1]
    answer = {"action": "status", "state": current, "language": (state or {}).get("language"),
              "version": (state or {}).get("version"), "recoverable": recoverable, "counts": {},
              "message": "", "skipped_atlases": []}
    if current in (PARTLY, FOREIGN) or (quick_status and current == INSTALLED):
        return answer
    if quick_status:
        # Foreign install detection uses text counts. The per-install catalog adds asset edits.
        stage = None
        catalog = _bundled_catalog(language)
    else:
        stage = _stage(game, work, language, state if current == INSTALLED else None, log, cycle_assets)
        catalog = stage.catalog
    result = _engine("status", game, catalog, work)
    counts = result.get("counts", {})
    if current in (NOT_INSTALLED, REPLACED) and _looks_translated(counts):
        answer["state"] = FOREIGN
    if stage is not None:
        answer.update(counts=counts, message=result.get("message", ""), skipped_atlases=stage.skipped)
    return answer


def _drop_staged(work: Path) -> None:
    """Remove the engine's staged packages (4 GB) once a job is over; the receipts hold the originals."""
    shutil.rmtree(Path(work) / "staged", ignore_errors=True)


def install(game: Path, work: Path, language: str, *, log=print,
            cycle_assets: frozenset[int] = frozenset()) -> dict:
    """Install a fresh patch, or restore a matching patch before changing language or version."""
    _recover_pending(game)
    state = read_state(work, game)
    receipts = _install_receipts(game)
    written = _files_written(receipts)
    current = _classify(game, state, receipts)
    if current == FOREIGN:
        raise PatchError("pc_foreign_install", "pc_repair_advice")
    if current == PARTLY and ((state or {}).get("files") or not written or _matching(game, written)[1]):
        raise PatchError("pc_receipts_mismatch", "pc_repair_advice")
    if current in (NOT_INSTALLED, REPLACED):
        stage = _stage(game, work, language, None, log, cycle_assets)
        _empty_replacements(work)
        scan = _engine("status", game, stage.catalog, work)
        if _looks_translated(scan.get("counts", {})):
            raise PatchError("pc_foreign_install", "pc_repair_advice")
        if current == REPLACED:
            log("PC edition: the launcher replaced the previous patch; installing against the updated files")
    else:
        previous = (state or {}).get("language"), (state or {}).get("version")
        if not written or _matching(game, written)[1]:
            raise PatchError("pc_receipts_mismatch", "pc_repair_advice")
        if previous != (language, _version()):
            log("PC edition: restoring the previous patch before installing the selected translation")
            _engine("restore", game, languages.catalog_dir(BUNDLE, languages.DEFAULT_LANGUAGE), work)
            state_path(work, game).unlink(missing_ok=True)
            state = None
        stage = _stage(game, work, language, state, log, cycle_assets)
    _empty_replacements(work)
    result = _engine("install", game, stage.catalog, work)
    files = {relative: digest for relative, digest in _files_written(_install_receipts(game)).items()
             if _sha256(Path(game) / relative) == digest}
    if not files:
        raise PatchError("pc_engine_failed", detail=result.get("message", ""))
    _write_json(state_path(work, game), {"schema": STATE_SCHEMA, "version": _version(), "language": language,
                                          "files": files, "patched": stage.patched})
    return {"action": "install", "state": INSTALLED, "language": language, "counts": result.get("counts", {}),
            "message": result.get("message", ""), "skipped_atlases": stage.skipped}


def restore(game: Path, work: Path, *, log=print) -> dict:
    """Remove translation: put back the originals this patcher's receipts hold."""
    recovered = _recover_pending(game)
    written = _files_written(_install_receipts(game))
    same, changed = _matching(game, written)
    if changed or (same and _classify(game, read_state(work, game), []) in (PARTLY, REPLACED)):
        raise PatchError("pc_receipts_mismatch", "pc_repair_advice")
    if not same and not recovered:
        raise PatchError("pc_no_receipt", "pc_repair_advice")
    result = _engine("restore", game, languages.catalog_dir(BUNDLE, languages.DEFAULT_LANGUAGE), work) if same else {}
    state_path(work, game).unlink(missing_ok=True)
    log("PC edition: " + str(result.get("message", "")))
    return {"action": "restore", "state": NOT_INSTALLED, "language": None, "message": result.get("message", "")}


def run(action: str, game: Path, work: Path, language: str, *, log=print,
        cycle_assets: frozenset[int] = frozenset(), quick_status: bool = False) -> dict:
    """One PC job: `install`, `status` (Check) or `restore`, on the game at or under <game>.

    <cycle_assets> is a PC cycle's one candidate config bin (`extra_text.resolve_candidates`), staged
    for Check and Install beside `extra_text.PC_SAFE_ASSETS`.

    Returns a JSON-able answer with ``state`` (one of `STATES`, or `FOREIGN` from Check).
    Check with <quick_status> returns the state without a coverage report.
    Every failure a player can meet raises `PatchError`.
    """
    if action not in ACTIONS:
        raise ValueError(f"unknown PC action {action!r}")
    game, work = resolve(Path(game)), Path(work)
    languages.get(language)
    guard()
    engine_hooks.install(receipts=receipts_root(work), log=log)
    started = time.perf_counter()
    if action == "status":
        answer = check(game, work, language, log=log, cycle_assets=cycle_assets, quick_status=quick_status)
    else:
        try:
            if action == "install":
                answer = install(game, work, language, log=log, cycle_assets=cycle_assets)
            else:
                answer = restore(game, work, log=log)
        finally:
            _drop_staged(work)
    answer["seconds"] = round(time.perf_counter() - started, 1)
    if cycle_assets:
        answer["cycle_assets"] = [f"{asset:016X}" for asset in sorted(cycle_assets)]
    return answer


# ---------------------------------------------------------------------------------------------------
# The child process and the selftest

def job_command(action: str, game: Path, work: Path, answer: Path, language: str) -> list[str]:
    """The command line of a PC job's child: the exe, or `hok_patcher.py` from source."""
    head = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, str(PROJECT / "app" / "hok_patcher.py")]
    return [*head, "--pc-job", action, str(game), str(work), str(answer), language]


def start_job(action: str, game: Path, work: Path, answer: Path, language: str):
    """Start a PC job as a low-priority child with no console; read its answer with `read_answer`."""
    import subprocess

    Path(answer).unlink(missing_ok=True)
    flags = BELOW_NORMAL_PRIORITY_CLASS | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    command = job_command(action, game, work, answer, language)
    if action == "status":
        command.append("--quick-status")
    return subprocess.Popen(command, creationflags=flags,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def read_answer(answer: Path) -> dict:
    """A finished child's answer, or the `PatchError` it raised; a child that left none failed outright."""
    try:
        data = json.loads(Path(answer).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise PatchError("pc_engine_failed", detail=error) from error
    if not data.get("ok"):
        raise PatchError.rebuilt(data.get("keys") or [], data.get("values") or {}, str(data.get("error", "")))
    return data["result"]


def job(action: str, game: str, work: str, answer: str, language: str, *options: str) -> int:
    """`--pc-job`: run one job, log to `<answer>.log`, answer `{"ok": ..., "result" | "keys": ...}` atomically.

    The window passes `--quick-status` for Check. A source job can pass `--cycle-asset <hash>`
    to inspect a candidate.
    """
    try:
        kernel = ctypes.windll.kernel32
        kernel.SetPriorityClass(kernel.GetCurrentProcess(), BELOW_NORMAL_PRIORITY_CLASS)
    except (AttributeError, OSError):
        pass
    answer_path = Path(answer)
    with answer_path.with_name(answer_path.name + ".log").open("w", encoding="utf-8") as log_file:
        def log(line: str) -> None:
            print(line, file=log_file, flush=True)

        sys.stdout = sys.stderr = log_file
        try:
            cycle_assets: frozenset[int] = frozenset()
            quick_status = action == "status" and options == ("--quick-status",)
            if options and not quick_status:
                import extra_text

                if len(options) != 2 or options[0] != "--cycle-asset":
                    raise ValueError(f"unknown PC job options {options!r}")
                cycle_assets = frozenset(extra_text.resolve_candidates(options[1]))
                log("PC cycle: enabling " + ", ".join(f"{asset:016X}" for asset in sorted(cycle_assets)))
            payload = {"ok": True, "result": run(action, Path(game), Path(work), language, log=log,
                                                 cycle_assets=cycle_assets, quick_status=quick_status)}
        except PatchError as error:
            payload = {"ok": False, "keys": list(error.keys), "error": str(error),
                       "values": {name: str(value) for name, value in error.values.items()}}
        except Exception as error:  # noqa: BLE001 - the parent shows it as an engine failure
            traceback.print_exc()
            payload = {"ok": False, "keys": ["pc_engine_failed"], "error": repr(error),
                       "values": {"detail": repr(error)}}
    _write_json(answer_path, payload)
    return 0 if payload["ok"] else 1


def selftest(game: Path, out: Path, cycle_assets: frozenset[int] = frozenset()) -> None:
    """`--pc-selftest <game copy> <out> [--cycle-asset <hash>]`: stage each language and let the engine
    verify it, writing nothing. <cycle_assets> is a PC cycle's candidate, staged as `run` stages it.

    The engine's `stage` action materializes the replacements and checks them without a commit, so the
    copy is never written and no process guard applies. `<out>/pc_selftest.json` has one entry per
    language; a failure's traceback goes to `<out>.log`.
    """
    out.mkdir(parents=True, exist_ok=True)
    report: dict = {"ok": False, "languages": {}}
    with (out.parent / (out.name + ".log")).open("w", encoding="utf-8") as log_file:
        sys.stdout = sys.stderr = log_file
        try:
            root, work = resolve(game), out / "work"
            engine_hooks.install(receipts=receipts_root(work))
            for code in languages.LANGUAGES:
                stage = _stage(root, work, code, None, print, cycle_assets)
                _empty_replacements(work)
                started = time.perf_counter()
                result = _engine("stage", root, stage.catalog, work)
                _drop_staged(work)
                report["languages"][code] = {
                    "counts": result.get("counts", {}), "skipped_atlases": stage.skipped,
                    "packages": [(item.get("package_id"), item.get("replacement_count"))
                                 for item in result.get("stages", [])],
                    "seconds": round(time.perf_counter() - started, 1)}
            report["ok"] = True
        except Exception:  # noqa: BLE001 - the report records the failure
            traceback.print_exc()
    (out / "pc_selftest.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
