"""Keep the pristine bytes an install overwrote, and rebuild the pristine layer from them.

A **pristine delta** describes one install: for every package file it wrote, the pristine length and
SHA-256, the staged length and SHA-256, and the pristine bytes of each range the install overwrote in
place. Data the install appended past the pristine end is not kept: truncating to the pristine length
removes it. Both patchers make one after a verified install and apply it on the next run, so a language
switch or a newer translation builds from the pristine layer without clearing the game's data.

Paths are relative to the override layer's `packages/` directory (`1/1_0.db`): the phone's
`files/QtsVFSCache/packages/`, the Windows session's `game/WXQ_Data/Package/builtin/`, a staged output
directory. The delta always points at pristine, never at a previous install, and each file's entry is
valid exactly while that file holds the staged SHA-256 it records.

File format: `MAGIC`, one line of JSON (the header: `schema`, `info`, `files`, `body_bytes`,
`body_sha256`, and `assets` when fingerprinted), then a zlib body holding every range's pristine bytes
in header order.

**After an in-game update.** A file the update rewrote matches neither side of its entry, so the delta
cannot rebuild it. `accept_replaced` decides, package by package, whether the update's bytes stand as
the new pristine: no file of the package may still hold this patcher's bytes, and no asset this
install changed may still be at its staged bytes (`assets`: per package, each changed asset's
uncompressed SHA-256 on both sides, from `asset_fingerprints`). The caller then also requires the text
pass to read the layer as pristine. A delta made before `assets` existed accepts no replaced file.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

SCHEMA = 1
MAGIC = b"HOKACE-PRISTINE-DELTA\n"
# The measured parameters (lab notebook, 2026-10-17, "Reverse delta from a staged layer back to the
# pristine one"): changed 4 KiB blocks, narrowed to 64-byte sub-blocks, runs closer than 256 coalesced.
BLOCK_SIZE = 4096
SUB_BLOCK_SIZE = 64
COALESCE_GAP = 256
# Read size while comparing; a whole multiple of BLOCK_SIZE so block boundaries stay aligned.
READ_SIZE = 256 * BLOCK_SIZE
# Where each patcher keeps its delta and the staged hashes of every install it made.
DELTA_NAME = "delta.bin"
STAGED_HASHES_NAME = "staged-hashes.json"

# A rebuild outcome per file the delta names.
REBUILT = "rebuilt"
ALREADY_PRISTINE = "pristine"
MISSING = "missing"
CHANGED = "changed"


class DeltaError(Exception):
    """A delta that cannot be read or does not rebuild its pristine file; the front ends report it."""


@dataclass(frozen=True)
class FileEntry:
    """One package file an install wrote. `pristine_sha256` is None for a file the install created."""

    path: str
    pristine_size: int
    pristine_sha256: str | None
    staged_size: int
    staged_sha256: str
    ranges: tuple[tuple[int, bytes], ...] = ()

    @property
    def created(self) -> bool:
        return self.pristine_sha256 is None


@dataclass(frozen=True)
class Delta:
    files: tuple[FileEntry, ...]
    info: dict = field(default_factory=dict)
    # {package id: {asset hash: [pristine SHA-256 or None, staged SHA-256]}}; None when not fingerprinted.
    assets: dict | None = None

    def entry(self, path: str) -> FileEntry | None:
        return next((item for item in self.files if item.path == path), None)

    @property
    def range_bytes(self) -> int:
        return sum(len(data) for item in self.files for _, data in item.ranges)

    @property
    def staged_hashes(self) -> set[str]:
        """The hashes only an install writes; a file staged unchanged is still at its pristine hash."""
        return {item.staged_sha256 for item in self.files if item.staged_sha256 != item.pristine_sha256}


@dataclass
class RebuildReport:
    """Per file the delta names: rebuilt from staged, already pristine, or matching neither."""

    rebuilt: list[str] = field(default_factory=list)
    pristine: list[str] = field(default_factory=list)
    unmatched: dict[str, str] = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        return not self.unmatched


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def package_files(directory: Path) -> list[str]:
    """Every `<package id>/<file>.db` under <directory>, as delta paths, in a stable order."""
    found = []
    for package in directory.iterdir():
        if package.is_dir() and package.name.isdecimal():
            found += [f"{package.name}/{path.name}" for path in package.iterdir()
                      if path.is_file() and path.suffix == ".db"]
    return sorted(found, key=lambda name: (int(name.split("/")[0]), name))


def _changed_sub_blocks(pristine: bytes, staged: bytes, base: int) -> Iterable[tuple[int, int]]:
    for start in range(0, len(pristine), SUB_BLOCK_SIZE):
        end = min(start + SUB_BLOCK_SIZE, len(pristine))
        if pristine[start:end] != staged[start:end]:
            yield base + start, base + end


def changed_ranges(pristine_path: Path, staged_path: Path) -> tuple[list[tuple[int, int]], str, str]:
    """The pristine ranges <staged_path> overwrote, as `(start, end)`, and both files' SHA-256.

    Both files are read whole from disk. A pristine tail past the staged end counts as overwritten;
    staged bytes past the pristine end are appended data, which truncation removes.
    """
    pristine_hash, staged_hash = hashlib.sha256(), hashlib.sha256()
    changed: list[tuple[int, int]] = []
    offset = 0
    with pristine_path.open("rb") as pristine_stream, staged_path.open("rb") as staged_stream:
        while True:
            pristine = pristine_stream.read(READ_SIZE)
            staged = staged_stream.read(READ_SIZE)
            pristine_hash.update(pristine)
            staged_hash.update(staged)
            if not pristine and not staged:
                break
            if pristine and pristine != staged[:len(pristine)]:
                for start in range(0, len(pristine), BLOCK_SIZE):
                    block = pristine[start:start + BLOCK_SIZE]
                    if block != staged[start:start + len(block)]:
                        changed += _changed_sub_blocks(block, staged[start:start + len(block)], offset + start)
            offset += len(pristine)
    merged: list[tuple[int, int]] = []
    for start, end in changed:
        if merged and start - merged[-1][1] < COALESCE_GAP:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return merged, pristine_hash.hexdigest(), staged_hash.hexdigest()


def make(pristine_dir: Path, staged_dir: Path, *, info: dict | None = None,
         fingerprint: bool = False) -> Delta:
    """The delta that takes every package file under <staged_dir> back to its copy in <pristine_dir>.

    <staged_dir> is a staged output (`<id>/<file>.db`, as `build_patch` writes it) or a layer holding
    the installed bytes; <pristine_dir> is the pristine layer the install was built from. With
    <fingerprint> (it needs the translation runtime), every staged package's changed assets are
    recorded for `accept_replaced`; a package that will not read is left out of them.
    """
    entries = []
    for name in package_files(staged_dir):
        staged = staged_dir / name
        pristine = pristine_dir / name
        if not pristine.is_file():
            entries.append(FileEntry(name, 0, None, staged.stat().st_size, sha256_file(staged)))
            continue
        spans, pristine_sha, staged_sha = changed_ranges(pristine, staged)
        ranges = []
        with pristine.open("rb") as stream:
            for start, end in spans:
                stream.seek(start)
                ranges.append((start, stream.read(end - start)))
        entries.append(FileEntry(name, pristine.stat().st_size, pristine_sha,
                                 staged.stat().st_size, staged_sha, tuple(ranges)))
    assets = None
    if fingerprint:
        from asset_fingerprints import UnreadablePackage, changed_assets

        assets = {}
        for package in sorted({entry.path.split("/")[0] for entry in entries}, key=int):
            try:
                assets[package] = changed_assets(pristine_dir / package, staged_dir / package)
            except UnreadablePackage:
                continue
    return Delta(tuple(entries), dict(info or {}), assets)


def _fsync_directory(directory: Path) -> None:
    if os.name == "nt":
        return  # Windows has no directory handle to flush; os.replace is durable on NTFS
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_atomic(path: Path, data: bytes) -> None:
    """Replace <path> with <data> only once the new bytes are durable."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    try:
        with partial.open("wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(partial, path)
        _fsync_directory(path.parent)
    finally:
        partial.unlink(missing_ok=True)


def encode(delta: Delta) -> bytes:
    body = b"".join(data for item in delta.files for _, data in item.ranges)
    header = {
        "schema": SCHEMA,
        "info": delta.info,
        "files": [{
            "path": item.path,
            "pristine_size": item.pristine_size,
            "pristine_sha256": item.pristine_sha256,
            "staged_size": item.staged_size,
            "staged_sha256": item.staged_sha256,
            "ranges": [[offset, len(data)] for offset, data in item.ranges],
        } for item in delta.files],
        "body_bytes": len(body),
        "body_sha256": hashlib.sha256(body).hexdigest(),
    }
    if delta.assets is not None:
        header["assets"] = delta.assets
    return MAGIC + json.dumps(header, separators=(",", ":")).encode("utf-8") + b"\n" + zlib.compress(body, 6)


def decode(data: bytes) -> Delta:
    if not data.startswith(MAGIC):
        raise DeltaError("not a pristine delta")
    line_end = data.find(b"\n", len(MAGIC))
    try:
        header = json.loads(data[len(MAGIC):line_end].decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as error:
        raise DeltaError(f"pristine delta header does not read: {error}") from error
    if header.get("schema") != SCHEMA:
        raise DeltaError(f"pristine delta schema {header.get('schema')!r} is not {SCHEMA}")
    try:
        body = zlib.decompress(data[line_end + 1:])
    except zlib.error as error:
        raise DeltaError(f"pristine delta body does not decompress: {error}") from error
    if len(body) != header["body_bytes"] or hashlib.sha256(body).hexdigest() != header["body_sha256"]:
        raise DeltaError("pristine delta body does not match its header")
    files = []
    position = 0
    for item in header["files"]:
        path = item["path"]
        parts = path.split("/")
        if len(parts) != 2 or not parts[0].isdecimal() or parts[1] in ("", ".", ".."):
            raise DeltaError(f"pristine delta names an invalid path: {path!r}")
        ranges = []
        for offset, length in item["ranges"]:
            ranges.append((offset, body[position:position + length]))
            position += length
        files.append(FileEntry(path, item["pristine_size"], item["pristine_sha256"],
                               item["staged_size"], item["staged_sha256"], tuple(ranges)))
    assets = header.get("assets")
    if assets is not None and not (isinstance(assets, dict) and all(
            isinstance(package, str) and package.isdecimal() and isinstance(changed, dict)
            and all(isinstance(pair, list) and len(pair) == 2 for pair in changed.values())
            for package, changed in assets.items())):
        raise DeltaError("pristine delta's asset record does not read")
    return Delta(tuple(files), header.get("info") or {}, assets)


def write(delta: Delta, path: Path) -> None:
    write_atomic(path, encode(delta))


def read(path: Path) -> Delta:
    try:
        data = path.read_bytes()
    except OSError as error:
        raise DeltaError(f"pristine delta cannot be read: {error}") from error
    return decode(data)


def _apply(entry: FileEntry, target: Path) -> None:
    """Turn <target>, holding the staged bytes, into the pristine file, and verify it."""
    with target.open("r+b") as stream:
        stream.truncate(entry.pristine_size)
        for offset, data in entry.ranges:
            stream.seek(offset)
            stream.write(data)
    if target.stat().st_size != entry.pristine_size or sha256_file(target) != entry.pristine_sha256:
        raise DeltaError(f"{entry.path}: the rebuilt file does not match its pristine SHA-256")


def classify(entry: FileEntry, layer_dir: Path) -> str:
    """Whether <layer_dir>'s copy of <entry> is at its staged or pristine bytes, missing, or changed."""
    path = layer_dir / entry.path
    if not path.is_file():
        return ALREADY_PRISTINE if entry.created else MISSING
    size = path.stat().st_size
    if size not in (entry.staged_size, entry.pristine_size):
        return CHANGED
    digest = sha256_file(path)
    # Pristine first: a file the install staged unchanged is at both, and needs no rebuild.
    if not entry.created and size == entry.pristine_size and digest == entry.pristine_sha256:
        return ALREADY_PRISTINE
    if size == entry.staged_size and digest == entry.staged_sha256:
        return REBUILT
    return CHANGED


def rebuild(layer_dir: Path, delta: Delta, out_dir: Path, *, fallback: Delta | None = None,
            log: Callable[[str], None] | None = None) -> RebuildReport:
    """Write the pristine copy of every file <delta> names, read from <layer_dir>, into <out_dir>.

    A file is taken only at its entry's staged length and SHA-256 (rebuilt) or its pristine ones (copied
    as is), and every rebuilt file is verified against the pristine SHA-256. A file the install created
    rebuilds as deleted. A file matching neither, or missing, is reported in `unmatched` and left alone:
    the caller decides whether that refuses the run. <out_dir> may be <layer_dir>, to rebuild in place.

    <fallback> is the delta of an install that may have been cut off part way: a file <delta> does not
    match is tried against its entry too. Both point at the same pristine layer, so either entry
    rebuilds the same pristine file.
    """
    report = RebuildReport()
    in_place = layer_dir.resolve() == out_dir.resolve()
    entries = {item.path: [item] for item in delta.files}
    for item in fallback.files if fallback else ():
        entries.setdefault(item.path, []).append(item)
    for candidates in entries.values():
        for entry in candidates:
            state = classify(entry, layer_dir)
            if state not in (MISSING, CHANGED):
                break
        if state in (MISSING, CHANGED):
            report.unmatched[entry.path] = state
            continue
        source, target = layer_dir / entry.path, out_dir / entry.path
        if entry.created:
            target.unlink(missing_ok=True)
        elif not in_place:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        if state == REBUILT and not entry.created:
            _apply(entry, target)
        (report.rebuilt if state == REBUILT else report.pristine).append(entry.path)
        if log:
            log(f"{entry.path}: {state}")
    return report


def accept_replaced(layer_dir: Path, delta: Delta, report: RebuildReport, *,
                    fallback: Delta | None = None) -> tuple[list[str], dict[str, str]]:
    """Which files an update replaced stand as the new pristine, and why each other package cannot.

    Returns (accepted file paths, {package id: reason}). <report> is `rebuild`'s over <layer_dir>, which
    holds the phone's bytes for every package that has a file in `report.unmatched`. A package's
    replaced files are accepted only when none of its files is still at its staged bytes, and none of
    the assets the install changed is still at its staged bytes (read from <layer_dir>). A package
    the update removed whole is accepted too. Text the update left in a file is caught afterwards by
    the text signal (`text_not_pristine`), which the caller must also require.
    """
    from asset_fingerprints import UnreadablePackage, package_assets

    entries: dict[str, list[FileEntry]] = {}
    for item in [*delta.files, *(fallback.files if fallback else ())]:
        entries.setdefault(item.path.split("/")[0], []).append(item)
    recorded_by_package = {**((fallback.assets if fallback else None) or {}), **(delta.assets or {})}
    accepted: list[str] = []
    refused: dict[str, str] = {}
    for package in sorted({name.split("/")[0] for name in report.unmatched}, key=int):
        ours = sorted({item.path for item in entries[package] if item.path in report.rebuilt})
        if ours:
            refused[package] = (f"{', '.join(ours)} still holds this patcher's bytes, "
                                "while the update changed the rest")
            continue
        unmatched = sorted({item.path for item in entries[package] if item.path in report.unmatched})
        missing = [name for name in unmatched if report.unmatched[name] == MISSING]
        if not (layer_dir / package / f"{package}.db").is_file():
            if len(missing) == len(unmatched):
                accepted += unmatched  # the update removed the package
            else:
                refused[package] = "its index is missing"
            continue
        if missing:
            refused[package] = f"{', '.join(missing)} is missing"
            continue
        recorded = recorded_by_package.get(package)
        if recorded is None:
            refused[package] = "no record of the assets this patcher changed in it (an older patcher version)"
            continue
        try:
            current = package_assets(layer_dir / package, set(recorded))
        except UnreadablePackage as error:
            refused[package] = f"it does not read ({error})"
            continue
        surviving = [name for name, (_, staged) in recorded.items() if current.get(name) == staged]
        if surviving:
            refused[package] = f"{len(surviving)} of the assets this patcher changed are still translated"
            continue
        accepted += unmatched
    return accepted, refused


def text_not_pristine(summary: dict) -> str | None:
    """Why a `build_patch` summary says its layer was not the pristine one, or None when it was.

    The game keeps no per-file pristine hash, so the text pass is the witness: over the pristine layer
    it translates records in every text table it reads, while over a translated layer it reads tables
    with nothing left to translate (lab notebook, 2026-10-17, "The pristine delta shipped"). The tables it
    planned are the ones staged in place, relocated, or reported in
    `text_skipped`; `counts["tables"]` is every catalog table the scan read.
    """
    scanned = summary.get("counts", {}).get("tables", 0)
    planned = sum(entry["stage_report"]["replacement_count"] for entry in summary.get("packages", [])
                  if entry.get("mode") in ("full", "fit-only", "relocated-text"))
    planned += sum(entry.get("dropped_count", 0) for entry in summary.get("text_skipped", []))
    if planned == 0:
        return "the text pass found no Chinese text table"
    if planned < scanned:
        return f"the text pass found Chinese in only {planned} of the {scanned} text tables it read"
    return None


def files_at(layer_dir: Path, hashes: set[str]) -> list[str]:
    """The package files under <layer_dir> whose SHA-256 is one of <hashes>."""
    if not hashes:
        return []
    return [name for name in package_files(layer_dir) if sha256_file(layer_dir / name) in hashes]


def load_staged_hashes(path: Path) -> set[str]:
    """The staged SHA-256 of every file every install of this patcher wrote; empty when none is kept."""
    try:
        return set(json.loads(path.read_text(encoding="utf-8"))["sha256"])
    except (OSError, ValueError, KeyError, TypeError):
        return set()


def record_staged_hashes(path: Path, hashes: Iterable[str]) -> None:
    """Add <hashes> to the record at <path>, durably."""
    merged = sorted(load_staged_hashes(path) | set(hashes))
    write_atomic(path, json.dumps({"schema": SCHEMA, "sha256": merged}, indent=1).encode("utf-8"))
