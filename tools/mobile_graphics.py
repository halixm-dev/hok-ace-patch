"""Port the catalog's English texture edits onto the Android ASTC textures.

The catalog payloads are PC-format data: BC7 (or raw RGBA32) blocks, sometimes a whole replacement
image and sometimes only the runs a Chinese label occupied. Android stores the same images as ASTC
inside Oodle-compressed chunks, so a payload can only be applied once the device texture has been
decompressed and its block footprint derived from the raw size.

Two payload families and four paths:

* a ``.blocks`` BC7 payload at the 4x4 footprint is ported block for block — BC7 and ASTC 4x4 both
  use 16-byte blocks on a 4x4 grid, so a PC byte range maps to the same byte range on the device;
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


def english_raw(mobile_raw: bytes, graphic: dict, catalog: Path) -> bytes | None:
    """Return the Android texture with the English edit applied, or None if unsupported."""
    width, height, fmt = _dimensions(graphic)
    if not width or not height or fmt not in PC_FORMATS:
        return None
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
        # Block-for-block port. Each range is a 16-byte-aligned run of BC7 blocks, which decode and
        # re-encode independently of where they sit in the image, so a run is handed to the codecs as
        # one <blocks*4>x4 strip and written back at the same offset.
        out = bytearray(mobile_raw)
        cursor = 0
        for offset, length in graphic["patch_ranges"]:
            row = payload[cursor:cursor + length]
            cursor += length
            blocks = length // 16
            rgba = decode_pc(row, blocks * 4, 4, "bc7")
            out[offset:offset + length] = encode_astc(rgba, blocks * 4, 4, 4, 4)
        return bytes(out)

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
