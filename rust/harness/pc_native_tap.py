"""Record the PC engine's calls into the game's QtsVFS for the Rust port to replay (wave 2, ADR-021).

The runtime's ``package_metadata`` (``query_package_hash``, ``stage_package_hash_metadata_batch``)
and ``native_verify.verify_staged_package`` load the installed game's ``QtsVFS.dll`` and
``QtskDB.dll``. This records them on the installed game, read only, with every copy and staged
package under ``<work>``:

- ``query``: each listed package's hash through QtsVFS, and every error the runtime raises before
  or after loading the DLLs (no internal package, no DLL folder, a bad package folder, a package
  QtsVFS will not mount);
- ``stage_batch``: the internal index restaged with unchanged, changed and refused hashes;
- ``verify``: a copied package read back through QtsVFS with right and wrong replacements, an
  asset QtsVFS cannot open (the structural fallback), every unrelated asset, a staged package on
  another volume (the hard links fail and it is copied), and, with ``--stage <catalog-folder>``,
  every ``verify_staged_package`` call ``stage_unity_package`` makes while staging the game as
  ``adaptive._run`` does.

Each line of ``<dir>/calls.jsonl`` is ``{"fn", "args", "result"}``; ``result`` is ``{"ok": ...}``
or ``{"error": "Class: message"}``. Replacement bytes are blobs under ``<dir>/blobs/<sha256>``. A
``verify`` call also names ``staged_copy``, a snapshot of the staged package taken at the call, so
the replay reads what the runtime read.

    .venv\\Scripts\\python.exe rust\\harness\\pc_native_tap.py <dir> <game> <work> [<cross-volume-work>] [--stage <catalog-folder>]
    cargo run --release -p hokace-qtsvfs --example native_replay -- <dir>

``<work>`` is wiped first. The game is never written. Migration tooling, run by hand: the exe, the
APK and ``tools/`` never import it.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import os
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
QUERY_PACKAGES = ("30", "14", "10", "2", "1", "0")


def _runtime():
    sys.path[:0] = [str(ROOT / "tools")]
    sys.path.append(str(ROOT / "resources" / "runtime"))
    from wxq_patch import native_verify, package_metadata, qtsvfs
    return native_verify, package_metadata, qtsvfs


def _error(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


class Tap:
    def __init__(self, out: pathlib.Path) -> None:
        self.out = out
        self.blobs = out / "blobs"
        self.blobs.mkdir(parents=True, exist_ok=True)
        self.calls = (out / "calls.jsonl").open("w", encoding="utf-8")
        self.count = 0

    def keep(self, data: bytes) -> str:
        digest = hashlib.sha256(data).hexdigest()
        path = self.blobs / digest
        if not path.exists():
            path.write_bytes(data)
        return digest

    def write(self, fn: str, args, result: dict, **extra) -> None:
        line = {"fn": fn, "args": args, "result": result, **extra}
        self.calls.write(json.dumps(line, ensure_ascii=False) + "\n")
        self.calls.flush()
        self.count += 1
        print(f"{fn} {str(args)[:110]} -> {str(result)[:150]}", flush=True)


def capture(tap: Tap, game: pathlib.Path, work: pathlib.Path, xvol: pathlib.Path | None,
            stage_catalog: pathlib.Path | None) -> None:
    native_verify, metadata, qtsvfs = _runtime()
    builtin = game / "WXQ_Data" / "Package" / "builtin"

    def query(package_dir: pathlib.Path, at: pathlib.Path = game) -> int | None:
        try:
            value = metadata.query_package_hash(at, package_dir)
            result = {"ok": value}
        except Exception as exc:  # noqa: BLE001 - the class and message are the recording
            value, result = None, {"error": _error(exc)}
        tap.write("query", [str(at), str(package_dir)], result)
        return value

    hashes: dict[str, int] = {}
    for name in QUERY_PACKAGES:
        value = query(builtin / name)
        if value is not None:
            hashes[name] = value
    bare = work / "bare-game"  # its own folder, so each fixture stays as the call found it
    (bare / "WXQ_Data" / "Package" / "builtin").mkdir(parents=True)
    query(builtin / "30", bare)  # no internal package
    fake = work / "fake-game"
    (fake / "WXQ_Data" / "Package" / "builtin").mkdir(parents=True)
    shutil.copytree(builtin / "0", fake / "WXQ_Data" / "Package" / "builtin" / "0")
    query(builtin / "30", fake)  # no DLL folder
    query(game / "WXQ_Data", game)  # not a decimal folder
    query(builtin / "99999999", game)  # missing
    broken = work / "broken" / "30"
    shutil.copytree(builtin / "30", broken)
    index = broken / "30.db"
    index.write_bytes(index.read_bytes()[: 106_496 + 64])
    query(broken)  # QtsVFS refuses the package
    empty = work / "empty" / "31"
    empty.mkdir(parents=True)
    query(empty)

    def stage(package_hashes, label: str) -> None:
        output = work / "stage" / label / "0.db"
        try:
            result = {"ok": metadata.stage_package_hash_metadata_batch(game, package_hashes, output)}
        except Exception as exc:  # noqa: BLE001
            result = {"error": _error(exc)}
        args = [str(game), list(package_hashes.items()) if isinstance(package_hashes, dict) else package_hashes,
                str(output)]
        tap.write("stage_batch", args, result)

    index_data = (builtin / "0" / "0.db").read_bytes()
    before = {name: metadata.find_package_hash_entry(builtin / "0" / "0.db", name)["hash"]
              for name in ("1", "2", "10", "14", "30")}
    stage(dict(hashes), "same")
    stage({"30": before["30"] ^ 0xFFFF_FFFF_FFFF_FFFF}, "flipped")
    stage({"2": before["2"] ^ 0xFFFF_FFFF_FFFF_FFFF, "10": before["10"] ^ 0x0101_0101_0101_0101,
           "1": before["1"]}, "several")
    stage({"14": before["14"] ^ 0xFF}, "kept-byte")  # seven bytes stay in place
    stage({"14": 0}, "zero")
    stage({"30": 2**64 - 1}, "max")
    stage({}, "empty")
    stage({"": 1}, "empty-name")
    stage({"30": -1}, "negative")
    stage({"30": 2**64}, "too-big")
    stage({"30": "1"}, "text")
    stage({"30": None}, "none")
    stage({"absent": 1}, "absent")
    stage({"30": 1, "absent": 2}, "one-absent")
    del index_data

    def verify(source: pathlib.Path, staged: pathlib.Path, replacements: dict[int, bytes], label: str,
               verify_all: bool = False, at: pathlib.Path = game) -> None:
        target = work / "verify" / label
        try:
            result = {"ok": native_verify.verify_staged_package(
                at, source, staged, replacements, target, verify_all_unrelated=verify_all)}
        except Exception as exc:  # noqa: BLE001
            result = {"error": _error(exc)}
        tap.write("verify", [str(at), str(source), str(staged),
                             [[f"{h:016X}", tap.keep(data)] for h, data in replacements.items()],
                             str(target), verify_all], result, staged_copy=str(staged))

    source = builtin / "30"
    package = qtsvfs.QtsPackage(source)
    assets = list(package.entries)
    picks = assets[:: max(1, len(assets) // 4)][:4]
    originals = {h: package.extract(h) for h in picks}
    copy = work / "copies" / "same" / "30"
    shutil.copytree(source, copy)
    verify(source, copy, originals, "native")
    verify(source, copy, {picks[0]: originals[picks[0]] + b"!"}, "mismatch")
    verify(source, copy, {**originals, 0x0123456789ABCDEF: b"absent"}, "unknown-hash")
    verify(source, copy, {}, "nothing")
    verify(source, copy, {picks[1]: originals[picks[1]]}, "all-unrelated", verify_all=True)
    verify(source, copy, {picks[1]: b"changed"}, "all-unrelated-mismatch", verify_all=True)
    # The staged copy keeps the source's bytes, so its hash reads but a different payload does not.
    shard = copy.parent.parent / "shard" / "30"
    shutil.copytree(source, shard)
    slots = list(qtsvfs.iter_chunk_slots(shard / "30_0.db"))
    victim = next(s for s in slots if s.file_hash == picks[2])
    with (shard / "30_0.db").open("r+b") as handle:
        handle.seek(victim.payload_offset)
        data = bytearray(handle.read(min(64, victim.compressed_size)))
        handle.seek(victim.payload_offset)
        handle.write(bytes(b ^ 0x5A for b in data))
    verify(source, shard, {picks[2]: originals[picks[2]]}, "corrupt-payload")
    verify(source, shard, {picks[3]: originals[picks[3]]}, "corrupt-unrelated", verify_all=True)
    orphan = work / "orphan" / "30"
    shutil.copytree(source, orphan)
    verify(orphan, copy, originals, "no-internal", at=fake)
    if xvol is not None:
        far = xvol / "30"
        shutil.rmtree(xvol, ignore_errors=True)
        shutil.copytree(source, far)
        verify(source, far, originals, "cross-volume")
    if stage_catalog is not None:
        capture_stage(tap, game, work, stage_catalog, native_verify)


def capture_stage(tap: Tap, game: pathlib.Path, work: pathlib.Path, catalog: pathlib.Path,
                  native_verify) -> None:
    """Each ``verify_staged_package`` call of staging the game as ``adaptive._run`` stages it."""
    from engine_hooks import install
    from wxq_patch import adaptive, unity_package_installer

    install()
    original = native_verify.verify_staged_package
    snapshots = work / "snapshots"

    signature = inspect.signature(original)

    def tapped(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        game_dir, source, staged, replacements, target, verify_all_unrelated = bound.arguments.values()
        copy = snapshots / str(tap.count) / pathlib.Path(staged).name
        shutil.copytree(staged, copy)
        try:
            result = {"ok": original(game_dir, source, staged, replacements, target,
                                     verify_all_unrelated=verify_all_unrelated)}
        except Exception as exc:  # noqa: BLE001
            result = {"error": _error(exc)}
            raise
        finally:
            tap.write("verify", [str(game_dir), str(source), str(staged),
                                 [[f"{h:016X}", tap.keep(data)] for h, data in sorted(replacements.items())],
                                 str(target), verify_all_unrelated], result, staged_copy=str(copy))
        return result["ok"]

    native_verify.verify_staged_package = tapped
    try:
        scan_work = work / "scan"
        plans, fingerprints, _, _ = adaptive.scan(game, catalog, scan_work, materialize=True)
        for package, replacements, _ in plans:
            stage = work / "staged" / package.package_id
            source_hashes = {}
            for path in (package.index_path, *package.shard_paths):
                source_hashes[path.name] = fingerprints[str(path.relative_to(game))]
            try:
                unity_package_installer.stage_unity_package(
                    game, replacements, stage, source_package_dir=package.package_dir,
                    global_donations=True, verify_all_unrelated=False, source_hashes=source_hashes)
            except Exception as exc:  # noqa: BLE001 - the verify call is recorded either way
                print(f"stage {package.package_id}: {_error(exc)}", flush=True)
    finally:
        native_verify.verify_staged_package = original


def main() -> int:
    argv = sys.argv[1:]
    stage_catalog = None
    if "--stage" in argv:
        at = argv.index("--stage")
        stage_catalog = pathlib.Path(argv[at + 1])
        del argv[at:at + 2]
    if len(argv) not in (3, 4):
        print(__doc__)
        return 2
    out, game, work = map(pathlib.Path, argv[:3])
    xvol = pathlib.Path(argv[3]) if len(argv) == 4 else None
    os.environ["HOK_CODECS"] = "python"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    shutil.rmtree(out, ignore_errors=True)
    tap = Tap(out)
    try:
        capture(tap, game.resolve(), work.resolve(), xvol, stage_catalog)
    finally:
        tap.calls.close()
    print(f"{tap.count} calls -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
