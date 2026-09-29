from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path


def qts_hash(data: bytes) -> int:
    forward = 0x5BD1E995
    for byte in data:
        forward = ((forward * 33) ^ byte) & 0xFFFFFFFF
    backward = 0xAB9423A7
    for byte in reversed(data):
        backward = ((backward * 33) ^ byte) & 0xFFFFFFFF
    return forward | (backward << 32)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--vendor", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("hashes", nargs="+")
    args = parser.parse_args()
    sys.path[:0] = [str(args.runtime.resolve()), str(args.vendor.resolve())]

    import cityhash
    import mmh3
    import xxhash
    from wxq_patch.qtsvfs import QtsPackage

    package = QtsPackage.from_flat_dir(args.package)
    for text_hash in args.hashes:
        file_hash = int(text_hash, 16)
        entry = package.entries[file_hash]
        raw = package.extract(file_hash)
        with package.index_path.open("rb") as stream:
            stream.seek(entry.entry_offset + 28)
            descriptor = stream.read(32)
        words = struct.unpack("<8I", descriptor)
        expected = struct.unpack_from("<Q", descriptor, 24)[0]
        candidates = {
            "qts": qts_hash(raw),
            "city": cityhash.CityHash64(raw),
            "city_seed0": cityhash.CityHash64WithSeed(raw, 0),
            "city_seed_file": cityhash.CityHash64WithSeed(raw, file_hash),
            "xxh64": xxhash.xxh64_intdigest(raw),
            "xxh3": xxhash.xxh3_64_intdigest(raw),
            "mmh3_64_a": mmh3.hash64(raw, signed=False)[0],
            "mmh3_64_b": mmh3.hash64(raw, signed=False)[1],
        }
        print(f"{file_hash:016X} size={len(raw)} descriptor={descriptor.hex()} words={words}")
        print(f"  expected={expected:016X}")
        for name, value in candidates.items():
            print(f"  {name:16s}={value:016X}{' MATCH' if value == expected else ''}")


if __name__ == "__main__":
    main()
