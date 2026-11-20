"""Content identities and commit-last receipts for immutable, exclusively owned attempts.

No receipt authorizes device work. Callers own locks, current-source reconciliation and
retention. Rehash after restart; only retain descriptors within one immutable invocation.
Snapshot wrappers must map the complete source manifest to their retained directory layout
and verify it before publication/reuse (including recovery Watchdog bytes where touched).
Missing complete producer evidence disables reuse (``windows_producer_identity`` returns
None). This module never changes the pipeline summary or falls back to version/mtime.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
import time
import uuid
from pathlib import Path
from typing import Callable, Mapping

SCHEMA = 1
RECEIPT_NAME = "build-receipt.json"
MAX_JSON = 16 * 1024 * 1024
MAX_FILES = 100_000
MAX_INTEGER = (1 << 53) - 1
HASH = re.compile(r"[0-9a-f]{64}\Z")
STAGES = frozenset({"prepared", "snapshot", "pristine", "staged", "installed"})
REFERENCES = frozenset({"summary", "delta", "manifest"})
_REPLACE_ATTEMPTS = 20  # about 3.5 s of backoff on Windows


class ArtifactError(ValueError):
    """Incomplete or incompatible retained content; ordinary fresh work remains possible."""


def installed_state_key(identity: dict, *, files: dict, installed: dict, delta: dict) -> str:
    """Final-state key, separate from immutable original build-source provenance.

    Caller independently audits installed APK and complete live files. A saved key
    cannot attest the phone, finalize metadata, or authorize dispatch.
    """
    _input(identity)
    validate_manifest(files)
    if not isinstance(installed, dict) or not installed or not isinstance(delta, dict):
        raise ArtifactError("Incomplete installed state")
    return identity_key({"schema": 1, "target": identity["target"], "request": identity["request"],
                         "translation": identity["translation"], "producer": identity["producer"],
                         "game_evidence": {name: value for name, value in identity["game"].items() if name != "files"},
                         "files": files, "installed": installed, "delta": delta})


def _canonical(value: object, depth: int = 0) -> None:
    if depth > 32:
        raise ArtifactError("Identity nesting exceeds limit")
    if value is None or type(value) is bool:
        return
    if type(value) is int and abs(value) <= MAX_INTEGER:
        return
    if isinstance(value, str):
        if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            raise ArtifactError("Surrogate characters are unsupported")
        return
    if isinstance(value, list):
        for item in value:
            _canonical(item, depth + 1)
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for key, item in value.items():
            # ASCII keys make lexical ordering identical on Python and JVM.
            if not key.isascii():
                raise ArtifactError("Identity keys must be ASCII")
            _canonical(item, depth + 1)
        return
    raise ArtifactError("Identity supports only JSON objects, lists, strings, integers, bool and null")


def canonical_bytes(value: object) -> bytes:
    """Schema-1 canonical JSON: UTF-8, ASCII keys sorted, no floats or extra whitespace."""
    _canonical(value)
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(data) > MAX_JSON:
        raise ArtifactError("Identity exceeds byte limit")
    return data


def identity_key(identity: object) -> str:
    """Hash canonical content, versioned independently of receipts and provenance."""
    return hashlib.sha256(canonical_bytes({"schema": SCHEMA, "identity": identity})).hexdigest()


def _pairs(items: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in items:
        if key in result:
            raise ArtifactError("Duplicate JSON key")
        result[key] = value
    return result


def read_record(path: Path) -> dict:
    """Bounded strict JSON reader (including duplicate keys and non-finite numbers)."""
    safe_file(path)
    if path.lstat().st_nlink != 1:
        raise ArtifactError("Hard-linked records are not immutable")
    with path.open("rb") as stream:
        data = stream.read(MAX_JSON + 1)
    if len(data) > MAX_JSON:
        raise ArtifactError("Record exceeds byte limit")
    try:
        result = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs,
                            parse_constant=lambda value: (_ for _ in ()).throw(ArtifactError(value)))
        canonical_bytes(result)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise ArtifactError("Invalid JSON record") from error
    if not isinstance(result, dict):
        raise ArtifactError("Record must be an object")
    return result


def relative_path(name: str) -> str:
    """Portable, normalized relative paths; reject NTFS aliases, ADS and traversal."""
    if not isinstance(name, str) or len(name) > 1024 or not name.isascii():
        raise ArtifactError("Invalid artifact path")
    parts = name.split("/")
    for part in parts:
        if (not part or part in {".", ".."} or part[-1:] in {".", " "}
                or re.search(r'[\\:\x00-\x1f<>"|?*]', part)
                or part.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", "CLOCK$",
                    *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}):
            raise ArtifactError("Unsafe artifact path")
    return name


def safe_file(path: Path, *, directory: bool = False) -> None:
    # Inspect all ancestors too: resolving first would hide a junction escape.
    for parent in (*reversed(path.absolute().parents), path.absolute()):
        info = parent.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ArtifactError("Links/reparse points are not reusable")
    info = path.stat()
    if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        raise ArtifactError("Expected a regular artifact")


def file_identity(path: Path) -> dict:
    """Stream a regular file's actual bytes; callers must prevent concurrent mutation."""
    safe_file(path)
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    if size > MAX_INTEGER:
        raise ArtifactError("Artifact exceeds size limit")
    return {"size": size, "sha256": digest.hexdigest()}


