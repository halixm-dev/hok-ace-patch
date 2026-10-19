"""Render the patcher icon (icon.ico for the exe, icon.png for the window) from the Android launcher artwork."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "resources"
ARTWORK = ROOT / "android" / "app" / "src" / "main" / "res" / "drawable-nodpi" / "ic_launcher_artwork.png"
SIZE = 256
MARGIN = 0.04  # of the side, so the art nearly fills the tile as Windows icons do
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def render() -> Image.Image:
    # The Android icon draws this art inset on a white adaptive background; Windows icons are
    # transparent, so take the art alone, cropped to its own bounds and centred on a square.
    art = Image.open(ARTWORK).convert("RGBA")
    art = art.crop(art.getchannel("A").getbbox())
    inner = round(SIZE * (1 - 2 * MARGIN))
    scale = inner / max(art.size)
    art = art.resize((round(art.width * scale), round(art.height * scale)), Image.LANCZOS)
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    image.alpha_composite(art, ((SIZE - art.width) // 2, (SIZE - art.height) // 2))
    return image


def main() -> None:
    image = render()
    image.save(HERE / "icon.ico", sizes=ICO_SIZES)
    image.save(HERE / "icon.png")
    print("icon written")


if __name__ == "__main__":
    main()
