"""Kill only the feasibility app at a saved fixture commit boundary, then verify byte rollback."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
import uuid

APP = "dev.halixm.hokacepatcher"
FIXTURE = "io.github.hokace.fixture"
RUNNER = APP + ".test/androidx.test.runner.AndroidJUnitRunner"
TEST = APP + ".ProcessDeathFixtureProbeTest"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", type=Path, required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--recover-case", help="Recover a previously armed UUID instead of starting another case")
    args = parser.parse_args()
    case = str(uuid.UUID(args.recover_case)) if args.recover_case else str(uuid.uuid4())
    args.output.mkdir(parents=True, exist_ok=False)
    prefix = [str(args.adb), "-s", args.serial]
    root = f"files/process-death-fixture-probes/{case}"
    report: dict = {"schema": 1, "case": case, "serial": args.serial, "passed": False,
                    "scope": "actual app process death and fixed disposable fixture file rollback; no APK install"}

    def adb(*arguments: str, timeout: float = 30) -> bytes:
        result = subprocess.run([*prefix, *arguments], capture_output=True, timeout=timeout, check=True)
        return result.stdout

    def receipt(name: str) -> dict:
        return json.loads(adb("exec-out", "run-as", APP, "cat", f"{root}/{name}.json"))

    def fixture_hash() -> str:
        paths = adb("shell", "pm", "path", "--user", "0", FIXTURE).decode().strip().splitlines()
        if len(paths) != 1 or not paths[0].startswith("package:/data/app/") or not paths[0].endswith("/base.apk"):
            raise RuntimeError("Fixture is missing or split; no process-death test started")
        blob = adb("exec-out", "cat", paths[0][len("package:"):])
        if not blob.startswith(b"PK") or not 1000 <= len(blob) <= 1024 * 1024:
            raise RuntimeError("Invalid fixture APK read-back")
        return hashlib.sha256(blob).hexdigest()

    def require_idle_app() -> None:
        services = adb("shell", "dumpsys", "activity", "services", APP).decode(errors="replace")
        if f"{APP}/.PatchWorkerService" in services or f"{APP}/{APP}.PatchWorkerService" in services:
            raise RuntimeError("Foreground patch/recovery service is active; stop safely before this fixture diagnostic")
        for folder, terminal in (("sessions", {"COMPLETE", "CANCELLED"}), ("first-setups", {"READY", "CANCELLED"})):
            names = adb("exec-out", "run-as", APP, "sh", "-c",
                        f"[ ! -d files/{folder} ] || ls -1 files/{folder}").decode().splitlines()
            for name in names:
                if name == "coordinator.lock":
                    continue
                if name.startswith(".creating-"):
                    uuid.UUID(name[len(".creating-"):])
                    continue
                if str(uuid.UUID(name)) != name:
                    raise RuntimeError("Unrecognized session entry")
                journal = json.loads(adb("exec-out", "run-as", APP, "cat", f"files/{folder}/{name}/journal.json"))
                if journal["phase"] not in terminal:
                    raise RuntimeError(f"Unfinished {folder} must be recovered before killing the feasibility app")
                if folder == "sessions" and (not journal["normal_verified"] or journal["packages_dirty"]
                                             or journal["mutation_intent"] is not None):
                    raise RuntimeError("Terminal patch journal still has unresolved recovery state")
        for suffix in ("", ".bak"):
            emergency = adb("exec-out", "run-as", APP, "sh", "-c",
                            f"[ ! -f files/emergency-restore.json{suffix} ] || cat files/emergency-restore.json{suffix}").strip()
            if emergency:
                value = json.loads(emergency)
                if value["schema"] != 1 or value["status"] not in {"verification_pending", "apk_verified"}:
                    raise RuntimeError("Unrecognized emergency recovery record")
                if value["status"] == "verification_pending":
                    raise RuntimeError("Emergency APK verification is pending; finish it before the fixture diagnostic")
        report["idle_app_preflight_passed"] = True

    def command(phase: str) -> list[str]:
        return [*prefix, "shell", "am", "instrument", "-w", "-r", "-e", "class", TEST,
                "-e", "probePhase", phase, "-e", "probeCase", case, RUNNER]

    process: subprocess.Popen | None = None
    started = time.monotonic()
    try:
        require_idle_app()
        report["fixture_apk_before"] = fixture_hash()
        if args.recover_case:
            armed = receipt("armed")
        else:
            with (args.output / "arm.log").open("wb") as log:
                process = subprocess.Popen(command("arm"), stdout=log, stderr=subprocess.STDOUT)
                deadline = time.monotonic() + 90
                armed = None
                while time.monotonic() < deadline:
                    try:
                        armed = receipt("armed")
                        break
                    except (json.JSONDecodeError, subprocess.CalledProcessError):
                        if process.poll() is not None:
                            raise RuntimeError("Arm instrumentation ended before its durable commit receipt; inspect arm.log")
                    time.sleep(0.5)
                if armed is None:
                    raise RuntimeError("No durable arm receipt within 90 seconds")
                if armed.get("case") != case or armed.get("boundary") != "index-renamed-before-acknowledgement":
                    raise RuntimeError("Unexpected arm boundary")
                pids = adb("shell", "pidof", APP).decode().strip().split()
                if str(armed["pid"]) not in pids:
                    raise RuntimeError("Armed app PID is no longer live; no additional kill issued")
                report["observed_live_pid"] = armed["pid"]
                report["force_stop_output"] = adb("shell", "am", "force-stop", APP).decode()
                process.wait(timeout=20)
                remaining = subprocess.run([*prefix, "shell", "pidof", APP], capture_output=True, timeout=15)
                if remaining.stdout.strip():
                    raise RuntimeError("App process remains after force-stop")
                report["observed_app_absent_after_kill"] = True
                report["arm_adb_exit"] = process.returncode
                process = None
        report["armed"] = armed
        (args.output / "armed.json").write_text(json.dumps(armed, indent=2) + "\n", encoding="utf-8")
        with (args.output / "recover.log").open("wb") as log:
            recovered = subprocess.run(command("recover"), stdout=log, stderr=subprocess.STDOUT, timeout=120)
        output = (args.output / "recover.log").read_text(encoding="utf-8", errors="replace")
        if recovered.returncode != 0 or "OK (1 test)" not in output or "FAILURES!!!" in output:
            raise RuntimeError("Recovery instrumentation did not pass; retained fixture ownership and snapshot permit recovery retry")
        restored = receipt("recovered")
        journal = restored["journal"]
        if (restored["case"] != case or restored["pid"] == armed["pid"] or restored["verified_files"] != 5
                or restored["apk_install_tested"] or journal["packages_dirty"]
                or journal["mutation_intent"] is not None or journal["normal_verified"]
                or journal["phase"] != "RESTORING"):
            raise RuntimeError("Recovered receipt does not prove the required file-only rollback")
        report["recovered"] = restored
        (args.output / "recovered.json").write_text(json.dumps(restored, indent=2) + "\n", encoding="utf-8")
        report["fixture_apk_after"] = fixture_hash()
        if report["fixture_apk_after"] != report["fixture_apk_before"]:
            raise RuntimeError("Fixture APK changed")
        cleaned = adb("shell", "run-as", FIXTURE, "sh", "-c",
                      "'[ ! -e files/QtsVFSCache ] && [ ! -e files/hokace-process-probe-owner ] && printf fixture-clean'")
        if cleaned.strip() != b"fixture-clean":
            raise RuntimeError("Fixture cleanup not independently confirmed")
        report["fixture_cleanup_verified"] = True
        report["passed"] = True
    except Exception as error:
        report["error"] = str(error)
        report["retry"] = f"Use --recover-case {case} with a fresh output directory if armed.json exists"
        raise
    finally:
        if process is not None and process.poll() is None:
            # Stop only the feasibility app; leave fixture/snapshot material for explicit recovery.
            subprocess.run([*prefix, "shell", "am", "force-stop", APP], capture_output=True, timeout=15)
            process.wait(timeout=20)
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({key: report[key] for key in ("case", "passed", "elapsed_seconds")}))


if __name__ == "__main__":
    main()
