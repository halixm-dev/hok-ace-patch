# Automatic continuation in both patchers

Status: ready-for-agent

Design confirmed by the user on 2026-11-11 through grilling Q1–Q10. **Implementation is in progress in two passes; verification and release gates remain open.** All tickets belong to one combined release. Begin with [start-here.md](start-here.md).

## Problem

An interruption currently loses reusable work or needs manual recovery. The Windows patcher can report success while the access APK remains installed, and live copies can truncate game files. Both patchers must safely finish an already approved action, reuse valid completed work, remove routine patch confirmations, show useful progress and address remaining speed findings.

This packet replaces the temporary handoff at `C:/Users/M1n3r4I5/AppData/Local/Temp/hok-ace-auto-resume-handoff-2026-11-11.md`. That file is not needed to implement the plan. `AGENTS.md` and existing ADRs continue to apply.

## Implementation Decisions

### Confirmed product decisions

| ID | Decision |
|---|---|
| Q1 | Resume on reopen or reconnect while open. No OS startup tasks or Android boot services. |
| Q2 | Include translation, Remove translation, and unfinished first setup/Re-download approved for an exact scope. Ask before new first-setup data deletion. Re-download deletion is automatic by the user's decision of 2026-11-13: a Start/automatic run deletes the measured damaged package files without a review, at most once per package per run; a package still damaged after its own download waits for the user's review. |
| Q3 | One combined release. Implement safety before speed; keep an optimization only after verification. An investigation may conclude no safe improvement. |
| Q4 | Recover consistency after changed game/translation inputs, then automatically redo invalidated stages once update readiness is established. |
| Q5 | Windows Close preserves continuation intent, finishes feasible cleanup, then exits. Stop safely revokes continuation. Android backgrounding follows the foreground-service lifecycle. |
| Q6 | One automatic retry after the first failure of an eligible operation, then a persistent pause. Reopen does not reset the budget. Never automatically repeat uninstall. |
| Q7 | Update/game-closed instruction is inline at Start. No routine checkbox/dialog. Ask Downloads finished only when setup/incomplete downloads need it. |
| Q8 | Reuse complete checkpoints. Restart an unfinished snapshot/build; no resume inside tar streams, native codecs or half-built packages. |
| Q9 | Retain valid reusable work after Stop safely. A later explicit Start can reuse it; Free up space can remove optional resolved cache. Per the player's 2026-11-12 preference, Android also releases that optional cache when an exact measured budget fails, then remeasures once and continues the same operation if it fits. Required/current/referenced recovery work stays pinned; remaining shortage waits without a retry/install loop. |
| Q10a | Lock language/provider/action/work-folder choices during unfinished work. Stop safely resolves the old action before different settings start a new action. |
| Q10b | If uncertain setup finds the original game still installed, pause for fresh data-loss consent. Never repeat uninstall automatically. |
| Q10c | Keep recovered_unconfirmed as honest history. Attempt fresh safe validation/build under saved authorization; pause if pristine data cannot be established. |

### Completion rules

| Rule | Required result |
|---|---|
| Verified complete | Complete intended file set, normal APK (unchanged installed APK under Root), and correct finalized pristine delta all verified. |
| Unknown outcome | Reconcile actual installed/file identity before retrying. Missing acknowledgment proves neither success nor no change. |
| Safe data | Immutable pre-action phone bytes are separate from reconstructed pristine input. Preserve the delta's meaning and per-patcher ownership. |
| Authorization | Persist action/language/provider/device/consent before dispatch. UI/status/summary/startup is not authorization. |
| Destructive scope | First-setup consent covers exact verified inputs and consequences; new/larger setup deletion requires consent. Re-download (user decision 2026-11-13) is approved automatically, still bound to the exact verified plan; a changed plan is measured and approved again before anything is deleted, and a package already re-downloaded in the run is not deleted again without the user's review. |
| Readiness | Known unfinished updates block translation writes. Stable hashes and a closed process alone cannot prove every download complete. |
| Reuse | Revalidate retained artifacts after restart; reuse proofs within one unchanged invocation. |
| Retry | Persist attempts before dispatch. Pause on persistent failure, invalid records, missing material or new consent needs. |
| Retention | Pin every artifact needed by unfinished work. Low space does not authorize deleting required recovery files. |
| Cancellation | Persist Stop safely before acknowledging it. Finish safety recovery after repeated interruption; keep the patch stopped. |

### User-visible states

| State | Meaning | Primary action |
|---|---|---|
| Working | Fresh authorized work | Stop safely |
| Continuing | Reusing interrupted approved work | Stop safely |
| Stopping safely | Stop recorded; operation/cleanup finishing | Disabled stopping button |
| Restoring | Returning files/APK to consistency | Explain current operation |
| Waiting for you | Access, approval, download, storage or consent needed | One specific next action |
| Verified complete | Files/APK/finalization verified | Open game |
| Recovery needs attention | Safe recovery cannot be completed/proven | Patch button becomes the required recovery action |

In Recovery needs attention, reuse the existing main patch button: change its label and click handler to the specific required recovery action. Save log stays a separate secondary action. The main button cannot start a fresh patch while recovery is unresolved. Apply this behavior in both patchers.

