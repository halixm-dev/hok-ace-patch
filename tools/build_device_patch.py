"""Stage English replacements for every text package pulled from an updated Android install.

Text tables are staged in place by the scanner layout: <game>/WXQ_Data/Package/builtin/<package id>/.
The catalog's texture edits are then ported onto the device's ASTC textures as a second pass. Each
changed package is written to <output>/<package id>/ and can be pushed back to
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


def _expand_staged_tokens(plans, log) -> int:
    """Bake the English resource terms into the staged replacements, after translation.

    translate_table requires source and target to carry identical placeholders, so the catalog keeps
    {Energy}/{LordExp}/{LordHp} and the client would otherwise expand them to Chinese at render time.
    Rewriting the materialized replacements keeps validation intact and still covers both staging
    paths, because full mode copies this directory and fit-only takes its subset from it.
    """
    from resource_tokens import expand_tokens_in_message

    changed = 0
    for _package, replacements, _per_asset in plans:
        for path in sorted(replacements.glob("*.assets")):
            raw = path.read_bytes()
            try:
                expanded, count = expand_tokens_in_message(raw)
            except Exception as error:  # an asset we cannot parse is left byte-for-byte alone
                log(f"token expand skipped {path.name}: {error}")
                continue
            if count:
                path.write_bytes(expanded)
                changed += count
    if changed:
        log(f"expanded resource tokens in {changed} replacement strings")
    return changed


def build_patch(game: pathlib.Path, catalog: pathlib.Path, work: pathlib.Path, output: pathlib.Path,
                *, fit_only_mode: bool = False, log=print) -> dict:
    """Scan <game>, stage English packages into <output>/<id>/ and return the summary."""
    from wxq_patch import adaptive
    from wxq_patch.unity_package_installer import capacity_report, stage_unity_package
    from qts_relocate import install_btree_slot_map
    from device_extensions import extend_graphics

    install_btree_slot_map()

    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    plans, fingerprints, counts, skipped = adaptive.scan(
        game, catalog, work / "scan", materialize=True
    )
    _expand_staged_tokens(plans, log)

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
    text_skipped = []

    def note_missing(package_id, planned, missing, mode):
        """Record the tables this run translated but did not put into the package.

        The drop loop below gives ground until the container takes what is left, so a package that
        stages successfully can still be missing part of its plan -- or, when it stages nothing, all
        of it. Without this the loss reaches the log only, and the summary reads as a clean run.
        """
        if not missing:
            return
        text_skipped.append({
            "package_id": package_id,
            "mode": mode,
            "considered_count": len(planned),
            "dropped_count": len(missing),
            "dropped": missing,
        })
        log(f"package {package_id}: {len(missing)} of {len(planned)} translated tables are not in the "
            f"staged package and stay in Chinese")

    for package, replacements, _per_asset in plans:
        planned = sorted(path.stem.upper() for path in replacements.glob("*.assets"))
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
            # The last attempt still wrote its own copy, so take it out again: the installer pushes
            # every package directory under <output>, not the summary, and a half-fitted package
            # must not reach the phone just because a texture pass made this run worth installing.
            shutil.rmtree(output / package.package_id, ignore_errors=True)
            log(f"package {package.package_id}: nothing left that fits in place")
            note_missing(package.package_id, planned, planned, mode)
            continue
        packages.append({
            "package_id": package.package_id,
            "mode": mode,
            "source_package": str(package.package_dir),
            "fit_summary": fit_summary,
            "stage_report": report,
        })
        log(f"package {package.package_id}: {mode} {report['status']} ({report['replacement_count']} assets)")
        staged_dir = work / ("full-replacements" if mode == "full" else "fit-replacements") / package.package_id
        staged_hashes = {path.stem.upper() for path in staged_dir.glob("*.assets")}
        missing = [item for item in planned if item not in staged_hashes]
        note_missing(package.package_id, planned, missing, mode)
    graphics, graphics_skipped = extend_graphics(game, catalog, output, log)
    packages += graphics
    summary = {
        "counts": dict(counts),
        "skipped_count": len(skipped),
        "fit_only": fit_only_mode,
        "packages": packages,
        "text_skipped": text_skipped,
        "graphics_skipped": graphics_skipped,
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
