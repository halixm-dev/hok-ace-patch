"""Bridge the Android worker to verified private snapshots and the translation engine."""
from __future__ import annotations

from copy import deepcopy
import importlib
import importlib.util
import json
import os
import platform
import hashlib
import runpy
import shutil
import stat
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qts_relocate import UnreachableSlot

# ENGINE_READ_ONLY: the engine folder is the measured producer identity (`files_key`) a run is bound to, so
# this process never writes into it. Importing tools/*.py would otherwise drop tools/__pycache__/*.pyc there
# mid-run (2026-11-12 device cycle: four .pyc files written during the build broke the build's own
# "Engine identity changed" check). EngineAssets.prepare removes such leftovers from older versions.
sys.dont_write_bytecode = True

REQUIRED_CODECS =("lz4.block", "zstandard", "astc_encoder", "texture2ddecoder", "ooz")
# In a session: the build input's rebuilt pristine files, and the delta of the install it stages.
PRISTINE_COPY = "pristine"
SESSION_DELTA = "pristine-delta.bin"
CLEAR_DATA = ("Clear the game's data (Android Settings > Apps > the game > Storage > Clear data), open the "
              "game and let it download again to the login screen, close it, then patch again.")
OTHER_PATCHER = "If the Windows patcher patched this phone last, patch it with that patcher instead."
# The start of the refusal for an in-game update stuck on translated files; the UI offers Re-download on it.
UPDATE_STUCK = "The game's update stopped on translated files"
# The start of the refusal for packages an update rewrote around this patcher's translation; the UI offers
# Re-download on it too.
UPDATE_MIXED = "A game update kept part of this patcher's translation"
# A measured relocation failure, bound to this session's verified inputs; no root cause is assumed.
PACKAGE_UNREACHABLE = "A game package could not be patched safely"
PACKAGE_REFUSED_NAME = "package-refused.json"
# After Re-download: the packages it deleted, kept until the game has downloaded them again.
REDOWNLOAD_NAME = "redownload.json"
# Packages a build over restored or replaced files refused on the text signal: Re-download takes them
# instead of restoring or accepting them again. Cleared once a run or a Re-download completes.
RESTORE_REFUSED_NAME = "restore-refused.json"
# In a session: where `_mixed_packages` tries asset restore, discarded afterwards.
RESTORE_TRIAL = "restore-trial"
# The copy of a package asset restore takes grows by each relocated chunk's slot header and trailer (at
# most 64 bytes with alignment) and is rounded up to the shard's growth step (`qts_relocate.FILE_GROWTH`).
SLOT_OVERHEAD = 64
SHARD_GROWTH = 0x4000
UPDATE_WAITING = "The game has not downloaded the re-downloaded files yet"
# The start of the refusal for a package the game was still downloading when the snapshot was taken;
# the UI shows the update wait on it too.
DOWNLOAD_UNFINISHED = "The game was still downloading game files"
# The start of `plan_redownload`'s refusal when no package is left to delete.
NOTHING_TO_REDOWNLOAD = "No game files hold a translation the patcher cannot rebuild"
# Mixed-package decisions (ticket 17): what `_decide_mixed` concluded for one verified session snapshot,
# kept in this process's memory only and never written to disk, so a restarted worker always decides
# afresh. Keyed by the resolved snapshot folder; each entry carries the proof it was made under
# (`_mixed_proof`) and is reused only while a fresh measurement gives the same proof.
MIXED_DECISION_LIMIT = 4
_MIXED_LOCK = threading.Lock()
_MIXED_DECISIONS: dict[str, dict] = {}
# Counters for the offline probes: decisions computed, reused, recorded, dropped as stale (`invalidated`) or
# not recordable (`unproven`), every restore `_restore_package` ran and the bytes it copied, the bytes the
# proofs hashed, and the seconds `_decide_mixed` took.
MIXED_DECISION_STATS: dict[str, float] = {
    "computed": 0, "reused": 0, "recorded": 0, "invalidated": 0, "unproven": 0,
    "restores": 0, "copied_bytes": 0, "proof_bytes": 0, "decide_seconds": 0.0}


class PatchError(Exception):
    """Expected feasibility failure which can be shown by the Android UI."""


def _prepare(root: Path) -> None:
    if sys.version_info[:2] != (3, 12):
        raise PatchError("The translation runtime requires Python 3.12")
    sys.dont_write_bytecode = True  # see ENGINE_READ_ONLY above; set again in case a caller reset it
    runtime = root / "runtime"
    tools = root / "tools"
    if not runtime.is_dir() or not tools.is_dir():
        raise PatchError("Verified runtime and tools directories are missing")
    # Android stdlib and pip-installed native libraries must precede the desktop bundle.
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    if str(runtime) not in sys.path:
        sys.path.append(str(runtime))
    import lz4.block

    if Path(lz4.block.__file__).is_relative_to(runtime):
        raise PatchError("Desktop LZ4 shadowed Android's native binding")
    pyc = runtime / "wxq_patch" / "__init__.pyc"
    if pyc.read_bytes()[:4] != importlib.util.MAGIC_NUMBER:
        raise PatchError("Consumed runtime bytecode does not match embedded Python")


def _catalog(root: Path, language: str) -> Path:
    """The verified catalog directory for <language>; an unknown code is refused, never defaulted."""
    import languages

    try:
        catalog = languages.catalog_dir(root, language)
    except ValueError as error:
        raise PatchError(str(error)) from error
    if not (catalog / "catalog.json.gz").is_file():
        raise PatchError(f"The {languages.get(language).name} catalog is missing from the engine")
    return catalog


def diagnostics(engine_root: str) -> str:
    """Return real imports and codec operations; unavailable bindings remain explicit gates."""
    root = Path(engine_root).resolve()
    _prepare(root)
    result: dict = {
        "python": sys.version,
        "machine": platform.machine(),
        "bytecode_magic": importlib.util.MAGIC_NUMBER.hex(),
        "codecs": {},
    }
    for name in REQUIRED_CODECS:
        try:
            module = importlib.import_module(name)
            result["codecs"][name] = {"loaded": True, "file": module.__file__}
        except (ImportError, OSError) as error:
            result["codecs"][name] = {"loaded": False, "reason": str(error)}
    import lz4.block
    import zstandard
    from wxq_patch import adaptive

    raw = bytes(range(256)) * 4096
    encoded = lz4.block.compress(raw, store_size=False)
    if lz4.block.decompress(encoded, uncompressed_size=len(raw)) != raw:
        raise PatchError("LZ4 real block round-trip failed")
    if zstandard.ZstdDecompressor().decompress(zstandard.ZstdCompressor().compress(raw)) != raw:
        raise PatchError("Zstandard frame round-trip failed")
    catalog = adaptive.load_catalog(root / "catalog")
    result["catalog_tables"] = len(catalog.known)
    result["catalog_textures"] = len(catalog.graphics)
    import languages

    result["languages"] = {code: len(adaptive.load_catalog(_catalog(root, code)).known)
                           for code in languages.LANGUAGES}
    result["lz4_roundtrip"] = result["zstd_roundtrip"] = True
    result["full_codec_gate"] = all(item["loaded"] for item in result["codecs"].values())
    return json.dumps(result, indent=2)


def engine_preflight(engine_root: str) -> str:
    """Refuse unsupported engine configurations before any access APK installation."""
    result = json.loads(diagnostics(engine_root))
    from package_rebuild import REBUILD_PACKAGES

    if REBUILD_PACKAGES or not result["full_codec_gate"]:
        raise PatchError("Android requires all codecs and an empty package rebuild configuration")
    return json.dumps(result)


def build_scratch(engine_root: str, session_root: str, language: str = "en") -> str:
    """Build in a fresh scratch session; this entry point never accesses live game files."""
    return _build_scratch(Path(engine_root).resolve(), Path(session_root).resolve(), language)


def _build_scratch(root: Path, session: Path, language: str, trusted: Path | None = None) -> str:
    """`build_scratch`. A source inside <trusted>, and the APK, were verified by the caller just before
    and are not hashed again; every other source still is."""
    _prepare(root)
    catalog = _catalog(root, language)
    from package_rebuild import REBUILD_PACKAGES

    if REBUILD_PACKAGES:
        raise PatchError("Android refuses package rebuilds; REBUILD_PACKAGES must be empty")
    for name in REQUIRED_CODECS:
        try:
            importlib.import_module(name)
        except (ImportError, OSError) as error:
            raise PatchError(f"Android codec gate failed: {name}: {error}") from error
    game, apk = session / "game", session / "normal.apk"
    if not game.is_dir() or not apk.is_file():
        raise PatchError("Scratch session requires game/ and a verified matching normal.apk")
    control = json.loads((session / "control.json").read_text(encoding="utf-8"))
    builtin = game / "WXQ_Data" / "Package" / "builtin"
    for name, expected in control["verified_source_files"].items():
        # The layer links into the session's snapshot (and, after a pristine rebuild, its pristine
        # copy), so a source must resolve inside the session rather than inside builtin itself.
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise PatchError("Invalid control input path")
        path = (builtin / name).resolve()
        if not (path.is_relative_to(session) or (trusted is not None and path.is_relative_to(trusted))):
            raise PatchError("Invalid control input path")
        if trusted is not None and path.is_relative_to(trusted):
            continue
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != expected:
            raise PatchError(f"Scratch source differs from desktop control: {name}")
    if trusted is None:
        with apk.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != control["apk"]["sha256"]:
                raise PatchError("Scratch APK differs from desktop control")
    work, output = session / "work", session / "out"
    if work.exists() or output.exists():
        raise PatchError("Use a new scratch session: work/out already exists")
    from build_device_patch import build_patch

    started = time.monotonic()
    with (session / "build.log").open("w", encoding="utf-8") as log_file:
        summary = build_patch(game, catalog, work, output, apk=apk,
                              builder_dir=None, cycle_assets=frozenset(),
                              log=lambda message: print(message, file=log_file, flush=True))
    reported = {str(item["package_id"]) for item in summary["packages"]}
    staged = {item.name for item in output.iterdir() if item.is_dir() and item.name.isdecimal()}
    if staged != reported:
        raise PatchError("Staged package directories do not match the build summary")
    if summary["cycle_assets"]:
        raise PatchError("Android scratch builds cannot enable cycle assets")
    hashes = {}
    for name in sorted(staged):
        for path in sorted((output / name).iterdir()):
            if path.is_file():
                with path.open("rb") as stream:
                    hashes[path.relative_to(output).as_posix()] = hashlib.file_digest(stream, "sha256").hexdigest()
    (session / "staged-hashes.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")
    (session / "metrics.json").write_text(json.dumps({"elapsed_seconds": time.monotonic() - started}), encoding="utf-8")
    return json.dumps(summary)


def graphics_oracle(engine_root: str, session_root: str) -> str:
    """Run the separately supplied development oracle; research is never shipped/imported by the app."""
    root, session = Path(engine_root).resolve(), Path(session_root).resolve()
    _prepare(root)
    oracle = session / "oracle" / "tools" / "research" / "check_graphics.py"
    if not oracle.is_file():
        raise PatchError("Development oracle must be supplied to scratch data separately")
    resources = session / "oracle" / "resources"
    resources.mkdir(parents=True, exist_ok=True)
    for name in ("catalog", "runtime", "sprites"):
        if not (resources / name).exists():
            (resources / name).symlink_to(root / name, target_is_directory=True)
    previous = sys.argv
    try:
        sys.argv = [str(oracle), "--game", str(session / "game")]
        functions = runpy.run_path(str(oracle))
        # Invoke main ourselves so SystemExit cannot kill the embedding process.
        from contextlib import redirect_stdout
        with (session / "graphics.log").open("w", encoding="utf-8", buffering=1) as log, redirect_stdout(log):
            result = functions["main"]()
        if result:
            raise PatchError("Android graphics oracle failed; see scratch graphics.log")
    finally:
        sys.argv = previous
    return "PASS: full catalog and downloaded-layer graphics oracle"


