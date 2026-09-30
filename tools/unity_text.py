"""Replace display strings inside Unity 2022.3 SerializedFiles whose type trees were stripped.

Tencent keeps the "type tree enabled" flag but writes zero nodes, which stock parsers reject. Only
the object table is needed: a string field in object data is an int32 length plus UTF-8 bytes padded
to 4, so a string can be swapped and the objects after it moved. Only MonoBehaviour (class 114)
objects are touched, because GameObject names can be lookup keys.

Not used by the pipeline on this game: every package whose prefabs carry UI labels either hangs the
lobby's loading or crashes the game at start (`stack corruption detected`) when its labels are
rewritten, so `extra_text.UNITY_TEXT_PACKAGES` is empty and no package is planned here. The module is
kept because it is the only reader of the format, and a future attempt starts from it.
"""
from __future__ import annotations

import struct
from typing import Callable

MONO_BEHAVIOUR = 114
OBJECT_ALIGN = 8
CJK_START = "\u3400"
CJK_END = "\u9fff"


class UnsupportedFile(Exception):
    """Raised when <data> is not a Unity 2022.x SerializedFile this reader understands."""


def _align(value: int, to: int) -> int:
    return (value + to - 1) // to * to


class SerializedFile:
    def __init__(self, data: bytes):
        self.data = data
        if len(data) < 48:
            raise UnsupportedFile("too small")
        version = struct.unpack_from(">I", data, 8)[0]
        if version != 22 or data[16] != 0:  # 2022.x format, little-endian metadata
            raise UnsupportedFile(f"format {version}")
        self.metadata_size = struct.unpack_from(">I", data, 20)[0]
        self.file_size, self.data_offset = struct.unpack_from(">QQ", data, 24)
        if self.file_size != len(data):
            raise UnsupportedFile("size mismatch")
        pos = data.index(b"\0", 48) + 1  # unity version string
        pos += 4  # target platform
        type_tree = data[pos]
        pos += 1
        type_count = struct.unpack_from("<i", data, pos)[0]
        pos += 4
        self.class_ids = []
        for _ in range(type_count):
            class_id, _stripped, script_index = struct.unpack_from("<iBh", data, pos)
            pos += 7
            if class_id == MONO_BEHAVIOUR or script_index >= 0:
                pos += 16  # script id
            pos += 16  # old type hash
            if type_tree:
                nodes = struct.unpack_from("<i", data, pos)[0]
                pos += 4
                if nodes:
                    string_size = struct.unpack_from("<i", data, pos)[0]
                    pos += 4 + nodes * 32 + string_size
                    dependencies = struct.unpack_from("<i", data, pos)[0]
                    pos += 4 + 4 * dependencies
            self.class_ids.append(class_id)
        object_count = struct.unpack_from("<i", data, pos)[0]
        pos += 4
        self.objects = []  # [table offset, path id, byte start, byte size, type index]
        for _ in range(object_count):
            pos = _align(pos, 4)
            path_id, start, size, type_index = struct.unpack_from("<qQIi", data, pos)
            self.objects.append([pos, path_id, start, size, type_index])
            pos += 24
        if pos > 48 + self.metadata_size or not all(
            0 <= o[4] < len(self.class_ids) and self.data_offset + o[2] + o[3] <= len(data) for o in self.objects
        ):
            raise UnsupportedFile("object table does not validate")

    def rewrite(self, translate: Callable[[str], str | None]) -> tuple[bytes, int]:
        """Return (new file bytes, strings replaced); returns the input when nothing was replaced."""
        pieces = []
        replaced = 0
        for obj in sorted(self.objects, key=lambda o: o[2]):
            start = self.data_offset + obj[2]
            body = self.data[start:start + obj[3]]
            if self.class_ids[obj[4]] == MONO_BEHAVIOUR:
                body, count = _rewrite_strings(body, translate)
                replaced += count
            pieces.append((obj, body))
        if not replaced:
            return self.data, 0
        out = bytearray(self.data[: self.data_offset])
        for obj, body in pieces:
            offset = _align(len(out), OBJECT_ALIGN) - self.data_offset
            out += b"\0" * (self.data_offset + offset - len(out))
            struct.pack_into("<QI", out, obj[0] + 8, offset, len(body))
            out += body
        struct.pack_into(">Q", out, 24, len(out))
        return bytes(out), replaced


def _rewrite_strings(body: bytes, translate: Callable[[str], str | None]) -> tuple[bytes, int]:
    out = bytearray()
    pos = count = 0
    while pos + 4 <= len(body):
        length = struct.unpack_from("<i", body, pos)[0]
        end = pos + 4 + length
        if 0 < length <= len(body) - pos - 4 and not any(body[end:_align(end, 4)]):
            try:
                text = body[pos + 4:end].decode("utf-8")
            except UnicodeDecodeError:
                text = None
            replacement = translate(text) if text and any(CJK_START <= c <= CJK_END for c in text) else None
            if replacement is not None and replacement != text:
                encoded = replacement.encode("utf-8")
                padded_old = _align(end, 4)
                out += struct.pack("<i", len(encoded)) + encoded + b"\0" * (_align(len(encoded), 4) - len(encoded))
                pos = padded_old
                count += 1
                continue
        out += body[pos:pos + 4]
        pos += 4
    out += body[pos:]
    return bytes(out), count
