"""Render a catalog payload or a device ASTC texture to PNG, so a texture can be identified by eye.

The catalog's ``previews/*.png`` only cover the whole-image ``.assets`` payloads, and nothing renders
what the *device* actually carries. That gap is what makes a family like the card panel hard to reason
about: the preview shows the English art, the device holds a different geometry of the same asset, and
nothing puts the two side by side.

Run by hand from the project root:

    :: the catalog's English payload at its declared geometry
    .venv\\Scripts\\python.exe tools\\research\\render_texture.py --hash C9E29F61B9E73713 ^
        --out dist\\graphics-diagnosis

    :: every asset in the dump whose raw size is exactly 121952 bytes
    .venv\\Scripts\\python.exe tools\\research\\render_texture.py --game <dump> --size 121952 ^
        --out dist\\graphics-diagnosis

    :: one device asset, decoded at an explicit geometry
    .venv\\Scripts\\python.exe tools\\research\\render_texture.py --game <dump> ^
        --hash C9E29F61B9E73713 --geometry 592x824@8x8 --out dist\\graphics-diagnosis

Off the runtime path: excluded from the exe build and never imported from ``app/`` or ``tools/``.
"""
from __future__ import annotations

import argparse
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.append(str(ROOT / "resources" / "runtime"))

import mobile_graphics as mg  # noqa: E402
from PIL import Image  # noqa: E402

CATALOG = ROOT / "resources" / "catalog"


def _parse_geometry(text: str) -> tuple[int, int, int, int]:
    """``592x824@8x8`` -> (592, 824, 8, 8)."""
    size, _, footprint = text.lower().partition("@")
    width, _, height = size.partition("x")
    bx, _, by = footprint.partition("x")
    return int(width), int(height), int(bx), int(by)


def _save(rgba: bytes, width: int, height: int, out: pathlib.Path, name: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{name}.png"
    # Device rows are top-down like the review renders; the PC payloads are bottom-up.
    Image.frombytes("RGBA", (width, height), rgba).transpose(Image.FLIP_TOP_BOTTOM).save(path)
    print(f"  {path}  {width}x{height}")


def render_catalog(catalog, hexhash: str, out: pathlib.Path) -> None:
    graphic = catalog.graphics.get(int(hexhash, 16))
    if graphic is None:
        print(f"  {hexhash} is not in the catalog")
        return
    width, height, fmt = mg._dimensions(graphic)
    if not width or not height or fmt not in mg.PC_FORMATS:
        print(f"  {hexhash} declares no usable geometry")
        return
    payload = (CATALOG / graphic["payload"]).read_bytes()
    label = (graphic.get("label") or "?").replace(" ", "-").replace("/", "-")
    _save(mg.decode_pc(payload, width, height, fmt), width, height, out,
          f"catalog_{hexhash}_{label}_{width}x{height}")


def device_assets(game: pathlib.Path, size: int | None, hexhash: str | None) -> list[tuple[str, int, int]]:
    """(package id, file hash, uncompressed size) for every asset matching the selector."""
    from wxq_patch.qtsvfs import QtsPackage  # noqa: PLC0415

    root = game / "WXQ_Data" / "Package" / "builtin"
    wanted = int(hexhash, 16) if hexhash else None
    found = []
    for directory in sorted(root.iterdir(), key=lambda p: p.name):
        if not directory.is_dir():
            continue
        try:
            slots = QtsPackage(directory).build_slot_map()
        except Exception:
            continue
        for file_hash, chunks in slots.items():
            if wanted is not None and file_hash != wanted:
                continue
            total = sum(slot.uncompressed_size for slot in chunks.values())
            if wanted is None and total != size:
                continue
            found.append((directory.name, file_hash, total))
    return found


def render_device(game: pathlib.Path, out: pathlib.Path, *, size: int | None,
                  hexhash: str | None, geometry: tuple[int, int, int, int] | None,
                  catalog) -> None:
    from device_extensions import _read_chunks  # noqa: PLC0415
    from qts_relocate import install_btree_slot_map  # noqa: PLC0415
    from wxq_patch.qtsvfs import QtsPackage  # noqa: PLC0415

    install_btree_slot_map()
    for package_id, file_hash, total in device_assets(game, size, hexhash):
        graphic = catalog.graphics.get(file_hash)
        if geometry is not None:
            width, height, bx, by = geometry
        elif graphic is not None:
            width, height, _fmt = mg._dimensions(graphic)
            layout = mg.astc_layout(total, width, height)
            if layout is None:
                print(f"  {file_hash:016X} @ {total} B: the catalog geometry {width}x{height} does not "
                      f"fit it; pass --geometry")
                continue
            bx, by = layout
        else:
            print(f"  {file_hash:016X} @ {total} B: not in the catalog; pass --geometry")
            continue
        expected = math.ceil(width / bx) * math.ceil(height / by) * 16
        if expected != total:
            print(f"  {file_hash:016X}: {width}x{height}@{bx}x{by} needs {expected} B, the asset is "
                  f"{total} B; skipping")
            continue
        slots = QtsPackage(game / "WXQ_Data" / "Package" / "builtin" / package_id).build_slot_map()
        chunks = _read_chunks(slots[file_hash])
        raw = b"".join(mg.oodle_decompress(payload, slot.uncompressed_size)
                       for slot, payload in chunks)
        label = (graphic.get("label") if graphic else None) or "unknown"
        label = label.replace(" ", "-").replace("/", "-")
        _save(mg.decode_astc(raw, width, height, bx, by), width, height, out,
              f"device_pkg{package_id}_{file_hash:016X}_{label}_{width}x{height}@{bx}x{by}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--game", type=pathlib.Path,
                        help="the dumped game directory holding WXQ_Data/Package/builtin")
    parser.add_argument("--hash", help="a catalog hash (renders its payload) or a device asset hash")
    parser.add_argument("--size", type=int,
                        help="render every device asset whose uncompressed size is exactly this")
    parser.add_argument("--geometry", help="decode the device asset as WxH@BXxBY, e.g. 592x824@8x8")
    parser.add_argument("--out", type=pathlib.Path, required=True, help="directory for the PNGs")
    args = parser.parse_args()

    from wxq_patch import adaptive  # noqa: PLC0415
    catalog = adaptive.load_catalog(CATALOG)

    if args.game:
        if not args.hash and args.size is None:
            parser.error("--game needs --hash or --size to know which assets to render")
        geometry = _parse_geometry(args.geometry) if args.geometry else None
        render_device(args.game, args.out, size=args.size, hexhash=args.hash.upper() if args.hash else None,
                      geometry=geometry, catalog=catalog)
    elif args.hash:
        render_catalog(catalog, args.hash.upper(), args.out)
    else:
        parser.error("pass --hash (catalog payload), or --game with --hash/--size (device texture)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
