"""Set or clear android:debuggable in the <application> element of a binary AndroidManifest.xml.

Setting it is how the patcher builds the temporary data-access APK. Clearing it is the way back: if a
run is interrupted after that APK is installed, the pull-then-restore path can adopt the debuggable
build as the game's own (its signature matches) and reinstall it forever, so a caller that needs the
original build back has to be able to write the flag the other way.
"""
from __future__ import annotations

import argparse
import struct
from pathlib import Path

RES_STRING_POOL = 0x0001
RES_XML = 0x0003
RES_XML_START_NAMESPACE = 0x0100
RES_XML_END_NAMESPACE = 0x0101
RES_XML_START_ELEMENT = 0x0102
RES_XML_END_ELEMENT = 0x0103
RES_XML_CDATA = 0x0104
RES_XML_RESOURCE_MAP = 0x0180
UTF8_FLAG = 0x100
TYPE_STRING = 0x03
TYPE_INT_BOOLEAN = 0x12
DEBUGGABLE_RES_ID = 0x0101000F
ANDROID_NS = "http://schemas.android.com/apk/res/android"
NO_INDEX = 0xFFFFFFFF
BOOLEAN_TRUE = 0xFFFFFFFF  # AXML encodes any non-zero word as true
BOOLEAN_FALSE = 0x00000000


def read_length8(data: bytes, pos: int) -> tuple[int, int]:
    value = data[pos]
    if value & 0x80:
        return ((value & 0x7F) << 8) | data[pos + 1], pos + 2
    return value, pos + 1


def read_length16(data: bytes, pos: int) -> tuple[int, int]:
    value = struct.unpack_from("<H", data, pos)[0]
    if value & 0x8000:
        low = struct.unpack_from("<H", data, pos + 2)[0]
        return ((value & 0x7FFF) << 16) | low, pos + 4
    return value, pos + 2


def parse_string_pool(chunk: bytes) -> tuple[list[str], int]:
    _, header_size, _, count, style_count, flags, strings_start, _ = struct.unpack_from("<HHIIIIII", chunk, 0)
    if style_count:
        raise ValueError("string pools with styles are not supported")
    offsets = struct.unpack_from(f"<{count}I", chunk, header_size)
    strings = []
    for offset in offsets:
        pos = strings_start + offset
        if flags & UTF8_FLAG:
            _, pos = read_length8(chunk, pos)
            byte_len, pos = read_length8(chunk, pos)
            strings.append(chunk[pos : pos + byte_len].decode("utf-8"))
        else:
            char_len, pos = read_length16(chunk, pos)
            strings.append(chunk[pos : pos + char_len * 2].decode("utf-16-le"))
    return strings, flags


def encode_length8(value: int) -> bytes:
    if value > 0x7F:
        return bytes([(value >> 8) | 0x80, value & 0xFF])
    return bytes([value])


def encode_length16(value: int) -> bytes:
    if value > 0x7FFF:
        return struct.pack("<HH", (value >> 16) | 0x8000, value & 0xFFFF)
    return struct.pack("<H", value)


def build_string_pool(strings: list[str], flags: int) -> bytes:
    data = bytearray()
    offsets = []
    for text in strings:
        offsets.append(len(data))
        if flags & UTF8_FLAG:
            encoded = text.encode("utf-8")
            data += encode_length8(len(text)) + encode_length8(len(encoded)) + encoded + b"\0"
        else:
            data += encode_length16(len(text)) + text.encode("utf-16-le") + b"\0\0"
    while len(data) % 4:
        data += b"\0"
    header_size = 28
    strings_start = header_size + 4 * len(strings)
    size = strings_start + len(data)
    header = struct.pack("<HHIIIIII", RES_STRING_POOL, header_size, size, len(strings), 0, flags, strings_start, 0)
    return header + struct.pack(f"<{len(strings)}I", *offsets) + bytes(data)


def shift(value: int, index: int) -> int:
    return value + 1 if value != NO_INDEX and value >= index else value


