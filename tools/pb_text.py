"""Generic protobuf string rewriting for QtsVFS config assets the catalog has no table for.

The assets are schema-less to us, so length-delimited fields are classified heuristically: valid
UTF-8 without control characters is text, otherwise a field that parses completely as a message is
recursed into, and anything else is left as opaque bytes.
"""
from __future__ import annotations

import re
from typing import Callable

CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


class NotMessage(Exception):
    """Raised when a byte string is not a well-formed protobuf message."""


def _varint(data: bytes, pos: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        if pos >= len(data) or shift > 63:
            raise NotMessage
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7


def _encode_varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _as_text(value: bytes) -> str | None:
    try:
        text = value.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return None if _CONTROL.search(text) else text


def rewrite(data: bytes, translate: Callable[[str], str | None], depth: int = 0) -> tuple[bytes, int]:
    """Return (message with translated strings, number of strings replaced).

    Raises NotMessage when <data> is not a well-formed protobuf message.
    """
    out = bytearray()
    pos = changed = 0
    while pos < len(data):
        key, after_key = _varint(data, pos)
        field, wire = key >> 3, key & 7
        if field == 0:
            raise NotMessage
        if wire == 0:
            _value, end = _varint(data, after_key)
            out += data[pos:end]
        elif wire == 1:
            end = after_key + 8
            out += data[pos:end]
        elif wire == 5:
            end = after_key + 4
            out += data[pos:end]
        elif wire == 2:
            length, start = _varint(data, after_key)
            end = start + length
            if end > len(data):
                raise NotMessage
            value = data[start:end]
            text = _as_text(value)
            if text is not None and CJK.search(text):
                replacement = translate(text)
                if replacement is not None and replacement != text:
                    value = replacement.encode("utf-8")
                    changed += 1
            elif text is None and depth < 16 and value:
                try:
                    value, nested = rewrite(value, translate, depth + 1)
                    changed += nested
                except NotMessage:
                    pass
            # A replaced string can encode to a different length, so the length prefix is rewritten.
            out += data[pos:after_key] + _encode_varint(len(value)) + value
        else:
            raise NotMessage
        if end > len(data):
            raise NotMessage
        pos = end
    return bytes(out), changed


def collect(data: bytes, depth: int = 0) -> list[str]:
    """Every Chinese-bearing string field in <data> (same classification as rewrite)."""
    found: list[str] = []

    def keep(text: str) -> None:
        found.append(text)
        return None

    rewrite(data, keep, depth)
    return found
