"""Record the PC engine's ``adaptive.run`` on fixture installations for the Rust port to replay
(wave 2, ADR-003, ADR-004).

``run`` is the PC edition's install engine: receipts, the transaction, recovery, the stale-state
prune, the Watchdog cleanup, the launcher list and the package-hash metadata. What it calls that
the port does not own is stubbed here and recorded call by call, the way ``RunHost`` takes it:
``scan``, ``stage_unity_package``, ``query_package_hash``, ``stage_package_hash_metadata_batch``,
``_assert_game_stopped`` and ``receipt_root`` (moved into the case's folder, as ``engine_hooks``
moves it into the work folder).

Each case is a synthetic PC-shaped installation and a sequence of steps on it. Its pre-state is
taken after any setup the replay does not repeat (a crash mid-swap, a game update, a stale
receipt), so the replay starts from the same bytes at the same absolute paths. Each line of
``<dir>/cases.jsonl`` is one case: ``base``, ``pre`` (every directory and file under it, files as
blobs under ``<dir>/blobs/<sha256>``, read-only ones flagged) and ``steps``; each step has its
``action``, whether another handle holds the mutation lock, the host calls in order (arguments,
result, the files each wrote), the result (the report without ``seconds``, or ``Class:
message``) and the tree after it. Receipt folder names (``<time_ns>-<hex>``) are replaced by
``receipt-<n>`` in order of appearance.

    .venv\\Scripts\\python.exe rust\\harness\\run_tap.py <dir> <live-base> [<cross-volume-work>]
    cargo run --release -p hokace-core --example run_replay -- <dir>

``<live-base>`` is where the cases run (wiped first); ``<cross-volume-work>``, on another volume,
makes one case's staged files fail to hard-link so ``commit`` copies them.

Migration tooling, run by hand: the exe, the APK and ``tools/`` never import it.
"""
from __future__ import annotations

import hashlib
import json
import msvcrt
import os
import pathlib
import re
import shutil
import stat
import sys
from types import SimpleNamespace

ROOT = pathlib.Path(__file__).resolve().parents[2]
RECEIPT_NAME = re.compile(r"\b\d{16,20}-[0-9a-f]{8}\b")


def _runtime():
    sys.path.append(str(ROOT / "resources" / "runtime"))
    from wxq_patch import adaptive
    return adaptive


adaptive = _runtime()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: pathlib.Path) -> str:
    return sha(path.read_bytes())