def patch(manifest: bytes, debuggable: bool = True) -> bytes:
    """Return <manifest> with android:debuggable set to <debuggable> on <application>."""
    value = BOOLEAN_TRUE if debuggable else BOOLEAN_FALSE
    file_type, file_header_size, _ = struct.unpack_from("<HHI", manifest, 0)
    if file_type != RES_XML:
        raise ValueError("not a binary XML file")

    chunks = []
    pos = file_header_size
    while pos < len(manifest):
        chunk_type, _, chunk_size = struct.unpack_from("<HHI", manifest, pos)
        chunks.append([chunk_type, bytearray(manifest[pos : pos + chunk_size])])
        pos += chunk_size

    pool_chunk = next(c for c in chunks if c[0] == RES_STRING_POOL)
    map_chunk = next(c for c in chunks if c[0] == RES_XML_RESOURCE_MAP)
    strings, flags = parse_string_pool(bytes(pool_chunk[1]))
    res_ids = list(struct.unpack_from(f"<{(len(map_chunk[1]) - 8) // 4}I", map_chunk[1], 8))

    if DEBUGGABLE_RES_ID in res_ids:
        name_index = res_ids.index(DEBUGGABLE_RES_ID)
        inserted = None
    else:
        name_index = len(res_ids)
        strings.insert(name_index, "debuggable")
        res_ids.append(DEBUGGABLE_RES_ID)
        inserted = name_index
    android_ns = strings.index(ANDROID_NS)

    pool_chunk[1] = bytearray(build_string_pool(strings, flags))
    map_chunk[1] = bytearray(struct.pack("<HHI", RES_XML_RESOURCE_MAP, 8, 8 + 4 * len(res_ids)) + struct.pack(f"<{len(res_ids)}I", *res_ids))

    patched_application = False
    for chunk in chunks:
        chunk_type, body = chunk
        if chunk_type not in (RES_XML_START_NAMESPACE, RES_XML_END_NAMESPACE, RES_XML_START_ELEMENT, RES_XML_END_ELEMENT, RES_XML_CDATA):
            continue
        header_size = struct.unpack_from("<H", body, 2)[0]
        if inserted is not None:
            # comment index lives in the node header
            struct.pack_into("<I", body, 12, shift(struct.unpack_from("<I", body, 12)[0], inserted))
            if chunk_type in (RES_XML_START_NAMESPACE, RES_XML_END_NAMESPACE, RES_XML_END_ELEMENT):
                for off in (header_size, header_size + 4):
                    struct.pack_into("<I", body, off, shift(struct.unpack_from("<I", body, off)[0], inserted))
            elif chunk_type == RES_XML_CDATA:
                struct.pack_into("<I", body, header_size, shift(struct.unpack_from("<I", body, header_size)[0], inserted))
                if body[header_size + 7] == TYPE_STRING:
                    struct.pack_into("<I", body, header_size + 8, shift(struct.unpack_from("<I", body, header_size + 8)[0], inserted))
        if chunk_type != RES_XML_START_ELEMENT:
            continue

        ext = header_size
        ns, name, attr_start, attr_size, attr_count = struct.unpack_from("<IIHHH", body, ext)
        if inserted is not None:
            struct.pack_into("<II", body, ext, shift(ns, inserted), shift(name, inserted))
        attrs = []
        for i in range(attr_count):
            off = ext + attr_start + i * attr_size
            a_ns, a_name, a_raw, a_vsize, a_res0, a_type, a_data = struct.unpack_from("<IIIHBBI", body, off)
            if inserted is not None:
                a_ns, a_name, a_raw = shift(a_ns, inserted), shift(a_name, inserted), shift(a_raw, inserted)
                if a_type == TYPE_STRING:
                    a_data = shift(a_data, inserted)
            attrs.append([a_ns, a_name, a_raw, a_vsize, a_res0, a_type, a_data])

        element_name = strings[shift(name, inserted) if inserted is not None else name]
        if element_name == "application":
            existing = next((a for a in attrs if a[1] == name_index), None)
            if existing:
                existing[2], existing[5], existing[6] = NO_INDEX, TYPE_INT_BOOLEAN, value
            else:
                attrs.append([android_ns, name_index, NO_INDEX, 8, 0, TYPE_INT_BOOLEAN, value])

                def sort_key(a):
                    return res_ids[a[1]] if a[1] < len(res_ids) else 0xFFFFFFFF

                attrs.sort(key=sort_key)
            patched_application = True
            # fix id/class/style attribute indexes (1-based) after sorting
            id_index = class_index = style_index = 0
            for i, a in enumerate(attrs, 1):
                attr_name = strings[a[1]]
                if a[0] == NO_INDEX and attr_name == "id":
                    id_index = i
                elif a[0] == NO_INDEX and attr_name == "class":
                    class_index = i
                elif a[0] == NO_INDEX and attr_name == "style":
                    style_index = i
            fixed = body[: ext + 12] + struct.pack("<HHHH", len(attrs), id_index, class_index, style_index)
            fixed += body[ext + 20 : ext + attr_start]
            for a in attrs:
                fixed += struct.pack("<IIIHBBI", *a).ljust(attr_size, b"\0")
            struct.pack_into("<I", fixed, 4, len(fixed))
            chunk[1] = bytearray(fixed)
        else:
            for i, a in enumerate(attrs):
                struct.pack_into("<IIIHBBI", body, ext + attr_start + i * attr_size, *a)

    if not patched_application:
        raise ValueError("<application> element not found")

    out = b"".join(bytes(c[1]) for c in chunks)
    return struct.pack("<HHI", RES_XML, file_header_size, file_header_size + len(out)) + out


def is_debuggable(manifest: bytes) -> bool:
    """True when <application> already turns android:debuggable on.

    patch() leaves a manifest byte-identical when the flag is already the value asked for, so this
    is exact: asking for true changes nothing only if it was true. A manifest with no debug attribute
    at all comes back changed, which is what keeps the official build from reading as debuggable.
    """
    return patch(manifest, debuggable=True) == manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--no-debuggable", action="store_true",
                        help="clear the flag instead of setting it, to rebuild the game's own manifest")
    args = parser.parse_args()
    args.output.write_bytes(patch(args.source.read_bytes(), not args.no_debuggable))


if __name__ == "__main__":
    main()
