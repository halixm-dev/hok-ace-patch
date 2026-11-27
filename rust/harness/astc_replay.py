"""Check ASTC encoder output against a codec tap (ADR-026).

Write candidate blocks as ``<width>x<height>-<bx>x<by>-<input SHA-256>.astc``
in the candidate folder. Files contain raw blocks in texture row order, without
an ASTC file header. Use the same tap inputs for every candidate.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import texture2ddecoder


MEAN_LIMIT = 2.0
MAX_LIMIT = 48


def replay(tap: Path, candidate: Path, failure_limit: int) -> bool:
    passed: Counter[str] = Counter()
    total: Counter[str] = Counter()
    identical = failures = 0
    worst_mean = 0.0
    worst_max = 0

    with (tap / "calls.jsonl").open(encoding="utf-8") as records:
        for line in records:
            call = json.loads(line)
            if call["fn"] != "encode_astc":
                continue

            width, height, bx, by = call["args"]
            footprint = f"{bx}x{by}"
            name = f"{width}x{height}-{footprint}-{call['input']}.astc"
            total[footprint] += 1

            reference = (tap / "blobs" / call["output"]).read_bytes()
            if hashlib.sha256(reference).hexdigest() != call["output"]:
                raise ValueError(f"reference hash mismatch for {name}")
            expected_size = ((width + bx - 1) // bx) * ((height + by - 1) // by) * 16
            if not (width > 0 and height > 0 and len(reference) == expected_size):
                raise ValueError(f"invalid reference size for {name}")

            try:
                encoded = (candidate / name).read_bytes()
                if len(encoded) != expected_size:
                    raise ValueError(f"expected {expected_size} bytes, got {len(encoded)}")
                if encoded == reference:
                    identical += 1
                else:
                    before = texture2ddecoder.decode_astc(reference, width, height, bx, by)
                    after = texture2ddecoder.decode_astc(encoded, width, height, bx, by)
                    difference_sum = maximum = worst_byte = 0
                    for index, (before_byte, after_byte) in enumerate(zip(before, after, strict=True)):
                        difference = abs(before_byte - after_byte)
                        difference_sum += difference
                        if difference > maximum:
                            maximum = difference
                            worst_byte = index
                    mean = difference_sum / len(before)
                    worst_mean = max(worst_mean, mean)
                    worst_max = max(worst_max, maximum)
                    if mean > MEAN_LIMIT or maximum > MAX_LIMIT:
                        y, x = divmod(worst_byte // 4, width)
                        channel = "BGRA"[worst_byte % 4]
                        raise ValueError(f"mean {mean:.3f}, max {maximum} at ({x}, {y}) {channel}")
            except (OSError, ValueError, RuntimeError) as error:
                if failures < failure_limit:
                    print(f"{name}: {error}")
                failures += 1
            else:
                passed[footprint] += 1

    if not total:
        raise ValueError("tap has no ASTC encode calls")
    for footprint, count in sorted(total.items()):
        print(f"{footprint}: {passed[footprint]}/{count} passed")
    print(f"{identical} byte-identical, {failures} failed, worst mean {worst_mean:.3f}, max {worst_max}")
    return failures == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tap", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--failure-limit", type=int, default=10)
    args = parser.parse_args()
    return 0 if replay(args.tap, args.candidate, args.failure_limit) else 1


if __name__ == "__main__":
    raise SystemExit(main())
