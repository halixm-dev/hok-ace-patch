"""Compare verified Android staging with its desktop control, including every asset's bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.append(str(ROOT / "resources/runtime"))


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desktop", type=Path, required=True)
    parser.add_argument("--android", type=Path, required=True)
    parser.add_argument("--hashes", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--adb", type=Path)
    parser.add_argument("--serial")
    parser.add_argument("--session")
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12):
        parser.error("Python 3.12 is required")
    if args.adb and (not args.serial or not args.session or
                     not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", args.session)):
        parser.error("Fetching needs --serial and a validated --session")
    expected = json.loads(args.hashes.read_text(encoding="utf-8"))
    for name, digest in expected.items():
        if not re.fullmatch(r"([0-9]+)/\1(?:_0)?[.]db", name):
            raise ValueError(f"Unexpected staged filename: {name}")
        target = args.android / name
        if args.adb and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            partial = target.with_suffix(target.suffix + ".partial")
            with partial.open("wb") as stream:
                process = subprocess.Popen([str(args.adb), "-s", args.serial, "exec-out", "run-as",
                                            "dev.halixm.hokacepatcher", "cat",
                                            f"files/scratch/{args.session}/out/{name}"], stdout=subprocess.PIPE)
                try:
                    shutil.copyfileobj(process.stdout, stream, 1024 * 1024)
                    if process.wait(timeout=30):
                        raise RuntimeError(f"ADB fetch failed: {name}")
                finally:
                    process.stdout.close()
                    if process.poll() is None:
                        process.kill()
                        process.wait()
            if sha256(partial) != digest:
                raise RuntimeError(f"Fetched output hash mismatch: {name}")
            partial.replace(target)
        if sha256(target) != digest:
            raise RuntimeError(f"Android output changed: {name}")

    import mobile_graphics as mg
    from qts_relocate import install_btree_slot_map, read_raw
    from wxq_patch import adaptive
    from wxq_patch.qtsvfs import QtsPackage

    install_btree_slot_map()
    catalog = adaptive.load_catalog(ROOT / "resources/catalog")
    report = {"identical_files": [], "identical_assets": 0, "unreadable_both": [],
              "textures": [], "failures": []}
    differing = set()
    for name in expected:
        if sha256(args.desktop / name) == expected[name]:
            report["identical_files"].append(name)
        else:
            differing.add(name.split("/")[0])
    for package_id in sorted(differing):
        pc, arm = QtsPackage(args.desktop / package_id), QtsPackage(args.android / package_id)
        if set(pc.entries) != set(arm.entries):
            raise RuntimeError(f"Entry set mismatch: {package_id}")
        pc_slots, arm_slots = pc.build_slot_map(), arm.build_slot_map()
        for asset in pc.entries:
            left, right = read_raw(pc, pc_slots, asset), read_raw(arm, arm_slots, asset)
            identity = f"{package_id}/{asset:016X}"
            if left is None and right is None:
                report["unreadable_both"].append(identity)
                continue
            if left == right:
                report["identical_assets"] += 1
                continue
            if left is None or right is None or len(left) != len(right) or asset not in catalog.graphics:
                report["failures"].append(identity + ": unexpected raw difference")
                continue
            graphic = catalog.graphics[asset]
            width, height, _ = mg._dimensions(graphic)
            layout = mg.astc_layout(len(left), width, height)
            if layout is None:
                candidates = mg.offset_layouts(len(left), width, height)
                if len(candidates) != 1:
                    report["failures"].append(identity + ": ambiguous texture geometry")
                    continue
                height, bx, by = candidates[0]
            else:
                bx, by = layout
            pc_rgba = mg.decode_astc(left, width, height, bx, by)
            arm_rgba = mg.decode_astc(right, width, height, bx, by)
            differences = [abs(a - b) for a, b in zip(pc_rgba, arm_rgba)]
            mean = sum(differences) / len(differences)
            report["textures"].append({"asset": identity, "width": width, "height": height,
                                       "footprint": [bx, by], "mean_rgba_difference": mean,
                                       "maximum_channel_difference": max(differences)})
            # Same tolerance as the independent ASTC round-trip oracle; record maxima too.
            if mean > 2.0:
                report["failures"].append(identity + f": decoded mean difference {mean:.6f} > 2")
        print(f"Compared all {len(pc.entries)} assets of package {package_id}", flush=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: len(value) if isinstance(value, list) else value
                      for key, value in report.items()}, indent=2))
    if report["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
