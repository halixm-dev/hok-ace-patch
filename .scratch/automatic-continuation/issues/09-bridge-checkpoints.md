# 09: Publish and reuse complete Android bridge outputs

Status: ready-for-agent
Implementation: complete
Verification: pending
Blocked by: 02, 08

## Scope and files

Own `android/app/src/main/python/android_bridge.py:build_snapshot/_build_scratch/clear_build/build_removal/keep_delta`, shared artifact-helper integration, necessary `tools/mobile_snapshot.py` receipt wrapper and new `tools/research/check_bridge_continuation.py`. Read architecture sections 2–5 and build_patch docstring. Keep fresh pipeline semantics and summary schema intact.

## Steps

1. Publish snapshot receipt only after exact-set/hash verification. A failed/incomplete snapshot remains an attempt; restart its transport instead of accepting fragments.
2. Add explicit bridge operations to inspect/verify a completed build and restart an incomplete attempt. Existing fresh-only APIs refuse `game/normal.apk/control.json/work/out`; do not bypass their guards blindly.
3. Isolate build attempt ownership and cleanup. Reset only incomplete attempt products; preserve committed snapshot, rollback originals, pinned APKs, authorization and a prior valid build until a replacement is published.
4. Publish STAGED last, after text/graphics/extra-text/repair/append, final restored-but-unstaged files, summary/metrics, complete staged hashes, pristine validation and session delta. The receipt hashes the complete output set plus final summary/delta.
5. Apply equivalent publication rules to Remove. Keep pristine copies separate from immutable actual phone snapshot; promotion of kept delta is later verified finalization, not build completion.
6. Expose verified receipt/results to Kotlin without redoing the build. Validate old receipts on restart; changed engine/game/delta invalidates the correct stage.

## Acceptance

- [ ] Summary-only, missing delta, missing restored output, extra/tampered file and incomplete native output are never reusable STAGED.
- [ ] Interrupted build reuses valid snapshot/APKs and restarts build in clean owned scratch.
- [ ] Complete build reuse performs zero stage calls and returns the same output hashes/summary/counts.
- [ ] Reset does not delete unresolved rollback or valid prior checkpoints.
- [ ] EN/ID, pristine-delta repatch and Remove preserve existing behavior/output.

## Checks and handoff

Run new bridge-continuation check plus mobile-snapshot, pristine-delta, artifact and staging-contract checks. Use synthetic bridge seams for fault boundaries and external real dumps for output parity. Record exact bridge API/receipt semantics for 10/16/17.

## Stop condition

If the fresh-only build guard fires, use an explicit validated reset/reuse path. Never recursively delete the session or assume existing output means completion.

## Comments

2026-11-12, pass 1: Implementation complete; verification pending. Every acceptance box remains
unchecked. No behavioral/unit/integration/UI-string/reference/performance/pipeline/device test ran.
No real game or immutable baseline/fixture input was touched; no commit, publication or release.

| Exact files changed for 09 | Purpose |
|---|---|
| `android/app/src/main/python/android_bridge.py` | Explicit measured identity, snapshot attempt/publication, owned build, complete inspection and conservative reset APIs; durable ownership before legacy build bytes; final output/delta/source/APK checks; isolated mutable pristine input; no build-time promotion. |
| `tools/mobile_snapshot.py` | Reject linked snapshot root; exact independently measured source-to-retained mapping, snapshot receipt publication last and explicit same-run verification. |
| `tools/research/check_bridge_continuation.py` (new) | Authored isolated synthetic snapshot/build commit-boundary, no-stage reuse, source/producer/APK/delta changes, missing summary/receipt/delta/restored output, extras/tampering, native-stage interruption, reset/link/Watchdog preservation, Remove and no-producer correctness probes. Synthetic staging replaces only the legacy staging entry point and writes real fixture delta binary with fingerprint=False; production package/fingerprint validation is unchanged. |
| `docs/features/language-switch.md`, `android-shizuku-patcher.md`, `patch-speed.md`, `asset-restore.md` | Document publication, pristine/actual snapshot separation, finalization and pending Kotlin/verification boundaries. Preserve earlier edits. |
| `.scratch/automatic-continuation/issues/09-bridge-checkpoints.md` | This check/API handoff. |

