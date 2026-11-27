# Map of the Rust migration

**Goal:** the whole repo as a Rust core with one Flutter UI for Windows and Android (ADR-001, ADR-009,
ADR-012). Python stays the reference and the fallback until the lift (ADR-019).

Start a session here, then read `HANDOFF.md` when there is one. Claim a unit before starting it
(`claimed by <session> <date>`), mark it `done` with its gate and replay results, and never take a
unit another session claimed. `rust-anything map --write` writes the measured state to
`PORT_MAP.md`; check this plan against it at each checkpoint.

## Decisions

`DECISIONS.md`, ADR-001 to ADR-028:

| ADR | Settles |
|---|---|
| 001 | Port the whole repo |
| 002 | Android library, arm64-v8a, NDK 28.2, 16 KiB pages |
| 003 | `wxq_patch`: logic from bytecode, data modules to data files |
| 004, 010 | Equivalence: files byte for byte; codec output by what it decodes to |
| 005 | Codecs in pure Rust |
| 006, 008, 019 | Runnable throughout; core first under the current UIs; Flutter last; ship beside the old apps |
| 007 | Checkpoints after each wave; device cycle before the lift and release |
| 009, 015, 018 | Flutter UI, `flutter_rust_bridge` v2, theme and strings generated from `resources/ui` |
| 011 | `tools/research`: checks and workflow generators only |
| 012 | One workspace, one core, three front ends |
| 013 | Port order |
| 014 | Pinyin table generated from pypinyin |
| 016 | Thin Kotlin plugin for Shizuku; pairing in Rust |
| 017 | Windows platform code in the core |
| 020 | Runtime data generator optional |
| 021 | PC path calls the game's own DLLs |
| 022 | LZ4 encoder byte-exact with liblz4 1.9.4 HC 12 |
| 023 | APK entries copied, not re-deflated |
| 024 | `adb.exe` behind a Rust transport |
| 025 | C++ pairing until the Rust port passes |
| 026, 027 | ASTC and BC7 judged after decoding, against Python |
| 028 | Title sizes as data |

Terms: `GLOSSARY.md`. Port rules: `RULES.md`. Research: `research/`.

## Waves

States: `open`, `claimed by <session> <date>`, `done`. Each unit is `tools/`, `app/` or
`wxq_patch` code; a unit in `tools/` or `app/` first moves into its own package so rust-anything can
bridge it (as `tools/block_scan` did).

### Wave 0: groundwork

| Unit | State |
|---|---|
| Cargo workspace under `rust/` (ADR-012) | done: `rust/hokace/`, member `core` (2026-11-27) |
| Pinyin table generator (ADR-014) | done: `rust/generators/pinyin_table.py` -> `core/data/pinyin.tsv.gz` (2026-11-27) |
| App case: offline pipeline on the 2026-11-25 dump, both languages (`rust/harness/pipeline_case.py`) | done: `rust/app-cases/pipeline/en.json`, `id.json`; two runs each identical (2026-11-27) |
| App cases: `--smoketest`, `--pc-selftest` | open (join waves 6 and 7) |
| Android ARM64 wheel build for unit crates (ADR-019) | done: `android/native/build_rust_wheels.py`, `stale_blocks_rs` and `hok_astc` wheels 16 KiB aligned; `hok_astc` built but not installed in the app (the phone keeps the `astc_encoder` wheel until a device cycle); neither yet run on a phone (2026-11-27) |

### Wave 1: codecs (ADR-005, ADR-010)

