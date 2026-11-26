---
feature: automatic-continuation
status: built; Android Root and Wireless debugging phone-cycled; Windows and Shizuku real cycles skipped by the user
updated: 2026-11-19
branch: feat/automatic-continuation
---

# Automatic continuation in both patchers

## Report

### What landed

One combined release (`d1033eb` and the fixes after it on `feat/automatic-continuation`). Both patchers
save the player's exact approved action before any work, keep verified completed work, recover
consistency after an interruption and continue that action on reopen or reconnect
([ADR 0010](../adr/0010-continue-the-authorized-action-from-verified-checkpoints.md)).

- **Windows patcher:** `app/patch_session.py` (run record, discovery, locks, serial binding),
  `app/device_transaction.py` (temp, rename, read-back per file; rollback from pre-action bytes),
  checkpoint reuse of snapshot and staged output, a blocking normal-APK restoration, signed normal-APK
  reuse, Stop safely and a Close that preserves continuation.
- **Android patcher:** `RunStore` (durable Start authorization, retry budget per logical operation,
  Re-download consent), bridge checkpoints (`snapshot_checkpoint`, `build_checkpoint`, reset of an
  incomplete attempt, completed-output copy), continuation on reopen, Stop safely, first-setup and
  provider return, identical-write skips, measured-shortage cache release, automatic Re-download with
  a loop guard, and mixed-package decision reuse within one worker.
- **Shared:** `tools/run_artifacts.py` (canonical identities, stage publication and validation,
  attempt ownership, producer identity), the shared states and copy in both languages (`PRODUCT.md`,
  `DESIGN.md`), and the offline checks named below.

Coverage counts did not move: the same-input EN and ID outputs equal the baseline's.

### Verification

| Gate | Result |
|---|---|
| Offline Python checks (`check_windows_recovery`, `check_run_artifacts`, `check_bridge_continuation`, `check_windows_repatch`, `check_pristine_delta`, `check_mobile_snapshot`, staging faults, controls, signing) | Pass |
| `check_ui_strings`, `check_references`, `check_staging_contract` | Pass (re-run at promotion) |
| Android JVM unit tests, full-codec debug and instrumentation builds | Pass (161/161 at promotion) |
| EN/ID output parity on the 1.8.0.1 fixture, with and without the APK | Pass: staged hashes, normalized summaries, counts, skip lists and delta mappings equal |
| Changed engine/game controls (`check_changed_input_controls.py`) | Pass, offline 15/15: each change refused, rebuilds equal fresh builds |
| Windows Remove on real 1.8.0.1 packages, offline (`check_windows_remove.py`) | Pass: byte-identical to pristine |
| Frozen `build.bat`, `--selftest`, `--smoketest` | Pass: EN and ID staged bytes identical to the source run, 14/14 files each; smoke 12/12 |
| Source `run.bat` | Pass by the user's chosen check (2026-11-18): the source pipeline headless (`--smoketest` 12/12, `--selftest` EN 73 s and ID 62 s, both ok) plus the phone screens below; the Windows window itself was not opened |
| Real cycles, Wireless debugging (C2–C8, scoped and automatic Re-download, Remove, Stop) | Pass (2026-11-12 to 2026-11-13) |
| Real cycles, Root (build, apply, Stop, final-check interruptions, switches, Remove; zero installs, owner and SELinux kept) | Pass (2026-11-18) |
| Interrupted automatic Re-download and its loop guard, Root | Interrupted deletion pass; guard held only after three cuts, fixed, re-checked on the phone over a second real update: the count held across an automatic re-plan (`redownload_delete` 2 after one cut and the finished deletion), complete 398/318. Pass (one cut on the fixed build) |
| Fixture-gated probes | PatchRequest 2/2, CoordinatorRecovery 19/19, SourceGuard 1/1, ApkPreparation 1/1 pass; `FullCoordinatorProbeTest` skipped by the user (needs about 16 GB internal) |
| Phone screens over adb, both languages | Pass by the user's chosen check (2026-11-19): EN progress, Free up space, Re-download wait and result; the EN to ID switch's progress and result in Indonesian (run `10c70338`, 398/318); no idle-screen flash after *Downloads finished* |
| Real-update history (`check_update_redownload.py`) | Pass on the 2026-11-18 cycle's captures, which replace the missing 2026-10-23 ones by the user's decision: plans 1, 10, 15, 21 after the update, as the phone did; nothing after the downloads; the second plan reuses the mixed-package decision |
| Performance | Single runs on one phone only, by the user's decision; see [patch-speed](patch-speed.md) |
| Real cycles, Windows patcher over USB | Skipped by the user (2026-11-17) |
| Real cycles, Shizuku | Skipped by the user (2026-11-18) |
| Legacy schema-1 safety-only retries | Kept unchanged by the user's decision (2026-11-18) |