def _error(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


class Blobs:
    def __init__(self, out: pathlib.Path) -> None:
        self.root = out / "blobs"
        self.root.mkdir(parents=True, exist_ok=True)

    def keep(self, data: bytes) -> str:
        name = sha(data)
        path = self.root / name
        if not path.exists():
            path.write_bytes(data)
        return name


class Names:
    """Receipt folder names to ``receipt-<n>``, in order of first appearance."""

    def __init__(self) -> None:
        self.map: dict[str, str] = {}

    def see(self, names) -> None:
        for name in sorted(names):
            self.map.setdefault(name, f"receipt-{len(self.map)}")

    def text(self, value: str) -> str:
        return RECEIPT_NAME.sub(lambda m: self.map.get(m.group(0), m.group(0)), value)


def tree(base: pathlib.Path) -> list[pathlib.Path]:
    return sorted(base.rglob("*"), key=lambda p: p.relative_to(base).as_posix())


def snapshot(base: pathlib.Path, names: Names) -> list:
    """Every directory and file under ``base``: ``[path, "<dir>" | sha256]``, sorted by path."""
    receipts = base / "receipts"
    if receipts.is_dir():
        names.see(p.name for p in receipts.iterdir() if p.is_dir() and RECEIPT_NAME.fullmatch(p.name))
    rows = []
    for path in tree(base):
        rel = names.text(path.relative_to(base).as_posix())
        rows.append([rel, "<dir>" if path.is_dir() else file_sha(path)])
    rows.sort(key=lambda r: r[0])
    return rows


def pre_state(base: pathlib.Path, blobs: Blobs) -> list:
    rows = []
    for path in tree(base):
        rel = path.relative_to(base).as_posix()
        if path.is_dir():
            rows.append([rel, None, False])
        else:
            readonly = not os.stat(path).st_mode & stat.S_IWRITE
            rows.append([rel, blobs.keep(path.read_bytes()), readonly])
    return rows


# -- the fixture installation ------------------------------------------------------------------

BUILTIN = pathlib.PurePath("WXQ_Data", "Package", "builtin")
PACKAGES = {"7": ["7.db", "7_0.db", "7_1.db"], "12": ["12.db", "12_0.db"]}


def build_game(game: pathlib.Path) -> None:
    for package, files in PACKAGES.items():
        folder = game / BUILTIN / package
        folder.mkdir(parents=True, exist_ok=True)
        for name in files:
            (folder / name).write_bytes(f"original {package}/{name}\n".encode() * 40)
    zero = game / BUILTIN / "0"
    zero.mkdir(parents=True)
    (zero / "0.db").write_bytes(b"internal index v1\n" * 20)
    (game / BUILTIN / "7" / "7_0.db.wxq-engpatch.tmp").write_bytes(b"left by a killed engine")
    (game / "WXQ.exe").write_bytes(b"MZ not really")
    listed = [p for p in sorted(game.rglob("*")) if p.is_file() and not p.name.endswith(".tmp")]
    entries = []
    for path in listed:
        name = str(path.relative_to(game))
        # One entry lower-cased, as the launcher sometimes records them: `_name_key` casefolds.
        if name.endswith("12_0.db"):
            name = name.lower()
        entries.append({"file": name, "file_size": path.stat().st_size})
    entries.append({"file": "Data\\字体\\font.ttf", "file_size": 1234})
    (game / "LocalFileList.json").write_text(
        json.dumps(entries, ensure_ascii=False, separators=(", ", ": ")), encoding="utf-8")
    watchdog = game / "WXQ_Data" / "QtsDataFolder" / "QtsVFSCache" / "Watchdog"
    (watchdog / "sub").mkdir(parents=True)
    (watchdog / "BrokenList.db").write_bytes(b"broken" * 10)
    (watchdog / "History.db").write_bytes(b"history" * 3)
    (watchdog / "notes.txt").write_bytes(b"x")
    (watchdog / "sub" / "deep.bin").write_bytes(b"deep" * 5)
    readonly = watchdog / "PatchList.db"
    readonly.write_bytes(b"patch list")
    os.chmod(readonly, stat.S_IREAD)
    (game / "QtsDataFolder" / "QtsVFSCache" / "Watchdog").mkdir(parents=True)


# -- the host stubs ----------------------------------------------------------------------------

class Host:
    """The stubbed calls of one step, scripted by ``spec`` and recorded in call order."""

    def __init__(self, spec: dict, game: pathlib.Path, blobs: Blobs, names: Names) -> None:
        self.spec, self.game, self.blobs, self.names = spec, game, blobs, names
        self.calls: list[dict] = []

    def record(self, fn: str, args, result, writes=()) -> None:
        self.calls.append({"fn": fn, "args": args, "result": result,
                           "writes": [[str(p), self.blobs.keep(p.read_bytes())] for p in writes]})

    def assert_game_stopped(self) -> None:
        running = self.spec.get("running")
        if running:
            message = "Close the game before patching: " + running
            self.record("assert_game_stopped", [], {"error": f"RuntimeError: {message}"})
            raise RuntimeError(message)
        self.record("assert_game_stopped", [], {"ok": None})

    def scan(self, game, assets, work, *, materialize):
        game = pathlib.Path(game)
        plans, fingerprints = [], {}
        for package in sorted(PACKAGES, key=int):
            folder = game / BUILTIN / package
            for path in sorted(folder.glob("*.db")):
                fingerprints[str(path.relative_to(game))] = file_sha(path)
        for drop in self.spec.get("drop_fingerprints", []):
            fingerprints.pop(drop, None)
        for package in self.spec.get("plans", {}):
            folder = game / BUILTIN / package
            replacements = pathlib.Path(work) / "replacements" / package
            if materialize:
                replacements.mkdir(parents=True, exist_ok=True)
                (replacements / "plan.json").write_text(json.dumps(self.spec["plans"][package]))
            shards = sorted(p for p in folder.glob(f"{package}_*.db") if p.is_file())
            plans.append((SimpleNamespace(package_id=package, package_dir=folder, index_path=folder / f"{package}.db",
                                          shard_paths=shards), replacements, {}))
        counts = dict(self.spec.get("counts", {}))
        skipped = self.spec.get("skipped", [])
        writes = [p for p in pathlib.Path(work).rglob("*") if p.is_file()] if materialize else []
        self.record("scan", [str(game), str(assets), str(work), materialize], {"ok": {
            "plans": [{"package_id": p.package_id, "package_dir": str(p.package_dir), "index_path": str(p.index_path),
                       "shard_paths": [str(s) for s in p.shard_paths], "replacements": str(r)} for p, r, _ in plans],
            "fingerprints": list(fingerprints.items()), "counts": counts, "skipped": skipped}}, writes)
        return plans, fingerprints, counts, skipped

    def stage_unity_package(self, game, replacements, stage, *, source_package_dir, global_donations,
                            verify_all_unrelated, source_hashes):
        package = pathlib.Path(source_package_dir).name
        plan = self.spec["plans"][package]
        args = [str(game), str(replacements), str(stage), str(source_package_dir), global_donations,
                verify_all_unrelated, list(source_hashes.items())]
        if "error" in plan:
            self.record("stage_unity_package", args, {"error": plan["error"]})
            raise RuntimeError(plan["error"].split(": ", 1)[1])
        out = pathlib.Path(stage) / package
        out.mkdir(parents=True, exist_ok=True)
        files, writes = [], []
        for name, content in plan.get("files", {}).items():
            source = pathlib.Path(source_package_dir) / name
            data = source.read_bytes() if content is None else content.encode()
            (out / name).write_bytes(data)
            writes.append(out / name)
            source_hash = file_sha(source) if source.exists() else None
            source_hash = plan.get("source_override", {}).get(name, source_hash)
            files.append({"name": name, "source_sha256": source_hash, "staged_sha256": sha(data)})
        for path in plan.get("touch", []):
            (self.game / path).write_bytes(b"the game updated this file mid-run")
            writes.append(self.game / path)
        result = {"package_id": package, "files": files, "verified": True}
        if "removed" in plan:
            result["removed_files"] = plan["removed"]
        if "fallbacks" in plan:
            result["native_verification"] = {"source_read_fallbacks": plan["fallbacks"]}
        self.record("stage_unity_package", args, {"ok": result}, writes)
        return result

    def query_package_hash(self, game, package_dir):
        package_dir = pathlib.Path(package_dir)
        digest = hashlib.sha256()
        for path in sorted(package_dir.glob("*.db")):
            digest.update(path.name.encode() + b"|" + path.read_bytes())
        value = digest.hexdigest()[:32]
        self.record("query_package_hash", [str(game), str(package_dir)], {"ok": value})
        return value

    def stage_package_hash_metadata_batch(self, game, package_hashes, output):
        output = pathlib.Path(output)
        updated = self.spec.get("metadata_updated", True)
        writes = []
        if updated:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"internal index v2\n" + json.dumps(package_hashes, sort_keys=True).encode())
            writes.append(output)
        result = {"updated": updated, "path": str(output), "packages": sorted(package_hashes)}
        self.record("stage_package_hash_metadata_batch", [str(game), list(package_hashes.items()), str(output)],
                    {"ok": result}, writes)
        return result


