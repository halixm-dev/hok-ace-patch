"""Extract bounded game snapshots and retain a complete source identity for Android recovery."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tarfile
from pathlib import Path, PurePosixPath

MAX_FILES = 8192
MAX_BYTES = 8 * 1024**3
GLOBAL_INDEX = "packages/builtin/Globalindex/GlobalIndexPrime.data"


def validate_path(name: str, *, directory: bool = False) -> None:
    """Mirror the privileged adapter's fixed scope, without normalizing unsafe paths."""
    if len(name) > 512 or "\\" in name or name.startswith("/"):
        raise ValueError("Invalid snapshot path")
    parts = name.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError("Invalid snapshot path")
    if parts[0] == "Watchdog":
        if len(parts) > 5 or (not directory and len(parts) < 2):
            raise ValueError("Unsupported Watchdog path")
        if any(not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", part) for part in parts[1:]):
            raise ValueError("Unsupported Watchdog filename")
        return
    if directory and name in ("packages", "packages/builtin", "packages/builtin/Globalindex"):
        return
    if directory and len(parts) in (3, 4) and parts[:2] == ["packages", "builtin"] and parts[2] in ("Merge", "CleanCopy"):
        if len(parts) == 3 or (re.fullmatch(r"[0-9]{1,10}", parts[3]) and int(parts[3]) <= 0xFFFFFFFF):
            return
        raise ValueError(f"Invalid updater package directory: {name}")
    if not directory and name == GLOBAL_INDEX:
        return
    if len(parts) != (2 if directory else 3) or parts[0] != "packages":
        raise ValueError(f"Unsupported package path: {name}")
    package = parts[1]
    if not re.fullmatch(r"[0-9]{1,10}", package) or int(package) > 0xFFFFFFFF:
        raise ValueError("Invalid package ID")
    if not directory and not re.fullmatch(rf"{re.escape(package)}(?:_[0-9]{{1,3}})?\.db|{re.escape(package)}\.info", parts[2]):
        raise ValueError("Unsupported package filename")


def extract_snapshot(archive: Path, destination: Path, *, maximum_bytes: int = MAX_BYTES) -> dict:
    """Stream a fresh tar into private storage; links, duplicates and unknown files fail closed."""
    if destination.exists() or not 0 < maximum_bytes <= MAX_BYTES:
        raise ValueError("Snapshot requires a fresh destination and a bounded budget")
    destination.mkdir(parents=True)
    files: dict = {}
    directories: list[str] = []
    seen: set[str] = set()
    total = 0
    try:
        with tarfile.open(archive, "r|") as source:
            for member in source:
                name = member.name.rstrip("/") if member.isdir() else member.name
                validate_path(name, directory=member.isdir())
                if name in seen or not (member.isdir() or member.isfile()):
                    raise ValueError("Snapshot contains a duplicate or non-regular entry")
                seen.add(name)
                if len(seen) > MAX_FILES * 2:
                    raise ValueError("Snapshot contains too many entries")
                target = destination.joinpath(*PurePosixPath(name).parts)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    directories.append(name)
                    continue
                total += member.size
                if member.size < 0 or total > maximum_bytes or len(files) >= MAX_FILES:
                    raise ValueError("Snapshot exceeds its storage budget")
                target.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                remaining = member.size
                with source.extractfile(member) as payload, target.open("xb") as output:
                    while remaining:
                        block = payload.read(min(1024 * 1024, remaining))
                        if not block:
                            raise ValueError("Truncated snapshot member")
                        output.write(block)
                        digest.update(block)
                        remaining -= len(block)
                    output.flush()
                    os.fsync(output.fileno())
                files[name] = {"bytes": member.size, "sha256": digest.hexdigest()}
        if "packages/1/1.info" not in files or not files:
            raise ValueError("Snapshot has no game version identity")
        version = json.loads((destination / "packages/1/1.info").read_text(encoding="utf-8"))
        if not isinstance(version, dict) or not isinstance(version.get("version"), str):
            raise ValueError("Unsupported game version identity")
        manifest = {"schema": 1, "files": files, "directories": sorted(directories),
                    "bytes": total, "game_info": version}
        temporary = destination / "manifest.json.partial"
        with temporary.open("x", encoding="utf-8") as output:
            json.dump(manifest, output, indent=2, sort_keys=True)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(destination / "manifest.json")
        if os.name == "posix":
            parents = [path for path in destination.rglob("*") if path.is_dir()]
            for directory in [*sorted(parents, key=lambda path: len(path.parts), reverse=True), destination, destination.parent]:
                descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        return manifest
    except BaseException:
        # This function owns only the fresh private destination it just created.
        shutil.rmtree(destination)
        raise


def verify_snapshot(destination: Path) -> dict:
    """Rehash retained originals before trusting them for build or rollback."""
    manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != 1 or not 0 < len(manifest["files"]) <= MAX_FILES:
        raise ValueError("Unsupported snapshot manifest")
    actual_files = set()
    for root_name in ("packages", "Watchdog"):
        root = destination / root_name
        if root.is_symlink():
            raise ValueError("Snapshot root contains a link")
        for path in root.rglob("*"):
            if path.is_symlink():
                raise ValueError("Snapshot contains a link")
            if path.is_file():
                actual_files.add(path.relative_to(destination).as_posix())
    if actual_files != set(manifest["files"]):
        raise ValueError("Snapshot file set changed")
    for name, expected in manifest["files"].items():
        validate_path(name)
        path = destination / name
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if path.stat().st_size != expected["bytes"] or digest != expected["sha256"]:
            raise ValueError(f"Snapshot file changed: {name}")
    return manifest
