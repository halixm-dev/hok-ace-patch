---
feature: patch-speed
status: built; phone-checked on the Redmi Note 9 Pro
updated: 2026-11-18
branch: master
---

# Android patch run speed

## Report

### Phone observations on the Root phone `ebad528e` (2026-11-18, single runs, no comparison)

By the user's decision of 2026-11-18 the performance gate closes on single runs: one phone (Redmi
Note 9 Pro, KernelSU, Root provider), one run per case, no repeats, so no shortcut below is claimed as a
measured saving. The [lab notebook](../lab-notebook.md)'s 2026-11-18 Root and Re-download entries hold the runs.

| Case | Observed |
|---|---|
| Fresh EN patch | About 18–19 min: prepare 40 s (first run only), snapshot about 6 min (unpack 78–84 s, identity 54–57 s, checkpoint 144–150 s), build 534–564 s, writes 2–3 s, final check about 1 min |
| Same-language repeat | Complete with 11 files rebuilt from the delta and none written (identical-write skips) |
| Resume after a kill or force-stop mid-apply | About 10 min: rollback about 2 min, snapshot recheck about 2.5 min, build inspection about 2.3 min, no rebuild |
| Force-stop at the final check (final-restore-only) | 2 min: no restore, rebuild or write |
| Remove | 15.7 min |
| After an automatic Re-download, *Downloads finished* to complete | 18 min 45 s: unpack 81.6 s, identity 50.7 s, checkpoint 144.5 s, build 571.5 s (asset restore of 19 and 20 included). Second update cycle (2026-11-19): 19 min 28 s, unpack 77.6 s, identity 51.3 s, checkpoint 155.2 s, build 602.6 s |
| Re-download planning | `redownload_plan` 89–97 s per plan |

### Phone observations on `f15a72e` (2026-11-12 to 2026-11-13, no comparison)

Single observations from the automatic continuation cycles, Android patcher on Wireless debugging; the
[lab notebook](../lab-notebook.md) holds the runs. None is a benchmark, and none is compared with the historical
616–621 s, which measured other code, data and phone.

| Observation | Value |
|---|---|
| Run without an interruption, Start to complete | 17–19 min (ID, ID repeat, EN, Remove) |
| Corrected C2 retry, coordinator time | 647.399 s; minimum sampled free space 4,115,369,984 B |
| Checkpoint reuse after an interruption | C3: snapshot reused (44 s, then 85 s revalidation, no unpack); C5: verified build reused; C6: only the normal install repeated |
| Automatic Re-download run `99584a53` | Snapshot unpack 56.6 s, build 345.5 s after the downloads, 37 min in all including about 13 min of in-game download |
| Storage | From 20:50 every run freed 5.7 GB left by the previous run's kept snapshot at its measured shortage |

Not measured on the phone: the completed-install output reuse and the staging retry shortcut below
(offline, ticket 18's measure runs had 0 failed attempts and 0 proofs, and the parity worker
recommends leaving the proof shortcut unwired).

### Completed-install output reuse (2026-11-12, pass 1, unverified)

| Boundary | Current source behavior |
|---|---|
| Work skipped | A fresh Translate Start may copy a matching completed result into a new owned build attempt, skipping pristine reconstruction and translation transforms. It still takes/audits a current full snapshot, rehashes retained output and original source/prime APKs, audits the actual current layer, and uses normal transaction/finalization checks. The copy records old input/result provenance rather than claiming new transforms. |
| Key | Exact provider/target/action/language/options, complete current producer/translation identity, actual expected normal/root APK, full expected live files and current delta/staged-hash/classification records. Original source provenance remains independently audited bytes; it is never replaced with a normalized APK identity. |
| Ineligible | Stopped, cancelled, unconfirmed, incomplete, invalidated or missing proof; changed inputs; Remove; Windows results with deletions that are already absent. Missing identity declines the shortcut. Unresolved mutations remain recovery work. |
| Cost and storage | Copying reserves actual result bytes plus normal restore/transaction space before allocation. Windows records validation/copy seconds, copied bytes and zero reconstruction/transform calls; Android records validation/copy milliseconds and the exact skipped operations. Copy publication is commit-last; an interrupted attempt cannot replace the prior proof. |
| Verification | Source and authored probes only. Actual-byte/count parity, interruptions, producer/options/game/metadata changes, Root zero installs, all three provider cycles and repeated total-time/storage controls remain open. Additional full hashes/snapshot/copies may cost more than they save; keep this shortcut only after measured safe benefit. Historical timings below do not measure it. |

### Staging retry measurement (2026-11-12, pass 1, unverified)

The in-place text loop drops one attributed table per failed `stage_unity_package` call and calls
it again; each call writes a package copy under `output/`. How much of a real run that costs was
never measured, so ticket 18 adds the measurement and a default-off shortcut, and claims nothing.

