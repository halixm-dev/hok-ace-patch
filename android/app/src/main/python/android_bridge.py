"""Bridge the Android worker to verified private snapshots and the translation engine."""
from __future__ import annotations

import importlib
import importlib.util
import json
import platform
import hashlib
import runpy
import sys
import time
from pathlib import Path

REQUIRED_CODECS = ("lz4.block", "zstandard", "astc_encoder", "texture2ddecoder", "ooz")


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
        path = (builtin / name).resolve()
        if not path.is_relative_to(builtin.resolve()):
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


def estimate_snapshot_build(engine_root: str, session_root: str, normal_apk: str,
                            language: str = "en") -> str:
    """Read verified snapshot and APK metadata before creating any build work/output."""
    root, session = Path(engine_root).resolve(), Path(session_root).resolve()
    _prepare(root)
    from mobile_snapshot import verify_snapshot
    from build_storage import estimate

    catalog = _catalog(root, language)
    manifest = verify_snapshot(session / "snapshot")
    return json.dumps(estimate(session / "snapshot/packages", catalog, Path(normal_apk), manifest,
                               scratch=session))


def build_snapshot(engine_root: str, session_root: str, normal_apk: str,
                   expected_apk_sha256: str, language: str = "en") -> str:
    """Build a retained, rehashed snapshot using the independently verified recovery APK."""
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
    builtin.parent.mkdir(parents=True)
    builtin.symlink_to(session / "snapshot" / "packages", target_is_directory=True)
    (session / "normal.apk").symlink_to(apk)
    control = {"verified_source_files": {
        name.removeprefix("packages/"): entry["sha256"]
        for name, entry in manifest["files"].items() if name.startswith("packages/")
    }, "apk": {"sha256": expected_apk_sha256}}
    (session / "control.json").write_text(json.dumps(control), encoding="utf-8")
    return build_scratch(str(root), str(session), language)


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
        results["label_warning"] = label_warning
        return json.dumps(results)
    except BaseException:
        shutil.rmtree(destination)
        raise
