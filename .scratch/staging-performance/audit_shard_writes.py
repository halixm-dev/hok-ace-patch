"""Run measure.py while counting actual shard-save reads and submitted write bytes.

Accepts measure.py arguments, including a fresh external --run directory. Counts
Python file I/O, not physical disk traffic. Each save also records the full file
size the preceding whole-file implementation would have submitted for writing.
"""
from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import qts_relocate


def main() -> None:
    run = Path(sys.argv[sys.argv.index("--run") + 1]).resolve()
    original_open = Path.open
    original_save = qts_relocate.Shard.save
    active = None
    rows = []

    class File:
        def __init__(self, handle, row):
            self.handle, self.row = handle, row

        def __enter__(self):
            self.handle.__enter__()
            return self

        def __exit__(self, *args):
            return self.handle.__exit__(*args)

        def __getattr__(self, name):
            return getattr(self.handle, name)

        def read(self, size=-1):
            result = self.handle.read(size)
            self.row["read_bytes"] += len(result)
            return result

        def write(self, value):
            result = self.handle.write(value)
            self.row["write_bytes"] += result
            self.row["write_calls"] += 1
            return result

    def open_file(path, *args, **kwargs):
        handle = original_open(path, *args, **kwargs)
        return File(handle, active) if active is not None else handle

    def save(shard) -> None:
        nonlocal active
        row = {"path": str(shard.path), "read_bytes": 0, "write_bytes": 0, "write_calls": 0}
        active = row
        try:
            original_save(shard)
        finally:
            active = None
        row["whole_file_write_bytes"] = shard.path.stat().st_size
        rows.append(row)

    with patch.object(Path, "open", open_file), patch.object(qts_relocate.Shard, "save", save):
        runpy.run_path(str(Path(__file__).with_name("measure.py")), run_name="__main__")
    result = {"saves": len(rows), "results": rows}
    for field in ("read_bytes", "write_bytes", "write_calls", "whole_file_write_bytes"):
        result[field] = sum(row[field] for row in rows)
    result["write_reduction_percent"] = 100 * (1 - result["write_bytes"] / result["whole_file_write_bytes"])
    (run / "shard-write-audit.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "results"}, indent=2))


if __name__ == "__main__":
    main()
