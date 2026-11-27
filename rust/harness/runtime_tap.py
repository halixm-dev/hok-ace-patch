"""Record the wxq_patch runtime's protobuf parsing for the Rust port to replay (wave 2, ADR-003).

The runtime is bytecode only, so its behaviour is the recording. This covers
``wxq_patch.protobuf_i18n`` (``decode_varint``, ``encode_varint``, ``_fields``, ``parse_i18n``,
``serialize_i18n``) and ``wxq_patch.adaptive.fields``, from three sources:

- generated edge cases: every varint width and error, every wire type, field zero, truncations, bad
  UTF-8, strict and lenient tables (``--generated``);
- every table ``adaptive.translate_table`` reads in one offline pipeline run (same arguments as
  ``pipeline_case.py run``), each also cut short and with a flipped byte (``--tap``);
- seeded random bytes (both modes).

Each line of ``<dir>/calls.jsonl`` is ``{"fn", "args", "input", "result"}``: ``input`` names a blob
under ``<dir>/blobs/<sha256>``, ``result`` is ``{"ok": ...}`` or ``{"error": "Class: message",
"partial": ...}``. Outputs that are streams (a field walk, a list of records) are the SHA-256 of a
canonical encoding the replay rebuilds (``stream_*`` below), so a 1 MB table costs one line.

    .venv\\Scripts\\python.exe rust\\harness\\runtime_tap.py --generated <dir>
    .venv\\Scripts\\python.exe rust\\harness\\runtime_tap.py --validation <dir>
    .venv\\Scripts\\python.exe rust\\harness\\runtime_tap.py --scan <dir> <game> <catalog>
    .venv\\Scripts\\python.exe rust\\harness\\runtime_tap.py --qts <dir> <package-root>
    .venv\\Scripts\\python.exe rust\\harness\\runtime_tap.py --metadata <dir> <internal-index>
    .venv\\Scripts\\python.exe rust\\harness\\runtime_tap.py --catalog <dir> <catalog-folder> ...
    .venv\\Scripts\\python.exe rust\\harness\\runtime_tap.py --scan-runtime <dir> <work> [<game> <catalog-folder>] ...
    .venv\\Scripts\\python.exe rust\\harness\\runtime_tap.py --tap <dir> -- <build_device_patch arguments>
    cargo run --release -p hokace-core --example runtime_replay -- <dir> ...

Migration tooling, run by hand: the exe, the APK and ``tools/`` never import it.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import pathlib
import random
import runpy
import struct
import sys
from types import SimpleNamespace

ROOT = pathlib.Path(__file__).resolve().parents[2]
TAP_BUDGET = 1 << 31  # bytes of distinct tables kept from one run


def _runtime():
    sys.path[:0] = [str(ROOT / "tools")]
    sys.path.append(str(ROOT / "resources" / "runtime"))
    from wxq_patch import adaptive, protobuf_i18n
    return adaptive, protobuf_i18n


def _error(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def _bytes(data: bytes) -> bytes:
    return struct.pack("<Q", len(data)) + data


def _int(value: int) -> bytes:
    return value.to_bytes(16, "little")


class Recorder:
    def __init__(self, out: pathlib.Path) -> None:
        self.blobs = out / "blobs"
        self.blobs.mkdir(parents=True, exist_ok=True)
        self.calls = (out / "calls.jsonl").open("w", encoding="utf-8")
        self.seen: set[str] = set()
        self.count = 0
        self.adaptive, self.pb = _runtime()
        self.catalogs: dict[object, str] = {}

    def keep(self, data: bytes) -> str:
        name = hashlib.sha256(data).hexdigest()
        path = self.blobs / name
        if not path.exists():
            path.write_bytes(data)
        return name

    def write(self, fn: str, args: list, data: bytes | None, result: dict) -> None:
        key = json.dumps([fn, args, None if data is None else hashlib.sha256(data).hexdigest()])
        if key in self.seen:
            return
        self.seen.add(key)
        self.count += 1
        line = {"fn": fn, "args": args, "input": None if data is None else self.keep(data), "result": result}
        self.calls.write(json.dumps(line) + "\n")

    # -- streams: the replay builds the same bytes and compares their SHA-256 --

    def stream_walk(self, data: bytes) -> dict:
        """``adaptive.fields`` over a table and over each of its top-level payloads, as
        ``translate_table`` walks it: ``O`` tag payload raw per outer field, ``I`` per inner field."""
        out = bytearray()
        try:
            for tag, payload, raw in self.adaptive.fields(data):
                out += b"O" + _int(tag) + _bytes(payload) + _bytes(raw)
                for inner_tag, inner_payload, inner_raw in self.adaptive.fields(payload):
                    out += b"I" + _int(inner_tag) + _bytes(inner_payload) + _bytes(inner_raw)
        except Exception as exc:  # noqa: BLE001 - the class and message are the recording
            return {"error": _error(exc), "partial": hashlib.sha256(out).hexdigest()}
        return {"ok": hashlib.sha256(out).hexdigest()}

    def stream_fields(self, data: bytes) -> dict:
        """``protobuf_i18n._fields``: ``F`` field wire, then ``V`` int or ``B`` bytes."""
        out = bytearray()
        try:
            for number, wire, value in self.pb._fields(data):
                out += b"F" + _int(number) + bytes([wire])
                out += b"V" + _int(value) if isinstance(value, int) else b"B" + _bytes(value)
        except Exception as exc:  # noqa: BLE001
            return {"error": _error(exc), "partial": hashlib.sha256(out).hexdigest()}
        return {"ok": hashlib.sha256(out).hexdigest()}

    @staticmethod
    def records_blob(records) -> bytes:
        return b"".join(_bytes(r.key.encode("utf-8")) + _bytes(r.translation.encode("utf-8")) for r in records)

    def table(self, data: bytes) -> None:
        """Every case one table gives."""
        self.write("adaptive.fields", [], data, self.stream_walk(data))
        self.write("protobuf_i18n._fields", [], data, self.stream_fields(data))
        for strict in (True, False):
            try:
                records = self.pb.parse_i18n(data, strict=strict)
            except Exception as exc:  # noqa: BLE001
                self.write("protobuf_i18n.parse_i18n", [strict], data, {"error": _error(exc)})
                continue
            blob = self.records_blob(records)
            self.write("protobuf_i18n.parse_i18n", [strict], data,
                       {"ok": [len(records), hashlib.sha256(blob).hexdigest()]})
            out = self.pb.serialize_i18n(records)
            self.write("protobuf_i18n.serialize_i18n", [], blob, {"ok": hashlib.sha256(out).hexdigest()})

    def varint(self, data: bytes, offset: int) -> None:
        try:
            value, end = self.pb.decode_varint(data, offset)
            result = {"ok": [str(value), end]}
        except Exception as exc:  # noqa: BLE001
            result = {"error": _error(exc)}
        self.write("protobuf_i18n.decode_varint", [offset], data, result)

    def encode(self, value: int) -> None:
        try:
            result = {"ok": self.pb.encode_varint(value).hex()}
        except Exception as exc:  # noqa: BLE001
            result = {"error": _error(exc)}
        self.write("protobuf_i18n.encode_varint", [str(value)], None, result)

    def translation(self, raw, asset, catalog, original) -> None:
        if catalog not in self.catalogs:
            snapshot = [
                catalog.unique,
                [(*key, value) for key, value in catalog.context.items()],
                [(*key, value, catalog.english_sources[key]) for key, value in catalog.english_updates.items()],
            ]
            self.catalogs[catalog] = self.keep(json.dumps(snapshot, ensure_ascii=False).encode())
        for build_output in (True, False):
            try:
                output, counts = original(raw, asset, catalog, build_output=build_output)
                result = {"ok": [None if output is None else hashlib.sha256(output).hexdigest(), list(counts.items())]}
            except Exception as exc:  # noqa: BLE001
                result = {"error": _error(exc)}
            self.write("translate_table", [str(asset), self.catalogs[catalog], build_output], raw, result)

    def close(self) -> None:
        self.calls.close()


def _varint(value: int) -> bytes:
    out = bytearray()
    while value >= 0x80:
        out.append(value & 0x7F | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def _ld(field: int, payload: bytes) -> bytes:
    return _varint(field << 3 | 2) + _varint(len(payload)) + payload


def _record(key: bytes, translation: bytes) -> bytes:
    return _ld(1, _ld(1, key) + _ld(2, translation))


def generated(rec: Recorder, rng: random.Random) -> None:
    values = [0, 1, 2, 127, 128, 255, 256, 300, 16383, 16384, 2**21 - 1, 2**21, 2**28, 2**31 - 1, 2**31,
              2**32 - 1, 2**32, 2**35, 2**42, 2**49, 2**56, 2**63 - 1, 2**63, 2**64 - 1, 2**64, 2**70 - 1,
              2**70, 2**77, 2**127 - 1, 2**127, 2**128 - 1]
    for value in values + [rng.getrandbits(rng.randint(1, 128)) for _ in range(200)]:
        rec.encode(value)
        encoded = _varint(value)
        for offset in (0, 1, 3):
            rec.varint(b"\x01\x02\x03"[:offset] + encoded + b"\x05", offset)
        rec.varint(encoded[:-1], 0)
    for value in (-1, -128, -(2**70)):
        rec.encode(value)
    for data, offset in [(b"", 0), (b"\x80", 0), (b"\x80" * 9 + b"\x01", 0), (b"\x80" * 10 + b"\x01", 0),
                         (b"\xff" * 10, 0), (b"\xff" * 9 + b"\x7f", 0), (b"\xff" * 9 + b"\x7f", 1),
                         (b"\x00", 1), (b"\x00", 5), (b"\x81\x80\x80\x00", 0), (b"\x05", 0),
                         (b"\x03\x80", -1), (b"\x05", -2), (b"", -1)]:
        rec.varint(data, offset)

    good = _record(b"key", "Translation".encode()) + _record("名字".encode(), "名".encode())
    tables = [
        b"", good, _record(b"", b""), _record(b"k", b"t") * 3,
        _ld(1, _ld(2, b"t") + _ld(1, b"k")),                       # translation first
        _ld(1, _ld(1, b"k") + _ld(1, b"k2") + _ld(2, b"t")),        # duplicate key
        _ld(1, _ld(1, b"k")), _ld(1, _ld(2, b"t")), _ld(1, b""),    # missing fields
        _ld(1, _ld(1, b"k") + _ld(2, b"t") + _ld(3, b"x")),         # unknown string field
        _ld(1, _ld(1, b"k") + _ld(2, b"t") + _varint(3 << 3) + b"\x05"),  # unknown varint field
        _ld(1, _ld(1, b"k") + _varint(2 << 3) + b"\x01" + _ld(2, b"t")),  # field 2 as a varint
        _ld(1, _ld(1, b"k") + _ld(2, b"t")) + _ld(2, b"zz"),        # extra top-level string
        _ld(1, _ld(1, b"k") + _ld(2, b"t")) + _varint(3 << 3) + b"\x07",
        _ld(1, _ld(1, b"k") + _ld(2, b"t")) + _varint(4 << 3 | 1) + b"12345678",
        _ld(1, _ld(1, b"k") + _ld(2, b"t")) + _varint(4 << 3 | 5) + b"1234",
        _varint(4 << 3 | 1) + b"1234567", _varint(4 << 3 | 5) + b"123",   # truncated fixed
        _varint(1 << 3 | 3) + b"\x00", _varint(1 << 3 | 4), _varint(1 << 3 | 6), _varint(1 << 3 | 7),
        b"\x00\x00", b"\x02\x00", b"\x0a", b"\x0a\x05abc", b"\x0a\x80", b"\x0a" + b"\xff" * 10 + b"\x01",
        _varint(2**64 << 3 | 2) + b"\x00", _varint(2**66 | 2) + b"\x01x",
        _ld(1, _ld(1, b"\xff") + _ld(2, b"t")), _ld(1, _ld(1, b"k") + _ld(2, b"\xc3")),
        _ld(1, _ld(1, b"ok\xe2\x82") + _ld(2, b"t")), _ld(1, _ld(1, b"\xe2\x28\xa1") + _ld(2, b"t")),
        _ld(1, _ld(1, b"\xed\xa0\x80") + _ld(2, b"t")), _ld(1, _ld(1, b"\xf0\x9f\x98") + _ld(2, b"t")),
        _ld(1, _ld(1, b"\xf4\x90\x80\x80") + _ld(2, b"t")), _ld(1, _ld(1, b"\xc0\xaf") + _ld(2, b"t")),
        _ld(1, _ld(1, b"\xe0\x80\x80") + _ld(2, b"t")), _ld(1, _ld(1, b"a\x80b") + _ld(2, b"t")),
        _ld(1, _ld(1, b"\xf0\x9f\x98\x80") + _ld(2, "é\x00\n ".encode())),
        _ld(1, _ld(1, b"k") + _ld(2, b"t") + b"\x0a\x09"),          # inner truncated
        _ld(1, b"\x00\x01"), _ld(1, b"\x0b"),                       # inner field zero, inner group
        _ld(1, _ld(18, b"x")), _ld(1, _ld(1, b"k") + _ld(2, b"t") + _ld(1, b"k")),
    ]
    for table in tables:
        rec.table(table)
    for _ in range(400):
        rec.table(bytes(rng.getrandbits(8) for _ in range(rng.randint(0, 40))))
    for _ in range(200):
        parts = [_record(bytes(rng.getrandbits(8) for _ in range(rng.randint(0, 6))),
                         bytes(rng.getrandbits(8) for _ in range(rng.randint(0, 6)))) for _ in range(rng.randint(1, 4))]
        rec.table(b"".join(parts))


def mutations(rec: Recorder, table: bytes, rng: random.Random) -> None:
    if not table:
        return
    for cut in {len(table) - 1, len(table) // 2, rng.randrange(len(table))}:
        rec.table(table[:cut])
    flipped = bytearray(table)
    flipped[rng.randrange(len(table))] ^= 1 << rng.randrange(8)
    rec.table(bytes(flipped))


def capture_tables(rec: Recorder, run, rng: random.Random) -> None:
    tables: dict[str, bytes] = {}
    kept = 0
    translate = rec.adaptive.translate_table

    def tapped(raw, asset, catalog, *, build_output=True):
        nonlocal kept
        name = hashlib.sha256(raw).hexdigest()
        if name not in tables and kept + len(raw) <= TAP_BUDGET:
            tables[name] = bytes(raw)
            kept += len(raw)
        rec.translation(raw, asset, catalog, translate)
        return translate(raw, asset, catalog, build_output=build_output)

    rec.adaptive.translate_table = tapped
    try:
        run()
    finally:
        rec.adaptive.translate_table = translate
    print(f"{len(tables)} distinct tables, {kept:,} bytes", flush=True)
    for name in sorted(tables):
        rec.table(tables[name])
        mutations(rec, tables[name], rng)


def run_pipeline(rest: list[str]) -> None:
    sys.argv = [str(ROOT / "tools" / "build_device_patch.py"), *rest]
    try:
        runpy.run_path(sys.argv[0], run_name="__main__")
    except SystemExit as stop:
        if stop.code:
            raise


def capture_validation(rec: Recorder, rng: random.Random) -> None:
    from wxq_patch.gemini import validate_translation

    def keep(source: str, target: str | None) -> None:
        rec.write("validate_translation", [source, target], None,
                  {"ok": validate_translation(source, target)})

    for folder in ("catalog", "catalog_id"):
        with gzip.open(ROOT / "resources" / folder / "catalog.json.gz", "rt", encoding="utf-8") as handle:
            catalog = json.load(handle)
        for source, target in catalog["unique"].items():
            keep(source, target)
        for _, _, source, target in catalog["contextual"]:
            keep(source, target)
        for _, _, previous, target, *source in catalog.get("english_updates", []):
            keep(source[0] if source else previous, target)

    samples = ["", None, "\x1c\x1f", "\x85　", "中文", "汉<bold=汉>", "<b=汉>x</b>", "<{汉}>", "{汉}",
               "{{汉}}", "{x}{x}", "{y}{x}", "<b>%d</b>", "</>", "%d%%", "%dmg", "%dÉ", "%０.２f",
               "%١$s", "%2$*s", "%%a", "%😀", "%+٠.𝟘f", "╀", "╿", "a;a", "abcd", "x" * 49]
    for source in samples:
        if source is not None:
            for target in samples:
                keep(source, target)
    chars = "0123456789-%* +.#uacsnEAe/$" "{}汉😀\n١𝟘"
    for _ in range(1500):
        source = "%" + "".join(rng.choices(chars, k=rng.randint(0, 24)))
        keep(source, source[1:])


def capture_qts(rec: Recorder, root: pathlib.Path) -> None:
    from wxq_patch import qtsvfs
    from qts_relocate import install_btree_slot_map

    def record_selection(path: pathlib.Path, stock: dict, selected: dict) -> None:
        inputs = bytearray()
        digest = hashlib.sha256()
        replacements = 0
        fields = tuple(qtsvfs.ChunkSlot.__annotations__)[1:]
        for asset, chunks in stock.items():
            for chunk_id, slot in chunks.items():
                inputs += struct.pack("<QIQI", asset, chunk_id, slot.slot_offset, slot.hash1 & 0xFFFFFFFF)
                current = selected[asset][chunk_id]
                if current != slot:
                    digest.update(struct.pack("<11Q", *(getattr(current, f) for f in fields)))
                    replacements += 1
        rec.write("qts.live_replacements", [str(path.resolve())], inputs,
                  {"ok": [replacements, digest.hexdigest()]})

    def package_cases() -> None:
        stock_builder = qtsvfs.QtsPackage.build_slot_map
        install_btree_slot_map()
        seen_shapes = set()
        for index in files:
            if index.stem != index.parent.name:
                continue
            package = qtsvfs.QtsPackage(index.parent)
            stock = stock_builder(package)
            selected = package.build_slot_map()
            if len(package.shard_paths) == 1:
                record_selection(package.shard_paths[0], stock, selected)
            for asset, entry in package.entries.items():
                chunks = selected.get(asset, {})
                shape = (package.package_id, entry.compression, min(2, len(chunks)))
                if shape in seen_shapes:
                    continue
                seen_shapes.add(shape)
                record_extract(package, asset, selected)

        first, second = 106_496, 106_560
        page, table, key = 4096, 256, 55
        for name, live, second_asset in [
            ("repointed", second, 100),
            ("still-live", first, 100),
            ("missing-candidate", second, 101),
        ]:
            path = (rec.blobs.parent / f"{name}.bin").resolve()
            data = bytearray(second + 64)
            struct.pack_into("<I", data, 8, len(data))
            struct.pack_into("<I", data, 0x30, table)
            struct.pack_into("<I", data, table + 4, 1)
            struct.pack_into("<II", data, table + 24, 1, page)
            struct.pack_into("<I", data, page, key)
            struct.pack_into("<I", data, page + 2040, live)
            struct.pack_into("<4I", data, page + 4080, 1, 0, 0, 0x30001)
            for offset, asset in [(first, 100), (second, second_asset)]:
                struct.pack_into("<IiIQIII", data, offset, offset, -1, 64, key, 0, 8, 4)
                struct.pack_into("<QII", data, offset + 36, asset, 0, 0)
            path.write_bytes(data)
            package = SimpleNamespace(shard_paths=[path])
            stock = stock_builder(package)
            selected = qtsvfs.QtsPackage.build_slot_map(package)
            record_selection(path, stock, selected)

    def record_extract(package, asset: int, slots: dict) -> None:
        chunks = {
            key: [str(slot.shard_path.resolve()), slot.payload_offset,
                  slot.compressed_size, slot.uncompressed_size]
            for key, slot in slots.get(asset, {}).items()
        }
        try:
            raw = package.extract(asset, slots)
            result = {"ok": [len(raw), hashlib.sha256(raw).hexdigest()]}
        except (ValueError, OSError) as error:
            result = {"error": _error(error)}
        rec.write("qts.extract", [asset, package.entries[asset].compression, chunks], None, result)

    def record(name: str, path: pathlib.Path, fields: tuple, reserved: bool = False) -> None:
        digest = hashlib.sha256()
        try:
            if name == "qts.index":
                rows = qtsvfs.parse_index(path).values()
            else:
                rows = qtsvfs.iter_chunk_slots(path, include_reserved_variants=reserved)
            count = 0
            for row in rows:
                digest.update(struct.pack("<" + "Q" * len(fields), *(getattr(row, f) for f in fields)))
                count += 1
            result = {"ok": [count, digest.hexdigest()]}
        except Exception as exc:  # noqa: BLE001
            result = {"error": _error(exc)}
        rec.write(name, [str(path.resolve()), reserved], None, result)

    files = sorted(root.rglob("*.db"))
    if not files:
        raise ValueError(f"no QtsVFS databases in {root}")
    for path in files:
        if path.stem == path.parent.name:
            record("qts.index", path, tuple(qtsvfs.IndexEntry.__annotations__))
        elif path.stem.startswith(path.parent.name + "_"):
            fields = tuple(qtsvfs.ChunkSlot.__annotations__)[1:]
            for reserved in (False, True):
                record("qts.slots", path, fields, reserved)

    package_cases()

    import lz4.block

    path = rec.blobs.parent / "synthetic-shard.bin"
    packed = lz4.block.compress(b"stored and compressed chunks", store_size=False)
    path.write_bytes(b"xyz" + packed)
    for compression, coords in [
        (0, []),
        (0, [(2, 0, 3, 3)]),
        (0, [(0, 0, 3, 3), (2, 999, 3, 3)]),
        (0, [(0, 0, 3, 3), (1, 1, 2, 2)]),
        (0, [(0, 999, 3, 3)]),
        (0, [(0, 0, 3, 4)]),
        (9, [(0, 0, 3, 3)]),
        (1, [(0, 3, len(packed), 28)]),
        (1, [(0, 3, len(packed), 29)]),
    ]:
        asset = 1
        package = SimpleNamespace(entries={asset: SimpleNamespace(compression=compression)})
        package.extract = qtsvfs.QtsPackage.extract.__get__(package)
        slots = {asset: {
            key: SimpleNamespace(shard_path=path.resolve(), payload_offset=offset,
                                 compressed_size=compressed, uncompressed_size=uncompressed)
            for key, offset, compressed, uncompressed in coords
        }}
        record_extract(package, asset, slots)

    def position_cases(data: bytes, before: list[tuple[int, int]], after: list[tuple[int, int]]) -> None:
        def slots(items):
            return [SimpleNamespace(slot_offset=offset, hash1=key) for offset, key in items]

        trial = bytearray(data)
        try:
            result = {"ok": qtsvfs.insert_slot_position_references(trial, slots(before), slots(after))}
        except Exception as exc:  # noqa: BLE001
            result = {"error": _error(exc)}
        result["bytes"] = hashlib.sha256(trial).hexdigest()
        rec.write("qts.insert_positions", [before, after], data, result)

    # Two copies of a small index leaf. Offsets are independent of the synthetic page storage.
    before = [(20000 + i * 64, 100 + i * 4) for i in range(15)]

    def pages(count: int = 2, *, prefix: int = 0, close_end: bool = False) -> bytes:
        data = bytearray(count * 4096 + prefix)
        for page in range(count):
            at = prefix + page * 4096
            for i, (offset, key) in enumerate(before):
                struct.pack_into("<I", data, at + i * 4, key)
                struct.pack_into("<I", data, at + 2040 + i * 4, offset)
            struct.pack_into("<I", data, at + 4092, 0x30000 | len(before))
            if close_end:
                struct.pack_into("<I", data, at + 2040 + len(before) * 4, 8)
        return bytes(data)

    data = pages()
    offsets = [offset for offset, _ in before]
    wanted = [20000, 20256, 20896, 1]
    rec.write("qts.find_positions", [offsets, wanted], data,
              {"ok": qtsvfs.find_slot_position_references(data, offsets, wanted)})
    for payload, existing, added in [
        (data, before, [(30000, 126)]),
        (data, before, [(30000, 98), (30064, 158)]),
        (data, before, [(30000, 100)]),
        (data, [], [(30000, 100)]),
        (data, before[:3], [(30000, 101)]),
        (pages(1), before, [(30000, 126)]),
        (pages(prefix=4, close_end=True), before, [(30000, 126)]),
        (pages(close_end=True), before, [(30000, 126)]),
        (data, before, [(30000, 126), (30064, 126)]),
    ]:
        position_cases(payload, existing, added)


def capture_metadata(rec: Recorder, out: pathlib.Path, index: pathlib.Path) -> None:
    from wxq_patch import package_metadata as metadata

    def lookup(path: pathlib.Path, name: str) -> None:
        try:
            result = {"ok": metadata.find_package_hash_entry(path, name)}
        except ValueError as exc:
            result = {"error": _error(exc)}
        rec.write("package_metadata.find", [str(path), name], path.read_bytes(), result)

    for name in ("", "0", "1", "10", "15", "19", "20", "21", "1050016095", "absent"):
        lookup(index, name)
    prefix = b"QTSF_PACKAGE\0xxINGQ"
    item = b"\x03\0\0\0abc\0" + struct.pack("<Q", 2**64 - 1)
    path = out / "synthetic-index.db"
    for contents in (
        b"", prefix[:-4], prefix + item, prefix + item + b"\0" * 17,
        prefix + item * 2 + b"\0" * 17, prefix + item.replace(b"abc", b"a c") + b"\0" * 17,
        prefix + item.replace(b"abc\0", b"abc!") + b"\0" * 17,
    ):
        path.write_bytes(contents)
        lookup(path, "abc")


def catalog_state(catalog) -> str:
    """The SHA-256 of an ``adaptive.Catalog``'s state: each dict in its order, each set sorted."""
    out = bytearray()

    def section(tag: bytes, items: list[bytes]) -> None:
        out.extend(tag + struct.pack("<Q", len(items)) + b"".join(items))

    section(b"U", [_bytes(k.encode()) + _bytes(v.encode()) for k, v in catalog.unique.items()])
    section(b"C", [b"".join(_bytes(p.encode()) for p in (*ident, target)) for ident, target in catalog.context.items()])
    section(b"E", [b"".join(_bytes(p.encode()) for p in (*ident, target, catalog.english_sources[ident]))
                   for ident, target in catalog.english_updates.items()])
    section(b"K", [h.to_bytes(16, "little", signed=True) for h in sorted(catalog.known)])
    section(b"G", [h.to_bytes(16, "little", signed=True)
                   + _bytes(json.dumps(g, ensure_ascii=False, separators=(",", ":")).encode())
                   for h, g in catalog.graphics.items()])
    section(b"T", [_bytes(t.encode()) for t in sorted(catalog.targets)])
    return hashlib.sha256(out).hexdigest()