Raw evidence is under `D:/scratch/hok-ac-pass2/`, `D:/scratch/hok-ac-loopguard/` and
`D:/scratch/hok-ac-loopguard2/`; the [lab notebook](../lab-notebook.md)'s 2026-11-12 to 2026-11-18 entries
hold the numbers. The coordinator log, tickets 01–19 and the validation matrix are in git history at
the feature's scratch folder (removed by the promoting commit; see `git log -- .scratch`).

### Journey

- **Plan (2026-11-11):** grilling Q1–Q10 fixed the decisions in [S2]; 19 ordered tickets; one release.
- **Pass 1 (2026-11-11 to 2026-11-12):** one worker per ticket implemented 01–18 with compile-only
  checks; reviews corrected the retry budget to one per logical operation and moved recovery off the
  engine.
- **Pass 2 (2026-11-12 to 2026-11-18):** offline checks and parity, then phone cycles. Found and fixed on
  the way: the `/data/user/0` against `/data/data` private-path alias in `RunStore`, an idle Stop that did
  not resolve, a non-fatal checkpoint reset defect, the measured-shortage cache release (the player's
  2026-11-12 preference), the Windows source producer identity (non-ASCII research file names), APK-build
  capture in the controls tool, a legacy session whose rollback could not finish, and fixture-gated
  probe defects.
- **Re-download decision (2026-11-13):** the scoped review became an automatic approval bound to the
  exact measured plan, with a loop guard ([update-stuck-redownload](update-stuck-redownload.md)).
- **Loop guard on the phone (2026-11-18):** an automatic re-approval of a re-measured plan re-armed the
  deletion budget, so the guard took three interruptions; the count now survives an automatic
  re-approval. The same cycle showed the idle saved-work screen for 2 to 4 s after *Delete and
  re-download* and *Downloads finished*; `UiTaskRunner` now resumes before it refreshes.
- **Withdrawn or declined:** the staging retry proof shortcut stays unwired (no failed attempts measured);
  legacy schema-1 retries are not migrated; no resume inside a tar stream, codec or half-built package.

### Still owed

Real interruption cycles for the Windows patcher and Shizuku; `FullCoordinatorProbeTest` on a phone
with about 16 GB free; a comparable (repeated) performance measurement; the Windows window opened at
the enlarged-font and progress states; one phone and one root manager only; a second interruption of
one automatic Re-download approval on the fixed build (unit-tested only). A Stop that lands between
preparation and authorization now reads as a cancel (a checkpoint before `authorize`, and
`RunStore.bind` names its refusal); that path is compiled and unit-tested, not re-timed on a phone.

## [S1] Problem

An interruption lost reusable work or needed manual recovery. The Windows patcher could report success
while the access APK remained installed, and live copies could truncate game files. Both patchers had
to finish an already approved action safely, reuse valid completed work, drop routine patch
confirmations, show useful progress and address the remaining speed findings.

## [S2] Design

Design confirmed by the user on 2026-11-11 (grilling Q1–Q10); `AGENTS.md` and the earlier ADRs still apply.

### Product decisions