| Checks actually run | Result |
|---|---|
| `.venv/Scripts/python.exe -m py_compile android/app/src/main/python/android_bridge.py tools/mobile_snapshot.py tools/research/check_bridge_continuation.py` | Passed (syntax/bytecode compilation only), repeated after edits. |
| `git diff --check` | Passed; existing LF/CRLF notices only. Whitespace only. |
| Bridge/mobile-snapshot/pristine-delta/artifact/staging-contract checks; EN/ID parity, real producer extraction, Android instrumentation/device cycles | Not run: deferred to pass 2 by the user's two-pass override. |

Exact bridge handoff for tickets 10/16/17:

| API / record | Contract |
|---|---|
| `checkpoint_identity(engine_root, session_root, normal_apk, keep_root, target_json, request_json, current_files_json, readiness_json, prepared_apks_json, producer_json)` | Returns `{reusable,identity}`. `target` is the exact saved target; request includes action=translate/remove, saved en/id language and empty ordinary options. Caller supplies independently measured current complete source manifest `{path:{size,sha256}}`, readiness, verified source/normal/access APK evidence (Root: exact installed APKs) and freshly measured `EngineAssets.producerIdentity`. Bridge matches source to retained snapshot, rehashes normal APK, validates/read-hashes kept delta + staged-hash record, rehashes actual engine tree against producer's engine key and constructs shared schema-1 identity. Null producer returns `identity:null,reusable:false`: use ordinary verified fresh processing, never fabricate a producer or force snapshot/build reuse. Kotlin must independently validate installed patcher base/splits/native/ABI and prepared APK evidence; bridge cannot measure Android PackageManager itself. |
| `begin_snapshot_attempt(engine_root, session_root, run_id)` | Persist `snapshot-attempts/<UUID>/attempt-owner.json` before transport bytes; returns `{attempt,destination}` with absent destination `<attempt>/snapshot`. Caller persists attempt id/destination in its journal before transport. Existing extraction APIs remain fresh-destination only. |
| Snapshot transport → canonical publication | Under coordinator ownership, extract to returned destination; compare transport bytes/hash and successful tar exit; verify exact current source set/hashes. Persist rename intent, then durably rename the completed owned destination into **absent** `session/snapshot`; never replace an existing snapshot. Persist canonical ownership and call `snapshot_checkpoint(...,publish=true)` last. Crash after rename/before receipt is an owned incomplete canonical snapshot: Kotlin must recover its saved attempt/rename intent, reverify full independent source and publish, or remove only that proven-owned incomplete snapshot and restart transport. No generic session deletion or fragment reuse. Snapshot reset API deliberately cannot delete the canonical snapshot. |
| `snapshot_checkpoint(engine_root, session_root, run_id, identity_json, publish=False)` | Publish only after the above transport/source checks; otherwise rehash/verify existing snapshot receipt. Exact set includes Watchdog. Same `run_id` required; identity compares current target/game/APKs while saved producer receipt is independently verified, so engine/language/delta changes alone do not discard a usable snapshot. Null producer cannot publish reusable receipt: ordinary snapshot verification/build still works, without restart reuse. |
| `build_checkpoint(engine_root, session_root, run_id, normal_apk, expected_apk_sha256, language="en", keep_root=None, identity_json="null", remove=False)` | Always allocates fresh durable owned `build-attempts/<UUID>`; never adopts old game/work/out or replaces a committed build. Separate `scratch/` holds trusted read-only snapshot links and mutable pristine reconstruction; no hardlinks. Calls existing fresh translation/Remove pipeline unchanged. Revalidates source/APK/kept delta, adds restored outputs, finishes summary/metrics/hash/delta read-back for **all** fresh builds. Commit-last receipt only when full identity and reusable payload exist. Returns `{attempt,result_root,output_root,hashes_path,delta_path,summary,receipt,reusable}`. Empty translation output conservatively declines reuse. |
| Result layout / STAGED receipt | Immutable `<attempt>/result/{out/,bridge-summary.json,staged-hashes.json,metrics.json,pristine-delta.bin,final-manifest.json,build-receipt.json}`. `out/device_patch_summary.json` is the unchanged pipeline summary; bridge-summary retains the returned pristine metadata/counts. Full final manifest includes every final output and other non-reference artifacts. Shared receipt references bridge-summary/final-manifest/session delta; Remove has explicit `delta:null` while its empty delta binary remains a hashed artifact. A summary alone, missing delta/restored file, extra/tampered output or incomplete publication never proves STAGED. |
| `inspect_build_checkpoint(engine_root, session_root, run_id, attempt_id, normal_apk, keep_root, identity_json)` | Current independently reconciled complete identity required. Verifies same-run owner, snapshot receipt, actual source/normal/kept delta/engine, entire exact result set and delta/hash semantics; returns the same result/summary without staging, native transforms or mutation. Changed producer invalidates build only. Failure declines reuse and does not authorize deleting a receipt-bearing attempt. No no-op installed receipt in 09; 16 owns it. |
| Kotlin path integration (10) | GameFileTransaction currently hardcodes session/out and session/staged-hashes. Extend its source descriptor to derive returned paths from a validated/persisted attempt UUID under the same journal session, and pin it **before** apply. PristineDelta pending source must derive the same result path. Never add symlink aliases to a committed result or move its files after publication. Actual rollback remains canonical session/snapshot, with Watchdog and normal APK independent. No Kotlin coordinator/router implementation is in 09. |
| `reset_checkpoint_attempt(engine_root, session_root, run_id, attempt_id, stage="staged")` | Caller holds coordinator lock and first proves no apply/recovery journal references this attempt. Strict UUID + exact durable owner; stage is staged/snapshot only. Present receipt anywhere, even damaged, pins attempt and refuses reset. Deletes only fixed owned scratch products and incomplete result, or incomplete snapshot-attempt destination. Never deletes session, canonical snapshot, originals/Watchdog/APKs/authorization/prior committed results. Retry allocates a **new** attempt; owner records remain. Legacy `clear_build(session_root)` requires exact durable build-owner marker, refuses receipts and keeps original fresh-only guards. Missing legacy ownership is attention, not permission to clear. |
| `keep_delta(engine_root, session_root, keep_root)` | Existing verified finalization caller only; for explicit checkpoints pass `result_root` as session_root. It verifies any present receipt and final output/delta semantics before original promotion/removal; receipt-free ordinary fresh output still receives read-back checks but gains no restart reuse. Build never calls it. Kotlin retains all old/pending deltas until finalization is durable. Recovery must use saved normal/original material without needing a new engine, as before. |
| RunStore integration (10) | Full measured source identity arrives after claim. Extend safe measured-stage linkage for claimed run without changing immutable action/target/provider/authorization; do not fake pre-snapshot evidence or silently rebind saved authorization. Null inputIdentity/producer is not reuse authority. APIs do not grant authorization, consent or retries. |
| Tickets 17/18 | Whole-build reuse does zero stage calls. Fresh build keeps current mixed-package classification/restore, allowlist, catalog, append/read-back and package pass order. No cached restore decision or retry-copy optimization is introduced. 17 must bind any decision reuse to the snapshot/delta/current producer; 18 measures fresh retry work separately. |

