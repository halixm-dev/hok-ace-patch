# 14: Skip Android identical writes and duplicate recovery hashing

Status: ready-for-agent
Implementation: complete
Verification: pending
Blocked by: 10, 11

## Scope and files

Own `PatchCoordinator.kt` apply/recovery loops, `GameFileTransaction.kt` rollback verified-originals seam and focused probes/metrics. Read patch-speed feature, architecture trust/write rules and existing expectedApplied/finishApply. Preserve current Windows skip behavior.

## Steps

1. From the just-verified snapshot/current-source manifest and complete staged hash set derive a separate changed-write subset. Compare exact bytes/hash/length, not path/version alone.
2. Write only changed files, but retain ALL staged/restored files in expected final manifest, checkpoint receipt and delta semantics. All-identical payload still needs full result verification/finalization.
3. Pass verified originals from recoverLocked into rollback within that same recovery invocation. Make proof lifetime explicit; discard on restart, source mutation or an invalidating operation. Preserve standalone rollback verification.
4. Keep per-write source verification, device temp/live read-back and complete applied-layer validation. Do not reuse in-memory trust across process death.
5. Record original/planned/written/skipped bytes/files and original-hash passes; compare with the pre-optimization control.

## Acceptance

- [ ] Same-input repeat writes fewer files/bytes when actually identical, without shrinking expected output/delta.
- [ ] Corrupt retained/current file cannot be skipped; missing/extra/tampered file blocks completion.
- [ ] Recovery hashes originals once per valid invocation, but freshly revalidates after restart.
- [ ] Interrupted apply/rollback, Remove and all-identical cases preserve final hashes/counts and APK verification.

## Checks and handoff

Run FullCoordinatorProbeTest, CoordinatorRecoveryProbeTest, RemovalRollbackProbeTest, transaction probes, unit/build checks and relevant bridge checks. Compare output/summary/delta with controls and count calls. Add observations to patch-speed feature; real timing goes in lab notebook only when measured.

## Stop condition

If proof lifetime is ambiguous, retain the verification. Output or recovery regression rejects the shortcut.

## Comments

Pass 1 implemented. Acceptance remains unchecked; no behavioral, unit, integration, performance, device, UI-string, reference or staging check ran for ticket 14.

| Area | Files and change |
|---|---|
| Apply/recovery | `PatchCoordinator.kt`: independent full-source audit, exact changed-write subset, complete expected/final/delta semantics; one originals proof per recovery invocation; saved final-normal shortcut removed; restart live audit required; durable Stop selects cancelled/stopped_consistent after forward finalization. |
| Transaction | `GameFileTransaction.kt`: opaque owner/generation/attribute-bound proof, single consumption, fresh standalone verification; staged source hashes remain checked. Whole-state rollback audit; only journal-touched staged package paths mutate. Explicit staged creations are deleted on rollback. |
| Durable state | `SessionJournal.kt`: attempted paths and Watchdog touch intent survive lost replies/outcome changes; reset only on a consistent new continuation. `RunStore.kt`: snapshot-bound source-download answer and bounded safety-access attempt seams. |
| Provider | `IPrivilegedDeviceService.aidl`, `PrivilegedDeviceService.kt`, new `RecoveryFilePolicy.kt`: bounded duplicate-rejecting before/after/explicit-absence policy; whole audit rows on stdin; target guard and actual rename/delete share game lock; Watchdog exact guard; existing exact validator unchanged. Root owner/SELinux helper unchanged, no Root installs. |
| Readiness UI | `MainActivity.kt`: existing download card/dialog handles changed-source readiness via saved action; existing copy/layout/theme reused. Open game checks pending recovery/emergency first. Stop/Retry cannot answer downloads. |
| Metrics | `RunMetrics.kt`: full original/planned/written/skipped files/bytes and original hash passes; latest recovery pass count in journal. Acknowledged write count intentionally excludes lost replies. |
| Probes | `TransactionProbeTest.java`, `FullCoordinatorProbeTest.java`, `CoordinatorRecoveryProbeTest.java`, `RemovalRollbackProbeTest.java`, `RunStoreProbeTest.kt`; new `PrivateRecoveryPolicy.java`, `RecoveryPolicyProbeTest.kt`. `ApkPreparationProbeTest.java` adds unsupported new method for its no-game-files fake. |
| Docs | `docs/features/patch-speed.md`, `language-switch.md`, `android-shell-providers.md`: behavior, trust lifetime, safety corrections and unrun gates. |

