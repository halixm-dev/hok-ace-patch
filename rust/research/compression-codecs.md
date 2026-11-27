# Research: the compression codecs (LZ4 block, zstd, ooz)

Researched 2026-11-27 for Wave 1 of the whole-repo migration (`rust/MAP.md`, "Wave 1: codecs"; ADR-005,
ADR-010 in `rust/DECISIONS.md`). Each claim names its source: a URL, `file:line` in this repo, a
bytecode location in `resources/runtime/wxq_patch/` (read with `marshal` + `dis` on Python 3.12, cited
as `module.pyc:function`, with the source line the bytecode records), or a measurement on the 1.12 dump
(`D:\HOK ACE Patcher Data\update-20261125`, the override layer `game\WXQ_Data\Package\builtin\` and the
prime census `census-work\prime\`). Claims marked **unverified** had no source that settled them.

## 1. What the repo calls

### 1.1 LZ4 block (python-lz4 4.4.5 on Windows, 4.3.2 on Android; both bundle liblz4 1.9.4)

Versions: `requirements.txt:6` (`lz4==4.4.5`), `android/app/build.gradle.kts:206,209` (4.3.2). Measured:
`lz4.library_version_string()` is `1.9.4` in `.venv`, and the strings `1.9.4` are in
`android/wheels/lz4-4.3.2-...arm64_v8a.whl`'s `lz4/_version.so` and `lz4/block/_block.so`. So both
platforms run the same liblz4 encoder.

Compress (all raw blocks, no size prefix):

| Call | Parameters | Where |
|---|---|---|
| `write_assets`, chunks of entries with compression id 1 | `mode="high_compression", compression=12, store_size=False` | `tools/device_extensions.py:120` |
| `qts_insert._encode`, compression id 1 | same; refuses a block whose length equals the piece's | `tools/qts_insert.py:44-48` |
| runtime `installer._compress` (every in-place text table) | same `('mode', 'compression', 'store_size')` = `('high_compression', 12, False)` | `installer.pyc:_compress`, source lines 68-70 |
| runtime callers of `_compress` | `_find_fit` (l. 291), `_merge_preceding_slot_donation_plans` (l. 703), `stage_patch` (two calls), `unity_package_installer.pyc:_fit_with_preceding_donations` and `:stage_unity_package` | bytecode `LOAD_GLOBAL _compress` in each |
| self-tests only | default mode (fast, acceleration 1), `store_size=True` | `app/hok_patcher.py:1628` |
| self-tests only | default mode, `store_size=False` | `android/app/src/main/python/android_bridge.py:136-137` |

Decompress (raw block, size given):

| Call | Where |
|---|---|
| `lz4.block.decompress(payload, uncompressed_size=slot.uncompressed_size)` for ids 1 and 9 | `tools/qts_relocate.py:568-569` (`LZ4_CODECS = (1, 9)`, l. 56) |
| runtime `QtsPackage.extract`, id `COMP_LZ4 = 1` (`qtsvfs.pyc` l. 14), then raises `Chunk … decompressed to an unexpected size` | `qtsvfs.pyc:QtsPackage.extract`, l. 456-458 and the size check after |
| runtime `native_verify._verify_structural.extract` (l. 90), `unity_package_installer.stage_full_unity_package`, `installer._merge_preceding_slot_donation_plans` (l. 690) | bytecode `KW_NAMES ('uncompressed_size',)` |

### 1.2 zstd (python-zstandard 0.25.0 / libzstd 1.5.7 on Windows, 0.22.0 on Android)

Versions: `requirements.txt:16`, `android/app/build.gradle.kts:207,210`; `zstandard.ZSTD_VERSION` is
`(1, 5, 7)` in `.venv` (measured).

- Decompress only, in the pipeline: `ZstdDecompressor().decompress(payload,
  max_output_size=slot.uncompressed_size)` when the payload opens with `28 B5 2F FD`, whatever the entry's
  compression id says (`tools/qts_relocate.py:57-61, 564-567`). No dictionary is passed.
- Compress only in self-tests, default level (3), frame format: `app/hok_patcher.py:1629`,
  `android_bridge.py:139`. **No pipeline path writes zstd**: `write_assets` and `qts_insert` re-encode a
  zstd-framed chunk in the entry's own codec (LZ4 for id 1, Oodle stored for id 4;
  `tools/device_extensions.py:119-122`, `tools/qts_insert.py:44-53`). The runtime bytecode has no zstd
  call at all (none of the `wxq_patch/*.pyc` code objects names `zstandard`).

### 1.3 ooz (pyooz 0.0.8, GPLv3+)

- `ooz.decompress(payload, raw_size)` is the only API used: `tools/qts_relocate.py:570-571` (entry id
  4), `tools/mobile_graphics.py:233-234` (`oodle_decompress`, used by `device_extensions.py:306` and the
  research readers). pyooz's metadata: "Python bindings to the ooz decompressor", classifier GPLv3+
  (`.venv/Lib/site-packages/pyooz-0.0.8.dist-info/METADATA`).
- There is no Oodle compressor. Writes use **stored** Oodle blocks: `oodle_stored` emits, per 256 KiB
  block (`OODLE_BLOCK = 0x40000`, `mobile_graphics.py:47`), the two bytes `CC 0C` and the raw bytes
  (`mobile_graphics.py:221-230`); callers `device_extensions.py:122,348`, `qts_insert.py:49-52`.
- The runtime never calls ooz (no code object names it); its `extract` raises `Unsupported compression`
  for anything but 0 and 1 (`qtsvfs.pyc:QtsPackage.extract`, l. 460-464).

### 1.4 Size limits the output must meet

- **Chunk size.** Raw chunks are at most 307 200 bytes: `MAX_QTS_PAGE_SIZE = 307200` (`installer.pyc`
  l. 38), `NATIVE_CHUNK_SIZE = 307200` (`tools/device_extensions.py:34`); a re-cut chunk size is rounded to
  `CHUNK_ALIGN = 0x1000` (`tools/qts_relocate.py:50, 454-469`). Measured maxima per chunk: 307 200 for LZ4
  in packages 1 and 10 and for Oodle everywhere, 16 384 for LZ4 and zstd in packages 19-21.
- **In-place fit (runtime).** `_find_fit` needs, for each compressed chunk, a slot of at least
  `48 + align4(len(payload))` bytes (`installer.pyc:_find_fit`, l. 292), and slot capacity is
  `slot_size - 48` (l. 309). A table whose chunks do not fit, even after the preceding-slot donations,
  is not staged in place and goes to the append path (`device_extensions.relocate_text`). So **the
  compressed length decides the staging summary's `mode`**, which ADR-004 requires to be equal.
- **Append/relocate (this repo).** A relocated or appended slot takes `align4(32 + len(payload)) + 16`
  bytes at the shard's end (`tools/qts_relocate.py:185-195, 197-208`); there is no per-slot cap, only
  shard growth.
- **Stored marker.** A chunk whose compressed size equals its raw size is read as stored
  (`qts_relocate.py:562-563`). An LZ4 block of exactly the piece's length would therefore read back as the
  LZ4 bytes; `qts_insert` refuses it (`qts_insert.py:38-48`), `write_assets` does not check (see T3).
  Oodle stored output is always 2 bytes per block longer, so it cannot hit this.

## 2. What the game data holds (measured)

Scan of every chunk in the 7 override packages (`1, 10, 15, 19, 20, 21, 1050016095`) and the prime census
packages, with the repo's `QtsPackage.build_slot_map`:

| Kind | Where | Count |
|---|---|---|
| LZ4 under id 1 | 1, 10, 19, 20, 21 | 9 272 chunks |
| LZ4 under id 9 | 19, 20, 21 | 4 616 chunks |
| zstd frame (under ids 1, 4 and 9) | 19, 20, 21, prime | 111 chunks, all decode |
| stored (sizes equal) | 20, 21 | 2 chunks |
| Oodle (id 4) | all | 60 685 chunks |

**Oodle:** I walked every block header of all 60 685 Oodle chunks (2-byte block header, then one 3-byte
quantum header per 256 KiB block, following ooz's `Kraken_ParseHeader` / `Kraken_ParseQuantumHeader`);
every chunk walked to its exact end. Every block has **decoder type 12** with the checksum bit clear;
headers seen: `8C` 59 984, `0C` 2 068 (no reset), `CC` 701 and `4C` 1 (stored), with 62 048 LZ quanta, 4
memset quanta and 702 stored blocks. In ooz, type 12 dispatches to `Leviathan_DecodeQuantum` (6 Kraken, 5
LZNA, 11 BitKnit, 10 Mermaid/Selkie; `Kraken_DecodeStep` in
https://raw.githubusercontent.com/powzix/ooz/master/kraken.cpp). So **the game's data is Leviathan
only**, and `oodle_stored`'s `0x0C` matches it. Not measured: which entropy types (raw, tANS, Huffman,
RLE, recursive/multi-array) occur inside the Leviathan quanta; the port must carry all of
`Kraken_DecodeBytes`. Not scanned: packages inside the APK (prime-only content); re-run the walker on
them before closing the port's scope.

**zstd:** every frame has dictionary id 0, no checksum, single segment, the content size in the header
equal to the slot's raw size, windows 1-16 KiB, and only *compressed* blocks (measured with
`zstandard.get_frame_parameters` and a block-header walk; no trailing bytes).

**LZ4 ratio (python-lz4 on the same chunks, decoded then re-encoded):**

| Package | Tencent's bytes | fast (default) | HC 9 | HC 12 | fast chunks larger than the original's aligned size |
|---|---|---|---|---|---|
| 1 (468 chunks) | 20 753 111 | 21 438 323 | 17 964 823 | 17 915 956 | 296 |
| 10 (2 312) | 13 233 887 | 12 973 019 | 10 444 171 | 10 380 025 | 556 |
| 19 (5 462) | 19 311 565 | 17 263 255 | 14 347 384 | 14 278 545 | 15 |
| 21 (3 747) | 14 746 697 | 13 753 615 | 11 929 631 | 11 884 289 | 48 |

HC 12 is 17-22 % smaller than fast mode, and fast output overflows Tencent's own slot in hundreds of
chunks. A fast-only encoder would push text tables off the in-place path.

## 3. Pure-Rust crates

### lz4_flex (block and frame)

- 0.14.x; MIT; `rust-version = 1.81`; edition 2021; features `std`, `safe-encode`, `safe-decode`,
  `frame`, `checked-decode` all default; `checked-decode` "Adds important checks while decoding. Only
  remove on trusted input!" (https://raw.githubusercontent.com/PSeitz/lz4_flex/main/Cargo.toml).
- "no unsafe by default"; the block format works without std, the frame format needs std; **no HC mode,
  "High compression" is a TODO**; its ratio equals liblz4's *fast* mode (0.2284 vs 0.2283 on a 66 KB JSON,
  0.6372 both on dickens) (https://docs.rs/crate/lz4_flex/latest).
- Block API: `decompress(input, min_uncompressed_size)` ("must be equal to or larger than the actual
  uncompressed size"), `decompress_into`, `compress`, `compress_into`, dictionary variants
  (https://docs.rs/lz4_flex/latest/lz4_flex/block/index.html).
- Pure Rust with one optional dependency (`twox-hash` for frames), so it builds for
  `aarch64-linux-android` like any no-FFI crate (inferred from the manifest; not built here).
- Verdict: a fine **decoder**; as an encoder it fails the in-place fit (section 2).

### LZ4 HC in pure Rust

| Crate | Version, license | Claim | Concern |
|---|---|---|---|
| lz4-pure-rs | 0.1.2, BSD-2-Clause | translation of upstream LZ4 (commit `9da37b2e`); "Compressed sizes are byte-identical to system at every level shown"; an optional sweep "matched system `lz4 1.9.4` for every tested corpus input and level"; HC 9-12 tested (https://docs.rs/lz4-pure-rs) | young (published 2026-10-29); depends on the `libc` crate (https://docs.rs/crate/lz4-pure-rs/latest/source/Cargo.toml.orig); unsafe use not stated |
| lz4r | 1.10.0, **GPL-2.0-only** | port of LZ4 1.10.0, "bit-for-bit identical" (https://docs.rs/crate/lz4r/latest) | GPL-2.0-only cannot be combined with ooz's GPL-3.0 code in one binary; ports 1.10.0, not 1.9.4; heavy CLI dependencies (`libc`, `nix`, `winapi`, `rayon`) |
| oxiarc-lz4 | 0.4.2, Apache-2.0 | encoders "verified byte-identical against reference `lz4 1.10.0`", scope tied to one fix (https://docs.rs/crate/oxiarc-lz4/latest) | HC parser and levels undocumented |

liblz4 1.9.4's level 12 is the optimal parser `{ lz4opt, 16384, LZ4_OPT_NUM }`, run in "ultra" mode
(`fullUpdate`), through `LZ4HC_compress_optimal`, `LZ4HC_FindLongerMatch`,
`LZ4HC_InsertAndGetWiderMatch` (pattern analysis and chain swap on) and `LZ4HC_encodeSequence`; the file is
BSD-2-Clause, about 1 400 lines, the optimal parser about 270
(https://raw.githubusercontent.com/lz4/lz4/v1.9.4/lib/lz4hc.c). **Unverified:** whether 1.10.0's level 12
emits the same bytes as 1.9.4's.

### ruzstd (zstd)

- 0.9.2 in the repository; MIT; `rust-version = 1.87`; edition 2018; features `hash` (twox-hash xxh64)
  and `std` default, `dict_builder` optional; `rustc-dep-of-std` shows it builds without std
  (https://raw.githubusercontent.com/KillingSpark/zstd-rs/master/ruzstd/Cargo.toml). docs.rs shows 0.9.1
  of 2026-10-11 as latest (https://docs.rs/crate/ruzstd/latest).
- Decoder: "a complete implementation of a Zstandard decompressor", fuzzed, test files "checked against
  their originals"; about 3.5x slower than C on enwik9 (https://docs.rs/crate/ruzstd/latest). The
  game's frames use no dictionary and no checksum (section 2), so the features the README leaves unclear
  are not needed.
- Encoder: levels Uncompressed, Fastest (~1), Default (~3), Better (~7), Best (~11); it "does not yet
  reach the speed, ratio or configurability of the original zstd library"; the README does not claim the
  output is checked against libzstd (https://github.com/KillingSpark/zstd-rs). Unsafe use not stated.
- Pure Rust, no build script dependency on C; builds for Android like any no-FFI crate (inferred).

### Oodle decoders

| Crate | State | Concern |
|---|---|---|
| oozle | binds powzix's C++ through CXX; repository archived (https://github.com/sehnryr/oozle, https://docs.rs/crate/oozle/latest/source/src/cpp/) | violates ADR-005 |
| oozextract 0.5.7 | Rust, "rust port of ooz oodle decompressor", Kraken/Mermaid/Selkie/Leviathan/LZNA/BitKnit, `algorithm/leviathan.rs`; `build.rs` only declares a `cfg` (https://github.com/lvlvllvlvllvlvl/oozextract, https://docs.rs/crate/oozextract/latest/source/build.rs) | labelled **MIT** (https://docs.rs/crate/oozextract/latest/source/Cargo.toml.orig) though it ports GPL code, no LICENSE file in the repository; docs.rs failed to build 0.5.7 (last good 0.5.0); depends on `wide`, `bytes`, `futures`, `test-log` in normal deps; no `#![forbid(unsafe_code)]` (https://docs.rs/crate/oozextract/latest/source/src/lib.rs) |

powzix/ooz: GPLv3-or-later header ("Kraken Decompressor for Windows", Copyright 2016 Powzix), decoder only
(compression goes through the external `oo2core` DLL), SSE/SSE2 and MSVC intrinsics, "not fuzz safe"
(https://github.com/powzix/ooz, https://raw.githubusercontent.com/powzix/ooz/master/kraken.cpp).
`kraken.cpp` is 4 452 lines (3 907 loc) and holds Kraken, Mermaid, Leviathan and the shared entropy
decoders; LZNA and BitKnit are in their own files (https://github.com/powzix/ooz/blob/master/kraken.cpp).
pyooz adds SIMDe so it builds for ARM64 (`METADATA`; `android/native/THIRD_PARTY.md:11`).

**Port size for Leviathan only.** Needed from `kraken.cpp`: the block and quantum header parsers, the
`Kraken_DecodeStep`/`Kraken_Decompress` loop (stored, memset and whole-block raw quanta), bit readers,
`Kraken_DecodeBytes` with all its entropy types (raw 0, tANS 1, Huffman 2/4, RLE 3, recursive 5), and
Leviathan's LZ table reader and match copy. Estimate **1 800-2 300 C++ lines -> about 2 000-2 500 lines
of safe Rust** (my estimate from the file's structure; Kraken's and Mermaid's quantum decoders, LZNA and
BitKnit drop out). The SSE paths become scalar or portable code. **License:** any port, or reuse of
oozextract, is a derived work of GPL-3.0-or-later ooz; the shipped exe and the Android library carry
GPL-3.0-or-later obligations (corresponding source, the GPL text), as ADR-005's consequence and
`android/native/THIRD_PARTY.md:11` already state. Every other crate linked in must be GPL-3-compatible
(MIT, BSD-2, Apache-2.0 are; GPL-2.0-only is not).

## 4. Traps

- **T1. Compressed size decides staging.** In-place fit is `48 + align4(len)` against `slot_size`
  (`installer.pyc:_find_fit` l. 292, 309). Any LZ4 encoder weaker than liblz4 HC 12 moves tables to the
  append path and changes the staging summary (ADR-004). Fast mode is 17-22 % larger (section 2). Even
  an HC encoder that is a few bytes larger on a tight chunk flips a decision. Byte-identical HC 12 is the
  only output that keeps ADR-004 without argument.
- **T2. Decoder edge semantics** (measured with the installed modules): `lz4.block.decompress` with an
  `uncompressed_size` larger than the true size returns the shorter result, smaller raises
  `LZ4BlockError`; `ooz.decompress` raises `RuntimeError("Could not decompress requested amount")` for any
  size other than the exact one; `ZstdDecompressor().decompress` **ignores `max_output_size` when the
  frame header carries the content size** (returned 1 100 bytes with a 1 099 limit). `read_raw` turns
  every exception into `None` (`qts_relocate.py:574-575`) and never checks the LZ4 length, while the
  runtime's `extract` raises on a length mismatch. The Rust decoders must reproduce each of these, not
  "be stricter".
- **T3. Stored-marker ambiguity.** `write_assets` (`device_extensions.py:119-120`) writes an HC block of
  the piece's exact length without the check `qts_insert.py:48` has; it would read back as stored.
  Keep the Python behavior in the port (ADR-004), and file the gap separately.
- **T4. Payload decides the codec, not the entry.** zstd frames sit under ids 1, 4 and 9, and one asset
  mixes LZ4 and zstd chunks (`qts_relocate.py:57-61`; measured in section 2). Test the magic before the
  id, then the stored test before both (the order at `qts_relocate.py:562-571`).
- **T5. No size prefix.** Every pipeline LZ4 block is raw (`store_size=False`); only the self-test at
  `app/hok_patcher.py:1628` uses the 4-byte little-endian prefix. Use `lz4_flex::block::decompress`, not
  `decompress_size_prepended`, for chunks.
- **T6. Oodle block framing.** 256 KiB blocks; byte 0 low nibble `0xC`, bit 6 stored, bit 7 reset; byte 1
  bit 7 checksums (all clear in the data), bits 0-6 the decoder type. A 307 200-byte chunk is two blocks,
  and the quantum header spans the whole block, not 128 KiB (my first walker assumed 128 KiB and failed on
  4 518 chunks). Quantum header bytes are big-endian (`(p[0]<<16)|(p[1]<<8)|p[2]`, kraken.cpp); all QTS
  shard fields are little-endian (`qts_relocate.py:157`).
- **T7. Oodle stored growth.** `oodle_stored` adds 2 bytes per 256 KiB block; the append path absorbs
  it, the in-place runtime path never writes Oodle.
- **T8. Two liblz4 builds.** Windows and Android both bundle liblz4 1.9.4 today (section 1.1). A port
  pinned to 1.10.0's HC (lz4r, oxiarc-lz4) needs a check that level 12 output equals 1.9.4's on the
  corpus before it can stand in.
- **T9. GPL mixing.** ooz forces GPL-3.0-or-later on the binary; lz4r's GPL-2.0-only is incompatible.
- **T10. zstd encoder is test-only.** Matching libzstd's encoder is not needed; ruzstd's output is only
  read back by ruzstd/libzstd in the self-tests.

## 5. Recommendation

| Codec | Recommendation |
|---|---|
| LZ4 decode | **lz4_flex** block API with default (safe, checked) features; match T2's length semantics in a thin wrapper. |
| LZ4 encode (HC 12) | **Port liblz4 1.9.4's level-12 path** (`lz4hc.c` optimal parser plus the hash-chain insert and sequence encoder it calls, BSD-2-Clause, roughly 600-800 lines of Rust), and gate it on byte-identical output against python-lz4 over every LZ4 chunk of the 1.12 dump (the corpus in section 2) and the staged tables. Evaluate **lz4-pure-rs** first as the candidate to adopt or vendor: it claims 1.9.4 parity at HC 9-12 and is BSD-2; adopt only if that corpus check passes and its `libc` use is confined to the CLI. Do not use lz4_flex (no HC) or lz4r (GPL-2.0-only). |
| zstd decode | **ruzstd** decoder; reproduce "content size wins over max_output_size"; corpus check on the 111 game frames. |
| zstd encode | **ruzstd** at Default, used only by the self-tests (T10). |
| ooz decode | **Port** Leviathan (type 12) and the shared entropy decoders from powzix/ooz into a safe-Rust crate, GPL-3.0-or-later; reject every other decoder type, as `read_raw` treats failures (return `None`). Use oozextract only as a cross-check, not a dependency (its MIT label on GPL-derived code, failed docs.rs build, async deps). Gate on byte-identical decode of all 60 685 Oodle chunks against pyooz, then re-scan the APK's packages for decoder types before closing scope. |
| Oodle stored encode | Port `oodle_stored` as is (`CC 0C` + raw per 256 KiB block); it is 10 lines. |

## 6. Leviathan port replay

`hokace-oodle` keeps the existing QTS framing and adapts the Leviathan and shared entropy code
from oozextract 0.5.7 under the original ooz GPL-3.0-or-later terms. It uses safe scalar byte
operations and has no runtime dependencies. The tANS reader zero-pads its forward lookahead
when a short stream ends before the next full 32-bit read. The decoded bits still come from
the recorded payload. [Source and license notices](../hokace/oodle/NOTICE.md)

| Corpus (1.12) | Python-decodable chunks | Exact Rust matches |
|---|---:|---:|
| Game dump | 60,684 | 60,684 |
| Cached normal APK | 108,118 | 108,118 |

`rust/harness/codec_corpus.py` records decoded SHA-256 with pyooz. Pass `--out <index> <game-root>`
for the dump, or `--out <index> --apk <normal.apk>` for the prime layer. Replay each index from
`rust/hokace` with `cargo run --release -p hokace-oodle --example framing -- <index>`. Both
layers use checksum-free Leviathan. The port also writes the existing stored block format.
