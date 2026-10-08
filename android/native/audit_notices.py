"""Inventory actual APK dependency metadata, notices and native payloads without claiming release clearance."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
from email import message_from_bytes
from pathlib import Path, PurePosixPath


def audit(apk: Path) -> dict:
    """Hash packaged notices and identify dependencies whose distribution notice is absent."""
    components, notices, native = [], {}, {}
    with zipfile.ZipFile(apk) as archive:
        engine = json.loads(archive.read("assets/engine/manifest.json"))
        for name, expected in engine["files"].items():
            if not name.startswith("notices/"):
                continue
            payload = archive.read(f"assets/engine/{name}.payload")
            actual = hashlib.sha256(payload).hexdigest()
            if actual != expected:
                raise ValueError(f"Packaged notice hash differs: {name}")
            notices[f"apk:assets/engine/{name}.payload"] = actual

        def scan(source: zipfile.ZipFile, scope: str) -> None:
            files = [name for name in source.namelist() if not name.endswith("/")]
            available = [name for name in files if any(token in PurePosixPath(name).name.upper()
                         for token in ("LICENSE", "NOTICE", "COPYING"))]
            for name in available:
                notices[scope + name] = hashlib.sha256(source.read(name)).hexdigest()
            for name in files:
                if name.endswith(".so"):
                    native[scope + name] = hashlib.sha256(source.read(name)).hexdigest()
                if not name.endswith(".dist-info/METADATA"):
                    continue
                payload = source.read(name)
                metadata = message_from_bytes(payload)
                parent = name.removesuffix("METADATA")
                own_notices = [scope + item for item in available if item.startswith(parent)]
                components.append({"name": metadata.get("Name"), "version": metadata.get("Version"),
                    "metadata": scope + name, "metadata_sha256": hashlib.sha256(payload).hexdigest(),
                    "license_label": (metadata.get("License") or "").strip().splitlines()[:1],
                    "license_classifiers": [item for item in metadata.get_all("Classifier", []) if item.startswith("License ::")],
                    "upstream": metadata.get_all("Project-URL", []) or [metadata.get("Home-page", "")],
                    "distribution_notices": own_notices,
                    "notice_review_required": not bool(own_notices)})
        scan(archive, "apk:")
        for name in archive.namelist():
            if name.endswith(".imy"):
                with zipfile.ZipFile(io.BytesIO(archive.read(name))) as nested:
                    scan(nested, name + "!/")
    with apk.open("rb") as stream:
        apk_digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"schema": 1, "release_ready": False,
        "scope": "Actual packaged Python metadata/notices and native file hashes; not legal clearance or a complete Maven/native-source inventory.",
        "apk_sha256": apk_digest,
        "python_components": sorted(components, key=lambda item: (item["name"] or "", item["metadata"])),
        "notice_files": dict(sorted(notices.items())), "native_files": dict(sorted(native.items())),
        "remaining_review": ["Exact Maven runtime dependency notices/source provenance",
            "Embedded Python native dependencies including OpenSSL, SQLite, libffi, compression and XML libraries",
            "Vendored codec source-header notices and corresponding-source completeness",
            "Application, precompiled translation runtime and catalog distribution permissions/license",
            "Combined application redistribution requirements; component source companion alone is insufficient"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.apk)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Inventoried {len(result['python_components'])} Python distributions, "
          f"{len(result['notice_files'])} notice files and {len(result['native_files'])} native payloads; release review remains open")


if __name__ == "__main__":
    main()
