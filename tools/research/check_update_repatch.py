"""Check the repatch after an in-game update offline, on a kept session's real packages.

    .venv\\Scripts\\python.exe tools\\research\\check_update_repatch.py --session <session> ^
        --work <scratch dir> [--apk <installed.apk>] [--skip-build]

<session> is a Windows session whose `game/.../builtin` holds the pristine layer and whose `staged/`
holds an install built from it. The phone after that install is the pristine packages with the staged
files laid over them. Each scenario then fakes what an update could leave, by writing asset bytes in
place (`device_extensions.write_assets`, which moves chunks and rewrites the index as a merge does),
and checks what `pristine_delta.accept_replaced` decides:

- no update: the delta rebuilds every file;
- an update merged into a package that still holds this patcher's assets: refused;
- an update replaced a package (pristine bytes plus a merged Chinese asset): accepted;
- a repair put back only some of the translated assets, then a merge: refused;
- a package whose index is still at the staged bytes while its shard changed: refused;
- an update removed a whole package: accepted;
- a shard missing beside its index: refused;
- a delta made before asset fingerprints existed: refused.

`accept_replaced` calls the partial repair restorable; the Windows patcher refuses it like any other,
as `decide` does. The Android bridge's `_restore_pristine` then runs over six of them in its snapshot
layout, and restores the partial repair's 151 textures instead (ADR 0008). Unless
--skip-build, it then runs the Windows patcher's own pull, rebuild, build (with the APK when
given), text signal and push against a fake phone holding the accepted update, and a second run over
the result, which must rebuild from the new delta. Faked updates stand in for a real one: what a real
update leaves was ticket 01 of language-switch (`docs/features/language-switch.md`).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import patcher_core  # noqa: E402  (puts tools/ and the runtime on sys.path)
from patcher_core import LAYER, PULL_RECORD, Patcher  # noqa: E402
import pristine_delta  # noqa: E402
from pristine_delta import CHANGED, MISSING  # noqa: E402

PACKAGES = ["0", "1", "10", "15", "19", "20", "21", "1050016095"]


def link_tree(source: Path, target: Path) -> None:
    """<target> holds every file of <source> as a hard link (read only by convention)."""
    for path in source.rglob("*"):
        if path.is_file():
            (target / path.relative_to(source)).parent.mkdir(parents=True, exist_ok=True)
            os.link(path, target / path.relative_to(source))


def fresh(base: Path, layer: Path, package: str) -> Path:
    """Replace <layer>'s package with a real copy of <base>'s, safe to write in place."""
    shutil.rmtree(layer / package, ignore_errors=True)
    shutil.copytree(base / package, layer / package)
    return layer / package


def merge_chinese_asset(package_dir: Path, recorded: dict) -> str:
    """Write one asset this patcher never changed with one byte flipped, as an update's merge would."""
    from device_extensions import write_assets
    from qts_relocate import install_btree_slot_map, read_raw
    from wxq_patch.qtsvfs import QtsPackage

    install_btree_slot_map()
    package = QtsPackage(package_dir)
    slots = package.build_slot_map()
    for file_hash, entry in package.entries.items():
        name = f"{file_hash:016X}"
        if name in recorded or entry.compression not in (1, 4):
            continue
        raw = read_raw(package, slots, file_hash)
        if not raw or len(raw) < 64:
            continue
        written, _ = write_assets(package_dir, {file_hash: raw[:-1] + bytes([raw[-1] ^ 1])})
        if written:
            return name
    raise RuntimeError(f"{package_dir.name}: no asset to merge into")


def restore_assets(package_dir: Path, pristine_dir: Path, names: list[str]) -> list[str]:
    """Write the pristine bytes of <names> back, as the updater's repair would; returns those written."""
    from device_extensions import write_assets
    from qts_relocate import install_btree_slot_map, read_raw
    from wxq_patch.qtsvfs import QtsPackage

    install_btree_slot_map()
    pristine = QtsPackage(pristine_dir)
    slots = pristine.build_slot_map()
    jobs = {int(name, 16): read_raw(pristine, slots, int(name, 16)) for name in names}
    written, _ = write_assets(package_dir, {key: raw for key, raw in jobs.items() if raw})
    return written


def decide(layer: Path, delta, out: Path):
    shutil.rmtree(out, ignore_errors=True)
    report = pristine_delta.rebuild(layer, delta, out)
    if report.complete:
        return report, [], {}
    accepted, restorable, refused = pristine_delta.accept_replaced(layer, delta, report)
    return report, accepted, {**restorable, **refused}  # as the Windows patcher, which refuses both