| Boundary | Current source behavior |
|---|---|
| Loop | `build_device_patch._stage_package` / `_retry_loop` hold the unchanged full → fit-only drop loop. `attribute_failure` returns the same hash `failing_asset` always did, plus its method (`slot-offset`, `traceback`, unmatched). Pass order, the extra-chunk exclusion, relocation, `text_skipped` and the summary are untouched. |
| Metrics | `build_patch(..., staging_metrics={})` fills per package the replacement-tree copies (files, bytes, seconds), every attempt (set size, seconds, outcome, error, attributed hash and method, output package files/bytes after it), relocation of the handed-on tables, and `totals`. Not in `device_patch_summary.json`; no shipped caller passes it. |
| Copy cost inside the runtime | Observed, not guessed: `tools/research/measure_staging_retries.py measure` wraps the real stager with an audit hook scoped to each call (`shutil.copyfile` calls/bytes, copytree/rmtree, writable opens, renames, removes) and the output copy's size afterwards. |
| Shortcut | `build_patch(..., retry_proofs=...)`, default None and passed by no shipped caller. A loop's key hashes the producer, package, loop/options, full index/shard SHA-256 and every starting replacement. A proof is used only after two identical baseline observations of the same key (`confirm_retry_proofs`); it pre-drops the recorded tables in the recorded order, so they still reach `relocate_text` or `text_skipped`. A missing table, an existing output copy (always the case after a failed full loop, so a fit-only proof is not used after that fallback) or any failure of the pre-routed attempt restores the full plan and the baseline loop. Unattributed failures and the full → fit-only fallback are never skipped. |
| Verification | Only `py_compile`, the staging-contract check and `git diff --check` ran. Synthetic fault cases (`measure_staging_retries.py faults`), real EN/ID measurements, proof confirmation and staged-hash/summary/delta parity with and without proofs are pass-2 gates. Keys re-read every package in full, so the shortcut may cost more than it saves; if the measured avoidable work is small, the verdict is no optimization and the metrics stay. |

### Windows signing reuse (2026-11-12, unverified)

Ticket 15 adds commit-last normal/access preparation receipts. Reopening can reuse
signed preparation after full source, output, manifest, signing and producer
verification. A pre-mutation restart copies only its explicitly retained compatible
generation into new owned files; incomplete outputs stay retained and unusable.
Missing complete producer evidence disables reuse while leaving fresh processing
and normal-APK safety recovery available.

The existing official conversion path already signs normal once; no duplicate-sign
saving is claimed for an ordinary fresh run. `check_windows_signing.py` now authors
generated-APK observations for signing calls/input bytes/elapsed time and separate
preparation elapsed time, covering official, signed, rename-refusal and retained
preparation paths. These probes have not run. Receipt publication/revalidation adds
full content reads; actual-APK repeated controls must show whether reuse saves time
before any performance claim or release decision. The Android measurements below
remain historical and do not measure this Windows change.

An Android patch run read the game layer about 13 times and the ~2 GB game APK about 19 times, most of
them back-to-back checks with nothing in between that could change the file. Five of those repeats are
gone, and the run no longer leaks the replaced game APKs the home app holds. On the Redmi Note 9 Pro a
rebuild from the delta takes 616–621 s instead of 906 s (−32%), peak free-space use drops by about
3.7 GiB, and the counts are unchanged (389 text tables, 398 applied textures, 1 skipped table). The
numbers and receipts are in `docs/lab-notebook.md`, 2026-10-18, "Android patch run: stage timings and
five fewer passes".

| what landed | where |
|---|---|
| each build input hashed once: `estimate_snapshot_build` reads the manifest, `build_scratch` no longer re-hashes what `build_snapshot` verified | Android bridge |
| pristine restore finds staged files from the verified manifest | `mobile_snapshot.package_files_at` |
| snapshot streamed from the pipe; no `snapshot.tar` on disk | `unpack_snapshot_stream` |
| access APK kept installed through the build, as on Windows | `PatchCoordinator` |
| `finishApply` reuses the originals verified before the apply; the access install reuses its own identity check | `PatchCoordinator` |
| replaced game APKs released after each game install and before each storage budget | `releaseReplacedGameApks` |

### Verification

| check | result |
|---|---|
| `build_snapshot` before and after, desktop, first install and rebuild from the Windows delta | equal staged SHA-256 for all 14 files, equal pristine report, counts, skip lists and summary |
| `tools/research/check_mobile_snapshot.py` | 8 tests pass: a streamed 2.95 GB layer equals file extraction; truncated, header-cut and oversized streams are refused |
| four phone runs (two baseline, two optimized) | 854.5 / 905.8 s before, 616.1 / 620.6 s after; device read-back passed on every run |
| patcher force-stopped 60 s into a build | recovery reinstalled the normal APK, the session became `CANCELLED`, `DEBUGGABLE` absent afterwards |
| one release-build run with the launcher fix | 603 s; free space 15.66 → 10.24 → 15.66 GiB, so no net loss |
| instrumentation probes | 17 of 18 pass |

