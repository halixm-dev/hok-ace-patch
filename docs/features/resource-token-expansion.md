---
feature: resource-token-expansion
status: delivered
updated: 2026-09-29
branch: master
commits: 7cada8e..d75cfa1
---

# Resource Token Expansion

## Report

**What was built** — translated card text no longer renders hybrid Chinese/English on the resource
terms. `tools/resource_tokens.py` maps `{Energy}`/`{LordExp}`/`{LordHp}` to `Energy`,
`Chessplayer EXP` and `Chessplayer HP`, and `expand_tokens_in_message` walks the protobuf framing of a
replacement asset — with its own varint, text-classification and length-prefix handling, because this
repo does not carry `tools/pb_text.py` — rewriting only fields that carry one of the three tokens, so
`{HeroName}`, `{X}` and numeric `{0|1}` are untouched. `tools/build_device_patch.py` calls
`_expand_staged_tokens(plans, log)` immediately after `adaptive.scan`, so the substitution lands after
`translate_table` validation and before staging, and both the `full`-mode copy and the `fit-only`
subset carry it.

The catalog is deliberately untouched: expanding the tokens there trips `placeholders_changed` and
the records are dropped. `README.md`, `AGENTS.md` and the delivered
`docs/features/standalone-patcher-app.md` no longer describe the hybrid text as an accepted
limitation.

**Verification** — repo Python 3.12.13 (`.venv`), no test suite. All commands run from
`D:\Projects\hok-ace-android-en`; pipeline outputs went to `D:\hok-verify-tokenfix`, outside the repo.

