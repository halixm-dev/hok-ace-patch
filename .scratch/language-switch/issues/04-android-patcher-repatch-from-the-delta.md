# 04: Android patcher repatches from the pristine delta

**What to build:** the same as 03 for the Android patcher, through the engine it ships (`android_bridge`), with no Kotlin reimplementation of the delta.

- After `GameFileTransaction.finishApply`: `make` the delta from the session's build input against `out/`, written atomically to `filesDir/pristine/delta.bin` (outside `sessions/`, so `releaseSession` never reclaims it); keep the staged hashes of every install.
- Before the build: `rebuild` into a separate build-input copy of only the files the delta names (~0.9 GB), the rest read from `snapshot/`. `snapshot/` keeps the phone's actual bytes, so rollback is unchanged.
- `build_storage.estimate` reserves the build-input copy; `requireSpace` checks it before the copy.
- The same pristine signals and refusals as 03, raised before the access APK is installed. The Language card's "Switching languages? Clear the game's data…" text (and its `UiText` Indonesian) changes when a delta applies.
- Engine manifest: Gradle stages `tools/pristine_delta.py`.

**Blocked by:** 02

**Status:** ready-for-agent

- [x] Delta kept after `finishApply`; staged-hash record kept
- [x] Build-input copy, budgeted; rollback still writes `snapshot/`
- [x] Refusals before the apply's access APK; Language card text in both UI languages
- [x] `:app:assembleDebug :app:assembleDebugAndroidTest` pass; `PristineDeltaProbeTest` covers rebuild and refusal (passes on a phone, 1 test in 3.0 s)

## Notes

Update `docs/features/android-shizuku-patcher.md` in the same change.

## Comments

2026-10-17, implemented: `android_bridge` (`estimate_snapshot_build`/`build_snapshot` take the kept
folder; `keep_delta`), `build_storage.estimate(pristine_copy_bytes=)`, `PristineDelta.kt`,
`PatchCoordinator` (`promoteSessionDelta`), the Language card. Details in
[android-shizuku-patcher](../../../docs/features/android-shizuku-patcher.md), "Repatch from the pristine
delta". Refusals come from `build_snapshot`, after the snapshot's normal APK is back and before the
apply's access APK, so no game file is written. The session delta is promoted once the run is
`COMPLETE` (also at the next run's start, for a run recovery completed). `PristineDeltaProbeTest` is
passes on the Xiaomi M2007J3SG (Android 12), 1 test in 3.0 s.
