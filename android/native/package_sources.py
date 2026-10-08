"""Package the pinned custom-codec source archives, build recipe and available license texts."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

from build_wheels import SOURCES


def package_sources(source_directory: Path, output: Path, compression_directory: Path | None = None,
                    freetype_directory: Path | None = None, maven_directory: Path | None = None) -> dict:
    """Match each original archive by SHA-256 before making a component source companion."""
    archives = {hashlib.sha256(path.read_bytes()).hexdigest(): path
                for path in source_directory.glob("*.tar.gz")}
    sources = dict(SOURCES)
    if compression_directory is not None:
        from build_compression_wheels import SOURCES as compression_sources
        sources.update(compression_sources)
        archives.update({hashlib.sha256(path.read_bytes()).hexdigest(): path
                         for path in compression_directory.glob("*.tar.gz")})
    if freetype_directory is not None:
        from build_freetype_wheel import SOURCE_SHA256
        sources["chaquopy-freetype"] = ("2.9.1", SOURCE_SHA256)
        archives.update({hashlib.sha256(path.read_bytes()).hexdigest(): path
                         for path in freetype_directory.glob("*.tar.gz")})
    payloads: dict[str, bytes] = {}
    components = {}
    for name, (version, expected) in sources.items():
        if expected not in archives:
            raise ValueError(f"Pinned source archive is missing: {name} {version}")
        path = archives[expected]
        payloads[f"sources/{path.name}"] = path.read_bytes()
        components[name] = {"version": version, "source_sha256": expected, "archive": path.name}
    root = Path(__file__).resolve().parent
    for name in ("build_wheels.py", "package_sources.py", "collect_source_notices.py", "audit_notices.py", "audit_maven.py", "download_maven_sources.py", "THIRD_PARTY.md"):
        payloads[name] = (root / name).read_bytes()
    if compression_directory is not None:
        payloads["build_compression_wheels.py"] = (root / "build_compression_wheels.py").read_bytes()
    if freetype_directory is not None:
        payloads["build_freetype_wheel.py"] = (root / "build_freetype_wheel.py").read_bytes()
    for path in sorted((root / "licenses").glob("*.txt")):
        payloads[f"licenses/{path.name}"] = path.read_bytes()
    payloads["licenses/sources.json"] = (root / "licenses/sources.json").read_bytes()
    for name, provenance in json.loads(payloads["licenses/sources.json"]).items():
        contents = payloads.get(f"licenses/{name}")
        if contents is None or hashlib.sha256(contents).hexdigest() != provenance["sha256"]:
            raise ValueError(f"Notice provenance hash differs: {name}")
    maven_sources = {}
    if maven_directory is not None:
        manifest = (maven_directory / "manifest.json").read_bytes()
        records = json.loads(manifest)
        if records.get("schema") != 1:
            raise ValueError("Unsupported Maven source manifest")
        for component in records["components"]:
            coordinate = component["coordinate"]
            parts = coordinate.split(":")
            if len(parts) != 3 or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", part) or part in (".", "..") for part in parts):
                raise ValueError("Unsupported Maven source coordinate")
            _, name, version = parts
            if set(component["files"]) != {f"{name}-{version}.pom", f"{name}-{version}-sources.jar"}:
                raise ValueError(f"Incomplete Maven source set: {coordinate}")
            if coordinate in maven_sources:
                raise ValueError("Duplicate Maven source coordinate")
            for name, identity in component["files"].items():
                if Path(name).name != name or "\\" in name or not name.endswith((".pom", "-sources.jar")):
                    raise ValueError("Unsupported Maven source filename")
                path = maven_directory / name
                if "error" in identity or not path.is_file():
                    raise ValueError(f"Maven source is missing: {name}")
                contents = path.read_bytes()
                if len(contents) != identity["bytes"] or hashlib.sha256(contents).hexdigest() != identity["sha256"]:
                    raise ValueError(f"Maven source identity differs: {name}")
                if f"maven/{name}" in payloads:
                    raise ValueError(f"Duplicate Maven source filename: {name}")
                payloads[f"maven/{name}"] = contents
            maven_sources[coordinate] = component
        payloads["maven/manifest.json"] = manifest
    report = {"schema": 1, "scope": "Pinned codec sources and optional published Maven sources; application, embedded runtime and binary/source equivalence remain separate reviews.",
              "components": components, "maven_sources": maven_sources, "files": {
                  name: hashlib.sha256(value).hexdigest() for name, value in sorted(payloads.items())}}
    payloads["manifest.json"] = json.dumps(report, indent=2, sort_keys=True).encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_suffix(output.suffix + ".partial")
    try:
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, value in sorted(payloads.items()):
                archive.writestr(name, value)
        with zipfile.ZipFile(partial) as archive:
            if archive.testzip() is not None:
                raise ValueError("Source companion CRC verification failed")
            for name, value in payloads.items():
                if archive.read(name) != value:
                    raise ValueError(f"Source companion read-back differs: {name}")
        partial.replace(output)
    finally:
        partial.unlink(missing_ok=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compression-sources", type=Path)
    parser.add_argument("--freetype-sources", type=Path)
    parser.add_argument("--maven-sources", type=Path)
    args = parser.parse_args()
    report = package_sources(args.sources, args.output, args.compression_sources, args.freetype_sources, args.maven_sources)
    print(f"Verified {len(report['components'])} pinned codec sources and {len(report['maven_sources'])} published Maven source sets: {args.output}")


if __name__ == "__main__":
    main()
