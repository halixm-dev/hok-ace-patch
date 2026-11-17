"""Offline identity/receipt mutation and publication probes; never accesses a phone.

Run with Python 3.12 from the repository root. Temporary tiny fixtures are generated
outside the repository and removed by TemporaryDirectory. No game dump is required.
"""
from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).absolute().parents[1]))
import run_artifacts as artifacts

VECTORS = Path(__file__).parent / "fixtures/run_artifacts/vectors.json"


def _refused(call) -> None:
    try:
        call()
    except (artifacts.ArtifactError, OSError):
        return
    raise AssertionError("Unsafe/incomplete content was reusable")


def _identity() -> dict:
    value = json.loads(VECTORS.read_text(encoding="utf-8"))["receipt"]["identity"]
    return copy.deepcopy(value)


def _stage(root: Path) -> dict:
    (root / "1").mkdir()
    (root / "1/1_0.db").write_bytes(b"tiny staged package")
    (root / "device_patch_summary.json").write_text("{}", encoding="utf-8")
    (root / "pristine-delta.bin").write_bytes(b"fixture delta bytes; not a real game delta")
    payload = {"1/1_0.db": artifacts.file_identity(root / "1/1_0.db")}
    (root / "expected-output-manifest.json").write_bytes(artifacts.canonical_bytes({"schema": 1, "files": payload}))
    return {"summary": "device_patch_summary.json", "delta": "pristine-delta.bin", "manifest": "expected-output-manifest.json"}


def _publication() -> None:
    identity = _identity()
    for boundary in ("artifacts_verified", "artifacts_synced", "receipt_synced", "receipt_committed", "receipt_read_back"):
        for old in (False, True):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                refs = _stage(root)
                if old:
                    artifacts.publish_receipt(root, identity=identity, run_id="old", stage="staged", references=refs)
                def kill(name: str) -> None:
                    if name == boundary:
                        raise InterruptedError(boundary)
                try:
                    artifacts.publish_receipt(root, identity=identity, run_id="new", stage="staged", references=refs, failpoint=kill)
                except InterruptedError:
                    pass
                else:
                    raise AssertionError("Publication boundary was not reached")
                # A kill is allowed to leave no checkpoint. A readable checkpoint must
                # still prove the exact old/new content, never an incomplete stage.
                try:
                    receipt = artifacts.verify_receipt(root, identity=identity, stage="staged")
                except artifacts.ArtifactError:
                    assert boundary == "receipt_synced" or (not old and boundary in {"artifacts_verified", "artifacts_synced"})
                else:
                    assert receipt["run_id"] == ("new" if boundary in {"receipt_committed", "receipt_read_back"} else "old")


