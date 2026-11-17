# 08: Persist Android Start authorization before dispatch

Status: ready-for-agent
Implementation: complete
Verification: pending
Blocked by: 01, 02

## Scope and files

Own new `RunStore.kt`, `PatchRequestStore.kt`, necessary `SessionJournal.kt` linkage, `PatchWorkerService.kt` dispatch claim and request/journal probes. Kotlin paths are under the existing app package. Read architecture sections 1–3/6, existing FirstSetupRequestStore and coordinator lock implementations. UI routing comes later.

## Steps

1. Persist exact action/language/provider/device-user target, preparation/input identities and continuation/stop/retry state before preparation/dispatch. Ordinary Start is durable authorization; destructive consent remains separately scoped.
2. Replace the routine checkbox-derived confirmation API with Start authorization. Preserve prepared receipt binding, root/non-root refusal and tamper checks. Remove the 15-minute expiry only for durable ongoing Start intent; retain one-use destructive request semantics.
3. Close the consumed-request-before-journal gap using an atomic recoverable claim linked to a stable run/session id. A claimed request with no child journal must be resumable exactly once, not lost or duplicated.
4. Integrate ownership with existing coordinator.lock and a documented lock order. Repeated service/UI dispatch attaches to the same run; process-local busy is not the safety lock.
5. Version readers/writers and preserve schema-1 journals as safety-only legacy recovery. Status JSON and Activity saved state cannot authorize new mutation. Root/Shizuku/Wireless keys must stay distinct.
6. Add persistent attempts/stop updates that are safe under service loss; validate malformed/oversized/traversing records and referenced preparation roots.

## Acceptance

- [ ] Crash before/after claim and before journal creation yields at most one authorized run, with no lost unfinished request.
- [ ] Picker/provider changes, stale receipts, wrong root kind and tampering cannot alter a pending action.
- [ ] Intent survives process death beyond 15 minutes without a fresh ordinary checkbox.
- [ ] Legacy/no-authorization records never become permission for a new patch.
- [ ] Shared lock prevents patch/setup/recovery/request races and Stop state survives restart.

## Checks and handoff

Add `RunStoreProbeTest`; extend PatchRequestProbeTest, JournalProbeTest, SessionPublicationProbeTest and pure route/state unit tests where appropriate. Run Android unit/build checks and affected instrumentation with validated fixtures. Hand off durable claim APIs and migration cases to 09–12.

## Stop condition

Do not replace validation by passing `true` to old confirmation methods. If journal and authorization cannot be correlated, pause without mutation.

## Comments

2026-11-12, pass 1: Implementation complete; verification pending. Acceptance remains unchecked. No unit/behavior/instrumentation/integration/UI-string/reference/performance/pipeline/device test ran. No real game mutation, fixture modification, commit, publication or release.

