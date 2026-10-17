"""Check every packaged engine payload against the manifest and repository bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    optimized = {}
    with zipfile.ZipFile(args.apk) as apk:
        manifest_bytes = apk.read("assets/engine/manifest.json")
        manifest = json.loads(manifest_bytes)["files"]
        for name, expected in manifest.items():
            assert not name.startswith("/") and ".." not in name.split("/"), name
            payload = apk.read(f"assets/engine/{name}.payload")
            assert hashlib.sha256(payload).hexdigest() == expected, name
            if name.startswith("tools/"):
                basename = Path(name).name
                source = ROOT / ("app" if basename == "apk_tools.py" else "tools") / basename
            elif name.startswith("notices/"):
                source = ROOT / "android/native/licenses" / name.removeprefix("notices/")
            else:
                source = ROOT / "resources" / name
            assert payload == source.read_bytes(), f"repository differs: {name}"
            if name in ("tools/qts_relocate.py", "tools/mobile_graphics.py", "tools/build_device_patch.py"):
                optimized[name] = expected
        assert len(optimized) == 3
        assert not any("/research/" in name or "/.scratch/" in name for name in apk.namelist())
    with args.apk.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    result = {"apk": str(args.apk.resolve()), "sha256": digest,
              "engine_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
              "payloads_verified": len(manifest), "all_payloads_match_manifest_and_repository": True,
              "optimized_modules": optimized, "research_not_bundled": True}
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
