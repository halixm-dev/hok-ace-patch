"""Compare legacy and page-only tree reads on saved pristine and staged shards.

Run with Python 3.12, passing one or more existing directories and --output JSON.
Inputs are read only. Each pair must produce the exact same live-offset map.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import qts_relocate as relocate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    original = Path.open
    read_bytes = 0

    class Reader:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            self.handle.__enter__()
            return self

        def __exit__(self, *pos):
            return self.handle.__exit__(*pos)

        def seek(self, *pos):
            return self.handle.seek(*pos)

        def read(self, *pos):
            nonlocal read_bytes
            value = self.handle.read(*pos)
            read_bytes += len(value)
            return value

    paths = sorted({p.resolve() for directory in args.directories
                    for p in directory.rglob("*_0.db")})
    results = []
    for index, path in enumerate(paths):
        row = {"path": str(path), "size": path.stat().st_size}
        # Alternate order to reduce systematic cache-order advantage.
        methods = ("legacy", "pages") if index % 2 else ("pages", "legacy")
        maps = {}
        for method in methods:
            read_bytes = 0
            with patch.object(Path, "open", lambda p, *a, **kw: Reader(original(p, *a, **kw))):
                start = time.perf_counter()
                maps[method] = (relocate.btree_offsets(relocate.Shard(path)) if method == "legacy"
                                else relocate._read_btree_offsets(path))
                elapsed = time.perf_counter() - start
            row[method] = {"wall_s": elapsed, "bytes_read": read_bytes}
        assert maps["legacy"] == maps["pages"], path
        row["map_equal"] = True
        results.append(row)
    result = {"shards": len(results), "all_maps_equal": True, "results": results}
    for method in ("legacy", "pages"):
        result[method] = {key: sum(row[method][key] for row in results)
                          for key in ("wall_s", "bytes_read")}
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "results"}, indent=2))


if __name__ == "__main__":
    main()
