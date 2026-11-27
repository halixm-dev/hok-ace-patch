# Handoff

Where the migration stands, for the next session. `MAP.md` holds the plan and each unit's state;
this file holds what is not in it.

## Wave 0 (2026-11-27)

- **Workspace:** `rust/hokace/` (Cargo workspace, toolchain 1.99.1 with `aarch64-linux-android`,
  `unsafe_code = "forbid"`). One member so far, `core` (`hokace-core`). The rust-anything crates in
  `rust/*-rs` stay outside it, each with its own lockfile and toolchain pin.
- **Pinyin table:** `rust/generators/pinyin_table.py` writes `rust/hokace/core/data/pinyin.tsv.gz`
  (89,034 lines; `--check` proves it current). The Rust port of `extra_text.pinyin_name` still needs
  pypinyin's mmseg cut over the `P` lines (wave 3).
- **App case:** `rust/harness/pipeline_case.py` records an offline pipeline run as a manifest of each
  output file's size and SHA-256 plus the staging summary, and compares two. The baselines are
  `rust/app-cases/pipeline/en.json` and `id.json`, on the 2026-11-25 dump with its normal APK
  (`D:\HOK ACE Patcher Data\update-20261125`, not in the repo). Each was run twice and compared
  identical, so a Rust run is held to them byte for byte. `--command` runs another pipeline with the
  same arguments.
- **Android wheels:** `android/native/build_rust_wheels.py` cross-builds the crates in its `CRATES`
  for `aarch64-linux-android` against Chaquopy's `libpython3.12.so`, with
  16 KiB load alignment, as `cp312-cp312-android_24_arm64_v8a` wheels. `tools/ci/build_android.ps1`
  runs it; `android/app/build.gradle.kts` installs the wheel in the full-codec build. A new unit
  crate the Android app loads joins `CRATES` and the Gradle pip block.

## Not done in wave 0

- App cases for `--selftest`, `--smoketest` and `--pc-selftest`: not recorded. `--selftest` covers
  what the pipeline case covers; the other two join with waves 6 and 7.
- The `stale_blocks_rs` wheel is in the debug APK (`requirements-common.imy`, 16 KiB aligned) but not yet run on a phone: the first device
  cycle (ADR-007) checks that `tools/block_scan` loads it there rather than falling back to Python.
- The Android workflow installs the toolchain `rust/stale-blocks-rs` pins; a second crate with
  another pin needs its own install step.

## Watch out

- `rust-anything enable` after `record` leaves the recording stale (the fingerprint covers the
  switch-on block). Re-record with `RUST_ANYTHING_MODE=old` and `--inputs <crate>/test-inputs.jsonl`.
- A running pipeline holds `rust/stale-blocks-rs/python/stale_blocks_rs/_native.pyd` open, so
  `rust-anything build` and `gate` fail with "Access is denied" until it exits.

## Wave 1, offline checkpoint passed (2026-11-27)

- `hokace-codecs` uses `lz4_flex`, `lz4-pure-rs` HC 12, `ruzstd`, `texture2ddecoder` and `png`.
  `cargo run --release -p hokace-codecs --example corpus -- <index> lz4 zstd stored` matched Python
  on 14,215 LZ4 chunks (including HC 12 bytes), 151 zstd and 2 stored. The index is
  `D:\scratch\rust-port\corpus.jsonl`. `lz4-pure-rs` 0.1.2 has 293 `unsafe` occurrences in its
  source. Its `libc` import in `sys.rs` supplies C type aliases. The workspace's own code forbids unsafe.
- `cargo run --release -p hokace-codecs --example tap -- <tap-dir> ...` replays texture decodes,
  LZ4 writes and PNGs. English is at `D:\scratch\rust-port\tap-en` and the fresh Indonesian recording
  uses the baseline's `clean-game`. The ASTC decoder matches all 124 synthetic HDR fixtures from
  `codec_tap.py --astc-hdr <dir>`, including rounding and signed endpoint deltas. The PNG decoder
  matches all 105 repo PNGs from `codec_tap.py --png <dir>`. See [texture replay evidence](research/texture-codecs.md).
