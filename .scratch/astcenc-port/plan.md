# Port Arm astcenc to Rust, byte for byte

Status: ported (2026-11-27): both taps match byte for byte at 1, 3 and 12 threads. Replaces ADR-026's vendored imgio route at the user's choice
("Port Arm astcenc anyway").

## Target

The bytes `tools/mobile_graphics._encode_astc` gets on Windows: astc-encoder-py 0.1.12's Arm astcenc
(commit `631fb04e1c4b`, the sdist's own copy of `Source/`), LDR, quality 85, no flags, identity
swizzle, U8 input, one context per footprint.

Measured on the 1.12 English tap (1,272 encode calls):

- All four Windows builds (`_encoder_avx2`, `_sse41`, `_sse2`, `_none`) give the same bytes: Arm's
  default invariance is on (`ASTCENC_NO_INVARIANCE` undefined) and MSVC `/fp:precise` never fuses
  a multiply and an add.
- `rust/harness/astcenc_oracle` (the sdist's sources, scalar ISA, `/fp:precise /O2`) gives the same
  bytes on all 1,272.
- The Android NEON build (`-ffp-contract=fast`) is not the target: it already differs from Windows
  (lab notebook, 192 textures).

So the Rust port follows the **scalar** (`none_4`) vector layer, 4 lanes, with no FMA anywhere
(Rust never contracts on its own; never call `mul_add`).

## Floating-point rules

- Every `float` is `f32`; keep C++'s evaluation order and its implicit `float`/`double`/`int`
  conversions exactly. `1.0f / x` stays a division.
- libm: the reached code calls `sinf`/`cosf` (weight-align tables), and the config interpolation in
  `astcenc_entry.cpp`. On Windows Rust's `f32::sin` reaches the same UCRT; on Android it would not.
  Generate any libm-derived table on Windows and embed it, or prove the call matches.
- `astc::` helpers in `astcenc_mathlib.h` (`flt_rd`, `int_to_float`, `float_as_int`, `clamp1f`...)
  are ported one for one.

## Order (each step checked before the next)

1. Vector layer: `vecmathlib_none_4.h`, `common_4.h`, the `vecmathlib.h` helpers; `mathlib.h/.cpp`,
   softfloat.
2. Tables: `quantization`, `weight_quant_xfer_tables`, `percentile_tables`, `integer_sequence`.
3. `block_sizes` (block-mode and decimation tables), `partition_tables`. Check: dump the
   oracle's `block_size_descriptor` and compare field by field.
4. `image` (U8 block load), `averages_and_directions`, `ideal_endpoints_and_weights`,
   `weight_align`, `find_best_partitioning`, `pick_best_endpoint_format`, `color_quantize` (LDR),
   `color_unquantize`, `decompress_symbolic`, `symbolic_physical`.
5. `compress_symbolic`, `entry` (`config_init` with the quality LERP, context alloc, single-thread
   `compress_image`).
6. Replay: every encode call of both language taps, byte for byte against the oracle and Python.

Divergence hunting: build the oracle with `/DASTCENC_DIAGNOSTICS` for the per-block search trace
and compare the Rust side's trace at the first differing block.

## Not reached (not ported)

HDR endpoint packing and unquantise, `compute_variance` (alpha scaling off), the diagnostic trace,
decompress-only contexts, the 8-wide (AVX2) vector layer, NEON kernels on aarch64.

## Speed (2026-11-27)

The 4-lane layer runs SSE2 kernels on x86_64 (`src/lanes.rs`, through `safe_arch`), and the
bilinear infill taps are inlined functions instead of closures. On the English tap it takes 49 s
at one thread and 13.4 s at 12; the first port took about 120 s and 25 s, and the AVX2 wheel
takes 32.8 s and 12.4 s. The ties-to-even `round` is exact in SSE2 (`(|a| + 2^23) - 2^23`, sign
put back). Both taps still match byte for byte at 1, 3 and 12 threads.
