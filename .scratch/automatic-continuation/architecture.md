# Durable continuation contract

This is the implementation contract for tickets 02–18. The checkpoints below are logical names; map Android's existing phases to them while retaining old journal readers. Use the existing Android coordinator/file transaction rather than replacing it wholesale.

## 1. Records and ownership

Keep authorization separate from low-level mutation outcomes. One run owns both, with explicit references; neither may contradict the other. UI/status is a projection, never an independent authority.

| Record | Required fields / meaning |
|---|---|
| Run intent | Schema, UUID, requested action (`translate`, `remove`, `first_setup`, `redownload`), language, exact provider key, device/Android-user target, user-chosen work root, authorization timestamp and source, lifecycle, continuation enabled, active child operation/session ids. Save before preparation starts. |
| Consent | Kind, approved input identity, exact consequence/deletion-plan digest, approval id/time, consumed outcome. A destructive approval belongs to one attempt, not every future run. Ordinary Start authorization has no checkbox-derived Boolean or 15-minute resume expiry. |
| Mutation journal | Operation id/kind/target, expected before/after identity, durable intent, observed outcome, next safe recovery step. Reuse Android SessionJournal and FirstSetupJournal. |
| Checkpoint receipt | Schema, run/session id, stage, complete input key, exact artifact set, sizes/hashes, summary/delta/manifest digests, producer identity and committed marker. Publish atomically only after verification. |
| Retry state | Logical operation key, failures/attempts, last failure class, budget exhausted, waiting reason. Persist before dispatch; distinguish an attempt from waiting for access. |
| Completion receipt | Final input/translation identity, expected installed-file manifest, installed APK identity, delta/finalization digests, result/counts and verified outcome. Created only after FINALIZED. |

### Storage and locks

| Platform | Implementation boundary |
|---|---|
| Windows | New `app/patch_session.py` owns bounded/validated JSON, atomic writes, session discovery and locks. Run state lives under the chosen work root's session directory. A small registry under the existing app settings directory indexes unfinished work roots, including after a folder change/restart. Write registry before starting mutation; verify referenced run data instead of trusting the index. |
| Windows device | Persist selected ADB serial plus Android user/package target. Bind every command with `-s`; use target checks before mutation. One OS-backed work-root lock plus one per-device lock in the stable app-state directory prevents different windows/folders from mutating the same phone. Kernel/file locks, not PID files alone, own live work. |
| Android | New `RunStore.kt` owns durable authorization/discovery; link SessionJournal/FirstSetupJournal by id. Existing `sessions/coordinator.lock` serializes claim/dispatch/setup/recovery. Keep claim-lock order consistent; prefer coordinator lock first, then request/run store. Service busy flags remain UI aids. |
| Both | Keep Android `GameFileLock` semantics for game-file scripts, and use equivalent locking for Windows device writes. Preserve descriptor inheritance so a child still writing holds the lock if its parent disappears. Never break an unknown live lock because a timeout elapsed. |

One run cannot retarget itself to a different phone, provider, language or action. Work-folder/provider/language controls stay locked until Stop safely resolves the old action. Different settings on a later explicit Start create a new run and use only identity-compatible cached work. No cross-patcher pending-run/delta import. Simultaneous Windows/Android patching is unsupported; refuse a detected foreign owner rather than stealing it.

### Durability and malformed state

Use `AtomicFile` plus fsync/directory sync/read-back on Android. Reuse `pristine_delta.write_atomic` where suitable on Windows, under exclusive ownership; ensure durability for directory publication/replacement on the supported filesystem. Required journal write failures stop before the associated mutation. Bound JSON sizes/counts; reject unsupported schemas, traversal, symlinks/reparse-point escapes, duplicate/conflicting identities and wrong target/action/provider. Keep corrupt records/material for diagnosis; never delete them and pretend the phone is pristine.

