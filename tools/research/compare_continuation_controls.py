"""Capture and compare external baseline/change staging controls without building.

Capture after each successful build with the SAME pristine input and dependencies:
  python compare_continuation_controls.py capture --staged OUT --pristine BUILTIN --apk APK --report FILE
Then compare the two reports. Only packages[*].source_package absolute roots are
normalized: a built-in package to `<builtin>/<id>`, a package added from the APK
(`<work>/prime/<id>`) to `<work>/prime/<id>`. All other summary fields, payload files,
delta ranges and asset bodies remain comparison gates; `normalizations` is metadata. This is research tooling, never shipping code.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.append(str(ROOT / "resources" / "runtime"))

import pristine_delta  # noqa: E402

SUMMARY = "device_patch_summary.json"
NORMALIZATIONS = ["packages[*].source_package: builtin-relative",
                  "packages[*].source_package: added-from-apk prime-relative"]


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _manifest(root: Path) -> dict:
    """Hash every ordinary file; refuse links instead of following fixture aliases."""
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or path.is_junction():
            raise ValueError(f"linked input: {path}")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = {
                "size": path.stat().st_size, "sha256": pristine_delta.sha256_file(path),
            }
    return result


def _summary(value: dict) -> dict:
    for package in value.get("packages", []):
        if "source_package" in package:
            path = package["source_package"].replace("\\", "/")
            marker = "/WXQ_Data/Package/builtin/"
            if package.get("mode") == "added-from-apk" and marker not in path:
                # extract_prime copies the APK's package to <work>/prime/<id>.
                if path.rsplit("/", 2)[-2:] != ["prime", str(package.get("package_id"))]:
                    raise ValueError(f"unrecognized prime source path: {path}")
                package["source_package"] = "<work>/prime/" + path.rsplit("/", 1)[1]
                continue
            if marker not in path:
                raise ValueError(f"unrecognized summary source path: {path}")
            relative = path.rsplit(marker, 1)[1]
            if not relative or "/" in relative or relative in {".", ".."}:
                raise ValueError(f"unrecognized package path: {path}")
            package["source_package"] = "<builtin>/" + relative
    return value


def capture(staged: Path, pristine: Path, apk: Path) -> dict:
    """Read-only capture; delta generation reads source/output but writes neither."""
    source = _manifest(pristine)
    output = _manifest(staged)
    raw_summary = json.loads((staged / SUMMARY).read_text(encoding="utf-8"))
    output.pop(SUMMARY)
    delta = pristine_delta.make(pristine, staged, fingerprint=True)
    files = [{"path": item.path, "pristine_size": item.pristine_size,
              "pristine_sha256": item.pristine_sha256, "staged_size": item.staged_size,
              "staged_sha256": item.staged_sha256,
              "ranges": [{"offset": offset, "size": len(data), "sha256": _digest(data)}
                         for offset, data in item.ranges]} for item in delta.files]
    bodies = {package: {name: {"head_size": body.head_size,
                              "record_size": len(body.record), "record_sha256": _digest(body.record),
                              "chunks": [{"raw_size": size, "stored_size": len(data),
                                          "sha256": _digest(data)} for size, data in body.chunks]}
                        for name, body in sorted(kept.items())}
              for package, kept in sorted((delta.bodies or {}).items())}
    return {"schema": 1, "normalizations": NORMALIZATIONS,
            "pristine": source,
            "apk": {"size": apk.stat().st_size, "sha256": pristine_delta.sha256_file(apk)},
            "output": output, "summary": _summary(raw_summary),
            "delta": {"files": files, "assets": delta.assets, "bodies": bodies,
                      "encoded_sha256": _digest(pristine_delta.encode(delta)),
                      "range_bytes": delta.range_bytes, "kept_body_bytes": delta.kept_body_bytes}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    inventory = commands.add_parser("capture")
    inventory.add_argument("--staged", type=Path, required=True)
    inventory.add_argument("--pristine", type=Path, required=True)
    inventory.add_argument("--apk", type=Path, required=True)
    inventory.add_argument("--report", type=Path, required=True)
    compare = commands.add_parser("compare")
    compare.add_argument("baseline", type=Path)
    compare.add_argument("changed", type=Path)
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12):
        parser.error("Use Python 3.12")
    if args.command == "capture":
        # Never overwrite an old control or put evidence inside immutable inputs.
        report = args.report.resolve()
        if any(report.is_relative_to(root.resolve()) for root in (args.pristine, args.staged)):
            parser.error("Report must be outside both input directories")
        if report == args.apk.resolve():
            parser.error("Report must not replace the APK input")
        result = capture(args.staged, args.pristine, args.apk)
        with report.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, sort_keys=True)
        print(f"Captured {len(result['output'])} output files; no parity verdict")
        return 0
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    changed = json.loads(args.changed.read_text(encoding="utf-8"))
    if baseline.get("schema") != 1 or changed.get("schema") != 1:
        parser.error("Unsupported control schema")
    # Which normalizations a capture applied is metadata, not output; a report from an
    # older capture differs there only and stays comparable.
    keys = sorted((set(baseline) | set(changed)) - {"normalizations"})
    differing = [key for key in keys if baseline.get(key) != changed.get(key)]
    print("FAIL differing sections: " + ", ".join(differing) if differing
          else "PASS identical input, output, normalized summary and pristine delta controls")
    return int(bool(differing))


if __name__ == "__main__":
    raise SystemExit(main())
