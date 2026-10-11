"""Read the device's Sprite rectangles for a regioned atlas out of Tencent's modified Unity assets.

Package 19's UI atlases are Unity SpriteAtlases split over two QTS assets: one holds the Texture2D's
pixels (raw ASTC), another holds the Sprite objects plus the Texture2D header. Tencent's SerializedFile
header is modified and UnityPy cannot read it, but each Sprite record is still plain: a length-prefixed
``Image_<id>`` name, 4-byte aligned, then ``m_Rect`` as four little-endian floats (x, y, w, h) with y
measured from the **bottom** of the texture. That is all this reads.

The catalog's ``regions`` place each sprite at its **PC** atlas position, and the mobile build packs the
same sprites elsewhere (the Career atlas moved 11 of its 13), so the device table is a run-time input:
the layout has changed at least once already and is never hard-coded.
"""
from __future__ import annotations

import re
import struct

NAME = re.compile(rb"([\x0c-\x14])\x00\x00\x00(Image_\d{5,10})")

# Regioned catalog atlas -> the QTS asset holding its Sprite objects, both in package 19. Measured by
# finding the atlas's sprite names (from the prefabs that draw them) in the package; the pixel asset was
# then identified by decoding every candidate at 1024x1024 ASTC 4x4 and cropping a sprite rect.
REGION_SPRITE_ASSETS: dict[int, int] = {
    # CareerAtlas (UIResources/Career/Atlas/CareerAtlas): ported by sprite, device-verified 2026-10-10 on
    # the Career screen (Xiaomi M2007J3SG, Android 12, game data 1.5.0.1, session 20261010-151438).
    0x13C19E4E4486B31C: 0x4AA2B26FF28CB65D,
    0xC9F49510F2F67402: 0x22BD565B3703EDA9,  # lobby START GAME / BATTLE TRAINING
    0xE86DF43167CA2143: 0x9F240FDA0FA58988,  # CANCEL READY / CONFIRM CHOICE / WAITING FOR PLAYERS
}


def sprite_rects(raw: bytes, width: int, height: int | None = None) -> dict[str, tuple[int, int, int, int]]:
    """Sprite boxes ``(x0, y0, x1, y1)`` in top-down pixels, the convention of the catalog's ``regions``."""
    height = width if height is None else height
    rects: dict[str, tuple[int, int, int, int]] = {}
    for match in NAME.finditer(raw):
        name = match.group(2).decode()
        if match.group(1)[0] != len(match.group(2)) or name in rects:
            continue
        at = (match.end() + 3) & ~3
        if at + 16 > len(raw):
            continue
        x, y, w, h = struct.unpack_from("<4f", raw, at)
        if not (0 <= x < width and 0 <= y < height and 0 < w <= width and 0 < h <= height):
            continue  # a name reference (atlas tag, prefab field), not a Sprite record
        rects[name] = (int(x), int(height - y - h), int(x + w), int(height - y))
    return rects
