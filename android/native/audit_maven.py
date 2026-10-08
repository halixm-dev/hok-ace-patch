"""Bind resolved runtime artifacts to cached POM license metadata without network access."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def audit(inventory: Path, cache: Path, published: Path | None = None, notice_output: Path | None = None) -> dict:
    """Verify cached artifact hashes; absent metadata remains explicitly unresolved."""
    source = json.loads(inventory.read_text(encoding="utf-8"))
    if source.get("schema") != 1 or not source.get("components"):
        raise ValueError("Unsupported resolved Maven inventory")
    components = []
    seen = set()
    published_records = {}
    if published is not None:
        manifest = json.loads((published / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("schema") != 1:
            raise ValueError("Unsupported published source inventory")
        for record in manifest["components"]:
            if record["coordinate"] in published_records:
                raise ValueError("Duplicate published source coordinate")
            published_records[record["coordinate"]] = record
    source_notices = bytearray(b"Published Maven source copyright/license comments\n"
        b"Leading comment inventory, not a complete redistribution review or binary/source reproducibility proof.\n")
    for item in source["components"]:
        coordinate = item["coordinate"]
        parts = coordinate.split(":")
        if len(parts) != 3 or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", part) or part in (".", "..") for part in parts):
            raise ValueError("Unsupported Maven coordinate")
        if coordinate in seen:
            raise ValueError("Duplicate resolved Maven coordinate")
        seen.add(coordinate)
        group, name, version = parts
        filename = item["artifact"]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+\.(?:jar|aar)", filename):
            raise ValueError("Invalid resolved artifact filename")
        root = cache / group / name / version
        candidates = [path for path in root.rglob(filename) if path.is_file() and
                      path.stat().st_size == item["bytes"] and digest(path) == item["sha256"]]
        if not candidates:
            raise ValueError(f"Resolved artifact missing or changed: {coordinate}")
        embedded = []
        with zipfile.ZipFile(candidates[0]) as archive:
            def notice_names(source: zipfile.ZipFile, prefix: str = "") -> None:
                for entry in source.namelist():
                    if not entry.endswith("/") and any(token in Path(entry).name.upper()
                                                       for token in ("LICENSE", "NOTICE", "COPYING")):
                        embedded.append({"path": prefix + entry,
                                         "sha256": hashlib.sha256(source.read(entry)).hexdigest()})
            notice_names(archive)
            if "classes.jar" in archive.namelist():
                with zipfile.ZipFile(io.BytesIO(archive.read("classes.jar"))) as classes:
                    notice_names(classes, "classes.jar!/")
        record = {**item, "binary_verified": True, "embedded_notices": embedded, "licenses": [],
                  "binary_source_equivalence_verified": False}
        poms = list(root.rglob(f"{name}-{version}.pom"))
        published_pom = None
        if published is not None:
            origin = published_records.get(coordinate)
            if origin is None or origin["binary_sha256"] != item["sha256"]:
                raise ValueError(f"Published source is not bound to this binary inventory: {coordinate}")
            for published_name in (f"{name}-{version}.pom", f"{name}-{version}-sources.jar"):
                identity = origin["files"].get(published_name)
                path = published / published_name
                if identity is None or "error" in identity or not path.is_file() or \
                        path.stat().st_size != identity["bytes"] or digest(path) != identity["sha256"]:
                    raise ValueError(f"Published metadata/source changed: {coordinate} {published_name}")
            published_pom = published / f"{name}-{version}.pom"
            if poms and any(digest(path) != digest(published_pom) for path in poms):
                raise ValueError(f"Cached and published POM differ: {coordinate}")
            poms = [published_pom]
            sources = published / f"{name}-{version}-sources.jar"
            blocks: dict[bytes, list[str]] = {}
            with zipfile.ZipFile(sources) as archive:
                if archive.testzip() is not None:
                    raise ValueError(f"Published source CRC failed: {coordinate}")
                for entry in archive.namelist():
                    if not entry.endswith((".java", ".kt")):
                        continue
                    with archive.open(entry) as source_file:
                        leading = source_file.read(16384)
                    for match in re.finditer(rb"/\*.*?\*/|(?:^[ \t]*//[^\r\n]*\r?\n)+", leading, re.S | re.M):
                        block = match.group()
                        if any(word in block.lower() for word in (b"copyright", b"spdx-license-identifier", b"licensed under")):
                            blocks.setdefault(block, []).append(entry)
            source_notices.extend(f"\n=== {coordinate}; published source SHA-256 {digest(sources)} ===\n".encode())
            for block, entries in sorted(blocks.items(), key=lambda pair: pair[1][0]):
                source_notices.extend(("\nOriginal files:\n" + "\n".join(entries) + "\n\n").encode())
                source_notices.extend(block + b"\n")
            if not blocks:
                source_notices.extend(b"No copyright/license comment found in the scanned source headers; consult published POM and retained upstream license.\n")
            record["published_source"] = {"sha256": digest(sources), "url": origin["files"][sources.name]["url"], "identity_verified": True,
                                          "crc_verified": True, "notice_blocks": len(blocks)}
        if not poms:
            record["metadata_status"] = "missing_cached_pom"
        else:
            if len({digest(path) for path in poms}) != 1:
                raise ValueError(f"Ambiguous cached Maven metadata: {coordinate}")
            payload = poms[0].read_bytes()
            if b"<!DOCTYPE" in payload or b"<!ENTITY" in payload:
                raise ValueError("Unsupported Maven XML declaration")
            tree = ET.fromstring(payload)
            ns = {"m": "http://maven.apache.org/POM/4.0.0"}
            record["pom_sha256"] = digest(poms[0])
            record["licenses"] = [{"name": license.findtext("m:name", namespaces=ns),
                                   "url": license.findtext("m:url", namespaces=ns)}
                                  for license in tree.findall("m:licenses/m:license", ns)]
            record["metadata_status"] = "declared" if record["licenses"] else "no_license_declaration"
            record["upstream"] = tree.findtext("m:url", namespaces=ns)
        components.append(record)
    if published is not None and set(published_records) != seen:
        raise ValueError("Published source inventory has unselected coordinates")
    if notice_output is not None:
        if published is None:
            raise ValueError("Source notices require verified published archives")
        notice_output.parent.mkdir(parents=True, exist_ok=True)
        notice_output.write_bytes(source_notices)
    return {"schema": 1, "release_ready": False, "resolved_inventory_sha256": digest(inventory),
            "scope": "Resolved release runtime candidates; cached binaries and optionally published POM/source hashes. Annotation classes may not survive APK packaging; plugin-injected runtime and binary/source reproducibility are separate.",
            "components": components,
            "remaining_review": ["Notice/source completeness beyond published archive identity",
                "Copyright/NOTICE completeness, not merely a license label",
                "Chaquopy plugin-injected runtime and embedded native dependencies",
                "Application/runtime/catalog distribution and combined redistribution requirements"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("--cache", type=Path, default=Path.home() / ".gradle/caches/modules-2/files-2.1")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--published", type=Path)
    parser.add_argument("--notice-output", type=Path)
    args = parser.parse_args()
    result = audit(args.inventory, args.cache, args.published, args.notice_output)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    missing = sum(item["metadata_status"] != "declared" for item in result["components"])
    print(f"Verified {len(result['components'])} resolved binaries; {missing} metadata gaps; source and redistribution review remain open")


if __name__ == "__main__":
    main()
