"""Explain duplicate encodes left by the shipped 512-entry / 4096-byte policy.

Reads the saved audit only; no encoding or package staging. Recorded times are
potential work avoided, not a measured speedup from a larger cache.
"""
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
    cache: OrderedDict[int, None] = OrderedDict()
    remaining = {}
    hits = 0
    for call in audit["calls"]:
        number = call["sample"]
        sample = audit["samples"][number]
        small = sample["input_bytes"] <= 4096
        if small and number in cache:
            hits += 1
            cache.move_to_end(number)
            continue
        if call["repeated"]:
            row = remaining.setdefault(number, {
                **sample, "reason": "evicted small input" if small else "over size limit",
                "remaining_calls": 0, "recorded_wall_s": 0.0, "assets": [],
            })
            row["remaining_calls"] += 1
            row["recorded_wall_s"] += call["wall_s"]
            if call["asset"] not in row["assets"]:
                row["assets"].append(call["asset"])
        if small:
            cache[number] = None
            if len(cache) > 512:
                cache.popitem(last=False)
    groups = {}
    for row in remaining.values():
        group = groups.setdefault(row["reason"], {"calls": 0, "recorded_wall_s": 0.0})
        group["calls"] += row["remaining_calls"]
        group["recorded_wall_s"] += row["recorded_wall_s"]
    result = {"audit_calls": audit["call_count"], "existing_hits": hits,
              "remaining_duplicate_calls": sum(r["remaining_calls"] for r in remaining.values()),
              "remaining_recorded_wall_s": sum(r["recorded_wall_s"] for r in remaining.values()),
              "groups": groups,
              "samples": sorted(remaining.values(), key=lambda row: -row["recorded_wall_s"])}
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "samples"}, indent=2))
    print(json.dumps(result["samples"][:4], indent=2))


if __name__ == "__main__":
    main()
