"""Build a language catalog's texture payloads from its review renders.

A non-English catalog ships only the images it re-draws, named the way the English catalog names them:
the render is `previews/<HASH>.png` and the payload the texture pass applies is `<HASH>.blocks` /
`<HASH>.assets`. Every other edit falls back to the English payload (`languages.payload_path`).

`LABELS` says which sprite of which catalog texture each render replaces. The payload is the English
one with that sprite's pixels swapped for the render's, in the payload's own format and patch ranges,
so the catalog's metadata (`format`, `patch_ranges`, geometry) applies to it unchanged:

* RGBA32 `.blocks`: the pixels are written straight into the bottom-up buffer;
* BC7 `.blocks`: only the 4x4 blocks the sprite touches are re-encoded (BC7 mode 6), every other block
  keeps the English bytes.

Run by hand from the project root after changing a render; `--check` rebuilds in memory and fails if
the shipped payloads differ, and reports how closely the BC7 blocks reproduce the render:

    .venv\\Scripts\\python.exe tools\\research\\make_language_payloads.py [--check]
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import mobile_graphics as mg  # noqa: E402

RESOURCES = ROOT / "resources"
ENGLISH = RESOURCES / "catalog"

# catalog directory -> (target texture, sprite label in its `regions`, render under previews/)
LABELS: dict[str, list[tuple[str, str, str]]] = {
    # The lobby's START GAME label exists twice in package 19: as its own 372x102 texture beside the
    # other button-state labels, and as a sprite of an atlas. The two are the same pixels (mean
    # difference 0.83 at offset 0,0), so one render serves both.
    "catalog_id": [
        ("863114A42F12EF76", "start_game", "863114A42F12EF76"),
        ("C9F49510F2F67402", "start_game", "863114A42F12EF76"),
    ],
}

_WEIGHTS = (0, 4, 9, 13, 17, 21, 26, 30, 34, 38, 43, 47, 51, 55, 60, 64)


# ------------------------------------------------------------------------------------------------
# BC7 mode 6: one subset, RGBA endpoints at 7 bits plus a p-bit each, 4-bit indices
# ------------------------------------------------------------------------------------------------

def _quantize(colour: list[float]) -> tuple[list[int], int]:
    """7-bit endpoint and p-bit closest to an 8-bit RGBA colour."""
    best = None
    for pbit in (0, 1):
        q = [min(127, max(0, round((c - pbit) / 2))) for c in colour]
        error = sum(((v << 1 | pbit) - c) ** 2 for v, c in zip(q, colour))
        if best is None or error < best[0]:
            best = (error, q, pbit)
    return best[1], best[2]


def _palette(q0, p0, q1, p1) -> list[tuple[int, ...]]:
    a = [v << 1 | p0 for v in q0]
    b = [v << 1 | p1 for v in q1]
    return [tuple(((64 - w) * x + w * y + 32) >> 6 for x, y in zip(a, b)) for w in _WEIGHTS]


def _indices(pixels, palette) -> tuple[list[int], int]:
    chosen, total = [], 0
    for pixel in pixels:
        error, index = min((sum((c - p) ** 2 for c, p in zip(colour, pixel)), i)
                           for i, colour in enumerate(palette))
        chosen.append(index)
        total += error
    return chosen, total


def _fit(pixels, indices) -> tuple[list[float], list[float]] | None:
    """Least-squares endpoints for fixed indices, or None when the indices do not span a line."""
    t = [_WEIGHTS[i] / 64 for i in indices]
    a = sum((1 - x) ** 2 for x in t)
    b = sum((1 - x) * x for x in t)
    c = sum(x * x for x in t)
    det = a * c - b * b
    if abs(det) < 1e-9:
        return None
    e0, e1 = [], []
    for ch in range(4):
        r0 = sum((1 - x) * p[ch] for x, p in zip(t, pixels))
        r1 = sum(x * p[ch] for x, p in zip(t, pixels))
        e0.append(min(255.0, max(0.0, (c * r0 - b * r1) / det)))
        e1.append(min(255.0, max(0.0, (a * r1 - b * r0) / det)))
    return e0, e1


def _principal(pixels) -> tuple[list[float], list[float]]:
    """Endpoints spanning the pixels along their principal axis."""
    n = len(pixels)
    mean = [sum(p[ch] for p in pixels) / n for ch in range(4)]
    centred = [[p[ch] - mean[ch] for ch in range(4)] for p in pixels]
    cov = [[sum(v[i] * v[j] for v in centred) for j in range(4)] for i in range(4)]
    axis = [1.0, 1.0, 1.0, 1.0]
    for _ in range(12):
        nxt = [sum(cov[i][j] * axis[j] for j in range(4)) for i in range(4)]
        norm = max(abs(v) for v in nxt)
        if norm < 1e-9:
            return mean, mean
        axis = [v / norm for v in nxt]
    proj = [sum(v[ch] * axis[ch] for ch in range(4)) for v in centred]
    scale = sum(v * v for v in axis)
    lo, hi = min(proj) / scale, max(proj) / scale
    clamp = lambda v: min(255.0, max(0.0, v))  # noqa: E731
    return ([clamp(mean[ch] + lo * axis[ch]) for ch in range(4)],
            [clamp(mean[ch] + hi * axis[ch]) for ch in range(4)])


def encode_bc7_block(pixels: list[tuple[int, int, int, int]]) -> bytes:
    """One 16-byte BC7 mode-6 block for 16 RGBA pixels in row-major order."""
    starts = [_principal(pixels),
              ([min(p[ch] for p in pixels) for ch in range(4)],
               [max(p[ch] for p in pixels) for ch in range(4)])]
    best = None
    for e0, e1 in starts:
        for _ in range(4):
            (q0, p0), (q1, p1) = _quantize(e0), _quantize(e1)
            indices, error = _indices(pixels, _palette(q0, p0, q1, p1))
            if best is None or error < best[0]:
                best = (error, q0, p0, q1, p1, indices)
            fitted = _fit(pixels, indices)
            if fitted is None:
                break
            e0, e1 = fitted
    _error, q0, p0, q1, p1, indices = best
    if indices[0] >= 8:  # the anchor index is stored in 3 bits, so its high bit must be clear
        q0, p0, q1, p1 = q1, p1, q0, p0
        indices = [15 - i for i in indices]
    value = position = 0

    def put(bits: int, width: int) -> None:
        nonlocal value, position
        value |= bits << position
        position += width

    put(1 << 6, 7)  # mode 6: six zero bits, then a one
    for ch in range(4):
        put(q0[ch], 7)
        put(q1[ch], 7)
    put(p0, 1)
    put(p1, 1)
    put(indices[0], 3)
    for index in indices[1:]:
        put(index, 4)
    assert position == 128
    return value.to_bytes(16, "little")


# ------------------------------------------------------------------------------------------------
# payloads
# ------------------------------------------------------------------------------------------------

def _graphics(catalog: Path) -> dict[str, dict]:
    with gzip.open(catalog / "catalog.json.gz", "rt", encoding="utf-8") as handle:
        return {graphic["hash"]: graphic for graphic in json.load(handle)["graphics"]}


def _sprite(graphic: dict, label: str, render: Image.Image) -> dict[tuple[int, int], tuple]:
    """Buffer (x, y) -> RGBA for every pixel of the render, placed at the sprite's box.

    Boxes are in display order (top-down); the payload buffer is bottom-up, so rows are mirrored.
    """
    box = next(region["box"] for region in graphic["regions"] if region["label"] == label)
    width, height = box[2] - box[0], box[3] - box[1]
    if render.size != (width, height):
        raise ValueError(f"{graphic['hash']} {label}: render is {render.size}, sprite is {width}x{height}")
    pixels = render.convert("RGBA").load()
    return {(box[0] + x, graphic["height"] - 1 - (box[1] + y)): pixels[x, y]
            for y in range(height) for x in range(width)}


def _rgba32_payload(graphic: dict, english: bytes, pixels: dict) -> bytes:
    width = graphic["width"]
    image = bytearray(width * graphic["height"] * 4)
    covered = set()
    cursor = 0
    for offset, length in graphic["patch_ranges"]:
        image[offset:offset + length] = english[cursor:cursor + length]
        covered.update(range(offset // 4, (offset + length) // 4))
        cursor += length
    for (x, y), colour in pixels.items():
        at = y * width + x
        if at not in covered:
            raise ValueError(f"{graphic['hash']}: sprite pixel {x},{y} lies outside the patch ranges")
        image[at * 4:at * 4 + 4] = bytes(colour)
    return b"".join(bytes(image[offset:offset + length]) for offset, length in graphic["patch_ranges"])


def _bc7_payload(graphic: dict, english: bytes, pixels: dict) -> bytes:
    blocks_x = graphic["width"] // 4
    where: dict[tuple[int, int], int] = {}  # block (x, y) -> byte offset in the payload
    cursor = 0
    for offset, length in graphic["patch_ranges"]:
        for at in range(offset, offset + length, 16):
            where[((at // 16) % blocks_x, (at // 16) // blocks_x)] = cursor + at - offset
        cursor += length
    out = bytearray(english)
    for block in sorted({(x // 4, y // 4) for x, y in pixels}):
        if block not in where:
            raise ValueError(f"{graphic['hash']}: sprite block {block} lies outside the patch ranges")
        at = where[block]
        rgba = mg.decode_pc(english[at:at + 16], 4, 4, "bc7")
        texels = [tuple(rgba[i * 4:i * 4 + 4]) for i in range(16)]
        for i in range(16):
            colour = pixels.get((block[0] * 4 + i % 4, block[1] * 4 + i // 4))
            if colour is not None:
                texels[i] = colour
        out[at:at + 16] = encode_bc7_block(texels)
    return bytes(out)


def _bc7_error(graphic: dict, payload: bytes, pixels: dict) -> float:
    """Mean absolute per-channel difference between the encoded sprite and the render."""
    blocks_x = graphic["width"] // 4
    where, cursor = {}, 0
    for offset, length in graphic["patch_ranges"]:
        for at in range(offset, offset + length, 16):
            where[((at // 16) % blocks_x, (at // 16) // blocks_x)] = cursor + at - offset
        cursor += length
    total = 0
    decoded: dict[tuple[int, int], bytes] = {}
    for (x, y), colour in pixels.items():
        block = (x // 4, y // 4)
        if block not in decoded:
            decoded[block] = mg.decode_pc(payload[where[block]:where[block] + 16], 4, 4, "bc7")
        i = (y % 4) * 4 + x % 4
        total += sum(abs(a - b) for a, b in zip(decoded[block][i * 4:i * 4 + 4], colour))
    return total / (len(pixels) * 4)


def build(catalog_name: str) -> dict[str, tuple[bytes, float | None]]:
    """Payload file name -> (bytes, BC7 error or None) for every label of <catalog_name>."""
    catalog = RESOURCES / catalog_name
    graphics = _graphics(catalog)
    built: dict[str, tuple[bytes, float | None]] = {}
    for target, label, render in LABELS[catalog_name]:
        graphic = graphics[target]
        name = graphic["payload"]
        english = (ENGLISH / name).read_bytes()
        pixels = _sprite(graphic, label, Image.open(catalog / "previews" / f"{render}.png"))
        if not name.endswith(".blocks"):
            raise ValueError(f"{target}: only .blocks payloads are rebuilt from a sprite")
        if graphic["format"] == "rgba32":
            built[name] = (_rgba32_payload(graphic, english, pixels), None)
        elif graphic["format"] == "bc7":
            payload = _bc7_payload(graphic, english, pixels)
            built[name] = (payload, _bc7_error(graphic, payload, pixels))
        else:
            raise ValueError(f"{target}: unsupported format {graphic['format']}")
    return built


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if a shipped payload differs")
    args = parser.parse_args()
    failed = False
    for catalog_name in LABELS:
        for name, (payload, error) in build(catalog_name).items():
            path = RESOURCES / catalog_name / name
            quality = "" if error is None else f", BC7 mean error {error:.2f}/255"
            if args.check:
                same = path.exists() and path.read_bytes() == payload
                failed |= not same
                print(f"{'ok  ' if same else 'DIFF'} {catalog_name}/{name} ({len(payload)} bytes{quality})")
            else:
                path.write_bytes(payload)
                print(f"wrote {catalog_name}/{name} ({len(payload)} bytes{quality})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
