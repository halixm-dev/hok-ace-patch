# Decisions for the Rust migration

The whole-app port's decisions, one ADR each, numbered in order and never renumbered. A changed
decision gets a new ADR that supersedes the old one. Settled with the user on 2026-11-27 in three
rounds of questions (Q1 to Q19). The repo's own design decisions stay in `docs/adr/`; this file
holds only the migration's.

## ADR-001: Port the whole repo to Rust
Status: accepted (2026-11-27)
Context: The phone runs the pipeline in Chaquopy's Python 3.12 and the Windows patcher is a frozen
Python exe. Only about 4% of a phone pipeline run is this repo's own Python (lab notebook,
2026-11-27); the rest is the upstream runtime, native codecs and file I/O, so single-function ports
cannot make the phone fast.
Decision: Every part of the repo moves to Rust: the phone pipeline (`android_bridge.py` and the
`tools/` it reaches), the Windows patcher (`app/`), the PC edition, the `wxq_patch` runtime (ADR-003)
and the native codecs (ADR-005). `tools/research/` follows ADR-011.
Consequences: Python remains only as the reference and the fallback until the lift (ADR-019).

## ADR-002: A Rust library loaded by the app, arm64-v8a only
Status: accepted (2026-11-27); the front end is superseded by ADR-009 and ADR-015
Context: The Android app is Kotlin with Chaquopy.
Decision: On Android the core is a Rust shared library for arm64-v8a, built with NDK 28.2.13676358,
16 KiB ELF page alignment, minSdk 29. On Windows it is part of one Rust-backed exe.
Consequences: No other ABI is built.

## ADR-003: Port the wxq_patch runtime from its bytecode; turn its data modules into data files
Status: accepted (2026-11-27)
Context: `resources/runtime/wxq_patch/` is 1.8 MB of Python 3.12 bytecode from the upstream PC patcher,
with no source in this repo. Most of it by size is data (`direct_*_overrides`, `*_content_groups`); the
logic is `adaptive`, `qtsvfs`, `protobuf_i18n`, `gemini`, `glossary`, `hok_terminology`, `pipeline`,
`installer`, `combined_installer`, `unity_package_installer`, `package_metadata`, `native_verify`,
`installation`, `launcher_metadata`.
Decision: Port the logic the patchers call from the disassembled bytecode, held to the Python runtime's
recorded behaviour. A generator script turns the data modules into data files the Rust core embeds; it
is re-run on every upstream runtime import.
Consequences: Each upstream import means regenerating the data, re-recording, and porting any logic
that changed. `AGENTS.md`'s boundary for `resources/runtime/` stays: the bytecode is read, never edited.

## ADR-004: Equivalence bar: every written file byte for byte
Status: accepted (2026-11-27); narrowed for codec output by ADR-010
Context: The patchers' output is game data; a wrong byte can crash the game.
Decision: Against the Python pipeline on the same dump and APK, in both languages, every file a run
writes (override layer, pristine delta, run artifacts) matches byte for byte and the staging summary
JSON is equal. Log lines need not match, except the counts the GUI shows (`count_translated` and the
untranslated counts).
Consequences: The offline pipeline run on the 1.12 dump (`D:\HOK ACE Patcher Data\update-20261125`)
is the main app case.

## ADR-005: Native libraries are rewritten in pure Rust
Status: accepted (2026-11-27)
Context: The pipeline uses liblz4, libzstd, the Arm ASTC encoder, texture2ddecoder, ooz (Oodle
decoder, GPL-3.0-or-later), and Pillow with FreeType. The user chose pure Rust over binding the same
C/C++ sources.
Decision: No C or C++ is bound. Each codec is a pure-Rust crate, an existing one where its output
meets ADR-010, otherwise a port.
Consequences: A Rust port of ooz is a derived work of GPL code; the shipped app keeps the GPL
obligations `android/native/THIRD_PARTY.md` already lists.

## ADR-006: The phone and the PC stay runnable while units move
Status: accepted (2026-11-27); the route is refined by ADR-019
Decision: Chaquopy and the frozen Python exe stay until the lift; every ported unit is reached through
its switch-on block, with Python as the fallback.

## ADR-007: Checkpoints
Status: accepted (2026-11-27)
Decision: Stop for the user's go-ahead after each wave of `MAP.md`, with the offline byte-for-byte
comparison (ADR-004) on the 1.12 dump. A device cycle on the user's phone before the lift and before
release.

## ADR-008: Ship beside the old apps first
Status: accepted (2026-11-27); detailed by ADR-019
Decision: The Rust build ships beside the Python one for one release; the old apps are retired only
after the user has run the new one on their phone.

