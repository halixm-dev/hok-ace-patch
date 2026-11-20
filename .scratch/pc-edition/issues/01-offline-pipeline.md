# 01: Engine hooks, the per-install catalog and BC7 atlas ports, offline

**What to build:** everything the PC edition needs from the pipeline, testable on a scratch copy of the PC edition's packages without the interface. See the [spec](../spec.md): *Code shape*, *What the per-install catalog carries*, *Shared texture code* and *Speed*.

- **`tools/engine_hooks.py`:** `install()` puts the `load_catalog` (terminology), `scan` (token expansion) and `receipt_root` hooks in place, idempotently. `scan` and `receipt_root` are taken only for a PC job, through an explicit argument. `terminology.install` moves in, and `build_device_patch` calls it from there.
- **Token expansion:** `build_device_patch._expand_staged_tokens` moves into `resource_tokens` as one function. Mobile calls it where it does today, and the PC `scan` hook calls the same function.
  - Before relying on the hook, check that the engine records no replacement hash between `scan` and `commit`. If it does, stop and ask.
- **`mobile_graphics.port_atlas`:** gains `codec: "astc" | "bc7"`. `tools/bc7_mode6.py` comes over from the fork as the encoder.
- **`tools/pc_catalog.py`:** builds the per-install catalog for one game and language:
  - regioned atlases at the PC sprite table (package 19);
  - Indonesian re-drawn payloads re-hashed from the installed original;
  - the Lua label and edits as whole-file entries;
  - a hard-linked stage under `<work>\pc\<game-id>\catalog\`, named after the language's catalog folder;
  - a cache keyed by `VERSION`, the language and the input asset hashes.
- **`extra_text`:** records the Lua scripts' PC package (10) next to `SCRIPT_EDITS`. Any other package is reached by a logged fallback scan.
- **Speed:** time each part against the fork on the same scratch copy. If BC7 encoding is the slow step, record that and ask before adding a native encoder.

**Blocked by:** none

**Status:** needs-triage

- [x] Mobile `--selftest` gives an identical summary and identical staged bytes before and after
- [x] `check_graphics.py` BC7 case passes: a re-run re-encodes nothing
- [x] `pc_catalog` builds both languages on a scratch copy, and a second build reuses the cached stage
- [x] Timings of the fork and this repo in `docs/lab-notebook.md`
- [x] The staging-contract docstring and `docs/features/texture-translation.md` updated where `port_atlas` and the token pass changed

## Comments

2026-11-20, Claude (branch `feat/pc-edition-01-offline-pipeline`):

- **Token hook check:** the engine records no replacement hash between `adaptive.scan` and `commit`
  (read from the disassembly of `wxq_patch.adaptive`), so the `scan` hook may rewrite the materialized
  replacements.
- **Mobile `--selftest`, identical:** `python run_selftest.py <src> D:/scratch/layer-verdict/session/game
  <out> en|id` (it calls `hok_patcher.selftest` from a source tree), on the pre-change tree and on this
  branch after its last edit. `selftest.json` is identical in both languages, and so are the SHA-256 of
  all 14 staged files.
- **`check_graphics.py` BC7 case:** `.venv\Scripts\python.exe tools\research\check_graphics.py` passes
  all sections (136 s). In `[13]`, "a re-run over its own output re-encodes nothing" reads 0 blocks for
  both the Career port and the Secret Technique titles. Getting there took two user decisions, both
  recorded in the lab notebook. BC7 was the slow step, so etcpak 0.9.15 was added as the first encoder.
  No BC7 encoder brought about 2600 alpha'd title-edge blocks within 6 levels, so BC7 blocks are judged
  by `BC7_MATCH_MEAN` = 14 while ASTC keeps 6. The random-noise round trip was replaced by 64 Career
  English blocks, judged premultiplied by `BLOCK_MATCH_MEAN` (worst 5.44). That limit is the port's
  own; a 4-level limit fails at 5.44.
- **`pc_catalog`, both languages, cached:** `python tools\pc_catalog.py --game
  D:/scratch/pc-edition-01/pc-game --resources resources --language en|id --work <dir>` on a copy of
  packages `0 1 10 15 19`. English was built in 124.1 s (48 assets patched) and Indonesian in 81.7 s
  (49). Second builds printed "stage reused" (0.03 s and 0.02 s). 400 payloads hard-linked, 0 copied.
  The ready atlas `E86DF43167CA2143` is refused at this installation's sprite table (no
  `Image_1585869273`) and dropped from the copy.
- **Timings:** in `docs/lab-notebook.md`, 2026-11-20, "PC edition ticket 01". The fork takes 32–37 s
  per first build and as long again with nothing changed (no cache). This repo does more work
  (titles, relayout, Lua) and takes 124 s and 82 s first, then 0.03 s.
- **Docs:** the `build_patch` docstring now names `engine_hooks.install` and
  `resource_tokens.expand_staged` and the codec argument. `docs/features/texture-translation.md` has
  the section "The PC edition: the same ports in BC7". `resource-token-expansion.md` and
  `terminology-table.md` name the moved functions. `check_references.py` and
  `check_staging_contract.py` pass.
- **Left for ticket 02:** etcpak is in `requirements.txt` but not yet in the freeze (`app/build_exe.py`,
  `--smoketest`). Nothing ships `pc_catalog` until `app/pc_edition.py` exists.
