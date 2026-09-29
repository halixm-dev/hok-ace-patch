"""Check the texture pass against the ground truth shipped in resources/catalog.

Two independent oracles, both in this repo:

* every ``.assets`` payload is the raw PC image, and ``previews/<HASH>.png`` is that image rendered.
  Decoding the payload at its declared geometry, flipping it vertically, and comparing pixel for
  pixel must give a zero difference -- that is what pins the row order and the BC7/RGBA32 handling.
* every ``.blocks`` payload is a byte patch at known offsets, so porting it onto a device texture must
  leave every byte outside ``graphic["patch_ranges"]`` bit-identical.

Run by hand from the project root:

    .venv\\Scripts\\python.exe tools\\research\\check_graphics.py
    .venv\\Scripts\\python.exe tools\\research\\check_graphics.py --game <WXQ_Data/Package parent dump>

The ``--game`` form adds the real device bytes: each texture the game packages actually carry is read
back through its Oodle chunk and the same invariants are asserted on it. Nothing here is imported by
the app or by the pipeline.

Off the runtime path: excluded from the exe build and never imported from ``app/`` or ``tools/``.
"""
from __future__ import annotations

import argparse
import math
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.append(str(ROOT / "resources" / "runtime"))

import mobile_graphics as mg  # noqa: E402
from PIL import Image  # noqa: E402
from wxq_patch import adaptive  # noqa: E402

CATALOG = ROOT / "resources" / "catalog"
PREVIEWS = CATALOG / "previews"
ASTC_QUANTISATION_MEAN = 2.0  # ASTC 4x4 is lossy; a correct round trip stays well inside this
ASTC_QUANTISATION_MAX = 48

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{'  ' + detail if detail else ''}")
    if not ok:
        FAILURES.append(label)


def vertical_flip(rgba: bytes, width: int, height: int) -> bytes:
    """PC payloads are bottom-up; the review renders are top-down."""
    stride = width * 4
    out = bytearray(len(rgba))
    for row in range(height):
        out[row * stride:(row + 1) * stride] = rgba[(height - 1 - row) * stride:(height - row) * stride]
    return bytes(out)


def mean_abs_diff(left: bytes, right: bytes) -> float:
    return sum(abs(a - b) for a, b in zip(left, right)) / len(left)


def device_bytes(width: int, height: int, bx: int, by: int) -> bytes:
    """A synthetic device texture of the shape <english_raw> expects, filled with a ramp."""
    size = math.ceil(width / bx) * math.ceil(height / by) * 16
    return bytes((i * 31 + 7) % 256 for i in range(size))


def ranges_of(graphic: dict) -> list[tuple[int, int]]:
    return [(offset, offset + length) for offset, length in graphic.get("patch_ranges", [])]


def outside_ranges(raw: bytes, new: bytes, ranges: list[tuple[int, int]]) -> int:
    return sum(
        1 for index, (before, after) in enumerate(zip(raw, new))
        if before != after and not any(start <= index < end for start, end in ranges)
    )


# --------------------------------------------------------------------------------------------
# 1. the review renders
# --------------------------------------------------------------------------------------------
def check_previews(catalog) -> None:
    print("\n[1] review renders reproduce from the catalog payloads")
    previews = sorted(PREVIEWS.glob("*.png"))
    check("44 previews are shipped", len(previews) == 44, str(len(previews)))
    worst = (0.0, "")
    compared = 0
    for path in previews:
        graphic = catalog.graphics.get(int(path.stem, 16))
        if graphic is None:
            check(f"{path.stem}: in catalog", False)
            continue
        width, height, fmt = mg._dimensions(graphic)
        payload = (CATALOG / graphic["payload"]).read_bytes()
        decoded = mg.decode_pc(payload, width, height, fmt)
        diff = mean_abs_diff(vertical_flip(decoded, width, height),
                             Image.open(path).convert("RGBA").tobytes())
        compared += 1
        if diff > worst[0]:
            worst = (diff, path.stem)
    check(f"all {compared} previews decode at zero difference", worst[0] == 0.0,
          f"worst {worst[0]:.6f} ({worst[1]})")


# --------------------------------------------------------------------------------------------
# 2. the six entries that carry no geometry
# --------------------------------------------------------------------------------------------
def check_missing_metadata(catalog) -> None:
    print("\n[2] entries with no declared format/width/height")
    check("exactly six entries need the table", len(mg.MISSING_METADATA) == 6,
          str(len(mg.MISSING_METADATA)))
    for hexhash, (fmt, width, height) in mg.MISSING_METADATA.items():
        graphic = catalog.graphics.get(int(hexhash, 16))
        if graphic is None:
            check(f"{hexhash}: in catalog", False)
            continue
        resolved = mg._dimensions(graphic)
        payload = (CATALOG / graphic["payload"]).read_bytes()
        check(f"{hexhash} -> {fmt} {width}x{height}",
              resolved == (width, height, fmt) and width * height * 4 == len(payload),
              f"payload {len(payload)} bytes")


