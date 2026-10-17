"""Check the Windows patcher's repatch paths offline, on synthetic layers with a stand-in for adb.

    .venv\\Scripts\\python.exe tools\\research\\check_windows_repatch.py

Covers `Patcher.pull_game_data`, `restore_pristine`, `check_first_delta`, `bootstrap_delta` and
`push_translation`:
a first install over pristine keeps a delta; the next run rebuilds the pristine layer from it; a changed
file, a translated layer with no delta, or a layer the text pass does not read as pristine is refused
before anything is written; a kept session bootstraps a first delta only when its backup was pristine;
and an install cut off part way still rebuilds. A pull with an earlier session pulls only the files
whose SHA-256 no copy in that session holds, and anything it cannot trust falls back to the full pull.
"""
from __future__ import annotations

import hashlib
import io
import json
import shutil
import sys
import tarfile
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app"))
import patcher_core  # noqa: E402
from patcher_core import LAYER, PENDING_DELTA, PULL_RECORD, PatchError, Patcher  # noqa: E402
import pristine_delta  # noqa: E402

PRISTINE = {"1/1_0.db": bytes(range(256)) * 512, "1/1.db": b"index" * 400, "15/15_0.db": b"texture" * 900}
ENGLISH = {"1/1_0.db": b"EN" * 100 + PRISTINE["1/1_0.db"][200:] + b"added", "15/15_0.db": PRISTINE["15/15_0.db"] + b"x"}
INDONESIAN = {"1/1_0.db": b"ID" * 300 + PRISTINE["1/1_0.db"][600:]}
PRISTINE_SUMMARY = {"counts": {"tables": 2}, "text_skipped": [], "language": "en",
                    "packages": [{"package_id": "1", "mode": "full", "stage_report": {"replacement_count": 2}}]}
PATCHED_SUMMARY = {"counts": {"tables": 2}, "text_skipped": [], "language": "en",
                   "packages": [{"package_id": "15", "mode": "graphics", "stage_report": {"replacement_count": 1}}]}


class Ui:
    def __init__(self):
        self.lines = []

    def log(self, line):
        self.lines.append(line)

    def set_step(self, key, state, detail=""):
        pass


