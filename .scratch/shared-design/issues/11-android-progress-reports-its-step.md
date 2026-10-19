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

**Status:** ready-for-agent

- [x] Step list confirmed (six steps)
- [ ] Worker reports the step key and total
- [ ] Bar and step line in ② (probe, with a saved state that carries a step)
- [ ] One Indonesian patch on a phone, with each step's screenshot looked at
