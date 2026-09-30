"""Measure the prime layer: what the APK carries that the downloaded packages do not.

The game reads two layers of data. Prime is baked into the APK at
``assets/bin/Data/Package/builtin/<id>/``; override is downloaded to
``files/QtsVFSCache/packages/<id>/`` and holds only what changed since the APK was built. The patcher
stages into override, so an asset that exists only in prime is unreachable -- no text table and no
texture. This prints how large that gap is, per package, and what closing it would gain.

Run by hand from the project root:

    .venv\\Scripts\\python.exe tools\\research\\prime_probe.py
    .venv\\Scripts\\python.exe tools\\research\\prime_probe.py --apk <apk> --game <dump> --packages 1

``--game`` is a session dump: the folder holding ``game/WXQ_Data/Package/builtin``, or the ``builtin``
folder itself. Nothing is written anywhere except a scratch copy of the APK's package indexes.

Off the runtime path: excluded from the exe build and never imported from ``app/`` or ``tools/``.
"""
from __future__ import annotations

import argparse
import pathlib
import shutil
import sys
import tempfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.append(str(ROOT / "resources" / "runtime"))

from qts_relocate import read_raw  # noqa: E402
from wxq_patch import adaptive  # noqa: E402
from wxq_patch.qtsvfs import QtsPackage  # noqa: E402

CATALOG = ROOT / "resources" / "catalog"
PRIME_PREFIX = "assets/bin/Data/Package/builtin/"
DEFAULT_APK = ROOT / "dist" / "HOK ACE Patcher Data" / "installed.apk"
DEFAULT_PACKAGES = ("1", "1050016095")


def find_dump(candidate: pathlib.Path) -> pathlib.Path | None:
    """The ``builtin`` folder holding the override packages, from a session or game dir."""
    for path in (candidate, candidate / "game" / "WXQ_Data" / "Package", candidate / "WXQ_Data" / "Package"):
        builtin = path if path.name == "builtin" else path / "builtin"
        if builtin.is_dir() and any(p.name.isdigit() for p in builtin.iterdir()):
            return builtin
    return None


def latest_session(work: pathlib.Path) -> pathlib.Path | None:
    sessions = sorted((work / "sessions").glob("*/game"), reverse=True) if (work / "sessions").is_dir() else []
    return sessions[0] if sessions else None


def extract_prime(apk: pathlib.Path, package_ids, target: pathlib.Path) -> dict[str, pathlib.Path]:
    """Copy each wanted package's ``.db`` files out of the APK; the shards are not needed to count."""
    found = {}
    with zipfile.ZipFile(apk) as archive:
        for info in archive.infolist():
            if not info.filename.startswith(PRIME_PREFIX) or info.is_dir():
                continue
            package_id, _, name = info.filename[len(PRIME_PREFIX):].partition("/")
            if package_id not in package_ids or "/" in name or not name.endswith(".db"):
                continue
            folder = target / package_id
            folder.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, (folder / name).open("wb") as out:
                shutil.copyfileobj(source, out, 1 << 20)
            found[package_id] = folder
    return found


def bytes_of(folder: pathlib.Path, package_id: str) -> int:
    return sum(p.stat().st_size for p in folder.glob(f"{package_id}*.db"))


def probe(package_id: str, prime_dir: pathlib.Path, override_dir: pathlib.Path | None, catalog, verbose: bool) -> dict:
    prime = QtsPackage(prime_dir)
    override = QtsPackage(override_dir) if override_dir is not None else None
    prime_set = set(prime.entries)
    override_set = set(override.entries) if override else set()
    prime_only = prime_set - override_set
    shared = prime_set & override_set

    print(f"\n=== package {package_id} ===", flush=True)
    print(f"  prime     {len(prime.entries):5d} assets  {bytes_of(prime_dir, package_id):>12,} bytes")
    if override:
        print(f"  override  {len(override.entries):5d} assets  {bytes_of(override_dir, package_id):>12,} bytes")
    print(f"  shared {len(shared)}   prime-only {len(prime_only)}   "
          f"override-only {len(override_set - prime_set)}")

    known = sorted(h for h in prime_only if h in catalog.known)
    graphics = sorted(h for h in prime_only if h in catalog.graphics)
    print(f"  prime-only covered by the catalog: {len(known)} text tables, {len(graphics)} textures")

    translated = records = unreadable = 0
    slots = prime.build_slot_map()
    for file_hash in known:
        raw = read_raw(prime, slots, file_hash)
        if raw is None:
            unreadable += 1
            continue
        try:
            _new, counts = adaptive.translate_table(raw, file_hash, catalog)
        except Exception as error:  # noqa: BLE001 - the runtime refusing a table is a result here
            unreadable += 1
            if verbose:
                print(f"    {file_hash:016X}: {error}")
            continue
        if counts.get("translated"):
            translated += 1
            records += counts["translated"]
    print(f"  of those tables, {translated} translate ({records:,} records); "
          f"{unreadable} the runtime refuses; {len(known) - translated - unreadable} already English")
    return {"prime": len(prime.entries), "override": len(override.entries) if override else 0,
            "shared": len(shared), "prime_only": len(prime_only), "known": len(known),
            "translated": translated, "records": records, "graphics": len(graphics)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apk", type=pathlib.Path, default=DEFAULT_APK)
    parser.add_argument("--game", type=pathlib.Path, help="session dump or its game/ dir")
    parser.add_argument("--packages", nargs="+", default=list(DEFAULT_PACKAGES))
    parser.add_argument("--work", type=pathlib.Path, default=ROOT / "dist" / "HOK ACE Patcher Data",
                        help="where to look for the newest session dump when --game is omitted")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if not args.apk.is_file():
        raise SystemExit(f"no APK at {args.apk}; pass --apk <path to the game APK>")
    session = args.game or latest_session(args.work)
    if session is None:
        raise SystemExit(f"no session dump under {args.work}; pass --game <dump>")
    dump = find_dump(session)
    if dump is None:
        raise SystemExit(f"{session} holds no WXQ_Data/Package/builtin; pass --game <dump>")
    print(f"APK   {args.apk}\ndump  {dump}")

    catalog = adaptive.load_catalog(CATALOG)
    print(f"catalog: {len(catalog.known)} text tables, {len(catalog.graphics)} textures, "
          f"{len(catalog.unique)} strings")

    with tempfile.TemporaryDirectory(prefix="hok-prime-probe-") as scratch:
        prime_dirs = extract_prime(args.apk, set(args.packages), pathlib.Path(scratch))
        for package_id in args.packages:
            if package_id not in prime_dirs:
                print(f"\n=== package {package_id} ===\n  not in the APK")
                continue
            override_dir = dump / package_id
            probe(package_id, prime_dirs[package_id], override_dir if override_dir.is_dir() else None,
                  catalog, args.verbose)


if __name__ == "__main__":
    main()