- `hokace-oodle` decodes checksum-free Leviathan and writes stored blocks. The
  `framing` example matched decoded bytes on all 60,684 dump and 108,118 APK chunks.
  The APK index is `D:\scratch\rust-port\wave1-oodle\oodle-apk.jsonl`. See
  [Oodle replay and provenance](research/compression-codecs.md#6-leviathan-port-replay).
- BC7 encoding matched 76,535 PC catalog blocks across both languages and 2,013 synthetic blocks
  byte for byte. The rebuilt Python extension passed the existing 20,057-case replay with
  `--final`. See [BC7 replay evidence](research/texture-codecs.md#6-experiments).
- **ASTC encoding is ported (ADR-026).** `hokace-astcenc` translates the wheel's Arm astcenc
  (`.scratch/astcenc-port/plan.md`). `cargo run --release -p hokace-astcenc --example replay --
  <tap-dir> --threads 12` matched every encode call of `tap-en` (1,272) and `tap-id-clean` (1,275)
  byte for byte, also at 1 and 3 threads. Speed on the English calls: 13.4 s at 12 threads and
  49 s at one (Indonesian: 13.2 s and 48 s), against the AVX2 wheel's 12.4 s and 32.8 s. The
  first port took 25 s and about 120 s. On x86_64 the 4-lane layer runs SSE2 kernels through
  `safe_arch` (`astcenc/src/lanes.rs`), each tested against the scalar definition. On the first
  20 calls at one thread it takes 12.2 s, against Arm's own builds' 10.8 s (SSE2) and 7.1 s
  (AVX2). Most of the gain came from inlining the bilinear infill closures. aarch64 runs the
  plain-Rust lanes, which LLVM vectorizes: on a Redmi Note 9 Pro
  (`rust/harness/phone_astc_timing.py`), the English tap takes 97.6 s on one fast core, against
  91.3 s for Arm's NEON build and 102.3 s for its scalar build, both with the Android wheel's
  flags. It takes 38.7 s at 8 threads, and every call matches the Windows bytes. NEON kernels
  would gain at most about 7%, and they need `unsafe`, which the workspace forbids. Going past
  AVX2-wheel parity at one thread needs 8-wide loops and runtime CPU dispatch.
- `hokace-codecs` encodes ASTC through it (`astc_encode::AstcEncoder`). The encoder keeps one
  context per footprint, as `mobile_graphics._contexts` does, and refuses input whose size isn't
  `width * height * 4`. `cargo run --release -p hokace-codecs --example tap -- <tap-dir>` now
  replays `encode_astc` too. Every codec call matched in both taps: English 1,272 encodes, 26
  ASTC and 1,200 PC decodes, 466 LZ4 writes; Indonesian 1,275 encodes and 469 LZ4 writes. 
- The Windows app encodes ASTC through it: `crates/hok_astc` (PyO3) wraps `AstcEncoder`,
  `app/build_exe.py` builds it into `build/native/hok_astc.pyd`, and `mobile_graphics._encode_astc`
  uses it when it loads and the wheel otherwise (`HOK_ASTC_ENCODER=native|python` forces one).
  Through `_encode_astc` both taps match (1,272/1,272 and 1,275/1,275), `check_graphics.py` passes
  with native forced, and the frozen `--smoketest` checks it loaded and matches the wheel. Speed is
  the wheel's (16.5 s against 16.1 s on the English tap). Android keeps the wheel: the phone
  wheel's bytes differ (`-ffp-contract=fast`), so switching it needs a device cycle.
- Both offline app cases pass with `HOK_ASTC_ENCODER=native` and `HOK_BC7_ENCODER=native`: the
  English and Indonesian runs on the 2026-11-25 dump compare identical to `rust/app-cases/pipeline/`
  (143 s and 223 s, against the baselines' 178 s and 490 s on a busier machine).
- `android/native/build_rust_wheels.py` also builds `crates/hok_astc` as
  `hok_astc-0.1.0-cp312-cp312-android_24_arm64_v8a.whl` (`hok_astc.abi3.so` at the top level, 16 KiB
  aligned, `PyInit_hok_astc` exported, linked only to `libpython3.12.so`, libdl, libm, libc).
  `build.gradle.kts` does not install it: installing it switches the phone from the `astc_encoder`
  wheel, whose bytes differ, so it waits for a device cycle (ADR-007).
- Upstream quirk kept: `compress_block`'s `static` overshoot is set by the first block the process
  compresses and reused by every later context (`ERRORVAL_OVERSHOOT`). A replay must run its calls
  in the tap's order in one process.
- `crates/hok_codecs` exposes LZ4, zstd, Oodle, ASTC/BC7 decoding, BC7 encoding and PNG decoding. The Python
  patchers select it through `tools/codec_backend.py`. In the binary runtime, `engine_hooks.install`
  redirects the LZ4 calls in the four modules that use it. The app keeps its Python codec
  fallbacks. `HOK_CODECS=native` exposes codec refusals and `HOK_CODECS=python` selects the reference.
  The Windows PC edition uses the full Rust BC7 encoder with the native search selected. The older
  `hok_bc7` extension and etcpak candidate still support source runs without `hok_codecs`.
- The forced-native graphics check found an invalid ASTC weight grid in its unrelated-art fixture.
  The decoder validates block parameters and marks invalid blocks magenta, so the splice can
  refuse the texture. Encoder weight initialization also uses the same arithmetic in debug and
  release builds.
- The ARM64 `hok_codecs` wheel builds, exports `PyInit_hok_codecs`, has 16 KiB load alignment, and
  links to Chaquopy's Python, libdl, libm and libc. Gradle includes it in the full-codec APK.
  Android diagnostics report the active backend. The ASTC encoder wheel remains a separate device
  gate.
- Workspace format, Clippy, Windows tests and Android ARM64 `cargo check` passed. The Python
  apps still drive both pipelines.
- Both forced-native offline app cases matched their baselines. Manifests are
  `D:\scratch\rust-port\wave1-wired\en.json` and `id.json`. In each summary, three
  `source_package` paths record the fresh scratch directory. Replacing those paths with the
  baseline's gave the expected SHA-256 for the summary and every other output already matched.
  The decoder fix also matched all 26 recorded ASTC calls per language.
- The rebuilt Windows exe passed `--smoketest`, including the full Rust BC7 encoder through mode
  7. The forced-native graphics check and BC7 extension replay passed. The Android
  `assembleDebug` and `testDebugUnitTest` tasks passed, and the debug APK passed ELF and ZIP
  alignment checks. The APK contains the exact `hok_codecs` wheel binary and its notices.
  See the [lab notebook](../docs/lab-notebook.md#2026-11-27--wave-1-codec-checkpoint).
- The user approved Wave 2 under ADR-007.

## Wave 2 in progress (2026-11-27)

- The bytecode oracle `rust/harness/runtime_tap.py` records generated wire cases, a read-only game
  scan in each language, catalog validation, QtsVFS readers and PC package hash lookup. It forces
  the Python backend. The Rust workspace's `runtime_replay` example checks the result, error class,
  field bytes and count order each case captures. Generated recordings are under `build/wave2-*`.
- `hokace-core` now reads protobuf varints, localization fields and I18N records. The native table
  translator uses Rust validation and keeps the original field bytes when it carries a field over.
  Cases matched on both game scans (2,578 wire cases and 238 translation calls per language),
  3,676 generated wire cases and 78,258 validation pairs. The PyO3 bridge prepares the text view
  after Python finishes the language-specific catalog edits. The Python scanner and staging code
  still own package discovery, I/O and writes. Source runs fall back when `hok_codecs` is absent.
  The Rust varint encoder accepts unsigned inputs up to 128 bits. All game fields fit.
- The Rust QtsVFS index and slot readers run through the existing engine hook. They use a buffered
  file handle to stay within Android's memory budget. All 21 game database cases matched. Position
  reference search and insertion matched ten synthetic cases, including failed insertion and an
  earlier page retained after a later insertion failed. These helpers remain in the core while the
  installers use the Python implementation. The PC package hash parser matched 17 cases on the
  installed game's read-only internal index and generated fixtures.
- Fully staged English and Indonesian on the 2026-11-25 dump with its normal APK and native readers,
  translator and codecs. Each produced 16 files matching its baseline. The only change was three
  scratch paths in each summary. The manifests are `build/wave2-en-pipeline.json` and
  `build/wave2-id-pipeline.json`. The summary hashes were checked by substituting just those paths
  in the verified Wave 1 summary bytes. No game or phone files were written.
- The rebuilt Windows exe passed `--smoketest`, including a Rust table rewrite and the QtsVFS hook.
  The ARM64 wheel rebuilt and matched the copy in the debug APK. The Gradle build and JVM tests
  passed, as did the APK and ELF alignment checks. No on-device run was made.
- The native reader now extracts stored and LZ4 assets and selects live B-tree slots. All 200 cases
  matched in `build/wave2-qts-extract`, `build/wave2-qts-staged` and `build/wave2-qts-pc`.
  The existing Python selection resolves ties and reports unreadable trees. The package writers
  still use the Python implementation.
- With extraction and slot selection active, all 16 file hashes per language matched after
  substituting the three scratch paths in each summary. See `build/wave2-qts-en-pipeline.json`
  and `build/wave2-qts-id-pipeline.json`.
- The Windows exe passed the extraction smoke check. The Android debug build and JVM test task
  passed. The APK contains the rebuilt ARM64 wheel binary, and its ELF and ZIP alignment checks
  passed. A phone device cycle is pending.
- `hokace-core::catalog` ports the runtime's `Catalog.__init__`, `Catalog.lookup` and `load_catalog`
  (gzip, JSON with key order kept, `int(h, 16)` as Python parses it). `runtime_tap.py --catalog`
  records the runtime's loader on both shipped catalogs, `Catalog(data)` on both as the apps build
  them after `engine_hooks`' supplement, admissions, glossary and English updates, 78 generated
  shapes (every error the runtime raises on purpose, the `KeyError`/`TypeError`/`ValueError` a
  wrong catalog meets, 22 hash spellings, each as a table hash and a graphic hash) and 2,698 lookups: all 2,783 matched
  (`build/wave2-catalog`). `int()` trims Unicode spaces but keeps `\x1c`-`\x1f`, unlike
  `str.strip()`. The port refuses catalog text in a non-string JSON type and Unicode digits
  other than ASCII in a hash, both of which the runtime would accept; the shipped catalogs have
  neither. Nothing calls it yet: `scan` reads the Python catalog until it moves.
- `build/wave2-qts-staged` named a staged output in a temporary folder that no longer exists, so it
  cannot be replayed, and was deleted on 2026-11-27; `build/wave2-qts-staged-scratch` re-records the
  same cases on `D:\scratch\rust-port\out` (86 calls, 0 mismatches). The Wave 1 forced-native runs'
  staged output under `D:\scratch\rust-port\wave1-wired` was deleted the same day; their manifests
  `en.json` and `id.json` remain.
- `hokace-core::scan` ports `adaptive.discover`, `adaptive.scan` and `apply_graphic_payload`, plus
  `QtsPackage.__init__` and the slot map `qts_relocate.install_btree_slot_map` installs (stock map,
  first slot per chunk; a single shard's stale chunks repointed through its B-tree; an unreadable
  B-tree keeps the stock map and is reported with Python's `struct.error` or `RuntimeError` text,
  as `BTREE_FALLBACKS` records it). `scan` takes the catalog already loaded (`CatalogData`, plus
  `text_view()` for the translator), since the apps' `load_catalog` is `engine_hooks`' edited one.
  `runtime_tap.py --scan-runtime <dir> <work> [<game> <catalog>] ...` records the runtime with its
  catalog as the input blob and the staged files as hashes. All 30 calls matched (`build/wave2-scan`):
  `clean-game` with both catalogs and both `materialize` values (709 unreadable assets, 118 tables,
  202,078 strings, every package fingerprint), and 8 synthetic games under `build/wave2-scan/fixtures`
  (folder sort and `isdecimal`, `<id>_*.db` matched case-insensitively and sorted so `3_10.db` comes
  before `3_2.db`, each skip reason, four B-tree fallbacks, a repointed chunk, patch ranges, and every
  error the scan lets out). The 2026-11-25 dump's B-trees all read, so its fallbacks list is empty.
  The port's own behaviour: non-ASCII decimal folder names and two live slots for one chunk are
  refused, and an `OSError` other than a missing file or refused permission, or an LZ4 block that
  will not decompress, carries Rust's text (no recording has either). Nothing calls it yet: wiring it
  means returning `QtsPackage` objects in the plans, and falling back to Python on a refusal.
- `hokace-core` now depends on `sha2` (fingerprints), so `crates/hok_codecs/Cargo.lock` was refreshed.
- Drive D had 1.4 GB free on 2026-11-27, not 7 GB. The materialized scans write their replacements to
  the `<work>` given to `--scan-runtime`. Point it at drive C.
- `hokace-core::run` ports `adaptive.run` and `_run`; `hokace-core::transaction` ports the receipts,
  `commit`, `recover`, `recover_pending`, `pending_recovery`, `find_restore`, `prune_stale_state`,
  `clear_watchdog_state` and `mutation_lock`; `hokace-core::launcher` ports `launcher_metadata`'s
  `stage_local_file_list` and `local_file_list_mismatches`. `hokace-core::pyos` holds the Windows
  `pathlib` and `os` behaviour they lean on (`resolve`, case-blind path equality and sort, glob,
  `OSError` text, text-mode CRLF, `json.dump` at `indent=2` and the launcher's inline layout,
  `casefold` from a generated table) and `hokace-core::pyjson` words a refused document as
  `json.loads` does (2,145 vectors from Python in `core/tests/json_errors.jsonl`). `scan`, the
  DLL-backed `stage_unity_package`, `query_package_hash` and `stage_package_hash_metadata_batch`,
  `receipt_root` and `_assert_game_stopped` stay behind `RunHost`.
  `rust/harness/run_tap.py <dir> <live-base> [<cross-volume-work>]` stubs those calls, runs eight
  synthetic PC installations through 42 steps and records each step's host calls, report (less
  `seconds`), error and tree; `cargo run --release -p hokace-core --example run_replay -- <dir>`
  rebuilds each pre-state at its recorded paths and replays it. All 42 matched, twice
  (`build/wave2-run`, cases under `%LOCALAPPDATA%\Temp\hokace-wave2-run`, the cross-volume work under
  `D:\scratch\rust-port\run-xvol`). The port's own: the mutation lock covers the whole lock file
  where the runtime locks byte 0 (each still shuts the other out); receipts are read as UTF-8 where
  the runtime uses the locale's encoding (receipts are ASCII); a receipt folder's random suffix
  comes from `RandomState`, not `uuid4`; `rmtree` clears read-only files; a document serde refuses
  that Python accepts (`NaN`, a lone surrogate) keeps serde's text. No recording reaches the
  rollback of a commit that fails mid-swap (only an `OSError` can), the `Recovery refused` checks,
  the backup and staged-copy verification failures or a Watchdog error. Nothing calls it yet:
  wiring it means a PyO3 `RunHost` over the Python scan and DLL calls.
- PC metadata staging, DLL calls and `native_verify` remain. The glossary data has no active caller and follows
  ADR-020. Wave 2 is still open under ADR-007.
