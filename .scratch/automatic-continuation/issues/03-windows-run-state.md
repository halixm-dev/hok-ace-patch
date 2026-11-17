# 03: Add Windows durable run state and exclusive ownership

Status: ready-for-agent
Implementation: complete
Verification: pending
Blocked by: 01, 02

## Scope and files

Own new `app/patch_session.py`, `app/patcher_core.py:Adb/Patcher` initialization/discovery, the settings registry seam in `app/hok_patcher.py`, and recovery probe additions. Read architecture sections 1–3, 6–7. Introduce no startup tasks.

## Steps

1. Persist validated run intent before preparation, including action/language/serial/user/work-root and continuation/stop/retry state. Index unfinished roots in existing app-state storage; registry durability failures block dispatch.
2. Acquire OS-backed work-root and stable per-device locks with a consistent ordering. Record owner/run ids for diagnostics; the live lock is authoritative. Detect duplicated/inconsistent pending candidates.
3. Bind ALL ADB device commands to the selected serial, including shell, pull/push, install, reconnect and identity reads. Refuse unexpected Android-user/package target changes.
4. Add safe discovery/load/update methods and explicit lifecycle transitions. Recover pending setup before requiring an installed game. Leave routing to the later coordinator ticket, but expose a deterministic next-action plan.
5. Persist attempt counters before dispatch; reopen/reconnect retains exhaustion. Add exact-root/path/schema validation and actionable keyed errors for missing/corrupt state.
6. Retain legacy pending-delta sessions as safety-only candidates without inventing Start authorization. Preserve existing folder/language settings and bootstrap behavior.

## Acceptance

- [ ] Two processes/same folder and two folders/same phone cannot acquire competing mutation ownership.
- [ ] Every fake ADB operation carries the saved serial; a different sole-connected phone cannot receive pending work.
- [ ] Discovery finds a pending setup with no game installed and a root not currently selected in the picker.
- [ ] Torn registry/journal writes, missing work drive and ambiguous candidates fail closed with no game mutation.
- [ ] Retry and Stop state survive process death; idle open with no saved authorization mutates nothing.

## Checks and handoff

Extend/run `check_windows_recovery.py`, `check_windows_repatch.py`, `check_run_artifacts.py`; run `check_ui_strings.py` for new keyed failures. Add process-level lock tests, not only two objects in one interpreter. Hand off load/discover/claim APIs and lock order to 04–07.

## Stop condition

Do not wire automatic game changes until lock/identity/persistence tests pass. Unknown legacy records get attention or justified safety recovery, never a fresh patch.

## Comments

Pass 1 implementation complete; verification pending. No behavior, integration, performance,
device checks, phone commands or commits. Automatic mutation routing remains gated.

| Changed files | Purpose |
|---|---|
| `app/patch_session.py` | Schema-1 bounded strict intent/registry, atomic durable replacement/read-back, OS root/device ownership, discovery, lifecycle and persistent Stop/retry APIs. |
| `app/patcher_core.py` | Discovery before space/game checks; explicit Start claims/persists before preparation; serial binding for all device ADB subprocesses; owner-user checks; serial/user/package-specific incremental pull reuse; pin unresolved sessions. |
| `app/hok_patcher.py` | Narrow settings seam: consult the durable registry before changing language/folder; existing settings format preserved. |
| `resources/ui/strings.json` | Seven Windows EN/ID keyed recovery errors. |
| `tools/research/_windows_fake_device.py`, `check_windows_recovery.py` | Explicit target grammar/observations; wrong-device ordinary assertion; host-only discovery, persistence, corruption, idle/legacy, process lock and inherited-child ownership probes. |
| `docs/features/language-switch.md` | Foundation and temporary pending-run gate documented without claiming verified continuation. |