Open gates/concerns: synthetic probes are authored but unexecuted; actual Android directory fsync,
link support (including Windows host permission to create synthetic fixture symlinks), native codec
pipeline and process-death publication require pass 2. Actual SHA/summary/metrics/delta output
comparisons are unrun. Real external
matching dump/APK controls must establish EN/ID, both switch directions, restored-but-unstaged delta,
Remove and hash/count/summary parity. Kotlin 10 must persist and pin selected attempts, implement
canonical snapshot ownership around rename, bind post-claim measured inputs safely and derive
transaction/finalization paths. Legacy unowned refused build debris intentionally refuses cleanup;
recovery/retention policy must not invent ownership. No new speed, safety or output-parity claim.



Final coordinator-review correction (pass 1): both final publication and inspection now validate
`bridge-summary.json` declarations as well as byte/hash/delta agreement. Every
`pristine.restored` file must exist in the complete output map; Remove's `removed` list must exactly
match it. Contradictory lists, duplicate/unsafe names and missing declared files fail closed without
changing either ordinary summary schema. Authored synthetic probes drop one restored file from
output **and** hash list **and** delta together while retaining the summary declaration, with and
without producer identity, plus a Remove-list contradiction. These probes are unrun.

Reset gap: if process death occurs after owned attempt/scratch directory creation but before the
legacy `build-owner.json` is written, reset refuses and retains that scratch directory. Ticket 10
may allocate a fresh owned attempt after reconciling the journal; it must not invent cleanup
ownership or delete the session. An authored synthetic probe covers retain + fresh restart.
Post-correction Python 3.12 `py_compile` passed for all three owned Python files; `git diff --check`
passed. Behavioral/output/parity/device gates remain pending.

