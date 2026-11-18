"""Describe explicitly supplied private Android probe inputs; never contacts a phone.

APKs and optional source files must already be below --root (outside this repo).
Identity JSON must come from ApkIdentity.read, not guessed manifest/signature values.
The Android preflight independently verifies identities and exact entry/file manifests.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def _digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _relative(root: Path, path: Path) -> str:
    if path.is_symlink() or path.absolute() != path.resolve():
        raise ValueError(f"Fixture symlink refused: {path}")
    return path.resolve().relative_to(root).as_posix()


def _apk(root: Path, path: Path, identity_file: Path) -> dict:
    identity = json.loads(identity_file.read_text(encoding="utf-8"))
    required = {"bytes", "sha256", "package", "version_code", "version_name", "certificate_sha256", "debuggable"}
    if set(identity) != required or identity["bytes"] != path.stat().st_size or identity["sha256"] != _digest(path):
        raise ValueError(f"Missing or mismatched ApkIdentity JSON for {path}")
    entries = {}
    with zipfile.ZipFile(path) as archive:
        for entry in archive.infolist():
            if entry.filename in entries:
                raise ValueError(f"Duplicate APK entry: {entry.filename}")
            with archive.open(entry) as stream:
                entries[entry.filename] = hashlib.file_digest(stream, "sha256").hexdigest()
    if "AndroidManifest.xml" not in entries:
        raise ValueError(f"Missing AndroidManifest.xml: {path}")
    return {"path": _relative(root, path), "identity": identity, "entries": entries}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--normal", required=True, type=Path)
    parser.add_argument("--normal-identity", required=True, type=Path)
    parser.add_argument("--access", required=True, type=Path)
    parser.add_argument("--access-identity", required=True, type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--staged-hashes", type=Path)
    parser.add_argument("--expected-counts", type=Path)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    if root.is_relative_to(ROOT):
        parser.error("Large private inputs must stay outside this repository")
    try:
        value = {"schema": 1, "normal": _apk(root, args.normal.absolute(), args.normal_identity),
                 "access": _apk(root, args.access.absolute(), args.access_identity)}
        if any((args.source_root, args.staged_hashes, args.expected_counts)):
            if not all((args.source_root, args.staged_hashes, args.expected_counts)):
                raise ValueError("Full fixture requires --source-root, --staged-hashes and --expected-counts together")
            source = args.source_root.absolute()
            value["source_root"] = _relative(root, source)
            value["source_files"] = {_relative(source, path): _digest(path)
                                     for path in sorted(source.rglob("*")) if path.is_file()}
            value["staged_hashes"] = json.loads(args.staged_hashes.read_text(encoding="utf-8"))
            value["expected_counts"] = json.loads(args.expected_counts.read_text(encoding="utf-8"))
            if not value["source_files"] or not value["staged_hashes"]:
                raise ValueError("Empty source or staged manifest")
        output = root / "fixture.json"
        if output.exists():
            raise ValueError(f"Refusing to replace existing descriptor: {output}")
        encoded = json.dumps(value, indent=2, sort_keys=True).encode("utf-8")
        if len(encoded) > 2 * 1024 * 1024:
            raise ValueError("Descriptor exceeds Android's 2 MiB bound")
        output.write_bytes(encoded)
        print(output)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