## ADR-009: One Flutter UI for Windows and Android
Status: accepted (2026-11-27); supersedes ADR-002's front end and the Q9 recommendation (Slint)
Context: The Windows patcher is tkinter and the Android app's UI is Kotlin; the user wants one UI
codebase.
Decision: One Flutter app is the UI on both Windows and Android, on top of the shared Rust core.
Consequences: The Kotlin UI and the tkinter GUI are both replaced at the lift.

## ADR-010: Codec output is judged by what it decodes to
Status: accepted (2026-11-27); narrows ADR-004
Context: Under ADR-005, matching libzstd's and astcenc's encoder output byte for byte would mean a
line-by-line port of tens of thousands of lines.
Decision: Compressed chunks must decompress to the same bytes and stay inside the package's size
limits. ASTC blocks must decode within `check_graphics.py`'s limits (mean 2.0, max 48). Decoders (ooz,
LZ4, zstd, texture2ddecoder) match exactly. Everything else stays byte for byte, and a device cycle
confirms the game reads it.
Consequences: The app cases compare codec output after decoding it.

## ADR-011: tools/research: port the checks and the workflow generators
Status: accepted (2026-11-27)
Decision: Port the `check_*.py` checks and the generators that are part of a workflow
(`apply_catalog_fixes.py`, `make_language_payloads.py`, `atlas_sprites.py`, `bc7_corpus.py`). The one-off
probes (`find_arm64_xrefs.py`, `ribbon_id_hunt.py` and the like) stay as the written record, unported.

## ADR-012: One workspace, one core, three thin front ends
Status: accepted (2026-11-27)
Decision: One Cargo workspace under `rust/` with one shared core (pipeline, runtime port, codecs),
used by the Android library, the Windows exe and the PC edition.
Consequences: The rust-anything unit crates (`stale-blocks-rs`, `outside-ranges-rs`,
`mean-abs-diff-rs` and later ones) become libraries of the core at the lift.

## ADR-013: Port order
Status: accepted (2026-11-27); detailed by ADR-019
Decision: Codecs first; then the runtime's parsing (`qtsvfs`, `protobuf_i18n`); then the `tools/`
pipeline; then the Android side; then the Windows app; then the PC edition; then the research checks.

## ADR-014: Pinyin from a table generated from pypinyin
Status: accepted (2026-11-27)
Context: `extra_text` romanises opponent names with pypinyin; Rust pinyin crates carry other data.
Decision: Generate a table from the pinned pypinyin at build time and ship it; regenerate it on every
pypinyin bump.

## ADR-015: Flutter calls Rust through flutter_rust_bridge v2
Status: accepted (2026-11-27)
Decision: `flutter_rust_bridge` v2 generates the Dart bindings for the core on Windows and Android.
Progress, logs and cancel are its streams, in place of today's threads and callbacks.

## ADR-016: A thin Kotlin plugin for Shizuku; the rest in Rust
Status: accepted (2026-11-27)
Context: Shizuku's API and the user service it binds are Java/Binder only.
Decision: A thin Kotlin plugin inside the Flutter app keeps Shizuku, the Binder user service and the
package installer. Everything else moves to Rust, including the wireless-debugging pairing (SPAKE2 and
the TLS key export, now C++ against BoringSSL), once research confirms a pure-Rust SPAKE2 that
interoperates with Android's ADB pairing.
Consequences: The plugin stays as small as Shizuku allows.

## ADR-017: Windows platform code moves to the core
Status: accepted (2026-11-27)
Decision: The ADB client, APK re-signing, the process guard and the launcher lookup move to the Rust
core. The Universal ADB Driver stays an installer the app downloads and runs.

## ADR-018: Theme and strings generated from resources/ui
Status: accepted (2026-11-27)
Decision: Flutter's theme is generated from `resources/ui`'s tokens, `resources/fonts/` ships with it,
and its localisation is generated from `strings.json`, so `DESIGN.md` and `check_ui_strings.py` stay
the single source. `DESIGN.md` is reworked for Flutter in the same change; `PRODUCT.md`'s voice is
unchanged.

## ADR-019: Core first under the current UIs; Flutter last
Status: accepted (2026-11-27); refines ADR-006, ADR-008 and ADR-013
Context: A Flutter UI cannot easily fall back to the Python pipeline on Windows.
Decision: The core moves to Rust unit by unit while the current UIs keep working: each unit reaches
the phone as an ARM64 wheel and the Windows exe as a PyO3 module, with Python as the fallback. The
Flutter app is built only on the finished Rust core. At the lift it replaces the Kotlin app and the
tkinter exe together, with the same Android `applicationId` (`dev.halixm.hokacepatcher`) and signing
key, so phones upgrade in place. One release ships the old apps beside it as a download before they
are retired.
Consequences: No Flutter-to-Python glue is written. Every wave before the Flutter one also builds its
crates as Android ARM64 wheels.

