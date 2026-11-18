# Validation and release gates

Planning did not run these implementation/device checks. Record actual results in the implementing ticket. Use `docs/lab-notebook.md` only for new measured timings/device verdicts, preserving unrelated entries.

## Starting checks

From the repo root, Python 3.12 only:

```bat
.venv\Scripts\python.exe --version
.venv\Scripts\python.exe tools\research\check_pristine_delta.py
.venv\Scripts\python.exe tools\research\check_windows_repatch.py
.venv\Scripts\python.exe tools\research\check_mobile_snapshot.py
.venv\Scripts\python.exe tools\research\check_ui_strings.py
.venv\Scripts\python.exe tools\research\check_references.py
.venv\Scripts\python.exe tools\research\check_staging_contract.py
android\gradlew.bat -p android :app:testDebugUnitTest :app:assembleDebug :app:assembleDebugAndroidTest
```

Run relevant checks per ticket; broaden at release. Fix genuine regressions; report pre-existing failures separately with evidence. New offline checks named in tickets do not exist until their owning ticket creates them. All fake-device probes must default to isolated private fixtures, with no real game mutation.

## Planned focused probes

| Owner | New/extended check | What it must observe |
|---|---|---|
| 01/03–07 | `tools/research/check_windows_recovery.py` | Run schema/locks/serial, setup, atomic temp/rename/read-back, false success, checkpoints, stop/close, retry budget |
| 02 | `tools/research/check_run_artifacts.py` | Identity mutations, bounded malformed records, crash publication, precise file set, source/frozen identity parity |
| 09 | `tools/research/check_bridge_continuation.py` | Snapshot/build reuse, incomplete attempt reset, final receipt after restored outputs/delta |
| 08/10/11/12 | Android `RunStoreProbeTest`, extended route/coordinator/setup/request/service probes | Durable authorization, dispatch claim gap, checkpoint reuse, repeated interruption, consent/Stop/provider binding |
| 14 | Extended `FullCoordinatorProbeTest`, `RemovalRollbackProbeTest`, recovery probes | Full expected set unchanged despite fewer writes/hashes |
| 16 | Extended `CacheReuseProbeTest` and Windows recovery/artifact probes | Actual installed bytes + complete key required for no-op receipt reuse |
| 17/18 | Existing asset/update checks plus focused probe/metrics additions | Same restore/deletion verdict/output; fewer real trial copies/staging retries |

Portable fake probes should use synthetic bytes and generated fixture APKs where possible. Where real APKs/packages are necessary, use an explicit validated fixture descriptor, not a hard-coded old game's expected identity. Never weaken production checks to make a fixture pass.

## Existing Android instrumentation

Install the matching debug app and test APK on the intended device only after reading the individual probe's scope. Bind every host command to its serial. From repo root:

```bat
adb -s <serial> shell am instrument -w -r -e class dev.halixm.hokacepatcher.CoordinatorRecoveryProbeTest,dev.halixm.hokacepatcher.FullCoordinatorProbeTest,dev.halixm.hokacepatcher.RemovalRollbackProbeTest dev.halixm.hokacepatcher.test/androidx.test.runner.AndroidJUnitRunner
```

Also run affected journal/request/publication/route/service-loss/first-setup/provider probes. Many operate in isolated contexts with fake device transports; read them before assuming they are harmless to a live game.

What actually ran on phone `f15a72e` (Xiaomi M2007J3SG, Android 12) in Pass 2, 2026-11-12 to 2026-11-13. Raw logs are in `D:/scratch/hok-ac-pass2/logs` unless noted.

