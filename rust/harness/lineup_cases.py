"""The config-bin, protobuf-text, share-code and Unity cases of leaves_tap.py: ``config_bin``, ``pb_text``,
``lineup_codes`` and ``unity_text`` on real files and on synthetic ones built here, each cut short and
with bytes changed.

Real inputs are the package-``1`` config bins in ``--config-bins`` (the three lineup bins among them, from
both layers, are named ``<layer>-<HASH>.bin``) and the staged replacements. A ``translate`` callback is
named by its mode so the replay can run the same one: ``mod4`` answers by a string's length (None, the
string itself, "", or a tagged reversal), ``all`` tags every string. Results over 2 KiB are recorded as
their SHA-256 (``_blob``).

Migration tooling, run by hand: the exe, the APK and ``tools/`` never import it.
"""
from __future__ import annotations

import base64
import hashlib
import random
import struct
import zlib
from pathlib import Path

import config_bin
import lineup_codes
import pb_text
import unity_text

MODES = ("mod4", "all")


def translator(mode: str, offered: list[str]):
    def translate(text: str):
        offered.append(text)
        if mode == "all":
            return f"EN:{text}"
        n = len(text)
        return (None, text, "", f"EN{n}:{text[::-1]}")[n % 4]
    return translate


def _blob(data: bytes) -> str:
    return data.hex() if len(data) <= 2048 else "sha256:" + hashlib.sha256(data).hexdigest()


def _texts(offered: list[str]) -> list:
    """The strings offered, or their count and digest when long."""
    joined = "\0".join(offered).encode()
    return offered if len(joined) <= 2048 else [len(offered), hashlib.sha256(joined).hexdigest()]


def _value(value) -> str:
    return f"i:{value}" if isinstance(value, int) else f"b:{value.hex()}"


def _entries_digest(entries) -> str:
    text = "".join(f"{number},{wire},{_value(value)};" for number, wire, value in entries)
    return hashlib.sha256(text.encode()).hexdigest()


def _parse_entries(spec: list) -> list:
    return [(int(n), w, int(v[2:]) if v.startswith("i:") else bytes.fromhex(v[2:])) for n, w, v in spec]


def _mutations(rng: random.Random, data: bytes, count: int, flips: int = 4) -> list[bytes]:
    found = []
    for _ in range(count):
        mutated = bytearray(data)
        for _ in range(rng.randint(1, flips)):
            if mutated:
                mutated[rng.randrange(len(mutated))] = rng.randrange(256)
        found.append(bytes(mutated))
    return found


def _write(out: Path, folder: str, name: str, data: bytes) -> str:
    path = out / folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path.relative_to(out).as_posix()


# --- config_bin -------------------------------------------------------------------------------------

def _config_calls(rec, relative: str, data: bytes) -> None:
    args = {"file": relative}
    rec.call("cb_fields", args, lambda: _entries_digest(config_bin.fields(data)))
    rec.call("cb_encode", args, lambda: _blob(config_bin.encode(config_bin.fields(data))))
    rec.call("cb_rows_md5", args, lambda: config_bin.rows_md5(config_bin.fields(data)).decode())
    rec.call("cb_checksum", args, lambda: config_bin.checksum(config_bin.fields(data)))
    rec.call("cb_reseal", args, lambda: _blob(config_bin.encode(config_bin.reseal(config_bin.fields(data)))))
    rec.call("cb_is_sealed", args, lambda: config_bin.is_sealed(data))


