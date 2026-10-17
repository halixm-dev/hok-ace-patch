"""Restore the user's matched pristine layer, retaining a verified pre-restore backup."""
from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
import sys
import tarfile
import uuid
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[2]
ADB = ROOT / "dist/HOK ACE Patcher Data/adb/adb.exe"
SNAPSHOT = ROOT / "dist/HOK ACE Patcher Data/pristine/20261016-101124"
NORMAL = ROOT / "dist/HOK ACE Patcher Data/installed.apk"
WORK = Path("D:/scratch/hok-staging-performance/phone-pristine-20261017-retry")
SERIAL = "f15a72e"
GAME = "com.tencent.tmgp.osgame"
CACHE = "files/QtsVFSCache"
TOKEN = uuid.uuid4().hex
REMOTE = "/data/local/tmp/hok-pristine-" + TOKEN
OLD_PACKAGES = "packages-before-pristine-" + TOKEN
OLD_WATCHDOG = "Watchdog-before-pristine-" + TOKEN


def adb(*args: str, timeout: int = 300) -> bytes:
    result = subprocess.run([str(ADB), "-s", SERIAL, *args], capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"ADB failed {args[:2]}: {result.stdout.decode(errors='replace')} "
                           f"{result.stderr.decode(errors='replace')}")
    return result.stdout


def private(script: str) -> bytes:
    return adb("exec-out", f"run-as {GAME} /system/bin/sh -c {shlex.quote('cd ' + CACHE + ' && ' + script)}")


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def archive_hashes(path: Path) -> dict[str, str]:
    hashes = {}
    with tarfile.open(path) as archive:
        for member in archive:
            parts = PurePosixPath(member.name).parts
            if not parts or parts[0] not in ("packages", "Watchdog") or ".." in parts:
                raise RuntimeError("Unexpected archive path: " + member.name)
            if member.isdir():
                continue
            if not member.isfile() or member.name in hashes:
                raise RuntimeError("Unexpected or duplicate archive entry: " + member.name)
            with archive.extractfile(member) as stream:
                hashes[member.name] = hashlib.file_digest(stream, "sha256").hexdigest()
    return hashes


def device_hashes() -> dict[str, str]:
    result = private("find packages Watchdog -type f -exec sha256sum '{}' +")
    return {name.strip(): value for value, name in
            (line.split(None, 1) for line in result.decode().splitlines())}


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=False)
    report = {"serial": SERIAL, "snapshot": str(SNAPSHOT), "status": "preflight"}
    moved = False
    verified = False
    try:
        snapshot = json.loads((SNAPSHOT / "snapshot.json").read_text())
        if digest(NORMAL) != snapshot["normal_apk_sha256"]:
            raise RuntimeError("Normal recovery APK differs from pristine snapshot")
        info = json.loads(private("cat packages/1/1.info"))
        if info != snapshot["package_1_info"]:
            raise RuntimeError(f"Data version differs: {info}")
        report["data_version"] = info
        incoming = archive_hashes(SNAPSHOT / "device-backup.tar")
        if {k: incoming.get(k) for k in snapshot["device_sha256"]} != snapshot["device_sha256"]:
            raise RuntimeError("Pristine archive differs from saved device hashes")
        print(f"Pristine archive verified: {len(incoming)} files", flush=True)

        before = device_hashes()
        report["before_hashes"] = before
        backup = WORK / "before-pristine.tar"
        adb("shell", "mkdir", REMOTE)
        adb("shell", "chmod", "755", REMOTE)
        # Write on the phone, then use ADB's file-transfer protocol instead of a shell stdout stream.
        adb("shell", "touch", REMOTE + "/before-pristine.tar")
        adb("shell", "chmod", "666", REMOTE + "/before-pristine.tar")
        print("Creating recovery archive on phone", flush=True)
        private(f"tar -cf {REMOTE}/before-pristine.tar packages Watchdog")
        print("Pulling recovery archive with ADB file transfer", flush=True)
        adb("pull", REMOTE + "/before-pristine.tar", str(backup), timeout=900)
        if archive_hashes(backup) != before:
            raise RuntimeError("Pre-restore backup failed verification")
        report["backup"] = str(backup)
        report["backup_sha256"] = digest(backup)
        print(f"Current layer backed up and verified: {len(before)} files", flush=True)
        adb("shell", "rm", REMOTE + "/before-pristine.tar")

        print("Transferring pristine archive to phone", flush=True)
        adb("push", str(SNAPSHOT / "device-backup.tar"), REMOTE + "/pristine.tar", timeout=900)
        adb("shell", "chmod", "644", REMOTE + "/pristine.tar")
        remote_sha = adb("shell", "sha256sum", REMOTE + "/pristine.tar").decode().split()[0]
        if remote_sha != digest(SNAPSHOT / "device-backup.tar"):
            raise RuntimeError("Pristine archive transfer hash differs")
        # The game is stopped, and its marker must still match immediately before mutation.
        adb("shell", "am", "force-stop", GAME)
        if json.loads(private("cat packages/1/1.info")) != info:
            raise RuntimeError("Data version changed before restore")
        moved = True
        private(f"set -e; test ! -e {OLD_PACKAGES}; test ! -e {OLD_WATCHDOG}; "
                f"mv packages {OLD_PACKAGES}; mv Watchdog {OLD_WATCHDOG}; "
                f"tar -xf {REMOTE}/pristine.tar; sync")
        restored = device_hashes()
        if restored != incoming:
            raise RuntimeError("Restored file inventory or hash differs from pristine archive")
        report["restored_hashes"] = restored
        report["verified_files"] = len(restored)
        verified = True
        # Both backup paths are UUID-named children of the fixed private cache; a verified PC tar survives.
        private(f"rm -rf {OLD_PACKAGES} {OLD_WATCHDOG}")
        print(f"Pristine layer restored and verified: {len(restored)} files", flush=True)
        report["status"] = "pristine-verified"
    except BaseException:
        if moved and not verified:
            private(f"if [ -d {OLD_PACKAGES} ]; then rm -rf packages; mv {OLD_PACKAGES} packages; fi; "
                    f"if [ -d {OLD_WATCHDOG} ]; then rm -rf Watchdog; mv {OLD_WATCHDOG} Watchdog; fi; sync")
            report["status"] = "rolled-back"
        raise
    finally:
        # Never leave the access APK installed, including on version/backup/transfer failure.
        print("Restoring verified normal game APK", flush=True)
        for attempt in range(3):
            try:
                output = adb("install", "-r", str(NORMAL))
                if b"Success" not in output:
                    raise RuntimeError(output.decode(errors="replace"))
                report["normal_apk_restored"] = True
                break
            except Exception:
                if attempt == 2:
                    report["normal_apk_restored"] = False
                    (WORK / "restore-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
                    raise
        flags = adb("shell", "dumpsys", "package", GAME).decode()
        if "DEBUGGABLE" in flags:
            raise RuntimeError("Normal game still reports DEBUGGABLE")
        if verified:
            # TEMP path is uniquely created by this invocation and is outside app data.
            adb("shell", "rm", "-rf", REMOTE)
        (WORK / "restore-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("Normal APK restored; pristine restore status: " + report["status"], flush=True)


if __name__ == "__main__":
    main()
