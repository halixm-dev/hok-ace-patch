"""Differential: mobile_snapshot.package_files_at(manifest) equals pristine_delta.files_at(dir) on real layers."""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[1]) / "tools"))
import pristine_delta  # noqa: E402
from mobile_snapshot import package_files_at  # noqa: E402

staged = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))["sha256"]
known = set(staged)
for layer in map(Path, sys.argv[3:]):
    files = {}
    for path in layer.rglob("*"):
        if path.is_file():
            with path.open("rb") as stream:
                files["packages/" + path.relative_to(layer).as_posix()] = {
                    "bytes": path.stat().st_size, "sha256": hashlib.file_digest(stream, "sha256").hexdigest()}
    manifest = {"schema": 1, "files": files}
    for hashes in (known, set(), {next(iter(known))}, {e["sha256"] for e in files.values()}):
        old, new = pristine_delta.files_at(layer, hashes), package_files_at(manifest, hashes)
        assert old == new, (layer, len(hashes), old, new)
    print(f"{layer}: {len(files)} files, at staged hashes: {pristine_delta.files_at(layer, known)} -- equal")
