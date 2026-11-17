# 02: Define complete identities and publish verified artifacts

Status: ready-for-agent
Implementation: complete
Verification: pending
Blocked by: 01

## Scope and files

Own new `tools/run_artifacts.py`, new `tools/research/check_run_artifacts.py`, identity packaging in `app/build_exe.py`, Android `EngineAssets.kt`/`android/app/build.gradle.kts`, and a small Kotlin identity/receipt reader if needed. Read architecture sections 1–4 and the `build_patch` docstring. Do not change stage routing or the summary schema.

## Steps

1. Implement versioned canonical identity encoding and bounded manifest validation: relative allowed paths, exact file sets, size/SHA-256, schema/producer identity and explicit optional inputs.
2. Define the architecture's input key excluding run id, timestamps and machine-dependent paths; those belong to provenance. Include action/language/options, source manifest/APKs/delta and all consumed translation/engine/payload code.
3. Extend packaged identity to cover embedded Android bridge, app executable semantics and native codecs. Preserve EngineAssets' existing manifest verification. For Windows, cover source modifications and frozen executable/native dependency semantics; do not use VERSION alone.
4. Provide Python APIs `identity_key`, `publish_receipt`, `verify_receipt` (names may follow local style, semantics stay fixed). Receipt publication verifies artifacts then atomically commits the last marker; readers reject incomplete publication.
5. Use a separate build-receipt file, retaining the existing summary contract. Define equivalent reader behavior with shared tiny JSON test vectors, without introducing a second transformation implementation in Kotlin.
6. Audit freezing/packaging for the new shipping helper. Research probes remain unbundled. Missing complete producer identity disables reuse rather than weakening it.

## Acceptance

- [ ] Changing any consumed catalog/fallback/payload/tool/runtime/bridge/codec input invalidates the key; a changed UI/app build may conservatively invalidate too.
- [ ] Reordering manifest JSON does not change its identity; request/run timestamps do not defeat compatible reuse.
- [ ] Missing/extra/tampered files, links/traversal, unknown schemas and summary-only output refuse reuse.
- [ ] A kill at each publication boundary yields either a valid old/new receipt or no reusable checkpoint.
- [ ] Source and built apps can locate/verify their identity material.

## Checks and handoff

Run `check_run_artifacts.py`, references/staging-contract checks and Android unit/build checks. Add mutation test vectors for every identity component, including same-size modified bytes. Hand off schema/example receipts and exact APIs to 03/08/09/16.

## Stop condition

If a consumed executable input cannot be identified, leave that reuse path disabled and document the gap. Preserve full ordinary operation; never infer equivalence from version, size or mtime.

## Comments

2026-11-11, pass 1: Implementation complete; verification pending. No behavioral, integration, performance or device checks ran. No phone operations, commits or publishing.

| Files | Implementation |
|---|---|
| `tools/run_artifacts.py` | Schema-1 canonical identities; strict bounded duplicate-key JSON; exact size/SHA-256 manifests; portable paths; ancestor links/reparse points and output hard-link refusal; owned attempts; fsync and atomic commit-last receipts. Windows replacement uses MoveFileExW with WRITE_THROUGH. |
| `app/build_exe.py` | Explicitly bundles shipping `run_artifacts`; probes remain unbundled. |
| `android/app/build.gradle.kts`, `EngineAssets.kt` | Producer source fingerprints in packaged engine manifest; full installed APK/split bytes identify DEX/app/coordinator, embedded bridge, packaged Python/native dependencies; extracted engine/native bytes and ABI also identified. Existing payload verification remains. Trusted filesDir is canonicalized once; linked descendants refuse. |
| `ArtifactReceipts.kt` | Equivalent strict canonical identity and read-only receipt verifier; no duplicate transformation pipeline. |
| `tools/research/check_run_artifacts.py`, `tools/research/fixtures/run_artifacts/vectors.json`, `ArtifactReceiptsTest.kt` | Tiny shared canonical/hash/receipt vectors; same-size mutations across source/catalog/fallback/runtime/sprites/app/interpreter/native/frozen bytes; missing/extra/tampered outputs; target errors, path/link/schema refusals; all five publication interruption boundaries with and without an old receipt. |

| Check | Result |
|---|---|
| `.venv\Scripts\python.exe -m py_compile tools/run_artifacts.py tools/research/check_run_artifacts.py app/build_exe.py` | Passed; syntax only. |
| Coordinator: `android/gradlew.bat -p android --offline :app:compileDebugKotlin :app:compileDebugUnitTestKotlin :app:compileDebugAndroidTestJavaWithJavac` | Passed on the then-current implementation, 53 s; no tests. Final target/producer validation edits followed, so final Kotlin compile remains pending. |
| `check_run_artifacts.py`, reference/staging checks, Android unit tests and final builds | Pending pass 2 by the user's two-pass instruction. Acceptance boxes stay open. |

API handoff for 03/08/09/16:

| API / schema | Contract |
|---|---|
| `canonical_bytes(value)`, `identity_key(value)` | UTF-8 JSON, ASCII keys sorted, stable separators, integer-only numbers within ±(2^53−1). Key = SHA-256 of canonical `{schema:1,identity:value}`. Relative path keys use `/`; path metadata, run UUID and timestamps do not belong in semantic identity. |
| `make_input_identity(*, target, request, game, apks, delta, translation, producer)` | Returns schema1 identity. Target requires nonblank package/device/provider and nonnegative integer android_user; provider enumeration stays with session binding. Request carries action, en/id language and all output-affecting options (fit-only/cycle assets included). Game carries complete `files` manifest and readiness evidence. APK/delta absence is explicit null; present records must contain their full byte identities and relevant semantic metadata/bodies. Translation includes selected catalog, fallback, runtime/payload/code identity. |
| `windows_producer_identity(root=None)` / Kotlin `EngineAssets.producerIdentity(context)` | Full byte evidence, or None/null: ordinary verified work continues, reuse disabled. Source: app/tools/resources, complete interpreter/import roots, actual interpreter exe and loaded native/codec/system DLL bytes. Frozen: actual executable, extracted bundle and native bytes. Android: complete installed base/split APKs, engine manifest/extracted bytes, native directory and ABI. No version/size/mtime equivalence fallback. |
| `tree_manifest(root)`, `verify_manifest(root, manifest)` | Exact relative-path → `{size,sha256}` mapping. Reject unsafe names, case collisions, links/junction ancestors, hard-linked output and extra/missing bytes. Root must be trusted; Android callers canonicalize the platform root once. |
| `create_attempt(parent, *, run_id, stage)` | New UUID directory plus durable attempt-owner.json; never deletes/reuses another attempt. Callers own locking, cleanup and retention. |
| `publish_receipt(root, *, identity, run_id, stage, references=None, failpoint=None)` | Stages: prepared/snapshot/pristine/staged/installed. Root is exclusively owned and immutable after publication. Rehashes/syncs all bytes, atomically publishes build-receipt.json last, reads back. Five private hooks: artifacts_verified, artifacts_synced, receipt_synced, receipt_committed, receipt_read_back. |
| `verify_receipt(root, *, identity=None, input_key=None, stage=None)` | Rehashes exact retained set; returns record or raises ArtifactError for missing/malformed/incompatible proof. Never authorizes device mutation. Prefer independently constructed current identity; raw input_key only after external current-input reconciliation. |
| Receipt | Exact fields: schema=1, committed=true, run_id, stage, input_key, producer_key, identity, artifacts, references. References explicitly name summary/delta/manifest, path or null; roles must be distinct. Their digests are in artifacts. No summary-contract changes. Shared vectors contain an example receipt and every referenced payload byte. |
| STAGED publication | Requires summary, final manifest and nonempty delta bytes; Remove explicitly requires delta=null. Final manifest is separate `{schema:1,files:{path:{size,sha256}}}` describing exactly all artifact files except referenced metadata and attempt-owner.json. Translation requires nonempty payload; empty translation outputs conservatively decline reuse while fresh operation remains available. Existing staged-hashes/summary formats stay untouched. |

Remaining caller responsibilities: layout-specific snapshot completeness (map game.files to retained layout, including recovery Watchdog material where touched); independently verify source/readiness and APK/delta semantics; hold producer/artifact inputs immutable; reconcile live inputs after restart; keep authorization outside receipts; retain all recovery references. APK/delta optional records are generic containers, so wrappers must supply and validate complete role-specific evidence. Prepared stages may precede a game snapshot. Inaccessible import/native material, links, unsupported filesystem durability, or incomplete producer evidence must disable reuse, never weaken identity or ordinary recovery. Producer hashing deliberately over-invalidates and is not a speed claim. Full Windows frozen packaging, real Android extraction/native filesystem support and crash durability remain pass-2/release gates.


Coordinator inspection: reviewed shared helper/reader, producer identity packaging and probe/vector sources. Corrected STAGED completeness, trusted Android filesDir alias handling and target field validation before advancing03. `git diff --check` passed. Final post-edit Android compile is running; behavior, actual filesystem durability, frozen/runtime and instrumentation gates remain pending.


Pass-2 review concern (not executed): Kotlin `treeManifest` uses `Files.getAttribute(path, "unix:nlink")`; Windows JVM providers do not expose Unix attributes. The receipt filesystem unit probe runs on Windows and may need a portable implementation or explicit unsupported-filesystem gate while preserving Android alias checks. Do not count compile success as proof of that test.


Final ticket02 post-edit compile: `android/gradlew.bat -p android --offline :app:compileDebugKotlin :app:compileDebugUnitTestKotlin :app:compileDebugAndroidTestJavaWithJavac` passed (BUILD SUCCESSFUL, 30 s). No behavioral tests ran.

