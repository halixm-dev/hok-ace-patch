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


def _expand_staged_tokens(plans, log, terms: dict[str, str]) -> int:
    """Bake the language's resource terms (<terms>) into the staged replacements, after translation.

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
                expanded, count = expand_tokens_in_message(raw, terms)
            except Exception as error:  # an asset we cannot parse is left byte-for-byte alone
                log(f"token expand skipped {path.name}: {error}")
                continue
            if count:
                path.write_bytes(expanded)
                changed += count
    if changed:
        log(f"expanded resource tokens in {changed} replacement strings")
    return changed


def _drop_uncatalogued_tables(plans, catalog, counts, log) -> list:
    """Drop the replacements for tables the catalog has no record for, and take the census down with them.

    `adaptive.scan` recognizes a localization table by its shape and translates it whenever every string
    it holds is in the catalog's string map, so a table the catalog has no `.blocks` for is staged all the
    same. That is how two assets the `extra_text` allowlist has never cleared — `3914DBBFECD1E54D` and
    `63922EF4D4C86526`, both in package 1 on this data — reached the phone once packages `1` and
    `1050016095` stopped being rebuilt: the rebuilt path consulted `catalog.known` alone, the in-place path
    did not, and the two disagreed about the same layer.

    The primary pass means *the catalog's tables*. Anything else needs a device cycle, which is what the
    allowlist is for, so a table the catalog does not list is left out here. `counts` is adjusted in place
    because it is the scanner's census and the summary reports it: a plan this function shortens must not
    leave the census claiming more than the run staged.
    """
    kept = []
    dropped = 0
    for package, replacements, per_asset in plans:
        for path in sorted(replacements.glob("*.assets")):
            file_hash = int(path.stem, 16)
            if file_hash in catalog.known:
                continue
            seen = per_asset.get(file_hash, {})
            counts["tables"] -= 1
            # The census omits a key whose count is zero: a catalog that translates every string the
            # scan met reports no "unknown" at all.
            for key in ("records", "translated", "unknown"):
                counts[key] = counts.get(key, 0) - seen.get(key, 0)
            path.unlink()
            dropped += 1
            log(f"package {package.package_id}: {file_hash:016X} is a table the catalog has no record "
                f"for ({seen.get('translated', 0)} of its strings it could translate); left Chinese, it "
                f"needs an extra_text cycle")
        if any(replacements.glob("*.assets")):
            kept.append((package, replacements, per_asset))
        else:
            log(f"package {package.package_id}: every table it planned sits outside the catalog; skipped")
    if dropped:
        log(f"{dropped} tables outside the catalog left unstaged")
    return kept


def rebuild_prime_packages(game: pathlib.Path, apk: pathlib.Path, transform, builder,
                           work: pathlib.Path, output: pathlib.Path, log,
                           refused: set[int]) -> list[dict]:
    """Rebuild every package whose translatable content partly lives only in the APK.

    Returns the summary entries; each also carries `textures_considered` and `textures_skipped`, which
    the caller moves into `graphics_skipped` rather than keeping on the entry, so that no reader can
    add the same skipped texture up twice.

    <transform> and <builder> belong to the caller, which hands the same pair to the append pass, so
    both passes decide an asset's fate the same way. <refused> is the caller's set, filled per package.
    """
    from package_rebuild import REBUILD_PACKAGES, extract_prime, rebuild_package

    prime = extract_prime(apk, set(REBUILD_PACKAGES), work / "prime")
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
                builder_dir: pathlib.Path | None = None, cycle_assets: frozenset[int] = frozenset(),
                log=print) -> dict:
    """Scan <game>, stage translated packages into <output>/<id>/ and return the summary.

    This docstring is the staging summary contract: change it in the same edit as the code it
    describes. Both the CLI (`main`) and the app call this entry.

    The text pass stages **the catalog's tables** (`catalog.known`) and nothing else: `adaptive.scan`
    recognizes a localization table by shape and can resolve strings for one the catalog has no record
    for, and those belong to a device cycle rather than to a normal run
    (`_drop_uncatalogued_tables`).

    - `catalog` decides the language. `languages.for_catalog` reads it from the directory name
      (`catalog` → English, `catalog_id` → Indonesian, anything else → English), and the run logs
      `language: <name>`. A catalog that ships only some catalog edits borrows the rest from the
      English one beside it. Nothing else names the language, so a caller picks one with
      `languages.catalog_dir(resources, code)` and passes that path.
    - It imports `wxq_patch` from whatever runtime directory the caller already put on `sys.path`; it
      never adds paths itself. That is what lets the frozen exe run it.
    - `cycle_assets` is a device cycle's one variable: the candidate queue's assets
      (`extra_text.CANDIDATE_ASSETS`) this run enables on top of the allowlist,
      `extra_text.SAFE_ASSETS`. Empty on a normal run. It must reach **both** paths that can translate
      such an asset — `extra_text.plan_package` and `package_rebuild.make_transform` — because the
      extra-text pass skips the packages a rebuild replaced whole, and package `1`, where fourteen of
      the fifteen candidates live, was one of them while `REBUILD_PACKAGES` named it. A candidate
      enabled in only one path is a silent no-op for the packages the other owns. Today the threading is
      the reverse of that: with `REBUILD_PACKAGES` empty, `plan_package` reaches every package and
      `make_transform`'s candidate branch is unreachable, so the two must stay wired together or putting
      a package back in `REBUILD_PACKAGES` silently stops the knob working there.
      `tools/build_device_patch.py --cycle-asset` is the only way to set it, and it accepts only a hash
      on `extra_text.CANDIDATE_ASSETS`.
    - It calls `qts_relocate.install_btree_slot_map()` before scanning, so a re-run reads live chunks
      rather than superseded copies of relocated ones.
    - It returns exactly the payload written to `output/device_patch_summary.json`: `language` (the code
      `for_catalog` resolved), `counts`, `skipped_count`, `fit_only`, `packages`, `text_skipped`,
      `graphics_skipped`, `append_skipped` and `cycle_assets` — each `packages` entry carrying
      `package_id`, `mode`, `source_package`, `fit_summary`, `stage_report`. `cycle_assets` is the list
      of candidate hashes a device cycle enabled, empty otherwise, so a staged build names its own
      variable. Callers read `stage_report["replacement_count"]`.
    - `apk` and `builder_dir` are what make the game's **other data layer** reachable. The game reads
      the prime layer, the packages baked into the APK, only when the override layer lacks an asset, and
      package `1` keeps most of its text — the chessplayer names among it — only in the prime layer.
      Given both, `package_rebuild.rebuild_prime_packages` re-lays out the packages in
      `REBUILD_PACKAGES` whole before the in-place loop runs, and `package_rebuild.add_prime_only`
      appends the catalog assets that exist only in the APK into the override layer's copy of every
      **other** package afterwards. `REBUILD_PACKAGES` is **empty**, so on a normal run only the append
      does anything and every package takes the in-place path first; the rebuild stays reachable by
      name, and it is the pipeline's only caller of `QtsVFS.dll`. The append is gated on the **APK**,
      not on the builder — it harvests each record from the APK's own copy of the package — so a run
      given the APK without the DLLs reaches the same primed content, and stages byte-identical
      packages. Given no APK, it logs that prime-only content stays Chinese and stages exactly as it did
      before, which is what keeps `--selftest` and the offline CLI usable without it.
    - Only packages that actually staged appear in `packages`. A package with nothing left that fits is
      logged and skipped, not reported as a result, and its directory is removed from `output/` so the
      directories there are exactly the reported packages — the installer pushes by directory, not by
      summary.
    - A package of textures whose **every** texture was skipped also writes no directory, so it stays out
      of `packages`; it is reported instead in `graphics_skipped` (`package_id`, `mode`,
      `skipped_count`, `considered_count`, `skipped`). Without that list a skipped texture is invisible
      in the summary, which is how `C9E29F61B9E73713` stayed Chinese unnoticed.
      `count_untranslated_graphics` reads it so the GUI can say how many images were left alone. A
      rebuilt package reports the textures its transform refused the same way, with `mode: rebuilt`.
    - The drop loop gives ground until the container takes what is left, so a package that stages
      successfully can still be missing part of its plan — and a package that stages nothing is missing
      all of it. Those tables are reported in `text_skipped` (`package_id`, `mode`, `considered_count`,
      `dropped_count`, `dropped`), one entry per package that lost something; `dropped` is the plan
      minus what the staged directory holds minus what `relocate_text` wrote afterwards, because
      relocation applies a table rather than losing it. `count_untranslated_text` reads it so the GUI
      can say how many tables stay in Chinese. The field names stay distinct from `graphics_skipped`'s
      on purpose: that list is textures that were never translated, this one is text that was translated
      and then not applied, and one accessor must not sum them into a total that means nothing.
    - `mode` is `full`, `fit-only`, `rebuilt`, `added-from-apk`, `relocated-text`, `graphics`, or
      `extra-text`. A `graphics` entry's `replacement_count` counts textures, not tables. A `rebuilt`
      entry counts both and carries `textures`, the share of its `replacement_count` that was catalog
      textures, plus `assets`, `translated_downloaded` and `added_from_apk`; `count_translated` must use
      `textures`, because classifying a rebuilt package by mode alone reports one of its two kinds as
      the other. An `added-from-apk` entry counts both kinds the same way and carries `textures` and
      `assets` for the same reason.
    - A package the append pass could not add to is reported in `append_skipped` (`package_id`,
      `mode: added-from-apk`, `reason`, `assets`, `textures`) — a full B-tree leaf, a device copy split over
      several shards, or an asset the encoder refuses, cases whose counts the pass can state as what it
      would have written. Its entries carry two shapes: a package the pass could not add to at all,
      which has no output directory behind it and is therefore not in `packages`, and the refused share
      of a package it *did* add to, which is in `packages` for the part that was written. The refused
      assets are absent from that entry, so without this second shape the summary reads as if the pass
      had added everything it offered. A package whose index will not read, or whose device copy has no
      `<id>_0.db`, is logged and skipped with no entry, the same way the extra-text pass treats a
      package it cannot read: there is no count to give it. Both GUI counters read it — `textures` as
      images that stay in Chinese, `assets - textures` as tables — so the app can say what stays Chinese
      and of which kind, rather than one total that means nothing.
    - After text relocation it calls
      `device_extensions.extend_graphics(game, catalog, output, log, skip=rebuilt)`, which discovers
      the game packages afresh (a texture-heavy package usually stages no text), ports every catalog
      edit present in them onto the device ASTC textures, and runs the extra-text pass. `skip` keeps
      it off a package the rebuild already replaced whole, which no longer matches the device's
      container. It returns `(reports, skipped)`: the reports become `packages`, the skips become
      `graphics_skipped`. It then calls `repair_card_dictionaries` to repair an older patch's
      already-English card dictionaries; successful repairs use `relocated-text` entries and
      unmeasured layouts are reported in `text_skipped`. Last of all, with an APK, it calls
      `package_rebuild.add_prime_only(...)` — also keyed on `rebuilt` — so an appended asset lands on
      the copy the passes above staged instead of being overwritten by one.
    """
    from wxq_patch import adaptive
    from wxq_patch.unity_package_installer import capacity_report, stage_unity_package
    from qts_relocate import install_btree_slot_map
    from device_extensions import exclude_extra_chunks, extend_graphics, relocate_text, repair_card_dictionaries
    from languages import for_catalog
    from terminology import install as install_terminology

    install_btree_slot_map()
    # Before the first load: the scanner and every pass after it load the catalog through this.
    install_terminology()
    language = for_catalog(catalog)
    log(f"language: {language.name} ({catalog.name})")

    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)

    loaded_catalog = adaptive.load_catalog(catalog)
    glossary = getattr(loaded_catalog, "terminology", None)  # absent when the runtime's loader ran
    supplemented = getattr(loaded_catalog, "supplemented", 0)
    if supplemented:
        log(f"catalog supplement: {supplemented} strings the game added after the catalog was built")
    if glossary:
        log("glossary: " + ", ".join(f"{count} catalog strings now read {term!r}"
                                     for term, count in sorted(glossary.items())))
    packages = []
    graphics_skipped = []
    append_skipped = []
    official_builder = transform = None
    if apk is None:
        # Both passes that reach into the APK read it, so without it the primed content — 297 of
        # package `1`'s tables and 71 of package `1050016095`'s textures on this data — stays Chinese.
        log("no APK given: text and textures that exist only in the APK stay Chinese")
    else:
        from package_rebuild import REBUILD_PACKAGES, make_transform

        refused: set[int] = set()
        # The transform reads the catalog and nothing else, so the append no longer needs QtsVFS.dll: it
        # harvests each record from the APK's own copy of the package. The builder is what lays a package
        # out whole, which only `REBUILD_PACKAGES` asks for.
        transform = make_transform(loaded_catalog, catalog, log, refused, candidates=cycle_assets)
        if builder_dir is None:
            log("no QtsVFS builder given: no package is laid out whole; the append covers the rest")
            if REBUILD_PACKAGES:
                log(f"  {REBUILD_PACKAGES} is named in REBUILD_PACKAGES but cannot be rebuilt without "
                    f"it, so their prime-only content stays Chinese")
        elif REBUILD_PACKAGES:
            from qts_builder import Builder

            official_builder = Builder(builder_dir)
        if official_builder is not None:
            for report in rebuild_prime_packages(game, apk, transform, official_builder, work, output,
                                                 log, refused):
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
    rebuilt = {entry["package_id"] for entry in packages}

    plans, fingerprints, counts, skipped = adaptive.scan(
        game, catalog, work / "scan", materialize=True
    )
    plans = _drop_uncatalogued_tables(plans, loaded_catalog, counts, log)
    _expand_staged_tokens(plans, log, language.resource_terms)

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

    graphics, graphics_skipped_extra = extend_graphics(game, catalog, output, log, skip=rebuilt,
                                                       candidates=cycle_assets)
    packages += graphics
    graphics_skipped += graphics_skipped_extra

    # Already-English tables produce no replacement plan. Repair the old oversized card-dictionary
    # chunks separately so running the new patcher over its predecessor also fixes the card labels.
    repaired, repair_skipped = repair_card_dictionaries(game, loaded_catalog, output, log, skip=rebuilt)
    packages += repaired
    text_skipped += repair_skipped

    if transform is not None:
        # Gated on the **APK**, not on the builder: the append harvests each record from the APK's own
        # prime copy of the package rather than asking Tencent's builder to mint one, so a run without
        # the DLLs reaches the primed content all the same.
        # Last, so an append lands on the copy the passes above staged rather than being overwritten
        # by one, and so a package a rebuild replaced whole is left alone (`rebuilt`).
        from package_rebuild import add_prime_only

        appended, append_skipped = add_prime_only(game, apk, transform, work,
                                                  output, rebuilt, log)
        packages += appended

    summary = {
        "language": language.code,
        "counts": dict(counts),
        "skipped_count": len(skipped),
        "fit_only": fit_only_mode,
        "packages": packages,
        "text_skipped": text_skipped,
        "graphics_skipped": graphics_skipped,
        "append_skipped": append_skipped,
        "cycle_assets": [f"{file_hash:016X}" for file_hash in sorted(cycle_assets)],
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
    parser.add_argument("--cycle-asset", action="append", metavar="HASH",
                        help="an extra-text candidate this device cycle enables, by hash or hex "
                             "prefix; repeatable, and comma-separated values are read as well")
    args = parser.parse_args()

    sys.path.insert(0, str(args.runtime.resolve()))
    cycle_assets: frozenset[int] = frozenset()
    if args.cycle_asset:
        from extra_text import CANDIDATE_ASSETS, UnknownCandidate, resolve_candidates

        try:
            cycle_assets = frozenset(resolve_candidates(",".join(args.cycle_asset)))
        except UnknownCandidate as error:
            known = "\n".join(f"  {file_hash:016X}  {what}"
                              for file_hash, what in CANDIDATE_ASSETS.items())
            parser.error(f"--cycle-asset: {error}\nthe measured candidates are:\n{known}")
        for file_hash in sorted(cycle_assets):
            print(f"device cycle: enabling {file_hash:016X} -- {CANDIDATE_ASSETS[file_hash]}")
    build_patch(args.game, args.catalog, args.work, args.output, fit_only_mode=args.fit_only,
                apk=args.apk, builder_dir=args.builder, cycle_assets=cycle_assets)


if __name__ == "__main__":
    main()