class FakeAdb:
    """Records pushes and copies them into <phone>, the way `cp` into packages/<id>/ would.

    It also answers the pull: `1.info`, `sha256sum` over the layer and `tar` of the layer or of named
    files. <garble> replaces the hash listing, <truncate> cuts every partial tar short.
    """

    def __init__(self, phone: Path, fail_after: int | None = None, *, garble: str | None = None,
                 truncate: bool = False):
        self.phone, self.fail_after, self.pushed = phone, fail_after, []
        self.garble, self.truncate, self.tars = garble, truncate, []

    def shell(self, command, check=True):
        if command.endswith("packages/1/1.info") and (self.phone / "1/1.info").is_file():
            return (self.phone / "1/1.info").read_text()
        return ""

    def exec_out(self, command):
        assert "sha256sum" in command, command
        if self.garble is not None:
            return self.garble
        return "".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  ./{path.relative_to(self.phone).as_posix()}\n"
                       for path in sorted(self.phone.rglob("*")) if path.is_file())

    def exec_out_to_file(self, command, target):
        whole = command.endswith(" packages Watchdog")
        names = ([path.relative_to(self.phone).as_posix() for path in self.phone.rglob("*") if path.is_file()]
                 if whole else command.split(" -C files/QtsVFSCache/packages ", 1)[1].split())
        self.tars.append("whole" if whole else names)
        with tarfile.open(target, "w") as tar:
            for name in names:
                tar.add(self.phone / name, arcname=f"packages/{name}" if whole else name)
        if self.truncate and not whole:
            target.write_bytes(target.read_bytes()[:512])

    def run(self, *args, check=True):
        if args[0] == "push":
            if self.fail_after is not None and len(self.pushed) >= self.fail_after:
                raise PatchError("cable pulled")
            name = args[2].split("/hokace/", 1)[1]
            self.pushed.append(name)
            (self.phone / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(args[1], self.phone / name)
        return ""


def _write(folder: Path, files: dict[str, bytes]) -> None:
    for name, data in files.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(data)


class Repatch(unittest.TestCase):
    def setUp(self):
        self.work = Path(tempfile.mkdtemp(prefix="windows-repatch-"))
        self.phone = self.work / "phone"
        _write(self.phone, PRISTINE)
        self.stamp = 0

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def session(self) -> Path:
        """Pull the phone into a new session, as `pull_game_data` does (backup tar plus layer copy)."""
        self.stamp += 1
        session = self.work / "sessions" / f"20261017-{self.stamp:06d}"
        shutil.copytree(self.phone, session / LAYER)
        with tarfile.open(session / "device-backup.tar", "w") as tar:
            for name in pristine_delta.package_files(self.phone):
                tar.add(self.phone / name, arcname=f"packages/{name}")
        return session

    def install(self, patcher: Patcher, session: Path, staged_files: dict, summary: dict,
                restored: list[str] | None) -> None:
        """What `run` does after the pull: build stand-in, first-delta check, push."""
        staged = session / "staged"
        _write(staged, {name: data for name, data in staged_files.items()})
        (staged / "device_patch_summary.json").write_text(json.dumps(summary), encoding="utf-8")
        if restored is None:
            patcher.check_first_delta(summary)
            restored = []
        patcher.push_translation(session, staged, restored)

    def patcher(self, fail_after=None) -> Patcher:
        patcher = Patcher(Ui(), self.work, "en")
        patcher.adb = FakeAdb(self.phone, fail_after)
        return patcher

    def phone_bytes(self):
        return {name: (self.phone / name).read_bytes() for name in pristine_delta.package_files(self.phone)}

    def test_first_install_then_switch_then_back(self):
        patcher = self.patcher()
        session = self.session()
        self.assertIsNone(patcher.restore_pristine(session))
        self.install(patcher, session, ENGLISH, PRISTINE_SUMMARY, None)
        self.assertTrue((self.work / "pristine" / "delta.bin").is_file())
        self.assertFalse((self.work / "pristine" / PENDING_DELTA).exists())
        self.assertEqual(self.phone_bytes(), {**PRISTINE, **ENGLISH})

        # Switch: the session layer is rebuilt to pristine before the build reads it.
        patcher = self.patcher()
        session = self.session()
        restored = patcher.restore_pristine(session)
        self.assertEqual(sorted(restored), ["1/1_0.db", "15/15_0.db"])
        self.assertEqual({name: (session / LAYER / name).read_bytes() for name in PRISTINE}, PRISTINE)
        self.assertIn("  rebuilt 2 files from the pristine delta", patcher.ui.lines)
        self.install(patcher, session, INDONESIAN, PRISTINE_SUMMARY, restored)
        # 15_0.db is not staged by this build, so its pristine copy goes back to the phone.
        self.assertEqual(self.phone_bytes(), {**PRISTINE, **INDONESIAN})

        patcher = self.patcher()
        session = self.session()
        restored = patcher.restore_pristine(session)
        self.assertEqual(restored, ["1/1_0.db"])
        self.install(patcher, session, ENGLISH, PRISTINE_SUMMARY, restored)
        self.assertEqual(self.phone_bytes(), {**PRISTINE, **ENGLISH})

    def test_changed_file_is_refused(self):
        patcher = self.patcher()
        session = self.session()
        patcher.restore_pristine(session)
        self.install(patcher, session, ENGLISH, PRISTINE_SUMMARY, None)
        (self.phone / "1/1_0.db").write_bytes(ENGLISH["1/1_0.db"][:-1])  # a repair or update
        with self.assertRaisesRegex(PatchError, "Clear the game's data"):
            self.patcher().restore_pristine(self.session())

    def test_cleared_data_with_a_newer_version_drops_the_stale_delta(self):
        patcher = self.patcher()
        session = self.session()
        patcher.restore_pristine(session)
        self.install(patcher, session, ENGLISH, PRISTINE_SUMMARY, None)
        newer = {name: data + b"v2" for name, data in PRISTINE.items()}  # cleared, then a newer download
        _write(self.phone, newer)
        patcher = self.patcher()
        session = self.session()
        self.assertIsNone(patcher.restore_pristine(session))
        self.assertTrue(any("no longer matches" in line for line in patcher.ui.lines))
        staged = {"1/1_0.db": b"EN" + newer["1/1_0.db"][2:]}
        self.install(patcher, session, staged, PRISTINE_SUMMARY, None)
        self.assertEqual(sorted(self.patcher().restore_pristine(self.session())), ["1/1_0.db"])

    def test_translated_layer_without_delta_is_refused(self):
        patcher = self.patcher()
        session = self.session()
        patcher.restore_pristine(session)
        self.install(patcher, session, ENGLISH, PRISTINE_SUMMARY, None)
        (self.work / "pristine" / "delta.bin").unlink()
        shutil.rmtree(self.work / "sessions")  # nothing to bootstrap from either
        with self.assertRaisesRegex(PatchError, "already translated"):
            self.patcher().restore_pristine(self.session())

    def test_other_patchers_layer_fails_the_text_signal(self):
        _write(self.phone, ENGLISH)  # translated by someone else: no hash this patcher recorded
        patcher = self.patcher()
        self.assertIsNone(patcher.restore_pristine(self.session()))
        with self.assertRaisesRegex(PatchError, "Android patcher"):
            patcher.check_first_delta(PATCHED_SUMMARY)
        self.assertEqual(self.phone_bytes(), {**PRISTINE, **ENGLISH})

    def test_bootstrap_from_a_kept_pristine_session(self):
        # An install made before deltas existed: a session with a pristine backup and its staged output.
        session = self.session()
        _write(session / "staged", ENGLISH)
        (session / "staged" / "device_patch_summary.json").write_text(json.dumps(PRISTINE_SUMMARY))
        _write(self.phone, ENGLISH)
        patcher = self.patcher()
        restored = patcher.restore_pristine(self.session())
        self.assertEqual(sorted(restored), ["1/1_0.db", "15/15_0.db"])
        self.assertTrue(any("made a pristine delta from the kept session" in line for line in patcher.ui.lines))

    def test_no_bootstrap_from_a_session_over_a_translated_layer(self):
        _write(self.phone, ENGLISH)
        session = self.session()  # its backup is already English
        _write(session / "staged", ENGLISH)
        (session / "staged" / "device_patch_summary.json").write_text(json.dumps(PATCHED_SUMMARY))
        patcher = self.patcher()
        self.assertIsNone(patcher.bootstrap_delta(self.session()))
        self.assertFalse((self.work / "pristine" / "delta.bin").exists())

    def test_install_cut_off_part_way_still_rebuilds(self):
        patcher = self.patcher()
        session = self.session()
        patcher.restore_pristine(session)
        self.install(patcher, session, ENGLISH, PRISTINE_SUMMARY, None)
        patcher = self.patcher(fail_after=0)
        session = self.session()
        restored = patcher.restore_pristine(session)
        newer = {"1/1_0.db": b"V2" * 50 + PRISTINE["1/1_0.db"][100:], "15/15_0.db": ENGLISH["15/15_0.db"] + b"y"}
        with self.assertRaisesRegex(PatchError, "cable pulled"):
            self.install(patcher, session, newer, PRISTINE_SUMMARY, restored)
        # Write the first file by hand, as if the cable came out after it.
        (self.phone / "1/1_0.db").write_bytes(newer["1/1_0.db"])
        self.assertTrue((self.work / "pristine" / PENDING_DELTA).is_file())
        session = self.session()
        self.assertEqual(sorted(self.patcher().restore_pristine(session)), ["1/1_0.db", "15/15_0.db"])
        self.assertEqual({name: (session / LAYER / name).read_bytes() for name in PRISTINE}, PRISTINE)

    def test_remove_translation_then_patch_again(self):
        patcher = self.patcher()
        session = self.session()
        patcher.restore_pristine(session)
        self.install(patcher, session, ENGLISH, PRISTINE_SUMMARY, None)
        remover = Patcher(Ui(), self.work, "en", remove=True)
        remover.adb = FakeAdb(self.phone)
        session = self.session()
        result = remover.write_back_pristine(session, remover.restore_pristine(session))
        self.assertEqual(sorted(result["removed"]), ["1/1_0.db", "15/15_0.db"])
        self.assertEqual(self.phone_bytes(), PRISTINE)
        self.assertFalse((self.work / "pristine" / "delta.bin").exists())
        self.assertFalse((self.work / "pristine" / PENDING_DELTA).exists())
        self.assertFalse(patcher_core.holds_delta(self.work))
        # Removing again has no record to remove from; a new patch run is a first install, which the
        # pristine signals accept and which a translated summary would refuse.
        session = self.session()
        with self.assertRaisesRegex(PatchError, "nothing to remove"):
            remover.write_back_pristine(session, remover.restore_pristine(session))
        patcher = self.patcher()
        session = self.session()
        self.assertIsNone(patcher.restore_pristine(session))
        with self.assertRaisesRegex(PatchError, "already translated"):
            patcher.check_first_delta(PATCHED_SUMMARY)
        self.install(patcher, session, INDONESIAN, PRISTINE_SUMMARY, None)
        self.assertEqual(self.phone_bytes(), {**PRISTINE, **INDONESIAN})
        self.assertEqual(sorted(self.patcher().restore_pristine(self.session())), sorted(INDONESIAN))

    def test_remove_without_a_record_is_refused(self):
        remover = Patcher(Ui(), self.work, "en", remove=True)
        remover.adb = FakeAdb(self.phone)
        session = self.session()
        with self.assertRaisesRegex(PatchError, "nothing to remove"):
            remover.write_back_pristine(session, remover.restore_pristine(session))

    def pull(self, adb: FakeAdb | None = None) -> tuple[Path, Patcher]:
        """The real `pull_game_data`, against the fake phone."""
        self.stamp += 1
        patcher = self.patcher()
        patcher.adb = adb or patcher.adb
        stamp = f"20261018-{self.stamp:06d}"
        with unittest.mock.patch.object(patcher_core, "datetime") as clock:
            clock.now.return_value.strftime.return_value = stamp
            session = patcher.pull_game_data()
        self.assertEqual(self.layer_bytes(session), self.all_phone_bytes())
        return session, patcher

    def all_phone_bytes(self):
        return {path.relative_to(self.phone).as_posix(): path.read_bytes()
                for path in self.phone.rglob("*") if path.is_file()}

    def layer_bytes(self, session: Path):
        layer = session / LAYER
        return {path.relative_to(layer).as_posix(): path.read_bytes() for path in layer.rglob("*") if path.is_file()}

    def record(self, session: Path) -> dict:
        return json.loads((session / PULL_RECORD).read_text(encoding="utf-8"))

    def test_pull_only_what_changed(self):
        _write(self.phone, {"1/1.info": b'{"version":"1.6.0.1","revision":"0"}'})
        session, patcher = self.pull()
        self.assertEqual(self.record(session)["mode"], "full")
        self.assertEqual(patcher.adb.tars, ["whole"])
        patcher.restore_pristine(session)
        self.install(patcher, session, ENGLISH, PRISTINE_SUMMARY, None)

        # The phone now holds the staged files and the session's layer is pristine: nothing to pull.
        session, patcher = self.pull()
        self.assertEqual(self.record(session)["mode"], "changed")
        self.assertEqual(self.record(session)["pulled_files"], 0)
        self.assertEqual(patcher.adb.tars, [])
        self.assertFalse((session / "device-backup.tar").exists())
        restored = patcher.restore_pristine(session)
        self.assertEqual(sorted(restored), ["1/1_0.db", "15/15_0.db"])
        self.install(patcher, session, ENGLISH, PRISTINE_SUMMARY, restored)

        # A data update changes one file and adds another: exactly those come over.
        _write(self.phone, {"1/1.db": b"index v2", "20/20_0.db": b"new package"})
        session, patcher = self.pull()
        self.assertEqual(patcher.adb.tars, [["1/1.db", "20/20_0.db"]])
        self.assertEqual(self.record(session)["pulled_files"], 2)

        # A file the phone no longer holds is not carried over from the earlier session.
        (self.phone / "20/20_0.db").unlink()
        self.pull()

    def test_partial_pull_falls_back_to_the_full_pull(self):
        _write(self.phone, {"1/1.info": b'{"version":"1.6.0.1","revision":"0"}'})
        self.pull()
        for version, (adb, reason) in enumerate([
                (FakeAdb(self.phone, garble="sha256sum: not found\n"), "did not read"),
                (FakeAdb(self.phone, garble=f"{'0' * 64}  ./../escape\n"), "did not read"),
                (FakeAdb(self.phone, truncate=True), "")]):
            # Each fallback becomes the next run's earlier session, so give each run a change to pull.
            _write(self.phone, {"1/1.db": b"index v%d" % version})
            session, patcher = self.pull(adb)
            self.assertEqual(self.record(session)["mode"], "full", reason)
            self.assertTrue(any("pulling everything" in line and reason in line for line in patcher.ui.lines))
            self.assertEqual(list(session.glob("pull-*.tar")), [])

    def test_partial_pull_batches_long_lists(self):
        _write(self.phone, {"1/1.info": b'{"version":"1.6.0.1","revision":"0"}'})
        self.pull()
        _write(self.phone, {f"{n}/{n}_0.db": str(n).encode() for n in range(1000, 1400)})
        session, patcher = self.pull()
        self.assertGreater(len(patcher.adb.tars), 1)
        self.assertTrue(all(len(" ".join(batch)) <= patcher_core.PULL_BATCH_CHARS for batch in patcher.adb.tars))
        self.assertEqual(self.record(session)["pulled_files"], 400)

    def test_holds_delta(self):
        self.assertFalse(patcher_core.holds_delta(self.work))
        patcher = self.patcher()
        session = self.session()
        patcher.restore_pristine(session)
        self.install(patcher, session, ENGLISH, PRISTINE_SUMMARY, None)
        self.assertTrue(patcher_core.holds_delta(self.work))


if __name__ == "__main__":
    unittest.main()