def _mutations() -> None:
    identity = _identity()
    for component in ("target", "request", "game", "apks", "delta", "translation", "producer"):
        changed = copy.deepcopy(identity)
        if changed[component] is None:
            changed[component] = {"explicit_presence": True}
        else:
            changed[component]["changed_input"] = True
        assert artifacts.identity_key(changed) != artifacts.identity_key(identity), component
    # Every byte-level producer component must participate, including same-size bytes.
    for component in identity["producer"]["components"]:
        changed = copy.deepcopy(identity)
        changed["producer"]["components"][component] = {"size": 1, "sha256": "f" * 64}
        assert artifacts.identity_key(changed) != artifacts.identity_key(identity), component
    for component in identity["translation"]:
        changed = copy.deepcopy(identity)
        changed["translation"][component]["sha256"] = "f" * 64
        assert artifacts.identity_key(changed) != artifacts.identity_key(identity), component
    for name, value in (("device", None), ("provider", ""), ("package", " "), ("android_user", True), ("android_user", -1)):
        bad = copy.deepcopy(identity); bad["target"][name] = value
        _refused(lambda: artifacts.make_input_identity(**{key: item for key, item in bad.items() if key != "schema"}))
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        refs = _stage(root)
        receipt = artifacts.publish_receipt(root, identity=identity, run_id="first", stage="staged", references=refs)
        second = artifacts.publish_receipt(root, identity=identity, run_id="later", stage="staged", references=refs)
        assert receipt["input_key"] == second["input_key"], "Run provenance defeated reuse"
        payload = root / "1/1_0.db"
        original = payload.read_bytes()
        payload.write_bytes(b"X" * len(original))
        _refused(lambda: artifacts.verify_receipt(root))
        payload.write_bytes(original)
        (root / "extra").write_bytes(b"unexpected")
        _refused(lambda: artifacts.verify_receipt(root))
        (root / "extra").unlink()
        payload.unlink()
        _refused(lambda: artifacts.verify_receipt(root))
        payload.write_bytes(original)
        for field, value in (("schema", 999), ("committed", False), ("producer_key", "0" * 64)):
            bad = copy.deepcopy(second); bad[field] = value
            (root / artifacts.RECEIPT_NAME).write_bytes(artifacts.canonical_bytes(bad))
            _refused(lambda: artifacts.verify_receipt(root))
        (root / artifacts.RECEIPT_NAME).write_bytes(artifacts.canonical_bytes(second))
        for bad_producer in (None, {}, {"schema": 1, "kind": "windows-frozen", "complete": False, "components": {}}):
            bad = copy.deepcopy(identity); bad["producer"] = bad_producer
            _refused(lambda: artifacts.publish_receipt(root, identity=bad, run_id="bad", stage="staged", references=refs))
        # Links/hard links may never turn retained output into mutable rollback input.
        alias = root / "alias"
        os.link(payload, alias)
        _refused(lambda: artifacts.verify_receipt(root))
        alias.unlink()
        try:
            alias.symlink_to(payload)
        except OSError:
            print("SKIP symlink creation: host permission unavailable; path/traversal checks still run")
        else:
            _refused(lambda: artifacts.verify_receipt(root))
            alias.unlink()
            alias.symlink_to(root / "1", target_is_directory=True)
            _refused(lambda: artifacts.tree_manifest(alias))
            alias.unlink()
        (root / artifacts.RECEIPT_NAME).unlink()
        _refused(lambda: artifacts.verify_receipt(root))
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "device_patch_summary.json").write_text("{}", encoding="utf-8")
        _refused(lambda: artifacts.publish_receipt(root, identity=identity, run_id="summary-only", stage="staged",
            references={"summary": "device_patch_summary.json", "delta": None, "manifest": None}))
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        refs = _stage(root)
        removal = copy.deepcopy(identity); removal["request"]["action"] = "remove"
        (root / refs["delta"]).unlink(); refs["delta"] = None
        artifacts.publish_receipt(root, identity=removal, run_id="remove", stage="staged", references=refs)
        artifacts.verify_receipt(root, identity=removal)


def _source_and_frozen() -> None:
    with tempfile.TemporaryDirectory() as directory:
        top = Path(directory); root = top / "source"; root.mkdir()
        consumed = ("app/code.py", "tools/transform.py", "resources/runtime/runtime.pyc",
                    "resources/catalog/catalog.json.gz", "resources/catalog/fallback.blocks",
                    "resources/catalog_id/catalog.json.gz", "resources/catalog_id/payload.blocks",
                    "resources/sprites/labels/title.png")
        for name in consumed:
            path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b"A")
        python = top / "python"; python.mkdir(); (python / "python.exe").write_bytes(b"A")
        dependency = top / "dependencies"; dependency.mkdir(); (dependency / "codec.pyd").write_bytes(b"A")
        native = top / "native.dll"; native.write_bytes(b"A")
        def native_identity():
            return {"0": artifacts.file_identity(native)}
        with patch.object(artifacts, "_windows_native_identity", native_identity), \
             patch.object(sys, "base_prefix", str(python)), patch.object(sys, "prefix", str(python)), \
             patch.object(sys, "executable", str(python / "python.exe")), \
             patch.object(sys, "path", [str(root), str(root / "tools"), str(dependency)]):
            before = artifacts.windows_producer_identity(root)
            assert before is not None
            for path in [*(root / name for name in consumed), python / "python.exe", dependency / "codec.pyd", native]:
                path.write_bytes(b"B")
                assert artifacts.windows_producer_identity(root) != before, path
                path.write_bytes(b"A")
            # Removing a required producer component disables reuse altogether.
            (root / "tools/transform.py").unlink(); (root / "tools").rmdir()
            assert artifacts.windows_producer_identity(root) is None
        bundle = top / "bundle"; bundle.mkdir(); (bundle / "codec.dll").write_bytes(b"A")
        exe = top / "patcher.exe"; exe.write_bytes(b"A")
        with patch.object(artifacts, "_windows_native_identity", native_identity), \
             patch.object(sys, "frozen", True, create=True), patch.object(sys, "_MEIPASS", str(bundle), create=True), \
             patch.object(sys, "executable", str(exe)):
            before = artifacts.windows_producer_identity()
            assert before is not None
            for path in (exe, bundle / "codec.dll", native):
                path.write_bytes(b"B")
                assert artifacts.windows_producer_identity() != before, path
                path.write_bytes(b"A")