def sign_with_java(engine_root: str, source_path: str, target_path: str, signer) -> str:
    """Keep the existing v2 format while delegating only RSA to the stable-key Java adapter."""
    root = Path(engine_root).resolve()
    _prepare(root)
    from apk_tools import sign_v2

    source, target = Path(source_path).resolve(), Path(target_path).resolve()
    if not source.is_file() or target.exists() or source == target:
        raise PatchError("Signing requires an existing APK and a fresh output path")
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".partial")
    try:
        sign_v2(source, partial, b"", bytes(signer.getCertificateDer()),
                rsa_signer=lambda data: bytes(signer.sign(data)),
                public_key_der=bytes(signer.getPublicKeyDer()))
        import os
        with partial.open("rb+") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
            os.fsync(stream.fileno())
        partial.replace(target)
        descriptor = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        partial.unlink(missing_ok=True)
    return json.dumps({"bytes": target.stat().st_size, "sha256": digest})


def unpack_snapshot(engine_root: str, archive_path: str, destination_path: str,
                    maximum_bytes: int) -> str:
    """Extract only fixed game paths into a fresh app-private recovery snapshot."""
    _prepare(Path(engine_root).resolve())
    from mobile_snapshot import extract_snapshot

    return json.dumps(extract_snapshot(Path(archive_path), Path(destination_path),
                                      maximum_bytes=int(maximum_bytes)))


def unpack_snapshot_stream(engine_root: str, descriptor: int, destination_path: str,
                           maximum_bytes: int) -> str:
    """`unpack_snapshot` from a pipe the privileged tar writes; owns and closes <descriptor>.

    Returns the stream's `bytes` and `sha256`, which the caller compares with what the tar sent.
    """
    with open(int(descriptor), "rb", buffering=0, closefd=True) as stream:
        _prepare(Path(engine_root).resolve())
        from mobile_snapshot import extract_snapshot_stream

        result = extract_snapshot_stream(stream, Path(destination_path), maximum_bytes=int(maximum_bytes))
    return json.dumps({"bytes": result["bytes"], "sha256": result["sha256"],
                       "files": len(result["manifest"]["files"])})


def verify_retained_snapshot(engine_root: str, destination_path: str) -> str:
    """Verify all originals before an interrupted session may roll back game files."""
    _prepare(Path(engine_root).resolve())
    from mobile_snapshot import verify_snapshot

    return json.dumps(verify_snapshot(Path(destination_path)))


def result_counts(engine_root: str, summary_json: str) -> str:
    """Use the desktop's exact four-counter classification for mobile results."""
    _prepare(Path(engine_root).resolve())
    from patch_summary import count_translated, count_untranslated_graphics, count_untranslated_text

    summary = json.loads(summary_json)
    tables, textures = count_translated(summary)
    return json.dumps({"text_tables": tables, "applied_textures": textures,
                       "skipped_tables": count_untranslated_text(summary),
                       "skipped_textures": count_untranslated_graphics(summary)})


def _read_delta(keep: Path) -> "pristine_delta.Delta | None":
    """The pristine delta this patcher kept for the phone, or None."""
    import pristine_delta

    path = keep / pristine_delta.DELTA_NAME
    if not path.is_file():
        return None
    try:
        return pristine_delta.read(path)
    except pristine_delta.DeltaError as error:
        raise PatchError(f"The patcher's record of the untranslated game files is damaged ({error}). "
                         + CLEAR_DATA) from error


def _stuck_packages(session: Path, keep: Path, manifest: dict) -> dict[str, int]:
    """{package: assets the game's updater could not patch} for each package this patcher translated.

    The game's `Watchdog/BrokenList.db` in the snapshot names them. A package counts as translated when
    the kept delta names one of its files, or one of its files is still at a hash this patcher staged.
    """
    import broken_list
    import pristine_delta
    from mobile_snapshot import package_files_at

    listed = broken_list.read(session / "snapshot" / "Watchdog" / "BrokenList.db")
    if not listed.assets:
        return {}
    delta = _read_delta(keep)
    ours = {entry.path.split("/")[0] for entry in delta.files} if delta else set()
    known = pristine_delta.load_staged_hashes(keep / pristine_delta.STAGED_HASHES_NAME)
    ours |= {name.split("/")[0] for name in package_files_at(manifest, known)}
    return {package: len(assets) for package, assets in sorted(listed.assets.items(), key=lambda item: int(item[0]))
            if package in ours}


def _refuse_unfinished_download(packages: Path) -> None:
    """Refuse a snapshot that holds a package folder without its index `<package>.db`.

    The game creates the folder first and writes the index once the package is downloaded: Xiaomi
    M2007J3SG, 2026-10-29, package 1060101007 had no index at the snapshot and a whole one minutes later.
    """
    unfinished = sorted((directory.name for directory in packages.iterdir() if directory.is_dir()
                         and directory.name.isdecimal() and not (directory / f"{directory.name}.db").is_file()),
                        key=int)
    if unfinished:
        raise PatchError(f"{DOWNLOAD_UNFINISHED}: package {', '.join(unfinished)}. Open the game, let it finish "
                         "downloading to the login screen, close it, then patch again.")


def _refuse_stuck_update(session: Path, keep: Path, manifest: dict) -> dict | None:
    """Refuse, before any game file is written, a phone whose in-game update stopped on our files.

    Patching or removing over it leaves the update stuck; the game's own repair cannot converge on a
    translated package (lab notebook, 2026-10-22). `plan_redownload` is the way out.

    Returns the identity of a `REDOWNLOAD_NAME` record whose packages are all back in <manifest>, or None.
    The build only reads the kept folder: it never drops that record itself, since `build_checkpoint`
    binds every kept record byte for the whole build (phone f15a72e, 2026-11-12, run 248572aa). The build
    reports it as `redownload_done`, and finalization drops exactly those bytes (`finalization_plan`).
    """
    from run_artifacts import file_identity

    _refuse_unfinished_download(session / "snapshot" / "packages")
    marker = keep / REDOWNLOAD_NAME
    obsolete = None
    if marker.is_file():
        before = file_identity(marker)
        waiting = [package for package in json.loads(marker.read_text(encoding="utf-8"))["packages"]
                   if not any(name.startswith(f"packages/{package}/") and name.endswith(".db")
                              for name in manifest["files"])]
        if waiting:
            raise PatchError(f"{UPDATE_WAITING}: package {', '.join(waiting)}. Open the game, let it finish the "
                             "update to the login screen, close it, then patch again.")
        if file_identity(marker) != before:
            raise PatchError("The kept Re-download record changed while it was read")
        obsolete = before
    stuck = _stuck_packages(session, keep, manifest)
    if stuck:
        named = ", ".join(f"{package} ({count} assets)" for package, count in stuck.items())
        raise PatchError(f"{UPDATE_STUCK}: package {named}. Re-download the damaged files: the patcher "
                         "deletes only those packages, then open the game, let it finish the update to the "
                         "login screen, close it, and patch again.")
    return obsolete


def _restore_refused(keep: Path) -> set[str]:
    """The packages a build refused on the text signal after restore or replace (`RESTORE_REFUSED_NAME`)."""
    try:
        return set(json.loads((keep / RESTORE_REFUSED_NAME).read_text(encoding="utf-8"))["packages"])
    except (OSError, ValueError, KeyError, TypeError):
        return set()


def _decide_mixed(packages: Path, delta: "pristine_delta.Delta", report: "pristine_delta.RebuildReport",
                  keep: Path, target: Path
                  ) -> tuple[list[str], dict[str, dict[str, str]], dict[str, str], set[str]]:
    """`accept_replaced`, then asset restore into <target>: (accepted files, {package: {file: SHA-256}}
    restored, {package: reason} refused, packages whose restore failed). The one decision
    `_restore_pristine` and `_mixed_packages` share.

    A package an earlier build refused on the text signal (`RESTORE_REFUSED_NAME`) is refused outright,
    whether restore or accept would take it, so Re-download takes it instead.
    """
    import pristine_delta

    started = time.monotonic()
    accepted, restorable, refused = pristine_delta.accept_replaced(packages, delta, report)
    for package in sorted(_restore_refused(keep), key=int):
        ours = [name for name in accepted if name.split("/")[0] == package]
        if ours or package in restorable:
            accepted = [name for name in accepted if name not in ours]
            restorable.pop(package, None)
            refused[package] = "a build over it read translated text"
    taken: dict[str, dict[str, str]] = {}
    failed: set[str] = set()
    for package, reason in restorable.items():
        try:
            taken[package] = _restore_package(packages, target, delta, package)
        except Exception as error:  # noqa: BLE001 - any failure leaves the package to Re-download
            shutil.rmtree(target / package, ignore_errors=True)
            refused[package] = f"{reason}, and restoring them failed ({error})"
            failed.add(package)
    _count("computed")
    _count("decide_seconds", time.monotonic() - started)
    return accepted, taken, refused, failed


def _count(name: str, amount: float = 1) -> None:
    with _MIXED_LOCK:
        MIXED_DECISION_STATS[name] += amount


def _forget_mixed_decisions() -> None:
    """Drop every kept decision, as a worker restart does. For the offline probes."""
    with _MIXED_LOCK:
        _MIXED_DECISIONS.clear()


def _hash_unlinked(path: Path) -> dict | None:
    """{size, sha256} of the regular file <path>, None when it is absent; raises on a link or other kind."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400 or not stat.S_ISREG(info.st_mode):
        raise OSError(f"{path.name} is not a regular file")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    size = path.stat().st_size
    _count("proof_bytes", size)
    return {"size": size, "sha256": digest}


def _engine_files(engine: Path) -> dict[str, dict]:
    """{path: {size, sha256}} for every engine file but Python's own `__pycache__`; raises on any link."""
    files: dict[str, dict] = {}
    for directory, dirs, names in os.walk(engine, followlinks=False):
        dirs[:] = sorted(name for name in dirs if name != "__pycache__")
        for name in dirs:
            info = (Path(directory) / name).lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise OSError(f"{name} is a link")
        for name in sorted(names):
            path = Path(directory) / name
            identity = _hash_unlinked(path)
            if identity is None:
                raise OSError(f"{name} disappeared")
            files[path.relative_to(engine).as_posix()] = identity
    return files


def _mixed_evidence(engine: Path | None, session: Path, keep: Path, manifest: dict | None) -> dict | None:
    """What a mixed-package decision depends on besides its rebuild report, measured now; None when it
    cannot be measured completely, and then nothing is recorded or reused.

    The session's resolved snapshot folder and its complete <manifest> (verified by the caller just before),
    every kept record byte that changes the decision (delta with its kept bodies, staged hashes,
    `restore-refused.json`, `redownload.json`), and every engine file. The bridge's own code, the installed
    patcher and the producer it reports cannot change while this process lives, which is the decision's
    whole lifetime.
    """
    import pristine_delta

    if engine is None or manifest is None:
        return None
    try:
        snapshot = (session / "snapshot").resolve(strict=True)
        records = {name: _hash_unlinked(keep / name)
                   for name in (pristine_delta.DELTA_NAME, pristine_delta.STAGED_HASHES_NAME,
                                RESTORE_REFUSED_NAME, REDOWNLOAD_NAME)}
        return {"schema": 1, "snapshot": str(snapshot), "files": manifest["files"], "records": records,
                "engine": {"root": str(engine), "files": _engine_files(engine)}}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _mixed_proof(evidence: dict | None, report: "pristine_delta.RebuildReport") -> str | None:
    """The key a decision is recorded and reused under: <evidence> plus the complete rebuild report."""
    from run_artifacts import ArtifactError, identity_key

    if evidence is None:
        return None
    try:
        return identity_key({**evidence, "report": {"rebuilt": sorted(report.rebuilt),
                                                    "pristine": sorted(report.pristine),
                                                    "unmatched": dict(sorted(report.unmatched.items()))}})
    except (ArtifactError, ValueError, TypeError):
        return None


