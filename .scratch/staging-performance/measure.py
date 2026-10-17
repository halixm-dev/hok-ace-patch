"""Measure offline staging stages without changing the shipping pipeline.

Each invocation needs a fresh run directory outside the repository. Stage totals
are exclusive of other measured stages; detail totals are nested and must not be
added to stages. Optional cProfile adds overhead, so compare wall times only from
unprofiled runs. Source dump and APK are read only.
"""
from __future__ import annotations

import argparse
import cProfile
import functools
import json
import platform
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, required=True)
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--language", choices=("en", "id"), default="en")
    parser.add_argument("--profile", action="store_true")
    args = parser.parse_args()
    run = args.run.resolve()
    if run.is_relative_to(ROOT) or run.exists():
        parser.error("--run must be a new directory outside the repository")
    if not args.game.is_dir() or not args.apk.is_file():
        parser.error("game directory and APK must exist")
    run.mkdir(parents=True)
    sys.path.insert(0, str(ROOT / "tools"))
    sys.path.append(str(ROOT / "resources/runtime"))

    import build_device_patch as staging
    import device_extensions
    import extra_text
    import mobile_graphics
    import package_rebuild
    import qts_insert
    import qts_relocate
    import terminology
    from wxq_patch import adaptive, unity_package_installer
    from wxq_patch.qtsvfs import QtsPackage

    # Install before wrapping: build_patch repeats these idempotent installs.
    qts_relocate.install_btree_slot_map()
    terminology.install()
    stages: dict[str, dict[str, Any]] = {}
    details: dict[str, dict[str, Any]] = {}
    stack: list[dict[str, Any]] = []

    def wrap(owner: Any, name: str, label: str, *, detail: bool = False) -> None:
        original = getattr(owner, name)

        @functools.wraps(original)
        def measured(*pos: Any, **kw: Any) -> Any:
            frame = {"label": label, "wall": time.perf_counter(), "cpu": time.process_time(),
                     "child_wall": 0.0, "child_cpu": 0.0}
            if not detail:
                stack.append(frame)
            try:
                return original(*pos, **kw)
            finally:
                wall = time.perf_counter() - frame["wall"]
                cpu = time.process_time() - frame["cpu"]
                table = details if detail else stages
                key = f"{stack[-1]['label']} / {label}" if detail and stack else label
                row = table.setdefault(key, {"calls": 0, "wall_s": 0.0, "cpu_s": 0.0})
                row["calls"] += 1
                row["wall_s"] += wall if detail else wall - frame["child_wall"]
                row["cpu_s"] += cpu if detail else cpu - frame["child_cpu"]
                if not detail:
                    stack.pop()
                    if stack:
                        stack[-1]["child_wall"] += wall
                        stack[-1]["child_cpu"] += cpu
                    print(f"TIMING {label}: {wall:.3f}s wall, {cpu:.3f}s CPU", flush=True)

        setattr(owner, name, measured)

    for owner, name, label in (
        (adaptive, "load_catalog", "Catalog loading and terminology"),
        (adaptive, "scan", "Scan and translate text"),
        (staging, "_drop_uncatalogued_tables", "Catalog-only filtering"),
        (staging, "_expand_staged_tokens", "Resource token expansion"),
        (device_extensions, "exclude_extra_chunks", "Text chunk eligibility"),
        (unity_package_installer, "stage_unity_package", "Write text packages"),
        (unity_package_installer, "capacity_report", "Fit-only capacity check"),
        (device_extensions, "relocate_text", "Relocate overflow text"),
        (device_extensions, "extend_graphics", "Texture pass and discovery"),
        (extra_text, "extend_text", "Extra text pass"),
        (device_extensions, "repair_card_dictionaries", "Repair card dictionaries"),
        (package_rebuild, "make_transform", "Prepare APK transforms"),
        (package_rebuild, "add_prime_only", "Append APK-only assets"),
    ):
        wrap(owner, name, label)
    for owner, name, label in (
        (adaptive, "discover", "Discover packages"),
        (adaptive, "translate_table", "Translate tables"),
        (QtsPackage, "build_slot_map", "Build slot maps"),
        (qts_relocate, "read_raw", "Read/decompress assets"),
        (qts_relocate.Shard, "__init__", "Load writable shards"),
        (qts_relocate.Shard, "save", "Save writable shards"),
        (package_rebuild, "extract_prime", "Extract APK packages"),
        (qts_insert, "add_assets", "Append and verify package assets"),
        (mobile_graphics, "encode_astc", "ASTC encoding"),
        (mobile_graphics, "decode_astc", "ASTC decoding"),
    ):
        wrap(owner, name, label, detail=True)

    profiler = cProfile.Profile() if args.profile else None
    with (run / "staging.log").open("w", encoding="utf-8") as log_file:
        def log(message: str) -> None:
            log_file.write(message + "\n")
            log_file.flush()
            print(message, flush=True)

        start_wall, start_cpu = time.perf_counter(), time.process_time()
        if profiler:
            profiler.enable()
        try:
            summary = staging.build_patch(
                args.game.resolve(),
                ROOT / "resources" / ("catalog_id" if args.language == "id" else "catalog"),
                run / "work", run / "out", apk=args.apk.resolve(), log=log,
            )
        finally:
            if profiler:
                profiler.disable()
                profiler.dump_stats(str(run / "calls.prof"))
        wall, cpu = time.perf_counter() - start_wall, time.process_time() - start_cpu
    result = {
        "python": sys.version, "platform": platform.platform(),
        "game": str(args.game.resolve()), "apk": str(args.apk.resolve()),
        "language": args.language, "profiled": args.profile,
        "wall_s": wall, "cpu_s": cpu, "stages_exclusive": stages,
        "details_inclusive_do_not_sum": details,
        "unattributed_wall_s": wall - sum(row["wall_s"] for row in stages.values()),
        "counts": summary["counts"],
    }
    if hasattr(mobile_graphics, "_encode_astc_cached"):
        result["astc_small_input_cache"] = mobile_graphics._encode_astc_cached.cache_info()._asdict()
    (run / "timings.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
