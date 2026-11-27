"""The manifest and BrokenList cases of leaves_tap.py: ``axml_set_debuggable``, ``axml_label`` and
``broken_list`` on real files and on synthetic ones built here, each cut short and with bytes changed.

Migration tooling, run by hand: the exe, the APK and ``tools/`` never import it.
"""
from __future__ import annotations

import hashlib
import random
import struct
import zipfile
from pathlib import Path

import axml_label
import axml_set_debuggable as axml
import broken_list

APP_NAME = "Honor of Kings: ACE"  # app/apk_preparation.py
LABELS = ("王者万象棋", APP_NAME, "HOK ACE", "", "x" * 200, "王" * 130, "😀")


def _chunk(kind: int, header_size: int, body: bytes) -> bytes:
    return struct.pack("<HHI", kind, header_size, 8 + len(body)) + body


def _node(kind: int, ext: bytes, comment: int = axml.NO_INDEX) -> bytes:
    return _chunk(kind, 16, struct.pack("<II", 1, comment) + ext)


def _attr(ns: int, name: int, raw: int, kind: int, data: int) -> bytes:
    return struct.pack("<IIIHBBI", ns, name, raw, 8, 0, kind, data)


def manifest(*, utf8=True, debuggable=None, twice=False, label="ref", map_label=True, application=True,
             styles=0, unsorted=False, extras=True, components=True) -> bytes:
    """A small binary manifest: the mapped attribute names first, as aapt writes them."""
    mapped = ["label"] + (["debuggable"] if debuggable is not None else []) + ["name"]
    ids = [axml_label.LABEL_RES_ID if map_label else 0x01010002]
    ids += [axml.DEBUGGABLE_RES_ID] if debuggable is not None else []
    ids += [0x01010003]
    if twice:
        mapped.append("debuggable")
        ids.append(axml.DEBUGGABLE_RES_ID)
    rest = [axml.ANDROID_NS, "android", "manifest", "application", "activity", "activity-alias", "provider",
            "permission", "id", "class", "style", "王者万象棋", "Own label", "text", "service"]
    strings = mapped + rest
    at = {text: index for index, text in reversed(list(enumerate(strings)))}
    pool = bytearray(axml.build_string_pool(strings, axml.UTF8_FLAG if utf8 else 0))
    if styles:
        struct.pack_into("<I", pool, 12, styles)
    ns = at[axml.ANDROID_NS]

    def element(name: str, attrs: list[bytes]) -> bytes:
        ext = struct.pack("<IIHHHHHH", axml.NO_INDEX, at[name], 20, 20, len(attrs), 0, 0, 0) + b"".join(attrs)
        return _node(axml.RES_XML_START_ELEMENT, ext, comment=at["text"]) + _node(
            axml.RES_XML_END_ELEMENT, struct.pack("<II", axml.NO_INDEX, at[name]))

    app = []
    if label == "ref":
        app.append(_attr(ns, 0, axml.NO_INDEX, axml_label.TYPE_REFERENCE, 0x7F0E0001))
    elif label is not None:
        app.append(_attr(ns, 0, at[label], axml.TYPE_STRING, at[label]))
    app.append(_attr(ns, at["name"], at["text"], axml.TYPE_STRING, at["text"]))
    if debuggable is not None:
        app.append(_attr(ns, at["debuggable"], axml.NO_INDEX, axml.TYPE_INT_BOOLEAN, 0xFFFFFFFF if debuggable else 0))
    if twice:
        app.append(_attr(ns, len(mapped) - 1, axml.NO_INDEX, axml.TYPE_INT_BOOLEAN, 0))
    if extras:
        app += [_attr(axml.NO_INDEX, at["id"], at["text"], axml.TYPE_STRING, at["text"]),
                _attr(axml.NO_INDEX, at["style"], axml.NO_INDEX, 0x10, 7),
                _attr(axml.NO_INDEX, at["class"], at["text"], axml.TYPE_STRING, at["text"])]
    if unsorted:
        app.reverse()
    body = _node(axml.RES_XML_START_NAMESPACE, struct.pack("<II", at["android"], ns))
    body += element("manifest", [])
    if application:
        body += element("application", app)
    if components:
        ref = _attr(ns, 0, axml.NO_INDEX, axml_label.TYPE_REFERENCE, 0x7F0E0001)
        body += element("activity", [ref]) + element("activity-alias", [ref]) + element("provider", [ref])
        body += element("permission", [ref]) + element("service", [_attr(ns, 0, axml.NO_INDEX, 1, 0x7F0E0002)])
        body += element("activity", [_attr(ns, 0, at["Own label"], axml.TYPE_STRING, at["Own label"])])
    body += _node(axml.RES_XML_CDATA, struct.pack("<IHBBI", at["text"], 8, 0, axml.TYPE_STRING, at["text"]))
    body += _node(axml.RES_XML_END_NAMESPACE, struct.pack("<II", at["android"], ns))
    content = bytes(pool) + _chunk(axml.RES_XML_RESOURCE_MAP, 8, struct.pack(f"<{len(ids)}I", *ids)) + body
    return struct.pack("<HHI", axml.RES_XML, 8, 8 + len(content)) + content