Coordinator review: inspected ownership/publication/reset, preserved fresh pipeline semantics, complete exact sets and Kotlin API handoff. Requested corrections received for producer-null output validation, same-run snapshot receipt binding and declared restored/Remove output completeness. Python3.12 syntax and whitespace passed; all behavior/parity/device/host-link gates remain pending. Advance10 on implemented interfaces only.

Pass 2 (2026-11-12, fsync/Windows fix worker): check_bridge_continuation: the 15 errors were the fsync bug (`publish_receipt` via `checkpoint_snapshot`). The remaining `test_reset_preserves_published_and_prior_checkpoint` expected ArtifactError from `clear_build` with no `build-owner.json`; production refuses with FileNotFoundError from `read_record` (an OSError), which is still a refusal. The test now accepts `(ArtifactError, OSError)`, as the neighbouring reset test does. The `android_bridge.py` fsyncs use `rb+` or write handles and were unchanged.

Commands (each `.venv\Scripts\python.exe tools\research\<name>.py`, run in this order on Windows 11, Python 3.12; logs `D:\scratch\hok-ac-pass2\logs\<name>.fsync-fix.log`): check_run_artifacts PASS; check_windows_file_transaction 16/16 OK; check_windows_checkpoints 28/28 OK; check_windows_controls 23/23 OK; check_windows_signing 18/18 OK; check_windows_recovery 104/104 OK; check_bridge_continuation 15/15 OK; check_windows_repatch 14/14 OK; check_pristine_delta 15/15 OK; check_mobile_snapshot 8/8 OK. Before the fixes: run_artifacts failed (EBADF), file_transaction 4 failures/1 error, checkpoints 28 errors, controls/signing/recovery errors, bridge 15 errors. Synthetic only; no device, no game data, nothing committed.

Pass 2 device-cycle fix (2026-11-12): First real Android cycle on `f15a72e` failed in `build_checkpoint` (`_validate_checkpoint_inputs`) with `ArtifactError: Engine identity changed` because Python wrote 4 new `tools/__pycache__/*.pyc` files (`config_bin`, `extra_text`, `lineup_codes`, `pb_text`) during `estimate_snapshot_build` after `checkpoint_identity` ran. `android_bridge.py` now sets `sys.dont_write_bytecode = True` on load and in `_prepare` (alongside `EngineAssets.removeGenerated` cleanup of prior bytecode caches). Checked `tools/research/check_bridge_continuation.py` (15/15 OK) and `EngineProbeTest.testEngineTreeStaysImmutableAcrossBuildImportsAndCleansStaleCaches` (PASS on `f15a72e`).

Pass 2 output-boundary fix (2026-11-12): run `63ff…` reached final build publication,
then refused `Final staged hashes omit or differ from output`. The parent coordinator independently
rehashed the real output: all 14 numeric package files matched staged hashes. The remaining file
was the upstream stager's `package1_stage_manifest.json`; its sibling
`package1_metadata_axwzfeqp/` was empty. No phone action was performed by this fix worker.

The regression was added **before** the fix. Its fixture reproduces the exact seven-package
layout (`1`, `10`, `1050016095`, `15`, `19`, `20`, `21`), the pipeline summary, verified stage
report and empty metadata directory, using synthetic bytes and the real bridge publication,
inspection, hashes and delta checks. It first failed with the exact phone exception. Runtime
bytecode was inspected read-only: `stage_unity_package` creates the metadata temporary directory,
performs QtsPackage read-back and emits the report; package 19 uses `unity19_stage_manifest.json`.
The report describes that pass before later relocation/graphics/append. Its historical hashes are
not a replacement for final payload hashes.

`_staged_payload_manifest` now classifies the explicit verified runtime report schema and empty,
correctly named metadata directories for present packages. Reports remain unchanged in `out/`
and are hashed by the complete final manifest/receipt. Both publication and read-only inspection
still compare the full numeric payload set/hashes with staged hashes and the delta, and retain
restored/Remove declaration checks. Unknown files/directories, malformed or orphaned reports,
nonempty/orphaned metadata directories and empty/nested package directories refuse. Thirteen
negative publication cases and receipt/numeric-payload corruption/reuse checks cover the boundary.
No runtime binary, pipeline producer, phone state or signing/install path was changed.

