"""Browse the device's texture assets as images, so a texture can be found by eye.

https://github.com/xentripital/hok-ace-android-en

**Why this is not just "decode every asset".** An ASTC texture's geometry is not stored anywhere in the
package: the raw byte count fixes only the *block count*, because every block is 16 bytes whatever its
size. So the same bytes can be a 568x304 texture at 8x8 or an 852x456 one at 12x12, and the block grid
itself -- how those blocks split between the two axes -- is known only up to factorization. Rendering an
asset therefore always involves a choice. This tool makes the choice explicit instead of hiding it:

* ``--candidates <size>`` renders one asset of that size at every plausible geometry, so the right one
  can be picked by eye. That is the authoritative step.
* ``--render`` then renders a whole size or package at the geometry you picked.
* ``--guess`` skips the picking: it trusts a geometry that matches a catalogued texture dimension, and
  otherwise decodes the candidates and keeps the most coherent, because a wrong grid leaves block-edge
  seams the pixels themselves show. It is a rule of thumb, not a proof, and the output says what it did.
* ``--diagnose`` reports how the device's real geometry relates to raw size, learned from the 323
  catalogued textures whose true dimensions are known.

Indexing the dump takes about a minute and is cached as JSON.

    .venv\\Scripts\\python.exe tools\\research\\browse_assets.py --game <dump> --sizes
    .venv\\Scripts\\python.exe tools\\research\\browse_assets.py --game <dump> --diagnose
    .venv\\Scripts\\python.exe tools\\research\\browse_assets.py --game <dump> --candidates 43168 --out <dir>
    .venv\\Scripts\\python.exe tools\\research\\browse_assets.py --game <dump> --package 19 ^
        --geometry 568x324@12x12 --out <dir>

Off the runtime path: excluded from the exe build and never imported from ``app/`` or ``tools/``.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import pathlib
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.append(str(ROOT / "resources" / "runtime"))

import mobile_graphics as mg  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from wxq_patch import adaptive  # noqa: E402

CATALOG = ROOT / "resources" / "catalog"
DEFAULT_INDEX = ROOT / "dist" / "graphics-diagnosis" / "asset_index.json"
DEFAULT_CELL = (220, 140)
CAPTION = 13
# The footprint the device itself uses for almost everything: `--diagnose` measures 311 of the 322
# catalogued textures it carries at 4x4, 10 at 6x6 and 1 at 8x8. Pinning it is what makes a blind
# render tractable, because the aspect filter then leaves little but the axis swap.
DEFAULT_FOOTPRINT = (4, 4)
# A texture whose aspect ratio is outside this is not a game texture; it is a bad geometry guess.
MIN_ASPECT, MAX_ASPECT = 0.3, 3.5


def build_index(game: pathlib.Path) -> list[dict]:
    """(package, hash, uncompressed size) for every asset in the dump. Index-only, no shard reads."""
    from wxq_patch.qtsvfs import QtsPackage  # noqa: PLC0415

    root = game / "WXQ_Data" / "Package" / "builtin"
    rows: list[dict] = []
    for directory in sorted(root.iterdir(), key=lambda p: p.name):
        if not directory.is_dir():
            continue
        try:
            slots = QtsPackage(directory).build_slot_map()
        except Exception:
            continue
        for file_hash, chunks in slots.items():
            rows.append({"package": directory.name, "hash": f"{file_hash:016X}",
                         "size": sum(slot.uncompressed_size for slot in chunks.values())})
    return rows


def load_index(game: pathlib.Path, path: pathlib.Path, rebuild: bool) -> list[dict]:
    if path.exists() and not rebuild:
        rows = json.loads(path.read_text())
        print(f"index: {len(rows)} assets ({path})")
        return rows
    rows = build_index(game)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows))
    print(f"index: {len(rows)} assets -> {path}")
    return rows


def catalog_dimensions() -> Counter:
    """The game's own texture dimensions, with how often each is declared.

    The declaration count is the tie-break that matters. A device raw size usually admits the axis swap
    as well as the true orientation -- 227856 B is both 404x564 and 564x404 at 4x4 -- and the catalog
    says which the game actually uses by how many entries declare it.
    """
    catalog = adaptive.load_catalog(CATALOG)
    counts: Counter = Counter()
    for graphic in catalog.graphics.values():
        width, height, _fmt = mg._dimensions(graphic)
        if width and height:
            counts[(width, height)] += 1
    return counts


def candidate_geometries(size: int, footprint: tuple[int, int] | None = DEFAULT_FOOTPRINT
                         ) -> list[tuple[int, int, int, int]]:
    """Every (width, height, bx, by) a <size>-byte ASTC buffer could hold, most detail first.

    The buffer is ``blocks`` 16-byte blocks; the grid splits them between the axes, and the footprint
    says how many pixels each block covers. Both are free, so the full candidate set is large -- but
    ``--diagnose`` measures that the device encodes 311 of the 322 catalogued textures it carries at
    **4x4**, and with the footprint pinned the grid usually pins too: the aspect filter then leaves only
    the axis swap. So 4x4 is the default and ``footprint=None`` is the escape hatch.
    """
    if size <= 0 or size % 16:
        return []
    blocks = size // 16
    found = set()
    divisors = {1, blocks}
    for step in range(2, math.isqrt(blocks) + 1):
        if not blocks % step:
            divisors.add(step)
            divisors.add(blocks // step)
    for bx, by in ([footprint] if footprint else mg.ASTC_FOOTPRINTS):
        for grid_x in divisors:
            width, height = grid_x * bx, (blocks // grid_x) * by
            if width < 16 or height < 16:
                continue
            if not MIN_ASPECT <= width / height <= MAX_ASPECT:
                continue
            found.add((width, height, bx, by))
    return sorted(found, key=lambda item: (-(item[0] * item[1]), item[2], item[3]))


def coherence(image: Image.Image) -> float:
    """Mean absolute difference between neighbouring pixels, both directions, sampled.

    A wrong block grid breaks the image's continuity at every block edge, which raises this. Both
    directions are needed: a scrambled orientation can come out as smooth *horizontal* streaks, which
    scores low on horizontal neighbours alone and would be preferred. Measured on 297088 B, the
    transpose is 352x844 of streaks and the truth is 844x352 of a crisp logo. Only comparable between
    candidates covering the same number of pixels -- which every candidate at one footprint does,
    since the area is 16 x block count either way.
    """
    grey = image.convert("L")
    width, height = grey.size
    if width < 2 or height < 2:
        return 0.0
    data = grey.tobytes()
    step_x = max(1, width // 256)
    step_y = max(1, height // 48)
    total = count = 0
    for y in range(0, height, step_y):
        base = y * width
        below = base + step_y * width
        for x in range(0, width - step_x, step_x):
            total += abs(data[base + x] - data[base + x + step_x])
            count += 1
            if below < len(data):
                total += abs(data[base + x] - data[below + x])
                count += 1
    return total / count if count else 0.0


def render_best(game: pathlib.Path, row: dict,
                candidates: list[tuple[int, int, int, int]]):
    """(geometry, image) for the most coherent of <candidates>, or (first, None).

    This is what settles an axis split the size alone cannot: an aspect ratio is only a guess, but a
    wrong grid leaves block-edge seams that the decoded pixels themselves show. Measured on a real
    case, 297088 B is 352x844 of streaks and 844x352 of a crisp logo, and only the second is right.
    """
    if len(candidates) == 1:
        return candidates[0], render(game, row, candidates[0])
    best: tuple[float, tuple[int, int, int, int], Image.Image] | None = None
    for geometry in candidates:
        image = render(game, row, geometry)
        if image is None:
            continue
        score = coherence(image)
        if best is None or score < best[0]:
            best = (score, geometry, image)
    return (best[1], best[2]) if best else (candidates[0], None)


def guess_candidates(size: int, counts: Counter, footprint: tuple[int, int] | None = DEFAULT_FOOTPRINT,
                     limit: int = 8):
    """(geometries to try, why), best first.

    An exact catalogued dimension is trusted outright, because the catalog knows the game's real sizes.
    Otherwise every candidate at the footprint comes back for the caller to settle by coherence -- the
    footprint the device uses varies by family (card art is 4x4, but the 568x304 Card Info panel behind
    ``BCCC8C957621FA27`` is 8x8), so the catalog test searches all six before falling back.
    """
    matches = []
    for candidate in candidate_geometries(size, None):
        width, height = candidate[0], candidate[1]
        exact, swapped = counts.get((width, height), 0), counts.get((height, width), 0)
        if exact or swapped:
            # An exact declaration beats a swapped one: without this both orientations of 227856 score
            # 302, because the same 302 card entries are counted from the other side.
            matches.append(((exact, swapped, width * height), candidate))
    if matches:
        _rank, candidate = max(matches, key=lambda item: item[0])
        declared = counts.get((candidate[0], candidate[1]), 0)
        return [candidate], (f"matches catalogued {candidate[0]}x{candidate[1]}, which "
                             f"{declared} catalog entries declare")
    candidates = candidate_geometries(size, footprint)
    if not candidates:
        return [], f"no geometry at {footprint or 'any footprint'} admits this size"
    if len(candidates) == 1:
        return candidates, f"the only geometry at {footprint or 'any footprint'}"
    return candidates[:limit], f"most coherent of {min(len(candidates), limit)} at " \
                              f"{footprint or 'any footprint'}"


_slot_maps: dict[tuple[str, str], dict] = {}


def read_raw(game: pathlib.Path, package_id: str, hex_hash: str) -> bytes | None:
    """The decompressed Oodle payload of one asset, or None.

    The package's slot map is cached per package. Rebuilding it per asset meant re-parsing an index
    that can hold 29,670 entries, once for every one of that package's assets, which is what made the
    first whole-build render spend 40 minutes reaching only 23 sheets.
    """
    from device_extensions import _read_chunks  # noqa: PLC0415
    from wxq_patch.qtsvfs import QtsPackage  # noqa: PLC0415

    key = (str(game), package_id)
    slots = _slot_maps.get(key)
    if slots is None:
        try:
            slots = QtsPackage(game / "WXQ_Data" / "Package" / "builtin" / package_id).build_slot_map()
        except Exception as error:
            print(f"      pkg {package_id}: {type(error).__name__}: {error}", flush=True)
            slots = {}
        _slot_maps[key] = slots
    chunks = _read_chunks(slots.get(int(hex_hash, 16), {}))
    if not chunks:
        return None
    try:
        return b"".join(mg.oodle_decompress(payload, slot.uncompressed_size)
                        for slot, payload in chunks)
    except Exception as error:
        print(f"      {package_id}/{hex_hash}: {type(error).__name__}: {error}", flush=True)
        return None


def render(game: pathlib.Path, row: dict, geometry: tuple[int, int, int, int]) -> Image.Image | None:
    width, height, bx, by = geometry
    raw = read_raw(game, row["package"], row["hash"])
    if raw is None:
        return None
    if len(raw) != math.ceil(width / bx) * math.ceil(height / by) * 16:
        print(f"      {row['package']}/{row['hash']}: {len(raw)} B is not {width}x{height}@{bx}x{by}")
        return None
    # Device rows are top-down like the review renders; both decoders return them bottom-up.
    return Image.frombytes("RGBA", (width, height),
                           mg.decode_astc(raw, width, height, bx, by)).transpose(Image.FLIP_TOP_BOTTOM)


class Sheets:
    """A streaming contact-sheet writer: pages are written as they fill.

    Each image is downscaled on arrival and the page is flushed the moment it is full, so a whole-build
    render never holds more than one page of thumbnails. Collecting every image first and writing the
    sheets at the end is what made the first attempt at the full build produce nothing at all: 26,424
    decoded textures is hundreds of gigabytes of RGBA buffers, so it thrashed long before sheet one.
    """

    def __init__(self, out: pathlib.Path, prefix: str, cell: tuple[int, int], columns: int,
                 per_sheet: int) -> None:
        self.out, self.prefix, self.cell = out, prefix, cell
        self.columns, self.per_sheet = columns, per_sheet
        self.page: list[tuple[str, Image.Image]] = []
        self.keys: list[str] = []
        # Continue numbering from the highest sheet already there, or a resumed run restarts at 0001
        # and overwrites the sheets -- and their sidecars -- that it was supposed to carry on from.
        if out.exists():
            numbers = [int(path.stem.rsplit("_", 1)[-1]) for path in out.glob(f"{prefix}_*.png")
                       if path.stem.rsplit("_", 1)[-1].isdigit()]
            self.written = max(numbers, default=0)
        else:
            self.written = 0
        self.font = ImageFont.load_default()

    def add(self, caption: str, image: Image.Image, key: str = "") -> None:
        thumb = image.convert("RGB")
        thumb.thumbnail(self.cell, Image.LANCZOS)
        self.page.append((caption, thumb))
        self.keys.append(key)
        if len(self.page) >= self.per_sheet:
            self.flush()

    def flush(self) -> None:
        if not self.page:
            return
        self.out.mkdir(parents=True, exist_ok=True)
        rows = math.ceil(len(self.page) / self.columns)
        canvas = Image.new("RGB", (self.cell[0] * self.columns, (self.cell[1] + CAPTION) * rows),
                           (24, 24, 28))
        draw = ImageDraw.Draw(canvas)
        for index, (caption, thumb) in enumerate(self.page):
            x = (index % self.columns) * self.cell[0]
            y = (index // self.columns) * (self.cell[1] + CAPTION)
            canvas.paste(thumb, (x + (self.cell[0] - thumb.width) // 2,
                                 y + (self.cell[1] - thumb.height) // 2))
            draw.text((x + 3, y + self.cell[1] + 1), caption, fill=(215, 215, 215), font=self.font)
        self.written += 1
        path = self.out / f"{self.prefix}_{self.written:04d}.png"
        canvas.save(path)
        # A sidecar listing the asset ids on the sheet, so an interrupted whole-build render can be
        # resumed instead of started over -- it is a ~30 minute job and it will get interrupted.
        (self.out / f"{self.prefix}_{self.written:04d}.ids").write_text("\n".join(self.keys),
                                                                       encoding="utf-8")
        print(f"  {path}  {canvas.width}x{canvas.height}  {len(self.page)} cells", flush=True)
        self.page = []
        self.keys = []


def rendered_ids(out: pathlib.Path, prefix: str) -> set[str]:
    """Asset ids already present in a sidecar under <out>, for --resume."""
    done: set[str] = set()
    for sidecar in out.glob(f"{prefix}_*.ids"):
        done.update(line.strip() for line in sidecar.read_text(encoding="utf-8").splitlines() if line)
    return done


def write_manifest(rows: list[dict], out: pathlib.Path, counts: Counter,
                   footprint: tuple[int, int] | None) -> None:
    """One CSV line per asset, named by its asset id: the inventory an id can be looked up in.

    ``basis`` records where the geometry came from, because it is the one column that is not a fact of
    the package. ``matches catalogued ...`` means the catalog declares a dimension of that size, so it
    is trustworthy; ``the only geometry ...`` means the size admits just one; anything else is a guess
    that ``--candidates <size>`` has to settle. Sorted by id so it reads as an inventory rather than as
    the largest-first order the sheets use.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["package", "id", "uncompressed_bytes", "geometry", "basis"])
        for row in sorted(rows, key=lambda item: item["hash"]):
            candidates, why = guess_candidates(row["size"], counts, footprint)
            geometry = ""
            if candidates:
                width, height, bx, by = candidates[0]
                geometry = f"{width}x{height}@{bx}x{by}"
            writer.writerow([row["package"], row["hash"], row["size"], geometry, why])
    print(f"  manifest: {len(rows)} assets -> {out}")


