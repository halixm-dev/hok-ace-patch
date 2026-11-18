"""Remove on real game data, offline: install a real build on a stand-in phone, Remove it, compare to pristine.

    .venv\\Scripts\\python.exe tools\\research\\check_windows_remove.py --pristine <builtin-dir> ^
        --staged <build-output> [--staged <another build-output>] --work <empty-dir>

<builtin-dir> is a pristine `WXQ_Data/Package/builtin`; each <build-output> is a `build_device_patch.py`
`--output` made from that layer. The stand-in phone holds the pristine copy of every package the build
touches (not the untouched ones). Each output then goes through the real Windows install
(`check_first_delta`, `push_translation`) and the real Remove (`restore_pristine`, `write_back_pristine`)
with the stand-in for adb from `check_windows_repatch.py`. Remove passes when every file on the phone is
byte-identical to pristine again, the removed list is exactly the files the install changed, and no delta
is left. Needs about 5x the touched packages' size free under <work>. Never touches a phone.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_windows_repatch as repatch  # noqa: E402
from check_windows_repatch import LAYER, patcher_core, pristine_delta  # noqa: E402

SUMMARY = "device_patch_summary.json"


def _hashes(root: Path) -> dict[str, str]:
    return {name: pristine_delta.sha256_file(root / name) for name in pristine_delta.package_files(root)}


def _one(pristine: Path, staged: Path, work: Path) -> dict:
    """One build output: install, then Remove; return the measured result or raise AssertionError."""
    packages = sorted({name.split("/", 1)[0] for name in pristine_delta.package_files(staged)})
    case = repatch.Repatch("test_remove_without_a_record_is_refused")
    case.setUp()
    shutil.rmtree(case.work)  # the synthetic phone setUp made; this run uses real data under <work>
    try:
        case.work = work
        work.mkdir(parents=True)
        case.phone = work / "phone"
        case.store = repatch.RunStore(work / "fixture-state")
        for package in packages:
            shutil.copytree(pristine / package, case.phone / package)
        before = _hashes(case.phone)
        started = time.monotonic()

        patcher = case.patcher()
        session = case.session()
        assert patcher.restore_pristine(session) is None, "the stand-in phone did not read as pristine"
        payload = session / "staged"
        for name in pristine_delta.package_files(staged):
            (payload / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(staged / name, payload / name)
        summary = json.loads((staged / SUMMARY).read_text(encoding="utf-8"))
        shutil.copyfile(staged / SUMMARY, payload / SUMMARY)
        patcher.check_first_delta(summary)
        patcher.push_translation(session, payload, [])
        patcher.file_transaction.finalize(patcher.keep, lambda: None)
        installed = _hashes(case.phone)
        changed = sorted(name for name in installed if installed[name] != before.get(name))
        assert changed, "the install changed no file"
        assert all(installed[name] == pristine_delta.sha256_file(staged / name)
                   for name in pristine_delta.package_files(staged)), "the phone does not hold the build"
        installed_at = time.monotonic()

        remover = case.patcher(remove=True)
        session = case.session()
        result = remover.write_back_pristine(session, remover.restore_pristine(session))
        remover.file_transaction.finalize(remover.keep, lambda: None)
        after = _hashes(case.phone)
        differing = sorted(name for name in set(before) | set(after) if before.get(name) != after.get(name))
        assert not differing, f"not pristine after Remove: {differing}"
        assert sorted(result["removed"]) == changed, (sorted(result["removed"]), changed)
        assert not patcher_core.holds_delta(work), "a delta is left after Remove"
        return {"packages": len(packages), "files": len(before), "changed": len(changed),
                "removed": len(result["removed"]), "install_s": round(installed_at - started),
                "remove_s": round(time.monotonic() - installed_at)}
    finally:
        case.doCleanups()
        if case.active is not None:
            case.active.run_owner.close()
            case.active = None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pristine", type=Path, required=True)
    parser.add_argument("--staged", type=Path, action="append", required=True)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12):
        parser.error("Use Python 3.12")
    if args.work.exists() and any(args.work.iterdir()):
        parser.error("--work must be empty or absent")
    failed = 0
    for index, staged in enumerate(args.staged):
        work = args.work / str(index)
        try:
            print(f"PASS {staged}: {_one(args.pristine, staged, work)}")
        except AssertionError as error:
            failed += 1
            print(f"FAIL {staged}: {error}")
        finally:
            shutil.rmtree(work, ignore_errors=True)
    return int(bool(failed))


if __name__ == "__main__":
    raise SystemExit(main())