| Command | Result |
|---|---|
| `python -m py_compile tools/resource_tokens.py tools/build_device_patch.py` | PASS |
| 33-check isolated script: token map, spacing, `{HeroName}`/`{0|1}` untouched, flat + nested walking, wire types 0/1/5 round-trip, length-prefix re-encode, `NotMessage` on field 0 / wire type 3 / truncated varint / overrunning length, idempotent re-walk | PASS 33/33 |
| `python app\hok_patcher.py --selftest <game dump> D:\hok-verify-tokenfix\run1` (scan + expand + stage) | PASS, exit 0, 1.08 min; log `expanded resource tokens in 3384 replacement strings` |
| Token grep over the 87 produced assets | PASS — 0 `{Energy}`, 0 `{LordExp}`, 0 `{LordHp}`; no `token expand skipped` line |
| `counts` vs the pre-fix baseline `staged\device_patch_summary.json` | IDENTICAL — `unreadable_assets` 612, `tables` 87, `records` 184569, `translated` 181316, `graphics` 0, `already_english` 2304, `unknown` 3, `unrecognized_tables` 1; `invalid_translation` absent |
| Package 1 staging | `full verified (72 assets)`, 15 dropped — same as baseline, mode stayed `full` |
| Integrity sweep re-walking all 87 produced assets | PASS — `files=87 still_changing=0 further_changes=0 unparsable=0` |
| `build_patch(..., fit_only_mode=True)` driver | PASS — 3384 expansions, 0 skips, package 1 `fit-only` 10 assets, counts unchanged, copied assets token-free |
| Expected strings | `When the chess player levels up, Chessplayer EXP +{3|2}` present; `Gain {0|1} Energy` 22×; `Chessplayer HP` 608× |
| Amendment T5/T6 (spacing): 58-check unit script including the boundary cases | PASS 58/58 |
| Amendment: in-memory A/B over the pre-fix assets | PASS — 3384 fields in 26 assets; glued strings 57 → 57, i.e. all 319 the first rule introduced are gone |
| Amendment: `--selftest` re-run (`D:\hok-verify-tokenfix\run2`) | PASS, 0.98 min; `expanded resource tokens in 3384 replacement strings`; counts identical to baseline; `full verified (72 assets)`, 15 dropped, mode `full` |
| Amendment: grep + integrity sweep over the 87 produced assets | PASS — 0 tokens, no `token expand skipped`, glued strings 57, `still_changing=0 unparsable=0` |
| Amendment: the strings the review flagged | `If Energy is negative` 22×, `Current Energy:` 11×, `the Energy obtained` 11×, `Chessplayer HP and` 11×; `IfEnergyis`, `CurrentEnergy:`, `theEnergyobtained`, `HPand` all 0 |
| Amendment: `fit_only_mode=True` re-run | PASS — 10 assets, 3384 expansions, 0 skips, counts unchanged |
| Sign rule: corpus recounted after review challenged the citation | `Energy-` 69 = 66 `Energy-Saving` + 1 `Energy-saving` + 1 `Energy-G…` + **1** real sign site; catalog writes ` +{` 441× and ` -{` 23×, i.e. signs with a leading space |
| `--selftest` after the sign rule (`run4`) | PASS, 1.02 min; 3384 expansions; counts identical to baseline; `full verified (72 assets)`, 15 dropped |
| Sign sites after the change | `Chessplayer EXP -{` 44×, `Energy -{` 11×, `Energy -2` 33×, `Chessplayer EXP-` 0×, `Energy -Saving` 0×; compounds untouched (`Energy-Saving` 66×, `Energy-saving` 1×) |
| `fit_only_mode=True` after the sign rule | PASS — 10 assets, 3384 expansions, 0 skips, counts unchanged |
| PyInstaller analysis (`build\pyinstaller\HOK ACE Mobile English Patcher\PYZ-00.toc`) | `resource_tokens` and `resource_tokens.py` both present, matching the known-good `qts_relocate` precedent |
| `python app\build_exe.py` with the app closed | PASS — `dist\HOK ACE Mobile English Patcher.exe` rebuilt, 48.25 MB, 22:17:50 against the module's 22:13:37 |
| Frozen exe `--selftest` against the game dump (`run5`) | PASS, exit 0 — `full verified (72 assets)`, and its output is **byte-identical** to the source run (`run4`): same SHA-256 over all 87 assets, 0 tokens, sign sites spaced. The shipped binary provably carries the final rule |
| Installed on the device (`f15a72e`, M2007J3SG, game data version 1.3.0.4) | PASS — package 1 hashed **on the phone** after the push matches the shard built with the fix: `1.db` `a0df436f…`, `1_0.db` `fbff2ec6…`, against `6cb13b99…` / `9a8f62e1…` before. Watchdog cleared, normal APK restored |
| On-device rendering (Card Info) | PASS — the user confirmed on the phone that the card text now renders in English |
| Independent review of `7cada8e..149e25e` | No critical findings. Reviewer re-derived the expansion from the pre-fix assets: 3384 fields, output byte-identical to all 87 produced files |
| Independent review of `cc60205..b670d90` | No critical findings. T5 and T6 both hold; the reviewer's independent walker+expander reproduced all 87 assets byte-for-byte and found the false `-` citation recorded above |
| Independent review of the sign rule (on `b670d90` + the working tree) | No critical bug. Independent reproduction again exact (3384 fields, 87/87 identical to `run4`); the sign predicate holds on all 165 sites; found the stale T5 acceptance text and the tag-shielded class now recorded in [S2] |

Verified on the device: the card text renders in English. The user confirmed it on the phone
(`f15a72e`) after the shard push, which closes the only item this document previously left
unverified. Nothing about this feature is outstanding.


**Journey log**

- The tempting fix — rewriting the tokens in `catalog.json.gz` — is silently counterproductive: the
  runtime's `gemini.validate_translation` compares `{...}` placeholders between source and target and
  rejects the record, so the string stays Chinese. Expanded *after* translation is the whole design.
- The pre-existing session at `dist\HOK ACE Patcher Data\sessions\20260929-212059` carried both the game
  dump and a pre-fix `build\scan\replacements` tree. That pair was a reusable, bit-exact oracle for this
  expansion: the pre-fix assets held exactly the 3067 + 451 + 608 tokens and reproduce the 3384-field
  result. It no longer exists — the app's own retention (`Patcher.prune_old_sessions`, which keeps the
  last two sessions) deleted it during the install runs below, so the built outputs under
  `D:\hok-verify-tokenfix` are all that survives of it. Re-pull the game data to recreate it.
