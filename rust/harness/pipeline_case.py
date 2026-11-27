"""The migration's main app case: one offline pipeline run, held as a manifest of what it wrote.

`rust/DECISIONS.md` ADR-004 holds every file a run writes to the Python pipeline's bytes. A run on
the 1.12 dump writes about 1.1 GB, too much to keep as a case, so this records each output file's
size and SHA-256 plus the staging summary, and compares two such manifests.

    .venv\\Scripts\\python.exe rust\\harness\\pipeline_case.py run --lang en --game <dump> --apk <apk>
        --work <dir> --out <dir> --manifest rust\\app-cases\\pipeline\\en.json [--command <exe> ...]
    .venv\\Scripts\\python.exe rust\\harness\\pipeline_case.py compare <a.json> <b.json>

Without ``--command`` the run is the Python pipeline (``tools/build_device_patch.py``); with it, the
given command takes the same arguments, so a Rust build is held to the same manifest. Codec output
that ADR-010, ADR-026 and ADR-027 judge after decoding still compares byte for byte here; a decoded
comparison joins when a codec's encoder moves to Rust (wave 1).

Migration tooling, run by hand: the exe, the APK and ``tools/`` never import it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
CATALOGS = {"en": ROOT / "resources" / "catalog", "id": ROOT / "resources" / "catalog_id"}
SUMMARY = "device_patch_summary.json"


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def manifest_of(out: pathlib.Path) -> dict:
    """Every file under <out>, by its POSIX path: [size, sha256]; and the staging summary."""
    files = {path.relative_to(out).as_posix(): [path.stat().st_size, _sha256(path)]
             for path in sorted(out.rglob("*")) if path.is_file()}
    summary = out / SUMMARY
    return {"files": files, "summary": json.loads(summary.read_text(encoding="utf-8")) if summary.is_file() else None}


def run(args: argparse.Namespace) -> int:
    for folder in (args.work, args.out):
        if folder.exists():
            shutil.rmtree(folder)
    command = args.command or [sys.executable, str(ROOT / "tools" / "build_device_patch.py")]
    argv = [*command, "--runtime", str(ROOT / "resources" / "runtime"), "--game", str(args.game),
            "--catalog", str(CATALOGS[args.lang]), "--work", str(args.work), "--output", str(args.out)]
    if args.apk:
        argv += ["--apk", str(args.apk)]
    started = time.perf_counter()
    result = subprocess.run(argv, cwd=ROOT)
    seconds = time.perf_counter() - started
    if result.returncode:
        print(f"the pipeline exited {result.returncode}", file=sys.stderr)
        return result.returncode
    record = {"lang": args.lang, "game": str(args.game), "apk": str(args.apk) if args.apk else None,
              "seconds": round(seconds, 1), **manifest_of(args.out)}
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{len(record['files'])} files in {seconds:.1f}s -> {args.manifest}")
    return 0


def compare(args: argparse.Namespace) -> int:
    left, right = (json.loads(path.read_text(encoding="utf-8")) for path in (args.left, args.right))
    problems = []
    if left["summary"] != right["summary"]:
        keys = sorted(set(left["summary"] or {}) | set(right["summary"] or {}))
        changed = [k for k in keys if (left["summary"] or {}).get(k) != (right["summary"] or {}).get(k)]
        problems.append(f"staging summary differs at: {', '.join(changed) or '(the whole summary)'}")
    for name in sorted(set(left["files"]) | set(right["files"])):
        a, b = left["files"].get(name), right["files"].get(name)
        if a != b:
            problems.append(f"{name}: {a and a[0]} bytes {a and a[1][:12]} vs {b and b[0]} bytes {b and b[1][:12]}")
    for line in problems:
        print(line)
    print("identical" if not problems else f"{len(problems)} differences")
    return 1 if problems else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="action", required=True)
    go = sub.add_parser("run")
    go.add_argument("--lang", choices=sorted(CATALOGS), required=True)
    go.add_argument("--game", type=pathlib.Path, required=True)
    go.add_argument("--apk", type=pathlib.Path)
    go.add_argument("--work", type=pathlib.Path, required=True)
    go.add_argument("--out", type=pathlib.Path, required=True)
    go.add_argument("--manifest", type=pathlib.Path, required=True)
    go.add_argument("--command", nargs="+", help="the pipeline to run in place of the Python one")
    same = sub.add_parser("compare")
    same.add_argument("left", type=pathlib.Path)
    same.add_argument("right", type=pathlib.Path)
    args = parser.parse_args()
    return run(args) if args.action == "run" else compare(args)


if __name__ == "__main__":
    sys.exit(main())