Closed with three items owed. `CoordinatorSourceGuardProbeTest` fails, and `CoordinatorRecoveryProbeTest`,
`FullCoordinatorProbeTest` and `ApkPreparationProbeTest` were not run, because they need the 1.4.0.2
fixtures that neither the Xiaomi nor the PC still has. The launcher release is measured only with the
Pixel launcher (`com.google.android.apps.nexuslauncher`). The on-device `sha256sum` that
`validateLayer` runs over the layer was never measured.

### Journey

- **Where the time went.** The `DiagnosticTrace` logcat lines were split into stages per run. The
  snapshot and everything before the build took ~250 s, against a ~113–121 s internal build.
  Reading the code turned up ~32 full 2–3 GB passes per run.
- **Keeping the access APK through the build** was the riskiest change: the journal state
  `NORMAL_RESTORED_FOR_BUILD`, recovery and the process-death probes assumed the normal APK there. ADR 0001
  only forbids opening the game while access is installed. The kill-during-build check above covers it.
- **The launcher pin** was found during the runs. Two runs were refused for storage although each freed
  its temporary files. One `am force-stop` of the launcher freed 9.45 GiB.

## [S1] Problem

A patch run on the phone took about 15 minutes, of which the build was about two. The rest went to
installs and to hashing the same unchanged files again and again. Each game install also left the replaced
~2.4 GB APK held by the home app, so free space fell run after run until a storage check refused.

## [S2] Design

Keep exactly one trust check before each step that consumes a file, and drop the repeats that follow it
with nothing in between. The device's read-back of each written file and `verifyInstalled` after each
install stay. `rollback` keeps its own `verifyOriginals`. The snapshot's transport check becomes "the
in-transit hash and the per-file hashes agree", with the same fail-closed rules as `extract_snapshot`.
The access APK follows Windows and stays installed from the snapshot through the apply. The game is not
opened in that window (ADR 0001).

## [S3] Out of Scope

- Removing any trust check before a consuming step, the device read-back, or `verifyInstalled`.
- The Windows patcher: its build is 40–50 s and its same-version pull 17–23 s, with no large lead left.
- The staging pipeline itself, already measured and optimized on 2026-10-17.

### Android complete-build reuse boundary (2026-11-12, pass 1)

The bridge can inspect a committed owned result and return its unchanged summary, output paths and
receipt without calling the stage builder. It rehashes the exact artifact set and validates the
current snapshot, full engine producer, normal APK and kept delta first. Summary-only output,
missing restored files/delta, extras and tampering refuse reuse. Producer identity unavailable means
ordinary fresh processing with no reusable receipt. No snapshot stream, codec or package fragment
is reused. Ticket 10 must wire dispatch to these explicit APIs; ticket 16 owns installed-receipt
skips, and ticket 17 owns classification reuse. No new speed measurement or behavior/parity result
is claimed; authored synthetic probes and external matching EN/ID controls remain pass-2 gates.

### Android exact-write subset and recovery proof (2026-11-12, Pass 1; unverified)

| Boundary | Current source behavior |
|---|---|
| Identical file | Independently audit the complete current layer against the verified snapshot, then compare every staged file's actual SHA-256 and length. Only changed staged files enter the write loop. |
| Full result | Identical skips and restored files stay in the full applied manifest, staged hashes, receipt and pristine delta. An all-identical run still clears/audits Watchdog, audits the normal APK and finalizes the delta. |
| Recovery hashing | An opaque descriptor belongs to one transaction and verification generation. Recovery passes it directly into rollback; standalone rollback hashes originals independently. Snapshot attribute changes, a new verification and consumption invalidate the descriptor. Every actual write still hashes its retained source. |
| Recovery mutation | Whole live-state audit precedes rollback. Each actual target is audited again under the same provider lock as its rename/deletion; unexpected bytes pause. Unchanged original package files are audit-only. |
| Metrics | `resource-metrics.json.file_io` records original/planned/written/skipped files and bytes plus original hash passes. Written counts acknowledge replies; a lost reply remains an uncertain outcome, not a measured successful write. `recovery_original_hash_passes` records the latest recovery invocation. |

Private transaction, Remove, recovery, policy parser/large-manifest and full-coordinator probes are authored; none ran. Historical timings above do not measure this change. Output/summary/delta parity, interruption behavior, device transport/ownership and comparative timings remain Pass-2 gates.