| Exact commands (project root, Python 3.12 `.venv`) | Result |
|---|---|
| `New-Item -ItemType Directory -Force build/bridge-probe-temp`; set `$env:TEMP = (Resolve-Path build/bridge-probe-temp).Path` and `$env:TMP = $env:TEMP` before checks | Isolated disposable fixture storage. Initial default sandbox TEMP was denied before fixture setup; rerun used this writable directory. |
| `.venv/Scripts/python.exe tools/research/check_bridge_continuation.py BridgeContinuation.test_phone_runtime_metadata_does_not_enter_staged_payload` | Before fix: RED, exact `ArtifactError: Final staged hashes omit or differ from output`; after fix: PASS. |
| `.venv/Scripts/python.exe tools/research/check_bridge_continuation.py` | Final rerun: 18/18 PASS, 36.355 s. Synthetic only; unchanged existing 15 controls also pass. |
| `.venv/Scripts/python.exe -m py_compile android/app/src/main/python/android_bridge.py tools/research/check_bridge_continuation.py` | PASS. |
| `.venv/Scripts/python.exe tools/research/check_staging_contract.py` | PASS. |
| `git diff --check -- android/app/src/main/python/android_bridge.py tools/research/check_bridge_continuation.py docs/features/language-switch.md .scratch/automatic-continuation/issues/09-bridge-checkpoints.md` | PASS; existing LF/CRLF notice only. |

Files changed for this fix: `android/app/src/main/python/android_bridge.py`,
`tools/research/check_bridge_continuation.py`, this Comments section, and
`docs/features/language-switch.md`. Nothing committed. The parent owns rebuilding and the real
phone retry; no new device-output/parity verdict is claimed here. Windows uses its existing
`pristine_delta.package_files(staged)` payload extraction, as independently checked by the parent;
no Windows change is needed for this failure.

Pass 2 device-cycle C3 fix (2026-11-12): on `f15a72e` the patcher was force-stopped about 100 s into
`build_checkpoint` of run `248572aa`. On reopen `resetIncompleteBuilds` called `reset_checkpoint_attempt` for
attempts `1d868950…` and `2e20c16a…`; each raised `FileNotFoundError` from `clear_build` reading the absent
`scratch/build-owner.json`. Each attempt held `attempt-owner.json` and a scratch with only the `snapshot` link.
That is the normal kill shape, not damage: `create_attempt` fsyncs `attempt-owner.json` (run id, stage) first,
then `build_checkpoint` makes `scratch/`, links `scratch/snapshot` to the session snapshot, and writes nothing
else there until `build_snapshot`/`build_removal` call `_own_legacy_build` (after verifying the snapshot and
hashing the APK, the ~100 s window). `clear_build` also returns an owned scratch to that same shape, so a second
reset failed the same way. The earlier "Reset gap" note (retain and refuse) is superseded for this one shape.

`reset_checkpoint_attempt` (staged) now: proves the attempt owner as before (`_owned_attempt`, exact
`{schema, run_id, stage}`; missing owner still refuses), refuses any `build-receipt.json` as before, refuses a
linked or non-directory scratch, runs `clear_build` only when a build owner exists, then `_clear_scratch_shell`:
the scratch may hold nothing, or exactly one entry `snapshot` that is a symlink whose target is exactly
`<session>/snapshot`; that link is unlinked (never followed) and the empty scratch removed. Any other entry,
including a `build-owner.json.partial` from a kill inside `write_atomic`, a foreign link target, or a real
directory, refuses with `PatchError` and leaves the scratch as it was. The attempt owner stays; a repeated reset
is a no-op. `clear_build` with no owner now refuses explicitly (`PatchError: No build ownership to reset`), not
by `FileNotFoundError`, so the Pass 2 relaxation of `test_reset_preserves_published_and_prior_checkpoint` is
restored to that exact refusal. Kotlin unchanged: a reset refusal is still logged by `resetIncompleteBuilds` and
the run continues in a fresh attempt. That is safe because `build_checkpoint` always allocates a new UUID attempt
(exclusive `attempt-owner.json`), never reads an older attempt, the journal-referenced attempt and published
results are skipped before any reset, and `requireSpace` measures real free space, so a retained attempt costs
only storage. Failing the run instead would block continuation on cleanup of material that is not used.

