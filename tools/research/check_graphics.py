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
    """A valid synthetic ASTC texture of the shape <english_raw> expects.

    Arbitrary ramp bytes are not ASTC blocks: the native decoder crashes on their invalid endpoint
    parameters on ARM64. These checks measure edits to valid textures, so encode a known opaque
    background instead. Byte comparisons still independently prove that untouched blocks stay intact.
    """
    return mg.encode_astc(bytes((7, 38, 69, 255)) * (width * height), width, height, bx, by)


def ranges_of(graphic: dict) -> list[tuple[int, int]]:
    return [(offset, offset + length) for offset, length in graphic.get("patch_ranges", [])]


def geometry_delta(raw_size: int, width: int, height: int) -> str:
    """How a <raw_size>-byte device texture differs from the catalog's <width>x<height>.

    A block count fixes the geometry only to within a block, so this reports a band: 7622 blocks
    at 8x8 is 74x103 blocks, which is 585..592 by 817..824 pixels -- the catalog's 592x816 grid
    plus one extra block row. Mapping a size back to one exact geometry would be a guess.
    """
    if raw_size % 16:
        return f"{raw_size} B is not a whole number of 16-byte blocks"
    blocks = raw_size // 16
    best: tuple[int, str] | None = None
    for bx, by in mg.ASTC_FOOTPRINTS:
        cat_x, cat_y = math.ceil(width / bx), math.ceil(height / by)
        if cat_x * cat_y == blocks:
            return f"{blocks} blocks at {bx}x{by} is exactly the catalog geometry"
        for nx in range(1, blocks + 1):
            if blocks % nx:
                continue
            ny = blocks // nx
            low_w, high_w = (nx - 1) * bx + 1, nx * bx
            low_h, high_h = (ny - 1) * by + 1, ny * by
            if not (low_w <= width <= high_w or low_h <= height <= high_h):
                continue
            cost = abs(nx - cat_x) + abs(ny - cat_y)
            detail = (f"{blocks} blocks at {bx}x{by} = {low_w}..{high_w} x {low_h}..{high_h} px "
                      f"({nx}x{ny} blocks; catalog geometry is {cat_x}x{cat_y})")
            if best is None or cost < best[0]:
                best = (cost, detail)
    return best[1] if best else f"{blocks} blocks fit no geometry near {width}x{height}"


def skip_reason(graphic: dict, raw_size: int, ported: bool) -> str | None:
    """Why <graphic> could not be ported onto a <raw_size>-byte device texture, or None.

    This explains a refusal that actually happened rather than predicting one. Whether a whole-image
    replacement whose geometry moved can be rescued depends on data -- the label has to align -- so a
    predictor would have to re-run the alignment to be right, and would drift from the code it mirrors.
    """
    if ported:
        return None
    width, height, fmt = mg._dimensions(graphic)
    if not width or not height or fmt not in mg.PC_FORMATS:
        return "no declared metadata"
    layout = mg.astc_layout(raw_size, width, height)
    if layout is None:
        detail = f"geometry: {geometry_delta(raw_size, width, height)}"
        if graphic["payload"].endswith(".assets"):
            return (f"{detail}; the label splice did not land (no label_box, or the two images did "
                    f"not align)")
        return detail
    if graphic["payload"].endswith(".blocks"):
        if fmt == "rgba32" or (fmt == "bc7" and layout == (4, 4)):
            return None
        return f"{fmt} .blocks on a {layout[0]}x{layout[1]} texture"
    return "english_raw returned nothing for a texture it should have replaced"


