# 16: Skip repeat restore/build only with a complete success receipt

Status: ready-for-agent
Implementation: complete
Verification: pending
Blocked by: 02, 06, 10, 12, 14, 15

## Scope and files

Own completion-receipt integration in both coordinators, shared artifact helper, Android InstalledGameVerifier/CacheReuseProbeTest seams and Windows recovery/artifact probes. Read architecture sections 1–4/5 finalization. This shortcut is distinct from reusing STAGED after interruption.

## Steps

1. Publish an installation receipt only after verified payload, normal/root APK and idempotent delta finalization. Store the exact complete expected layer manifest, input key, translation identity, action/language and honest result/counts.
2. On explicit Start, validate actual installed APK and current relevant package hashes against the receipt before skipping pristine reconstruction/staging. A receipt alone does not attest the phone still has those bytes.
3. Include complete engine/catalog/English-fallback/sprite/bridge/native semantics, source/prime APK, options and pristine delta inputs. Language/version/size/mtime alone never qualify.
4. If provider access requires a temporary access install merely to validate live bytes, keep that verified access/normal cycle; advertise only the work actually skipped. Root still installs nothing.
5. Handle receipt invalidation after game/engine change, Remove, optional cleanup and damaged-file deletion. recovered_unconfirmed/cancelled/missing/incomplete receipts cannot authorize this no-op path.
6. Fall back to ordinary verified processing on a benign cache miss, or attention on unresolved mutation/corruption. Preserve complete counts/skipped reporting from the verified matching result.

## Acceptance

- [ ] Identical installed state skips restore/build after required actual-byte audit.
- [ ] Same-size changed game/APK/catalog/tool/bridge/codec, language/options or delta invalidates reuse.
- [ ] Forged/torn/stale/missing-file receipt and unconfirmed result cannot produce success.
- [ ] No-op still restores/verifies normal APK if access was needed, with no false Open game.

## Checks and handoff

Run artifact/Windows recovery probes, CacheReuseProbeTest, coordinator/route/installed verifier probes and unit/build checks. Assert skipped stage calls plus retained mandatory hashes/installs. Measure validation cost against saved work; retain the shortcut only with safe benefit.

## Stop condition

If current live inputs cannot be read or complete identity is missing, decline the shortcut. A no-op receipt is an optimization, not a replacement for authorization/recovery.

## Comments

Pass 1 implementation complete, 2026-11-12. Verification pending; every acceptance box remains unchecked. No behavioral/unit/instrumentation/performance/pipeline/UI-string/reference/staging script or game/ADB/device operation ran. No commit, publication, release or ticket 17/18 work.

| Files | Implementation |
|---|---|
| `app/patcher_core.py`, `app/windows_checkpoints.py`, `tools/run_artifacts.py` | Windows schema-2 completion proof adds original full identity, complete intended files, final metadata/classification identity, exact installed normal, complete result and APK lineage. Consumer requires independently finalized transaction, stage/result binding and resolved terminal retention proof; current source/prime APKs, source→normal unsigned inventories, producer/options/full live files and delta are re-read. A fresh owned result copy bypasses restore/build only; normal transaction audit/install/finalization remains. |
| `PatchCoordinator.kt`, `InstalledGameVerifier.kt`, Android `android_bridge.py` | Android complete receipt after audited payload/APK/metadata. Fresh Start independently validates old journal/terminal/preparation/source/prime/whole applied manifest and actual live bytes. Verified prior result copies into a new owned attempt with CURRENT input identity and separate exact old run/input/result lineage. Mandatory shell access/normal cycle remains; Root installs nothing. Original source identity is never fabricated from normalized bytes; exact equal full identities may share the same retained bytes. |
| `PristineDelta.kt`, `SessionJournal.kt` | STAGED seals expected old delta/record/classification and desired final record before writes, comparing complete build-input identities. Finalization seals/pins explicit old/absence/final identities and backup bytes, accepts only write-order-justified interrupted pairs, verifies BOTH active final records/absence and backups/intent even on finalized=true, and then returns read-only. New refusal/Re-download knowledge is not deleted. Required failed promotion cannot close unconfirmed/consistent or release material. |
| `RunStore.kt`, `ApkPreparation.kt` | Short durable completion/Stop linearization outside expensive hashing; late Stop after completed linearization cannot rewrite terminal history. Optional source cleanup preserves actual source bytes still needed by the newest completion proof/current preparation; bulk cleanup invalidates receipts before releasing bytes and unresolved runs remain pinned. |
| `check_run_artifacts.py`, `check_windows_checkpoints.py` (included by existing `check_windows_recovery.py`) | Authored final-state-key identity mutations; independent fresh Start reconstruction/build/install/write counts; stopped/unconfirmed/forged proof and changed source/options; low-space/cut old-cache preservation; absent-created/deletion miss; Stop during content hashing AND candidate receipt publication. |
| `CacheReuseProbeTest.kt` (replaces old real-service/legacy-confirm Java probe), `FullCoordinatorProbeTest.java`, `CoordinatorRecoveryProbeTest.java`, `RemovalRollbackProbeTest.java` | CacheReuse now private synthetic metadata/APK-ZIP only: active same-size tamper/missing record, stage-seal foreign knowledge, sealed interrupted record→delta state, missing intent/changed backup/new refusal, Remove required absence, linked ancestor, source-prime inventory, Stop/hash/publication ordering and publication cut. FullCoordinator adds independently authorized repeat Start over fake device/current full bytes, complete counts/lineage, zero new build/writes, retained full snapshot audit and mandatory two shell installs. Existing seals updated to context and justified intent states. Full data remains an explicit external fixture gate. |
| `docs/features/{language-switch,patch-speed,android-shell-providers}.md` | Current boundaries, conservative misses and unrun provider/parity/performance gates. |

