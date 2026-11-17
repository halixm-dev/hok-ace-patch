"""Measure the in-place staging drop loop, confirm retry proofs, and run its synthetic fault cases.

Python 3.12 only. Research tooling: nothing imports or bundles it. Authored in ticket 18 pass 1 and
not yet run. Three subcommands, from the project root:

    .venv\\Scripts\\python.exe tools\\research\\measure_staging_retries.py faults

        Synthetic fault cases for ``build_device_patch._stage_package`` with a fake package and a
        fake stager (no runtime, game dump or device): baseline parity with metrics on, a confirmed
        proof, one observation only, conflicting observations, a different failing asset, a changed
        chunk layout, changed translation bytes, an unknown error, fit-only mode, an existing output
        copy and a proof naming a table the plan lacks.

    .venv\\Scripts\\python.exe tools\\research\\measure_staging_retries.py measure ^
        --runtime resources\\runtime --game <game-dir> --catalog resources\\catalog ^
        --work <new-work-dir> --output <new-out-dir> --apk <installed.apk> ^
        --metrics <file.json> [--proofs <confirmed.json>] [--fit-only] [--no-keys]

        Runs ``build_patch`` once with ``staging_metrics`` and, unless ``--no-keys``, a producer key
        (``run_artifacts.windows_producer_identity``) so every loop's exact-input key and observed
        proof are recorded. Each real ``stage_unity_package`` call is also observed from outside the
        compiled runtime with a ``sys.addaudithook`` scoped to the call: ``shutil.copyfile`` calls
        and source bytes, ``shutil.copytree``/``rmtree``, writable opens, renames and removes, plus
        the files/bytes of the output package copy after it. ``--no-keys`` skips the key hashing
        (it reads every index/shard/replacement in full) for a timing control. ``--work``,
        ``--output`` and ``--metrics`` must be new and outside the game directory and the APK's
        directory; keep them outside the repo too, or the producer key changes between runs.

    .venv\\Scripts\\python.exe tools\\research\\measure_staging_retries.py confirm ^
        <metrics-1.json> <metrics-2.json> [...] --out <confirmed.json>

        Merges the proofs two or more baseline ``measure`` runs observed under one producer key
        (``build_device_patch.confirm_retry_proofs``). A conflicting group is left out and listed.

A confirmed proof is the only way ``build_patch`` pre-routes a table, and no shipped caller passes
one. Whether to wire it anywhere is a pass-2 decision from these measurements and from staged-output
parity against the baseline; no speed gain is claimed here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

PRODUCER = "a" * 64


# --- fake package and stager for the fault cases ------------------------------------------------


@dataclass(frozen=True)
class _Slot:
    slot_offset: int
    slot_size: int


class _FakePackage:
    """The attributes `_stage_package` and `_RetryProofs` read from a QtsPackage."""

    def __init__(self, game: Path, package_id: str, hashes: list[int]):
        self.package_id = package_id
        self.package_dir = game / "WXQ_Data" / "Package" / "builtin" / package_id
        self.package_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.package_dir / f"{package_id}.idx"
        self.shard_paths = [self.package_dir / f"{package_id}_0.db"]
        self.index_path.write_bytes(b"index:" + b",".join(f"{h:016X}".encode() for h in hashes))
        self.shard_paths[0].write_bytes(b"shard bytes " * 64)
        self.slots = {h: {0: _Slot(1000 + i * 100, 100)} for i, h in enumerate(hashes)}

    def build_slot_map(self) -> dict:
        return self.slots


def stage_unity_package(directory: Path, target: Path, rules: dict, package: _FakePackage) -> dict:
    """Fake stager; the name matters: `attribute_failure` reads `file_hash` from this frame.

    It rewrites its whole output copy each call, then fails on the first rule it meets: ``unknown``
    before naming any asset, ``trace`` while iterating that asset, ``slot`` after fitting with an
    offset inside that asset's slot.
    """
    names = sorted(int(path.stem, 16) for path in directory.glob("*.assets"))
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    (target / "attempt.bin").write_bytes(json.dumps([f"{h:016X}" for h in names]).encode())
    if rules.get("unknown"):
        raise RuntimeError("opaque stager failure")
    for file_hash in names:
        if rules.get(file_hash) == "trace":
            raise RuntimeError("asset does not fit")
    for name in names:
        if rules.get(name) == "slot":
            raise RuntimeError(f"no safe insertion point for slot {package.slots[name][0].slot_offset + 7}")
    body = b"".join((directory / f"{h:016X}.assets").read_bytes() for h in names)
    (target / "package.bin").write_bytes(body)
    return {"status": "staged", "replacement_count": len(names)}


class _Run:
    """One `_stage_package` call in its own work/output directories, sharing a game and plan."""

    def __init__(self, case: "StagingRetryFaults", name: str, *, rules_full: dict, rules_fit: dict,
                 fit_only_mode: bool = False, proofs=None, record: dict | None = None,
                 precreate_output: bool = False):
        import build_device_patch as bdp

        self.work = case.root / name / "work"
        self.output = case.root / name / "out"
        self.work.mkdir(parents=True)
        self.output.mkdir(parents=True)
        if precreate_output:
            (self.output / case.package.package_id).mkdir()
        self.calls: list[list[str]] = []
        package = case.package

        def stage(directory: Path, donations: bool) -> dict:
            self.calls.append(sorted(path.stem.upper() for path in directory.glob("*.assets")))
            return stage_unity_package(directory, self.output / package.package_id,
                                       rules_full if donations else rules_fit, package)

        def fit_only(package_, replacements: Path):
            target = self.work / "fit-replacements" / package_.package_id
            target.mkdir(parents=True)
            for path in replacements.glob("*.assets"):
                shutil.copy2(path, target / path.name)
            return {"assets": []}, target

        self.error = None
        try:
            self.report, self.mode, self.fit_summary = bdp._stage_package(
                package, case.replacements, stage=stage, fit_only=fit_only, fit_only_mode=fit_only_mode,
                work=self.work, output=self.output, log=lambda message: None, proofs=proofs, record=record)
        except RuntimeError as error:
            self.error = str(error)
            self.report = self.mode = self.fit_summary = None
        loop = "full-replacements" if self.mode == "full" else "fit-replacements"
        staged_dir = self.work / loop / package.package_id
        self.staged = sorted(path.name for path in staged_dir.glob("*.assets")) if self.report else []
        copy = self.output / package.package_id
        self.files = ({path.relative_to(copy).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                       for path in sorted(copy.rglob("*")) if path.is_file()} if copy.is_dir() else {})

    def outcome(self) -> tuple:
        return self.error, self.report, self.mode, self.fit_summary, self.staged, self.files


A, B, C, D = 0x1111111111111111, 0x2222222222222222, 0x3333333333333333, 0x4444444444444444


class StagingRetryFaults(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="hok-staging-retry-probe-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.game = self.root / "game"
        self.package = _FakePackage(self.game, "7", [A, B, C, D])
        self.replacements = self.root / "safe-replacements" / "7"
        self.replacements.mkdir(parents=True)
        for file_hash in (A, B, C, D):
            (self.replacements / f"{file_hash:016X}.assets").write_bytes(f"english {file_hash:016X}".encode())
        self.fingerprints = {str(path.relative_to(self.game)): f"fp:{path.name}"
                             for path in [self.package.index_path, *self.package.shard_paths]}
        self.runs = 0

    def proofs(self, proofs: list[dict]):
        import build_device_patch as bdp

        return bdp._RetryProofs(PRODUCER, proofs, self.game, self.fingerprints, lambda message: None)

    def run_(self, **kwargs) -> _Run:
        self.runs += 1
        return _Run(self, f"run{self.runs}", **kwargs)

    def observe(self, times: int, **kwargs) -> list[dict]:
        """Baseline runs with keys on: return every proof they observed."""
        observed = []
        for _ in range(times):
            record: dict = {}
            self.run_(proofs=self.proofs([]), record=record, **kwargs)
            observed += [loop["proof"] for loop in record["loops"] if loop["proof"]]
        return observed

    def confirmed(self, times: int = 2, **kwargs) -> list[dict]:
        import build_device_patch as bdp

        return bdp.confirm_retry_proofs(self.observe(times, **kwargs))["proofs"]

    @staticmethod
    def attempts(record: dict) -> int:
        return sum(len(loop["attempts"]) for loop in record["loops"])

    def test_metrics_and_keys_leave_baseline_unchanged(self) -> None:
        rules = {A: "trace", B: "slot"}
        plain = self.run_(rules_full=rules, rules_fit={})
        record: dict = {}
        measured = self.run_(rules_full=rules, rules_fit={}, proofs=self.proofs([]), record=record)
        self.assertEqual(plain.outcome(), measured.outcome())
        self.assertEqual(plain.fit_summary, {"dropped_while_staging": [f"{A:016X}", f"{B:016X}"]})
        self.assertEqual(self.attempts(record), 3)
        loop = record["loops"][0]
        self.assertEqual([a["attribution"] for a in loop["attempts"]], ["traceback", "slot-offset", None])
        self.assertIsNone(loop["prerouted"])

    def test_confirmed_proof_takes_one_attempt_with_same_output(self) -> None:
        rules = {A: "trace", B: "slot"}
        proofs = self.confirmed(rules_full=rules, rules_fit={})
        self.assertEqual(len(proofs), 1)
        self.assertEqual(proofs[0]["confirmations"], 2)
        baseline = self.run_(rules_full=rules, rules_fit={})
        record: dict = {}
        routed = self.run_(rules_full=rules, rules_fit={}, proofs=self.proofs(proofs), record=record)
        self.assertEqual(baseline.outcome(), routed.outcome())
        self.assertEqual(len(baseline.calls), 3)
        self.assertEqual(len(routed.calls), 1)
        self.assertEqual(record["loops"][0]["preroute_outcome"], "staged")
        self.assertIsNone(record["loops"][0]["proof"], "a pre-routed run is not a new observation")

    def test_one_observation_is_not_a_proof(self) -> None:
        rules = {A: "trace"}
        proofs = self.confirmed(times=1, rules_full=rules, rules_fit={})
        self.assertEqual(proofs[0]["confirmations"], 1)
        record: dict = {}
        self.run_(rules_full=rules, rules_fit={}, proofs=self.proofs(proofs), record=record)
        self.assertIsNone(record["loops"][0]["prerouted"])
        self.assertEqual(self.attempts(record), 2)

    def test_conflicting_observations_are_left_out(self) -> None:
        import build_device_patch as bdp

        first = self.observe(1, rules_full={A: "trace"}, rules_fit={})[0]
        second = dict(first, dropped=[f"{B:016X}"])
        merged = bdp.confirm_retry_proofs([first, second])
        self.assertEqual(merged["proofs"], [])
        self.assertEqual(len(merged["conflicts"]), 1)

    def test_different_failing_asset_falls_back_to_baseline(self) -> None:
        proofs = self.confirmed(rules_full={A: "trace", B: "slot"}, rules_fit={})
        changed = {A: "trace", B: "slot", C: "trace"}  # the stager now also fails on C
        baseline = self.run_(rules_full=changed, rules_fit={})
        record: dict = {}
        routed = self.run_(rules_full=changed, rules_fit={}, proofs=self.proofs(proofs), record=record)
        self.assertEqual(baseline.outcome(), routed.outcome())
        self.assertEqual(record["loops"][0]["preroute_outcome"], "fell-back")
        self.assertEqual(len(routed.calls), len(baseline.calls) + 1)
        self.assertEqual(routed.calls[1], baseline.calls[0], "the baseline restarts from the full plan")

    def test_changed_chunk_layout_changes_the_key(self) -> None:
        rules = {A: "trace"}
        proofs = self.confirmed(rules_full=rules, rules_fit={})
        self.package.index_path.write_bytes(self.package.index_path.read_bytes() + b";chunk 2")
        record: dict = {}
        self.run_(rules_full=rules, rules_fit={}, proofs=self.proofs(proofs), record=record)
        self.assertIsNone(record["loops"][0]["prerouted"])
        self.assertNotEqual(record["loops"][0]["key"], proofs[0]["key"])

    def test_changed_translation_changes_the_key(self) -> None:
        rules = {A: "trace"}
        proofs = self.confirmed(rules_full=rules, rules_fit={})
        (self.replacements / f"{C:016X}.assets").write_bytes(b"other translation")
        record: dict = {}
        self.run_(rules_full=rules, rules_fit={}, proofs=self.proofs(proofs), record=record)
        self.assertIsNone(record["loops"][0]["prerouted"])

    def test_unknown_error_keeps_the_fit_only_fallback(self) -> None:
        rules_full, rules_fit = {"unknown": True}, {A: "trace"}
        proofs = self.confirmed(rules_full=rules_full, rules_fit=rules_fit)
        self.assertEqual([proof["loop"] for proof in proofs], ["fit-only"])
        baseline = self.run_(rules_full=rules_full, rules_fit=rules_fit)
        record: dict = {}
        routed = self.run_(rules_full=rules_full, rules_fit=rules_fit, proofs=self.proofs(proofs), record=record)
        self.assertEqual(baseline.outcome(), routed.outcome())
        full, fit = record["loops"]
        self.assertEqual(full["outcome"], "unattributed-fallback")
        self.assertIsNone(full["prerouted"])
        self.assertEqual(len(full["attempts"]), 1)
        # The failed full attempt left its output copy, so the fit-only proof is declined (the
        # existing-output-copy guard) and the fit-only loop runs exactly as the baseline does.
        self.assertTrue(routed.output.joinpath(self.package.package_id).exists())
        self.assertIsNone(fit["prerouted"])
        self.assertIsNone(fit["preroute_outcome"])
        self.assertEqual(fit["outcome"], "staged")
        self.assertEqual(len(fit["attempts"]), 2)

    def test_unknown_fit_only_error_is_raised_either_way(self) -> None:
        rules = {"unknown": True}
        baseline = self.run_(rules_full=rules, rules_fit=rules, fit_only_mode=True)
        record: dict = {}
        routed = self.run_(rules_full=rules, rules_fit=rules, fit_only_mode=True,
                           proofs=self.proofs([]), record=record)
        self.assertEqual(baseline.error, "opaque stager failure")
        self.assertEqual(baseline.outcome(), routed.outcome())
        self.assertEqual(record["loops"][0]["outcome"], "unattributed-raise")
        self.assertIsNone(record["loops"][0]["proof"])

    def test_fit_only_mode_does_not_use_a_full_proof(self) -> None:
        rules = {A: "trace"}
        full_proofs = self.confirmed(rules_full=rules, rules_fit=rules)
        record: dict = {}
        self.run_(rules_full=rules, rules_fit=rules, fit_only_mode=True,
                  proofs=self.proofs(full_proofs), record=record)
        self.assertIsNone(record["loops"][0]["prerouted"])
        fit_proofs = self.confirmed(rules_full=rules, rules_fit=rules, fit_only_mode=True)
        baseline = self.run_(rules_full=rules, rules_fit=rules, fit_only_mode=True)
        record = {}
        routed = self.run_(rules_full=rules, rules_fit=rules, fit_only_mode=True,
                           proofs=self.proofs(fit_proofs), record=record)
        self.assertEqual(baseline.outcome(), routed.outcome())
        self.assertEqual(record["loops"][0]["preroute_outcome"], "staged")
        record = {}
        self.run_(rules_full=rules, rules_fit=rules, proofs=self.proofs(fit_proofs), record=record)
        self.assertIsNone(record["loops"][0]["prerouted"], "a fit-only proof never routes the full loop")

    def test_existing_output_copy_skips_the_proof(self) -> None:
        rules = {A: "trace"}
        proofs = self.confirmed(rules_full=rules, rules_fit={})
        record: dict = {}
        self.run_(rules_full=rules, rules_fit={}, proofs=self.proofs(proofs), record=record,
                  precreate_output=True)
        self.assertIsNone(record["loops"][0]["prerouted"])
        self.assertEqual(self.attempts(record), 2)

    def test_proof_naming_an_absent_table_is_not_used(self) -> None:
        rules = {A: "trace"}
        proofs = self.confirmed(rules_full=rules, rules_fit={})
        forged = [dict(proofs[0], dropped=["9999999999999999"])]
        record: dict = {}
        self.run_(rules_full=rules, rules_fit={}, proofs=self.proofs(forged), record=record)
        self.assertIsNone(record["loops"][0]["prerouted"])
        self.assertEqual(self.attempts(record), 2)

    def test_malformed_or_prerouted_proofs_are_ignored(self) -> None:
        rules = {A: "trace"}
        proofs = self.confirmed(rules_full=rules, rules_fit={})
        bad = [dict(proofs[0], prerouted=True), dict(proofs[0], dropped=["1111"]),
               dict(proofs[0], schema=2), dict(proofs[0], outcome="empty")]
        self.assertEqual(self.proofs(bad).proofs, {})


# --- real measurement --------------------------------------------------------------------------


class _StageObserver:
    """Counts filesystem work inside each real stage_unity_package call, from audit events."""

    WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC

    def __init__(self) -> None:
        self.active: dict | None = None
        self.calls: list[dict] = []

    def hook(self, event: str, args: tuple) -> None:
        current = self.active
        if current is None:
            return
        try:
            if event == "shutil.copyfile":
                current["copyfile_calls"] += 1
                current["copyfile_bytes"] += os.stat(args[0]).st_size
            elif event == "shutil.copytree":
                current["copytree_calls"] += 1
            elif event == "shutil.rmtree":
                current["rmtree_calls"] += 1
            elif event == "os.rename":
                current["renames"] += 1
            elif event == "os.remove":
                current["removes"] += 1
            elif event == "open":
                mode, flags = args[1], args[2]
                writable = (any(c in mode for c in "wax+") if isinstance(mode, str)
                            else bool(isinstance(flags, int) and flags & self.WRITE_FLAGS))
                current["writable_opens" if writable else "read_opens"] += 1
        except Exception:  # an audit hook must never break the call it observes
            current["hook_errors"] += 1

    def wrap(self, original, tree_size):
        observer = self

        def observed_stage(*args, **kwargs):
            source = Path(kwargs.get("source_package_dir", ""))
            output = Path(args[2]) if len(args) > 2 else Path(kwargs.get("output_dir", ""))
            entry = {"index": len(observer.calls) + 1, "package_id": source.name,
                     "global_donations": kwargs.get("global_donations"), "outcome": "failed",
                     "copyfile_calls": 0, "copyfile_bytes": 0, "copytree_calls": 0, "rmtree_calls": 0,
                     "renames": 0, "removes": 0, "writable_opens": 0, "read_opens": 0, "hook_errors": 0}
            observer.calls.append(entry)
            started = time.perf_counter()
            observer.active = entry
            try:
                result = original(*args, **kwargs)
                entry["outcome"] = "staged"
                return result
            except BaseException as error:
                entry["error_type"] = type(error).__name__
                raise
            finally:
                observer.active = None
                entry["seconds"] = time.perf_counter() - started
                entry["output_files"], entry["output_bytes"] = tree_size(output / source.name)

        return observed_stage


def _new_outside(path: Path, forbidden: list[Path], what: str) -> Path:
    path = path.resolve()
    if path.exists():
        raise SystemExit(f"{what} must not exist yet: {path}")
    for root in forbidden:
        if path == root or path.is_relative_to(root):
            raise SystemExit(f"{what} must be outside {root}")
    return path


def measure(args: argparse.Namespace) -> int:
    game = args.game.resolve()
    forbidden = [game] + ([args.apk.resolve().parent] if args.apk else [])
    work = _new_outside(args.work, forbidden, "--work")
    output = _new_outside(args.output, forbidden, "--output")
    metrics_path = _new_outside(args.metrics, forbidden, "--metrics")

    producer_key = None
    if not args.no_keys:
        import run_artifacts

        # Before the pipeline is imported, as run_artifacts asks.
        identity = run_artifacts.windows_producer_identity(ROOT)
        if identity is None:
            raise SystemExit("producer identity unavailable; pass --no-keys for a metrics-only run")
        # --runtime may sit outside resources/, which the producer identity covers; name it too.
        producer_key = run_artifacts.identity_key({
            "producer": identity, "runtime": run_artifacts._tree_identity(args.runtime.resolve())})
    proofs = None
    if args.proofs:
        loaded = json.loads(args.proofs.read_text(encoding="utf-8"))
        if producer_key is None or loaded.get("producer_key") != producer_key:
            raise SystemExit("--proofs was confirmed under a different producer key; not used")
        proofs = {"producer_key": producer_key, "proofs": loaded.get("proofs", [])}
    elif producer_key is not None:
        proofs = {"producer_key": producer_key, "proofs": []}  # keys and observations, no pre-route

    sys.path.append(str(args.runtime.resolve()))
    import wxq_patch.unity_package_installer as installer
    import build_device_patch as bdp

    observer = _StageObserver()
    installer.stage_unity_package = observer.wrap(installer.stage_unity_package, bdp._tree_size)
    sys.addaudithook(observer.hook)

    staging_metrics: dict = {}
    started = time.perf_counter()
    summary = bdp.build_patch(game, args.catalog.resolve(), work, output, fit_only_mode=args.fit_only,
                              apk=args.apk, staging_metrics=staging_metrics, retry_proofs=proofs)
    elapsed = time.perf_counter() - started
    observed_totals = {name: sum(call[name] for call in observer.calls)
                       for name in ("copyfile_calls", "copyfile_bytes", "copytree_calls", "rmtree_calls",
                                    "renames", "removes", "writable_opens", "output_bytes", "seconds")}
    observed_totals["calls"] = len(observer.calls)
    observed_totals["failed_calls"] = sum(call["outcome"] != "staged" for call in observer.calls)
    report = {
        "schema": 1,
        "inputs": {"game": str(game), "catalog": str(args.catalog.resolve()),
                   "apk": str(args.apk.resolve()) if args.apk else None, "fit_only": args.fit_only,
                   "producer_key": producer_key, "keys": not args.no_keys,
                   "proofs_file": str(args.proofs.resolve()) if args.proofs else None,
                   "python": sys.version},
        "elapsed_seconds": elapsed,
        "summary_counts": summary["counts"],
        "build": staging_metrics,
        "observed_stage_calls": observer.calls,
        "observed_totals": observed_totals,
        "proofs_observed": [loop["proof"] for package in staging_metrics.get("packages", [])
                            for loop in package.get("loops", []) if loop.get("proof")],
    }
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"elapsed_seconds": elapsed, "totals": staging_metrics.get("totals"),
                      "observed_totals": observed_totals}, indent=2))
    return 0


def confirm(args: argparse.Namespace) -> int:
    import build_device_patch as bdp

    if len(args.metrics) < 2:
        raise SystemExit("confirm needs at least two baseline measure runs")
    keys, observations = set(), []
    for path in args.metrics:
        report = json.loads(path.read_text(encoding="utf-8"))
        if report["inputs"].get("proofs_file"):
            raise SystemExit(f"{path}: a run given proofs is not a baseline observation")
        keys.add(report["inputs"].get("producer_key"))
        observations += report.get("proofs_observed", [])
    if len(keys) != 1 or None in keys:
        raise SystemExit("the runs do not share one producer key")
    result = bdp.confirm_retry_proofs(observations)
    result["producer_key"] = keys.pop()
    result["runs"] = [str(path.resolve()) for path in args.metrics]
    if args.out.exists():
        raise SystemExit(f"--out must not exist yet: {args.out}")
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"{len(result['proofs'])} confirmed proofs, {len(result['conflicts'])} conflicting groups")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("faults", help="synthetic fault cases; no runtime or game")
    run = commands.add_parser("measure", help="one real build_patch run with staging metrics")
    run.add_argument("--runtime", type=Path, required=True)
    run.add_argument("--game", type=Path, required=True)
    run.add_argument("--catalog", type=Path, required=True)
    run.add_argument("--work", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--metrics", type=Path, required=True)
    run.add_argument("--apk", type=Path)
    run.add_argument("--proofs", type=Path)
    run.add_argument("--fit-only", action="store_true")
    run.add_argument("--no-keys", action="store_true")
    merge = commands.add_parser("confirm", help="merge baseline observations into confirmed proofs")
    merge.add_argument("metrics", type=Path, nargs="+")
    merge.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "faults":
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(StagingRetryFaults)
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    if args.command == "measure":
        if args.no_keys and args.proofs:
            parser.error("--proofs needs keys")
        return measure(args)
    return confirm(args)


if __name__ == "__main__":
    sys.exit(main())
