"""Re-lay the Secret Technique card titles in LordSkillCardAtlas, so each English title gets its own box.

The Chinese titles are sprites sized to the Chinese (mostly 160-312 x 44). The English titles are set at
one size for all (36 pt, no sideways squeeze; the five MAGICAL DEERIE and five GRACEFUL STEPS titles on
two lines), so each needs a box of its own size, and the atlas is re-packed to hold them. The new places
are this repo's data, ``resources/sprites/<HASH>/layout.json``, made from a pristine layer by
``tools/research/atlas_sprites.py layout``. Moving a sprite changes three kinds of asset besides the
atlas's pixels, all in package 19 (ADR 0009):

* the Sprite table (``sprite_table.REGION_SPRITE_ASSETS``): each title Sprite's ``m_Rect``, its four
  vertex positions, ``textureRect`` and ``uvTransform``;
* the TimiAtlas, Tencent's own index of the same sprites: each title's rect and pixel pivot;
* each Secret Technique card prefab: the ``Title`` RectTransform's ``sizeDelta``, which the card draws
  the sprite at, set to the new sprite size. The shared template prefab ``UICardLordSkill_Secret`` sets
  one 196x44 box for all 32 titles and is left alone.

Every edit is a float written in place, so no asset changes length. ``relayout`` refuses (returns None)
unless every art sprite sits at its recorded rect, every title at its pristine rect or its new one, and
every card's ``Title`` box at its pristine size or its new one: a later layout is reported as skipped
instead of drawn wrong. The labels are drawn at the sprites' sizes (``mobile_graphics.label_atlas``), so a
refused relayout also refuses the atlas: the titles stay Chinese together, never half moved.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Callable

TITLE_ATLAS = 0x0B4DA7A85D27E87A  # UIResources/CardComponent/LordSkillCard/Atlas/LordSkillCardAtlas
LAYOUT_FILE = "layout.json"
SPRITE_CLASS = 213
RECT_TRANSFORM_CLASS = 224
PIXELS_PER_UNIT = 100.0  # every sprite of this atlas; the vertices are the rect in units about the pivot


def load_layout(catalog_dir: Path) -> dict | None:
    """The shipped title layout beside the catalogs (``resources/sprites/<HASH>/layout.json``), or None."""
    from mobile_graphics import SPRITE_ART

    path = Path(catalog_dir).parent / SPRITE_ART / f"{TITLE_ATLAS:016X}" / LAYOUT_FILE
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


class _Reader:
    """Little-endian reads over one serialized Unity object."""

    def __init__(self, data: bytes) -> None:
        self.data, self.at = data, 0

    def take(self, fmt: str) -> tuple:
        values = struct.unpack_from("<" + fmt, self.data, self.at)
        self.at += struct.calcsize("<" + fmt)
        return values

    def align(self) -> None:
        self.at = (self.at + 3) & ~3

    def string(self) -> str:
        (length,) = self.take("i")
        text = self.data[self.at:self.at + length].decode("utf-8", "replace")
        self.at += length
        self.align()
        return text

    def skip_bytes(self) -> int:
        """Skip a length-prefixed byte array; return where its bytes start."""
        (length,) = self.take("i")
        start = self.at
        self.at += length
        self.align()
        return start


def sprite_fields(obj: bytes) -> tuple[str, dict[str, int], tuple[float, ...]]:
    """A Unity 2022 Sprite's name, the offsets of the fields a move rewrites, and its ``m_Rect``.

    Offsets are within the object: ``rect`` (4 floats), ``vertices`` (4 xyz positions), ``texture_rect``
    (4 floats) and ``uv_transform`` (4 floats, ``textureRect`` + 36 bytes).
    """
    r = _Reader(obj)
    name = r.string()
    at = {"rect": r.at}
    rect = r.take("4f")
    r.take("2f4ff2fI")  # offset, border, pixelsToUnits, pivot, extrude
    r.at += 1           # isPolygon
    r.align()
    r.at += 24          # render data key
    for _ in range(r.take("i")[0]):
        r.string()      # atlas tags
    r.take("iq")        # sprite atlas
    r.take("iqiq")      # texture, alpha texture
    for _ in range(r.take("i")[0]):
        r.take("iq")
        r.string()      # secondary textures
    (submeshes,) = r.take("i")
    r.at += submeshes * 48
    r.skip_bytes()      # index buffer
    (vertices,) = r.take("I")
    (channels,) = r.take("i")
    r.at += channels * 4
    data_at = r.skip_bytes()
    if vertices != 4 or r.at - data_at < 4 * 12:
        raise ValueError(f"{name}: {vertices} vertices, not the quad a move rewrites")
    at["vertices"] = data_at
    (bind_poses,) = r.take("i")
    r.at += 64 * bind_poses
    at["texture_rect"] = r.at
    at["uv_transform"] = r.at + 36
    return name, at, rect


def _objects(raw: bytes, class_id: int):
    """``(path_id, start, size)`` of every object of <class_id> in a serialized file."""
    from unity_text import SerializedFile

    parsed = SerializedFile(raw)
    for _pos, path_id, start, size, type_index in parsed.objects:
        if parsed.class_ids[type_index] == class_id:
            yield path_id, parsed.data_offset + start, size


def _rect_size_at(obj: bytes) -> int:
    """Offset of a RectTransform's ``sizeDelta`` (2 floats) within the object."""
    at = 12 + 16 + 12 + 12  # GameObject, rotation, position, scale
    (children,) = struct.unpack_from("<i", obj, at)
    return at + 4 + 12 * children + 12 + 24  # father, then anchorMin, anchorMax, anchoredPosition


