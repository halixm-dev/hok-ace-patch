"""Map the three package-1 config bins whose rows carry lineup share codes (docs/features/official-lineups.md).

A share code is base64 of raw deflate of an ``OSProto.OneLineup`` protobuf, decoded on the phone by
``EmbattleFormationDataClass:_decode``. Its text never shows up in a byte search of the bin, so this
measures it from inside the codes, in both data layers:

* **Which table each bin is.** The package-10 Lua annotations (``---@class ResData.<Table>`` with its
  ``---@field`` lines, in declared order) are matched against every row's field numbers and wire types.
  A table is named when it is the one fitting class that declares a share-code field, and the package-1
  data-bin registry (``ResData.<Table>`` -> file name) must list it, or the run stops. Two limits: the
  fit takes a class's field numbers from its declared order, which the annotations do not guarantee; and
  how a registry file name becomes an asset hash is not known, so the registry confirms the table exists,
  not that it is this asset.
* **Every Chinese string**, inside the codes (``OneLineup`` and its nested messages) and in the rows'
  own string fields, with how many codes or rows use it.
* **The round trip** of each code through protobuf, deflate and base64, and which ``zlib`` settings
  reproduce the stored deflate stream.
* **Derived values**: whether any row field equals the code's length, a CRC32, an MD5, or the salted MD5
  the encoder computes (``GetMd5WithSalt``).

The ``OneLineup`` field numbers are measured, not read from the annotations: the annotations carry no
numbers, and ``STLineupHero`` skips field 2, so declared order is not numbering. Fields no shipped code
carries keep the number their declared order implies and are marked ``inferred``.

Run by hand from the project root:

    .venv\\Scripts\\python.exe tools\\research\\lineup_bins.py --game <dump> --prime <prime-layer> ^
        --out <dir>

``--game`` is a session dump (the folder holding ``WXQ_Data/Package/builtin``, or ``builtin`` itself),
read as the override layer. ``--prime`` is a folder holding the prime layer's package folders (a run's
``build/prime``). Writes ``lineup-strings.json`` and ``lineup-bins.json`` to ``--out``; nothing else.

Off the runtime path: excluded from the exe build and never imported from ``app/`` or ``tools/``.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import pathlib
import re
import sys
import zlib
from collections import Counter, defaultdict
from collections.abc import Iterator

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.append(str(ROOT / "resources" / "runtime"))

BINS = ("F79FB1A213A9DA90", "6A2B886E5DCF22DC", "C0C56FEFDCA0EA5D")
LAYERS = ("prime", "override")
CJK = re.compile(r"[　-〿㐀-鿿＀-￯]")
NOT_BASE64 = re.compile(rb"[^A-Za-z0-9+/=]")
CODE_FIELD_NAMES = ("FormationDataCode", "Encode", "LineupCode")

# Measured from the shipped codes (see the module docstring); "inferred" = no shipped code carries it.
HERO = {1: ("ID", "int"), 3: ("Level", "int"), 4: ("EquipIDs", "ints"), 5: ("Type", "int"),
        6: ("IsEvo", "int"), 7: ("Desc", "str"), 8: ("PositionX", "int"), 9: ("PositionZ", "int")}
OPERATION = {1: ("Index", "int"), 2: ("BeginRound", "int"), 3: ("EndRound", "int"),
             4: ("MainHeroIDs", HERO), 5: ("SubHeroIDs", HERO), 6: ("Desc", "str")}
LORD = {1: ("LordID", "int"), 2: ("Desc", "str")}
ONE_LINEUP = {1: ("Name", "str"), 2: ("Provider", "str"), 3: ("PreviewHeroes", HERO), 4: ("Type", "int"),
              5: ("SimpleDesc", "str"), 6: ("PositionDesc", "str"), 7: ("EquipDesc", "str"),
              8: ("OperationDetails", OPERATION), 9: ("LordInfos", LORD), 10: ("TalentIDs", "ints"),
              11: ("EffectCardIDs", "ints"), 12: ("TalentDesc", "str"), 13: ("EffectCardDesc", "str"),
              14: ("Version", "str"), 15: ("SeasonID", "int")}
INFERRED = {"OneLineup": {10, 11, 12, 13}, "STLineupHero": set(), "STOperationDetail": set(),
            "STLineupLordInfo": set()}
MESSAGE_NAMES = {id(ONE_LINEUP): "OneLineup", id(HERO): "STLineupHero", id(OPERATION): "STOperationDetail",
                 id(LORD): "STLineupLordInfo"}


# --- protobuf wire format -------------------------------------------------------------------------------

def _varint(data: bytes, pos: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        shift += 7
        if byte < 0x80:
            return value, pos


def _fields(data: bytes) -> list[tuple[int, int, object]]:
    """[(field number, wire type, value)] in stored order; length-delimited values stay bytes."""
    pos, found = 0, []
    while pos < len(data):
        key, pos = _varint(data, pos)
        number, wire = key >> 3, key & 7
        if wire == 0:
            value, pos = _varint(data, pos)
        elif wire == 2:
            size, pos = _varint(data, pos)
            value = data[pos:pos + size]
            pos += size
        elif wire == 1:
            value, pos = data[pos:pos + 8], pos + 8
        elif wire == 5:
            value, pos = data[pos:pos + 4], pos + 4
        else:
            raise ValueError(f"wire type {wire} at byte {pos}")
        if pos > len(data):
            raise ValueError("field runs past the end")
        found.append((number, wire, value))
    return found


def _put_varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _encode(entries: list[tuple[int, int, object]]) -> bytes:
    """Serialize a field list with minimal varints and lengths, in the order given."""
    out = bytearray()
    for number, wire, value in entries:
        out += _put_varint(number << 3 | wire)
        if wire == 0:
            out += _put_varint(value)
        elif wire == 2:
            out += _put_varint(len(value)) + value
        else:
            out += value
    return bytes(out)


def _reencode(data: bytes, schema: dict, by_number: bool) -> bytes:
    """Rebuild a message from its parsed fields, recursing into known submessages."""
    entries = []
    for number, wire, value in _fields(data):
        kind = schema.get(number, (None, None))[1]
        if isinstance(kind, dict) and wire == 2:
            value = _reencode(value, kind, by_number)
        entries.append((number, wire, value))
    if by_number:
        entries.sort(key=lambda entry: entry[0])  # stable: repeated fields keep their order
    return _encode(entries)


# --- reading the layers -------------------------------------------------------------------------------

def _package_dir(root: pathlib.Path, package: str) -> pathlib.Path:
    for candidate in (root / "WXQ_Data" / "Package" / "builtin" / package, root / package):
        if candidate.is_dir():
            return candidate
    raise SystemExit(f"no package {package} under {root}")


def _assets(package_dir: pathlib.Path, wanted: set[int] | None = None) -> Iterator[tuple[str, bytes]]:
    from qts_relocate import install_btree_slot_map, read_raw
    from wxq_patch.qtsvfs import QtsPackage

    install_btree_slot_map()
    package = QtsPackage(package_dir)
    slots = package.build_slot_map()
    for file_hash in package.entries:
        if wanted is not None and file_hash not in wanted:
            continue
        try:
            raw = read_raw(package, slots, file_hash)
        except Exception:  # noqa: BLE001 - an unreadable asset is simply not a candidate
            raw = None
        if raw is not None:
            yield f"{file_hash:016X}", raw


def _annotations(package_dir: pathlib.Path) -> dict[str, list[tuple[str, str]]]:
    """{ResData class: [(field, type)] in declared order}, from the package's Lua annotation asset."""
    for name, raw in _assets(package_dir):
        if b"---@class ResData.ResSeasonAILineupDataBin" not in raw:
            continue
        classes: dict[str, list[tuple[str, str]]] = {}
        current = None
        for line in raw.decode("utf-8", "replace").splitlines():
            match = re.match(r"---@class ResData\.(\S+)", line)
            if match:
                current = match.group(1)
                classes[current] = []
                continue
            match = re.match(r"---@field (\S+) (\S+)", line)
            if match and current:
                classes[current].append((match.group(1), match.group(2)))
            elif not line.startswith("---"):
                current = None
        print(f"annotations: {package_dir.name}/{name}, {len(classes)} ResData classes")
        return classes
    raise SystemExit(f"no ResData annotations in package {package_dir}")


