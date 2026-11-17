# 11: Make Android Stop, setup and reconnect follow saved intent

Status: ready-for-agent
Implementation: complete
Verification: pending
Blocked by: 10

## Scope and files

Own `PatchWorkerService.kt`, `FirstSetupCoordinator.kt`, `FirstSetupJournal.kt`, `FirstSetupRequestStore.kt`, stop/lifecycle parts of `MainActivity.kt`, `WorkerStatus.kt` and provider lifecycle seams as needed. Read architecture sections 3/6–7, ADRs 0001/0002/0007 and existing first-setup/provider probes.

## Steps

1. Treat the Stop safely tap as the instruction: remove its redundant confirmation, persist intentional Stop first, immediately publish Stopping safely, disable duplicate requests and reach the next safe boundary. Explain waiting for current build/install work; do not pretend cancellation is instantaneous.
2. On repeated interruption finish safety recovery, then stay stopped. Keep valid snapshot/build cache for explicit later Start; Activity recreation/backgrounding alone must not cancel the service.
3. Route unfinished approved setup automatically using its existing journal and pinned normal APK. Missing-game recovery installs only; original still present after uncertain uninstall waits for fresh destructive approval; unrelated installed identity refuses.
4. Preserve the parent requested action across setup/download wait. After required Downloads finished answer and validation, continue the saved translation without a routine patch dialog.
5. Reconnect the exact recorded provider while open, attach/claim one worker and keep retry state. Show grant/pairing/installer intervention where needed; provider permission cannot be silently granted or replaced by another provider.
6. Persist one automatic retry budget per eligible operation; waiting is not repeated install dispatch. Explicit Retry can re-arm safe work, but never bypass setup consent or repeat uninstall.

## Acceptance

- [ ] Stop during snapshot/build/apply/install responds immediately, restores safely and remains stopped through process death/reopen.
- [ ] Repeated Stop is disabled; background/rotation leaves the foreground worker correctly owned.
- [ ] Setup uninstall/install-gap recovery never repeats uninstall; new approval required when original remains.
- [ ] Download completion resumes the same parent action/language/provider; no hidden new authorization.
- [ ] Provider return resumes automatically within budget; exhausted failures survive reopen and show one next action.

## Checks and handoff

Run first-setup coordinator/journal/request/consent/worker-guard probes, WorkerServiceLossProbeTest, ProcessDeathFixtureProbeTest, RunStoreProbeTest and provider/route checks with fixtures. Add a stop-during-recovery case and second-kill case. Run UI-string and Android unit/build checks.

## Stop condition

Keep privileged permission/installer/download steps as explicit user intervention. If no safe setup recovery is possible, retain the saved APK and report attention, never clear data again.

## Comments

Pass 1 (implementation only, 2026-11-12). Not done in this pass: no device or adb use, no probe runs, no change to the real game, no commit. Uncommitted changes from other tickets were left as they were. `PatchCoordinator.kt` was not touched. The acceptance boxes stay unchecked until pass 2.

### Changed files

**`android/.../MainActivity.kt`**

- Stop safely
  - Stop safely is one tap with no dialog.
  - `requestStop` saves the Stop first; `saveStop` retries briefly while the store lock is busy.
  - It then shows *Stopping safely*, disables the button and sends `cancel`.
  - A `stopping` flow survives Activity recreation. It runs only the steps that `AutomaticRoute.allowedWhileStopping` allows, then `finishStop`.
  - If one of those steps fails, the screen shows that failure's own next action, and the Stop stays saved.
- Reopen: `resumeSavedAction` now uses `AutomaticRoute.onLaunch`. It covers a saved Stop, setup recovery, continuation within the retry budget, and attaching to a live worker (including its `stopping` flag).
- Provider
  - `provider()` returns the saved run's provider.
  - The provider and language pickers are locked while a run is unresolved.
  - `waitingForAccess` waits for the saved Wireless debugging provider and resumes when it returns. Pair stays usable meanwhile.