def _move_sprites(table: bytes, layout: dict) -> bytes | None:
    titles, art = layout["titles"], layout["art"]
    out = bytearray(table)
    seen = set()
    for _path_id, start, size in _objects(table, SPRITE_CLASS):
        name, at, rect = sprite_fields(table[start:start + size])
        if name in art:
            if list(rect) != art[name]:
                return None
            seen.add(name)
            continue
        if name not in titles or list(rect) not in (titles[name]["was"], titles[name]["now"]):
            return None
        x, y, w, h = titles[name]["now"]
        half_w, half_h = w / 2 / PIXELS_PER_UNIT, h / 2 / PIXELS_PER_UNIT
        struct.pack_into("<4f", out, start + at["rect"], x, y, w, h)
        struct.pack_into("<12f", out, start + at["vertices"], -half_w, half_h, 0, half_w, half_h, 0,
                         -half_w, -half_h, 0, half_w, -half_h, 0)
        struct.pack_into("<4f", out, start + at["texture_rect"], x, y, w, h)
        struct.pack_into("<4f", out, start + at["uv_transform"],
                         PIXELS_PER_UNIT, x + w / 2, PIXELS_PER_UNIT, y + h / 2)
        seen.add(name)
    return bytes(out) if seen == set(titles) | set(art) else None


def _move_index(index: bytes, layout: dict) -> bytes | None:
    """The TimiAtlas: each name, 4-aligned, then rect (x, y, w, h), border (4), pivot in pixels (2)."""
    out = bytearray(index)
    for name, title in layout["titles"].items():
        key = struct.pack("<i", len(name)) + name.encode()
        if index.count(key) != 1:
            return None
        at = (index.index(key) + len(key) + 3) & ~3
        rect = list(struct.unpack_from("<4f", index, at))
        pivot = struct.unpack_from("<2f", index, at + 32)
        if rect not in (title["was"], title["now"]) or pivot != (rect[2] / 2, rect[3] / 2):
            return None
        x, y, w, h = title["now"]
        struct.pack_into("<4f", out, at, x, y, w, h)
        struct.pack_into("<2f", out, at + 32, w / 2, h / 2)
    return bytes(out)


def _move_box(prefab: bytes, box: dict, size: tuple[float, float]) -> bytes | None:
    for path_id, start, length in _objects(prefab, RECT_TRANSFORM_CLASS):
        if path_id != box["path_id"]:
            continue
        at = start + _rect_size_at(prefab[start:start + length])
        if list(struct.unpack_from("<2f", prefab, at)) not in (box["was"], list(size)):
            return None
        out = bytearray(prefab)
        struct.pack_into("<2f", out, at, *size)
        return bytes(out)
    return None


def _guarded(move, *args) -> bytes | None:
    """<move>'s result, or None when the asset does not parse as the layout expects."""
    from unity_text import UnsupportedFile

    try:
        return move(*args)
    except (UnsupportedFile, ValueError, struct.error):
        return None


def relayout(read: Callable[[int], bytes | None], layout: dict) -> dict[int, bytes] | None:
    """New raw bytes for every asset the layout changes, by hash (empty when all already match), or None.

    <read> returns an asset's raw bytes from the package being patched, or None if it lacks it.
    """
    jobs: dict[int, bytes] = {}
    sources = {int(layout["sprite_table"], 16): _move_sprites, int(layout["timi_atlas"], 16): _move_index}
    for asset, move in sources.items():
        raw = read(asset)
        new = _guarded(move, raw, layout) if raw else None
        if new is None:
            return None
        if new != raw:
            jobs[asset] = new
    for asset, box in layout["boxes"].items():
        raw = read(int(asset, 16))
        _x, _y, w, h = layout["titles"][box["sprite"]]["now"]
        new = _guarded(_move_box, raw, box, (w, h)) if raw else None
        if new is None:
            return None
        if new != raw:
            jobs[int(asset, 16)] = new
    return jobs