def _entry_cases() -> list[list]:
    row = "b:" + bytes([8, 1]).hex()
    index = "b:" + bytes([10, 2, 5, 6, 18, 4, 8, 7, 16, 9]).hex()
    digest = "b:" + (b"0" * 32).hex()
    return [
        [[1, 2, digest], [2, 2, row], [3, 2, index], [4, 0, "i:0"]],
        [[1, 0, "i:3"], [2, 2, row], [4, 0, "i:0"]],
        [[1, 2, digest], [2, 2, row], [4, 2, "b:00"]],
        [[1, 2, digest], [2, 2, row], [4, 5, "b:00000000"]],
        [[1, 1, "b:0000000000000000"], [2, 2, row], [4, 0, "i:0"]],
        [[2, 2, row], [2, 0, "i:5"]],
        [[2, 0, "i:5"]],
        [[3, 0, "i:5"]],
        [[3, 2, "b:" + bytes([8, 0x80, 0x80, 0x80, 0x80, 0x10]).hex()]],
        [[3, 2, "b:" + bytes([16, 3]).hex()]],
        [[3, 2, "b:" + bytes([18, 2, 8, 0x7F]).hex()], [3, 2, "b:" + bytes([10, 1, 0x80]).hex()]],
        [[3, 2, "b:" + bytes([10, 2, 0x80, 0x80]).hex()]],
        [[3, 2, "b:" + bytes([13, 1, 2, 3, 4]).hex()]],
        [[2, 1, "b:0102030405060708"], [7, 5, "b:01020304"], [1 << 60, 0, f"i:{(1 << 70) - 1}"]],
        [[2, 3, "b:"], [4, 1, "i:7"]],
        [],
    ]


