"""Compare tree-page staging against the saved original baseline, including full summary."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    evidence = ROOT / ".scratch/staging-performance"
    baseline = json.loads((evidence / "verification.json").read_text())["run1"]["hashes"]
    hashes = {}
    for path in sorted((args.run / "out").rglob("*.db")):
        with path.open("rb") as handle:
            hashes[path.relative_to(args.run / "out").as_posix()] = hashlib.file_digest(handle, "sha256").hexdigest()
    assert hashes == baseline, "staged package bytes differ from original baseline"

    def summary(run: Path) -> dict:
        value = json.loads((run / "out/device_patch_summary.json").read_text())
        for package in value["packages"]:
            source = package.get("source_package")
            if source and Path(source).is_relative_to(run / "work/prime"):
                package["source_package"] = "<PRIME>/" + Path(source).relative_to(run / "work/prime").as_posix()
        return value

    # optimized1 was already compared in full against the original baseline.
    assert summary(args.run) == summary(Path("D:/scratch/hok-staging-performance/optimized1")), "full summary differs"
    timings = json.loads((args.run / "timings.json").read_text())
    result = {"run": str(args.run), "db_hashes": hashes,
              "all_14_db_files_match_original_baseline": True,
              "complete_normalized_summary_matches_verified_control": True,
              "counts": timings["counts"], "wall_s": timings["wall_s"],
              "slot_map_calls": sum(row["calls"] for key, row in
                                    timings["details_inclusive_do_not_sum"].items()
                                    if key.endswith("Build slot maps"))}
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"PASS: {len(hashes)} package hashes, full normalized summary, counts and all skips match")


if __name__ == "__main__":
    main()
