"""Inspect a regioned atlas's device sprite table and build this repo's art for it.

``mobile_graphics.port_atlas`` places each catalog region at the device's own sprite rect, read from the
package at run time (``sprite_table.sprite_rects``). It also draws two kinds of repo-owned art, kept in
``resources/sprites/<HASH>/``:

* ``restore/<sprite>.png`` -- a pristine crop of every sprite the old offset-for-offset port overwrote,
  so the blocks it damaged can be redrawn from data rather than from what the phone holds. A sprite
  qualifies when its device rect, in any of the layouts given, meets a block of the payload's
  ``patch_ranges`` and it is neither a catalog region nor a label this repo draws.
* ``labels/<sprite>.png`` -- English renders for sprites the catalog never translated
  (``mobile_graphics.ATLAS_LABELS``). The first drafts were assembled here from the catalog's own English
  glyphs, so they share the labels' face, size and alpha, with the letters no catalog label carries
  built from parts of the same face (K, L, R, F). The user then polished both by hand (2026-10-10,
  ``tools/research/career_atlas/edit/``), so the shipped PNGs are the source of truth: ``labels --out``
  drafts elsewhere and never writes over them. Check a changed label with
  ``tools/research/career_atlas/validate_assets.py --delivered <dir>``.
  The Secret Technique card titles (``SECRET_TITLES``, an atlas the catalog has no edit for) are font
  renders instead (``title_label``): the Chinese art is a black heavy sans with a grey semi-transparent
  edge, tinted gold by the card's material, so the render keeps that greyscale and lets the material
  colour it. They are set at one size, never squeezed, in boxes of their own, so the atlas's title
  sprites are re-packed: ``layout`` writes ``resources/sprites/<HASH>/layout.json``, which
  ``card_titles.relayout`` applies at run time (ADR 0009).

Subcommands, run by hand from the project root (``<pkg19>`` is a dump's ``WXQ_Data/Package/builtin/19``):

    .venv\\Scripts\\python.exe tools\\research\\atlas_sprites.py table --package <pkg19> [--out <dir>]
    .venv\\Scripts\\python.exe tools\\research\\atlas_sprites.py restore --pristine <pkg19> ^
        --layout <pkg19> [--layout <pkg19> ...] [--check]
    .venv\\Scripts\\python.exe tools\\research\\atlas_sprites.py layout --pristine <pkg19> [--check]
    .venv\\Scripts\\python.exe tools\\research\\atlas_sprites.py labels [--out <dir>] [--check]

``table`` prints every regioned atlas's catalog boxes beside the device rects and, with ``--out``,
writes ``<HASH>_rects.json`` and a render with the device rects (red) and the catalog boxes (yellow).
``restore`` crops from the ``--pristine`` dump, which must be a copy the patch never wrote to.
``layout`` packs the Secret Technique titles at their ``title_size`` around the art and records each card
prefab's ``Title`` box; it reads only a pristine package, and ``--check`` fails if the shipped file
differs. ``restore --check`` rebuilds the crops in memory and fails if the shipped PNGs' pixels differ;
``labels --check`` verifies each shipped label is in ``ATLAS_LABELS`` and in its atlas's format (RGBA,
transparent outer ring; Career labels white wherever visible, card titles grey wherever visible).
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.append(str(ROOT / "resources" / "runtime"))

import card_titles  # noqa: E402
import mobile_graphics as mg  # noqa: E402
import qts_relocate  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from sprite_table import REGION_SPRITE_ASSETS, sprite_rects  # noqa: E402

CATALOG = ROOT / "resources" / "catalog"
ART = ROOT / "resources" / mg.SPRITE_ART
CAREER = "13C19E4E4486B31C"
SECRET_TITLES = "0B4DA7A85D27E87A"  # LordSkillCardAtlas, the Secret Technique cards' titles
TITLE_FONT = ROOT / "resources" / "fonts" / "BarlowCondensed-ExtraBold.ttf"
# Measured on the 32 Chinese titles: black fill and a ~2 px edge, grey near (102, 99, 89) at alpha ~165.
# The edge is shaded, measured by distance from the ink (2026-11-11): a 1 px dark outline all round, a
# darker shade above each stroke and a light band 2-3 px below it, which the card's gold tint turns bright
# gold; the sides sit between. Layers, bottom up: ring, shade (shifted up), light (shifted down), outline.
TITLE_EDGE = (100, 96, 86, 60)        # the ring (the layers stack: these alphas are tuned to the sums)
TITLE_SHADE = (40, 38, 34, 100)       # above the ink, 2-3 px out (Chinese 37-65 at alpha 105-150)
TITLE_LIGHT = (225, 214, 188, 120)    # below the ink, 2-3 px out (Chinese 145-185 at alpha 115-155)
TITLE_OUTLINE = (82, 78, 72, 140)     # 1 px out on every side (Chinese 68-103 at alpha 180-234)
TITLE_STROKE = 2       # px of edge the layout keeps inside the box (TITLE_CLEAR beyond it)
TITLE_EDGE_REACH = 3   # px the drawn edge reaches: 1 px into TITLE_CLEAR, so the outer ring stays clear
TITLE_SHADE_SHIFT = 1  # px the shade and light copies are moved up and down, to TITLE_EDGE_REACH
TITLE_MARGIN = 4       # px of the box width the widest line leaves free (the Chinese leaves 2-3 a side)
TITLE_SCALE = 4        # drawn at 4x, then reduced with premultiplied alpha
TITLE_POINTS = 36      # one size for every title, never squeezed (the user's pick, 2026-11-11)
# Titles set on two lines, broken after the colon (the user's pick): at 36 pt on one line they are wider
# than the card (MAGICAL DEERIE: HEAVY ARMOR 424 px, the card about 400).
TWO_LINE_TITLES = ("MAGICAL DEERIE:", "GRACEFUL STEPS:")
TITLE_ART_GAP = 1      # px kept clear round the atlas's art sprites when the titles are packed
TITLE_LINE_GAP = 1     # px between two lines' capitals
TITLE_CLEAR = 2        # px left clear above and below the ink, so the outer ring stays transparent
# The bevelled titles (神奇小鹿·… and 心之引力): their edge is warmer, near (110, 101, 74) at alpha ~190, and
# each stroke's top carries a gold highlight (up to (183, 161, 91)) about 2 px deep.
BEVELLED_TITLES = {"Image_1758425074", "Image_1771257742", "Image_292161172", "Image_51264393",
                   "Image_640166584", "Image_13884294"}
TITLE_BEVEL_EDGE = (110, 101, 74, 70)
TITLE_BEVEL_SHADE = (50, 45, 30, 120)       # Chinese 44-53 at alpha 178-190
TITLE_BEVEL_LIGHT = (200, 185, 140, 110)    # Chinese 126-143 at alpha 150-194
TITLE_BEVEL_OUTLINE = (80, 71, 45, 150)     # Chinese 66-83 at alpha 228-243
TITLE_BEVEL_GOLD = (183, 158, 88, 255)
TITLE_BEVEL = 2.0


def graphics() -> dict[str, dict]:
    catalog = json.load(gzip.open(CATALOG / "catalog.json.gz"))
    return {g["hash"]: g for g in catalog["graphics"]}


def read_atlas(package_dir: Path, texture: str) -> tuple[Image.Image, dict[str, tuple[int, ...]]]:
    """The atlas decoded top-down, and its device sprite table."""
    from wxq_patch.qtsvfs import QtsPackage

    qts_relocate.install_btree_slot_map()
    package = QtsPackage(package_dir)
    slots = package.build_slot_map()
    raw = qts_relocate.read_raw(package, slots, int(texture, 16))
    graphic = graphics()[texture]
    width, height = int(graphic["width"]), int(graphic["height"])
    rects = sprite_rects(qts_relocate.read_raw(package, slots, REGION_SPRITE_ASSETS[int(texture, 16)]),
                         width, height)
    image = Image.frombytes("RGBA", (width, height), mg.decode_astc(raw, width, height, 4, 4))
    return image.transpose(Image.FLIP_TOP_BOTTOM), rects


def damaged_blocks(graphic: dict) -> set[tuple[int, int]]:
    """Top-down (block x, block y) of every 4x4 block the payload's patch_ranges write."""
    width, height = int(graphic["width"]), int(graphic["height"])
    blocks_x = width // 4
    found = set()
    for offset, length in graphic["patch_ranges"]:
        for block in range(offset // 16, (offset + length) // 16):
            found.add((block % blocks_x, height // 4 - 1 - block // blocks_x))
    return found


def overwritten(graphic: dict, rects: dict[str, tuple[int, ...]]) -> dict[str, int]:
    """Sprites (not regions, not labels) whose rect meets a patched block: name -> pixels hit."""
    blocks = damaged_blocks(graphic)
    owned = {r.get("sprite") for r in graphic["regions"]} | set(mg.ATLAS_LABELS.get(graphic["hash"], {}))
    hit = {}
    for name, (x0, y0, x1, y1) in rects.items():
        count = sum(1 for y in range(y0, y1) for x in range(x0, x1) if (x // 4, y // 4) in blocks)
        if count and name not in owned:
            hit[name] = count
    return hit


def cmd_table(args) -> int:
    for texture in [f"{h:016X}" for h in REGION_SPRITE_ASSETS if f"{h:016X}" in graphics()]:
        graphic = graphics()[texture]
        image, rects = read_atlas(args.package, texture)
        print(f"{texture}: {len(rects)} sprites")
        moved = 0
        for region in graphic["regions"]:
            device = rects.get(region["sprite"])
            state = "ABSENT" if device is None else "same" if tuple(region["box"]) == device else "MOVED"
            moved += state != "same"
            print(f"  {region['label']:26s} {region['sprite']:18s} catalog {tuple(region['box'])} "
                  f"device {device} {state}")
        hit = overwritten(graphic, rects)
        print(f"  {moved} of {len(graphic['regions'])} regions not at their catalog box; "
              f"{len(hit)} other sprites meet a patched block: "
              + ", ".join(f"{n} ({c} px)" for n, c in sorted(hit.items(), key=lambda i: -i[1])))
        if args.out:
            args.out.mkdir(parents=True, exist_ok=True)
            canvas = Image.new("RGBA", image.size, (40, 40, 60, 255))
            canvas.alpha_composite(image)
            draw = ImageDraw.Draw(canvas)
            for box in rects.values():
                draw.rectangle((box[0], box[1], box[2] - 1, box[3] - 1), outline=(255, 0, 0, 255))
            for region in graphic["regions"]:
                box = region["box"]
                draw.rectangle((box[0], box[1], box[2] - 1, box[3] - 1), outline=(255, 255, 0, 255), width=2)
            canvas.save(args.out / f"{texture}_rects.png")
            (args.out / f"{texture}_rects.json").write_text(json.dumps(rects, indent=1))
    return 0


def _same_pixels(path: Path, image: Image.Image) -> bool:
    if not path.exists():
        return False
    with Image.open(path) as shipped:
        return shipped.convert("RGBA").tobytes() == image.tobytes() and shipped.size == image.size


def cmd_restore(args) -> int:
    graphic = graphics()[CAREER]
    pristine, pristine_rects = read_atlas(args.pristine, CAREER)
    wanted: dict[str, int] = {}
    for layout in [args.pristine, *args.layout]:
        _image, rects = read_atlas(layout, CAREER)
        for name, count in overwritten(graphic, rects).items():
            wanted[name] = max(wanted.get(name, 0), count)
    target = ART / CAREER / "restore"
    stale = []
    for name in sorted(wanted):
        if name not in pristine_rects:
            print(f"  {name}: not in the pristine table, no crop")
            continue
        crop = pristine.crop(pristine_rects[name])
        if args.check:
            if not _same_pixels(target / f"{name}.png", crop):
                stale.append(name)
        else:
            target.mkdir(parents=True, exist_ok=True)
            crop.save(target / f"{name}.png")
        print(f"  {name} {crop.size[0]}x{crop.size[1]} (up to {wanted[name]} px overwritten)")
    extra = sorted(p.stem for p in target.glob("*.png") if p.stem not in wanted)
    if args.check:
        if stale or extra:
            print(f"FAILED: stale {stale}, unexpected {extra}")
            return 1
        print(f"restore crops current ({len(wanted)})")
    elif extra:
        print(f"note: {target} also holds {extra}, which no given layout needs")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    table = sub.add_parser("table")
    table.add_argument("--package", type=Path, required=True)
    table.add_argument("--out", type=Path)
    restore = sub.add_parser("restore")
    restore.add_argument("--pristine", type=Path, required=True)
    restore.add_argument("--layout", type=Path, action="append", default=[])
    restore.add_argument("--check", action="store_true")
    layout = sub.add_parser("layout")
    layout.add_argument("--pristine", type=Path, required=True)
    layout.add_argument("--check", action="store_true")
    labels = sub.add_parser("labels")
    labels.add_argument("--check", action="store_true")
    labels.add_argument("--out", type=Path, help="write fresh drafts here (never over the shipped art)")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    return {"table": cmd_table, "restore": cmd_restore, "layout": cmd_layout,
            "labels": cmd_labels}[args.command](args)


# ------------------------------------------------------------------------------------------------
# Label renders. The catalog's Career labels are white glyphs whose shape is all in alpha (RGB measures
# 254-255 wherever alpha >= 30), so a label is composed as an alpha mask and written white. The source
# face is the catalog's ACHIEVEMENT POINTS (cap height 16; MY CHESSPLAYERS is a pixel shorter, so the
# two are not mixed within a word). Its two lines sit 19.5 rows apart (tops at rows 5.3 and 24.8); a
# piece taken from line 1 moves down a whole 19 rather than being resampled, because the half-pixel
# shift measurably blurred every stem. Letters are set one clear column apart, as the source sets them.
# ------------------------------------------------------------------------------------------------
BAND = 21  # rows of one text line, in line-2 coordinates (source row 22 + i)


def english_region(label: str) -> Image.Image:
    """A Career region's English pixels, decoded out of the catalog payload at its PC box."""
    graphic = graphics()[CAREER]
    width, height = int(graphic["width"]), int(graphic["height"])
    payload = (CATALOG / graphic["payload"]).read_bytes()
    canvas = bytearray(width * height * 4)
    cursor = 0
    for offset, length in graphic["patch_ranges"]:
        first, count = offset // 16, length // 16
        strip = mg.decode_pc(payload[cursor:cursor + length], count * 4, 4, "bc7")
        cursor += length
        row0, column = (first // (width // 4)) * 4, (first % (width // 4)) * 4
        for row in range(4):
            start = ((row0 + row) * width + column) * 4
            canvas[start:start + count * 16] = strip[row * count * 16:(row + 1) * count * 16]
    image = Image.frombytes("RGBA", (width, height), bytes(canvas)).transpose(Image.FLIP_TOP_BOTTOM)
    box = next(r["box"] for r in graphic["regions"] if r["label"] == label)
    return image.crop(box)


LINE1_TOP = 3   # line-1 source row r stands on band row r - 3, line-2 row r on r - 22
LINE2_TOP = 22
STRONG = 120    # alpha above which a column counts as part of a letter for spacing


def _alpha(image: Image.Image, top: int, rows: int, x0: int, x1: int) -> list[list[int]]:
    alpha = image.getchannel("A").load()
    return [[alpha[x, y] if 0 <= y < image.height else 0 for x in range(x0, x1)]
            for y in range(top, top + rows)]


def _blank(width: int, rows: int = BAND) -> list[list[int]]:
    return [[0] * width for _ in range(rows)]


def _paste(target: list[list[int]], piece: list[list[int]], dx: int, rows: range | None = None) -> None:
    """Union <piece> into <target> at column <dx>; both are line-1 source rows from LINE1_TOP."""
    for i in rows if rows is not None else range(len(piece)):
        for j, value in enumerate(piece[i]):
            target[i][dx + j] = max(target[i][dx + j], value)


def glyphs() -> dict[str, list[list[int]]]:
    """The alpha of every letter MY SKINS and TOTAL PROFIT need, on line 2's band."""
    source = english_region("achievement_points")
    line2 = {ch: _alpha(source, LINE2_TOP, BAND, *cols)
             for ch, cols in {"P": (28, 39), "O": (39, 50), "I": (50, 56), "N": (56, 67),
                              "T": (67, 76), "S": (77, 87)}.items()}
    # Line 1 (ACHIEVEMENT) is edited in its own rows and only then moved onto line 2's baseline.
    raw = {name: _alpha(source, LINE1_TOP, BAND, *cols)
           for name, cols in {"A": (2, 14), "I": (34, 40), "E": (40, 49)}.items()}

    def rows(first: int, last: int) -> range:
        """Source line-1 rows first..last (inclusive) as indexes into a raw glyph."""
        return range(first - LINE1_TOP, last - LINE1_TOP + 1)

    # The I (source cols 34..39) and the E (40..48) put their stems at the same offset, cols 1..4.
    i_, e = raw["I"], raw["E"]
    # F: the E down to row 16, then the I's stem and foot instead of the lower arm.
    f = [e[k][:] if k < rows(17, 17)[0] else i_[k] + [0] * (len(e[k]) - len(i_[k])) for k in range(BAND)]
    # L: the I's head and stem down to row 16, then the E's stem and lower arm.
    l_ = [i_[k] + [0] * (len(e[k]) - len(i_[k])) if k < rows(17, 17)[0] else e[k][:] for k in range(BAND)]
    # The legs of K and R: A's right leg (source cols 8..13, rows 12..21) with its crossbar cut away.
    leg = _blank(6)
    _paste(leg, [row[6:12] for row in raw["A"]], 0, rows(12, 21))
    for k in rows(15, 16):
        leg[k][0] = 0
    # K: the I, the leg running down from the stem's right edge (glyph col 4) at mid-height, and the
    # leg mirrored top to bottom as the arm, so its foot serif becomes the arm's head serif. (V's own
    # arm was tried first: it climbs too steeply and reads as a second stem.)
    arm = _blank(6)
    for k in rows(5, 13):
        arm[k] = leg[26 - 2 * LINE1_TOP - k][:]  # source row r takes the leg's row 26 - r
    k_ = _blank(11)
    _paste(k_, i_, 0)
    _paste(k_, arm, 4)
    _paste(k_, leg, 4)
    # R: line 2's P with the leg dropping from its bowl, which closes on band rows 9-10 -- where the
    # leg (line-1 rows 12..21) starts.
    r = [row + [0] * 3 for row in line2["P"]]
    _paste(r, leg, 6)
    return {**line2, "A": raw["A"], "F": f, "L": l_, "K": k_, "R": r}


def _word(text: str, faces: dict[str, list[list[int]]]) -> list[list[int]]:
    """<text> set with one clear column between letters' solid columns; faint edges may overlap."""
    rows: list[list[int]] = [[0] * 2 for _ in range(BAND)]
    pen = 1
    for ch in text:
        glyph = faces[ch]
        solid = [j for j in range(len(glyph[0])) if any(row[j] > STRONG for row in glyph)]
        left = solid[0] if pen > 1 else 0
        for i in range(BAND):
            for j in range(left - 1 if left else 0, len(glyph[i])):
                x = pen + j - left
                while x >= len(rows[i]):
                    rows[i].append(0)
                rows[i][x] = max(rows[i][x], glyph[i][j])
        pen += solid[-1] - left + 2
    width = max(len(row) for row in rows)
    used = [j for j in range(width) if any(j < len(row) and row[j] > 8 for row in rows)]
    return [(row + [0] * width)[used[0]:used[-1] + 1] for row in rows]


def render_label(lines: list[tuple[str, int]], size: tuple[int, int], faces) -> Image.Image:
    """<lines> of (word, top row), each centred, white over the composed alpha."""
    alpha = Image.new("L", size, 0)
    for text, top in lines:
        word = _word(text, faces)
        left = (size[0] - len(word[0])) // 2
        for i, row in enumerate(word):
            for j, value in enumerate(row):
                if 0 <= top + i < size[1] and value:
                    alpha.putpixel((left + j, top + i), max(alpha.getpixel((left + j, top + i)), value))
    # Straight alpha, white everywhere: blending the colour toward black at partial alpha (as compositing
    # over a transparent-black canvas does) leaves a grey fringe on every antialiased edge in game.
    image = Image.new("RGBA", size, (255, 255, 255, 0))
    image.putalpha(alpha)
    return image


def labels() -> dict[str, Image.Image]:
    faces = glyphs()
    my = english_region("my_chessplayers")
    # MY SKINS keeps MY CHESSPLAYERS' first line exactly where it is, so the Career switch's two states
    # share it; SKINS takes the second line one row above where the source face stands it.
    skins = render_label([("SKINS", 21)], (117, 45), faces)
    skins.alpha_composite(my.crop((0, 0, 117, 22)), (0, 0))
    return {
        "Image_410780920": skins,
        "Image_920603129": render_label([("TOTAL", 1), ("PROFIT", 21)], (87, 45), faces),
    }


def _title_font() -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(TITLE_FONT), TITLE_POINTS * TITLE_SCALE)


def _two_lines(text: str) -> list[str]:
    """<text> broken after its colon, or else at the word break that best balances the two lines."""
    if ": " in text:
        head, tail = text.split(": ", 1)
        return [head + ":", tail]
    words = text.split()
    cut = min(range(1, len(words)), key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
    return [" ".join(words[:cut]), " ".join(words[cut:])]


def title_lines(text: str) -> list[str]:
    """The lines a title is set in: two for the hero-name titles (``TWO_LINE_TITLES``), else one."""
    return _two_lines(text) if text.startswith(TWO_LINE_TITLES) else [text]


def _up4(value: float) -> int:
    return (math.ceil(value) + 3) // 4 * 4


def title_size(text: str) -> tuple[int, int]:
    """The box a title needs at TITLE_POINTS, unsqueezed: its widest line plus TITLE_MARGIN, by a height
    every title of its line count shares (one line: the tallest title's ink; two: two capitals and the
    gap), plus TITLE_CLEAR above and below; both rounded up to the 4x4 block grid."""
    font, stroke = _title_font(), TITLE_STROKE * TITLE_SCALE

    def ink(line: str) -> tuple[int, int, int, int]:
        return font.getbbox(line, stroke_width=stroke)

    lines = title_lines(text)
    wide = max(ink(line)[2] - ink(line)[0] for line in lines) / TITLE_SCALE + TITLE_MARGIN
    if len(lines) == 1:
        tall = max(ink(t)[3] - ink(t)[1] for t in mg.ATLAS_LABELS[SECRET_TITLES].values()) // TITLE_SCALE
    else:
        cap = ink("H")
        tall = math.ceil((2 * (cap[3] - cap[1]) + TITLE_LINE_GAP * TITLE_SCALE) / TITLE_SCALE)
    return _up4(wide), _up4(tall + 2 * TITLE_CLEAR + 1)


def title_label(text: str, size: tuple[int, int], bevelled: bool = False) -> Image.Image:
    """A Secret Technique title in TITLE_FONT at TITLE_POINTS (``title_lines``), centred, black on a
    shaded edge; a <bevelled> title also takes the gold highlight its Chinese art has along each stroke's
    top. Never squeezed: a box narrower than the title raises."""
    lines = title_lines(text)
    width, height = size
    canvas = (width * TITLE_SCALE, height * TITLE_SCALE)
    stroke = TITLE_STROKE * TITLE_SCALE
    font = _title_font()
    wide = max(font.getbbox(line, stroke_width=stroke)[2] - font.getbbox(line, stroke_width=stroke)[0]
               for line in lines)
    if wide > (width - TITLE_MARGIN) * TITLE_SCALE:
        raise ValueError(f"{text!r} does not fit {width}x{height} at {TITLE_POINTS} pt")
    if len(lines) == 1:
        box = font.getbbox(text, stroke_width=stroke)
        places = [((canvas[0] - (box[2] - box[0])) // 2 - box[0], (canvas[1] - (box[3] - box[1])) // 2 - box[1])]
    else:
        cap = font.getbbox("H", stroke_width=stroke)
        pitch = cap[3] - cap[1] + TITLE_LINE_GAP * TITLE_SCALE
        top = (canvas[1] - (len(lines) * pitch - TITLE_LINE_GAP * TITLE_SCALE)) // 2 - cap[1]
        places = []
        for row, line in enumerate(lines):
            box = font.getbbox(line, stroke_width=stroke)
            places.append(((canvas[0] - (box[2] - box[0])) // 2 - box[0], top + row * pitch))
    def mask(width: int, shift: int = 0) -> Image.Image:
        """The lines stroked <width> px (at 1x) and moved <shift> px down."""
        out = Image.new("L", canvas, 0)
        for line, (x, y) in zip(lines, places):
            ImageDraw.Draw(out).text((x, y + shift * TITLE_SCALE), line, font=font, fill=255,
                                     stroke_width=width * TITLE_SCALE, stroke_fill=255)
        return out
    fill = mask(0)
    tones = ((TITLE_BEVEL_EDGE, TITLE_BEVEL_SHADE, TITLE_BEVEL_LIGHT, TITLE_BEVEL_OUTLINE) if bevelled
             else (TITLE_EDGE, TITLE_SHADE, TITLE_LIGHT, TITLE_OUTLINE))
    reach = TITLE_EDGE_REACH - TITLE_SHADE_SHIFT
    layers = (mask(TITLE_EDGE_REACH), mask(reach, -TITLE_SHADE_SHIFT), mask(reach, TITLE_SHADE_SHIFT), mask(1))
    image = Image.new("RGBA", canvas, tones[0][:3] + (0,))
    for tone, shape in zip(tones, layers):
        layer = Image.new("RGBA", canvas, tone[:3] + (255,))
        layer.putalpha(shape.point(lambda v, a=tone[3]: v * a // 255))
        image.alpha_composite(layer)
    black = Image.new("RGBA", canvas, (0, 0, 0, 255))
    black.putalpha(fill)
    image.alpha_composite(black)
    if bevelled:
        # The fill's top band: inside the glyph, but not inside it TITLE_BEVEL px further up.
        above = Image.new("L", canvas, 0)
        above.paste(fill, (0, round(TITLE_BEVEL * TITLE_SCALE)))
        band = Image.new("L", canvas, 0)
        band.paste(fill, (0, 0))
        band = Image.composite(Image.new("L", canvas, 0), band, above.point(lambda v: 255 if v > 127 else 0))
        gold = Image.new("RGBA", canvas, TITLE_BEVEL_GOLD)
        gold.putalpha(band)
        image.alpha_composite(gold)
    # Reduce premultiplied, so the transparent surround does not darken or lighten the edge.
    return image.convert("RGBa").resize(size, Image.LANCZOS).convert("RGBA")


def title_layout_file() -> Path:
    return ART / SECRET_TITLES / card_titles.LAYOUT_FILE


def title_sizes() -> dict[str, tuple[int, int]]:
    """Each title sprite's size in the shipped layout (``resources/sprites/<HASH>/layout.json``)."""
    titles = json.loads(title_layout_file().read_text(encoding="utf-8"))["titles"]
    return {name: (int(t["now"][2]), int(t["now"][3])) for name, t in titles.items()}


def drafts() -> dict[str, dict[str, Image.Image]]:
    """Fresh drafts of every label, by folder (``<atlas>/labels``) then sprite."""
    sizes = title_sizes()
    out = {f"{CAREER}/labels": labels(), f"{SECRET_TITLES}/labels": {}}
    for name, text in mg.ATLAS_LABELS[SECRET_TITLES].items():
        out[f"{SECRET_TITLES}/labels"][name] = title_label(text, sizes[name], name in BEVELLED_TITLES)
    return out


# Packing. Every title is one of two heights, so the titles are laid on shelves across the atlas, tall
# shelves first, through the gaps the art leaves (each art sprite inflated by TITLE_ART_GAP and rounded out
# to the block grid); on each shelf the widest title goes into the tightest gap that takes it. Titles sit
# edge to edge: each keeps its own transparent TITLE_CLEAR rim. MaxRects did not fit at full size.
TITLE_SPRITE_PATH = b"UIResources/CardComponent/LordSkillCard\x00"


def pack_titles(sizes: dict[str, tuple[int, int]], art: dict[str, list[float]], side: int
                ) -> dict[str, list[int]]:
    """Bottom-up ``[x, y, w, h]`` for each title of <sizes>, around the <art> rects, or raise."""
    def down4(v: float) -> int:
        return int(v) // 4 * 4

    obstacles = [(down4(x - TITLE_ART_GAP), down4(y - TITLE_ART_GAP),
                  _up4(x + w + TITLE_ART_GAP), _up4(y + h + TITLE_ART_GAP)) for x, y, w, h in art.values()]

    def gaps_at(y: int, h: int) -> list[list[int]]:
        cuts = sorted((x0, x1) for x0, y0, x1, y1 in obstacles if y0 < y + h and y1 > y)
        found, x = [], 0
        for x0, x1 in cuts + [(side, side)]:
            if x0 - x >= 40:
                found.append([x, y, x0 - x])
            x = max(x, x1)
        return found

    placed: dict[str, list[int]] = {}
    y = 0
    for h in sorted({h for _w, h in sizes.values()}, reverse=True):
        todo = sorted((n for n, (_w, hh) in sizes.items() if hh == h), key=lambda n: (-sizes[n][0], n))
        gaps: list[list[int]] = []
        while todo:
            if y + h > side:
                raise ValueError(f"{len(todo)} titles left over: the atlas is full")
            gaps += gaps_at(y, h)
            y += h
            left = []
            for name in todo:
                w = sizes[name][0]
                fits = [g for g in gaps if g[2] >= w]
                if not fits:
                    left.append(name)
                    continue
                gap = min(fits, key=lambda g: (g[2] - w, g[1], g[0]))
                placed[name] = [gap[0], gap[1], w, h]
                gap[0] += w
                gap[2] -= w
            todo = left
    return placed


def title_boxes(package, slots, skip: set[int]) -> tuple[dict[str, dict], list[str]]:
    """Each card prefab's ``Title`` RectTransform, by prefab hash: path id, sprite, pristine size. A
    prefab naming more than one title (the shared template) is listed apart and left alone."""
    import struct

    from unity_text import SerializedFile, UnsupportedFile

    titles = set(mg.ATLAS_LABELS[SECRET_TITLES])
    boxes, shared = {}, []
    for file_hash in sorted(package.entries):
        if file_hash in skip:
            continue
        try:
            raw = qts_relocate.read_raw(package, slots, file_hash)
        except Exception:  # noqa: BLE001 -- an unreadable asset is not a card prefab
            continue
        if not raw or TITLE_SPRITE_PATH not in raw:
            continue
        try:
            parsed = SerializedFile(raw)
        except UnsupportedFile:
            continue
        frames, uses = {}, []
        for _pos, path_id, start, size, type_index in parsed.objects:
            obj = raw[parsed.data_offset + start:parsed.data_offset + start + size]
            kind = parsed.class_ids[type_index]
            if kind not in (card_titles.RECT_TRANSFORM_CLASS, 114):
                continue
            owner = struct.unpack_from("<iq", obj, 0)[1]
            if kind == card_titles.RECT_TRANSFORM_CLASS:
                at = card_titles._rect_size_at(obj)
                frames[owner] = (path_id, list(struct.unpack_from("<2f", obj, at)))
                continue
            at = obj.find(TITLE_SPRITE_PATH)
            while at >= 0:
                name_at = (at + len(TITLE_SPRITE_PATH) + 3) & ~3
                length = struct.unpack_from("<i", obj, name_at)[0]
                sprite = obj[name_at + 4:name_at + 4 + length].decode(errors="replace")
                if sprite in titles:
                    uses.append((owner, sprite))
                at = obj.find(TITLE_SPRITE_PATH, at + 1)
        if len(uses) > 1:
            shared.append(f"{file_hash:016X}")
        elif uses:
            owner, sprite = uses[0]
            path_id, size = frames[owner]
            boxes[f"{file_hash:016X}"] = {"path_id": path_id, "sprite": sprite, "was": size}
    return boxes, shared


def make_layout(package_dir: Path) -> dict:
    """The title layout from a pristine package 19: art rects, each title's pristine and new rect, the
    card prefabs' Title boxes."""
    import struct

    from wxq_patch.qtsvfs import QtsPackage

    qts_relocate.install_btree_slot_map()
    package = QtsPackage(package_dir)
    slots = package.build_slot_map()
    table_hash = REGION_SPRITE_ASSETS[int(SECRET_TITLES, 16)]
    table = qts_relocate.read_raw(package, slots, table_hash)
    titles = mg.ATLAS_LABELS[SECRET_TITLES]
    key = struct.pack("<i", len(next(iter(titles)))) + next(iter(titles)).encode()
    index_hash = next(h for h in sorted(package.entries) if h not in (table_hash, int(SECRET_TITLES, 16))
                      and b"LordSkillCardAtlas" in (raw := qts_relocate.read_raw(package, slots, h) or b"")
                      and key in raw)
    rects = {}
    for _path_id, start, size in card_titles._objects(table, card_titles.SPRITE_CLASS):
        name, _at, rect = card_titles.sprite_fields(table[start:start + size])
        rects[name] = [float(v) for v in rect]
    art = {n: r for n, r in sorted(rects.items()) if n not in titles}
    side = mg.LABEL_ATLASES[int(SECRET_TITLES, 16)][0]
    now = pack_titles({n: title_size(t) for n, t in titles.items()}, art, side)
    boxes, shared = title_boxes(package, slots, {int(SECRET_TITLES, 16), table_hash, index_hash})
    return {
        "atlas": SECRET_TITLES,
        "sprite_table": f"{table_hash:016X}",
        "timi_atlas": f"{index_hash:016X}",
        "points": TITLE_POINTS,
        "art": art,
        "titles": {n: {"text": titles[n], "was": rects[n], "now": [float(v) for v in now[n]]}
                   for n in sorted(titles)},
        "boxes": boxes,
        "shared_left_alone": shared,
    }


def cmd_layout(args) -> int:
    """Write (or ``--check``) resources/sprites/<HASH>/layout.json from a pristine package 19."""
    layout = make_layout(args.pristine)
    text = json.dumps(layout, indent=1, ensure_ascii=False) + "\n"
    path = title_layout_file()
    print(f"  {len(layout['titles'])} titles, {len(layout['art'])} art sprites, {len(layout['boxes'])} card "
          f"boxes, {len(layout['shared_left_alone'])} shared prefab(s) left alone")
    if args.check:
        current = path.is_file() and path.read_text(encoding="utf-8") == text
        print("layout current" if current else f"FAILED: {path} differs from a fresh layout")
        return 0 if current else 1
    path.write_text(text, encoding="utf-8")
    print(f"wrote {path}")
    return 0


def _label_faults(image: Image.Image, atlas: str) -> list[str]:
    """What keeps <image> from being a shippable label: the format its atlas's labels share."""
    faults = []
    if image.mode != "RGBA":
        faults.append(f"mode {image.mode}, not RGBA")
        image = image.convert("RGBA")
    pixels = [p for p in image.get_flattened_data() if p[3] >= 30]
    if atlas == CAREER:
        tinted = sum(1 for r, g, b, _a in pixels if min(r, g, b) < 245)
        if tinted:
            faults.append(f"{tinted} tinted pixels (labels are white, shaped by alpha)")
    else:
        solid = [p for p in pixels if p[3] >= 240]
        black = sum(1 for r, g, b, _a in solid if max(r, g, b) < 50) / max(1, len(solid))
        if black < 0.6:
            faults.append(f"{black:.0%} of the solid pixels black (a title is black with an edge; the Chinese "
                          "art measures 66-95 %)")
    w, h = image.size
    edge = max(image.getpixel((x, y))[3] for x in range(w) for y in range(h) if x in (0, w - 1) or y in (0, h - 1))
    if edge > 16:
        faults.append(f"outermost ring not transparent (alpha {edge})")
    return faults


def cmd_labels(args) -> int:
    """Shipped labels are hand-finished art (LABELS_PROVENANCE): draft into --out, verify with --check.

    The glyph assembly above made the first drafts; the shipped PNGs were then polished by hand, so they
    are the source of truth and are never regenerated over. ``--out`` writes fresh drafts to start a new
    label from; ``--check`` verifies every shipped label is in ATLAS_LABELS and in the labels' format.
    """
    if args.out:
        for folder, images in drafts().items():
            (args.out / folder).mkdir(parents=True, exist_ok=True)
            for name, image in images.items():
                image.save(args.out / folder / f"{name}.png")
                print(f"  draft {folder}/{name} {image.size[0]}x{image.size[1]}: {mg.ATLAS_LABELS[folder.split('/')[0]].get(name)}")
    if not args.check:
        return 0
    failed = False
    folders = {f"{atlas}/labels" for atlas in mg.ATLAS_LABELS}
    folders |= {f"{p.parent.parent.name}/{p.parent.name}" for p in ART.glob("*/labels*/Image_*.png")}
    for folder in sorted(folders):
        atlas, kind = folder.split("/")
        wording = mg.ATLAS_LABELS.get(atlas, {}) if kind == "labels" else {}
        shipped = {p.stem: p for p in (ART / folder).glob("Image_*.png")}
        for name in sorted(set(shipped) | set(wording)):
            if name not in shipped or name not in wording:
                print(f"  FAIL {folder}/{name}: {'no PNG' if name not in shipped else 'no wording for it'}")
                failed = True
                continue
            with Image.open(shipped[name]) as image:
                faults = _label_faults(image, folder.split("/")[0])
                print(f"  {'FAIL' if faults else 'ok  '} {folder}/{name} {image.size[0]}x{image.size[1]}: "
                      f"{wording[name]}" + (f" -- {'; '.join(faults)}" if faults else ""))
            failed |= bool(faults)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