def select(rows: list[dict], args) -> list[dict]:
    if args.all:
        chosen = rows
    else:
        packages = set(args.package or [])
        sizes = set(args.size or [])
        chosen = [row for row in rows if row["package"] in packages or row["size"] in sizes]
    if args.min_size:
        chosen = [row for row in chosen if row["size"] >= args.min_size]
    if args.max_size:
        chosen = [row for row in chosen if row["size"] <= args.max_size]
    # Largest first by default: the substantial textures are the interesting ones, and a --limit then
    # works, because a package's hundreds of few-hundred-byte config blobs sort to the end. A whole
    # build is the other way round -- `size-asc` streams sheets out immediately instead of spending the
    # first many minutes on the handful of 17 MB textures.
    order = {
        "size-desc": lambda row: (-row["size"], row["package"], row["hash"]),
        "size-asc": lambda row: (row["size"], row["package"], row["hash"]),
        "id": lambda row: (row["hash"],),
    }[args.order]
    return sorted(chosen, key=order)


def report_sizes(rows: list[dict], top: int, footprint: tuple[int, int] | None) -> None:
    counts = Counter(row["size"] for row in rows)
    textures = [size for size in counts if candidate_geometries(size, footprint)]
    print(f"\n{len(counts)} distinct uncompressed sizes across {len(rows)} assets; "
          f"{len(textures)} of them admit a texture at {footprint or 'any footprint'}")
    print(f"  {'size':>9}{'count':>8}  geometries  candidates")
    for size, count in counts.most_common(top):
        geometries = candidate_geometries(size, footprint)
        shown = ", ".join(f"{w}x{h}@{bx}x{by}" for w, h, bx, by in geometries[:3])
        print(f"  {size:>9}{count:>8}{len(geometries):>12}  "
              + (shown + (" ..." if len(geometries) > 3 else "") if geometries
                 else "not a texture at this footprint"))