def validate_manifest(manifest: object) -> dict:
    if not isinstance(manifest, dict) or len(manifest) > MAX_FILES:
        raise ArtifactError("Invalid manifest")
    seen = set()
    for name, item in manifest.items():
        relative_path(name)
        if name.lower() in seen:
            raise ArtifactError("Conflicting artifact paths")
        seen.add(name.lower())
        if (not isinstance(item, dict) or set(item) != {"size", "sha256"}
                or type(item["size"]) is not int or not 0 <= item["size"] <= MAX_INTEGER
                or not isinstance(item["sha256"], str) or not HASH.fullmatch(item["sha256"])):
            raise ArtifactError("Invalid artifact identity")
    return manifest


def tree_manifest(root: Path, *, exclude: frozenset[str] = frozenset()) -> dict:
    """Exact bounded recursive file set. No links, special files or writable hard links."""
    safe_file(root, directory=True)
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs:
            safe_file(Path(directory) / name, directory=True)
        for name in files:
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if relative in exclude:
                safe_file(path)
                continue
            relative_path(relative)
            if path.lstat().st_nlink != 1:
                raise ArtifactError("Hard-linked artifacts are not immutable")
            result[relative] = file_identity(path)
            if len(result) > MAX_FILES:
                raise ArtifactError("Too many artifacts")
    return validate_manifest(dict(sorted(result.items())))


def verify_manifest(root: Path, manifest: Mapping, *, exclude: frozenset[str] = frozenset()) -> None:
    validate_manifest(manifest)
    if tree_manifest(root, exclude=exclude) != manifest:
        raise ArtifactError("Artifact file set or bytes differ")


