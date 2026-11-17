# 15: Reuse an already signed Windows normal APK

Status: ready-for-agent
Implementation: complete
Verification: pending
Blocked by: 04, 06

## Scope and files

Own `patcher_core.py:prepare_normal_apk/build_signed`, preparation receipt details and signing-count probes. Read architecture APK identity rules and current manifest rename fallback. No signing-key or APK-content expansion.

## Steps

1. Separate `installed_source_requires_conversion` from `prepared_normal_is_signed`. The first describes the phone's source before any local rewrite; it must survive creating a signed local artifact.
2. When manifest rename/debug cleanup already produced the verified signed normal APK, use that artifact for required conversion instead of signing it again.
3. Persist/reuse the signed artifact by source/content/manifest/signing identity and atomic receipt. Incomplete signing output remains non-reusable.
4. Preserve first-setup consent/uninstall recovery and the non-fatal rename fallback. A local signed file cannot falsely imply the phone already has the patcher signature.
5. Measure signing call/byte counts and preparation time for official source, already signed source, rename failure and cache reuse.

## Acceptance

- [ ] Rename+official conversion signs the normal output once, while still requiring proper conversion consent/install.
- [ ] Normal/access signer/debug identities and manifest-only content constraints remain correct.
- [ ] Interrupted/tampered cached signing output is rejected; rename refusal never fails an otherwise valid run.
- [ ] Already-signed no-op preparation does not reinstall unnecessarily after verified identity.

## Checks and handoff

Run Windows recovery/repatch/artifact probes with signing-count assertions and UI-string check if copy changes. Compare APK entry inventory/manifest and installed identity semantics, not necessarily RSA output bytes if the producer is nondeterministic. Real install acceptance remains in 19.

## Stop condition

If cached/local signature facts cannot distinguish phone state from artifact state, keep the safe conversion behavior and reject the optimization.

## Comments

Pass 1 implementation complete, 2026-11-12. Verification pending; all acceptance
boxes remain unchecked. Dependencies 04/06/07 were consumed as implemented
interfaces, not verified behavior. No behavioral, unit, integration, performance,
pipeline, UI-string, reference, staging, device or build probe ran. No real game,
ADB, immutable external baseline/fixture, Android, signing-key or catalog changes;
no commit, release or next-ticket implementation.

| Changed file | Ticket 15 responsibility |
|---|---|
| `app/patcher_core.py` | Explicit installed-source conversion versus signed-local-normal facts; extracted exact consent/install conversion; normal receipt publication and resume before consent; access receipt reuse; one explicitly retained pre-mutation generation can seed a fresh owned generation; signing refuses existing/dangling outputs and nonmanifest replacements |
| `app/windows_checkpoints.py` | `PreparedApks`: bounded commit-last per-role receipt, complete producer/source/manifest/key/cert/output binding; actual unsigned entry inventory comparison at publication AND every consumption; malformed proof is a cache miss; immutable receipt publication |
| `app/patch_session.py` | Narrow APK path guard uses lstat, rejecting dangling links, reparse points, hard links and nonregular files before pull/copy/sign |
| `tools/research/check_windows_signing.py` | 18 private generated signed-APK probes, authored only; real binary manifest/v2 fixtures; counted signer input bytes/calls/time and preparation/reuse elapsed time; explicit unsupported-host symlink skip |
| `tools/research/check_windows_recovery.py` | Recovery suite includes the new signing probe class |
| `docs/features/standalone-patcher-app.md`, `docs/features/patch-speed.md` | Current preparation boundaries and unrun safety/performance gates; historical Android measurements remain separate |
| This ticket | Implementation/verification split and exact handoff |

| Check actually run | Result |
|---|---|
| Python 3.12 AST parse + module imports | Passed on Python 3.12.10. Final command parsed/imported patcher_core, windows_checkpoints, patch_session, check_windows_signing and check_windows_recovery. No fixture setup, unittest loader, entry point, producer computation, ADB or pipeline invoked. |
| Earlier AST/import check | Passed for the same list excluding patch_session before the narrow link fix; superseded by the final five-module check. |
| Signing/recovery/repatch/artifact probes; actual-APK content/timing controls; frozen source/build/device cycles | NOT RUN under the two-pass override. No new safety/count/timing acceptance claim. |

The exact final syntax/import command, from the repository root, was:

```powershell
.venv/Scripts/python.exe -c "import ast, importlib, pathlib, sys; print(sys.version); names=['app/patcher_core.py','app/windows_checkpoints.py','app/patch_session.py','tools/research/check_windows_signing.py','tools/research/check_windows_recovery.py']; [ast.parse(pathlib.Path(name).read_text(encoding='utf-8-sig'), filename=name) for name in names]; sys.path[:0]=['app','tools','tools/research']; [importlib.import_module(name) for name in ['patcher_core','windows_checkpoints','patch_session','check_windows_signing','check_windows_recovery']]; print('Syntax and imports passed; no probe entry point invoked')"
```

### Safety/API handoff to 16 / Pass 2

| Boundary | Contract / remaining evidence |
|---|---|
| Ordinary official conversion | Ticket 04 already signs normal once; this change does not invent a fresh-run duplicate-sign saving. Official source still needs exact one-use data-loss consent/uninstall recovery. Local signing never proves phone conversion. |
| Receipt | `normal-preparation-receipt.json` / `access-preparation-receipt.json`, schema 1, committed marker, run id, complete canonical input key/identity, output full APK identity and unsigned content key. `_publish` provides atomic durable read-back; receipt is written last. No mutable journal belongs in an output tree receipt. |
| Manifest-only proof | Source/output APK inventories are streamed and bounded to 100,000 entries, rejecting duplicates. Only the current requested manifest and v1 signing records may differ. The consumer recomputes this relationship rather than trusting a self-consistent forged receipt. Full output identity includes exact bytes, package/version/signers/debug flag. |
| Reuse scope | Same owned journal, or the single explicitly retired pre-mutation journal passed by `_restart_preparation`; no loose cache scan, timestamp/size guess or cross-run permission. Current observed phone source must match before copies. New generation copies/reverifies and publishes a new receipt; old recovery identities/files/complete receipts stay untouched. |
| Missing/changed producer | Reuse disabled. Fresh verified normal/access processing remains possible; `verify_prepared` and pinned normal/install/lost-reply safety recovery remain independent of producer discovery. Missing receipt does not destroy recovery material. |
| Stop and consent | Saved Stop with official source still present cancels consistently before producer lookup, dialog or uninstall. New tests assert zero installs/uninstalls and no producer/dialog dispatch. Existing uninstall uncertainty cannot gain another automatic uninstall. |
| Fallback | No reusable access proof retains the existing fresh owned access generation plus exact saved-identity comparison. Serialization mismatch pauses instead of overwriting immutable recovery. Uncommitted signed outputs/receipts are retained and never consumed. |
| Probes authored, unrun | Official single-sign/consent, signed no-op, rename refusal, normal/access cache reuse, torn/tampered receipt/output, missing/changed producer, publication cut, changed source/manifest/key, pre-mutation restart, partial outputs, Stop-before-consent, forged nonmanifest content, dangling links. Generated fixture signing happens outside preparation counts. |
| Measurement gate | New tool prints signer input bytes/calls/seconds plus preparation/reuse seconds when executed. Receipt publication/revalidation adds full source/output reads; actual-APK repeated controls must decide whether the safe shortcut saves time. No measured result yet. |
| Pass 2 commands | Run `check_windows_signing.py`, `check_windows_recovery.py`, `check_windows_repatch.py`, `check_run_artifacts.py`; then matching actual-APK entry/manifest and repeated timing controls, source/frozen checks and separately authorized device interruption/install cycles. No UI copy changed. Real install acceptance remains ticket 19. |

Coordinator source review required and received corrections for independent
source-to-output inventory verification, Stop before official conversion consent,
and dangling-link output rejection. These are source changes plus authored
regressions, not passing behavioral evidence.

Pass 2 (2026-11-12, fsync/Windows fix worker): check_windows_signing "The game app could not be verified" was downstream of the fsync bug (`ApkJournal.update` in `prepare_normal_apk`). 18/18 OK after the `sync_file` fix; no signing change.

Commands (each `.venv\Scripts\python.exe tools\research\<name>.py`, run in this order on Windows 11, Python 3.12; logs `D:\scratch\hok-ac-pass2\logs\<name>.fsync-fix.log`): check_run_artifacts PASS; check_windows_file_transaction 16/16 OK; check_windows_checkpoints 28/28 OK; check_windows_controls 23/23 OK; check_windows_signing 18/18 OK; check_windows_recovery 104/104 OK; check_bridge_continuation 15/15 OK; check_windows_repatch 14/14 OK; check_pristine_delta 15/15 OK; check_mobile_snapshot 8/8 OK. Before the fixes: run_artifacts failed (EBADF), file_transaction 4 failures/1 error, checkpoints 28 errors, controls/signing/recovery errors, bridge 15 errors. Synthetic only; no device, no game data, nothing committed.
