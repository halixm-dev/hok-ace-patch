"""Offline check of compare_continuation_controls' summary normalization; no game dump needed.

Run with Python 3.12 from the repository root. Synthetic summaries only: a built-in package
and a package added from the APK must normalize, and every other source path must be refused
rather than silently passing the comparison.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import compare_continuation_controls as controls  # noqa: E402

WORK = "D:\\scratch\\run\\work"
GAME = "D:\\scratch\\game\\WXQ_Data\\Package\\builtin"


def _normalized(packages: list[dict]) -> list[str]:
    return [package["source_package"] for package in controls._summary({"packages": packages})["packages"]]


def _refused(package: dict) -> None:
    try:
        controls._summary({"packages": [package]})
    except ValueError:
        return
    raise AssertionError(f"accepted {package}")


def _compare(baseline: dict, changed: dict) -> int:
    with tempfile.TemporaryDirectory() as directory:
        paths = []
        for name, report in (("a.json", baseline), ("b.json", changed)):
            path = Path(directory) / name
            path.write_text(json.dumps(report), encoding="utf-8")
            paths.append(str(path))
        return subprocess.run([sys.executable, str(HERE / "compare_continuation_controls.py"), "compare", *paths],
                              capture_output=True).returncode


def main() -> None:
    assert sys.version_info[:2] == (3, 12), "Use the project's Python 3.12 environment"
    assert _normalized([
        {"package_id": "15", "mode": "rebuilt", "source_package": GAME + "\\15"},
        {"package_id": "21", "mode": "added-from-apk", "source_package": WORK + "\\prime\\21"},
        {"package_id": "10", "mode": "added-from-apk", "source_package": "/tmp/work/prime/10"},
    ]) == ["<builtin>/15", "<work>/prime/21", "<work>/prime/10"]
    # Packages without a source path stay as they are.
    assert controls._summary({"packages": [{"package_id": "1"}]}) == {"packages": [{"package_id": "1"}]}
    for package in (
        {"package_id": "21", "mode": "added-from-apk", "source_package": WORK + "\\prime\\10"},   # wrong id
        {"package_id": "21", "mode": "added-from-apk", "source_package": WORK + "\\other\\21"},   # not prime
        {"package_id": "21", "mode": "rebuilt", "source_package": WORK + "\\prime\\21"},          # prime, wrong mode
        {"package_id": "15", "mode": "rebuilt", "source_package": GAME + "\\15\\nested"},         # nested
        {"package_id": "15", "mode": "rebuilt", "source_package": GAME + "\\"},                   # empty id
    ):
        _refused(package)
    report = {"schema": 1, "normalizations": controls.NORMALIZATIONS, "output": {"a": 1}}
    older = {**report, "normalizations": controls.NORMALIZATIONS[:1]}
    assert _compare(older, report) == 0, "an older capture's normalization list failed the compare"
    assert _compare(report, {**report, "output": {"a": 2}}) == 1, "differing output passed"
    print("PASS continuation-control normalization and compare gates")


if __name__ == "__main__":
    main()