def _producer(producer: object) -> dict:
    if (not isinstance(producer, dict) or type(producer.get("schema")) is not int or producer.get("schema") != SCHEMA
            or producer.get("complete") is not True or producer.get("kind") not in
            {"windows-source", "windows-frozen", "android"}
            or not isinstance(producer.get("components"), dict) or not producer["components"]):
        raise ArtifactError("Complete producer identity is unavailable; reuse disabled")
    required = {"windows-source": {"app", "tools", "resources", "python", "dependencies", "native", "executable"},
                "windows-frozen": {"executable", "bundle", "native"},
                "android": {"installed_apks", "engine", "native", "abi"}}[producer["kind"]]
    if not required <= producer["components"].keys():
        raise ArtifactError("Incomplete producer components")
    components = producer["components"]
    if producer["kind"].startswith("windows-"):
        executable = components.get("executable")
        validate_manifest({"executable": executable})
        if executable["size"] == 0:
            raise ArtifactError("Empty executable identity")
        for name in (("app", "tools", "resources", "python") if producer["kind"] == "windows-source" else ("bundle",)):
            item = components[name]
            if not isinstance(item, dict) or set(item) != {"manifest_key", "files"} or not item["files"]:
                raise ArtifactError("Missing executable tree evidence")
    else:
        validate_manifest(components["installed_apks"])
        if not components["installed_apks"] or any(item["size"] == 0 for item in components["installed_apks"].values()):
            raise ArtifactError("Missing installed patcher APK bytes")
        if not isinstance(components["engine"], dict) or set(components["engine"]) != {"manifest_sha256", "files_key"}:
            raise ArtifactError("Missing engine evidence")
    def evidence(item: object) -> None:
        if isinstance(item, dict) and set(item) == {"size", "sha256"}:
            validate_manifest({"evidence": item})
        elif isinstance(item, dict) and set(item) == {"manifest_key", "files"}:
            if (not isinstance(item["manifest_key"], str) or not HASH.fullmatch(item["manifest_key"])
                    or type(item["files"]) is not int or not 0 <= item["files"] <= MAX_FILES):
                raise ArtifactError("Invalid producer tree evidence")
        elif isinstance(item, dict) and set(item) == {"manifest_sha256", "files_key"}:
            if any(not isinstance(value, str) or not HASH.fullmatch(value) for value in item.values()):
                raise ArtifactError("Invalid engine evidence")
        elif item == {"packaged_in_apks": True}:
            return
        elif isinstance(item, (dict, list)):
            for value in item.values() if isinstance(item, dict) else item:
                evidence(value)
        else:
            raise ArtifactError("Producer evidence must identify actual bytes")
    for name, component in producer["components"].items():
        if name == "abi":
            if not isinstance(component, list) or not component or not all(isinstance(item, str) and item for item in component):
                raise ArtifactError("Missing ABI evidence")
        else:
            evidence(component)
    if not producer["components"].get("native"):
        # An empty extracted Android directory is still identified by the complete APKs.
        if producer["kind"] != "android":
            raise ArtifactError("Missing native dependency evidence")
    canonical_bytes(producer)
    return producer


def _stage_references(root: Path, stage: str, identity: dict, references: dict, artifacts: dict) -> None:
    if set(references) != REFERENCES:
        raise ArtifactError("References must explicitly name summary, delta and manifest")
    names = []
    for name in references.values():
        if name is not None:
            if relative_path(name) not in artifacts:
                raise ArtifactError("Missing referenced artifact")
            names.append(name)
    if len(set(names)) != len(names):
        raise ArtifactError("Artifact metadata roles must be distinct")
    if stage != "staged":
        return
    if references["summary"] is None or references["manifest"] is None:
        raise ArtifactError("Staged receipt requires summary and complete output manifest")
    remove = identity["request"]["action"] == "remove"
    if (references["delta"] is None) != remove:
        raise ArtifactError("Staged delta must be present for translation and explicitly absent for Remove")
    read_record(root / references["summary"])
    manifest = read_record(root / references["manifest"])
    if set(manifest) != {"schema", "files"} or type(manifest["schema"]) is not int or manifest["schema"] != SCHEMA:
        raise ArtifactError("Unknown final output manifest")
    validate_manifest(manifest["files"])
    expected = {name: item for name, item in artifacts.items() if name not in {*names, "attempt-owner.json"}}
    if manifest["files"] != expected or (not remove and not expected):
        raise ArtifactError("Incomplete final output manifest")
    if not remove and artifacts[references["delta"]]["size"] == 0:
        raise ArtifactError("Missing staged delta bytes")


def make_input_identity(*, target: dict, request: dict, game: dict, apks: dict | None,
                        delta: dict | None, translation: dict, producer: dict | None) -> dict:
    """Only semantic inputs. Run ids, timestamps and host paths belong in provenance.

    ``game`` must contain the complete ``files`` manifest plus readiness evidence.
    APK/delta absence is explicit null; when present include their file_identity and
    semantic metadata/body records. All output flags belong in request.options.
    Translation may be a content digest/manifest; producer covers the full engine too.
    """
    value = dict(schema=SCHEMA, target=target, request=request, game=game, apks=apks,
                 delta=delta, translation=translation, producer=producer)
    _input(value)
    return value