def report_packages(rows: list[dict]) -> None:
    counts = Counter(row["package"] for row in rows)
    print(f"\n{len(counts)} packages carrying assets")
    for package, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        biggest = max((row["size"] for row in rows if row["package"] == package), default=0)
        print(f"  pkg {package:<12}{count:>7} assets, largest {biggest} B")


def report_diagnose(rows: list[dict]) -> None:
    """How the device's real geometry relates to raw size, learned from textures whose truth we know.

    The catalogued assets the device carries share the catalog's asset id, so for those the true
    dimensions *and* the device's byte count are both known -- which pins exactly which footprint the
    device encoded them at. That is the only place the mapping is observable rather than guessed.
    """
    catalog = adaptive.load_catalog(CATALOG)
    device_size = {int(row["hash"], 16): row["size"] for row in rows}

    print("\n[1] the footprints the device encodes at, for the catalogued textures it carries")
    footprints: Counter = Counter()
    ambiguous, absent = [], 0
    for graphic in catalog.graphics.values():
        width, height, _fmt = mg._dimensions(graphic)
        if not width or not height:
            continue
        size = device_size.get(int(graphic["hash"], 16))
        if size is None:
            absent += 1
            continue
        hits = [f"{bx}x{by}" for bx, by in mg.ASTC_FOOTPRINTS
                if math.ceil(width / bx) * math.ceil(height / by) * 16 == size]
        if len(hits) == 1:
            footprints[hits[0]] += 1
        elif hits:
            ambiguous.append(f"{graphic['hash']} {width}x{height} {size} B -> {hits}")
        else:
            absent += 1
    for footprint, count in footprints.most_common():
        print(f"    {footprint:<8}{count} catalogued textures")
    print(f"    carrying a size no footprint of their own dimensions explains: {absent}")
    print(f"    explaining more than one footprint: {len(ambiguous)}")
    for detail in ambiguous[:4]:
        print(f"      {detail}")

    print("\n[2] how ambiguous a blind render is, per footprint")
    counts = Counter(row["size"] for row in rows)
    for footprint, label in ((DEFAULT_FOOTPRINT, "the device's usual 4x4"), (None, "all six footprints")):
        buckets: Counter = Counter()
        for size in counts:
            buckets[min(len(candidate_geometries(size, footprint)), 4)] += 1
        print(f"    at {footprint or 'any'}: sizes by geometry count {dict(sorted(buckets.items()))}"
              f"   (4 means 4 or more)")
    print("    the most ambiguous sizes at all six footprints:")
    worst = sorted(((len(candidate_geometries(size, None)), size, counts[size]) for size in counts),
                   reverse=True)
    for count, size, assets in worst[:5]:
        options = ", ".join(f"{w}x{h}@{bx}x{by}" for w, h, bx, by in candidate_geometries(size, None)[:3])
        print(f"      {size:>9} B  {assets:>6} assets  {count:>3} geometries: {options}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--game", type=pathlib.Path,
                        help="the dumped game directory holding WXQ_Data/Package/builtin")
    parser.add_argument("--index", type=pathlib.Path, default=DEFAULT_INDEX,
                        help=f"JSON index cache (default {DEFAULT_INDEX})")
    parser.add_argument("--rebuild", action="store_true", help="rebuild the index cache")
    parser.add_argument("--sizes", action="store_true", help="list the raw sizes and their asset counts")
    parser.add_argument("--packages", action="store_true", help="list the packages and their asset counts")
    parser.add_argument("--diagnose", action="store_true", help="report how geometry relates to raw size")
    parser.add_argument("--top", type=int, default=25, help="rows in the --sizes listing")
    parser.add_argument("--footprint", default="4x4",
                        help="ASTC block footprint to assume: WxH, or 'all' for all six (default 4x4, "
                             "which is what the device uses for 311 of the 322 catalogued textures "
                             "it carries)")
    parser.add_argument("--size", type=int, action="append", help="select this raw size (repeatable)")
    parser.add_argument("--package", action="append", help="select this package id (repeatable)")
    parser.add_argument("--all", action="store_true", help="select every asset (needs --limit)")
    parser.add_argument("--candidates", type=int,
                        help="render one asset of this raw size at every plausible geometry")
    parser.add_argument("--geometry", help="render at WxH@BXxBY")
    parser.add_argument("--guess", action="store_true", help="pick the geometry by rule of thumb")
    parser.add_argument("--render", action="store_true", help="render the selected assets")
    parser.add_argument("--limit", type=int,
                        help="most assets to render (required with --all)")
    parser.add_argument("--min-size", type=int, help="only assets at least this many uncompressed bytes")
    parser.add_argument("--max-size", type=int, help="only assets at most this many uncompressed bytes")
    parser.add_argument("--columns", type=int, default=6, help="cells per sheet row")
    parser.add_argument("--per-sheet", type=int, default=48, help="cells per sheet")
    parser.add_argument("--cell", default="220x140", help="cell size WxH")
    parser.add_argument("--out", type=pathlib.Path, help="directory for the sheets")
    parser.add_argument("--manifest", type=pathlib.Path,
                        help="write a CSV inventory of the selected assets, one line per asset id "
                             "(ignores --limit, so --all --manifest gives the whole build)")
    parser.add_argument("--order", choices=("size-desc", "size-asc", "id"), default="size-desc",
                        help="render order; size-asc streams sheets out fastest (default size-desc)")
    parser.add_argument("--resume", action="store_true",
                        help="skip assets already listed in a sheet sidecar under --out, so an "
                             "interrupted whole-build render can be continued")
    parser.add_argument("--trace", action="store_true",
                        help="log each asset id to stderr just before decoding it; the last line names "
                             "the asset when a native decoder crash kills the run (exit -1073741819)")
    parser.add_argument("--skip", action="append", metavar="ID",
                        help="never decode this asset id (repeatable), for an asset that crashes the "
                             "decoder")
    args = parser.parse_args()

    if not args.game:
        parser.error("--game is required")
    if args.footprint.lower() == "all":
        footprint = None
    else:
        try:
            left, _sep, right = args.footprint.lower().partition("x")
            footprint = (int(left), int(right))
        except ValueError:
            parser.error(f"--footprint wants WxH, got {args.footprint!r}")
        if footprint not in mg.ASTC_FOOTPRINTS:
            parser.error(f"footprint must be one of {mg.ASTC_FOOTPRINTS}")
    from qts_relocate import install_btree_slot_map  # noqa: PLC0415

    install_btree_slot_map()
    rows = load_index(args.game, args.index, args.rebuild)

    if args.sizes:
        report_sizes(rows, args.top, footprint)
    if args.packages:
        report_packages(rows)
    if args.diagnose:
        report_diagnose(rows)

    dimensions = catalog_dimensions()
    cell = tuple(int(part) for part in args.cell.lower().split("x"))

    if args.candidates:
        chosen = [row for row in rows if row["size"] == args.candidates][:1]
        if not chosen:
            print(f"\nno asset has an uncompressed size of {args.candidates} B")
            return 1
        options = candidate_geometries(args.candidates, footprint)
        print(f"\n{args.candidates} B ({len(options)} plausible geometries), "
              f"rendering one asset at each:", flush=True)
        writer = Sheets(args.out, f"candidates_{args.candidates}", cell, 2, 12) if args.out else None
        for geometry in options[:12]:
            image = render(args.game, chosen[0], geometry)
            if image is not None and writer is not None:
                writer.add(f"{geometry[0]}x{geometry[1]}@{geometry[2]}x{geometry[3]}", image)
        if writer is not None:
            writer.flush()

    if args.manifest:
        chosen = select(rows, args)
        if not chosen:
            parser.error("--manifest needs --size, --package or --all")
        write_manifest(chosen, args.manifest, dimensions, footprint)

    if args.render:
        selection = select(rows, args)
        if not selection:
            parser.error("--render needs --size, --package or --all")
        if args.all and args.limit is None:
            print(f"  --all with no --limit: rendering every one of {len(selection)} assets")
        if args.resume and args.out:
            done = rendered_ids(args.out, "assets")
            before = len(selection)
            selection = [row for row in selection if row["hash"] not in done]
            print(f"  resume: {before - len(selection)} already on a sheet, {len(selection)} to go")
        selection = selection[:args.limit] if args.limit else selection
        print(f"\nrendering {len(selection)} assets")
        fixed = None
        if args.geometry:
            size_part, _at, footprint_part = args.geometry.lower().partition("@")
            left, _sep, right = size_part.partition("x")
            ahead, _sep2, behind = footprint_part.partition("x")
            try:
                fixed = (int(left), int(right), int(ahead), int(behind))
            except ValueError:
                parser.error(f"--geometry wants WxH@BXxBY, got {args.geometry!r}")
        elif not args.guess:
            parser.error("pass --geometry, or --guess to use the rule of thumb")

        # Guessing is per asset, not per run: a package holds many sizes, and one geometry for all of
        # them would render almost everything wrong.
        writer = Sheets(args.out, "assets", cell, args.columns, args.per_sheet) if args.out else None
        reasons: Counter = Counter()
        not_textures = 0
        rendered = 0
        skipping = {value.upper() for value in (args.skip or [])}
        for row in selection:
            if row["hash"] in skipping:
                continue
            if args.trace:
                print(f"TRACE {row['package']} {row['hash']} {row['size']}", file=sys.stderr,
                      flush=True)
            image = None
            if fixed is not None:
                geometry = fixed
                image = render(args.game, row, geometry)
            else:
                candidates, why = guess_candidates(row["size"], dimensions, footprint)
                if not candidates:
                    not_textures += 1
                    continue
                geometry, image = render_best(args.game, row, candidates)
                reasons[f"{geometry[0]}x{geometry[1]}@{geometry[2]}x{geometry[3]}  ({why})"] += 1
            if image is not None:
                rendered += 1
                if writer is not None:
                    writer.add(f"{row['hash']} pkg {row['package']}", image, row["hash"])
        if writer is not None:
            writer.flush()
        print(f"  rendered {rendered} assets, {not_textures} were not textures", flush=True)
        if reasons:
            print("  geometries chosen by the rule of thumb:")
            for reason, count in reasons.most_common():
                print(f"    {count:>6} assets  {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