| Run (build) | Classes | Result | Log |
|---|---|---|---|
| Safe set, first (vc100, 13:32) | 28 app-private/read-only classes | 141 run: 94 pass, 26 skipped, 21 fail (10 *Private path alias*: the `/data/user/0` vs `/data/data` production bug, fixed in `RunStore.privateRoot`; the rest test bugs) | `instr_safe.log` |
| Safe set, after fixes | Same 28 classes | 142 run: 115 pass, 26 fixture-skipped, 1 fail (`FirstSetupPolicyProbeTest` uid expectation, environmental, also fails at HEAD) | `instr_safe_pass2.log` |
| Safe set, after engine/lock fixes | Same 28 classes, more cases | 146 run: 118 pass, 27 fixture-skipped, 1 fail (the same `FirstSetupPolicyProbeTest`) | `D:/scratch/hok-ac-pass2/probe-full-after-fixes.log` |
| Storage fix (`3c2594df`) | `StorageRetentionProbeTest`, `PausedStopProbeTest` | OK (3 tests) | `storage-fix-probes-final.log` |
| Automatic cache pressure (`798b04fe`) | `StorageRetentionProbeTest` (6), `PausedStopProbeTest` (1) | OK (7 tests) | `automatic-cache-pressure-probes.log` |
| Measured-shortage reclaim (18:42; installed build not logged) | `StorageRetentionProbeTest` (3), `EngineProbeTest` (2) | OK (5 tests) | `reclaim-probes.log` |
| fixes-1920 (`a4dff827`) and stopfix-2350 (`21f51bb2`) | `RunStoreProbeTest`, `StorageRetentionProbeTest`, `EngineProbeTest` | OK (35 tests) each | `fixes-1920-probes.log`, `stopfix-2350-probes.log` |
| autoredownload-1130 (`38c31162`) | The three above plus `CoordinatorRecoveryProbeTest` | OK (56 tests), but `CoordinatorRecoveryProbeTest`'s 19 cases were fixture-skipped | `autoredownload-1130-probes.log` |

Fixture-gated (skipped by `Assume` until 2026-11-18; see the gate table for the first run): `CoordinatorRecoveryProbeTest` (19), `FullCoordinatorProbeTest` (4–5), `ApkPreparationProbeTest`, `CoordinatorSourceGuardProbeTest`, one `PatchRequestProbeTest` case. They need an app-private source/APK descriptor (`PrivateProbeFixtures`); ticket 01 moved four probes onto it. `CacheReuseProbeTest` ran (10 pass) and has since been deleted from the working tree. `RedownloadReviewProbeTest` exists only on branch `fix/redownload-recovery` (`413a837`), not on master or in this working tree; it ran on an API-36 emulator (lab notebook, 2026-11-12), not on this phone.

Not run (each needs its own mutation review or consent): `ShizukuProbeTest` opt-ins, `FixtureInstallerProbeTest` install methods, `WorkerServiceLossProbeTest` (leaves a real emergency record), `WorkerProbeTest`, `FirstSetupWorkerGuardProbeTest` and `WorkerPermissionProbeTest` (overwrite real worker state), wireless pairing, and the `MainActivity` UI tests while real pending state exists.

Ticket 01 removes brittle fixture assumptions or explicitly reports those gates unavailable. A build that compiles tests is not a passing instrumentation run.

## Failure-injection matrix

For every row assert: one worker; correct target/action/provider; no false Verified complete/Open game; required bytes/delta retained; bounded attempts; exact final output or safe actionable pause. Count snapshot/build/install/write calls to prove reuse. Repeat interruption during recovery, not only during the original action.

| Injection point / condition | Required observation |
|---|---|
| Before/after Start persistence and request claim | No unapproved work; saved authorization survives claim-before-journal death; one dispatch |
| Unreadable, truncated, unknown-schema or missing record | Attention; no guessed authorization, cleanup of required material or game mutation |
| Two windows/services; two work folders; wrong phone/user | One owner; second request cannot write/install or retarget pending work |
| Snapshot stream half-complete | Restart snapshot only; reuse prepared material; incomplete data never published |
| Snapshot committed, build half-complete | Reuse snapshot; restart build only in fresh attempt |
| Summary written but restored outputs/delta absent | Refuse STAGED reuse; no apply |
| Completed STAGED output | Reopen skips snapshot/build after required validation |
| Temp copy partially written / temp hash fails | Live old file intact; safe temp cleanup/retry |
| Rename committed before acknowledgment | Inspect live new hash before any retry; no truncation/no unnecessary duplicate write |
| Between file commits | Rollback incomplete apply to saved pre-action bytes; reuse committed build to continue |
| During rollback/Watchdog restore | Repeated recovery converges; complete file/Watchdog set verified |
| Payload verified, normal install fails | Blocking restoration state; no translation rebuild and no false success |
| Normal install committed, reply lost | Installed identity audit recognizes success; avoid needless reinstall |
| Delta promotion/removal or final receipt publication cut | Idempotent finalization; old/pending pristine material remains usable |
| First setup before uninstall | Stop avoids deletion; approval still scoped |
| First setup uninstall/install gap | Missing game recovered from pinned normal APK; uninstall count stays one |
| Uncertain uninstall, original still present | Fresh data-loss consent required; no automatic repeated uninstall |
| Provider/USB loss and return | Wait/reconnect same saved target/provider; attach or claim one worker; retry budget preserved |
| Engine/catalog/fallback/sprite/native-code change | Invalidate affected stage/no-op receipt; retain independent recovery ability |
| Game/APK change while stopped | Reconcile safety first; readiness and pristine rules gate fresh snapshot/build |
| Verified payload later changed by game | Old result stays recovered_unconfirmed; fresh safe work or actionable pause, no success upgrade |
| Low storage before stage/temp/install/recovery | Budget actual operation and recovery reserve; keep required recovery files |
| Recovery needs attention shown in either patcher | Existing main patch button has recovery label/handler and cannot start a fresh patch; Save log is separate and secondary |
| Stop during build/install/write and during recovery | Immediate Stopping safely; repeated button disabled; recover and stay stopped across reopen |
| Windows Close at the same points | Preserve continuation; feasible cleanup then close; reopen continues saved action |
| Android Activity recreate/background/force-stop | Background does not cancel service; force-stop resumes on reopen only with durable authorization |
| Repeated identical failure/reopen | Initial attempt + one safe automatic retry; persistent pause thereafter |
| Re-download consent changes or plan grows | Fresh consent; approved deletion replay reconciles actual absence/hashes |
| Free up space while unresolved | Required artifacts excluded; resolved optional cache removal invalidates receipts |
| Legacy journals/pending delta/no durable authorization | Safety recovery only as justified; no silent new patch permission |