| Unit | State |
|---|---|
| LZ4 decode (`lz4_flex`), HC 12 compress byte-exact (ADR-022) | done in `hokace-codecs`: 14,215 dump chunks and replayed pipeline writes match Python |
| zstd decode and compress | done in `hokace-codecs`: 151 dump frames match Python, Rust encoder round-trips in the codec test |
| ooz (Oodle) decode | done in `hokace-oodle`: 60,684 dump and 108,118 APK chunks match Python exactly |
| texture2ddecoder (ASTC, BC7 and the formats the pipeline decodes) | done in `hokace-codecs`: pipeline decodes and 124 HDR fixtures match Python exactly |
| ASTC encoder (ADR-026) | ported in `hokace-astcenc`: every call of both language taps (1,272 English, 1,275 Indonesian, 749,778 blocks) matches Python byte for byte at 1, 3 and 12 threads; `hokace-codecs` encodes through it (`AstcEncoder`, both taps match through the codec tap replay); wired into the Windows app through `crates/hok_astc` (`mobile_graphics` falls back to the wheel; both taps match through `_encode_astc`; frozen `--smoketest` checks it); its Android wheel builds (`build_rust_wheels.py`), but the app keeps the `astc_encoder` wheel until a device cycle |
| BC7 encoder (`bc7_mode6`) | done in `hokace-codecs`: both PC catalog builds match 76,535 blocks exactly, and the existing extension passes its 20,057-case replay |
| PNG decode (`png`) | done in `hokace-codecs`: 105 repo PNGs match Pillow |

Wave 1 passed its offline checkpoint on 2026-11-27. The app codecs have Python fallbacks, the
Windows smoke test passed, and the Android debug APK contains the aligned `hok_codecs` wheel.
English and Indonesian match their baselines with native codecs forced, after accounting for the
recorded scratch paths. See [the handoff](HANDOFF.md) for the verification record. Android's Rust
ASTC encoder still needs a device cycle. The user approved Wave 2 (ADR-007).

### Wave 2: runtime parsing

| Unit | State |
|---|---|
| `wxq_patch.qtsvfs` | Native index, slot and payload readers run through the app hooks. The mobile slot map uses Rust to resolve live B-tree offsets. All 200 cases matched across the clean and staged mobile packages, PC package 1 and generated fixtures. Position reference search and insertion match the synthetic replay and await writer integration. |
| `wxq_patch.protobuf_i18n` and `adaptive.fields` | done for the Rust core. 3,676 generated and 2,578 game cases per language matched. `adaptive.fields` is used by the native translator. |
| `wxq_patch.gemini.validate_translation` | done for the native table path. 78,258 pairs matched. |
| `wxq_patch.adaptive` (`translate_table`, `scan`, `run`) | claimed by Codex Wave 2 session 2026-11-27. `translate_table` runs in both apps with the Rust text view of the catalog. 476 calls matched, with and without staged output. The runtime's catalog loader (`Catalog.__init__`, `lookup`, `load_catalog`) is ported in `hokace-core::catalog`: 2,783 calls matched (`build/wave2-catalog`: both shipped catalogs, both as the apps build them after `engine_hooks`' edits, 2,698 lookups and every error path); not yet wired, since `scan` still reads Python's catalog. `discover`, `scan` and `apply_graphic_payload` are ported in `hokace-core::scan`, over the B-tree slot map the pipeline installs: 30 calls matched (`build/wave2-scan`: the 2026-11-25 dump in both languages, both `materialize` values, every fingerprint and staged replacement, plus synthetic games for every skip, fallback and raised error). Not yet wired: the apps still scan in Python. `run` and `_run` are ported in `hokace-core::run`, over the transaction layer in `hokace-core::transaction` (receipts, `commit`, `recover`, the stale-state prune, the Watchdog cleanup, the mutation lock) and the launcher list in `hokace-core::launcher`, with `scan`, the DLL-backed staging and hash calls, `receipt_root` and the running-game check behind `RunHost`: 42 steps matched (`build/wave2-run`: 8 synthetic installations through status, stage, install and restore, a crash mid-swap, stale and corrupt receipts, every error `_run` raises on purpose, a held lock and a cross-volume copy). Not yet wired: the PC edition still runs Python's engine. |
| `wxq_patch.glossary`, `hok_terminology` | deferred under ADR-020 until `pipeline` needs them. There are no active callers. |
| `wxq_patch.package_metadata`, `native_verify` | claimed by Codex Wave 2 session 2026-11-27. Package hash lookup matches 17 recorded cases. DLL calls, metadata staging and verification remain. |

