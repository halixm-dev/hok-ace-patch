# 06: Continue Windows work from committed checkpoints

Status: ready-for-agent
Implementation: complete
Verification: pending
Blocked by: 02, 04, 05

## Scope and files

Own `patcher_core.py:Patcher.run/pull_game_data/build_translation/prune_old_sessions`, `patch_session.py` planner, and artifact wrappers around existing shared staging. Read architecture sections 3–4/7 and `build_patch` docstring. UI stop/close wiring is ticket 07.

## Steps

1. Refactor `run` into checkpoint-driven operations behind the existing GUI/core boundary. Discover/claim unfinished saved action before creating a fresh timestamp session or demanding full build capacity.
2. Add completed-snapshot and completed-build receipts using ticket 02. Build publication includes restored-but-unstaged outputs, full expected hashes, summary and session delta. Keep summary schema unchanged.
3. Resume from valid prepared APK/snapshot/STAGED/payload/normal/finalization checkpoints per architecture. Restart only incomplete snapshot/build attempts in owned fresh scratch. Never treat a summary file as STAGED.
4. Before using retained work validate relevant retained and live identities. Changed engine invalidates stage; changed game/APK invalidates affected snapshot/preparation after safety reconciliation. Missing pristine evidence pauses.
5. Reuse staged output after rollback of an incomplete apply. Payload verified + missing normal restoration runs restore/finalization only. Preserve Remove and first-setup/update-wait routing.
6. Replace newest-two-only pruning with reference-aware cleanup and bounded resolved cache. Keep stopped reusable work; block cleanup of required recovery artifacts.

## Acceptance

- [ ] Reopen after SNAPSHOT_READY performs zero snapshot transfer if inputs still match.
- [ ] Reopen after STAGED performs zero build; interrupted build restarts build but keeps snapshot/APKs.
- [ ] Final-install-only recovery performs no staging or translation writes.
- [ ] Engine/game/APK/selection mutations cause correct invalidation, refusal or fresh authorized work; no silent retarget.
- [ ] Legacy delta bootstrap/repatch/Remove paths still work, and cleanup never deletes pending references.

## Checks and handoff

Run recovery/repatch/artifact/pristine probes. Assert calls and bytes, not just final success. Compare unchanged-input output/summary/delta with fresh controls for EN/ID and Remove. Hand off structured run outcome/next-action events to 07/13.

## Stop condition

Keep a failed receipt path as ordinary verified work or attention. Do not weaken trust checks to claim a stage was reused.

## Comments

Pass 1 implementation complete, 2026-11-12. Verification pending; all acceptance boxes
remain unchecked. Dependencies 02-05 were consumed as implemented interfaces, not verified
behavior. No behavioral, integration, performance, pipeline, device or Gradle checks ran;
no baseline/immutable fixture mutation, commit, release or subagent occurred.

The coordinator's earlier 2026-11-12 checkpoint recorded partial implementation after a
usage-limit interruption. The resumed work now includes its listed ordering, preparation,
retry-scope, cancellation-proof and cleanup corrections. This supersedes only that WIP
status; it does not close any verification gate.

| Files changed by 06 | Responsibility |
|---|---|
| `app/patcher_core.py` | Discovery-first saved-intent dispatch; lazy fresh-build engine import; preparation restart/source proof; verified snapshot/STAGED reuse; incomplete-attempt restart; restored/deleted output publication; rollback-before-reapply and restaging generation; final-install-only recovery; authenticated saved result; terminal receipt and structured events; normal-install binding; scoped retries/capacity/retention integration |
| `app/windows_checkpoints.py` | Owned UUID attempts persisted before mkdir; ticket02 snapshot/build receipts; complete retained/live verification; source proof independent of current engine; distinct mutable pristine copy; reference-aware resolved groups and cache invalidation before owned deletion |
| `app/patch_session.py` | Explicit reconciliation lifecycle edges; invalidating rejected retained output preserves used attempts; explicit safe recovery Retry can re-arm while leaving Stop irrevocable |
| `app/device_transaction.py` | Narrow integration: optional pinned `result-binding.json`; validated `prepare(initial_cycle=0)` to avoid retired per-file-key collisions; finalization callback contract audits with access, restores/verifies normal, then promotes metadata; Stop recheck before first finalization intent |
| `tools/research/check_windows_checkpoints.py` | New private synthetic signed-APK/checkpoint coordinator fixtures and assertions; no real translation producer or native codec run |
| `tools/research/check_windows_recovery.py` | Includes checkpoint probes; fake download wait remains explicit rather than silently granting readiness |
| `tools/research/_windows_fake_device.py` | Opt-in realistic refusal of game-private transaction commands while the installed APK is nondebuggable |
| `docs/features/language-switch.md`, `docs/features/standalone-patcher-app.md` | Current implementation boundaries, ordering and unrun verification gates |

