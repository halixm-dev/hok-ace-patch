"""Check the lineup-bin pass offline: each bin's translation reads back, and a cycle build changes one asset.

For each lineup bin (``lineup_codes.LINEUP_BINS``) in both layers and both languages, the pass
(``extra_text.rewrite_config``) is applied to the layer's own copy, and the result is checked field by
field against the original:

* the bin passes its own checksum (``config_bin.is_sealed``) and its index is kept;
* every code decodes by the game's steps, with the same fields in the same order;
* every text field reads back as its target (``catalog.unique``, resource tokens expanded), and every
  other field of the codes and rows is byte-identical;
* no Chinese is left, and the pass run on its own output changes nothing.

Given ``--control`` and ``--cycle`` (two ``build_device_patch.py`` output folders, the second with
``--cycle-asset <hash>``), it also lists the files and package-``1`` assets that differ between them and
checks that the staged asset is the pass's output for the game's copy.

Run by hand from the project root:

    .venv\\Scripts\\python.exe tools\\research\\check_lineup_cycle.py --game <dump> --prime <prime-layer> ^
        [--control <out> --cycle <out> --language en|id]

``--game`` and ``--prime`` are read as in ``lineup_bins.py``. Nothing is written.

Off the runtime path: excluded from the exe build and never imported from ``app/`` or ``tools/``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from lineup_bins import LAYERS, ROOT, _assets, _package_dir  # noqa: E402  (puts tools/ on sys.path)
import config_bin  # noqa: E402
import extra_text  # noqa: E402
import lineup_codes  # noqa: E402
from languages import for_catalog  # noqa: E402
from resource_tokens import expand_resource_tokens  # noqa: E402
from terminology import install as install_terminology  # noqa: E402
from wxq_patch import adaptive  # noqa: E402

CATALOGS = {"en": ROOT / "resources" / "catalog", "id": ROOT / "resources" / "catalog_id"}


def _compare(old: bytes, new: bytes, schema: dict | None, target, tally: dict[str, int]) -> None:
    """Walk <old> and <new> together; text fields against <target>, everything else byte for byte."""
    before, after = config_bin.fields(old), config_bin.fields(new)
    if [(n, w) for n, w, _ in before] != [(n, w) for n, w, _ in after]:
        tally["field order changed"] += 1
        return
    for (number, wire, was), (_, _, now) in zip(before, after):
        kind = schema.get(number, "opaque") if schema is not None else "opaque"
        if wire == 2 and kind is None:
            tally["text fields"] += 1
            tally["read back as target"] += now.decode() == target(was.decode())
        elif wire == 2 and isinstance(kind, dict):
            _compare(was, now, kind, target, tally)
        else:
            tally["other fields identical" if was == now else "OTHER FIELDS DIFFER"] += 1


def check_bin(file_hash: int, raw: bytes, catalog, terms: dict[str, str]) -> dict[str, int | bool]:
    official = extra_text.official_only(catalog)

    def target(text: str) -> str:
        found = official(text)
        return expand_resource_tokens(found, terms) if found else text

    new = extra_text.rewrite_config(file_hash, raw, catalog, print, terms)
    if new is None:
        return {"translated": False}
    tally = dict.fromkeys(("text fields", "read back as target", "other fields identical",
                           "OTHER FIELDS DIFFER", "field order changed", "codes"), 0)
    layout = lineup_codes.LINEUP_BINS[file_hash]
    top_old, top_new = config_bin.fields(raw), config_bin.fields(new)
    for (number, _, was), (_, _, now) in zip(top_old, top_new):
        if number != config_bin.ROW_FIELD:
            continue
        for (inner, wire, a), (_, _, b) in zip(config_bin.fields(was), config_bin.fields(now)):
            if inner == layout.code_field:
                tally["codes"] += 1
                _compare(lineup_codes.decode_code(a), lineup_codes.decode_code(b), lineup_codes.ONE_LINEUP,
                         target, tally)
            elif inner in layout.text_fields and wire == 2:
                tally["text fields"] += 1
                tally["read back as target"] += b.decode() == target(a.decode())
            else:
                tally["other fields identical" if a == b else "OTHER FIELDS DIFFER"] += 1
    stored = {number: value for number, _, value in top_old}
    resealed = {number: value for number, _, value in top_new}
    return {"bytes": len(new), "sealed": config_bin.is_sealed(new), "index kept": stored[3] == resealed[3],
            "old checksum stale": stored[4] != resealed[4], **tally,
            "chinese left": len(lineup_codes.strings(file_hash, new)),
            "rerun is a no-op": extra_text.rewrite_config(file_hash, new, catalog, print, terms) is None}


def _ok(result: dict) -> bool:
    return (result.get("translated", True) and result["sealed"] and result["index kept"]
            and result["text fields"] == result["read back as target"] and not result["OTHER FIELDS DIFFER"]
            and not result["field order changed"] and not result["chinese left"] and result["rerun is a no-op"])


def compare_builds(control: pathlib.Path, cycle: pathlib.Path, game: pathlib.Path, catalog,
                   terms: dict[str, str]) -> bool:
    def files(root: pathlib.Path) -> dict[str, str]:
        return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in root.rglob("*") if p.is_file()}

    before, after = files(control), files(cycle)
    print(f"files in one build only: {sorted(before.keys() ^ after.keys())}")
    print(f"files that differ: {sorted(f for f in before.keys() & after.keys() if before[f] != after[f])}")
    enabled = json.loads((cycle / "device_patch_summary.json").read_text(encoding="utf-8"))["cycle_assets"]
    print(f"cycle_assets: {enabled}")
    old = dict(_assets(_package_dir(control, "1")))
    new = dict(_assets(_package_dir(cycle, "1")))
    differ = sorted(name for name in old.keys() | new.keys() if old.get(name) != new.get(name))
    print(f"package 1: {len(old)} vs {len(new)} entries, assets that differ: {differ}")
    pristine = dict(_assets(_package_dir(game, "1")))
    ok = differ == enabled
    for name in enabled:
        expected = extra_text.rewrite_config(int(name, 16), pristine[name], catalog, print, terms)
        same = old.get(name) == pristine[name] and new.get(name) == expected
        print(f"{name}: control is the game's copy and cycle is the pass's output: {same}")
        ok &= same
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", type=pathlib.Path, required=True, help="session dump (override layer)")
    parser.add_argument("--prime", type=pathlib.Path, required=True, help="folder of prime-layer packages")
    parser.add_argument("--control", type=pathlib.Path, help="output folder of a build without a cycle")
    parser.add_argument("--cycle", type=pathlib.Path, help="output folder of the same build with one")
    parser.add_argument("--language", choices=sorted(CATALOGS), default="en", help="the two builds' language")
    args = parser.parse_args()

    install_terminology()  # the catalog as a run loads it: terminology and the catalog supplement
    roots = {"prime": args.prime, "override": args.game}
    wanted = set(lineup_codes.LINEUP_BINS)
    loaded = {code: (adaptive.load_catalog(path), for_catalog(path).resource_terms) for code, path in CATALOGS.items()}
    ok = True
    for layer in LAYERS:
        assets = dict(_assets(_package_dir(roots[layer], "1"), wanted))
        for file_hash in lineup_codes.LINEUP_BINS:
            name = f"{file_hash:016X}"
            if name not in assets:
                print(f"{layer} {name}: absent")
                continue
            for code, (catalog, terms) in loaded.items():
                result = check_bin(file_hash, assets[name], catalog, terms)
                ok &= _ok(result)
                print(f"{layer} {name} {code}: {len(assets[name])} -> {result}")
    if args.control and args.cycle:
        catalog, terms = loaded[args.language]
        ok &= compare_builds(args.control, args.cycle, args.game, catalog, terms)
    print("every lineup bin reads back" if ok else "A CHECK FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
