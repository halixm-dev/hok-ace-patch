"""Run one tree's android_bridge.build_snapshot on desktop and record its staged hashes and timing.

usage: bridge_equivalence.py <repo> <work> <layer> <apk> <scenario: first|rebuilt> [<staged-dir> <keep-src>]
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

repo, work, layer, apk, scenario = map(Path, sys.argv[1:6])
scenario = str(scenario)
staged_dir = Path(sys.argv[6]) if len(sys.argv) > 6 else None
keep_src = Path(sys.argv[7]) if len(sys.argv) > 7 else None
if work.exists():
    shutil.rmtree(work)
engine, session, keep = work / "engine", work / "session", work / "keep"
engine.mkdir(parents=True)
for name in ("runtime", "catalog", "catalog_id", "sprites", "key"):
    subprocess.run(["cmd", "/c", "mklink", "/J", str(engine / name), str(repo / "resources" / name)],
                   check=True, capture_output=True)
(engine / "tools").mkdir()
for path in (repo / "tools").glob("*.py"):
    shutil.copy2(path, engine / "tools" / path.name)
shutil.copy2(repo / "app" / "apk_tools.py", engine / "tools" / "apk_tools.py")

# The snapshot: hard links to the layer, with the staged files laid over it for a rebuild.
packages = session / "snapshot" / "packages"
files = {}
for path in layer.rglob("*"):
    if not path.is_file():
        continue
    relative = path.relative_to(layer).as_posix()
    source = staged_dir / relative if staged_dir and (staged_dir / relative).is_file() else path
    target = packages / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    os.link(source, target)
    with source.open("rb") as stream:
        files["packages/" + relative] = {"bytes": source.stat().st_size,
                                         "sha256": hashlib.file_digest(stream, "sha256").hexdigest()}
(session / "snapshot" / "Watchdog").mkdir()
(session / "snapshot" / "manifest.json").write_text(json.dumps({"schema": 1, "files": files, "directories": []}))
keep.mkdir()
if keep_src:
    for name in ("delta.bin", "staged-hashes.json"):
        shutil.copy2(keep_src / name, keep / name)

sys.path.insert(0, str(repo / "android/app/src/main/python"))
import android_bridge  # noqa: E402

with apk.open("rb") as stream:
    apk_sha = hashlib.file_digest(stream, "sha256").hexdigest()
started = time.monotonic()
estimate = json.loads(android_bridge.estimate_snapshot_build(str(engine), str(session), str(apk), "en", str(keep)))
estimated = time.monotonic()
summary = json.loads(android_bridge.build_snapshot(str(engine), str(session), str(apk), apk_sha, "en", str(keep)))
finished = time.monotonic()
staged = json.loads((session / "staged-hashes.json").read_text())
build = json.loads((session / "metrics.json").read_text())["elapsed_seconds"]
result = {"repo": str(repo), "scenario": scenario, "estimate_seconds": round(estimated - started, 1),
          "build_snapshot_seconds": round(finished - estimated, 1), "internal_build_seconds": round(build, 1),
          "pristine": summary.get("pristine"), "counts": summary.get("counts"),
          "text_skipped": summary.get("text_skipped"), "graphics_skipped": summary.get("graphics_skipped"),
          "append_skipped": summary.get("append_skipped"), "staged": staged,
          "delta_sha256": hashlib.sha256((session / "pristine-delta.bin").read_bytes()).hexdigest()}
(work / "result.json").write_text(json.dumps(result, indent=1))
print(json.dumps({k: v for k, v in result.items() if k != "staged"}, indent=1))
print(f"{len(staged)} staged files")
