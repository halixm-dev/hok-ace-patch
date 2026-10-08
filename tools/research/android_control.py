"""Capture a versioned desktop control and portability inventory without any device writes."""
from __future__ import annotations

import argparse
import dis
import hashlib
import json
import marshal
import subprocess
import sys
import types
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "app"))
sys.path.append(str(ROOT / "resources" / "runtime"))


def sha256(path: Path) -> str:
    """Hash a large input without loading it into memory."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inventory(folder: Path) -> dict[str, str]:
    return {path.relative_to(folder).as_posix(): sha256(path)
            for path in sorted(folder.rglob("*")) if path.is_file() and "__pycache__" not in path.parts}


def imports(code: types.CodeType) -> set[str]:
    result = {str(op.argval) for op in dis.get_instructions(code) if op.opname == "IMPORT_NAME"}
    for value in code.co_consts:
        if isinstance(value, types.CodeType):
            result |= imports(value)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="completed DLL-free pipeline output")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12):
        parser.error("Python 3.12 is required")
    from apk_tools import signed_with
    from axml_set_debuggable import is_debuggable
    from patcher_core import count_translated, count_untranslated_graphics, count_untranslated_text
    from qts_relocate import install_btree_slot_map, read_raw
    from wxq_patch.qtsvfs import QtsPackage

    snapshot = json.loads((args.snapshot / "snapshot.json").read_text(encoding="utf-8"))
    game = args.snapshot / "game" / "WXQ_Data" / "Package" / "builtin"
    verified = {}
    for name, expected in snapshot["device_sha256"].items():
        relative = Path(name).relative_to("packages")
        actual = sha256(game / relative)
        if actual != expected:
            raise RuntimeError(f"Pristine snapshot changed: {name}")
        verified[relative.as_posix()] = actual
    apk_hash = sha256(args.apk)
    if apk_hash != snapshot["normal_apk_sha256"]:
        raise RuntimeError("APK does not match the pristine snapshot")
    with zipfile.ZipFile(args.apk) as archive:
        manifest = archive.read("AndroidManifest.xml")
    if is_debuggable(manifest) or not signed_with(args.apk, (ROOT / "resources/key/cert.der").read_bytes()):
        raise RuntimeError("APK is not the stable-key-signed normal recovery APK")
    summary = json.loads((args.output / "device_patch_summary.json").read_text(encoding="utf-8"))
    reported = {str(entry["package_id"]) for entry in summary["packages"]}
    staged = {path.name for path in args.output.iterdir() if path.is_dir() and path.name.isdecimal()}
    if reported != staged or summary["cycle_assets"] or any(p["mode"] == "rebuilt" for p in summary["packages"]):
        raise RuntimeError("Control violates the DLL-free/default-cycle output contract")
    install_btree_slot_map()
    package = QtsPackage(args.output / "1")
    slots = package.build_slot_map()[0xC059EA43719099F1]
    entry = package.entries[0xC059EA43719099F1]
    raw = read_raw(package, package.build_slot_map(), 0xC059EA43719099F1)
    if len(slots) != 2 or entry.chunk_size != 307200 or raw is None or len(raw) != 313710:
        raise RuntimeError("Talent dictionary control no longer matches the measured two-chunk fix")
    runtime_imports = {}
    for path in sorted((ROOT / "resources/runtime/wxq_patch").rglob("*.pyc")):
        code = marshal.loads(path.read_bytes()[16:])
        runtime_imports[path.relative_to(ROOT / "resources/runtime").as_posix()] = sorted(imports(code))
    tables, textures = count_translated(summary)
    report = {
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "python": sys.version,
        "snapshot": str(args.snapshot.resolve()),
        "data_version": snapshot["package_1_info"],
        "apk": {"path": str(args.apk.resolve()), "sha256": apk_hash, "debuggable": False,
                "stable_signing_key": True},
        "verified_source_files": verified,
        "catalog": inventory(ROOT / "resources/catalog"),
        "runtime": inventory(ROOT / "resources/runtime"),
        "runtime_imports": runtime_imports,
        "staged": inventory(args.output),
        "summary": summary,
        "counters": {"tables": tables, "applied_textures": textures,
                     "skipped_tables": count_untranslated_text(summary),
                     "skipped_textures": count_untranslated_graphics(summary)},
        "talent": {"raw_sha256": hashlib.sha256(raw).hexdigest(), "raw_bytes": len(raw),
                   "chunk_size": entry.chunk_size,
                   "keys": [f"{slots[key].hash1:016X}" for key in sorted(slots)]},
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"verified_source_files": len(verified), "counters": report["counters"],
                      "talent": report["talent"]}, indent=2))


if __name__ == "__main__":
    main()
