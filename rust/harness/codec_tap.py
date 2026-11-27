"""Run the offline pipeline and keep every codec call it makes, for the Rust codecs to replay (wave 1).

The dump's chunks (`codec_corpus.py`) cover decoding; what the pipeline itself encodes and decodes,
the staged tables, the textures it reads and the ASTC blocks it writes, only shows up in a run. This
wraps, for one run of ``tools/build_device_patch.py`` (same arguments as `pipeline_case.py run`):

- ``lz4.block.compress`` (every caller, the runtime's in-place staging included),
- ``mobile_graphics.decode_astc``, ``decode_pc`` and ``_encode_astc``,

and writes ``<tap>/calls.jsonl``, one line per distinct call, ``{"fn", "args", "input", "output"}``,
with each input and output kept once under ``<tap>/blobs/<sha256>``. The run's own output is the
pipeline's, unchanged.

    .venv\\Scripts\\python.exe rust\\harness\\codec_tap.py --tap <dir> -- <build_device_patch arguments>
    .venv\\Scripts\\python.exe rust\\harness\\codec_tap.py --png <dir>
    .venv\\Scripts\\python.exe rust\\harness\\codec_tap.py --astc-hdr <dir>
    .venv\\Scripts\\python.exe rust\\harness\\codec_tap.py --astc-solid <dir>

Migration tooling, run by hand: the exe, the APK and ``tools/`` never import it.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import random
import runpy
import struct
import sys
import threading

ROOT = pathlib.Path(__file__).resolve().parents[2]


def keep(blobs: pathlib.Path, data: bytes) -> str:
    name = hashlib.sha256(data).hexdigest()
    path = blobs / name
    if not path.exists():
        path.write_bytes(data)
    return name


def record_pngs(tap: pathlib.Path) -> None:
    from PIL import Image

    blobs = tap / "blobs"
    blobs.mkdir(parents=True, exist_ok=True)
    paths = sorted((ROOT / "resources").rglob("*.png"))
    with (tap / "calls.jsonl").open("w", encoding="utf-8") as calls:
        for path in paths:
            raw = path.read_bytes()
            with Image.open(path) as image:
                record = {
                    "fn": "decode_png",
                    "args": image.size,
                    "input": keep(blobs, raw),
                    "output": keep(blobs, image.convert("RGBA").tobytes()),
                }
            calls.write(json.dumps(record) + "\n")
    print(f"{len(paths)} PNGs -> {tap}")


def record_astc_hdr(tap: pathlib.Path) -> None:
    """Record HDR void-extent colors and nonconstant HDR endpoint blocks."""
    import astc_encoder as astc
    from texture2ddecoder import decode_astc

    blobs = tap / "blobs"
    blobs.mkdir(parents=True, exist_ok=True)
    rng = random.Random(26)
    count = 0
    with (tap / "calls.jsonl").open("w", encoding="utf-8") as calls:
        def record(raw: bytes, side: int, block: int) -> None:
            nonlocal count
            bgra = decode_astc(raw, side, side, block, block)
            rgba = bytearray(bgra)
            rgba[0::4], rgba[2::4] = bgra[2::4], bgra[0::4]
            calls.write(json.dumps({"fn": "decode_astc", "args": [side, side, block, block],
                                    "input": keep(blobs, raw), "output": keep(blobs, bytes(rgba))}) + "\n")
            count += 1

        # A 64x64 image contains 256 void blocks, each with four binary16 values.
        void_extent = bytes.fromhex("fcffffffffffffff")
        for start in range(0, 1 << 16, 1024):
            raw = b"".join(void_extent + struct.pack("<4H", *range(value, value + 4))
                           for value in range(start, start + 1024, 4))
            record(raw, 64, 4)

        for block in (4, 5, 6, 8, 10, 12):
            side = block * 8 - 1  # Include partial blocks on both edges.
            for profile in (astc.ASTCProfile.HDR, astc.ASTCProfile.HDR_RGB_LDR_A):
                codec = astc.ASTCContext(astc.ASTCConfig(profile, block, block, 1, 85), 1)
                for case in range(5):
                    values = []
                    for y in range(side):
                        for x in range(side):
                            values.extend((rng.random() * 4 if case % 2 else x / 15,
                                           rng.random() / 4 if case % 3 else y / 45,
                                           rng.random() if case % 4 else (x + y) / 40,
                                           rng.random() if case % 5 else (x + y) / (2 * side)))
                    image = astc.ASTCImage(astc.ASTCType.F32, side, side, 1,
                                           struct.pack(f"<{len(values)}f", *values))
                    record(codec.compress(image, astc.ASTCSwizzle()), side, block)
    print(f"{count} ASTC HDR calls -> {tap}")


def record_astc_solid(tap: pathlib.Path) -> None:
    """Record every RGBA8 channel value in solid blocks at all six footprints."""
    import astc_encoder as astc

    blobs = tap / "blobs"
    blobs.mkdir(parents=True, exist_ok=True)
    colors = [bytes((value, 255 - value, (value + 64) % 256, value)) for value in range(256)]
    footprints = (4, 5, 6, 8, 10, 12)
    with (tap / "calls.jsonl").open("w", encoding="utf-8") as calls:
        for block in footprints:
            # A 16 by 16 grid of solid blocks, with both last edges clipped.
            side = 16 * block - 1
            raw = b"".join(colors[y // block * 16 + x // block]
                           for y in range(side) for x in range(side))
            config = astc.ASTCConfig(astc.ASTCProfile.LDR, block, block, 1, 85)
            codec = astc.ASTCContext(config, 1)
            image = astc.ASTCImage(astc.ASTCType.U8, side, side, 1, raw)
            encoded = codec.compress(image, astc.ASTCSwizzle())
            record = {"fn": "encode_astc", "args": [side, side, block, block],
                      "input": keep(blobs, raw), "output": keep(blobs, encoded)}
            calls.write(json.dumps(record) + "\n")
    print(f"{len(footprints)} solid ASTC calls -> {tap}")


def main() -> int:
    argv = sys.argv[1:]
    if len(argv) == 2 and argv[0] == "--png":
        record_pngs(pathlib.Path(argv[1]))
        return 0
    if len(argv) == 2 and argv[0] == "--astc-hdr":
        record_astc_hdr(pathlib.Path(argv[1]))
        return 0
    if len(argv) == 2 and argv[0] == "--astc-solid":
        record_astc_solid(pathlib.Path(argv[1]))
        return 0
    if len(argv) < 3 or argv[0] != "--tap" or argv[2] != "--":
        print(__doc__)
        return 2
    tap, rest = pathlib.Path(argv[1]), argv[3:]
    blobs = tap / "blobs"
    blobs.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    lock = threading.Lock()
    calls = (tap / "calls.jsonl").open("w", encoding="utf-8")

    def record(fn: str, args: list, data: bytes, out: bytes) -> None:
        with lock:
            key = json.dumps([fn, args, hashlib.sha256(data).hexdigest()])
            if key in seen:
                return
            seen.add(key)
            calls.write(json.dumps({"fn": fn, "args": args, "input": keep(blobs, bytes(data)),
                                    "output": keep(blobs, bytes(out))}) + "\n")

    sys.path[:0] = [str(ROOT / "tools")]
    sys.path.append(str(ROOT / "resources" / "runtime"))
    import lz4.block
    import mobile_graphics

    compress = lz4.block.compress

    def tapped_compress(data, *args, **kwargs):
        out = compress(data, *args, **kwargs)
        record("lz4.compress", [list(args), sorted(kwargs.items())], data, out)
        return out

    lz4.block.compress = tapped_compress
    decode_astc, decode_pc, encode = mobile_graphics.decode_astc, mobile_graphics.decode_pc, mobile_graphics._encode_astc

    def tapped_decode_astc(raw, width, height, bx, by):
        out = decode_astc(raw, width, height, bx, by)
        record("decode_astc", [width, height, bx, by], raw, out)
        return out

    def tapped_decode_pc(raw, width, height, fmt):
        out = decode_pc(raw, width, height, fmt)
        record("decode_pc", [width, height, fmt], raw, out)
        return out

    def tapped_encode(rgba, width, height, bx, by):
        out = encode(rgba, width, height, bx, by)
        record("encode_astc", [width, height, bx, by], rgba, out)
        return out

    mobile_graphics.decode_astc, mobile_graphics.decode_pc = tapped_decode_astc, tapped_decode_pc
    mobile_graphics._encode_astc = tapped_encode
    sys.argv = [str(ROOT / "tools" / "build_device_patch.py"), *rest]
    try:
        runpy.run_path(sys.argv[0], run_name="__main__")
    except SystemExit as stop:
        if stop.code:
            raise
    finally:
        calls.close()
    print(f"{len(seen)} distinct codec calls -> {tap}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
