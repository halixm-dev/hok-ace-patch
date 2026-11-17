# 04: Verify Windows installs and recover first setup durably

Status: ready-for-agent
Implementation: complete
Verification: pending
Blocked by: 03

## Scope and files

Own `app/patcher_core.py:prepare_normal_apk/prepare_debuggable_apk/restore_normal_apk/Adb.install`, narrowly needed `app/apk_tools.py` identity helpers, `app/patch_session.py` setup/install records and probes. Read ADRs 0001/0002, architecture sections 2–3/5–6 and existing Android setup/verifier for reference. Signing performance is ticket 15.

## Steps

1. Identify prepared/installed source/normal/access APKs by content plus package/version/signer/debug state. Verify actual installed bytes independently after install and after ambiguous replies; ADB Success is not completion.
2. Replace size/mtime cache eligibility with verified content records. Pin normal/access material referenced by unresolved work so caches cannot overwrite or delete it. Never treat installed access bytes as normal input.
3. Journal access/normal install intent before dispatch. On failure preserve a blocking restoration state and recovery path; final normal failure must prevent `Patcher.run`/GUI success.
4. Before destructive setup, persist verified saved normal APK, source identity, exact informed consent and uninstall intent. The saved normal must be installable without the original game remaining present.
5. Recover before ordinary installed-game/fresh-build-space checks: absent game + matching uninstall intent → install/verify saved normal; normal already present → acknowledge; original still present → fresh consent; unrelated app → refuse. Never repeat uninstall automatically.
6. After signature conversion, show required in-game download readiness and do not translate until it is resolved. Keep rename failure non-fatal as AGENTS.md requires; no extra APK content changes.

## Acceptance

- [ ] Failed final restoration yields recovery_required/attention, never translated/success/Open game.
- [ ] “Install committed then transport failed” is recognized by installed identity before any retry.
- [ ] First-setup interruption in the uninstall/install gap recovers despite missing game; uninstall count never exceeds its exact consent scope.
- [ ] Different/tampered APK, signer or debug flag refuses success even with Success text.
- [ ] Recovery-only normal install can proceed with enough recovery space but less than fresh-run 8 GiB.

## Checks and handoff

Run Windows recovery/repatch/artifact probes and UI-string check. Cover both already re-signed and official-source APKs using fixtures. No destructive live setup test here; ticket 19 owns that gate. Record install identity observation and precise blocking result contract for 05–07.

## Stop condition

If installed identity cannot be established, retain material and report attention. Never change signing keys or silently uninstall a different/source APK.

## Comments

Pass 1 implementation complete; verification pending. No behavioral, integration,
performance or device checks; no phone operations, commits, releases or subagents.
Acceptance remains open. Coordinator owns final routing/builds.

| Changed files | Purpose |
|---|---|
| `app/apk_tools.py` | Complete APK byte/package/version/signer/debug identity; bounded binary manifest/signature parsing and normalized malformed-input failures. |
| `app/patch_session.py` | Strict run/target-bound ApkJournal, immutable role records, pinned material, install intents/outcomes, exact setup approval UUID/time/consequence digest and consumed scope. |
| `app/patcher_core.py` | Independent installed-APK observations; fresh verified preparation; journal-before-install/uninstall; lost-reply reconciliation; blocking final normal restoration; missing-game setup repair before fresh checks; download readiness. |
| `resources/ui/strings.json` | Five EN/ID keyed APK/setup/recovery failures. |
| `tools/research/_windows_fake_device.py` | Explicit installed-byte/package/pull/hash/install grammar and wrong-commit fixture option; no blanket success. |
| `tools/research/check_windows_recovery.py` | Converted normal-restore and setup-gap expectedFailures to ordinary assertions. Added small real binary-manifest/v2-signed APK fixtures, official-source and patcher-signed preparation, wrong signer/debug/tamper, low-space repair, lost reply and no loose-file authority probes. |
| `docs/features/standalone-patcher-app.md` | APK/setup boundaries and pending verification documented. |

| Check actually run | Result |
|---|---|
| `.venv/Scripts/python.exe -m py_compile app/apk_tools.py app/patch_session.py app/patcher_core.py tools/research/_windows_fake_device.py tools/research/check_windows_recovery.py` | Passed on final Python edits. Syntax only. |
| Windows recovery/repatch/artifact probes; UI-string check; behavioral/device checks | Deferred to Pass 2 by user instruction. |

