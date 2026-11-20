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

- [ ] Mobile `--selftest` gives an identical summary and identical staged bytes before and after
- [ ] `check_graphics.py` BC7 case passes: a re-run re-encodes nothing
- [ ] `pc_catalog` builds both languages on a scratch copy, and a second build reuses the cached stage
- [ ] Timings of the fork and this repo in `docs/lab-notebook.md`
- [ ] The staging-contract docstring and `docs/features/texture-translation.md` updated where `port_atlas` and the token pass changed

## Comments
