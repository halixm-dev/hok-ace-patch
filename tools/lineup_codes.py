"""Translate the text inside a lineup bin's share codes, and reseal the bin (official-lineups ticket 04).

Three package-``1`` config bins carry lineup share codes, one per row (``LINEUP_BINS``). A share code is
base64 (standard, padded) of raw deflate of an ``OSProto.OneLineup`` protobuf, and the game decodes it on
the phone (``EmbattleFormationDataClass:_decode``): strip non-base64 characters, base64-decode, inflate,
parse. Its text never shows in the bin's bytes, so the generic protobuf rewrite (``pb_text``) cannot reach
it, and that rewrite would leave the bin's checksum stale besides.

``rewrite_bin`` decodes each code, translates the ``OneLineup`` text fields (``ONE_LINEUP``), re-encodes the
message with each code's own field order kept (the order is per code, not field-number order), re-deflates
at zlib's default level and memLevel and re-base64s it. It then translates the row's own text fields,
rebuilds the row and reseals fields 1 and 4 (``config_bin.reseal``). A code, row or bin with nothing to
translate keeps its bytes, which is what makes the pass idempotent: run on its own output it finds no
Chinese left that it can translate. Every translated code is decoded again the game's way before it is
used, and the bin's digests are checked, so a rewrite that would not read back is refused rather than
written.

Measured in the lab notebook, "The three lineup bins mapped" and "Config bin checksums recomputed".
"""
from __future__ import annotations

import base64
import re
import zlib
from typing import Callable

from config_bin import NotConfigBin, ROW_FIELD, encode, fields, is_sealed, reseal

NOT_BASE64 = re.compile(rb"[^A-Za-z0-9+/=]")
_CJK = re.compile(r"[㐀-鿿豈-﫿]")

# Text fields of each message a code nests, by measured field number; a dict is a submessage's schema.
# TalentDesc (12) and EffectCardDesc (13) are left out: no shipped code carries them, so their numbers
# are inferred from declared order only.
_HERO = {7: None}                                   # STLineupHero.Desc
_OPERATION = {6: None, 4: _HERO, 5: _HERO}          # STOperationDetail.Desc, MainHeroIDs, SubHeroIDs
_LORD = {2: None}                                   # STLineupLordInfo.Desc
ONE_LINEUP = {1: None, 2: None, 5: None, 6: None, 7: None,  # Name, Provider, SimpleDesc, PositionDesc, EquipDesc
              3: _HERO, 8: _OPERATION, 9: _LORD}            # PreviewHeroes, OperationDetails, LordInfos

# {asset hash: (row field holding the code, row fields holding text)}, field numbers by declared order.
LINEUP_BINS: dict[int, tuple[int, frozenset[int]]] = {
    0xF79FB1A213A9DA90: (4, frozenset({9})),        # ResSeasonAILineupDataBin: FormationDataCode, LineupDesc
    0x6A2B886E5DCF22DC: (11, frozenset({22, 23})),  # ResRecommendLineup: Encode, LineupName, LineupDesc
    0xC0C56FEFDCA0EA5D: (5, frozenset({7})),        # ResHeroStrategyDataBin: LineupCode, Title
}

Translate = Callable[[str], "str | None"]


class NotLineupBin(ValueError):
    """Raised when a lineup bin, a row or a share code does not parse, or a rewrite would not read back."""


def decode_code(code: bytes) -> bytes:
    """The ``OneLineup`` bytes of a share code, by the game's steps."""
    try:
        return zlib.decompress(base64.b64decode(NOT_BASE64.sub(b"", code)), -15)
    except (ValueError, zlib.error) as error:
        raise NotLineupBin(f"share code does not decode ({error})") from error


def encode_code(message: bytes) -> bytes:
    """A share code for <message>: raw deflate at zlib's default settings, then padded base64."""
    packer = zlib.compressobj(zlib.Z_DEFAULT_COMPRESSION, zlib.DEFLATED, -15)
    return base64.b64encode(packer.compress(message) + packer.flush())


def _text(value: bytes) -> str | None:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _translated(value: bytes, translate: Translate) -> bytes | None:
    text = _text(value)
    if text is None or not _CJK.search(text):
        return None
    target = translate(text)
    return target.encode("utf-8") if target and target != text else None


def _message(data: bytes, schema: dict, translate: Translate) -> tuple[bytes, int]:
    """(<data> with its schema's text fields translated in place, strings replaced); order kept."""
    entries = fields(data)
    changed = 0
    for at, (number, wire, value) in enumerate(entries):
        if number not in schema or wire != 2:
            continue
        inner = schema[number]
        if inner is None:
            new = _translated(value, translate)
            count = new is not None
        else:
            new, count = _message(value, inner, translate)
        if count:
            entries[at] = (number, wire, new)
            changed += count
    return (encode(entries), changed) if changed else (data, 0)


def rewrite_code(code: bytes, translate: Translate) -> tuple[bytes, int]:
    """(<code> with its text translated, strings replaced); <code> itself when nothing changes."""
    message = decode_code(code)
    try:
        new, changed = _message(message, ONE_LINEUP, translate)
    except NotConfigBin as error:
        raise NotLineupBin(f"share code is not a OneLineup ({error})") from error
    if not changed:
        return code, 0
    new_code = encode_code(new)
    if decode_code(new_code) != new:
        raise NotLineupBin("re-encoded share code does not read back")
    return new_code, changed


def rewrite_bin(file_hash: int, raw: bytes, translate: Translate) -> tuple[bytes, int]:
    """(<raw> with its codes' and rows' text translated and the bin resealed, strings replaced).

    Returns <raw> itself and 0 when nothing changes. Raises NotLineupBin when the bin, a row or a code
    does not parse, or when the result does not read back sealed.
    """
    code_field, text_fields = LINEUP_BINS[file_hash]
    try:
        entries = fields(raw)
        changed = 0
        for at, (number, wire, value) in enumerate(entries):
            if number != ROW_FIELD or wire != 2:
                continue
            row = fields(value)
            row_changed = 0
            for slot, (inner, inner_wire, item) in enumerate(row):
                if inner_wire != 2:
                    continue
                if inner == code_field:
                    new, count = rewrite_code(item, translate)
                elif inner in text_fields:
                    new = _translated(item, translate)
                    count = new is not None
                else:
                    continue
                if count:
                    row[slot] = (inner, inner_wire, new)
                    row_changed += count
            if row_changed:
                entries[at] = (number, wire, encode(row))
                changed += row_changed
        if not changed:
            return raw, 0
        new_raw = encode(reseal(entries))
        if not is_sealed(new_raw):
            raise NotLineupBin("resealed bin does not pass its own checksum")
    except NotConfigBin as error:
        raise NotLineupBin(f"{file_hash:016X} is not a config bin ({error})") from error
    return new_raw, changed


def strings(file_hash: int, raw: bytes) -> list[str]:
    """Every Chinese string the pass would offer to translate in <raw>, codes and rows, in stored order."""
    code_field, text_fields = LINEUP_BINS[file_hash]
    found: list[str] = []

    def collect(text: str) -> str | None:
        found.append(text)
        return None

    for number, wire, value in fields(raw):
        if number != ROW_FIELD or wire != 2:
            continue
        for inner, inner_wire, item in fields(value):
            if inner_wire != 2:
                continue
            if inner == code_field:
                _message(decode_code(item), ONE_LINEUP, collect)
            elif inner in text_fields:
                _translated(item, collect)
    return found