| API for 05–07 | Contract |
|---|---|
| `apk_tools.apk_identity(path)` | Exact size/sha256/package/version/signers/debuggable from bytes; signer certificate SHA-256 list. Missing signer/unsupported manifest fails closed. Does not confer install authority or replace Android signature validation. |
| `Adb.installed_identity()` | Independently enumerate fixed package/user0, resolve one /data/app APK, hash before/after pulling, read bytes/metadata, confirm stable path. Returns None only for an empty successful package enumeration; unknown identity is keyed failure. All commands use saved serial/profile. |
| `Adb.install(path)` | Inspect expected file, dispatch once, audit actual installed bytes even after transport exception. Matching exact identity succeeds; Success text alone does not. Does not own durable intent; use install_prepared. |
| `ApkJournal(owner,create=False)` | children.apk_session binds sessions/UUID/apk-journal.json and source/normal/access APKs. Run/target/schema/identity/consent validated; normal must be nondebuggable. APK identities immutable; publication syncs pinned bytes before acknowledgment. Recovery does not load a translation engine. |
| `Patcher.verify_prepared(role)` | Rehash/parse pinned APK against journal; reject links/reparse/hard links, tampering or missing proof. |
| `Patcher.install_prepared(role,operation)` | Persist apk_OPERATION attempt and exact intent before dispatch; reconcile first and after ambiguity. Outcomes intent/verified/attention. Expected live identities only; absent allowed solely for normal with setup install intent. Used budgets preserved. Coordinator supplies distinct operation names for distinct cycles. |
| `Patcher.restore_normal_apk()` | Uses final_normal; clears debuggable_installed only after proof. Failure raises error_normal_recovery and lifecycle=attention, blocking run/GUI success. |
| `Patcher.recover_first_setup()` | Requires owned journal/scoped consumed uninstall intent; never uninstalls. Repairs absent game using saved normal without fresh 8 GiB checks; acknowledges normal; original gives error_setup_consent; other bytes give error_apk_identity. Leaves waiting_update, no translation. |
| `Patcher.finish_setup_update()` | Explicit download confirmation, normal identity verification and force-stop, then setup ready/lifecycle preparing. 06 must wire saved readiness routing before translation. |
| `OwnedRun.begin_attempt(...,safety_recovery=True)` | Bounded non-destructive recovery may run despite Stop/attention, so normal restoration remains possible. Destructive work never bypasses prohibition; resolved runs refuse. Caller must establish authority from the saved journal. |

Remaining concerns for Pass 2: run all authored probes/UI-string check; verify real installed-APK path/signer formats, storage/filesystem durability and process cuts, frozen dependencies/runtime packaging, repeated disconnect and installer consent popups. Fresh preparation deliberately declines cross-run APK output reuse; access preparation reuse is same-invocation only until a complete producer receipt exists. Incomplete producer identity never weakens ordinary verified work or pinned normal recovery. Unresolved APKs stay pinned; ticket06 retains them through file/delta finalization. Preparation restart currently reports attention for uncommitted output rather than deleting/reusing it. General pending patch runs still block fresh Start; only validated first-setup safety repair is routed here. No baseline/parity fixture was modified or executed.


Final static checks: Python 3.12 py_compile passed for all five changed Python files. Scoped git diff --check passed (only the existing LF/CRLF normalization warning). No behavioral probe, UI-string checker, build, phone command or mutation was executed.

Coordinator review: inspected identity bounds, consent consumption, install reconciliation, restoration failure and realistic probe assertions. Required parser/consent/recovery corrections applied. Acceptance gates remain open for Pass 2.

Pass 2 (2026-11-12, fsync/Windows fix worker): check_windows_recovery: 104/104 OK after the shared fsync/replace fixes and the lock-holding-child teardown wait (test only).

Commands (each `.venv\Scripts\python.exe tools\research\<name>.py`, run in this order on Windows 11, Python 3.12; logs `D:\scratch\hok-ac-pass2\logs\<name>.fsync-fix.log`): check_run_artifacts PASS; check_windows_file_transaction 16/16 OK; check_windows_checkpoints 28/28 OK; check_windows_controls 23/23 OK; check_windows_signing 18/18 OK; check_windows_recovery 104/104 OK; check_bridge_continuation 15/15 OK; check_windows_repatch 14/14 OK; check_pristine_delta 15/15 OK; check_mobile_snapshot 8/8 OK. Before the fixes: run_artifacts failed (EBADF), file_transaction 4 failures/1 error, checkpoints 28 errors, controls/signing/recovery errors, bridge 15 errors. Synthetic only; no device, no game data, nothing committed.
