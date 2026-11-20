"""Changed engine/game real controls: saved work is refused, and redone work matches a fresh run.

    .venv\\Scripts\\python.exe tools\\research\\check_changed_input_controls.py ^
        --game-a <pristine dump, older> --game-b <pristine dump, newer> --work <empty dir outside the repo>

Each dump is a patcher pristine folder (`device-backup.tar` in the phone's snapshot layout, plus
`snapshot.json` naming its normal APK). The engine is the Android build's own engine assets
(`android/app/build/generated/engine-assets/engine`, run `:app:assembleDebug` first), unpacked as
`EngineAssets` does. Every call is the real `android_bridge` function: `checkpoint_identity`,
`snapshot_checkpoint`, `build_checkpoint`, `inspect_build_checkpoint` and `copy_completed_checkpoint`.
Only the Kotlin side is stood in for: the measured live files, the producer record and the target.

Cases (five real builds, English):
  1. Same inputs: the saved build is reused with no staging call.
  2. Game change A -> B: the identity and the old build are refused; the rebuild in the same session
     matches a fresh build of B in a new session.
  3. Same-size game change: one live file's hash differs at the same size; refused.
  4. Engine change (one catalog string): the saved build and the completed-output copy are refused,
     the snapshot is kept; the rebuild matches a fresh build with that engine and differs from B's.
  5. Same-size engine change (one byte of a tools comment): refused before any build.
  6. Windows: `windows_producer_identity` over copies of this checkout changes for both engine
     changes, and a staged receipt published under the old producer is refused under each new one.

Research tooling; never shipping code. Needs about 40 GB free under <work>.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "android/app/build/generated/engine-assets/engine"
PATCHER_APK = ROOT / "android/app/build/outputs/apk/debug/app-debug.apk"
TARGET = {"device": "control", "provider": "root", "android_user": 0, "package": "com.tencent.tmgp.osgame"}
REQUEST = {"action": "translate", "language": "en", "options": {}}
READINESS = {"control_closed_and_downloads_finished": True}


def _load_bridge():
    spec = importlib.util.spec_from_file_location("bridge_controls", ROOT / "android/app/src/main/python/android_bridge.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _unpack_engine(destination: Path) -> Path:
    """The Android engine assets as `EngineAssets` lays them out: `.payload` dropped."""
    for source in sorted(ASSETS.rglob("*")):
        if source.is_file():
            relative = source.relative_to(ASSETS).as_posix()
            name = relative[:-len(".payload")] if relative.endswith(".payload") else relative
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    for tool in (ROOT / "tools").glob("*.py"):
        packed = destination / "tools" / tool.name
        if packed.exists() and packed.read_bytes() != tool.read_bytes():
            raise SystemExit(f"Engine assets are stale ({tool.name}); run :app:assembleDebug first")
    return destination


CHANGED_SOURCE = "取消"  # "Cancel" -> "CANCEL"


def _change_catalog(engine: Path) -> str:
    """One English string in the English catalog, as an upstream catalog import would change it.

    A `unique` row, not an `english_updates` row: an update replaces only a previously installed
    translation, so a build from pristine data never applies it. The new value keeps its length.
    """
    path = engine / "catalog/catalog.json.gz"
    catalog = json.loads(gzip.decompress(path.read_bytes()))
    source = CHANGED_SOURCE
    catalog["unique"][source] = catalog["unique"][source].upper()
    path.write_bytes(gzip.compress(json.dumps(catalog, ensure_ascii=False).encode("utf-8"), mtime=0))
    return source


def _change_comment_same_size(tools: Path) -> str:
    """One byte of a comment in a tools module; the file keeps its size."""
    path = tools / "languages.py"
    data = path.read_bytes()
    index = data.index(b"#") + 1
    while data[index:index + 1] in (b" ", b"\r", b"\n"):
        index += 1
    flipped = b"X" if data[index:index + 1] != b"X" else b"Y"
    path.write_bytes(data[:index] + flipped + data[index + 1:])
    assert path.stat().st_size == len(data)
    return path.name


class Controls:
    def __init__(self, work: Path):
        self.work = work
        self.bridge = _load_bridge()
        self.events: list[dict] = []
        self.stage_calls = 0
        original = self.bridge._stage_translation

        def counted(*args, **kwargs):
            self.stage_calls += 1
            return original(*args, **kwargs)
        self.bridge._stage_translation = counted

    def log(self, case: str, verdict: str, **detail) -> None:
        self.events.append({"case": case, "verdict": verdict, **detail})
        print(f"[{verdict}] {case} {json.dumps(detail, ensure_ascii=False)}", flush=True)

    def producer(self, engine: Path) -> dict:
        from run_artifacts import file_identity, identity_key, tree_manifest
        return {"schema": 1, "complete": True, "kind": "android", "components": {
            "installed_apks": {"base.apk": file_identity(PATCHER_APK)},
            "engine": {"manifest_sha256": hashlib.sha256((engine / "manifest.json").read_bytes()).hexdigest(),
                       "files_key": identity_key(tree_manifest(engine))},
            "native": {"packaged_in_apks": True}, "abi": ["control-host"]}}

    def identity(self, engine: Path, session: Path, apk: Path, keep: Path, *, files: dict | None = None,
                 producer: dict | None = None) -> dict:
        from mobile_snapshot import verify_snapshot
        from run_artifacts import file_identity
        if files is None:
            manifest = verify_snapshot(session / "snapshot")
            files = {name: {"size": item["bytes"], "sha256": item["sha256"]} for name, item in manifest["files"].items()}
        value = json.loads(self.bridge.checkpoint_identity(
            str(engine), str(session), str(apk), str(keep), json.dumps(TARGET), json.dumps(REQUEST),
            json.dumps(files), json.dumps(READINESS), json.dumps({"root": file_identity(apk)}),
            json.dumps(producer or self.producer(engine))))
        assert value["reusable"], value
        return value["identity"]

    def session(self, name: str, dump: Path, engine: Path, apk: Path) -> tuple[Path, Path, str, dict]:
        from mobile_snapshot import extract_snapshot
        session, keep = self.work / name, self.work / (name + "-keep")
        session.mkdir()
        keep.mkdir()
        extract_snapshot(dump / "device-backup.tar", session / "snapshot")
        run_id = str(uuid.uuid4())
        identity = self.identity(engine, session, apk, keep)
        self.bridge.snapshot_checkpoint(str(engine), str(session), run_id, json.dumps(identity), True)
        return session, keep, run_id, identity

    def build(self, label: str, engine: Path, session: Path, keep: Path, run_id: str, apk: Path,
              identity: dict) -> dict:
        from run_artifacts import file_identity
        started, calls = time.monotonic(), self.stage_calls
        result = json.loads(self.bridge.build_checkpoint(
            str(engine), str(session), run_id, str(apk), file_identity(apk)["sha256"], "en", str(keep),
            json.dumps(identity)))
        assert self.stage_calls == calls + 1 and result["reusable"], (label, result["reusable"])
        self.log(label, "BUILT", seconds=round(time.monotonic() - started), attempt=result["attempt"],
                 counts=result["summary"].get("counts"))
        return result

    def inspect(self, engine: Path, session: Path, keep: Path, run_id: str, apk: Path, result: dict,
                identity: dict) -> dict:
        calls = self.stage_calls
        try:
            return json.loads(self.bridge.inspect_build_checkpoint(
                str(engine), str(session), run_id, result["attempt"], str(apk), str(keep), json.dumps(identity)))
        finally:
            assert self.stage_calls == calls, "inspect staged"

    def refused(self, case: str, call) -> None:
        try:
            call()
        except Exception as error:  # Every refusal type counts; the message is the evidence.
            self.log(case, "PASS", refused=f"{type(error).__name__}: {error}"[:300])
            return
        self.log(case, "FAIL", refused=None)
        raise AssertionError(case + ": changed input was accepted")

    @staticmethod
    def payload(result: dict) -> dict:
        import pristine_delta
        root = Path(result["result_root"])
        hashes = json.loads((root / "staged-hashes.json").read_text(encoding="utf-8"))
        delta = pristine_delta.read(Path(result["delta_path"]))
        summary = result["summary"]
        ranges = lambda entry: hashlib.sha256(repr(entry.ranges).encode()).hexdigest()
        return {"hashes": hashes,
                "delta": sorted((entry.path, entry.pristine_sha256, entry.staged_sha256, ranges(entry))
                                for entry in delta.files),
                "assets": delta.assets,
                "bodies": hashlib.sha256(repr(sorted((package, sorted(items.items())) for package, items
                                                     in (delta.bodies or {}).items())).encode()).hexdigest(),
                "counts": summary.get("counts"), "skipped": {key: summary.get(key) for key in
                                                              ("text_skipped", "textures_skipped") if key in summary}}

    def same(self, case: str, first: dict, second: dict) -> None:
        a, b = self.payload(first), self.payload(second)
        differing = sorted(name for name in a["hashes"].keys() | b["hashes"].keys()
                           if a["hashes"].get(name) != b["hashes"].get(name))
        if a == b:
            self.log(case, "PASS", files=len(a["hashes"]), counts=a["counts"])
            return
        self.log(case, "FAIL", differing=differing[:20], counts=[a["counts"], b["counts"]],
                 delta_equal=a["delta"] == b["delta"])
        raise AssertionError(case)


def windows_case(controls: Controls, work: Path) -> None:
    from run_artifacts import (canonical_bytes, identity_key, make_input_identity, publish_receipt, tree_manifest,
                               verify_receipt, windows_producer_identity)
    keys = {}
    for label in ("base", "catalog", "same-size"):
        root = work / f"windows-{label}"
        for name in ("app", "tools", "resources"):
            shutil.copytree(ROOT / name, root / name, ignore=shutil.ignore_patterns("__pycache__"))
        if label == "catalog":
            _change_catalog(root / "resources")
        elif label == "same-size":
            _change_comment_same_size(root / "tools")
        producer = windows_producer_identity(root)
        if producer is None:
            controls.log(f"windows producer {label}", "FAIL", producer=None)
            raise AssertionError("windows producer unavailable")
        keys[label] = producer
    distinct = len({identity_key(value) for value in keys.values()}) == 3
    controls.log("windows producer changes for both engine changes", "PASS" if distinct else "FAIL",
                 keys={label: identity_key(value)[:16] for label, value in keys.items()})
    assert distinct

    def identity(producer: dict) -> dict:
        return make_input_identity(
            target={"device": "control", "android_user": 0, "package": "com.tencent.tmgp.osgame", "provider": "adb"},
            request={"action": "translate", "language": "en",
                     "options": {"fit_only": False, "cycle_assets": [], "normal_manifest": "saved-intent"}},
            game={"files": {"packages/1/1.db": {"size": 1, "sha256": "0" * 64}}, "readiness": "control"},
            apks={"normal": {"sha256": "1" * 64}}, delta=None,
            translation={"scope": "complete-producer"}, producer=producer)
    staged = work / "windows-staged"
    staged.mkdir()
    # The layout Checkpoints.publish_build writes: summary, delta and the complete output manifest.
    (staged / "out.bin").write_bytes(b"staged control payload")
    (staged / "delta.pending.bin").write_bytes(b"staged control delta")
    (staged / "device_patch_summary.json").write_bytes(canonical_bytes({"control": True}))
    refs = {"summary": "device_patch_summary.json", "delta": "delta.pending.bin",
            "manifest": "expected-output-manifest.json"}
    files = {name: item for name, item in tree_manifest(staged).items()
             if name not in {refs["summary"], refs["delta"]}}
    (staged / refs["manifest"]).write_bytes(canonical_bytes({"schema": 1, "files": files}))
    publish_receipt(staged, identity=identity(keys["base"]), run_id=str(uuid.uuid4()), stage="staged",
                    references=refs)
    verify_receipt(staged, identity=identity(keys["base"]), stage="staged")
    for label in ("catalog", "same-size"):
        controls.refused(f"windows staged receipt under the {label} producer",
                         lambda label=label: verify_receipt(staged, identity=identity(keys[label]), stage="staged"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game-a", required=True, type=Path)
    parser.add_argument("--game-b", required=True, type=Path)
    parser.add_argument("--work", required=True, type=Path)
    args = parser.parse_args()
    work = args.work.resolve()
    if work.is_relative_to(ROOT) or (work.exists() and any(work.iterdir())):
        parser.error("--work must be a new or empty folder outside the repository")
    work.mkdir(parents=True, exist_ok=True)
    if sys.version_info[:2] != (3, 12):
        parser.error("Python 3.12 only")

    e1 = _unpack_engine(work / "engine-e1")
    sys.path.insert(0, str(e1 / "tools"))
    e2 = work / "engine-e2"
    shutil.copytree(e1, e2)
    changed_source = _change_catalog(e2)
    e3 = work / "engine-e3"
    shutil.copytree(e1, e3)
    changed_tool = _change_comment_same_size(e3 / "tools")
    controls = Controls(work)
    apks = {}
    for label, dump in (("a", args.game_a), ("b", args.game_b)):
        record = json.loads((dump / "snapshot.json").read_text(encoding="utf-8"))
        apk = Path(record["normal_apk"])
        from run_artifacts import file_identity
        if file_identity(apk)["sha256"] != record["normal_apk_sha256"]:
            parser.error(f"{apk} is not the dump's normal APK")
        apks[label] = apk
    controls.log("setup", "INFO", changed_source=changed_source, changed_tool=changed_tool,
                 apks={label: str(path) for label, path in apks.items()})

    # 1. Same inputs.
    s1, k1, run1, id_a = controls.session("s1", args.game_a, e1, apks["a"])
    r1 = controls.build("build A (engine 1)", e1, s1, k1, run1, apks["a"], id_a)
    reused = controls.inspect(e1, s1, k1, run1, apks["a"], r1, id_a)
    ok = reused["attempt"] == r1["attempt"] and reused["reusable"]
    controls.log("same inputs reuse the saved build, no staging call", "PASS" if ok else "FAIL")
    assert ok

    # 2. Game change A -> B, measured live by the coordinator.
    from mobile_snapshot import extract_snapshot, verify_snapshot
    retired = work / "s2-b-snapshot"
    extract_snapshot(args.game_b / "device-backup.tar", retired)
    live_b = {name: {"size": item["bytes"], "sha256": item["sha256"]}
              for name, item in verify_snapshot(retired)["files"].items()}
    controls.refused("game A->B: identity over the old snapshot",
                     lambda: controls.identity(e1, s1, apks["a"], k1, files=live_b))
    (s1 / "snapshot").rename(s1 / "snapshot-retired-a")
    retired.rename(s1 / "snapshot")
    id_b_in_s1 = controls.identity(e1, s1, apks["b"], k1)
    controls.bridge.snapshot_checkpoint(str(e1), str(s1), run1, json.dumps(id_b_in_s1), True)
    controls.refused("game A->B: old build under the new identity",
                     lambda: controls.inspect(e1, s1, k1, run1, apks["b"], r1, id_b_in_s1))
    r2 = controls.build("rebuild B in the continued session", e1, s1, k1, run1, apks["b"], id_b_in_s1)
    s2, k2, run2, id_b = controls.session("s2", args.game_b, e1, apks["b"])
    r3 = controls.build("fresh build B (engine 1)", e1, s2, k2, run2, apks["b"], id_b)
    controls.same("game A->B: rebuild equals fresh build", r2, r3)

    # 3. Same-size game change.
    name = next(name for name, item in sorted(live_b.items()) if name.startswith("packages/") and item["size"] > 0)
    changed = copy.deepcopy(live_b)
    changed[name]["sha256"] = "f" * 64
    controls.refused(f"same-size game change ({name})",
                     lambda: controls.identity(e1, s2, apks["b"], k2, files=changed))

    # 4. Engine change: one catalog string.
    id_b_e2 = controls.identity(e2, s2, apks["b"], k2)
    controls.refused("engine change: saved build under the new engine",
                     lambda: controls.inspect(e2, s2, k2, run2, apks["b"], r3, id_b_e2))
    from run_artifacts import file_identity
    completion = file_identity(Path(r3["result_root"]) / "build-receipt.json")["sha256"]
    controls.refused("engine change: completed-output copy",
                     lambda: controls.bridge.copy_completed_checkpoint(
                         str(e2), str(s2), run2, str(apks["b"]), str(k2), json.dumps(id_b_e2),
                         r3["result_root"], completion))
    controls.bridge.snapshot_checkpoint(str(e2), str(s2), run2, json.dumps(id_b_e2), False)
    controls.log("engine change keeps the snapshot", "PASS")
    r4 = controls.build("rebuild B with engine 2 in the continued session", e2, s2, k2, run2, apks["b"], id_b_e2)
    s3, k3, run3, id_b_fresh_e2 = controls.session("s3", args.game_b, e2, apks["b"])
    r5 = controls.build("fresh build B (engine 2)", e2, s3, k3, run3, apks["b"], id_b_fresh_e2)
    controls.same("engine change: rebuild equals fresh build", r4, r5)
    before, after = controls.payload(r3)["hashes"], controls.payload(r4)["hashes"]
    moved = sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))
    controls.log("engine change reaches the output", "PASS" if moved else "FAIL", changed_files=moved)
    assert moved, "the catalog change did not reach the staged output"

    # 5. Same-size engine change.
    controls.refused("same-size engine change: identity with the old producer",
                     lambda: controls.identity(e3, s2, apks["b"], k2, producer=controls.producer(e1)))
    id_b_e3 = controls.identity(e3, s2, apks["b"], k2)
    controls.refused("same-size engine change: saved build",
                     lambda: controls.inspect(e3, s2, k2, run2, apks["b"], r3, id_b_e3))

    # 6. Windows producer.
    windows_case(controls, work)

    (work / "report.json").write_text(json.dumps(controls.events, indent=2, ensure_ascii=False), encoding="utf-8")
    failed = [event for event in controls.events if event["verdict"] == "FAIL"]
    print(f"{'FAIL' if failed else 'PASS'}: {sum(e['verdict'] == 'PASS' for e in controls.events)} checks passed; "
          f"report {work / 'report.json'}")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