def _input(value: object) -> dict:
    keys = {"schema", "target", "request", "game", "apks", "delta", "translation", "producer"}
    if not isinstance(value, dict) or set(value) != keys or type(value["schema"]) is not int or value["schema"] != SCHEMA:
        raise ArtifactError("Unknown input identity schema")
    for name in ("target", "request", "game", "translation"):
        if not isinstance(value[name], dict) or not value[name]:
            raise ArtifactError(f"Missing identity component: {name}")
    if not {"package", "android_user", "device", "provider"} <= value["target"].keys():
        raise ArtifactError("Incomplete target binding")
    for name in ("package", "device", "provider"):
        if not isinstance(value["target"][name], str) or not value["target"][name].strip():
            raise ArtifactError("Invalid target binding")
    user = value["target"]["android_user"]
    if type(user) is not int or not 0 <= user <= MAX_INTEGER:
        raise ArtifactError("Invalid Android user binding")
    if (value["request"].get("action") not in {"translate", "remove", "first_setup", "redownload"}
            or value["request"].get("language") not in {"en", "id"}
            or not isinstance(value["request"].get("options"), dict)):
        raise ArtifactError("Incomplete request identity")
    if "readiness" not in value["game"]:
        raise ArtifactError("Missing readiness evidence")
    validate_manifest(value["game"].get("files"))
    for name in ("apks", "delta"):
        if value[name] is not None and (not isinstance(value[name], dict) or not value[name]):
            raise ArtifactError(f"Invalid optional input: {name}")
    _producer(value["producer"])
    canonical_bytes(value)
    return value


def _tree_identity(root: Path) -> dict:
    manifest = tree_manifest(root)
    return {"manifest_key": identity_key(manifest), "files": len(manifest)}


