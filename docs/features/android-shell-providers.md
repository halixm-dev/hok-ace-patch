---
feature: android-shell-providers
status: building; ticket 03 device test requested
updated: 2026-11-13
---

# Android patcher shell providers

## Report

### Wireless debugging real interruption cycles (2026-11-12 to 2026-11-13, `f15a72e`)

Phone `f15a72e` (Xiaomi M2007J3SG, Android 12), Wireless debugging only; details in the
[lab notebook](../lab-notebook.md).

| Case | Verdict |
|---|---|
| Force-stop during build (C3, twice) | Reopen resumed the saved action on the same provider with one worker; the snapshot was reused. The first one logged a non-fatal reset defect, fixed in the bridge and rechecked (`ddfda089`). **Pass** |
| Worker killed mid-apply (C5) | *Worker disconnected*, no false *installed app changed*; the automatic retry reconnected the same provider by port scan, rolled back, reused the verified build and completed. **Pass** |
| Force-stop in the final normal install (C6) | Reopen restored and verified the normal APK with no snapshot, build or apply repeated. **Pass** |
| Stop reporting (build `21f51bb2`) | A Stop during the final install reports the translation as added (`stopped_after_finish`); a Stop mid-write shows *Checking the original game files* and *Restoring the original game files* before *Stopped safely*. **Pass** |

Open: Shizuku and Root real cycles (not selected by the user), so Root's zero-install path has no new
phone run; the home screen's priority of recovery over Re-download; the screen heading stays
*Stopping safely* during rollback.

### Completion reuse provider boundary (2026-11-12, pass 1, unverified)

| Provider/rule | Current source behavior |
|---|---|
| Shizuku / Wireless debugging | Reusing success output keeps the verified temporary-access/normal cycle needed for actual full-file auditing; it advertises only reconstruction/transforms skipped. The exact normal APK is independently verified before finalization/completion. |
| Root | Reuses the same current full-byte audits and new owned attempt without access APKs or any install/reinstall. The actual installed APK must remain the exact expected source. |
| Recovery | Sealed delta promotion and complete-result recovery remain engine-free for saved bytes. Unconfirmed metadata failures stay pinned/actionable. Completion/Stop selection serializes only short durable publication, with expensive content hashing outside the run-store lock. |
| Gates | Private completion/finalization/Stop and fresh Start coordinator probes are authored only. All provider interruption/device cycles, current-byte invalidations and timing controls remain pending. |

### Automatic continuation: authorization seam (2026-11-12, unverified)

| Rule | Current source behavior |
|---|---|
| Start | `RunStore` durably saves exact action, language, provider, local device identity, primary Android user and package before APK preparation. Root, Shizuku and Wireless debugging stay distinct. |
| Dispatch | The service connects using the saved provider. Under `sessions/coordinator.lock`, a recoverable claim and schema-2 journal share one stable run/session UUID and authorization digest. Duplicate dispatch attaches to the existing child rather than starting another patch. |
| Stop and ownership | Stop updates the short run-store lock without waiting for a long coordinator operation. Preparation/dispatch hold coordinator ownership first; store operations never acquire it in reverse order. Process-local busy and worker status grant no permission. |
| Migration | Schema-1 patch requests cannot start new mutation; old session journals remain available for justified safety recovery. Ordinary Start has no 15-minute expiry. Destructive setup consent keeps its separate one-use expiry. |
| Open work | Tickets 09–13 supply checkpoint continuation, parent setup linkage, provider recovery routing, scoped deletion consent and final UI. Compilation alone proves no device behavior. Pass-2 probes and all three provider interruption cycles remain open. |

### Automatic continuation: checkpoint dispatch (2026-11-12, pass 1, unverified)

| Rule | Current source behavior |
|---|---|
| Startup | On a fresh launch the app attaches to a live worker of the one saved action (same `run` in worker state). Otherwise it continues a confirmed (`prepared`/`claimed`) action that may still continue, through the ordinary recovery-first route. A Shizuku that is not running is waited for, not opened. A clean idle screen, a saved status or a Stopped action starts nothing. |
| Routing | `AutomaticRoute.choose` takes the pending Starts. A session linked to the one continuable claimed Start goes to that Start's dispatch (`CONTINUE_RUN`); any other session gets safety recovery only. A Stopped action with nothing mid-change is resolved without device work (`RESOLVE_STOPPED`). More than one candidate goes to `MANUAL`. |
| Provider | A continuation runs on the saved provider. Root still installs no APK: it checks the installed app it left in place before reading or writing, and recovery never needs the engine. |
| Waiting | A build refused over damaged files records `waiting_reason` (`redownload_consent_required`) and returns `waiting`. Start never deletes files; the scoped consent is ticket 12's. |

### Automatic continuation: Stop safely, setup and provider return (2026-11-12, pass 1, unverified)