def _kept_decision(evidence: dict | None, proof: str | None) -> dict | None:
    """The decision recorded for <evidence>'s snapshot under exactly <proof>, as a copy, or None.

    An entry for the same snapshot under any other proof is stale and dropped.
    """
    if evidence is None or proof is None:
        return None
    with _MIXED_LOCK:
        entry = _MIXED_DECISIONS.get(evidence["snapshot"])
        if entry is None:
            return None
        if entry["proof"] != proof:
            del _MIXED_DECISIONS[evidence["snapshot"]]
            MIXED_DECISION_STATS["invalidated"] += 1
            return None
        return deepcopy(entry)


def _record_decision(evidence: dict | None, proof: str | None, after: dict | None,
                     accepted: list[str], taken: dict, refused: dict[str, str], failed: set[str]) -> None:
    """Keep a freshly computed decision for later calls in this process, when it is safe to.

    Only when its inputs measured the same before and after it was made (<evidence>, <after>), and no
    restore failed: a failed restore may be transient (space, I/O), and reusing it could name more
    packages for Re-download than a fresh decision would.
    """
    if proof is None or after != evidence or failed:
        _count("unproven")
        return
    with _MIXED_LOCK:
        _MIXED_DECISIONS.pop(evidence["snapshot"], None)
        _MIXED_DECISIONS[evidence["snapshot"]] = {
            "proof": proof, "accepted": list(accepted), "refused": dict(refused),
            "restored": sorted(taken, key=int)}
        while len(_MIXED_DECISIONS) > MIXED_DECISION_LIMIT:
            del _MIXED_DECISIONS[next(iter(_MIXED_DECISIONS))]
        MIXED_DECISION_STATS["recorded"] += 1


def _mixed_refusal(report: "pristine_delta.RebuildReport", refused: dict[str, str]) -> PatchError:
    """`UPDATE_MIXED` naming <refused>, as `_restore_pristine` raises it."""
    names = ", ".join(f"{name} ({state})" for name, state in sorted(report.unmatched.items()))
    reasons = "; ".join(f"package {package}: {reason}" for package, reason in refused.items())
    return PatchError(f"{UPDATE_MIXED}: package {', '.join(refused)}. Re-download those packages: the "
                      "patcher deletes only their files, then open the game, let it download them to the "
                      "login screen, close it, and patch again. The game files changed since the last "
                      f"patch (a game update or repair): {names} ({reasons}).")


def _restore_package(packages: Path, target: Path, delta: "pristine_delta.Delta",
                     package: str) -> dict[str, str]:
    """Copy <package> whole under <target> and restore its carried-over assets (ADR 0008).

    Returns {file: SHA-256} for every file of the copy. Raises on anything that does not read back.
    """
    import pristine_delta
    from asset_fingerprints import package_assets

    copy = target / package
    if any(entry.created for entry in delta.files if entry.path.split("/")[0] == package):
        raise pristine_delta.DeltaError("the patch created one of its files")
    recorded = delta.assets[package]
    _count("restores")
    shutil.rmtree(copy, ignore_errors=True)
    copy.mkdir(parents=True)
    for item in (packages / package).iterdir():
        if not item.is_file():
            raise pristine_delta.DeltaError(f"{item.name} is not a file")
        shutil.copyfile(item, copy / item.name)
        _count("copied_bytes", item.stat().st_size)
    pristine_delta.restore_assets(copy, recorded, delta.bodies[package])
    current = package_assets(copy, set(recorded))
    left = [name for name, (_, staged) in recorded.items() if current.get(name) == staged]
    if left:
        raise pristine_delta.DeltaError(f"{len(left)} assets still translated after restore")
    return {f"{package}/{item.name}": pristine_delta.sha256_file(item) for item in sorted(copy.iterdir())}


def _mixed_packages(session: Path, keep: Path, manifest: dict, engine: Path | None = None) -> dict[str, str]:
    """{package: reason} for each package `_restore_pristine` refuses with `UPDATE_MIXED`, or {}.

    The same decision, without keeping the pristine copy: an update rewrote the package's files, but
    this patcher's bytes or translated assets are still in it, and asset restore cannot take it (tried
    on a copy that is then discarded).

    With <engine> (the caller verified <manifest> against the snapshot just before), a decision this
    process already made for the same session snapshot is reused when every input it depended on measures
    the same now (`_mixed_evidence`, the rebuild report); then no trial copy is made. Otherwise the decision
    is made afresh and kept for the next call.
    """
    import pristine_delta
    from mobile_snapshot import package_files_at

    delta = _read_delta(keep)
    if delta is None:
        return {}
    packages = session / "snapshot" / "packages"
    report = pristine_delta.RebuildReport()
    for entry in delta.files:
        state = pristine_delta.classify(entry, packages)
        if state in (pristine_delta.MISSING, pristine_delta.CHANGED):
            report.unmatched[entry.path] = state
        else:
            (report.rebuilt if state == pristine_delta.REBUILT else report.pristine).append(entry.path)
    known = pristine_delta.load_staged_hashes(keep / pristine_delta.STAGED_HASHES_NAME)
    if report.complete or not package_files_at(manifest, known):
        return {}
    evidence = _mixed_evidence(engine, session, keep, manifest)
    proof = _mixed_proof(evidence, report)
    kept = _kept_decision(evidence, proof)
    if kept is not None:
        _count("reused")
        return kept["refused"]
    trial = session / RESTORE_TRIAL
    try:
        accepted, taken, refused, failed = _decide_mixed(packages, delta, report, keep, trial)
    finally:
        shutil.rmtree(trial, ignore_errors=True)
    after = _mixed_evidence(engine, session, keep, manifest) if proof is not None else None
    _record_decision(evidence, proof, after, accepted, taken, refused, failed)
    return refused


def _record_unreachable_slot(engine: Path, session: Path, scratch: Path, keep: Path,
                             manifest: dict, error: UnreachableSlot) -> bool:
    """Bind a real staged-shard relocation failure to its source snapshot and current producer.

    This is evidence for a plan, never deletion consent. Keep it in the parent session so resetting
    the failed build attempt cannot lose it. A prime-only package with no snapshot file is not eligible.
    """
    from mobile_snapshot import verify_snapshot
    from pristine_delta import write_atomic
    from run_artifacts import identity_key

    path = error.path.absolute()
    package = path.parent.name
    shard_id = path.name.removeprefix(f"{package}_").removesuffix(".db")
    if (not package.isascii() or not package.isdecimal() or str(int(package)) != package
            or not shard_id.isascii() or not shard_id.isdecimal()
            or path.name != f"{package}_{shard_id}.db"
            or path.parent != scratch / "out" / package
            or not path.resolve().is_relative_to(scratch.resolve())
            or f"packages/{package}/{path.name}" not in manifest["files"]
            or verify_snapshot(session / "snapshot") != manifest):
        return False
    evidence = _mixed_evidence(engine, session, keep, manifest)
    if evidence is None:
        return False
    write_atomic(session / PACKAGE_REFUSED_NAME, json.dumps({"schema": 1,
        "evidence": identity_key(evidence), "packages": {package: str(error)}}).encode("utf-8"))
    return True


def _unreachable_packages(engine: Path, session: Path, keep: Path, manifest: dict) -> dict[str, str]:
    """Read measured failures only for exactly the same snapshot, engine and kept records."""
    from run_artifacts import ArtifactError, identity_key, read_record

    marker = session / PACKAGE_REFUSED_NAME
    if not marker.exists():
        return {}
    try:
        record = read_record(marker)
        packages = record["packages"]
        if (set(record) != {"schema", "evidence", "packages"} or record["schema"] != 1
                or not isinstance(packages, dict) or not packages
                or any(not name.isascii() or not name.isdecimal() or str(int(name)) != name
                       or not isinstance(reason, str) or not reason
                       or not any(path.startswith(f"packages/{name}/") for path in manifest["files"])
                       for name, reason in packages.items())):
            return {}
        evidence = _mixed_evidence(engine, session, keep, manifest)
        return packages if evidence is not None and record["evidence"] == identity_key(evidence) else {}
    except (ArtifactError, OSError, ValueError, KeyError, TypeError):
        return {}


def _graphics_candidates(engine: Path) -> set[int]:
    """Both catalogs' texture targets, with measured aliases and the repo's atlas labels."""
    import mobile_graphics
    from wxq_patch import adaptive

    wanted = set(mobile_graphics.LABEL_ATLASES)
    for language in ("en", "id"):
        catalog = adaptive.load_catalog(_catalog(engine, language))
        wanted.update(mobile_graphics.catalog_graphics(catalog.graphics))
    return wanted


def _inspect_graphics_packages(engine: Path, session: Path, keep: Path, manifest: dict,
                               excluded: set[str]) -> dict[str, str]:
    """Find unreachable texture slots before review, even when mixed data prevented staging.

    The verified snapshot stays read-only. A suspect package the delta knows is rebuilt/restored
    in a disposable copy and checked again, so a recoverable translated file is not deleted just
    because its current slot map is damaged. Already selected packages need no further inspection.
    No new failure record is kept: this measurement is part of the exact plan itself.
    """
    from dataclasses import replace
    import tempfile
    import pristine_delta
    from qts_relocate import install_btree_slot_map, unreachable_slots
    from wxq_patch.qtsvfs import QtsPackage

    wanted = _graphics_candidates(engine)
    if not wanted:
        return {}
    install_btree_slot_map()
    packages = session / "snapshot" / "packages"
    # `packages/builtin/Globalindex/` is the game's global index, not a package (Redmi 2312DRA50G, 2026-11-13).
    names = {part for name in manifest["files"] if name.startswith("packages/")
             and (part := name.split("/")[1]).isascii() and part.isdecimal()}
    delta = None
    delta_loaded = False
    refused = {}
    for name in sorted(names - excluded, key=int):
        source = packages / name
        try:
            failures = unreachable_slots(QtsPackage(source), wanted)
            if not failures:
                continue
            if not delta_loaded:
                delta = _read_delta(keep)
                delta_loaded = True
            entries = tuple(item for item in delta.files if item.path.split("/")[0] == name) if delta else ()
            if entries:
                local = replace(delta, files=entries)
                with tempfile.TemporaryDirectory(prefix="redownload-inspection-", dir=session) as folder:
                    target = Path(folder)
                    shutil.copytree(source, target / name)
                    report = pristine_delta.rebuild(packages, local, target)
                    if not report.complete:
                        _accepted, _taken, mixed, _failed = _decide_mixed(packages, local, report, keep, target)
                        if mixed:
                            refused[name] = mixed[name]
                            continue
                    failures = unreachable_slots(QtsPackage(target / name), wanted)
            if failures:
                refused[name] = f"{failures[0]}; {len(failures)} unreachable texture chunks"
        except Exception as error:  # noqa: BLE001 - never turn an incomplete scan into a partial deletion plan
            raise PatchError(f"Re-download inspection could not finish package {name}: {error}") from error
    return refused