def install_host(host: Host, receipts: pathlib.Path) -> None:
    adaptive.receipt_root = lambda game: receipts
    adaptive._assert_game_stopped = host.assert_game_stopped
    adaptive.scan = host.scan
    adaptive.stage_unity_package = host.stage_unity_package
    adaptive.query_package_hash = host.query_package_hash
    adaptive.stage_package_hash_metadata_batch = host.stage_package_hash_metadata_batch


# -- cases -------------------------------------------------------------------------------------

def changed(package: str, *names: str) -> dict:
    return {name: f"english {package}/{name}\n" * 30 for name in names}


PLAN_7 = {"files": {**changed("7", "7_0.db"), "7.db": None}}
PLAN_12 = {"files": changed("12", "12.db", "12_0.db"), "fallbacks": ["asset-1", "asset-2"]}
COUNTS = {"translated": 12345, "unknown": 67, "graphics": 3, "capacity_skipped": 1001}
DONE = {"already_english": 12345, "unknown": 67}


def lifecycle() -> tuple[list, list]:
    install = {"plans": {"7": PLAN_7, "12": PLAN_12}, "counts": COUNTS, "skipped": [["x", "reason"]]}
    steps = [
        ("status", {}),
        ("status", {"plans": {"7": PLAN_7}, "counts": COUNTS}),
        ("stage", install),
        ("install", install),
        ("status", {"counts": DONE}),
        ("install", {"counts": DONE, "metadata_updated": False}),
        ("install", {"counts": {}}),
        ("restore", {}),
        ("status", {"counts": COUNTS}),
        ("restore", {}),
    ]
    return [], steps


