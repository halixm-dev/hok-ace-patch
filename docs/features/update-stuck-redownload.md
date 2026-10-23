---
feature: update-stuck-redownload
status: built, device-tested (one-run plan on a phone 2026-10-23)
updated: 2026-10-23
branch: master
---

# Re-download damaged files after a stuck update

## Report

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
| the deletion plan and the wait record | `android_bridge.plan_redownload`, `keep_redownload` (`redownload.json` beside the delta) |
| the device cycle tooling and its check | `tools/research/update_cycle.py`, `watchdog_history.py`, `check_update_redownload.py` |
| the run | `PatchCoordinator.redownloadLocked`, worker action `redownload` |
| the device step | `IPrivilegedDeviceService.deleteGameFile` (protocol 12) |
| the screen | `MainActivity`: "The game update is stuck" → Re-download damaged files; "Finish the game update" |

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
| Re-download | A patch run up to the snapshot, then `plan_redownload` stages every file of each stuck package, and of each package `_mixed_packages` refuses, in one run (`.db` and `.info`) for deletion, with its snapshot SHA-256 in `staged-hashes.json`. Each deletion is journaled (`delete_file`, packages dirty) and checks the file still holds that hash. Then `Watchdog` is cleared and the normal APK restored |
| Rollback | As for a patch: an interrupted run writes every staged file back from the snapshot, then restores `Watchdog` |
| Waiting for the download | `keep_redownload` writes `redownload.json` before the first deletion. While a package it names has no `.db` in the snapshot, Start and Remove refuse with `UPDATE_WAITING` ("Finish the game update"); once the files are back the record is dropped |
| After the download | The delta's files in a re-downloaded package no longer match; `pristine_delta.accept_replaced` takes them as the new pristine when none of the translation is left, as after any update |
| Clear data | Every other refusal that ends in `CLEAR_DATA` gets its own home message; it no longer reads as a lack of space (its "Storage" made `friendlyFailure` show the free-space notice) |
| Consent | The confirmation asks only that the game is closed: the update has not finished. It reuses the patch request store's consent field |

## [S3] Out of Scope

The Windows patcher; detecting a stuck update before the user runs the patcher (the broken list is
readable only under the access APK); a stuck texture package, which follows the same path but is
unmeasured; writing the pristine bytes back before an update so it never sticks (`.scratch/language-switch`
ticket 07 dropped it: nothing on the phone precedes an update).

## Verification

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
- Device run of the one-run plan (2026-10-23, same phone, debug build of `48f10fa`, update 1.6.0.1 → 1.7.0.2
  over an English install): Start refused the stuck package `1` (50 assets); one Re-download deleted `1`, `10`
  and `21` (9 files); the game downloaded them and reached the login screen; Start patched English with asset
  restore for `15`, `19`, `20`, no refusal and no clear; the game reads English and the login survived.