| Exact files changed for 08 | Purpose |
|---|---|
| `android/app/src/main/java/dev/halixm/hokacepatcher/RunStore.kt` (new) | Durable exact Start intent; strict versioned/type-checked/duplicate-key-refusing bounded JSON; canonical digests/read-back; exact provider/device/user/package/root; short store lock; persistent attempts/Stop; stable recoverable claim and guarded resolution. |
| `android/app/src/main/java/dev/halixm/hokacepatcher/PatchRequestStore.kt` | Explicit saved-run preparation binding; full installed/source/normal/access identities and receipt hash; independent APK reload; root-kind/path/link/tamper refusal. Old checkbox confirm/claim methods remain compile-compatible refusals, never permission. |
| `android/app/src/main/java/dev/halixm/hokacepatcher/SessionJournal.kt` | Optional schema-2 stable run/session UUID and authorization-key linkage; schema-1 safety-only reader; linked identity fields immutable; duplicate/linked malformed record refusal; restart only an owned unpublished initial draft, never a second published child. |
| `android/app/src/main/java/dev/halixm/hokacepatcher/PatchCoordinator.kt` | Shared coordinator ownership, durable claim+dispatch, duplicate child attachment, saved language, ordinary Start authority guard on old primitives, persisted Stop checks, Free up space refusal while authorization is unresolved. Ordinary translation cannot silently become destructive damaged-file deletion. |
| `android/app/src/main/java/dev/halixm/hokacepatcher/FirstSetupCoordinator.kt` | Narrow delegation of existing exclusive lock to the shared helper; existing pending-session and consent semantics retained. |
| `android/app/src/main/java/dev/halixm/hokacepatcher/PatchWorkerService.kt` | Validate durable requests before busy ownership, connect exact saved provider, serialize preparation, persist attempt before work, retain run id in projection, dispatch through coordinator, persist Stop before cancellation. Schema-2 safety recovery resolves provider from its correlated run even when stopped. |
| `android/app/src/main/java/dev/halixm/hokacepatcher/MainActivity.kt` | Narrow real Start-before-preparation seam and explicit preparation binding. Existing routine dialogs remain for 13; their checkbox is no longer ordinary authority. |
| `android/app/src/androidTest/java/dev/halixm/hokacepatcher/RunStoreProbeTest.kt` (new) | Authored synthetic metadata probes: expiry-free ordinary intent, exact saved choices, strict malformed types/fields/provider/root/duplicate JSON, size/traversal/link refusal, retry/Stop persistence, Stop while coordinator is held, fresh direct primitive denial, legacy/no-status authority and saved-provider safety recovery. |
| `android/app/src/androidTest/java/dev/halixm/hokacepatcher/AuthorizedProbeRun.java` (new) | Explicit validated fixture → private copied APK preparation → real Start/binding helper. No hard-coded fixture fallback or production bypass. |
| `android/app/src/androidTest/java/dev/halixm/hokacepatcher/PatchRequestProbeTest.java`, `JournalProbeTest.java`, `SessionPublicationProbeTest.java` | Authored claim-before-journal interruption/reclaim, stable duplicate attachment, exact provider/action, tampered receipt, legacy refusal, schema linkage/immutability and unpublished initial draft restart/refusal probes. |
| `android/app/src/androidTest/java/dev/halixm/hokacepatcher/FullCoordinatorProbeTest.java`, `CoordinatorSourceGuardProbeTest.java`, `FirstSetupJournalProbeTest.java` | Migrate full private fixture mutation to durable Start/dispatch and copied APK paths; source/official/preexisting setup refusal checks retained against new API. |
| `docs/features/android-shell-providers.md`, `android-shizuku-patcher.md`, `language-switch.md`, `standalone-patcher-app.md`, `update-stuck-redownload.md` | Describe current authorization/claim/safety seam, scoped-consent pause, unchanged legacy safety recovery and open continuation/device gates. Preserve earlier unrelated content. |
| `.scratch/automatic-continuation/issues/08-android-run-authorization.md` | This implementation/check/API handoff. |

| Check actually run | Result |
|---|---|
| Initial compile command inside sandbox | Did not start Gradle: access denied to existing wrapper cache `.zip.lck`; no test ran. |
| Escalated `android/gradlew.bat -p android --offline :app:compileDebugKotlin :app:compileDebugUnitTestKotlin :app:compileDebugAndroidTestJavaWithJavac` | Earlier trees passed, BUILD SUCCESSFUL in 2m44s, 32s and 29s. Compile-only tasks; no tests. Final post-edit compile recorded below. SDK/JDK supplied through process environment only; no `local.properties`. |
| `git diff --check` | Passed; CRLF conversion notices only. Whitespace check only. |
| Behavioral/request/journal/publication/route/instrumentation/UI-string/reference/device gates | Not run, deferred to pass 2 by user override. New fixture-dependent probes require ticket01 validated descriptor; missing material is an open assumption gate, malformed material fails. |

API handoff for 09–13:

