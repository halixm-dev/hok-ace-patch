"""Hunt for the mobile build's own ids for the wide-format Card Info ribbon family.

The catalog keys 27 entries at 568x304 (all ``label_box [168, 244, 400, 296]``, all a 172672-byte
BC7 ``.assets`` payload) -- four per faction, so the Card Info ribbon exists upstream for every
faction. The device carries only one of them, Sunset's ``BCCC8C957621FA27``, which is why Sunset
alone shows an English ribbon. The other factions' wide assets, if the build carries them, sit under
ids the catalog does not key.

This looks for them by content rather than by name. A device texture that *is* a member of the family
must be the same art everywhere except the ribbon band -- the band is the one part the factions
differ in. Four steps, cheapest first:

  [1] the family, and how many *distinct* arts it really holds (payload dedupe);
  [2] the raw sizes that admit a 568x304-shaped texture, using ``offset_layouts`` -- the code's own
      acceptance test -- as the filter;
  [3] a dump census at those sizes (index-only, no shard reads);
  [4] a content score for every surviving (candidate, geometry) against every family entry, plus a
      measured codec floor: what a *genuine* sibling scores at that footprint, from the one pair we
      know is genuine (the device's Sunset texture against its catalog entry).

Scoring uses PIL's C-level ``ImageChops``/``ImageStat`` over the *whole* image rather than
``mobile_graphics._row_diff``'s sampled rows, so a sweep over every catalog entry is affordable. It
is a mean absolute difference per pixel per channel, which is the same quantity as the code's metric,
so the scores are comparable but not identical; anything that looks like a match is re-checked with
the shipped functions before it is believed. Run by hand from the project root:

    .venv\\Scripts\\python.exe tools\\research\\ribbon_id_hunt.py --game <dump>
    .venv\\Scripts\\python.exe tools\\research\\ribbon_id_hunt.py --floor-only
    .venv\\Scripts\\python.exe tools\\research\\ribbon_id_hunt.py --game <dump> --render <dir>

Off the runtime path: excluded from the exe build and never imported from ``app/`` or ``tools/``.
"""
from __future__ import annotations

import argparse
import hashlib
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.append(str(ROOT / "resources" / "runtime"))

import mobile_graphics as mg  # noqa: E402
from PIL import Image, ImageChops, ImageStat  # noqa: E402
from wxq_patch import adaptive  # noqa: E402

CATALOG = ROOT / "resources" / "catalog"
TARGET = (568, 304)
OFFSETS = range(-mg.ALIGNMENT_SEARCH, mg.ALIGNMENT_SEARCH + 1)


def target_entries(catalog) -> dict[int, dict]:
    """The catalog's wide-ribbon family, keyed by the integer asset hash."""
    return {h: g for h, g in catalog.graphics.items() if mg._dimensions(g)[:2] == TARGET}


def payload_rgba(graphic: dict) -> bytes:
    width, height, fmt = mg._dimensions(graphic)
    return mg.decode_pc((CATALOG / graphic["payload"]).read_bytes(), width, height, fmt)


def image(rgba: bytes, width: int, height: int) -> Image.Image:
    """Both decoders return bottom-up buffers, so this is consistent for either side."""
    return Image.frombytes("RGBA", (width, height), rgba)


def outside_score(catalog_image: Image.Image, device_image: Image.Image,
                  rows: tuple[int, int], offset: int) -> float | None:
    """Mean abs difference per pixel per channel outside <rows>, catalog row y against device y+offset.

    ``rows`` is in payload order, which is the order both images are built in, so the band is one
    contiguous row range. Returns None when the offset pushes the overlap off the device.
    """
    height_catalog, height_device = catalog_image.height, device_image.height
    total = count = 0.0
    for start, stop in ((0, rows[0]), (rows[1], height_catalog)):
        device_start, device_stop = max(0, start + offset), min(height_device, stop + offset)
        if device_start >= device_stop:
            continue
        catalog_start, catalog_stop = device_start - offset, device_stop - offset
        left = catalog_image.crop((0, catalog_start, catalog_image.width, catalog_stop)).convert("RGB")
        right = device_image.crop((0, device_start, device_image.width, device_stop)).convert("RGB")
        band = sum(ImageStat.Stat(ImageChops.difference(left, right)).mean) / 3.0
        total += band * (catalog_stop - catalog_start)
        count += catalog_stop - catalog_start
    return total / count if count else None


