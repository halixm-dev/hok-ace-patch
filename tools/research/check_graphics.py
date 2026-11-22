"""Check the texture pass against the ground truth shipped in resources/catalog.

Two independent oracles, both in this repo:

* every ``.assets`` payload is the raw PC image, and ``previews/<HASH>.png`` is that image rendered.
  Decoding the payload at its declared geometry, flipping it vertically, and comparing pixel for
  pixel must give a zero difference -- that is what pins the row order and the BC7/RGBA32 handling.
* every ``.blocks`` payload is a byte patch at known offsets, so porting it onto a device texture must
  leave every byte outside ``graphic["patch_ranges"]`` bit-identical -- except a regioned atlas whose
  device layout moved, which is ported sprite by sprite and may change only the blocks of the old
  offsets and of its device sprite boxes (section 10, and ``atlas_blocks``). An atlas the catalog has
  no edit for (``mobile_graphics.LABEL_ATLASES``) may change only its labels' blocks (section 11), and
  the Secret Technique title relayout may change only the moved sprites' fields (section 12).
  The PC edition's BC7 ports (``codec="bc7"``, section 13) hold the same invariants on a synthetic
  BC7 texture, and a re-run over their own output encodes no block.

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
from hashlib import sha256
import math
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.append(str(ROOT / "resources" / "runtime"))

import card_titles  # noqa: E402
import hand_card_titles  # noqa: E402
import mobile_graphics as mg  # noqa: E402
from PIL import Image  # noqa: E402
from sprite_table import REGION_SPRITE_ASSETS, sprite_rects  # noqa: E402
from wxq_patch import adaptive  # noqa: E402

CATALOG = ROOT / "resources" / "catalog"
# A device sprite table recorded from the phone's game data of 2026-10-10 (atlas_sprites.py table), so
# the sprite-aware port is exercised on a real moved layout without a dump.
LAYOUT_FIXTURE = ROOT / "tools" / "research" / "fixtures" / "13C19E4E4486B31C_rects.json"
# Pristine copies (phone, game data 1.9.2.4) of the three kinds of asset a title relayout rewrites: the
# LordSkillCardAtlas Sprite table, its TimiAtlas, and Qiao Xi's card prefab (Symphony of Tides).
FIXTURES = ROOT / "tools" / "research" / "fixtures"
TITLE_FIXTURES = {0xF86A7241DD039F73: "F86A7241DD039F73.bin", 0xEFF7C954C6C31786: "EFF7C954C6C31786.bin",
                  0x0DC65BAEC80F297C: "0DC65BAEC80F297C.bin"}
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


def skip_reason(graphic: dict, raw_size: int, ported: bool,
                sprites: dict[str, tuple[int, ...]] | None = None) -> str | None:
    """Why <graphic> could not be ported onto a <raw_size>-byte device texture, or None when it was.

    <sprites> is the device's sprite table for a regioned atlas: a region it holds at another size
    refuses the whole atlas (ADR 0006), and so does a table that carries none of the regions. A region it
    merely lacks is left out by the port, not refused.

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
        if fmt == "bc7" and layout == (4, 4) and sprites is not None:
            refused, present = [], 0
            for region in graphic.get("regions", []):
                pc, device = region["box"], sprites.get(region.get("sprite", ""))
                if device is None:
                    continue
                present += 1
                if (device[2] - device[0], device[3] - device[1]) != (pc[2] - pc[0], pc[3] - pc[1]):
                    refused.append(f"{region.get('sprite')} ({region['label']}) resized on the device")
            if not present and graphic.get("regions"):
                refused.append("no region's sprite is in the device's sprite table")
            if refused:
                return "regioned atlas refused: " + "; ".join(refused)
        if fmt not in ("rgba32", "bc7") or (fmt == "bc7" and layout != (4, 4)):
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


def catalog_sprites(graphic: dict) -> dict[str, tuple[int, ...]] | None:
    """A regioned atlas's sprite table as the catalog lays it out (the PC layout), else None.

    Given this, a regioned atlas takes the offset port, which is what the synthetic checks assert.
    """
    if int(graphic["hash"], 16) not in REGION_SPRITE_ASSETS:
        return None
    return {r["sprite"]: tuple(r["box"]) for r in graphic["regions"]}