def capture_catalog(rec: Recorder, folders: list[pathlib.Path], rng: random.Random) -> None:
    """``adaptive.Catalog`` (``__init__``, ``lookup``) and ``load_catalog``: the runtime's own loader
    on each shipped catalog, ``Catalog(data)`` on the data the apps build it from (after
    ``engine_hooks``' supplement, admissions, glossary and English updates), and generated shapes."""
    import catalog_supplement
    import catalog_updates
    import terminology
    from languages import for_catalog

    adaptive = rec.adaptive

    def build(name: str, data) -> None:
        blob = json.dumps(data, ensure_ascii=False).encode("utf-8")
        try:
            catalog = adaptive.Catalog(json.loads(blob))
        except Exception as exc:  # noqa: BLE001 - the class and message are the recording
            rec.write("adaptive.Catalog", [name], blob, {"error": _error(exc)})
            return
        rec.write("adaptive.Catalog", [name], blob, {"ok": catalog_state(catalog)})
        sources = list(catalog.unique)
        probes = [(ident[0], ident[1], ident[2]) for ident in catalog.context]
        probes += [("00BF2528D217FFFA", "#K#", s) for s in rng.sample(sources, min(150, len(sources)))]
        probes += [("0000000000000001", "k", "no such source"), ("", "", "")]
        for asset_hex, key, source in probes:
            for asset in {int(asset_hex, 16) if asset_hex else 0, 1, -1, 2**64 + 5}:
                rec.write("adaptive.Catalog.lookup", [name, str(asset), key, source], blob,
                          {"ok": catalog.lookup(asset, key, source)})

    for folder in folders:
        try:
            rec.write("adaptive.load_catalog", [str(folder)], None, {"ok": catalog_state(adaptive.load_catalog(folder))})
        except Exception as exc:  # noqa: BLE001
            rec.write("adaptive.load_catalog", [str(folder)], None, {"error": _error(exc)})
        if not (folder / "catalog.json.gz").is_file():
            continue
        with gzip.open(folder / "catalog.json.gz", "rt", encoding="utf-8") as handle:
            data = json.load(handle)
        build(f"{folder.name}:shipped", json.loads(json.dumps(data)))
        language = for_catalog(folder)
        catalog_supplement.apply(data, language.code)
        catalog_updates.admit_tables(data)
        terminology.apply(data, language.terms)
        catalog_updates.apply(data, language.code)
        build(f"{folder.name}:edited", data)

    base = {"schema": 1, "unique": {"源": "Source", "名": "Name", "dup": "Source"},
            "contextual": [["000000000000000A", "#K1#", "源", "Context source"],
                           ["000000000000000A", "#K1#", "源", "Context source"],
                           ["-000000000000001", "k", "x", "Negative asset"],
                           ["00000000000000AB", "#K2#", "名", "Name here"]],
            "english_updates": [["000000000000000A", "#K1#", "Old", "New"],
                                ["000000000000000A", "#K1#", "Old", "New", "旧"],
                                ["000000000000000B", "#K3#", "Prev", "Next", "源"]],
            "table_hashes": ["00BF2528D217FFFA", " 0a\n", "0x0A", "+f", "-1", "0_a", "0x_a", "abcdef", "ABCDEF"],
            "graphics": [{"hash": "0A", "label": "first", "n": [1, 2]}, {"hash": "0B", "flag": True},
                         {"hash": "0x0a", "label": "second wins at first place", "text": "é\n\"\\\u0001"}]}

    def variant(**changes):
        data = json.loads(json.dumps(base))
        for key, value in changes.items():
            if value is KeyError:
                data.pop(key)
            else:
                data[key] = value
        return data

    cases = {
        "base": base, "schema-true": variant(schema=True), "schema-float": variant(schema=1.0),
        "schema-2": variant(schema=2), "schema-text": variant(schema="1"), "schema-null": variant(schema=None),
        "no-schema": variant(schema=KeyError), "no-unique": variant(unique=KeyError),
        "no-contextual": variant(contextual=KeyError), "no-updates": variant(english_updates=KeyError),
        "no-hashes": variant(table_hashes=KeyError), "no-graphics": variant(graphics=KeyError),
        "short-row": variant(contextual=[["A", "k", "s"]]), "long-row": variant(contextual=[["A", "k", "s", "t", "u"]]),
        "empty-row": variant(contextual=[[]]),
        "conflict": variant(contextual=[["A", "k", "s", "t"], ["A", "k", "s", "u"]]),
        "update-3": variant(english_updates=[["A", "k", "p"]]),
        "update-6": variant(english_updates=[["A", "k", "p", "t", "b", "x"]]),
        "update-conflict": variant(english_updates=[["A", "k", "p", "t"], ["A", "k", "p", "u", "b"]]),
        "update-source-overwritten": variant(english_updates=[["A", "k", "p", "t", "b1"], ["A", "k", "p", "t", "b2"]]),
        "hashes-int": variant(table_hashes=5), "hashes-null": variant(table_hashes=None),
        "hash-int": variant(table_hashes=[5]), "graphics-null": variant(graphics=None),
        "graphic-no-hash": variant(graphics=[{"label": "x"}]), "graphic-list": variant(graphics=[["0A"]]),
        "graphic-text": variant(graphics=["0A"]), "graphic-int": variant(graphics=[7]),
        "graphic-null": variant(graphics=[None]), "graphic-hash-int": variant(graphics=[{"hash": 10}]),
        "data-list": [1], "data-text": "schema", "data-int": 3, "data-null": None,
    }
    for literal in ["", " ", "zz", "it's", "a\"b'", "0x", "0X", "_1", "1_", "1__2", "0x__1", "0x_", "- 1", "+-1",
                    "0x-1", "1 2", " 1　", "\x1c1\x1f", "1 ", "g" * 250, "é", "\t"]:
        cases[f"hash {literal!r}"] = variant(table_hashes=[literal])
        cases[f"graphic hash {literal!r}"] = variant(graphics=[{"hash": literal}])
    for name, data in cases.items():
        build(name, data)


