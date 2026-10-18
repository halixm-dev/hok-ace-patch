"""Extract bounded game snapshots and retain a complete source identity for Android recovery."""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import tarfile
from pathlib import Path, PurePosixPath
from typing import BinaryIO

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


class HashingReader(io.RawIOBase):
    """A read-only stream that hashes and counts every byte read through it, refusing more than <limit>."""

    def __init__(self, stream: BinaryIO, limit: int):
        self.stream, self.limit, self.bytes, self.hash = stream, limit, 0, hashlib.sha256()

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:
        count = self.stream.readinto(buffer)
        if count:
            self.bytes += count
            if self.bytes > self.limit:
                raise ValueError("Snapshot stream exceeds its storage budget")
            self.hash.update(memoryview(buffer)[:count])
        return count or 0

    def drain(self) -> None:
        """Read to the end, so the transport identity covers the tar's trailing padding too."""
        while self.read(1024 * 1024):
            pass


def extract_snapshot_stream(stream: BinaryIO, destination: Path, *, maximum_bytes: int = MAX_BYTES) -> dict:
    """`extract_snapshot` from a stream, read to its end: the manifest plus the stream's bytes and SHA-256."""
    reader = HashingReader(stream, maximum_bytes)
    manifest = extract_snapshot(reader, destination, maximum_bytes=maximum_bytes)
    try:
        reader.drain()
    except BaseException:
        shutil.rmtree(destination)
        raise
    return {"manifest": manifest, "bytes": reader.bytes, "sha256": reader.hash.hexdigest()}


def extract_snapshot(archive: Path | BinaryIO, destination: Path, *, maximum_bytes: int = MAX_BYTES) -> dict:
    """Stream a fresh tar (a path or a readable stream) into private storage; links, duplicates and
    unknown files fail closed."""
    if destination.exists() or not 0 < maximum_bytes <= MAX_BYTES:
        raise ValueError("Snapshot requires a fresh destination and a bounded budget")
    destination.mkdir(parents=True)
    files: dict = {}
    directories: list[str] = []
    seen: set[str] = set()
    total = 0
    try:
        opened = (tarfile.open(archive, "r|") if isinstance(archive, Path)
                  else tarfile.open(fileobj=archive, mode="r|"))
        with opened as source:
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


def read_manifest(destination: Path) -> dict:
    """The retained manifest, unverified: for estimates only, never to trust the files it names."""
    manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != 1 or not 0 < len(manifest["files"]) <= MAX_FILES:
        raise ValueError("Unsupported snapshot manifest")
    return manifest


def package_files_at(manifest: dict, hashes: set[str]) -> list[str]:
    """`pristine_delta.files_at` over a verified snapshot, read from its manifest instead of rehashing."""
    found = []
    for name, entry in manifest["files"].items():
        parts = name.split("/")
        if (len(parts) == 3 and parts[0] == "packages" and parts[1].isdecimal()
                and parts[2].endswith(".db") and entry["sha256"] in hashes):
            found.append(f"{parts[1]}/{parts[2]}")
    return sorted(found, key=lambda name: (int(name.split("/")[0]), name))


def verify_snapshot(destination: Path) -> dict:
    """Rehash retained originals before trusting them for build or rollback."""
    manifest = read_manifest(destination)
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
