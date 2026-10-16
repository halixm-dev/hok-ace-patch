r"""Build the Career-atlas reference pack: the crops and previews ``art_brief.md`` points at.

Run from the project root:  .venv\Scripts\python.exe tools\research\career_atlas\build_reference_pack.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "research"))
sys.path.append(str(ROOT / "resources" / "runtime"))

import atlas_sprites as A  # noqa: E402
import mobile_graphics as mg  # noqa: E402
import qts_relocate  # noqa: E402
from PIL import Image  # noqa: E402
from sprite_table import sprite_rects  # noqa: E402
from wxq_patch.qtsvfs import QtsPackage  # noqa: E402

OUT = Path(__file__).resolve().parent
DATA = ROOT / "dist" / "HOK ACE Patcher Data"
TODAY = DATA / "sessions" / "20261010-115042" / "game" / "WXQ_Data" / "Package" / "builtin" / "19"
PRISTINE = DATA / "pristine" / "20261003-173730" / "game" / "WXQ_Data" / "Package" / "builtin" / "19"
BG = (38, 40, 62, 255)  # the Career panel's navy, sampled behind the labels


def on_bg(image: Image.Image, scale: int) -> Image.Image:
    canvas = Image.new("RGBA", image.size, BG)
    canvas.alpha_composite(image)
    return canvas.resize((image.width * scale, image.height * scale), Image.NEAREST)


def save(image: Image.Image, folder: str, name: str) -> None:
    (OUT / folder).mkdir(parents=True, exist_ok=True)
    image.save(OUT / folder / f"{name}.png")
    on_bg(image, 8).save(OUT / folder / f"{name}@8x_on_navy.png")


def main() -> None:
    # The catalog's own English labels: the style to match.
    for label in ("my_chessplayers", "achievement_points", "total_achievement_points", "glory_gold",
                  "strongest_king", "total_power"):
        save(A.english_region(label), "reference_english", label)
    # The Chinese originals the new labels replace, and the two badges, from the pristine 10-03 atlas.
    pristine, pristine_rects = A.read_atlas(PRISTINE, A.CAREER)
    for sprite, name in (("Image_410780920", "zh_Image_410780920_我的皮肤"),
                         ("Image_920603129", "zh_Image_920603129_总盈利"),
                         ("Image_1795213190", "zh_Image_1795213190_badge_失败"),
                         ("Image_1611657762", "zh_Image_1611657762_badge_胜利")):
        save(pristine.crop(pristine_rects[sprite]), "originals", name)
    # What ships today.
    for path in sorted((A.ART / A.CAREER / "labels").glob("*.png")):
        save(Image.open(path).convert("RGBA"), "current", path.stem)
    # The whole ported atlas, for context.
    qts_relocate.install_btree_slot_map()
    package = QtsPackage(TODAY)
    slots = package.build_slot_map()
    raw = qts_relocate.read_raw(package, slots, int(A.CAREER, 16))
    rects = sprite_rects(qts_relocate.read_raw(package, slots, 0x4AA2B26FF28CB65D), 1024, 1024)
    graphic = A.graphics()[A.CAREER]
    new = mg.english_raw(raw, graphic, A.CATALOG, rects)
    atlas = Image.frombytes("RGBA", (1024, 1024), mg.decode_astc(new, 1024, 1024, 4, 4))
    atlas = atlas.transpose(Image.FLIP_TOP_BOTTOM)
    on_bg(atlas.crop((190, 100, 1024, 460)), 1).save(OUT / "context_atlas_after_port.png")
    (OUT / "sprite_boxes.json").write_text(json.dumps(
        {name: rects[name] for name in ("Image_410780920", "Image_920603129", "Image_1795213190",
                                         "Image_1611657762")}, indent=1))
    print(f"reference pack written to {OUT}")


if __name__ == "__main__":
    main()
