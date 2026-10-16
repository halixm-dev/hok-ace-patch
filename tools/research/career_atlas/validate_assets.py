r"""Check hand-finished Career-atlas art against the specs in art_brief.md, and render previews to judge it by eye.

Needs only Pillow (``pip install pillow``); runs anywhere, with or without the rest of the repo:

    python tools/research/career_atlas/validate_assets.py [--delivered tools/research/career_atlas/delivered]

Every PNG in --delivered named after a sprite in SPECS is checked. Prints PASS/FAIL per rule, writes
``preview_sheet.png`` (each delivery beside the current render and its style reference, at 1x and 4x on
the game's navy) and ``preview_in_context.png`` (the deliveries pasted into the ported atlas), and exits
non-zero on any failure. If ``astc_encoder`` and ``texture2ddecoder`` are importable it also previews
each delivery after the game's ASTC 4x4 round trip, which is how the phone will actually show it.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
NAVY = (38, 40, 62, 255)
BOXES = json.loads((HERE / "sprite_boxes.json").read_text())
CONTEXT_ORIGIN = (190, 100)  # context_atlas_after_port.png is the atlas cropped at this corner

# sprite -> (kind, text, style reference, the original it replaces)
SPECS = {
    "Image_410780920": ("label", "MY SKINS", "reference_english/my_chessplayers.png",
                        "originals/zh_Image_410780920_我的皮肤.png"),
    "Image_920603129": ("label", "TOTAL PROFIT", "reference_english/achievement_points.png",
                        "originals/zh_Image_920603129_总盈利.png"),
    "Image_1795213190": ("badge", "LOSS", None, "originals/zh_Image_1795213190_badge_失败.png"),
    "Image_1611657762": ("badge", "WIN", None, "originals/zh_Image_1611657762_badge_胜利.png"),
}
FAILURES: list[str] = []


def check(name: str, rule: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {rule}" + (f"  ({detail})" if detail else ""))
    if not ok:
        FAILURES.append(f"{name}: {rule}")


def size_of(sprite: str) -> tuple[int, int]:
    x0, y0, x1, y1 = BOXES[sprite]
    return x1 - x0, y1 - y0


def text_rows(image: Image.Image, threshold: int = 128) -> list[tuple[int, int]]:
    """Runs of rows holding ink (alpha above <threshold>): one run per line of text."""
    alpha = image.getchannel("A").load()
    inked = [any(alpha[x, y] > threshold for x in range(image.width)) for y in range(image.height)]
    runs, start = [], None
    for y, on in enumerate(inked + [False]):
        if on and start is None:
            start = y
        elif not on and start is not None:
            runs.append((start, y))
            start = None
    return runs


def check_label(name: str, image: Image.Image) -> None:
    px = list(image.get_flattened_data())
    tinted = sum(1 for r, g, b, a in px if a >= 30 and min(r, g, b) < 245)
    check(name, "glyphs are pure white (RGB >= 245 wherever alpha >= 30), the shape all in alpha",
          tinted == 0, f"{tinted} tinted pixels")
    edge = [image.getpixel((x, y))[3] for x in range(image.width) for y in (0, image.height - 1)]
    edge += [image.getpixel((x, y))[3] for y in range(image.height) for x in (0, image.width - 1)]
    check(name, "the outermost pixel ring is transparent (alpha <= 16)", max(edge) <= 16,
          f"max edge alpha {max(edge)}")
    runs = text_rows(image)
    heights = [b - a for a, b in runs if b - a >= 6]
    check(name, "two lines of text, each 14-17 px of solid ink (the catalog labels' cap height)",
          len(heights) == 2 and all(14 <= h <= 17 for h in heights), f"line heights {heights}")
    if name == "Image_410780920":
        # The Career switch shows MY SKINS and MY CHESSPLAYERS in one spot: the MY line must not move.
        # A few touched-up pixels are allowed (the user's 2026-10-10 polish filled two half-covered
        # joins of the M); a shifted or redrawn MY is not.
        mine = image.getchannel("A").crop((0, 0, image.width, 22)).tobytes()
        theirs = Image.open(HERE / "reference_english" / "my_chessplayers.png").convert("RGBA")
        theirs = theirs.getchannel("A").crop((0, 0, image.width, 22)).tobytes()
        touched = sum(1 for a, b in zip(mine, theirs) if a != b)
        check(name, "line 1 (MY, alpha rows 0-21) matches MY CHESSPLAYERS' (at most 10 touched pixels)",
              touched <= 10, f"{touched} pixels differ")
    coverage = sum(a for *_rgb, a in px) / 255 / len(px)
    check(name, "ink coverage 6-30 % (the catalog labels measure 8-26 %)", 0.06 <= coverage <= 0.30,
          f"{coverage:.1%}")


def check_badge(name: str, image: Image.Image, original: Image.Image) -> None:
    # The ring, its glow and the script subtitle must survive: compare everything outside the central
    # text band (the middle 70 % of width, rows 30..80 of 126) with the original.
    a, b = image.load(), original.load()
    total = count = 0
    for y in range(image.height):
        for x in range(image.width):
            if 18 <= x < 108 and 30 <= y < 80:
                continue
            total += max(abs(a[x, y][c] * a[x, y][3] - b[x, y][c] * b[x, y][3]) // 255 for c in range(3))
            total += abs(a[x, y][3] - b[x, y][3])
            count += 1
    mean = total / count
    check(name, "ring, glow and script subtitle unchanged outside the text band (mean diff <= 6)",
          mean <= 6, f"mean {mean:.2f}")
    corners = [image.getpixel(p)[3] for p in ((0, 0), (125, 0), (0, 125), (125, 125))]
    check(name, "corners stay transparent", max(corners) <= 16, f"corner alpha {corners}")


def astc_round_trip(image: Image.Image) -> Image.Image | None:
    try:
        import astc_encoder
        import texture2ddecoder
    except ImportError:
        return None
    w, h = image.size
    pw, ph = -(-w // 4) * 4, -(-h // 4) * 4
    padded = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    padded.paste(image, (0, 0))
    config = astc_encoder.ASTCConfig(astc_encoder.ASTCProfile.LDR, 4, 4, 1, 85)
    raw = astc_encoder.ASTCContext(config).compress(
        astc_encoder.ASTCImage(astc_encoder.ASTCType.U8, pw, ph, 1, padded.tobytes()),
        astc_encoder.ASTCSwizzle())
    bgra = texture2ddecoder.decode_astc(raw, pw, ph, 4, 4)
    return Image.frombytes("RGBA", (pw, ph), bgra, "raw", "BGRA").crop((0, 0, w, h))


def on_navy(image: Image.Image, scale: int) -> Image.Image:
    canvas = Image.new("RGBA", image.size, NAVY)
    canvas.alpha_composite(image)
    return canvas.resize((image.width * scale, image.height * scale), Image.NEAREST)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--delivered", type=Path, default=HERE / "delivered")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    found = {p.stem: p for p in args.delivered.rglob("Image_*.png") if p.stem in SPECS}
    if not found:
        print(f"no deliveries in {args.delivered} (expected files named {', '.join(SPECS)}.png)")
        return 1
    rows = []
    context = Image.open(HERE / "context_atlas_after_port.png").convert("RGBA")
    for name, path in sorted(found.items()):
        kind, text, reference, original_path = SPECS[name]
        print(f"{name} ({kind}, {text}) <- {path}")
        image = Image.open(path)
        check(name, "PNG in RGBA mode", image.format == "PNG" and image.mode == "RGBA",
              f"{image.format} {image.mode}")
        image = image.convert("RGBA")
        check(name, f"exactly {size_of(name)[0]}x{size_of(name)[1]} px", image.size == size_of(name),
              f"{image.size[0]}x{image.size[1]}")
        if image.size != size_of(name):
            continue
        original = Image.open(HERE / original_path).convert("RGBA")
        if kind == "label":
            check_label(name, image)
        else:
            check_badge(name, image, original)
        x0, y0, *_ = BOXES[name]
        spot = (x0 - CONTEXT_ORIGIN[0], y0 - CONTEXT_ORIGIN[1])
        context.paste(Image.new("RGBA", image.size, NAVY), spot)
        context.alpha_composite(image, spot)
        strip = [original, image]
        current = HERE / "current" / f"{name}.png"
        if current.exists():
            strip.append(Image.open(current).convert("RGBA"))
        if reference:
            strip.append(Image.open(HERE / reference).convert("RGBA"))
        trip = astc_round_trip(image)
        if trip is not None:
            strip.append(trip)
        rows.append(strip)
    scale = 4
    width = max(sum(i.width * scale + 12 for i in row) for row in rows)
    height = sum(max(i.height for i in row) * scale + 12 for row in rows)
    sheet = Image.new("RGBA", (width, height), (10, 10, 14, 255))
    y = 0
    for row in rows:
        x = 0
        for item in row:
            sheet.paste(on_navy(item, scale), (x, y))
            x += item.width * scale + 12
        y += max(i.height for i in row) * scale + 12
    sheet.save(HERE / "preview_sheet.png")
    context.save(HERE / "preview_in_context.png")
    print("\npreview_sheet.png: original | delivery | current render | style reference | after ASTC (if available)")
    print("preview_in_context.png: deliveries pasted into the ported Career atlas")
    if FAILURES:
        print(f"\nFAILED ({len(FAILURES)}):\n  " + "\n  ".join(FAILURES))
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