Authored controls: all-identical/changed full manifests; corrupt current/retained bytes; transaction-scoped/consumed proof and one recovery hash pass; repeated interruption; newer/missing/extra bytes refusal; update between audit and rename; created-file rollback; Remove changed subset; full metrics; strict malformed/duplicate/float policy; 8192-file stdin transport construction; saved final-normal changed layer; unknown installed APK refusal; Stop at normal audit; source-download answer binding/Stop; durable safety retry exhaustion. Existing fixtures requiring normal/access/full controls remain explicit unavailable gates if absent.

Checks: first compile-only Gradle invocation passed (BUILD SUCCESSFUL, 2m15s): `android/gradlew.bat -p android --offline :app:compileDebugKotlin :app:compileDebugUnitTestKotlin :app:compileDebugAndroidTestJavaWithJavac`. Final compile after all probe/source edits and whitespace result recorded below. No test task, adb, game build pipeline or live UI ran.

Handoff: ticket 15 owns Windows signing reuse, untouched here. Ticket 16 must keep restart independent live audits and full intended manifests; no installed-no-op receipt implemented here. Broader legacy recovery retry/installer policy remains Pass-2 review scope; the added access-audit sends use stable budgets and refuse unknown installed identities. Mandatory normal safety restoration remains available, and Root remains zero installs. Ticket 17/18 staging/mixed-package logic untouched. All acceptance, private probes, full parity, provider/device cycles and comparative measurements remain pending.


Review corrections: linked ordinary recovery normal sends now use durable `recovery_normal_restore`; emergency restoration has its independent `recovery_emergency_normal` budget. Both reconcile actual normal/access before sends, permit Stop safety work, and allow initial plus one only. Explicit existing Retry alone re-arms those safe scopes (including a stopped unresolved run), preserving Stop/uninstall/Re-download budgets. Reopen never re-arms them. New source readiness and retry controls are authored in `RunStoreProbeTest`.

Remaining migration boundary: schema-1 legacy sessions have no RunStore authorization/attempt record, so their pre-existing safety-only install retry policy is unchanged. They never gain fresh automatic patch authority; any broader legacy retry migration is an explicit Pass-2/ticket-19 review gate. No installed-no-op16 implementation or real provider correctness claim is made.

Intermediate final compile failed only on missing `java.nio.file.Files` import in the newly authored TransactionProbeTest; fixed. This was a compile-only failure, not a test run. Latest compile result follows.


Final allowed checks: Gradle `--offline :app:compileDebugKotlin :app:compileDebugUnitTestKotlin :app:compileDebugAndroidTestJavaWithJavac` **BUILD SUCCESSFUL (38s)** on the final source and authored probes (JDK21/SDK paths from coordinator; existing cache through approved escalation). Prior post-import-fix compile also passed (1m42s). `git diff --check` **exit 0**, only pre-existing LF/CRLF warnings. No test tasks or behavioral/static-policy scripts ran. Implementation is complete, verification pending, acceptance unchecked. No source edits planned after this handoff.

Pass 2 instrumentation (2026-11-12): `TransactionProbeTest.testProofIsTransactionScopedAndRecoveryHashesOnce` (2 vs 3 writes) and `testExplicitlyCreatedStagedFileIsDeletedByRollback` (1 vs 2) were test bugs: rollback always ends by restoring Watchdog from the snapshot (unchanged since HEAD), which the fake device counts as a write. Production is unchanged; the fake now records written paths and the probes assert the exact sequence (`1.db` apply, `1.db` rollback, `Watchdog/list.db`; and created file, `Watchdog/list.db`), so an untouched shard or `.info` write would still fail. `JournalProbeTest` used the old `relative` intent key; production's `intent` requires `path` with a writable game path, so the probe now passes `path`. Its `.info` rejection was stale since 1e11802 (Re-download makes a package's own `.info` writable); it now accepts `packages/1/1.info` and rejects `packages/1/2.info` and `packages/1/1.info.bak`. Safe set: all transaction/journal/removal probes pass.

**2026-11-18 — migration boundary closed: no migration.** Reviewed under ticket 19; the user chose to keep the policy as it is ("Yes, record it"). Schema-1 sessions keep their safety-only recovery with no RunStore budget. Evidence and reasoning: lab notebook, 2026-11-18 legacy-retry review.
