# Evidence used for this plan

Source read on 2026-11-11. Lines are navigation hints; locate the named method before editing. No tests, benchmarks or phone operations were run during planning.

## Windows

| Fact | Source | Required change |
|---|---|---|
| Storage/installed-game checks precede recovery | `app/patcher_core.py:Patcher.run` (~293) | Discover unfinished setup before fresh-run checks. |
| No serial binding/process or device ownership | `Adb.run`, `wait_for_device` | Bind serial/user and acquire work/device locks. |
| APK cache uses size; access cache size/mtime | `prepare_normal_apk`, `prepare_debuggable_apk` | Use full content identities. |
| Uninstall/install gap has no durable setup record | `prepare_normal_apk` (~453) | Pin normal APK and consent before uninstall. |
| Manifest rewrite/sign can be repeated | `prepare_normal_apk` (~442–459) | Reuse signed bytes, retain installed-signature fact. |
| Installer checks Success text | `Adb.install` (~262) | Independently verify installed identity. |
| Pristine rebuild mutates pulled layer | `restore_pristine` (~605) | Keep immutable pre-action bytes separately. |
| Partial pull has no backup tar | `pull_changed` (~546) | Rollback must not assume a tar exists. |
| Direct live cp; final restore warns then returns | `push_translation` (~800), `restore_normal_apk` (~826) | Atomic transaction and blocking recovery outcome. |
| Pruning keeps newest two, ignoring pending work | `prune_old_sessions` (~845) | Reference-aware retention. |
| Daemon worker/ADB-killing Close; detail discarded | `app/hok_patcher.py:pump`, `start`, `close` | Cooperative stop/close and structured progress. |
| Fake push writes straight to fake live file | `tools/research/check_windows_repatch.py:FakeAdb` | Model upload/temp/rename/live separately to prove failure behavior. |

## Android

Kotlin paths below are under `android/app/src/main/java/dev/halixm/hokacepatcher/`.

| Fact | Source | Required change/preservation |
|---|---|---|
| Automatic state is Activity-local; open avoids mutations | `MainActivity.kt` (~121,405,1045) | Durable approved-intent startup dispatch. |
| Process-local busy; START_NOT_STICKY | `PatchWorkerService.kt` (~106,227) | Durable claim/ownership, not a sticky-only fix. |
| Shared coordinator lock and game-private flock exist | `PatchCoordinator`, `FirstSetupCoordinator`, `GameFileLock.kt` | Preserve lock hierarchy and orphan-child locking. |
| Language/action saved late; provider mostly root/non-root | `SessionJournal`, `PatchCoordinator` (~401), service | Persist full action/provider/language before work. |
| Incomplete apply rolls back; verified payload can finish forward | `recoverLocked` (~626) | Preserve both safety paths. |
| Recovery cancels pre-payload runs then deletes reusable work | `recoveryCompletionPhase`, `releaseIfResolved`, `releaseSession` | Separate consistency recovery from authorization revocation/cleanup. |
| File writes already verify temp/rename/read-back | `GameFileTransaction.write`, `PrivilegedDeviceService` (~515) | Extend reconciliation, preserve the protocol. |
| Expected output includes unchanged files | `expectedApplied`, `finishApply` | Keep complete output when skipping writes. |
| Originals rehashed in recovery and rollback | `recoverLocked`, `GameFileTransaction.rollback` | Same-invocation verified-originals reuse only. |
| Request checkbox/15-minute/one-use claim precedes journal | `PatchRequestStore.kt` (~30,85–103) | Durable Start auth, atomic claim linkage. |
| Build refusal can immediately delete damaged package files | `PatchCoordinator.kt` (~409–420) | Exact Re-download consequence consent. |
| Setup already recovers without a second uninstall | `FirstSetupCoordinator.kt`, `FirstSetupJournal.kt` | Preserve and route automatically; original still installed needs renewed consent. |
| Installed verifier checks bytes/version/signer/debug | `InstalledGameVerifier.kt` | Preserve independently after uncertain installs. |
| Unconfirmed is distinct | `SessionJournal`, `WorkerStatus`, `recoverLocked` | Never upgrade to success without a fresh verified run. |

## Shared pipeline

| Fact | Source | Consequence |
|---|---|---|
| Delta is pristine reconstruction, not arbitrary corruption recovery | `tools/pristine_delta.py`, `asset_fingerprints.py` | Save true pre-action rollback material. |
| Summary written before Android restores outputs/hashes/delta finish | `build_device_patch.py` (~539), bridge (~731–777) | Publish a final atomic build receipt last. |
| Current build APIs require fresh directories | `android_bridge.py:_build_scratch`, `build_snapshot` (~706) | Explicit reuse/reset entry points. |
| Snapshot extractor deletes incomplete destination | `tools/mobile_snapshot.py` (~85–198) | Reuse complete snapshot; restart interrupted snapshot. |
| Multiple passes modify one package | `build_patch` docstring and implementation | Intermediate package output is not complete. |
| Engine manifest omits bridge/app/native-codec semantics | `EngineAssets.kt`, `android/app/build.gradle.kts` (~19–68) | Extend complete producer identity. |
| Trial restoration/classification repeats | bridge `_restore_package`, `_mixed_packages`, `plan_redownload` | Snapshot-scoped decision reuse. |
| Text retries remove one failing asset at a time | `failing_asset`, staging loops (~426/450) | Measure attempts/copy cost before optimization. |

## Historical evidence and limits

| Record | Measured result | Limit |
|---|---|---|
| Lab notebook 2026-10-18 patch-speed | About 616–621 s Android after earlier optimizations | Different code/data/device; no new savings measured here. |
| Same record, build kill | Manual recovery restores normal APK after kill | Not automatic checkpoint continuation. |
| Lab notebook 2026-10-24 provider tests | Root/wireless loss recovery; cross-provider completed runs; screen-off run | Does not validate this new design. |
| Asset-restore feature/ADR 0008 | Offline restoration and recorded device limits | Do not claim next-update acceptance beyond the existing record. |

## Preserve existing work

Planning baseline modified `AGENTS.md`, `docs/features/extra-text-cycles.md`, `docs/lab-notebook.md`, `docs/translation-progress.md`, `tools/extra_text.py`. Untracked `.impeccable/` and title-size drafts/phone-test/bin artifacts existed. Recheck git status per ticket and preserve them.

The inspected `.venv` is Python 3.12.10. Keep all large game/APK/work data outside the repo. Preserve keys, vendor DLLs, upstream catalogs/runtime and hand-finished sprite labels. `PRODUCT.md` has stale recovery limitations; reconcile them with shipped behavior in ticket 19.

At the final planning check, HEAD was `5220e22` and the earlier unrelated tracked modifications were no longer dirty. This task made no commits or source changes; use current git status, not the initial caution list, as the live workspace state.
