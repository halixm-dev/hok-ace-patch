# 01: Make interruption probes reproducible

Status: ready-for-agent
Implementation: complete
Verification: pending
Blocked by: none

## Scope and files

Own `tools/research/check_windows_repatch.py`, new `tools/research/check_windows_recovery.py`, small reusable fake transports/fixtures under `tools/research/`, and fixture loading in affected Android `src/androidTest` coordinator/preparation probes. Read [evidence](../evidence.md), [validation](../validation.md) and the existing probe implementation before running it. Production behavior changes belong to later tickets.

## Steps

1. Run the three starting Python checks and Android unit/build checks from validation; record baseline outcomes and unavailable fixtures.
2. Change Windows FakeAdb to represent host upload, remote upload area, destination temp and live files separately. Shell cp/rename/hash/sync operations must affect the correct storage. Preserve existing repatch assertions.
3. Add named fault hooks before/after journal write, upload, temp copy/hash, rename, acknowledgment, read-back, install commit and finalization. Track calls and actual bytes; an installer can commit and then lose its reply.
4. Add regression scenarios demonstrating current normal-restore false success, first-setup missing-game gap, wrong-device reuse and direct-copy interruption. Keep these explicitly expected-current-failure until the relevant ticket replaces the expectation; keep baseline checks runnable.
5. Replace hard-coded Android old-game fixture hash/file-count assumptions with validated fixture descriptors or generated app-private fixtures where possible. Verify descriptors, normal/access identities and exact manifests before use. Preserve the production verifier's strictness.
6. Add an explicit fixture preflight/refusal for checks that still need real external material. Document the exact input missing, not just “test unavailable.”

## Acceptance

- [ ] Existing delta/repatch/snapshot checks still exercise their original behavior.
- [ ] A truncated fake live copy and lost commit reply are observably different; probes would catch false success.
- [ ] Fake phone mutation never reaches a real game; fixtures are outside shipping imports/bundles.
- [ ] Portable Android checks stop depending on another phone's fixed APK hash; unavailable full fixtures are explicit.
- [ ] Baseline commands/results and open gates recorded under Comments.

## Checks and handoff

Run the three starting Python checks, the new recovery probe, and affected Android unit/instrumentation probes where available. Build app/test APKs. Hand off the failpoint names/call counters used by tickets 03–12. Do not mark a known red assertion as newly fixed here.

## Stop condition

If a fixture probe may uninstall a real game, defer that live case to ticket 19's consented device cycle. Do not relax production checks to satisfy a test.

## Comments

Pass 1 implementation complete; **all behavioral, baseline, integration, performance and device checks are deferred to Pass 2 by user instruction**. No phone command, installer, real game mutation or commit was performed.

| Changed files | Purpose |
|---|---|
| `tools/research/check_windows_repatch.py`, `_windows_fake_device.py` | Preserve original repatch assertions; isolate host input, uploaded bytes, destination temps and live bytes; reject unknown fake commands. |
| `tools/research/check_windows_recovery.py` | Four expected-current-failure assertions call actual `Patcher` methods: normal restore must block, missing first-setup game must recover, wrong serial must refuse old session reuse, interrupted direct copy must retain originals. Separate fake self-checks cover temp/rename and commit-before-reply behavior. |
| `tools/research/make_probe_fixture_descriptor.py` | Host-only descriptor generator for explicitly supplied APKs/identities and optional full source/output fixtures outside the repo; no phone API. |
| Android `PrivateProbeFixtures.java` | Bounded app-private descriptor preflight; independent full APK identity and exact ZIP-entry/source manifests. Missing inputs report an explicit JUnit assumption; malformed inputs fail. |
| Android `ApkPreparationProbeTest.java`, `CoordinatorRecoveryProbeTest.java`, `CoordinatorSourceGuardProbeTest.java`, `FullCoordinatorProbeTest.java` | Replace old fixed APK hashes/paths and full-fixture file/count constants with validated descriptor evidence. Production verifier unchanged. |
| `README.md` | Add offline interruption-check command. |

| Check actually run | Result |
|---|---|
| `.venv/Scripts/python.exe --version` | Python 3.12.10 |
| `.venv/Scripts/python.exe -m py_compile tools/research/_windows_fake_device.py tools/research/check_windows_repatch.py tools/research/check_windows_recovery.py` | Passed |
| `.venv/Scripts/python.exe -m py_compile tools/research/_windows_fake_device.py tools/research/check_windows_repatch.py tools/research/check_windows_recovery.py tools/research/make_probe_fixture_descriptor.py` | Passed |
| Starting delta/repatch/mobile-snapshot checks; new recovery check; Android unit/instrumentation | Not run: deferred to Pass 2. No behavior baseline result claimed. |
| Android app/test compile/build | Delegated to coordinator for consolidated build; SDK/JDK found by coordinator. No local Gradle invocation. |
| `git diff --check` | Passed (whitespace only; no behavior executed). |

