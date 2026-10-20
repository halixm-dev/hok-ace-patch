# 11: Android progress reports its step

**What to build:** While work runs, ② shows a determinate bar and "Step N of M · <step>" in the player's language. See the [spec](../spec.md), "Progress".

Today ② shows a spinner and the worker's free-text line. `UiText` translates only the lines in its table; any other line becomes one generic Indonesian sentence.

- The Android step list is six steps, not the Windows seven (confirmed 2026-10-19). Verification is not a step of its own: each install already checks the installed app. Each step starts at the first of the worker's progress lines below (traced from source, patcher 1.6.1.10):

  | # | Step | Worker action | Starts at |
  |---|---|---|---|
  | 1 | Check game | `prepare` | "Checking other Android profiles for the game", "Checking saved normal and access APKs" |
  | 2 | Prepare files | `prepare` | "Copying and verifying the installed source APK", "Preparing normal and access APKs…", or "Reusing verified saved APKs…" |
  | 3 | Unlock access | `patch` / `remove` | "Opening game data access" (access APK install), then "Measuring downloaded game data…" and "Saving complete game data and Watchdog snapshot" |
  | 4 | Build translation | `patch` / `remove` | "Building text and graphics from the verified private snapshot"; on removal, "Rebuilding the original game files from the pristine delta" |
  | 5 | Write translation | `patch` / `remove` | "Applying package file <name>" |
  | 6 | Restore game app | `patch` / `remove` | "Restoring normal game APK", through its install check |

- Steps 1 and 2 run in the `prepare` action, before the confirmation dialog. Steps 3 to 6 run after it, so the count carries across the dialog. When preparation is skipped because saved APKs are reused, the run still reports steps 1 and 2.
- The snapshot belongs to step 3: it runs under the access APK and is part of opening the data. Watch its share of the run on the phone; if it dominates, propose splitting out a "Read game data" step.
- Remove translation uses the same six steps. Steps 4 and 5 read *Rebuild original files* and *Write original files* there.
- The worker state gains a stable step key and a total beside its free-text line. The free-text line moves to the log.
- Step names go in the shared strings file.
- Recovery, first setup and Free up space keep their own wording and show no count. Older states without a step still show their line.

Supersedes ticket 07.

**Blocked by:** 10

**Status:** ready-for-human (one Indonesian patch on a phone)

- [x] Step list confirmed (six steps)
- [x] Worker reports the step key and total
- [x] Bar and step line in ② (probe, with a saved state that carries a step)
- [ ] One Indonesian patch on a phone, with each step's screenshot looked at

## Comments

2026-10-20: `WorkerStep` holds the six step keys (`check_game`, `prepare_files`, `unlock_access`, `build`, `write`, `restore_game_app`) and the progress lines that start each. `PatchWorkerService.show` puts `step` and `steps` (6) beside `progress` in every running record of `prepare`, `patch` and `remove`; other actions carry no step. `prepare` starts at 1 and stops at 2, `patch` and `remove` start at 3. A step never goes back and never skips one, so a run that fails at step 3 or 4 and restores the game app while recovering stays at its step instead of jumping to 6. `UiText.step` turns a running record into "Step N of M · <step>" from the shared strings: `progress_step`, `step_translate` (now shared with Windows) and seven new `android_step_*` keys, Indonesian marked `draft`. Removal reads *Rebuild original files* and *Write original files* for 4 and 5. While work runs ② shows a bar (track `disabled-fill`, fill `ink`) in place of the button, for every running state; it is determinate with a step, and the step line replaces the free-text line, which stays in the log. A record without a step keeps its translated line and an indeterminate bar.

Tests: `ProgressStepTest` (JVM) checks the real message sequences of prepare (with reuse), patch, a failed removal and recovery, and the line in both languages. `InterfaceProbeTest.progressShowsTheStepFromTheSavedState` checks the line, the bar and the button's place by driving `GuidedHome` with a saved-state record; `MainActivity.refreshHome`'s wiring is not probed, since a live run needs the worker. `CacheReuseProbeTest` checks the prepare worker records only steps 1 and 2 of 6. `testDebugUnitTest`, `assembleDebug`, `assembleDebugAndroidTest` and `check_ui_strings.py` pass. The probes were not run: the attached phone holds the release patcher. Between `prepare` and `patch` the record carries no step, so ② shows an indeterminate bar for that moment. The notification still shows the free-text line.

2026-10-20: The probes now pass on a phone (ticket 13). The Indonesian patch is still owed.
