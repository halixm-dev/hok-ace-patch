"""Bridge the Android worker to verified private snapshots and the translation engine."""
from __future__ import annotations

import importlib
import importlib.util
import json
import platform
import hashlib
import runpy
import shutil
import sys
import time
from pathlib import Path

REQUIRED_CODECS = ("lz4.block", "zstandard", "astc_encoder", "texture2ddecoder", "ooz")
# In a session: the build input's rebuilt pristine files, and the delta of the install it stages.
PRISTINE_COPY = "pristine"
SESSION_DELTA = "pristine-delta.bin"
CLEAR_DATA = ("Clear the game's data (Android Settings > Apps > the game > Storage > Clear data), open the "
              "game and let it download again to the login screen, close it, then patch again.")
OTHER_PATCHER = "If the Windows patcher patched this phone last, patch it with that patcher instead."


class PatchError(Exception):
    """Expected feasibility failure which can be shown by the Android UI."""


def _prepare(root: Path) -> None:
    if sys.version_info[:2] != (3, 12):
        raise PatchError("The translation runtime requires Python 3.12")
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
    root = Path(engine_root).resolve()
    session = Path(session_root).resolve()
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
        if not path.is_relative_to(session):
            raise PatchError("Invalid control input path")
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != expected:
            raise PatchError(f"Scratch source differs from desktop control: {name}")
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


def estimate_snapshot_build(engine_root: str, session_root: str, normal_apk: str,
                            language: str = "en", keep_root: str | None = None) -> str:
    """Read verified snapshot and APK metadata before creating any build work/output.

    With a kept pristine delta (<keep_root>), the build input's copy of the files it names is reserved
    too: `build_snapshot` rebuilds them beside the snapshot, which keeps the phone's actual bytes.
    """
    root, session = Path(engine_root).resolve(), Path(session_root).resolve()
    _prepare(root)
    from mobile_snapshot import verify_snapshot
    from build_storage import estimate

    catalog = _catalog(root, language)
    manifest = verify_snapshot(session / "snapshot")
    delta = _read_delta(Path(keep_root)) if keep_root else None
    copy_bytes = sum(entry.pristine_size for entry in delta.files) if delta else 0
    return json.dumps(estimate(session / "snapshot/packages", catalog, Path(normal_apk), manifest,
                               scratch=session, pristine_copy_bytes=copy_bytes))


def _restore_pristine(session: Path, keep: Path) -> dict:
    """Rebuild the files the kept delta names into the session's build-input copy, or refuse.

    Returns `{"mode": "rebuilt" | "first", "rebuilt": [...], "pristine": [...], "sha256": {...}}`, the
    last naming the pristine SHA-256 of every file the copy holds. `replaced` names the files a game
    update rewrote that `pristine_delta.accept_replaced` takes as the new pristine: the build reads them
    from the snapshot, and the text signal must then pass. Raises PatchError, before any game file is
    written, when the snapshot is neither at the delta's staged bytes nor at pristine and no update
    replaced it cleanly.
    """
    import pristine_delta

    packages = session / "snapshot" / "packages"
    known = pristine_delta.load_staged_hashes(keep / pristine_delta.STAGED_HASHES_NAME)
    delta = _read_delta(keep)
    if delta is None:
        if pristine_delta.files_at(packages, known):
            raise PatchError("This phone is already translated, and the patcher cannot rebuild its "
                             "untranslated game files. " + CLEAR_DATA)
        return {"mode": "first", "rebuilt": [], "pristine": [], "sha256": {}}
    copy = session / PRISTINE_COPY
    if copy.exists():
        raise PatchError("Snapshot build requires a fresh session layout")
    translated = pristine_delta.files_at(packages, known)
    report = pristine_delta.rebuild(packages, delta, copy)
    if not report.complete and not translated:
        # Nothing this patcher wrote is left, as after clearing the game's data and downloading a newer
        # version: the delta describes a layer that is gone, and the text signal decides instead.
        shutil.rmtree(copy, ignore_errors=True)
        return {"mode": "first", "rebuilt": [], "pristine": [], "sha256": {}, "stale": len(report.unmatched)}
    replaced: list[str] = []
    if not report.complete:
        replaced, refused = pristine_delta.accept_replaced(packages, delta, report)
        if refused:
            names = ", ".join(f"{name} ({state})" for name, state in sorted(report.unmatched.items()))
            reasons = "; ".join(f"package {package}: {reason}" for package, reason in refused.items())
            raise PatchError(f"The game files changed since the last patch (a game update or repair): {names} "
                             f"({reasons}). The patcher cannot rebuild the untranslated files. " + CLEAR_DATA)
    leftover = [name for name in translated if name not in report.rebuilt]
    if leftover:
        raise PatchError(f"Translated game files the patcher has no record of: {', '.join(leftover)}. "
                         + CLEAR_DATA)
    return {"mode": "rebuilt", "rebuilt": report.rebuilt, "pristine": report.pristine, "replaced": replaced,
            "sha256": {entry.path: entry.pristine_sha256 for entry in delta.files
                       if not entry.created and entry.path not in replaced},
            "deleted": [entry.path for entry in delta.files if entry.created and entry.path not in replaced]}


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

    manifest = verify_snapshot(session / "snapshot")
    with apk.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != expected_apk_sha256:
        raise PatchError("Recovery APK changed before snapshot build")
    game = session / "game"
    builtin = game / "WXQ_Data" / "Package" / "builtin"
    if game.exists() or (session / "normal.apk").exists() or (session / "control.json").exists():
        raise PatchError("Snapshot build requires a fresh session layout")
    restored = (_restore_pristine(session, Path(keep_root)) if keep_root
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
    summary = json.loads(build_scratch(str(root), str(session), language))
    if keep_root is None:
        return json.dumps(summary)
    import pristine_delta

    if restored.get("replaced"):
        reason = pristine_delta.text_not_pristine(summary)
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
    # A file the previous install translated and this build leaves alone goes back to pristine too.
    untranslated = [name for name in restored["rebuilt"] if name not in hashes]
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
                           "replaced": restored.get("replaced", [])}
    return json.dumps(summary)


def removal_bytes(engine_root: str, keep_root: str) -> int:
    """The pristine bytes `build_removal` will rebuild: what Remove translation must reserve."""
    _prepare(Path(engine_root).resolve())
    delta = _read_delta(Path(keep_root))
    return sum(entry.pristine_size for entry in delta.files) if delta else 0


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

    verify_snapshot(session / "snapshot")
    output = session / "out"
    if output.exists() or (session / "staged-hashes.json").exists():
        raise PatchError("Removal requires a fresh session layout")
    restored = _restore_pristine(session, keep)
    if restored["mode"] != "rebuilt":
        raise PatchError("This patcher has no record of a translation on this phone, so there is nothing "
                         "to remove. " + OTHER_PATCHER)
    if restored.get("deleted"):
        raise PatchError("Removing a package file the patch created is not supported")
    if not restored["rebuilt"]:
        raise PatchError("The game files are already untranslated; there is nothing to remove.")
    hashes = {}
    for name in restored["rebuilt"]:
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
                           "already_pristine": len(restored["pristine"]), "restored": sorted(hashes)}
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
    pristine_delta.record_staged_hashes(keep / pristine_delta.STAGED_HASHES_NAME, delta.staged_hashes)
    if delta.files:
        pristine_delta.write(delta, keep / pristine_delta.DELTA_NAME)
    else:
        (keep / pristine_delta.DELTA_NAME).unlink(missing_ok=True)
    return json.dumps({"files": len(delta.files), "bytes": delta.range_bytes})


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
    except Exception as error:
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
