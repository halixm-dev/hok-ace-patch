"""Write the app's own name into a binary AndroidManifest.xml.

The launcher reads <application android:label> and the task switcher reads the label of the activity
under it. In this game both are the same resource reference (`@string/game_name`, `王者万象棋`), so
the name is written wherever that reference *is* a label: the reference is what identifies the app's
name, and a component carrying it is showing the app under that name. A component with a label of its
own, the QR-code activity, keeps it.

The new name is a literal value, so `resources.arsc` is untouched and text the game itself reads from
R.string.game_name is unchanged; only what the system shows is renamed.

The string pool codec is imported from axml_set_debuggable, where the debug-flag edit lives and where
it was written; this module edits the same file a second way.
"""
from __future__ import annotations

import struct

from axml_set_debuggable import (
    RES_STRING_POOL,
    RES_XML,
    RES_XML_RESOURCE_MAP,
    RES_XML_START_ELEMENT,
    TYPE_STRING,
    build_string_pool,
    parse_string_pool,
)

LABEL_RES_ID = 0x01010001
TYPE_REFERENCE = 0x01
# The elements a label is read from. A permission's label is not the name the app is listed under, so
# carrying the same reference there would be a coincidence rather than the app's name.
COMPONENTS = frozenset({"activity", "activity-alias", "service", "receiver", "provider"})


def set_label(manifest: bytes, label: str) -> bytes:
    """Return <manifest> with the app's name replaced by <label>.

    The manifest comes back byte-identical when the name is already <label>, which is what makes
    `set_label(manifest, label) == manifest` an exact test for "already named": nothing is written to
    the string pool either, so a second call cannot grow it.

    Raises ValueError on a manifest this cannot read or has no name to replace, so a caller can treat
    the rename as optional.
    """
    file_type, file_header_size, _ = struct.unpack_from("<HHI", manifest, 0)
    if file_type != RES_XML:
        raise ValueError("not a binary XML file")

    chunks = []
    pos = file_header_size
    while pos < len(manifest):
        chunk_type, _, chunk_size = struct.unpack_from("<HHI", manifest, pos)
        chunks.append((chunk_type, bytearray(manifest[pos : pos + chunk_size])))
        pos += chunk_size

    pool = next((body for kind, body in chunks if kind == RES_STRING_POOL), None)
    resource_map = next((body for kind, body in chunks if kind == RES_XML_RESOURCE_MAP), None)
    if pool is None or resource_map is None:
        raise ValueError("the manifest has no string pool or resource map")
    strings, flags = parse_string_pool(bytes(pool))
    res_ids = list(struct.unpack_from(f"<{(len(resource_map) - 8) // 4}I", resource_map, 8))
    if LABEL_RES_ID not in res_ids:
        raise ValueError("the manifest has no android:label attribute")
    name_index = res_ids.index(LABEL_RES_ID)

    # Collect the attributes to write, in document order: <application> is the parent of everything
    # that can be labelled, so it is what says which reference the components below it are carrying.
    targets = []
    shared = None
    seen_application = False
    for kind, body in chunks:
        if kind != RES_XML_START_ELEMENT:
            continue
        ext = struct.unpack_from("<H", body, 2)[0]
        _, name, attr_start, attr_size, attr_count = struct.unpack_from("<IIHHH", body, ext)
        found = None
        for i in range(attr_count):
            offset = ext + attr_start + i * attr_size
            attribute = struct.unpack_from("<IIIHBBI", body, offset)
            if attribute[1] == name_index:
                found = (offset, attribute[5], attribute[6])
                break
        element = strings[name]
        if element == "application":
            seen_application = True
            if found is None:
                raise ValueError("<application> has no android:label")
            offset, value_type, data = found
            if value_type == TYPE_REFERENCE:
                shared = data
                targets.append((body, offset))
            elif not (value_type == TYPE_STRING and data < len(strings) and strings[data] == label):
                targets.append((body, offset))
        elif shared is not None and element in COMPONENTS and found is not None:
            offset, value_type, data = found
            if value_type == TYPE_REFERENCE and data == shared:
                targets.append((body, offset))

    if not seen_application:
        raise ValueError("<application> element not found")
    if not targets:
        return manifest

    if label in strings:
        index = strings.index(label)
    else:
        # Appended, so every index already in the file stays valid and nothing has to be shifted.
        index = len(strings)
        pool[:] = build_string_pool(strings + [label], flags)
    for body, offset in targets:
        namespace, attribute_name, _, value_size, value_res0 = struct.unpack_from("<IIIHB", body, offset)
        struct.pack_into("<IIIHBBI", body, offset, namespace, attribute_name, index, value_size, value_res0,
                         TYPE_STRING, index)

    content = b"".join(bytes(body) for _, body in chunks)
    return struct.pack("<HHI", RES_XML, file_header_size, file_header_size + len(content)) + content