def _edited_catalog(folder: pathlib.Path) -> dict:
    """The catalog data ``engine_hooks``' ``load_catalog`` builds ``Catalog`` from."""
    import catalog_supplement
    import catalog_updates
    import terminology
    from languages import for_catalog

    with gzip.open(folder / "catalog.json.gz", "rt", encoding="utf-8") as handle:
        data = json.load(handle)
    language = for_catalog(folder)
    catalog_supplement.apply(data, language.code)
    catalog_updates.admit_tables(data)
    terminology.apply(data, language.terms)
    catalog_updates.apply(data, language.code)
    return data


BASE = 106_496


def _index(entries) -> bytes:
    """A QtsVFS index: one 84-byte entry per ``(hash, compression, chunk_size, size)``."""
    data = bytearray(BASE)
    for file_hash, compression, chunk_size, size in entries:
        entry = bytearray(84)
        struct.pack_into("<IiI", entry, 0, len(data), -1, len(entry))
        struct.pack_into("<I", entry, 24, 48)
        struct.pack_into("<I", entry, 44, size)
        struct.pack_into("<HHIQ", entry, 68, compression, 0, chunk_size, file_hash)
        data += entry
    struct.pack_into("<I", data, 8, len(data))
    return bytes(data)


def _shard(slots, live="all", table=256, page=4096) -> bytes:
    """A shard of ``(file_hash, chunk_id, payload, uncompressed_size, hash1)`` slots.

    ``live`` is the B-tree leaf: ``"all"`` lists every slot, a list gives ``(key, offset)`` rows by
    slot index (``("slot", i)``) or as numbers, ``None`` writes no page table, ``"count"`` an
    over-full leaf and ``"short"`` a page past the end."""
    data = bytearray(BASE)
    offsets = []
    for file_hash, chunk_id, payload, size, hash1 in slots:
        body = (32 + len(payload) + 3) & ~3
        slot = bytearray(max(body + 16, 48))
        struct.pack_into("<IiI", slot, 0, len(data), -1, len(slot))
        struct.pack_into("<QIII", slot, 12, hash1, 0, len(payload) + 4, size)
        slot[32:32 + len(payload)] = payload
        struct.pack_into("<QII", slot, len(slot) - 16, file_hash, 0, chunk_id)
        offsets.append((hash1 & 0xFFFFFFFF, len(data)))
        data += slot
    struct.pack_into("<I", data, 8, len(data))
    if live is None:
        return bytes(data)
    rows = offsets if live in ("all", "count", "short") else [
        offsets[item[1]] if isinstance(item, tuple) else item for item in live]
    struct.pack_into("<I", data, 0x30, table)
    if table + 8 > len(data):
        return bytes(data[:table])
    struct.pack_into("<I", data, table + 4, 1)
    struct.pack_into("<II", data, table + 24, 1, len(data) - 100 if live == "short" else page)
    if live == "short":
        return bytes(data)
    for i, (key, offset) in enumerate(rows):
        struct.pack_into("<I", data, page + i * 4, key)
        struct.pack_into("<I", data, page + 2040 + i * 4, offset)
    count = 600 if live == "count" else len(rows)
    struct.pack_into("<4I", data, page + 4080, 1, 0, 0, 0x30000 | count)
    return bytes(data)