| Handoff API | Meaning |
|---|---|
| `Faults(cuts={point: occurrence})` | One-shot named failure; `calls[point]`, ordered `events`, `bytes[operation]` observe attempted and completed effects. |
| `before_` / `after_` + `journal_write`, `upload`, `temp_copy`, `temp_hash`, `rename`, `acknowledgment`, `read_back`, `install_commit`, `finalization`, `live_copy`, `sync` | Full exported `FAILPOINTS` list. `Faults.operation(name, callback)` brackets future journal/finalization code without research imports in production. |
| `FakeAdb.copy(..., temporary=True)`, `.rename(...)`, `.digest(..., temporary=True)` | Temp-copy/verify/commit/read-back fixture operations. After-rename loss leaves new live bytes and no acknowledgment. |
| `FakeAdb.installed`, `.install_attempts`, `.pushed`, `.commands`, `.tars` | Actual synthetic installed APK bytes and transport counts. After-install-commit loss leaves APK installed despite raised reply failure. |
| `partial_live_copy=N`, `fail_after=N`, `serial=...` | Legacy truncation, existing push-count interruption and target identities. Upload itself cannot change live files. |

Fixture preflight: the four affected Android probes require target app-private `files/probe-fixtures/automatic-continuation/fixture.json`, schema 1. `normal` and `access` each contain a relative `path`, full production `ApkIdentity.json()` as `identity`, and exact ZIP-entry SHA-256 map as `entries`. Place those APKs below the descriptor directory. No legacy `control-1402` or `game-access-1402` fallback is attempted. Full coordinator additionally needs `source_root` (relative directory of the package layer), exact `source_files` map (relative package paths to SHA-256), `staged_hashes` map, and `expected_counts` (`text_tables`, `applied_textures`, `skipped_tables`, `skipped_textures`). Normal/access package, version, signer and debug flags are independently checked before any coordinator operation.

Missing external material: no matching game normal/access APK pair, independently captured identity JSON, full pristine package fixture, reference staged manifest or expected-count descriptor was supplied for this new descriptor location. Use the generator with `--root <external-fixture-dir> --normal <normal.apk> --normal-identity <normal-identity.json> --access <access.apk> --access-identity <access-identity.json>`; add all of `--source-root`, `--staged-hashes`, `--expected-counts` for full coordinator checks. The generator refuses existing output and does not copy/install material. Fixture placement/device execution remains a separately controlled gate.

Known limits/open gates: expected failures document current gaps, not fixes. Ticket 04 must evolve the missing-game regression to create its valid durable setup record once that schema exists (the baseline currently has only loose cached APKs). Tickets 03–07 replace expected-current-failure expectations as their guarantees ship. Future production shell protocols must extend the strict fake command grammar explicitly. Other Android probes outside these four retain existing fixture dependencies and require scope review before any instrumentation. Baseline archive pointer and consolidated build results belong to coordinator.md. Real device cycles remain ticket 19 and cannot be replaced by these probes.


Coordinator review: inspected all changed/new fake transports, descriptor/preflight and probe callers; scope remains test-only. Consolidated Android compile passed: `android/gradlew.bat -p android --offline :app:compileDebugKotlin :app:compileDebugAndroidTestJavaWithJavac` (SDK/JDK process env, approved Gradle cache access). BUILD SUCCESSFUL in 2m19s. No behavioral/instrumentation tests run. Acceptance remains pending.

Pass 2 (2026-11-12, fsync/Windows fix worker): Commands (each `.venv\Scripts\python.exe tools\research\<name>.py`, run in this order on Windows 11, Python 3.12; logs `D:\scratch\hok-ac-pass2\logs\<name>.fsync-fix.log`): check_run_artifacts PASS; check_windows_file_transaction 16/16 OK; check_windows_checkpoints 28/28 OK; check_windows_controls 23/23 OK; check_windows_signing 18/18 OK; check_windows_recovery 104/104 OK; check_bridge_continuation 15/15 OK; check_windows_repatch 14/14 OK; check_pristine_delta 15/15 OK; check_mobile_snapshot 8/8 OK. Before the fixes: run_artifacts failed (EBADF), file_transaction 4 failures/1 error, checkpoints 28 errors, controls/signing/recovery errors, bridge 15 errors. Synthetic only; no device, no game data, nothing committed.

Fake/probe seams (test-only): `_windows_fake_device.FakeAdb` now has the production `boundary` seam (called before shell/run/exec_out/exec_out_to_file, as `Adb.run` does). The controls fixture binds it only while `_dispatch` runs. The manual `case.setUp()` fixture in controls registers cleanups first, so a failing setUp still releases run locks.
