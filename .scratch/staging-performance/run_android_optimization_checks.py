"""Update the development patcher and run app-private optimization probes.

Requires explicit device and APK paths. Refuses dirty/pending retained sessions.
Never installs the game, restores a data layer, or invokes a patch coordinator.
Keeps before/after journal hashes and the normal APK identity in --work.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

PATCHER = "dev.halixm.hokacepatcher"
GAME = "com.tencent.tmgp.osgame"
CLASSES = ",".join(f"{PATCHER}.{name}" for name in
                   ("EngineProbeTest", "NativeDependencyProbeTest", "PackageIoProbeTest"))


def file_hash(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", type=Path, required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--previous-apk", type=Path, required=True)
    parser.add_argument("--test-apk", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--skip-patcher-install", action="store_true",
                        help="retry only test APK/probes after the verified patcher is already installed")
    args = parser.parse_args()
    if args.work.exists():
        parser.error("--work must be new")
    args.work.mkdir(parents=True)
    prefix = [str(args.adb), "-s", args.serial]

    def adb(*arguments: str, timeout: int = 60) -> bytes:
        result = subprocess.run([*prefix, *arguments], capture_output=True, timeout=timeout)
        if result.returncode:
            raise RuntimeError(result.stderr.decode(errors="replace") + result.stdout.decode(errors="replace"))
        return result.stdout

    def installed_hash(package: str) -> str:
        path = adb("shell", "pm", "path", "--user", "0", package).decode().strip()
        assert re.fullmatch(r"package:/data/app/[A-Za-z0-9_./~=+-]+/base\.apk", path), path
        return adb("shell", "sha256sum", path.removeprefix("package:")).decode().split()[0]

    def journals() -> dict:
        paths = adb("shell", "run-as", PATCHER, "find", "files/sessions", "-name", "journal.json")
        result = {}
        for path in paths.decode().splitlines():
            assert re.fullmatch(r"files/sessions/[a-zA-Z0-9-]+/journal\.json", path), path
            raw = adb("exec-out", "run-as", PATCHER, "cat", path)
            value = json.loads(raw)
            assert value["phase"] in ("COMPLETE", "CANCELLED"), value["phase"]
            assert value["normal_verified"] and not value["packages_dirty"]
            assert value.get("mutation_intent") is None and value.get("recovery_normal_intent") is None
            result[path] = {"sha256": hashlib.sha256(raw).hexdigest(), "phase": value["phase"],
                            "normal_verified": True, "packages_dirty": False}
        return result

    before = {"patcher_sha256": installed_hash(PATCHER), "normal_apk_sha256": installed_hash(GAME),
              "journals": journals()}
    expected_before = args.apk if args.skip_patcher_install else args.previous_apk
    assert before["patcher_sha256"] == file_hash(expected_before), "installed patcher differs from expected backup/build"
    (args.work / "before.json").write_text(json.dumps(before, indent=2), encoding="utf-8")
    installs = [("instrumentation", args.test_apk)]
    if not args.skip_patcher_install:
        installs.insert(0, ("patcher", args.apk))
    for label, apk in installs:
        print(f"Installing verified {label} APK in place", flush=True)
        output = adb("install", "-r", str(apk.resolve()), timeout=180)
        (args.work / f"install-{label}.log").write_bytes(output)
        assert b"Success" in output, output
    print("Running four app-private Android checks", flush=True)
    output = adb("shell", "am", "instrument", "-w", "-r", "-e", "requireFullCodecs", "true",
                 "-e", "class", CLASSES, f"{PATCHER}.test/androidx.test.runner.AndroidJUnitRunner", timeout=300)
    (args.work / "instrumentation.log").write_bytes(output)
    print(output.decode(errors="replace"), flush=True)
    after = {"patcher_sha256": installed_hash(PATCHER), "normal_apk_sha256": installed_hash(GAME),
             "journals": journals()}
    (args.work / "after.json").write_text(json.dumps(after, indent=2), encoding="utf-8")
    assert after["patcher_sha256"] == file_hash(args.apk), "installed patcher differs"
    assert after["normal_apk_sha256"] == before["normal_apk_sha256"], "normal game APK changed"
    assert after["journals"] == before["journals"], "retained session changed"
    assert b"OK (4 tests)" in output and b"FAILURES!!!" not in output, "Android tests failed"
    report = {"status": "passed", "android_tests": 4, "installed_patcher_sha256": after["patcher_sha256"],
              "normal_apk_sha256": after["normal_apk_sha256"], "normal_apk_unchanged": True,
              "retained_journals_unchanged": True, "game_data_commands_executed": False,
              "scope": "Tiny app-private fixtures and native checks; no full staging or device cycle."}
    (args.work / "receipt.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