def _scan_fixtures(root: pathlib.Path) -> list[tuple[pathlib.Path, dict]]:
    """Synthetic games for every path ``discover`` and ``scan`` take, each with its catalog."""
    import lz4.block

    def lz4_block(data: bytes) -> bytes:
        return lz4.block.compress(data, store_size=False)

    def sha(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def text(*pairs) -> bytes:
        return b"".join(_record(k.encode(), v.encode()) for k, v in pairs)

    def package(game, name, index, shards):
        folder = game / "WXQ_Data" / "Package" / "builtin" / name
        folder.mkdir(parents=True, exist_ok=True)
        if index is not None:
            (folder / f"{name}.db").write_bytes(index)
        for shard, data in shards.items():
            (folder / shard).write_bytes(data)
        return folder

    hello, bye = text(("k1", "你好"), ("k2", "再见")), text(("k3", "再见"))
    art, art2, new_art = b"chinese art bytes", b"older art bytes!!", b"english art"
    ranged = bytearray(art2)
    ranged[2:5], ranged[8:10] = b"ENG", b"XY"
    assets = root / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "c.bin").write_bytes(new_art)
    (assets / "f.bin").write_bytes(b"ENGXY")
    known = [0x10, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x1C, 0x1D, 0x1E, 0x30, 0x80, 0x91, 0xA0, 0xC0, 0xD0, 0xE0]
    graphics = [
        {"hash": "12", "source_sha256": sha(art), "patched_sha256": sha(new_art), "payload": "c.bin"},
        {"hash": "13", "source_sha256": sha(art), "patched_sha256": sha(new_art), "payload": "c.bin"},
        {"hash": "14", "source_sha256": sha(b"x"), "patched_sha256": sha(b"y"), "payload": "c.bin",
         "previous_sha256": [sha(b"z")]},
        {"hash": "15", "source_sha256": sha(b"x"), "patched_sha256": sha(bytes(ranged)), "payload": "f.bin",
         "previous_sha256": [sha(b"z"), sha(art2)], "patch_ranges": [[2, 3], [8, 2]]},
        {"hash": "20", "source_sha256": sha(art), "patched_sha256": sha(new_art), "payload": "c.bin"},
    ]
    catalog = {"schema": 1, "unique": {"你好": "Hello", "再见": "Goodbye"}, "contextual": [],
               "english_updates": [], "table_hashes": [f"{h:X}" for h in known], "graphics": graphics}
    games = []

    game = root / "game-a"
    old, new = b"\x0a\xff\xff", lz4_block(hello)
    half = len(hello) // 2
    first, second = lz4_block(hello[:half]), lz4_block(hello[half:])
    slots = [
        (0x10, 0, lz4_block(hello), len(hello), 0x1010),
        (0x11, 0, lz4_block(bye), len(bye), 0x1011),
        (0x12, 0, lz4_block(art), len(art), 0x1012),
        (0x13, 0, lz4_block(new_art), len(new_art), 0x1013),
        (0x14, 0, lz4_block(b"other"), 5, 0x1014),
        (0x15, 0, lz4_block(art2), len(art2), 0x1015),
        (0x16, 1, lz4_block(hello), len(hello), 0x1016),
        (0x17, 0, lz4_block(hello), len(hello), 0x1017),
        (0x18, 0, lz4_block(b"\x0a\xff"), 2, 0x1018),
        (0x19, 0, hello, len(hello), 0x1019),
        (0x1A, 0, lz4_block(old), len(old), 0x101A),
        (0x1A, 0, new, len(hello), 0x101A),
        (0x1B, 0, lz4_block(text(("k", "plain"))), len(text(("k", "plain"))), 0x101B),
        (0x1D, 0, first, half, 0x101D),
        (0x1D, 1, second, len(hello) - half, 0x111D),
        (0x1E, 0, lz4_block(hello), len(hello), 0x101E),
        (0x20, 0, art, len(art), 0x1020),
    ]
    live = [("slot", i) for i in range(len(slots)) if i != 10]
    package(game, "1", _index([
        (0x10, 1, 0, len(hello)), (0x11, 1, 0, len(bye)), (0x12, 1, 0, len(art)), (0x13, 1, 0, len(new_art)),
        (0x14, 1, 0, 5), (0x15, 1, 0, len(art2)), (0x16, 1, 0, len(hello)), (0x17, 1, 0, len(hello) + 1),
        (0x18, 1, 0, 2), (0x19, 0, 0, len(hello)), (0x1A, 1, 0, len(hello)), (0x1B, 1, 0, len(text(("k", "plain")))),
        (0x1C, 1, 0, 4), (0x1D, 1, half, len(hello)), (0x1E, 9, 0, len(hello)), (0x20, 0, 0, len(art)),
    ]), {"1_1.db": _shard(slots, live)})
    package(game, "2", _index([(0x90, 1, 0, 4)]), {"2_1.db": _shard([(0x90, 0, lz4_block(b"abcd"), 4, 1)])})
    package(game, "3", _index([(0x30, 1, 0, len(hello))]), {
        "3_10.db": _shard([(0x30, 0, lz4_block(hello), len(hello), 0x3030)], None),
        "3_2.db": _shard([(0x30, 0, lz4_block(bye), len(hello), 0x3031)], None),
    })
    package(game, "4", None, {})
    package(game, "5", b"\0" * 100, {})
    empty_index = bytearray(BASE + 400)
    struct.pack_into("<I", empty_index, 8, len(empty_index))
    package(game, "6", bytes(empty_index), {})
    (game / "WXQ_Data" / "Package" / "builtin" / "7").write_bytes(b"a file")
    package(game, "abc", _index([(0x10, 1, 0, 1)]), {})
    package(game, "8", _index([(0x80, 1, 0, len(hello))]),
            {"8_1.db": _shard([(0x80, 0, lz4_block(hello), len(hello), 0x8080)], None)})
    folder = package(game, "9", _index([(0x91, 1, 0, len(hello))]),
                     {"9_1.DB": _shard([(0x91, 0, lz4_block(hello), len(hello), 0x9191)]), "9_x.txt": b"x"})
    (folder / "9_d.db").mkdir(exist_ok=True)
    package(game, "10", _index([(0xA0, 1, 0, len(hello))]), {})
    package(game, "11", b"", {})
    package(game, "12", _index([(0xC0, 1, 0, len(hello))]),
            {"12_1.db": _shard([(0xC0, 0, lz4_block(hello), len(hello), 0xC0C0)], "all", table=10**6)})
    package(game, "13", _index([(0xD0, 1, 0, len(hello))]),
            {"13_1.db": _shard([(0xD0, 0, lz4_block(hello), len(hello), 0xD0D0)], "count")})
    package(game, "14", _index([(0xE0, 1, 0, len(hello))]),
            {"14_1.db": _shard([(0xE0, 0, lz4_block(hello), len(hello), 0xE0E0)], "short")})
    games.append((game, catalog))

    games.append((root / "game-b", catalog))
    (root / "game-b" / "WXQ_Data" / "Package").mkdir(parents=True, exist_ok=True)

    game = root / "game-c"
    package(game, "1", _index([(0x10, 1, 0, len(hello))]), {"1_1.db": b""})
    games.append((game, catalog))

    def graphic_game(name: str, entry: dict) -> None:
        game = root / name
        package(game, "1", _index([(0x12, 1, 0, len(art))]),
                {"1_1.db": _shard([(0x12, 0, lz4_block(art), len(art), 0x1012)])})
        data = json.loads(json.dumps(catalog))
        data["graphics"] = [{"hash": "12", "source_sha256": sha(art), **entry}]
        games.append((game, data))

    graphic_game("game-d", {"patched_sha256": sha(new_art), "payload": "missing.bin"})
    graphic_game("game-e", {"patched_sha256": sha(new_art), "payload": "c.bin", "patch_ranges": [[0, 99]]})
    graphic_game("game-f", {"payload": "c.bin"})
    graphic_game("game-g", {"patched_sha256": sha(b"not it"), "payload": "c.bin"})
    graphic_game("game-h", {"patched_sha256": sha(new_art), "payload": "c.bin", "patch_ranges": [[0, 3]]})
    return games


