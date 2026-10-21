"""Recompute the two digests a config bin stores, and reseal a lineup bin after a rewrite (docs/features/official-lineups.md).

A config bin is a protobuf: ``1`` = a 32-character upper-case hex digest, ``2`` = the rows (each a
serialized row message), ``3`` = an index (``1`` = packed uint32 keys, ``2`` = entries of ``1`` = key and
``2`` = packed uint32 values) and ``4`` = a uint32 checksum.

* **Field 1** is ``MD5`` of the rows' bytes concatenated, in stored order.
* **Field 4** is what the game checks. ``PBDatabinLoader.cpp`` ``DecodeFromStream`` (libGameCore.so
  ``0x4ac16fc``, 1.6.0.1) seeds a 32-bit state with ``0x01234567`` and folds in, through ``0x31ccc4c``
  (``h = (h ^ byte) * 0x89ABCDEF`` per byte), every row's bytes, then each index key as 4 little-endian
  bytes, then each index entry's key and values the same way. A mismatch logs
  ``[DATABIN] {0} checksum mismatch`` and frees the bin instead of loading it, so the game drops what the
  bin feeds. The loader does not compare field 1.

The port is the shipping one, ``tools/config_bin.py``; this script is its evidence.

The index depends on the rows' keys only, so a rewrite that changes no key keeps it.

``--check`` recomputes both values for every config bin of package ``1`` in both layers. ``--prove``
then changes one lineup name in each lineup bin, reseals it, and shows that the stale checksum fails, the
resealed one passes, the code still decodes, and every other row keeps its bytes.

    .venv\\Scripts\\python.exe tools\\research\\config_bin_checksum.py --game <dump> --prime <prime-layer>

``--game`` and ``--prime`` are read as in ``lineup_bins.py``. Nothing is written.

Off the runtime path: excluded from the exe build and never imported from ``app/`` or ``tools/``.
"""
from __future__ import annotations

import argparse
import base64
import pathlib
import re
import sys
import zlib
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from lineup_bins import BINS, LAYERS, NOT_BASE64, _assets, _encode, _fields, _package_dir  # noqa: E402
# The shipping port (tools/config_bin.py); lineup_bins put tools/ on sys.path.
from config_bin import checksum, reseal, rows_md5  # noqa: E402

CODE_FIELDS = {"F79FB1A213A9DA90": 4, "6A2B886E5DCF22DC": 11, "C0C56FEFDCA0EA5D": 5}
HEAD = re.compile(rb"\n [0-9A-F]{32}")
TEST_NAME = "Checksum test"


def _by_number(entries: list[tuple[int, int, object]]) -> dict[int, object]:
    """{field number: value}, the last occurrence winning (the bin's singular fields)."""
    return {number: value for number, _, value in entries}


def _is_config_bin(raw: bytes) -> bool:
    return HEAD.match(raw) is not None


def check(roots: dict[str, pathlib.Path]) -> bool:
    ok = True
    parsed: dict[str, dict[str, list[tuple[int, int, object]]]] = {}
    for layer in LAYERS:
        counts: Counter[str] = Counter()
        parsed[layer] = {}
        for name, raw in _assets(_package_dir(roots[layer], "1")):
            if b"ResData.ResSeasonAILineupDataBin" in raw[:1 << 16] and not _is_config_bin(raw):
                registry_fields = Counter(inner for _, _, entry in _fields(raw) for inner, _, _ in _fields(entry))
                print(f"{layer} registry {name}: entry field numbers {dict(registry_fields)}")
            if not _is_config_bin(raw):
                continue
            try:
                entries = _fields(raw)
            except (ValueError, IndexError):
                counts["unparsed"] += 1
                continue
            parsed[layer][name] = entries
            stored = _by_number(entries)
            counts["bins"] += 1
            counts["field 1 = md5(rows)"] += stored.get(1) == rows_md5(entries)
            counts["field 4 = checksum"] += stored.get(4) == checksum(entries)
            counts["re-serializes identically"] += _encode(entries) == raw
        print(f"{layer}: {dict(counts)}")
        ok &= counts["bins"] == counts["field 1 = md5(rows)"] == counts["field 4 = checksum"]
    index: Counter[str] = Counter()
    for name in parsed["prime"].keys() & parsed["override"].keys():
        prime, override = (_by_number(parsed[layer][name]) for layer in LAYERS)
        rows_same = ([v for n, _, v in parsed["prime"][name] if n == 2]
                     == [v for n, _, v in parsed["override"][name] if n == 2])
        index[f"rows {'same' if rows_same else 'differ'}, index {'same' if prime.get(3) == override.get(3) else 'differs'}"] += 1
    print(f"bins in both layers: {dict(index)}")
    return ok


def _rename(code: bytes, name: str) -> bytes:
    """Replace ``OneLineup.Name`` in a share code, keeping the stored field order."""
    inflated = zlib.decompress(base64.b64decode(NOT_BASE64.sub(b"", code)), -15)
    message = [(n, w, name.encode() if n == 1 else v) for n, w, v in _fields(inflated)]
    packer = zlib.compressobj(6, zlib.DEFLATED, -15)
    return base64.b64encode(packer.compress(_encode(message)) + packer.flush())


def prove(roots: dict[str, pathlib.Path]) -> bool:
    ok = True
    wanted = {int(name, 16) for name in BINS}
    for layer in LAYERS:
        assets = dict(_assets(_package_dir(roots[layer], "1"), wanted))
        for name in BINS:
            entries = _fields(assets[name])
            stored = _by_number(entries)
            row_at = next(i for i, (n, _, _) in enumerate(entries) if n == 2)
            row = _fields(entries[row_at][2])
            row = [(n, w, _rename(v, TEST_NAME) if n == CODE_FIELDS[name] else v) for n, w, v in row]
            changed = list(entries)
            changed[row_at] = (2, 2, _encode(row))

            stale = checksum(changed) == stored[4]
            sealed = reseal(changed)
            sealed_raw = _encode(sealed)
            again = _fields(sealed_raw)
            code = _by_number(_fields(again[row_at][2]))[CODE_FIELDS[name]]
            read_back = _by_number(_fields(zlib.decompress(base64.b64decode(code), -15)))[1]
            others_kept = all(a == b for i, (a, b) in enumerate(zip(entries, again))
                              if i != row_at and a[0] not in (1, 4))
            # The two "passes" lines only show reseal() agrees with checksum(); the evidence that checksum()
            # is the game's is check() reproducing every stored value.
            results = {
                "unchanged bin reseals to itself": _encode(reseal(entries)) == assets[name],
                "stale checksum fails": not stale,
                "resealed checksum passes": _by_number(again)[4] == checksum(again),
                "resealed md5 passes": _by_number(again)[1] == rows_md5(again),
                "name reads back": read_back.decode() == TEST_NAME,
                "other rows and index kept": others_kept,
            }
            print(f"{layer} {name}: {len(assets[name])} -> {len(sealed_raw)} B, {results}")
            ok &= all(results.values())
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", type=pathlib.Path, required=True, help="session dump (override layer)")
    parser.add_argument("--prime", type=pathlib.Path, required=True, help="folder of prime-layer packages")
    args = parser.parse_args()
    roots = {"prime": args.prime, "override": args.game}
    checked = check(roots)
    proved = prove(roots)
    print("all digests recomputed" if checked else "SOME DIGESTS DID NOT RECOMPUTE")
    print("reseal proven on every lineup bin" if proved else "RESEAL FAILED")
    return 0 if checked and proved else 1


if __name__ == "__main__":
    raise SystemExit(main())