- Retry
  - `retryAutomatically` records error, recovery_required, cancelled, provider-loss and interrupted results with their failure class (`failureClass`) and retries once within the failed operation's budget.
  - Waiting for the saved provider is saved as the waiting reason `provider` (`waitForAccess`, `RunStore.waitFor`), never as an attempt.
  - An explicit Start calls `RunStore.rearm`.
- First setup
  - Consent passes the parent run.
  - `setup_cancelled` asks for fresh consent on the same preparation.
  - A `prepared` result for a run whose setup is READY starts `patch` without the routine dialog.

**`PatchWorkerService.kt`**

- `cancel`
  - Ignored when the worker is idle or a Stop is already in progress.
  - Otherwise it saves the Stop, cancels the coordinators, and publishes `stopping` in the worker state and the notification. The notification's Stop action is removed.
- `dispatchRun`
  - `first_setup` binds to the consent's parent run, which must be a translate run that may continue and is not Root. It persists the parent's `first_setup` attempt before claiming the consent (never re-armed).
  - `setup_recover` and `setup_update` bind to the journal's parent run, even after a Stop.
  - Legacy setups without a parent run keep the current provider.
- A request refused because its run was already stopped reports `cancelled` with its own flow, not a damaged record.

**`FirstSetupCoordinator.kt`**

- `run(..., consentRequest, parentRun)` requires the parent run to match the consent's.
- A saved Stop or cancel before the uninstall intent removes nothing. This is rechecked after the last force-stop.
- Recovery is unchanged: install only, never uninstall. If the original is still present, setup ends as cancelled.

**`FirstSetupJournal.kt`**

- Adds an optional, validated `parent_run`, read as `parentRun`.
- Adds `readyFor(context, runId)`.
- A cancelled result now includes `fresh_consent_required` and `preparation`.

**`FirstSetupRequestStore.kt`**

- `confirm(..., parentRun)` requires an authorized, continuing, non-Root translate Start for this target.
- Adds `parent(id)`.
- Consent stays one-use, with its 15-minute claim window.

**`RunStore.kt`**

- The retry budget is per logical operation and reuses the existing `beginAttempt` counts (tickets 08 and 10) as the one source of truth: `attempts[<operation>]` is 1 for the initial attempt and 2 once its automatic retry was sent. Operation keys are the ones persisted before dispatch: `preparation` (service), `dispatch` and the coordinator stages through `operation(journal, name)` (`PatchCoordinator`, unchanged), and `first_setup`. A failure before any operation began is charged to the pseudo-operation `start`, counted by `recordFailure` itself.
- `beginAttempt` also saves `last_operation` and clears `waiting`.
- `recordFailure(id, failureClass)` charges the failure to `last_operation`, saves `failure: {operation, class}`, and returns true while that operation's count is below 2. Otherwise it saves `waiting: "explicit_retry"` and returns false.
- `Run.retryExhausted` is true when the failed operation's count is 2, so a second failure of the same operation pauses persistently, while a different operation still has its own retry.
- `waitFor(id, reason)` saves the waiting reason (`provider`, `explicit_retry`) or clears it; never an attempt.
- `rearm` requires `mayContinue`, clears every attempt except `uninstall`, `first_setup` and `redownload_delete`, and clears `last_operation`, `failure` and `waiting`.
- Schema: three optional, validated fields (`last_operation`, `failure`, `waiting`); `schema` stays 1 and older records still load. A `failure` must name an operation present in `attempts`.

**`AutomaticRoute.kt`**

- Adds `allowedWhileStopping(step)`, `Launch`, `Saved` and `onLaunch(run, runs, setups)`.
- `choose` is unchanged.

**`GuidedHome.kt`**

- Adds `stopping(value)`, a minimal UI seam that disables the Stop button and relabels it.

**`WorkerStatus.kt`**

- Adds descriptions for a running record that is stopping, for `stopped_consistent`, and for a setup cancellation that needs fresh consent.

**`resources/ui/strings.json`**

- Adds `android` to the platforms of `stopping_safely`, `waiting_operation_boundary` and `stopped_safely_note`.
- New draft keys: `stop_not_saved` and `retrying_saved_action`.