Windows recovery discovery runs before fresh-run free-space and installed-game checks. Recovery-only work budgets the actual install/rollback/temp space it needs, not a full fresh build. Missing work drive, unavailable device, unknown installed identity or multiple unresolved candidates becomes Waiting for you/Recovery needs attention; never pick one arbitrarily.

## 2. Content identity

`input_key = SHA256(canonical JSON(identity))`: UTF-8, sorted keys, stable separators, sorted file paths, normalized relative separators, no mtime/absolute-path-only identities. Version this format. Identity records consumed bytes, not merely version labels.

| Component | Included evidence |
|---|---|
| Target | Package, Android user, serial/device binding, provider/access kind |
| Request | Action, language, fit-only/cycle-asset options and every output-affecting flag |
| Game | Complete source package manifest (paths/lengths/SHA-256) and relevant update/readiness evidence; source APK/prime-layer identity |
| APKs | Installed source, prepared normal/access and expected final installed identity; bytes, package/version, signer and debug flag |
| Delta | Actual delta and staged-record hashes, schema, associated asset-body content; missing delta is explicit |
| Translation | Runtime bytecode; all consumed shared tools/app transformation code; selected catalog plus English fallback edits; sprite labels/restores and other consumed payloads; configuration/allowlist changes |
| Executable semantics | Android bridge and app/coordinator build identity, ABI and native codec/library identities; Windows source/frozen application and Python/native dependency identities |

A conservative full installed patcher/build content digest may cover executable semantics. Android engine-manifest digest is one component, not the whole key. Include packaged library/code fingerprints at build time; source runs must reflect modified local modules without a release-version bump. If complete identity is unavailable, do ordinary verified work and decline cache reuse.

Recovery from already saved pristine/original bytes and normal APK must not require loading a new Python engine. An engine/app upgrade invalidates translation reuse, not the ability to restore known bytes safely. Treat incompatible journal readers as a blocking recovery problem rather than guessing fields.

## 3. Checkpoints and dispatch

| Checkpoint / interruption | Verification on return | Next action |
|---|---|---|
| Intent only / preparation incomplete | Target, ownership, consent, any prepared receipts | Resume/restart preparation. No install from partial APK output. |
| First uninstall/install intent | Installed source/normal/absence and pinned normal material | Missing game: install/verify saved normal. Normal present: record outcome. Original present after ambiguous uninstall: pause for fresh consent. Different identity: refuse. |
| Waiting for game update | Expected installed APK, download/readiness observations | Show Downloads finished only where needed; validate/close game before snapshot. No translation write during update. |
| Snapshot incomplete | Target and APK/access state; no valid snapshot receipt | Remove only that owned incomplete attempt; restart snapshot. Keep prepared APKs and authorization. |
| SNAPSHOT_READY | Exact retained snapshot set/hashes and current game/source inputs | Reuse snapshot if compatible. Changed live input invalidates snapshot/build, after safety recovery. |
| Build incomplete | Retained snapshot receipt and attempt ownership | Restart build in fresh attempt workspace; retain snapshot/APKs. Do not use a summary or partially staged package. |
| STAGED | Complete build receipt, output hashes/set, summary and delta, current source compatibility | Reuse output; avoid snapshot transfer/build repeat. Install access only if needed. |
| Apply incomplete | Original/staged manifests, mutation intent, live before/after file state | Reconcile temp/commit-before-ack; preserve rollback of incomplete Android apply. Restore complete pre-action bytes, then continue using valid STAGED output. Windows uses the same conservative rollback-before-reapply rule. |
| PAYLOAD_VERIFIED; final install unfinished | Full intended layer/read-back, normal/root APK identity | Finish normal APK restoration, no rebuild/rewrite. Unknown successful install is audited before retry. |
| NORMAL_VERIFIED; finalization unfinished | Layer identity, correct old/pending delta and ownership | Complete idempotent delta promotion/removal and receipt publication. Never report complete prematurely. |
| FINALIZED | Complete success receipt still matches current reality | Show result or reuse via ticket 16. If changed, invalidate success reuse and run safe new work. |
| Stop requested | Saved stop intent and unresolved mutations | Restore consistency, finalize safe state, mark cancelled; keep valid reusable artifacts. No automatic patch continuation. |
| Recovered unconfirmed | Old payload was verified, later live state differs | Preserve old unconfirmed result; establish a fresh safe source and continue under saved action, or pause if pristine/readiness cannot be established. |