def plan_redownload(engine_root: str, session_root: str, keep_root: str, plan_root: str | None = None) -> str:
    """Re-download damaged files: name the package files to delete so the game downloads them again.

    The packages are those `_stuck_packages` names ({package: broken assets}) and those `_mixed_packages`
    names ({package: reason}), plus current measured relocation failures and a read-only texture-slot
    inspection of the remaining packages, in one run. Suspect packages the delta can rebuild or restore
    are checked in a disposable copy first. An update that sticks on package `1` has already merged
    around the translation in the others (lab notebook, 2026-10-23), and they would otherwise refuse the
    next Start for a second Re-download. Every file of each is staged for deletion; `staged-hashes.json`
    holds each one's snapshot SHA-256, which is what rollback writes back. Measured on 2026-10-22 and
    2026-10-23 (in two runs, before the plan took both in one): with the packages deleted and `Watchdog`
    cleared, the game downloaded them and finished the update. Refuses, before any game file is changed,
    when no package is stuck, mixed or named by a current measured relocation failure.

    <plan_root>, when given, is a fresh folder the completed plan is kept in instead of the session
    itself (`redownload_plan`). Disposable inspection copies under the session are removed on exit.
    """
    summary, _ = _plan_redownload(engine_root, session_root, keep_root, plan_root)
    return json.dumps(summary)