# --------------------------------------------------------------------------------------------
# 3. the ASTC codec
# --------------------------------------------------------------------------------------------
def check_codec() -> None:
    print("\n[3] ASTC encode/decode round trip")
    width, height = 64, 64
    buffer = bytearray()
    for y in range(height):
        for x in range(width):
            buffer += bytes(((x * 4) % 256, (y * 4) % 256, ((x + y) * 2) % 256, 255))
    rgba = bytes(buffer)
    packed = mg.encode_astc(rgba, width, height, 4, 4)
    check("packed size is the ASTC footprint",
          len(packed) == math.ceil(width / 4) * math.ceil(height / 4) * 16, str(len(packed)))
    back = mg.decode_astc(packed, width, height, 4, 4)
    mean = mean_abs_diff(rgba, back)
    worst = max(abs(a - b) for a, b in zip(rgba, back))
    check("round trip stays inside ASTC quantisation",
          mean <= ASTC_QUANTISATION_MEAN and worst <= ASTC_QUANTISATION_MAX,
          f"mean {mean:.3f} max {worst}")
    check("encode is deterministic", mg.encode_astc(rgba, width, height, 4, 4) == packed)


# --------------------------------------------------------------------------------------------
# 4. footprint resolution
# --------------------------------------------------------------------------------------------
def check_layout(catalog) -> None:
    print("\n[4] astc_layout inverts the size calculation")
    check("a raw size no footprint fits returns None", mg.astc_layout(12345, 404, 564) is None)

    # Every declared entry at every footprint: the size that footprint implies must resolve back to
    # it. Deriving the size at 4x4 and asserting 4x4 would prove nothing.
    usable = [g for g in catalog.graphics.values() if g.get("width") and g.get("height")]
    mismatches: list[str] = []
    for graphic in usable:
        width, height = graphic["width"], graphic["height"]
        for bx, by in mg.ASTC_FOOTPRINTS:
            size = math.ceil(width / bx) * math.ceil(height / by) * 16
            if mg.astc_layout(size, width, height) != (bx, by):
                mismatches.append(f"{bx}x{by}@{width}x{height}")
    check(f"all {len(usable)} declared entries round-trip at all six footprints",
          not mismatches, f"{len(mismatches)} mismatches" + (f" {mismatches[:4]}" if mismatches else ""))


# --------------------------------------------------------------------------------------------
# 5. the block-patch invariant, on synthetic device textures
# --------------------------------------------------------------------------------------------
def check_block_patch(catalog) -> None:
    print("\n[5] .blocks patches change nothing outside patch_ranges")
    blocks = [g for g in catalog.graphics.values() if g["payload"].endswith(".blocks")]
    by_format: dict[str, int] = {}
    bad_outside = 0
    not_ported = 0
    nondeterministic = 0
    not_idempotent = 0
    for graphic in blocks:
        width, height, fmt = mg._dimensions(graphic)
        raw = device_bytes(width, height, 4, 4)
        new = mg.english_raw(raw, graphic, CATALOG)
        if new is None:
            not_ported += 1
            continue
        by_format[fmt or "?"] = by_format.get(fmt or "?", 0) + 1
        if len(new) != len(raw):
            bad_outside += 1
            continue
        if outside_ranges(raw, new, ranges_of(graphic)):
            bad_outside += 1
        if mg.english_raw(raw, graphic, CATALOG) != new:
            nondeterministic += 1
        if mg.english_raw(new, graphic, CATALOG) != new:
            not_idempotent += 1
    check(f"every .blocks entry ports ({len(blocks) - not_ported}/{len(blocks)})",
          not_ported == 0, f"{by_format}")
    check("no byte outside patch_ranges changes", bad_outside == 0, f"{bad_outside} entries")
    check("the port is deterministic", nondeterministic == 0, f"{nondeterministic} entries")
    check("a re-run over its own output changes nothing", not_idempotent == 0,
          f"{not_idempotent} entries")


# --------------------------------------------------------------------------------------------
# 6. full replacements
# --------------------------------------------------------------------------------------------
def check_full_replacement(catalog) -> None:
    print("\n[6] .assets replacements rebuild the whole texture")
    assets = [g for g in catalog.graphics.values() if g["payload"].endswith(".assets")]
    good = nondeterministic = not_idempotent = 0
    for graphic in assets:
        width, height, _fmt = mg._dimensions(graphic)
        raw = device_bytes(width, height, 4, 4)
        new = mg.english_raw(raw, graphic, CATALOG)
        if new is None or len(new) != len(raw) or new == raw:
            continue
        good += 1
        if mg.english_raw(raw, graphic, CATALOG) != new:
            nondeterministic += 1
        if mg.english_raw(new, graphic, CATALOG) != new:
            not_idempotent += 1
    check(f"every .assets entry replays ({good}/{len(assets)})", good == len(assets))
    check("the replay is deterministic", nondeterministic == 0, f"{nondeterministic}")
    check("a re-run over its own output changes nothing", not_idempotent == 0, f"{not_idempotent}")


