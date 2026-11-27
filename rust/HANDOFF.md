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
  (today `stale-blocks-rs`) for `aarch64-linux-android` against Chaquopy's `libpython3.12.so`, with
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