## Real output and timing controls

Use external pristine dump, matching APK and external scratch with sufficient free space:

```bat
.venv\Scripts\python.exe tools\research\check_pristine_delta.py --game <pristine-game> --apk <installed.apk> --work <external-scratch>
```

Compare baseline/change with the same inputs: all staged SHA-256 and file sets; normalized summary (remove only explicit nondeterministic timings/paths); applied/skipped text/texture counts; delta pristine/staged mappings and asset bodies; expected live layer. Cover EN, ID, EN→ID, ID→EN, same-language repeat, Remove and changed engine/game. Keep existing append/allowlist/region checks unchanged.

Measure fresh, same-language, language-switch, completed-build resume, interrupted-build resume and final-install-only recovery separately. Record total/stage durations, transferred/written bytes, build calls, hash passes, install attempts, storage minimum and device/input/build identity. Use comparable repeated runs where practical. Historical 616–621 s is not the control for changed code/data/device. Reject a shortcut on output/safety regression; record an investigation with no safe gain as such.

## Gate status (2026-11-17)

PASS means a run with recorded evidence; OPEN means not run or not passed; SKIPPED means the user chose not to run it, and it stays open for release review. Evidence: [coordinator.md](coordinator.md) (C), the [lab notebook](../../docs/lab-notebook.md) (N) and the ticket Comments.