| Check actually executed | Result |
|---|---|
| Python 3.12.10 AST parse + imports | Passed on changed Python shipping/probe modules; imported only, no probe loaders or entry points invoked. |
| Android compile-only first invocation | Main/unit Kotlin compiled; Java probe compilation exposed three old `PristineDelta.seal` call signatures. Updated those callers and interrupted-state fixture. No test task ran. |
| Android compile-only next invocation | BUILD SUCCESSFUL (46s), using JDK21/SDK paths and approved existing Gradle cache. Final post-edit compile result appended below. |
| `git diff --check` | Exit 0 (existing LF/CRLF warnings only). |

Conservative boundaries: this is output reuse after a CURRENT full snapshot/audit, not a zero-read phone no-op. Only pristine reconstruction and translation transforms are skipped; all necessary current hashes/access/normal/finalization remain. Source/prime provenance, receipts and summary are rehashed; unknown/missing identity declines optional reuse. Remove and Windows nonempty deletion declarations decline before allocation because already-absent files provide no new deletion pre-action proof. Unresolved/corrupt required state is never permission to overwrite or clean up. A copy cut leaves its new attempt without a receipt and preserves old proof; new Start authorization is never borrowed from the old run. Storage reserves include retained bytes through actual free space plus clone/normal/temp needs.

Stop publication boundary: Windows hashes first, then checks durable/queued Stop under its short control lock, publishes candidate record, checks lock-free queued Stop again, and commits terminal/retention proof. Android hashes first, then under its short run-store lock atomically selects Stop, publishes receipt, journals terminal state and resolves run; a concurrent later Stop orders after that already completed terminal operation. Neither path holds UI Stop behind content hashes. Terminal proof is required in addition to receipt outcome on reuse.

Open Pass-2 gates: execute artifact/checkpoint/recovery/signing/bridge probes; Android CacheReuse, FullCoordinator, recovery/removal/route/installed verifier probes and unit checks; complete EN/ID/switch/Remove/changed-game/producer/options/source/delta parity and repeated interruption controls; source/frozen import/build checks; UI strings/reference/staging checks; actual APK inventory and real provider cycles (separate consent for destructive work). Measure validation+snapshot+copy costs, hashes/bytes/install/build counts, total time and storage against controls. Keep shortcut only on measured safe benefit. No safety/parity/speed claim follows from compilation. No saved real-update capture is available; ticket 19 update/deletion replay gate remains open. Legacy schema-2 finalizations missing new sealed identities refuse rather than invent proof; migration behavior remains a Pass-2/19 review gate.

Handoff: coordinator source review required before advancing. Ticket 17/18 logic untouched. All acceptance and release gates stay open.

Coordinator preflight for16: inspect PristineDelta.finalize specifically. Current finalized=true early return never re-reads active delta/record. Before first pending intent, previous active/record backups lack a sealed explicit absence/hash identity; restart merges whatever current staged-hash record exists. Bind expected old and pending identities, validate active intermediate/final states and read back both active delta (or required absence) and staged-hash record before publishing/using completion. Do not overwrite unrelated changed active knowledge or fabricate a success from saved finalized flags. Preserve engine-independent recovery and unconfirmed pristine knowledge without allowing an unconfirmed completion receipt.

Also inspect recoverLocked.finish unconfirmed branch: it catches/logs PristineDelta.finalize failure then can close CANCELLED. A failed required pristine-knowledge promotion must remain pinned/actionable and cannot allow cleanup of required bodies or a misleading consistent closure. Stop after a durable finalization intent still needs metadata consistency, while remaining cancelled and ineligible for no-op/Open.

Pass 2 (2026-11-12, fsync/Windows fix worker): Production fix: `windows_checkpoints.reuse_completed` published `validation_and_copy_seconds` as a float, which canonical records refuse (`ArtifactError: Identity supports only ...`), so verified-completion reuse could never publish. It now records `validation_and_copy_ms` as whole milliseconds, matching Android's `completion-reuse-metrics.json`.

Commands (each `.venv\Scripts\python.exe tools\research\<name>.py`, run in this order on Windows 11, Python 3.12; logs `D:\scratch\hok-ac-pass2\logs\<name>.fsync-fix.log`): check_run_artifacts PASS; check_windows_file_transaction 16/16 OK; check_windows_checkpoints 28/28 OK; check_windows_controls 23/23 OK; check_windows_signing 18/18 OK; check_windows_recovery 104/104 OK; check_bridge_continuation 15/15 OK; check_windows_repatch 14/14 OK; check_pristine_delta 15/15 OK; check_mobile_snapshot 8/8 OK. Before the fixes: run_artifacts failed (EBADF), file_transaction 4 failures/1 error, checkpoints 28 errors, controls/signing/recovery errors, bridge 15 errors. Synthetic only; no device, no game data, nothing committed.

Pass 2 instrumentation (2026-11-12): the eight `CacheReuseProbeTest` failures (`Private path alias`) were the production root-alias defect recorded in 02 (fixed by `RunStore.privateRoot`); `RemovalRollbackProbeTest.testRemoveFinalizationIsByteOnlyAndIdempotent` also pinned its attempt before creating the result folder (test order fixed). `stopRacingShortPublicationOrdersAfterAlreadyLinearizedCompletion` then crashed the process: its raw Stop thread hit `OverlappingFileLockException` from the in-process store lock. Production callers (`MainActivity.saveStop`, `PatchWorkerService`) catch and retry, so the probe now retries the same way and asserts the Stop was saved after completion with `stop_requested` false. All CacheReuse probes pass.