| Check actually run | Result |
|---|---|
| `.venv/Scripts/python.exe --version` | Python 3.12.10 |
| Python 3.12 `ast.parse` and imports of seven edited modules | Passed. Modules: patcher_core, patch_session, device_transaction, windows_checkpoints, check_windows_checkpoints, check_windows_recovery, _windows_fake_device. Imports did not invoke tests, pipeline or fixtures. |
| Scoped `git diff --check` | Passed before final documentation handoff; final syntax/diff check repeated after edits. |
| Behavioral/recovery/repatch/artifact/pristine probes; EN/ID/Remove parity; device/installer interruption; frozen build/Gradle | NOT RUN by the user's two-pass instruction. No timing/count/safety acceptance claim. |

The syntax/import command reads each of the seven listed Python sources with `ast.parse`,
adds `app`, `tools`, `tools/research` to `sys.path`, and imports those modules. It never calls
`unittest`, fixture setup, a probe entry point or `build_patch`.

| Authored assertions (UNRUN) | Evidence required in Pass 2 |
|---|---|
| Reopen with snapshot or STAGED | Zero snapshot transfer; respectively one synthetic build or zero builds; exact expected live bytes/result |
| Summary-only/incomplete attempt; engine/game mutation | New owned build attempt; keep independent snapshot on engine change; changed game refuses old staging and requests fresh source |
| Restored-but-unstaged output | Included in receipt and complete expected layer |
| Interrupted apply | Actual rollback then valid stage reapply, persistent overall attempts and advanced cycle |
| Payload verified/final install only | No producer identity loading, snapshot transfer, build or payload rewrite |
| Finalization ordering | Fake refuses run-as under normal; complete live audit precedes independent normal install/audit and metadata promotion |
| Saved result tampering | No forged counts or completion receipt |
| Stop during normal restore/after finalization intent | First finalization blocked; already-started finalization finishes forward with stopped_consistent/cancelled, never Open game |
| Preparation gaps | Incomplete normal restarts in a new child; signed normal before official setup does not grant conversion/consent; original remains installed on Stop; changed/missing source refuses |
| Retry and mandatory safety scopes | Rejected checkpoint retains attempts; ordinary cycles cannot spend Stop repair scope; unknown installed bytes cannot resolve cancellation |
| Remove and retention | Reuse completed Remove output, retire pristine delta, preserve unresolved references and newest stopped cache |

### API handoff to 07 / 13 / 15 / 16

| API / artifact | Exact contract |
|---|---|
| `Patcher.run()` | Discovers/claims before fresh checks; rehydrates work/keep/language/action/target from immutable saved intent. Returns the unchanged pipeline/Remove result only after normal/layer/delta proof and completion publication. Cancellation raises keyed error_cancelled; unresolved recovery never returns success. Legacy pending records remain safety attention. |
| `Patcher.event(state,next_action,**detail)` / `.outcome` | Optional `ui.run_event(dict)` projects working/continuing/waiting/attention/cancelled/verified_complete and concrete next action. This is UI data, never authorization. Existing GUI still needs ticket07/13 integration. |
| `_continue_authorized`, `_resume_stages`, `_finish_transaction` | Owned worker seams. Safety reconciliation precedes producer loading; final-install-only uses pinned journals and saved receipt identity. Snapshot/STAGED reuse requires full retained/live checks. Do not dispatch these from UI status alone. |
| `Checkpoints(owner,session)` | Session must equal durable children.data_session. Snapshot verification rehashes recovery and exact live inventory, APKs/readiness. Staging compares current complete producer; no complete producer means fresh verified processing only. A summary is never STAGED. |
| `owned_attempt(owner,session,kind)` | Only prepared/snapshot/build; persists UUID child before mkdir; verifies owned path/no links. Failed attempts are retained, never overwritten. |
| `DeviceTransaction.prepare(...,initial_cycle=0)` | Core chooses max retired verified-rolled-back file cycle +1 for a new staging generation. Per-file keys cannot collide with the retired generation. `files_apply` is still the SAME overall initial+one budget; capacity and cycle bounds refuse before mutation. |
| `DeviceTransaction.finalize(keep,verify_normal)` | Requires access for full layer audit; callback MUST restore and independently verify normal, not expect it already restored. Only then metadata promotion/readback. Recheck Stop after callback before first finalizing intent. Reopened finalizing/finalized repeats access audit and normal callback, never skips either. |
| `access-plan.json` / `install_prepared` | Stable run/target/scope/cycle access and paired normal names. Every normal cleanup except setup_normal is centrally bound to plan.normal. Intent/lost replies reuse that scope. Ordinary, finalization and mandatory recovery scopes have bounded persistent budgets; reopen cannot invent a new failure scope. |
| `OwnedRun.invalidate_checkpoint(key,retained_proof_invalid=True)` | Only after rejecting retained proof and reconciling mutation safety. Clears completed flag only; keeps attempts/failures/exhaustion. It is not rearm. |
| `OwnedRun.rearm(...safe_idempotent=True,explicit_retry=True,safety_recovery=True)` | Explicit user Retry may re-arm required safe consistency repair while Stop remains true/continuation false. Never call automatically; destructive dispatch still cannot bypass Stop/consent. 07 owns thread-safe explicit Retry policy. |
| `completion-receipt.json` | Run/target/action/language, complete expected files, exact normal APK, retained metadata and result, optional build receipt identity. Publish/read back after file finalization; lifecycle last. stopped_consistent is NEVER eligible for ticket16 no-op reuse. Missing complete producer/build proof also disables no-op reuse. |
| `result-binding.json` in transaction-meta | Pins summary digest, optional build receipt digest and session-relative committed root before writes. Saved-result recovery checks transaction material plus saved receipt identity without loading current engine. Corrupt/missing proof preserves recovery but blocks trusted completion counts. |
| `prune_old_sessions(...owner=...)` / `prune_sessions` | Requires owned root/device locks. Pending child references and unknown/legacy/malformed material are pinned. Only validated resolved optional groups may be invalidated/deleted, retaining newest per exact target (including stopped work). 16 Free up space must honor the same pins/invalidation marker. |
| Signed preparation for 15 | Source/normal/access remain immutable pinned identities. Without complete producer reuse proof, fresh access generation is compared with saved identity; a legitimate changed serialization that cannot fit this immutable generation pauses conservatively. Do not overwrite old recovery APKs or treat nondeterminism alone as tampering. |

