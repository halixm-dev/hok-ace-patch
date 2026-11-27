"""Record every BC7 encoder call from cold PC catalog builds on a game copy.

Run with Python 3.12: bc7_case.py --game <copy> --work <fresh-dir>
Each 80-byte record contains 64 input RGBA bytes and one 16-byte Python block.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.append(str(ROOT / "resources" / "runtime"))

import bc7_mode6
import pc_catalog


def capture(game: Path, work: Path, language: str) -> None:
    """Build one catalog and save its reference blocks after a successful run."""
    records = bytearray()
    reference = bc7_mode6.encode_block

    def encode(pixels: list[bc7_mode6.Pixel]) -> bytes:
        block = reference(pixels)
        records.extend(channel for pixel in pixels for channel in pixel)
        records.extend(block)
        return block

    bc7_mode6.encode_block = encode
    try:
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        pc_catalog.build(game, ROOT / "resources", language, work / f"catalog-{language}", version=version)
    finally:
        bc7_mode6.encode_block = reference
    if not records:
        raise SystemExit(f"{language}: no BC7 encoder calls")
    output = work / f"bc7-{language}.bin"
    output.write_bytes(records)
    print(f"{output}: {len(records) // 80} blocks", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", required=True, type=Path)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--languages", nargs="+", choices=("en", "id"), default=("en", "id"))
    args = parser.parse_args()
    args.work.mkdir(parents=True)
    os.environ[bc7_mode6.ENCODER_ENV] = "python"
    for language in args.languages:
        capture(args.game, args.work, language)


if __name__ == "__main__":
    main()
