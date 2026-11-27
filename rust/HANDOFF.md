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

## Wave 1, in progress (2026-11-27)

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
- Upstream quirk kept: `compress_block`'s `static` overshoot is set by the first block the process
  compresses and reused by every later context (`ERRORVAL_OVERSHOOT`). A replay must run its calls
  in the tap's order in one process.
- Workspace format, Clippy, Windows tests and Android ARM64 `cargo check` passed. The Wave 1
  codecs still need the app fallback wiring, Windows extension, Android wheel and offline
  replay before the ADR-007 checkpoint. The Python apps still drive both pipelines.
