"""Check Re-download against the real update captured on 2026-10-23 (lab notebook, "An update over a patched
layer, captured end to end").

    .venv\\Scripts\\python.exe tools\\research\\check_update_redownload.py --work <scratch dir on D:> ^
        [--cycle D:\\scratch\\hok-update-cycle] [--expect-update 1,10,21] [--expect-finish 10,21]

Another cycle's captures pass the packages its phone planned: over `after-finish`, the layer once the game
has downloaded them again, a run that deleted every planned package at once expects none (`--expect-finish ""`).

The cycle's captures (`tools/research/update_cycle.py`) name every file's SHA-256; the bytes come from its
`objects/` store and the extracted snapshots, hard-linked, so <work> must be on the same drive. The delta
is made as the Android patcher made it after `after-patch` (pristine 1.6.0.1 against the English install,
with asset fingerprints). Over the `after-update` layer, where the game's repair stuck on package `1` while
`10` and `21` kept appended assets and `15`, `19`, `20` kept only modified ones:
- Re-download plans `1`, `10` and `21` in one run, and nothing restore can take;
- over the `after-finish` layer (package `1` downloaded again), it plans `10` and `21`, as the phone did;
- (ticket 17) a second plan of the same session, through an engine the bridge can identify, plans exactly
  the same files and reuses the first one's mixed-package decision, so it runs fewer trial restores (the
  graphics inspection's trial restores are not kept).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.append(str(ROOT / "resources" / "runtime"))
sys.path.insert(0, str(ROOT / "android" / "app" / "src" / "main" / "python"))
import pristine_delta  # noqa: E402

SNAPSHOTS = ROOT / "dist" / "HOK ACE Patcher Data" / "pristine"
TRANSLATED = ["1", "10", "1050016095", "15", "19", "20", "21"]


class Bytes:
    """A file holding each SHA-256: the cycle's objects, then the snapshots' extracted layers."""

    def __init__(self, cycle: Path) -> None:
        self.objects = cycle / "objects"
        self.layers: dict[str, Path] = {}
        for record in sorted(SNAPSHOTS.glob("*/snapshot.json")):
            builtin = record.parent / "game" / "WXQ_Data" / "Package" / "builtin"
            for path, digest in json.loads(record.read_text(encoding="utf-8"))["device_sha256"].items():
                if path.startswith("packages/") and (builtin / path.removeprefix("packages/")).is_file():
                    self.layers.setdefault(digest, builtin / path.removeprefix("packages/"))

    def path(self, digest: str) -> Path:
        own = self.objects / digest
        return own if own.is_file() else self.layers[digest]


def capture(cycle: Path, label: str) -> dict[str, str]:
    return json.loads((cycle / label / "capture.json").read_text(encoding="utf-8"))["files"]


def link_layer(files: dict[str, str], source: Bytes, target: Path, names: list[str]) -> None:
    for name in names:
        (target / name).parent.mkdir(parents=True, exist_ok=True)
        os.link(source.path(files[f"packages/{name}"]), target / name)


def package_names(files: dict[str, str]) -> list[str]:
    return sorted(path.removeprefix("packages/") for path in files
                  if path.startswith("packages/") and path.split("/")[1] in TRANSLATED)


def session(cycle: Path, label: str, source: Bytes, root: Path) -> Path:
    """An Android session whose snapshot is the translated packages and `Watchdog` of capture <label>."""
    files = capture(cycle, label)
    snapshot = root / "snapshot"
    names = package_names(files)
    link_layer(files, source, snapshot / "packages", names)
    with tarfile.open(cycle / label / "Watchdog.tar") as tar:
        member = next((m for m in tar.getmembers() if m.name.endswith("Watchdog/BrokenList.db")), None)
        (snapshot / "Watchdog").mkdir(parents=True)
        if member is not None:
            (snapshot / "Watchdog" / "BrokenList.db").write_bytes(tar.extractfile(member).read())
    manifest = {f"packages/{name}": {"bytes": (snapshot / "packages" / name).stat().st_size,
                                     "sha256": files[f"packages/{name}"]} for name in names}
    if (snapshot / "Watchdog" / "BrokenList.db").is_file():
        path = snapshot / "Watchdog" / "BrokenList.db"
        manifest["Watchdog/BrokenList.db"] = {"bytes": path.stat().st_size,
                                              "sha256": pristine_delta.sha256_file(path)}
    (snapshot / "manifest.json").write_text(json.dumps({"schema": 1, "files": manifest, "directories": []}),
                                            encoding="utf-8")
    return root


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cycle", type=Path, default=Path(r"D:\scratch\hok-update-cycle"))
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--expect-update", default="1,10,21",
                        help="packages Re-download plans over after-update (the 2026-10-23 cycle's by default)")
    parser.add_argument("--expect-finish", default="10,21",
                        help="packages it plans over after-finish; empty for a layer that needs none")
    args = parser.parse_args()
    if args.work.exists():
        shutil.rmtree(args.work)
    args.work.mkdir(parents=True)
    import android_bridge as bridge

    source = Bytes(args.cycle)
    pushed, patched = capture(args.cycle, "after-push"), capture(args.cycle, "after-patch")
    # A staged output holds every `.db` of each package it changed, the unchanged index included.
    changed = {name.split("/")[0] for name in package_names(patched)
               if pushed.get(f"packages/{name}") != patched[f"packages/{name}"]}
    staged_names = [name for name in package_names(patched)
                    if name.split("/")[0] in changed and name.endswith(".db")]
    pristine, staged = args.work / "pristine", args.work / "staged"
    link_layer(pushed, source, pristine, package_names(pushed))
    link_layer(patched, source, staged, staged_names)
    delta = pristine_delta.make(pristine, staged, info={"patcher": "android"}, fingerprint=True)
    keep = args.work / "keep"
    keep.mkdir()
    pristine_delta.write(delta, keep / pristine_delta.DELTA_NAME)
    pristine_delta.record_staged_hashes(keep / pristine_delta.STAGED_HASHES_NAME, delta.staged_hashes)
    engine = args.work / "engine"
    engine.mkdir()
    for name, target in (("runtime", ROOT / "resources" / "runtime"), ("tools", ROOT / "tools"),
                         ("catalog", ROOT / "resources" / "catalog"),
                         ("catalog_id", ROOT / "resources" / "catalog_id")):
        subprocess.run(["cmd", "/c", "mklink", "/J", str(engine / name), str(target)], check=True,
                       capture_output=True)

    # Ticket 17: a real copy of the engine can be identified, so the bridge keeps its decision for the
    # session; the junction engine above cannot, so the first plan of each session is the fresh control.
    identified = args.work / "engine-copy"
    shutil.copytree(ROOT / "tools", identified / "tools", ignore=shutil.ignore_patterns("__pycache__", "research"))
    shutil.copytree(ROOT / "resources" / "runtime", identified / "runtime", ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("catalog", "catalog_id"):
        shutil.copytree(ROOT / "resources" / name, identified / name)

    failures = []
    expectations = (("after-update", args.expect_update), ("after-finish", args.expect_finish))
    for label, expected in ((label, [name for name in text.split(",") if name]) for label, text in expectations):
        root = session(args.cycle, label, source, args.work / label)
        # What a patch run's refused build leaves behind, before the same run plans the deletion: the
        # build claims ownership first (`_own_legacy_build`), which is what `clear_build` resets.
        bridge._own_legacy_build(root.absolute())
        (root / "out").mkdir()
        (root / "game" / "WXQ_Data").mkdir(parents=True)
        (root / "staged-hashes.json").write_text("{}", encoding="utf-8")
        bridge.clear_build(str(root))
        try:
            plan = json.loads(bridge.plan_redownload(str(engine), str(root), str(keep)))
        except bridge.PatchError as error:
            # A layer the game has downloaded again in full holds nothing to re-download: the bridge refuses.
            if expected or bridge.NOTHING_TO_REDOWNLOAD not in str(error):
                raise
            print(f"ok   {label}: Re-download plans nothing (refused: {bridge.NOTHING_TO_REDOWNLOAD}), expected []")
            continue
        planned = sorted(plan["packages"], key=int)
        files = sorted({name.split("/")[0] for name in plan["redownload"]}, key=int)
        ok = planned == expected and files == expected
        print(f"{'ok  ' if ok else 'FAIL'} {label}: Re-download plans {planned} ({len(plan['redownload'])} files), "
              f"expected {expected}")
        if not ok:
            failures.append(label)
        control = (plan, json.loads((root / "staged-hashes.json").read_text(encoding="utf-8")))
        bridge._forget_mixed_decisions()
        rounds = []
        for round_name in ("first", "again"):
            folder = root / "redownload-plans" / round_name
            before = dict(bridge.MIXED_DECISION_STATS)
            again = json.loads(bridge.plan_redownload(str(identified), str(root), str(keep), str(folder)))
            moved = {name: bridge.MIXED_DECISION_STATS[name] - before[name] for name in before}
            rounds.append(((again, json.loads((folder / "staged-hashes.json").read_text(encoding="utf-8"))), moved))
        (first, first_moved), (second, second_moved) = rounds
        mixed = bool(first_moved["computed"])  # a layer with no mixed package decides nothing
        # Ticket 17 keeps `_mixed_packages`' decision; the graphics inspection's trial restores of a suspect
        # package are not kept, so the second plan still restores those, and only those.
        ok = (first == control and second == control
              and (not mixed or (first_moved["recorded"] >= 1 and second_moved["reused"] >= 1
                                 and second_moved["restores"] < first_moved["restores"])))
        print(f"{'ok  ' if ok else 'FAIL'} {label}: the same session plans the same again, reusing its decision "
              f"(first: computed {first_moved['computed']:.0f}, restores {first_moved['restores']:.0f}, "
              f"copied {first_moved['copied_bytes']:,.0f} B; again: reused {second_moved['reused']:.0f}, "
              f"restores {second_moved['restores']:.0f}, proof hashed {second_moved['proof_bytes']:,.0f} B)")
        if not ok:
            failures.append(f"{label} reuse")
    shutil.rmtree(args.work, ignore_errors=True)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
