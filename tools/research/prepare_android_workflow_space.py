"""Archive verified private scratch outputs and compact duplicates before full workflow tests."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import uuid
from pathlib import Path

PACKAGE = "dev.halixm.hokacepatcher"
BASE = "files/scratch/control-1402-verified"
MAX_FILE = 3 * 1024**3


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", type=Path, required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--rerun-session", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    suffix = args.rerun_session.removeprefix("rerun-english-")
    if args.rerun_session != "rerun-english-" + str(uuid.UUID(suffix)):
        parser.error("A canonical rerun probe session is required")
    rerun = "files/scratch/" + args.rerun_session
    args.output.mkdir(parents=True, exist_ok=True)

    def command(script: str, *, timeout: int = 60) -> bytes:
        return subprocess.run([str(args.adb), "-s", args.serial, "exec-out",
                               f"run-as {PACKAGE} /system/bin/sh -c {shlex.quote(script)}"],
                              check=True, capture_output=True, timeout=timeout).stdout

    def read(path: str) -> bytes:
        payload = command("cat " + shlex.quote(path))
        if len(payload) > 8 * 1024 * 1024:
            raise ValueError("Oversized evidence file")
        return payload

    def save(name: str, value: bytes) -> None:
        path = args.output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        if path.read_bytes() != value:
            raise ValueError("Local evidence read-back differs")

    def hashes(paths: dict[str, str]) -> None:
        items = list(paths.items())
        for start in range(0, len(items), 64):
            batch = items[start:start + 64]
            result = command("sha256sum " + " ".join(shlex.quote(name) for name, _ in batch), timeout=120)
            actual = {}
            for line in result.decode().splitlines():
                digest, name = line.split(None, 1)
                actual[name.strip()] = digest
            if actual != dict(batch):
                raise ValueError("Retained scratch file hash differs")

    def export_file(relative: str, name: str, expected: str) -> None:
        path = args.output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(path.suffix + ".partial")
        process = subprocess.Popen([str(args.adb), "-s", args.serial, "exec-out", "run-as",
                                    PACKAGE, "cat", relative], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        digest = hashlib.sha256()
        length = 0
        try:
            with partial.open("wb") as stream:
                while block := process.stdout.read(1024 * 1024):
                    length += len(block)
                    if length > MAX_FILE:
                        raise ValueError("Oversized stage file")
                    digest.update(block)
                    stream.write(block)
                stream.flush()
                os.fsync(stream.fileno())
            if process.wait(30) or digest.hexdigest() != expected:
                raise ValueError("Stage export transport/hash differs")
            with partial.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                    raise ValueError("Local stage read-back differs")
            partial.replace(path)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            process.stdout.close()
            process.stderr.close()
            partial.unlink(missing_ok=True)

    controls = {}
    stages = {}
    for label, root in (("first-android", BASE), ("rerun", rerun)):
        for name in ("control.json", "staged-hashes.json", "metrics.json", "build.log",
                     "out/device_patch_summary.json"):
            value = read(root + "/" + name)
            save(label + "/" + name, value)
            if name == "control.json":
                controls[label] = json.loads(value)
            if name == "staged-hashes.json":
                stages[label] = json.loads(value)
        for name, expected in stages[label].items():
            parts = name.split("/")
            if len(parts) != 2 or not re.fullmatch(r"[0-9]{1,10}", parts[0]) or not re.fullmatch(
                    re.escape(parts[0]) + r"(?:_[0-9]{1,3})?\.db", parts[1]):
                raise ValueError("Unexpected staged package path")
            if not re.fullmatch(r"[0-9a-f]{64}", expected):
                raise ValueError("Invalid staged digest")
            export_file(root + "/out/" + name, label + "/out/" + name, expected)
    print("Stage outputs and evidence exported with full hash read-back", flush=True)
    originals = controls["first-android"]["verified_source_files"]
    rerun_inputs = controls["rerun"]["verified_source_files"]
    expected_inputs = dict(originals)
    expected_inputs.update(stages["first-android"])
    if rerun_inputs != expected_inputs or any(rerun_inputs.get(name) != digest for name, digest in stages["rerun"].items()):
        raise ValueError("Rerun is not the verified already-English composite")
    # These names have the same fixed policy the development input manifest used. Refuse any
    # path which might escape the verified source trees before generating shell arguments.
    for name, digest in expected_inputs.items():
        if name.startswith("/") or ".." in name.split("/") or "\\" in name or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Invalid retained source identity")
    hashes({BASE + "/game/WXQ_Data/Package/builtin/" + name: digest for name, digest in originals.items()})
    hashes({rerun + "/game/WXQ_Data/Package/builtin/" + name: digest for name, digest in rerun_inputs.items()})
    normal_hash = controls["first-android"]["apk"]["sha256"]
    if not re.fullmatch(r"[0-9a-f]{64}", normal_hash):
        raise ValueError("Invalid normal APK identity")
    protected = "files/recovery/" + normal_hash + "/normal.apk"
    identity = json.loads(read("files/recovery/" + normal_hash + "/identity.json"))
    save("protected-normal-identity.json", json.dumps(identity, indent=2).encode())
    if identity["sha256"] != normal_hash or identity["debuggable"]:
        raise ValueError("Protected normal APK identity differs")
    hashes({protected: normal_hash, BASE + "/normal.apk": normal_hash,
            BASE + "/java-game-signed.apk": normal_hash})
    print("All pristine/rerun sources and duplicate/protected APKs rehashed", flush=True)

    canonical = "/data/user/0/" + PACKAGE + "/"
    removals = [BASE + "/work", BASE + "/out", rerun + "/game", rerun + "/work", rerun + "/out"]
    guards = []
    for relative in [BASE, rerun, *removals]:
        guards.append(f"[ ! -L {shlex.quote(relative)} ] && [ -d {shlex.quote(relative)} ] && "
                      f"[ \"$(realpath {shlex.quote(relative)})\" = {shlex.quote(canonical + relative)} ] || exit 1")
    for relative in [protected, BASE + "/normal.apk", BASE + "/java-game-signed.apk"]:
        guards.append(f"[ ! -L {shlex.quote(relative)} ] && [ -f {shlex.quote(relative)} ] && "
                      f"[ \"$(realpath {shlex.quote(relative)})\" = {shlex.quote(canonical + relative)} ] || exit 1")
    pending, redundant = BASE + "/normal.apk.protected-link", BASE + "/normal.apk.redundant"
    guards.append(f"[ ! -e {shlex.quote(pending)} ] && [ ! -L {shlex.quote(pending)} ] && "
                  f"[ ! -e {shlex.quote(redundant)} ] && [ ! -L {shlex.quote(redundant)} ] || exit 1")
    # Change only the duplicate pathname. The protected cache and approved pristine tree survive.
    mutation = f"ln -s {shlex.quote(canonical + protected)} {shlex.quote(pending)} && " + \
        f"mv {shlex.quote(BASE + '/normal.apk')} {shlex.quote(redundant)} && " + \
        f"mv {shlex.quote(pending)} {shlex.quote(BASE + '/normal.apk')} && sync {shlex.quote(BASE)} && " + \
        f"[ \"$(sha256sum {shlex.quote(BASE + '/normal.apk')} | cut -d ' ' -f 1)\" = {shlex.quote(normal_hash)} ] && " + \
        "rm -rf " + " ".join(shlex.quote(path) for path in removals) + " && " + \
        f"rm {shlex.quote(redundant)} {shlex.quote(BASE + '/java-game-signed.apk')} && " + \
        f"sync {shlex.quote(BASE)} && sync {shlex.quote(rerun)} && printf compacted"
    if command("; ".join(guards) + "; " + mutation, timeout=120) != b"compacted":
        raise ValueError("Compaction acknowledgment differs; inspect retained paths")
    save("compaction.json", json.dumps({"schema": 1, "removed": removals + [redundant, BASE + "/java-game-signed.apk"],
         "normal_apk_link": canonical + protected, "pristine_sources_verified": len(originals),
         "rerun_sources_verified": len(rerun_inputs), "all_stage_files_exported": True}, indent=2).encode())
    print("PASS: only verified duplicates/build files compacted; pristine and protected recovery retained", flush=True)


if __name__ == "__main__":
    main()