def _config(rec, out: Path, bins: list[Path]) -> None:
    rng = random.Random(23)
    for path in bins:
        data = path.read_bytes()
        relative = f"config/{path.name}"
        _write(out, "config", path.name, data)
        _config_calls(rec, relative, data)
    sample = rng.sample(bins, min(len(bins), 60))
    for path in sample:
        data = path.read_bytes()
        for index, mutated in enumerate(_mutations(rng, data, 8) + [data[: len(data) // 2], data[:-1]]):
            relative = _write(out, "config-fuzz", f"{path.stem}.{index}.bin", mutated)
            _config_calls(rec, relative, mutated)
    for raw in (b"", b"\x08", b"\x0b", b"\x00\x00", b"\x0a\x05ab", b"\x09" + b"\x01" * 8, b"\x0d\x01",
                b"\x08" + b"\xff" * 10 + b"\x01", b"\x08" + b"\xff" * 9 + b"\x01", b"\x0a" + b"\xff" * 9 + b"\x01"):
        relative = _write(out, "config-fuzz", f"synthetic-{raw.hex()}.bin", raw)
        _config_calls(rec, relative, raw)
    for spec in _entry_cases():
        for op in ("encode", "rows_md5", "checksum", "reseal"):
            def run(spec=spec, op=op):
                entries = _parse_entries(spec)
                if op == "encode":
                    return config_bin.encode(entries).hex()
                if op == "rows_md5":
                    return config_bin.rows_md5(entries).decode()
                if op == "checksum":
                    return config_bin.checksum(entries)
                return [[str(n), w, _value(v)] for n, w, v in config_bin.reseal(entries)]
            rec.call("cb_entries", {"entries": [[str(n), w, v] for n, w, v in spec], "op": op}, run)


# --- pb_text ----------------------------------------------------------------------------------------

def _pb_calls(rec, relative: str, data: bytes, depths=(0,)) -> None:
    for depth in depths:
        for mode in MODES:
            def run(depth=depth, mode=mode):
                offered: list[str] = []
                new, count = pb_text.rewrite(data, translator(mode, offered), depth)
                return [_blob(new), count, _texts(offered)]
            rec.call("pb_rewrite", {"file": relative, "depth": depth, "mode": mode}, run)
        rec.call("pb_collect", {"file": relative, "depth": depth}, lambda depth=depth: _texts(pb_text.collect(data, depth)))


def _nest(depth: int) -> bytes:
    message = b"\x0a\x06" + "王者".encode()
    for _ in range(depth):
        message = b"\x12" + bytes([len(message)]) + message if len(message) < 128 else b"\x12\x7f" + message[:127]
    return message


def _pb(rec, out: Path, bins: list[Path], replacements: list[Path]) -> None:
    rng = random.Random(29)
    for path in bins:
        _pb_calls(rec, f"config/{path.name}", path.read_bytes())
    for folder in replacements:
        for path in sorted(folder.rglob("*.assets")):
            raw = path.read_bytes()
            for cut in (len(raw), len(raw) // 2):
                relative = _write(out, "pb", f"{path.stem}.{cut}.assets", raw[:cut])
                _pb_calls(rec, relative, raw[:cut])
    for path in rng.sample(bins, min(len(bins), 40)):
        for index, mutated in enumerate(_mutations(rng, path.read_bytes(), 6)):
            relative = _write(out, "pb-fuzz", f"{path.stem}.{index}.bin", mutated)
            _pb_calls(rec, relative, mutated)
    synthetic = [b"", b"\x00", b"\x08\x01", b"\x0a\x00", b"\x0a\x01\x07", b"\x0a\x03\xe7\x8e\x8b", b"\x0a\x02\xe7\x8e",
                 b"\x0a\x04\x01\xe7\x8e\x8b", b"\x0a\x03\xef\xa4\x80", b"\x0a\x03\xe3\x90\x80", b"\x0d\x01\x02",
                 b"\x09" + b"\x00" * 8, b"\x0b", b"\x0a\x05\x0a\x03\xe7\x8e\x8b", b"\x0a\x05\x0a\x03\xe7\x8e\x8c\xff",
                 b"\x0a\x06\x0a\x03\xe7\x8e\x8b\x00", b"\x0a\x07" + "王\n者".encode(),
                 b"\x08" + b"\x80" * 10 + b"\x01", b"\x08" + b"\x80" * 9 + b"\x01", _nest(14), _nest(15), _nest(16),
                 _nest(17), _nest(20), b"\x0a\x80\x01" + "王".encode() * 42 + b"ab"]
    for index, raw in enumerate(synthetic):
        relative = _write(out, "pb-fuzz", f"synthetic{index}.bin", raw)
        _pb_calls(rec, relative, raw, depths=(0, 3, 16, 17))


# --- lineup_codes -----------------------------------------------------------------------------------

def _codes(path: Path, file_hash: int) -> list[bytes]:
    code_field = lineup_codes.LINEUP_BINS[file_hash].code_field
    found = []
    for number, wire, row in config_bin.fields(path.read_bytes()):
        if number != 2 or wire != 2:
            continue
        found += [item for inner, inner_wire, item in config_bin.fields(row)
                  if inner == code_field and inner_wire == 2]
    return found


def _packers(data: bytes) -> list[bytes]:
    """<data> deflated by every block kind zlib writes: stored, fixed, dynamic, Huffman-only, RLE."""
    found = []
    for level, strategy in ((0, zlib.Z_DEFAULT_STRATEGY), (1, zlib.Z_FIXED), (6, zlib.Z_DEFAULT_STRATEGY),
                            (9, zlib.Z_HUFFMAN_ONLY), (6, zlib.Z_RLE)):
        packer = zlib.compressobj(level, zlib.DEFLATED, -15, 8, strategy)
        found.append(packer.compress(data) + packer.flush())
    return found


def _encodings(rng: random.Random) -> list[bytes]:
    words = [w.encode() for w in ("王者", "lineup", "英雄", "card", "\x00\x01", "chess", "Steal", "万象")]
    found = [b"", b"a", b"ab", b"abc", b"\x00" * 3, b"\x00" * 300, b"\x00" * 70000, bytes(range(256)) * 300]
    for size in (10, 100, 1000, 5000, 20000, 33000, 70000, 140000, 300000):
        found.append(bytes(rng.randrange(256) for _ in range(size)))
        text = bytearray()
        while len(text) < size:
            text += rng.choice(words) if rng.random() < 0.9 else bytes([rng.randrange(256)])
        found.append(bytes(text[:size]))
        found.append(bytes(rng.choice(b"ab") for _ in range(size)))
    pattern = bytearray()
    while len(pattern) < 120000:
        pattern += bytes([rng.randrange(4)]) * rng.randrange(1, 300)
    found.append(bytes(pattern))
    return found


def _lineup(rec, out: Path, bins: list[Path]) -> None:
    rng = random.Random(31)
    lineup_files = [(path, int(path.stem.split("-")[1], 16)) for path in bins
                    if "-" in path.stem and int(path.stem.split("-")[1], 16) in lineup_codes.LINEUP_BINS]
    messages = []
    codes = []
    for path, file_hash in lineup_files:
        for code in _codes(path, file_hash):
            codes.append(code)
            messages.append(lineup_codes.decode_code(code))
    variants = list(codes)
    for code in rng.sample(codes, min(len(codes), 40)):
        variants += [code[: len(code) // 2], code[:-1], code[:-2], b" " + code + b"\n", code + b"AAAA", code + b"="]
        variants += _mutations(rng, code, 3, flips=2)
    variants += [b"", b"A", b"AB", b"AB==", b"!!!!", b"AAAA", b"A===", b"AB=CD", b"ABC=D", b"wA==", b"8A==", b"/w==",
                 b"AwA=", b"AwAA", b"Aw"]
    streams = []
    for data in (b"", b"x", b"abcabcabcabc" + b"y" * 300, bytes(range(256)) * 4, *rng.sample(messages, 10)):
        streams += _packers(data)
    for stream in list(streams):
        streams += [stream[: len(stream) // 2], stream + b"trailing"]
        streams += _mutations(rng, stream, 12, flips=2)
    streams += [bytes([b]) for b in range(256)]
    streams += [bytes([rng.randrange(256) for _ in range(rng.randrange(1, 40))]) for _ in range(400)]
    variants += [base64.b64encode(stream) for stream in streams]
    for code in variants:
        rec.call("lc_decode", {"code": code.hex()}, lambda code=code: _blob(lineup_codes.decode_code(code)))
    for message in messages + _encodings(rng) + [m for message in rng.sample(messages, 20)
                                                for m in _mutations(rng, message, 3)]:
        name = hashlib.sha256(message).hexdigest()[:16] + ".bin"
        rec.call("lc_encode", {"file": _write(out, "lineup-messages", name, message)},
                 lambda message=message: _blob(lineup_codes.encode_code(message)))
    for code in variants[: len(codes) + 120]:
        for mode in MODES:
            def run(code=code, mode=mode):
                offered: list[str] = []
                new, count = lineup_codes.rewrite_code(code, translator(mode, offered))
                return [_blob(new), count, _texts(offered)]
            rec.call("lc_rewrite_code", {"code": code.hex(), "mode": mode}, run)
    cases = []
    for path, file_hash in lineup_files:
        data = path.read_bytes()
        cases.append((path.name, file_hash, data))
        for index, mutated in enumerate(_mutations(rng, data, 25) + [data[: len(data) // 2], data[:-1]]):
            cases.append((f"{path.stem}.{index}.bin", file_hash, mutated))
    row_cases = [
        [(1, 2, b"0" * 32), (2, 2, b"\x22\x02\x41\x41"), (4, 0, 0)],
        [(1, 0, 5), (2, 2, b"\x4a\x03" + "王".encode()), (4, 0, 0)],
        [(1, 2, b"0" * 32), (2, 2, b"\x4a\x03" + "王".encode()), (4, 2, b"")],
        [(1, 2, b"0" * 32), (2, 2, b"\x4a\x03" + "王".encode()), (2, 0, 3), (4, 0, 0)],
        [(1, 1, b"0" * 8), (2, 2, b"\x4a\x03" + "王".encode()), (4, 0, 0)],
        [(2, 2, b"\x4a\x03" + "王".encode()), (3, 0, 9)],
        [(2, 2, b"\x4a\x03" + "王".encode()), (3, 2, b"\x08\x80\x80\x80\x80\x10")],
        [(2, 2, b"\x4a\x03" + "王".encode()), (3, 2, b"\x0b")],
        [(2, 2, b"\x4a\x03" + "王".encode() + b"\x0b")],
        [(2, 2, b"\x48\x80\x01")],
        [(2, 2, b"\x22\x04AAAA")],
        [(2, 2, b"\x22" + bytes([len(c)]) + c) for c in codes[:1] if len(c) < 128],
    ]
    for index, entries in enumerate(row_cases):
        raw = b"".join(config_bin._put_varint(n << 3 | w) + (config_bin._put_varint(v) if w == 0 else
                       (config_bin._put_varint(len(v)) + v if w == 2 else v)) for n, w, v in entries)
        cases.append((f"rows{index}.bin", 0xF79FB1A213A9DA90, raw))
    cases.append(("unparsed.bin", 0xF79FB1A213A9DA90, b"\x10\x80\x00"))
    for name, file_hash, data in cases:
        relative = _write(out, "lineup", name, data)
        for mode in MODES:
            def run(file_hash=file_hash, data=data, mode=mode):
                offered: list[str] = []
                new, count = lineup_codes.rewrite_bin(file_hash, data, translator(mode, offered))
                return [_blob(new), count, _texts(offered)]
            rec.call("lc_rewrite_bin", {"hash": f"{file_hash:016X}", "file": relative, "mode": mode}, run)
        rec.call("lc_strings", {"hash": f"{file_hash:016X}", "file": relative},
                 lambda file_hash=file_hash, data=data: _texts(lineup_codes.strings(file_hash, data)))


# --- unity_text -------------------------------------------------------------------------------------

def _string(text: str | bytes) -> bytes:
    raw = text.encode() if isinstance(text, str) else text
    return struct.pack("<i", len(raw)) + raw + b"\0" * (-len(raw) % 4)


def serialized(*, types=((114, -1), (1, -1), (114, 0)), type_tree=0, nodes=0, bodies=None, data_offset=None,
               version=22, endian=0, order=None, pad_metadata=16) -> bytes:
    """A small Unity 2022 SerializedFile with stripped type trees."""
    if bodies is None:
        bodies = [(0, _string("王者万象棋") + struct.pack("<i", 7) + _string("chess")),
                  (1, _string("王者")), (2, _string("英雄") + _string(b"\xff\xfe") + b"\x01\x00\x00\x00ab"),
                  (0, b"\x03\x00\x00\x00" + "王".encode() + b"\x00" + _string("卡牌"))]
    meta = bytearray(b"2022.3.21f1\0") + struct.pack("<i", 13) + bytes([type_tree]) + struct.pack("<i", len(types))
    for class_id, script in types:
        meta += struct.pack("<iBh", class_id, 0, script)
        if class_id == 114 or script >= 0:
            meta += b"S" * 16
        meta += b"H" * 16
        if type_tree:
            meta += struct.pack("<i", nodes)
            if nodes:
                meta += struct.pack("<i", 3) + b"N" * (32 * nodes) + b"abc" + struct.pack("<i", 1) + b"D" * 4
    meta += struct.pack("<i", len(bodies))
    table_at = []
    for _ in bodies:
        while (48 + len(meta)) % 4:
            meta += b"\0"
        table_at.append(len(meta))
        meta += b"\0" * 24
    meta += b"\0" * pad_metadata
    start = 48 + len(meta)
    offset = data_offset if data_offset is not None else (start + 15) // 16 * 16
    blob = bytearray()
    placed = []
    for type_index, body in bodies:
        while len(blob) % 8:
            blob += b"\0"
        placed.append((len(blob), len(body), type_index))
        blob += body
    for index, at in enumerate(order or range(len(bodies))):
        rel, size, type_index = placed[at]
        struct.pack_into("<qQIi", meta, table_at[index], index + 1, rel, size, type_index)
    head = bytearray(48)
    body = bytes(meta) + b"\0" * max(0, offset - start)
    total = 48 + len(body) + len(blob) if offset >= start else offset + len(blob)
    struct.pack_into(">I", head, 8, version)
    head[16] = endian
    struct.pack_into(">IQQ", head, 20, len(meta), total, offset)
    data = bytes(head) + body
    data = (data + bytes(blob)) if offset >= start else (data[:offset] + bytes(blob))
    if len(data) != total:
        data = data[:total] + b"\0" * (total - len(data))
    return data


UNITY = {
    "plain": {}, "type-tree": {"type_tree": 1}, "type-tree-nodes": {"type_tree": 1, "nodes": 2},
    "reordered": {"order": [3, 1, 0, 2]}, "no-mono": {"types": ((1, -1), (2, -1), (3, 5))},
    "empty": {"bodies": []}, "late-data": {"data_offset": 400}, "version": {"version": 21}, "big-endian": {"endian": 1},
    "tight": {"pad_metadata": 0}, "plain-text": {"bodies": [(0, _string("ascii only") + _string("x"))]},
}


def _unity_summary(data: bytes) -> list:
    parsed = unity_text.SerializedFile(data)
    return [parsed.metadata_size, parsed.file_size, parsed.data_offset, parsed.class_ids, parsed.objects]


def _unity(rec, out: Path) -> None:
    rng = random.Random(37)
    bases = {name: serialized(**options) for name, options in UNITY.items()}
    bases["short"] = bases["plain"][:40]
    bases["no-nul"] = bases["plain"][:48] + b"x" * 30
    bases["sized-wrong"] = bases["plain"] + b"\0"
    cases = []
    for name, data in bases.items():
        cases.append((name, data))
        cases += [(f"{name}.cut{cut}", data[:cut]) for cut in sorted(rng.sample(range(len(data)), min(len(data), 12)))]
        for index, mutated in enumerate(_mutations(rng, data, 40, flips=3)):
            size = struct.pack(">Q", len(mutated))
            cases.append((f"{name}.flip{index}", mutated[:24] + size + mutated[32:] if index % 2 else mutated))
    for name, data in cases:
        relative = _write(out, "unity", f"{name}.bin", data)
        rec.call("ut_parse", {"file": relative}, lambda data=data: _unity_summary(data))
        for mode in MODES:
            def run(data=data, mode=mode):
                offered: list[str] = []
                new, count = unity_text.SerializedFile(data).rewrite(translator(mode, offered))
                return [_blob(new), count, _texts(offered)]
            rec.call("ut_rewrite", {"file": relative, "mode": mode}, run)
    bodies = [b"", b"\x01\x00", b"\x00\x00\x00\x00", _string("王"), _string("王")[:-1],
              b"\x03\x00\x00\x00" + "王".encode() + b"\x01", b"\x03\x00\x00\x00\xe7\x8e",
              b"\xff\xff\xff\xff" + "王".encode(), _string("一") + b"\x00\x00", _string("abc王") + b"x"]
    for body in bodies:
        for mode in MODES:
            def run(body=body, mode=mode):
                offered: list[str] = []
                new, count = unity_text._rewrite_strings(body, translator(mode, offered))
                return [new.hex(), count, offered]
            rec.call("ut_strings", {"body": body.hex(), "mode": mode}, run)


def record(rec, out: Path, config_bins: list[Path], replacements: list[Path]) -> None:
    bins = sorted(path for folder in config_bins for path in folder.glob("*.bin"))
    _config(rec, out, bins)
    _pb(rec, out, bins, replacements)
    _lineup(rec, out, bins)
    _unity(rec, out)
