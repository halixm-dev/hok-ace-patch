"""Append a <provider> element to <application> in a binary AndroidManifest.xml."""
from __future__ import annotations

import argparse
import struct
from pathlib import Path

from axml_set_debuggable import (
    ANDROID_NS,
    NO_INDEX,
    RES_STRING_POOL,
    RES_XML,
    RES_XML_END_ELEMENT,
    RES_XML_RESOURCE_MAP,
    RES_XML_START_ELEMENT,
    TYPE_INT_BOOLEAN,
    TYPE_STRING,
    build_string_pool,
    parse_string_pool,
)

NAME_RES_ID = 0x01010003
EXPORTED_RES_ID = 0x01010010
AUTHORITIES_RES_ID = 0x01010018


def add_provider(manifest: bytes, class_name: str, authority: str) -> bytes:
    _, file_header_size, _ = struct.unpack_from("<HHI", manifest, 0)
    chunks = []
    pos = file_header_size
    while pos < len(manifest):
        chunk_type, _, chunk_size = struct.unpack_from("<HHI", manifest, pos)
        chunks.append([chunk_type, bytes(manifest[pos : pos + chunk_size])])
        pos += chunk_size

    pool_chunk = next(c for c in chunks if c[0] == RES_STRING_POOL)
    map_chunk = next(c for c in chunks if c[0] == RES_XML_RESOURCE_MAP)
    strings, flags = parse_string_pool(pool_chunk[1])
    res_ids = list(struct.unpack_from(f"<{(len(map_chunk[1]) - 8) // 4}I", map_chunk[1], 8))

    def attr_name(res_id: int) -> int:
        if res_id not in res_ids:
            raise ValueError(f"attribute 0x{res_id:08X} missing from resource map")
        return res_ids.index(res_id)

    def plain_string(text: str) -> int:
        # Non-attribute strings may live anywhere after the resource-mapped prefix.
        for index in range(len(res_ids), len(strings)):
            if strings[index] == text:
                return index
        strings.append(text)
        return len(strings) - 1

    android_ns = strings.index(ANDROID_NS)
    provider = plain_string("provider")
    class_index = plain_string(class_name)
    authority_index = plain_string(authority)
    attrs = sorted(
        [
            (android_ns, attr_name(NAME_RES_ID), class_index, TYPE_STRING, class_index),
            (android_ns, attr_name(EXPORTED_RES_ID), NO_INDEX, TYPE_INT_BOOLEAN, 0),
            (android_ns, attr_name(AUTHORITIES_RES_ID), authority_index, TYPE_STRING, authority_index),
        ],
        key=lambda a: res_ids[a[1]],
    )
    body = struct.pack("<IIHHHHHH", NO_INDEX, provider, 20, 20, len(attrs), 0, 0, 0)
    for ns, name, raw, data_type, data in attrs:
        body += struct.pack("<IIIHBBI", ns, name, raw, 8, 0, data_type, data)
    start = struct.pack("<HHIII", RES_XML_START_ELEMENT, 16, 16 + len(body), 1, NO_INDEX) + body
    end = struct.pack("<HHIIIII", RES_XML_END_ELEMENT, 16, 24, 1, NO_INDEX, NO_INDEX, provider)

    application = strings.index("application")
    for i, (chunk_type, data) in enumerate(chunks):
        if chunk_type == RES_XML_END_ELEMENT and struct.unpack_from("<I", data, 20)[0] == application:
            chunks[i:i] = [[RES_XML_START_ELEMENT, start], [RES_XML_END_ELEMENT, end]]
            break
    else:
        raise ValueError("</application> not found")

    pool_chunk[1] = build_string_pool(strings, flags)
    out = b"".join(c[1] for c in chunks)
    return struct.pack("<HHI", RES_XML, file_header_size, file_header_size + len(out)) + out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--class-name", required=True)
    parser.add_argument("--authority", required=True)
    args = parser.parse_args()
    args.output.write_bytes(add_provider(args.source.read_bytes(), args.class_name, args.authority))


if __name__ == "__main__":
    main()
