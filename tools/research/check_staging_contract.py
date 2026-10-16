"""Check that the staging summary contract lives in ``build_patch``'s docstring and ``AGENTS.md`` only points to it.

The contract -- the summary's fields, the ``mode`` values and what each entry carries, the skipped
lists and the counters that read them, the pass order, the APK/builder gating -- changes in the same
edit as the code only while it sits beside that code. This reads the docstring with ``ast`` (nothing is
imported, so no runtime is needed) and confirms each piece of the contract is named there, and that
``AGENTS.md`` names where the contract is without restating it.

Run by hand from the project root:

    .venv\\Scripts\\python.exe tools\\research\\check_staging_contract.py

Exit code 0 means the contract is in place; otherwise one line per failure is printed. It imports
nothing from ``app/`` or ``tools/``, and nothing imports it.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STAGING = ROOT / "tools" / "build_device_patch.py"
INSTRUCTIONS = ROOT / "AGENTS.md"

# What the contract has to name, by topic. Each is a code identifier the contract is about. The
# signature is not listed: it is the function's own, directly above the docstring.
CONTRACT = {
    "parameters": ["builder_dir", "cycle_assets"],
    "language": ["languages.for_catalog", "languages.catalog_dir", "language: <name>"],
    "summary fields": ["device_patch_summary.json", "counts", "skipped_count", "fit_only", "packages",
                       "text_skipped", "graphics_skipped", "append_skipped"],
    "package entry": ["package_id", "source_package", "fit_summary", "stage_report", "replacement_count"],
    "modes": ["`full`", "`fit-only`", "`rebuilt`", "`added-from-apk`", "`relocated-text`", "`graphics`",
              "`extra-text`"],
    "rebuilt and appended entries": ["textures", "assets", "translated_downloaded", "added_from_apk"],
    "skipped lists": ["considered_count", "dropped_count", "dropped", "reason"],
    "counters": ["count_translated", "count_untranslated_graphics", "count_untranslated_text"],
    "pass order": ["qts_relocate.install_btree_slot_map()", "package_rebuild.rebuild_prime_packages",
                   "relocate_text", "device_extensions.extend_graphics", "repair_card_dictionaries",
                   "package_rebuild.add_prime_only"],
    "gating": ["REBUILD_PACKAGES", "QtsVFS.dll", "--selftest", "wxq_patch", "sys.path"],
    "device cycle": ["extra_text.plan_package", "package_rebuild.make_transform", "--cycle-asset",
                     "extra_text.CANDIDATE_ASSETS", "extra_text.SAFE_ASSETS"],
}

# Phrases only the contract itself carries; the instructions must not restate them.
CONTRACT_ONLY = ["### `build_patch` contract", "`text_skipped` (`package_id`", "`graphics_skipped` (`package_id`",
                 "`append_skipped` (`package_id`", "translated_downloaded", "`mode` is `full`"]

# The pointer: the instructions must say where the contract is.
POINTER = ["`tools/build_device_patch.py`", "`build_patch`", "docstring"]


def _docstring() -> str:
    tree = ast.parse(STAGING.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "build_patch":
            return ast.get_docstring(node) or ""
    raise SystemExit(f"{STAGING.relative_to(ROOT)}: no build_patch function")


def check() -> list[str]:
    doc = " ".join(_docstring().split())
    failures = [f"build_patch docstring: {topic}: does not name {name!r}"
                for topic, names in CONTRACT.items() for name in names if name not in doc]
    text = INSTRUCTIONS.read_text(encoding="utf-8")
    failures += [f"AGENTS.md: restates the contract ({phrase!r})" for phrase in CONTRACT_ONLY if phrase in text]
    lines = [line for line in text.splitlines() if all(p in line for p in POINTER[:2])]
    if not any("docstring" in line for line in lines):
        failures.append("AGENTS.md: no pointer naming `tools/build_device_patch.py`, `build_patch` and its docstring")
    return failures


def main() -> int:
    failures = check()
    for failure in failures:
        print(failure)
    if failures:
        print(f"{len(failures)} failure(s)")
        return 1
    print("staging contract is in the docstring; AGENTS.md points to it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
