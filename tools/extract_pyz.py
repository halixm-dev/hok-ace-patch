from __future__ import annotations

import argparse
import importlib.util
import json
import marshal
import pathlib
import struct
import zlib


def safe_path(root: pathlib.Path, module: str, is_package: bool) -> pathlib.Path:
    parts = module.split(".")
    target = root.joinpath(*parts)
    if is_package:
        target = target / "__init__.pyc"
    else:
        target = target.with_suffix(".pyc")
    resolved = target.resolve()
    if root.resolve() not in resolved.parents:
        raise ValueError(f"unsafe module path: {module!r}")
    return target


def extract(pyz_path: pathlib.Path, output: pathlib.Path) -> None:
    blob = pyz_path.read_bytes()
    if blob[:4] != b"PYZ\0":
        raise SystemExit("not a PYZ archive")
    source_magic = blob[4:8]
    if source_magic != importlib.util.MAGIC_NUMBER:
        raise SystemExit(
            f"Python bytecode mismatch: archive={source_magic.hex()} "
            f"runtime={importlib.util.MAGIC_NUMBER.hex()}"
        )
    toc_position = struct.unpack_from("!I", blob, 8)[0]
    toc = marshal.loads(blob[toc_position:])
    output.mkdir(parents=True, exist_ok=True)
    manifest = []
    entries = toc.items() if isinstance(toc, dict) else toc
    for module, record in entries:
        type_code, position, compressed_size = record
        is_package = type_code == 1
        if type_code not in (0, 1):
            continue
        code = marshal.loads(zlib.decompress(blob[position : position + compressed_size]))
        target = safe_path(output, module, is_package)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Timestamp/hash metadata is irrelevant for inspection. A zeroed PEP 552
        # header produces a valid Python 3.12 pyc for marshal/disassembly tools.
        target.write_bytes(source_magic + b"\0" * 12 + marshal.dumps(code))
        manifest.append(
            {
                "module": module,
                "package": is_package,
                "path": str(target.relative_to(output)),
            }
        )
    (output / "_manifest.json").write_text(json.dumps(manifest, indent=2), "utf-8")
    print(f"Extracted {len(manifest)} modules to {output}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pyz", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    args = parser.parse_args()
    extract(args.pyz, args.output)


if __name__ == "__main__":
    main()