def atlas_blocks(graphic: dict, sprites: dict[str, tuple[int, ...]]) -> set[int]:
    """Raw-order 4x4 blocks the sprite-aware port may write: the old offsets plus every drawn box."""
    width, height = int(graphic["width"]), int(graphic["height"])
    allowed = {block for offset, length in graphic["patch_ranges"]
               for block in range(offset // 16, (offset + length) // 16)}
    names = [r["sprite"] for r in graphic["regions"]] + list(mg.ATLAS_LABELS.get(graphic["hash"], {}))
    for name in names:
        if name in sprites:
            x0, y0, x1, y1 = sprites[name]
            allowed.update(((height - 1 - y) // 4) * (width // 4) + x // 4
                           for y in range(y0, y1) for x in range(x0, x1))
    return allowed


def blocks_outside(raw: bytes, new: bytes, allowed: set[int]) -> int:
    return sum(1 for index in range(0, len(raw), 16)
               if raw[index:index + 16] != new[index:index + 16] and index // 16 not in allowed)


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
        sprites = catalog_sprites(graphic)
        new = mg.english_raw(raw, graphic, CATALOG, sprites)
        if new is None:
            not_ported += 1
            continue
        by_format[fmt or "?"] = by_format.get(fmt or "?", 0) + 1
        if len(new) != len(raw):
            bad_outside += 1
            continue
        if outside_ranges(raw, new, ranges_of(graphic)):
            bad_outside += 1
        if mg.english_raw(raw, graphic, CATALOG, sprites) != new:
            nondeterministic += 1
        if mg.english_raw(new, graphic, CATALOG, sprites) != new:
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
    atlas = catalog.graphics[next(iter(REGION_SPRITE_ASSETS))]
    check("a regioned atlas without the device's sprite table returns None, never the PC offsets",
          mg.english_raw(device_bytes(1024, 1024, 4, 4), atlas, CATALOG) is None)
    # A sprite the device dropped is left out, and the rest still port (1.11.0.2 dropped CONFIRM CHOICE
    # from E86DF43167CA2143). A table holding none of the regions, or one at another size, refuses.
    ready = catalog.graphics[0xE86DF43167CA2143]
    table = {r["sprite"]: tuple(r["box"]) for r in ready["regions"]}
    dropped = next(r for r in ready["regions"] if r["label"] == "confirm_choice")
    raw = device_bytes(1024, 1024, 4, 4)
    partial = mg.english_raw(raw, ready, CATALOG, {k: v for k, v in table.items() if k != dropped["sprite"]})
    full = mg.english_raw(raw, ready, CATALOG, table)
    kept = [r for r in ready["regions"] if r is not dropped]
    same = partial is not None and all(
        sprite_diff(mg.decode_astc(partial, 1024, 1024, 4, 4), 1024, 1024, tuple(r["box"]),
                    crop_box(mg.decode_astc(full, 1024, 1024, 4, 4), 1024, 1024, r["box"])) <= mg.BLOCK_MATCH_MEAN
        for r in kept)
    check("a region the device dropped is left out and the others still port", same,
          f"left out {dropped['label']}")
    check("a table with none of the regions returns None",
          mg.english_raw(raw, ready, CATALOG, {"Image_0": (0, 0, 4, 4)}) is None)
    x0, y0, x1, y1 = table[kept[0]["sprite"]]
    check("a region at another size still refuses the atlas",
          mg.english_raw(raw, ready, CATALOG, {**table, kept[0]["sprite"]: (x0, y0, x1 - 4, y1)}) is None)


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
    from qts_relocate import read_raw  # noqa: PLC0415

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
            package, chunks = present[file_hash]
            row["raw"] = b"".join(mg.oodle_decompress(payload, slot.uncompressed_size)
                                  for slot, payload in _read_chunks(chunks))
            # The device's own sprite table, read the way port_graphics reads it.
            sprites = None
            sprite_asset = REGION_SPRITE_ASSETS.get(file_hash)
            if sprite_asset is not None and sprite_asset in package.entries:
                table = read_raw(package, package.build_slot_map(), sprite_asset)
                sprites = sprite_rects(table, width, height) if table else None
            new = mg.english_raw(row["raw"], graphic, CATALOG, sprites)
            ported = new is not None and len(new) == len(row["raw"])
            reason = skip_reason(graphic, len(row["raw"]), ported, sprites)
            if reason is not None:
                row["outcome"] = "skipped"
                row["detail"] = reason
            elif new == row["raw"]:
                row["outcome"] = "already English"
            elif sprites is not None:
                # A regioned atlas, ported at the device's sprite rects: it may write the old offsets
                # (to restore them) and its drawn boxes, and nothing else.
                row["outcome"] = "ported by sprite"
                row["outside"] = blocks_outside(row["raw"], new, atlas_blocks(graphic, sprites))
                row["idempotent"] = mg.english_raw(new, graphic, CATALOG, sprites) == new
                # The same atlas carrying the old offset port must end as this one does: blocks may
                # differ only where this input already showed the target and kept its own bytes.
                payload = (CATALOG / graphic["payload"]).read_bytes()
                other = mg.english_raw(mg._port_blocks(row["raw"], graphic, payload), graphic, CATALOG, sprites)
                a, b = mg.decode_astc(new, width, height, 4, 4), mg.decode_astc(other, width, height, 4, 4)
                row["from_damaged"] = (sum(1 for i in range(0, len(new), 16) if new[i:i + 16] != other[i:i + 16]),
                                       sum(mg._premultiplied_diff(a, b, i) for i in range(0, len(a), 4))
                                       / (width * height))
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

    for outcome in ("ported", "ported by sprite", "replaced", "spliced", "already English", "skipped",
                    "absent"):
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

    by_sprite = by_outcome.get("ported by sprite", [])
    stray = [r["hash"] for r in by_sprite if r.get("outside")]
    check("a sprite-aware atlas port touches only the old offsets and its drawn boxes", not stray,
          f"{len(by_sprite)} atlases" + (f", stray blocks in {stray}" if stray else ""))
    not_idempotent = [r["hash"] for r in by_sprite if not r.get("idempotent")]
    check("a sprite-aware atlas port over its own output changes nothing", not not_idempotent,
          f"{len(by_sprite)} atlases" + (f", {not_idempotent} not idempotent" if not_idempotent else ""))
    apart = [(r["hash"], *r["from_damaged"]) for r in by_sprite]
    check("the same atlas carrying the old offset port ends where this one does",
          all(mean <= 0.1 for _h, _blocks, mean in apart),
          "; ".join(f"{h}: {blocks} blocks differ, decoded mean {mean:.3f}" for h, blocks, mean in apart))

    accounted = sum(len(by_outcome.get(o, []))
                    for o in ("ported", "ported by sprite", "replaced", "spliced", "already English",
                              "skipped"))
    check("every texture the dump carries is ported, already English, or a documented skip",
          accounted == len(reachable),
          f"{len(by_outcome.get('ported', []))} ported, {len(by_sprite)} ported by sprite, "
          f"{len(by_outcome.get('replaced', []))} replaced, {len(spliced)} spliced, "
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


# --------------------------------------------------------------------------------------------
# 10. the sprite-aware atlas port, on a recorded device layout
# --------------------------------------------------------------------------------------------
def crop_box(image: bytes, width: int, height: int, box) -> bytes:
    """Top-down RGBA of <box> out of a decoded (bottom-up) texture."""
    x0, y0, x1, y1 = box
    out = bytearray()
    for y in range(y0, y1):
        at = ((height - 1 - y) * width + x0) * 4
        out += image[at:at + (x1 - x0) * 4]
    return bytes(out)


def sprite_diff(image: bytes, width: int, height: int, box, pixels: bytes) -> float:
    """Mean premultiplied difference between a decoded texture's top-down <box> and <pixels>."""
    x0, y0, x1, y1 = box
    total = count = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            at, src = ((height - 1 - y) * width + x) * 4, ((y - y0) * (x1 - x0) + x - x0) * 4
            total += max(
                [abs(image[at + 3] - pixels[src + 3])]
                + [abs(image[at + c] * image[at + 3] - pixels[src + c] * pixels[src + 3]) // 255
                   for c in range(3)])
            count += 1
    return total / count


def check_atlas(catalog) -> None:
    print("\n[10] the Career atlas, ported at a recorded device layout")
    import json  # noqa: PLC0415

    graphic = catalog.graphics[0x13C19E4E4486B31C]
    width, height = int(graphic["width"]), int(graphic["height"])
    sprites = {name: tuple(box) for name, box in json.loads(LAYOUT_FIXTURE.read_text()).items()}
    moved = [r["label"] for r in graphic["regions"] if sprites.get(r["sprite"]) != tuple(r["box"])]
    check("the recorded layout moves catalog regions", bool(moved), f"{len(moved)} of {len(graphic['regions'])}")
    raw = device_bytes(width, height, 4, 4)
    new = mg.english_raw(raw, graphic, CATALOG, sprites)
    check("the atlas ports", new is not None and len(new) == len(raw))
    if new is None:
        return
    check("only the old offsets and the drawn boxes change",
          blocks_outside(raw, new, atlas_blocks(graphic, sprites)) == 0)
    decoded = mg.decode_astc(new, width, height, 4, 4)
    payload = (CATALOG / graphic["payload"]).read_bytes()
    english = bytes(mg.decode_astc(mg._port_blocks(raw, graphic, payload), width, height, 4, 4))
    worst = max(sprite_diff(decoded, width, height, sprites[r["sprite"]],
                            crop_box(english, width, height, r["box"])) for r in graphic["regions"])
    check("every region's English stands at its device box", worst <= mg.BLOCK_MATCH_MEAN,
          f"worst mean difference {worst:.2f}")
    labels, restorations = mg.atlas_art(CATALOG, graphic["hash"], sprites)
    drawn = max((sprite_diff(decoded, width, height, sprites[n], px) for n, px in labels.items()), default=99)
    check("this repo's labels are drawn at their device boxes",
          set(labels) == set(mg.ATLAS_LABELS[graphic["hash"]]) and drawn <= mg.BLOCK_MATCH_MEAN,
          f"{sorted(labels)}, worst {drawn:.2f}")
    check("restoration crops apply to the recorded layout", bool(restorations), f"{len(restorations)} crops")
    check("the port is deterministic", mg.english_raw(raw, graphic, CATALOG, sprites) == new)
    check("a re-run over its own output changes nothing", mg.english_raw(new, graphic, CATALOG, sprites) == new)
    # A flat synthetic background is not the crops' art, so the same-art guard rightly declines every
    # restoration here; what must agree is everything drawn. --game compares whole real atlases.
    from_damaged = mg.english_raw(mg._port_blocks(raw, graphic, payload), graphic, CATALOG, sprites)
    other = mg.decode_astc(from_damaged, width, height, 4, 4) if from_damaged else b""
    boxes = [sprites[r["sprite"]] for r in graphic["regions"]] + [sprites[n] for n in labels]
    apart = max((sprite_diff(other, width, height, box, crop_box(decoded, width, height, box))
                 for box in boxes), default=99) if other else 99
    check("input already carrying the old offset port draws what clean input draws", apart <= 1.0,
          f"worst mean difference over {len(boxes)} drawn boxes {apart:.2f}")
    check("the catalog's own layout takes the offset port byte for byte",
          mg.english_raw(raw, graphic, CATALOG, catalog_sprites(graphic))
          == mg._port_blocks(raw, graphic, payload))
    region = graphic["regions"][0]
    shrunk = {**sprites, region["sprite"]: (*sprites[region["sprite"]][:3], sprites[region["sprite"]][3] - 1)}
    check("a region whose device sprite changed size is refused",
          mg.english_raw(raw, graphic, CATALOG, shrunk) is None)
    missing = {k: v for k, v in sprites.items() if k != region["sprite"]}
    left = mg.english_raw(raw, graphic, CATALOG, missing)
    check("a region absent from the device table is left out, never refusing the atlas (ADR 0006, amended)",
          left is not None and left != new)


# --------------------------------------------------------------------------------------------
# 11. an atlas the catalog has no edit for, carried by this repo's labels alone
# --------------------------------------------------------------------------------------------
def title_sprites(layout: dict, height: int) -> dict[str, tuple[int, int, int, int]]:
    """Top-down boxes of the title layout: the art where it is, each title where the layout moves it."""
    def box(rect: list[float]) -> tuple[int, int, int, int]:
        x, y, w, h = (int(v) for v in rect)
        return x, height - y - h, x + w, height - y

    return {**{n: box(r) for n, r in layout["art"].items()},
            **{n: box(t["now"]) for n, t in layout["titles"].items()}}


def check_label_atlas() -> None:
    print("\n[11] the Secret Technique titles, drawn at the shipped title layout")
    texture = "0B4DA7A85D27E87A"
    width, height = mg.LABEL_ATLASES[int(texture, 16)]
    layout = card_titles.load_layout(CATALOG)
    check("the title layout ships", layout is not None)
    if layout is None:
        return
    sprites = title_sprites(layout, height)
    titles = [sprites[n] for n in layout["titles"]]
    check("every title is in the atlas, on the 4x4 block grid",
          all(0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height and not (x0 % 4 or y0 % 4 or x1 % 4 or y1 % 4)
              for x0, y0, x1, y1 in titles))

    def meet(a, b, gap=0):
        return a[0] < b[2] + gap and b[0] < a[2] + gap and a[1] < b[3] + gap and b[1] < a[3] + gap

    overlaps = sum(meet(a, b) for i, a in enumerate(titles) for b in titles[i + 1:])
    art_hits = sum(meet(t, sprites[n], 1) for t in titles for n in layout["art"])
    check("no title overlaps another or comes within 1 px of the art", not overlaps and not art_hits,
          f"{overlaps} overlaps, {art_hits} art contacts")
    check("the layout covers every title", set(layout["titles"]) == set(mg.ATLAS_LABELS[texture]))
    raw = device_bytes(width, height, 4, 4)
    new = mg.label_atlas(raw, texture, CATALOG, sprites)
    check("the atlas takes its labels", new is not None and len(new) == len(raw))
    if new is None:
        return
    labels, _restorations = mg.atlas_art(CATALOG, texture, sprites)
    allowed = mg._box_blocks([sprites[name] for name in labels], width, height)
    check("only the labels' blocks change", blocks_outside(raw, new, allowed) == 0,
          f"{len(allowed)} blocks allowed")
    decoded = mg.decode_astc(new, width, height, 4, 4)
    drawn = max((sprite_diff(decoded, width, height, sprites[n], px) for n, px in labels.items()), default=99)
    check("every label is drawn at its device box",
          set(labels) == set(mg.ATLAS_LABELS[texture]) and drawn <= mg.BLOCK_MATCH_MEAN,
          f"{len(labels)} labels, worst {drawn:.2f}")
    indonesian = mg.label_atlas(raw, texture, CATALOG.parent / "catalog_id", sprites)
    check("Indonesian draws the same English titles", indonesian == new)
    check("the draw is deterministic", mg.label_atlas(raw, texture, CATALOG, sprites) == new)
    check("a re-run over its own output changes nothing", mg.label_atlas(new, texture, CATALOG, sprites) == new)
    name = next(iter(mg.ATLAS_LABELS[texture]))
    shrunk = {**sprites, name: (*sprites[name][:3], sprites[name][3] - 1)}
    check("a label whose device sprite changed size refuses the atlas",
          mg.label_atlas(raw, texture, CATALOG, shrunk) is None)
    check("a label absent from the device table refuses the atlas",
          mg.label_atlas(raw, texture, CATALOG, {k: v for k, v in sprites.items() if k != name}) is None)
    check("a texture of another size is refused",
          mg.label_atlas(device_bytes(width, height, 6, 6), texture, CATALOG, sprites) is None)
    unmoved = sprite_rects((FIXTURES / TITLE_FIXTURES[0xF86A7241DD039F73]).read_bytes(), width, height)
    check("the pristine layout refuses the atlas (no label fits an unmoved sprite)",
          mg.label_atlas(raw, texture, CATALOG, unmoved) is None)


def check_label_texture() -> None:
    print("\n[14] a standalone label drawn from this repo's art, per language (LABEL_TEXTURES)")
    for texture, (width, height, _name) in sorted(mg.LABEL_TEXTURES.items()):
        name = f"{texture:016X}"
        english = mg.label_texture_art(CATALOG, name)
        indonesian = mg.label_texture_art(CATALOG.parent / "catalog_id", name)
        check(f"{name}: English and Indonesian art ship at {width}x{height}",
              english is not None and indonesian is not None)
        if english is None or indonesian is None:
            continue
        check(f"{name}: Indonesian draws its own art, not the English", english != indonesian)
        device = device_bytes(width, height, 6, 6)
        drawn = mg.label_texture(device, name, CATALOG)
        check(f"{name}: the phone's 6x6 texture is replaced whole at its own size",
              drawn is not None and len(drawn) == len(device) and drawn != device)
        if drawn is not None:
            shown = vertical_flip(mg.decode_astc(drawn, width, height, 6, 6), width, height)
            check(f"{name}: it decodes to the art", mean_abs_diff(shown, english) < 4,
                  f"mean {mean_abs_diff(shown, english):.2f}")
            check(f"{name}: a re-run over its own output changes nothing",
                  mg.label_texture(drawn, name, CATALOG) == drawn)
        pc = bytes(width * height * 4)
        rows = mg.label_texture(pc, name, CATALOG, codec="rgba32")
        check(f"{name}: the PC's RGBA32 texture gets the art in bottom-up rows",
              rows is not None and vertical_flip(rows, width, height) == english)
        check(f"{name}: a texture of another size returns None",
              mg.label_texture(device[:-16], name, CATALOG) is None
              and mg.label_texture(pc[:-4], name, CATALOG, codec="rgba32") is None)


def check_relayout() -> None:
    print("\n[12] the Secret Technique title relayout, on pristine fixtures")
    import struct  # noqa: PLC0415

    width, height = mg.LABEL_ATLASES[card_titles.TITLE_ATLAS]
    shipped = card_titles.load_layout(CATALOG)
    if shipped is None:
        check("the title layout ships", False)
        return
    qiao = f"{0x0DC65BAEC80F297C:016X}"
    layout = {**shipped, "boxes": {qiao: shipped["boxes"][qiao]}}  # the one prefab kept as a fixture
    pristine = {h: (FIXTURES / name).read_bytes() for h, name in TITLE_FIXTURES.items()}
    jobs = card_titles.relayout(pristine.get, layout)
    check("all three assets move", jobs is not None and set(jobs) == set(pristine),
          f"{len(jobs or {})} of {len(pristine)}")
    if not jobs or set(jobs) != set(pristine):
        return
    check("no asset changes length", all(len(jobs[h]) == len(pristine[h]) for h in jobs))
    table = jobs[0xF86A7241DD039F73]
    check("the moved table reads back at the layout's boxes",
          sprite_rects(table, width, height) == title_sprites(shipped, height))
    changed = {i for i, (a, b) in enumerate(zip(pristine[0xF86A7241DD039F73], table)) if a != b}
    allowed: set[int] = set()
    for _pid, start, size in card_titles._objects(table, card_titles.SPRITE_CLASS):
        name, at, _rect = card_titles.sprite_fields(table[start:start + size])
        if name in shipped["titles"]:
            for field, length in (("rect", 16), ("vertices", 48), ("texture_rect", 16), ("uv_transform", 16)):
                allowed.update(range(start + at[field], start + at[field] + length))
    check("only the titles' rect, vertices, textureRect and uvTransform change", changed <= allowed,
          f"{len(changed)} bytes changed")
    index = jobs[0xEFF7C954C6C31786]
    found = []
    for name, title in shipped["titles"].items():
        key = struct.pack("<i", len(name)) + name.encode()
        at = (index.index(key) + len(key) + 3) & ~3
        values = struct.unpack_from("<10f", index, at)
        found.append(list(values[:4]) == title["now"] and values[8:] == (title["now"][2] / 2, title["now"][3] / 2))
    check("the TimiAtlas carries each title's new rect and pivot", all(found), f"{sum(found)} of {len(found)}")
    box = layout["boxes"][qiao]
    prefab = jobs[0x0DC65BAEC80F297C]
    sizes = [list(struct.unpack_from("<2f", prefab, start + card_titles._rect_size_at(prefab[start:start + n])))
             for pid, start, n in card_titles._objects(prefab, card_titles.RECT_TRANSFORM_CLASS)
             if pid == box["path_id"]]
    check("Qiao Xi's Title box takes its sprite's new size",
          sizes == [shipped["titles"][box["sprite"]]["now"][2:]], f"{box['was']} -> {sizes}")
    moved = {**pristine, **jobs}
    check("a re-run over its own output changes nothing", card_titles.relayout(moved.get, layout) == {})
    art = next(iter(shipped["art"]))
    nudged = {**shipped, "art": {**shipped["art"], art: [v + 4 for v in shipped["art"][art]]}}
    check("an art sprite away from its recorded rect refuses", card_titles.relayout(pristine.get, nudged) is None)
    name = next(iter(shipped["titles"]))
    odd = {**layout, "titles": {**shipped["titles"], name: {**shipped["titles"][name],
                                                          "was": [0.0, 0.0, 4.0, 4.0]}}}
    check("a title at neither its pristine nor its new rect refuses", card_titles.relayout(pristine.get, odd) is None)
    other = {**layout, "boxes": {qiao: {**box, "was": [1.0, 1.0]}}}
    check("a Title box at neither size refuses", card_titles.relayout(pristine.get, other) is None)
    check("a missing asset refuses",
          card_titles.relayout({h: b for h, b in pristine.items() if h != 0xEFF7C954C6C31786}.get, layout) is None)
    check("bytes that do not parse refuse",
          card_titles.relayout({**pristine, 0xF86A7241DD039F73: b"\0" * 64}.get, layout) is None)


# --------------------------------------------------------------------------------------------
# 13. the PC edition's BC7 atlases: the same ports, decoded and re-encoded as BC7
# --------------------------------------------------------------------------------------------
def bc7_texture(width: int, height: int, rgba: tuple[int, int, int, int] = (7, 38, 69, 255)) -> bytes:
    """A valid flat BC7 texture: one encoded block, repeated (every block of a flat image is the same)."""
    import bc7_mode6  # noqa: PLC0415

    return bc7_mode6.encode_block([rgba] * 16) * ((width // 4) * (height // 4))


class EncodeCounter:
    """Counts `bc7_mode6.encode_block` calls; `_reencode` imports it at call time, so this sees each one."""

    def __init__(self) -> None:
        import bc7_mode6  # noqa: PLC0415

        self.module, self.original, self.calls, self.seconds = bc7_mode6, bc7_mode6.encode_block, 0, 0.0

    def __enter__(self) -> "EncodeCounter":
        def counted(pixels):
            started = time.perf_counter()
            try:
                return self.original(pixels)
            finally:
                self.calls += 1
                self.seconds += time.perf_counter() - started

        self.module.encode_block = counted
        return self

    def __exit__(self, *_exc) -> None:
        self.module.encode_block = self.original


def check_bc7(catalog) -> None:
    print("\n[13] the PC edition's BC7 atlases (port_atlas / label_atlas with codec='bc7')")
    import json  # noqa: PLC0415
    import random  # noqa: PLC0415

    import bc7_mode6  # noqa: PLC0415
    from pc_catalog import block_runs  # noqa: PLC0415

    graphic = catalog.graphics[0x13C19E4E4486B31C]
    width, height = int(graphic["width"]), int(graphic["height"])
    raw = bc7_texture(width, height)
    payload = (CATALOG / graphic["payload"]).read_bytes()
    english = mg.decode_pc(mg._apply_blocks(raw, graphic, payload), width, height, "bc7")
    # Blocks of real label art: the Career atlas's English, sampled where the catalog patches it, judged
    # premultiplied as the port judges a block (mobile_graphics.BLOCK_MATCH_MEAN). A plain RGBA mean also
    # counts the color under transparent pixels, which BC7 may drop: 30.4 on one such block (2026-11-20).
    rng = random.Random(20261120)
    patched = [offset // 16 + i for offset, length in graphic["patch_ranges"] for i in range(length // 16)]
    worst = total = 0.0
    for block in rng.sample(patched, 64):
        row, column = (block // (width // 4)) * 4, (block % (width // 4)) * 4
        pixels = [tuple(english[((row + y) * width + column + x) * 4:((row + y) * width + column + x) * 4 + 4])
                  for y in range(4) for x in range(4)]
        decoded = mg.decode_pc(bc7_mode6.encode_block(pixels), 4, 4, "bc7")
        difference = bc7_mode6.mismatch(pixels, [tuple(decoded[i:i + 4]) for i in range(0, 64, 4)])
        worst, total = max(worst, difference), total + difference
    check("a block of the Career atlas's English round-trips", worst <= mg.BLOCK_MATCH_MEAN,
          f"64 blocks, mean {total / 64:.2f}, worst {worst:.2f}")
    edge = [(255, 255, 255, 255)] * 8 + [(0, 0, 0, 0)] * 8
    decoded = mg.decode_pc(bc7_mode6.encode_block(edge), 4, 4, "bc7")
    check("a block half label, half transparent keeps both", mean_abs_diff(decoded, bytes(c for p in edge for c in p)) <= 1.0)

    sprites = {name: tuple(box) for name, box in json.loads(LAYOUT_FIXTURE.read_text()).items()}
    with EncodeCounter() as first:
        new = mg.port_atlas(raw, graphic, CATALOG, sprites, codec="bc7")
    check("the Career atlas ports in BC7", new is not None and len(new) == len(raw),
          f"{first.calls} blocks encoded in {first.seconds:.1f}s")
    if new is None:
        return
    check("only the old offsets and the drawn boxes change",
          blocks_outside(raw, new, atlas_blocks(graphic, sprites)) == 0)
    decoded = mg.decode_pc(new, width, height, "bc7")
    worst = max(sprite_diff(decoded, width, height, sprites[r["sprite"]],
                            crop_box(english, width, height, r["box"])) for r in graphic["regions"])
    check("every region's English stands at its device box", worst <= mg.BLOCK_MATCH_MEAN,
          f"worst mean difference {worst:.2f}")
    labels, _restorations = mg.atlas_art(CATALOG, graphic["hash"], sprites)
    drawn = max((sprite_diff(decoded, width, height, sprites[n], px) for n, px in labels.items()), default=99)
    check("this repo's labels are drawn at their device boxes", drawn <= mg.BLOCK_MATCH_MEAN,
          f"{sorted(labels)}, worst {drawn:.2f}")
    check("the port is deterministic", mg.port_atlas(raw, graphic, CATALOG, sprites, codec="bc7") == new)
    with EncodeCounter() as rerun:
        again = mg.port_atlas(new, graphic, CATALOG, sprites, codec="bc7")
    check("a re-run over its own output re-encodes nothing", again == new and rerun.calls == 0,
          f"{rerun.calls} blocks encoded")
    check("the catalog's own layout takes the catalog's blocks byte for byte",
          mg.port_atlas(raw, graphic, CATALOG, catalog_sprites(graphic), codec="bc7")
          == mg._apply_blocks(raw, graphic, payload))
    region = graphic["regions"][0]
    shrunk = {**sprites, region["sprite"]: (*sprites[region["sprite"]][:3], sprites[region["sprite"]][3] - 1)}
    check("a region whose sprite changed size is refused",
          mg.port_atlas(raw, graphic, CATALOG, shrunk, codec="bc7") is None)
    check("an unknown codec is refused", mg.port_atlas(raw, graphic, CATALOG, sprites, codec="etc2") is None)
    ranges = block_runs(raw, new)
    patch = {"patch_ranges": ranges}
    check("the per-install payload rebuilds the port from the original",
          mg._apply_blocks(raw, patch, b"".join(new[o:o + n] for o, n in ranges)) == new,
          f"{len(ranges)} runs, {sum(n for _o, n in ranges) // 16} blocks")

    texture = "0B4DA7A85D27E87A"
    width, height = mg.LABEL_ATLASES[int(texture, 16)]
    layout = card_titles.load_layout(CATALOG)
    if layout is None:
        check("the title layout ships", False)
        return
    titles = title_sprites(layout, height)
    raw = bc7_texture(width, height)
    with EncodeCounter() as first:
        new = mg.label_atlas(raw, texture, CATALOG, titles, codec="bc7")
    check("the Secret Technique titles draw in BC7", new is not None and len(new) == len(raw),
          f"{first.calls} blocks encoded in {first.seconds:.1f}s")
    if new is None:
        return
    labels, _restorations = mg.atlas_art(CATALOG, texture, titles)
    allowed = mg._box_blocks([titles[name] for name in labels], width, height)
    check("only the labels' blocks change", blocks_outside(raw, new, allowed) == 0)
    decoded = mg.decode_pc(new, width, height, "bc7")
    drawn = max(sprite_diff(decoded, width, height, titles[n], px) for n, px in labels.items())
    check("every title is drawn at its box", drawn <= mg.BLOCK_MATCH_MEAN, f"worst {drawn:.2f}")
    with EncodeCounter() as rerun:
        again = mg.label_atlas(new, texture, CATALOG, titles, codec="bc7")
    check("a re-run over its own output re-encodes nothing", again == new and rerun.calls == 0,
          f"{rerun.calls} blocks encoded")
    check("the ASTC path is untouched by the codec argument",
          mg.label_atlas(device_bytes(width, height, 4, 4), texture, CATALOG, titles)
          == mg.label_atlas(device_bytes(width, height, 4, 4), texture, CATALOG, titles, codec="astc"))


def check_hand_card_titles() -> None:
    print("\n[15] the captured Secret Technique hand cards")
    edits = hand_card_titles.load_edits(CATALOG)
    check("both languages carry one edit for each Secret Technique title",
          len(edits) == len(mg.ATLAS_LABELS[f"{card_titles.TITLE_ATLAS:016X}"])
          and edits == hand_card_titles.load_edits(CATALOG.with_name("catalog_id")))
    raw = bytes(hand_card_titles.RAW_SIZE)
    expected = bytearray(raw)
    stride = hand_card_titles.ROW_BYTES
    first = stride + 16
    second = first + stride
    expected[first:first + 16] = b"\x11" * 16
    expected[second:second + 16] = b"\x22" * 16
    edit = hand_card_titles.TitleEdit(sha256(raw).hexdigest(), sha256(expected).hexdigest(),
                                    (1, 1, 2, 3), b"\x11" * 16 + b"\x22" * 16)
    patched = edit.apply(raw)
    check("only the measured title blocks change", patched == expected)
    check("the title patch is idempotent", patched is not None and edit.apply(patched) == patched)
    check("the title patch refuses an unmeasured revision", edit.apply(b"\xff" + raw[1:]) is None)


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
    check_atlas(catalog)
    check_label_atlas()
    check_label_texture()
    check_relayout()
    check_hand_card_titles()
    check_bc7(catalog)
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