Discovery first attaches to an existing matching live worker. If no worker owns the lock, claim the saved run and reconcile its journal. A restart/reconnect cannot launch a second coordinator, reset Stop, grant consent, or reset retry counters. Idle startup with no durable authorization performs no game mutation. Legacy pending sessions may perform only safety recovery justified by their existing records; they gain no new automatic patch authorization. Unknown outcomes always reconcile before any retry.

## 4. Snapshots, staging and invalidation

| Artifact | Publication | Reuse / invalidation |
|---|---|---|
| Prepared APKs | Verified immutable APKs + identities; pin referenced files against cache replacement | Reuse only for matching source/content/signature/manifest options. Never promote/cache access APK as normal. |
| Snapshot | Verify full file set; manifest + receipt committed last | Hash retained files after restart and compare current source evidence before mutation. Interrupted transport restarts. |
| Pristine build input | Separate copy/reconstructed input, explicitly related to snapshot/delta | Never overwrite the snapshot used for rollback, including through a shared writable hard link. Recompute if game/delta identity changes. |
| Staged build | Fresh attempt; finish all passes, restored-but-unstaged files, summary, final hashes and delta; verify then publish receipt last | Build changes invalidate stage only; source changes invalidate snapshot/stage. No partial-package checkpoint. |
| Recovery originals | Actual pre-action installed bytes, including previous translation; Watchdog where touched | Retain until file consistency and all mutation/finalization outcomes are durable. Never substitute pristine reconstruction. |
| Mixed-package decisions | Validated result bound to snapshot/delta/engine | Session-only reuse; changed inputs or restart require fresh proof. See ticket 17. |

Use a separate `build-receipt.json` beside existing pipeline outputs; do not change `device_patch_summary.json`'s staging contract just to add workflow metadata. Add shared Python helpers in `tools/run_artifacts.py` for canonical identities, stage publication/validation and attempt ownership. Existing `build_patch` remains the fresh-build primitive. Windows wraps its final outputs; Android publishes after bridge-specific finalization. Android reset logic removes only incomplete attempt-owned build data, preserving snapshot, rollback material, prior committed output and consent.

Every artifact reuse check has a trust scope: after restart rehash required retained bytes and reconcile live inputs; within one invocation reuse an immutable verified descriptor until a mutation changes it. Never use a language/version/size/timestamp match alone to skip restore/build. A changed engine keeps a usable snapshot if current game identity still matches; a changed game/APK requires a new appropriate snapshot/preparation. Always restore/inspect safety-critical in-flight work using its saved identities before adopting new inputs.

## 5. File writes and finalization

Windows new `app/device_transaction.py` owns the file protocol; `Patcher` calls it. Android extends GameFileTransaction. The exact expected final manifest contains unchanged originals plus ALL intended outputs, including restored files and identical-write skips.

