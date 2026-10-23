"""Read the game's own update history (`Watchdog/History.db`): when its updater merged what, and into which package.

Each in-game update and repair appends records here; a fresh download logs one merge per package it
patched through diffs (214 on the 2026-10-16 download, lab notebook 2026-10-17, "What the game's updater
records"). A merge dated after the last install says the game updated over the translation. A research reader
(language-switch ticket 01, `docs/features/language-switch.md`): no patcher pass reads it.

The file is a QtsVFS shard (`broken_list` reads the same slots): `u32` self offset, `-1`, `u32` payload
size, `u64` key, payload. Each record's payload is `u32` 8, `u32` body length, seven `u32` local time
fields (year, month, day, hour, minute, second, millisecond), `u32` kind, `u32` text length, then the
ASCII text. A merge (kind 2) reads `<package>|<prime hash>|<base hash>|<current hash>|<current hash>|1|1`;
the other kinds' meanings are not known and are kept as read. A slot that does not read that way is
skipped, never guessed at.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import datetime

MERGE = 2
_SLOT = struct.Struct("<IiIQ")
_HEAD = struct.Struct("<II7III")


@dataclass(frozen=True)
class Record:
    """One history record: its local time, its kind (2 is a merge) and its text as read."""

    when: datetime
    kind: int
    text: str

    @property
    def merge(self) -> bool:
        return self.kind == MERGE and self.package.isdecimal()

    @property
    def package(self) -> str:
        return self.text.split("|", 1)[0]


def _record(payload: bytes) -> Record | None:
    if len(payload) < _HEAD.size:
        return None
    marker, body, year, month, day, hour, minute, second, milli, kind, length = _HEAD.unpack_from(payload)
    raw = payload[_HEAD.size:_HEAD.size + length]
    if marker != 8 or len(raw) != length or not 0 < length <= body or not raw.isascii():
        return None
    try:
        when = datetime(year, month, day, hour, minute, second, milli * 1000)
    except (ValueError, OverflowError):
        return None
    return Record(when, kind, raw.decode("ascii"))


def parse(data: bytes) -> list[Record]:
    """Every record of a `History.db`'s bytes, in file order; the header and unreadable slots are left out."""
    records = []
    for offset in range(0, len(data) - _SLOT.size + 1, 4):
        self_offset, marker, size, _ = _SLOT.unpack_from(data, offset)
        if self_offset != offset or marker != -1 or not 0 < size <= len(data) - offset - _SLOT.size:
            continue
        record = _record(data[offset + _SLOT.size:offset + _SLOT.size + size])
        if record is not None:
            records.append(record)
    return records


def merges_after(records: list[Record], since: datetime) -> list[Record]:
    """The merges dated after <since>, in the phone's local time as the records are."""
    return [record for record in records if record.merge and record.when > since]