## ADR-020: The runtime's data generator is optional
Status: accepted (2026-11-27); amends ADR-003
Context: No function the patchers reach reads any of the runtime's 25 data modules; the patchers'
text comes from `catalog.json.gz` (`research/wxq-patch-runtime.md`).
Decision: The data-module generator is built only if `pipeline` is ever ported.
Consequences: Wave 0 drops it.

## ADR-021: The PC path calls the game's own DLLs from Rust
Status: accepted (2026-11-27); an exception to ADR-005
Context: `adaptive._run`'s default metadata builder loads the game's installed `QtsVFS.dll` and
`QtskDB.dll` over ctypes (`research/wxq-patch-runtime.md`).
Decision: Rust loads and calls those DLLs (`libloading`) from the user's game install. They are the
game's code, not shipped by this repo, so ADR-005 does not cover them.
Consequences: The PC edition stays Windows-only; nothing reimplements Tencent's metadata.
The DLL calls live in `hokace/qtsvfs`, the one workspace crate allowed `unsafe`, behind
`hokace-core`'s `QtsVfs` trait (2026-11-27).

## ADR-022: The LZ4 encoder matches liblz4 1.9.4 level 12 byte for byte
Status: accepted (2026-11-27); narrows ADR-010 for LZ4
Context: The HC level-12 compressed length decides whether the runtime stages a table in place; LZ4
fast mode overflows Tencent's slots in 296 of 468 chunks of package 1 (`research/compression-codecs.md`).
Decision: Adopt `lz4-pure-rs` only if it matches python-lz4 on the 1.12 dump's whole LZ4 corpus;
otherwise port liblz4 1.9.4's level-12 path. `lz4_flex` decodes.

## ADR-023: An APK rewrite copies each entry's compressed bytes
Status: accepted (2026-11-27); amends ADR-004 for the normal and access APKs
Context: Today every entry is re-deflated through CPython's zlib; matching those bytes needs an
identical deflate (`research/device-and-apk.md`).
Decision: Copy each entry's compressed bytes unchanged, rewrite only `AndroidManifest.xml`, re-sign
v2. Verified by entry content, `apksigner verify` and a device cycle, not byte equality with Python.

## ADR-024: adb.exe stays behind a Rust transport
Status: accepted (2026-11-27); refines ADR-017
Decision: The ADB wire client is written once in Rust (Android needs it over TCP). On Windows it runs
over `adb.exe` behind a transport trait; `nusb` USB is opt-in until device cycles pass, with `adb.exe`
as the fallback.

## ADR-025: Today's C++ pairing stays until the Rust port passes
Status: accepted (2026-11-27); a temporary exception to ADR-005, refines ADR-016
Context: No crate interoperates with adbd's BoringSSL SPAKE2 (`research/device-and-apk.md`).
Decision: Port BoringSSL's SPAKE2 on `curve25519-dalek` with a small RustCrypto rustls provider. The
C++ pairing (`android/app/src/main/cpp`) stays until the port matches vectors from today's
`libhokace_adb.so` and pairs with the user's phone; then it is deleted.

## ADR-026: Port Arm astcenc byte for byte
Status: accepted (2026-11-27); replaces the imgio route at the user's choice, restates ADR-010's ASTC limit
Context: imgio 0.2.0's astcenc 6.0.0 port exceeded the decoded limit on 57 of 1,272 English calls,
6 of them a mis-scored block (`research/texture-codecs.md`). All four Windows wheel builds give the
same bytes, which a scalar `/fp:precise` build of the wheel's own sources reproduces.
Decision: `hokace-astcenc` translates the wheel's Arm astcenc (commit `631fb04e1c4b`) at LDR, quality
85, identity swizzle, one reused context per footprint, following the scalar vector layer with no
FMA and the build's own sin/cos tables embedded, so Android gets the Windows bytes. It is held to
byte identity with Python on Windows. The decoded limit (mean 2.0, max 48) stays as ADR-027's.

## ADR-027: BC7 output is judged after decoding
Status: accepted (2026-11-27); widens ADR-010 to BC7
Decision: BC7 output is held to ADR-026's limits, Rust's decoded output against Python's. BC7 blocks
have a fixed size, so file sizes do not change (repo ADR 0011).

## ADR-028: Title sizes recorded as data
Status: accepted (2026-11-27); refines ADR-011 for `atlas_sprites.py`
Context: No pure-Rust font library reproduces FreeType's hinting (`research/texture-codecs.md`).
Decision: Record the title sizes as data so `layout --check` needs no font; `ab_glyph` draws drafts only.