- An already-patched install cannot be re-patched by the normal flow. `adaptive.scan` over the phone's
  patched data reported `already_english` 125408 against 2304 on the clean dump, staged nothing, and
  `build_patch` returned no packages — so the token expansion, which runs on the *replacement* assets
  after the scan, had nothing to act on. Installing this change on that phone therefore meant pushing
  the shard built from the clean dump directly. The scan only ever translates tables that still hold
  Chinese; a data reset is what puts them back.
- Grepping the staged `*.db` shards says nothing about string coverage — their blobs are neither raw nor
  zlib/gzip, and they retain superseded container data (207 raw token bytes, all inside blocks
  byte-identical to the pre-fix build). Judge coverage from `build\scan\replacements` instead.
- The reference implementation's spacing rule was copied verbatim, and that is also its flaw: it adds a
  space only before a digit/placeholder and before `+`, leaving 319 strings with the term glued to an
  adjacent word (`IfEnergyis negative`). Copying a rule that was verified only as "the tokens are gone"
  is not the same as verifying the text it produces — the fix is the boundary-aware rule in [S2].
- A measured-sounding corpus citation is not evidence until the literal is re-counted. The `-` half of
  the first boundary rule was justified as "the catalog glues its minus (`Energy-` 69×)"; 66 of those 69
  are `Energy-Saving`, a hyphenated compound, and only one is a real glued sign. The catalog in fact
  writes ` +{` 441× and ` -{` 23×, i.e. signs *with* a leading space, so the rule was spaced the wrong
  way for all 66 sign sites until review challenged the number rather than the conclusion.
