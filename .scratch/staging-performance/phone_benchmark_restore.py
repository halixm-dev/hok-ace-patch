"""Back up the live layer, verify a matching pristine restore, and restore the normal APK.

Explicit APK/snapshot/device/new-work arguments are required. Never clears game data.
Keeps a verified PC recovery archive. The normal APK is restored in finally, including
version/backup failures after access installation. --restore is required for layer writes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import uuid
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.append(str(ROOT / "resources/runtime"))
GAME = "com.tencent.tmgp.osgame"
PATCHER = "dev.halixm.hokacepatcher"
CACHE = "files/QtsVFSCache"


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def archive_hashes(path: Path) -> dict[str, str]:
    hashes = {}
    with tarfile.open(path) as archive:
        for member in archive:
            parts = PurePosixPath(member.name).parts
            if not parts or parts[0] not in ("packages", "Watchdog") or ".." in parts or member.name.startswith("/"):
                raise RuntimeError("Unexpected archive path: " + member.name)
            if member.isdir():
                continue
            if not member.isfile() or member.name in hashes:
                raise RuntimeError("Non-regular or duplicate archive member: " + member.name)
            with archive.extractfile(member) as handle:
                hashes[member.name] = hashlib.file_digest(handle, "sha256").hexdigest()
    return hashes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("adb", "snapshot", "normal", "access", "work"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--expected-patcher-sha256", required=True)
    parser.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    work = args.work.resolve()
    if work.exists() or work.is_relative_to(ROOT):
        parser.error("--work must be a new external directory")
    work.mkdir(parents=True)
    prefix = [str(args.adb), "-s", args.serial]
    report = {"status": "preflight", "snapshot": str(args.snapshot.resolve())}
    receipt = work / "restore-report.json"

    def save() -> None:
        receipt.write_text(json.dumps(report, indent=2), encoding="utf-8")

    def adb(*arguments: str, timeout: int = 300) -> bytes:
        result = subprocess.run([*prefix, *arguments], capture_output=True, timeout=timeout)
        if result.returncode:
            raise RuntimeError(result.stdout.decode(errors="replace") + result.stderr.decode(errors="replace"))
        return result.stdout

    def private(script: str) -> bytes:
        command = f"run-as {GAME} /system/bin/sh -c " + shlex.quote("cd " + CACHE + " && " + script)
        return adb("exec-out", command)

    def installed_hash(package: str) -> str:
        path = adb("shell", "pm", "path", "--user", "0", package).decode().strip()
        if not re.fullmatch(r"package:/data/app/[A-Za-z0-9_./~=+-]+/base\.apk", path):
            raise RuntimeError("Unexpected APK path")
        return adb("shell", "sha256sum", path.removeprefix("package:")).decode().split()[0]

    def device_hashes() -> dict[str, str]:
        lines = private("find packages Watchdog -type f -exec sha256sum '{}' +").decode().splitlines()
        return {name.strip(): value for value, name in (line.split(None, 1) for line in lines)}

    print("Verifying cached recovery APKs and pristine archive", flush=True)
    from apk_tools import signed_with
    from axml_set_debuggable import is_debuggable
    import zipfile

    snapshot = json.loads((args.snapshot / "snapshot.json").read_text())
    normal_sha = digest(args.normal)
    assert normal_sha == snapshot["normal_apk_sha256"]
    cert = (ROOT / "resources/key/cert.der").read_bytes()
    for path, debug in ((args.normal, False), (args.access, True)):
        assert signed_with(path, cert), "APK signer differs"
        with zipfile.ZipFile(path) as archive:
            assert is_debuggable(archive.read("AndroidManifest.xml")) == debug
    assert installed_hash(GAME) == normal_sha, "Installed game differs from verified recovery APK"
    assert installed_hash(PATCHER) == args.expected_patcher_sha256, "Wrong patcher engine installed"
    paths = adb("shell", "run-as", PATCHER, "find", "files/sessions", "-name", "journal.json").decode().splitlines()
    for path in paths:
        assert re.fullmatch(r"files/sessions/[a-zA-Z0-9-]+/journal\.json", path)
        journal = json.loads(adb("exec-out", "run-as", PATCHER, "cat", path))
        assert journal["phase"] in ("COMPLETE", "CANCELLED") and journal["normal_verified"]
        assert not journal["packages_dirty"] and journal.get("mutation_intent") is None
    incoming = archive_hashes(args.snapshot / "device-backup.tar")
    assert {name: incoming.get(name) for name in snapshot["device_sha256"]} == snapshot["device_sha256"]
    if shutil.disk_usage(work).free < 3 * 1024**3:
        raise RuntimeError("Less than 3 GiB PC space for a fresh verified recovery backup")
    report.update(normal_apk_sha256=normal_sha, pristine_archive_sha256=digest(args.snapshot / "device-backup.tar"),
                  incoming_files=len(incoming))
    save()
    token = uuid.uuid4().hex
    remote = "/data/local/tmp/hok-benchmark-" + token
    old_packages = "packages-before-benchmark-" + token
    old_watchdog = "Watchdog-before-benchmark-" + token
    access_attempted = False
    moved = verified = False
    before = {}
    try:
        adb("shell", "am", "force-stop", GAME)
        print("Installing temporary access APK; approve the phone prompt", flush=True)
        access_attempted = True
        assert b"Success" in adb("install", "-r", str(args.access.resolve()), timeout=360)
        info = json.loads(private("cat packages/1/1.info"))
        assert info == snapshot["package_1_info"], f"Live data version differs: {info}"
        report["data_version"] = info
        update_path = f"/sdcard/Android/data/{GAME}/files/Cache/Update/NewVersionInfo.json"
        marker = json.loads(adb("exec-out", "cat", update_path))
        report["update_markers"] = {update_path: marker}
        assert int(marker["needDownloadSize"]) == 0, "In-game update incomplete"
        before = device_hashes()
        report["before_hashes"] = before
        save()
        adb("shell", "mkdir", remote)
        adb("shell", "chmod", "755", remote)
        adb("shell", "touch", remote + "/before.tar")
        adb("shell", "chmod", "666", remote + "/before.tar")
        print("Creating current-layer recovery archive on phone", flush=True)
        private(f"tar -cf {remote}/before.tar packages Watchdog")
        backup = work / "before-benchmark.tar"
        print("Pulling and verifying the recovery archive", flush=True)
        adb("pull", remote + "/before.tar", str(backup), timeout=900)
        assert archive_hashes(backup) == before, "Recovery backup differs from live files"
        report.update(backup=str(backup), backup_sha256=digest(backup), backup_verified=True)
        save()
        adb("shell", "rm", remote + "/before.tar")
        print(f"Recovery backup verified: {len(before)} files", flush=True)
        if not args.restore:
            report["status"] = "backup-verified"
            return
        print("Transferring the matching pristine layer", flush=True)
        adb("push", str((args.snapshot / "device-backup.tar").resolve()), remote + "/pristine.tar", timeout=900)
        adb("shell", "chmod", "644", remote + "/pristine.tar")
        assert adb("shell", "sha256sum", remote + "/pristine.tar").decode().split()[0] == report["pristine_archive_sha256"]
        assert json.loads(private("cat packages/1/1.info")) == info
        moved = True
        print("Restoring pristine packages; keeping rollback directories until verified", flush=True)
        private(f"set -e; test ! -e {old_packages}; test ! -e {old_watchdog}; "
                f"mv packages {old_packages}; mv Watchdog {old_watchdog}; tar -xf {remote}/pristine.tar; sync")
        assert device_hashes() == incoming, "Pristine file inventory/hash differs"
        verified = True
        report.update(status="pristine-verified", verified_files=len(incoming))
        save()
        private(f"rm -rf {old_packages} {old_watchdog}")
        adb("shell", "rm", remote + "/pristine.tar")
        print(f"Pristine layer verified: {len(incoming)} files", flush=True)
    except BaseException as error:
        report["error"] = str(error)
        if moved and not verified:
            private(f"if [ -d {old_packages} ]; then rm -rf packages; mv {old_packages} packages; fi; "
                    f"if [ -d {old_watchdog} ]; then rm -rf Watchdog; mv {old_watchdog} Watchdog; fi; sync")
            report["status"] = "rolled-back"
            assert device_hashes() == before, "Rollback differs from saved live layer"
        raise
    finally:
        if access_attempted:
            print("Restoring verified normal APK; approve installation prompts", flush=True)
            report["normal_apk_restored"] = False
            for attempt in range(3):
                try:
                    assert b"Success" in adb("install", "-r", str(args.normal.resolve()), timeout=360)
                    assert installed_hash(GAME) == normal_sha
                    assert "DEBUGGABLE" not in adb("shell", "dumpsys", "package", GAME).decode()
                    report["normal_apk_restored"] = True
                    break
                except Exception as error:
                    print(f"Normal restore attempt {attempt + 1} failed: {error}", flush=True)
            save()
            assert report["normal_apk_restored"], "Normal APK recovery still required"
        save()
        print(json.dumps({k: v for k, v in report.items() if k not in ("before_hashes", "update_markers")}, indent=2), flush=True)


if __name__ == "__main__":
    main()
