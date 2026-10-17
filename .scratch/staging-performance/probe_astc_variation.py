"""Replay one recorded large ASTC input in fresh processes with fixed initialization order."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit", type=Path)
    parser.add_argument("--sample", type=int, default=1475)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--max-ratio", type=float, default=1.5)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--prime-sequence", action="store_true")
    parser.add_argument("--cpus", help="Comma-separated Windows logical CPU ids, one fresh process each")
    parser.add_argument("--cpu", type=int)
    args = parser.parse_args()
    if args.child:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        kernel.GetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t),
                                                 ctypes.POINTER(ctypes.c_size_t)]
        kernel.SetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        process = kernel.GetCurrentProcess()
        affinity, system = ctypes.c_size_t(), ctypes.c_size_t()
        if not kernel.GetProcessAffinityMask(process, ctypes.byref(affinity), ctypes.byref(system)):
            raise ctypes.WinError(ctypes.get_last_error())
        if args.cpu is not None:
            assert args.cpu >= 0 and affinity.value & (1 << args.cpu), "CPU unavailable to benchmark process"
            if not kernel.SetProcessAffinityMask(process, 1 << args.cpu):
                raise ctypes.WinError(ctypes.get_last_error())
            affinity.value = 1 << args.cpu
        sys.path.insert(0, str(ROOT / "tools"))
        import mobile_graphics as graphics
        audit = json.loads((args.audit / "astc-audit.json").read_text())
        directory = args.audit / "astc-inputs"
        rows = []
        first = audit["calls"][0]["sample"]
        sequence = ([call["sample"] for call in audit["calls"][-72:]] if args.prime_sequence
                    else [args.sample] * args.repeats)
        for number in [first, *sequence]:
            sample = audit["samples"][number]
            rgba = (directory / f"{number}.rgba").read_bytes()
            expected = (directory / f"{number}.astc").read_bytes()
            processor_before = kernel.GetCurrentProcessorNumber()
            wall, cpu = time.perf_counter(), time.process_time()
            encoded = graphics._encode_astc(rgba, sample["width"], sample["height"], sample["bx"], sample["by"])
            rows.append({"sample": number, "wall_s": time.perf_counter() - wall,
                         "cpu_s": time.process_time() - cpu,
                         "processor_before": processor_before,
                         "processor_after": kernel.GetCurrentProcessorNumber(),
                         "affinity_mask": affinity.value,
                         "output_sha256": hashlib.sha256(encoded).hexdigest(),
                         "matches_audit": encoded == expected})
            if len(rows) == 1:
                context = graphics._context(sample["bx"], sample["by"])
                backends = [Path(module.__file__) for name, module in sys.modules.items()
                            if name.startswith("astc_encoder._encoder_")]
                rows[0]["encoder_metadata"] = {
                    "version": graphics.astc_encoder.__version__, "threads": context.threads,
                    "backend_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                       for path in backends},
                    "config": {name: getattr(context.config, name) for name in (
                        "flags", "profile", "tune_partition_count_limit", "tune_block_mode_limit",
                        "tune_refinement_limit", "tune_candidate_limit", "tune_db_limit")},
                }
        print(json.dumps(rows))
        return
    if args.output is None:
        parser.error("--output is required")
    trials = []
    cpus = [int(value) for value in args.cpus.split(",")] if args.cpus else [None] * args.trials
    for trial, cpu_id in enumerate(cpus):
        command = [sys.executable, str(Path(__file__).resolve()), str(args.audit),
                   "--sample", str(args.sample), "--repeats", str(args.repeats), "--child"]
        if args.prime_sequence:
            command.append("--prime-sequence")
        if cpu_id is not None:
            command.extend(["--cpu", str(cpu_id)])
        result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=180)
        rows = json.loads(result.stdout)
        trials.append(rows)
        print(f"trial {trial + 1}, CPU {cpu_id}: {sum(r['wall_s'] for r in rows[1:]):.3f}s total", flush=True)
    steady = [row for trial in trials for row in trial[1:]]
    batch_totals = [sum(row["wall_s"] for row in trial[1:]) for trial in trials]
    comparable = batch_totals if args.prime_sequence else [row["wall_s"] for row in steady]
    ratio = max(comparable) / min(comparable)
    result = {"python": sys.version, "platform": platform.platform(), "audit": str(args.audit.resolve()),
              "sample": args.sample, "prime_sequence": args.prime_sequence,
              "requested_cpus": cpus,
              "batch_wall_seconds": batch_totals, "trials": trials, "maximum_to_minimum_wall_ratio": ratio,
              "ratio_limit": args.max_ratio, "time_variation_detected": ratio > args.max_ratio,
              "all_outputs_match_audit": all(row["matches_audit"] for trial in trials for row in trial)}
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "trials"}, indent=2))
    assert result["all_outputs_match_audit"], "native output changed with fixed inputs/order"
    assert not result["time_variation_detected"], "fixed-input native encoding time varies beyond the limit"


if __name__ == "__main__":
    main()
