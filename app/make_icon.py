"""Render the patcher icon (icon.ico for the exe, icon.png for the window) with Pillow."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parents[1] / "resources"
SIZE = 1024
FONTS = Path("C:/Windows/Fonts")


def font(names: list[str], size: int) -> ImageFont.FreeTypeFont:
    for name in names:
        path = FONTS / name
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size)


def gradient(size: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    # Diagonal blend: build a small ramp and let the resize interpolate it smoothly.
    ramp = Image.new("RGB", (2, 2))
    ramp.putdata([top, tuple((a + b) // 2 for a, b in zip(top, bottom)),
                  tuple((a + b) // 2 for a, b in zip(top, bottom)), bottom])
    return ramp.resize((size, size), Image.BILINEAR)


def render() -> Image.Image:
    base = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle([40, 40, SIZE - 40, SIZE - 40], radius=220, fill=255)
    base.paste(gradient(SIZE, (40, 30, 92), (12, 16, 40)), (0, 0), mask)

    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse([230, 170, 794, 734], fill=(124, 92, 255, 150))
    base = Image.alpha_composite(base, Image.composite(glow.filter(ImageFilter.GaussianBlur(90)), Image.new("RGBA", base.size), mask))

    draw = ImageDraw.Draw(base)
    gold = (246, 196, 83)
    draw.ellipse([212, 152, 812, 752], outline=gold, width=34)
    for angle_box in ([212, 152, 812, 752],):
        draw.arc(angle_box, start=200, end=340, fill=(255, 230, 160), width=12)

    title = font(["segoeuib.ttf", "arialbd.ttf"], 300)
    draw.text((SIZE / 2, 452), "EN", font=title, fill=(255, 255, 255), anchor="mm")
    label = font(["segoeuib.ttf", "arialbd.ttf"], 118)
    draw.rounded_rectangle([190, 790, 834, 930], radius=70, fill=(246, 196, 83))
    draw.text((SIZE / 2, 860), "HOK ACE", font=label, fill=(28, 22, 64), anchor="mm")
    return base


def main() -> None:
    image = render()
    image.save(HERE / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    image.resize((256, 256), Image.LANCZOS).save(HERE / "icon.png")
    print("icon written")


if __name__ == "__main__":
    main()
