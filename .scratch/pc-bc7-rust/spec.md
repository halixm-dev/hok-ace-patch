# Port the PC BC7 mode 7 encoder to Rust

## Problem

The first English PC catalog build spent 174 of 241 profiled seconds in Python's mode 7 fallback. The first encoder, etcpak, processed 29,960 blocks in 1.2 seconds. A fivefold speedup of mode 7 alone would save about 139 seconds on that historical profile. Measure today's unprofiled build before making a release claim. [Lab notebook](../../docs/lab-notebook.md)

## Implementation decisions

Port the final mode 7 candidate and the math it calls. Keep Python 3.12's `encode_block(pixels) -> bytes` as the caller interface. Preserve etcpak, the order and early exits for modes 6, 5 and 4, and the final candidate comparison. The Android ASTC pipeline, catalog contents, sprite placement and receipt format are outside this port.

Use a small Windows Rust/PyO3 extension built in release mode. Suggested private interface: `encode_mode7(rgba: bytes) -> bytes`, taking exactly 64 row-order RGBA bytes and returning one 16-byte BC7 block. Adapt this result to the existing candidate-selection code in Python. Use the existing independent decoder to obtain candidate pixels and verify its output against the reference. Keep the Python implementation available for source runs and differential tests. Make native selection explicit in verification so silent fallback cannot produce a passing benchmark or release smoke test.

## Execution order

| Order | Deliverable | Finish when |
|---|---|---|
| 1 | [Baseline and reference blocks](issues/01-baseline.md) | Another run can reproduce the input blocks, expected bytes and cold-build timing. |
| 2 | [Rust port and parity](issues/02-port.md) | Native mode 7 produces the reference bytes and wins an unprofiled comparison. |
| 3 | [Windows delivery and verification](issues/03-delivery.md) | The frozen executable exercises native mode 7 and both languages pass the catalog comparison. |

Start at ticket 01. Work in the existing checkout and preserve concurrent edits. Record measured results, fixture identity and any missing hardware or game copy in the handoff. Keep game dumps and generated atlases in the chosen work folder.

## Handoff (2026-11-26)

Numbers, fixture digests and the environment are in the [lab notebook](../../docs/lab-notebook.md), 2026-11-26 "PC BC7 mode 7 in Rust".

- **Built:** `crates/hok_bc7` (Rust 1.99.1 pinned by `rust-toolchain.toml`, PyO3 0.30.1 locked in `Cargo.lock`, x64 MSVC). It is a bit-exact port of `bc7_mode6._mode7_python`. `bc7_mode6._mode7` dispatches to it through `mode7_backend_name`/`MODE7_ENV`. `app/build_exe.py` builds it (`--native-only` for just the `.pyd`), and the Windows workflow installs the pinned toolchain.
- **Fixtures:** the work folder is `D:/scratch/pc-bc7-rust/`, with the game copy in `game/`, the corpus in `corpus/game-{en,id}.{bin,json}` and `synthetic/corpus/synthetic.*`, and timings in `timing-{python,native}.json`. Regenerate them with `tools/research/bc7_mode7_corpus.py` (`capture`, `synthetic`, `replay`, `time-build`). The smoke test's fixture block is synthetic record 69.
- **Measured:** parity on 16,398 game and 2013 synthetic blocks, final `encode_block` bytes included. Mode 7 runs 50× faster. Cold builds dropped from 80.3 s to 27.7 s in English and from 77.9 s to 30.9 s in Indonesian, with byte-identical catalogs.
- **Not run:** the PC cycle on the installed game (runbook `docs/runbooks/pc-cycle.md`) and `check_pc_install.py` on a copy. The staged catalogs are byte-identical, so neither is expected to differ.
