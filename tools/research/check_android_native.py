"""Inventory ELF load alignment in an Android APK, including Chaquopy's nested archives."""
from __future__ import annotations

import argparse
import io
import json
import struct
import zipfile
from pathlib import Path

MAX_LIBRARY_BYTES = 64 * 1024 * 1024
PAGE_SIZE = 16384


def inspect_elf(data: bytes) -> dict:
    """Read ELF64 program headers without executing or loading the library."""
    if len(data) < 64 or data[:6] != b"\x7fELF\x02\x01":
        raise ValueError("Expected little-endian ELF64")
    machine = struct.unpack_from("<H", data, 18)[0]
    offset = struct.unpack_from("<Q", data, 32)[0]
    size, count = struct.unpack_from("<HH", data, 54)
    if size < 56 or not count or offset + count * size > len(data):
        raise ValueError("Invalid ELF program-header bounds")
    segments = []
    for index in range(count):
        kind, flags, file_offset, address, _, file_size, memory_size, alignment = struct.unpack_from(
            "<IIQQQQQQ", data, offset + index * size)
        if kind != 1:
            continue
        if file_offset + file_size > len(data) or memory_size < file_size:
            raise ValueError("Invalid ELF load segment")
        segments.append({"offset": file_offset, "address": address, "alignment": alignment,
                         "flags": flags, "aligned_16k": alignment >= PAGE_SIZE and
                         file_offset % PAGE_SIZE == address % PAGE_SIZE})
    if not segments:
        raise ValueError("ELF has no load segments")
    return {"machine": machine, "segments": segments,
            "aligned_16k": all(segment["aligned_16k"] for segment in segments)}


def inventory(apk: Path) -> dict:
    libraries = {}
    with zipfile.ZipFile(apk) as outer:
        for item in outer.infolist():
            if item.filename.endswith(".so"):
                if item.file_size > MAX_LIBRARY_BYTES:
                    raise ValueError("Oversized library")
                libraries[item.filename] = inspect_elf(outer.read(item))
            elif item.filename.startswith("assets/chaquopy/") and item.filename.endswith((".imy", ".zip")):
                if item.file_size > MAX_LIBRARY_BYTES:
                    raise ValueError("Oversized nested Python archive")
                payload = io.BytesIO(outer.read(item))
                if not zipfile.is_zipfile(payload):
                    continue
                with zipfile.ZipFile(payload) as nested:
                    for library in nested.infolist():
                        if not library.filename.endswith(".so"):
                            continue
                        if library.file_size > MAX_LIBRARY_BYTES:
                            raise ValueError("Oversized nested library")
                        libraries[f"{item.filename}!/{library.filename}"] = inspect_elf(nested.read(library))
    if not libraries:
        raise ValueError("APK contains no native libraries")
    return {"apk": str(apk.resolve()), "libraries": libraries,
            "all_load_segments_aligned_16k": all(value["aligned_16k"] for value in libraries.values()),
            "limitations": "Static ELF alignment only; ZIP alignment, loader behavior and physical 16 KB device acceptance are separate checks."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = inventory(args.apk)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    failed = [name for name, entry in report["libraries"].items() if not entry["aligned_16k"]]
    print(f"Inspected {len(report['libraries'])} native libraries; {len(failed)} lack 16 KB ELF alignment")
    for name in failed:
        print(name)
    return int(bool(failed))


if __name__ == "__main__":
    raise SystemExit(main())
