"""Replay real small ASTC inputs with native versus bounded reuse, comparing exact bytes.

Pass the external audit run directory and --output JSON. Uses the unchanged native
encoder as the control. Alternates order over three rounds; empties the cache each
round. Large unique images are verified by full staging instead.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import mobile_graphics as graphics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit_run", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit = json.loads((args.audit_run / "astc-audit.json").read_text())
    # Preserve the original first native call. Omitting the initial large 8x8
    # image changes native bytes for sample 240 even with reuse disabled.
    first = audit["samples"][audit["calls"][0]["sample"]]
    directory = args.audit_run / "astc-inputs"
    first_id = first["id"]
    first_output = graphics._encode_astc((directory / f"{first_id}.rgba").read_bytes(),
                                        first["width"], first["height"], first["bx"], first["by"])
    assert first_output == (directory / f"{first_id}.astc").read_bytes()
    samples = {}
    for sample in audit["samples"]:
        if sample["input_bytes"] <= graphics.ASTC_CACHE_MAX_INPUT:
            number = sample["id"]
            directory = args.audit_run / "astc-inputs"
            samples[number] = ((directory / f"{number}.rgba").read_bytes(),
                               (directory / f"{number}.astc").read_bytes(), sample)
    sequence = [c["sample"] for c in audit["calls"] if c["sample"] in samples]
    results = []
    for round_number in range(3):
        modes = ("native", "reuse") if round_number % 2 == 0 else ("reuse", "native")
        for mode in modes:
            graphics._encode_astc_cached.cache_clear()
            encode = graphics._encode_astc if mode == "native" else graphics.encode_astc
            wall, cpu = time.perf_counter(), time.process_time()
            for number in sequence:
                rgba, expected, sample = samples[number]
                encoded = encode(rgba, sample["width"], sample["height"], sample["bx"], sample["by"])
                assert encoded == expected, (f"round {round_number + 1} {mode}: sample {number} "
                                             "differs from audited native bytes")
            wall, cpu = time.perf_counter() - wall, time.process_time() - cpu
            info = graphics._encode_astc_cached.cache_info()
            results.append({"round": round_number + 1, "mode": mode, "wall_s": wall,
                            "cpu_s": cpu, "native_calls": len(sequence) if mode == "native" else info.misses,
                            "all_bytes_equal": True, "cache": info._asdict()})
    result = {"first_native_sample_preserved": first_id,
              "small_requests": len(sequence), "unique_small_inputs": len(samples), "results": results}
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
