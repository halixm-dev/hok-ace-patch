"""Compare actual legacy and direct-buffer Shard I/O, bytes and Python memory.

Requires a NEW external --work directory, plus --output JSON. Generates a 64 MiB
valid synthetic shard and reuses two disposable copies over three alternating
rounds. Excludes fixture/copy setup and hashes from timings. Keeps generated files.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import shutil
import struct
import time
import tracemalloc
from pathlib import Path

from check_shard_io import ROOT, fixture
from qts_relocate import FILE_GROWTH, Shard


class LegacyShard(Shard):
    def __init__(self, path: Path):
        self.path = path
        self.data = bytearray(path.read_bytes())
        self.data_end = self._u32(8)
        self.leaves = self._active_leaf_pages()
        self.relocated = 0

    def save(self) -> None:
        size = max(self._u32(12), (self.data_end + FILE_GROWTH - 1) // FILE_GROWTH * FILE_GROWTH)
        if len(self.data) < size:
            self.data.extend(b"\0" * (size - len(self.data)))
        struct.pack_into("<II", self.data, 8, self.data_end, size)
        self.path.write_bytes(bytes(self.data[:size]))


class WholeFileShard(Shard):
    def save(self) -> None:
        size = max(self._u32(12), (self.data_end + FILE_GROWTH - 1) // FILE_GROWTH * FILE_GROWTH)
        if len(self.data) < size:
            self.data.extend(b"\0" * (size - len(self.data)))
        struct.pack_into("<II", self.data, 8, self.data_end, size)
        with memoryview(self.data)[:size] as buffer:
            self.path.write_bytes(buffer)


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--control", choices=("legacy", "whole"), default="legacy")
    parser.add_argument("--append-mib", type=int, default=0)
    args = parser.parse_args()
    work = args.work.resolve()
    if work.exists() or work.is_relative_to(ROOT):
        parser.error("--work must be a new directory outside the repository")
    work.mkdir(parents=True)
    source = work / "source.db"
    size = 64 * 1024 * 1024
    fixture(source, size)
    original_hash = digest(source)
    rows = []
    for number in range(3):
        hashes = {}
        modes = (args.control, "direct") if number % 2 == 0 else ("direct", args.control)
        for mode in modes:
            target = work / f"{mode}.db"
            shutil.copy2(source, target)
            row = {"round": number + 1, "mode": mode}
            gc.collect()
            tracemalloc.start()
            wall, cpu = time.perf_counter(), time.process_time()
            factory = {"legacy": LegacyShard, "whole": WholeFileShard, "direct": Shard}[mode]
            shard = factory(target)
            row["load_wall_s"], row["load_cpu_s"] = time.perf_counter() - wall, time.process_time() - cpu
            row["load_peak_python_bytes"] = tracemalloc.get_traced_memory()[1]
            tracemalloc.stop()
            shard.data[-1] = 19
            if args.append_mib:
                shard.data.extend(bytes(args.append_mib * 1024 * 1024))
                shard.data_end += args.append_mib * 1024 * 1024
            tracemalloc.start()
            wall, cpu = time.perf_counter(), time.process_time()
            shard.save()
            row["save_wall_s"], row["save_cpu_s"] = time.perf_counter() - wall, time.process_time() - cpu
            row["save_peak_extra_python_bytes"] = tracemalloc.get_traced_memory()[1]
            tracemalloc.stop()
            del shard
            hashes[mode] = digest(target)
            rows.append(row)
        assert hashes[args.control] == hashes["direct"], "saved bytes differ"
    assert digest(source) == original_hash, "source changed"
    result = {"shard_bytes": size, "control": args.control, "append_mib": args.append_mib,
              "all_saved_hashes_equal": True,
              "source_unchanged": True, "results": rows}
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
