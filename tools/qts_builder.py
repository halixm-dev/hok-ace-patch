"""Rebuild a whole QtsVFS package with Tencent's own builder (VFS_BuildPackage in QtsVFS.dll).

The mobile build reads two layers of game data: the packages baked into the APK (prime) and the
downloaded ones under files/QtsVFSCache (override), which hold only what changed since that build.
The game reads override first, so an override package that carries the APK's content too is how a
prime-only asset gets translated. Growing a package means new B-tree keys, and only the game's own
builder derives them, so the official DLL does the layout and this module aligns its output.

The PC and Android builds share the package format, and every lookup key (entry key, chunk hash1) is
derived from the file hash and the contents, so a package built on Windows is valid on Android.

The builder output is aligned with the package it replaces:

* records only the builder writes are dropped (the ``INGQ`` global-index node, the export-setting and
  remain-dir node files);
* the ``QTSF_PACKAGE`` node (version, package hash) is copied from the original override package;
* per-entry flag words the builder resets are restored from the original entries.
"""
from __future__ import annotations

import ctypes
import json
import os
import shutil
import struct
from pathlib import Path

# "hash|0|size|asset path|source path|" + one "offset,packed compression flag,block size;" per block.
DESC_LINE = "{hash}|0|{size}|BatchAssets/{hash:016X}.assets|{source}|0,{flag},{chunk_size};\n"
BUILDER_VERSION = "1.0.6.65"
# Left unset, MaxStorageSize is read from uninitialised memory and the builder randomly writes one
# storage file per asset. 1 GiB matches the game's own shards.
MAX_STORAGE_SIZE = 1 << 30
# Compression level the game's packages record; the packed flag is level << 16 | type.
DEFAULT_LEVEL = 5

PAGE = 0x1000
KEYS_PER_PAGE = 510
LEAF_TYPE = 3
ENTRY_SIZE = 92
PACKAGE_NODE_NAME = b"QTSF_PACKAGE"
GLOBAL_INDEX_MAGIC = b"INGQ"
ENTRY_FLAGS = 28  # two u32 flag words the builder resets
ENTRY_COMPRESSION = 76  # packed compression flag


def qtsvfs_dir(pc_game: Path) -> Path:
    """Folder holding the builder inside a PC game install."""
    return pc_game / "WXQ_Data" / "Plugins" / "x86_64"


def find_builder_dir(candidates: list[Path]) -> Path | None:
    """First candidate that is a PC game install or already holds QtsVFS.dll + QtskDB.dll."""
    for path in candidates:
        for folder in (path, qtsvfs_dir(path)):
            if (folder / "QtsVFS.dll").is_file() and (folder / "QtskDB.dll").is_file():
                return folder
    return None


class Builder:
    """Tencent's VFS_BuildPackage, loaded from a folder holding QtsVFS.dll and QtskDB.dll."""

    def __init__(self, bin_dir: Path):
        bin_dir = bin_dir.resolve()
        self.bin_dir = bin_dir
        self._cookie = os.add_dll_directory(str(bin_dir)) if hasattr(os, "add_dll_directory") else None
        ctypes.CDLL(str(bin_dir / "QtskDB.dll"))
        self.dll = ctypes.CDLL(str(bin_dir / "QtsVFS.dll"))
        for name in ("VFS_Initialize_Scripted", "VFS_Initialize"):
            init = getattr(self.dll, name, None)
            if init is not None:
                init.restype = ctypes.c_int
                init()
                break
        self.dll.VFS_BuildPackage.argtypes = [ctypes.c_char_p] * 4
        self.dll.VFS_BuildPackage.restype = ctypes.c_bool
        self.dll.VFS_GetLastError.restype = ctypes.c_int

    def build(self, package_id: str, assets: list[dict], work: Path) -> Path:
        """Build <package_id> from assets [{file_hash, raw, flag, chunk_size}]; return its folder.

        <flag> is the packed compression flag (level << 16 | type) the entry should get.
        """
        work = work.resolve()
        shutil.rmtree(work, ignore_errors=True)
        src, out, config = work / "src", work / "out", work / "config"
        (src / "BatchAssets").mkdir(parents=True)
        out.mkdir()
        config.mkdir()
        lines = []
        for asset in sorted(assets, key=lambda a: a["file_hash"]):
            if not asset["raw"]:
                raise ValueError(f"{asset['file_hash']:016X}: the builder cannot store empty files")
            path = src / "BatchAssets" / f"{asset['file_hash']:016X}.assets"
            path.write_bytes(asset["raw"])
            lines.append(DESC_LINE.format(hash=asset["file_hash"], size=len(asset["raw"]), source=path,
                                          flag=asset["flag"], chunk_size=asset["chunk_size"]))
        (config / "qts_layout_desc.json").write_text(json.dumps({
            "Version": BUILDER_VERSION, "BuildID": 1, "MaxStorageSize": MAX_STORAGE_SIZE, "AllInOne": False,
            "InternalPackage": package_id, "ExtraExportDataPackage": "", "WriteVersion": True, "WriteBuildID": True,
        }, indent=2), encoding="utf-8")
        (config / f"qts_package_desc_{package_id}.txt").write_text("".join(lines), encoding="utf-8")
        cwd = os.getcwd()
        os.chdir(work)
        try:
            ok = self.dll.VFS_BuildPackage(str(src).encode(), str(out).encode(), str(config).encode(),
                                           package_id.encode())
        finally:
            os.chdir(cwd)
        if not ok:
            raise RuntimeError(f"QtsVFS builder failed with error {self.dll.VFS_GetLastError()}")
        built = out / package_id
        shards = sorted(built.glob(f"{package_id}_*.db"))
        if not (built / f"{package_id}.db").is_file() or len(shards) != 1:
            raise RuntimeError(f"unexpected builder output for package {package_id}: {[p.name for p in shards]}")
        return built


