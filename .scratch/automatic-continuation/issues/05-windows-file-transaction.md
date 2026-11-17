# 05: Make Windows game writes recoverable and atomic per file

Status: ready-for-agent
Implementation: complete
Verification: pending
Blocked by: 03, 04

## Scope and files

Own new `app/device_transaction.py`, `patcher_core.py:pull_game_data/restore_pristine/push_translation/write_back_pristine`, journal transaction fields and realistic fake transport probes. Read architecture sections 4–5, ADR 0001, language-switch feature and Android GameFileLock/GameFileTransaction. Preserve the shared pristine-delta file format.

## Steps

1. Preserve immutable actual pre-action phone bytes and touched Watchdog contents before mutation. Keep them distinct from reconstructed pristine build input, including changed-only pulls that lack a backup tar.
2. Define the complete expected final file set and planned write subset. Keep existing Windows identical-output skip, but verify the full final set and retained source identity.
3. Replace direct live cp with journal intent → destination-directory temp copy → temp length/hash/sync → rename → parent sync/live read-back → durable acknowledgment. Use fixed validated paths/session temp names and device-side file locking equivalent to GameFileLock.
4. Reconcile before/after/absent/other live state on unknown outcomes. Clean only owned temps. Roll back incomplete apply to verified pre-action bytes, including Watchdog; repeated rollback interruption remains recoverable.
5. Save old/pending delta and staged-hash record before writes. After verified payload and normal APK, finalize delta promotion/removal idempotently; retain enough old/pending material through any finalization crash.
6. Remove success inference from cp/install exit codes. A complete layer audit and finalization record gate success. Unexpected external changes pause for existing pristine/update handling rather than blind rollback.

## Acceptance

- [ ] Partial temp copy never truncates the live target; before/after rename failures are distinguishable.
- [ ] Post-rename lost reply reconciles actual bytes; corrupt read-back blocks success.
- [ ] Between-file and repeated rollback interruptions converge to verified expected output or verified pre-action state.
- [ ] Remove preserves pristine/delta semantics, including crash during delta deletion; changed-only sessions can recover.
- [ ] Earlier translated bytes can be restored on Stop; reconstructed pristine bytes are not substituted for them.

## Checks and handoff

Run Windows recovery/repatch and pristine-delta probes. Inject every write/finalization boundary and Watchdog restore failure. Report file/byte/install counts and final hashes. Device filesystem/rename behavior remains a ticket 19 gate.

## Stop condition

If true pre-action bytes or complete file-set proof are missing, refuse before game writes. Do not use the pristine delta to guess truncated bytes or overwrite a detected new game update.

## Comments

Pass 1 implementation completed 2026-11-11. Acceptance boxes remain unchecked until Pass 2.

| Changed file | Implementation |
|---|---|
| `app/device_transaction.py` | Run/target/child-bound transaction; fixed Android-compatible game-private lock; separate upload/destination temporary/live paths; strict complete inventory; before/after identities; persisted intents and acknowledgment; per-file temp/hash/sync/rename/read-back; explicit deletion; repeated rollback; bounded apply/reapply; idempotent delta finalization after full payload/normal audits |
| `app/patcher_core.py` | Full and changed-only snapshots preserve actual package/Watchdog bytes in `recovery/` before pristine reconstruction; immutable snapshot manifest; storage gate; transaction apply/rollback integration; normal verification before finalization; explicit delta-created file deletion proof; UUID-session candidate ordering uses timestamp only to choose a hash-verified reuse candidate |
| `tools/research/_windows_fake_device.py` | Strict structured shell-protocol interpretation; separate live/upload/temp/Watchdog state; delete/directory failpoints; partial temporary copy support; no subprocess/device access |
| `tools/research/check_windows_file_transaction.py` | Synthetic real-journal probes for transfer/temp/rename cuts, unknown replies, corrupt read-back, repeated rollback/Watchdog recovery, external changes, Stop, bounded reapply, changed-only snapshots, explicit deletion, unrelated pending-delta refusal and interrupted promotion/removal |
| `tools/research/check_windows_recovery.py` | Includes transaction probes; direct-live-copy expected failure becomes an ordinary atomic-temp preservation assertion; wrong-target session reuse remains observable |
| `tools/research/check_windows_repatch.py` | Legacy primitive fixture harness supplies explicit durable ownership and fixture-only normal evidence/finalization; obsolete hand-cp interruption case uses actual journal rollback; keeps registry consistent when removing synthetic retained layers |
| `docs/features/language-switch.md` | Describes current Pass 1 protocol and distinguishes earlier verification from unrun transaction gates |

`app/patch_session.py` required no edit: its existing UUID child, ownership, Stop and retry APIs support the transaction.

| Check actually run | Result |
|---|---|
| `.venv/Scripts/python.exe --version` | Python 3.12.10 |
| Python 3.12 AST parsing and imports of the six changed Python modules | Passed; latest invocation after final code changes |
| Behavioral/integration/performance/device/Gradle checks | Not run: user's TWO PASSES rule |
| Real staged hashes/counts/timings or device filesystem semantics | Not measured; no parity/safety/speed claim |

The syntax/import command parsed `app/device_transaction.py`, `app/patcher_core.py`,
`tools/research/_windows_fake_device.py`, `tools/research/check_windows_file_transaction.py`,
`tools/research/check_windows_recovery.py`, and `tools/research/check_windows_repatch.py`
with `ast.parse`, then imported those modules after adding `app`, `tools`, and
`tools/research` to `sys.path`. It did not invoke any probe or pipeline.

