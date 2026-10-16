# T11 — Independent, adversarial review of the spacing amendment (cc60205..b670d90)

Reviewed commit: `b670d90` ("fix: space resource terms at the words they were glued to"), single commit,
3 files (`tools/resource_tokens.py`, `README.md`, `docs/features/resource-token-expansion.md`).
Read-only review: I modified nothing except this file. Feature base: `7cada8e`.

**Snapshot caveat (environment churn during the review).** Another process ran concurrently in this
workspace: it moved `dist\HOK ACE Patcher Data` out of the repo (to `D:\hok-verify-tokenfix\PatcherData-hold2`),
then moved it back, rebuilt the exe (22:05:24), produced `run3`, and edited the spec **in the working tree**
(6 insertions / 8 deletions, uncommitted; `git status` = `M docs/features/resource-token-expansion.md`,
`?? tasks/`). Line numbers below are the **committed** b670d90 numbers; the working-tree spec has shifted by
-2 after line ~46. Every corpus number below was re-read after the churn from the oracle at
`dist\HOK ACE Patcher Data\sessions\20260929-212059\build\scan\replacements\1` (re-confirmed at read time:
87 assets holding exactly 3067 `{Energy}` + 451 `{LordExp}` + 608 `{LordHp}`).

Method: I wrote an **independent** extractor/expander (recursive protobuf walk collecting length-delimited
UTF-8-without-control-character payloads; token occurrences collected then spliced, rather than the module's
earliest-match `find` loop) and compared it against both the module and the real pipeline output.

---

## Verdict 1 — SPEC COMPLIANCE: both criteria hold

**T5 — MET** (`docs/features/resource-token-expansion.md:250`, rule at `:150-157`).