Pass 2 fix (2026-11-12): the unix:nlink concern was real (`ArtifactReceiptsTest.receiptReadsSharedBytesAndRejectsMutations` failed on the Windows JVM with `View 'unix' not available`). `ArtifactReceipts` now reads link counts through one internal seam, `linkCount`, used by both `treeManifest` and `verify`; its production default is still `Files.getAttribute(path, "unix:nlink")`, so on Android every receipt and artifact must have exactly one link and an unreadable count throws and refuses (never taken as 1). Only the unit test opts into a host fallback (one link for its fresh files when the host has no unix view). New `unreadableOrSharedLinkCountRefuses` proves a throwing reader, a count of 2, and an aliased artifact beside a single-link receipt all refuse. No other receipt check changed. `:app:testDebugUnitTest :app:assembleDebug :app:assembleDebugAndroidTest` (offline): BUILD SUCCESSFUL, 105 tests, 0 failures.

Pass 2 (2026-11-12, fsync/Windows fix worker): Root cause: `os.fsync` on a file opened read-only (`"rb"`) raises `OSError [Errno 9]` on Windows (FlushFileBuffers needs write access). Fixed with one helper, `run_artifacts.sync_file(path)`: POSIX keeps the old read-only fsync; Windows opens `O_RDWR|O_BINARY` (no create, no truncate, nothing written) and fsyncs; any failure raises. Used by `publish_receipt` (each artifact) and `ApkJournal.update` (each APK). The other fsync sites already write or use `rb+` and were left alone; directory sync stays POSIX-only.

Second production fix: `run_artifacts._replace` (MoveFileExW REPLACE_EXISTING|WRITE_THROUGH) failed intermittently with WinError 5 even when nothing else in the process touched the file (single-threaded stress: 4 of 3000 replaces in %TEMP%, from a scanner or indexer holding the fresh file). It now retries only errors 5 and 32 with bounded backoff (20 attempts, about 3.5 s), then raises; the move stays atomic. Stress after the fix: 0 of 3000.

Commands (each `.venv\Scripts\python.exe tools\research\<name>.py`, run in this order on Windows 11, Python 3.12; logs `D:\scratch\hok-ac-pass2\logs\<name>.fsync-fix.log`): check_run_artifacts PASS; check_windows_file_transaction 16/16 OK; check_windows_checkpoints 28/28 OK; check_windows_controls 23/23 OK; check_windows_signing 18/18 OK; check_windows_recovery 104/104 OK; check_bridge_continuation 15/15 OK; check_windows_repatch 14/14 OK; check_pristine_delta 15/15 OK; check_mobile_snapshot 8/8 OK. Before the fixes: run_artifacts failed (EBADF), file_transaction 4 failures/1 error, checkpoints 28 errors, controls/signing/recovery errors, bridge 15 errors. Synthetic only; no device, no game data, nothing committed.

Pass 2 instrumentation fix (2026-11-12): production bug, release-blocking. On a real phone (f15a72e, Android 12) the app process sees `filesDir=/data/user/0/dev.halixm.hokacepatcher/files` but `canonicalPath=/data/data/dev.halixm.hokacepatcher/files` (measured by `RunStoreProbeTest.privateRootTrustsOnlyThePlatformAlias`). `PatchCoordinator.sessions`, `PristineDelta.directory` and `RecoveryStore.root` were built from the raw `filesDir`, so `SessionJournal.resultRoot`/`redownloadPlanRoot` refused every pinned build attempt or plan with `Private path alias`, and the `RunStore.safe(context.filesDir.canonicalFile, ...)` / `ArtifactReceipts.safe` checks on session, pristine and recovery files would refuse as escaped. Fix: new `RunStore.privateRoot(context)` canonicalizes `filesDir` once and trusts only the platform's own alias at or above the app data folder: every folder from `dataDir` down to `filesDir` must be unlinked, and the canonical files folder must equal the canonical data folder plus the same relative path (a linked files folder, a folder outside the data folder, or the data folder itself refuse). Those three roots now use it. `RunStore.safe` and `ArtifactReceipts.safe` are unchanged and stay exact. Probes now build their isolated roots from `privateRoot`. Full safe set: 142 run, 115 pass, 26 skipped (missing fixtures), 1 environmental fail; log `D:/scratch/hok-ac-pass2/logs/instr_safe_pass2.log`.

Pass 2 device-cycle fix (2026-11-12, real Android run `63ff0ad4-1b7e-44a8-9ed1-bbbe1dcb63fb` on `f15a72e`): On the first Wireless debugging cycle, `checkpoint_identity` measured `engine_root` (`files/engine/f1b2cd13...`) with 12 existing `tools/__pycache__/*.pyc` files (`files_key=b8720fb2...`); `estimate_snapshot_build` then imported `extra_text`, `lineup_codes`, `config_bin`, `pb_text`, writing 4 new `.pyc` files into `tools/__pycache__`, so `_validate_checkpoint_inputs` refused with `ArtifactError: Engine identity changed`. Fix: `android_bridge.py` sets `sys.dont_write_bytecode = True` on import and in `_prepare`, and `EngineAssets.removeGenerated` strips generated `__pycache__/*.pyc*` and `.partial` files before extraction (refusing unexpected unlisted files). `EngineProbeTest.testEngineTreeStaysImmutableAcrossBuildImportsAndCleansStaleCaches` verifies `files_key` immutability across module imports and cleanup of stale `.pyc`/`.partial` caches without weakening `treeManifest`.
