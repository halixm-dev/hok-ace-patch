---
feature: patch-speed
status: built; phone-checked on the Redmi Note 9 Pro
updated: 2026-10-23
branch: master
---

# Android patch run speed

## Report

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
