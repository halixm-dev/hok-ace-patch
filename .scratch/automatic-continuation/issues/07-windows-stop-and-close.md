# 07: Wire safe Windows Stop, Close and progress

Status: ready-for-agent
Implementation: complete
Verification: pending
Blocked by: 06

## Scope and files

Own `app/hok_patcher.py:start/worker/pump/close/_on_ui/show_start`, core cancellation/progress seams and their probes. Read architecture section 6, spec user states, PRODUCT.md and DESIGN.md. Final copy/theme reconciliation is ticket 13.

## Steps

1. Use a non-daemon worker and cooperative cancellation. Persist Stop before acknowledging it, disable repeat Stop, resolve/cancel pending UI requests and wait at safe operation boundaries without freezing the UI.
2. Distinguish Close from Stop: Close preserves continuation, finishes feasible cleanup/normal restoration, then exits. Disconnection/forced kill leaves recoverable durable state. Do not kill the shared ADB server or unrelated ADB work.
3. Startup discovers saved work and automatically dispatches or attaches via existing lock; connection return triggers the same idempotent path. No fresh action without saved/user authorization.
4. Carry detail/bytes/wait reason from worker through pump to display. Show install approval prompts and current indivisible operation; use indeterminate progress if total is unknown.
5. Lock choices for pending work and render only the core's verified result as success/Open game. Retry action uses persisted budget/reset rules and cannot restart a stopped action automatically.

## Acceptance

- [ ] Stop during build/install/write acknowledges immediately; window remains responsive, no repeated stop request, safe recovery stays stopped after reopen.
- [ ] Close during the same points preserves intent and next reopen continues; repeated Close cannot spawn/kill competing workers.
- [ ] A worker waiting for a UI answer cannot deadlock Close/Stop.
- [ ] pump displays real detail/byte progress and actionable phone wait prompts.
- [ ] Failed normal restoration stays blocking and never becomes Translation added/Open game.

## Checks and handoff

Run recovery/repatch and UI-string checks; exercise `run.bat` for Close/Stop/progress with a fake or non-destructive setup, then real cycles in 19. Record observed UI states and unresolved device gates. Ticket 13 completes shared strings/design rules.

## Stop condition

If an operation cannot stop immediately, show what it is waiting for and keep durable intent. Never claim stopped safely until consistency is verified.

## Comments

Pass 1 implementation complete, 2026-11-12. Verification pending; every acceptance
box stays unchecked. Dependencies 01-06 are implemented interfaces, not verified
behavior. No behavioral/unit/integration/UI-string/reference/performance/device or
pipeline checks ran. No real game or immutable baseline/fixture mutation, commit,
release, screenshot or observed interactive UI result.

| Changed file | Responsibility |
|---|---|
| `app/hok_patcher.py` | Non-daemon worker/control threads; idempotent Stop/Close; synchronous disk-free flag queue before cancelled dialogs; cancellable and exception-safe UI waits; saved-intent-only startup dispatch; pending choice locks; core-event/detail/byte/APK-entry progress; honest indeterminate states; verified-only success results; close waits without blocking Tk or stopping shared ADB |
| `app/patcher_core.py` | Queued pre-claim controls and persistence boundaries; cancellation-free mandatory cleanup; recovery context loading on early control; already-finalizing forward safety; bounded owned ADB children; exact-phone reconnect waiting; measured progress; stable durable reconciliation guards; bounded automatic transient retry and explicit safe Retry |
| `app/patch_session.py` | Whole-method reentrant serialization of owner read/modify/write, Stop/Close, retry and ownership release; exhausted-dispatch guard blocks new non-safety sends while allowing audited bounded safety repair |
| `resources/ui/strings.json` | Windows control/wait/install/progress keys with matching EN/ID placeholders; shared Stop safely key gains Windows platform; new ID copy marked draft |
| `tools/research/check_windows_controls.py` | Private synthetic race, pre-claim Stop, delayed control saver/UI waits, callback exception, repeated Close, startup authorization, retry/exhaustion/reopen, explicit safe recovery Retry, save-failure/no-ack, measured progress, false-success, build/install/file-commit interruption probes |
| `tools/research/check_windows_recovery.py` | Includes both new control probe classes in the existing recovery suite |
| `docs/features/language-switch.md`, `docs/features/standalone-patcher-app.md` | Scoped current behavior and open Pass 2/device/visual gates, preserving earlier records |
| This ticket | Implementation/verification split, check record and handoff |

| Check actually run | Result |
|---|---|
| `.venv/Scripts/python.exe` Python 3.12.10 `ast.parse`, JSON parse and imports | Passed for patch_session, patcher_core, hok_patcher, check_windows_controls and check_windows_recovery. No fixture setup, unittest/probe entry point, window, ADB, pipeline or runtime producer invoked. Repeated after final source changes. |
| Import output | CustomTkinter warned its font_shapes font could not be loaded and selected circle_shapes. Import passed. Rendering quality remains an unrun UI gate; no visual claim. |
| Behavioral/recovery/repatch/UI-string/reference/staging checks; `run.bat`; source/frozen/device/installer interruption; parity/timing/Gradle | NOT RUN under the user's two-pass override. Required gates remain open. |

### Control and retry handoff to 08 / 13 / 15 / 16 / Pass 2

- `Patcher.queue_control(stop=True/close=True)` is the disk-free, monotonic UI seam.
  Queue it BEFORE cancelling a UI wait. `request_control` persists through the
  serialized owner on a short non-daemon control thread and returns true only when
  an owned intent exists and is durable. A pre-claim request stays queued; worker
  claim/authorization/boundaries persist it before mutation or cleanup. Failed save
  cannot acknowledge Stopping safely and prevents automatic window exit.
