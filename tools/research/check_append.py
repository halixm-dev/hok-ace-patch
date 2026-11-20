"""Check the append pass (`package_rebuild.add_prime_only`): synthetic cases always, a real layer on request.

    .venv\\Scripts\\python.exe tools\\research\\check_append.py
    .venv\\Scripts\\python.exe tools\\research\\check_append.py --game <game dir> --apk <installed.apk> [--package <id>]

The synthetic cases run the pass's own control flow over stand-in packages (no runtime package, no APK),
and hold it to what `AGENTS.md` asks of it:

1. a full B-tree leaf (`TreeFull`) goes into `append_skipped` and the run goes on to the next package;
   the staged copy it created for that package is removed, and one an earlier pass made is kept
2. a re-run over its own output offers nothing again: an asset the staged copy already holds is not
   appended twice, so no B-tree key is indexed twice
3. assets the encoder refused are reported as skipped beside the share that was written

`add_assets` itself (the encode, the B-tree link, the read-back through `QtsPackage`) is the real code in
the `--game` form, which runs the pass on one package of a dumped layer with its APK and asserts:

4. it adds at least one asset, and a second run over the same output adds none; the assets the encoder
   refused are offered again and reported again, since they still stay Chinese
5. every asset the device package already held reads back byte-identical from the staged copy

The dump is only read; the staged copy goes to a temporary folder. Nothing here is imported by the app
or by the pipeline.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.append(str(ROOT / "resources" / "runtime"))
import package_rebuild  # noqa: E402
import qts_insert  # noqa: E402
import qts_relocate  # noqa: E402
from qts_relocate import TreeFull  # noqa: E402
from wxq_patch import qtsvfs  # noqa: E402


class FakePackage:
    """What add_prime_only reads of a QtsPackage: its id, files and entry hashes."""

    def __init__(self, folder: Path, entries) -> None:
        self.package_id = folder.name
        self.index_path = folder / f"{folder.name}.db"
        self.shard_paths = [folder / f"{folder.name}_0.db"]
        self.entries = dict.fromkeys(entries)

    def build_slot_map(self) -> dict:
        return {file_hash: {0: None} for file_hash in self.entries}


class Transform:
    """Translates every hash it lists; the pass reads the four sets to know what is catalogued."""

    def __init__(self, hashes: set[int], textures: set[int] = frozenset()) -> None:
        self.tables, self.graphics, self.scripts, self.config = hashes - textures, set(textures), set(), set()

    def __call__(self, file_hash: int, raw: bytes) -> bytes:
        return b"english " + raw


class Synthetic(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.game, self.work, self.output = (self.folder / name for name in ("game", "work", "out"))
        self.builtin = self.game / "WXQ_Data" / "Package" / "builtin"
        self.device: dict[str, set[int]] = {}   # what each device package holds
        self.prime: dict[str, set[int]] = {}    # what each APK package holds
        self.calls: list[tuple[str, list[int]]] = []
        self.tree_full: set[str] = set()
        self.refuse: set[int] = set()
        saved = (package_rebuild.extract_prime, qtsvfs.QtsPackage, qts_insert.add_assets, qts_relocate.read_raw)
        self.addCleanup(self._restore, saved)
        package_rebuild.extract_prime = self._extract_prime
        qtsvfs.QtsPackage = self._package
        qts_insert.add_assets = self._add_assets
        qts_relocate.read_raw = lambda package, slots, file_hash: f"{file_hash:x}".encode()

    @staticmethod
    def _restore(saved) -> None:
        package_rebuild.extract_prime, qtsvfs.QtsPackage, qts_insert.add_assets, qts_relocate.read_raw = saved

    def add(self, package_id: str, device: set[int], prime: set[int]) -> None:
        folder = self.builtin / package_id
        folder.mkdir(parents=True)
        for name in (f"{package_id}.db", f"{package_id}_0.db"):
            (folder / name).write_bytes(b"device " + name.encode())
        self.device[package_id], self.prime[package_id] = set(device), set(prime)

    def _extract_prime(self, apk, package_ids, target: Path, index_only: bool = False) -> dict[str, Path]:
        found = {}
        for package_id in sorted(self.prime if package_ids is None else package_ids):
            folder = target / package_id
            folder.mkdir(parents=True, exist_ok=True)
            found[package_id] = folder
        return found

    def _package(self, folder) -> FakePackage:
        folder = Path(folder)
        if folder.parent == self.builtin:
            return FakePackage(folder, self.device[folder.name])
        if folder.parent == self.output:
            return FakePackage(folder, self.device[folder.name] | self._staged(folder))
        return FakePackage(folder, self.prime[folder.name])

    def _staged(self, folder: Path) -> set[int]:
        marker = folder / "appended.txt"
        return {int(line, 16) for line in marker.read_text().split()} if marker.exists() else set()

    def _add_assets(self, package_id, target: Path, assets, source, log, *, source_slots=None) -> list[str]:
        hashes = [asset["file_hash"] for asset in assets]
        self.calls.append((package_id, hashes))
        if package_id in self.tree_full:
            raise TreeFull(f"{package_id}_0.db: no free page pair for a split")
        written = [f"{file_hash:016X}" for file_hash in hashes if file_hash not in self.refuse]
        with (target / "appended.txt").open("a") as marker:
            marker.write("".join(f"{line}\n" for line in written))
        return written

    def run_pass(self, transform: Transform) -> tuple[list[dict], list[dict]]:
        lines: list[str] = []
        return package_rebuild.add_prime_only(self.game, self.folder / "installed.apk", transform,
                                              self.work, self.output, set(), lines.append)

    def test_tree_full_is_skipped_and_the_run_goes_on(self) -> None:
        self.add("10", {1}, {1, 2, 3})
        self.add("20", {5}, {5, 6})
        self.tree_full = {"10"}
        entries, skipped = self.run_pass(Transform({2, 3, 6}, textures={3}))
        self.assertEqual([entry["package_id"] for entry in entries], ["20"])
        self.assertEqual(len(skipped), 1)
        self.assertEqual((skipped[0]["package_id"], skipped[0]["assets"], skipped[0]["textures"]), ("10", 2, 1))
        self.assertIn("no free page pair", skipped[0]["reason"])
        self.assertFalse((self.output / "10").exists(), "the copy the pass created must not stay behind")

    def test_tree_full_keeps_a_staged_copy_an_earlier_pass_made(self) -> None:
        self.add("10", {1}, {1, 2})
        (self.output / "10").mkdir(parents=True)
        (self.output / "10" / "10_0.db").write_bytes(b"an earlier pass's text")
        self.tree_full = {"10"}
        entries, skipped = self.run_pass(Transform({2}))
        self.assertEqual((entries, [entry["package_id"] for entry in skipped]), ([], ["10"]))
        self.assertEqual((self.output / "10" / "10_0.db").read_bytes(), b"an earlier pass's text")

    def test_a_rerun_offers_nothing_already_staged(self) -> None:
        self.add("10", {1}, {1, 2, 3})
        transform = Transform({2, 3})
        entries, skipped = self.run_pass(transform)
        self.assertEqual((entries[0]["assets"], skipped), (2, []))
        again, skipped = self.run_pass(transform)
        self.assertEqual((again, skipped), ([], []))
        self.assertEqual(self.calls, [("10", [2, 3])], "a staged asset must not be appended a second time")

    def test_a_rerun_appends_only_what_is_still_missing(self) -> None:
        self.add("10", {1}, {1, 2, 3})
        self.run_pass(Transform({2}))
        entries, _ = self.run_pass(Transform({2, 3}))
        self.assertEqual(self.calls, [("10", [2]), ("10", [3])])
        self.assertEqual(entries[0]["assets"], 1)

    def test_refused_assets_are_reported_beside_the_written_share(self) -> None:
        self.add("10", {1}, {1, 2, 3, 4})
        self.refuse = {3, 4}
        entries, skipped = self.run_pass(Transform({2, 3, 4}, textures={4}))
        self.assertEqual(entries[0]["assets"], 1)
        self.assertEqual((skipped[0]["package_id"], skipped[0]["assets"], skipped[0]["textures"]), ("10", 2, 1))

    def test_a_rerun_reports_a_refused_asset_again(self) -> None:
        self.add("10", {1}, {1, 2, 3})
        self.refuse = {3}
        self.run_pass(Transform({2, 3}))
        entries, skipped = self.run_pass(Transform({2, 3}))
        self.assertEqual(entries, [])
        self.assertEqual((skipped[0]["assets"], skipped[0]["reason"]), (1, "no asset could be re-encoded"))
        self.assertTrue((self.output / "10").is_dir(), "the first run's copy holds its appends")

    def test_nothing_appended_when_every_asset_is_refused(self) -> None:
        self.add("10", {1}, {1, 2})
        self.refuse = {2}
        entries, skipped = self.run_pass(Transform({2}))
        self.assertEqual((entries, skipped[0]["reason"]), ([], "no asset could be re-encoded"))
        self.assertFalse((self.output / "10").exists())


def check_game(game: Path, apk: Path, package: str | None) -> int:
    """Run the real pass on one package of <game> twice; 0 when every property holds."""
    import json

    from qts_relocate import install_btree_slot_map, read_raw
    from engine_hooks import install as install_terminology
    from wxq_patch import adaptive
    from wxq_patch.qtsvfs import QtsPackage

    install_btree_slot_map()
    install_terminology()
    catalog_dir = ROOT / "resources" / "catalog"
    lines: list[str] = []
    transform = package_rebuild.make_transform(adaptive.load_catalog(catalog_dir), catalog_dir,
                                               lines.append, set())
    builtin = game / "WXQ_Data" / "Package" / "builtin"
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as temp:
        work, output = Path(temp) / "work", Path(temp) / "out"
        prime = package_rebuild.extract_prime(apk, None, work / "prime-index", index_only=True)
        ids = sorted(prime) if package is None else [package]
        for package_id in ids:
            skip = set(prime) - {package_id}
            entries, skipped = package_rebuild.add_prime_only(game, apk, transform, work, output, skip,
                                                              lines.append)
            if entries or skipped or package is not None:
                break
        else:
            print("no package of this layer has prime-only catalog content to append")
            return 1
        print("\n".join(lines[-3:]))
        added = sum(entry["assets"] for entry in entries)
        print(f"package {package_id}: {added} assets appended, {len(skipped)} skipped entries")
        if not added:
            failures.append(f"4. package {package_id}: the first run appended nothing")
        again, skipped_again = package_rebuild.add_prime_only(game, apk, transform, work, output,
                                                              set(prime) - {package_id}, lines.append)
        if again:
            failures.append(f"4. a second run appended again: {json.dumps(again)}")
        # What the encoder refused is offered again and still stays Chinese, so it is reported again.
        refused = sum(entry["assets"] for entry in skipped)
        if sum(entry["assets"] for entry in skipped_again) != refused:
            failures.append(f"4. a second run reports other skips than the first: {json.dumps(skipped_again)}")
        if (output / package_id).is_dir():
            device, staged = QtsPackage(builtin / package_id), QtsPackage(output / package_id)
            device_slots, staged_slots = device.build_slot_map(), staged.build_slot_map()
            changed = [f"{file_hash:016X}" for file_hash in device.entries
                       if read_raw(device, device_slots, file_hash) != read_raw(staged, staged_slots, file_hash)]
            print(f"package {package_id}: {len(device.entries) - len(changed)} of {len(device.entries)} "
                  "existing assets read back unchanged")
            if changed:
                failures.append(f"5. {len(changed)} existing assets changed: {', '.join(changed[:10])}")
    for failure in failures:
        print(f"FAIL {failure}")
    return 1 if failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--game", type=Path, help="a dumped game directory (holds WXQ_Data)")
    parser.add_argument("--apk", type=Path, help="the installed APK that layer was read with")
    parser.add_argument("--package", help="the package to append to; default: the first with content")
    args = parser.parse_args()
    if bool(args.game) != bool(args.apk):
        parser.error("--game and --apk go together")
    result = unittest.main(argv=[sys.argv[0]], exit=False, verbosity=1).result
    code = 0 if result.wasSuccessful() else 1
    if args.game:
        code |= check_game(args.game, args.apk, args.package)
    sys.exit(code)


if __name__ == "__main__":
    main()
