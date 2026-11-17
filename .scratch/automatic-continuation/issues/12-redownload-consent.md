# 12: Require exact consent for Re-download deletion

Status: ready-for-agent
Implementation: complete
Verification: pending
Blocked by: 09, 10, 11

## Scope and files

Own damaged-file fallback in `PatchCoordinator.kt`, scoped request storage in `RunStore.kt`, `MainActivity.kt:showRedownloadConfirmation`, bridge plan/decision handoff and related probes. Read update-stuck-redownload/asset-restore features, ADRs 0002/0008 and architecture consent/transition rules. Do not add Windows Re-download.

## Steps

1. Replace automatic build-refusal→deletion with plan→Waiting for you unless a stored explicit approval covers the exact current plan/consequences.
2. Bind approval to snapshot/delta/engine identity, exact package/file set and hashes, planned Watchdog change and stated re-download/login/data consequences. Ordinary Start alone does not approve damaged-file deletion.
3. Persist approved plan and deletion intents before mutation. Reconcile absent/already-deleted files and unknown replies; changed/expanded plan requires new approval. An unexplained missing file is not automatically an approved deletion.
4. Continue an interrupted approved Re-download without another routine dialog if scope still matches. Keep normal/root APK verification, rollback where supported, update readiness and full retained pristine knowledge intact.
5. Preserve parent translation intent across the required game-download step. Force-stop/verify/readiness check before new snapshot/translation; do not translate incomplete downloads.
6. Make consent refusal/cancel deterministic: no deletion and no endless re-prompt loop. Recovery of an already-mutated plan remains available even if continuation is stopped.

## Acceptance

- [ ] Build refusal alone performs zero package deletion.
- [ ] Exact approval is resumable across process death; new/changed package scope pauses again.
- [ ] Delete committed before lost reply is reconciled; unknown files are not silently deleted.
- [ ] No silent game data clear or repeated destructive setup is introduced.
- [ ] Approved Re-download→download wait→translation resumes the original authorized action safely.

## Checks and handoff

Extend coordinator/request/route/removal recovery probes and affected bridge update/asset-restore checks; run UI-string and Android unit/build checks. Count actual deletes, prompts and installs for rejection, same-plan resume and changed-plan cases. Live package deletion/download is a ticket 19 consented gate.

## Stop condition

If the exact deletion plan cannot be bound to current verified inputs, show the consequences and wait. Do not restore checkbox convenience by granting all confirmation booleans.

## Comments

### Pass 1 (2026-11-12): implemented, compiled, not run

**Changed files**

- `android/app/src/main/java/dev/halixm/hokacepatcher/PatchCoordinator.kt`:
  - `redownloadLocked` is gone. In its place: `planRedownload`, `requirePlanScope`, `writeRecord`, `savedPlan`, `pinRedownload`/`offerRedownload`, `pinnedPlanHolds`, `redownloadStage`, `waitingStep`, `waitingResult` and `awaitUser`.
  - `continueLocked(..., redownload)` runs the approved stage after the snapshot is revalidated.
  - The catch returns `status: waiting` for a `WaitingForUser` once the run is consistent (rolled back, normal APK verified, `CANCELLED`).
  - New constants: `REDOWNLOAD_DOWNLOAD` and `REDOWNLOAD_CONSEQUENCES`. `releaseSession` also frees `redownload-plans`.
- `RunStore.kt`:
  - New `Run.redownload` / `Redownload` record (states `awaiting_consent`, `declined`, `approved`, `deleting`, `deleted`, `downloads_confirmed`), strictly validated.
  - New methods: `proposeRedownload`, `approveRedownload`, `declineRedownload`, `redownloadProgress`, `requireFreshRedownloadConsent`, `confirmRedownloadDownloads`.
  - `redownload_delete` is never re-armed.
- `SessionJournal.kt`:
  - New `redownloadPlanRoot`. `resultRoot` resolves to the build attempt, then the pinned plan, then the session.
  - New record keys `redownload_plan`, `redownload_plan_sha256`, `redownloaded` and `redownload_kept`.
- `MainActivity.kt`:
  - The scoped `showRedownloadConfirmation(run)` has no checkbox. It shows the files, packages, size and consequences; Not now or dismissing it records a decline.
  - New `showRedownloadDownloads`, `reviewRedownload` and `redownloadWaits`. CONTINUE_RUN, launch, the `waiting` result and the home cards all handle the wait.
  - The `redownloading` flag, the `redownload` prepare path and its checkbox dialog are removed.
