# 02: Find the lineup bins' stored checksum

**What to build:** a verdict on whether the lineup bins can be rewritten without the game dropping them. Every config bin withdrawn so far stores an MD5 that a rewrite leaves stale. The game then drops what the bin feeds: the Diamond Frenzy Starting Lineup grid drew empty when its bin was appended (lab notebook, 2026-10-16), and ADR 0005 records the Talent Card grid case. This ticket finds out whether the same applies here before any device work.

- For each of the three bins, look for stored digests (16-byte MD5 or a hex string) per row and per file, in both data layers.
- Work out what each digest covers by recomputing it over candidate spans (the row, the code field, the decoded code, the whole bin, with or without a salt). Read the game's own checking code in package `10` (the data-bin loader, `GetMd5WithSalt`) for the salt and the span.
- If a digest is recomputable, prove it offline: change one string, recompute, and show the result matches the game's own check as the Lua does it.
- ADR 0004 dropped `pb_text.has_row_checksum` as a gate. This ticket measures; it does not reintroduce a heuristic gate.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Stored digests located (or shown absent) in each bin, both layers
- [ ] What each covers, with the recomputation that matches
- [ ] Verdict: recomputable, no checksum, or neither. If neither, stop the effort before ticket 04 and say so here.
- [ ] Findings added to `docs/lab-notebook.md`
