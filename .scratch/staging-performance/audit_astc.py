"""Run measure.py unchanged while recording exact ASTC inputs and repeated work.

Accepts measure.py arguments. Use a new external --run directory. Every native
encode still runs; this is an audit, not a caching benchmark. Saves one RGBA/ASTC
pair per unique input under <run>/astc-inputs for exact offline replay.
"""
from __future__ import annotations

import hashlib
import json
import runpy
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.append(str(ROOT / "resources/runtime"))
import mobile_graphics as graphics


def main() -> None:
    run = Path(sys.argv[sys.argv.index("--run") + 1]).resolve()
    encode = graphics.encode_astc
    translate = graphics.english_raw
    unique: dict[tuple, int] = {}
    samples = []
    calls = []
    asset = ""

    def english_raw(raw, graphic, *args, **kwargs):
        nonlocal asset
        previous, asset = asset, graphic["hash"]
        try:
            return translate(raw, graphic, *args, **kwargs)
        finally:
            asset = previous

    def encode_astc(rgba: bytes, width: int, height: int, bx: int, by: int) -> bytes:
        start = time.perf_counter()
        output = encode(rgba, width, height, bx, by)
        wall = time.perf_counter() - start
        key = (rgba, width, height, bx, by)
        digest = hashlib.sha256(output).hexdigest()
        repeated = key in unique
        if not repeated:
            number = len(samples)
            unique[key] = number
            directory = run / "astc-inputs"
            directory.mkdir(exist_ok=True)
            (directory / f"{number}.rgba").write_bytes(rgba)
            (directory / f"{number}.astc").write_bytes(output)
            samples.append({"id": number, "width": width, "height": height,
                            "bx": bx, "by": by, "input_bytes": len(rgba),
                            "output_bytes": len(output), "output_sha256": digest})
        number = unique[key]
        assert samples[number]["output_sha256"] == digest, "identical inputs encoded differently"
        calls.append({"sample": number, "asset": asset, "wall_s": wall, "repeated": repeated})
        return output

    graphics.english_raw = english_raw
    graphics.encode_astc = encode_astc
    runpy.run_path(str(Path(__file__).with_name("measure.py")), run_name="__main__")
    result = {"calls": calls, "samples": samples, "call_count": len(calls),
              "unique_inputs": len(samples), "repeated_calls": sum(c["repeated"] for c in calls),
              "native_wall_s": sum(c["wall_s"] for c in calls),
              "repeated_native_wall_s": sum(c["wall_s"] for c in calls if c["repeated"]),
              "unique_input_bytes": sum(s["input_bytes"] for s in samples),
              "unique_output_bytes": sum(s["output_bytes"] for s in samples)}
    (run / "astc-audit.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("calls", "samples")}, indent=2))


if __name__ == "__main__":
    main()
