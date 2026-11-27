"""Index every compressed chunk of a dump, with what the Python codecs make of it (`rust/DECISIONS.md` wave 1).

The Rust codecs are held to the Python ones on the game's own data (ADR-010, ADR-022). This walks
every package under the given folders with the pipeline's own reader (`QtsPackage` and the B-tree slot
map, as `qts_relocate.read_raw` does), classifies each chunk the way `read_raw` does (stored, zstd by
its magic, LZ4 for ids 1 and 9, Oodle for id 4) and writes one JSON line per chunk:

    {"shard": <index into "shards">, "offset", "size", "raw", "kind": "stored|zstd|lz4|oodle|other",
     "decoded": <SHA-256 of the Python decode, or null when it raised>,
     "hc12": [<length>, <SHA-256>] (LZ4 only: python-lz4 HC 12, raw block, of the decoded bytes)}

The first line is {"shards": [<path>, ...], "versions": {...}}. Only offsets go in, never payloads, so
the index is small; the Rust check reads the shards itself.

    .venv\\Scripts\\python.exe rust\\harness\\codec_corpus.py --out <corpus.jsonl> <package root> [...]
    .venv\\Scripts\\python.exe rust\\harness\\codec_corpus.py --out <prime.jsonl> --apk <normal.apk>

With ``--apk``, extract the built-in package shards beside the index so Rust can reopen them.

Migration tooling, run by hand: the exe, the APK and ``tools/`` never import it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools")]
sys.path.append(str(ROOT / "resources" / "runtime"))

import lz4  # noqa: E402
import lz4.block  # noqa: E402
import ooz  # noqa: E402
import zstandard  # noqa: E402
from package_rebuild import extract_prime  # noqa: E402
from qts_relocate import LZ4_CODECS, ZSTD_MAGIC, install_btree_slot_map  # noqa: E402
from wxq_patch.qtsvfs import QtsPackage  # noqa: E402


def _decode(kind: str, payload: bytes, raw: int) -> bytes:
    if kind == "stored":
        return payload
    if kind == "zstd":
        return zstandard.ZstdDecompressor().decompress(payload, max_output_size=raw)
    if kind == "lz4":
        return lz4.block.decompress(payload, uncompressed_size=raw)
    if kind == "oodle":
        return ooz.decompress(payload, raw)
    raise ValueError(kind)


def index(roots: list[pathlib.Path], out: pathlib.Path) -> dict:
    install_btree_slot_map()
    shards: list[str] = []
    counts: dict[str, int] = {}
    started = time.perf_counter()
    with out.open("w", encoding="utf-8") as lines:
        packages = sorted({db.parent for root in roots for db in root.rglob("*.db")})
        records = []
        for package_dir in packages:
            try:
                package = QtsPackage(package_dir)
                slots = package.build_slot_map()
            except Exception as error:  # noqa: BLE001 - a package that will not read is reported, not fatal
                print(f"skip {package_dir}: {error}", file=sys.stderr)
                continue
            for file_hash, chunks in slots.items():
                entry = package.entries.get(file_hash)
                for _, slot in sorted(chunks.items()):
                    path = str(pathlib.Path(slot.shard_path).resolve())
                    if path not in shards:
                        shards.append(path)
                    with open(slot.shard_path, "rb") as handle:
                        handle.seek(slot.payload_offset)
                        payload = handle.read(slot.compressed_size)
                    raw = slot.uncompressed_size
                    if slot.compressed_size == raw:
                        kind = "stored"
                    elif payload[:4] == ZSTD_MAGIC:
                        kind = "zstd"
                    elif entry is not None and entry.compression in LZ4_CODECS:
                        kind = "lz4"
                    elif entry is not None and entry.compression == 4:
                        kind = "oodle"
                    else:
                        kind = "other"
                    record = {"shard": shards.index(path), "offset": slot.payload_offset,
                              "size": slot.compressed_size, "raw": raw, "kind": kind, "decoded": None}
                    if kind != "other":
                        try:
                            decoded = _decode(kind, payload, raw)
                            record["decoded"] = hashlib.sha256(decoded).hexdigest()
                            if kind == "lz4":
                                packed = lz4.block.compress(decoded, mode="high_compression", compression=12,
                                                            store_size=False)
                                record["hc12"] = [len(packed), hashlib.sha256(packed).hexdigest()]
                        except Exception:  # noqa: BLE001 - recorded as a failed decode, as read_raw treats it
                            pass
                    counts[kind] = counts.get(kind, 0) + 1
                    records.append(record)
            print(f"{package_dir.name}: {sum(counts.values())} chunks so far", flush=True)
        head = {"shards": shards, "versions": {"lz4": lz4.library_version_string(),
                                               "zstd": ".".join(map(str, zstandard.ZSTD_VERSION))}}
        lines.write(json.dumps(head) + "\n")
        for record in records:
            lines.write(json.dumps(record, separators=(",", ":")) + "\n")
    print(f"{counts} in {time.perf_counter() - started:.0f}s -> {out}")
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=pathlib.Path, required=True)
    parser.add_argument("--apk", type=pathlib.Path)
    parser.add_argument("roots", type=pathlib.Path, nargs="*")
    args = parser.parse_args()
    roots = args.roots
    if args.apk:
        prime = args.out.with_name(f"{args.out.stem}-prime")
        packages = extract_prime(args.apk, None, prime)
        if not packages:
            parser.error("the APK contains no built-in packages")
        roots += list(packages.values())
    if not roots:
        parser.error("provide a package root or --apk")
    index(roots, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
