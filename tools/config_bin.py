"""Read, write and reseal a config bin: the two digests the game stores beside a config bin's rows.

A config bin is a protobuf: ``1`` = a 32-character upper-case hex digest, ``2`` = the rows (each a
serialized row message), ``3`` = an index (``1`` = packed uint32 keys, ``2`` = entries of ``1`` = key and
``2`` = packed uint32 values) and ``4`` = a uint32 checksum.

* **Field 1** is ``MD5`` of the rows' bytes concatenated, in stored order, as upper-case hex.
* **Field 4** is what the game checks. libGameCore's ``PBDatabinLoader`` ``DecodeFromStream`` seeds a
  32-bit state with ``0x01234567`` and folds in ``h = (h ^ byte) * 0x89ABCDEF`` over every row's bytes,
  then each index key as 4 little-endian bytes, then each index entry's key and values the same way. A
  mismatch frees the bin instead of loading it, so the game drops what the bin feeds.

The index depends on the rows' keys only, so a rewrite that changes no key keeps it. The port matches the
stored values of every config bin of package ``1`` in both layers (lab notebook, "Config bin checksums
recomputed"); ``tools/research/config_bin_checksum.py --check`` reproduces that.
"""
from __future__ import annotations

import hashlib

FOLD_SEED = 0x01234567
FOLD_MULTIPLIER = 0x89ABCDEF
DIGEST_FIELD = 1
ROW_FIELD = 2
INDEX_FIELD = 3
CHECKSUM_FIELD = 4

Field = tuple[int, int, object]


class NotConfigBin(ValueError):
    """Raised when bytes do not parse as the protobuf framing a config bin or row uses."""


def _varint(data: bytes, pos: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        if pos >= len(data) or shift > 63:
            raise NotConfigBin(f"varint runs past byte {pos}")
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        shift += 7
        if byte < 0x80:
            return value, pos


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


def fields(data: bytes) -> list[Field]:
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
            raise NotConfigBin(f"wire type {wire} at byte {pos}")
        if pos > len(data) or number == 0:
            raise NotConfigBin("field runs past the end")
        found.append((number, wire, value))
    return found


def encode(entries: list[Field]) -> bytes:
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


def _fold(state: int, data: bytes) -> int:
    for byte in data:
        state = ((state ^ byte) * FOLD_MULTIPLIER) & 0xFFFFFFFF
    return state


def _packed(value: int | bytes, wire: int) -> list[int]:
    if wire == 0:
        return [int(value)]
    found, pos = [], 0
    while pos < len(value):
        number, pos = _varint(value, pos)
        found.append(number)
    return found


def rows_md5(entries: list[Field]) -> bytes:
    """Field 1: MD5 of the rows' bytes, upper-case hex."""
    rows = b"".join(value for number, _, value in entries if number == ROW_FIELD)
    return hashlib.md5(rows).hexdigest().upper().encode()


def checksum(entries: list[Field]) -> int:
    """Field 4, as ``DecodeFromStream`` computes it."""
    state = FOLD_SEED
    for number, _, value in entries:
        if number == ROW_FIELD:
            state = _fold(state, value)
    keys: list[int] = []
    index_entries: list[bytes] = []
    for number, _, value in entries:
        if number != INDEX_FIELD:
            continue
        for inner, wire, item in fields(value):
            if inner == 1:
                keys += _packed(item, wire)
            elif inner == 2:
                index_entries.append(item)
    for key in keys:
        state = _fold(state, key.to_bytes(4, "little"))
    for entry in index_entries:
        for inner, wire, item in fields(entry):
            if inner in (1, 2):
                for number in _packed(item, wire):
                    state = _fold(state, number.to_bytes(4, "little"))
    return state


def reseal(entries: list[Field]) -> list[Field]:
    """The same bin with fields 1 and 4 recomputed, everything else and the order kept."""
    head, total = rows_md5(entries), checksum(entries)
    return [(n, w, head if n == DIGEST_FIELD else total if n == CHECKSUM_FIELD else v) for n, w, v in entries]


def is_sealed(raw: bytes) -> bool:
    """True when <raw>'s stored fields 1 and 4 are the values its rows and index give."""
    entries = fields(raw)
    stored = {number: value for number, _, value in entries}
    return stored.get(DIGEST_FIELD) == rows_md5(entries) and stored.get(CHECKSUM_FIELD) == checksum(entries)
