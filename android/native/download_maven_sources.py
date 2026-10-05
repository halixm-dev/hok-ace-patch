"""Retain published source JARs and POMs for an exact resolved Maven runtime inventory."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import re
import urllib.request
from pathlib import Path

MAX_DOWNLOAD = 8 * 1024 * 1024
REPOSITORIES = {"androidx.annotation": "https://dl.google.com/dl/android/maven2/",
                "dev.rikka.shizuku": "https://repo.maven.apache.org/maven2/",
                "org.jetbrains": "https://repo.maven.apache.org/maven2/",
                "org.jetbrains.kotlin": "https://repo.maven.apache.org/maven2/"}


def download(inventory: Path, output: Path) -> dict:
    """Reuse hash-verified originals; source identity is not binary/source reproducibility."""
    resolved = json.loads(inventory.read_text(encoding="utf-8"))
    if resolved.get("schema") != 1 or not resolved.get("components"):
        raise ValueError("Unsupported Maven runtime inventory")
    old_manifest = output / "manifest.json"
    old = {}
    if old_manifest.is_file():
        manifest = json.loads(old_manifest.read_text(encoding="utf-8"))
        if manifest.get("schema") != 1:
            raise ValueError("Unsupported retained source manifest")
        old = {record["coordinate"]: record for record in manifest["components"]}
    filenames = set()
    coordinates = set()
    for row in resolved["components"]:
        parts = row["coordinate"].split(":")
        if len(parts) != 3 or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", part) or part in (".", "..") for part in parts):
            raise ValueError("Unsupported Maven coordinate")
        group, name, version = parts
        if group not in REPOSITORIES or row["coordinate"] in coordinates:
            raise ValueError("Unsupported repository or duplicate Maven coordinate")
        coordinates.add(row["coordinate"])
        for filename in (f"{name}-{version}.pom", f"{name}-{version}-sources.jar"):
            if filename in filenames:
                raise ValueError("Maven source filename collision")
            filenames.add(filename)
    output.mkdir(parents=True, exist_ok=True)
    pending: dict[str, bytes] = {}

    def obtain(row: dict) -> dict:
        group, name, version = row["coordinate"].split(":")
        base = REPOSITORIES[group] + group.replace(".", "/") + f"/{name}/{version}/"
        record = {"coordinate": row["coordinate"], "binary_sha256": row["sha256"], "files": {}}
        for filename in (f"{name}-{version}.pom", f"{name}-{version}-sources.jar"):
            url, target = base + filename, output / filename
            previous = old.get(row["coordinate"], {})
            identity = previous.get("files", {}).get(filename)
            if target.exists():
                content = target.read_bytes()
                if identity is None or previous.get("binary_sha256") != row["sha256"] or \
                        identity.get("url") != url or identity.get("bytes") != len(content) or \
                        identity.get("sha256") != hashlib.sha256(content).hexdigest():
                    raise ValueError(f"Retained source identity differs: {filename}")
            else:
                with urllib.request.urlopen(url, timeout=30) as response:
                    content = response.read(MAX_DOWNLOAD + 1)
                if not content or len(content) > MAX_DOWNLOAD:
                    raise ValueError(f"Published source exceeds download bound: {filename}")
                if identity is not None and (previous.get("binary_sha256") != row["sha256"] or
                        identity.get("url") != url or identity.get("bytes") != len(content) or
                        identity.get("sha256") != hashlib.sha256(content).hexdigest()):
                    raise ValueError(f"Previously recorded published source differs: {filename}")
                pending[filename] = content
            record["files"][filename] = {"url": url, "bytes": len(content),
                                          "sha256": hashlib.sha256(content).hexdigest()}
        return record

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as workers:
        records = list(workers.map(obtain, resolved["components"]))
    result = {"schema": 1, "components": records}
    temporary_manifest = output / "manifest.json.partial"
    temporary_manifest.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    temporary_manifest.replace(old_manifest)
    # Record expected identities before publishing any new source file. A failed/interrupted
    # write can be retried against that identity instead of adopting an unknown partial file.
    for filename, content in pending.items():
        target = output / filename
        temporary = output / (filename + ".partial")
        temporary.write_bytes(content)
        temporary.replace(target)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = download(args.inventory, args.output)
    print(f"Retained {len(result['components'])} published Maven source/POM sets with SHA-256 records")


if __name__ == "__main__":
    main()