| Rule | Current source behavior |
|---|---|
| Stop safely | One tap, no second dialog. The app saves Stop on the run first (`continuation=false`, `stop_requested=true`), then shows *Stopping safely* with the button disabled and tells the worker. The worker saves Stop again, publishes `stopping` in its state, drops the notification's Stop action and ends at the next safe boundary: the current build or install finishes or is rolled back, never cut mid-file. |
| After Stop | Only safety work runs (`AutomaticRoute.allowedWhileStopping`): emergency verification, patch or setup recovery, and closing the stopped record. A new preparation, the saved action or the downloads question never starts. A failure leaves the Stop saved; reopening finishes the recovery and the action stays stopped. Valid snapshot and build checkpoints are kept for a later explicit Start. |
| Reopen | `AutomaticRoute.onLaunch` reads durable records only: a saved Stop finishes recovery, an approved setup with an uninstall or install intent is recovered install-only, and a Start that may continue resumes unless its last failed operation has spent its automatic retry. Rotation or backgrounding never stops the foreground worker; the screen reattaches to it. |
| Provider | While a saved action is unresolved, the screen uses that action's provider, and the provider and language pickers are locked. A Shizuku that is not running, or Wireless debugging that is off, unpaired or off Wi-Fi, is waited for while the app is open, with that provider's own instruction on screen. No permission is granted silently, and no other provider is used. Setup recovery and the downloads answer use the provider of the setup's parent Start, even after Stop. |
| Retry | Each logical operation (the `RunStore.beginAttempt` key the worker saves before dispatch: `preparation`, `dispatch`, the coordinator stages, `first_setup`) gets its initial attempt plus one automatic retry. `RunStore.recordFailure` charges a failure to the operation last begun (`start` if none began), and saves its class and the waiting reason with the run, so reopening does not reset it. Waiting for a provider is saved as a reason, never as an attempt. When the same operation fails on its retry, the action pauses and the screen shows one next action. An explicit Start or Try again re-arms safe operations (`RunStore.rearm`). It never clears Stop, an uninstall attempt or any setup or Re-download consent. |