| Check | Result |
|---|---|
| `.venv/Scripts/python.exe tools/research/check_bridge_continuation.py` | 21/21 PASS, no skips (Windows host created the links). New: `test_phone_c3_killed_before_build_owner_clears_link_never_target` (snapshot tree unchanged, link removed, owner kept, second reset no-op, fresh build in new attempt), `test_scratch_without_build_owner_refuses_anything_unexpected` (extra entry, partial owner, foreign link, directory in place of link), `test_scratch_without_build_owner_requires_attempt_owner`, `test_crash_before_scratch_link_clears_empty_scratch_and_restarts_fresh` (replaces the retain test); interrupted-build test now also proves only `attempt-owner.json` remains and a second reset passes. |
| `.venv/Scripts/python.exe -m py_compile android/app/src/main/python/android_bridge.py tools/research/check_bridge_continuation.py` | PASS. |

Not covered: `tools/research/check_update_redownload.py` calls `clear_build` on a session it never owned; it
already refused before this change (`FileNotFoundError`), now with `PatchError`. It needs the update-cycle dump
and was not run. A kill inside the owned build can leave `restore-trial/`, outside `clear_build`'s allowlist;
that scratch still refuses and is retained. Phone re-check of the C3 shape is pending.

### 2026-11-12: Pass 2 device-cycle build-check fix

Phone f15a72e, run 248572aa (18:54–18:59): after an approved Re-download of package `1` the game downloaded
it again; the next `build_checkpoint` recorded `delta_before` with `redownload.json` present, then
`_refuse_stuck_update` (inside `build_snapshot`) unlinked the record at 18:56:31 because the package was back.
After 317 s the post-build kept-delta check refused ("Snapshot, kept delta or pinned APK changed during
build"); `delta.bin` and `staged-hashes.json` were unchanged. Every first build after a Re-download burned an attempt.

Fix: the build no longer writes the kept folder. `_refuse_stuck_update` returns the obsolete record's identity
(re-hashed after reading) and `build_snapshot` / `build_removal` report it as `redownload_done` in the bridge
summary (receipt-hashed). `finalization_plan` carries it (null for a copied completed output,
`reuse-provenance.json`); `PristineDelta.finalize` drops the record last, after the delta/record promotion and
the restore-refused drop, and before `finalized` is journaled, only while it holds exactly the sealed bytes.
A cut after the drop resumes: the "Re-download knowledge changed" check accepts absence only for that plan. The
legacy `keep_delta` drops it the same way. The post-build check in `build_checkpoint` is unchanged and still
refuses any kept change. Receipt: a published build keeps the record in its identity, so inspect/reuse in the
same run holds; after finalization the old identity no longer matches (a stale build cannot apply), and the next
build binds the new identity once with no claim left (no loop). Completion reuse compares only
target/request/translation/producer and re-runs `finalize(old)`, which accepts the dropped record.

| Check | Result |
|---|---|
| `.venv/Scripts/python.exe tools/research/check_bridge_continuation.py` | 25/25 PASS. New: `test_phone_f15a72e_build_after_redownload_keeps_record_and_publishes` (fails under the old mid-build drop with the phone's exact error), `test_redownload_record_still_waiting_refuses_and_is_kept`, `test_any_kept_change_during_build_still_refuses` (record removed or rewritten, staged hashes, restore-refused, delta), `test_copied_completed_output_never_drops_a_record`. |
| `py_compile` bridge + check; `check_staging_contract.py` | PASS. |
| `gradlew :app:testDebugUnitTest :app:assembleDebug :app:assembleDebugAndroidTest -PpatchVersionCode=100 -PfullCodecs=true` | BUILD SUCCESSFUL. |

Not covered: no instrumentation probe for the new `finalize` drop (compiled only); `check_asset_restore.py` and
`check_update_redownload.py` need game dumps and were not run. `build_snapshot` still writes
`restore-refused.json` on its `UPDATE_MIXED` refusal; that path raises before the post-build check and the record
is the refusal's purpose, so it was left as is. Phone re-check pending.
