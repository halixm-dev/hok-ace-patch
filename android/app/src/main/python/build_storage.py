"""Estimate additional offline-build files without decoding assets or copying whole packages."""
from __future__ import annotations

import re
import struct
import tempfile
import zipfile
from pathlib import Path

PRIME_PREFIX = "assets/bin/Data/Package/builtin/"
MAX_BYTES = 8 * 1024**3


def _prime_files(apk: Path) -> dict[str, dict[str, int]]:
    """{package id: {file name: bytes}} for every APK prime package file, refusing odd paths."""
    found: dict[str, dict[str, int]] = {}
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
            files = found.setdefault(package, {})
            if filename in files or entry.file_size < 0 or entry.file_size > MAX_BYTES:
                raise ValueError("Duplicate or oversized APK prime file")
            files[filename] = entry.file_size
    if not found or sum(sum(files.values()) for files in found.values()) > MAX_BYTES:
        raise ValueError("APK prime extraction exceeds storage budget")
    return found


def _prime_entries(apk: Path, scratch: Path) -> dict[str, set[int]]:
    """Asset keys of every APK prime package, read from its index alone (as `add_prime_only` does)."""
    from package_rebuild import extract_prime
    from wxq_patch.qtsvfs import QtsPackage

    with tempfile.TemporaryDirectory(prefix="storage-estimate-", dir=scratch) as folder:
        entries = {}
        for package, index_dir in extract_prime(apk, None, Path(folder), index_only=True).items():
            try:
                entries[package] = set(QtsPackage(index_dir).entries)
            except Exception:  # noqa: BLE001 - the build skips an index that will not read, too
                continue
        return entries


def estimate(packages: Path | str, catalog: Path | str, apk: Path | str, manifest: dict,
             scratch: Path | str | None = None, pristine_copy_bytes: int = 0) -> dict:
    """Account for extracted prime, staged copies and replacement work; not a peak guarantee.

    Only a package that holds something this run can translate is staged, and the append reads only the
    APK packages whose catalog content the downloaded copy lacks, so those are what is reserved -- twice
    for a staged package (output plus a staging attempt's copy). <pristine_copy_bytes> is the build
    input's copy of the files a pristine delta rebuilds (0 without one).
    """
    if type(pristine_copy_bytes) is not int or not 0 <= pristine_copy_bytes <= MAX_BYTES:
        raise ValueError("Invalid pristine copy size")
    from wxq_patch.adaptive import load_catalog
    from wxq_patch.qtsvfs import QtsPackage
    from extra_text import SAFE_ASSETS, SCRIPT_ASSETS, UNITY_TEXT_PACKAGES
    from mobile_graphics import DEVICE_REVISIONS

    packages, catalog, apk = Path(packages), Path(catalog), Path(apk)
    scratch = Path(scratch) if scratch is not None else packages.parent
    package_bytes = 0
    sizes: dict[str, int] = {}
    for name, identity in manifest["files"].items():
        if not name.startswith("packages/"):
            continue
        size = identity["bytes"]
        if type(size) is not int or not 0 <= size <= MAX_BYTES:
            raise ValueError("Invalid build source size")
        package_bytes += size
        package = name.removeprefix("packages/").split("/")[0]
        sizes[package] = sizes.get(package, 0) + size
    if not 0 < package_bytes <= MAX_BYTES:
        raise ValueError("Build source exceeds snapshot budget")

    loaded = load_catalog(catalog)
    tables = loaded.known | SAFE_ASSETS | SCRIPT_ASSETS
    # Textures go straight to the staged package; device revisions are their aliases on the phone.
    wanted = tables | set(loaded.graphics) | set(DEVICE_REVISIONS)
    source_payload_bytes = 0
    device: dict[str, set[int]] = {}
    for directory in packages.iterdir():
        if not directory.is_dir() or not directory.name.isdecimal():
            continue
        package = QtsPackage(directory)
        device[directory.name] = set(package.entries)
        with package.index_path.open("rb") as source:
            for key in tables & package.entries.keys():
                source.seek(package.entries[key].entry_offset + 44)
                length = source.read(4)
                if len(length) != 4:
                    raise ValueError("Truncated build input descriptor")
                source_payload_bytes += struct.unpack("<I", length)[0]

    prime_files = _prime_files(apk)
    prime_entries = _prime_entries(apk, scratch)
    index_bytes = sum(files.get(f"{package}.db", 0) for package, files in prime_files.items())
    prime_bytes = 0
    staged = {package for package, keys in device.items() if keys & wanted} | (set(UNITY_TEXT_PACKAGES) & device.keys())
    for package, keys in prime_entries.items():
        if package in device and (keys & wanted) - device[package]:
            staged.add(package)
            prime_bytes += sum(prime_files.get(package, {}).values())
    staged_bytes = sum(sizes.get(package, 0) for package in staged)

    # A non-English catalog reads the English payloads it does not re-draw, so those count too.
    from languages import ENGLISH

    files = {path.relative_to(catalog): path for path in catalog.rglob("*") if path.is_file()}
    english = catalog.parent / ENGLISH.catalog
    if english != catalog and english.is_dir():
        for path in english.rglob("*"):
            if path.is_file():
                files.setdefault(path.relative_to(english), path)
    catalog_bytes = sum(path.stat().st_size for path in files.values())
    # Scan, excluded-chunk, full and fit replacement trees can coexist. Use source plus
    # catalog payload as a growth allowance per copy; translation/native peaks still need measurement.
    replacements = 4 * (source_payload_bytes + catalog_bytes)
    components = {"prime_index_bytes": index_bytes, "prime_extraction_bytes": prime_bytes,
                  "staged_package_bytes": staged_bytes, "staging_attempt_bytes": staged_bytes,
                  "replacement_work_bytes": replacements, "pristine_copy_bytes": pristine_copy_bytes}
    return {"schema": 2, "estimate_only": True, "components": components,
            "additional_bytes": sum(components.values()), "source_payload_bytes": source_payload_bytes,
            "catalog_bytes": catalog_bytes, "package_bytes": package_bytes,
            "staged_packages": sorted(staged, key=int)}
