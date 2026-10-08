"""Restore archived first-control outputs into private scratch for an already-English probe."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import subprocess
import sys
import uuid
from pathlib import Path

PACKAGE = "dev.halixm.hokacepatcher"
BASE = "files/scratch/control-1402-verified"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", type=Path, required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--archive", type=Path, required=True, help="Export directory produced by prepare_android_workflow_space")
    args = parser.parse_args()
    root = args.archive / "first-android"

    def remote(script: str) -> bytes:
        command = [str(args.adb), "-s", args.serial, "exec-out",
                   f"run-as {PACKAGE} /system/bin/sh -c {shlex.quote(script)}"]
        return subprocess.run(command, capture_output=True, check=True, timeout=60).stdout

    expected = json.loads((root / "staged-hashes.json").read_bytes())
    saved_control = json.loads((root / "control.json").read_bytes())
    current = json.loads(remote("cat " + shlex.quote(BASE + "/control.json")))
    current_stage = json.loads(remote("cat " + shlex.quote(BASE + "/staged-hashes.json")))
    if current_stage != expected or current["verified_source_files"] != saved_control["verified_source_files"] or current["apk"] != saved_control["apk"]:
        raise ValueError("Archive and retained device control differ")
    files = {}
    for name, digest in expected.items():
        parts = name.split("/")
        if len(parts) != 2 or not re.fullmatch(r"[0-9]{1,10}", parts[0]) or not re.fullmatch(
                re.escape(parts[0]) + r"(?:_[0-9]{1,3})?\.db", parts[1]) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Invalid archived package identity")
        path = root / "out" / name
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != digest:
                raise ValueError("Local archived stage changed")
        files[name] = (path, digest)
    summary = root / "out/device_patch_summary.json"
    files["device_patch_summary.json"] = (summary, hashlib.sha256(summary.read_bytes()).hexdigest())
    session = "restore-firststage-" + str(uuid.uuid4())
    temporary = "files/scratch/" + session + "/out"
    canonical = "/data/user/0/" + PACKAGE + "/"
    checks = f"[ ! -L {shlex.quote(BASE)} ] && [ \"$(realpath {shlex.quote(BASE)})\" = {shlex.quote(canonical + BASE)} ] && " + \
        f"[ ! -e {shlex.quote(BASE + '/out')} ] && [ ! -L {shlex.quote(BASE + '/out')} ] && " + \
        f"[ ! -e {shlex.quote('files/scratch/' + session)} ] && printf ready"
    if remote(checks) != b"ready":
        raise ValueError("Stage restore requires the compacted control's fresh output path")
    # Reuse the measured token-authenticated loopback receiver. exec-in has no receiver
    # acknowledgment, raw Windows shell stdin truncated at 0x1a, and base64 was too slow.
    command = [sys.executable, str(Path(__file__).with_name("android_harness.py")),
               "--adb", str(args.adb), "--serial", args.serial, "--session", session]
    for name, (path, _) in files.items():
        command.extend(["--file", str(path), "out/" + name])
    subprocess.run(command, check=True, timeout=600)
    # Independent whole-file read-back precedes the final directory publication.
    for name, (_, digest) in files.items():
        if remote("sha256sum " + shlex.quote(temporary + "/" + name)).decode().split()[0] != digest:
            raise ValueError("Restored scratch stage read-back differs; retain receiver session")
    script = f"[ ! -L {shlex.quote(temporary)} ] && [ -d {shlex.quote(temporary)} ] && " + \
        f"[ \"$(realpath {shlex.quote(temporary)})\" = {shlex.quote(canonical + temporary)} ] && " + \
        f"[ ! -e {shlex.quote(BASE + '/out')} ] && [ ! -L {shlex.quote(BASE + '/out')} ] && " + \
        f"mv {shlex.quote(temporary)} {shlex.quote(BASE + '/out')} && sync {shlex.quote(BASE)} && printf restored"
    if remote(script) != b"restored":
        raise ValueError("Restored stage directory was not committed")
    print(f"PASS: restored {len(expected)} archived stage files into app-private control scratch")


if __name__ == "__main__":
    main()
