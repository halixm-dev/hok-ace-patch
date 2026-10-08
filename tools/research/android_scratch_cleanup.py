"""Export a successful performance probe's evidence before pruning only its disposable build files."""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import uuid
from pathlib import Path

PACKAGE = "dev.halixm.hokacepatcher"
EVIDENCE = ("resource-metrics.json", "metrics.json", "control.json", "staged-hashes.json",
            "build.log", "out/device_patch_summary.json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", type=Path, required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    identity = args.session.removeprefix("performance-")
    if args.session != "performance-" + str(uuid.UUID(identity)):
        parser.error("Only a canonical performance probe session may be pruned")
    root = "files/scratch/" + args.session

    def read(relative: str) -> bytes:
        result = subprocess.run([str(args.adb), "-s", args.serial, "exec-out", "run-as", PACKAGE,
                                 "cat", relative], check=True, capture_output=True, timeout=30)
        if len(result.stdout) > 8 * 1024 * 1024:
            raise ValueError("Oversized performance evidence")
        return result.stdout

    payloads = {name: read(root + "/" + name) for name in EVIDENCE}
    if json.loads(payloads["resource-metrics.json"])["status"] != "complete":
        raise ValueError("Do not prune an unsuccessful performance probe")
    expected = json.loads(read("files/scratch/control-1402-verified/staged-hashes.json"))
    if json.loads(payloads["staged-hashes.json"]) != expected:
        raise ValueError("Retain outputs: measured build differs from the first Android control")
    args.output.mkdir(parents=True, exist_ok=True)
    for name, payload in payloads.items():
        target = args.output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        if target.read_bytes() != payload:
            raise ValueError("Local evidence read-back differs")
    # Resolve all targets before either deletion. rm removes links inside those disposable
    # directories without following them; input links, recovery caches and journals remain.
    canonical = "/data/user/0/" + PACKAGE + "/" + root
    script = f"base=$(realpath {shlex.quote(root)}) || exit 1; " + \
        f"[ \"$base\" = {shlex.quote(canonical)} ] || exit 1; " + \
        "for name in work out; do path=\"$base/$name\"; " + \
        "[ ! -L \"$path\" ] && [ -d \"$path\" ] && " + \
        "[ \"$(realpath \"$path\")\" = \"$path\" ] || exit 1; done; " + \
        "rm -rf \"$base/work\" \"$base/out\" && sync \"$base\" && printf generated-build-removed"
    result = subprocess.run([str(args.adb), "-s", args.serial, "exec-out",
                             f"run-as {PACKAGE} /system/bin/sh -c {shlex.quote(script)}"],
                            check=True, capture_output=True, timeout=60)
    if result.stdout != b"generated-build-removed":
        raise ValueError("Scratch pruning was not acknowledged")
    (args.output / "cleanup.json").write_text(json.dumps({
        "session": args.session, "staged_hashes_match_first_android_control": True,
        "removed": [canonical + "/work", canonical + "/out"],
        "inputs_and_recovery_retained": True,
    }, indent=2), encoding="utf-8")
    print("PASS: evidence exported, hashes match; only generated performance work/out removed")


if __name__ == "__main__":
    main()