- Two build-time hazards, both hit while rebuilding the exe: `build_exe.py` runs PyInstaller with
  `--noconfirm` against `dist\`, where the app's own ~7.5 GB working folder lives, and it cannot replace
  `dist\HOK ACE Mobile English Patcher.exe` at all while the app is running (`PermissionError: WinError 5`
  in the final assembly step). Move the working folder aside before building, and confirm no app process
  holds the exe. Moving that folder under a live app is unsafe in general — it happened here, was caught
  immediately, and was reverted with nothing written.

## [S1] Problem

Translated card and resource strings still render hybrid Chinese/English on the device. Two observed
cases:

| Card | On screen | Should be |
|---|---|---|
| Yixing | `When the chess player levels up, 棋手经验+2.` | `When the chess player levels up, Chessplayer EXP +2.` |
| Niu Mo | `Triumph: Gain 1能量.` | `Triumph: Gain 1 Energy.` |

The English part is correct, so translation *is* applied. Only the resource name stays Chinese.

Cause: the catalog deliberately keeps the format tokens `{Energy}`, `{LordExp}` and `{LordHp}` in the
English target text, because the runtime's `translate_table` runs `gemini.validate_translation`,
which matches `{...}` with `PLACEHOLDER_RE` and rejects any record whose target placeholders differ
from the source (`placeholders_changed`). Substituting the token inside the catalog therefore rejects
the record and the string is not replaced at all — the text gets *more* Chinese, not less.

At render time the client substitutes the resource *display name*, and those names are still Chinese
in the shipped tables:

- `{Energy}` → `能量`
- `{LordExp}` → `棋手经验`
- `{LordHp}` → `棋手生命值`

Measured on this repo's present pipeline: a scan of the dumped game directory leaves **3,067**
`{Energy}`, **451** `{LordExp}` and **608** `{LordHp}` occurrences across the 87 assets in
`<session>/build/scan/replacements/1/`.

Until this change the repo documented the defect as accepted rather than fixed — `README.md`
(*Translation coverage*), `AGENTS.md` (*Constraints*), and
`docs/features/standalone-patcher-app.md`, whose `[S3] Out of Scope` explicitly parked
"attaching the reference's `RESOURCE_TOKEN_FIX.md` work". All three are updated by the same change
that implements this feature.

## [S2] Design

Expand the three static resource tokens into English **after** translation and **before** staging,
so `validate_translation` still sees matching placeholders on both sides.

```
game data ──adaptive.scan / translate_table──> scan/replacements/<id>/*.assets   (tokens intact)
                                                        │
                                                        └─ _expand_staged_tokens()   <-- expand here
                                                                 │
                                                    fit_only() / stage()  →  output/<id>/
```

### Token map and spacing

`tools/resource_tokens.py` owns the mapping:

```python
RESOURCE_TOKENS = {
    "{Energy}": "Energy",
    "{LordExp}": "Chessplayer EXP",
    "{LordHp}": "Chessplayer HP",
}
```

`{LordExp}` maps to `Chessplayer EXP`, not `Chess player experience`: the token is read as a stat
(`棋手经验+{0}`), matching the catalog's own phrasing `Chessplayer EXP +{0}`.

The catalog glued the token to the words around it, because the Chinese expansion needs no space
(`获得{0|1}{Energy}。`). An English term does, so `expand_resource_tokens` inserts one at the
boundaries the corpus actually has, counted over the 87 pre-fix assets:

| Boundary | Occurrences | Action |
|---|---|---|
| before: latin letter (`Current{Energy}:`, `If{Energy}is`) | 33 | insert a space |
| before: digit or `}` (`get5{Energy}`, `{0|1}{Energy}`) | 2562 | insert a space |
| after: latin letter (`{Energy}to Obtain`, `5{LordHp}and1`) | 341 | insert a space |
| after: a sign that precedes a digit or placeholder (`{LordExp}+{3\|2}`, `{Energy}-2`) | 165 | insert a space |
| after: punctuation, markup, end of string, a hyphen inside a compound | remainder | unchanged |

The sign rule is the catalog's own: it writes a sign before a placeholder **with a leading space** —
` +{` 441 times and ` -{` 23 times, and none of those 464 sits after a token, so the count is a genuine
convention and not an echo of these sites — so `{LordExp}-{3|2}` becomes `Chessplayer EXP -{3|2}`, not
`Chessplayer EXP-{3|2}`. The lookahead is one character, which is what separates a sign from a hyphen
inside a compound: the corpus has 66 `Energy-Saving` and 1 `Energy-saving`, and none of the 165 sign
sites begins one.

Every other boundary keeps the catalog's own spacing, which is why the rule only ever touches text it
actually substituted: internals such as `RoundEnergyTitle2RoundInfo2` stay byte-identical.

Four boundary classes are knowingly left alone:

| Class | Sites | Why |
|---|---|---|
| a sign shielded by a closing tag: `{LordHp}</color>-10.` renders as `Chessplayer HP-10.` | 67 | the catalog glues signs in that position itself — 1214 token-free `>+` and 82 token-free `>-` — so spacing here would *diverge* from its style. `_tail` reads one character past the term; a tag-skipping lookahead would be needed to reach it |
| a following digit (`{Energy}5`) | 0 | the corpus has none |
| a non-ASCII letter (`é{Energy}`) | 0 | the corpus has none |
| `%` (`100%{Energy}`) | 0 | the corpus has none |

The last three are unmeasured rather than decided: with no occurrence there is no convention to match,
and the rule stays inside the classes it was counted on.

### Walker contract

`expand_tokens_in_message(data: bytes) -> tuple[bytes, int]` returns the rewritten message and the
number of string fields changed. This repo does **not** carry `tools/pb_text.py`, so the module is
self-contained: it brings its own varint decode/encode, its own UTF-8 + control-character text
classification, and its own `NotMessage`.

- Only length-delimited (wire type 2) fields are candidates; a field is treated as text when it
  decodes as UTF-8 with no control characters.
- A text field is rewritten when it contains a `{Name}`-shaped token (`\{[A-Za-z][A-Za-z0-9_]*\}`).
  Only names present in `RESOURCE_TOKENS` are actually substituted, so `{HeroName}`, `{X}`, `{P1}`
  and numeric tokens such as `{0|1}` pass through untouched.
- Nested messages are recursed into only when the field is *not* valid text, to a maximum depth of
  16 — the same classification the reference's `pb_text.rewrite` uses.
- Because a replacement changes the encoded length, the field's length prefix is re-encoded. A raw
  byte-level `.replace()` would corrupt the table.

`NotMessage` is raised when the data is not a well-formed message (unknown wire type, field number 0,
truncated varint, or a length that overruns the buffer).

### Hook contract

`tools/build_device_patch.py` gains `_expand_staged_tokens(plans, log) -> int`, called immediately
after `adaptive.scan(...)` and before the `fit_only` / `stage` closures run:

```python
plans, fingerprints, counts, skipped = adaptive.scan(
    game, catalog, work / "scan", materialize=True
)
_expand_staged_tokens(plans, log)
```

For every plan it rewrites each `*.assets` in that plan's materialized `replacements` directory in
place, logs `expanded resource tokens in <n> replacement strings` once when anything changed, and
returns the changed count.

Ordering is the load-bearing part. Expansion must happen on the *same* `replacements` directory the
staging paths later read: `full` mode `copytree`s it into `work/full-replacements/<id>`, and
`fit-only` copies the surviving subset into `work/fit-replacements/<id>`. Expanding first means both
paths carry the expanded text. This repo has no `device_extensions`, so there is no relocated-asset
path to cover.

An asset that raises is logged as `token expand skipped <name>: <error>` and left byte-for-byte
untouched; the run continues. `NotMessage` from the walker is therefore contained. An I/O failure
reading or writing an asset is *not* caught and does abort the run — deliberately, since silently
skipping an asset would quietly shrink coverage.

### Consequences to expect

- Expansion changes string lengths (some shorter: `{Energy}` → `Energy`; some longer:
  `{LordExp}` → `Chessplayer EXP`). Which assets fit inside their original slack in `full` mode may
  therefore shift slightly. A change in the staged asset count is by design; a fallback from `full`
  to `fit-only` would not be.
- `counts` from `adaptive.scan` are unaffected: expansion rewrites staged string content, it does not
  change how many tables or records were translated. `patcher_core.count_translated` still reports
  text tables only, and the GUI wording stays as it is. **Superseded** — `count_translated` returns
  `(text tables, textures)` and the GUI reports both, per
  `docs/features/texture-translation.md`.
- **Spacing.** The first delivery copied the reference's narrower rule (space only before a
  digit/placeholder and before `+`) and left 319 strings with the term glued to an adjacent word —
  `IfEnergyis negative`, `theEnergyobtained this Round`, `CurrentEnergy:`. The boundary-aware rule
  above was added afterwards. Re-measured on the same 87 produced assets, glued strings are back to the
  57 that the catalog already had before this feature began, and those remaining cases are pre-existing
  catalog text, not substitution sites.

### Testing boundary

This repo has no test suite, so verification is a real pipeline run against the dumped game
directory at `dist/HOK ACE Patcher Data/sessions/20260929-212059/game`, compared with that session's
recorded pre-fix baseline (`staged/device_patch_summary.json`): `tables` 87, `records` 184569,
`translated` 181316, `already_english` 2304, `unreadable_assets` 612, no `invalid_translation` key,
and package `1` staged `full` with `replacement_count` 72.

## [S3] Out of Scope

- Adopting `tools/pb_text.py`, `tools/extra_text.py`, `device_extensions`, `mobile_graphics` or
  `unity_text`, or the extra-text / relocated-text / graphics coverage they provide. The reference's
  lookup-time expansion inside `extra_text.translator_for` has no counterpart here because this repo
  has no `extra_text.py`.
- Expanding `{HeroName}`, `{X}`, `{P1}` or numeric tokens such as `{0|1}`; these are filled
  dynamically and would otherwise render literally.
- Touching `resources/catalog/` or `resources/runtime/`. The catalog must keep the tokens — expanding
  it trips `placeholders_changed` and drops records.
- Fixing the same defect at its source in the PC patcher pipeline that produces the catalog.
- Graphics or texture coverage; the pipeline still has no `graphics` package mode.
