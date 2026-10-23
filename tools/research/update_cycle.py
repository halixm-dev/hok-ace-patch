"""Run a device cycle at an in-game update: put a pristine snapshot on the phone, then capture each step.

    .venv\\Scripts\\python.exe tools\\research\\update_cycle.py push --cycle <dir> --snapshot <snapshot dir>
    .venv\\Scripts\\python.exe tools\\research\\update_cycle.py capture <label> --cycle <dir>
    .venv\\Scripts\\python.exe tools\\research\\update_cycle.py compare <label-a> <label-b> --cycle <dir>

For `.scratch/language-switch` tickets 01 and 07. <cycle> holds one folder per capture and an `objects/`
store of package bytes by SHA-256. A capture installs the access APK, hashes every file under
`files/QtsVFSCache` on the phone, keeps `Watchdog/` and the game's logs whole, and pulls only the package
files whose bytes no snapshot or earlier capture holds. The normal APK goes back in a `finally`, and its
SHA-256 on the phone is checked. `push` captures the phone first (`before-push`), then replaces
`packages` and `Watchdog` with the snapshot's `device-backup.tar` and checks every file against its
`snapshot.json`.

`compare` names each package file that changed between two captures, whether it was rewritten in place or
grew, which known snapshot it now equals, what `BrokenList.db` names and which `History.db` records are new.
Run from the project root with the phone on USB and nothing else using adb.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import broken_list  # noqa: E402
import pristine_delta  # noqa: E402
import watchdog_history  # noqa: E402

GAME = "com.tencent.tmgp.osgame"
PATCHER = "dev.halixm.hokacepatcher"
DATA = ROOT / "dist" / "HOK ACE Patcher Data"
ACCESS_APK = DATA / "access.apk"
NORMAL_APK = DATA / "installed.apk"
SNAPSHOTS = DATA / "pristine"
CACHE = "files/QtsVFSCache"
EXTERNAL = f"/sdcard/Android/data/{GAME}/files"
EXTERNAL_FILES = ("Cache/Update/NewVersionInfo.json", "bqLog/ccs_log/normal1.log")
REMOTE_TMP = "/data/local/tmp/hokace-cycle"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def adb(*args: str, check: bool = True, binary: bool = False, timeout: float | None = None) -> str | bytes:
    result = subprocess.run(["adb", *args], capture_output=True, timeout=timeout)
    if check and result.returncode != 0:
        raise SystemExit(f"adb {' '.join(args)} failed: {(result.stdout + result.stderr).decode(errors='replace')}")
    return result.stdout if binary else result.stdout.decode("utf-8", errors="replace")


def run_as(command: str, *, binary: bool = False, check: bool = True) -> str | bytes:
    return adb("exec-out", f"run-as {GAME} sh -c '{command}'", binary=binary, check=check)


def install(apk: Path) -> None:
    for attempt in range(2):
        output = adb("install", "-r", str(apk), check=False)
        if "Success" in output:
            return
        print(f"  install {apk.name} attempt {attempt + 1}: {output.strip()}")
    raise SystemExit(f"could not install {apk}")


def installed_apk_sha256() -> str:
    path = adb("shell", "pm", "path", GAME).strip().splitlines()[0].removeprefix("package:")
    return adb("shell", "sha256sum", path).split()[0]


class AccessWindow:
    """The access APK installed for the duration of a `with`, the normal APK reinstalled and checked after."""

    def __init__(self) -> None:
        self.normal_sha256 = pristine_delta.sha256_file(NORMAL_APK)

    def __enter__(self) -> AccessWindow:
        adb("shell", "am", "force-stop", GAME)
        print("installing the access APK")
        install(ACCESS_APK)
        return self

    def __exit__(self, *_: object) -> None:
        print("reinstalling the normal APK")
        install(NORMAL_APK)
        actual = installed_apk_sha256()
        if actual != self.normal_sha256:
            raise SystemExit(f"normal APK on the phone is {actual}, expected {self.normal_sha256}")
        print(f"  normal APK verified ({actual[:12]})")


class Objects:
    """Package bytes by SHA-256: this cycle's own store, then every snapshot's `device-backup.tar`."""

    def __init__(self, cycle: Path) -> None:
        self.store = cycle / "objects"
        self.store.mkdir(parents=True, exist_ok=True)
        self.in_tar: dict[str, tuple[Path, str]] = {}
        for record in sorted(SNAPSHOTS.glob("*/snapshot.json")):
            tar = record.parent / "device-backup.tar"
            if tar.is_file():
                for path, digest in json.loads(record.read_text(encoding="utf-8"))["device_sha256"].items():
                    self.in_tar.setdefault(digest, (tar, path))

    def has(self, digest: str) -> bool:
        return digest in self.in_tar or (self.store / digest).is_file()

    def path(self, digest: str, scratch: Path) -> Path:
        """A file holding <digest>'s bytes, extracted into <scratch> when it lives in a snapshot's tar."""
        own = self.store / digest
        if own.is_file():
            return own
        tar_path, member = self.in_tar[digest]
        target = scratch / digest
        if not target.is_file():
            scratch.mkdir(parents=True, exist_ok=True)
            with tarfile.open(tar_path) as tar:
                source = tar.extractfile(member) or tar.extractfile("./" + member)
                target.write_bytes(source.read())
        return target

    def add(self, data: bytes) -> str:
        digest = sha256_bytes(data)
        (self.store / digest).write_bytes(data)
        return digest

    def snapshot_names(self, digest: str) -> list[str]:
        return [record.parent.name for record in sorted(SNAPSHOTS.glob("*/snapshot.json"))
                if digest in json.loads(record.read_text(encoding="utf-8"))["device_sha256"].values()]


def phone_hashes() -> dict[str, str]:
    output = run_as(f"cd {CACHE} && find packages Watchdog -type f -exec sha256sum {{}} +")
    hashes = {}
    for line in output.splitlines():
        digest, _, path = line.strip().partition("  ")
        if len(digest) == 64:
            hashes[path.removeprefix("./")] = digest
    return hashes


def capture(cycle: Path, label: str, note: str = "") -> Path:
    folder = cycle / label
    if folder.exists():
        raise SystemExit(f"{folder} exists; pick another label")
    folder.mkdir(parents=True)
    objects = Objects(cycle)
    record: dict[str, object] = {"label": label, "note": note, "time": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    for name in EXTERNAL_FILES:
        data = adb("exec-out", f"cat {EXTERNAL}/{name}", binary=True, check=False)
        (folder / Path(name).name).write_bytes(data)
    record["external_listing"] = adb("shell", f"ls -la {EXTERNAL}/Cache/Update", check=False)
    with AccessWindow():
        record["info_1"] = run_as(f"cat {CACHE}/packages/1/1.info", check=False)
        record["listing"] = run_as(f"cd {CACHE} && ls -la . Watchdog packages/builtin 2>&1", check=False)
        print("hashing the layer on the phone")
        record["files"] = hashes = phone_hashes()
        (folder / "Watchdog.tar").write_bytes(run_as(f"cd {CACHE} && tar -cf - Watchdog", binary=True))
        (folder / "QtsVFS.log").write_bytes(run_as(f"cat {CACHE}/QtsVFS.log", binary=True, check=False))
        pulled = 0
        for path, digest in sorted(hashes.items()):
            if path.startswith("Watchdog/") or objects.has(digest):
                continue
            data = run_as(f"cat {CACHE}/{path}", binary=True)
            if objects.add(data) != digest:
                raise SystemExit(f"{path} changed while it was read")
            pulled += len(data)
            print(f"  pulled {path} ({len(data):,} B)")
        record["pulled_bytes"] = pulled
        patcher = adb("exec-out", f"run-as {PATCHER} tar -cf - -C files pristine", binary=True, check=False)
        if patcher[:512].strip(b"\0"):
            (folder / "patcher-pristine.tar").write_bytes(patcher)
    (folder / "capture.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(f"captured {label}: {len(hashes)} files, {pulled:,} B pulled")
    return folder


def push(cycle: Path, snapshot: Path) -> None:
    expected = json.loads((snapshot / "snapshot.json").read_text(encoding="utf-8"))["device_sha256"]
    tar = snapshot / "device-backup.tar"
    capture(cycle, "before-push", f"phone before {snapshot.name} was pushed")
    with AccessWindow():
        free = adb("shell", "df", "-k", "/data").splitlines()[-1].split()
        if int(free[3]) * 1024 < tar.stat().st_size * 1.2:
            raise SystemExit(f"phone has {int(free[3]) // 1024} MB free; the snapshot needs room for its tar first")
        adb("shell", f"rm -rf {REMOTE_TMP} && mkdir -p {REMOTE_TMP}")
        print(f"pushing {tar} ({tar.stat().st_size:,} B)")
        adb("push", str(tar), f"{REMOTE_TMP}/layer.tar", timeout=3600)
        adb("shell", f"chmod -R 755 {REMOTE_TMP}")
        run_as(f"cd {CACHE} && rm -rf packages Watchdog && tar -xf {REMOTE_TMP}/layer.tar")
        adb("shell", f"rm -rf {REMOTE_TMP}")
        actual = phone_hashes()
        wrong = sorted(path for path in set(expected) | set(actual) if expected.get(path) != actual.get(path)
                       and not path.startswith("Watchdog/"))
        if wrong:
            raise SystemExit(f"{len(wrong)} files differ from {snapshot.name} after the push: {wrong[:10]}")
        print(f"phone layer equals {snapshot.name}: {len(expected)} files")
    capture(cycle, "after-push", f"{snapshot.name} pushed")


def _history(folder: Path) -> list[watchdog_history.Record]:
    with tarfile.open(folder / "Watchdog.tar") as tar:
        member = next((m for m in tar.getmembers() if m.name.endswith("Watchdog/History.db")), None)
        return watchdog_history.parse(tar.extractfile(member).read()) if member else []


def _broken(folder: Path) -> broken_list.BrokenList:
    scratch = folder / "_broken"
    with tarfile.open(folder / "Watchdog.tar") as tar:
        member = next((m for m in tar.getmembers() if m.name.endswith("Watchdog/BrokenList.db")), None)
        if member is None:
            return broken_list.BrokenList()
        scratch.mkdir(exist_ok=True)
        (scratch / "BrokenList.db").write_bytes(tar.extractfile(member).read())
    return broken_list.read(scratch / "BrokenList.db")


def compare(cycle: Path, first: str, second: str) -> None:
    a = json.loads((cycle / first / "capture.json").read_text(encoding="utf-8"))
    b = json.loads((cycle / second / "capture.json").read_text(encoding="utf-8"))
    objects = Objects(cycle)
    scratch = cycle / "_compare"
    print(f"{first} -> {second}: 1.info {a['info_1']!r} -> {b['info_1']!r}")
    packages_a = {p: d for p, d in a["files"].items() if p.startswith("packages/")}
    packages_b = {p: d for p, d in b["files"].items() if p.startswith("packages/")}
    changed = sorted(p for p in set(packages_a) | set(packages_b) if packages_a.get(p) != packages_b.get(p))
    print(f"{len(changed)} package files changed of {len(packages_b)}")
    for path in changed:
        before, after = packages_a.get(path), packages_b.get(path)
        if before is None or after is None:
            print(f"  {path}: {'added' if before is None else 'removed'}")
            continue
        names = objects.snapshot_names(after)
        detail = ""
        if objects.has(before) and objects.has(after):
            old, new = objects.path(before, scratch), objects.path(after, scratch)
            ranges, _, _ = pristine_delta.changed_ranges(old, new)
            rewritten = sum(end - start for start, end in ranges)
            detail = (f"{old.stat().st_size:,} -> {new.stat().st_size:,} B, {len(ranges)} ranges "
                      f"({rewritten:,} B) rewritten")
        print(f"  {path}: {detail}{'; equals ' + ', '.join(names) if names else ''}")
    shutil.rmtree(scratch, ignore_errors=True)  # bytes extracted from the snapshots' tars
    known = {(r.when, r.kind, r.text) for r in _history(cycle / first)}
    new_records = [r for r in _history(cycle / second) if (r.when, r.kind, r.text) not in known]
    print(f"History.db: {len(new_records)} new records")
    for record in new_records[:40]:
        print(f"  {record.when.isoformat(sep=' ')} kind {record.kind}: {record.text}")
    broken = _broken(cycle / second)
    print(f"BrokenList.db: {sum(map(len, broken.assets.values()))} assets in "
          f"{sorted(broken.assets, key=int)}, {broken.unreadable} unreadable")
    for name in ("NewVersionInfo.json",):
        print(f"{name}: {(cycle / second / name).read_text(encoding='utf-8', errors='replace')[:400]}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)
    push_parser = sub.add_parser("push")
    push_parser.add_argument("--snapshot", type=Path, required=True)
    capture_parser = sub.add_parser("capture")
    capture_parser.add_argument("label")
    capture_parser.add_argument("--note", default="")
    compare_parser = sub.add_parser("compare")
    compare_parser.add_argument("first")
    compare_parser.add_argument("second")
    for each in (push_parser, capture_parser, compare_parser):
        each.add_argument("--cycle", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "push":
        push(args.cycle, args.snapshot)
    elif args.action == "capture":
        capture(args.cycle, args.label, args.note)
    else:
        compare(args.cycle, args.first, args.second)


if __name__ == "__main__":
    main()
