"""Count untranslated Chinese in catalogued tables and allowed Official recommendation lineups.

Run with Python 3.12: --game <game-dir> --apk <apk> --work <scratch-dir>
--output <json>. Optional --overlay <staged-dir> checks a staged patch against
the same pristine layer, reading the actual effective bytes without translating them again.
No game, catalog or staged bytes are changed. Creator nicknames stay as written.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.append(str(ROOT / "resources/runtime"))

from package_rebuild import extract_prime
import config_bin
from extra_text import official_only
import lineup_codes
from qts_relocate import install_btree_slot_map, read_raw
from terminology import install
from wxq_patch import adaptive
from wxq_patch.qtsvfs import QtsPackage

TOKENS = re.compile(r"\{[^{}]*\}")
OFFICIAL_LINEUPS = 0xF79FB1A213A9DA90


def _lineup_nicknames(raw: bytes) -> set[str]:
    """Provider and Author identify creators and stay as written."""
    names = set()
    code_field = lineup_codes.LINEUP_BINS[OFFICIAL_LINEUPS].code_field
    for number, wire, row in config_bin.fields(raw):
        if number != config_bin.ROW_FIELD or wire != 2:
            continue
        for inner, inner_wire, value in config_bin.fields(row):
            if inner_wire != 2:
                continue
            if inner == 19:
                names.add(value.decode("utf-8"))
            elif inner == code_field:
                names.update(value.decode("utf-8") for number, wire, value
                             in config_bin.fields(lineup_codes.decode_code(value)) if number == 2 and wire == 2)
    return names


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, required=True)
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--overlay", type=Path)
    args = parser.parse_args()
    install_btree_slot_map()
    install()
    catalogs = {code: adaptive.load_catalog(ROOT / "resources" / folder)
                for code, folder in (("en", "catalog"), ("id", "catalog_id"))}
    counts = {code: Counter() for code in catalogs}
    unknown = {code: {} for code in catalogs}
    chinese = {code: {} for code in catalogs}
    lineups = {code: {} for code in catalogs}
    tables = Counter()
    refused = []
    prime = extract_prime(args.apk, None, args.work / "prime", index_only=True)
    layer = args.game / "WXQ_Data/Package/builtin"
    folders = {p.name for p in layer.iterdir() if p.is_dir() and p.name.isdigit()}
    if args.overlay:
        folders |= {p.name for p in args.overlay.iterdir() if p.is_dir() and p.name.isdigit()}
    known = set().union(*(catalog.known for catalog in catalogs.values()))

    def record(store: dict, source: str, package: str, asset: int, key: str) -> None:
        row = store.setdefault(source, {"tables": [], "packages": [], "rows": 0, "example_key": key})
        for field, value in (("tables", f"{asset:016X}"), ("packages", package)):
            if value not in row[field]:
                row[field].append(value)
        row["rows"] += 1

    for package in sorted(folders | set(prime), key=int):
        override_dir = layer / package
        if args.overlay and (args.overlay / package / f"{package}.db").is_file():
            override_dir = args.overlay / package
        override = QtsPackage(override_dir) if (override_dir / f"{package}.db").is_file() else None
        prime_package = QtsPackage(prime[package]) if package in prime else None
        override_entries = set(override.entries) if override else set()
        prime_entries = set(prime_package.entries) if prime_package else set()
        wanted = known | {OFFICIAL_LINEUPS}
        sources = [("override", override, override_entries & wanted)]
        prime_known = (prime_entries - override_entries) & wanted
        if prime_known:
            full = extract_prime(args.apk, {package}, args.work / "prime")
            prime_package = QtsPackage(full[package])
        sources.append(("prime_only", prime_package, prime_known))
        for name, source_package, assets in sources:
            if not assets:
                continue
            slots = source_package.build_slot_map()
            for asset in sorted(assets):
                raw = read_raw(source_package, slots, asset)
                if raw is None:
                    raise RuntimeError(f"Unreadable catalog table: {package}/{asset:016X}")
                if asset == OFFICIAL_LINEUPS:
                    texts = lineup_codes.strings(asset, raw)
                    nicknames = _lineup_nicknames(raw)
                    for code, catalog in catalogs.items():
                        translate = official_only(catalog)
                        missing = Counter(text for text in texts if text not in nicknames and translate(text) is None)
                        remaining = Counter(text for text in texts if text not in nicknames)
                        lineups[code] = {"layer": name, "chinese_fields": len(texts),
                                        "distinct_chinese": len(set(texts)), "nickname_count": len(set(texts) & nicknames),
                                        "missing": dict(missing), "remaining_chinese": dict(remaining) if args.overlay else None}
                    continue
                try:
                    adaptive.translate_table(raw, asset, catalogs["en"], build_output=False)
                except adaptive.ProtobufError as error:
                    refused.append({"package": package, "asset": f"{asset:016X}", "layer": name,
                                    "reason": str(error)})
                    continue
                tables[name] += 1
                for code, catalog in catalogs.items():
                    translated, result = adaptive.translate_table(raw, asset, catalog)
                    counts[code].update(result)
                    for _tag, nested, _encoded in adaptive.fields(raw):
                        fields = {tag: value.decode("utf-8") for tag, value, _ in adaptive.fields(nested)}
                        key, text = fields[10], fields[18]
                        if adaptive.CJK_RE.search(TOKENS.sub("", text)) and catalog.lookup(asset, key, text) is None:
                            record(unknown[code], text, package, asset, key)
                    effective = raw if args.overlay else translated
                    for _tag, nested, _encoded in adaptive.fields(effective):
                        fields = {tag: value.decode("utf-8") for tag, value, _ in adaptive.fields(nested)}
                        if adaptive.CJK_RE.search(TOKENS.sub("", fields[18])):
                            record(chinese[code], fields[18], package, asset, fields[10])
        if any(s[2] for s in sources):
            print(f"Package {package}: {tables}", flush=True)
    report = {"source": str(args.game), "overlay": str(args.overlay) if args.overlay else None,
              "catalog_tables_read": dict(tables), "refused": refused, "languages": {code: {
                  "counts": dict(counts[code]), "distinct": len(unknown[code]),
                  "rows": sum(row["rows"] for row in unknown[code].values()),
                  "strings": dict(sorted(unknown[code].items())),
                  "official_lineups": lineups[code],
                  "remaining_chinese": dict(sorted(chinese[code].items()))} for code in catalogs}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for code in catalogs:
        print(code, {key: value for key, value in report["languages"][code].items()
                     if key not in ("strings", "remaining_chinese", "official_lineups")},
              "remaining Chinese:", len(chinese[code]), flush=True)
        print(code, "Official lineups:", lineups[code], flush=True)


if __name__ == "__main__":
    main()
