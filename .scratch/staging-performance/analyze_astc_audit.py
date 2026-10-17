"""Model bounded exact-input reuse on a recorded ASTC audit, without encoding."""
from __future__ import annotations

import argparse
import json
from collections import OrderedDict
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit = json.loads(args.audit.read_text())
    results = []
    for limit in (4096, 8192, 16384, 65536):
        for capacity in (128, 256, 512):
            cache: OrderedDict[int, None] = OrderedDict()
            hits = 0
            saved = 0.0
            peak = 0
            for call in audit["calls"]:
                sample = audit["samples"][call["sample"]]
                if sample["input_bytes"] > limit:
                    continue
                number = sample["id"]
                if number in cache:
                    hits += 1
                    saved += call["wall_s"]
                    cache.move_to_end(number)
                else:
                    cache[number] = None
                    if len(cache) > capacity:
                        cache.popitem(last=False)
                    peak = max(peak, sum(audit["samples"][i]["input_bytes"] +
                                         audit["samples"][i]["output_bytes"] for i in cache))
            results.append({"max_input_bytes": limit, "capacity": capacity,
                            "hits": hits, "recorded_hit_native_wall_s": saved,
                            "peak_input_output_bytes": peak})
    result = {key: value for key, value in audit.items() if key not in ("calls", "samples")}
    result["bounded_reuse_models"] = results
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
