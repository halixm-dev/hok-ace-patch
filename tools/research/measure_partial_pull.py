"""Measure what `Patcher.pull_changed` would pull, offline, against a kept session and a stand-in phone.

    .venv\\Scripts\\python.exe tools\\research\\measure_partial_pull.py --previous <session> ^
        --phone <layer dir> [--overlay <staged dir>] [--copy-to <scratch dir>]

<phone> is a layer as the phone holds it (`game/WXQ_Data/Package/builtin` of a kept dump); <overlay>
lays a staged output over it, as the phone looks after that install. The phone's hashes are taken
locally. Prints the files and bytes a partial pull copies and pulls, the time spent hashing, and with
<copy-to> the time copying the reused files there (the folder is removed afterwards).
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app"))
from patcher_core import LAYER, reusable_files  # noqa: E402
import pristine_delta  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--phone", type=Path, required=True)
    parser.add_argument("--overlay", type=Path)
    parser.add_argument("--copy-to", type=Path)
    args = parser.parse_args()

    phone = {path.relative_to(args.phone).as_posix(): path for path in args.phone.rglob("*") if path.is_file()}
    if args.overlay:
        for name in pristine_delta.package_files(args.overlay):
            phone[name] = args.overlay / name
    start = time.perf_counter()
    device = {name: pristine_delta.sha256_file(path) for name, path in phone.items()}
    phone_seconds = time.perf_counter() - start

    start = time.perf_counter()
    found, missing = reusable_files(device, [args.previous / "staged", args.previous / LAYER])
    match_seconds = time.perf_counter() - start
    total = sum(path.stat().st_size for path in phone.values())
    reused = sum(phone[name].stat().st_size for name in found)
    pulled = sum(phone[name].stat().st_size for name in missing)
    print(f"phone layer: {len(device)} files, {total / 1e6:.1f} MB (hashed locally in {phone_seconds:.1f} s)")
    print(f"reused from {args.previous.name}: {len(found)} files, {reused / 1e6:.1f} MB "
          f"(hashing and matching {match_seconds:.1f} s)")
    print(f"pulled: {len(missing)} files, {pulled / 1e6:.1f} MB")
    for name in missing[:40]:
        print(f"  {name}  {phone[name].stat().st_size / 1e6:.2f} MB")
    if args.copy_to:
        target = args.copy_to / "measure-partial-pull"
        start = time.perf_counter()
        for name, source in found.items():
            (target / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target / name)
        print(f"copying the reused files: {time.perf_counter() - start:.1f} s")
        shutil.rmtree(target)


if __name__ == "__main__":
    main()
