"""Expand game format tokens that the client would otherwise fill with Chinese labels.

Card descriptions keep tokens such as {Energy}, {LordExp} and {LordHp}. The client substitutes
resource display names at render time, and those names are still Chinese in the shipped tables, so
translated strings render hybrid ("Gain 1能量"). The catalog cannot be fixed instead: translate_table
compares placeholders between source and target, so substituting there rejects the record. The
substitution happens here, on the staged replacements after translation.
"""
from __future__ import annotations

import re

RESOURCE_TOKENS = {
    "{Energy}": "Energy",
    "{LordExp}": "Chessplayer EXP",
    "{LordHp}": "Chessplayer HP",
}

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

# Any brace token; only names in RESOURCE_TOKENS are rewritten, so dynamic tokens such as
# {HeroName} and numeric {0|1} pass through untouched.
_TOKEN_RE = re.compile(r"\{[A-Za-z][A-Za-z0-9_]*\}")

# The catalog glued the token to the words around it, because the Chinese expansion needs no space
# ("获得{0|1}{Energy}。"). An English term does, so a space is inserted at those boundaries. The delta
# spacing follows the catalog's own stat phrasing, which writes "Chessplayer EXP +{0}" and "Energy +2"
# but glues a minus ("Energy-2", 69 occurrences): '+' is spaced, '-' is deliberately not.
_SPACE_BEFORE = re.compile(r"[A-Za-z0-9}]")
_SPACE_AFTER = re.compile(r"[A-Za-z+]")

_MAX_DEPTH = 16


class NotMessage(Exception):
    """Raised when a byte string is not a well-formed protobuf message."""


def expand_resource_tokens(text: str) -> str:
    """Return <text> with resource tokens replaced by English terms.

    A space is inserted where the term would otherwise run into the preceding character (a letter,
    digit or placeholder) or into a following letter or '+'. Anything else — punctuation, a following
    '-', markup — keeps the catalog's own spacing.
    """
    if not text or "{" not in text:
        return text
    out: list[str] = []
    index = 0
    while index < len(text):
        found = width = -1
        term = ""
        for token, name in RESOURCE_TOKENS.items():
            at = text.find(token, index)
            if at >= 0 and (found < 0 or at < found):
                found, term, width = at, name, len(token)
        if found < 0:
            out.append(text[index:])
            break
        end = found + width
        lead = " " if found and _SPACE_BEFORE.match(text[found - 1]) else ""
        tail = " " if end < len(text) and _SPACE_AFTER.match(text[end]) else ""
        out.append(f"{text[index:found]}{lead}{term}{tail}")
        index = end
    return "".join(out)


def expand_tokens_in_message(data: bytes) -> tuple[bytes, int]:
    """Return (<data> with resource tokens expanded, number of string fields changed).

    Walks the protobuf framing the way <data>'s reader does, but visits a string whenever it carries
    a resource token rather than whenever it carries CJK: the strings that need expanding are the
    already-translated English ones. Raises NotMessage when <data> is not a well-formed message.
    """
    return _walk(data, 0)


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


def _walk(data: bytes, depth: int) -> tuple[bytes, int]:
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
            if text is not None and _TOKEN_RE.search(text):
                replacement = expand_resource_tokens(text)
                if replacement != text:
                    value = replacement.encode("utf-8")
                    changed += 1
            elif text is None and depth < _MAX_DEPTH and value:
                try:
                    value, nested = _walk(value, depth + 1)
                    changed += nested
                except NotMessage:
                    pass
            # The expansion changes the encoded length, so the length prefix is re-encoded too.
            out += data[pos:after_key] + _encode_varint(len(value)) + value
        else:
            raise NotMessage
        if end > len(data):
            raise NotMessage
        pos = end
    return bytes(out), changed