### Remaining gates / limitations

- Ticket07 still owns cooperative non-daemon worker control, thread-safe Stop/Close persistence,
  cancellation of UI waits, reconnect and bounded transient retry scheduling. This ticket does
  not claim working live Stop/Close controls or automatic retry timing.
- Before first finalization, Stop requires pre-action rollback; after durable finalizing intent,
  forward-safe completion yields stopped_consistent/cancelled. Retain originals/old metadata
  for ticket07's further consistency handling; never upgrade that outcome to a translation success.
- Real EN/ID, language-switch, Remove, legacy bootstrap/changed-only behavior and baseline parity
  remain unrun. Coordinator owns external compare_continuation_controls.py and its README row.
- Unknown producer/unsafe preparation transitions may report attention. No complete identity is
  fabricated. Changed APK/game must remain within verified source/pristine/readiness rules.
- Full retained/live hashes and snapshot copies are deliberately conservative. Capacity reserves,
  bounded 256 retry keys, shell lock/sync/rename behavior and source/frozen import packaging require
  measurement/verification. No speed or reduced-storage claim.
- Historical device results in feature records do not verify the new continuation protocol.
Coordinator review 2026-11-12: source inspected against ticket/architecture and requested corrections received. Whole-workspace git diff --check passed (CRLF advisory only). Implementation may advance to07; behavioral acceptance remains pending.

Pass 2 (2026-11-12, fsync/Windows fix worker): check_windows_checkpoints fixture fixes (test-only): `fresh_repeat` took a recovery inventory after the first run finalized on the non-debuggable normal APK (run-as closed). It now lifts `require_debuggable_run_as` only for that fixture inventory; the run under test still installs access itself, and the install-count assertions are unchanged. `test_changed_engine_keeps_snapshot_but_rebuilds_stage` mutated a nonexistent `executable` component of the Android vector producer; it now changes `native/libcodec.so`.

Commands (each `.venv\Scripts\python.exe tools\research\<name>.py`, run in this order on Windows 11, Python 3.12; logs `D:\scratch\hok-ac-pass2\logs\<name>.fsync-fix.log`): check_run_artifacts PASS; check_windows_file_transaction 16/16 OK; check_windows_checkpoints 28/28 OK; check_windows_controls 23/23 OK; check_windows_signing 18/18 OK; check_windows_recovery 104/104 OK; check_bridge_continuation 15/15 OK; check_windows_repatch 14/14 OK; check_pristine_delta 15/15 OK; check_mobile_snapshot 8/8 OK. Before the fixes: run_artifacts failed (EBADF), file_transaction 4 failures/1 error, checkpoints 28 errors, controls/signing/recovery errors, bridge 15 errors. Synthetic only; no device, no game data, nothing committed.
