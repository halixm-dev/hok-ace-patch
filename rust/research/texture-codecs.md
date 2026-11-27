# Texture and image codecs: what the repo uses, and the pure-Rust route

Research for the Rust migration (`rust/DECISIONS.md`), 2026-11-27. Constraints that shape it:
ADR-005 (pure Rust, no C or C++ bound) and ADR-010 (ASTC output judged by what it decodes to,
`check_graphics.py`'s mean 2.0 / max 48; decoders match exactly; everything else byte for byte).

Sources are cited inline: `file:line` for this repo; the downloaded package sources (texture2ddecoder
1.0.6 sdist, texture2ddecoder 0.1.2 crate, astc-encoder-py 0.1.12 sdist, etcpak 0.9.15 sdist,
imgio 0.2.0 crate, png 0.18.1 crate); crates.io API records; and five experiments run for this note
(section 6). The experiment scripts lived in the session scratchpad and are described there well
enough to re-run.

## 1. What the repo uses

### 1.1 astc_encoder (astc-encoder-py 0.1.12)

The single shipping call site is `tools/mobile_graphics.py`:

| Setting | Value | Where |
|---|---|---|
| Profile | `ASTCProfile.LDR` (= 1, the **linear** LDR profile, not `LDR_SRGB` = 0) | `tools/mobile_graphics.py:391`; enum values in `astc_encoder/enum.py` (installed package) |
| Block footprint | `(bx, by)` from the raw size: 4x4, 5x5, 6x6, 8x8, 10x10, 12x12 (`ASTC_FOOTPRINTS`); every atlas and catalog `.blocks` port is 4x4, a whole-image replacement or splice takes whatever the device texture uses | `tools/mobile_graphics.py:48`, `:237-243`, `:459-474`, `:836-868` |
| Block z | 1 | `tools/mobile_graphics.py:391` |
| Quality | **85** (a float between the presets MEDIUM = 60 and THOROUGH = 98) | `tools/mobile_graphics.py:391`; presets in `astc_encoder/enum.py` |
| Flags | none (`flags=0`, the `ASTCConfig` default): no alpha weighting, no perceptual metric, no `USE_DECODE_UNORM8`, no `SELF_DECOMPRESS_ONLY` | `tools/mobile_graphics.py:391`; default in `astc_encoder/encoder.pyi` (`ASTCConfig.__init__`) |
| Swizzle | `ASTCSwizzle()` = identity RGBA | `tools/mobile_graphics.py:411`; default in `encoder.pyi` (`ASTCSwizzle.__init__`) |
| Input | `ASTCType.U8`, straight (non-premultiplied) RGBA8, in the texture's own **bottom-up** row order | `tools/mobile_graphics.py:410`, `:415`, `:445`, `:687` |
| Threads | `os.cpu_count()` per context; contexts cached per footprint; small inputs (<= 4096 B) memoised by an `lru_cache` of 512 | `tools/mobile_graphics.py:203-209`, `:389-406` |

At quality 85 `astcenc_config_init` interpolates MEDIUM and THOROUGH (LERP over the preset table for
the footprint's bandwidth class, `astcenc_entry.cpp:470-560` in the sdist). The effective tuning, read
back from `ASTCConfig` for every footprint: partition count limit 4, 2/3/4-partition index limits
66/49/25, block-mode centile 88, refinement limit 4, candidate limit 4, partitioning candidates 3/2/2,
MSE overshoot 7.43-7.78, `tune_db_limit` 59.4 (4x4) down to 33.6 (12x12), mode-0 search enable 0.0
(4x4), 0.34 (5x5, 6x6), 1.0 (8x8 and up). So the search reaches **all four partition counts, dual-plane
trials and the full LDR endpoint-mode set** - nothing short of the full compressor.

The encoder library inside astc-encoder-py 0.1.12 is Arm astcenc at commit `631fb04e1c4b` (2024-09-11,
"Add support for fixed-width 128-bit SVE implementation"), after tag 4.8.0 and before 5.0.0 (GitHub
API: `repos/K0lb3/astc-encoder-py/contents/src` and `repos/ARM-software/astc-encoder/commits/631fb04`).
The Windows wheel picks an AVX2, SSE4.1, SSE2 or scalar build at import time from `archspec`
(`astc_encoder/encoder.py`); the Android wheel is built here as scalar and NEON variants with
`-ffp-contract=fast` (`android/native/build_wheels.py:116-122`).

Other users: the frozen exe's `--smoketest` round-trips one flat 4x4 block (max error 8,
`app/hok_patcher.py:1631-1633`); `tools/research/career_atlas/validate_assets.py:121-125` previews an
ASTC round trip at the same settings; `tools/research/check_graphics.py:283-301` is the ADR-010
check (section 4.1). Freezing: `app/build_exe.py:103-104`; Android gate:
`android/app/src/main/python/android_bridge.py:29`; identity hashing: `tools/run_artifacts.py:351-352`.

### 1.2 texture2ddecoder 1.0.6

Only two functions are called, both returning **BGRA8** that the repo swaps to RGBA
(`tools/mobile_graphics.py:427-430`, `tools/bc7_mode6.py:513-516`):

| Function | Use | Where |
|---|---|---|
| `decode_astc(raw, w, h, bx, by)` | every device texture read; every re-run/idempotence comparison | `tools/mobile_graphics.py:359`, `:424`, `:700`, `:818`; `tools/research/check_graphics.py` (many) |
| `decode_bc7(raw, w, h)` | catalog BC7 payloads (`decode_pc`) and the PC edition's atlases; single 4x4 blocks in the BC7 encoder's error loop | `tools/mobile_graphics.py:417`; `tools/bc7_mode6.py:508-516` |

No other `decode_*` (BC1-6, ETC, PVRTC, crunch) is used in `tools/`, `app/` or the Android Python
(grep over those trees). The wxq_patch runtime bytecode does not import any codec (`grep -a` over
`resources/runtime/`).

### 1.3 etcpak 0.9.15 (BC7 encoder only)

`tools/bc7_mode6.py:487-504`: `etcpak.compress_bc7(rgba, 4, 4, params)` on one block at a time, with
`BC7CompressBlockParams()` defaults except `m_uber_level = 2` (`tools/bc7_mode6.py:50`). Its
encoder is Rich Geldreich's `bc7enc.cpp` (4,126 lines, header comment "Currently supports modes 1, 6
for RGB blocks, and modes 5, 6, 7 for RGBA blocks", `etcpak-0.9.15/src/etcpak/bc7enc.cpp:1-2`). Its
own `decompress_bc7` is avoided because it crashed (`tools/bc7_mode6.py:508-512`). Windows-only path:
the PC edition (`app/build_exe.py:119`). A block etcpak leaves above mean 6.0 goes to the repo's own
modes 6/5/4/7, already in Rust (`crates/hok_bc7`).

### 1.4 Pillow 13.0.0

Shipping code reads PNGs and nothing else:

| Operation | Where |
|---|---|
| `Image.open(png).convert("RGBA").tobytes()`, size check against the sprite box | `tools/mobile_graphics.py:484-500` (atlas labels and restore crops), `:660-670` (label textures) |
| Write a 4x4 PNG in the smoke test | `app/hok_patcher.py:1634-1635` |
| Build-time icon: open, LANCZOS resize, paste on a canvas, save ICO and PNG | `app/make_icon.py:19-32` |

The research generators ADR-011 ports use more:

* `tools/research/atlas_sprites.py`: `frombytes` + `FLIP_TOP_BOTTOM` (`:118-119`), `crop`,
  `alpha_composite`, `ImageDraw.rectangle` (`:163-170`), `putpixel`/`putalpha` (`:353-367`),
  **FreeType text**: `ImageFont.truetype(BarlowCondensed-ExtraBold.ttf, 36*4)` (`:68`, `:81-82`,
  `:383-384`), `getbbox(..., stroke_width=...)` (`:406-422`), `ImageDraw.text(..., stroke_width,
  stroke_fill)`, `point`, `Image.composite`, `paste`, and a premultiplied LANCZOS reduction
  `convert("RGBa").resize(size, LANCZOS).convert("RGBA")` (`:425-480`). `make_layout` sizes every title
  from `getbbox` (`:625`), so `layout --check` (`:640-653`) depends on FreeType's metrics.
* `tools/research/make_language_payloads.py:253` opens review renders (its BC7 is its own mode-6
  encoder, `:122-149`, not etcpak).
* `tools/research/check_graphics.py:254` opens PNGs; `validate_assets.py` opens, pads and previews.

Every PNG under `resources/` is 8-bit RGBA, non-interlaced (59 under `resources/sprites/`, `file`
over each).

## 2. Pure-Rust options

### 2.1 Decoder: the `texture2ddecoder` crate 0.1.2

* MIT OR Apache-2.0, `no_std`, author Rudolf Kolbe, the same author as the Python package
  (`Cargo.toml` of the crate; crates.io record, updated 2025-03-21). **Zero `unsafe`** in `src/`
  (grep). Builds for `aarch64-linux-android` (`cargo check --target aarch64-linux-android`, section 6).
* It is a function-by-function translation of the same AssetStudio C++ the Python wheel compiles:
  `astc.rs` (1,849 lines) against `astc.cpp` (1,153), `bcn/bc7.rs` against `bcn.cpp:939-1134`. The
  LDR colour path is identical: `select_color` is the same integer formula in both
  (`astc.cpp:156-158`, `astc.rs:221-225`), the weight infill is the same fixed point
  (`astc.cpp:888-991`, `astc.rs:1371-1502`), the BC7 interpolation and `expand_quantized` match
  (`bcn.cpp:932-1119`, `bc7.rs:127-330`), and both pack a pixel as `b | g<<8 | r<<16 | a<<24`
  (`color.h`, `color.rs:25-27`), so `u32::to_le_bytes` gives the Python's BGRA bytes.
* **FP16 to UNORM8 conversion**: C++ uses `roundf(f * 255)`
  (`astc.cpp:160-181`); Rust uses `floor(f * 255)` (`astc.rs:227-249`). It reaches only HDR endpoint
  modes and **HDR (FP16) void-extent blocks** (`buf[1] & 2`, `astc.cpp:1117-1120`). Measured: 218 of
  439 FP16 void-extent blocks differ by 1 (experiment 1). The repo's encoder (LDR profile) never writes
  either; game textures might.
* **Signed HDR endpoint deltas**: `decode_endpoints_hdr11` in C++ stores the deltas in `int16_t`.
  The Rust crate sets the equivalent 16-bit mask in an `i32`, producing large positive values for
  negative deltas in endpoint modes 11, 14 and 15. The ASTC source in `hokace-codecs` fixes both
  differences. [Rust source](https://docs.rs/crate/texture2ddecoder/0.1.2/source/src/astc.rs)
  [Python decoder's C++ source](https://github.com/K0lb3/texture2ddecoder/blob/master/src/Texture2DDecoder/astc.cpp)
* Input checks differ: the Rust function returns `Err` on short data, too-large blocks, or a short
  output (`astc.rs:1774-1806`); the Python binding passes the buffer through unchecked
  (`pylink.cpp:101-130`). On malformed ASTC blocks the C++ reads out of bounds (11-14 of 20 random
  chunks crashed the Python process, experiment 3; the dump has two such textures,
  `docs/lab-notebook.md:600-603`, and a fixture once SIGSEGV'd the decoder, `:1078`) while the Rust
  **panics** on index bounds (`panic!("Unsupported ASTC format")`, `astc.rs:1364`, `:1406`, `:1443`).

Verdict: for every well-formed LDR block, byte-identical (experiments 1-2: 1,425,887 BC7 blocks,
339,648 encoder-written ASTC blocks over all six footprints, 34 whole images including partial edge
blocks, 0 differing bytes).

### 2.2 ASTC encoders

| Crate | Pure Rust | Status | Fit |
|---|---|---|---|
| `imgio` 0.2.0 (Apache-2.0 AND MIT, rust-version 1.88, edition 2024) | yes; `src/astcenc` is a port of **astcenc 6.0.0**, 26,034 lines of Rust; 50 `unsafe`, all x86-64 intrinsics in `enc/sse.rs` behind `cfg(target_arch = "x86_64")`, with a scalar lane-exact fallback elsewhere (`sse.rs:249`) | created 2026-11-21, 1 GitHub star, one author, 133 downloads (crates.io and GitHub API, 2026-11-27) | the only pure-Rust full astcenc found. Claims byte-identical output against C++ goldens across profiles, presets, flags and ISAs (`docs/spec/astcenc.md` in the repo). Quality 85 is not reachable from the public `Quality` enum (`src/encode.rs:396-401`), only through the crate-internal `astcenc` module (`pub(crate) mod astcenc`, `src/lib.rs:14`), so it would be vendored or forked |
| `ktx-rs` 4.4.4 (qbart) | yes, the earlier astcenc 5.x port that imgio's came from (`NOTICE.md:24` of imgio) | created 2026-10-27, 2 stars | same lineage; carries all of KTX-Software |
| `praxi-encoder` 0.3.1 (qbart) | claims BC7 and ASTC | 2026-11-13, video codec | not a general encoder |
| `astcenc-rs` 0.2.0, `astcenc-sys`, `ctt-astcenc`, `dashpack-astcenc-sys` | **no**: bindings to Arm's C++ | | excluded by ADR-005 |
| `intel_tex_2`, `ispc-tex` | **no**: ISPC binaries | | excluded |
| `basisu` 0.1.0 | pure-Rust transcoder (UASTC to ASTC), not a general ASTC encoder | | no |

(crates.io search API for "astc" and "astc encoder", 2026-11-27.)

Measured on this machine (x86-64, experiment 4), whole-image encode, decoded through texture2ddecoder,
mean / max absolute channel difference to the source:

| Image | Encoder | 4x4 | 8x8 |
|---|---|---|---|
| 592x816 catalog art `10C6E5EC9ABB723E` | astcenc C++ q85 (repo today) | 0.028 / 28, 36 ms | 0.245 / 103, 130 ms |
| | imgio MEDIUM (60) | 0.036 / 32, 26 ms | 0.706 / 103, 64 ms |
| | imgio THOROUGH (98) | 0.025 / 26, 52 ms | 0.225 / 103, 138 ms |
| `1D502C26FF87D4B4` | astcenc C++ q85 | 0.094 / 30, 113 ms | 0.695 / 94, 206 ms |
| | imgio THOROUGH | 0.089 / 30, 98 ms | 0.673 / 94, 194 ms |
| check_codec's 64x64 ramp | astcenc C++ q85 | 0.796 / 4, 7 ms | 1.277 / 7, 9 ms |
| | imgio THOROUGH | 0.735 / 4, 24 ms | 1.275 / 7, 38 ms |

imgio at MEDIUM matches astcenc's MEDIUM quality, and at THOROUGH matches or beats the repo's q85, at
similar whole-image speed on x86-64. Its bytes are not the repo's bytes (it ports 6.0.0, the repo runs
a 4.8-era commit; 1 of 12 cases came out byte-identical), which ADR-010 allows. Two costs show: the
public `encode` builds a new context per call (18-24 ms for a 64x64 image against astcenc's 4-7 ms),
which matters because the pipeline makes thousands of small strip encodes (3,654 compressor calls in one
profiled run, `docs/lab-notebook.md:2199`); and its aarch64 speed is unmeasured: off x86-64 it runs the
scalar emulation of the SSE lanes, not NEON (`enc/sse.rs:249`), and ASTC encoding is already 4-50 s of a
phone run (`docs/lab-notebook.md:2171-2172`).

### 2.3 PNG and image

* `png` 0.18.1 (MIT OR Apache-2.0, `#![forbid(unsafe_code)]` in `src/lib.rs`, rust-version 1.73).
  Decoding every one of the 105 PNGs under `resources/` with `Transformations::EXPAND | ALPHA |
  STRIP_16` gives exactly Pillow's `convert("RGBA").tobytes()` (experiment 5, 0 differ). That is
  all the shipping code needs.
* `image` 0.25.10 (MIT OR Apache-2.0, rust-version 1.88, 11 `unsafe` lines) covers `make_icon.py`'s
  ICO/PNG writing and resize, but its Lanczos3 is its own float kernel, not Pillow's fixed-point
  `Resample.c`, so the pixels of a resized image will differ. That matters only where a check compares
  resized output: `make_icon.py` is build-time, and `atlas_sprites.py`'s `title_label` only drafts (the
  shipped labels are hand-finished and never regenerated, `atlas_sprites.py:11-17`, `:685-690`).
  `fast_image_resize` 5.3.0/6.2.0 carries 669 `unsafe` lines (SIMD); not needed.
* Compositing (`alpha_composite`, `putalpha`, `point`, `composite`, crops) is a few dozen lines of
  integer code; Pillow's `alpha_composite` rounding would have to be copied if a `--check` compares
  its output, which none does today (`_same_pixels` compares a restore crop, not a composite,
  `atlas_sprites.py:176-180`).

### 2.4 Font rasterising

Only `tools/research/atlas_sprites.py` draws text (section 1.4); no shipping code does. Candidates:
`ab_glyph` 0.2.32 (Apache-2.0, 0 `unsafe`; `ab_glyph_rasterizer` 0.1.10 has 5), `fontdue` 0.9.5
(MIT OR Apache-2.0 OR Zlib, 30 `unsafe`), `swash` 0.2.10 (Apache-2.0 OR MIT, 54 `unsafe`; has hinting
and shaping). None reproduces Pillow's FreeType path (hinted outlines, `FT_Stroker` for
`stroke_width`, Pillow's bbox arithmetic), so `title_size` and therefore `layout.json` would change.
(`unsafe` counts: grep over each crate's `src/`.)

## 3. A faithful astcenc port versus a simpler encoder

**Source size.** The astcenc library in the wheel is 27,903 lines (`Source/astcenc_*.cpp|h`, `wc -l`).
Of that, about 5,900 are the four ISA headers (`vecmathlib_{none,sse,avx2,neon}*.h`), which collapse to
one Rust vector layer; the diagnostic trace (464) and `compute_variance` (472, alpha scaling, unused at
`a_scale_radius` 0) are not reached; HDR endpoint packing in `color_quantize.cpp` (2,149) and HDR
unquantize are unreachable in the LDR profile. What the repo's preset does reach: config init and the
preset LERP, block-size descriptors with the percentile tables (`block_sizes` 1,184 +
`percentile_tables` 1,251), partition tables and `find_best_partitioning` (481 + 781), averages and
directions (948), ideal endpoints and weights (1,658), angular weight alignment (482), endpoint format
choice (1,350), LDR colour quantisation, `compress_symbolic` with 1-4 partitions and dual plane (1,456),
integer-sequence and symbolic-to-physical packing (739 + 544), the symbolic decoder used for errors
(622), and the U8 image loader (558). Roughly 14,000-16,000 lines of C++ on the reached path; imgio's
equivalent is 26,034 lines of Rust including tables and LZ-RDO.

**Bit-exactness is not on offer anyway.** The repo's own two builds already disagree: the Android
(NEON, `-ffp-contract=fast`) and Windows outputs of the same run differ in 192 ASTC textures
(mean 0.0094, max channel 46, `docs/lab-notebook.md:1077`); `label_texture` notes 1-4 of 1054 blocks
differ between processes (`tools/mobile_graphics.py:696-698`); and imgio's notes record that astcenc's
`sinf`/`cosf` tables differ by 1 ulp between libms. ADR-010 was written for this.

**A simpler encoder** that meets check_codec's limits is small: the ramp is smooth and opaque, and a
one-partition, one-plane encoder with a least-squares RGBA line, a few weight grids and the integer
sequence encoder (perhaps 3,000-5,000 lines with the block-mode and partition tables, which the format
fixes) would pass mean 2.0 / max 48. It would not hold the quality the pipeline relies on: label glyph
edges need 2-3 partitions and dual plane (the same reason the BC7 side needed modes 4, 5 and 7,
`tools/bc7_mode6.py:19-23`), 8x8/6x6 whole-image replacements need the block-mode search, and the
pipeline's own gates (`BLOCK_MATCH_MEAN` 6.0 premultiplied, `tools/mobile_graphics.py:191`;
`LABEL_MATCH_MEAN` 12.0, `:64`; the `label_atlas` fixed point within `LABEL_PASSES` 4, `:165`, `:645-655`)
would trip more often, re-encoding blocks and possibly breaking idempotence.

**Estimate.** Vendoring imgio's `src/astcenc` (Apache-2.0, attributions in its `NOTICE.md`), exposing
`config_init(LDR, bx, by, 1, 85.0, 0)`, a reusable context and a block-strip entry point: days, plus
proof on the 1.12 dump. Porting astcenc ourselves on the reached path: weeks, with the same proof.
A simple encoder: a week or two, with a quality gap that only a device cycle could clear.

## 4. Traps

1. **What "mean 2.0, max 48" measures.** `check_graphics.py:59-60, 283-301` applies it to one 64x64
   opaque ramp at 4x4 against its **source**. On real art the current encoder itself exceeds max 48
   at 8x8 (max 94-104 against the source, experiment 4). Applied per texture, the limit has to be read
   as "Rust encoder's decode against the Python encoder's decode", as the Android/Windows comparison
   did (`docs/lab-notebook.md:1077`), or it fails the reference too. Worth stating in ADR-010.
2. **Row order.** PC and device textures are stored bottom-up; both decoders return storage order with
   no flip (`color.h:78-85`, `color.rs:83-105`); `decode_pc` documents it (`mobile_graphics.py:414-415`).
   PNG art is top-down and is flipped before encoding (`:687`), drawn with `height - 1 - y`
   (`:560-565`, `:706-716`), and block indices mirror rows (`:718-726`). The `png` crate, like Pillow,
   returns top-down.
3. **Channel order.** texture2ddecoder returns BGRA (both); astcenc and etcpak take RGBA. The Rust
   crate returns `u32` per pixel: write it with `to_le_bytes` to get the Python's bytes on both
   targets.
4. **sRGB versus linear.** The encoder must use the linear `LDR` profile. `LDR_SRGB` changes the error
   weighting and forces UNORM8 decode rounding for RGB (`ASTCConfigFlags` docs, `astc_encoder/enum.py`).
   texture2ddecoder has no colour-space notion at all.
5. **Decoder rounding.** texture2ddecoder's LDR output is not astcenc's: on encoder output about 10 % of
   channels differ by 1 from astcenc's own decoder (27,315 of 262,144, experiment 6, both 4x4 and 8x8).
   The repo judges every block by texture2ddecoder, so a new encoder should score its candidates with
   the same `select_color` rounding or accept a little slack; `USE_DECODE_UNORM8` is off today, so do not
   turn it on.
6. **FP16 void-extent and HDR.** Preserve rounding (C `roundf`) and sign extension for the endpoint
   deltas. Both affect valid HDR blocks (section 2.1).
7. **Malformed blocks.** The Python decoder can crash the process; the Rust crate panics. Wrap decodes
   in `catch_unwind` or patch the bounds, and keep "decode failed" a skipped texture, never a failed
   run (AGENTS.md, *Skipped textures*).
8. **Alpha.** Straight alpha in and out. astcenc runs without alpha weighting, while the repo's stale
   test is premultiplied (`tools/block_scan/__init__.py:10-27`) and the art is white-on-alpha
   (`atlas_sprites.py:362-366`). A new encoder with alpha weighting would change which blocks the
   stale scan re-encodes.
9. **Footprints and edges.** Six square footprints only; partial edge blocks (568x70 at 8x8) are padded
   by astcenc's clamped loads; the decoder crops (`copy_block_buffer`). A partial-block encoder must
   pad the same way or accept different (invisible) padding error.
10. **Threads and caching.** The current output is byte-identical at 1-12 threads (comment at
    `tools/mobile_graphics.py:205-206`) and small encodes are memoised; a port must be deterministic for
    a given input or the re-run guards (`LABEL_TEXTURE_KEEP` 2, `:183`) start keeping stale output.
11. **BC7 first candidate.** The Python path runs etcpak's `bc7enc.cpp` at uber level 2, then tries
    its own modes when the first candidate's premultiplied mean difference exceeds 6. ADR-027
    evaluates the final block after decoding. The `rustbcx` subset matched the final Python bytes on
    every recorded encoder call in both PC catalog builds (experiment 8).
12. **BC7 float operations.** The shared fallback search calls `f64::powf` with an opaque exponent
    to preserve CPython 3.12's `float_pow` behavior. The standard library uses the platform's
    math implementation, so replay the fallback search when changing the target or toolchain.
13. **FreeType metrics in a check.** `atlas_sprites.py layout --check` compares a layout computed from
    FreeType bboxes; a pure-Rust rasteriser cannot pass it as written.

## 5. Recommendation per codec

| Codec | Recommendation |
|---|---|
| ASTC and BC7 decode (texture2ddecoder) | Use the `texture2ddecoder` crate 0.1.2 for BC7. The ASTC-only source in `hokace-codecs` matches the Python decoder's HDR rounding and signed endpoint deltas. Wrap each texture's decode in `catch_unwind` and map a panic to a skipped texture. |
| ASTC encode (astcenc) | Vendor imgio 0.2.0's `src/astcenc` (Apache-2.0) into a workspace crate, call it at LDR / 85.0 / no flags / identity swizzle with one reused context per footprint, and judge it under ADR-010 against the Python encoder's decoded output on the 1.12 dump in both languages, plus `check_graphics.py`. Measure it on the phone before committing: it runs scalar on aarch64. Fall back to our own port of astcenc's reached path only if the vendored code fails that comparison; do not write a simplified encoder. |
| BC7 encode (etcpak `bc7enc.cpp`) | Use the `rustbcx` 0.8.0 single-block encoder at uber level 2 and the shared `hok_bc7` fallback search. Replay `rust/harness/bc7_case.py` captures for the complete output and `tools/research/bc7_corpus.py replay --backend native --final` for the existing Python extension. |
| PNG read (Pillow) | `png` 0.18.1 with `EXPAND | ALPHA | STRIP_16`; identical to Pillow on all 105 repo PNGs. |
| PNG/ICO write, resize (`make_icon.py`) | `image` 0.25.10 (`png`, `ico` features only), or keep `make_icon.py` as a build-time Python step; its output is a checked-in asset, not run output. |
| Compositing in the research generators | Hand-written integer code; copy Pillow's rounding only where a `--check` compares the result. |
| Font rasterising (`atlas_sprites.py`) | Do not try to match FreeType. Record each title's measured `title_size` in `layout.json` (or a fixture) so `layout --check` needs no font, and use `ab_glyph` (0 `unsafe`) for `labels --out` drafts, accepting different draft pixels. Raise it as a decision against ADR-011. |

## 6. Experiments

All on Windows 11 x86-64, Python 3.12 `.venv`, Rust 1.99.1, 2026-11-27.

1. **Per-block decode, Python vs Rust crate.** A Rust harness decoded each 16-byte block alone with
   `texture2ddecoder` 0.1.2; Python decoded the same with 1.0.6. Inputs: every BC7 block of the 369 BC7
   catalog payloads (1,225,887 blocks), 200,000 random BC7 blocks, ASTC blocks astcenc wrote at LDR q85
   from 12 catalog images at each of the six footprints (339,648), and 439 FP16 void-extent blocks.
   Result: 0 differing bytes except the void-extent set (218 differ, max 1).
2. **Whole images.** 30 ASTC images (5 sizes including 101x37, 17x250 and 3x3, 6 footprints) and 4
   random BC7 images: 0 of 34 differ.
3. **Random ASTC bytes.** 20 chunks of 2,000 random blocks at 4x4, 8x8 and 12x12, Python in a child
   process: 11, 13 and 14 chunks crashed it; the Rust crate panicked on about 40 % of blocks; outputs
   on the rest differ (undefined input).
4. **Encoder bench.** Three largest BC7 `.assets` images and check_codec's ramp, encoded by astcenc
   (astc-encoder-py, all cores) at q60/85/98 and by imgio 0.2.0 at MEDIUM/THOROUGH, all decoded by
   texture2ddecoder; table in section 2.2.
5. **PNG.** `png` 0.18.1 against Pillow 13.0.0 `convert("RGBA").tobytes()` on all 105 `resources/**/*.png`:
   0 differ.
6. **texture2ddecoder vs astcenc's decoder** (`ASTCContext.decompress`, DECOMPRESS_ONLY) on a 256x256
   encode at 4x4 and 8x8: 27,315 and 27,444 of 262,144 channels differ, max 1.
7. **HDR decoder parity.** `rust/harness/codec_tap.py --astc-hdr <tap>` records 64 void-extent
   images covering all 65,536 binary16 channel bit patterns and 60 images with 3,840 encoded HDR
   and HDR RGB / LDR alpha blocks across the six pipeline footprints. `cargo run --release -p
   hokace-codecs --example tap -- <tap>` replayed 124/124 against Python. The original crate matched
   54/124. Rounding alone brought that to 64/124, and sign-extending the HDR endpoint deltas closed
   the remaining 60 differences.
8. **BC7 encoder parity.** `rust/harness/bc7_case.py --game <copy> --work <fresh-dir>` recorded all
   38,175 English and 38,360 Indonesian blocks from cold Python PC catalog builds on the 1.11.0.2
   copy used by the original BC7 corpus. `cargo run --release -p hokace-codecs --example bc7 --
   <bc7-en.bin> <bc7-id.bin>` matched every 16-byte block. Decoded mean and maximum differences
   were both zero. The rebuilt Python extension additionally matched all five modes and final blocks
   on the existing 20,057-record corpus. The vendored single-block subset builds on Rust 1.99.1.
   The full crate declares Rust 1.100.
   [rustbcx source](https://github.com/OctoKeights/rustbcx/tree/e58a6dde6ade655bbba8357615cd48a59d6fdb39)

9. **Solid ASTC encoding.** `cargo run --release -p hokace-codecs --example astc_solid -- <tap-dir> ...`
   compares each solid source block to the corresponding block from Arm's encoder. The 1.12 English
   tap matches all 86,195 solid blocks. `codec_tap.py --astc-solid <tap>` adds 1,536 blocks covering
   every RGBA8 channel value at all six footprints, including partial blocks. All match exactly.
10. **Non-solid ASTC encoding.** An imgio backport experiment restored reverse dual-plane search,
    4-partition tuning and weight refinement. It still failed 57 of 1,272 English calls under
    `astc_replay.py <tap-dir> <candidate-dir>`. The footprint breakdown is 6 of 1,190 at 4x4, 11 of 18
    at 6x6 and 40 of 64 at 8x8. Re-encoding the same inputs in Python on one thread matched all recorded
    bytes. Start the non-solid port at 4x4 with the one-partition dual-plane cases `700a9801…` at (0, 2)
    and `ec24ae6c…` at (328, 2). Both encoders select mode 1106 in those blocks. Decode the symbol fields
    and trace endpoint fitting and quantized weights against Arm's diagnostic build before changing
    partition selection. [Pinned Arm source](https://github.com/ARM-software/astc-encoder/tree/631fb04e1c4b/Source)

`cargo check --release --target aarch64-linux-android` passed for harnesses depending on
`texture2ddecoder` 0.1.2, `imgio` 0.2.0 (default features off) and `png` 0.18.1; nothing was linked or
run on a phone.