`recovered_unconfirmed` is not Verified complete and cannot produce a success receipt. A new verified run may later complete; the old result remains unconfirmed. Withhold the ready-to-play Open game action while file consistency or normal APK restoration is unresolved. A safe download-wait screen may offer Open game to finish downloads after files/APK are verified consistent; it does not claim translation complete. A resolved Stop can return to safe idle without claiming the requested translation completed.

### Architecture and verification

- [architecture.md](architecture.md): records, transitions, reuse/invalidation and finalization.
- [validation.md](validation.md): commands, failure matrix and release evidence.
- [evidence.md](evidence.md): code facts, historical evidence and workspace cautions.
- [ADR 0010](../../docs/adr/0010-continue-the-authorized-action-from-verified-checkpoints.md): the durable-authorization/retention trade-off.

### Implementation order

Use numeric order. Every ticket specifies files, dependencies, steps, checks and stop conditions.

| Ticket | Work | Depends on |
|---|---|---|
| [01](issues/01-probes-and-fixtures.md) | Reproducible probes and realistic fake transports | — |
| [02](issues/02-artifact-identities.md) | Complete identities and committed artifact receipts | 01 |
| [03](issues/03-windows-run-state.md) | Windows journal, discovery, serial binding and locks | 01, 02 |
| [04](issues/04-windows-apk-and-setup.md) | Windows installed identity, blocking restoration and setup | 03 |
| [05](issues/05-windows-file-transaction.md) | Windows atomic writes, rollback material and delta finalization | 03, 04 |
| [06](issues/06-windows-continuation.md) | Windows checkpoint continuation/invalidation | 02, 04, 05 |
| [07](issues/07-windows-stop-and-close.md) | Windows stop/close and useful progress | 06 |
| [08](issues/08-android-run-authorization.md) | Android durable Start authorization and ownership | 01, 02 |
| [09](issues/09-bridge-checkpoints.md) | Bridge build publication/reuse and failed-attempt restart | 02, 08 |
| [10](issues/10-android-continuation.md) | Android dispatch, recovery and retention | 08, 09 |
| [11](issues/11-android-stop-and-setup.md) | Android Stop safely, setup and provider reconnect | 10 |
| [12](issues/12-redownload-consent.md) | Scoped consent for damaged-file deletion | 09, 10, 11 |
| [13](issues/13-shared-progress-and-copy.md) | Shared states, confirmation removal and EN/ID copy | 07, 11, 12 |
| [14](issues/14-android-write-and-hash-skips.md) | Android identical writes and same-call recovery hash reuse | 10, 11 |
| [15](issues/15-windows-signing-reuse.md) | Windows signed normal APK reuse | 04, 06 |
| [16](issues/16-verified-install-receipt.md) | Strong installed receipt to skip repeat staging | 02, 06, 10, 12, 14, 15 |
| [17](issues/17-mixed-package-decision-reuse.md) | Snapshot-scoped restore/classification reuse | 09, 12 |
| [18](issues/18-measured-staging-retries.md) | Measure retry copies; relocate proven failures | 02, 09 |
| [19](issues/19-release-verification-and-docs.md) | Combined release verification and feature records | 01–18 |

## Out of Scope

| Exclusion | Boundary |
|---|---|
| Work at boot | Reopen/reconnect only; no new startup tasks/boot services. |
| Fine-grained snapshot/build resume | Restart unfinished stage; retain completed checkpoints. |
| Removing integrity checks | Remove duplicates; retain consumer-boundary/post-write verification. |
| Automatic new deletion | Informed consent for new setup/data clear/deletion scope. |
| Windows update-repair feature | Preserve mixed-package refusal; asset restore/Re-download remains Android-only. |
| Transfer of pending actions | Bind each to its device/provider; never share pristine deltas between patchers. |
| Simultaneous patchers on one phone | One owning patcher; respect shared file locks/refuse known foreign ownership. Cross-host distributed coordination is outside scope. |
| Coverage expansion | Preserve catalog/allowlist/append/atlas gates and applied/skipped counts. |
| Additional APK changes | Normal APK remains manifest-only; preserve signing key. |

## Definition of done

| Gate | Evidence |
|---|---|
| Implementation | Tickets resolved with actual commands/results. An optimization declined on evidence records its measured reason. |
| Safety | No false success, repeated uninstall, overlapping local workers, missing writes or lost pristine delta in the failure matrix. |
| Reuse | Stage/transport call counts prove checkpoint reuse, invalidation and Stop remaining stopped. |
| Output | Same-input EN/ID hashes, normalized summaries, counts and skip lists preserve controls. |
| Device | Real interruption/reconnect gates for Windows and three Android providers. Unrun gates stay open and block a release claim. |
| Speed | Comparable observations support shortcuts. Historical 616–621 s is context, not a new benchmark/promise. |
| Delivery | One combined release; source/frozen Windows and built Android checked; affected docs reconciled. |

## Comments

2026-11-11: Planning only. Three read-only source investigations checked Windows, Android and shared-pipeline facts. No implementation, benchmarks, phone operations or commits. Preserve unrelated workspace changes.

Planning validation: `check_references.py` passed; `check_staging_contract.py` passed; packet-only static validation passed for all 24 Markdown files, 19 ordered tickets, local links, backward dependencies and required ticket sections; `git diff --check` passed. These validate documents, not implementation behavior. Implementation/device checks in validation.md remain unrun by this task.
