---
feature: resource-token-expansion
status: designed
updated: 2026-09-29
branch: master
commits:
---

# Resource Token Expansion

## Report

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

Today this repo documents the defect as accepted rather than fixed — `README.md` (*Translation
coverage*), `AGENTS.md` (*Constraints*), and `docs/compose/spec/standalone-patcher-app.md`, whose
`[S3] Out of Scope` explicitly parked "attaching the reference's `RESOURCE_TOKEN_FIX.md` work".

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
(`棋手经验+{0}`), matching the catalog's own phrasing `Chessplayer EXP +{0}`. `expand_resource_tokens`
applies the spacing the surrounding catalog text uses:

- a space is inserted when the token is glued to a preceding digit or `}` — `{0|1}{Energy}` → `{0|1} Energy`;
- remaining occurrences are replaced bare;
- `Chessplayer EXP+` → `Chessplayer EXP +`, so `{LordExp}+{3|2}` becomes `Chessplayer EXP +{3|2}`.

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
untouched; the run continues. Token expansion never propagates an exception out of `build_patch`.

### Consequences to expect

- Expansion changes string lengths (some shorter: `{Energy}` → `Energy`; some longer:
  `{LordExp}` → `Chessplayer EXP`). Which assets fit inside their original slack in `full` mode may
  therefore shift slightly. A change in the staged asset count is by design; a fallback from `full`
  to `fit-only` would not be.
- `counts` from `adaptive.scan` are unaffected: expansion rewrites staged string content, it does not
  change how many tables or records were translated. `patcher_core.count_translated` still reports
  text tables only, and the GUI wording stays as it is.

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

## Tasks

- [ ] T1: Add `tools/resource_tokens.py` with the token map, `expand_resource_tokens` and the self-contained `expand_tokens_in_message` — acceptance: on the two strings from [S1], `{Energy}`/`{LordExp}` expand to `Energy`/`Chessplayer EXP` with the documented spacing, `{HeroName}` and `{0|1}` are left untouched, and a re-walk of the output reports 0 further changes instead of raising (covers: S2)
- [ ] T2: Call `_expand_staged_tokens(plans, log)` in `build_patch` right after `adaptive.scan` — acceptance: a scan + expand over the dumped game directory leaves 0 `{Energy}`, 0 `{LordExp}` and 0 `{LordHp}` occurrences across all 87 assets in `scan/replacements/1`, and the log carries no `token expand skipped` line (covers: S2; depends: T1)
- [ ] T3: Full `build_patch` run into a work and output directory outside this repo — acceptance: `counts` match the pre-fix baseline exactly, `invalid_translation` is absent, package `1` still stages with mode `full` and a non-empty `replacement_count`, and the staged strings carry no resource tokens (covers: S2; depends: T2)
- [ ] T4: Update `README.md`, `AGENTS.md` and `docs/compose/spec/standalone-patcher-app.md` so the token limitation is no longer described as accepted — acceptance: no document still claims the tokens are left for the client to expand, and the `[S3]` entry that parked this work is marked superseded (covers: S2; depends: T2)
