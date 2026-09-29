"""Port the catalog's English texture edits onto the Android ASTC textures.

The catalog payloads are PC-format data: BC7 (or raw RGBA32) blocks, sometimes a whole replacement
image and sometimes only the runs a Chinese label occupied. Android stores the same images as ASTC
inside Oodle-compressed chunks, so a payload can only be applied once the device texture has been
decompressed and its block footprint derived from the raw size.

Two payload families and three paths:

* a ``.blocks`` BC7 payload at the 4x4 footprint is ported block for block — BC7 and ASTC 4x4 both
  use 16-byte blocks on a 4x4 grid, so a PC byte range maps to the same byte range on the device;
* a ``.blocks`` RGBA32 payload is pasted onto the decoded image and only the blocks it touches are
  re-encoded;
* a ``.assets`` payload replaces the whole image.

Nothing here raises for a texture it cannot handle: ``english_raw`` returns ``None`` and the caller
counts the texture as skipped. A silently skipped texture is far better than a failed patch run.
"""
from __future__ import annotations

import math
from pathlib import Path

import astc_encoder
import ooz
import texture2ddecoder

OODLE_BLOCK = 0x40000  # Oodle LZ streams are split into 256 KiB blocks
ASTC_FOOTPRINTS = [(4, 4), (5, 5), (6, 6), (8, 8), (10, 10), (12, 12)]
PC_FORMATS = ("bc7", "rgba32")

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

_contexts: dict[tuple[int, int], astc_encoder.ASTCContext] = {}


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
        return None
    bx, by = layout
    payload = (catalog / graphic["payload"]).read_bytes()

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
