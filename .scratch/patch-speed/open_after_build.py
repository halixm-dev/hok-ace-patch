"""After an in-process build_snapshot (as Chaquopy runs it), list files and mappings still open under the session.

usage: open_after_build.py <repo> <prepared work dir from bridge_equivalence.py> <apk>
"""
import gc
import hashlib
import json
import shutil
import sys
from pathlib import Path



repo, work, apk = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
session = work / "session"
for name in ("game", "work", "out", "pristine", "normal.apk", "control.json", "staged-hashes.json",
             "metrics.json", "build.log", "pristine-delta.bin"):
    path = session / name
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)
sys.path.insert(0, str(repo / "android/app/src/main/python"))
import android_bridge  # noqa: E402

with apk.open("rb") as stream:
    digest = hashlib.file_digest(stream, "sha256").hexdigest()
json.loads(android_bridge.estimate_snapshot_build(str(work / "engine"), str(session), str(apk), "en", str(work / "keep")))
json.loads(android_bridge.build_snapshot(str(work / "engine"), str(session), str(apk), digest, "en", str(work / "keep")))
gc.collect()
# Windows refuses to delete a file this process still has open or mapped: each refusal is a held file.
held = []
for name in ("work", "out", "pristine", "game", "snapshot"):
    path = session / name
    if path.exists():
        shutil.rmtree(path, onexc=lambda function, failed, error: held.append((failed, type(error).__name__)))
print(f"files still held by the process after the build: {len(held)}")
for failed, error in held[:40]:
    print(f"  {error}: {failed}")
