from __future__ import annotations

import argparse
import json
import pathlib
import struct
import zlib


COOKIE_MAGIC = b"MEI\x0c\x0b\x0a\x0b\x0e"
COOKIE_SIZE = 88
TOC_STRUCT = struct.Struct("!IIIIBB")


def safe_path(root: pathlib.Path, name: str) -> pathlib.Path:
    relative = pathlib.PureWindowsPath(name)
    parts = [part for part in relative.parts if part not in ("", ".", "..", "\\", "/")]
    target = root.joinpath(*parts)
    resolved = target.resolve()
    if root.resolve() not in (resolved, *resolved.parents):
        raise ValueError(f"unsafe archive path: {name!r}")
    return target


def extract(executable: pathlib.Path, output: pathlib.Path) -> None:
    blob = executable.read_bytes()
    cookie = blob.find(COOKIE_MAGIC)
    if cookie < 0:
        raise SystemExit("PyInstaller cookie not found")

    package_length, toc_position, toc_length, python_version = struct.unpack_from(
        "!IIII", blob, cookie + len(COOKIE_MAGIC)
    )
    package_end = cookie + COOKIE_SIZE
    package_start = package_end - package_length
    toc_cursor = package_start + toc_position
    toc_end = toc_cursor + toc_length
    output.mkdir(parents=True, exist_ok=True)

    manifest = {
        "source": str(executable),
        "package_start": package_start,
        "package_end": package_end,
        "python_version": python_version,
        "entries": [],
    }

    while toc_cursor < toc_end:
        entry_size, entry_position, compressed_size, raw_size, compressed, type_code = (
            TOC_STRUCT.unpack_from(blob, toc_cursor)
        )
        raw_name = blob[toc_cursor + TOC_STRUCT.size : toc_cursor + entry_size]
        name = raw_name.rstrip(b"\0").decode("utf-8", "replace")
        data = blob[
            package_start + entry_position : package_start + entry_position + compressed_size
        ]
        if compressed:
            data = zlib.decompress(data)
        if len(data) != raw_size:
            raise ValueError(f"size mismatch for {name!r}: {len(data)} != {raw_size}")

        record = {
            "name": name,
            "type": chr(type_code),
            "compressed": bool(compressed),
            "size": raw_size,
        }
        manifest["entries"].append(record)
        if raw_size:
            target = safe_path(output, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        toc_cursor += entry_size

    (output / "_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(f"Extracted {len(manifest['entries'])} entries to {output}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    args = parser.parse_args()
    extract(args.executable, args.output)


if __name__ == "__main__":
    main()