def capture_scan(rec: Recorder, work_root: pathlib.Path, targets: list[tuple[pathlib.Path, pathlib.Path | None]]) -> None:
    """``adaptive.discover`` and ``adaptive.scan`` (both ``materialize`` values) as the mobile
    pipeline runs them: ``qts_relocate``'s B-tree slot map installed, ``load_catalog`` giving the
    catalog the apps build. Each target is a game and a catalog folder; synthetic fixtures follow."""
    import shutil

    import qts_relocate

    adaptive = rec.adaptive
    qts_relocate.install_btree_slot_map()
    original_loader = adaptive.load_catalog

    def file_hash(path: pathlib.Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def run(name: str, game: pathlib.Path, assets: pathlib.Path, data: dict) -> None:
        blob = json.dumps(data, ensure_ascii=False).encode("utf-8")
        adaptive.load_catalog = lambda folder: adaptive.Catalog(json.loads(blob))
        try:
            catalog = adaptive.load_catalog(assets)
            try:
                packages, skipped = adaptive.discover(game, catalog)
                result = {"ok": [[[p.package_id, str(p.index_path), [str(s) for s in p.shard_paths],
                                   hashlib.sha256(",".join(f"{h:016X}" for h in p.entries).encode()).hexdigest()]
                                  for p in packages], skipped]}
            except Exception as exc:  # noqa: BLE001 - the class and message are the recording
                result = {"error": _error(exc)}
            rec.write("adaptive.discover", [name, str(game)], blob, result)
            for materialize in (False, True):
                work = work_root / f"{len(rec.seen)}"
                shutil.rmtree(work, ignore_errors=True)
                qts_relocate.BTREE_FALLBACKS.clear()
                try:
                    plans, fingerprints, total, skipped = adaptive.scan(game, assets, work, materialize=materialize)
                    written = sorted([str(p.relative_to(work)), file_hash(p)] for p in work.rglob("*") if p.is_file())
                    result = {"ok": {
                        "plans": [[package.package_id, str(replacements.relative_to(work)),
                                   [[f"{h:016X}", list(counts.items())] for h, counts in per_asset.items()]]
                                  for package, replacements, per_asset in plans],
                        "fingerprints": list(fingerprints.items()), "total": list(total.items()),
                        "skipped": skipped, "written": written,
                        "fallbacks": list(qts_relocate.BTREE_FALLBACKS.items())}}
                except Exception as exc:  # noqa: BLE001
                    result = {"error": _error(exc)}
                rec.write("adaptive.scan", [name, str(game), str(assets), materialize], blob, result)
                shutil.rmtree(work, ignore_errors=True)
                print(f"scan {name} materialize={materialize}: {str(result)[:160]}", flush=True)
        finally:
            adaptive.load_catalog = original_loader

    for game, folder in targets:
        run(f"{game.name}:{folder.name}", game, folder, _edited_catalog(folder))
    fixtures = (rec.blobs.parent / "fixtures").resolve()
    shutil.rmtree(fixtures, ignore_errors=True)
    for game, data in _scan_fixtures(fixtures):
        run(game.name, game, fixtures / "assets", data)


def main() -> int:
    argv = sys.argv[1:]
    scan = None
    qts = None
    metadata = None
    catalogs = None
    scan_targets = None
    if len(argv) == 2 and argv[0] in ("--generated", "--validation"):
        out, rest = pathlib.Path(argv[1]), None
    elif len(argv) >= 3 and argv[0] == "--tap" and argv[2] == "--":
        out, rest = pathlib.Path(argv[1]), argv[3:]
    elif len(argv) == 4 and argv[0] == "--scan":
        out, game, catalog = map(pathlib.Path, argv[1:])
        rest, scan = None, (game, catalog)
    elif len(argv) == 3 and argv[0] == "--qts":
        out, qts = map(pathlib.Path, argv[1:])
        rest = None
    elif len(argv) == 3 and argv[0] == "--metadata":
        out, metadata = map(pathlib.Path, argv[1:])
        rest = None
    elif len(argv) >= 3 and argv[0] == "--catalog":
        out, catalogs = pathlib.Path(argv[1]), [pathlib.Path(a) for a in argv[2:]]
        rest = None
    elif len(argv) >= 3 and argv[0] == "--scan-runtime" and len(argv) % 2 == 1:
        out, work = pathlib.Path(argv[1]), pathlib.Path(argv[2])
        pairs = [pathlib.Path(a) for a in argv[3:]]
        rest, scan_targets = None, list(zip(pairs[::2], pairs[1::2]))
    else:
        print(__doc__)
        return 2
    os.environ["HOK_CODECS"] = "python"
    rec = Recorder(out)
    rng = random.Random(20261127)
    try:
        if scan is not None:
            from engine_hooks import install
            install()
            capture_tables(rec, lambda: rec.adaptive.scan(*scan, out, materialize=False), rng)
        elif scan_targets is not None:
            capture_scan(rec, work, scan_targets)
        elif qts is not None:
            capture_qts(rec, qts)
        elif catalogs is not None:
            capture_catalog(rec, catalogs, rng)
        elif metadata is not None:
            capture_metadata(rec, out, metadata)
        elif argv[0] == "--validation":
            capture_validation(rec, rng)
        elif rest is None:
            generated(rec, rng)
        else:
            capture_tables(rec, lambda: run_pipeline(rest), rng)
    finally:
        rec.close()
    print(f"{rec.count} distinct calls -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