def _registry(package_dir: pathlib.Path) -> dict[str, str]:
    """{ResData type: data-bin file name}, from the package-1 registry asset."""
    for _, raw in _assets(package_dir):
        if b"ResData.ResSeasonAILineupDataBin" not in raw[:1 << 16] or not raw.startswith(b"\n"):
            continue
        try:
            entries = [_fields(value) for number, wire, value in _fields(raw) if number == 1 and wire == 2]
            pairs = [{n: v for n, _, v in entry} for entry in entries]
            names = {pair[1].decode(): pair[2].decode() for pair in pairs}
        except (ValueError, KeyError, UnicodeDecodeError, IndexError):
            continue
        if "ResData.ResSeasonAILineupDataBin" in names:
            return names
    return {}


# --- naming a bin ---------------------------------------------------------------------------------------

def _wire_fits(declared: str, wire: int, classes: dict[str, list[tuple[str, str]]]) -> bool:
    def scalar(kind: str) -> bool:
        return kind in ("number", "boolean") or (kind.startswith("ResData.") and kind[8:] not in classes)
    if declared.endswith("[]"):
        return wire in (0, 1, 2, 5) if scalar(declared[:-2]) else wire == 2
    return wire in (0, 1, 5) if scalar(declared) else wire == 2


def _fitting_classes(rows: list[bytes], classes: dict[str, list[tuple[str, str]]]) -> list[str]:
    fitting = []
    for name, declared in classes.items():
        if declared and all(number <= len(declared) and _wire_fits(declared[number - 1][1], wire, classes)
                            for row in rows for number, wire, _ in _fields(row)):
            fitting.append(name)
    return fitting