**Where it stands (2026-10-24).** Shizuku, Wireless debugging and Root built and device-tested. The Android patcher offers three shell
providers: Shizuku (today's), Wireless debugging and Root, picked by the user on the home screen. The
work in flight is [`.scratch/shell-providers/`](../../.scratch/shell-providers/spec.md), tickets 01–04;
the root write path is decided in [ADR 0007](../adr/0007-on-a-rooted-phone-write-the-override-layer-directly.md).
Shizuku's own history stays in [android-shizuku-patcher](android-shizuku-patcher.md). Ticket 01 passed on a phone;
tickets 02 and 03 passed on the same phone, and passed again in an independent retest. No coverage count moves.

### Journey log

- Feasibility read of the code: the worker needs only a shell process, and `ShellServiceStarter` already
  starts it without Shizuku, so any provider that can run one shell command can start it — settled by
  reading, not measured (2026-10-22).
- Grilling rounds 1–3 settled the design (2026-10-22). Round 4 kept the six progress steps under root (two skipped), put KernelSU first and set the device-test handshake (2026-10-23).
- Ticket 01 built: the home screen's ② Shell provider picker, the `WorkerStarter` seam with Shizuku as its one implementation, and the refusal of Shizuku running as root; device test requested (2026-10-24).
- Ticket 01 passed its device test on the Redmi Note 9 Pro (2026-10-24).
- Ticket 02 built: the Wireless debugging provider, an ADB client ported from Shizuku (pairing by notification reply, the worker started over an ADB shell stream, a lost connection as a worker loss), plus Conscrypt and a BoringSSL SPAKE2 library, about 3.7 MB; pairing and the worker start verified on an emulator; device test requested (2026-10-24).
- Ticket 02 passed its device test on the Redmi Note 9 Pro: pairing by notification, a full patch, a loss mid-write recovered, and the three refusals (2026-10-24).
- Ticket 03 built: the Root provider. `su -c` starts the worker as uid 0, which runs the same locked scripts in the game's data directory and gives what it creates the owner and SELinux label of `files/QtsVFSCache` (`chown`, `chcon`, umask 000 to match `run-as`; measured as root on KernelSU, see the ticket). A root preparation copies only the installed game app for the build; a root run installs nothing, records the installed app in its journal (`root_installed`) and verifies it is still installed at the end. Unlock access and Restore game app are skipped with a log line each. A run recovers only through the kind of provider that started it. Device test requested (2026-10-24).
- Ticket 03 device test failed on eb1943d: KernelSU's `su` runs in the patcher's mount namespace, where app data isolation hides `/data/user/0/<game>`. A root run now falls back to `/data_mirror/data_ce/null/0/<game>`, and the KernelSU grant lines say to reopen HOK ACE, since a grant reaches only processes started after it. Device test requested again (2026-10-24).
- Ticket 03 device test passed on `75a7f69` (KernelSU): patch, game start, loss mid-write and recovery. A dead worker's call is now journalled as *Worker disconnected* rather than `null` (2026-10-24).
- Tickets 02 and 03 passed an independent retest on `1f5301a`: the dead-worker line reaches ③ as each provider's own line (2026-10-24).
- The tests' minor findings fixed: the wireless connection log names no port before it finds one and gives a lost connection's exception type instead of `null`; a root run's result says *The game app was not replaced* instead of naming the normal app; under Root a retained normal APK alone no longer offers *Reinstall saved game app* (a pending emergency restore still does). Tickets 01–03 resolved (2026-10-24).
- Ticket 04 on the KernelSU phone: Shizuku then Root and Root then Shizuku share one pristine delta (identical but for its time), and a Wireless debugging run completes under deep Doze with the screen off (2026-10-24).
- A provider lost during prepare now reports itself: the cancelled prepare carries *<provider> disconnected*, and ③ shows *Wireless debugging disconnected. No game files changed…* or *Root access stopped. No game files changed…*, leading back to Start. ③ also reads *Turn on wireless debugging* while the switch is off, not *Ready when you are* (2026-10-24).
- On an Android 12 Xiaomi, discovery kept finding only another phone's wireless debugging service on the same Wi-Fi, so Start refused with *Wireless debugging is off* while it was on; the port is now found by scan when discovery names none on this phone (`AdbMdns.scan`: a listener in the ephemeral range that answers CNXN with STLS). A provider's refusal now leads ③ to Start instead of recovery options. Passed on that phone (2026-10-29).
- A provider lost while recovery checked the installed game app read as *The installed game app changed* (phone `f15a72e`, Wireless debugging switched off mid-recovery). That check now tells the two apart: a dead worker, or a remote call, stream or wait that ended early, journals *Worker disconnected while checking the installed game app*, which ③ treats as a lost provider and waits for the same provider; only a completed check against a live worker can report a different app, and an unfinished check never counts as a match (2026-11-12).

## [S1] Problem

The Android patcher needs a second app, Shizuku, installed, started and authorized before it can do
anything. The goal is one app instead of two; Shizuku stays as a third provider through early testing.
Full statement: the spec's *Problem*.

## [S2] Design

Lives in the spec's *Implementation Decisions* while the work is in flight, and moves here when the
last ticket lands.

## [S3] Out of Scope

Removing Shizuku; hiding root; wireless debugging without Wi-Fi; restoring the original signature on a
phone with a re-signed normal APK; the Windows patcher. Full list: the spec's *Out of Scope*.

### Guarded Android recovery and changed-source readiness (2026-11-12, Pass 1; unverified)

| Boundary | Current source behavior |
|---|---|
| Provider API | `reconcileGameFiles` accepts a duplicate-rejecting, bounded strict policy of original/intended hashes, lengths and explicit absence. Whole audits use a small locked shell loop with policy rows on stdin; file count does not enlarge a `sh -c` argument. Existing `validateGameSnapshot` exact-set/read-back semantics are unchanged. |
| Mutation boundary | Rollback target checks and actual rename/deletion share the provider game lock. Retained-source hash, device temp hash/length, sync, rename and live hash/length read-back remain. Watchdog clearing has its own guarded exact audit. |
| Installed app | Recovery independently audits the actual installed normal/access identity before installing access. Unknown installed APKs pause; emergency normal restoration only replaces the known access APK. Root verifies its pinned installed identity before recovery and installs zero APKs; owner/SELinux handling is unchanged. |
| Retry/Stop | Recovery access audits have durable logical budgets (`recovery_access_audit`, `recovery_rollback_access`), initial plus one. Actual access identity is reconciled before charging a send. Stop permits bounded safety work, never fresh translation; mandatory normal restoration remains available after audit-budget exhaustion. |
| Changed pending source | A changed saved source requires a durable snapshot-bound Downloads finished answer under the same Start. Stable hashes/process closure and Retry supply no readiness proof. The existing download card/dialog asks; no fresh translation writes occur while waiting. Initial explicit Start keeps its inline readiness instruction. |

All new probes are private/fake and unrun. Real provider interruption, shell compatibility/large-policy transport, output parity, EN/ID/large-font UI and reference/UI-string checks remain Pass-2 gates. No new performance or device verdict is claimed.

Linked recovery normal sends also use durable `recovery_normal_restore`, with an independent `recovery_emergency_normal` safety budget. Each permits initial plus one; only explicit Retry re-arms safe recovery scopes, including while Stop remains saved. Exhaustion retains originals and an actionable recovery state. Schema-1 legacy sessions keep their pre-existing safety-only retry behavior; broader legacy retry migration remains a Pass-2 review gate.