def loops(data: bytes) -> bool:
    """True when the chunk walk both edits make would never end (a chunk of size 0)."""
    if len(data) < 8:
        return False
    pos = struct.unpack_from("<H", data, 2)[0]
    while pos < len(data):
        if len(data) - pos < 8:
            return False
        size = struct.unpack_from("<I", data, pos + 4)[0]
        if size == 0:
            return True
        pos += size
    return False


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _install(data: bytes) -> list:
    """`apk_preparation.manifest_to_install` without its log: the flag cleared, then the name."""
    if axml.is_debuggable(data):
        data = axml.patch(data, debuggable=False)
    try:
        named = axml_label.set_label(data, APP_NAME)
    except ValueError as error:
        return [_digest(data), f"{type(error).__name__}: {error}"]
    return [_digest(named), None]


VARIANTS = {
    "plain": {}, "utf16": {"utf8": False}, "debug-on": {"debuggable": True}, "debug-off": {"debuggable": False},
    "debug-twice": {"debuggable": True, "twice": True}, "unsorted": {"unsorted": True, "debuggable": False},
    "label-own": {"label": "王者万象棋"}, "label-other": {"label": "Own label"}, "label-none": {"label": None},
    "no-label-id": {"map_label": False}, "no-application": {"application": False}, "styles": {"styles": 1},
    "no-extras": {"extras": False}, "no-components": {"components": False},
    "utf16-debug": {"utf8": False, "debuggable": True, "unsorted": True},
}