**Probes**

- `FirstSetupCoordinatorProbeTest`
  - A Stop saved before the run, and one saved at the last force-stop: no uninstall, and the record closes.
  - Stop during removal: the install finishes, the run stays stopped, and the downloads answer does not continue it.
  - Stop during recovery, then a second kill: the uninstall count stays 1 and recovery is install only.
  - Original still present after an uncertain uninstall: fresh consent is required, the cancelled setup cannot recover again, and a changed identity is refused.
  - A READY setup hands off only to its own Start.
- `RunStoreProbeTest`
  - `oneAutomaticRetryPerLogicalOperationSurvivesReopenAndOnlyExplicitRetryRearmsSafeWork`: a pre-operation failure is charged to `start`; waiting is a reason, not an attempt; a failed `snapshot` retries; a different operation (`build`) has its own retry; a second `build` failure pauses with `explicit_retry`, its class kept across a new store instance; `rearm` clears safe operations, failure and waiting, keeps `uninstall`/`redownload_delete`/`first_setup`, and refuses after a Stop.
  - Setup dispatch uses the parent run's provider after a Stop.
  - Destructive setup dispatch requires a continuing, non-Root parent run.
- `AutomaticRouteProbeTest`: the step filter used while stopping, and the `onLaunch` table.

**Docs**

- `android-shell-providers.md`: new "Stop safely, setup and provider return" table.
- `standalone-patcher-app.md`: First setup row.
- `android-shizuku-patcher.md`: note on retry and Stop.

### Checks actually run

- Compile: `android/gradlew.bat -p android --offline :app:compileDebugKotlin :app:compileDebugUnitTestKotlin :app:compileDebugAndroidTestJavaWithJavac` (JDK 21, sandbox disabled for the Gradle cache). Result: **BUILD SUCCESSFUL** (final run 47 s).
- `.venv\Scripts\python.exe tools\research\check_ui_strings.py`: exit 1, with the same failures as before this ticket.
  - RunStore field names `sha256`, `certificate_sha256`, `record_sha256` and `receipt_sha256`, flagged by mistake (from ticket 08).
  - Windows `PatchError` text and placeholder findings in `app/`.
  - No new finding from this ticket's keys or literals.
- `git diff --check`: clean (CRLF notices only).
- No .py file was touched, so py_compile was not needed.
- Not run in this pass: any probe, unit test, instrumentation test or device check.
- Probes not changed and not run: `WorkerServiceLossProbeTest`, `ProcessDeathFixtureProbeTest`, and the first-setup request, journal and consent probes. The stop-during-recovery and second-kill cases were added to `FirstSetupCoordinatorProbeTest` instead.

### Known concerns

- A fresh launch now acts on its own in two cases: a saved Stop (safety recovery only) and an approved setup intent. A setup waiting for downloads asks its question on every open while its Start may continue. Needs a product check against spec Q1.
- A failure is charged to the operation last begun. A failure in code that runs after an operation succeeded but before the next `beginAttempt` is charged to that earlier operation; the coordinator begins an operation for each stage, so this is narrow.
- A fresh first-setup consent after an uncertain uninstall uses the parent's second `first_setup` attempt; a third is refused until a new Start.
- Stop takes effect at the coordinator's next `checkpoint()`. A long Python build or an install is waited out. The screen explains the wait; its length was not measured.
- `refreshHome` re-reads `RunStore.pending()` every second to keep the saved provider. If the store lock is held, it keeps the last reading.
- The service's refusal path stops without calling `startForeground`. This pattern predates the ticket and was not changed.
- The routine patch and Re-download dialogs remain everywhere except the continuation after setup.
- The old Stop dialog keys (`stop_safely_question`, "Keep going", "Stop and recover") are now unused.
- If a Stop's setup finishes in WAITING_FOR_GAME_UPDATE, the stopped Start stays unresolved until the downloads answer, because a pending setup blocks `resolve`. The next Start asks the question, then resolves the old Start and prepares fresh.

