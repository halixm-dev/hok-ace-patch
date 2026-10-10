"""Port the catalog's English texture edits onto the Android ASTC textures.

The catalog payloads are PC-format data: BC7 (or raw RGBA32) blocks, sometimes a whole replacement
image and sometimes only the runs a Chinese label occupied. Android stores the same images as ASTC
inside Oodle-compressed chunks, so a payload can only be applied once the device texture has been
decompressed and its block footprint derived from the raw size.

Two payload families and five paths:

* a ``.blocks`` BC7 payload at the 4x4 footprint is ported block for block — BC7 and ASTC 4x4 both
  use 16-byte blocks on a 4x4 grid, so a PC byte range maps to the same byte range on the device;
* except a regioned atlas (``sprite_table.REGION_SPRITE_ASSETS``), whose mobile build may pack its
  sprites elsewhere: it is ported sprite by sprite at the device's own rects (``port_atlas``), and
  refused outright without them;
* a ``.blocks`` RGBA32 payload is pasted onto the decoded image and only the blocks it touches are
  re-encoded;
* a ``.assets`` payload replaces the whole image;
* a ``.assets`` payload whose device revision moved geometry is spliced: the two images are aligned,
  only the label's pixels are copied across, and only the blocks those pixels touch are re-encoded.

Nothing here raises for a texture it cannot handle: ``english_raw`` returns ``None`` and the caller
counts the texture as skipped. A silently skipped texture is far better than a failed patch run.
"""
from __future__ import annotations

import math
from pathlib import Path

import astc_encoder
import ooz
import texture2ddecoder

from languages import payload_path
from sprite_table import REGION_SPRITE_ASSETS

OODLE_BLOCK = 0x40000  # Oodle LZ streams are split into 256 KiB blocks
ASTC_FOOTPRINTS = [(4, 4), (5, 5), (6, 6), (8, 8), (10, 10), (12, 12)]
PC_FORMATS = ("bc7", "rgba32")

# Recovering a whole-image replacement whose device revision is a different size. A consumer build can
# re-cut the same art by a block row, which changes the raw size and makes `astc_layout` refuse it. The
# two images are still the same art though, so the label can be moved across once the alignment is
# measured. These bound the search and gate the result.
ALIGNMENT_SEARCH = 16      # px of vertical offset to try
ALIGNMENT_MAX_MEAN = 12.0  # mean per-pixel difference outside the label that still counts as same art
ALIGNMENT_MIN_GAIN = 0.75  # the winning offset must beat the median offset by this much to be believed
ALIGNMENT_STEP_X = 8       # sample every Nth pixel horizontally; the art differs in blocks, not pixels
ALIGNMENT_STEP_ROWS = 4    # and every Nth row vertically
# A label already carrying the English pixels measures ~3.5 once decoded; the Chinese one measures ~64.
# 12 sits well clear of both, so a re-run is recognised instead of being re-encoded.
LABEL_MATCH_MEAN = 12.0

# Six catalog entries carry no format/width/height, so their payloads could never be applied. All six
# are 159040-byte map banners of one family (no label_box, no capture_row, no footer_group), and
# 568 * 70 * 4 == 159040 exactly. The four with a review render decode to it at zero difference; the
# other two are inferred from the identical payload length and the same family, and are the only
# texture metadata here that is not pixel-verified.
# Keyed by graphic["hash"], which is the uppercase hex string the loaded catalog actually carries.
MISSING_METADATA: dict[str, tuple[str, int, int]] = {
    "04D47725DE379AD7": ("rgba32", 568, 70),
    "078D65B9906EAB4B": ("rgba32", 568, 70),
    "6A7F8C75A66ADE07": ("rgba32", 568, 70),
    "CAB4D44F77EE39BD": ("rgba32", 568, 70),
    "D2317B3C316126EE": ("rgba32", 568, 70),
    "EA2F803D955BE24F": ("rgba32", 568, 70),
}

