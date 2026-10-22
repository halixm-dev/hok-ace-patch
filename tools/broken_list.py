"""Read the game's own record of package assets its updater could not patch (`Watchdog/BrokenList.db`).

When an in-game update meets an asset whose bytes are not what the package's stored check values say
(an asset a translation changed), the updater records the asset here and stops the whole update; the
game then shows "资源修复失败，请清理资源后重新下载资源". A healthy layer's list holds its header record
only (lab notebook, 2026-10-17, "What the game's updater records"; 2026-10-22, "An update stuck on
translated files").

The file is a QtsVFS shard: slots of `u32` self offset, `-1`, `u32` payload size, `u64` key, payload.
The first slot is the `qtsvfs-watchdog` header. Each asset record's payload is `u32` 8, `u32` body length
(60 + name length), 8 zero bytes, the `u64` asset hash at +16, then at +64 the `u32` length and ASCII
digits of the package's name. A slot that does not read that way is counted in `unreadable`, never
guessed at.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

HEADER_MARK = b"qtsvfs-watchdog"
_SLOT = struct.Struct("<IiIQ")
_NAME_AT = 64


@dataclass
class BrokenList:
    """The assets the updater gave up on, by package name, and the slots that did not read."""

    assets: dict[str, set[str]] = field(default_factory=dict)
    unreadable: int = 0

    @property
    def empty(self) -> bool:
        return not self.assets and not self.unreadable


def _record(payload: bytes) -> tuple[str, str] | None:
    """(package name, asset hash as 16 hex digits) of one record payload, or None."""
    if len(payload) < _NAME_AT + 4:
        return None
    header, body = struct.unpack_from("<II", payload, 0)
    length = struct.unpack_from("<I", payload, _NAME_AT)[0]
    name = payload[_NAME_AT + 4:_NAME_AT + 4 + length]
    if header != 8 or not 1 <= length <= 10 or body != 60 + length or len(name) != length or not name.isdigit():
        return None
    return name.decode("ascii"), f"{struct.unpack_from('<Q', payload, 16)[0]:016X}"


def read(path: Path) -> BrokenList:
    """The records of <path>; an absent file reads as an empty list."""
    result = BrokenList()
    if not path.is_file():
        return result
    data = path.read_bytes()
    for offset in range(0, len(data) - _SLOT.size + 1, 4):
        self_offset, marker, size, _ = _SLOT.unpack_from(data, offset)
        if self_offset != offset or marker != -1 or not 0 < size <= len(data) - offset - _SLOT.size:
            continue
        payload = data[offset + _SLOT.size:offset + _SLOT.size + size]
        if HEADER_MARK in payload:
            continue
        record = _record(payload)
        if record is None:
            result.unreadable += 1
            continue
        result.assets.setdefault(record[0], set()).add(record[1])
    return result