Both offline mobile app cases matched with the Wave 2 readers and translator active, after accounting
for three scratch paths in each summary. The Wave 2 checkpoint is still open.

### Wave 3: pipeline leaves (`tools/`)

| Unit | State |
|---|---|
| `languages`, `terminology`, `catalog_supplement`, `catalog_updates` | open |
| `resource_tokens` | open |
| `pb_text`, `unity_text`, `config_bin`, `lineup_codes` | open |
| `sprite_table`, `card_titles`, `hand_card_titles` | open |
| `asset_fingerprints`, `broken_list`, `axml_label`, `axml_set_debuggable` | open |
| `block_scan` | done: `stale-blocks-rs`, gate passed, diff 242/242 (2026-11-27) |

### Wave 4: pipeline core (`tools/`)

| Unit | State |
|---|---|
| `qts_relocate`, `qts_insert` | open |
| `package_rebuild` | open |
| `mobile_graphics` | open |
| `device_extensions` | open |
| `extra_text` | open |
| `pristine_delta`, `run_artifacts`, `mobile_snapshot`, `patch_summary` | open |
| `build_device_patch`, `build_mobile_patch` (the staging contract) | open |

### Wave 5: Android side

| Unit | State |
|---|---|
| `android_bridge.py`, `build_storage.py` | open |
| Wireless-debugging pairing (SPAKE2, TLS key export; ADR-016) | open |

### Wave 6: Windows core (ADR-017)

| Unit | State |
|---|---|
| `adb_device`, `game_data_pull` | open |
| `apk_tools` (rewrite, v2 signing), `apk_preparation` | open |
| `translation_payload`, `pristine_layer` | open |
| `patcher_core`, `patch_session`, `device_transaction`, `windows_checkpoints` | open |

### Wave 7: PC edition

| Unit | State |
|---|---|
| `wxq_patch` installers (`pipeline`, `installer`, `combined_installer`, `unity_package_installer`, `installation`, `launcher_metadata`) | open |
| `engine_hooks`, `pc_catalog`, `pc_edition` | open |

### Wave 8: Flutter app and the lift (ADR-009, ADR-015, ADR-016, ADR-018, ADR-019)

| Unit | State |
|---|---|
| Flutter app on the core (Windows and Android) | open |
| Kotlin plugin: Shizuku, Binder user service, package installer | open |
| Theme, fonts and strings generated from `resources/ui` | open |
| Lift: drop Chaquopy and the PyInstaller exe; same `applicationId` and key | open |

### Wave 9: research checks (ADR-011)

| Unit | State |
|---|---|
| `check_*.py` | open |
| `apply_catalog_fixes`, `make_language_payloads`, `atlas_sprites`, `bc7_corpus` | open |

### Already ported, research only

| Unit | State |
|---|---|
| `pixel_diff.outside_ranges` | done: `outside-ranges-rs`, gate passed, diff 455/455 (2026-11-27) |
| `pixel_diff.mean_abs_diff` | done: `mean-abs-diff-rs`, gate passed, diff 254/254 (2026-11-27) |

## Open questions

- `tools/qts_builder.py` drives Tencent's `QtsVFS.dll` over ctypes for `--builder` runs from source,
  and `REBUILD_PACKAGES` is empty (repo ADR 0003). Drop the `--builder` path in Rust, or keep it in
  Python for source runs? (ADR-021 covers only the PC path's metadata builder.)

Resolved by round 4 (ADR-020 to ADR-028): the runtime's data modules, the game's DLLs, the LZ4
encoder, APK rewriting, `adb.exe`, pairing, the ASTC and BC7 encoders, fonts. Network use: none reached
(`research/wxq-patch-runtime.md`).

## Out of scope

- The one-off research probes (ADR-011).
- `resources/qtsvfs/` (Tencent's DLLs) and `resources/key/`: kept as they are.
