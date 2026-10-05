"""Record Android ABI/page size and run development-only codec loading checks without game access."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

APP = "dev.halixm.hokacepatcher"
TEST_APP = APP + ".test"
CLASSES = APP + ".EngineProbeTest," + APP + ".NativeDependencyProbeTest"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", type=Path, required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--install", action="store_true", help="Install/update only the built development app/test APKs")
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12):
        parser.error("Use Python 3.12")
    args.output.mkdir(parents=True, exist_ok=False)
    repo = Path(__file__).resolve().parents[2]
    prefix = [str(args.adb), "-s", args.serial]
    report: dict = {"schema": 1, "serial": args.serial, "passed": False,
                    "scope": "development app native loading and codec operations; no game access or Shizuku changes"}
    started = time.monotonic()

    def command(arguments: list[str], *, timeout: float = 30, log: str | None = None) -> str:
        result = subprocess.run(arguments, capture_output=True, timeout=timeout)
        output = result.stdout.decode("utf-8", errors="replace") + result.stderr.decode("utf-8", errors="replace")
        if log:
            (args.output / log).write_text(output, encoding="utf-8")
        if result.returncode != 0:
            raise RuntimeError(f"Command failed ({result.returncode}); inspect {log or 'device diagnostics'}")
        return output

    def adb(*arguments: str, **kwargs) -> str:
        return command([*prefix, *arguments], **kwargs)

    try:
        report["stage"] = "device inspection"
        if adb("get-state").strip() != "device":
            raise RuntimeError("Authorize USB debugging before running this probe")
        properties = {}
        for key in ("ro.product.manufacturer", "ro.product.model", "ro.build.version.release",
                    "ro.build.version.sdk", "ro.product.cpu.abilist", "ro.kernel.qemu", "ro.boot.qemu"):
            properties[key] = adb("shell", "getprop", key).strip()
        report["properties"] = properties
        page_size = int(adb("shell", "getconf", "PAGE_SIZE").strip())
        report["page_size"] = page_size
        if int(properties["ro.build.version.sdk"]) < 30 or "arm64-v8a" not in properties["ro.product.cpu.abilist"].split(","):
            raise RuntimeError("This build requires Android 11+ and arm64-v8a")
        if page_size not in (4096, 16384):
            raise RuntimeError("Unmeasured native page size")
        report["reported_emulator"] = any(properties[key] == "1" for key in ("ro.kernel.qemu", "ro.boot.qemu"))
        report["stage"] = "built APK inspection"
        apks = [(APP, repo / "android/app/build/outputs/apk/debug/app-debug.apk"),
                (TEST_APP, repo / "android/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk")]
        aapt = args.adb.resolve().parent.parent / "build-tools/35.0.0/aapt2.exe"
        report["apks"] = []
        for package, path in apks:
            badging = command([str(aapt), "dump", "badging", str(path)])
            match = re.search(r"^package: name='([^']+)'", badging, re.MULTILINE)
            if not match or match.group(1) != package:
                raise RuntimeError("Built APK has an unexpected package; refuse installation")
            with path.open("rb") as source:
                digest = hashlib.file_digest(source, "sha256").hexdigest()
            report["apks"].append({"package": package, "bytes": path.stat().st_size, "sha256": digest})
        command([sys.executable, str(repo / "tools/research/check_android_native.py"), str(apks[0][1]),
                 "--report", str(args.output / "native-inventory.json")], timeout=60, log="native-inspection.log")
        if args.install:
            report["stage"] = "development APK installation"
            for index, (_, path) in enumerate(apks):
                output = adb("install", "-r", str(path), timeout=180, log=f"install-{index}.log")
                if not re.search(r"^Success\s*$", output, re.MULTILINE):
                    raise RuntimeError("Development APK installation did not acknowledge success")
        report["stage"] = "installed development APK identity"
        report["installed_apks"] = []
        for expected in report["apks"]:
            paths = adb("shell", "pm", "path", "--user", "0", expected["package"]).strip().splitlines()
            if len(paths) != 1:
                raise RuntimeError("Development app is missing or split")
            match = re.fullmatch(r"package:(/data/app/[A-Za-z0-9._/~+=-]+/base\.apk)", paths[0])
            if not match:
                raise RuntimeError("Unexpected installed development APK path")
            path = match.group(1)
            digest = adb("shell", "sha256sum", path, timeout=60).split()[0]
            length = int(adb("shell", "stat", "-c", "%s", path).strip())
            if digest != expected["sha256"] or length != expected["bytes"]:
                raise RuntimeError("Installed development APK differs from the inspected build")
            report["installed_apks"].append({"package": expected["package"], "bytes": length, "sha256": digest})
        report["stage"] = "codec instrumentation"
        output = adb("shell", "am", "instrument", "-w", "-r", "-e", "class", CLASSES,
                     "-e", "requireFullCodecs", "true", TEST_APP + "/androidx.test.runner.AndroidJUnitRunner",
                     timeout=240, log="codec-probes.log")
        if not re.search(r"^OK \(2 tests\)\s*$", output, re.MULTILINE) or "FAILURES!!!" in output:
            raise RuntimeError("Both codec tests must pass; an ADB exit code is not sufficient")
        report["passed"] = True
        report["stage"] = "complete"
        report["game_mutated"] = False
        report["device_16k_loading_observed"] = page_size == 16384
        report["limits"] = "Required codec imports/frame/font operations only; physical-device identity must be confirmed separately. No full game build, watched rendering, FGS timeout or patch acceptance"
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
