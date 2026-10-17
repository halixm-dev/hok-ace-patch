"""Replay the full audited ASTC call sequence at several encoder thread counts.

Each thread count runs in a fresh child process (the encoder context keeps state
between calls), replays every audited call in order through `_encode_astc`, and
compares each output with the recorded native bytes. Pass the external audit run
directory and --output JSON. Exits nonzero when any thread count changes a byte.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def child(audit_run: Path, threads: int, only_large: bool) -> dict:
    sys.path.insert(0, str(ROOT / "tools"))
    import astc_encoder
    import mobile_graphics as graphics

    def context(bx: int, by: int):
        if (bx, by) not in graphics._contexts:
            config = astc_encoder.ASTCConfig(astc_encoder.ASTCProfile.LDR, bx, by, 1, 85)
            graphics._contexts[(bx, by)] = astc_encoder.ASTCContext(config, threads)
        return graphics._contexts[(bx, by)]

    graphics._context = context
    audit = json.loads((audit_run / "astc-audit.json").read_text())
    samples = {s["id"]: s for s in audit["samples"]}
    directory = audit_run / "astc-inputs"
    calls = [c["sample"] for c in audit["calls"]]
    mismatches, large_wall, total_wall = [], 0.0, 0.0
    for index, number in enumerate(calls):
        sample = samples[number]
        rgba = (directory / f"{number}.rgba").read_bytes()
        start = time.perf_counter()
        encoded = graphics._encode_astc(rgba, sample["width"], sample["height"],
                                        sample["bx"], sample["by"])
        elapsed = time.perf_counter() - start
        total_wall += elapsed
        if sample["input_bytes"] > graphics.ASTC_CACHE_MAX_INPUT:
            large_wall += elapsed
        if encoded != (directory / f"{number}.astc").read_bytes():
            mismatches.append({"call": index, "sample": number})
    return {"threads": threads, "calls": len(calls), "mismatches": mismatches[:20],
            "mismatch_count": len(mismatches), "encode_wall_s": total_wall,
            "large_encode_wall_s": large_wall}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit_run", type=Path)
    parser.add_argument("--threads", default="1,2,4,8")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--child", type=int)
    args = parser.parse_args()
    if args.child is not None:
        print(json.dumps(child(args.audit_run, args.child, False)))
        return
    results = []
    for threads in [int(t) for t in args.threads.split(",")]:
        run = subprocess.run([sys.executable, __file__, str(args.audit_run), "--child", str(threads)],
                             capture_output=True, text=True, check=True)
        results.append(json.loads(run.stdout.strip().splitlines()[-1]))
        print(json.dumps(results[-1]), flush=True)
    receipt = {"cpu_count": os.cpu_count(), "results": results,
               "all_bytes_equal": all(r["mismatch_count"] == 0 for r in results)}
    if args.output:
        args.output.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    sys.exit(0 if receipt["all_bytes_equal"] else 1)


if __name__ == "__main__":
    main()
