---
feature: update-stuck-redownload
status: built, device-tested (one-run plan 2026-10-23; reviewed and automatic Re-download on a phone 2026-11-13)
updated: 2026-11-13
branch: master
---

# Re-download damaged files after a stuck update

## Report

### Phone cycles on old data (2026-11-13, Wireless debugging, `f15a72e`)

Pristine 1.8.0.1 plus release 1.8.1.2 in English, then the in-game update to 1.10.1.2, which left
`BrokenList` holding 68 assets in packages 1 and 10. Details and raw evidence paths are in the
[lab notebook](../lab-notebook.md)'s 2026-11-13 entries.

| Case | Verdict |
|---|---|
| Release 1.8.1.2 alone | Refused `UPDATE_STUCK` 1, 10; its Re-download deleted 1, 10 and 21, then every re-patch failed with `15_0.db: slot 0x1dd2c4 (key DD242E3E) not in the B-tree`. The field bug, reproduced |
| Planner on build 21f51bb2 | Found package 15, then crashed on `packages/builtin/Globalindex` (`invalid literal for int() ... 'builtin'`). Fixed by `77461c4` (release 1.10.1.3, merged as `8582585`) |
| Reviewed Re-download, run `c26b206d` | Approved on the card; deleted package 15's three files; after *Downloads finished*, complete 398/318, 1 table and 0 textures skipped. **Pass** |
| Automatic Re-download, run `99584a53` (app `38c31162`) | One plan for 1, 10, 15 and 21 (12 files, 499,515,540 B) deleted with no review; approval source `automatic`; the only taps were Start, Open game and *Downloads finished*; complete 398/318/1/0. **Pass** |

Still not phone-tested: the loop-guard fallback (a package still damaged after its own download goes
back to the review card) and an interrupted automatic deletion (`CoordinatorRecoveryProbeTest`'s cases
were fixture-skipped on the phone). The affected Redmi itself was not available. No coverage count
moved.

### Automatic Re-download, once per package per run (2026-11-13, phone-checked once)

By the user's decision of 2026-11-13, a Start or automatic run no longer stops on **Review Re-download**.
When its build refuses over damaged packages (stuck update, mixed packages, or an unreachable texture
slot such as `15_0.db: slot ... not in the B-tree`), the coordinator measures and pins the exact plan as
before, approves it itself (the run record keeps the approval with `source: "automatic"`) and goes on
in the same run, on the snapshot and access it already verified, to the existing deletion: the progress
line reads "Damaged game files found; deleting them so the game downloads them again", the files are
deleted under their intents, the normal APK is restored and verified, and the card asks the player to
open the game, let it download and tap **Downloads finished**. That tap stays: it is a readiness answer,
not consent. The translation then continues.

Nothing else about the deletion changed: the plan stays bound to the snapshot, delta, records, engine,
APKs and exact file hashes; a plan that no longer holds is measured again and the new plan is approved
again before anything is deleted; an interrupted deletion rolls back and resumes without a dialog.

Loop guard (`RunStore.automaticRedownloadAllowed`): automatic approval applies only to a package the run
has not deleted yet (`redownloaded_packages` in the run record) and while the deletion budget is unspent.
A package still damaged after its own download, or a deletion interrupted twice, waits for the player's
review on the existing card, which then says the game already downloaded these files again.

Checked offline first: JVM unit tests (`AutomaticRedownloadTest`), debug and instrumentation builds, and
`check_ui_strings.py`. Then one phone cycle passed: run `99584a53` (above). The loop guard and an
interrupted automatic deletion remain without a phone run.

### Unreachable texture slots (2026-11-12, offline checked)

