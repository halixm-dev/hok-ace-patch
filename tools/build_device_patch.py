"""Stage English replacements for every text package pulled from an updated Android install.

The game directory must use the scanner layout: <game>/WXQ_Data/Package/builtin/<package id>/.
Each changed package is written to <output>/<package id>/ and can be pushed back to
files/QtsVFSCache/packages/<package id>/ on the device.
"""
from __future__ import annotations

import argparse
import json
import re
import pathlib
import shutil
import sys

from build_mobile_patch import synthetic_metadata_builder


SLOT_ERROR = re.compile(r"no safe insertion point for slot (\d+)")


def failing_asset(error: BaseException, package=None) -> int | None:
    """Return the file hash responsible for a stage_unity_package failure.

    Position-index errors are raised after all assets were fitted, so the asset
    being iterated is unrelated; blame the asset whose original slot holds the offset.
    """
    match = SLOT_ERROR.search(str(error))
    if match and package is not None:
        offset = int(match.group(1))
        for file_hash, chunks in package.build_slot_map().items():
            for slot in chunks.values():
                if slot.slot_offset <= offset < slot.slot_offset + slot.slot_size:
                    return file_hash
        return None
    tb = error.__traceback__
    found = None
    while tb:
        if tb.tb_frame.f_code.co_name == "stage_unity_package":
            found = tb.tb_frame.f_locals.get("file_hash")
        tb = tb.tb_next
    return found


def build_patch(game: pathlib.Path, catalog: pathlib.Path, work: pathlib.Path, output: pathlib.Path,
                *, fit_only_mode: bool = False, log=print) -> dict:
    """Scan <game>, stage English packages into <output>/<id>/ and return the summary."""
    from wxq_patch import adaptive
    from wxq_patch.unity_package_installer import capacity_report, stage_unity_package
    from qts_relocate import install_btree_slot_map

    install_btree_slot_map()

    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    plans, fingerprints, counts, skipped = adaptive.scan(
        game, catalog, work / "scan", materialize=True
    )

    def fit_only(package, replacements):
        fit_summary = capacity_report(package.package_dir, replacements)
        allowed = {item["hash"] for item in fit_summary["assets"] if item["status"] != "blocked"}
        fit_replacements = work / "fit-replacements" / package.package_id
        if fit_replacements.exists():
            shutil.rmtree(fit_replacements)
        fit_replacements.mkdir(parents=True)
        for path in replacements.glob("*.assets"):
            if path.stem.upper() in allowed:
                shutil.copy2(path, fit_replacements / path.name)
        return fit_summary, fit_replacements

    def stage(package, replacements, fingerprints, donations):
        source_hashes = {
            path.name: fingerprints[str(path.relative_to(game))]
            for path in [package.index_path, *package.shard_paths]
        }

        def builder(game_dir, assets, build_root):
            return synthetic_metadata_builder(package, game_dir, assets, build_root)

        return stage_unity_package(
            game,
            replacements,
            output,
            source_package_dir=package.package_dir,
            metadata_builder=builder,
            verify_all_unrelated=False,
            global_donations=donations,
            source_hashes=source_hashes,
        )

    packages = []
    for package, replacements, _per_asset in plans:
        fit_summary = None
        report = None
        mode = "full"
        if not fit_only_mode:
            full_replacements = work / "full-replacements" / package.package_id
            if full_replacements.exists():
                shutil.rmtree(full_replacements)
            shutil.copytree(replacements, full_replacements)
            full_dropped = []
            # Guarded on a non-empty set: a package whose every asset was dropped has nothing
            # left to stage, and looping again would never succeed.
            while any(full_replacements.glob("*.assets")):
                try:
                    report = stage(package, full_replacements, fingerprints, True)
                    break
                except RuntimeError as error:
                    file_hash = failing_asset(error, package)
                    victim = next(full_replacements.glob(f"{file_hash:016X}.assets"), None) if file_hash is not None else None
                    if victim is None:
                        log(f"package {package.package_id}: full staging failed ({error}); retrying fit-only")
                        mode = "fit-only"
                        break
                    victim.unlink()
                    full_dropped.append(f"{file_hash:016X}")
            if mode == "full":
                fit_summary = {"dropped_while_staging": full_dropped}
                log(f"package {package.package_id}: dropped {len(full_dropped)} assets in full mode")
        if fit_only_mode or mode == "fit-only":
            mode = "fit-only"
            fit_summary, fit_replacements = fit_only(package, replacements)
            dropped = []
            while any(fit_replacements.glob("*.assets")):
                try:
                    report = stage(package, fit_replacements, fingerprints, False)
                    break
                except RuntimeError as error:
                    file_hash = failing_asset(error, package)
                    victim = next(fit_replacements.glob(f"{file_hash:016X}.assets"), None) if file_hash is not None else None
                    if victim is None:
                        raise
                    victim.unlink()
                    dropped.append(f"{file_hash:016X}")
            fit_summary["dropped_while_staging"] = dropped
            log(f"package {package.package_id}: dropped {len(dropped)} assets that competed for slack")
        if report is None:
            # Every remaining table was dropped, as on a re-run over an already patched package.
            log(f"package {package.package_id}: nothing left that fits in place")
            continue
        packages.append({
            "package_id": package.package_id,
            "mode": mode,
            "source_package": str(package.package_dir),
            "fit_summary": fit_summary,
            "stage_report": report,
        })
        log(f"package {package.package_id}: {mode} {report['status']} ({report['replacement_count']} assets)")
    summary = {
        "counts": dict(counts),
        "skipped_count": len(skipped),
        "fit_only": fit_only_mode,
        "packages": packages,
    }
    (output / "device_patch_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log(json.dumps(summary["counts"], indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=pathlib.Path, required=True)
    parser.add_argument("--game", type=pathlib.Path, required=True)
    parser.add_argument("--catalog", type=pathlib.Path, required=True)
    parser.add_argument("--work", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--fit-only", action="store_true")
    args = parser.parse_args()

    sys.path.insert(0, str(args.runtime.resolve()))
    build_patch(args.game, args.catalog, args.work, args.output, fit_only_mode=args.fit_only)


if __name__ == "__main__":
    main()