| ID | Decision |
|---|---|
| Q1 | Resume on reopen or reconnect while open. No OS startup tasks or Android boot services. |
| Q2 | Include translation, Remove translation, and unfinished first setup/Re-download approved for an exact scope. Ask before new first-setup data deletion. Re-download deletion is automatic by the user's decision of 2026-11-13: a Start/automatic run deletes the measured damaged package files without a review, at most once per package per run; a package still damaged after its own download, or a deletion interrupted twice, waits for the user's review. |
| Q3 | One combined release. Safety before speed; keep an optimization only after verification. An investigation may conclude no safe improvement. |
| Q4 | Recover consistency after changed game/translation inputs, then automatically redo invalidated stages once update readiness is established. |
| Q5 | Windows Close preserves continuation intent, finishes feasible cleanup, then exits. Stop safely revokes continuation. Android backgrounding follows the foreground-service lifecycle. |
| Q6 | One automatic retry after the first failure of an eligible operation, then a persistent pause. Reopen does not reset the budget. Never automatically repeat uninstall. |
| Q7 | The update/game-closed instruction is inline at Start. No routine checkbox/dialog. Ask Downloads finished only when setup or incomplete downloads need it. |
| Q8 | Reuse complete checkpoints. Restart an unfinished snapshot/build; no resume inside tar streams, native codecs or half-built packages. |
| Q9 | Retain valid reusable work after Stop safely. A later explicit Start can reuse it; Free up space can remove optional resolved cache. Per the player's 2026-11-12 preference, Android also releases that optional cache when an exact measured budget fails, then remeasures once and continues the same operation if it fits. Required/current/referenced recovery work stays pinned; remaining shortage waits without a retry/install loop. |
| Q10a | Lock language/provider/action/work-folder choices during unfinished work. Stop safely resolves the old action before different settings start a new action. |
| Q10b | If uncertain setup finds the original game still installed, pause for fresh data-loss consent. Never repeat uninstall automatically. |
| Q10c | Keep `recovered_unconfirmed` as honest history. Attempt fresh safe validation/build under saved authorization; pause if pristine data cannot be established. |

### Completion rules

| Rule | Required result |
|---|---|
| Verified complete | Complete intended file set, normal APK (unchanged installed APK under Root), and correct finalized pristine delta all verified. |
| Unknown outcome | Reconcile actual installed/file identity before retrying. A missing acknowledgment proves neither success nor no change. |
| Safe data | Immutable pre-action phone bytes are separate from reconstructed pristine input. Preserve the delta's meaning and per-patcher ownership. |
| Authorization | Persist action/language/provider/device/consent before dispatch. UI/status/summary/startup is not authorization. |
| Destructive scope | First-setup consent covers exact verified inputs and consequences; new or larger setup deletion requires consent. Re-download is approved automatically, still bound to the exact verified plan; a changed plan is measured and approved again before anything is deleted, an automatic re-approval keeps the run's deletion count, and a package already re-downloaded in the run is not deleted again without the user's review. |
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

In Recovery needs attention the main patch button changes its label and handler to the specific
required recovery action; Save log stays a separate secondary action, and the button cannot start a
fresh patch while recovery is unresolved. Both patchers. `recovered_unconfirmed` is not Verified
complete and produces no success receipt. Open game is withheld while file consistency or normal APK
restoration is unresolved; a safe download-wait screen may offer Open game to finish downloads once
files/APK are verified consistent, without claiming the translation complete. A resolved Stop returns
to safe idle without claiming the requested translation completed.

### Records and ownership

Authorization is kept separate from low-level mutation outcomes. One run owns both, with explicit
references; neither may contradict the other. UI/status is a projection, never an independent authority.

| Record | Fields and meaning |
|---|---|
| Run intent | Schema, UUID, requested action (`translate`, `remove`, `first_setup`, `redownload`), language, exact provider key, device/Android-user target, work root, authorization time and source, lifecycle, continuation enabled, active child operation/session ids. Saved before preparation starts. |
| Consent | Kind, approved input identity, exact consequence/deletion-plan digest, approval id/time and source, consumed outcome. A destructive approval belongs to one attempt. Ordinary Start authorization has no checkbox Boolean and no resume expiry. |
| Mutation journal | Operation id/kind/target, expected before/after identity, durable intent, observed outcome, next safe recovery step (Android `SessionJournal`, `FirstSetupJournal`). |
| Checkpoint receipt | Schema, run/session id, stage, complete input key, exact artifact set, sizes/hashes, summary/delta/manifest digests, producer identity and committed marker; published atomically only after verification. |
| Retry state | Logical operation key, attempts, last failure class, budget exhausted, waiting reason; persisted before dispatch. An attempt is distinct from waiting for access. |
| Completion receipt | Final input/translation identity, expected installed-file manifest, installed APK identity, delta/finalization digests, result/counts and verified outcome; created only after FINALIZED. |

| Platform | Storage and locks |
|---|---|
| Windows | `app/patch_session.py` owns bounded, validated JSON, atomic writes, discovery and locks. Run state lives under the work root's session directory; a small registry under the app settings directory indexes unfinished work roots and is verified against the run data, never trusted alone. |
| Windows device | The ADB serial plus Android user/package target is saved and every command bound with `-s`. One OS-backed work-root lock and one per-device lock keep different windows or folders from mutating the same phone. |
| Android | `RunStore` owns durable authorization and discovery and links `SessionJournal`/`FirstSetupJournal` by id. `sessions/coordinator.lock` serializes claim, dispatch, setup and recovery (coordinator lock first, then the run store). Service busy flags are UI aids. |
| Both | `GameFileLock` semantics for game-file scripts, with descriptor inheritance so a child still writing holds the lock; an unknown live lock is never broken on a timeout. |