- `control_boundary` runs before owned ADB commands, step changes, APK-entry callbacks
  and translation-build log callbacks. UI wait cancellation also calls it before
  raising. Cleanup sets `_recovering` to bypass further user cancellation, never
  journal budgets. Early saved-run control loads pinned journals/transaction before
  recovery. Already-started finalization finishes forward, yielding cancelled for
  Stop rather than success.
- Each owned ADB subprocess has a 180-second timeout. It affects only that child;
  no shared server/process shutdown. Command outcome uncertainty is journal-audited
  before retry. Device timing/slow installer adequacy and child/remote lock behavior
  remain Pass 2 real-device/frozen gates. Unknown build totals remain indeterminate;
  cooperative build response waits for an existing log/APK-entry boundary.
- `_dispatch` persists `control_reconcile_<digest>` before connected dispatch, where
  digest uses actual non-control attempts/completion progress. Repeated read failure
  before a send cannot borrow unrelated pending-work permission. Exact-phone absent/
  unauthorized waiting polls with 1-5 second backoff without spending attempts.
  Guard exhaustion still permits one audit dispatch per reopen with
  `owner.dispatch_read_only=True`; new non-safety `begin_attempt` refuses, while
  mandatory safe recovery retains its independent bounded budgets. No guard UUID,
  timestamp, reconnect or invocation-count reset.
- Explicit UI Retry re-arms exhausted known safe prepare/snapshot/build/files/APK and
  control-reconciliation keys. It never re-arms uninstall, clears Stop, changes target
  or grants destructive consent. Every actual mutation retains its own initial+one
  durable budget. Transport eligibility follows keyed errors/causes or child timeout;
  arbitrary filesystem failures do not become automatic retries.
- `App.worker` reads the actual rehydrated patcher's Remove action, and accepts success
  only with core `outcome.state == verified_complete`. Pending work locks settings;
  startup with no discovered durable intent remains idle. Live ownership is refused
  through existing locks rather than spawning a second worker.
- Ticket 13 owns final shared states/EN-ID copy reconciliation and visual/interactive
  review in the pinned PRODUCT/DESIGN layout. Technical step/build detail remains
  visible; verify comprehensibility, wrapping, scaling, all dialog/control states and
  the CustomTkinter import font warning in Pass 2.
- Run the new control probe directly and through recovery, existing recovery/repatch
  probes and UI-string checks in Pass 2. Verify actual source/frozen GUI Close/Stop
  during build/install/write, repeated interruption during cleanup, reconnect,
  exhausted Retry across reopen, incomplete normal restoration and verified-only
  result controls before checking any acceptance box. Real-device gates belong to19.


### Final review correction, 2026-11-12

Immediately after `DeviceTransaction.finalize` returns, `_finish_transaction` now
flushes queued controls under the existing control lock before selecting/publishing
the terminal receipt. A Stop queued during metadata promotion, with its save thread
still delayed, becomes durable `stopped_consistent`/cancelled. Finalization stays
forward-safe; no new rollback or reduced live proof. The authored deterministic
`test_stop_queued_at_finalize_return_publishes_cancelled_without_saver` wraps the real
synthetic transaction finalizer, queues Stop just before return without a saver, and
asserts durable Stop, finalized files, cancelled receipt/UI outcome and zero rollback.
This probe is UNRUN. Final Python 3.12 syntax/import checks passed after the correction;
the same CustomTkinter font fallback warning remains. All acceptance gates stay pending.

Same-app Retry correction: the GUI keeps a separate `pending_stop` until a verified
cancelled/completed outcome. A failed save/recovery leaves it set. Replacement Retry
workers receive the queued Stop before their thread starts, keeping the saving state
and disabling another Stop. Retry therefore retries Stop persistence/consistency
recovery rather than silently continuing the patch. An authored headless probe
asserts queue-before-worker-start with an unsaved pending Stop. This protects this
open app only; no persistence is claimed across forced death while disk writes fail.

Coordinator review: inspected control/thread/locking/progress/startup/retry paths against ticket and architecture; requested retry-bound, dialog-control race, finalization Stop and failed-save Retry corrections received. Whole-workspace git diff --check passed (CRLF advisory only). Advance08 on implemented interfaces; every behavioral acceptance remains pending.

Pass 2 (2026-11-12, fsync/Windows fix worker): check_windows_controls fixes (all test-side): the UI SimpleNamespace fakes gained `pump=Mock()` (pump reschedules `self.pump`); the bytes expectation now uses `hok_patcher._size(4096)` (ticket 13 formats sizes); the WindowsControlRecovery fixture binds the control boundary as `Patcher.run` does (`_bind_control` before dispatch, unbound after), and FakeAdb calls it before each command. With that seam, a Close after the first rename surfaces at the next ADB command and the transaction rolls back to the pre-action bytes, as the test requires. No production control change.

Commands (each `.venv\Scripts\python.exe tools\research\<name>.py`, run in this order on Windows 11, Python 3.12; logs `D:\scratch\hok-ac-pass2\logs\<name>.fsync-fix.log`): check_run_artifacts PASS; check_windows_file_transaction 16/16 OK; check_windows_checkpoints 28/28 OK; check_windows_controls 23/23 OK; check_windows_signing 18/18 OK; check_windows_recovery 104/104 OK; check_bridge_continuation 15/15 OK; check_windows_repatch 14/14 OK; check_pristine_delta 15/15 OK; check_mobile_snapshot 8/8 OK. Before the fixes: run_artifacts failed (EBADF), file_transaction 4 failures/1 error, checkpoints 28 errors, controls/signing/recovery errors, bridge 15 errors. Synthetic only; no device, no game data, nothing committed.