# Catalog edits the mobile build carries under another asset hash. The three 404x564 effect-card band
# edits below exist in neither data layer under their own hash, yet package 15 holds exactly one
# uncatalogued card per edit whose band decodes to the band of a catalogued card sharing that edit's
# payload at a mean difference of 0.01-0.02 (the next-closest band in the census is 0.38, a blank band).
# A band edit is the same bytes for every card of its group, so the payload lands unchanged. Measured
# over all 1994 card textures of the 1.4.0.2 layer; `962747E1E5B73A93` is the Riverlands effect card
# Armed Power, whose band stayed Chinese.
DEVICE_REVISIONS: dict[int, int] = {
    0x962747E1E5B73A93: 0x884E0B4581F47CF7,  # Riverlands effect card (Armed Power)
    0xC71FEF8D6BE03BBF: 0x89C771ECFCDC7FBE,  # Sunset effect card
    0x29B6B1724CC28DE0: 0x197CC5393D16E3CB,  # Three Kingdoms effect card
}

# A regioned atlas (``sprite_table.REGION_SPRITE_ASSETS``) is ported sprite by sprite at the device's own
# rects. This repo's art for it lives in resources/<SPRITE_ART>/<HASH>/, beside the catalogs: labels/
# holds renders for sprites the catalog never translated, restore/ the pristine crops of the sprites the
# old offset-for-offset port overwrote. Both are top-down RGBA PNGs at the sprite's own size, made by
# tools/research/atlas_sprites.py. Every language uses them: the atlas's rank names are English in both.
SPRITE_ART = "sprites"
# Wording of each label render, by atlas then sprite. Free translations where the catalog has none,
# recorded here the way extra_text.OFFICIAL_FIXES records its own. Both renders are hand-polished, and
# device-verified 2026-10-10 on the Career screen (Xiaomi M2007J3SG, Android 12, game data 1.5.0.1).
ATLAS_LABELS: dict[str, dict[str, str]] = {
    "13C19E4E4486B31C": {
        "Image_410780920": "MY SKINS",      # 我的皮肤, the Career switch's skin state; no catalog entry
        "Image_920603129": "TOTAL PROFIT",  # 总盈利; the catalog's text table says "Total profit"
    },
}
# A block whose decoded pixels already show the target within this mean premultiplied difference is left
# alone: that keeps an untouched pristine block's own bytes and spares a re-run re-encoding a lossy decode
# of itself. Measured on the Career atlas, the first run leaves 4350 (today's layout) to 7091 (10-03) of
# ~9800 candidate blocks to re-encode, with no gap in the distribution at the threshold; about 1500 blocks
# stay above it after encoding (ASTC cannot get closer than a mean of 25 to some glyph edges) and are
# re-encoded on every run, which is byte-identical only because the encoder is deterministic for the same
# input on the same platform.
BLOCK_MATCH_MEAN = 6.0
# A restoration crop is used only while the device's copy of the sprite, outside the blocks the old port
# wrote, still matches it this closely. The same art re-encoded at another block phase measured <= 5.3.
RESTORE_MATCH_MEAN = 12.0

_contexts: dict[tuple[int, int], astc_encoder.ASTCContext] = {}


def catalog_graphics(graphics: dict[int, dict]) -> dict[int, dict]:
    """<graphics> plus each edit's device revision, keyed by the hash the device carries it under."""
    merged = dict(graphics)
    for device_hash, catalog_hash in DEVICE_REVISIONS.items():
        if catalog_hash in graphics:
            merged.setdefault(device_hash, graphics[catalog_hash])
    return merged


def oodle_stored(raw: bytes, decoder_type: int = 0x0C) -> bytes:
    """Wrap <raw> as uncompressed Oodle blocks (header 0xCC = reset + raw + magic nibble).

    No Oodle compressor exists for Python, only ooz's decompressor, and the game accepts stored
    blocks, so a relocated chunk keeps the container the shard expects without being recompressed.
    """
    out = bytearray()
    for start in range(0, len(raw), OODLE_BLOCK):
        out += bytes((0xCC, decoder_type)) + raw[start:start + OODLE_BLOCK]
    return bytes(out)


def oodle_decompress(payload: bytes, raw_size: int) -> bytes:
    return ooz.decompress(payload, raw_size)


def astc_layout(raw_size: int, width: int, height: int) -> tuple[int, int] | None:
    """The ASTC block footprint that makes <raw_size> bytes hold a <width>x<height> image."""
    for bx, by in ASTC_FOOTPRINTS:
        if math.ceil(width / bx) * math.ceil(height / by) * 16 == raw_size:
            return bx, by
    return None


