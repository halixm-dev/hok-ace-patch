"""Check the pristine delta: synthetic cases always, and the real round trip and switch on request.

    .venv\\Scripts\\python.exe tools\\research\\check_pristine_delta.py
    .venv\\Scripts\\python.exe tools\\research\\check_pristine_delta.py --game <pristine game dir> ^
        --apk <path>\\installed.apk --work <scratch dir on a drive with ~15 GB free>

The synthetic cases need nothing. With `--game` (a pristine layer, `<dir>/WXQ_Data/Package/builtin`
inside it) it also builds English and Indonesian from that layer and checks that
- `rebuild` over each staged output reproduces every pristine SHA-256, and reports the delta sizes;
- English, then `rebuild`, then Indonesian stages byte-identical files to Indonesian from pristine, and
  the same for Indonesian then English and English then English;
- a named file one byte different, truncated or missing is reported, never rebuilt;
- each build from pristine passes the text signal (`text_not_pristine`), and a build over an
  English-translated layer fails it in both languages.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import pristine_delta  # noqa: E402
from pristine_delta import ALREADY_PRISTINE, CHANGED, MISSING, REBUILT, DeltaError  # noqa: E402


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Synthetic(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="pristine-delta-"))
        self.pristine_dir, self.staged_dir = self.root / "pristine", self.root / "staged"
        base = bytes(range(256)) * 4096  # 1 MiB
        self.pristine = {
            "1/1_0.db": base,
            "1/1.db": base[:5000],
            "15/15_0.db": base * 2,
            "7/7.db": base[:3000],  # longer than its staged copy
        }
        staged_one = bytearray(base)
        staged_one[10:20] = b"x" * 10           # two writes 200 bytes apart: one range
        staged_one[220:230] = b"y" * 10
        staged_one[700000:700001] = b"z"        # far away: its own range
        staged_one += b"appended" * 1000
        self.staged = {
            "1/1_0.db": bytes(staged_one),
            "1/1.db": base[:5000],              # unchanged but staged
            "15/15_0.db": base * 2 + b"tail",   # appended only
            "7/7.db": base[:1000] + b"q" * 500,  # shorter, and changed
            "9/9_0.db": b"created by the patch",
        }
        for name, data in self.pristine.items():
            _write(self.pristine_dir / name, data)
        for name, data in self.staged.items():
            _write(self.staged_dir / name, data)
        _write(self.staged_dir / "device_patch_summary.json", b"{}")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _delta(self):
        return pristine_delta.make(self.pristine_dir, self.staged_dir, info={"language": "en"})

    def test_ranges_follow_the_measured_parameters(self):
        entry = self._delta().entry("1/1_0.db")
        self.assertEqual([(offset, len(data)) for offset, data in entry.ranges], [(0, 256), (699968, 64)])
        self.assertEqual(entry.ranges[0][1], self.pristine["1/1_0.db"][:256])
        self.assertEqual(self._delta().entry("15/15_0.db").ranges, ())
        self.assertEqual(self._delta().entry("1/1.db").ranges, ())

    def test_created_file_records_no_pristine(self):
        entry = self._delta().entry("9/9_0.db")
        self.assertTrue(entry.created)
        self.assertEqual((entry.pristine_size, entry.staged_sha256), (0, _sha(self.staged["9/9_0.db"])))

    def test_round_trip_through_the_file_format(self):
        delta = self._delta()
        path = self.root / "keep" / "delta.bin"
        pristine_delta.write(delta, path)
        self.assertEqual(pristine_delta.read(path), delta)
        self.assertFalse(path.with_name("delta.bin.partial").exists())

    def test_rebuild_into_another_directory(self):
        delta = self._delta()
        out = self.root / "out"
        report = pristine_delta.rebuild(self.staged_dir, delta, out)
        self.assertEqual(sorted(report.rebuilt), ["1/1_0.db", "15/15_0.db", "7/7.db", "9/9_0.db"])
        self.assertEqual(report.pristine, ["1/1.db"])  # staged unchanged
        self.assertTrue(report.complete)
        for name, data in self.pristine.items():
            self.assertEqual((out / name).read_bytes(), data, name)
        self.assertFalse((out / "9/9_0.db").exists())

    def test_rebuild_in_place_and_again(self):
        delta = self._delta()
        layer = self.root / "layer"
        shutil.copytree(self.staged_dir, layer)
        pristine_delta.rebuild(layer, delta, layer)
        for name, data in self.pristine.items():
            self.assertEqual((layer / name).read_bytes(), data, name)
        again = pristine_delta.rebuild(layer, delta, layer)  # an already pristine layer
        self.assertEqual(sorted(again.pristine), sorted(self.staged))
        self.assertEqual(again.rebuilt, [])

    def test_refusals(self):
        delta = self._delta()
        layer = self.root / "layer"
        shutil.copytree(self.staged_dir, layer)
        changed = bytearray(self.staged["1/1_0.db"])
        changed[500000] ^= 1
        (layer / "1/1_0.db").write_bytes(bytes(changed))
        (layer / "15/15_0.db").write_bytes(self.staged["15/15_0.db"][:-1])
        (layer / "1/1.db").unlink()
        before = {name: (layer / name).read_bytes() for name in ("1/1_0.db", "15/15_0.db")}
        report = pristine_delta.rebuild(layer, delta, layer)
        self.assertEqual(report.unmatched, {"1/1_0.db": CHANGED, "15/15_0.db": CHANGED, "1/1.db": MISSING})
        self.assertEqual(sorted(report.rebuilt), ["7/7.db", "9/9_0.db"])
        self.assertEqual(report.pristine, [])
        for name, data in before.items():
            self.assertEqual((layer / name).read_bytes(), data, f"{name} was touched")

    def test_fallback_covers_an_interrupted_install(self):
        old = self._delta()
        newer = dict(self.staged, **{"1/1_0.db": self.staged["1/1_0.db"][:-5] + b"other"})
        _write(self.root / "newer" / "1/1_0.db", newer["1/1_0.db"])
        pending = pristine_delta.make(self.pristine_dir, self.root / "newer")
        layer = self.root / "layer"
        shutil.copytree(self.staged_dir, layer)
        (layer / "1/1_0.db").write_bytes(newer["1/1_0.db"])  # the new install wrote this file only
        self.assertEqual(pristine_delta.rebuild(layer, old, self.root / "a").unmatched, {"1/1_0.db": CHANGED})
        report = pristine_delta.rebuild(layer, old, layer, fallback=pending)
        self.assertTrue(report.complete)
        self.assertEqual((layer / "1/1_0.db").read_bytes(), self.pristine["1/1_0.db"])

    def test_staged_hashes_leave_out_unchanged_files(self):
        delta = self._delta()
        self.assertNotIn(_sha(self.pristine["1/1.db"]), delta.staged_hashes)
        self.assertIn(_sha(self.staged["1/1_0.db"]), delta.staged_hashes)
        self.assertEqual(pristine_delta.files_at(self.staged_dir, delta.staged_hashes),
                         ["1/1_0.db", "7/7.db", "9/9_0.db", "15/15_0.db"])
        self.assertEqual(pristine_delta.files_at(self.pristine_dir, delta.staged_hashes), [])

    def test_text_signal(self):
        def summary(tables, packages, skipped=()):
            return {"counts": {"tables": tables}, "text_skipped": list(skipped),
                    "packages": [{"mode": mode, "stage_report": {"replacement_count": count}}
                                 for mode, count in packages]}
        # 1.6.0.1 pristine: 83 tables in place, 11 relocated, of 94 read; textures do not count.
        self.assertIsNone(pristine_delta.text_not_pristine(
            summary(94, [("full", 83), ("relocated-text", 11), ("graphics", 302), ("added-from-apk", 293)])))
        self.assertIsNone(pristine_delta.text_not_pristine(
            summary(94, [("full", 80), ("relocated-text", 11)], [{"dropped_count": 3}])))
        self.assertIn("no Chinese", pristine_delta.text_not_pristine(summary(387, [("graphics", 3)])))
        self.assertIn("2 of the 387", pristine_delta.text_not_pristine(summary(387, [("relocated-text", 2)])))

    def test_classify(self):
        delta = self._delta()
        self.assertEqual(pristine_delta.classify(delta.entry("1/1_0.db"), self.staged_dir), REBUILT)
        self.assertEqual(pristine_delta.classify(delta.entry("1/1_0.db"), self.pristine_dir), ALREADY_PRISTINE)
        self.assertEqual(pristine_delta.classify(delta.entry("9/9_0.db"), self.pristine_dir), ALREADY_PRISTINE)

    def test_tampered_body_is_refused(self):
        data = bytearray(pristine_delta.encode(self._delta()))
        data[-3] ^= 0xFF
        with self.assertRaises(DeltaError):
            pristine_delta.decode(bytes(data))
        with self.assertRaises(DeltaError):
            pristine_delta.decode(b"something else")

    def test_rebuild_refuses_a_delta_that_does_not_reach_pristine(self):
        delta = self._delta()
        entry = delta.entry("1/1_0.db")
        broken = pristine_delta.FileEntry(entry.path, entry.pristine_size, entry.pristine_sha256,
                                          entry.staged_size, entry.staged_sha256, entry.ranges[:1])
        with self.assertRaises(DeltaError):
            pristine_delta.rebuild(self.staged_dir, pristine_delta.Delta((broken,)), self.root / "out")

    def test_staged_hash_record_accumulates(self):
        path = self.root / "pristine" / "staged-hashes.json"
        self.assertEqual(pristine_delta.load_staged_hashes(path), set())
        pristine_delta.record_staged_hashes(path, ["a", "b"])
        pristine_delta.record_staged_hashes(path, ["b", "c"])
        self.assertEqual(pristine_delta.load_staged_hashes(path), {"a", "b", "c"})


# ---------- real data ----------

def _build(game: Path, language: str, apk: Path, work: Path, out: Path) -> None:
    sys.path.append(str(ROOT / "resources" / "runtime"))
    import languages
    from build_device_patch import build_patch

    catalog = languages.catalog_dir(ROOT / "resources", language)
    with (work.parent / f"{out.name}.log").open("w", encoding="utf-8") as log:
        build_patch(game, catalog, work, out, apk=apk, builder_dir=None,
                    log=lambda line: print(line, file=log, flush=True))


def _layer(pristine: Path, staged: Path, target: Path) -> None:
    """A full layer: <pristine>'s files hard-linked, with <staged>'s files copied over them."""
    for path in pristine.rglob("*"):
        if path.is_file():
            destination = target / path.relative_to(pristine)
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.link(path, destination)
    for name in pristine_delta.package_files(staged):
        (target / name).unlink(missing_ok=True)
        shutil.copyfile(staged / name, target / name)


def _hashes(staged: Path) -> dict[str, str]:
    return {name: pristine_delta.sha256_file(staged / name) for name in pristine_delta.package_files(staged)}


def real(game: Path, apk: Path, work: Path) -> int:
    builtin = game / "WXQ_Data" / "Package" / "builtin"
    pristine_hashes = {}
    results: dict = {"deltas": {}, "switches": {}}
    failures = 0
    staged = {}
    for language in ("en", "id"):
        out = work / f"from-pristine-{language}"
        if not (out / "device_patch_summary.json").is_file():
            shutil.rmtree(out, ignore_errors=True)
            _build(game, language, apk, work / f"work-{language}", out)
        staged[language] = out
        summary = json.loads((out / "device_patch_summary.json").read_text(encoding="utf-8"))
        reason = pristine_delta.text_not_pristine(summary)
        print(f"{language} from pristine: text signal {'FAILS: ' + reason if reason else 'reads pristine'}")
        failures += reason is not None
        delta = pristine_delta.make(builtin, out, info={"language": language})
        encoded = pristine_delta.encode(delta)
        report = pristine_delta.rebuild(out, delta, work / f"rebuilt-{language}")
        for name in report.rebuilt:
            pristine_hashes[name] = pristine_delta.sha256_file(builtin / name)
            if pristine_delta.sha256_file(work / f"rebuilt-{language}" / name) != pristine_hashes[name]:
                failures += 1
                print(f"FAIL {language}: {name} does not round-trip")
        shutil.rmtree(work / f"rebuilt-{language}")
        results["deltas"][language] = {"files": len(delta.files), "rebuilt": len(report.rebuilt),
                                       "raw_bytes": delta.range_bytes, "encoded_bytes": len(encoded)}
        print(f"{language}: {len(report.rebuilt)} files rebuilt, {len(report.pristine)} staged unchanged, of "
              f"{len(delta.files)}; delta "
              f"{len(encoded) / 1e6:.2f} MB encoded ({delta.range_bytes / 1e6:.2f} MB raw)")
        if len(report.rebuilt) + len(report.pristine) != len(delta.files):
            failures += 1

    for first, second in (("en", "id"), ("id", "en"), ("en", "en")):
        name = f"{first}-then-{second}"
        layer_game = work / name / "game"
        shutil.rmtree(work / name, ignore_errors=True)
        layer = layer_game / "WXQ_Data" / "Package" / "builtin"
        _layer(builtin, staged[first], layer)
        delta = pristine_delta.decode(pristine_delta.encode(pristine_delta.make(builtin, staged[first])))
        report = pristine_delta.rebuild(layer, delta, layer)
        out = work / name / "staged"
        _build(layer_game, second, apk, work / name / "work", out)
        same = _hashes(out) == _hashes(staged[second])
        reason = pristine_delta.text_not_pristine(
            json.loads((out / "device_patch_summary.json").read_text(encoding="utf-8")))
        if reason:
            print(f"{name}: the rebuilt layer does not read as pristine: {reason}")
            failures += 1
        results["switches"][name] = {"rebuilt": len(report.rebuilt), "identical": same}
        print(f"{name}: rebuilt {len(report.rebuilt)} files; staged output "
              f"{'byte-identical to' if same else 'DIFFERS from'} {second} from pristine")
        failures += not same
        shutil.rmtree(work / name)

    # Refusals over a real staged layer: one byte different, truncated, missing.
    delta = pristine_delta.make(builtin, staged["en"])
    layer = work / "refusals"
    shutil.rmtree(layer, ignore_errors=True)
    shutil.copytree(staged["en"], layer)
    names = [entry.path for entry in delta.files]
    with (layer / names[0]).open("r+b") as stream:
        stream.seek(100)
        byte = stream.read(1)
        stream.seek(100)
        stream.write(bytes([byte[0] ^ 1]))
    with (layer / names[1]).open("r+b") as stream:
        stream.truncate(delta.entry(names[1]).staged_size - 1)
    (layer / names[2]).unlink()
    report = pristine_delta.rebuild(layer, delta, layer)
    expected = {names[0]: CHANGED, names[1]: CHANGED, names[2]: MISSING}
    refused = report.unmatched == expected
    print(f"refusals: {report.unmatched} {'as expected' if refused else 'UNEXPECTED'}")
    failures += not refused
    shutil.rmtree(layer)
    results["refusals"] = refused

    # A layer translated with no delta behind it (another patcher's, or an older version's) must fail
    # the text signal, in either language.
    patched = work / "patched-en" / "game"
    shutil.rmtree(work / "patched-en", ignore_errors=True)
    _layer(builtin, staged["en"], patched / "WXQ_Data" / "Package" / "builtin")
    for language in ("en", "id"):
        out = work / "patched-en" / f"staged-{language}"
        _build(patched, language, apk, work / "patched-en" / f"work-{language}", out)
        reason = pristine_delta.text_not_pristine(
            json.loads((out / "device_patch_summary.json").read_text(encoding="utf-8")))
        print(f"{language} over an English layer: {reason or 'READ AS PRISTINE'}")
        results.setdefault("patched_layer", {})[language] = reason
        failures += reason is None
    shutil.rmtree(work / "patched-en")
    (work / "pristine-delta-check.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game", type=Path, help="a pristine game directory")
    parser.add_argument("--apk", type=Path, help="the cached installed.apk")
    parser.add_argument("--work", type=Path, help="scratch directory for the builds")
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Synthetic)
    if not unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful():
        return 1
    if args.game is None:
        return 0
    if args.apk is None or args.work is None:
        parser.error("--game needs --apk and --work")
    args.work.mkdir(parents=True, exist_ok=True)
    return real(args.game, args.apk, args.work)


if __name__ == "__main__":
    raise SystemExit(main())
