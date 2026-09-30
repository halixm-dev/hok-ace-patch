"""Stage English replacements for every text package pulled from an updated Android install.

Text tables are staged in place by the scanner layout: <game>/WXQ_Data/Package/builtin/<package id>/.
Two things extend that: packages whose translatable content only exists in the APK are rebuilt whole
against the APK (``package_rebuild``), and the catalog's texture edits are ported onto the device's
ASTC textures as a second pass. Each changed package is written to <output>/<package id>/ and can be
pushed back to files/QtsVFSCache/packages/<package id>/ on the device.
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


def rebuild_prime_packages(game: pathlib.Path, catalog_dir: pathlib.Path, apk: pathlib.Path,
                           builder_dir: pathlib.Path, work: pathlib.Path, output: pathlib.Path,
                           log) -> list[dict]:
    """Rebuild every package whose translatable content partly lives only in the APK.

    Returns the summary entries; each also carries `textures_considered` and `textures_skipped`, which
    the caller moves into `graphics_skipped` rather than keeping on the entry, so that no reader can
    add the same skipped texture up twice.
    """
    from wxq_patch import adaptive
    from package_rebuild import REBUILD_PACKAGES, extract_prime, make_transform, rebuild_package
    from qts_builder import Builder

    catalog = adaptive.load_catalog(catalog_dir)
    prime = extract_prime(apk, set(REBUILD_PACKAGES), work / "prime")
    builder = Builder(builder_dir)
    refused: set[int] = set()
    transform = make_transform(catalog, catalog_dir, log, refused)
    reports = []
    for package_id in REBUILD_PACKAGES:
        device_dir = game / "WXQ_Data" / "Package" / "builtin" / package_id
        if package_id not in prime or not device_dir.is_dir():
            log(f"package {package_id}: not in the APK or not downloaded; skipped")
            continue
        report = rebuild_package(package_id, device_dir, prime[package_id], transform, builder,
                                 work, output, log, refused)
        if report is None:
            continue
        if report["textures_skipped"]:
            log(f"package {package_id}: {len(report['textures_skipped'])} of "
                f"{report['textures_considered']} textures cannot be translated and stay in Chinese")
        reports.append(report)
    return reports


def build_patch(game: pathlib.Path, catalog: pathlib.Path, work: pathlib.Path, output: pathlib.Path,
                *, fit_only_mode: bool = False, apk: pathlib.Path | None = None,
                builder_dir: pathlib.Path | None = None, log=print) -> dict:
    """Scan <game>, stage English packages into <output>/<id>/ and return the summary.

    With <apk> and <builder_dir> (a folder holding the PC QtsVFS.dll), the packages that keep
    translatable text or textures only inside the APK are rebuilt whole; every other package is
    patched in place.
    """
    from wxq_patch import adaptive
    from wxq_patch.unity_package_installer import capacity_report, stage_unity_package
    from qts_relocate import install_btree_slot_map
    from device_extensions import exclude_extra_chunks, extend_graphics, relocate_text

    install_btree_slot_map()

    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)

    packages = []
    graphics_skipped = []
    if apk is not None and builder_dir is not None:
        for report in rebuild_prime_packages(game, catalog, apk, builder_dir, work, output, log):
            if report["textures_skipped"]:
                graphics_skipped.append({
                    "package_id": report["package_id"],
                    "mode": "rebuilt",
                    "skipped_count": len(report["textures_skipped"]),
                    "considered_count": report["textures_considered"],
                    "skipped": report["textures_skipped"],
                })
            packages.append({key: value for key, value in report.items()
                             if key not in ("textures_considered", "textures_skipped")})
    else:
        log("APK or QtsVFS builder not available: text and textures that exist only in the APK stay Chinese")
    rebuilt = {entry["package_id"] for entry in packages}

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

    text_skipped = []

    def note_missing(package_id: str, planned: list[str], missing: list[str], mode: str) -> None:
        """Record the tables this run translated but did not put into the package.

        The drop loop gives ground until the container takes what is left, so a package that stages
        successfully can still be missing part of its plan -- or, when it stages nothing, all of it.
        Without this the loss reaches the log only, and the summary reads as a clean run.
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

    # A table the loop could not stage is handed to relocate_text after the loop, so what counts as a
    # loss can only be decided once relocation has run.
    pending_text = []  # (package id, plan, mode, hashes staged in place)
    dropped_text = []  # (package, {file hash: replacement path}) the loop did not stage

    for package, replacements, _per_asset in plans:
        # A rebuilt package no longer matches the device's copy, so the in-place stager must not
        # re-derive it; the rebuild already carried everything the package holds.
        if package.package_id in rebuilt:
            continue

        all_replacements = replacements
        planned = sorted(path.stem.upper() for path in all_replacements.glob("*.assets"))
        # Tables that would need more chunks than the original has are kept away from the stager,
        # which would invent lookup keys for the new chunks; relocate_text appends them instead.
        replacements, _excluded = exclude_extra_chunks(package, all_replacements, work, log)
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
            # relocate_text below can still put the tables back into a clean copy of the package.
            shutil.rmtree(output / package.package_id, ignore_errors=True)
            log(f"package {package.package_id}: nothing left that fits in place")
        else:
            packages.append({
                "package_id": package.package_id,
                "mode": mode,
                "source_package": str(package.package_dir),
                "fit_summary": fit_summary,
                "stage_report": report,
            })
            log(f"package {package.package_id}: {mode} {report['status']} ({report['replacement_count']} assets)")
        staged_dir = work / ("full-replacements" if mode == "full" else "fit-replacements") / package.package_id
        staged_hashes = {path.stem.upper() for path in staged_dir.glob("*.assets")} if report is not None else set()
        pending_text.append((package.package_id, planned, mode, staged_hashes))
        dropped_text.append((package, {
            int(path.stem, 16): path for path in all_replacements.glob("*.assets")
            if path.stem.upper() not in staged_hashes
        }))

    relocated: dict[str, set[str]] = {}
    for package, dropped in dropped_text:
        if not dropped:
            continue
        written, _refused = relocate_text(package, output, dropped, log)
        if not written:
            continue
        relocated.setdefault(package.package_id, set()).update(written)
        packages.append({"package_id": package.package_id, "mode": "relocated-text",
                         "stage_report": {"status": "relocated", "replacement_count": len(written)}})

    for package_id, planned, mode, staged_hashes in pending_text:
        # A table relocation wrote into this package is applied, not lost, so it is not a loss to
        # report. The set is keyed by package because the same asset hash can be planned in more than
        # one of them, and applying it in one says nothing about the other.
        applied = staged_hashes | relocated.get(package_id, set())
        note_missing(package_id, planned, [h for h in planned if h not in applied], mode)

    graphics, graphics_skipped_extra = extend_graphics(game, catalog, output, log, skip=rebuilt)
    packages += graphics
    graphics_skipped += graphics_skipped_extra

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
    parser.add_argument("--apk", type=pathlib.Path, help="the APK the prime layer is read from")
    parser.add_argument("--builder", type=pathlib.Path, help="folder with QtsVFS.dll + QtskDB.dll")
    args = parser.parse_args()

    sys.path.insert(0, str(args.runtime.resolve()))
    build_patch(args.game, args.catalog, args.work, args.output, fit_only_mode=args.fit_only,
                apk=args.apk, builder_dir=args.builder)


if __name__ == "__main__":
    main()