def label_rows(graphic: dict, height: int) -> tuple[int, int] | None:
    """The label's row range in the decoded payload buffer.

    ``label_box`` is stated in display order (top-down) like the review renders, while the payload
    buffer is bottom-up, so the box has to be mirrored to index it. Cropping the payload at the raw
    ``label_box`` rows returns a blank band; mirroring first returns the text.
    """
    box = graphic.get("label_box")
    if not box:
        return None
    top, bottom = height - box[3], height - box[1]
    if top >= bottom or top < 0:
        return None
    return top, bottom


def offset_layouts(raw_size: int, width: int, height: int) -> list[tuple[int, int, int]]:
    """(device_height, bx, by) whose blocks fill <raw_size> at the catalog's width.

    The block count pins the geometry to within a block, so this returns the band's tallest height:
    every height in the band covers the same block grid, so they share one decode and one encode and
    the choice between them cannot change the output bytes.
    """
    layouts = []
    for bx, by in ASTC_FOOTPRINTS:
        blocks_x = math.ceil(width / bx)
        if not blocks_x or raw_size % (blocks_x * 16):
            continue
        blocks_y = raw_size // (blocks_x * 16)
        tallest, lowest = blocks_y * by, (blocks_y - 1) * by + 1
        if lowest - ALIGNMENT_SEARCH <= height <= tallest + ALIGNMENT_SEARCH:
            layouts.append((tallest, bx, by))
    return layouts


def _row_diff(left: bytes, right: bytes, width: int, left_row: int, right_row: int) -> float:
    """Mean absolute difference between two rows, sampled. Alpha is skipped: it is flat here."""
    left_at, right_at = left_row * width * 4, right_row * width * 4
    total = count = 0
    for x in range(0, width * 4, ALIGNMENT_STEP_X * 4):
        for channel in (0, 1, 2):
            total += abs(left[left_at + x + channel] - right[right_at + x + channel])
            count += 1
    return total / count


