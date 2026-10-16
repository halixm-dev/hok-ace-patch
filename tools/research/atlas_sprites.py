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

Subcommands, run by hand from the project root (``<pkg19>`` is a dump's ``WXQ_Data/Package/builtin/19``):

    .venv\\Scripts\\python.exe tools\\research\\atlas_sprites.py table --package <pkg19> [--out <dir>]
    .venv\\Scripts\\python.exe tools\\research\\atlas_sprites.py restore --pristine <pkg19> ^
        --layout <pkg19> [--layout <pkg19> ...] [--check]
    .venv\\Scripts\\python.exe tools\\research\\atlas_sprites.py labels [--out <dir>] [--check]

``table`` prints every regioned atlas's catalog boxes beside the device rects and, with ``--out``,
writes ``<HASH>_rects.json`` and a render with the device rects (red) and the catalog boxes (yellow).
``restore`` crops from the ``--pristine`` dump, which must be a copy the patch never wrote to.
``restore --check`` rebuilds the crops in memory and fails if the shipped PNGs' pixels differ;
``labels --check`` verifies each shipped label is in ``ATLAS_LABELS`` and in the labels' format (RGBA,
white wherever it is visible, transparent outer ring).
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.append(str(ROOT / "resources" / "runtime"))

import mobile_graphics as mg  # noqa: E402
import qts_relocate  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402
from sprite_table import REGION_SPRITE_ASSETS, sprite_rects  # noqa: E402

CATALOG = ROOT / "resources" / "catalog"
ART = ROOT / "resources" / mg.SPRITE_ART
CAREER = "13C19E4E4486B31C"


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
    for texture in [f"{h:016X}" for h in REGION_SPRITE_ASSETS]:
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
    labels = sub.add_parser("labels")
    labels.add_argument("--check", action="store_true")
    labels.add_argument("--out", type=Path, help="write glyph-assembled drafts here (never over the shipped art)")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    return {"table": cmd_table, "restore": cmd_restore, "labels": cmd_labels}[args.command](args)


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


def _label_faults(image: Image.Image) -> list[str]:
    """What keeps <image> from being a shippable label: the format the catalog's own labels share."""
    faults = []
    if image.mode != "RGBA":
        faults.append(f"mode {image.mode}, not RGBA")
        image = image.convert("RGBA")
    tinted = sum(1 for r, g, b, a in image.get_flattened_data() if a >= 30 and min(r, g, b) < 245)
    if tinted:
        faults.append(f"{tinted} tinted pixels (labels are white, shaped by alpha)")
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
    target = ART / CAREER / "labels"
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        for name, image in labels().items():
            image.save(args.out / f"{name}.png")
            print(f"  draft {name} {image.size[0]}x{image.size[1]}: {mg.ATLAS_LABELS[CAREER][name]}")
    if not args.check:
        return 0
    failed = False
    shipped = {p.stem: p for p in target.glob("Image_*.png")}
    for name in sorted(set(shipped) | set(mg.ATLAS_LABELS[CAREER])):
        if name not in shipped or name not in mg.ATLAS_LABELS[CAREER]:
            print(f"  FAIL {name}: {'no PNG' if name not in shipped else 'not in ATLAS_LABELS'}")
            failed = True
            continue
        with Image.open(shipped[name]) as image:
            faults = _label_faults(image)
            print(f"  {'FAIL' if faults else 'ok  '} {name} {image.size[0]}x{image.size[1]}: "
                  f"{mg.ATLAS_LABELS[CAREER][name]}" + (f" -- {'; '.join(faults)}" if faults else ""))
        failed |= bool(faults)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