1. Verify recovery material and source file identity. Reserve one full temp-file allocation plus remaining normal-install/rollback reserve.
2. Persist per-file intent (target, expected old/new hash/length, session temp name).
3. Copy to a session-specific temp in the destination directory; verify temp bytes/length and sync. Reject unsafe paths/links. Windows host-to-device upload staging is separate from live destination.
4. Rename within the destination filesystem, sync parent, read back live bytes/length, then durably acknowledge the commit. A reply alone does not establish the live hash.
5. On interruption classify live target as before, after, absent or other; reconcile a valid committed outcome or rollback from verified pre-action bytes. Unexpected external bytes pause instead of being overwritten blindly. Clear only this session's temps under the game lock.
6. Clear/restore Watchdog as a journalled operation with preserved pre-action contents where rollback needs them. Validate complete applied/restored layer.
7. Persist PAYLOAD_VERIFIED. Verify the installed normal APK (or root APK unchanged). Reconcile uncertain installer outcomes before reinstalling.
8. Idempotently promote the correct pristine delta, or durably remove it for verified Remove. Keep old/pending/material references until finalization is crash-safe. Publish FINALIZED/completion receipt last.

Per-file rename is atomic; a whole layer is not. Preserve rollback across between-file interruptions and interrupted rollback. If current files show a new game update, apply the existing pristine/mixed-package safety rules rather than rolling an old snapshot over that update.

## 6. Retry, Stop and Close

| Situation | Policy |
|---|---|
| Transient eligible operation | Initial attempt + one automatic retry total for the same logical operation. Persist attempts before sending. Reconcile before retry. |
| Same error after restart/reconnect | Budget remains exhausted. Show one cause/fix and Retry. User Retry re-arms only safe idempotent work; destructive work still needs scoped consent. |
| Waiting for OS/provider/download/storage | Not an attempt loop. Subscribe/poll with bounded backoff while open; state stays Waiting for you. No automatic permission grant. |
| Uninstall uncertainty | No automatic second uninstall. Fresh explicit destructive approval is a new attempt scope. |
| Stop safely | Durable `continuation=false`, `stop_requested=true` first. Immediate Stopping safely feedback; disable repeated Stop. Cancel pending UI waits, reach operation boundary, restore files/APK and stay cancelled. |
| Windows Close | Record close-preserves-continuation first; finish current indivisible work or safely abort its attempt, perform feasible cleanup/normal restore, then close. Keep UI responsive. If disconnected, persist unresolved state so next reopen recovers. |
| Android leave screen | Do not equate Activity onStop/onDestroy with Stop safely. Foreground service can continue; force-stop/process death is recovered on reopen. |

Keep Windows worker non-daemon with cooperative cancellation and bounded child-process handling. Do not kill all ADB processes/server as routine Close. If forced termination occurs at any point, saved intent determines recovery on next reopen. Surface operation detail and bytes only when measured; build/install with no known total uses an honest indeterminate state.

## 7. Retention and migration

Unresolved actions pin their APKs, snapshot/originals, staged output, manifests, old/pending deltas and journals. Cleanup may delete attempt-local scratch after its output checkpoint commits; it may not delete files still referenced for continuation/recovery. Keep the newest reusable resolved session per device target; do not automatically retain every historic multi-GB snapshot or a separate bulk cache for every language/provider. Include retained cache in storage estimates and offer explicit Free up space if needed. Per the player's 2026-11-12 preference, an Android coordinator budget that measures insufficient space may also release optional resolved cache, including the newest, under its lock. Invalidate receipts durably before bulk deletion, preserve current and unresolved references (including a completed-output source being copied), then remeasure the same budget once and continue the same operation if it fits. Remaining shortage stays a measured storage wait without spending retry attempts or reinstalling in a loop. Unknown/corrupt authorization prevents cleanup. This does not clear app cache generally, saved APKs, game data or the active pristine delta. Free up space uses the same receipt invalidation and recovery exclusions. A later explicit Start may reuse a stopped action's compatible content under a new authorization id.

Legacy data has three cases: valid old journal → existing justified safety recovery; incomplete artifacts with no approval → inert cache or attention, never auto-apply; corrupt/unknown records → attention with logs, no destructive fallback. Migrate metadata without editing the actual delta/catalog/package format. Test old Android phases including NORMAL_RESTORED_FOR_BUILD/APPLY_ACCESS_INSTALLED, and existing Windows pending deltas/changed-only sessions.
