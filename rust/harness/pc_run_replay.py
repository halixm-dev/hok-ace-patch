"""Replay run_tap's PC transaction cases through the installed Windows engine hook.

Run with Python 3.12 and the built native extension:
    pc_run_replay.py <recording> <scratch-parent> <cross-volume-scratch-parent>

The scratch parents must be on separate volumes to check the cross-volume copy.
"""
from __future__ import annotations

import builtins
import json
import msvcrt
import shutil
import stat
import sys
import tempfile
from collections import deque
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from run_tap import Blobs, Host, Names, PLAN_7, ROOT, _error, adaptive, build_game, install_host, snapshot


def relocate(value, paths):
    if isinstance(value, str):
        for old, new in paths.items():
            value = value.replace(old, new)
        return value
    if isinstance(value, list):
        return [relocate(item, paths) for item in value]
    if isinstance(value, dict):
        return {relocate(key, paths): relocate(item, paths) for key, item in value.items()}
    return value


class ReplayHost:
    def __init__(self, calls: list, blobs: Path) -> None:
        self.calls = deque(calls)
        self.blobs = blobs

    def call(self, name: str, args: list):
        record = self.calls.popleft()
        assert (name, args) == (record["fn"], record["args"]), (name, args, record)
        for filename, digest in record["writes"]:
            path = Path(filename)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((self.blobs / digest).read_bytes())
        result = record["result"]
        if "error" in result:
            kind, message = result["error"].split(": ", 1)
            raise getattr(builtins, kind)(message)
        return result["ok"]

    def assert_game_stopped(self):
        return self.call("assert_game_stopped", [])

    def scan(self, game, assets, work, *, materialize):
        result = self.call("scan", [str(game), str(assets), str(work), materialize])
        plans = []
        for plan in result["plans"]:
            package = SimpleNamespace(package_id=plan["package_id"], package_dir=Path(plan["package_dir"]),
                                      index_path=Path(plan["index_path"]), shard_paths=list(map(Path, plan["shard_paths"])))
            plans.append((package, Path(plan["replacements"]), {}))
        return plans, dict(result["fingerprints"]), result["counts"], result["skipped"]

    def stage_unity_package(self, game, replacements, stage, *, source_package_dir, global_donations,
                            verify_all_unrelated, source_hashes):
        return self.call("stage_unity_package", [str(game), str(replacements), str(stage), str(source_package_dir),
                                                global_donations, verify_all_unrelated,
                                                [list(pair) for pair in source_hashes.items()]])

    def query_package_hash(self, game, package_dir):
        return self.call("query_package_hash", [str(game), str(package_dir)])

    def stage_package_hash_metadata_batch(self, game, package_hashes, output):
        return self.call("stage_package_hash_metadata_batch",
                         [str(game), [list(pair) for pair in package_hashes.items()], str(output)])


@contextmanager
def operation_lock(receipts: Path, locked: bool):
    if not locked:
        yield
        return
    receipts.mkdir(parents=True, exist_ok=True)
    with (receipts / "operation.lock").open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def replay(case: dict, blobs: Path) -> int:
    base = Path(case["base"])
    game, assets, receipts = (Path(case[key]) for key in ("game", "assets", "receipts"))
    names = Names()
    for relative, digest, readonly in case["pre"]:
        path = base / relative
        if digest is None:
            path.mkdir(parents=True, exist_ok=True)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((blobs / digest).read_bytes())
        if readonly:
            path.chmod(stat.S_IREAD)
    snapshot(base, names)
    for index, step in enumerate(case["steps"]):
        for work in map(Path, case.get("extra_work", [])):
            if work.exists():
                shutil.rmtree(work)
            work.mkdir()
        host = ReplayHost(step["calls"], blobs)
        install_host(host, receipts)
        with operation_lock(receipts, step["locked"]):
            try:
                report = adaptive.run(step["action"], game, assets, Path(step["work"]), preserve_launcher_list=False)
                report.pop("seconds", None)
                result = {"ok": report}
            except Exception as exc:
                result = {"error": _error(exc)}
        label = case["name"], index + 1, step["action"]
        assert not host.calls, (label, host.calls, result)
        assert snapshot(base, names) == step["tree"], (label, "tree", result)
        assert json.dumps(step["result"]) == names.text(json.dumps(result)), (label, step["result"], result)
        for path, expected in step["extra_tree"].items():
            assert snapshot(Path(path), names) == expected, (label, path)
    print(f'{case["name"]}: {len(case["steps"])} passed')
    return len(case["steps"])


def check_launcher_guard(base: Path) -> None:
    game, work, receipts = (base / name for name in ("game", "work", "receipts"))
    build_game(game)
    names = Names()
    before = dict(snapshot(game, names))
    host = Host({"plans": {"7": PLAN_7}}, game, Blobs(base), names)
    install_host(host, receipts)
    try:
        adaptive.run("install", game, base / "assets", work)
    except RuntimeError as exc:
        assert "LocalFileList.json" in str(exc), exc
    else:
        raise AssertionError("the install accepted a launcher size change")
    after = dict(snapshot(game, names))
    for name, digest in before.items():
        if name == "LocalFileList.json" or ("/builtin/" in name and not name.endswith(".tmp")):
            assert after[name] == digest, name
    assert not list(receipts.glob("*/receipt.json"))
    print("launcher guard: refused before commit")


def main(recording: Path, parent: Path, cross_parent: Path) -> None:
    sys.path.insert(0, str(ROOT / "tools"))
    from engine_hooks import install

    with tempfile.TemporaryDirectory(dir=parent) as primary, tempfile.TemporaryDirectory(dir=cross_parent) as cross:
        install(receipts=Path(primary) / "app-receipts")
        from hok_codecs import pc_run

        assert adaptive.run is pc_run, "PC engine hook did not select Rust"
        total = 0
        for line in (recording / "cases.jsonl").read_text(encoding="utf-8").splitlines():
            case = json.loads(line)
            paths = {case["base"]: str(Path(primary) / case["name"])}
            for index, work in enumerate(case.get("extra_work", [])):
                paths[work] = str(Path(cross) / str(index))
            total += replay(relocate(case, paths), recording / "blobs")
        check_launcher_guard(Path(primary) / "launcher-guard")
    print(f"{total} matched through the Windows engine hook")


if __name__ == "__main__":
    main(*(Path(arg).resolve() for arg in sys.argv[1:]))