def label_block_boxes(graphic: dict, raw_size: int) -> list[tuple[int, int, int, int]]:
    """Per candidate block footprint, the block box (x0, y0, x1, y1) a splice could touch.

    The alignment offset is data-dependent, so each box carries ``ALIGNMENT_SEARCH`` blocks of slack.
    Only the label's blocks may differ after a splice -- the whole-image analogue of ``patch_ranges``,
    and the invariant ``check_game`` asserts on a real device texture.
    """
    width, height, _fmt = mg._dimensions(graphic)
    box = graphic.get("label_box")
    rows = mg.label_rows(graphic, height) if box else None
    if rows is None or not width:
        return []
    return [
        (box[0] // bx,
         max(0, rows[0] - mg.ALIGNMENT_SEARCH) // by,
         (box[2] - 1) // bx,
         (rows[1] - 1 + mg.ALIGNMENT_SEARCH) // by)
        for _device_height, bx, by in mg.offset_layouts(raw_size, width, height)
    ]


def changed_blocks_outside(graphic: dict, raw: bytes, new: bytes, width: int,
                           bx: int, by: int) -> int:
    """Changed 16-byte blocks falling outside any box the label could occupy, or -1 if unknowable."""
    boxes = label_block_boxes(graphic, len(raw))
    if not boxes:
        return -1
    blocks_x = math.ceil(width / bx)
    outside = 0
    for index in range(0, min(len(raw), len(new)), 16):
        if raw[index:index + 16] == new[index:index + 16]:
            continue
        position = index // 16
        block_x, block_y = position % blocks_x, position // blocks_x
        if not any(x0 <= block_x <= x1 and y0 <= block_y <= y1 for x0, y0, x1, y1 in boxes):
            outside += 1
    return outside


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
def device_rows(catalog, game: pathlib.Path) -> list[dict]:
    """One row per catalog entry: where the dump carries it and what the port does with it.

    Every entry gets a row, including the ones the dump does not carry at all. Those are the
    point: an aggregate count cannot tell you which entry is missing.

    ``absent`` here means **absent from this dump**, which is the downloaded layer only. It does not
    mean the mobile build lacks the asset: the APK's built-in packages are a second layer the game
    reads, and most of those entries live there. ``prime_probe.py`` counts that layer. Calling an
    entry unreachable needs both.
    """
    from device_extensions import _read_chunks  # noqa: PLC0415

    packages, _ = adaptive.discover(game, catalog)
    present: dict[int, tuple] = {}
    owner: dict[int, str] = {}
    for package in packages:
        slots = package.build_slot_map()
        for file_hash in package.entries:
            if file_hash in catalog.graphics and file_hash in slots:
                present.setdefault(file_hash, (package, slots[file_hash]))
                owner.setdefault(file_hash, package.package_id)

    rows = []
    for file_hash, graphic in catalog.graphics.items():
        width, height, fmt = mg._dimensions(graphic)
        row = {
            "hash": f"{file_hash:016X}",
            "label": graphic.get("label") or "?",
            "kind": graphic["payload"].rsplit(".", 1)[-1],
            "geometry": f"{width}x{height} {fmt}" if width and height else "no metadata",
            "declared": graphic.get("package") or "-",
            "owner": owner.get(file_hash, "-"),
            "present": file_hash in present,
            "raw": None,
            "outcome": "absent",
            "detail": "",
        }
        if row["present"]:
            _package, chunks = present[file_hash]
            row["raw"] = b"".join(mg.oodle_decompress(payload, slot.uncompressed_size)
                                  for slot, payload in _read_chunks(chunks))
            new = mg.english_raw(row["raw"], graphic, CATALOG)
            ported = new is not None and len(new) == len(row["raw"])
            reason = skip_reason(graphic, len(row["raw"]), ported)
            if reason is not None:
                row["outcome"] = "skipped"
                row["detail"] = reason
            elif new == row["raw"]:
                row["outcome"] = "already English"
            elif graphic["payload"].endswith(".blocks"):
                row["outcome"] = "ported"
                row["outside"] = outside_ranges(row["raw"], new, ranges_of(graphic))
            elif mg.astc_layout(len(row["raw"]), *mg._dimensions(graphic)[:2]):
                row["outcome"] = "replaced"
            else:
                # The device revision is a different size, so the whole-image replacement was landed
                # by moving just the label across. Only the label's blocks may have changed.
                row["outcome"] = "spliced"
                width, _catalog_height, _fmt = mg._dimensions(graphic)
                footprint = mg.offset_layouts(len(row["raw"]), width, _catalog_height)
                row["outside"] = (changed_blocks_outside(graphic, row["raw"], new, width, footprint[0][1],
                                                        footprint[0][2])
                                  if footprint else -1)
                row["idempotent"] = mg.english_raw(new, graphic, CATALOG) == new
        rows.append(row)
    rows.sort(key=lambda r: (r["outcome"], r["label"], r["hash"]))
    return rows


def check_game(catalog, game: pathlib.Path, *, table: bool = False) -> None:
    print(f"\n[8] real device bytes from {game}")
    from qts_relocate import install_btree_slot_map  # noqa: PLC0415

    # Without this a re-run over an already-patched dump reads the superseded chunks the relocation
    # left behind, the same way the stock scanner does, so every texture would look unpatched.
    install_btree_slot_map()
    rows = device_rows(catalog, game)

    by_outcome: dict[str, list[dict]] = {}
    for row in rows:
        by_outcome.setdefault(row["outcome"], []).append(row)
    reachable = [r for r in rows if r["present"]]

    check("the dump carries catalog textures", bool(reachable), f"{len(reachable)} of {len(rows)}")

    # The per-entry table. Absent and skipped rows are what a run cannot translate, so they are
    # printed by default; the 300-odd applied rows are available with --table.
    interesting = [r for r in rows if r["outcome"] in ("absent", "skipped")]
    shown = rows if table else interesting
    if shown:
        print(f"  {'hash':<17}{'kind':<8}{'catalog geometry':<18}{'decl':<6}{'owner':<7}"
              f"{'raw':>8}  label")
        for row in shown:
            raw = str(len(row["raw"])) if row["raw"] else "-"
            print(f"  {row['hash']:<17}{row['kind']:<8}{row['geometry']:<18}{row['declared']:<6}"
                  f"{row['owner']:<7}{raw:>8}  {row['label']}")
            if row["detail"]:
                print(f"      {row['outcome']}: {row['detail']}")

    for outcome in ("ported", "replaced", "spliced", "already English", "skipped", "absent"):
        count = len(by_outcome.get(outcome, []))
        if count:
            print(f"  {outcome}: {count}")

    bad_outside = sum(1 for row in by_outcome.get("ported", []) if row.get("outside"))
    check("patch textures change nothing outside patch_ranges", bad_outside == 0,
          f"{len(by_outcome.get('ported', []))} ported, "
          f"{len(by_outcome.get('replaced', []))} replaced wholesale")

    spliced = by_outcome.get("spliced", [])
    stray = [r["hash"] for r in spliced if r.get("outside")]
    check("a label splice touches only the label's blocks", not stray,
          f"{len(spliced)} spliced" + (f", stray bytes in {stray}" if stray else ""))
    not_idempotent = [r["hash"] for r in spliced if not r.get("idempotent")]
    check("a label splice over its own output changes nothing", not not_idempotent,
          f"{len(spliced)} spliced" + (f", {not_idempotent} not idempotent" if not_idempotent else ""))

    accounted = sum(len(by_outcome.get(o, []))
                    for o in ("ported", "replaced", "spliced", "already English", "skipped"))
    check("every texture the dump carries is ported, already English, or a documented skip",
          accounted == len(reachable),
          f"{len(by_outcome.get('ported', []))} ported, {len(by_outcome.get('replaced', []))} "
          f"replaced, {len(spliced)} spliced, "
          f"{len(by_outcome.get('already English', []))} already English, "
          f"{len(by_outcome.get('skipped', []))} skipped; {len(by_outcome.get('absent', []))} of "
          f"{len(rows)} catalog entries are not in this dump (the downloaded layer -- run "
          f"prime_probe.py for the APK's layer before calling any of them unreachable)")


# --------------------------------------------------------------------------------------------
# 9. the label splice, on a synthetic device revision
# --------------------------------------------------------------------------------------------
def synthetic_revision(graphic, extra_rows: int, label_fill: tuple[int, int, int, int]) -> bytes:
    """The catalog's art re-cut taller by <extra_rows>, carrying a different label.

    Builds the situation the splice exists for, without a device dump: same art, moved geometry,
    and a label that is not the catalog's -- so the English pixels are genuinely absent.
    """
    width, height, fmt = mg._dimensions(graphic)
    rgba = bytearray(mg.decode_pc((CATALOG / graphic["payload"]).read_bytes(), width, height, fmt))
    rows, box = mg.label_rows(graphic, height), graphic["label_box"]
    stride = width * 4
    for y in range(rows[0], rows[1]):
        for x in range(box[0], box[2]):
            at = y * stride + x * 4
            rgba[at:at + 4] = bytes(label_fill)
    grown = bytearray(extra_rows * stride) + rgba
    return mg.encode_astc(bytes(grown), width, height + extra_rows, 8, 8)


def check_splice(catalog) -> None:
    print("\n[9] the label splice, on a synthetic device revision")
    graphic = next(g for g in catalog.graphics.values()
                   if g["payload"].endswith(".assets") and g.get("label_box")
                   and mg._dimensions(g)[:2] == (568, 304))
    width, height, fmt = mg._dimensions(graphic)
    extra = 8
    device_raw = synthetic_revision(graphic, extra, (0, 0, 0, 255))
    check("the synthetic revision is a different size from the catalog's",
          mg.astc_layout(len(device_raw), width, height) is None,
          f"catalog 568x304, revision {len(device_raw)} B")

    spliced = mg.english_raw(device_raw, graphic, CATALOG)
    check("the splice lands a texture astc_layout refuses", spliced is not None,
          "None" if spliced is None else f"{len(spliced)} B")
    if spliced is None:
        return
    check("the splice keeps the length", len(spliced) == len(device_raw),
          f"{len(spliced)} vs {len(device_raw)}")

    boxes = label_block_boxes(graphic, len(device_raw))
    footprint = mg.offset_layouts(len(device_raw), width, height)
    outside = (changed_blocks_outside(graphic, device_raw, spliced, width, footprint[0][1], footprint[0][2])
               if footprint else -1)
    check("it touches only the label's blocks", outside == 0, f"{outside} stray blocks in {boxes}")

    # The label the device now carries must be the catalog's, measured the same way the code decides.
    catalog_rgba = mg.decode_pc((CATALOG / graphic["payload"]).read_bytes(), width, height, fmt)
    revision_height = height + extra
    rows, box = mg.label_rows(graphic, height), graphic["label_box"]
    before = mg._label_diff(catalog_rgba, mg.decode_astc(device_raw, width, revision_height, 8, 8),
                            width, revision_height, rows, box, extra)
    after = mg._label_diff(catalog_rgba, mg.decode_astc(spliced, width, revision_height, 8, 8),
                           width, revision_height, rows, box, extra)
    check("the spliced label is the catalog's, and the original was not",
          after is not None and before is not None and after <= mg.LABEL_MATCH_MEAN < before,
          f"before {before:.1f}, after {after:.1f}, threshold {mg.LABEL_MATCH_MEAN}")

    check("a re-run over the splice changes nothing",
          mg.english_raw(spliced, graphic, CATALOG) == spliced)
    check("the splice is deterministic",
          mg.english_raw(device_raw, graphic, CATALOG) == spliced)

    # Negative: unrelated art at a mismatched geometry must be refused, not spliced blindly.
    noise = bytes((index * 37 + 11) % 256 for index in range(len(device_raw)))
    check("unrelated bytes at a mismatched geometry are refused",
          mg.english_raw(noise, graphic, CATALOG) is None)
    # Negative: no label_box means there is nothing to splice, so it stays a skip.
    check("a replacement with no label_box is still skipped",
          mg.english_raw(device_raw, {**graphic, "label_box": None}, CATALOG) is None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--game", type=pathlib.Path,
                        help="the dumped game directory to read real device textures from: the one "
                             "holding WXQ_Data/Package/builtin (not a staged output)")
    parser.add_argument("--skip-slow", action="store_true",
                        help="skip the whole-catalog ASTC replay checks")
    parser.add_argument("--table", action="store_true",
                        help="print every catalog texture's device row, not just the absent/skipped "
                             "ones (needs --game)")
    args = parser.parse_args()

    start = time.perf_counter()
    catalog = adaptive.load_catalog(CATALOG)
    print(f"catalog: {len(catalog.graphics)} graphics entries, "
          f"{len(list(PREVIEWS.glob('*.png')))} previews")

    check_previews(catalog)
    check_missing_metadata(catalog)
    check_codec()
    check_layout(catalog)
    check_splice(catalog)
    if args.skip_slow:
        print("\n[5][6][7] skipped (--skip-slow)")
    else:
        check_block_patch(catalog)
        check_full_replacement(catalog)
        check_unsupported(catalog)
    if args.game:
        check_game(catalog, args.game, table=args.table)

    print(f"\n{time.perf_counter() - start:.1f}s")
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): " + "; ".join(FAILURES))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