### Handoff seams

- **12**
  - `RunStore.rearm` never clears `redownload_delete`.
  - `allowedWhileStopping` excludes any deletion.
  - `retryAutomatically` returns false for stopped runs.
  - `waiting` results still end the flow.
- **13**
  - Copy for *Stopping safely*, `waiting_operation_boundary` and `stopped_safely_note` (now on Android too).
  - The draft keys `stop_not_saved` and `retrying_saved_action`, and the English lines in WorkerStatus.
  - Removing the remaining routine dialogs and the unused Stop dialog keys.
  - One shared state model for Waiting for you.
- **14**: nothing beyond the unchanged coordinator paths.
- **16–18**: `RunStore.Run` carries `attempts` per operation, `failure` (operation, class) and `waiting`, which metrics can read.
- **19**
  - Real Stop, kill and provider-loss cycles on Shizuku, Wireless debugging and Root.
  - Run every probe named above.

Pass 2 instrumentation (2026-11-12): `FirstSetupPolicyProbeTest.testInvalidRemovalIdentityRejectedBeforeShellAccess` still fails, environmental and pre-existing (HEAD has the same order): `removeGameForFirstSetup` checks the worker uid (`requireInstalls`) before the identity, and the probe runs as the app uid. The uid check was not changed. The Stop race probe in CacheReuse now retries Stop as `saveStop` does (see 10).

Pass 2 device-cycle fix (2026-11-12): Real Android cycle `63ff0ad4-1b7e-44a8-9ed1-bbbe1dcb63fb` failed in `build`, ran `recoverLocked` (`beginSafetyAttempt("recovery_normal_restore")`), restored normal APK cleanly, and then `MainActivity.retryAutomatically` called `RunStore.recordFailure`, charging `failure.operation` and `last_operation` to `"recovery_normal_restore"` instead of `"build"`. Fix: `PatchCoordinator.continueLocked` captures `lastOperation` before calling `recoverLocked`; when `recoverLocked` succeeds cleanly and `journal.phase != COMPLETE`, `RunStore.restoreOperation` (under `requireCoordinator`) restores `last_operation` to the failing stage (or removes it if `null`). When `recoverLocked` itself throws (or dies mid-restore), the safety operation remains charged. Verified by `RunStoreProbeTest.cleanSafetyFallbackRestoresFailingOperationWhileFailedSafetyStaysChargedToSafety` (PASS on `f15a72e`); `FullCoordinatorProbeTest.testStageFailureWithCleanRecoveryChargesFailingStageAndRecoveryFailureChargesSafety` skipped on device due to missing private probe fixtures.


Pass 2 idle-Stop fix (2026-11-12): `MainActivity.routeAutomatic` posted `RESOLVE_STOPPED` to the UI and then called `runTask` while the original task still held `busy=true`. The nested task was dropped, so a clean cancelled session stayed on Stopping safely indefinitely (real run `e64b26df-33c6-48fa-9ee3-8a9963fb01ba`). `AutomaticRouteTask` now resolves in the original background task before delivering its result. The resolver re-reads routing under `RunStore.coordinator` and calls unchanged `RunStore.resolve`, which still refuses pending setup/emergency/patch recovery. The extracted `UiTaskRunner` preserves the original busy gate and callback order. No saved Stop, attempt budget or continuation permission is changed; no game worker starts to close an idle Stop.

Regression: `IdleStopRoutingTest.stoppedIdleActionClosesBeforeBusyTaskDeliversUi` first failed at line 30 with the original nested submission. After the fix, `android/gradlew.bat -p android --offline :app:testDebugUnitTest --tests dev.halixm.hokacepatcher.IdleStopRoutingTest :app:compileDebugKotlin` passed (4 tests). Additional cases cover blocked resolution, unknown pending recovery, throwing-task cleanup, nested/concurrent submission refusal, busy release and acceptance of a later task. Uses isolated deterministic task/UI queues; never launches MainActivity, a service or the game. Real installed fix verification remains with the coordinator.