def alignment(catalog_image: Image.Image, device_image: Image.Image,
              rows: tuple[int, int]) -> tuple[int, float, float] | None:
    """(offset, score, median score) -- the same search ``align_rows`` runs, over every offset."""
    scored = []
    for offset in OFFSETS:
        score = outside_score(catalog_image, device_image, rows, offset)
        if score is not None:
            scored.append((offset, score))
    if not scored:
        return None
    best = min(scored, key=lambda item: item[1])
    median = sorted(score for _offset, score in scored)[len(scored) // 2]
    return best[0], best[1], median


def label_score(catalog_image: Image.Image, device_image: Image.Image,
                box: list[int], rows: tuple[int, int], offset: int) -> float | None:
    """Mean abs difference inside the label band, at the measured alignment."""
    start, stop = max(0, rows[0] + offset), min(device_image.height, rows[1] + offset)
    if start >= stop:
        return None
    catalog_rows = (start - offset, stop - offset)
    left = catalog_image.crop((box[0], catalog_rows[0], box[2], catalog_rows[1])).convert("RGB")
    right = device_image.crop((box[0], start, box[2], stop)).convert("RGB")
    return sum(ImageStat.Stat(ImageChops.difference(left, right)).mean) / 3.0


def candidate_sizes(width: int, height: int) -> dict[int, list[tuple[int, int, int]]]:
    """Raw sizes admitting a 568x304-shaped texture, with the layouts that actually admit it."""
    sizes: dict[int, list[tuple[int, int, int]]] = {}
    for bx, by in mg.ASTC_FOOTPRINTS:
        blocks_x = math.ceil(width / bx)
        for blocks_y in range(1, 300):
            size = blocks_x * blocks_y * 16
            layouts = mg.offset_layouts(size, width, height)
            if layouts and size not in sizes:
                sizes[size] = layouts
    return sizes


def census(game: pathlib.Path) -> list[tuple[str, int, int]]:
    """(package id, file hash, uncompressed size) for every asset in the dump."""
    from wxq_patch.qtsvfs import QtsPackage  # noqa: PLC0415

    root = game / "WXQ_Data" / "Package" / "builtin"
    found = []
    for directory in sorted(root.iterdir(), key=lambda p: p.name):
        if not directory.is_dir():
            continue
        try:
            slots = QtsPackage(directory).build_slot_map()
        except Exception:
            continue
        for file_hash, chunks in slots.items():
            found.append((directory.name, file_hash,
                          sum(slot.uncompressed_size for slot in chunks.values())))
    return found


def device_raw(game: pathlib.Path, package_id: str, file_hash: int) -> bytes | None:
    from device_extensions import _read_chunks  # noqa: PLC0415
    from wxq_patch.qtsvfs import QtsPackage  # noqa: PLC0415

    slots = QtsPackage(game / "WXQ_Data" / "Package" / "builtin" / package_id).build_slot_map()
    chunks = _read_chunks(slots.get(file_hash, {}))
    if not chunks:
        return None
    try:
        return b"".join(mg.oodle_decompress(payload, slot.uncompressed_size)
                        for slot, payload in chunks)
    except Exception as error:
        print(f"      decompress failed: {type(error).__name__}: {error}")
        return None


def dedupe(targets: dict[int, dict]) -> None:
    print(f"\n[1] the wide-ribbon family: {len(targets)} entries")
    digests: dict[str, list[int]] = {}
    for file_hash, graphic in targets.items():
        payload = (CATALOG / graphic["payload"]).read_bytes()
        digests.setdefault(hashlib.sha256(payload).hexdigest(), []).append(file_hash)
    print(f"  {len(digests)} distinct payloads among {len(targets)} entries")
    for digest, members in sorted(digests.items(), key=lambda kv: -len(kv[1])):
        labels = sorted({targets[h].get("label") or "?" for h in members})
        ids = " ".join(f"{h:016X}" for h in sorted(members))
        print(f"  {digest[:12]} x{len(members):<2} {', '.join(labels):<34}{ids}")


def floor(targets: dict[int, dict], samples: list[int]) -> None:
    """What a genuine sibling scores, per footprint, measured on known-good art.

    A sample entry's own payload is re-encoded as ASTC at each footprint -- exactly the situation a
    device revision of that art would present -- and scored against every family entry. The self
    score is the floor a genuine sibling has to reach; the spread shows how well the family's shared
    art discriminates between entries at all.
    """
    print("\n[2] codec floor: the same art re-cut to each device footprint")
    entries = {h: (g, image(payload_rgba(g), *TARGET)) for h, g in targets.items()}
    for sample in samples:
        graphic = targets[sample]
        rgba = payload_rgba(graphic)
        print(f"\n  sample {sample:016X} {graphic.get('label')} (its own payload, re-encoded)")
        for bx, by in mg.ASTC_FOOTPRINTS:
            packed = mg.encode_astc(rgba, *TARGET, bx, by)
            height = math.ceil(TARGET[1] / by) * by
            device = image(mg.decode_astc(packed, TARGET[0], height, bx, by), TARGET[0], height)
            rows = mg.label_rows(graphic, TARGET[1])
            ranked = []
            for other_hash, (other, other_image) in entries.items():
                found = alignment(other_image, device, mg.label_rows(other, TARGET[1]))
                if found is not None:
                    ranked.append((found[1], other_hash))
            ranked.sort()
            own = next((score for score, h in ranked if h == sample), None)
            nearest = next(((score, h) for score, h in ranked if h != sample), None)
            print(f"    {bx}x{by} @ {len(packed):>6} B: own {own:6.2f}"
                  f"  next distinct {nearest[0]:6.2f} ({nearest[1]:016X})"
                  f"  worst {ranked[-1][0]:6.2f}")


def sweep(game: pathlib.Path, targets: dict[int, dict], sizes: dict, render: pathlib.Path | None) -> None:
    entries = {h: (g, image(payload_rgba(g), *TARGET)) for h, g in targets.items()}
    hits = sorted((pkg, h, size) for pkg, h, size in census(game) if size in sizes)
    print(f"\n[4] census: {len(hits)} assets land in a 568x304-shaped raw size")
    for pkg, file_hash, size in hits:
        print(f"  pkg {pkg:<12}{file_hash:016X}  {size:>7} B  "
              + ", ".join(f"{bx}x{by} -> {height} px" for height, bx, by in sizes[size]))

    ranked: list[tuple[float, str, int, int, int, int, list]] = []
    for pkg, file_hash, size in hits:
        raw = device_raw(game, pkg, file_hash)
        if raw is None:
            continue
        for device_height, bx, by in sizes[size]:
            device = image(mg.decode_astc(raw, TARGET[0], device_height, bx, by),
                           TARGET[0], device_height)
            scores = []
            for other_hash, (other, other_image) in entries.items():
                found = alignment(other_image, device, mg.label_rows(other, TARGET[1]))
                if found is None:
                    continue
                offset, score, median = found
                band = label_score(other_image, device, other["label_box"],
                                   mg.label_rows(other, TARGET[1]), offset)
                scores.append((score, median, other_hash, offset, band))
            scores.sort()
            print(f"\n  pkg {pkg} {file_hash:016X} {size} B as {TARGET[0]}x{device_height}@{bx}x{by}")
            for score, median, other_hash, offset, band in scores[:5]:
                print(f"      {other_hash:016X} {targets[other_hash].get('label') or '?':<18}"
                      f"outside {score:7.2f} (median {median:7.2f}, gain {median / score:5.1f}x)"
                      f" offset {offset:+3d}  band {'n/a' if band is None else f'{band:6.2f}'}")
            runner_up = scores[1][0] if len(scores) > 1 else math.inf
            ranked.append((scores[0][0], pkg, file_hash, size, bx, by,
                           [scores[0][2], scores[0][3], runner_up / scores[0][0]]))
            if render is not None:
                render.mkdir(parents=True, exist_ok=True)
                path = render / f"device_pkg{pkg}_{file_hash:016X}_{TARGET[0]}x{device_height}@{bx}x{by}.png"
                device.transpose(Image.FLIP_TOP_BOTTOM).save(path)

    print("\n[5] every candidate, by its best family score (lower is a better match)")
    print(f"  {'outside':>8}{'margin':>8}  {'pkg':<12}{'hash':<18}{'size':>8}  best family entry")
    for score, pkg, file_hash, size, bx, by, (best_hash, best_offset, margin) in sorted(ranked):
        print(f"  {score:8.2f}{margin:8.2f}x {pkg:<12}{file_hash:016X}  {size:>7} B  "
              f"{best_hash:016X} {targets[best_hash].get('label') or '?':<18}"
              f" (as {TARGET[0]}x{'-'}@{bx}x{by} offset {best_offset:+d})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--game", type=pathlib.Path,
                        help="the dumped game directory holding WXQ_Data/Package/builtin")
    parser.add_argument("--render", type=pathlib.Path,
                        help="write a PNG of each candidate geometry here")
    parser.add_argument("--floor-only", action="store_true",
                        help="only print the family and the codec floor (no dump needed)")
    args = parser.parse_args()

    catalog = adaptive.load_catalog(CATALOG)
    targets = target_entries(catalog)
    print(f"catalog: {len(catalog.graphics)} graphics, {len(targets)} at {TARGET[0]}x{TARGET[1]}")
    dedupe(targets)

    samples = [h for h, g in targets.items() if (g.get("label") or "") in ("Sunset", "Riverlands", "Mecha")]
    samples = sorted(samples, key=lambda h: (targets[h].get("label"), h))[:3]
    floor(targets, samples)
    if args.floor_only:
        return 0

    if not args.game:
        parser.error("pass --game (or --floor-only for the catalog-only sections)")

    from qts_relocate import install_btree_slot_map  # noqa: PLC0415

    install_btree_slot_map()
    sizes = candidate_sizes(*TARGET)
    print(f"\n[3] {len(sizes)} raw sizes admit a {TARGET[0]}x{TARGET[1]}-shaped texture")
    for size in sorted(sizes):
        print(f"  {size:>8} B  " + ", ".join(f"{bx}x{by} -> {h} px"
                                            for h, bx, by in sizes[size]))
    sweep(args.game, targets, sizes, args.render)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