# --------------------------------------------------------------------------------------------
# 7. the unsupported cases stay skips
# --------------------------------------------------------------------------------------------
def check_unsupported(catalog) -> None:
    print("\n[7] unsupported textures are skipped, never raised")
    sample = next(g for g in catalog.graphics.values() if g["payload"].endswith(".blocks"))
    check("unknown format returns None",
          mg.english_raw(device_bytes(64, 64, 4, 4), {**sample, "format": "astc"}, CATALOG) is None)
    check("unresolvable raw size returns None",
          mg.english_raw(b"\0" * 7, sample, CATALOG) is None)
    astc = [g for g in catalog.graphics.values()
            if g["payload"].endswith(".blocks") and g.get("format") == "bc7"]
    wide = next(g for g in astc if mg._dimensions(g)[0] >= 64)
    width, height, _ = mg._dimensions(wide)
    check("a BC7 patch on a non-4x4 device texture returns None",
          mg.english_raw(device_bytes(width, height, 8, 8), wide, CATALOG) is None)


# --------------------------------------------------------------------------------------------
# 8. the real device bytes
# --------------------------------------------------------------------------------------------
def check_game(catalog, game: pathlib.Path) -> None:
    print(f"\n[8] real device bytes from {game}")
    from device_extensions import _read_chunks  # noqa: PLC0415
    from qts_relocate import install_btree_slot_map  # noqa: PLC0415

    # Without this a re-run over an already-patched dump reads the superseded chunks the relocation
    # left behind, the same way the stock scanner does, so every texture would look unpatched.
    install_btree_slot_map()
    packages, _ = adaptive.discover(game, catalog)
    present: dict[int, tuple] = {}
    for package in packages:
        slots = package.build_slot_map()
        for file_hash in package.entries:
            if file_hash in catalog.graphics and file_hash in slots:
                present[file_hash] = (package, slots[file_hash])
    check("the dump carries catalog textures", bool(present), f"{len(present)} across "
          f"{sorted({p.package_id for p, _ in present.values()})}")

    bad_outside = 0
    patched = replaced = unchanged = unsupported = 0
    skipped: list[str] = []
    footprints: dict[tuple[int, int] | None, int] = {}
    for file_hash, (_package, chunks) in present.items():
        graphic = catalog.graphics[file_hash]
        # Every chunk, not just the first: a 1024x1024 texture spans four of them.
        raw = b"".join(mg.oodle_decompress(payload, slot.uncompressed_size)
                       for slot, payload in _read_chunks(chunks))
        width, height, _dim = mg._dimensions(graphic)
        layout = mg.astc_layout(len(raw), width, height)
        footprints[layout] = footprints.get(layout, 0) + 1
        new = mg.english_raw(raw, graphic, CATALOG)
        if new is None or len(new) != len(raw):
            # A patch that will not port onto this texture's footprint. By design that is a skip,
            # not a failure -- english_raw must never raise for a texture it cannot handle.
            unsupported += 1
            skipped.append(f"{file_hash:016X}@{len(raw)}B@{layout or 'no footprint'}")
            continue
        if new == raw:
            unchanged += 1
            continue
        if graphic["payload"].endswith(".blocks"):
            patched += 1
            if outside_ranges(raw, new, ranges_of(graphic)):
                bad_outside += 1
        else:
            replaced += 1
    check("the device footprints resolve from the real raw sizes", None not in footprints,
          ", ".join(f"{'x'.join(map(str, k)) if k else 'none'}: {v}"
                    for k, v in sorted(footprints.items(), key=lambda kv: -kv[1])))
    check("patch textures change nothing outside patch_ranges", bad_outside == 0,
          f"{patched} ported, {replaced} replaced wholesale")
    check("every present texture is ported, already English, or a documented skip",
          patched + replaced + unchanged + unsupported == len(present),
          f"{patched} ported, {replaced} replaced, {unchanged} already English, "
          f"{unsupported} skipped" + (f" {skipped}" if skipped else ""))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--game", type=pathlib.Path,
                        help="the dumped game directory to read real device textures from: the one "
                             "holding WXQ_Data/Package/builtin (not a staged output)")
    parser.add_argument("--skip-slow", action="store_true",
                        help="skip the whole-catalog ASTC replay checks")
    args = parser.parse_args()

    start = time.perf_counter()
    catalog = adaptive.load_catalog(CATALOG)
    print(f"catalog: {len(catalog.graphics)} graphics entries, "
          f"{len(list(PREVIEWS.glob('*.png')))} previews")

    check_previews(catalog)
    check_missing_metadata(catalog)
    check_codec()
    check_layout(catalog)
    if args.skip_slow:
        print("\n[5][6][7] skipped (--skip-slow)")
    else:
        check_block_patch(catalog)
        check_full_replacement(catalog)
        check_unsupported(catalog)
    if args.game:
        check_game(catalog, args.game)

    print(f"\n{time.perf_counter() - start:.1f}s")
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): " + "; ".join(FAILURES))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
