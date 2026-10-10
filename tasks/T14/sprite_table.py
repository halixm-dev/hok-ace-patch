"""Print a device sprite atlas's sprite table and render the atlas with every sprite boxed.

Package 19's UI atlases are Unity SpriteAtlases split over QTS assets: one asset holds the Texture2D's
pixels (raw ASTC), another holds the Sprite objects plus the Texture2D header. Tencent's SerializedFile
header is modified (UnityPy cannot read it), but each Sprite record is plain: a length-prefixed
``Image_<id>`` name, 4-byte aligned, followed by ``m_Rect`` as four little-endian floats
(x, y, w, h) with y measured from the **bottom** of the texture. This reads exactly that.

    .venv\\Scripts\\python.exe tasks\\T14\\sprite_table.py --package <dump>\\WXQ_Data\\Package\\builtin\\19 ^
        --texture 13C19E4E4486B31C --sprites 4AA2B26FF28CB65D --size 1024 --out <dir>

Writes ``<out>/<texture>_rects.json`` ({sprite: [x0, y0, x1, y1]} in top-down pixel coordinates, the
convention the catalog's ``regions[].box`` uses) and ``<out>/<texture>_rects.png``, then compares the
catalog's ``regions`` for that texture against the device rects.
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
from sprite_table import sprite_rects  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402
from wxq_patch.qtsvfs import QtsPackage  # noqa: E402

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--texture", required=True)
    parser.add_argument("--sprites", required=True)
    parser.add_argument("--size", type=int, default=1024)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    qts_relocate.install_btree_slot_map()
    package = QtsPackage(args.package)
    slots = package.build_slot_map()
    rects = sprite_rects(qts_relocate.read_raw(package, slots, int(args.sprites, 16)), args.size)
    pixels = qts_relocate.read_raw(package, slots, int(args.texture, 16))
    image = Image.frombytes("RGBA", (args.size, args.size),
                            mg.decode_astc(pixels, args.size, args.size, 4, 4)).transpose(Image.FLIP_TOP_BOTTOM)
    canvas = Image.new("RGBA", image.size, (40, 40, 60, 255))
    canvas.alpha_composite(image)
    draw = ImageDraw.Draw(canvas)
    for box in rects.values():
        draw.rectangle(box, outline=(255, 0, 0, 255))

    catalog = json.load(gzip.open(ROOT / "resources" / "catalog" / "catalog.json.gz"))
    entry = next((g for g in catalog["graphics"] if g["hash"] == args.texture.upper()), None)
    for region in (entry or {}).get("regions", []):
        device = rects.get(region["sprite"])
        moved = device is not None and tuple(device) != tuple(region["box"])
        draw.rectangle(region["box"], outline=(255, 255, 0, 255), width=2)
        print(f"{region['label']:26s} {region['sprite']:18s} catalog {tuple(region['box'])} "
              f"device {device} {'MOVED' if moved else 'same' if device else 'ABSENT'}")

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / f"{args.texture}_rects.json").write_text(json.dumps(rects, indent=1))
    canvas.save(args.out / f"{args.texture}_rects.png")
    print(f"{len(rects)} sprites -> {args.out}")


if __name__ == "__main__":
    main()