def new_and_removed() -> tuple[list, list]:
    plan = {"files": {**changed("7", "7_0.db"), "7_2.db": "a new shard\n"}, "removed": ["7_1.db"],
            "fallbacks": ["only-one"]}
    install = {"plans": {"7": plan}, "counts": COUNTS}
    return [], [("install", install), ("status", {"counts": DONE}), ("restore", {}), ("status", {})]


def metadata_repair() -> tuple[list, list]:
    def setup(run):
        run("install", {"plans": {"7": PLAN_7}, "counts": COUNTS, "metadata_updated": False})
        # The launcher rewrote its list after a check: the installed file's size is stale again.
        game_list = run.game / "LocalFileList.json"
        entries = json.loads(game_list.read_text(encoding="utf-8"))
        for entry in entries:
            if entry["file"].endswith("7_0.db"):
                entry["file_size"] = 1
        game_list.write_text(json.dumps(entries, ensure_ascii=False, separators=(", ", ": ")), encoding="utf-8")
    return [setup], [("status", {"counts": DONE}), ("install", {"counts": DONE}), ("status", {"counts": DONE}),
                     ("restore", {})]


def crash() -> tuple[list, list]:
    def setup(run):
        real = os.replace
        calls = {"n": 0}

        def replace(src, dst):
            calls["n"] += 1
            if calls["n"] == 4:  # preparing, pending, live -> .ace-old, then die before .ace-new -> live
                raise KeyboardInterrupt("process killed mid-swap")
            return real(src, dst)

        os.replace = replace
        try:
            run("install", {"plans": {"7": PLAN_7, "12": PLAN_12}, "counts": COUNTS})
        except KeyboardInterrupt:
            pass
        finally:
            os.replace = real
    install = {"plans": {"7": PLAN_7}, "counts": COUNTS}
    return [setup], [("status", {"plans": {"7": PLAN_7}, "counts": COUNTS}), ("restore", {}), ("install", install),
                     ("restore", {})]


def stale_state() -> tuple[list, list]:
    def setup(run):
        run("install", {"plans": {"7": PLAN_7}, "counts": COUNTS})
        run("install", {"plans": {"12": PLAN_12}, "counts": COUNTS})
        # A game update replaced the first install's file: its receipt no longer matches live.
        (run.game / BUILTIN / "7" / "7_0.db").write_bytes(b"updated by the launcher\n" * 9)
        (run.game / BUILTIN / "7" / "7_0.db.ace-old").write_bytes(b"left over")
        (run.game / BUILTIN / "12" / "12.db.ace-new").write_bytes(b"left over too")
        receipts = run.base / "receipts"
        rolled = receipts / "1700000000000000000-0badf00d"
        rolled.mkdir()
        (rolled / "receipt.json").write_text(json.dumps({"schema": 1, "state": "rolled_back", "action": "install",
                                                         "files": [{"relative": "..\\outside.db", "before": None,
                                                                    "after": "0" * 64}, {"relative": 5}]}))
        odd = receipts / "1700000000000000002-cafecafe"
        odd.mkdir()
        (odd / "receipt.json").write_text(json.dumps({"schema": 1, "state": "preparing", "action": "install",
                                                      "files": []}))
        (receipts / "stray.txt").write_text("not a receipt folder")
    return [setup], [("status", {"counts": DONE}), ("restore", {}), ("install", {"counts": DONE}),
                     ("status", {"counts": DONE})]


def corrupt_receipt() -> tuple[list, list]:
    """A receipt that will not parse stops every mutating step, as the runtime reads them all."""
    def setup(run):
        run("install", {"plans": {"7": PLAN_7}, "counts": COUNTS})
        broken = run.base / "receipts" / "1700000000000000001-deadbeef"
        broken.mkdir()
        (broken / "receipt.json").write_bytes(b"{not json")
    return [setup], [("status", {"counts": DONE}), ("install", {"counts": DONE}), ("restore", {})]


def failures() -> tuple[list, list]:
    def plan(**extra):
        return {"plans": {"7": {**PLAN_7, **extra}}, "counts": COUNTS}
    relative = str(BUILTIN / "7" / "7_0.db")
    steps = [
        ("install", {**plan(), "running": "WXQ.exe"}),
        ("install", plan(source_override={"7_0.db": "f" * 64})),
        ("install", plan(files={"7_9.db": "unknown\n"}, source_override={"7_9.db": "e" * 64})),
        ("install", plan(removed=["7_0.db"])),
        ("install", plan(removed=["7_8.db"])),
        ("install", {**plan(), "drop_fingerprints": [str(BUILTIN / "7" / "7_1.db")]}),
        ("stage", plan(error="RuntimeError: Native staging failed for asset 0x1F")),
        ("install", plan(touch=[relative])),
        ("restore", {}),
        ("install", {**plan(), "locked": True}),
        ("stage", plan(files={"7_0.db": "x" * 7, "7_1.db": None}, removed=[])),
    ]
    return [], steps


