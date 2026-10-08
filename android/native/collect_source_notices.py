"""Retain leading copyright/license comments from the exact pinned codec source archives."""
from __future__ import annotations

import argparse
import hashlib
import re
import tarfile
from pathlib import Path

from build_wheels import SOURCES


def collect(sources: Path, output: Path) -> None:
    """Preserve original comment bytes; this inventory still needs a source/license review."""
    archives = {}
    for path in sources.glob("*.tar.gz"):
        with path.open("rb") as stream:
            archives[hashlib.file_digest(stream, "sha256").hexdigest()] = path
    result = bytearray(b"Pinned codec source header notices\n"
        b"Leading comment inventory; includes source which may be unused. Not a complete redistribution review.\n")
    for component, (version, digest) in SOURCES.items():
        if digest not in archives:
            raise ValueError(f"Missing pinned source: {component} {version}")
        blocks: dict[bytes, list[str]] = {}
        with tarfile.open(archives[digest]) as archive:
            for member in archive:
                if not member.isfile() or Path(member.name).suffix.lower() not in (".c", ".h", ".cpp", ".hpp"):
                    continue
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError("Source archive member is unreadable")
                with source:
                    leading = source.read(16384)
                for match in re.finditer(rb"/\*.*?\*/|(?:^[ \t]*//[^\r\n]*\r?\n)+", leading, re.S | re.M):
                    block = match.group()
                    if any(word in block.lower() for word in (b"copyright", b"spdx-license-identifier", b"licensed under", b"permission is hereby")):
                        blocks.setdefault(block, []).append(member.name)
        result.extend(f"\n=== {component} {version}; source SHA-256 {digest} ===\n".encode())
        for block, names in sorted(blocks.items(), key=lambda item: item[1][0]):
            result.extend(("\nOriginal source files:\n" + "\n".join(names) + "\n\n").encode())
            result.extend(block)
            result.extend(b"\n")
        if not blocks:
            raise ValueError(f"No source header notices found: {component}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(result)
    print(f"Retained {len(result)} bytes of original source notice blocks in {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    collect(args.sources, args.output)


if __name__ == "__main__":
    main()