def _installed_keys() -> None:
    """Same-length byte identities and every output-affecting request/producer must invalidate."""
    identity = _identity()
    files = {"packages/1/1.db": {"size": 4, "sha256": "a" * 64}}
    normal = {"size": 4, "sha256": "b" * 64, "debuggable": False}
    delta = {"delta.bin": {"size": 4, "sha256": "c" * 64}, "staged-hashes.json": None}
    key = artifacts.installed_state_key(identity, files=files, installed=normal, delta=delta)
    for changed in ({}, {"packages/1/1.db": {"size": 4, "sha256": "d" * 64}}):
        assert artifacts.installed_state_key(identity, files=changed, installed=normal, delta=delta) != key
    assert artifacts.installed_state_key(identity, files=files, installed={**normal, "sha256": "d" * 64}, delta=delta) != key
    assert artifacts.installed_state_key(identity, files=files, installed=normal, delta={**delta, "delta.bin": None}) != key
    for name in ("language", "options"):
        changed = copy.deepcopy(identity)
        changed["request"][name] = "id" if name == "language" else {"cycle_assets": ["measured-candidate"]}
        assert artifacts.installed_state_key(changed, files=files, installed=normal, delta=delta) != key
    for component in ("app", "tools", "resources", "python", "native", "executable"):
        changed = copy.deepcopy(identity)
        evidence = changed["producer"]["components"].get(component)
        if evidence is None:
            continue
        def mutate(value: object) -> bool:
            if isinstance(value, dict):
                for field in ("sha256", "manifest_key"):
                    if field in value:
                        value[field] = "d" * 64; return True
                return any(mutate(item) for item in value.values())
            return False
        assert mutate(evidence)
        assert artifacts.installed_state_key(changed, files=files, installed=normal, delta=delta) != key


def main() -> None:
    assert sys.version_info[:2] == (3, 12), "Use the project's Python 3.12 environment"
    vectors = json.loads(VECTORS.read_text(encoding="utf-8"))
    for vector in vectors["canonical"]:
        assert artifacts.canonical_bytes(vector["value"]).decode("utf-8") == vector["canonical"]
        assert artifacts.identity_key(vector["value"]) == vector["key"]
    for name in vectors["invalid_paths"]:
        _refused(lambda: artifacts.relative_path(name))
    _refused(lambda: artifacts.validate_manifest({"A": {"size": 1, "sha256": "0" * 64}, "a": {"size": 1, "sha256": "0" * 64}}))
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "record.json"
        for text in vectors["invalid_json"]:
            path.write_text(text, encoding="utf-8")
            _refused(lambda: artifacts.read_record(path))
        path.write_bytes(b" " * (artifacts.MAX_JSON + 1))
        _refused(lambda: artifacts.read_record(path))
    _publication(); _mutations(); _source_and_frozen(); _installed_keys()
    print("PASS run artifact identities, byte mutations and all publication boundaries")


if __name__ == "__main__":
    main()