def align_rows(catalog_rgba: bytes, device_rgba: bytes, width: int, catalog_height: int,
               device_height: int, rows: tuple[int, int]) -> int | None:
    """The offset putting the catalog image's row y at the device's row y+offset, or None.

    BC7 on the PC and ASTC on the device never decode the same source to identical pixels, so the
    overlap is compared and the winner must both stay under ``ALIGNMENT_MAX_MEAN`` and dip well below
    the median offset. Unrelated art, or the wrong block footprint, scores flat and is refused.
    """
    scored: list[tuple[int, float]] = []
    # The label is the one place the two images are expected to differ, so it is left out. The rows
    # compared do not depend on the offset, so they are picked once.
    compared = list(range(0, rows[0], ALIGNMENT_STEP_ROWS)) + \
        list(range(rows[1], catalog_height, ALIGNMENT_STEP_ROWS))
    for offset in range(-ALIGNMENT_SEARCH, ALIGNMENT_SEARCH + 1):
        total = count = 0.0
        for y in compared:
            target = y + offset
            if 0 <= target < device_height:
                total += _row_diff(catalog_rgba, device_rgba, width, y, target)
                count += 1
        scored.append((offset, total / count if count else math.inf))
    usable = [item for item in scored if item[1] != math.inf]
    if not usable:
        return None
    best = min(usable, key=lambda item: item[1])
    median = sorted(value for _, value in usable)[len(usable) // 2]
    if best[1] > ALIGNMENT_MAX_MEAN or best[1] > ALIGNMENT_MIN_GAIN * median:
        return None
    return best[0]


def _label_diff(catalog_rgba: bytes, device_rgba: bytes, width: int, device_height: int,
                rows: tuple[int, int], box: list[int], offset: int) -> float | None:
    """Mean absolute difference between the catalog's label and the device's, or None if it does not fit."""
    stride = width * 4
    left = box[0] * 4
    length = (box[2] - box[0]) * 4
    total = count = 0
    for y in range(rows[0], rows[1], 2):
        target = y + offset
        if not 0 <= target < device_height:
            return None
        source_at, target_at = y * stride + left, target * stride + left
        for x in range(0, length, ALIGNMENT_STEP_X * 4):
            for channel in (0, 1, 2):
                total += abs(catalog_rgba[source_at + x + channel]
                             - device_rgba[target_at + x + channel])
                count += 1
    return total / count if count else None


def splice_label(mobile_raw: bytes, graphic: dict, catalog: Path, width: int, height: int,
                 fmt: str) -> bytes | None:
    """Land <graphic>'s label on a device texture whose geometry moved, or return None.

    Used when the device revision no longer matches the catalog's recorded size, which is a rejection
    for a whole-image replacement. The art is still the same art, so rather than rescaling the payload
    -- which would resample every glyph -- this finds the alignment between the two images and copies
    only the ``label_box`` pixels across, then re-encodes just the blocks that touch. Every other byte
    of the device texture, including any art the mobile build genuinely re-drew, is left alone.
    """
    rows = label_rows(graphic, height)
    if rows is None:
        return None
    box = graphic["label_box"]
    payload = payload_path(catalog, graphic["payload"]).read_bytes()
    catalog_rgba = decode_pc(payload, width, height, fmt)
    for device_height, bx, by in offset_layouts(len(mobile_raw), width, height):
        device_rgba = bytearray(decode_astc(mobile_raw, width, device_height, bx, by))
        offset = align_rows(bytes(catalog_rgba), bytes(device_rgba), width, height, device_height, rows)
        if offset is None:
            continue
        existing = _label_diff(catalog_rgba, bytes(device_rgba), width, device_height, rows, box, offset)
        if existing is not None and existing <= LABEL_MATCH_MEAN:
            # Already spliced. Returning the bytes untouched keeps a re-run idempotent: re-encoding the
            # same region from a lossy decode would perturb the blocks along the label's edge.
            return mobile_raw
        touched: set[tuple[int, int]] = set()
        stride = width * 4
        for y in range(rows[0], rows[1]):
            target = y + offset
            if not 0 <= target < device_height:
                return None
            source_at, target_at = y * stride + box[0] * 4, target * stride + box[0] * 4
            length = (box[2] - box[0]) * 4
            device_rgba[target_at:target_at + length] = catalog_rgba[source_at:source_at + length]
            for x in range(box[0], box[2], bx):
                touched.add((x // bx, target // by))
        encoded = encode_astc(bytes(device_rgba), width, device_height, bx, by)
        blocks_x = math.ceil(width / bx)
        out = bytearray(mobile_raw)
        for block_x, block_y in touched:
            at = (block_y * blocks_x + block_x) * 16
            out[at:at + 16] = encoded[at:at + 16]
        return bytes(out)
    return None


def _context(bx: int, by: int) -> astc_encoder.ASTCContext:
    if (bx, by) not in _contexts:
        config = astc_encoder.ASTCConfig(astc_encoder.ASTCProfile.LDR, bx, by, 1, 85)
        _contexts[(bx, by)] = astc_encoder.ASTCContext(config)
    return _contexts[(bx, by)]


def encode_astc(rgba: bytes, width: int, height: int, bx: int, by: int) -> bytes:
    image = astc_encoder.ASTCImage(astc_encoder.ASTCType.U8, width, height, 1, rgba)
    return _context(bx, by).compress(image, astc_encoder.ASTCSwizzle())


def decode_pc(raw: bytes, width: int, height: int, fmt: str) -> bytes:
    """PC texture data -> RGBA8, in the PC's own row order (bottom-up)."""
    if fmt == "bc7":
        return _bgra_to_rgba(texture2ddecoder.decode_bc7(raw, width, height))
    if fmt == "rgba32":
        return raw[: width * height * 4]
    raise ValueError(f"unsupported PC format {fmt}")


def decode_astc(raw: bytes, width: int, height: int, bx: int, by: int) -> bytes:
    return _bgra_to_rgba(texture2ddecoder.decode_astc(raw, width, height, bx, by))


def _bgra_to_rgba(data: bytes) -> bytes:
    buf = bytearray(data)
    buf[0::4], buf[2::4] = buf[2::4], buf[0::4]
    return bytes(buf)


def _dimensions(graphic: dict) -> tuple[int, int, str | None]:
    """The texture's declared geometry, falling back to MISSING_METADATA for the six bare entries."""
    width, height = int(graphic.get("width") or 0), int(graphic.get("height") or 0)
    fmt = graphic.get("format")
    if not width or not height or fmt not in PC_FORMATS:
        fallback = MISSING_METADATA.get(graphic.get("hash", ""))
        if fallback is not None:
            fmt, width, height = fallback
    return width, height, fmt


def _port_blocks(mobile_raw: bytes, graphic: dict, payload: bytes) -> bytes:
    """Port a BC7 ``.blocks`` payload onto a 4x4 ASTC texture at the same byte offsets.

    Each range is a 16-byte-aligned run of BC7 blocks, which decode and re-encode independently of where
    they sit in the image, so a run is handed to the codecs as one <blocks*4>x4 strip and written back
    at the same offset.
    """
    out = bytearray(mobile_raw)
    cursor = 0
    for offset, length in graphic["patch_ranges"]:
        row = payload[cursor:cursor + length]
        cursor += length
        blocks = length // 16
        rgba = decode_pc(row, blocks * 4, 4, "bc7")
        out[offset:offset + length] = encode_astc(rgba, blocks * 4, 4, 4, 4)
    return bytes(out)


def atlas_art(catalog: Path, texture: str, sprites: dict[str, tuple[int, int, int, int]]
              ) -> tuple[dict[str, bytes], dict[str, bytes]]:
    """This repo's art for <texture>'s device sprites: ``(labels, restorations)``, top-down RGBA each.

    Only a sprite the device table carries at the art's own size is returned; anything else is left out,
    so a later layout that drops or resizes a sprite stops drawing it rather than drawing it wrong.
    """
    from PIL import Image

    art: tuple[dict[str, bytes], dict[str, bytes]] = ({}, {})
    root = Path(catalog).parent / SPRITE_ART / texture
    for found, kind in zip(art, ("labels", "restore")):
        names = ATLAS_LABELS.get(texture, {}) if kind == "labels" else None
        for path in sorted((root / kind).glob("Image_*.png")):
            box = sprites.get(path.stem)
            if box is None or (names is not None and path.stem not in names):
                continue
            with Image.open(path) as image:
                if image.size != (box[2] - box[0], box[3] - box[1]):
                    continue
                found[path.stem] = image.convert("RGBA").tobytes()
    return art


def _premultiplied_diff(left: bytes | bytearray, right: bytes | bytearray, at: int) -> int:
    """Largest channel difference between two RGBA pixels once each is weighted by its own alpha."""
    la, ra = left[at + 3], right[at + 3]
    worst = abs(la - ra)
    for channel in range(3):
        worst = max(worst, abs(left[at + channel] * la - right[at + channel] * ra) // 255)
    return worst


def port_atlas(mobile_raw: bytes, graphic: dict, catalog: Path,
               sprites: dict[str, tuple[int, int, int, int]]) -> bytes | None:
    """Port a regioned atlas edit sprite by sprite, at the device's own sprite rects, or return None.

    The catalog drew its ``.blocks`` patch on the PC atlas layout, and the mobile atlas may pack the same
    sprites elsewhere: ported offset for offset, a moved sprite's English lands on whatever the device
    keeps there (9 of the Career atlas's 13 labels did). So each region's English pixels are decoded out
    of the payload at the region's PC box and composited into the same sprite's **device** box.

    The phone may already carry the old offset port's damage, so the pixels it could have damaged are
    taken from data rather than from the device copy wherever data exists: the blocks that port wrote
    (the payload's ``patch_ranges``) are redrawn from this repo's restoration crops (``atlas_art``),
    transparent where no sprite lies. A sprite there with no crop, or whose crop no longer matches the
    device's art (``_same_art``), keeps the device's pixels. Labels this repo draws are written over
    their whole device box, then each region's English over its own.

    Only the 4x4 blocks those pixels touch are re-encoded, and of those only the ones whose decoded pixels
    do not already show the target (``BLOCK_MATCH_MEAN``), which keeps a pristine block's own bytes and
    spares a re-run re-encoding a lossy decode of itself. When nothing moved and there is no art to
    draw, this is exactly the offset port.
    """
    width, height, fmt = _dimensions(graphic)
    if (fmt != "bc7" or not graphic["payload"].endswith(".blocks") or width % 4 or height % 4
            or astc_layout(len(mobile_raw), width, height) != (4, 4)):
        return None
    moves: list[tuple[tuple[int, ...], tuple[int, ...]]] = []
    for region in graphic["regions"]:
        pc, device = tuple(region["box"]), sprites.get(region.get("sprite", ""))
        if device is None or (device[2] - device[0], device[3] - device[1]) != (pc[2] - pc[0], pc[3] - pc[1]):
            return None
        moves.append((pc, tuple(device)))
    payload = payload_path(catalog, graphic["payload"]).read_bytes()
    labels, restorations = atlas_art(catalog, graphic["hash"], sprites)
    if all(pc == device for pc, device in moves) and not labels and not restorations:
        return _port_blocks(mobile_raw, graphic, payload)

    blocks_x, stride = width // 4, width * 4

    def block_of(x: int, y: int) -> int:
        """Raw-order block index of top-down pixel (x, y); textures are stored bottom-up."""
        return ((height - 1 - y) // 4) * blocks_x + x // 4

    def at(x: int, y: int) -> int:
        return (height - 1 - y) * stride + x * 4

    # The English pixels, decoded out of the payload's own runs, and the blocks those runs cover.
    english = bytearray(width * height * 4)
    damaged: set[int] = set()
    cursor = 0
    for offset, length in graphic["patch_ranges"]:
        first, count = offset // 16, length // 16
        strip = decode_pc(payload[cursor:cursor + length], count * 4, 4, "bc7")
        cursor += length
        raw_row, column = (first // blocks_x) * 4, (first % blocks_x) * 4
        for row in range(4):
            start = (raw_row + row) * stride + column * 4
            english[start:start + count * 16] = strip[row * count * 16:(row + 1) * count * 16]
        damaged.update(range(first, first + count))
    for pc, _device in moves:
        if any(block_of(x, y) not in damaged for y in range(pc[1], pc[3]) for x in range(pc[0], pc[2])):
            return None  # the payload does not carry this region's pixels; refuse rather than guess

    device_rgba = decode_astc(mobile_raw, width, height, 4, 4)
    target = bytearray(device_rgba)
    decided = bytearray(width * height)

    def put(x: int, y: int, source: bytes | bytearray, source_at: int) -> None:
        here = at(x, y)
        target[here:here + 4] = source[source_at:source_at + 4]
        decided[here // 4] = 1

    # 1. The old port's footprint: transparent, then every sprite in it from its restoration crop.
    for block in damaged:
        raw_row, column = (block // blocks_x) * 4, (block % blocks_x) * 4
        for row in range(raw_row, raw_row + 4):
            target[row * stride + column * 4:row * stride + column * 4 + 16] = bytes(16)
            decided[row * width + column:row * width + column + 4] = b"\1\1\1\1"
    owned = {region.get("sprite") for region in graphic["regions"]} | set(labels)
    for name, (x0, y0, x1, y1) in sprites.items():
        if name in owned:
            continue
        crop = restorations.get(name)
        inside = [(x, y) for y in range(y0, y1) for x in range(x0, x1) if block_of(x, y) in damaged]
        if not inside:
            continue
        if crop is not None and not _same_art(crop, device_rgba, (x0, y0, x1, y1), damaged, block_of, at):
            crop = None  # the device redrew this sprite since the crop was taken: never paint stale art
        for x, y in inside:
            if crop is None:
                here = at(x, y)
                target[here:here + 4] = device_rgba[here:here + 4]
                decided[here // 4] = 0
            else:
                put(x, y, crop, ((y - y0) * (x1 - x0) + x - x0) * 4)
    # 2. This repo's labels, then 3. the catalog's English, each over its whole device box.
    for name, pixels in labels.items():
        x0, y0, x1, y1 = sprites[name]
        for y in range(y0, y1):
            for x in range(x0, x1):
                put(x, y, pixels, ((y - y0) * (x1 - x0) + x - x0) * 4)
    for pc, device in moves:
        for dy in range(pc[3] - pc[1]):
            for dx in range(pc[2] - pc[0]):
                put(device[0] + dx, device[1] + dy, english, at(pc[0] + dx, pc[1] + dy))

    # Re-encode only the decided blocks whose pixels do not already show the target.
    touched = set(damaged)
    for x0, y0, x1, y1 in [sprites[name] for name in labels] + [device for _pc, device in moves]:
        touched.update(block_of(x, y) for y in range(y0, y1, 4) for x in range(x0, x1, 4))
        touched.update(block_of(x1 - 1, y) for y in range(y0, y1, 4))
        touched.update(block_of(x, y1 - 1) for x in range(x0, x1, 4))
        touched.add(block_of(x1 - 1, y1 - 1))
    stale = [block for block in sorted(touched)
             if _block_mismatch(target, device_rgba, decided, block, blocks_x, width) > BLOCK_MATCH_MEAN]
    if not stale:
        return mobile_raw
    out = bytearray(mobile_raw)
    rows: dict[int, list[int]] = {}
    for block in stale:
        rows.setdefault(block // blocks_x, []).append(block % blocks_x)
    for block_row, columns in rows.items():
        first, last = min(columns), max(columns) + 1
        strip = bytearray()
        for row in range(block_row * 4, block_row * 4 + 4):
            strip += target[row * stride + first * 16:row * stride + last * 16]
        encoded = encode_astc(bytes(strip), (last - first) * 4, 4, 4, 4)
        for column in columns:
            block = block_row * blocks_x + column
            out[block * 16:block * 16 + 16] = encoded[(column - first) * 16:(column - first + 1) * 16]
    return bytes(out)


def _block_mismatch(target: bytearray, device: bytes, decided: bytearray, block: int, blocks_x: int,
                    width: int) -> float:
    """Mean premultiplied difference between target and device over a block's decided pixels."""
    raw_row, column = (block // blocks_x) * 4, (block % blocks_x) * 4
    total = count = 0
    for row in range(raw_row, raw_row + 4):
        for x in range(column, column + 4):
            if decided[row * width + x]:
                total += _premultiplied_diff(target, device, (row * width + x) * 4)
                count += 1
    return total / count if count else 0.0


def _same_art(crop: bytes, device: bytes, box: tuple[int, int, int, int], damaged: set[int],
              block_of, at) -> bool:
    """Whether a restoration crop is still the device's art, judged where the old port never wrote."""
    x0, y0, x1, y1 = box
    total = count = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            if block_of(x, y) in damaged:
                continue
            crop_at, here = ((y - y0) * (x1 - x0) + x - x0) * 4, at(x, y)
            la, ra = crop[crop_at + 3], device[here + 3]
            total += max([abs(la - ra)] + [abs(crop[crop_at + c] * la - device[here + c] * ra) // 255
                                           for c in range(3)])
            count += 1
    return not count or total / count <= RESTORE_MATCH_MEAN


def english_raw(mobile_raw: bytes, graphic: dict, catalog: Path,
                sprites: dict[str, tuple[int, int, int, int]] | None = None) -> bytes | None:
    """Return the Android texture with the English edit applied, or None if unsupported.

    <sprites> is the device's own sprite table for a regioned atlas (``sprite_table.sprite_rects``).
    An atlas in ``REGION_SPRITE_ASSETS`` is refused without it: its PC offsets are not the device's.
    """
    width, height, fmt = _dimensions(graphic)
    if not width or not height or fmt not in PC_FORMATS:
        return None
    if int(graphic.get("hash") or "0", 16) in REGION_SPRITE_ASSETS:
        return port_atlas(mobile_raw, graphic, catalog, sprites) if sprites else None
    layout = astc_layout(len(mobile_raw), width, height)
    if layout is None:
        # The device revision is a different size from the catalog's record, so no block-for-block
        # mapping exists. A whole-image replacement can still land, by moving just its label across.
        if graphic["payload"].endswith(".assets"):
            return splice_label(mobile_raw, graphic, catalog, width, height, fmt)
        return None
    bx, by = layout
    # A non-English catalog ships only the images it re-draws; the rest are the English edits.
    payload = payload_path(catalog, graphic["payload"]).read_bytes()

    if graphic["payload"].endswith(".blocks") and fmt == "bc7" and layout == (4, 4):
        return _port_blocks(mobile_raw, graphic, payload)

    if graphic["payload"].endswith(".blocks"):
        if fmt != "rgba32":
            return None
        # Partial RGBA32 patch: paste the PC pixels onto the decoded image, then re-encode only the
        # ASTC blocks those pixels touch so the rest of the texture stays bit-identical.
        rgba = bytearray(decode_astc(mobile_raw, width, height, bx, by))
        touched: set[tuple[int, int]] = set()
        cursor = 0
        for offset, length in graphic["patch_ranges"]:
            rgba[offset:offset + length] = payload[cursor:cursor + length]
            cursor += length
            for pixel in range(offset // 4, (offset + length + 3) // 4):
                touched.add(((pixel % width) // bx, (pixel // width) // by))
        encoded = encode_astc(bytes(rgba), width, height, bx, by)
        blocks_x = math.ceil(width / bx)
        out = bytearray(mobile_raw)
        for block_x, block_y in touched:
            at = (block_y * blocks_x + block_x) * 16
            out[at:at + 16] = encoded[at:at + 16]
        return bytes(out)

    # Full replacement: rebuild the PC image, then re-encode it at the Android block footprint.
    return encode_astc(decode_pc(payload, width, height, fmt), width, height, bx, by)