# --- decoding the codes ---------------------------------------------------------------------------------

def _strings(data: bytes, schema: dict, path: str, found: list[tuple[str, str]], seen: Counter) -> None:
    message = MESSAGE_NAMES[id(schema)]
    for number, wire, value in _fields(data):
        name, kind = schema.get(number, (f"#{number}", None))
        field = f"{path}.{name}" if path else name
        seen[f"{message}.{name}#{number}:{wire}"] += 1
        if isinstance(kind, dict) and wire == 2:
            _strings(value, kind, field, found, seen)
        elif kind == "str" and wire == 2:
            text = value.decode("utf-8")
            if CJK.search(text):
                found.append((field, text))
        elif kind is None:
            seen[f"{message}.UNKNOWN#{number}"] += 1


def _deflate_settings(stream: bytes, inflated: bytes) -> list[str]:
    matches = []
    for level in range(10):
        for mem_level in range(1, 10):
            for strategy in range(5):
                packer = zlib.compressobj(level, zlib.DEFLATED, -15, mem_level, strategy)
                if packer.compress(inflated) + packer.flush() == stream:
                    matches.append(f"level={level},memLevel={mem_level},strategy={strategy}")
    return matches


def _salted_md5(code: str) -> str:
    return hashlib.md5(f"{len(code)}{code}osgame".encode()).hexdigest()