| Clause | Evidence |
|---|---|
| spaces a term glued to a preceding letter/digit/`}` | corpus: 2595 of 4126 occurrences are in `[A-Za-z0-9}]` (letters 33, digits+`}` 2562 — exactly the spec's two rows); all 2595 get a space (`tools/resource_tokens.py:61`). Synthetic: `Current{Energy}:`→`Current Energy:`, `get5{Energy}`→`get5 Energy`, `{0\|1}{Energy}`→`{0\|1} Energy` |
| and to a following letter or `+` | corpus: 440 = letters 341 + `+` 99 (matches spec rows 154/155 exactly); `tools/resource_tokens.py:62`. Synthetic: `{Energy}to…`, `If{Energy}is`, `{LordExp}+{3\|2}`→`Chessplayer EXP +{3\|2}` |
| leaves `-`, markup, punctuation alone | 66 `-` sites untouched; `<b>{Energy}</b>`→`<b>Energy</b>`; `.`/`,`/`:`/`;` untouched (`{Energy},` stays `Energy,`) |
| **no produced string has a substituted term glued to an adjacent word** | **0 of 4126** substitution sites have an alphanumeric neighbour, measured on the raw string **and** on the tag-stripped (visible) text. This is the decisive check: it is done per *site*, not per string, on the exact output the pipeline wrote |

**T6 — MET** (`:251`), all re-derived from the on-disk artifacts, not from the log:

| Claim | Verified |
|---|---|
| same run reproduces `counts` | `run2\staged\device_patch_summary.json` `counts` == the pre-fix baseline's, dict-for-dict: `tables` 87, `records` 184569, `translated` 181316, `already_english` 2304, `unreadable_assets` 612, `unknown` 3, `unrecognized_tables` 1, `graphics` 0; `invalid_translation` absent; `skipped_count` 612 (`run1` identical too) |
| package `1` `full` at 72 assets | `mode` `full`, `stage_report.replacement_count` 72, `selftest.json` `{"ok": true, "packages": [["1", 72]]}`; `run2.log` = `full verified (72 assets)`, `dropped 15 assets in full mode` |
| 0 resource tokens | raw byte counts over all 87 produced assets: `{Energy}` 0, `{LordExp}` 0, `{LordHp}` 0 |
| no `token expand skipped` | `run2.log` has exactly 4 lines and contains no skip line |
| produced assets re-walk to 0 changes | `expand_tokens_in_message` over all 87 → 0 further changes, 0 assets differing; also 0 over `run1` |
| (row 44) 3384 fields in 26 assets | reproduced exactly: 3384 token-carrying fields, 26 distinct assets |
| (row 44) glued strings 57 → 57 | reproducible: 57 strings carry a term with a **letter** directly adjacent, identical pre-fix and post-fix (61 with digits included; the spec's number is the letters-only metric). The substantive claim — the residue is pre-existing catalog text, not substitution sites — is confirmed independently by 0/4126 |
| (row 47) flagged strings | `If Energy is negative` 22×, `Current Energy:` 11×, `the Energy obtained` 11×, `Chessplayer HP and` 11×; `IfEnergyis`/`CurrentEnergy:`/`theEnergyobtained`/`HPand` all 0 — exactly as recorded |
| (row 48) fit-only | `fitout2`: `fit_only` true, `mode` `fit-only`, `replacement_count` 10; `fitwork2\scan\replacements\1` (87) and `fitwork2\fit-replacements\1` (10) both token-free; counts unchanged |
| (row 159-160) `RoundEnergyTitle2RoundInfo2` byte-identical | the one pre-fix string containing it is present byte-identical in run2 |

Only the T5/T6 items are in scope here; T1–T4 were the earlier, already-reviewed range.

## Verdict 2 — CORRECTNESS: no critical bug; the loop is sound

Attacked in the order the task asked.

1. **`found`/`width`/`term` bookkeeping.** `found = width = -1`, `term = ""` are always assigned together
   (`tools/resource_tokens.py:53-56`), so `end = found + width` can never be a stale `found - 1`
   (no infinite loop), and `found < 0` only means "no token left" (`:57`) since a successful assignment
   forces `width = len(token) >= 8`. Between 53 and 56 no state leaks across iterations.
2. **Overlap / missed matches.** No resource token is a substring of another, and none contains `{` after
   index 0, so no occurrence can hide inside a previously matched one; `index = end` (`:64`) therefore skips
   nothing. My splice-based reimplementation flags overlaps explicitly and reported none; it agreed with the
   module on **all 3384** corpus strings (0 mismatches). Earliest-match `min` is correct: every token is
   searched from `index` and the smallest `at` wins.
   *Theoretical tie*: two tokens cannot start at the same index (distinct first characters), so the strict
   `at < found` comparison is never order-dependent.
3. **Determinism of `RESOURCE_TOKENS` iteration.** Verified empirically, not by argument: re-running over
   all 3384 corpus strings with the dict reversed and with a third arbitrary permutation produced
   **identical output**; a repeat run is identical too. (No `sorted()` is needed and none is present.)
4. **Double space.** Impossible by construction: a lead space is inserted only when the previous character is
   `[A-Za-z0-9}]` and a tail space only when the next is `[A-Za-z+]`, and neither class is a space; two tokens
   in a row (`{Energy}{LordHp}`) get exactly one space, between them. Checked on the corpus: 0 strings
   containing `"  "` in the pre-fix tree, `run1` and `run2`; and 0 in every synthetic case, including
   `x{Energy}{LordExp}{LordHp}y` → `x Energy Chessplayer EXP Chessplayer HP y`.
5. **String start / end.** `found and …` (`:61`) suppresses the lead space at index 0; `end < len(text)`
   (`:62`) suppresses the tail space at the end. `{Energy}`→`Energy`, `{Energy},`→`Energy,`,
   `{0\|1}{Energy}。`→`{0\|1} Energy。` (corpus, 22×).
6. **Text not produced by the substitution is untouched.** Insertions happen only at a token boundary, and
   everything outside is copied verbatim (`:58`, `:63`). Proof at asset level: my independent
   walker+expander reproduced **all 87** `run2` assets byte-for-byte (and so did the module), so nothing
   else in those files moved. `RoundEnergyTitle2RoundInfo2` byte-identical; tag spans `<color…>` are
   38773 pre-fix and 38773 in run2, 0 malformed tags on either side; **0** token occurrences sit inside a
   `<…>` span (so a tag can never be split). 99 token-carrying strings are identifier-*shaped*
   (`3{Energy}Reward`, `{Energy}catcher`) but they are card-name display text, not keys — they expand as
   intended (`3 Energy Reward`, `Energy Catcher`), no key is renamed.
7. **Idempotence.** Second application changes nothing: 0 non-fixpoints among the 3384 corpus strings, and a
   full re-walk of all 87 produced assets reports 0 changes. The module *can* be non-idempotent on
   brace-nested input (`{{Energy}}` → `{Energy}` → `Energy`), but that requires a token immediately preceded
   by `{` and followed by `}` — the corpus has 0 such sites (the before-character classes are
   `}`/digit/space/`>`/letters/BOS only), so it is unreachable here. Note the walker already charged the
   field once, so even there the count semantics stay coherent.
8. **Deleted `Chessplayer EXP+` normalisation (old `:45`).** Nothing real is lost. Its only producer from a
   token was `{LordExp}+`, which the new tail rule handles identically — verified: 22× `Chessplayer EXP +{3\|2}`
   in run2 (the [S1] target string), plus `5 Chessplayer EXP +` for the digit-preceded variant. The
   normalisation's *other* effect was on literal catalog text; corpus counts for the pre-fix assets:
   `Chessplayer EXP+` **0**, `Chessplayer HP+` 0, `Energy+` 0, and the spaced forms (`Chessplayer EXP +{0}`,
   `Chessplayer EXP +▲{0}`) 2. So it rewrote nothing. Deleting it also removes the previously-noted
   "normalisation is not token-gated" latent issue (T7 finding #3).
9. **Latent gaps in the boundary classes (all 0 corpus occurrences today).** `{Energy}5`→`Energy5`
   (no digit in `_SPACE_AFTER`); `é{Energy}`→`éEnergy` and `{Energy}é`→`Energyé` (non-ASCII letters are
   outside `[A-Za-z]`); `100%{Energy}`→`100%Energy`. The corpus after-characters are
   space 1400, `.` 1190, `<` 544, `,` 375, letters 341, `+` 99, `-` 66, `:` 22, `;` 33, `★` 22, `~` 12,
   `{` 11, `，` 11, … — no digits, no non-ASCII letters, no `%`. So none of these can fire on this corpus.
10. **Remaining glued-looking output, and why it is not a T5 violation.** `{LordExp}★` (22×) → `Chessplayer
    EXP★`, `…Energy}~…` (12×) → `Energy~{0|4}`: the neighbour is a symbol, not a word. `get5{Energy}，5{LordHp}and1…`
    → `get5 Energy，5 Chessplayer HP and1Special Equipment plate.`: the *terms* are now correctly spaced on both
    sides; the residual `and1Special` glue and the full-width `，` are literal catalog text (present in the
    pre-fix string) — outside this feature.

**Conclusion: no critical correctness finding.** The 319 introduced glued strings are gone, the output is
reproducible byte-for-byte from the pre-fix inputs by an independent implementation, and no new defect class
appears in the produced data.

## Verdict 3 — CODEBASE CONSISTENCY: consistent, with one wrong corpus citation

- **AGENTS.md style rules**: module docstring (`resource_tokens.py:1-8`), `from __future__ import annotations`
  (`:9`), full type hints (`:39`, `:68`, `:78`, `:91`, `:103`, `:111`), UPPER_CASE module constants
  (`RESOURCE_TOKENS` `:13`, `_CONTROL` `:19`, `_TOKEN_RE` `:23`, `_SPACE_BEFORE` `:29`, `_SPACE_AFTER` `:30`,
  `_MAX_DEPTH` `:32`), `_name` private helpers — all match. `import re` is still used (`:19,23,29,30,135`),
  so no orphan import. No file I/O in the module, so no `pathlib`/`PatchError` needed; the internal
  `NotMessage` stays contained in the already-reviewed hook (`build_device_patch.py:59-63`). Max line length
  102 vs 126/107 elsewhere in `tools/` — consistent with the repo, which has no enforced limit. LF endings,
  no tabs.
- **README.md:51-55** — the stale pre-amendment sentence ("a minority of strings still show the term glued to
  an adjacent word (for example `CurrentEnergy:`") is gone, and the new wording is accurate in what it
  claims: spaces appear before a preceding word/placeholder and after a following word/`+`; the `-` and
  symbol cases are not claimed to be spaced. It does not spell out the digit case (`get5{Energy}` → `get5 Energy`)
  nor the `-` exception, both of which the spec table covers; cosmetic only.
- **Spec [S2] table (`:150-157`)** — every count reproduces exactly (2562 + 33 before, 341 + 99 after, 66 `-`),
  including the claim that internals stay byte-identical.
- **No stale pre-amendment claim survives in a shipping document.** A repo-wide search for
  `glued`/`CurrentEnergy`/`IfEnergyis`/`energyobtained`/`HPand`/`319`/`376`/`minority of strings` hits only the
  spec (self-describing the amendment), the module comment, and `tasks/T7/progress.md` — the earlier review
  record for the pre-amendment range, an untracked artifact like this file, not shipping documentation.
  `AGENTS.md:76`, `docs/features/standalone-patcher-app.md:185-190,204-207` mention the tokens but make no
  spacing claim, so nothing there went stale. `dist\…exe` freshness is T7's, not this amendment's.

---

## Findings

**Critical: none.** Both acceptance criteria hold and no correctness bug was found.

**Non-critical**

1. **The cited corpus evidence for the `-` decision does not exist.** `tools/resource_tokens.py:26-28` and
   spec:156 say the catalog "writes … `Energy +2` but glues a minus (`Energy-2`, 69 occurrences)". Measured on
   the 87 pre-fix assets: `Energy +2` = **0**, `Energy-2` = **0**, `Energy -` = 0 (so that half of the claim is
   vacuous), and the 69 `Energy-` are 66 `Energy-Saving Module/Shop`, 1 `Energy-Saving…`-style
   (`Energy-saving mode`), 1 `Energy-…`, plus exactly **one** real glued-minus site, `… Hero Card Energy-{0}`.
   The *conclusion* still stands, on better evidence: `Energy-{0}` (1×) vs the spaced `Energy +{0}` (1×) and
   `Chessplayer EXP +{0}` / `Chessplayer EXP +▲{0}` (2×) — i.e. "minus glued, plus spaced", 1-vs-3 rather than
   69-vs-12. Since the whole amendment is justified as corpus-derived, quote the real numbers. Behaviour
   complies with T5 as written; this is a documentation-accuracy defect, not a code defect.
2. **The 66 `-` sites are the one place the output can still read run-on**, and the counter-evidence is not
   recorded: `{LordExp}-{3|2}` renders `Chessplayer EXP-3`, `{Energy}-{0|1}` renders `Energy-2`, while the
   catalog itself writes a minus that follows a word as ` -{0|15}` (23×, e.g. "is available until -{0|15}").
   T5 explicitly requires leaving `-` alone, so this is not a criterion failure — but the spec should record
   that the opposite convention also exists in the corpus, so the choice is not re-litigated later.
3. **Latent boundary gaps** (0 corpus occurrences, listed so they are not rediscovered as bugs): a following
   digit is not spaced (`{Energy}5` → `Energy5`), non-ASCII letters are not spaced (`é{Energy}` → `éEnergy`),
   `%` is not spaced (`100%{Energy}` → `100%Energy`).
4. **Brace-nested input is not a fixpoint**: `{{Energy}}` → `{Energy}` on the first pass. Unreachable in this
   corpus (0 tokens preceded by `{`), and a re-walk of every produced asset changes nothing.
5. **Informational**: symbol neighbours (`Chessplayer EXP★` 22×, `Energy~{0|4}` 12×) are inside the spec's
   "remainder → unchanged" row; `tasks/T7/progress.md:29-31` still describes the pre-amendment rule (untracked
   historical record); the reference `hok-ace-mobile-en/tools/resource_tokens.py:31-38` keeps the narrow rule,
   i.e. the repos now diverge by design — the spec's journey log documents that.

## Appendix — the exe rebuild / bundling item, verified read-only

The task record for T11 carries the summary "Rebuild the shipping exe safely and confirm bundling". My
assignment was read-only, so I did not run `build.bat`/`build_exe.py`; the rebuild had already been done by
the concurrent process, and I verified the outcome read-only. All four checks pass:

| Check | Evidence |
|---|---|
| exe newer than the amended module | `dist\HOK ACE Mobile English Patcher.exe` 22:05:24 (50,588,392 B) vs `tools\resource_tokens.py` 21:57:15 — and `git status` shows the module unmodified, so the file on disk *is* the amended b670d90 content, written before the build |
| the amended module is bundled | `build\pyinstaller\HOK ACE Mobile English Patcher\PYZ-00.toc` (22:05:04, same build) lists `('resource_tokens', 'D:\…\tools\resource_tokens.py', …)`, alongside the known-good `qts_relocate` |
| the frozen build runs the amended rule | `run3` (22:06:35, after the 22:05:24 rebuild) is **byte-identical to `run2` on all 87 assets** and carries the new-rule-only strings: `If Energy is negative` 22×, `Current Energy:` 11×, `the Energy obtained` 11×, `Chessplayer HP and` 11×, `Chessplayer EXP +{3|2}` 22×, with `IfEnergyis`/`CurrentEnergy:`/`theEnergyobtained`/`HPand` all 0 and 0 tokens of each kind |
| `--selftest` reports package 1 at 72 | `run3\selftest.json` = `{"ok": true, "packages": [["1", 72]]}`; `run3.log` = `expanded resource tokens in 3384 replacement strings`, `dropped 15 assets in full mode`, `full verified (72 assets)`, counts equal to the pre-fix baseline |

Byte-identity between `run2` (source run) and `run3` (post-rebuild run) is what makes this evidence
discriminating rather than merely consistent: the shipped exe reproduces the amended rule's output exactly.

## Not verified

- The "54-check unit script" is not in the repo; I could not re-run it. I spot-checked its listed cases myself
  (all pass) and replaced the rest with corpus-wide checks.
- That no *live* string still renders a Chinese expansion (on-device, out of scope for T5/T6).
- The concurrent uncommitted spec edits and the `run3`/exe rebuild: another agent's work, outside this
  amendment (T7). My corpus reads were re-confirmed against the oracle after the working folder was moved and
  moved back; the 87-asset tree still carried exactly the pre-fix token counts at read time.
