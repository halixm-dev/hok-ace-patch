"""Verify retained benchmark receipts and installed APKs without changing phone data."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

OLD = "174600da-38c5-4b2e-abf2-0e791f8f2f04"
NEW = "bbf81617-5ac4-4ad8-aaa2-3a295e27db8c"
ENGINE = "ff5d8aa28fad5fc986033a2845e50bc8825e3ebd37239a448be41249437240db"
NORMAL = "29b3ee7e5a0d21de7d1282d704416402d341b651da95af2eeb5b274c818defdc"
PATCHER = "28f8be573e882d96953cbfddb54611114d023de8c7eab3ca7f81530b8855e68e"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    def load(session: str, name: str) -> dict:
        return json.loads((args.evidence / session / name).read_text(encoding="utf-8-sig"))

    def adb(*command: str) -> str:
        return subprocess.run([args.adb, "-s", args.serial, *command], check=True,
                              capture_output=True, timeout=90).stdout.decode().strip()

    def installed_hash(package: str) -> str:
        path = adb("shell", "pm", "path", "--user", "0", package)
        assert re.fullmatch(r"package:/data/app/[A-Za-z0-9_./~=+-]+/base\.apk", path)
        return adb("shell", "sha256sum", path.removeprefix("package:")).split()[0]

    journal = load(NEW, "journal.json")
    assert journal["phase"] == "COMPLETE" and journal["engine_id"] == ENGINE
    assert journal["normal_verified"] and not journal["packages_dirty"]
    assert journal.get("mutation_intent") is None and journal.get("recovery_normal_intent") is None
    hashes = load(NEW, "staged-hashes.json")
    assert hashes == load(OLD, "staged-hashes.json") and len(hashes) == 14
    normalize = lambda value: json.dumps(value, sort_keys=True).replace(OLD, "SESSION").replace(NEW, "SESSION")
    assert normalize(load(NEW, "out/device_patch_summary.json")) == normalize(load(OLD, "out/device_patch_summary.json"))
    normal_hash = installed_hash("com.tencent.tmgp.osgame")
    patcher_hash = installed_hash("dev.halixm.hokacepatcher")
    assert normal_hash == NORMAL and patcher_hash == PATCHER
    assert "DEBUGGABLE" not in adb("shell", "dumpsys", "package", "com.tencent.tmgp.osgame")
    old_metrics, new_metrics = (load(session, "resource-metrics.json") for session in (OLD, NEW))
    old_build, new_build = (load(session, "metrics.json")["elapsed_seconds"] for session in (OLD, NEW))
    assert new_metrics["status"] == "complete" and new_metrics["unavailable_readings"] == 0
    result = {"session": NEW, "engine_id": ENGINE, "phase": journal["phase"],
              "normal_apk_sha256": normal_hash, "patcher_apk_sha256": patcher_hash,
              "normal_not_debuggable": True, "all_14_staged_hashes_match_older_phone_run": True,
              "full_summary_matches_after_session_path_normalization": True,
              "counts": journal["counts"], "old_metrics": old_metrics, "new_metrics": new_metrics,
              "old_internal_build_seconds": old_build, "new_internal_build_seconds": new_build,
              "internal_build_time_reduction_percent": 100 * (1 - new_build / old_build),
              "sampled_rss_reduction_percent": 100 * (1 - new_metrics["maximum_sampled_rss_kib"] / old_metrics["maximum_sampled_rss_kib"]),
              "comparison_limits": "Single sequential runs; older total includes interrupted final-install recovery. Internal build timer excludes pre-build snapshot/APK verification. RSS sampled once per second; HWM is process lifetime. Free space may include other apps. No controlled end-to-end speedup claim.",
              "screen_verdict": "pending user check"}
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