| Check actually run | Result |
|---|---|
| `.venv/Scripts/python.exe -m py_compile app/patch_session.py app/patcher_core.py app/hok_patcher.py tools/research/_windows_fake_device.py tools/research/check_windows_recovery.py` | Passed on final Python edits; syntax only. |
| Recovery/repatch/artifact behavioral checks; `check_ui_strings.py`; integration/device tests | Deferred to Pass 2 by user instruction. Acceptance remains open. |

| API for 04–07 | Contract |
|---|---|
| `patcher_core.discover_pending_runs(work=None)`, `Patcher.discover_runs()` | Consult all indexed roots plus selected root before fresh free-space/installed-game checks. Return zero or one candidate; malformed/missing/duplicate/conflicting candidates raise keyed PatchError. No phone work. |
| `RunStore(state_dir).load(root)` | Exact-root validated schema-1 `sessions/run-intent.json`; no fallback to empty authorization. Registry path is `SETTINGS.parent/unfinished-runs.json`, separate from best-effort settings. |
| `RunStore.discover(selected_root=None)` | Candidate `{kind:authorized,root,record,plan}` or `{kind:legacy_safety,root,session,plan:safety_attention}`. Multiple unresolved candidates fail closed, including legacy ambiguity. Legacy records confer no Start authorization. |
| `RunStore.claim(root,target,run_id=None)`, `Patcher.claim_run(target,run_id=None)` | Context-managed `OwnedRun`; new claim generates UUID, existing claim requires exact saved UUID/target. Target is `{serial,android_user,package}`; provider is exactly `adb`, package fixed. Claim does not grant authorization. |
| Lock ordering | Root `.patch-owner.lock` → stable state-dir `device-<SHA256(serial)>.lock` → short-lived `registry.lock`. Discovery only takes registry lock. Nonblocking kernel/exclusive-share ownership; never break by PID age. Windows handles are inherited through `OwnedRun.subprocess_options()` into ADB children so a surviving child pins ownership. Release after child exit. |
| `OwnedRun.authorize(action,language)` | Explicit Start only. Validates target/action/language; registry written/read back before intent publication. Crash between these leaves blocking missing state. Existing unresolved intent cannot be replaced. Returns copied record. |
| `OwnedRun.update(**changes)` | Only lifecycle/continuation/Stop/Close/children/retry/consents mutable. Re-read current revision/content under locks; immutable target/request, stale-owner writes and revoked Stop reject. Explicit lifecycle progression; waiting/attention retain authorization. |
| `next_action(record)` | Deterministic hint: prepare/reconcile_preparation/reconcile_setup/verify_snapshot/restart_build/verify_stage/reconcile_files/restore_normal/finalize/restore_then_cancel/wait/retry_required/attention/resolved. Never proof or authority to mutate. |
| `stop()`, `preserve_close()` | Stop persists continuation=false + stop_requested=true irrevocably. Close records preservation without resetting Stop. 07 must reconcile safety before terminal cancellation; no automatic route is wired. |
| `begin_attempt(key,destructive=False)` | Persist counter before dispatch. Ordinary maximum 2; destructive maximum 1. Waiting is not an attempt. Reconciliation/current target/scoped consent remain coordinator responsibilities. |
| `record_failure(key,class)`, `wait(key,reason)`, `rearm(key,safe_idempotent=,explicit_retry=)` | Persist failures/wait without resetting on reopen. Explicit Retry can rearm safe idempotent work only. Destructive work needs a new exact consent/attempt scope through 04; generic consents containers are not authority. |
| `complete_attempt(key,reconciled_success=True)` | Persist verified/reconciled success without clearing attempts/failures/exhaustion. Planner ignores exhausted completed successes; completed operations cannot dispatch again under the same logical key. Caller supplies consumer-boundary verification, not a successful transport reply. |
| Owned pending correlation | Explicit pulls persist UUID `children.data_session` before creating `sessions/<uuid>`. Discovery correlates only an exact saved child UUID under that root, returning `pending_sessions` on the authorized candidate; 04/06 still reconcile its journal/delta. Unrelated/unknown pending directories remain separate safety candidates and fail ambiguity. Legacy timestamp sessions gain no invented correlation. |
| `Adb.bind(serial,android_user=None)`, `assert_target()` | Refuse serial/user retarget; every device invocation includes `-s`, including exec-out and reconnect. Only host devices/start-server are unbound. Current profile must remain owner user 0, since existing run-as/path protocol cannot safely handle another profile. |

