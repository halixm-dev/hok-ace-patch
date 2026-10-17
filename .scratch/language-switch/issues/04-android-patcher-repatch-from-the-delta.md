# 04: Android patcher repatches from the pristine delta

**What to build:** the same as 03 for the Android patcher, through the engine it ships (`android_bridge`), with no Kotlin reimplementation of the delta.

- After `GameFileTransaction.finishApply`: `make` the delta from the session's build input against `out/`, written atomically to `filesDir/pristine/delta.bin` (outside `sessions/`, so `releaseSession` never reclaims it); keep the staged hashes of every install.
- Before the build: `rebuild` into a separate build-input copy of only the files the delta names (~0.9 GB), the rest read from `snapshot/`. `snapshot/` keeps the phone's actual bytes, so rollback is unchanged.
- `build_storage.estimate` reserves the build-input copy; `requireSpace` checks it before the copy.
- The same pristine signals and refusals as 03, raised before the access APK is installed. The Language card's "Switching languages? Clear the game's data…" text (and its `UiText` Indonesian) changes when a delta applies.
- Engine manifest: Gradle stages `tools/pristine_delta.py`.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] Delta kept after `finishApply`; staged-hash record kept
- [ ] Build-input copy, budgeted; rollback still writes `snapshot/`
- [ ] Refusals before the access APK; Language card text in both UI languages
- [ ] `:app:assembleDebug :app:assembleDebugAndroidTest` pass; an instrumentation probe covers rebuild and refusal

## Notes

Update `docs/features/android-shizuku-patcher.md` in the same change.
