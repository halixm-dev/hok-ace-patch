---
feature: update-stuck-redownload
status: built, not device-tested
updated: 2026-10-22
branch: master
---

# Re-download damaged files after a stuck update

## Report

When an in-game update stops on the files a translation changed, the Android patcher now says so and
offers **Re-download damaged files** instead of "clear the game's data". It deletes every file of each
translated package the game's broken list names, clears `Watchdog`, and restores the normal APK. The
game then downloads those packages whole and finishes its update, and the next Start patches as usual.

The recipe was measured by hand on the user's phone (lab notebook, 2026-10-22, "An update stuck on
translated files, and Re-download"). The patcher's own run of it has passed offline checks and unit tests
only; no phone has run it yet. The Windows patcher does not detect a stuck update.

| what landed | where |
|---|---|
| the broken-list reader | `tools/broken_list.py` |
| the refusal on a stuck update, before any write, on Start and on Remove | `android_bridge._refuse_stuck_update` |
| the deletion plan and the wait record | `android_bridge.plan_redownload`, `keep_redownload` (`redownload.json` beside the delta) |
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
| Not ours | Broken assets only in packages this patcher never touched do not refuse; the game repairs those itself |
| Re-download | A patch run up to the snapshot, then `plan_redownload` stages every file of each stuck package (`.db` and `.info`) for deletion, with its snapshot SHA-256 in `staged-hashes.json`. Each deletion is journaled (`delete_file`, packages dirty) and checks the file still holds that hash. Then `Watchdog` is cleared and the normal APK restored |
| Rollback | As for a patch: an interrupted run writes every staged file back from the snapshot, then restores `Watchdog` |
| Waiting for the download | `keep_redownload` writes `redownload.json` before the first deletion. While a package it names has no `.db` in the snapshot, Start and Remove refuse with `UPDATE_WAITING` ("Finish the game update"); once the files are back the record is dropped |
| After the download | The delta's files in a re-downloaded package no longer match; `pristine_delta.accept_replaced` takes them as the new pristine when none of the translation is left, as after any update |
| Consent | The confirmation asks only that the game is closed: the update has not finished. It reuses the patch request store's consent field |

## [S3] Out of Scope

The Windows patcher; detecting a stuck update before the user runs the patcher (the broken list is
readable only under the access APK); a stuck texture package, which follows the same path but is
unmeasured; writing the pristine bytes back before an update so it never sticks (`.scratch/language-switch`
ticket 07).

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
- Not done: a device run of the patcher's Re-download. It needs a stuck update, which only a real game
  update makes.