On Windows, a USB copy that differs from a stable phone checksum is a retryable read failure.
If the phone's APK path or checksum changes during the read, recovery requires a new verification.

A run never retargets itself to a different phone, provider, language or action. Different settings on
a later explicit Start create a new run and use only identity-compatible cached work. No cross-patcher
pending-run or delta import. Records are bounded; unsupported schemas, traversal, links, duplicate
identities and wrong targets are refused, and corrupt records are kept for diagnosis, never deleted as
if the phone were pristine. Windows recovery discovery runs before the fresh-run space and game checks,
and recovery budgets only the space it needs.

### Content identity

`input_key = SHA256(canonical JSON(identity))`: UTF-8, sorted keys, stable separators, sorted
normalized relative paths, no mtimes, versioned. Identity records consumed bytes, not version labels.

| Component | Included evidence |
|---|---|
| Target | Package, Android user, serial/device binding, provider/access kind |
| Request | Action, language, fit-only/cycle-asset options and every output-affecting flag |
| Game | Complete source package manifest (paths/lengths/SHA-256), update/readiness evidence, source APK/prime-layer identity |
| APKs | Installed source, prepared normal/access and expected final installed identity: bytes, package/version, signer, debug flag |
| Delta | Actual delta and staged-record hashes, schema, asset bodies; a missing delta is explicit |
| Translation | Runtime bytecode, consumed tools/app transformation code, selected catalog plus English fallback, sprite labels/restores and other payloads, configuration/allowlist |
| Executable semantics | Android bridge and app/coordinator build identity, ABI and native codec identities; Windows source/frozen application and Python/native dependency identities |

Without a complete identity the run does ordinary verified work and declines reuse. Recovery from
saved pristine/original bytes and the normal APK never needs a new Python engine: an engine upgrade
invalidates translation reuse, not the ability to restore known bytes.

### Checkpoints and dispatch

| Checkpoint / interruption | Verified on return | Next action |
|---|---|---|
| Intent only / preparation incomplete | Target, ownership, consent, prepared receipts | Resume or restart preparation; no install from partial APK output |
| First-setup uninstall/install intent | Installed source/normal/absence and pinned normal material | Missing game: install the saved normal APK. Original present after an ambiguous uninstall: pause for fresh consent. Different identity: refuse |
| Waiting for game update | Expected installed APK, readiness observations | Downloads finished only where needed; no translation write during an update |
| Snapshot incomplete | No valid snapshot receipt | Remove only that owned attempt; restart the snapshot, keeping APKs and authorization |
| SNAPSHOT_READY | Retained snapshot set/hashes against current inputs | Reuse if compatible; a changed live input invalidates snapshot and build after safety recovery |
| Build incomplete | Snapshot receipt, attempt ownership | Restart the build in a fresh attempt; never use a summary or partial package |
| STAGED | Build receipt, output set/hashes, summary, delta, source compatibility | Reuse the output; no snapshot transfer or rebuild |
| Apply incomplete | Original/staged manifests, mutation intent, live state | Reconcile temp/commit-before-ack; roll back to pre-action bytes, then continue from the valid STAGED output |
| PAYLOAD_VERIFIED, final install unfinished | Intended layer read-back, normal/root APK identity | Finish the normal APK restoration only; audit an unknown install before retrying |
| NORMAL_VERIFIED, finalization unfinished | Layer identity, old/pending delta and ownership | Idempotent delta promotion/removal and receipt publication |
| FINALIZED | Success receipt against current reality | Show the result, or reuse it; if reality changed, run safe new work |
| Stop requested | Saved stop intent, unresolved mutations | Restore consistency, mark cancelled, keep reusable artifacts; no automatic continuation |
| Recovered unconfirmed | Verified payload later changed | Keep the unconfirmed result; continue under the saved action from a fresh safe source, or pause |

Discovery attaches to a live matching worker first; with no lock owner it claims the saved run and
reconciles its journal. A restart cannot launch a second coordinator, reset Stop, grant consent or reset
retry counters. Idle startup with no durable authorization mutates nothing. Legacy pending sessions get
only the safety recovery their records justify.

### Snapshots, staging and invalidation