The Android checkpoint build now also offers the existing scoped Re-download approval when a staged
shard raises `qts_relocate.UnreachableSlot`. This is the recovery log's `15_0.db: slot ... not in the
B-tree` failure, which previously escaped as a generic RuntimeError and never reached the planner.
The exception retains the shard path, key and offset; no log message is parsed into deletion scope.
The refused package must have the same shard in the verified source snapshot, and the error must come
from this attempt's staged copy. A prime-only package absent from the snapshot is not eligible.

`package-refused.json` in the parent session binds the one package to the verified snapshot files,
resolved snapshot path, engine bytes and kept delta/records. It survives resetting an incomplete build.
The planner ignores it when those inputs differ or the record is malformed, and merges a valid package
with any independently stuck or mixed packages. Detection and planning change no live game files.
The existing plan digest, separate approval, live-layer validation, rollback, normal APK restoration
and download wait remain the deletion path. It does not automatically delete package `15`, clear all
game data, or treat a raw exported log as recovery authorization.

This is a recovery fallback, not a diagnosis of the older patcher or Tencent's update. The affected
Redmi's bytes were unavailable; a tiny synthetic shard reproduces the exact relocation exception through
the real checkpoint/error/planner path. The test and measurements are in the lab notebook's
2026-11-12 recovery-log follow-up. The existing healthy real texture replay still passes. No affected
phone or end-to-end download cycle has been tested for this fallback.

### Check mixed packages and texture slots before one review (2026-11-12, offline checked)

A mixed refusal used to stop before graphics staging, so the planner could miss a broken texture
package until a second download cycle. `_plan_redownload` now collects stuck/mixed packages and then
checks remaining snapshot packages with `qts_relocate.unreachable_slots` before returning the plan.
The targets are both catalogs' graphics, measured aliases and repo atlas labels. Each selected slot
is compared with its own shard's current B-tree, using the corrected live slot map and reading only
tree metadata. It collects every detected package instead of stopping at the first missing slot.

Already selected packages are skipped. If a suspect package has delta entries, the planner rebuilds
or asset-restores it in a disposable private copy and checks again: a problem that restore fixes does
not add a deletion. Copies are removed on success or failure. An unreadable tree or failed inspection
aborts planning instead of silently presenting a partly checked deletion list. This adds no deletion
consent, changes no source snapshot or live package, and keeps the existing bound plan/deletion guards.

The mixed-plus-B-tree regression failed before this change (package 15 absent from review) and passes
afterward. The offline suite also checks multiple broken packages, live slots, exact delta restoration,
skipping already selected packages and refusing partial inspection. A healthy captured layer's 290
packages (402 texture targets across both catalogs) gives no false deletion candidates in 14.99 s.
The affected Redmi is still unavailable. This checks current texture-slot reachability; it does not
predict an unrelated error introduced later in staging or a later game update.

### Scoped Re-download approval (ticket 12, 2026-11-12; live cycle pending)

Start never authorizes deleting damaged packages. When the build refuses over a stuck or mixed package, the
saved action measures an exact plan, pins it, rolls back, restores the normal APK and waits for the user
(*Waiting for you*). The screen shows the plan's files, packages, size and consequences; **Delete and
re-download** approves that plan's digest only. The approved deletion runs inside the same saved action,
then the action waits for the game's download and continues the translation after the user confirms it,
with the build checking readiness again.

The review is inline on the main card. **Delete and re-download** starts that scoped deletion directly,
without a second confirmation. After restoration finishes, the card offers **Open game** and
**Downloads finished**. Open the game, finish downloading to the login screen, close it, return and tap
**Downloads finished** to continue directly. Returning alone never confirms completion. A tap keeps
the displayed run id and plan digest; a newer plan cannot silently replace the reviewed scope.

Verification: 21 focused JVM tests pass. An isolated API-36 emulator preview passes 26 UI/private-store
tests, including all 38 home-state captures in English and Indonesian at font scale 1.0, direct button
routing, and exact-plan approval/rejection. The four new recovery screenshots were visually inspected.
This checks presentation and synthetic metadata, not live game deletion or download on the Redmi.


When an in-game update stops on the files a translation changed, the Android patcher now says so and
offers **Re-download damaged files** instead of "clear the game's data". It deletes every file of each
translated package the game's broken list names, clears `Watchdog`, and restores the normal APK. The
game then downloads those packages whole and finishes its update, and the next Start patches as usual.

The same offer now replaces "clear the game's data" when an update finished but rewrote a translated
package around the translation (`UPDATE_MIXED`): the pristine delta cannot rebuild such a package, and
deleting it lets the game download it whole. Seen on the user's phone at 16:30 on 2026-10-22: packages
`10`, `15`, `19`, `20` and `21` kept 2, 302, 22, 1 and 1 translated assets after the r815437 update.
Since [asset restore](asset-restore.md), a mixed package whose carried-over assets the patcher can write
back is restored instead, and only the rest are refused and re-downloaded (`10` and `21` in that case).

The recipe was measured by hand on the user's phone (lab notebook, 2026-10-22, "An update stuck on
translated files, and Re-download"), and the patcher's own runs passed on a phone on 2026-10-23 (lab
notebook, "An update over a patched layer, captured end to end"): a stuck update on package `1`, then a
Start refusing `10` and `21` as mixed, each re-downloaded, and Start then patched without a clear. Since
then one Re-download takes both: the stuck packages and the mixed ones asset restore cannot take, which
passed on a phone the same day (lab notebook, "One Re-download takes a stuck package and the mixed ones
together"). The Windows patcher does not detect a stuck update.

| what landed | where |
|---|---|
| the broken-list reader | `tools/broken_list.py` |
| the refusal on a stuck update, before any write, on Start and on Remove | `android_bridge._refuse_stuck_update` |
| the refusal on a mixed package, and its plan | `android_bridge._restore_pristine` (`UPDATE_MIXED`), `_mixed_packages` |
| the deletion plan and the wait record | `android_bridge.redownload_plan` (into `redownload-plans/<id>/`), `redownload_evidence`, `keep_redownload` (`redownload.json` beside the delta); `plan_redownload` stays for the research checks |
| the device cycle tooling and its check | `tools/research/update_cycle.py`, `watchdog_history.py`, `check_update_redownload.py` |
| the plan, its approval and the run | `PatchCoordinator.planRedownload`, `awaitUser` (`RedownloadApproved`), `waitingStep`, `redownloadStage`; `RunStore.Redownload` (`proposeRedownload(automatic = true)`, `automaticRedownloadAllowed`, `approveRedownload`, `declineRedownload`, `confirmRedownloadDownloads`) |
| the device step | `IPrivilegedDeviceService.deleteGameFile` (protocol 12) |
| the screen | `MainActivity`: Let the game download the files → Open game (`openDownloadGame`) → Downloads finished (`confirmDownloads`); only for a plan the loop guard holds back, Review Re-download with measured scope → Delete and re-download (`reviewRedownload`). Both taps act directly, without dialogs |

From 2026-11-06 to 2026-11-12 Start deleted those packages without a second approval. Ticket 12 replaced that
with the scoped approval, for Start and Remove alike; the separate `redownload` action and its checkbox are
gone. On 2026-11-13 the user chose automatic deletion again, now bound to the measured plan and limited to
once per package per run. Asset restore stays automatic.

## [S1] Problem

Tencent's updater checks each asset against the check values its package stores. A translated asset
fails the check, the updater records it in `Watchdog/BrokenList.db` and refuses the whole update; the
game shows "资源修复失败，请清理资源后重新下载资源" on every launch. The failed update and repair leave the
translated files changed, so the pristine delta can no longer rebuild them, and Remove translation
refuses. Until now the only way out was clearing the game's data, about 2.8 GB to download again.

## [S2] Design

| Area | Behavior |
|---|---|
| Detection | `build_snapshot` and `build_removal` read the snapshot's `Watchdog/BrokenList.db`. A package it names counts when this patcher translated it: the kept delta names one of its files, or one of its files is at a staged hash. Any such package refuses the run with `UPDATE_STUCK`, before the pristine rebuild |
| Mixed package | With no stuck package, `_restore_pristine` refuses each package `pristine_delta.accept_replaced` refuses (this patcher's bytes or translated assets left in an updated package), and each restorable one [asset restore](asset-restore.md) cannot take, with `UPDATE_MIXED`, naming them. `plan_redownload` names the same packages through `_mixed_packages`, which tries the restore on a copy it then discards |
| Not ours | Broken assets only in packages this patcher never touched do not refuse; the game repairs those itself |
| Plan | On a damaged-file refusal, `redownload_plan` stages every file of each stuck package, and of each package `_mixed_packages` refuses (`.db` and `.info`), into a fresh `redownload-plans/<id>/` with its snapshot SHA-256 in `staged-hashes.json`. Kotlin binds `plan.json`: run, session, authorization, action, target and provider, the snapshot manifest's SHA-256, engine and producer, the run's APKs, the kept delta and its `redownload.json` / `restore-refused.json` records, every file with hash and size, the Watchdog files cleared, and the consequence codes (`PatchCoordinator.REDOWNLOAD_CONSEQUENCES`). It is written atomically and read back; its digest is `ArtifactReceipts.identityKey(plan)`. The journal pins it (`redownload_plan`, `redownload_plan_sha256`) before the run record offers it (`RunStore.proposeRedownload`) |
| Automatic approval | User decision 2026-11-13. The journal pins the plan with `waiting_reason: redownload_consent_required`, and `proposeRedownload(automatic = true)` approves it in the same run-record write (approval `source: "automatic"`) when `RunStore.automaticRedownloadAllowed` holds. `awaitUser` then throws `RedownloadApproved`, and `continueLocked` runs `redownloadStage` in the same run, on the snapshot and access it already verified. The approval resets the attempt budgets (`redownload_delete` too) as a new destructive scope, as the user's did |
| Loop guard | `automaticRedownloadAllowed`: only an unanswered plan, with fewer than two `redownload_delete` attempts, and none of whose packages is in the run record's `redownloaded_packages` (every package `redownloadProgress(..., deleted)` recorded in this run, whoever approved it). Otherwise the refusal becomes `WaitingForUser`: the run rolls back, restores the normal APK, closes the session `CANCELLED` and returns `status: waiting` with `reason: redownload_consent_required`. A plan that cannot be measured leaves the ordinary refusal: nothing unbound is deleted |
| Review (loop guard only) | The card's Delete and re-download tap calls `RunStore.approveRedownload(run, digest)` for the displayed digest only (approval `source: "user"`); it never clears Stop. Leaving the card grants nothing; Stop safely ends the action. Older saved `declined` plans remain reviewable and are never approved automatically. The same digest offered again keeps its answer; any other digest replaces it, approved automatically only if the loop guard allows |
| Re-download | Only from an approved digest, after the snapshot is revalidated against the live layer. The pinned plan must still hold (`pinnedPlanHolds`: same run, manifest, engine, producer, APKs, delta, records and file hashes); otherwise the plan is measured again, pinned and approved again automatically (subject to the loop guard), and only that exact digest proceeds. `deleting` and the `redownload_delete` attempt are saved, `keep_redownload` writes its record (its identity kept as `redownload_kept`), and each deletion is journaled (`delete_file`, packages dirty) and checks the file still holds its hash. Then `Watchdog` is cleared, `redownloaded` and the `redownload_download_required` wait are saved, the approval is consumed (`deleted`) and the normal APK restored (Root: verified unchanged) |
| Interrupted deletion | Rollback, as for a patch: every staged file and `Watchdog` back from the snapshot. The plan stays pinned and approved, so the next dispatch resumes it without a dialog; its own `redownload.json` is the one record change allowed. After two `redownload_delete` attempts the approval returns to `awaiting_consent` |
| Parent action | The translation (or removal) is the saved action throughout. After the deletion it waits for the game's download; **Downloads finished** (`confirmRedownloadDownloads`) dispatches it at once (no second tap on Continue saved work; still refused while a worker runs), and the build's own readiness check (`UPDATE_WAITING`, `DOWNLOAD_UNFINISHED`) sends it back to the download wait, never to deletion |
| Source downloads after a Re-download | The deletion makes the saved snapshot stale on purpose. Leaving the download wait, `waitingStep` takes the confirmed answer as the source-download answer too (`RunStore.confirmSourceDownloadsAfterRedownload`), bound to that one snapshot's manifest digest and only for the plan the journal last recorded as deleted (`redownloadAnswersSourceDownloads`). So `snapshotStage` does not open access only to wait for **Downloads finished** a second time (device cycle 2026-11-12). It still retires and retakes the snapshot from the live layer, spends the answer once (`consumeSourceDownloads`), and drops an answer the layer no longer needs, so it never covers a later, unrelated change |
| Stop | Stop works in every state: a waiting action resolves consistent; a Stop mid-deletion rolls the files back |
| Rollback | As for a patch: an interrupted run writes every staged file back from the snapshot, then restores `Watchdog` |
| Waiting for the download | `keep_redownload` writes `redownload.json` before the first deletion. While a package it names has no `.db` in the snapshot, Start and Remove refuse with `UPDATE_WAITING` ("Finish the game update"). Once the files are back, the build only reads the record: it reports it as `redownload_done` (the record's identity) in its summary and never writes the kept folder, which `build_checkpoint` binds for the whole build. Finalization (`finalization_plan` → `PristineDelta.finalize`, after the delta is promoted; `keep_delta` for a legacy session) drops the record only while it still holds exactly those bytes. A copied completed output never drops one. Until then a published build stays reusable; once dropped, the next build binds the new kept identity (phone f15a72e, 2026-11-12, run 248572aa: the build used to drop it mid-build, and every first build after a Re-download refused with "kept delta changed during build") |
| After the download | The delta's files in a re-downloaded package no longer match; `pristine_delta.accept_replaced` takes them as the new pristine when none of the translation is left, as after any update |
| Clear data | Every other refusal that ends in `CLEAR_DATA` gets its own home message; it no longer reads as a lack of space (its "Storage" made `friendlyFailure` show the free-space notice) |
| A blocked install during the refusal | The normal restore after a refusal can fail on the phone's installer (`INSTALL_FAILED_USER_RESTRICTED`). Once the emergency restore verifies the normal APK and no game file is mid-change or written, `PatchCoordinator.closeIfNothingToRecover` closes the run, so its status stays `error` with the refusal's own text and the screen offers Re-download. A run the emergency restore could not finish stays `recovery_required` |

## [S3] Out of Scope

The Windows patcher (no Re-download there); one wording for the approval across both patchers (ticket 13);
reusing a mixed-package decision across worker processes (within one worker, see
[asset-restore](asset-restore.md) "Mixed-package decision reuse"); detecting a stuck update before the user runs the patcher (the broken list is
readable only under the access APK); a stuck texture package, which follows the same path but is
unmeasured; writing the pristine bytes back before an update so it never sticks ([language-switch](language-switch.md)
withdrew it: nothing on the phone precedes an update).

## Verification

- Ticket 12 (2026-11-12): `compileDebugKotlin`, `compileDebugUnitTestKotlin`, `compileDebugAndroidTestJavaWithJavac`,
  `py_compile` and `check_ui_strings.py` (no new findings) only. The probes in `RunStoreProbeTest`,
  `SessionPublicationProbeTest` and `CoordinatorRecoveryProbeTest` are authored, not run.
- `tools/research/check_ui_strings.py`: OK, 255 strings.
- `:app:testDebugUnitTest` (including `ProgressStepTest` re-download steps and `ResultStateTest`'s result) and
  `:app:assembleDebug` pass. `:app:assembleDebugAndroidTest` fails to compile in `DiagnosticLogExportProbeTest`,
  which predates this change (`DiagnosticLogExport` now takes the device service).
- Offline bridge check on the phone's real files (stuck package `1` and its broken list; the re-downloaded
  package and the empty list): Start and Remove refuse with `UPDATE_STUCK`; a broken list in an untranslated
  package does not refuse; the plan names `1/1.db`, `1/1.info`, `1/1_0.db` with their snapshot hashes; a run
  with package `1` absent waits; with it back, the record is dropped and the run goes on; a healthy phone's
  Re-download refuses.
- Offline mixed-package check (pristine r815437 package `1` against the phone's translated one, both
  package files then changed): Remove refuses with `UPDATE_MIXED` ("332 of the assets this patcher changed
  are still translated"); the plan names `1/1.db`, `1/1.info`, `1/1_0.db`; with the re-downloaded package the
  plan refuses as there is nothing to re-download.
- Device runs (2026-10-23, Xiaomi M2007J3SG, patcher 1.7.1.3): Re-download of a stuck package `1`, the game
  downloaded it and finished; Re-download of mixed `10` and `21` after the update had finished, the game
  downloaded them too; Start then patched. That build planned the two runs apart.
- `tools/research/check_update_redownload.py` on that phone's captured layers: over the stuck layer the plan
  names `1`, `10`, `21` in one run; over the finished layer, `10`, `21`, as the phone did.
- Blocked install during the refusal, and the deletion inside a patch run: compiled and unit-tested, and an
  offline run over the phone's stuck 1.9.1.3 layer refused, cleared and planned package `1`'s 3 files (lab notebook,
  2026-11-06). Not yet exercised on a phone. `check_update_redownload.py` could not run: its 2026-10-23 captures are
  no longer on this PC.
- Device run of the one-run plan (2026-10-23, same phone, debug build of `48f10fa`, update 1.6.0.1 → 1.7.0.2
  over an English install): Start refused the stuck package `1` (50 assets); one Re-download deleted `1`, `10`
  and `21` (9 files); the game downloaded them and reached the login screen; Start patched English with asset
  restore for `15`, `19`, `20`, no refusal and no clear; the game reads English and the login survived.