| API / record | Contract |
|---|---|
| `RunStore.start(action, language, provider, Target.local(context))` | Save explicit ordinary Start before preparation. Actions: translate/remove/first_setup/redownload. Local device binding uses Android secure app-scoped device id; only primary user 0 and fixed game package. Existing unresolved actions/recovery refuse new Start. Ordinary intent does not expire and grants no destructive consent. |
| `load(id)`, `pending()` → `Run` | Strict read, no status fallback. `Run` exposes exact target/action/language/provider/sessionId/authorizationKey/preparation/inputIdentity/attempts/Stop/lifecycle. Store schema1; bounded at 16 MiB including full input identity; at most 1024 records/64 operation budgets. Unknown provider/schema/extra fields or malformed scalar types refuse. Canonical digests detect accidental/tampered changes, not an adversarial app-private writer capable of rewriting every digest. |
| `RunStore.coordinator(context) { ... }` | One kernel-backed `sessions/coordinator.lock`. Thread-scoped ownership permits nested existing coordinator callbacks without reopening the same OS lock. Normal lock order: coordinator → runs/store.lock; store-only load/Stop/attempt updates never reverse-acquire coordinator. Setup/coordinator exclusive helpers share it. |
| `beginAttempt(id, operation)` | Persist initial + at most one automatic retry for a logical operation before dispatch. Service calls preparation after access is connected; coordinator calls dispatch before work. Reopen does not reset counts. Waiting/access is not an attempt. Explicit safe retry rearming and operation-specific failure/wait classification remain 10/11. Never apply this budget as uninstall permission. |
| `stop(id)` | Store-only short lock; atomically continuation=false/stop_requested=true before acknowledging Stop. Does not block behind long coordinator work. Read/write failure means no Stop acknowledgement. Existing checkpoints consult saved state; full lifecycle/reconnect/notification wiring remains 11/13. |
| `PatchRequestStore.authorize(runId, prepared)`, `authorizeRoot(runId, prepared)` | Bind only exact private preparation plus receipt hash/full APK identities. Shell signature conversion refuses. Rebinding is allowed only to identical material before claim. No ordinary checkbox Boolean or 15-minute deadline. |
| `claimRun(id, action, provider)` | Caller holds shared coordinator ownership. Revalidates saved receipt and independent full APKs, then durable `claimed` lifecycle. Does NOT consume/drop the request. Run id equals stable session id; root/nonroot and exact providers remain distinct. |
| `PatchCoordinator.dispatch(id, action, provider)` | Owns shared lock across claim and existing run/journal creation. Missing child resumes same id; existing linked child returns terminal result or recovery_required attachment without fresh mutation. Schema-2 creation uses `SessionJournal.create(..., runId, authorizationKey)`. Ordinary run()/runRoot() cannot mutate without private dispatch authority. New destructive first_setup/redownload dispatch refuses pending 11/12 scoped integration. |
| `bindInputs(id, identity)` / `Run.inputIdentity` | Before claim, persist full canonical current target/request input identity, exact-target checked and immutable once bound. Null means not yet measured, never reuse permission. Ticket09/10 must construct complete source/snapshot/producer/delta/readiness identity and bind it before their stages; no fake identity or summary-derived permission. Snapshot/checkpoint publication remains 09. |
| `PatchWorkerService.dispatchRun(context,intent)` | Pure pre-busy lookup/validation seam. prepare requires run; patch/remove/redownload requires request matching action. Schema2 recovery resolves exact provider through correlated journal/run and permits safety recovery after Stop. Legacy recovery remains old justified safety path; invalid records never fall back to current picker. |
| `resolve(id)` | Coordinator first; requires no pending setup/session/emergency recovery. Existing linked terminal child/auth key must match. Cancelled child requires Stop; missing claimed child refuses attention. No-child authorized/prepared Stop may resolve. Never infer safety from status or automatically treat recovered_unconfirmed as complete. |

Open integration boundaries: 10 owns discovery/continuation routing and recovering a cancelled/unconfirmed child into later safe work; this ticket deliberately attaches/refuses rather than duplicating it. 11 owns explicit safe retry rearming, provider waits, setup request/parent run/journal linkage, durable idle Stop and complete stopped-state resolution. During official-signature conversion, the parent ordinary translate intent already exists, but its preparation is NOT ordinary-authorized; the old explicit one-use data-loss/Scan-to-login consent remains necessary. Existing setup APIs are still separate and must be linked by 11 before combined release; an ordinary intent never substitutes for consent. 12 owns exact destructive-plan consent and its one-use outcome/reconciliation; until then new redownload dispatch and automatic damaged-file fallback safely pause. 13 removes routine dialogs and updates shared copy; no passing true to old confirm methods was introduced.

Pass-2 concerns: actual Android fsync/AtomicFile crash behavior and shared OS lock contention need the authored probes, not compile evidence; private APK probes copy potentially large validated files and need storage. Legacy refusal probes intentionally cannot exercise new mutation without Start; full fixture probes now use real durable APIs. No coverage count changes or speed claims.


Final post-edit compile (including shared FirstSetup lock helper, saved-provider recovery linkage, strict readers and all newly authored probes): `android/gradlew.bat -p android --offline :app:compileDebugKotlin :app:compileDebugUnitTestKotlin :app:compileDebugAndroidTestJavaWithJavac` **passed**, BUILD SUCCESSFUL in 23s (37 tasks; 6 executed). Only existing/deprecated Android API notices. No test task ran. Final `git diff --check` passed; no behavior/device evidence claimed.

Coordinator review: inspected authorization/claim/service/lock/readers and fixture migration against architecture; requested corrections received. Final diff whitespace passed. Advance09 on implemented interfaces; acceptance stays pending. Integration note for10: full snapshot identity becomes available after claim, so bindInputs lifecycle/API needs a safe measured-stage linkage extension; never fabricate pre-snapshot input evidence or alter saved target/action/provider.

Pass 2 instrumentation (2026-11-12): `RunStoreProbeTest.invalidationNeedsAConsistentLinkedJournal` used the non-file write path `packages/1` (correctly refused by `GameFilePolicy`); now `packages/1/1.db`. New `privateRootTrustsOnlyThePlatformAlias` covers the trusted-root fix recorded in 02. RunStore probes all pass.