- `WorkerStatus.kt`: a `waiting` line.
- `android/app/src/main/python/android_bridge.py`:
  - `plan_redownload`/`_plan_redownload` take an optional plan folder.
  - New `redownload_plan` (exact files, Watchdog, delta and records), `redownload_evidence` and `NOTHING_TO_REDOWNLOAD`.
  - `keep_redownload` reads from the plan folder and returns the record's identity.
- `resources/ui/strings.json`: 13 new draft keys (en and id) for ticket 13:
  - `redownload_review_title`, `redownload_review_scope`, `redownload_review_consequences`.
  - `not_now`, `not_yet`, `review_redownload`, `downloads_finished`.
  - `redownload_waiting_title`, `redownload_waiting_body`, `redownload_declined_body`.
  - `redownload_download_title`, `redownload_download_body`, `redownload_plan_changed`.
- Probes (authored, not run):
  - `RunStoreProbeTest.kt`: 4 tests. Scoped digest, decline/approve, a changed plan replacing the answer, the consumed approval and deletion budget, Stop, malformed records.
  - `SessionPublicationProbeTest.java`: the pinned plan root and result root, and a traversal refusal.
  - `CoordinatorRecoveryProbeTest.java`: an interrupted deletion rolls back through the pinned plan and stays approved.
  - `AutomaticRouteProbeTest.java`: comment only.
- Docs: `docs/features/update-stuck-redownload.md` (Report, links, Design rows, Out of Scope, Verification). `asset-restore.md` is unchanged because its behavior did not change.

**Checks run**

- `gradlew -p android --offline :app:compileDebugKotlin :app:compileDebugUnitTestKotlin :app:compileDebugAndroidTestJavaWithJavac` (JDK 21): BUILD SUCCESSFUL.
- `.venv\Scripts\python.exe -m py_compile android/app/src/main/python/android_bridge.py` (Python 3.12.10): exit 0.
- `git diff --check`: exit 0. It printed only LF/CRLF warnings on files this ticket does not own.
- `tools/research/check_ui_strings.py`: no new findings. It still reports the existing RunStore `*sha256` field names and the Windows app text. A new `plan_sha256` hit was avoided by not passing it through `text(...)`.
- Nothing was run on a device. No unit tests, instrumentation or offline bridge runs.

**Concerns**

- An interrupted deletion is reconciled by rollback, then a resume of the same approved plan. It is not finished forward. A cut after `finishDeletion` but before the `redownloaded` record is reconciled the same way: the session is no longer dirty, so the resume replans against a changed layer. The snapshot is retaken, the digest changes and a new approval is asked. That is safe but asks twice. A forward-reconciliation seam is left in `waitingStep`.
- `pinnedPlanHolds` allows exactly one change during a resume: this plan's own `redownload.json` (identity saved as `redownload_kept`), with `restore-refused.json` absent. Everything else must match byte for byte.
- If the plan cannot be measured, the ordinary damaged-files refusal stays, with no wait and nothing offered. The old home card's Re-download button now means Start, which measures again.
- `bridge("redownload_plan")`, `redownload_evidence`, the keep_redownload return value and every UI path are unexercised. The research checks still call the 3-argument `plan_redownload`, which stays compatible.
- The legacy `redownload` worker action and the `run/runRoot(redownload=true)` parameters stay refused but are not deleted.

**Handoff seams**

- 13: unify the approval copy across patchers using the 13 draft keys above plus the existing `delete_and_redownload`. `REDOWNLOAD_CONSEQUENCES` codes map one-to-one onto the consequences text.
- 14–16: the `waiting` result (`reason`, `redownload{plan_sha256,state,files,packages,bytes}`) and `RunStore.Redownload.state` drive any notification or route work. Launch never prompts; a card asks.
- 17: `_plan_redownload` and `_mixed_packages` still decide independently of the build. Reuse goes in `planRedownload`/`redownload_plan`, keyed by the plan's snapshot, delta and engine binding.
- 18–19: `redownload_delete` budget and `requireFreshRedownloadConsent`. The `redownloaded` journal history (max 32) records each consumed plan digest.

Pass 2 instrumentation (2026-11-12): `SessionPublicationProbeTest.pinnedRedownloadPlanIsTheResultRootOnlyWhileNoBuildIsPinned` failed with `Private path alias` because the pinned plan folder sat under the raw `/data/user/0` files path; production `PatchCoordinator` had the same defect (see 02, `RunStore.privateRoot`). Now passes. Write intents in the publication probes used the non-file path `packages/1`, which `GameFilePolicy` correctly refuses; they now use `packages/1/1.db`.