class Checks:
    def __init__(self, session: Path, work: Path):
        self.pristine, self.staged, self.work = session / LAYER, session / "staged", work
        self.failures: list[str] = []

    def expect(self, name: str, condition: bool, detail: str) -> None:
        print(f"{'PASS' if condition else 'FAIL'}  {name}: {detail}")
        if not condition:
            self.failures.append(name)

    def setup(self) -> None:
        if self.work.exists():
            shutil.rmtree(self.work)
        self.installed = self.work / "installed"
        for package in PACKAGES:
            shutil.copytree(self.pristine / package, self.installed / package)
        for name in pristine_delta.package_files(self.staged):
            shutil.copyfile(self.staged / name, self.installed / name)
        start = time.perf_counter()
        self.delta = pristine_delta.make(self.pristine, self.staged, info={"check": "update"}, fingerprint=True)
        self.delta = pristine_delta.decode(pristine_delta.encode(self.delta))  # as read back from disk
        counts = {package: len(assets) for package, assets in self.delta.assets.items()}
        print(f"delta: {len(self.delta.files)} files, changed assets per package {counts} "
              f"({time.perf_counter() - start:.1f} s)")

    def scenario(self, name: str) -> Path:
        layer = self.work / "scenarios" / name
        link_tree(self.installed, layer)
        return layer

    def run_scenarios(self) -> Path:
        assets = self.delta.assets
        out = self.work / "rebuilt"

        layer = self.scenario("no-update")
        report, _, _ = decide(layer, self.delta, out)
        self.expect("no update", report.complete and len(report.rebuilt) == 11, f"rebuilt {len(report.rebuilt)}")

        layer = self.scenario("merge-over-patched")
        merged = merge_chinese_asset(fresh(self.installed, layer, "10"), assets["10"])
        _, accepted, refused = decide(layer, self.delta, out)
        self.expect("merge over a patched package", "10" in refused and not accepted,
                    f"merged {merged}; refused {refused}")

        layer = self.scenario("replaced")
        for package in ("1", "15"):
            merge_chinese_asset(fresh(self.pristine, layer, package), assets[package])
        _, accepted, refused = decide(layer, self.delta, out)
        self.expect("package replaced by the update", not refused and sorted(accepted) == sorted(
            [n for n in (f"1/1.db", "1/1_0.db", "15/15.db", "15/15_0.db")
             if pristine_delta.sha256_file(layer / n) != pristine_delta.sha256_file(self.pristine / n)]),
            f"accepted {accepted}; refused {refused}")
        replaced_layer = layer

        layer = self.scenario("partial-repair")
        package_dir = fresh(self.installed, layer, "15")
        changed = sorted(assets["15"])
        written = restore_assets(package_dir, self.pristine / "15", changed[: len(changed) // 2])
        merge_chinese_asset(package_dir, assets["15"])
        _, accepted, refused = decide(layer, self.delta, out)
        self.expect("repair put back half the textures", "15" in refused,
                    f"restored {len(written)} of {len(changed)}; refused {refused}")

        layer = self.scenario("full-repair")
        package_dir = fresh(self.installed, layer, "15")
        written = restore_assets(package_dir, self.pristine / "15", changed)
        merge_chinese_asset(package_dir, assets["15"])
        _, accepted, refused = decide(layer, self.delta, out)
        complete = len(written) == len(changed)
        self.expect("repair put back every texture", ("15" not in refused) == complete,
                    f"restored {len(written)} of {len(changed)}; accepted {accepted}; refused {refused}")

        layer = self.scenario("index-still-staged")
        package_dir = fresh(self.installed, layer, "21")
        merge_chinese_asset(package_dir, assets["21"])
        shutil.copyfile(self.staged / "21/21.db", package_dir / "21.db")
        _, accepted, refused = decide(layer, self.delta, out)
        staged_index = pristine_delta.sha256_file(package_dir / "21.db") == pristine_delta.sha256_file(self.staged / "21/21.db")
        self.expect("index at staged bytes, shard changed", "21" in refused,
                    f"index staged {staged_index}; refused {refused}")

        layer = self.scenario("package-removed")
        shutil.rmtree(layer / "1050016095")
        _, accepted, refused = decide(layer, self.delta, out)
        self.expect("package removed", not refused and sorted(accepted) == ["1050016095/1050016095.db",
                                                                              "1050016095/1050016095_0.db"],
                    f"accepted {accepted}; refused {refused}")

        layer = self.scenario("shard-missing")
        (layer / "19/19_0.db").unlink()
        _, accepted, refused = decide(layer, self.delta, out)
        self.expect("shard missing beside its index", "19" in refused, f"refused {refused}")

        old = pristine_delta.Delta(self.delta.files, self.delta.info)  # no asset record
        _, accepted, refused = decide(replaced_layer, old, out)
        self.expect("delta without asset fingerprints", set(refused) == {"1", "15"} and not accepted,
                    f"refused {refused}")
        return replaced_layer

    def run_android(self) -> None:
        """The Android bridge's `_restore_pristine` over the same scenarios, with its snapshot layout."""
        sys.path.insert(0, str(ROOT / "android" / "app" / "src" / "main" / "python"))
        import android_bridge

        keep = self.work / "android-keep"
        keep.mkdir(parents=True, exist_ok=True)
        pristine_delta.write(self.delta, keep / pristine_delta.DELTA_NAME)
        pristine_delta.record_staged_hashes(keep / pristine_delta.STAGED_HASHES_NAME, self.delta.staged_hashes)
        for name, refuse in [("no-update", False), ("replaced", False), ("full-repair", False),
                             ("package-removed", False), ("merge-over-patched", True),
                             ("partial-repair", False)]:  # asset restore (ADR 0008) takes the repaired half
            session = self.work / "android" / name
            link_tree(self.work / "scenarios" / name, session / "snapshot" / "packages")
            try:
                restored = android_bridge._restore_pristine(session, keep)
            except android_bridge.PatchError as error:
                self.expect(f"android {name}", refuse, f"refused: {str(error)[:160]}")
                continue
            copy = session / android_bridge.PRISTINE_COPY
            # `_link_build_input` reads every `sha256` name from the copy and every other file from the
            # snapshot, so the copy must hold exactly those, at those hashes.
            copied = all((copy / item).is_file() and pristine_delta.sha256_file(copy / item) == digest
                         for item, digest in restored["sha256"].items())
            outside = not set(restored["replaced"]) & set(restored["sha256"])
            taken = sorted(restored["assets_restored"], key=int)
            self.expect(f"android {name}", not refuse and copied and outside
                        and taken == (["15"] if name == "partial-repair" else []),
                        f"mode {restored['mode']}, rebuilt {len(restored['rebuilt'])}, replaced "
                        f"{restored['replaced']}, assets restored in {taken}, copy matches {copied}")

    def run_patcher(self, update: Path, apk: Path | None) -> None:
        """The Windows patcher's own steps over the faked update, then a second run over its result."""
        from check_windows_repatch import FakeAdb, Ui

        work = self.work / "patcher"
        phone = work / "phone"
        shutil.copytree(update, phone)
        keep = work / "pristine"
        keep.mkdir(parents=True)
        pristine_delta.write(self.delta, keep / pristine_delta.DELTA_NAME)
        pristine_delta.record_staged_hashes(keep / pristine_delta.STAGED_HASHES_NAME, self.delta.staged_hashes)
        # The session of the install, as a previous session the partial pull copies from.
        previous = work / "sessions" / "20261017-000000"
        link_tree(self.installed, previous / LAYER)
        link_tree(self.staged, previous / "staged")
        hashes = {path.relative_to(self.installed).as_posix(): pristine_delta.sha256_file(path)
                  for path in self.installed.rglob("*") if path.is_file()}
        (previous / PULL_RECORD).write_text(json.dumps({"mode": "full", "sha256": hashes}), encoding="utf-8")

        for run in (1, 2):
            ui = Ui()
            patcher = Patcher(ui, work, "en")
            patcher.adb = FakeAdb(phone)
            patcher.normal_apk = apk
            patcher.ui.set_step = lambda *args: None
            from unittest import mock
            with mock.patch.object(patcher_core, "datetime") as clock:
                clock.now.return_value.strftime.return_value = f"20261018-00000{run}"
                session = patcher.pull_game_data()
            record = json.loads((session / PULL_RECORD).read_text(encoding="utf-8"))
            restored = patcher.restore_pristine(session)
            start = time.perf_counter()
            summary, staged = patcher.build_translation(session)
            build_seconds = time.perf_counter() - start
            if restored is None or patcher.replaced:
                patcher.check_first_delta(summary)
                restored = restored or []
            pushed_before = len(patcher.adb.pushed)
            if staged or restored:
                patcher.push_translation(session, staged, restored)
            pushed = patcher.adb.pushed[pushed_before:]
            text = pristine_delta.text_not_pristine(summary)
            delta = pristine_delta.read(keep / pristine_delta.DELTA_NAME)
            print("\n".join("    " + line for line in ui.lines if "rebuilt" in line or "replaced" in line
                            or "unchanged since" in line or "already on the phone" in line or "pulled" in line))
            if run == 1:
                self.expect("patcher run over the update",
                            record["mode"] == "changed" and sorted(patcher.replaced) and text is None
                            and delta.assets is not None and len(restored) > 0,
                            f"pull {record['mode']} ({record.get('pulled_files')} files pulled), "
                            f"replaced {patcher.replaced}, rebuilt {len(restored)}, text signal "
                            f"{text or 'pristine'}, build {build_seconds:.0f} s, pushed {len(pushed)}")
                # The new delta points at the update's bytes for the files it replaced.
                for name in patcher.replaced:
                    entry = delta.entry(name)
                    if entry is not None:
                        self.expect(f"new delta's pristine side of {name}",
                                    entry.pristine_sha256 == pristine_delta.sha256_file(update / name),
                                    "equals the update's bytes")
            else:
                self.expect("second run rebuilds from the new delta",
                            not patcher.replaced and len(restored) > 0 and not pushed and text is None,
                            f"pull {record['mode']} ({record.get('pulled_files')} files pulled), rebuilt "
                            f"{len(restored)}, pushed {len(pushed)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--apk", type=Path)
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()
    checks = Checks(args.session, args.work)
    checks.setup()
    update = checks.run_scenarios()
    checks.run_android()
    if not args.skip_build:
        checks.run_patcher(update, args.apk)
    print(f"\n{'FAILED: ' + ', '.join(checks.failures) if checks.failures else 'all checks passed'}")
    sys.exit(1 if checks.failures else 0)


if __name__ == "__main__":
    main()
