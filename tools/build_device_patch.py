"""Stage English replacements for every text package pulled from an updated Android install.

Text tables are staged in place by the scanner layout: <game>/WXQ_Data/Package/builtin/<package id>/.
Two things extend that: packages whose translatable content only exists in the APK are rebuilt whole
against the APK (``package_rebuild``), and the catalog's texture edits are ported onto the device's
ASTC textures as a second pass. Each changed package is written to <output>/<package id>/ and can be
pushed back to files/QtsVFSCache/packages/<package id>/ on the device.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import pathlib
import shutil
import sys
import time

from build_mobile_patch import synthetic_metadata_builder


SLOT_ERROR = re.compile(r"no safe insertion point for slot (\d+)")
RETRY_SCHEMA = 1
# A retry proof pre-routes tables only after this many independent baseline runs observed the same
# key, the same failures and the same drops (`confirm_retry_proofs`).
RETRY_PROOF_CONFIRMATIONS = 2
ERROR_TEXT_LIMIT = 500
PRODUCER_KEY = re.compile(r"[0-9a-f]{64}\Z")


def attribute_failure(error: BaseException, package=None) -> tuple[int | None, str | None]:
    """Return ``(file hash, method)`` for a stage_unity_package failure; see `failing_asset`.

    `method` is ``slot-offset`` (the slot holding the reported offset), ``slot-offset-unmatched``
    (no slot holds it), ``traceback`` (the asset the stager was iterating) or None (no stager
    frame named an asset).
    """
    match = SLOT_ERROR.search(str(error))
    if match and package is not None:
        offset = int(match.group(1))
        for file_hash, chunks in package.build_slot_map().items():
            for slot in chunks.values():
                if slot.slot_offset <= offset < slot.slot_offset + slot.slot_size:
                    return file_hash, "slot-offset"
        return None, "slot-offset-unmatched"
    tb = error.__traceback__
    found = None
    while tb:
        if tb.tb_frame.f_code.co_name == "stage_unity_package":
            found = tb.tb_frame.f_locals.get("file_hash")
        tb = tb.tb_next
    return found, ("traceback" if found is not None else None)


def failing_asset(error: BaseException, package=None) -> int | None:
    """Return the file hash responsible for a stage_unity_package failure.

    Position-index errors are raised after all assets were fitted, so the asset
    being iterated is unrelated; blame the asset whose original slot holds the offset.
    """
    return attribute_failure(error, package)[0]


def _tree_size(root: pathlib.Path) -> tuple[int, int]:
    """Return ``(files, bytes)`` of the regular files under <root>; (0, 0) when it is absent."""
    files = size = 0
    if root.is_dir():
        for path in root.rglob("*"):
            if path.is_file():
                files += 1
                size += path.stat().st_size
    return files, size


def _sha256(path: pathlib.Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def confirm_retry_proofs(observations: list[dict]) -> dict:
    """Merge the retry proofs several baseline runs observed into a confirmed proof set.

    Proofs group by ``(package_id, loop, key)``. A group whose observations agree exactly on the
    drops and on every attributed failure becomes one proof carrying ``confirmations``; a group that
    disagrees anywhere is left out and listed under ``conflicts``, because it is not deterministic.
    `build_patch` uses a proof only with at least `RETRY_PROOF_CONFIRMATIONS` confirmations.
    """
    groups: dict[tuple, list[dict]] = {}
    for proof in observations:
        if (not isinstance(proof, dict) or proof.get("schema") != RETRY_SCHEMA
                or proof.get("outcome") != "staged" or proof.get("prerouted")):
            continue
        groups.setdefault((proof["package_id"], proof["loop"], proof["key"]), []).append(proof)
    proofs, conflicts = [], []
    for (package_id, loop, key), seen in sorted(groups.items()):
        shapes = {json.dumps([proof["dropped"], proof["attributions"]], sort_keys=True) for proof in seen}
        if len(shapes) != 1:
            conflicts.append({"package_id": package_id, "loop": loop, "key": key, "observations": len(seen)})
            continue
        first = seen[0]
        proofs.append({"schema": RETRY_SCHEMA, "package_id": package_id, "loop": loop, "key": key,
                       "outcome": "staged", "dropped": first["dropped"],
                       "attributions": first["attributions"], "confirmations": len(seen)})
    return {"schema": RETRY_SCHEMA, "proofs": proofs, "conflicts": conflicts}


class _RetryProofs:
    """Exact-input retry proofs: the key of a staging loop and the confirmed drops recorded for it.

    The key covers the caller's producer key (code, runtime and interpreter), the package id, the
    loop and its stager options, the full SHA-256 and size of the package's index and every shard
    beside the scanner's own fingerprint, and the SHA-256 and size of every replacement the loop
    starts with. Any change to one of them is a different key, so a proof never outlives its inputs.
    """

    def __init__(self, producer_key: str, proofs: list[dict], game: pathlib.Path, fingerprints: dict, log):
        self.producer_key = producer_key
        self.game = game
        self.fingerprints = fingerprints
        self.log = log
        self._sources: dict[str, dict] = {}
        self.proofs: dict[tuple[str, str, str], list[str]] = {}
        for proof in proofs:
            if (isinstance(proof, dict) and proof.get("schema") == RETRY_SCHEMA
                    and proof.get("outcome") == "staged" and not proof.get("prerouted")
                    and isinstance(proof.get("confirmations"), int)
                    and proof["confirmations"] >= RETRY_PROOF_CONFIRMATIONS
                    and isinstance(proof.get("dropped"), list) and proof["dropped"]
                    and all(isinstance(h, str) and re.fullmatch(r"[0-9A-F]{16}", h) for h in proof["dropped"])
                    and len(set(proof["dropped"])) == len(proof["dropped"])):
                self.proofs[(str(proof["package_id"]), str(proof["loop"]), str(proof["key"]))] = list(proof["dropped"])

    def _source(self, package) -> dict:
        cached = self._sources.get(package.package_id)
        if cached is None:
            cached = {}
            for path in [package.index_path, *package.shard_paths]:
                cached[path.name] = {
                    "size": path.stat().st_size,
                    "sha256": _sha256(path),
                    "scan_fingerprint": str(self.fingerprints.get(str(path.relative_to(self.game)))),
                }
            self._sources[package.package_id] = cached
        return cached

    def key(self, package, loop_dir: pathlib.Path, loop: str, donations: bool) -> str:
        identity = {
            "schema": RETRY_SCHEMA,
            "producer": self.producer_key,
            "package_id": package.package_id,
            "loop": loop,
            "stager": {"global_donations": donations, "verify_all_unrelated": False},
            "source": self._source(package),
            "replacements": {path.name.upper(): {"size": path.stat().st_size, "sha256": _sha256(path)}
                             for path in sorted(loop_dir.glob("*.assets"))},
        }
        encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(encoded.encode("ascii")).hexdigest()

    def lookup(self, package_id: str, loop: str, key: str) -> list[str] | None:
        return self.proofs.get((package_id, loop, key))


def _retry_loop(package, loop_dir: pathlib.Path, source_dir: pathlib.Path, attempt, *, loop: str,
                donations: bool, raise_unattributed: bool, output: pathlib.Path, log,
                proofs: _RetryProofs | None, record: dict | None):
    """Stage <loop_dir>, dropping the attributed failing table and retrying until it stages.

    Returns ``(report, dropped, unattributed error)``. An unattributed failure is re-raised when
    <raise_unattributed>, else returned with ``report`` None. With a confirmed proof for this exact
    key the proof's drops are removed before the first attempt; if that attempt fails in any way, the
    removed tables are copied back from <source_dir>, the package copy it wrote is removed, and the
    baseline loop runs from the full set as if the proof had not existed.
    """
    dropped: list[str] = []
    attributions: list[dict] = []
    attempts: list[dict] | None = None
    key = None
    if record is not None:
        attempts = []
        record.update({"loop": loop, "key": None, "key_seconds": 0.0, "prerouted": None,
                       "preroute_outcome": None, "attempts": attempts, "outcome": None,
                       "dropped": dropped, "proof": None})
    if proofs is not None:
        started = time.perf_counter()
        key = proofs.key(package, loop_dir, loop, donations)
        if record is not None:
            record["key"] = key
            record["key_seconds"] = time.perf_counter() - started

    def run(*, prerouted: bool):
        started = time.perf_counter()
        entry = None
        if attempts is not None:
            files, size = _tree_size(loop_dir)
            entry = {"index": len(attempts) + 1, "prerouted": prerouted, "replacement_files": files,
                     "replacement_bytes": size, "outcome": "failed", "error_type": None, "error": None,
                     "attributed": None, "attribution": None}
            attempts.append(entry)
        try:
            result = attempt(loop_dir)
            if entry is not None:
                entry["outcome"] = "staged"
            return result
        except BaseException as error:
            if entry is not None:
                entry["error_type"] = type(error).__name__
                entry["error"] = str(error)[:ERROR_TEXT_LIMIT]
            raise
        finally:
            if entry is not None:
                entry["seconds"] = time.perf_counter() - started
                entry["output_files"], entry["output_bytes"] = _tree_size(output / package.package_id)

    planned = proofs.lookup(package.package_id, loop, key) if proofs is not None and key is not None else None
    if planned is not None:
        victims = [next(loop_dir.glob(f"{name}.assets"), None) for name in planned]
        if any(victim is None for victim in victims):
            log(f"package {package.package_id}: a {loop} retry proof names a table this plan lacks; not used")
        elif (output / package.package_id).exists():
            log(f"package {package.package_id}: an output copy already exists; {loop} retry proof not used")
        else:
            names = [victim.name for victim in victims]
            for victim in victims:
                victim.unlink()
            if record is not None:
                record["prerouted"] = list(planned)
            try:
                report = run(prerouted=True)
            except Exception as error:  # any failure here falls back to the unchanged baseline loop
                log(f"package {package.package_id}: {loop} staging with {len(names)} proven drops failed "
                    f"({error}); retrying the baseline loop from the full plan")
                shutil.rmtree(output / package.package_id, ignore_errors=True)
                for name in names:
                    shutil.copy2(source_dir / name, loop_dir / name)
                if record is not None:
                    record["preroute_outcome"] = "fell-back"
            else:
                dropped.extend(planned)
                log(f"package {package.package_id}: {len(planned)} tables left to relocation by a "
                    f"confirmed {loop} retry proof")
                if record is not None:
                    record["preroute_outcome"] = "staged"
                    record["outcome"] = "staged"
                return report, dropped, None

    report = None
    # Guarded on a non-empty set: a package whose every asset was dropped has nothing
    # left to stage, and looping again would never succeed.
    while any(loop_dir.glob("*.assets")):
        try:
            report = run(prerouted=False)
            break
        except RuntimeError as error:
            file_hash, method = attribute_failure(error, package)
            victim = next(loop_dir.glob(f"{file_hash:016X}.assets"), None) if file_hash is not None else None
            if attempts is not None:
                attempts[-1]["attributed"] = f"{file_hash:016X}" if file_hash is not None else None
                attempts[-1]["attribution"] = method if victim is not None else (
                    f"{method}-absent" if method else None)
            if victim is None:
                if record is not None:
                    record["outcome"] = "unattributed-raise" if raise_unattributed else "unattributed-fallback"
                if raise_unattributed:
                    raise
                return None, dropped, error
            victim.unlink()
            dropped.append(f"{file_hash:016X}")
            attributions.append({"hash": f"{file_hash:016X}", "method": method,
                                 "error_type": type(error).__name__, "error": str(error)[:ERROR_TEXT_LIMIT]})
    if record is not None:
        record["outcome"] = "staged" if report is not None else "empty"
        if report is not None and key is not None and dropped:
            record["proof"] = {"schema": RETRY_SCHEMA, "package_id": package.package_id, "loop": loop,
                               "key": key, "outcome": "staged", "prerouted": False,
                               "dropped": list(dropped), "attributions": attributions}
    return report, dropped, None


def _stage_package(package, replacements: pathlib.Path, *, stage, fit_only, fit_only_mode: bool,
                   work: pathlib.Path, output: pathlib.Path, log, proofs: _RetryProofs | None = None,
                   record: dict | None = None):
    """Stage one package's text tables in place: the full loop, then fit-only when that fails.

    Returns ``(report, mode, fit_summary)``. <stage> is ``stage(directory, donations)``; <fit_only>
    is ``fit_only(package, replacements) -> (fit_summary, directory)``.
    """
    fit_summary = None
    report = None
    mode = "full"
    loops = record.setdefault("loops", []) if record is not None else None
    copies = record.setdefault("copies", []) if record is not None else None
    if not fit_only_mode:
        full_replacements = work / "full-replacements" / package.package_id
        if full_replacements.exists():
            shutil.rmtree(full_replacements)
        started = time.perf_counter()
        shutil.copytree(replacements, full_replacements)
        if copies is not None:
            files, size = _tree_size(full_replacements)
            copies.append({"kind": "full-replacements", "files": files, "bytes": size,
                           "seconds": time.perf_counter() - started})
        loop_record = {} if loops is not None else None
        if loops is not None:
            loops.append(loop_record)
        report, full_dropped, error = _retry_loop(
            package, full_replacements, replacements, lambda directory: stage(directory, True),
            loop="full", donations=True, raise_unattributed=False, output=output, log=log,
            proofs=proofs, record=loop_record)
        if error is not None:
            log(f"package {package.package_id}: full staging failed ({error}); retrying fit-only")
            mode = "fit-only"
        if mode == "full":
            fit_summary = {"dropped_while_staging": full_dropped}
            log(f"package {package.package_id}: dropped {len(full_dropped)} assets in full mode")
    if fit_only_mode or mode == "fit-only":
        mode = "fit-only"
        started = time.perf_counter()
        fit_summary, fit_replacements = fit_only(package, replacements)
        if copies is not None:
            files, size = _tree_size(fit_replacements)
            copies.append({"kind": "fit-replacements", "files": files, "bytes": size,
                           "seconds": time.perf_counter() - started,
                           "includes": "capacity_report"})
        loop_record = {} if loops is not None else None
        if loops is not None:
            loops.append(loop_record)
        report, dropped, _error = _retry_loop(
            package, fit_replacements, replacements, lambda directory: stage(directory, False),
            loop="fit-only", donations=False, raise_unattributed=True, output=output, log=log,
            proofs=proofs, record=loop_record)
        fit_summary["dropped_while_staging"] = dropped
        log(f"package {package.package_id}: dropped {len(dropped)} assets that competed for slack")
    return report, mode, fit_summary


def _retry_totals(metrics: dict) -> dict:
    """Sum the per-attempt staging metrics across every package."""
    totals = {"packages": 0, "attempts": 0, "failed_attempts": 0, "prerouted_attempts": 0,
              "stage_seconds": 0.0, "failed_stage_seconds": 0.0, "attempt_output_bytes": 0,
              "failed_attempt_output_bytes": 0, "replacement_copy_files": 0, "replacement_copy_bytes": 0,
              "replacement_copy_seconds": 0.0, "key_seconds": 0.0, "prerouted_tables": 0,
              "preroute_fallbacks": 0, "relocated_tables": 0, "relocate_seconds": 0.0}
    for package in metrics["packages"]:
        totals["packages"] += 1
        for copy in package.get("copies", []):
            totals["replacement_copy_files"] += copy["files"]
            totals["replacement_copy_bytes"] += copy["bytes"]
            totals["replacement_copy_seconds"] += copy["seconds"]
        for loop in package.get("loops", []):
            totals["key_seconds"] += loop.get("key_seconds", 0.0)
            if loop.get("preroute_outcome") == "fell-back":
                totals["preroute_fallbacks"] += 1
            elif loop.get("preroute_outcome") == "staged":
                totals["prerouted_tables"] += len(loop["prerouted"])
            for attempt in loop.get("attempts", []):
                totals["attempts"] += 1
                totals["stage_seconds"] += attempt["seconds"]
                totals["attempt_output_bytes"] += attempt["output_bytes"]
                totals["prerouted_attempts"] += bool(attempt["prerouted"])
                if attempt["outcome"] != "staged":
                    totals["failed_attempts"] += 1
                    totals["failed_stage_seconds"] += attempt["seconds"]
                    totals["failed_attempt_output_bytes"] += attempt["output_bytes"]
        relocation = package.get("relocation")
        if relocation:
            totals["relocated_tables"] += len(relocation["written"])
            totals["relocate_seconds"] += relocation["seconds"]
    return totals


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
                staging_metrics: dict | None = None, retry_proofs: dict | None = None,
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
    - Before the first catalog load it calls `engine_hooks.install()` with no receipts, which wraps
      `adaptive.load_catalog` alone (terminology, the catalog supplement and the data-update catalog
      edits); `scan` and `receipt_root` are taken only by a PC job. Right after `adaptive.scan` it calls
      `resource_tokens.expand_staged(plans, log, language.resource_terms)` on the materialized
      replacements, so both staging paths carry the expanded resource tokens.
    - `cycle_assets` is a device cycle's one variable: the candidate queue's assets
      (`extra_text.CANDIDATE_ASSETS`) this run enables on top of the allowlist,
      `extra_text.SAFE_ASSETS`. Empty on a normal run. It must reach **both** paths that can translate
      such an asset — `extra_text.plan_package` and `package_rebuild.make_transform` — because the
      extra-text pass skips the packages a rebuild replaced whole, and package `1`, where all but one
      of the candidates live, was one of them while `REBUILD_PACKAGES` named it. A candidate
      enabled in only one path is a silent no-op for the packages the other owns. Both paths rewrite an
      enabled asset through the one `extra_text.rewrite_config`. The three lineup bins
      (`lineup_codes.LINEUP_BINS`) go through `lineup_codes.rewrite_bin` there: the text inside each
      share code and in the row text fields is translated, every other byte of the code and the row is
      kept, and the bin's fields 1 and 4 are resealed (`config_bin.reseal`), with resource tokens
      expanded per string before the seal; a run that does not enable a lineup bin leaves it
      byte-identical. A lineup bin the override layer lacks reaches it by append (`transform.config`),
      like any other candidate. Today the threading is
      the reverse of that: with `REBUILD_PACKAGES` empty, `plan_package` reaches every package and
      `make_transform`'s candidate branch is unreachable, so the two must stay wired together or putting
      a package back in `REBUILD_PACKAGES` silently stops the knob working there.
      `tools/build_device_patch.py --cycle-asset` is the only way to set it, and it accepts only a hash
      on `extra_text.CANDIDATE_ASSETS`.
    - It calls `qts_relocate.install_btree_slot_map()` before scanning, so a re-run reads live chunks
      rather than superseded copies of relocated ones. A shard whose B-tree will not read keeps the
      stock scanner's map; the run logs each one (`qts_relocate.BTREE_FALLBACKS`) and goes on, since
      that map is right on a pristine shard. Its live-offset check reads the current
      page table and tree pages without loading the shard payload; it caches no mutable tree state.
      Writable `Shard` loads fill one bytearray directly; saves compare 64 KiB regions against the
      current staged file and write only changed regions, restoring the same final file length.
      Comparisons use bounded temporary buffers. Package layout, pass order and read-back checks
      stay intact; no mutable disk state is cached between saves.
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
    - The drop loop (`_retry_loop`, once for `full` and once for `fit-only`) drops the one table each
      failure is attributed to (`attribute_failure`: the slot holding a reported offset, else the
      asset the stager frame was iterating) and retries. An unattributed full failure falls back to
      fit-only; an unattributed fit-only failure is raised.
    - `staging_metrics` (default None) is a dict the run fills in place with what the drop loop cost:
      per package the replacement-tree copies (files, bytes, seconds), each attempt's replacement
      set, duration, outcome, error, attributed hash and method, and the files/bytes of the package
      copy under `output/` after it, the relocation of the tables it handed on, and `totals`. It is
      measurement only: it is not part of `device_patch_summary.json` and changes no staged byte.
    - `retry_proofs` (default None; no shipped caller passes it) is `{"producer_key": <64 hex>,
      "proofs": [...]}` from `confirm_retry_proofs`. With it, each loop's exact-input key is hashed
      (producer, package id, loop and stager options, full SHA-256 of the index and shards, every
      starting replacement) and recorded in `staging_metrics` with the baseline `proof` it observed.
      A proof with `RETRY_PROOF_CONFIRMATIONS` identical baseline observations of the same key, and
      only then, removes its drops before the first attempt, in the recorded order, so
      `dropped_while_staging`, `text_skipped` and relocation see the same tables as the baseline:
      every pre-routed table still goes to `relocate_text` or is reported as not applied. It is
      skipped when the plan lacks a named table or the package's output copy already exists (as it
      does after a failed full loop, so a fit-only proof is not used after that fallback); if the
      pre-routed attempt fails in any way, the tables are copied back, its output copy removed and
      the baseline loop runs from the full plan. An unattributed or fit-only fallback is never
      skipped. Without a valid producer key every package keeps the baseline loop.
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
      edit present in them onto the device ASTC textures (`port_atlas`'s default `codec="astc"`; the
      PC edition's `pc_catalog` passes `"bc7"`), draws this repo's labels into each atlas the
      catalog has no edit for (`mobile_graphics.LABEL_ATLASES`, counted as a texture like an edit, and
      skipped the same way), replaces each standalone label the catalog has no edit for with this
      repo's art in the catalog's language (`mobile_graphics.LABEL_TEXTURES`, counted and skipped the
      same way; a package without the texture draws nothing), and runs the extra-text pass. Drawing the Secret Technique title atlas
      also re-lays its title sprites (`card_titles.relayout`, ADR 0009): package `19`'s Sprite table,
      its TimiAtlas and 33 card prefabs are rewritten in place beside the atlas. They are not counted as
      textures and add no field; a layout that does not match refuses the atlas, which is then skipped
      like any texture, and none of them is written. `skip` keeps
      it off a package the rebuild already replaced whole, which no longer matches the device's
      container. ASTC encoding reuses at most 512 exact pixel/geometry results whose input is at most
      4096 bytes; larger images keep the native path. Codec settings and texture gates are unchanged.
      A texture package copied for the first time reuses its source chunk offsets, retargeted to
      that identical copy; an existing output package is scanned afresh before relocation.
      It returns `(reports, skipped)`: the reports become `packages`, the skips become
      `graphics_skipped`. It then calls `repair_card_dictionaries` to repair an older patch's
      already-English card dictionaries; successful repairs use `relocated-text` entries and
      unmeasured layouts are reported in `text_skipped`. Extra-text planners check asset eligibility
      in the package index before scanning chunks; card repair scans chunks only if an indexed
      dictionary has a non-native chunk size, using the staged index when present. These checks do
      not change the allowlist, enabled candidates, pass order or summary counts.
      Last of all, with an APK, it calls
      `package_rebuild.add_prime_only(...)` — also keyed on `rebuilt` — so an appended asset lands on
      the copy the passes above staged instead of being overwritten by one.
      The append reuses its just-read prime source slot map within the same call; the source is
      unchanged, and the written output still gets a fresh QtsPackage scan and read-back.
    """
    from wxq_patch import adaptive
    from wxq_patch.unity_package_installer import capacity_report, stage_unity_package
    from qts_relocate import BTREE_FALLBACKS, install_btree_slot_map
    from device_extensions import exclude_extra_chunks, extend_graphics, relocate_text, repair_card_dictionaries
    from languages import for_catalog
    from engine_hooks import install as install_engine_hooks
    from resource_tokens import expand_staged

    install_btree_slot_map()
    BTREE_FALLBACKS.clear()
    # Before the first load: the scanner and every pass after it load the catalog through this.
    install_engine_hooks()
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
    expand_staged(plans, log, language.resource_terms)

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

    proofs = None
    if retry_proofs is not None:
        producer_key = retry_proofs.get("producer_key") if isinstance(retry_proofs, dict) else None
        if isinstance(producer_key, str) and PRODUCER_KEY.fullmatch(producer_key):
            proofs = _RetryProofs(producer_key, list(retry_proofs.get("proofs") or []), game, fingerprints, log)
            log(f"retry proofs: {len(proofs.proofs)} confirmed for this producer")
        else:
            log("retry proofs ignored: no valid producer key; every package keeps the baseline retry loop")
    if staging_metrics is not None:
        staging_metrics.clear()
        staging_metrics.update({"schema": RETRY_SCHEMA, "retry_proofs_enabled": proofs is not None,
                                "packages": []})
    package_metrics: dict[str, dict] = {}

    for package, replacements, _per_asset in plans:
        # A rebuilt package no longer matches the device's copy, so the in-place stager must not
        # re-derive it; the rebuild already carried everything the package holds.
        if package.package_id in rebuilt:
            continue

        record = None
        if staging_metrics is not None:
            record = {"package_id": package.package_id}
            staging_metrics["packages"].append(record)
            package_metrics[package.package_id] = record
        all_replacements = replacements
        planned = sorted(path.stem.upper() for path in all_replacements.glob("*.assets"))
        # Tables that would need more chunks than the original has are kept away from the stager,
        # which would invent lookup keys for the new chunks; relocate_text appends them instead.
        started = time.perf_counter()
        replacements, excluded = exclude_extra_chunks(package, all_replacements, work, log)
        if record is not None:
            files, size = _tree_size(replacements)
            record.update({"planned_count": len(planned), "excluded_extra_chunks": sorted(excluded),
                           "copies": [{"kind": "safe-replacements", "files": files, "bytes": size,
                                       "seconds": time.perf_counter() - started}]})
        report, mode, fit_summary = _stage_package(
            package, replacements,
            stage=lambda directory, donations, package=package: stage(package, directory, fingerprints,
                                                                       donations),
            fit_only=fit_only, fit_only_mode=fit_only_mode, work=work, output=output, log=log,
            proofs=proofs, record=record)
        if record is not None:
            record["mode"] = mode
            record["staged"] = report is not None
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
        started = time.perf_counter()
        written, refused_text = relocate_text(package, output, dropped, log)
        if package.package_id in package_metrics:
            package_metrics[package.package_id]["relocation"] = {
                "offered": sorted(f"{file_hash:016X}" for file_hash in dropped),
                "written": sorted(written), "refused": sorted(refused_text),
                "seconds": time.perf_counter() - started}
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
        if package_id in package_metrics:
            package_metrics[package_id]["not_applied"] = [h for h in planned if h not in applied]
    if staging_metrics is not None:
        staging_metrics["totals"] = _retry_totals(staging_metrics)

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

    for shard, reason in sorted(BTREE_FALLBACKS.items()):
        log(f"{pathlib.Path(shard).name}: B-tree did not read ({reason}); slots taken from the stock "
            "scanner, which can be stale if this shard was relocated before")

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
