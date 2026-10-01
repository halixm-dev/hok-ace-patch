"""Measure the extra-text assets that are not in the allowlist: where they live, and what a cycle wins.

`extra_text.SAFE_ASSETS` is an allowlist because nothing about a config asset predicts what rewriting it
costs, and the note beside it names fifteen more assets that have never been put on a phone. This
measures all fifteen against a game dump: which package carries each one, how many Chinese strings it
holds, how many of those the catalog has an official English for, and -- through the pass's own planner
-- exactly which assets a cycle naming it would rewrite. It is the census a cycle starts its order from,
and the offline check that the cycle mechanism selects the asset the cycle names and nothing else.

Run by hand from the project root:

    .venv\\Scripts\\python.exe tools\\research\\extra_text_candidates.py --game <dump>
    .venv\\Scripts\\python.exe tools\\research\\extra_text_candidates.py --game <dump> --candidate 63922EF4

``--game`` is a session dump: the folder holding ``WXQ_Data/Package/builtin``, or ``builtin`` itself.
The catalog is read, never written, and nothing is written anywhere.

Off the runtime path: excluded from the exe build and never imported from ``app/`` or ``tools/``.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.append(str(ROOT / "resources" / "runtime"))

import extra_text  # noqa: E402
import pb_text  # noqa: E402
from qts_relocate import read_raw  # noqa: E402
from wxq_patch import adaptive  # noqa: E402
from wxq_patch.qtsvfs import QtsPackage  # noqa: E402

CATALOG = ROOT / "resources" / "catalog"


def find_dump(candidate: pathlib.Path) -> pathlib.Path | None:
    """The ``builtin`` folder holding the packages, from a session or game dir."""
    for path in (candidate, candidate / "game" / "WXQ_Data" / "Package",
                 candidate / "WXQ_Data" / "Package"):
        builtin = path if path.name == "builtin" else path / "builtin"
        if builtin.is_dir() and any(p.name.isdigit() for p in builtin.iterdir()):
            return builtin
    return None


def packages_of(builtin: pathlib.Path) -> dict[str, QtsPackage]:
    """Every readable package in the dump, by id."""
    found = {}
    for package_dir in sorted((p for p in builtin.iterdir() if p.is_dir() and p.name.isdigit()),
                              key=lambda p: int(p.name)):
        try:
            found[package_dir.name] = QtsPackage(package_dir)
        except Exception:  # noqa: BLE001 - a package we cannot index is not this census's business
            continue
    return found


def locate(packages: dict[str, QtsPackage], hashes: set[int]) -> dict[int, list[str]]:
    """For each wanted hash, the ids of the packages whose index carries it."""
    where: dict[int, list[str]] = {}
    for package_id, package in packages.items():
        for file_hash in set(package.entries) & hashes:
            where.setdefault(file_hash, []).append(package_id)
    return where


def measure(package: QtsPackage, file_hash: int, catalog, skip: set[int]) -> dict:
    """What a rewrite of one asset would look at, what the catalog covers, and what it would change."""
    row = {"fields": 0, "distinct": 0, "covered": 0, "rewrites": 0, "planned": 0, "note": ""}
    entry = package.entries[file_hash]
    raw = read_raw(package, package.build_slot_map(), file_hash)
    if raw is None:
        row["note"] = f"unreadable at compression {entry.compression}"
        return row
    row["raw"] = len(raw)
    try:
        strings = pb_text.collect(raw)
    except pb_text.NotMessage:
        row["note"] = "not a protobuf message"
        return row
    row["fields"] = len(strings)
    row["distinct"] = len(set(strings))
    row["covered"] = sum(1 for s in set(strings) if s in catalog.unique)
    # The pass's own translator and planner, so this measures the shipped behaviour rather than a copy.
    _new, changed = pb_text.rewrite(raw, extra_text.translator_for(file_hash, catalog))
    row["rewrites"] = changed
    jobs = extra_text.plan_package(package, catalog, skip, lambda _message: None,
                                  candidates=frozenset({file_hash}))
    row["planned"] = len(jobs)
    row["selected"] = file_hash in jobs
    return row


def quiet(_message: str) -> None:
    """The planner's log has nothing to say in a census."""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", type=pathlib.Path, required=True, help="a session dump or its builtin")
    parser.add_argument("--candidate", help="print one candidate's strings instead of the table")
    args = parser.parse_args()

    builtin = find_dump(args.game)
    if builtin is None:
        parser.error(f"{args.game} does not hold WXQ_Data/Package/builtin")
    catalog = adaptive.load_catalog(CATALOG)
    packages = packages_of(builtin)
    where = locate(packages, set(extra_text.CANDIDATE_ASSETS))
    skip = set(catalog.known) | set(catalog.graphics)
    print(f"{builtin}\n{len(packages)} packages, catalog covers "
          f"{len(catalog.unique)} distinct strings\n")

    for file_hash, what in extra_text.CANDIDATE_ASSETS.items():
        places = where.get(file_hash)
        if not places:
            print(f"{file_hash:016X}  not in the downloaded layer")
            print(f"{'':18}{what}")
            continue
        for package_id in places:
            package = packages[package_id]
            row = measure(package, file_hash, catalog, skip)
            print(f"{file_hash:016X}  pkg {package_id:>3}  raw {row.get('raw', 0):>7}  "
                  f"fields {row['fields']:>5}  distinct {row['distinct']:>5}  "
                  f"official {row['covered']:>4}  rewrites {row['rewrites']:>4}  "
                  f"selected {row['planned']}"
                  + (f"  [{row['note']}]" if row["note"] else ""))
            print(f"{'':18}{what}")
    # The mechanism's own check: a run that names no candidate plans the allowlist and nothing else,
    # which is what says the cycle knob is inert on a normal build.
    extra: list[int] = []
    for package in packages.values():
        extra += sorted(extra_text.plan_package(package, catalog, skip, quiet))
    outside = sorted(set(extra) - extra_text.SAFE_ASSETS)
    print(f"\nwithout a cycle the pass plans {len(extra)} assets, all of them from the allowlist"
          + ("" if not outside else f" EXCEPT {', '.join(f'{file_hash:016X}' for file_hash in outside)}"))

    if args.candidate:
        file_hash = extra_text.resolve_candidates(args.candidate)[0]
        for package_id in where.get(file_hash, []):
            package = packages[package_id]
            raw = read_raw(package, package.build_slot_map(), file_hash)
            translate = extra_text.translator_for(file_hash, catalog)
            strings = sorted(set(pb_text.collect(raw)))
            print(f"\n{file_hash:016X} in package {package_id}")
            print("-- would translate:")
            for text in strings:
                replacement = translate(text)
                if replacement is not None:
                    print(f"   {text!r} -> {replacement!r}")
            print("-- left Chinese:")
            for text in strings:
                if translate(text) is None:
                    print(f"   {text!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