### API handoff to 06/07

1. Keep `OwnedRun` claimed. Its `children.data_session` UUID is persisted before the session directory exists. `Patcher.preserve_recovery_snapshot(session)` commits `recovery-manifest.json` with target, exact files and directories; true pre-action bytes are in `recovery/packages` and `recovery/Watchdog`. Pristine input remains under `session/LAYER`; never substitute it for recovery originals. An incomplete snapshot refuses and needs a fresh owned snapshot attempt.
2. `DeviceTransaction(owner, ShellTransport(adb, reserve_bytes=...))` loads the bound `file-transaction.json`. `prepare(outputs, metadata, remove_delta=...)` creates it before mutation. Outputs map package-relative names to retained Paths or explicit `None` deletion. The core proves a missing reconstructed file was delta-created before requesting deletion. Required metadata includes a valid shared-format pending delta (empty for Remove) and strict new staged-hash record. Optional old delta/pending/hash presence is verified and pinned. A pending entry must match the complete intended output identity. No summary-format change.
3. `reconcile()` verifies retained originals/metadata, classifies every live file and refuses unexpected bytes/set changes. It does not dispatch. `apply()` accepts prepared state; interrupted applying state requires `rollback()` before continuing. `audit()` checks the complete expected live set, including identical-write skips. Watchdog clearing follows package writes. Recovery can roll back with damaged staging because it needs originals and pinned identities rather than the translation engine/output bytes.
4. `rollback()` is repeatable and uses safety-recovery retry scopes without revoking Stop. After verified rollback, `reapply()` can begin a distinct cycle only while continuation is authorized. The overall `files_apply` budget is initial attempt plus one retry across all cycles/reopen; a cycle never re-arms it. Per-file keys include cycle/direction/path digest. Never call `owner.rearm` automatically. The generic planner must reconcile actual committed journal outcomes before treating an exhausted-but-successful operation as failed.
5. `finalize(keep, verify_normal)` audits the full applied layer and invokes an independent installed-normal verifier on every call, including resumed/finalized calls. `Patcher.verify_normal_installed` uses the pinned APK journal. Old/pending material survives promotion/removal; Remove retires the keep delta through durable rename. Exact delta and staged-hash read-backs precede transaction `finalized`. It also reconciles `files_apply.completed` after a final-record/acknowledgment gap. Product completion receipt/lifecycle publication belongs to 06. `payload_verified` with Stop refuses finalization and needs safe rollback; already-started finalization must reconcile forward before any subsequent action.
6. No full startup dispatcher, Close handler, new automatic install cycle, retention cleanup or authorization migration was added. A Stop arriving after normal restoration can leave a pinned rollback need; 07 must restore access under its distinct install operation identity before file rollback. Keep unresolved recovery/APK/delta/stage material pinned.

### Remaining gates and concerns

| Concern | Pass 2 / later requirement |
|---|---|
| Conservative complete manifests are repeatedly hashed per file | Measure cost; no performance claim or weakened audit |
| Run retry record is bounded to 256 keys | Preflight refuses if it cannot retain every proposed apply/rollback budget; measure real write/Watchdog counts; never omit payload files to fit |
| Shell `flock`, `sync <file/dir>`, atomic rename, storage reserve | Validate on supported phones/filesystems; unsupported commands fail closed |
| Extra true pre-action layer copy and normal APK reserve | Validate real low-space/storage behavior; no large fixture was created or modified |
| Probe suite and legacy fixture harness | Authored and importable, not behaviorally verified; run recovery/repatch/pristine-delta checks in Pass 2 |
| Durable removal/promotion and repeated interruption | Run boundary injection, full EN/ID/switch/Remove output controls and real-device cycles before release |

No real game mutation, pipeline run, Gradle invocation, commit or fixture mutation occurred.

Coordinator review complete: inspected implementation/probes and requested corrections listed in coordinator record; git diff --check passed (CRLF advisories only). No behavioral acceptance claimed. Dependencies may advance to06 under user's implementation-first override.

Pass 2 (2026-11-12, fsync/Windows fix worker): test_each_temp_boundary_keeps_live_original: per Steps 4 ("Clean only owned temps"; rollback recovers), a cut leaves this session's own `.hok-<session>-*.tmp`. Production `inventory` already skips only that exact owned name, and `_path` refuses any other `.hok-` name, so production was correct and the test was comparing a raw tree. It now asserts that every stray is this session's owned temp, every live game file is unchanged, the strict inventory equals the pre-action inventory, and after `rollback()` the raw tree equals the originals (no temp outlives recovery). The WinError 5 in the watchdog test was the `_replace` flake, fixed in run_artifacts.

Commands (each `.venv\Scripts\python.exe tools\research\<name>.py`, run in this order on Windows 11, Python 3.12; logs `D:\scratch\hok-ac-pass2\logs\<name>.fsync-fix.log`): check_run_artifacts PASS; check_windows_file_transaction 16/16 OK; check_windows_checkpoints 28/28 OK; check_windows_controls 23/23 OK; check_windows_signing 18/18 OK; check_windows_recovery 104/104 OK; check_bridge_continuation 15/15 OK; check_windows_repatch 14/14 OK; check_pristine_delta 15/15 OK; check_mobile_snapshot 8/8 OK. Before the fixes: run_artifacts failed (EBADF), file_transaction 4 failures/1 error, checkpoints 28 errors, controls/signing/recovery errors, bridge 15 errors. Synthetic only; no device, no game data, nothing committed.