def _manifests(rec, out: Path, apks: list[Path]) -> None:
    folder = out / "manifests"
    folder.mkdir(exist_ok=True)
    bases: dict[str, bytes] = {}
    real = set()
    for apk in apks:
        with zipfile.ZipFile(apk) as archive:
            bases[apk.stem] = archive.read("AndroidManifest.xml")
        real.add(apk.stem)
    for name, options in VARIANTS.items():
        bases[name] = manifest(**options)
    bases["not_xml"] = b"\x01\x00" + bases["plain"][2:]
    bases["short"] = bases["plain"][:5]
    rng = random.Random(7)
    cases: list[tuple[str, bytes, bool]] = []
    for name, data in bases.items():
        cases.append((name, data, True))
        cuts = sorted(rng.sample(range(len(data)), min(len(data), 25 if name in real else 40)))
        cases += [(f"{name}.cut{cut}", data[:cut], False) for cut in cuts]
        for index in range(60 if name in real else 150):
            mutated = bytearray(data)
            for _ in range(rng.randint(1, 4)):
                if mutated:
                    # A real manifest's string pool and first elements sit in its first 4 KiB.
                    mutated[rng.randrange(min(len(mutated), 4096 if name in real else len(mutated)))] = rng.randrange(256)
            cases.append((f"{name}.flip{index}", bytes(mutated), False))
    for name, data, base in cases:
        if loops(data):
            continue
        path = folder / f"{name}.bin"
        path.write_bytes(data)
        relative = path.relative_to(out).as_posix()
        for debuggable in (True, False):
            rec.call("axml_patch", {"file": relative, "debuggable": debuggable},
                     lambda data=data, debuggable=debuggable: _digest(axml.patch(data, debuggable)))
        rec.call("axml_is_debuggable", {"file": relative}, lambda data=data: axml.is_debuggable(data))
        for label in LABELS if base else (APP_NAME,):
            rec.call("axml_set_label", {"file": relative, "label": label},
                     lambda data=data, label=label: _digest(axml_label.set_label(data, label)))
        rec.call("axml_install", {"file": relative}, lambda data=data: _install(data))
    for text in ("", "a", "王者", "x" * 128, "y" * 40000, "😀a"):
        for flags in (0, axml.UTF8_FLAG):
            rec.call("axml_build_pool", {"strings": [text, "b"], "flags": flags},
                     lambda text=text, flags=flags: axml.build_string_pool([text, "b"], flags).hex())


def _slot(offset: int, payload: bytes, key: int = 0) -> bytes:
    return struct.pack("<IiIQ", offset, -1, len(payload), key) + payload


def _record(package: bytes, asset: int, header: int = 8, body=None) -> bytes:
    body = 60 + len(package) if body is None else body
    return struct.pack("<II8xQ40xI", header, body, asset, len(package)) + package


def _listed(path: Path) -> dict:
    listed = broken_list.read(path)
    return {"assets": {package: sorted(assets) for package, assets in sorted(listed.assets.items())},
            "unreadable": listed.unreadable, "empty": listed.empty}


def _broken(rec, out: Path, files: list[Path]) -> None:
    folder = out / "broken"
    folder.mkdir(exist_ok=True)
    datas = {f"real{index}": path.read_bytes() for index, path in enumerate(files)}
    shard = bytearray()
    for payload in (b"..qtsvfs-watchdog..", _record(b"1", 0x39E980368CABE4A4), _record(b"21", 0xFFFFFFFFFFFFFFFF),
                    _record(b"1", 0x0123), _record(b"1", 0x39E980368CABE4A4), _record(b"1", 5, header=9),
                    _record(b"", 5), _record(b"12345678901", 5), _record(b"1a", 5), _record(b"3", 5, body=99),
                    b"short", _record(b"30", 7) + b"tail", _record(b"\xd9\xa3", 5, body=62)):
        shard += _slot(len(shard), payload)
        while len(shard) % 4:
            shard += b"\0"
    shard += struct.pack("<IiI", len(shard), -1, 1000)  # a size past the end
    datas["synthetic"] = bytes(shard)
    datas["empty"] = b""
    rng = random.Random(11)
    for name, data in list(datas.items()):
        for index in range(40):
            mutated = bytearray(data)
            for _ in range(rng.randint(1, 6)):
                if mutated:
                    mutated[rng.randrange(len(mutated))] = rng.randrange(256)
            datas[f"{name}.flip{index}"] = bytes(mutated)
        datas[f"{name}.cut"] = data[: len(data) * 2 // 3]
    for name, data in datas.items():
        path = folder / f"{name}.db"
        path.write_bytes(data)
        rec.call("broken_list", {"file": path.relative_to(out).as_posix()}, lambda path=path: _listed(path))
    rec.call("broken_list", {"file": "broken/absent.db"}, lambda: _listed(folder / "absent.db"))


def record(rec, out: Path, apks: list[Path], broken_files: list[Path]) -> None:
    _manifests(rec, out, apks)
    _broken(rec, out, broken_files)