Temporary gate for 04/06: existing explicit workflow deliberately leaves lifecycle=preparing after
completion/error, because legacy normal restoration can falsely succeed. It never declares FINALIZED.
Subsequent fresh Start/settings changes block; unresolved material is pinned. 04/06 must reconcile
the actual APK/files and implement checkpoint/finalization routes before lifting that gate. First
setup can be discovered with no installed game, but executing its saved repair is 04/06 work.
Pre-mutation cancellation transitions will need 07's proven-safe boundary; do not mark a mutated
action resolved just to clear the UI. Unknown legacy deltas still require justified recovery proof.

Review corrections implemented: retry completed-success persists used budgets across reopening;
ADB command names are allowlisted before serial insertion (all global target selectors, including
`-t`, reject); own pending sessions correlate by durable child UUID while foreign pending blocks.
New probes cover successful second-attempt reopening and owned/foreign pending distinctions.

Durability/process failure probes are authored but unrun. Filesystem support, inherited Windows
handle behavior, full UI copy check, repeated disconnect/user switch and all lock acceptance remain
Pass 2 gates. Unsupported/corrupt state is preserved for diagnosis, never silently cleared.


Coordinator inspected final ownership/binding/planner integration and authored probes. Requested retry-success, selector and own-pending correlation corrections; all implemented and source-reviewed. `git diff --check` passed (existing CRLF conversion advisory only). No behavioral checks executed;04 may consume implemented APIs while verification stays pending.

Pass 2 (2026-11-12, fsync/Windows fix worker): `ApkJournal.update` now syncs each APK through `run_artifacts.sync_file` (it was a read-only fsync, EBADF on Windows). WinError 32 on `state/device-*.lock`: production releases correctly (`OwnedRun.close` closes every FileLock, and a constructor failure closes too). Two test causes: (1) the controls fixture registered `case.doCleanups` after a `case.setUp()` that raised from the fsync bug, so the owner was never closed; fixed by registering cleanup first. (2) recovery `test_child_keeps_locks_after_parent_process_dies` deliberately has a grandchild inherit the locks, and teardown deleted the temp dir before that grandchild exited; the test now opens the grandchild (SYNCHRONIZE) and waits up to 20 s for it.

Second production fix: `run_artifacts._replace` (MoveFileExW REPLACE_EXISTING|WRITE_THROUGH) failed intermittently with WinError 5 even when nothing else in the process touched the file (single-threaded stress: 4 of 3000 replaces in %TEMP%, from a scanner or indexer holding the fresh file). It now retries only errors 5 and 32 with bounded backoff (20 attempts, about 3.5 s), then raises; the move stays atomic. Stress after the fix: 0 of 3000.

Commands (each `.venv\Scripts\python.exe tools\research\<name>.py`, run in this order on Windows 11, Python 3.12; logs `D:\scratch\hok-ac-pass2\logs\<name>.fsync-fix.log`): check_run_artifacts PASS; check_windows_file_transaction 16/16 OK; check_windows_checkpoints 28/28 OK; check_windows_controls 23/23 OK; check_windows_signing 18/18 OK; check_windows_recovery 104/104 OK; check_bridge_continuation 15/15 OK; check_windows_repatch 14/14 OK; check_pristine_delta 15/15 OK; check_mobile_snapshot 8/8 OK. Before the fixes: run_artifacts failed (EBADF), file_transaction 4 failures/1 error, checkpoints 28 errors, controls/signing/recovery errors, bridge 15 errors. Synthetic only; no device, no game data, nothing committed.
