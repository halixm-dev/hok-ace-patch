"""Estimate additional offline-build files without decoding assets or copying the APK."""
from __future__ import annotations

import re
import struct
import zipfile
from pathlib import Path

PRIME_PREFIX = "assets/bin/Data/Package/builtin/"
MAX_BYTES = 8 * 1024**3


def estimate(packages: Path | str, catalog: Path | str, apk: Path | str, manifest: dict) -> dict:
    """Account for extracted prime, staged copies and replacement work; not a peak guarantee."""
    from wxq_patch.adaptive import load_catalog
    from wxq_patch.qtsvfs import QtsPackage
    from extra_text import SAFE_ASSETS

    packages, catalog, apk = Path(packages), Path(catalog), Path(apk)
    package_bytes = 0
    for name, identity in manifest["files"].items():
        if not name.startswith("packages/"):
            continue
        size = identity["bytes"]
        if type(size) is not int or not 0 <= size <= MAX_BYTES:
            raise ValueError("Invalid build source size")
        package_bytes += size
    if not 0 < package_bytes <= MAX_BYTES:
        raise ValueError("Build source exceeds snapshot budget")

    wanted = load_catalog(catalog).known | SAFE_ASSETS
    source_payload_bytes = 0
    for directory in packages.iterdir():
        if not directory.is_dir() or not directory.name.isdecimal():
            continue
        package = QtsPackage(directory)
        with package.index_path.open("rb") as source:
            for key in wanted & package.entries.keys():
                source.seek(package.entries[key].entry_offset + 44)
                length = source.read(4)
                if len(length) != 4:
                    raise ValueError("Truncated build input descriptor")
                source_payload_bytes += struct.unpack("<I", length)[0]

    prime_bytes = 0
    seen = set()
    with zipfile.ZipFile(apk) as archive:
        for entry in archive.infolist():
            if entry.is_dir() or not entry.filename.startswith(PRIME_PREFIX):
                continue
            name = entry.filename.removeprefix(PRIME_PREFIX)
            if not re.fullmatch(r"[0-9]{1,10}/[0-9]{1,10}(?:_[0-9]{1,3})?\.db", name):
                raise ValueError("Unsupported APK prime path for storage estimate")
            package, filename = name.split("/")
            if int(package) > 0xFFFFFFFF or not (filename.startswith(package + ".") or filename.startswith(package + "_")):
                raise ValueError("APK prime package identity differs")
            if name in seen or entry.file_size < 0 or entry.file_size > MAX_BYTES:
                raise ValueError("Duplicate or oversized APK prime file")
            seen.add(name)
            prime_bytes += entry.file_size
    if not prime_bytes or prime_bytes > MAX_BYTES:
        raise ValueError("APK prime extraction exceeds storage budget")

    catalog_bytes = sum(path.stat().st_size for path in catalog.rglob("*") if path.is_file())
    # Scan, excluded-chunk, full and fit replacement trees can coexist. Use source plus
    # catalog payload as a growth allowance per copy; translation/native peaks still need measurement.
    replacements = 4 * (source_payload_bytes + catalog_bytes)
    # Reserve every downloaded package twice: final output plus a staging attempt's copy.
    components = {"prime_extraction_bytes": prime_bytes, "staged_package_bytes": package_bytes,
                  "staging_attempt_bytes": package_bytes, "replacement_work_bytes": replacements}
    return {"schema": 1, "estimate_only": True, "components": components,
            "additional_bytes": sum(components.values()), "source_payload_bytes": source_payload_bytes,
            "catalog_bytes": catalog_bytes}