def cross_volume(work: pathlib.Path | None):
    if work is None:
        return None

    def case() -> tuple[list, list]:
        plan = {"files": {**changed("7", "7_0.db"), "7_2.db": "a new shard\n"}, "removed": ["7_1.db"]}
        return [], [("install", {"plans": {"7": plan}, "counts": COUNTS, "work": str(work)}), ("restore", {})]
    return case


class Runner:
    def __init__(self, base: pathlib.Path, blobs: Blobs, names: Names) -> None:
        self.base, self.blobs, self.names = base, blobs, names
        self.game = base / "game"
        self.receipts = base / "receipts"
        self.work = base / "work"
        self.assets = base / "assets"

    def __call__(self, action: str, spec: dict) -> tuple[dict, list[dict]]:
        host = Host(spec, self.game, self.blobs, self.names)
        install_host(host, self.receipts)
        work = pathlib.Path(spec.get("work", self.work))
        held = None
        if spec.get("locked"):
            self.receipts.mkdir(parents=True, exist_ok=True)
            held = open(self.receipts / "operation.lock", "a+b")
            held.seek(0, 2)
            if held.tell() == 0:
                held.write(b"0")
                held.flush()
            held.seek(0)
            msvcrt.locking(held.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            report = adaptive.run(action, self.game, self.assets, work)
            report.pop("seconds", None)
            result = {"ok": report}
        except Exception as exc:  # noqa: BLE001 - the class and message are the recording
            result = {"error": _error(exc)}
        finally:
            if held is not None:
                held.seek(0)
                msvcrt.locking(held.fileno(), msvcrt.LK_UNLCK, 1)
                held.close()
        return result, host.calls


def record_case(name: str, case, live: pathlib.Path, blobs: Blobs, out) -> None:
    base = live / name
    shutil.rmtree(base, ignore_errors=True)
    if base.exists():
        for path in base.rglob("*"):
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        shutil.rmtree(base)
    names = Names()
    run = Runner(base, blobs, names)
    build_game(run.game)
    run.work.mkdir(parents=True)
    setups, steps = case()
    for setup in setups:
        setup(run)
    # The setup's receipts take their names before any step runs.
    snapshot(base, names)
    line = {"name": name, "base": str(base), "game": str(run.game), "receipts": str(run.receipts),
            "assets": str(run.assets), "pre": pre_state(base, blobs), "steps": []}
    extra_work = {pathlib.Path(spec["work"]) for _, spec in steps if "work" in spec}
    if extra_work:
        line["extra_work"] = [str(p) for p in sorted(extra_work)]
    for action, spec in steps:
        for work in extra_work:
            shutil.rmtree(work, ignore_errors=True)
            work.mkdir(parents=True)
        result, calls = run(action, spec)
        after = snapshot(base, names)
        text = names.text(json.dumps(result, ensure_ascii=False))
        line["steps"].append({"action": action, "work": spec.get("work", str(run.work)),
                              "locked": bool(spec.get("locked")), "calls": calls,
                              "result": json.loads(text), "tree": after,
                              "extra_tree": {str(w): snapshot(w, names) for w in extra_work}})
        print(f"{name} {action}: {text[:150]}", flush=True)
    out.write(json.dumps(line, ensure_ascii=False) + "\n")


def main() -> int:
    if len(sys.argv) not in (3, 4):
        print(__doc__)
        return 2
    out = pathlib.Path(sys.argv[1]).resolve()
    live = pathlib.Path(sys.argv[2]).resolve()
    cross = pathlib.Path(sys.argv[3]).resolve() if len(sys.argv) == 4 else None
    out.mkdir(parents=True, exist_ok=True)
    blobs = Blobs(out)
    cases = {"lifecycle": lifecycle, "new-and-removed": new_and_removed, "metadata-repair": metadata_repair,
             "crash": crash, "stale-state": stale_state,
             "corrupt-receipt": corrupt_receipt, "failures": failures}
    if cross is not None:
        cases["cross-volume"] = cross_volume(cross)
    with (out / "cases.jsonl").open("w", encoding="utf-8") as handle:
        for name, case in cases.items():
            record_case(name, case, live, blobs, handle)
    print(f"{len(cases)} cases -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
