# T13 — Independent review of the sign-branch amendment (uncommitted working tree on top of b670d90)

Reviewed: the uncommitted working-tree change to `tools/resource_tokens.py` + `docs/features/resource-token-expansion.md`
(`git status` = `M docs/features/resource-token-expansion.md`, `M tools/resource_tokens.py`, `?? tasks/`; diff vs
b670d90 = 31 lines module + 41 lines spec, README **not** touched). Read-only review: I modified nothing except this file.
The ~1-minute pipeline and the exe build were **not** re-run; all conclusions come from the pre-fix oracle, the on-disk
runs, and my own independent implementation.

Environment at review time: oracle `dist\HOK ACE Patcher Data\sessions\20260929-212059\build\scan\replacements\1`
intact (87 assets, 3067 `{Energy}` + 451 `{LordExp}` + 608 `{LordHp}` = 4126 occurrences); `run4` (source, 22:13:55),
`run5` (frozen exe, 22:19:10), `fitwork3`/`fitout3` present; exe 22:17:50 > module 22:13:37.

---

## Verdict 1 — T5 as amended: intent MET, but T5's own text is now stale

The **rule** changed correctly and the change is justified by evidence I re-derived myself:

| Evidence (independently re-counted) | Value |
|---|---|
| ` +{` / ` -{` in the pre-fix corpus | **441** / **23** ✓ |
| of those, how many sit immediately after a resource token (circularity check) | **0** — all 464 are independent literal catalog text, so the citation is sound non-circular evidence |
| independent literal "delta after a stat name": `Energy +{MingShiYin_Energy:3}`, `Energy +{0}`, `Chessplayer EXP +{0}`, `Chessplayer EXP +▲{0}` | 11 + 1 + 1 + 1, all **spaced** — the convention the rule now follows |
| `Energy-` follow chars | `S` 66, `s` 1, `G` 1, `{` 1 ✓ (the parent's recount is exactly right) |
| `-Saving` / `Energy-Saving` / `Energy-saving` | 259 / 66 / 1 ✓ |
| token-side sign sites | **165** = `{LordExp}+{` 55, `{LordExp}-{` 44, `{Energy}+{` 44, `{Energy}-{` 11, `{Energy}-2` 11 ✓ |
| every sign site's following char | `{` or a digit in all 165/165 ✓ — so the predicate covers the whole class |
| the `{...}` opened after a sign, corpus-wide | `{0\|1}`, `{0\|2}`, `{3\|2}`, `{3\|4}`, `{MingShiYin_2:2}` — all values, **no text token** |

`{Energy}-2` really is a delta (`… free refreshes, {Energy}-2 per Round.` → `Energy -2 per Round`) ✓, and compounds are
correctly untouched in the output: run4 has `Energy-Saving` 66×, `Energy-saving` 1×, `Energy -Saving` 0×.

**But T5's acceptance text was not updated** and now contradicts both the code and [S2]:
`docs/features/resource-token-expansion.md:267` still reads "…to a following letter or `+`, **leaves `-`**,
markup and punctuation alone…", while `[S2]` (spec:164) and `_tail` (`tools/resource_tokens.py:39-52`) now space a
sign-`-`. A reader taking T5 as the yardstick would score the shipped code as *failing* T5. Non-critical (documentation),
but it must be resolved one way or the other — update T5's acceptance, or record the sign rule as its own task.

## Verdict 2 — Correctness: no critical bug; one measured coverage gap

**Item 1 — independent re-derivation (as requested).** My own walker + expander (written from the intent:
splice token occurrences; space before an ASCII alnum/`}`; space after a word, or after a `+`/`-` that introduces a
digit or `{`) was run over all 87 pre-fix assets and diffed against the current module and against run4 on disk:

| Comparison | Result |
|---|---|
| changed fields | 3384 (unchanged from before, as expected) |
| my output vs `expand_tokens_in_message` | **0 assets differ** (87/87 identical) |
| my output vs `run4\build\scan\replacements\1` | **0 assets differ** (87/87 identical) |
| ASCII-digit variant vs `str.isdigit()` variant | 0 assets differ — no Unicode-digit dependence in this corpus |
| run4 vs run5 (SHA-256 over name+bytes of all 87) | **identical** (`ac9068250a138b2f…`), confirming the parent's claim |

No asset or field disagrees, so there is no string to report for item 1.

**Item 2 — high-signal invariants on the new output (run4):**

| Invariant | Result |
|---|---|
| substituted term adjacent to an alphanumeric, raw | **0 / 4126 sites** |
| … tag-stripped (visible) text | **0 / 4126 sites** |
| resource token inside a `<…>` span | 0 pre-fix, 0 run4 |
| `<color…>` spans / malformed tag spans | 38773 → 38773 / 0 → 0 |
| `RoundEnergyTitle2RoundInfo2`-style keys | 1 string pre-fix, byte-identical in run4 |
| tokens left in the produced assets | `{Energy}` 0, `{LordExp}` 0, `{LordHp}` 0 |
| strings containing a double space | 18 pre-fix, **18** run4 (no new one) |
| idempotence (non-fixpoints of the 3384 corpus strings; re-walk of run4) | 0; 0 further changes |
| glued-string metric (letters-adjacent) | 57 pre-fix, **57** run4 — unchanged |

**Item 3 — attack on the new sign branch:**

| Probe | Output | Verdict |
|---|---|---|
| `{Energy}-`, `{Energy}+` at end of string | `Energy-`, `Energy+` | correct (`end + 1 < len` guard) |
| `{Energy}- 2` (sign, space, digit) | `Energy- 2` | latent miss, 0 corpus sites |
| `{Energy}--2` | `Energy--2` | latent, 0 corpus sites |
| `{Energy}-2nd` | `Energy -2nd` | the one predicate weakness: an ordinal/compound whose next element starts with a digit would be spaced. The corpus has 172 glued `word-N` compounds (`3-Choose-1`, `top-3`, `5-Choice-2`) but **no token-side instance** — all 165 sign sites are deltas |
| `{Energy}-é` (non-ASCII letter) | `Energy-é` | same known latent class as `%`/digit |
| `{Energy}-٤`, `{Energy}-４` | `Energy -٤`, `Energy -４` | `isdigit()` accepts non-ASCII digits; harmless, 0 corpus sites |
| `{Energy}-{HeroName}`, `{Energy}-{}` | `Energy -{HeroName}`, `Energy -{}` | the `{` clause accepts **any** brace token; corpus-only evidence says the 165 shapes open values, so no misfire here (latent if a text token ever follows a sign) |
| `{Energy}</color>-2`, `<b>{Energy}</b>-2` | `Energy</color>-2`, `<b>Energy</b>-2` | **the gap — see finding 1** |
| double space | no synthetic case creates one; corpus count unchanged | clean |
| can it break a tag? | the branch needs the next char to be a sign and the char after it a digit/`{`, so it can never insert inside `<…>`; tags stay balanced | clean |
| multi-byte safety | `text[end]`/`text[end+1]` are code points, not bytes; no split | clean |

**Finding 1 (non-critical, top of this round) — 67 sites where a closing tag shields a signed delta from the rule.**
`{LordHp}</color>-10.` and `{LordHp}</color>-{1|15}` appear 67 times (44 `-{…}`, 23 `-10`; 4 distinct strings across 23
assets). run4 keeps them glued: raw `<color=#FFE897>Chessplayer HP</color>-10.`, **rendered `Chessplayer HP-10.`** — the
same run-on shape the sign rule exists to remove, unreachable because `_tail` only looks at `text[end]` (`<`).
The counter-argument is real and I measured it: the catalog's own token-free text writes this shape without a space too —
`…<b>Temporary Level</b></color></a>+10.` occurs **56 times** (`</color> -{`/`</color> -1` = 0×, and the 44/23
`</color>-{`/`</color>-1` are the selfsame token sites, so they are not independent evidence). So this is a genuine
convention collision (delta convention: `word +N`, 9062 spaced vs 172 compound-glued; tag convention: `</tag>+N` glued,
56×), **not** a T5 violation — T5 only forbids glue to a *word*, and the visible neighbour here is `-`. Recommended:
either let `_tail` skip a closing tag, or — cheaper and honest — scope spec:164 to "a sign **immediately** after the
term" and add this class to the knowingly-unhandled note with the 67-site measurement.

## Verdict 3 — Consistency: style clean, four non-critical documentation defects

- **Style / AGENTS.md**: `_tail` is a private, typed, documented helper at module level; `_SPACE_AFTER` stays UPPER_CASE;
  `re` still used; no new imports; no I/O; the module comment now cites figures I re-counted (441 / 23) instead of the
  bogus `Energy-` 69×. Consistent.
- **`tools/resource_tokens.py:26-28`** — the comment is now accurate and non-circular (verified: 0 of the 464 ` +{`/` -{`
  sit after a token). Accurate.
- **spec:164** — the row's *count* (165) and its examples are right, but its wording ("a sign that precedes a digit or
  placeholder") also describes the 67 tag-shielded sites the code does not touch; reword to "a sign **immediately** after
  the term". Non-critical.
- **spec:174** — "Three boundary classes are knowingly left alone **because the corpus has none of them**" is falsified by
  the 67-site class: a corpus-**present** boundary class is also unhandled, and it is not listed. Non-critical, but this
  sentence is exactly the kind of claim the last review round was about, so it should not ship as-is.
- **spec:267 (T5)** — stale acceptance text (see Verdict 1). Non-critical.
- **spec report table** — the row "Independent review of `7cada8e..149e25e`" now appears **twice** (verified count 2):
  the parent's edit re-added it below the new rows. Non-critical, mechanical.
- **`README.md:53-54`** — not updated by this round: "…or into a following word or `+`". The rule now also spaces a
  following `-`, and the `+` case is conditional on a digit/placeholder, so the enumeration is stale. Non-critical.
- **Stale-wording sweep (item 4)** — the old claims are gone from `tools/` and `docs/`: no `glues its own minus`,
  `Energy-` 69×, `deliberately not` or `no space` survives except (a) spec:49, the new recount row, (b) spec:81, the
  journey-log lesson that quotes the bad citation *as a lesson*, and (c) `tasks/T11/progress.md:145`, my own earlier
  review record. All three are correct in context. The only residual staleness is the README sentence above.

---

## Findings

**Critical: none.**

**Non-critical**
1. **67 tag-shielded signed deltas stay glued** (`Chessplayer HP-10`, `Chessplayer HP-{1|15}`): top finding of the round;
   evidence and both readings given above; recommendation is reword-or-extend, not an urgent code change.
2. **spec:267 (T5) still says "leaves `-` alone"** — contradicts [S2] and the code; a T5-as-written reading fails the
   shipped rule.
3. **spec:174 "knowingly left alone because the corpus has none of them"** — a corpus-present class (the 67) is unhandled
   and unlisted.
4. **spec:164 wording overstates the predicate** (should be "a sign immediately after the term").
5. **Duplicate row** "Independent review of `7cada8e..149e25e`" in the spec report table (2 occurrences).
6. **README.md:53-54 stale** — enumerates "a following word or `+`" only.
7. Latent predicate edges, 0 corpus sites each: `{Energy}-2nd` → `Energy -2nd` (compound whose next element is a digit);
   sign followed by space/another sign; `{…}` clause accepts a text token; non-ASCII digit accepted by `isdigit()`.

## Not verified

- The 58-check unit script is not in the repo (I re-derived the listed cases and replaced the rest with corpus-wide
  checks). The exe build and both pipeline runs were taken as given per instructions — I did not re-run them, but I did
  independently confirm run4 == run5 byte-for-byte, the exe/module mtimes, and `run4.log` / `run5\selftest.json`.
- On-device rendering (unchanged limitation).