def _measure_bin(rows: list[bytes], code_number: int, row_classes: list[tuple[str, str]]) -> dict:
    strings: list[tuple[str, str]] = []
    row_strings: list[tuple[str, str]] = []
    seen: Counter = Counter()
    trip = Counter()
    deflate = Counter()
    derived = Counter()
    for row in rows:
        entries = _fields(row)
        for number, wire, value in entries:
            if wire == 2 and number != code_number and number <= len(row_classes):
                try:
                    text = value.decode("utf-8")
                except UnicodeDecodeError:
                    continue
                if CJK.search(text):
                    row_strings.append((row_classes[number - 1][0], text))
        codes = [value for number, wire, value in entries if number == code_number and wire == 2]
        if not codes:
            trip["rows without a code"] += 1
            continue
        stored = codes[0]
        text = stored.decode("ascii", "replace")
        filtered = NOT_BASE64.sub(b"", stored)
        trip["codes"] += 1
        if filtered != stored:
            trip["codes with non-base64 characters"] += 1
        stream = base64.b64decode(filtered)
        inflated = zlib.decompress(stream, -15)
        in_code: list[tuple[str, str]] = []
        _strings(inflated, ONE_LINEUP, "", in_code, seen)
        strings.extend(dict.fromkeys(in_code))  # count a string once per code that uses it

        trip["protobuf re-serialized in stored order identical"] += _reencode(inflated, ONE_LINEUP, False) == inflated
        trip["protobuf re-serialized in field-number order identical"] += _reencode(inflated, ONE_LINEUP, True) == inflated
        trip["base64 identical"] += base64.b64encode(stream) == filtered
        settings = _deflate_settings(stream, inflated)
        trip["deflate reproduced by some zlib setting"] += bool(settings)
        deflate.update(settings)

        digests = {
            "len(code)": str(len(stored)), "len(deflate)": str(len(stream)), "len(protobuf)": str(len(inflated)),
            "crc32(code)": str(zlib.crc32(stored)), "crc32(protobuf)": str(zlib.crc32(inflated)),
            "md5(code)": hashlib.md5(stored).hexdigest(), "md5(protobuf)": hashlib.md5(inflated).hexdigest(),
            "salted md5(code)": _salted_md5(text),
        }
        raw_digests = {"md5(code)": hashlib.md5(stored).digest(), "md5(protobuf)": hashlib.md5(inflated).digest(),
                       "crc32(code)": zlib.crc32(stored).to_bytes(4, "little"),
                       "crc32(protobuf)": zlib.crc32(inflated).to_bytes(4, "little")}
        for number, wire, value in entries:
            if number == code_number:
                continue
            for label, digest in raw_digests.items():
                if wire != 0 and value == digest:
                    derived[f"field {number} ({row_classes[number - 1][0]}) = raw {label}"] += 1
            if wire in (1, 5):
                shown = str(int.from_bytes(value, "little"))
            else:
                shown = str(value) if wire == 0 else value.decode("latin-1").lower()
            if not shown:
                continue
            for label, digest in digests.items():
                if shown == digest or (len(shown) >= 6 and wire == 2 and shown in digest):
                    derived[f"field {number} ({row_classes[number - 1][0]}) = {label}"] += 1
    return {"strings": strings, "row_strings": row_strings, "fields_seen": seen, "round_trip": trip,
            "deflate_settings": deflate, "derived": derived}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", type=pathlib.Path, required=True, help="session dump (override layer)")
    parser.add_argument("--prime", type=pathlib.Path, required=True, help="folder of prime-layer packages")
    parser.add_argument("--out", type=pathlib.Path, required=True)
    args = parser.parse_args()

    roots = {"prime": args.prime, "override": args.game}
    classes = _annotations(_package_dir(args.prime, "10"))
    registry = _registry(_package_dir(args.prime, "1"))
    print(f"registry: {len(registry)} data bins")

    report: dict = {}
    listing: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(Counter)))
    wanted = {int(name, 16) for name in BINS}
    for layer in LAYERS:
        assets = dict(_assets(_package_dir(roots[layer], "1"), wanted))
        for name in BINS:
            if name not in assets:
                report.setdefault(name, {})[layer] = "absent"
                continue
            top = _fields(assets[name])
            rows = [value for number, wire, value in top if number == 2 and wire == 2]
            fitting = _fitting_classes(rows, classes)
            semantic = [table for table in fitting
                        if any(field in CODE_FIELD_NAMES for field, _ in classes[table])]
            if len(semantic) != 1:
                raise SystemExit(f"{name} {layer}: {fitting} fit the rows; none or several hold a code field")
            table = semantic[0]
            if f"ResData.{table}" not in registry:
                raise SystemExit(f"{name} {layer}: {table} is not in the package-1 data-bin registry")
            declared = classes[table]
            code_number = next(i + 1 for i, (field, _) in enumerate(declared) if field in CODE_FIELD_NAMES)
            measured = _measure_bin(rows, code_number, declared)
            report.setdefault(name, {})[layer] = {
                "bytes": len(assets[name]),
                "table": table,
                "other_fitting_classes": [c for c in fitting if c != table],
                "in_registry": registry.get(f"ResData.{table}"),
                "code_field": f"{declared[code_number - 1][0]} (#{code_number})",
                "rows": len(rows),
                "top_level_fields": sorted(Counter(number for number, _, _ in top).items()),
                "round_trip": dict(measured["round_trip"]),
                "deflate_settings_for_every_code": sorted(
                    setting for setting, count in measured["deflate_settings"].items()
                    if count == measured["round_trip"]["codes"]),
                "deflate_settings": dict(sorted(measured["deflate_settings"].items())),
                "derived_from_code": dict(measured["derived"]),
                "onelineup_fields_seen": dict(sorted(measured["fields_seen"].items())),
            }
            for field, text in measured["strings"]:
                listing[f"{name} {table}"][f"code: {field}"][text][layer] += 1
            for field, text in measured["row_strings"]:
                listing[f"{name} {table}"][f"row: {field}"][text][layer] += 1

    args.out.mkdir(parents=True, exist_ok=True)
    strings_out = {
        bin_name: {field: [{"source": text, **{layer: counts.get(layer, 0) for layer in LAYERS}}
                           for text, counts in sorted(texts.items())]
                   for field, texts in sorted(fields.items())}
        for bin_name, fields in listing.items()
    }
    (args.out / "lineup-strings.json").write_text(json.dumps(strings_out, ensure_ascii=False, indent=1) + "\n",
                                                   encoding="utf-8")
    report["inferred_field_numbers"] = {message: sorted(numbers) for message, numbers in INFERRED.items()}
    (args.out / "lineup-bins.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n",
                                                encoding="utf-8")

    changed = [(bin_name, field, item["source"]) for bin_name, fields in strings_out.items()
               for field, items in fields.items() for item in items if item["prime"] != item["override"]]
    print(f"{len(changed)} entries are used by a different number of codes or rows in the two layers")
    for name in BINS:
        for layer in LAYERS:
            entry = report[name][layer]
            if isinstance(entry, str):
                print(f"{name} {layer}: {entry}")
                continue
            print(f"{name} {layer}: {entry['table']} (registry: {entry['in_registry']}), {entry['rows']} rows, "
                  f"{entry['round_trip']}")
    distinct = sum(len(texts) for fields in strings_out.values() for texts in fields.values())
    sources = {item["source"] for fields in strings_out.values() for texts in fields.values() for item in texts}
    print(f"{distinct} distinct (bin, field, string) entries, {len(sources)} distinct strings, "
          f"{sum(len(s.encode()) for s in sources)} B of UTF-8 -> {args.out / 'lineup-strings.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