Pass 2 device-cycle Re-download fix (2026-11-12, phone f15a72e, run 248572aa, scoped Re-download of package 1): **Downloads finished** was asked twice. The confirmed Re-download download (`downloads_confirmed`) continued the action, but `snapshotStage` then found the layer the deletion changed and waited on `source_download_required` after a full access install and normal restore (~3.5 min). `waitingStep` now records the confirmed answer as the source-download answer for the stale snapshot's manifest digest (`RunStore.confirmSourceDownloadsAfterRedownload`, granted only by `redownloadAnswersSourceDownloads`: run may continue, plan `downloads_confirmed`, and it is the plan the journal last recorded as deleted), before any access install. The snapshot is still retired and retaken, the build's `UPDATE_WAITING`/`DOWNLOAD_UNFINISHED` check still sends an unfinished download back to the download wait, and the answer is spent once (`consumeSourceDownloads`; `snapshotStage` also drops one the layer no longer needs). The dialog's confirmation (and the plan approval) now dispatch the saved action through `UiTaskRunner`'s `then`, after the gate clears, instead of landing on Continue saved work. Copy: the approval shows MB under 1 GB (`StorageBudget.freeSpaceLabel`) and no longer counts packages ("1 game packages"); a home app restart that freed under 100 MB reports nothing. Tests: `RedownloadSourceAnswerTest`, `SizeLabelTest`, `UiTaskRunnerTest` (JVM); `RunStoreProbeTest.aConfirmedRedownloadDownloadAnswersOnlyTheSnapshotItMadeStaleOnce` (authored, not run on a device). Not yet re-cycled on the phone.

User-directed flow change (2026-11-12): review scope and consequences now sit on the main card.
Delete and re-download approves the displayed run id/digest and starts directly; no confirmation
modal. The next card offers Open game and Downloads finished; the latter confirms and resumes
directly. Returning alone grants nothing. Changed scope is refused for another review. Existing
RunStore/worker consent and recovery guards stay in place. UI-only checks use a separate emulator
preview app id and synthetic private metadata; the affected Redmi remains unavailable.

Automatic Re-download (2026-11-13, user decision, reverses step 1 and the "Ordinary Start alone does not
approve" rule for Re-download only; first-setup consent is unchanged). The user chose fully automatic
deletion: a Start/automatic run whose build refuses over damaged packages (stuck update, mixed packages,
unreachable texture slot) deletes the planned files with no review card and no dialog, then waits for the
game's download and **Downloads finished** (still asked: a closed game and stable hashes cannot prove the
downloads complete), and continues the translation in the same run.

- `RunStore.proposeRedownload(..., automatic = true)` approves the plan in the same write as the proposal
  (approval `source: "automatic"`; the user's review saves `"user"`, and an approval without a source reads
  as the user's). `PatchCoordinator.awaitUser` pins and offers the plan, then throws `RedownloadApproved`;
  `continueLocked` catches it around `buildStage` and runs `redownloadStage` on the snapshot and access
  already verified in this run. Plan digest binding, `pinnedPlanHolds`, live-layer validation, intents,
  rollback, normal APK restore, pristine delta and the download wait are unchanged.
- A changed plan (`redownloadStage`) deletes nothing under the old approval: it is pinned, offered and
  approved again automatically.
- Loop guard, `RunStore.automaticRedownloadAllowed`: automatic approval only for an unanswered plan, with
  the `redownload_delete` budget unspent (under 2), and none of its packages in the run record's new
  `redownloaded_packages` (written by `redownloadProgress(..., deleted)`, whoever approved). Otherwise the
  plan waits under `redownload_consent_required` and the existing review card (now with
  `redownload_repeat_review` when a package repeats) is the manual option.
- An interrupted automatic deletion resumes from `waitingStep` without a dialog, as an approved plan did.
- Removed unused consent-only strings `redownload_waiting_title`, `redownload_waiting_body`,
  `redownload_declined_body`, `review_redownload`. `WorkerStatus`'s consent line now reads as the
  loop guard's review.
- Checks: JVM `testDebugUnitTest` (new `AutomaticRedownloadTest`), `assembleDebug` +
  `assembleDebugAndroidTest`, `check_ui_strings.py`. Probes updated (`RunStoreProbeTest` two new tests and
  a malformed source case, `CoordinatorRecoveryProbeTest` automatic approval), authored, not run on a
  device. No phone cycle yet for the automatic path.