| Gate | Status | Evidence |
|---|---|---|
| Offline Python checks (Windows file transaction, checkpoints, controls, signing, recovery, run artifacts, bridge continuation, repatch, pristine delta, mobile snapshot, staging faults) | PASS | C, Pass 2 Windows/bridge entry; `D:/scratch/hok-ac-pass2/logs/*.fsync-fix.log` |
| `check_ui_strings`, `check_references`, `check_staging_contract` | PASS | C; re-run after each later fix |
| Android unit tests and full-codec builds | PASS | C (109/109, later 151/151 JVM; assembleDebug and AndroidTest builds) |
| EN/ID output parity on the 1.8.0.1 fixture | PASS | C, parity worker; `D:/scratch/hok-ac-pass2/parity/` |
| Real cycles, Android Wireless debugging: C2–C8, scoped and automatic Re-download, Remove, Stop reporting | PASS | N, 2026-11-12 and 2026-11-13 entries |
| Real cycles, Windows patcher over USB (W1–W5) | SKIPPED (user, 2026-11-17, "Skip windows patcher") | C, last entry |
| Real cycles, Android Shizuku | SKIPPED (user, 2026-11-18, "Skip the Shizuku cycles") | ticket 19 comment, 2026-11-18 |
| Real cycles, Android Root (zero installs, owner/SELinux) | PASS (2026-11-18, `cda1f22`, KernelSU phone): force-stop mid-build, worker kill mid-apply, Stop mid-apply, force-stop after the writes and at the final check, EN/ID switches and Remove; zero installs, game owner and labels kept, Remove byte-identical to pristine | N, 2026-11-18 Root entry |
| Fixture-gated probes (`CoordinatorRecoveryProbeTest`, `FullCoordinatorProbeTest`, `ApkPreparationProbeTest`, `CoordinatorSourceGuardProbeTest`) | PARTIAL (2026-11-18, `cda1f22` + legacy-recovery fix and probe corrections: PatchRequest 2/2, CoordinatorRecovery 19/19, SourceGuard 1/1, ApkPreparation 1/1; FullCoordinator SKIPPED by the user 2026-11-18: needs about 16 GB internal) | Lab notebook, 2026-11-18 corrected-probes entry; ticket 19 comment |
| Automatic Re-download loop-guard fallback and an interrupted automatic deletion | OPEN | N, automatic Re-download entry |
| Frozen `build.bat` and `--selftest` | PASS (2026-11-17, `96c4613`) | N, 2026-11-17 frozen-build entry: EN and ID staged bytes identical to the source run, 14/14 files each; `--smoketest` 12/12. Text and texture passes only (`--selftest` passes no APK) |
| Source `run.bat` | OPEN | Needs a person at the GUI |
| GUI/visual checks (both languages, enlarged fonts, progress/Close/Stop/permission states) on either patcher | OPEN | Not run on the phone builds; emulator captures exist only for the review card (N, 2026-11-12) |
| Comparable performance measurements (fresh, repeat, resume, final-restore-only) | OPEN | Single phone observations only (N); no comparison |
| Parity finding: `run_artifacts.windows_producer_identity` is None for every source checkout (non-ASCII names under `tools/research/career_atlas/originals/`) | FIXED (2026-11-18): the 8 files renamed to ASCII; identity is `windows-source` from this checkout; `check_run_artifacts.py` (CI `checks`) refuses a non-ASCII tracked name | C, parity worker finding 1 |
| Parity finding: `compare_continuation_controls.py capture` refuses APK builds | FIXED (2026-11-18): capture normalizes an `added-from-apk` package's `<work>/prime/<id>` itself; EN and ID +APK builds at HEAD captured with no wrapper each compare PASS against both Pass 2 reports of their language (base and current); `check_continuation_controls.py` (CI `checks`) | N, 2026-11-18 entry |
| Remove output offline (Windows) | PASS (2026-11-18): EN and ID +APK builds installed and removed on a stand-in phone holding the real 1.8.0.1 packages; every file byte-identical to pristine after Remove, 11 removed = 11 changed of 14, no delta left (`check_windows_remove.py`) | N, 2026-11-18 Remove entry |
| Changed engine/game real controls | PASS (2026-11-18, offline, 15/15): real `android_bridge` checkpoints on 1.8.0.1 then 1.10.1.2 pristine dumps; game, same-size game, catalog and same-size engine changes each refused; rebuilds equal fresh builds (14 files), the catalog change reaches `1/1_0.db`; Windows producer keys change for both engine changes and the old staged receipt is refused (`check_changed_input_controls.py`). Not on a phone, no real Windows build | N, 2026-11-18 changed-controls entry |
| Legacy schema-1 safety-only retry migration | CLOSED by decision (user, 2026-11-18, "Yes, record it"): no migration; the safety-only policy stays as it is | N, 2026-11-18 legacy-retry review |
| Historical `check_update_redownload.py` real-update capture | OPEN | C, 2026-11-12 user answer |

The old-data cycles left real-update captures under `D:/scratch/hok-ac-pass2/device-cycles/redownload-1801` (`before-push`, `after-push`, `after-update-old-patch`, `old-patch-15-error-2`, each with `capture.json` and `Watchdog.tar`, plus `objects`) and `autoredownload-1801b` (`before-push`, `after-push`, `after-update`, `objects`). They may serve as the real-update capture that check needs, but the check reads the labels `after-push`, `after-patch`, `after-update` and `after-finish`, and these captures have no `after-patch` or `after-finish`. It has not been run against them, so the gate stays open.

## Release gate

Real interruption cycles are required for Windows and Android Shizuku, Wireless debugging and Root. Follow `docs/runbooks/device-cycle.md`; obtain separate informed consent for destructive first-setup/data-deletion tests. Private fixture checks can proceed without that live-game consent. Retain verified normal APK, logs and recovery access during each cycle. Root must install zero APKs and retain owner/SELinux behavior.

Check Windows source (`run.bat`), frozen build (`build.bat`, then `--selftest <game-dir> <out-dir>`), Android unit/build/instrumentation, both UI languages, enlarged fonts/scaling and progress/close states. New runtime imports must freeze correctly; do not ship research modules. Final feature report lists passed/unrun gates honestly. A source build or historical device cycle cannot close a new real interruption gate.