def _u32(data, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _active_leaves(data) -> list[int]:
    table = _u32(data, 0x30)
    pages = []
    for i in range(_u32(data, table + 4)):
        logical, active = struct.unpack_from("<II", data, table + 24 + i * 24)
        tail = _u32(data, active + PAGE - 4)
        if tail >> 16 == LEAF_TYPE and _u32(data, active + PAGE - 16) == logical:
            pages.append(active)
    if not pages:
        raise RuntimeError("no active B-tree leaf pages")
    return pages


def index_records(data) -> list[int]:
    """Offsets of every record the index B-tree points at."""
    offsets = []
    for page in _active_leaves(data):
        count = _u32(data, page + PAGE - 4) & 0xFFFF
        offsets += struct.unpack_from(f"<{count}I", data, page + KEYS_PER_PAGE * 4)
    return offsets


def remove_records(data: bytearray, offsets: set[int]) -> int:
    """Drop the B-tree keys pointing at <offsets>; the records themselves become dead space."""
    removed = 0
    for page in _active_leaves(data):
        tail = _u32(data, page + PAGE - 4)
        count = tail & 0xFFFF
        keys = struct.unpack_from(f"<{count}I", data, page)
        values = struct.unpack_from(f"<{count}I", data, page + KEYS_PER_PAGE * 4)
        keep = [(k, v) for k, v in zip(keys, values) if v not in offsets]
        if len(keep) == count:
            continue
        if not keep:
            raise RuntimeError("removing these records would empty a B-tree leaf")
        removed += count - len(keep)
        data[page:page + KEYS_PER_PAGE * 8] = bytes(KEYS_PER_PAGE * 8)
        struct.pack_into(f"<{len(keep)}I", data, page, *(k for k, _ in keep))
        struct.pack_into(f"<{len(keep)}I", data, page + KEYS_PER_PAGE * 4, *(v for _, v in keep))
        struct.pack_into("<I", data, page + PAGE - 4, (tail & 0xFFFF0000) | len(keep))
    return removed


def _package_node(data, offsets) -> int | None:
    for offset in offsets:
        if data[offset + 32:offset + 32 + len(PACKAGE_NODE_NAME)] == PACKAGE_NODE_NAME:
            return offset
    return None


def package_node(index_path: Path) -> bytes | None:
    """The QTSF_PACKAGE record of an existing package index, or None when it has none."""
    data = index_path.read_bytes()
    offset = _package_node(data, index_records(data))
    return None if offset is None else data[offset:offset + _u32(data, offset + 8)]


def entry_words(index: bytes, entry) -> tuple[int, int]:
    """The two u32 flag words of an entry record, which the builder resets."""
    return struct.unpack_from("<II", index, entry.entry_offset + ENTRY_FLAGS)


def entry_flag(index: bytes, entry) -> int:
    """The packed compression flag of an entry record.

    Packages that record no level fall back to the one the game writes, so a rebuilt entry is
    encoded the way the surrounding ones are.
    """
    packed = struct.unpack_from("<I", index, entry.entry_offset + ENTRY_COMPRESSION)[0]
    return packed if packed >> 16 else (DEFAULT_LEVEL << 16) | entry.compression


def finalize(built: Path, package_id: str, file_hashes: set[int], template_node: bytes | None,
             entry_words: dict[int, tuple[int, int]]) -> dict:
    """Align the builder output at <built> with the override package it replaces (see module doc).

    Raises when the build is missing an entry it was given, wrote no package node, or lost the
    template node's size -- all of which would otherwise reach the phone as a broken package.
    """
    index_path = built / f"{package_id}.db"
    data = bytearray(index_path.read_bytes())
    drop = set()
    kept_entries = set()
    node_offset = None
    for offset in index_records(data):
        size = _u32(data, offset + 8)
        if size == ENTRY_SIZE:
            file_hash = struct.unpack_from("<Q", data, offset + 36)[0]
            if file_hash in file_hashes:
                kept_entries.add(file_hash)
                words = entry_words.get(file_hash)
                if words is not None:
                    struct.pack_into("<II", data, offset + ENTRY_FLAGS, *words)
            else:
                drop.add(offset)
        elif data[offset + 32:offset + 32 + len(PACKAGE_NODE_NAME)] == PACKAGE_NODE_NAME:
            node_offset = offset
        elif data[offset + 28:offset + 32] == GLOBAL_INDEX_MAGIC:
            drop.add(offset)
        else:
            raise RuntimeError(f"package {package_id}: unknown index record at {offset:#x} (size {size})")
    if kept_entries != file_hashes:
        raise RuntimeError(f"package {package_id}: {len(file_hashes - kept_entries)} files missing from the build")
    if node_offset is None:
        raise RuntimeError(f"package {package_id}: builder wrote no package node")
    if template_node is not None:
        size = _u32(data, node_offset + 8)
        if len(template_node) != size:
            raise RuntimeError(f"package {package_id}: package node size {size} != original {len(template_node)}")
        data[node_offset + 4:node_offset + size] = template_node[4:]
    removed = remove_records(data, drop)
    index_path.write_bytes(bytes(data))
    return {"entries": len(kept_entries), "removed_records": removed}
