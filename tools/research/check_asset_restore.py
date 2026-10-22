"""Check asset restore (ADR 0008) offline, on a real pristine layer and the install staged from it.

    .venv\\Scripts\\python.exe tools\\research\\check_asset_restore.py --work D:\\scratch\\asset-restore ^
        [--pristine <builtin dir>] [--staged <staged output>] [--apk <path>\\installed.apk]

The defaults are the 1.7.0.1 pristine snapshot and the English install that went on the phone
(the asset restore spec, commit `a2526fa`, Evidence). The check fakes what an update that keeps part of
the translation leaves: a staged package with one asset this patcher never changed rewritten in place
(`device_extensions.write_assets`, as an update's merge would), so every file differs from both sides
of the delta while the translated assets survive. It then checks that
- the delta keeps each modified asset's pristine stored chunks and record, and nothing for an appended
  one, and that both survive the file format (a delta without them reads as before);
- `accept_replaced` calls such a package restorable only when every survivor is a modified asset with
  a kept body, and refuses one with an appended survivor;
- `restore_assets` on a copy brings every surviving asset back to its pristine SHA-256 and stored
  chunks, leaves the update's own asset alone, and refuses a record whose check token changed;
- the Android bridge restores what it can, refuses with `UPDATE_MIXED` naming only the rest, Re-download
  plans only those, and Remove translation writes the restored packages;
- with --apk, `build_snapshot` over the whole layer restores, builds, passes the text signal, and its new
  delta points at the restored packages as pristine.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.append(str(ROOT / "resources" / "runtime"))
import pristine_delta  # noqa: E402

PRISTINE = ROOT / "dist" / "HOK ACE Patcher Data" / "pristine" / "20261022-1.7.0.1" / "game" / "WXQ_Data" / \
    "Package" / "builtin"
STAGED = Path(r"D:\scratch\hok-1.7.0.1\out5-catalog")
# The packages the r815437 update left mixed on the phone (spec, Evidence). 10 and 21 hold an appended
# asset this patcher added (21 nothing else), so restore cannot take them.
MIXED = ["10", "15", "19", "20", "21"]
RESTORABLE = ["15", "19", "20"]
REFUSED = ["10", "21"]


def merge_chinese_asset(package_dir: Path, recorded: dict) -> str:
    """Rewrite one asset this patcher never changed, one byte shorter, as an update's merge would.

    The raw length changes, so the index differs from both sides of the delta too.
    """
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
        written, _ = write_assets(package_dir, {file_hash: raw[:-2] + bytes([raw[-2] ^ 1])})
        if written:
            return name
    raise RuntimeError(f"{package_dir.name}: no asset to merge into")


class Checks:
    def __init__(self, pristine: Path, staged: Path, work: Path):
        self.pristine, self.staged, self.work = pristine, staged, work
        self.failures: list[str] = []

    def expect(self, name: str, condition: bool, detail: str) -> None:
        print(f"{'PASS' if condition else 'FAIL'}  {name}: {detail}")
        if not condition:
            self.failures.append(name)

    def setup(self) -> None:
        if self.work.exists():
            shutil.rmtree(self.work)
        self.work.mkdir(parents=True)
        start = time.perf_counter()
        self.delta = pristine_delta.make(self.pristine, self.staged, info={"check": "restore"}, fingerprint=True)
        self.encoded = pristine_delta.encode(self.delta)
        print(f"delta: {len(self.delta.files)} files, {len(self.encoded):,} bytes encoded, ranges "
              f"{self.delta.range_bytes:,}, kept asset bodies {self.delta.kept_body_bytes:,} "
              f"({time.perf_counter() - start:.1f} s)")

    def check_delta(self) -> None:
        from asset_fingerprints import _stored

        modified = {package: sorted(name for name, (before, _) in assets.items() if before is not None)
                    for package, assets in self.delta.assets.items()}
        kept = {package: sorted(bodies) for package, bodies in self.delta.bodies.items() if bodies}
        self.expect("bodies kept for exactly the modified assets",
                    kept == {package: names for package, names in modified.items() if names},
                    f"{ {package: len(names) for package, names in kept.items()} }")
        package = "20"
        name = next(iter(self.delta.bodies[package]))
        body = self.delta.bodies[package][name]
        # `_stored` is the fingerprint's own reading: (compression, ((chunk id, raw size, payload SHA-256), ...)).
        expected = [(raw, digest) for _, raw, digest in _stored(self.pristine / package)[name][1]]
        self.expect("a kept body is the pristine stored chunks",
                    [(raw, hashlib.sha256(payload).hexdigest()) for raw, payload in body.chunks] == expected,
                    f"{package}/{name}: {len(body.chunks)} chunk(s), record {len(body.record)} B")
        decoded = pristine_delta.decode(self.encoded)
        self.expect("bodies survive the file format", decoded == self.delta,
                    f"{len(self.encoded):,} bytes")
        legacy = pristine_delta.Delta(self.delta.files, self.delta.info, self.delta.assets)
        data = pristine_delta.encode(legacy)
        self.expect("a delta without bodies reads as before",
                    pristine_delta.decode(data) == legacy and b"asset_bodies" not in data,
                    f"{len(data):,} bytes")
        # A reader from before asset restore: one zlib.decompress of everything after the header line.
        line_end = self.encoded.find(b"\n", len(pristine_delta.MAGIC))
        header = json.loads(self.encoded[len(pristine_delta.MAGIC):line_end])
        body = zlib.decompress(self.encoded[line_end + 1:])
        self.expect("an older reader still reads the ranges", len(body) == header["body_bytes"]
                    and hashlib.sha256(body).hexdigest() == header["body_sha256"], f"{len(body):,} bytes")

    def make_mixed(self, layer: Path, packages: list[str]) -> dict[str, str]:
        """<layer> as the phone after the install, with each of <packages> rewritten by a faked update."""
        merged = {}
        for name in pristine_delta.package_files(self.staged):
            package = name.split("/")[0]
            (layer / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.staged / name, layer / name)
        for package in packages:
            merged[package] = merge_chinese_asset(layer / package, self.delta.assets[package])
        return merged

    def check_accept(self) -> None:
        layer = self.work / "mixed"
        self.merged = self.make_mixed(layer, MIXED)
        self.mixed = layer
        report = pristine_delta.rebuild(layer, self.delta, self.work / "rebuilt")
        accepted, restorable, refused = pristine_delta.accept_replaced(layer, self.delta, report)
        self.expect("modified survivors with kept bodies are restorable",
                    sorted(restorable, key=int) == RESTORABLE and not accepted,
                    f"restorable {sorted(restorable, key=int)}")
        self.expect("an appended survivor refuses", sorted(refused, key=int) == REFUSED and all(
            "added by the patcher" in reason for reason in refused.values()), f"refused {refused}")
        legacy = pristine_delta.Delta(self.delta.files, self.delta.info, self.delta.assets)
        _, restorable, refused = pristine_delta.accept_replaced(layer, legacy, report)
        self.expect("a delta without bodies refuses them all", not restorable and sorted(refused, key=int) == MIXED,
                    f"refused {sorted(refused, key=int)}")

    def check_restore(self) -> None:
        from asset_fingerprints import _stored, package_assets

        for package in RESTORABLE:
            copy = self.work / "restore" / package
            shutil.copytree(self.mixed / package, copy)
            recorded, bodies = self.delta.assets[package], self.delta.bodies[package]
            before = _stored(copy)
            start = time.perf_counter()
            restored = pristine_delta.restore_assets(copy, recorded, bodies)
            seconds = time.perf_counter() - start
            pristine = _stored(self.pristine / package)
            after = _stored(copy)
            sha = package_assets(copy, set(recorded) | {self.merged[package]})
            back = all(sha[name] == recorded[name][0] for name in restored)
            # Stored chunks compared by digest, through the fingerprint's own reading (chunk ids included).
            chunks = all(after[name] == pristine[name] for name in restored)
            untouched = all(after[name] == stored for name, stored in before.items() if name not in restored)
            grown = sum(path.stat().st_size for path in copy.iterdir()) - sum(
                path.stat().st_size for path in (self.mixed / package).iterdir())
            self.expect(f"restore package {package}",
                        sorted(restored) == sorted(recorded) and back and chunks and untouched,
                        f"{len(restored)} of {len(recorded)} assets back to pristine SHA-256 {back}, stored "
                        f"chunks {chunks}, every other asset untouched {untouched} (the update's "
                        f"{self.merged[package]} too), +{grown:,} B, {seconds:.1f} s")
            again = pristine_delta.restore_assets(copy, recorded, bodies)
            self.expect(f"restore package {package} again", again == [], "nothing left to restore")

        copy = self.work / "restore-token" / "20"
        shutil.copytree(self.mixed / "20", copy)
        from wxq_patch.qtsvfs import QtsPackage

        name = next(iter(self.delta.assets["20"]))
        entry = QtsPackage(copy).entries[int(name, 16)]
        index = bytearray((copy / "20.db").read_bytes())
        index[entry.entry_offset + pristine_delta.TOKEN_START] ^= 1
        (copy / "20.db").write_bytes(bytes(index))
        try:
            pristine_delta.restore_assets(copy, self.delta.assets["20"], self.delta.bodies["20"])
            self.expect("a changed check token refuses", False, "restored")
        except pristine_delta.DeltaError as error:
            self.expect("a changed check token refuses", "check token" in str(error), str(error))

    def session(self, name: str, layer: Path) -> Path:
        """An Android session whose snapshot holds <layer>'s packages (hard links), with its manifest."""
        root = self.work / "android" / name
        snapshot = root / "snapshot"
        files = {}
        for path in sorted(layer.rglob("*")):
            if path.is_file():
                target = snapshot / "packages" / path.relative_to(layer)
                target.parent.mkdir(parents=True, exist_ok=True)
                os.link(path, target)
                files[f"packages/{path.relative_to(layer).as_posix()}"] = {
                    "bytes": path.stat().st_size, "sha256": pristine_delta.sha256_file(path)}
        (snapshot / "Watchdog").mkdir()
        (snapshot / "manifest.json").write_text(json.dumps({"schema": 1, "files": files, "directories": []}),
                                                encoding="utf-8")
        return root

    def check_android(self) -> None:
        sys.path.insert(0, str(ROOT / "android" / "app" / "src" / "main" / "python"))
        import android_bridge as bridge
        from asset_fingerprints import package_assets

        engine = self.work / "engine"
        engine.mkdir()
        for name in ("runtime", "tools"):
            target = ROOT / ("resources/runtime" if name == "runtime" else "tools")
            subprocess.run(["cmd", "/c", "mklink", "/J", str(engine / name), str(target)], check=True,
                           capture_output=True)
        keep = self.work / "keep"
        keep.mkdir()
        (keep / pristine_delta.DELTA_NAME).write_bytes(self.encoded)
        pristine_delta.record_staged_hashes(keep / pristine_delta.STAGED_HASHES_NAME, self.delta.staged_hashes)

        # Every mixed package: restore takes 15, 19 and 20; 10 and 21 are refused and only they re-download.
        mixed = self.session("mixed", self.mixed)
        manifest = json.loads((mixed / "snapshot" / "manifest.json").read_text(encoding="utf-8"))
        try:
            bridge._restore_pristine(mixed, keep, manifest)
            self.expect("refusal names only what restore cannot take", False, "not refused")
        except bridge.PatchError as error:
            named = str(error).split(". ")[0]
            self.expect("refusal names only what restore cannot take",
                        named == f"{bridge.UPDATE_MIXED}: package 10, 21", named)
        plan_session = self.session("plan", self.mixed)
        start = time.perf_counter()
        plan = json.loads(bridge.plan_redownload(str(engine), str(plan_session), str(keep)))
        self.expect("Re-download plans only those", sorted(plan["packages"], key=int) == REFUSED
                    and {name.split("/")[0] for name in plan["redownload"]} == set(REFUSED)
                    and not (plan_session / bridge.RESTORE_TRIAL).exists(),
                    f"{plan['redownload']} ({time.perf_counter() - start:.1f} s)")

        # Only restorable packages mixed: the pristine copy takes them, and Remove writes them.
        layer = self.work / "restorable"
        for name in pristine_delta.package_files(self.mixed):
            source = self.mixed / name if name.split("/")[0] in RESTORABLE else self.staged / name
            (layer / name).parent.mkdir(parents=True, exist_ok=True)
            os.link(source, layer / name)
        restorable = self.session("restorable", layer)
        manifest = json.loads((restorable / "snapshot" / "manifest.json").read_text(encoding="utf-8"))
        reserved = bridge._copy_bytes(self.delta, manifest)
        start = time.perf_counter()
        restored = bridge._restore_pristine(restorable, keep, manifest)
        seconds = time.perf_counter() - start
        copy = restorable / bridge.PRISTINE_COPY
        at_hashes = all((copy / name).is_file() and pristine_delta.sha256_file(copy / name) == digest
                        for name, digest in restored["sha256"].items())
        back = all(package_assets(copy / package, set(self.delta.assets[package])) == {
            name: before for name, (before, _) in self.delta.assets[package].items()} for package in RESTORABLE)
        used = sum(path.stat().st_size for path in copy.rglob("*") if path.is_file())
        self.expect("the pristine copy takes the restored packages",
                    sorted(restored["assets_restored"], key=int) == RESTORABLE and at_hashes and back
                    and used <= reserved,
                    f"restored {restored['assets_restored']}, copy at its hashes {at_hashes}, assets pristine "
                    f"{back}, copy {used:,} B of {reserved:,} reserved, {seconds:.1f} s")
        self.expect("a mixed-only session plans no Re-download",
                    bridge._mixed_packages(self.session("restorable-plan", layer), keep, manifest) == {}, "{}")

        removal = self.session("remove", layer)
        summary = json.loads(bridge.build_removal(str(engine), str(removal), str(keep)))
        output = removal / "out"
        written = {name for name in summary["removed"]}
        expected = {name for names in restored["assets_restored"].values() for name in names}
        phone = self.work / "after-remove"  # the phone once the apply wrote out/ over the snapshot
        for path in (removal / "snapshot" / "packages").rglob("*"):
            if path.is_file():
                name = path.relative_to(removal / "snapshot" / "packages")
                (phone / name).parent.mkdir(parents=True, exist_ok=True)
                os.link(output / name if (output / name).is_file() else path, phone / name)
        back = all(package_assets(phone / package, set(self.delta.assets[package])) == {
            name: before for name, (before, _) in self.delta.assets[package].items()} for package in RESTORABLE)
        self.expect("Remove writes the restored packages",
                    expected <= written and summary["pristine"]["assets_restored"] == RESTORABLE and back,
                    f"wrote {sorted(written)}")

        # A build whose text signal failed over restored packages leaves them to Re-download.
        marker = keep / bridge.RESTORE_REFUSED_NAME
        marker.write_text(json.dumps({"packages": ["19"]}), encoding="utf-8")
        refused = bridge._mixed_packages(self.session("restore-refused", layer), keep, manifest)
        marker.unlink()
        self.expect("a package whose restored build failed goes to Re-download", sorted(refused) == ["19"],
                    f"{refused}")
        self.engine, self.keep, self.layer = engine, keep, layer

    def check_build(self, apk: Path) -> None:
        """The whole layer with the restorable packages mixed: build_snapshot restores, builds, and the
        text signal passes; the new delta points at the restored packages as pristine."""
        import android_bridge as bridge

        for name in ("catalog", "catalog_id", "sprites", "ui", "fonts", "key"):
            if (ROOT / "resources" / name).is_dir() and not (self.engine / name).exists():
                subprocess.run(["cmd", "/c", "mklink", "/J", str(self.engine / name), str(ROOT / "resources" / name)],
                               check=True, capture_output=True)
        layer = self.work / "whole"
        for path in self.pristine.rglob("*"):
            if path.is_file():
                name = path.relative_to(self.pristine)
                source = self.layer / name if (self.layer / name).is_file() else path
                (layer / name).parent.mkdir(parents=True, exist_ok=True)
                os.link(source, layer / name)
        session = self.session("build", layer)
        with apk.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        start = time.perf_counter()
        try:
            summary = json.loads(bridge.build_snapshot(str(self.engine), str(session), str(apk), digest, "en",
                                                       str(self.keep)))
        except bridge.PatchError as error:
            self.expect("build over restored packages", False, str(error)[:300])
            return
        delta = pristine_delta.read(session / bridge.SESSION_DELTA)
        copy = session / bridge.PRISTINE_COPY
        points = all(delta.entry(name) is None or delta.entry(name).pristine_sha256 == pristine_delta.sha256_file(
            copy / name) for package in RESTORABLE for name in pristine_delta.package_files(copy)
            if name.startswith(f"{package}/"))
        self.expect("build over restored packages",
                    summary["pristine"]["assets_restored"] == RESTORABLE
                    and pristine_delta.text_not_pristine(summary) is None and points,
                    f"text signal {pristine_delta.text_not_pristine(summary) or 'pristine'}, new delta points at "
                    f"the restored copy {points}, kept bodies {delta.kept_body_bytes:,} B, "
                    f"{time.perf_counter() - start:.0f} s")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pristine", type=Path, default=PRISTINE)
    parser.add_argument("--staged", type=Path, default=STAGED)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--apk", type=Path, help="the installed.apk matching --pristine: also run a whole build")
    args = parser.parse_args()
    checks = Checks(args.pristine, args.staged, args.work)
    checks.setup()
    checks.check_delta()
    checks.check_accept()
    checks.check_restore()
    checks.check_android()
    if args.apk:
        checks.check_build(args.apk)
    print(f"\n{'FAILED: ' + ', '.join(checks.failures) if checks.failures else 'all checks passed'}")
    return 1 if checks.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