| Artifact | Publication | Reuse / invalidation |
|---|---|---|
| Prepared APKs | Verified immutable APKs and identities, pinned | Reuse only for matching source/content/signature/manifest options; the access APK is never cached as normal |
| Snapshot | Full file set verified; manifest and receipt committed last | Rehash after restart and compare current source evidence; within one worker a file already hashed is rechecked by its stat signature (`run_artifacts.remember_verified`); an interrupted transport restarts |
| Pristine build input | Separate from the rollback snapshot | Never overwrites it, including through a shared hard link; recomputed when game or delta identity changes |
| Staged build | Fresh attempt; all passes, restored files, summary, hashes and delta, then `build-receipt.json` last | Build changes invalidate the stage; source changes invalidate snapshot and stage |
| Recovery originals | Actual pre-action bytes, including a previous translation, and Watchdog | Kept until consistency and every outcome are durable; never replaced by a pristine reconstruction |
| Mixed-package decisions | Bound to snapshot, delta and engine | Reused within one worker only ([asset-restore](asset-restore.md)) |

`device_patch_summary.json`'s staging contract is unchanged; workflow metadata lives in
`build-receipt.json`. `build_patch` stays the fresh-build primitive.

### File writes and finalization

The expected final manifest holds unchanged originals plus every intended output, restored files and
identical-write skips included.

1. Verify recovery material and source identity; reserve one temp file plus the install/rollback reserve.
2. Persist the per-file intent (target, expected old/new hash and length, session temp name).
3. Copy to a session temp in the destination directory; verify and sync it. Reject unsafe paths and links.
4. Rename, sync the parent, read the live bytes back, then acknowledge durably.
5. On interruption classify each target as before, after, absent or other; reconcile a committed outcome
   or roll back from verified pre-action bytes. Unexpected bytes pause instead of being overwritten.
6. Clear/restore Watchdog as a journalled operation; validate the complete layer.
7. Persist PAYLOAD_VERIFIED; verify the normal APK (Root: unchanged), reconciling uncertain installs first.
8. Promote the pristine delta, or remove it for a verified Remove; publish FINALIZED and the completion
   receipt last.

### Retry, Stop and Close

| Situation | Policy |
|---|---|
| Transient eligible operation | Initial attempt plus one automatic retry per logical operation, persisted before sending, reconciled before the retry |
| Same error after restart/reconnect | Budget stays exhausted; one cause, one fix and Retry. Retry re-arms only safe idempotent work |
| Waiting for OS/provider/download/storage | Not an attempt; Waiting for you, with bounded polling while open |
| Uninstall uncertainty | No automatic second uninstall; fresh explicit approval |
| Stop safely | Durable `continuation=false`, `stop_requested=true` first; immediate Stopping safely, repeated Stop disabled; restore files/APK and stay cancelled |
| Windows Close | Record close-preserves-continuation, finish or abort the current indivisible work, clean up and restore the normal APK, then close; ADB is not killed |
| Android leaving the screen | Not a Stop; the foreground service continues and a force-stop is recovered on reopen |

### Retention and migration

Unresolved actions pin their APKs, snapshot and originals, staged output, manifests, old/pending deltas
and journals. The newest reusable resolved session per device target is kept. Free up space and the
Android measured-shortage release invalidate receipts durably before bulk deletion, never touch current
or unresolved references, remeasure once and continue if the operation fits. Legacy data: a valid old
journal gets its safety recovery; incomplete artifacts with no approval stay inert; corrupt records ask
for attention with logs.

## [S3] Out of Scope

| Exclusion | Boundary |
|---|---|
| Work at boot | Reopen/reconnect only; no startup tasks or boot services |
| Fine-grained snapshot/build resume | Restart the unfinished stage; keep completed checkpoints |
| Removing integrity checks | Remove duplicates only; keep consumer-boundary and post-write verification |
| Automatic new deletion | Informed consent for new setup/data clear/deletion scope (Re-download excepted by the 2026-11-13 decision) |
| Windows update repair | The Windows patcher keeps its mixed-package refusal; asset restore and Re-download stay Android-only |
| Transfer of pending actions | Each is bound to its device and provider; pristine deltas are never shared between patchers |
| Simultaneous patchers on one phone | One owning patcher; a detected foreign owner is refused. Cross-host coordination is outside scope |
| Coverage expansion | Catalog, allowlist, append and atlas gates and the applied/skipped counts unchanged |
| Additional APK changes | The normal APK stays manifest-only; the signing key is unchanged |