def _windows_native_identity() -> dict:
    """Hash mapped native dependencies too, including system VC/runtime DLL bytes."""
    if os.name != "nt":
        raise ArtifactError("Windows producer requested on a different platform")
    import ctypes
    import importlib
    from ctypes import wintypes
    # Load every shipped transform/signing binding before enumerating dependencies.
    for name in ("lz4.block", "zstandard", "astc_encoder", "texture2ddecoder", "ooz",
                 "PIL.Image", "PIL.ImageFont", "cryptography.hazmat.primitives.asymmetric.rsa"):
        importlib.import_module(name)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    process = kernel.GetCurrentProcess
    process.restype = wintypes.HANDLE
    enumerate_modules = kernel.K32EnumProcessModules
    enumerate_modules.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.HMODULE),
                                  wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    enumerate_modules.restype = wintypes.BOOL
    modules = (wintypes.HMODULE * 4096)()
    needed = wintypes.DWORD()
    if not enumerate_modules(process(), modules, ctypes.sizeof(modules), ctypes.byref(needed)):
        raise ctypes.WinError(ctypes.get_last_error())
    if needed.value > ctypes.sizeof(modules):
        raise ArtifactError("Native dependency list exceeds limit")
    module_name = kernel.GetModuleFileNameW
    module_name.argtypes = [wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
    module_name.restype = wintypes.DWORD
    identities = []
    for module in modules[:needed.value // ctypes.sizeof(wintypes.HMODULE)]:
        buffer = ctypes.create_unicode_buffer(32768)
        count = module_name(module, buffer, len(buffer))
        if not 0 < count < len(buffer):
            raise ArtifactError("Unidentified native dependency")
        identities.append(file_identity(Path(buffer.value)))
    return {str(index): item for index, item in enumerate(sorted(identities, key=identity_key))}


def windows_producer_identity(root: Path | None = None) -> dict | None:
    """Conservatively hash shipped bytes or source + entire interpreter/import roots.

    This intentionally over-invalidates. No release stamp or package version substitutes
    for executable/native bytes. Caller must treat None as fresh-work-only, never as a key.
    Run before importing new code and hold producer inputs immutable through publication.
    """
    try:
        native = _windows_native_identity()
        if getattr(sys, "frozen", False):
            components = {"executable": file_identity(Path(sys.executable)),
                          "bundle": _tree_identity(Path(sys._MEIPASS)), "native": native}
            kind = "windows-frozen"
        else:
            root = (root or Path(__file__).absolute().parents[1]).absolute()
            components = {name: _tree_identity(root / name) for name in ("app", "tools", "resources")}
            components["executable"] = file_identity(Path(sys.executable))
            # Includes stdlib, DLLs, codecs and the interpreter itself, not only imported modules.
            components["python"] = _tree_identity(Path(sys.base_prefix))
            dependencies = []
            covered = {root, root / "app", root / "tools", root / "resources/runtime", Path(sys.base_prefix)}
            for entry in sorted(set(sys.path + [sys.prefix])):
                path = Path(entry or os.getcwd()).absolute()
                if path in covered:
                    continue
                if not path.exists():
                    # CPython adds a stdlib zip path even when the directory stdlib is used.
                    if path == Path(sys.base_prefix) / f"python{sys.version_info.major}{sys.version_info.minor}.zip":
                        continue
                    raise ArtifactError("Unidentified import root")
                evidence = _tree_identity(path) if path.is_dir() else file_identity(path)
                dependencies.append(evidence)
            components["dependencies"] = sorted(dependencies, key=identity_key)
            components["native"] = native
            kind = "windows-source"
        return _producer({"schema": SCHEMA, "complete": True, "kind": kind, "components": components})
    except (ArtifactError, OSError, RuntimeError, ImportError):
        return None


def sync_file(path: Path) -> None:
    """Flush one existing regular file's bytes to stable storage; failures raise.

    POSIX fsyncs a read-only descriptor, as before. Windows FlushFileBuffers needs a
    handle with write access, so the file is opened read-write without truncation or
    creation; nothing is written. A file that cannot be opened that way raises.
    """
    flags = os.O_RDONLY if os.name != "nt" else os.O_RDWR | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def sync_directory(root: Path) -> None:
    if os.name == "nt":
        # Windows publication uses MOVEFILE_WRITE_THROUGH below. Opening directories for
        # FlushFileBuffers is unsupported on some Windows filesystems; do not fake fsync.
        return
    descriptor = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def replace_file(source: Path, target: Path) -> None:
    if os.name == "nt":
        import ctypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        move = kernel.MoveFileExW
        move.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
        move.restype = ctypes.c_int
        # A scanner or indexer briefly opening the fresh file without delete sharing makes
        # the replace fail with access denied or a sharing violation (measured about 1 in
        # 750 replaces in %TEMP%). Retry for a bounded time; the move stays all-or-nothing
        # and a persistent failure still raises.
        delay = 0.005
        for attempt in range(_REPLACE_ATTEMPTS):
            if move(str(source), str(target), 0x1 | 0x8):
                break
            error = ctypes.get_last_error()
            if error not in {5, 32} or attempt == _REPLACE_ATTEMPTS - 1:
                raise ctypes.WinError(error)
            time.sleep(delay)
            delay = min(delay * 2, 0.25)
    else:
        os.replace(source, target)
    sync_directory(target.parent)


def create_attempt(parent: Path, *, run_id: str, stage: str) -> Path:
    """Create a fresh owned directory; never reset/delete a previous attempt here."""
    if stage not in STAGES or not isinstance(run_id, str) or not 1 <= len(run_id) <= 128:
        raise ArtifactError("Invalid attempt owner")
    safe_file(parent, directory=True)
    path = parent / str(uuid.uuid4())
    path.mkdir()
    with (path / "attempt-owner.json").open("xb") as stream:
        stream.write(canonical_bytes({"schema": SCHEMA, "run_id": run_id, "stage": stage}))
        stream.flush()
        os.fsync(stream.fileno())
    sync_directory(path)
    sync_directory(parent)
    return path


def publish_receipt(root: Path, *, identity: dict, run_id: str, stage: str,
                    references: dict[str, str | None] | None = None,
                    expected_artifacts: dict | None = None,
                    failpoint: Callable[[str], None] | None = None) -> dict:
    """Verify all output bytes, fsync, then atomically publish the last commit marker.

    Exclusive ownership and no subsequent artifact writes are required. Failpoints are
    deterministic private probe hooks, never authorization. Kills can leave an inert temp;
    readers reject it as an extra file. Publication never adopts summary-only output.
    When supplied, expected_artifacts must match the first byte audit before publishing.
    """
    _input(identity)
    if stage not in STAGES or not isinstance(run_id, str) or not 1 <= len(run_id) <= 128:
        raise ArtifactError("Invalid receipt owner/stage")
    references = references or {name: None for name in sorted(REFERENCES)}
    if set(references) != REFERENCES:
        raise ArtifactError("References must explicitly name summary, delta and manifest")
    artifacts = tree_manifest(root, exclude=frozenset({RECEIPT_NAME}))
    if expected_artifacts is not None and artifacts != expected_artifacts:
        raise ArtifactError("Artifact file set or bytes differ from expected")
    if not artifacts or set(artifacts) <= {"device_patch_summary.json", "attempt-owner.json"}:
        raise ArtifactError("Summary/owner alone is not an artifact checkpoint")
    _stage_references(root, stage, identity, references, artifacts)
    record = {"schema": SCHEMA, "committed": True, "run_id": run_id, "stage": stage,
              "input_key": identity_key(identity), "producer_key": identity_key(identity["producer"]),
              "identity": identity, "artifacts": artifacts, "references": references}
    payload = canonical_bytes(record)
    hit = failpoint or (lambda name: None)
    hit("artifacts_verified")
    for name in artifacts:
        sync_file(root / name)
    hit("artifacts_synced")
    temp = root / ("." + RECEIPT_NAME + "." + str(uuid.uuid4()) + ".tmp")
    with temp.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    hit("receipt_synced")
    # Ensure no writer changed the artifact set between verification and publication.
    verify_manifest(root, artifacts, exclude=frozenset({RECEIPT_NAME, temp.name}))
    replace_file(temp, root / RECEIPT_NAME)
    hit("receipt_committed")
    verified = verify_receipt(root, identity=identity, stage=stage)
    hit("receipt_read_back")
    return verified


def _verify_receipt(root: Path, *, identity: dict | None = None, input_key: str | None = None,
                    stage: str | None = None) -> dict:
    """Rehash exact retained files and reject missing/partial/unknown publications.

    Caller must additionally reconcile current live game/APK/readiness evidence before
    mutation. Supplying identity is preferred; a raw key is for independently checked inputs.
    """
    record = read_record(root / RECEIPT_NAME)
    if (set(record) != {"schema", "committed", "run_id", "stage", "input_key", "producer_key",
                        "identity", "artifacts", "references"}
            or type(record["schema"]) is not int or record["schema"] != SCHEMA
            or record["committed"] is not True or record["stage"] not in STAGES
            or not isinstance(record["run_id"], str) or not 1 <= len(record["run_id"]) <= 128):
        raise ArtifactError("Unknown/incomplete receipt")
    saved = _input(record["identity"])
    if record["input_key"] != identity_key(saved) or record["producer_key"] != identity_key(saved["producer"]):
        raise ArtifactError("Receipt identity mismatch")
    if identity is not None:
        _input(identity)
        if record["input_key"] != identity_key(identity):
            raise ArtifactError("Inputs changed")
    if input_key is not None and record["input_key"] != input_key:
        raise ArtifactError("Input key changed")
    if stage is not None and record["stage"] != stage:
        raise ArtifactError("Stage changed")
    references = record["references"]
    if not isinstance(references, dict) or set(references) != REFERENCES:
        raise ArtifactError("Invalid artifact references")
    validate_manifest(record["artifacts"])
    if not record["artifacts"] or set(record["artifacts"]) <= {"device_patch_summary.json", "attempt-owner.json"}:
        raise ArtifactError("Summary/owner alone is not an artifact checkpoint")
    if RECEIPT_NAME in record["artifacts"]:
        raise ArtifactError("Receipt cannot include itself")
    _stage_references(root, record["stage"], saved, references, record["artifacts"])
    verify_manifest(root, record["artifacts"], exclude=frozenset({RECEIPT_NAME}))
    return record


def verify_receipt(root: Path, *, identity: dict | None = None, input_key: str | None = None,
                   stage: str | None = None) -> dict:
    """Read/revalidate retained output; every malformed/missing proof raises ArtifactError.

    A receipt proves retained content only. Caller separately reconciles current live
    inputs/readiness and owns the lock. It never grants authorization to mutate a device.
    """
    try:
        return _verify_receipt(root, identity=identity, input_key=input_key, stage=stage)
    except ArtifactError:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        raise ArtifactError("Missing or malformed artifact receipt") from error
