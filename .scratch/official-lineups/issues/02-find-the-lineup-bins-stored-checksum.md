# 02: Find the lineup bins' stored checksum

**What to build:** a verdict on whether the lineup bins can be rewritten without the game dropping them. Every config bin withdrawn so far stores an MD5 that a rewrite leaves stale. The game then drops what the bin feeds: the Diamond Frenzy Starting Lineup grid drew empty when its bin was appended (lab notebook, 2026-10-16), and ADR 0005 records the Talent Card grid case. This ticket finds out whether the same applies here before any device work.

- For each of the three bins, look for stored digests (16-byte MD5 or a hex string) per row and per file, in both data layers.
- Work out what each digest covers by recomputing it over candidate spans (the row, the code field, the decoded code, the whole bin, with or without a salt). Read the game's own checking code in package `10` (the data-bin loader, `GetMd5WithSalt`) for the salt and the span.
- If a digest is recomputable, prove it offline: change one string, recompute, and show the result matches the game's own check as the Lua does it.
- ADR 0004 dropped `pb_text.has_row_checksum` as a gate. This ticket measures; it does not reintroduce a heuristic gate.

**Blocked by:** None (can start immediately)

**Status:** done

- [x] Stored digests located (or shown absent) in each bin, both layers
- [x] What each covers, with the recomputation that matches
- [x] Verdict: recomputable, no checksum, or neither. If neither, stop the effort before ticket 04 and say so here.
- [x] Findings added to `docs/lab-notebook.md`

## Comments

2026-10-21: done offline with `tools/research/config_bin_checksum.py` (lab notebook, "Config bin checksums recomputed"). **Verdict: recomputable.**
- Field 1 is `MD5(rows concatenated)`, upper-case hex.
- Field 4, the value the game checks, is a per-byte fold `h = (h ^ byte) * 0x89ABCDEF` seeded `0x01234567`, over the rows, then the index keys, then the index entries (each as 4 little-endian bytes). The check is native (`PBDatabinLoader.cpp` `DecodeFromStream`), not Lua.
- Both values recompute on every config bin of package `1` in both layers.
- For ticket 04: rewrite the codes, keep the index (no key changes), then call `reseal` to recompute fields 1 and 4.