def _plan_redownload(engine_root: str, session_root: str, keep_root: str,
                     plan_root: str | None) -> tuple[dict, dict]:
    """`plan_redownload`'s work: (summary, verified snapshot manifest)."""
    root, session, keep = Path(engine_root).resolve(), Path(session_root).resolve(), Path(keep_root).resolve()
    _prepare(root)
    from mobile_snapshot import verify_snapshot

    manifest = verify_snapshot((session / "snapshot").resolve())
    target = session
    if plan_root:
        target = Path(plan_root).resolve()
        if target.parent.parent != session or target.parent.name != "redownload-plans":
            raise PatchError("A Re-download plan belongs in its own session folder")
        target.mkdir(parents=True, exist_ok=False)
    output = target / "out"
    if output.exists() or (target / "staged-hashes.json").exists():
        raise PatchError("Re-download requires a fresh session layout")
    packages = _unreachable_packages(root, session, keep, manifest)
    packages.update({package: f"{count} assets the game could not patch"
                     for package, count in _stuck_packages(session, keep, manifest).items()})
    # Both inspections must finish before presenting the combined scope. An unknown mixed-package
    # result must not be silently omitted just because another package already needs Re-download.
    mixed = _mixed_packages(session, keep, manifest, engine=root)
    packages = {**mixed, **packages}
    packages.update(_inspect_graphics_packages(root, session, keep, manifest, set(packages)))
    if not packages:
        raise PatchError(f"{NOTHING_TO_REDOWNLOAD}, so there is nothing to "
                         "re-download. Open the game, let it finish its update, close it, then patch again.")
    hashes = {}
    for name, entry in manifest["files"].items():
        parts = name.split("/")
        if len(parts) == 3 and parts[0] == "packages" and parts[1] in packages:
            hashes[f"{parts[1]}/{parts[2]}"] = entry["sha256"]
    summary = {"redownload": sorted(hashes, key=lambda name: (int(name.split("/")[0]), name)),
               "packages": packages}
    output.mkdir()
    (output / "device_patch_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (target / "staged-hashes.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")
    return summary, manifest


def redownload_plan(engine_root: str, session_root: str, keep_root: str, plan_root: str) -> str:
    """Measure the exact Re-download scope into the fresh folder <plan_root>; no game file is changed.

    Returns what Kotlin binds the user's approval to, beside its own snapshot, engine and APK evidence:
    `packages` ({package: reason}), `files` ({"packages/<file>": {sha256, bytes}}, every file deleted),
    `watchdog` ({"Watchdog/<file>": {sha256, bytes}}, the update records the run clears), `delta` (the
    kept delta's identity) and `records` (the kept files that change which packages are named). The
    deletion itself reads `staged-hashes.json` in <plan_root>, which Kotlin checks against `files`.
    """
    summary, manifest = _plan_redownload(engine_root, session_root, keep_root, plan_root)
    keep = Path(keep_root).resolve()
    entries = manifest["files"]
    files = {f"packages/{name}": {"sha256": entries[f"packages/{name}"]["sha256"],
                                  "bytes": entries[f"packages/{name}"]["bytes"]} for name in summary["redownload"]}
    watchdog = {name: {"sha256": entry["sha256"], "bytes": entry["bytes"]}
                for name, entry in sorted(entries.items()) if name.startswith("Watchdog/")}
    return json.dumps({"packages": summary["packages"], "files": files, "watchdog": watchdog,
                       "delta": _delta_identity(keep), "records": _redownload_records(keep)})


def _redownload_records(keep: Path) -> dict:
    """{name: file identity or None} for the kept records that change which packages a plan names."""
    from run_artifacts import file_identity

    return {name: file_identity(keep / name) if (keep / name).is_file() else None
            for name in (REDOWNLOAD_NAME, RESTORE_REFUSED_NAME)}


def redownload_evidence(engine_root: str, keep_root: str) -> str:
    """The kept delta's identity and records now, as `redownload_plan` binds them; nothing is written.

    Kotlin checks an approved plan against them before it deletes anything, and again when an interrupted
    deletion resumes.
    """
    _prepare(Path(engine_root).resolve())
    keep = Path(keep_root).resolve()
    return json.dumps({"delta": _delta_identity(keep), "records": _redownload_records(keep)})


def _own_legacy_build(session: Path) -> None:
    """Persist ownership before creating any fresh build products."""
    from pristine_delta import write_atomic
    marker = session / "build-owner.json"
    if marker.exists():
        raise PatchError("An earlier build attempt requires explicit reset")
    if any((session / name).exists() or (session / name).is_symlink()
           for name in ("game", "out", "work", PRISTINE_COPY, "normal.apk", "control.json",
                        "staged-hashes.json", SESSION_DELTA)):
        raise PatchError("Build products already exist without this attempt ownership")
    write_atomic(marker, json.dumps({"schema": 1, "session": str(session),
                                    "kind": "bridge-build"}).encode("utf-8"))


def clear_build(session_root: str) -> str:
    """Reset only an owned incomplete legacy build, preserving all recovery material.

    Caller holds coordinator ownership and must not reset products referenced by apply/recovery.
    A present receipt (even damaged) is retained for diagnosis; it never licenses cleanup.
    """
    from run_artifacts import read_record
    session = Path(session_root).absolute()
    if (session / "build-receipt.json").exists() or (session / "out/build-receipt.json").exists():
        raise PatchError("A published build cannot be reset")
    owner = session / "build-owner.json"
    if not owner.exists() and not owner.is_symlink():
        raise PatchError("No build ownership to reset")
    if read_record(owner) != {
            "schema": 1, "session": str(session), "kind": "bridge-build"}:
        raise PatchError("Build ownership differs")
    _remove_build_products(session)
    (session / "build-owner.json").unlink()
    return "{}"


def _remove_build_products(session: Path) -> None:
    """Fixed build-only allowlist; never traverse a linked directory root."""
    for name in ("game", "out", "work", PRISTINE_COPY):
        path = session / name
        if path.is_symlink() or getattr(path.lstat() if path.exists() else None,
                                       "st_file_attributes", 0) & 0x400:
            raise PatchError("Refusing a linked build directory")
    for name in ("game", "out", "work", PRISTINE_COPY):
        path = session / name
        if path.exists():
            shutil.rmtree(path)
    for name in ("normal.apk", "control.json", "staged-hashes.json", SESSION_DELTA,
                 "metrics.json", "build.log"):
        (session / name).unlink(missing_ok=True)


def keep_redownload(engine_root: str, session_root: str, keep_root: str, plan_root: str | None = None) -> str:
    """Once a Re-download run completes, remember its packages until the game downloads them again.

    Until then a patch or removal would read a layer without them, so `_refuse_stuck_update` refuses it.
    <plan_root> is the plan's own folder (`redownload_plan`); without it the session's legacy layout.
    Returns the package count and the written record's identity, which Kotlin keeps in the journal so a
    resumed deletion of the same plan recognises its own record.
    """
    _prepare(Path(engine_root).resolve())
    import pristine_delta
    from run_artifacts import file_identity

    session, keep = Path(session_root).resolve(), Path(keep_root).resolve()
    source = Path(plan_root).resolve() if plan_root else session
    if plan_root and (source.parent.parent != session or source.parent.name != "redownload-plans"):
        raise PatchError("A Re-download plan belongs in its own session folder")
    summary = json.loads((source / "out" / "device_patch_summary.json").read_text(encoding="utf-8"))
    keep.mkdir(parents=True, exist_ok=True)
    pristine_delta.write_atomic(keep / REDOWNLOAD_NAME,
                                json.dumps({"packages": sorted(summary["packages"], key=int)}).encode("utf-8"))
    (keep / RESTORE_REFUSED_NAME).unlink(missing_ok=True)  # the game downloads those packages afresh
    return json.dumps({"packages": len(summary["packages"]), "record": file_identity(keep / REDOWNLOAD_NAME)})


def estimate_snapshot_build(engine_root: str, session_root: str, normal_apk: str,
                            language: str = "en", keep_root: str | None = None) -> str:
    """Read verified snapshot and APK metadata before creating any build work/output.

    With a kept pristine delta (<keep_root>), the build input's copy of the files it names is reserved
    too: `build_snapshot` rebuilds them beside the snapshot, which keeps the phone's actual bytes.
    """
    root, session = Path(engine_root).resolve(), Path(session_root).resolve()
    _prepare(root)
    from mobile_snapshot import read_manifest
    from build_storage import estimate

    catalog = _catalog(root, language)
    # Sizes only: `build_snapshot`, which runs next, verifies every file before the build reads it.
    manifest = read_manifest(session / "snapshot")
    _refuse_unfinished_download(session / "snapshot" / "packages")
    delta = _read_delta(Path(keep_root)) if keep_root else None
    copy_bytes = _copy_bytes(delta, manifest)
    return json.dumps(estimate(session / "snapshot/packages", catalog, Path(normal_apk), manifest,
                               scratch=session, pristine_copy_bytes=copy_bytes))


def _copy_bytes(delta: "pristine_delta.Delta | None", manifest: dict | None) -> int:
    """The most the session's pristine copy can hold: every file the delta rebuilds, except that a
    package asset restore may take (one with kept bodies whose files an update changed, by the
    snapshot's <manifest>) counts as a whole copy of it grown by its kept chunks. Without <manifest>,
    every package with kept bodies counts as its larger side plus those chunks."""
    if delta is None:
        return 0
    total = sum(entry.pristine_size for entry in delta.files)
    for package, kept in (delta.bodies or {}).items():
        if not kept:
            continue
        entries = [entry for entry in delta.files if entry.path.split("/")[0] == package]
        if manifest is None:
            total += sum(max(entry.staged_size, entry.pristine_size) for entry in entries)
        else:
            listed = {name.removeprefix("packages/"): item for name, item in manifest["files"].items()
                      if name.startswith(f"packages/{package}/")}
            if all(listed.get(entry.path, {}).get("sha256") in (entry.staged_sha256, entry.pristine_sha256)
                   for entry in entries):
                continue  # the delta rebuilds the package whole
            # Restore copies the package whole in place of the files the rebuild would write.
            total += sum(item["bytes"] for item in listed.values()) - sum(entry.pristine_size for entry in entries)
        # Each relocated chunk also takes a slot header and trailer, and the shard grows in 16 KiB steps.
        chunks = sum(len(body.chunks) for body in kept.values())
        total += delta.package_body_bytes(package) + SLOT_OVERHEAD * chunks + SHARD_GROWTH
    return total


def _restore_pristine(session: Path, keep: Path, manifest: dict | None = None,
                      engine: Path | None = None) -> dict:
    """Rebuild the files the kept delta names into the session's build-input copy, or refuse.

    Returns `{"mode": "rebuilt" | "first", "rebuilt": [...], "pristine": [...], "sha256": {...}}`, the
    last naming the pristine SHA-256 of every file the copy holds. `replaced` names the files a game
    update rewrote that `pristine_delta.accept_replaced` takes as the new pristine: the build reads them
    from the snapshot, and the text signal must then pass. A package it calls restorable is copied
    whole and its carried-over assets written back (`pristine_delta.restore_assets`, ADR 0008):
    `assets_restored` names each such package's files restore changed ({package: [files]}), the copy
    holds every file of it, and the text signal must pass too. Raises PatchError, before any game file
    is written, when the snapshot is neither at the delta's staged bytes nor at pristine and no update
    replaced it cleanly or restore could not take it (`UPDATE_MIXED`, naming only those packages).
    <manifest> is the snapshot's, verified by the caller just before; without it the snapshot's package
    files are hashed here. With both <manifest> and <engine>, the mixed-package decision is kept for, and
    may come from, `_mixed_packages` and later calls on the same session snapshot (`_mixed_evidence`).
    """
    import pristine_delta
    from mobile_snapshot import package_files_at

    packages = session / "snapshot" / "packages"
    known = pristine_delta.load_staged_hashes(keep / pristine_delta.STAGED_HASHES_NAME)

    def files_at() -> list[str]:
        return (package_files_at(manifest, known) if manifest is not None
                else pristine_delta.files_at(packages, known))

    Layer = pristine_delta.Layer
    delta = _read_delta(keep)
    if delta is None:
        if pristine_delta.layer_verdict(files_at(), None).kind is Layer.NO_RECORD:
            raise PatchError("This phone is already translated, and the patcher cannot rebuild its "
                             "untranslated game files. " + CLEAR_DATA)
        return {"mode": "first", "rebuilt": [], "pristine": [], "sha256": {}}
    copy = session / PRISTINE_COPY
    if copy.exists():
        raise PatchError("Snapshot build requires a fresh session layout")
    translated = files_at()
    report = pristine_delta.rebuild(packages, delta, copy)
    verdict = pristine_delta.layer_verdict(translated, report)
    if verdict.kind is Layer.STALE:
        # Nothing this patcher wrote is left, as after clearing the game's data and downloading a newer
        # version: the delta describes a layer that is gone, and the text signal decides instead.
        shutil.rmtree(copy, ignore_errors=True)
        return {"mode": "first", "rebuilt": [], "pristine": [], "sha256": {}, "stale": len(report.unmatched)}
    replaced: list[str] = []
    taken: dict[str, dict[str, str]] = {}
    if verdict.kind is Layer.MIXED:
        # A refusal this process already proved for the same session snapshot and inputs is raised again
        # without trying restore; a decision that took every package is always made afresh, since the
        # build needs the restored copies themselves.
        evidence = _mixed_evidence(engine, session, keep, manifest)
        proof = _mixed_proof(evidence, report)
        kept = _kept_decision(evidence, proof)
        if kept is not None and kept["refused"]:
            _count("reused")
            raise _mixed_refusal(report, kept["refused"])
        # Restore is tried even when another package refuses, so the refusal names exactly what
        # `_mixed_packages` does.
        replaced, taken, refused, failed = _decide_mixed(packages, delta, report, keep, copy)
        after = _mixed_evidence(engine, session, keep, manifest) if proof is not None else None
        _record_decision(evidence, proof, after, replaced, taken, refused, failed)
        verdict = pristine_delta.layer_verdict(translated, report, refused)
        if verdict.kind is Layer.CHANGED:
            raise _mixed_refusal(report, refused)
    if verdict.kind is Layer.UNCOVERED:
        raise PatchError(f"Translated game files the patcher has no record of: {', '.join(verdict.names)}. "
                         + CLEAR_DATA)
    sha256 = {entry.path: entry.pristine_sha256 for entry in delta.files
              if not entry.created and entry.path not in replaced}
    restored_files: dict[str, list[str]] = {}
    for package, hashes in taken.items():
        sha256.update(hashes)
        restored_files[package] = [name for name, digest in hashes.items() if digest != (
            manifest["files"][f"packages/{name}"]["sha256"] if manifest is not None
            else pristine_delta.sha256_file(packages / name))]
    return {"mode": "rebuilt", "rebuilt": report.rebuilt, "pristine": report.pristine, "replaced": replaced,
            "sha256": sha256, "assets_restored": restored_files,
            "deleted": [entry.path for entry in delta.files if entry.created and entry.path not in replaced]}


def _restored_files(restored: dict) -> list[str]:
    """The files asset restore changed, from `_restore_pristine`'s result."""
    return [name for names in restored.get("assets_restored", {}).values() for name in names]


def _link_build_input(session: Path, builtin: Path, restored: dict) -> None:
    """The build's layer: the snapshot, with every file the delta names read from the pristine copy."""
    snapshot, copy = session / "snapshot" / "packages", session / PRISTINE_COPY
    replaced = set(restored["sha256"]) | set(restored.get("deleted", []))
    touched = {name.split("/")[0] for name in replaced}
    builtin.mkdir(parents=True)
    for entry in snapshot.iterdir():
        if entry.name not in touched:
            (builtin / entry.name).symlink_to(entry, target_is_directory=entry.is_dir())
            continue
        (builtin / entry.name).mkdir()
        for item in entry.iterdir():
            name = f"{entry.name}/{item.name}"
            if name in replaced:
                continue
            (builtin / name).symlink_to(item, target_is_directory=item.is_dir())
    for name in restored["sha256"]:
        (builtin / name).symlink_to(copy / name)


def build_snapshot(engine_root: str, session_root: str, normal_apk: str,
                   expected_apk_sha256: str, language: str = "en", keep_root: str | None = None) -> str:
    """Build a retained, rehashed snapshot using the independently verified recovery APK.

    With <keep_root>, the patcher's pristine delta first rebuilds the files it names into the session's
    build-input copy (the snapshot keeps the phone's bytes for rollback), the build reads that pristine
    layer, and the delta of the staged install is written to the session for `keep_delta`. With no
    delta kept, a layer the text pass does not read as pristine is refused. Every refusal comes before
    any game file is written.
    """
    root, session, apk = Path(engine_root).resolve(), Path(session_root).resolve(), Path(normal_apk).resolve()
    _prepare(root)
    from mobile_snapshot import verify_snapshot

    manifest = verify_snapshot((session / "snapshot").resolve())
    with apk.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != expected_apk_sha256:
        raise PatchError("Recovery APK changed before snapshot build")
    game = session / "game"
    builtin = game / "WXQ_Data" / "Package" / "builtin"
    if game.exists() or (session / "normal.apk").exists() or (session / "control.json").exists():
        raise PatchError("Snapshot build requires a fresh session layout")
    _own_legacy_build(session)
    redownload_done = _refuse_stuck_update(session, Path(keep_root), manifest) if keep_root else None
    restored = (_restore_pristine(session, Path(keep_root), manifest, engine=root) if keep_root
                else {"mode": "first", "rebuilt": [], "pristine": [], "sha256": {}})
    builtin.parent.mkdir(parents=True)
    if restored["mode"] == "rebuilt":
        _link_build_input(session, builtin, restored)
    else:
        builtin.symlink_to(session / "snapshot" / "packages", target_is_directory=True)
    (session / "normal.apk").symlink_to(apk)
    sources = {name.removeprefix("packages/"): entry["sha256"]
               for name, entry in manifest["files"].items() if name.startswith("packages/")}
    sources.update(restored["sha256"])
    for name in restored.get("deleted", []):
        sources.pop(name, None)
    control = {"verified_source_files": sources, "apk": {"sha256": expected_apk_sha256}}
    (session / "control.json").write_text(json.dumps(control), encoding="utf-8")
    # The snapshot files and the APK were verified above; only the pristine copy is hashed again.
    summary = json.loads(_build_scratch(root, session, language, trusted=(session / "snapshot").resolve()))
    if keep_root is None:
        return json.dumps(summary)
    import pristine_delta

    restored_packages = sorted(restored.get("assets_restored", {}), key=int)
    if restored.get("replaced") or restored_packages:
        reason = pristine_delta.text_not_pristine(summary)
        if reason and restored_packages:
            # Restore read back, yet the layer is not pristine. The text pass does not say which package
            # holds the text, so Re-download takes every package restored or replaced instead.
            suspects = set(restored_packages) | {name.split("/")[0] for name in restored["replaced"]}
            keep = Path(keep_root)
            named = sorted(_restore_refused(keep) | suspects, key=int)
            pristine_delta.write_atomic(keep / RESTORE_REFUSED_NAME, json.dumps({"packages": named}).encode("utf-8"))
            raise PatchError(f"{UPDATE_MIXED}: package {', '.join(sorted(suspects, key=int))}. Re-download those "
                             "packages: the patcher deletes only their files, then open the game, let it download "
                             "them to the login screen, close it, and patch again. The patcher wrote the original "
                             f"bytes back into package {', '.join(restored_packages)}, but the build still read "
                             f"translated text ({reason}).")
        if reason:
            raise PatchError(f"The game update left some of this patcher's translation in the files it changed "
                             f"({reason}), so the patcher cannot rebuild the untranslated files. " + CLEAR_DATA)
    if restored["mode"] == "first":
        reason = pristine_delta.text_not_pristine(summary)
        if reason:
            raise PatchError(f"This phone is already translated ({reason}), by an older patcher version or "
                             "another patcher, so the patcher cannot switch or update the translation "
                             "without its untranslated game files. " + CLEAR_DATA + " " + OTHER_PATCHER)
    output = session / "out"
    hashes = json.loads((session / "staged-hashes.json").read_text(encoding="utf-8"))
    # A file the previous install translated and this build leaves alone goes back to pristine too, and
    # so does a file asset restore changed.
    untranslated = [name for name in [*restored["rebuilt"], *_restored_files(restored)]
                    if name not in hashes]
    for name in untranslated:
        (output / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(session / PRISTINE_COPY / name, output / name)
        hashes[name] = restored["sha256"][name]
    (session / "staged-hashes.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")
    delta = pristine_delta.make(builtin, output, info={
        "patcher": "android", "language": summary.get("language", language),
        "made": time.strftime("%Y-%m-%dT%H:%M:%S")}, fingerprint=True)
    pristine_delta.write(delta, session / SESSION_DELTA)
    summary["pristine"] = {"mode": restored["mode"], "rebuilt": len(restored["rebuilt"]),
                           "already_pristine": len(restored["pristine"]), "restored": untranslated,
                           "delta_bytes": delta.range_bytes, "stale": restored.get("stale", 0),
                           "replaced": restored.get("replaced", []),
                           "assets_restored": sorted(restored.get("assets_restored", {}), key=int)}
    if redownload_done is not None:
        summary["redownload_done"] = redownload_done
    return json.dumps(summary)


def removal_bytes(engine_root: str, keep_root: str, session_root: str | None = None) -> int:
    """The pristine bytes `build_removal` will rebuild: what Remove translation must reserve.

    With <session_root>, its snapshot's manifest says which packages asset restore may copy.
    """
    _prepare(Path(engine_root).resolve())
    from mobile_snapshot import read_manifest

    manifest = read_manifest(Path(session_root).resolve() / "snapshot") if session_root else None
    return _copy_bytes(_read_delta(Path(keep_root)), manifest)


def build_removal(engine_root: str, session_root: str, keep_root: str) -> str:
    """Remove translation: stage the rebuilt pristine files as the session's output, with no new patch.

    The apply writes `out/` exactly as it writes a translation, with `snapshot/` as its rollback, and
    the session's delta is empty, so once the run completes `keep_delta` deletes the patcher's delta:
    the phone's files are pristine, and the next patch run is a first install. Refuses, before any game file is written, when the snapshot cannot be
    rebuilt or this patcher has no record of a translation on it.
    """
    root, session, keep = Path(engine_root).resolve(), Path(session_root).resolve(), Path(keep_root).resolve()
    _prepare(root)
    import pristine_delta
    from mobile_snapshot import verify_snapshot

    manifest = verify_snapshot((session / "snapshot").resolve())
    output = session / "out"
    if output.exists() or (session / "staged-hashes.json").exists():
        raise PatchError("Removal requires a fresh session layout")
    _own_legacy_build(session)
    redownload_done = _refuse_stuck_update(session, keep, manifest)
    restored = _restore_pristine(session, keep, manifest, engine=root)
    if restored["mode"] != "rebuilt":
        raise PatchError("This patcher has no record of a translation on this phone, so there is nothing "
                         "to remove. " + OTHER_PATCHER)
    if restored.get("deleted"):
        raise PatchError("Removing a package file the patch created is not supported")
    restored_files = _restored_files(restored)
    if not restored["rebuilt"] and not restored_files:
        raise PatchError("The game files are already untranslated; there is nothing to remove.")
    hashes = {}
    for name in [*restored["rebuilt"], *restored_files]:
        (output / name).parent.mkdir(parents=True, exist_ok=True)
        (session / PRISTINE_COPY / name).replace(output / name)
        hashes[name] = restored["sha256"][name]
    summary = {"language": None, "counts": {}, "skipped_count": 0, "fit_only": False, "packages": [],
               "text_skipped": [], "graphics_skipped": [], "append_skipped": [], "cycle_assets": [],
               "removed": sorted(hashes)}
    (output / "device_patch_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (session / "staged-hashes.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")
    pristine_delta.write(pristine_delta.Delta((), {"patcher": "android", "removed": True,
                                                   "made": time.strftime("%Y-%m-%dT%H:%M:%S")}),
                         session / SESSION_DELTA)
    summary["pristine"] = {"mode": "removed", "rebuilt": len(hashes),
                           "already_pristine": len(restored["pristine"]), "restored": sorted(hashes),
                           "assets_restored": sorted(restored.get("assets_restored", {}), key=int)}
    if redownload_done is not None:
        summary["redownload_done"] = redownload_done
    return json.dumps(summary)


def keep_delta(engine_root: str, session_root: str, keep_root: str) -> str:
    """Make the session's delta the patcher's own, once its install is verified complete.

    An empty delta (Remove translation) deletes the patcher's delta instead: the phone's files are
    pristine, so the next run is a first install under both pristine signals.
    """
    _prepare(Path(engine_root).resolve())
    import pristine_delta

    session, keep = Path(session_root).resolve(), Path(keep_root).resolve()
    delta = pristine_delta.read(session / SESSION_DELTA)
    if (session / "bridge-summary.json").exists():
        from run_artifacts import verify_receipt
        removing = delta.info.get("removed") is True
        if (session / "build-receipt.json").exists():
            receipt = verify_receipt(session, stage="staged")
            removing = receipt["identity"]["request"]["action"] == "remove"
        # Receipt-free fresh work retains all ordinary read-back checks, but is not reusable.
        _verify_final_build(session, remove=removing)
    pristine_delta.record_staged_hashes(keep / pristine_delta.STAGED_HASHES_NAME, delta.staged_hashes)
    (keep / RESTORE_REFUSED_NAME).unlink(missing_ok=True)  # the layer it describes is pristine again
    if delta.files:
        pristine_delta.write(delta, keep / pristine_delta.DELTA_NAME)
    else:
        (keep / pristine_delta.DELTA_NAME).unlink(missing_ok=True)
    _drop_redownload_done(keep, _redownload_done(session))
    return json.dumps({"files": len(delta.files), "bytes": delta.range_bytes})


def _redownload_done(result: Path) -> dict | None:
    """The `redownload_done` identity <result>'s own build reported, or None.

    Only a build made in this session reports it: a copied completed output (`reuse-provenance.json`)
    carries an older session's claim and never drops a record.
    """
    from run_artifacts import ArtifactError, HASH, read_record

    summary_path = result / "bridge-summary.json"
    if not summary_path.exists() or (result / "reuse-provenance.json").exists():
        return None
    claim = read_record(summary_path).get("redownload_done")
    if claim is None:
        return None
    if (not isinstance(claim, dict) or set(claim) != {"size", "sha256"} or type(claim["size"]) is not int
            or claim["size"] < 0 or not isinstance(claim["sha256"], str) or not HASH.fullmatch(claim["sha256"])):
        raise ArtifactError("Invalid Re-download record claim")
    return claim


def _drop_redownload_done(keep: Path, claim: dict | None) -> None:
    """Drop the kept Re-download record only when it still holds exactly the bytes the build read as done."""
    from run_artifacts import file_identity

    marker = keep / REDOWNLOAD_NAME
    if claim is not None and marker.is_file() and file_identity(marker) == claim:
        marker.unlink()


def prepare_game_apks(engine_root: str, source_path: str, destination_path: str, signer) -> str:
    """Rewrite only the manifest, producing stable-key normal/access recovery material."""
    import shutil
    import zipfile
    root, source, destination = Path(engine_root).resolve(), Path(source_path), Path(destination_path)
    _prepare(root)
    from apk_tools import rewrite_apk, signed_with
    from axml_set_debuggable import is_debuggable, patch
    from axml_label import set_label

    if destination.exists():
        raise PatchError("APK preparation requires a fresh private directory")
    with zipfile.ZipFile(source) as archive:
        manifest = archive.read("AndroidManifest.xml")
    if is_debuggable(manifest):
        raise PatchError("An access APK cannot become normal recovery material")
    normal_manifest = manifest
    label_warning = None
    try:
        normal_manifest = set_label(manifest, "Honor of Kings: ACE")
    except Exception as error:  # noqa: BLE001 - the launcher rename must never fail a run (AGENTS.md)
        label_warning = str(error)
    destination.mkdir(parents=True)
    results = {}
    try:
        for name, replacement in (("normal", normal_manifest), ("access", patch(normal_manifest, True))):
            target = destination / f"{name}.apk"
            if name == "normal" and replacement == manifest and signed_with(source, (root / "key/cert.der").read_bytes()):
                # Match Windows: an already-normal stable-key APK retains its content identity.
                shutil.copyfile(source, target)
                import os
                with target.open("rb+") as stream:
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
                    os.fsync(stream.fileno())
                descriptor = os.open(destination, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                results[name] = {"bytes": target.stat().st_size, "sha256": digest}
                continue
            unsigned = destination / "unsigned.apk"
            # The access copy is derived from exactly the normal APK recovery will install.
            apk_source = source if name == "normal" else destination / "normal.apk"
            rewrite_apk(apk_source, unsigned, {"AndroidManifest.xml": replacement})
            results[name] = json.loads(sign_with_java(str(root), str(unsigned), str(target), signer))
            unsigned.unlink()
            with zipfile.ZipFile(target) as written:
                if written.read("AndroidManifest.xml") != replacement:
                    raise PatchError(f"The {name} APK does not carry the manifest written into it")
            if name == "access" and not is_debuggable(replacement):
                raise PatchError("The access manifest does not turn android:debuggable on")
        results["label_warning"] = label_warning
        return json.dumps(results)
    except BaseException:
        shutil.rmtree(destination)
        raise


# Explicit continuation APIs. These never authorize dispatch, live writes or delta promotion.
# Kotlin owns coordinator.lock, current-source reconciliation and artifact retention.
def _delta_identity(keep: Path | None) -> dict | None:
    from run_artifacts import file_identity
    import pristine_delta

    if keep is None:
        return None
    # Reading validates the binary format and its embedded kept asset bodies as on a fresh run.
    delta = _read_delta(keep)
    records = {name: file_identity(keep / name) if (keep / name).exists() else None
               for name in (pristine_delta.DELTA_NAME, pristine_delta.STAGED_HASHES_NAME,
                            RESTORE_REFUSED_NAME, REDOWNLOAD_NAME)}
    return {"files": records, "present": delta is not None}


def checkpoint_identity(engine_root: str, session_root: str, normal_apk: str,
                        keep_root: str | None, target_json: str, request_json: str,
                        current_files_json: str, readiness_json: str,
                        prepared_apks_json: str, producer_json: str) -> str:
    """Measure bridge inputs; current_files/readiness are independently measured by Kotlin.

    prepared_apks identifies installed source + pinned normal/access (Root: exact installed APKs).
    producer_json is freshly obtained EngineAssets.producerIdentity, never a saved version string.
    A null producer returns identity=null/reusable=false; proceed with ordinary fresh build only.
    No target, readiness or authorization is invented by the bridge.
    """
    root, session = Path(engine_root).resolve(), Path(session_root).resolve()
    _prepare(root)
    from mobile_snapshot import verify_snapshot
    from run_artifacts import ArtifactError, file_identity, identity_key, make_input_identity, tree_manifest

    manifest = verify_snapshot(session / "snapshot")
    files = {name: {"size": entry["bytes"], "sha256": entry["sha256"]}
             for name, entry in manifest["files"].items()}
    if files != json.loads(current_files_json):
        raise PatchError("Snapshot differs from current measured game files")
    producer = json.loads(producer_json)
    if producer is None:
        return json.dumps({"reusable": False, "identity": None})
    if producer["kind"] != "android" or producer["components"]["engine"]["files_key"] != identity_key(tree_manifest(root)):
        raise ArtifactError("Current engine differs from producer evidence")
    request = json.loads(request_json)
    if request["action"] not in {"translate", "remove"} or request["options"]:
        raise PatchError("Bridge checkpoints require ordinary default translation or Remove")
    prepared = json.loads(prepared_apks_json)
    if not isinstance(prepared, dict) or not prepared:
        raise PatchError("Complete independently verified prepared APK evidence is required")
    identity = make_input_identity(
        target=json.loads(target_json), request=request,
        game={"files": files, "readiness": json.loads(readiness_json)},
        apks={"normal": file_identity(Path(normal_apk).resolve()), "prepared": prepared},
        delta=_delta_identity(Path(keep_root).resolve() if keep_root else None),
        translation={"engine_files_key": identity_key(tree_manifest(root))}, producer=producer)
    return json.dumps({"reusable": True, "identity": identity})


def _validate_checkpoint_inputs(root: Path, session: Path, apk: Path | None,
                                keep: Path | None, identity: dict) -> None:
    from mobile_snapshot import verify_snapshot
    from run_artifacts import ArtifactError, file_identity, identity_key, make_input_identity, tree_manifest

    # Validate every shared identity field, not just its digest.
    make_input_identity(**{name: item for name, item in identity.items() if name != "schema"})
    manifest = verify_snapshot(session / "snapshot")
    files = {name: {"size": item["bytes"], "sha256": item["sha256"]}
             for name, item in manifest["files"].items()}
    if identity["game"]["files"] != files:
        raise ArtifactError("Snapshot source identity changed")
    engine = identity_key(tree_manifest(root))
    if (identity["producer"]["kind"] != "android"
            or identity["producer"]["components"]["engine"]["files_key"] != engine
            or identity["translation"] != {"engine_files_key": engine}):
        raise ArtifactError("Engine identity changed")
    if apk is not None and identity["apks"]["normal"] != file_identity(apk):
        raise ArtifactError("Pinned normal APK changed")
    if identity["delta"] != _delta_identity(keep):
        raise ArtifactError("Kept pristine delta identity changed")
    if identity["request"]["action"] not in {"translate", "remove"} or identity["request"]["options"]:
        raise ArtifactError("Unsupported checkpoint action/options")


def snapshot_checkpoint(engine_root: str, session_root: str, run_id: str,
                        identity_json: str, publish: bool = False) -> str:
    """Commit after transport + exact live source verification, or rehash a completed snapshot.

    Caller has compared stream bytes/hash and process exit before publish=True. Null producer
    uses ordinary verified snapshot processing without a reusable receipt instead.
    """
    _prepare(Path(engine_root).resolve())
    from mobile_snapshot import checkpoint_snapshot
    return json.dumps(checkpoint_snapshot(Path(session_root).resolve() / "snapshot",
                                          identity=json.loads(identity_json), run_id=run_id,
                                          publish=publish))


def begin_snapshot_attempt(engine_root: str, session_root: str, run_id: str) -> str:
    """Persist fresh transport ownership before extraction; destination does not yet exist.

    Kotlin must publish this attempt's destination as its snapshot path only after verification.
    Never transport into an existing snapshot or resume tar fragments.
    """
    _prepare(Path(engine_root).resolve())
    from run_artifacts import create_attempt
    parent = Path(session_root).resolve() / "snapshot-attempts"
    parent.mkdir(exist_ok=True)
    attempt = create_attempt(parent, run_id=run_id, stage="snapshot")
    return json.dumps({"attempt": attempt.name, "destination": str(attempt / "snapshot")})


def _owned_attempt(session: Path, attempt_id: str, run_id: str, stage: str) -> Path:
    import uuid
    from run_artifacts import ArtifactError, read_record
    if str(uuid.UUID(attempt_id)) != attempt_id:
        raise ArtifactError("Invalid attempt id")
    parent = "build-attempts" if stage == "staged" else "snapshot-attempts"
    attempt = session / parent / attempt_id
    if read_record(attempt / "attempt-owner.json") != {"schema": 1, "run_id": run_id, "stage": stage}:
        raise ArtifactError("Attempt owner differs")
    return attempt


def _require_plain_directory(path: Path) -> None:
    info = path.lstat()
    if (stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400
            or not stat.S_ISDIR(info.st_mode)):
        raise PatchError("Refusing a linked build directory")


def _clear_scratch_shell(scratch: Path, session: Path) -> None:
    """Remove a staged scratch that holds no build product, never following a link.

    `build_checkpoint` creates the scratch, then links `snapshot` to the session's snapshot, and
    writes nothing else into it until the legacy build owner exists; `clear_build` returns an owned
    scratch to that same shape. So the only content accepted is that one link, as a symlink with
    exactly that target, and the scratch is removed only when it then stands empty. The link itself is
    unlinked; its target is never opened. Anything else refuses and is retained for diagnosis.
    """
    entries = {entry.name: entry for entry in os.scandir(scratch)}
    if set(entries) - {"snapshot"}:
        raise PatchError("Build scratch without ownership holds unexpected files")
    link = entries.get("snapshot")
    if link is not None:
        target = os.readlink(link.path) if link.is_symlink() else None
        if os.name == "nt" and target and target.startswith("\\\\?\\"):
            target = target[4:]  # Windows hosts report the long-path form of the target as written.
        if target != str(session / "snapshot"):
            raise PatchError("Build scratch without ownership holds an unexpected snapshot link")
        try:
            os.unlink(link.path)
        except (IsADirectoryError, PermissionError):
            if os.name != "nt":
                raise
            os.rmdir(link.path)  # Windows directory symlink: removes the link, never its target.
    scratch.rmdir()


def reset_checkpoint_attempt(engine_root: str, session_root: str, run_id: str, attempt_id: str,
                             stage: str = "staged") -> str:
    """Explicit reset of incomplete owned products only, under coordinator ownership.

    Coordinator must first prove no apply/recovery journal references this attempt. A present
    receipt, even invalid, pins the entire attempt. Originals/Watchdog/APKs/auth are never cleared.
    The attempt's owner marker is retained. A staged scratch with a legacy build owner is cleared
    through `clear_build`; one without it is the state `build_checkpoint` leaves when killed before
    `build_snapshot`/`build_removal` write that owner, and is cleared only in that exact shape
    (`_clear_scratch_shell`). Any other content refuses. Repeating a reset is a no-op.
    Start the retry in a newly allocated attempt, not this directory.
    """
    _prepare(Path(engine_root).resolve())
    from run_artifacts import ArtifactError, tree_manifest
    if stage not in {"snapshot", "staged"}:
        raise ArtifactError("Unsupported reset stage")
    attempt = _owned_attempt(Path(session_root).resolve(), attempt_id, run_id, stage)
    if any(attempt.rglob("build-receipt.json")):
        raise PatchError("Published or damaged checkpoints must be retained")
    if stage == "snapshot":
        target = attempt / "snapshot"
        if target.exists():
            tree_manifest(target)  # Reject links/escapes before any recursive delete.
            shutil.rmtree(target)
    else:
        scratch = attempt / "scratch"
        if scratch.exists() or scratch.is_symlink():
            _require_plain_directory(scratch)
            owner = scratch / "build-owner.json"
            if owner.exists() or owner.is_symlink():
                # Trusted snapshot symlink is deliberately excluded from the fixed build allowlist.
                clear_build(str(scratch))
            _clear_scratch_shell(scratch, Path(session_root).resolve())
        result = attempt / "result"
        if result.exists():
            tree_manifest(result)
            shutil.rmtree(result)
    return "{}"


def build_checkpoint(engine_root: str, session_root: str, run_id: str, normal_apk: str,
                     expected_apk_sha256: str, language: str = "en", keep_root: str | None = None,
                     identity_json: str = "null", remove: bool = False) -> str:
    """Fresh owned build; publish STAGED only after the legacy bridge's full finalization.

    Returns attempt/result/output paths, complete summary and receipt (or null when complete
    producer identity is unavailable). A previous committed attempt is never replaced/deleted.
    Apply must consume returned output + staged hashes, not the session's old out/ path.
    """
    root, session, apk = Path(engine_root).resolve(), Path(session_root).resolve(), Path(normal_apk).resolve()
    keep = Path(keep_root).resolve() if keep_root else None
    _prepare(root)
    started = time.monotonic()
    from mobile_snapshot import checkpoint_snapshot, verify_snapshot
    from qts_relocate import UnreachableSlot
    from run_artifacts import create_attempt, file_identity, publish_receipt

    identity = json.loads(identity_json)
    snapshot_before = verify_snapshot(session / "snapshot")
    delta_before = _delta_identity(keep)
    if identity is not None:
        _validate_checkpoint_inputs(root, session, apk, keep, identity)
        if identity["request"]["action"] != ("remove" if remove else "translate") or identity["request"]["language"] != language:
            raise PatchError("Build action/language differs from saved inputs")
        checkpoint_snapshot(session / "snapshot", identity=identity, run_id=run_id)
    if file_identity(apk)["sha256"] != expected_apk_sha256:
        raise PatchError("Pinned normal APK differs")
    parent = session / "build-attempts"
    parent.mkdir(exist_ok=True)
    attempt = create_attempt(parent, run_id=run_id, stage="staged")
    scratch = attempt / "scratch"
    scratch.mkdir()
    # Only read-only inputs link outside this attempt. All mutable reconstruction/output is separate.
    (scratch / "snapshot").symlink_to(session / "snapshot", target_is_directory=True)
    if remove:
        if keep is None:
            raise PatchError("Remove requires this patcher's pristine delta")
        summary = json.loads(build_removal(str(root), str(scratch), str(keep)))
    else:
        try:
            summary = json.loads(build_snapshot(str(root), str(scratch), str(apk), expected_apk_sha256,
                                                language, str(keep) if keep else None))
        except UnreachableSlot as error:
            if (keep is not None and _delta_identity(keep) == delta_before
                    and file_identity(apk)["sha256"] == expected_apk_sha256
                    and _record_unreachable_slot(root, session, scratch, keep, snapshot_before, error)):
                raise PatchError(f"{PACKAGE_UNREACHABLE}: package {error.path.parent.name}. "
                                 "Review Re-download to replace only the affected package files, then "
                                 "let the game finish downloading before continuing. " + str(error)) from error
            raise
        if keep is None:
            # Ordinary fresh API historically omits delta without keep_root. Checkpoint builds always
            # validate pristine and retain the pending delta before publishing reusable output.
            import pristine_delta
            reason = pristine_delta.text_not_pristine(summary)
            if reason:
                raise PatchError("Checkpoint source is not pristine: " + reason)
            delta = pristine_delta.make(scratch / "game/WXQ_Data/Package/builtin", scratch / "out",
                                        info={"patcher": "android", "language": language}, fingerprint=True)
            pristine_delta.write(delta, scratch / SESSION_DELTA)
    # The build only reads the kept folder; an obsolete Re-download record is reported in the summary
    # (`redownload_done`) and dropped at finalization, so any kept change here is foreign and refuses.
    if (verify_snapshot(session / "snapshot") != snapshot_before
            or _delta_identity(keep) != delta_before
            or file_identity(apk)["sha256"] != expected_apk_sha256):
        raise PatchError("Snapshot, kept delta or pinned APK changed during build")
    result = attempt / "result"
    result.mkdir()
    (scratch / "out").replace(result / "out")
    for name in ("staged-hashes.json", SESSION_DELTA, "metrics.json"):
        if (scratch / name).exists():
            (scratch / name).replace(result / name)
    # Preserve pipeline summary format; final bridge summary (with pristine information) is separate.
    (result / "bridge-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (result / "metrics.json").write_text(json.dumps({"elapsed_seconds": time.monotonic() - started}), encoding="utf-8")
    _final_build_manifest(result, remove=remove)
    receipt = None
    if identity is not None:
        _validate_checkpoint_inputs(root, session, apk, keep, identity)
        # Empty translation output is valid ordinary work but cannot be a reusable STAGED.
        from run_artifacts import read_record
        reusable_payload = bool(read_record(result / "staged-hashes.json")) or remove
        if reusable_payload:
            receipt = publish_receipt(result, identity=identity, run_id=run_id, stage="staged",
                                  references={"summary": "bridge-summary.json", "manifest": "final-manifest.json",
                                              "delta": None if remove else SESSION_DELTA})
    return json.dumps(_checkpoint_result(attempt, result, summary, receipt))


def copy_completed_checkpoint(engine_root: str, session_root: str, run_id: str, normal_apk: str,
                              keep_root: str, identity_json: str, previous_root: str,
                              completion_sha256: str) -> str:
    """Copy independently audited success output under NEW ownership; never restore/build.

    Kotlin first audits actual current APK/layer, old journal/preparation and active
    finalization bytes. This bridge rehashes retained build/source inputs again;
    interrupted copies have no receipt and cannot be applied.
    """
    root, session, apk = Path(engine_root).resolve(), Path(session_root).resolve(), Path(normal_apk).resolve()
    keep, prior = Path(keep_root).resolve(), Path(previous_root).resolve()
    _prepare(root)
    from run_artifacts import (ArtifactError, RECEIPT_NAME, create_attempt, file_identity,
                               identity_key, publish_receipt, read_record, verify_receipt)
    from mobile_snapshot import verify_snapshot

    identity = json.loads(identity_json)
    _validate_checkpoint_inputs(root, session, apk, keep, identity)
    previous = verify_receipt(prior, stage="staged")
    old = previous["identity"]
    for name in ("target", "request", "translation", "producer"):
        if old[name] != identity[name]:
            raise ArtifactError("Completed build inputs changed: " + name)
    if ({name: value for name, value in old["game"].items() if name != "files"} !=
            {name: value for name, value in identity["game"].items() if name != "files"}):
        raise ArtifactError("Completed build readiness evidence changed")
    if old["apks"]["normal"] != file_identity(apk):
        raise ArtifactError("Completed build prime APK changed")
    old_session = prior.parent.parent.parent
    snapshot = verify_snapshot(old_session / "snapshot")
    files = {name: {"size": item["bytes"], "sha256": item["sha256"]} for name, item in snapshot["files"].items()}
    if files != old["game"]["files"]:
        raise ArtifactError("Completed build original source changed")
    remove = identity["request"]["action"] == "remove"
    _verify_final_build(prior, remove=remove)
    parent = session / "build-attempts"
    parent.mkdir(exist_ok=True)
    attempt = create_attempt(parent, run_id=run_id, stage="staged")
    result = attempt / "result"
    result.mkdir()
    for name in previous["artifacts"]:
        if name in {"final-manifest.json", "reuse-provenance.json"}:
            continue
        target = result / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with (prior / name).open("rb") as source, target.open("xb") as output:
            shutil.copyfileobj(source, output, 1024 * 1024)
            output.flush(); os.fsync(output.fileno())
    (result / "reuse-provenance.json").write_text(json.dumps({"schema": 1,
        "kind": "completed-install-output-copy", "run_id": previous["run_id"],
        "input_key": previous["input_key"], "completion_sha256": completion_sha256,
        "summary": file_identity(prior / "bridge-summary.json")}), encoding="utf-8")
    _final_build_manifest(result, remove=remove)
    _validate_checkpoint_inputs(root, session, apk, keep, identity)
    verify_receipt(prior, input_key=identity_key(old), stage="staged")
    receipt = publish_receipt(result, identity=identity, run_id=run_id, stage="staged",
        references={"summary": "bridge-summary.json", "manifest": "final-manifest.json",
                    "delta": None if remove else SESSION_DELTA})
    return json.dumps(_checkpoint_result(attempt, result, read_record(result / "bridge-summary.json"), receipt))


def finalization_plan(engine_root: str, result_root: str, remove: bool = False) -> str:
    """The byte-level finalization a verified install of <result_root> performs, decided now.

    Kotlin seals it beside the STAGED journal entry, so promotion/removal after the payload and normal
    APK are verified needs no Python, codec or newer engine: it merges `staged_hashes` into the kept
    record exactly as `keep_delta` would, then copies (or, for Remove, deletes) the kept delta.
    `redownload_done` is the identity of the kept Re-download record this build read with every package
    back (`_refuse_stuck_update`), or null: finalization drops the record only while it holds exactly
    those bytes, after the delta is promoted, so no build ever changes the kept folder it is bound to.
    """
    _prepare(Path(engine_root).resolve())
    import pristine_delta

    result = Path(result_root).resolve()
    _verify_final_build(result, remove=remove)
    delta = pristine_delta.read(result / SESSION_DELTA)
    digest = hashlib.sha256((result / SESSION_DELTA).read_bytes()).hexdigest()
    return json.dumps({"schema": 1, "remove": bool(remove), "files": len(delta.files),
                       "bytes": delta.range_bytes, "delta_sha256": digest,
                       "staged_hashes": sorted(delta.staged_hashes),
                       "redownload_done": _redownload_done(result)}, sort_keys=True)


def _staged_payload_manifest(output: Path) -> dict:
    """Separate game files from the runtime stager's bounded, retained verification reports.

    stage_unity_package writes package<N>_stage_manifest.json (unity19 for package 19)
    and empty package<N>_metadata_<mkdtemp suffix> directories beside numeric packages.
    Reports describe its own pass, before relocation/graphics/append, so their file hashes
    are historical evidence, not the final hashes. The complete result receipt hashes them
    unchanged. No other root entries or nonempty metadata directories are accepted.
    """
    import re
    from run_artifacts import ArtifactError, HASH, read_record, tree_manifest

    actual = tree_manifest(output)  # Reject links/special files before classifying anything.
    payload = {}
    report_keys = {"status", "package_id", "replacement_count", "verified_unrelated_assets",
                   "batch_builder_invocations", "position_reference_updates",
                   "position_reference_insertions", "slot_donation_updates", "assets", "files"}
    for path in output.iterdir():
        name = path.name
        if re.fullmatch(r"[0-9]+", name) and path.is_dir():
            children = list(path.iterdir())
            if not children or any(not child.is_file() for child in children):
                raise ArtifactError("Empty or nested staged package output")
            payload.update({key: value for key, value in actual.items() if key.startswith(name + "/")})
            continue
        if name == "device_patch_summary.json" and path.is_file():
            continue
        metadata = re.fullmatch(r"package([0-9]+)_metadata_[a-z0-9_]{8}", name)
        if metadata is not None and path.is_dir():
            if any(path.iterdir()) or not (output / metadata.group(1)).is_dir():
                raise ArtifactError("Runtime metadata directory is nonempty or orphaned")
            continue
        match = re.fullmatch(r"package([0-9]+)_stage_manifest\.json|unity(19)_stage_manifest\.json", name)
        if match is None or not path.is_file():
            raise ArtifactError("Unknown staged output: " + name)
        package = match.group(1) or match.group(2)
        if name == "package19_stage_manifest.json" or not (output / package).is_dir():
            raise ArtifactError("Runtime stage report package differs")
        report = read_record(path)
        if (set(report) not in (report_keys, report_keys | {"native_verification"})
                or report["status"] != "verified" or report["package_id"] != package
                or any(type(report[key]) is not int or report[key] < 0 for key in
                       ("replacement_count", "verified_unrelated_assets", "batch_builder_invocations"))
                or any(not isinstance(report[key], list) for key in
                       ("position_reference_updates", "position_reference_insertions",
                        "slot_donation_updates", "assets", "files"))
                or ("native_verification" in report and not isinstance(report["native_verification"], dict))
                or report["replacement_count"] != len(report["assets"])):
            raise ArtifactError("Invalid runtime stage report")
        seen = set()
        for item in report["assets"]:
            if (not isinstance(item, dict) or set(item) != {"hash", "raw_size", "raw_sha256", "chunks"}
                    or not isinstance(item["hash"], str) or not re.fullmatch(r"[0-9A-F]{16}", item["hash"])
                    or item["hash"] in seen or not isinstance(item["raw_sha256"], str)
                    or not HASH.fullmatch(item["raw_sha256"])
                    or any(type(item[key]) is not int or item[key] < 0 for key in ("raw_size", "chunks"))):
                raise ArtifactError("Invalid runtime stage asset report")
            seen.add(item["hash"])
        seen = set()
        for item in report["files"]:
            if (not isinstance(item, dict) or set(item) != {"name", "source_sha256", "staged_sha256"}
                    or not isinstance(item["name"], str)
                    or not re.fullmatch(re.escape(package) + r"(?:_[0-9]+)?\.db", item["name"])
                    or f"{package}/{item['name']}" not in actual
                    or item["name"] in seen
                    or any(not isinstance(item[key], str) or not HASH.fullmatch(item[key])
                           for key in ("source_sha256", "staged_sha256"))):
                raise ArtifactError("Invalid runtime stage file report")
            seen.add(item["name"])
        if not seen:
            raise ArtifactError("Empty runtime stage file report")
    return payload


def _final_build_manifest(result: Path, *, remove: bool) -> None:
    """Read back final output hashes and delta; restored-but-unstaged files are mandatory too."""
    import pristine_delta
    from run_artifacts import ArtifactError, read_record, tree_manifest

    hashes = read_record(result / "staged-hashes.json")
    _verify_declared_outputs(result, hashes, remove=remove)
    payload = _staged_payload_manifest(result / "out")
    if {name: item["sha256"] for name, item in payload.items()} != hashes:
        raise ArtifactError("Final staged hashes omit or differ from output")
    delta = pristine_delta.read(result / SESSION_DELTA)
    if remove:
        if delta.files:
            raise ArtifactError("Remove delta is not empty")
    elif {entry.path: entry.staged_sha256 for entry in delta.files} != hashes:
        raise ArtifactError("Session delta does not describe the full staged output")
    references = {"bridge-summary.json", "final-manifest.json"}
    if not remove:
        references.add(SESSION_DELTA)
    files = tree_manifest(result)
    (result / "final-manifest.json").write_text(json.dumps({"schema": 1, "files": {
        name: item for name, item in files.items() if name not in references}}, sort_keys=True), encoding="utf-8")


def _checkpoint_result(attempt: Path, result: Path, summary: dict, receipt: dict | None) -> dict:
    return {"attempt": attempt.name, "result_root": str(result), "output_root": str(result / "out"),
            "hashes_path": str(result / "staged-hashes.json"), "delta_path": str(result / SESSION_DELTA),
            "summary": summary, "receipt": receipt, "reusable": receipt is not None}


def inspect_build_checkpoint(engine_root: str, session_root: str, run_id: str, attempt_id: str,
                             normal_apk: str, keep_root: str | None, identity_json: str) -> str:
    """Rehash a completed build after restart; performs zero staging/native transform calls.

    Caller first reconciles current installed/source/readiness/producer evidence. Failure declines
    reuse, never authorizes reset of a receipt-bearing attempt. A summary alone always fails.
    """
    root, session = Path(engine_root).resolve(), Path(session_root).resolve()
    _prepare(root)
    from mobile_snapshot import checkpoint_snapshot
    from run_artifacts import read_record, verify_receipt
    identity = json.loads(identity_json)
    _validate_checkpoint_inputs(root, session, Path(normal_apk).resolve(),
                                Path(keep_root).resolve() if keep_root else None, identity)
    checkpoint_snapshot(session / "snapshot", identity=identity, run_id=run_id)
    attempt = _owned_attempt(session, attempt_id, run_id, "staged")
    result = attempt / "result"
    receipt = verify_receipt(result, identity=identity, stage="staged")
    if receipt["run_id"] != run_id:
        raise PatchError("Build receipt owner differs")
    # Semantic delta/hashes validation reads only; do not rewrite the committed final manifest.
    _verify_final_build(result, remove=identity["request"]["action"] == "remove")
    return json.dumps(_checkpoint_result(attempt, result, read_record(result / "bridge-summary.json"), receipt))


def _verify_final_build(result: Path, *, remove: bool) -> None:
    import pristine_delta
    from run_artifacts import ArtifactError, read_record, tree_manifest
    hashes = read_record(result / "staged-hashes.json")
    _verify_declared_outputs(result, hashes, remove=remove)
    payload = _staged_payload_manifest(result / "out")
    if {name: item["sha256"] for name, item in payload.items()} != hashes:
        raise ArtifactError("Final staged output changed")
    delta = pristine_delta.read(result / SESSION_DELTA)
    if (remove and delta.files) or (not remove and {entry.path: entry.staged_sha256 for entry in delta.files} != hashes):
        raise ArtifactError("Final session delta differs")



def _verify_declared_outputs(result: Path, hashes: dict, *, remove: bool) -> None:
    """Summary declarations cannot disappear by editing output, hashes and delta together."""
    from run_artifacts import ArtifactError, read_record, relative_path

    summary = read_record(result / "bridge-summary.json")
    pristine = summary.get("pristine", {})
    if not isinstance(pristine, dict):
        raise ArtifactError("Invalid bridge pristine summary")

    def declared(value: object) -> set[str]:
        if not isinstance(value, list) or not all(isinstance(name, str) for name in value):
            raise ArtifactError("Invalid declared output list")
        names = {relative_path(name) for name in value}
        if len(names) != len(value):
            raise ArtifactError("Duplicate declared output")
        return names

    restored = declared(pristine.get("restored", []))
    if not restored <= hashes.keys():
        raise ArtifactError("Declared restored output is missing")
    if remove:
        removed = declared(summary.get("removed"))
        if removed != hashes.keys():
            raise ArtifactError("Remove output differs from declared removed files")
