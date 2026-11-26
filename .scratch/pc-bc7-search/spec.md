# Port the PC BC7 modes 6, 5 and 4 to Rust

Status: ready-for-human (everything but the PC cycle on the installed game is done; see Handoff)

## Problem

After mode 7 went native ([pc-bc7-rust](../pc-bc7-rust/spec.md)), a cold English PC catalog build took about 28 s, and about 18 s of it was the Python modes 6, 5 and 4 that `encode_block` tries on every block etcpak leaves above `NATIVE_GOOD_ENOUGH`. The user asked for them to be ported too (2026-11-26).

## Decisions

- **One native search.** `crates/hok_bc7` runs `encode_block`'s whole loop past etcpak (`encode_search(rgba, best_error) -> (block | None, modes tried)`): modes 6, 5, 4 (index mode 0, then 1) and 7, in `ENCODERS` order, with the same strict first-winner comparison and the same `GOOD_ENOUGH` early exit. Each mode's error comes from its own decoded pixels, as the Python reference computes it, so no texture2ddecoder call runs per mode.
- **One generic line fit.** `_initial`, `_assign`, `_refine` and `_fit` are ported once, over 1, 3 or 4 channels, 2-, 3- or 4-bit indices and each quantizer (`QUANTIZE_5..8`, `_quantize_pbit`, `_quantize_pbit5`). Mode 7 now runs through the same fit, so its corpus was replayed again.
- **Python 3.12 float behavior** as for mode 7 (Neumaier `sum()`, the C runtime's `pow` for `** 2`), plus `round()` rounding half to even.
- **Interface.** `encode_mode(rgba, mode, index_mode=0) -> (block, decoded RGBA)` serves the parity checks; `encode_mode7` stays. `HOK_BC7_MODE7` became `HOK_BC7_ENCODER`, because it now selects the backend for every hand-written mode. A `hok_bc7` build without `encode_search` counts as not built.
- **Corpus tool.** `bc7_mode7_corpus.py` became `tools/research/bc7_corpus.py`. A record now holds the input, the final `encode_block` bytes and each mode's reference block and decoded RGBA, for every block the search saw.

## Handoff (2026-11-26)

Numbers are in the [lab notebook](../../docs/lab-notebook.md), 2026-11-26 "PC BC7 modes 6, 5 and 4 in Rust". The work folder is `D:/scratch/pc-bc7-search/`: the corpora are in `corpus/` and `synthetic/corpus/` (both in `all/corpus/` for replay), the timings in `timing/`, and the game copy is still `D:/scratch/pc-bc7-rust/game`.

- **Not run:** the PC cycle on the installed game (`docs/runbooks/pc-cycle.md`), the frozen `--pc-selftest` and `check_pc_install.py` on a copy. The staged catalogs are byte-identical to the previous native build's, so none of them is expected to differ.
