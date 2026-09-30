---
feature: text-drop-report
status: in-progress
updated: 2026-09-30
branch: feat/text-drop-report
commits:
---

# Text Drop Report

## Report

## [S1] Problem

`build_patch` loses translated text tables and does not say so. When the QtsVFS container cannot take a
translated table, the staging loop deletes that table, restages, and repeats; the package then still
appears in `packages` with a `verified` status, so the summary and the GUI both read as a clean run.

Measured on the 09:28 and 10:23 sessions (both fresh 1.4.0.1 Chinese data, `translated: 181617`), the
run logged `package 1: full verified (81 assets)` while **11 of the 92** translated tables never made it.
Re-running the loop reproduces the same 11, in the same order, with the errors the code does not log:
`Additional QtsVFS chunks require one contiguous physical window` for the two 600 KB tables, and
`QtsVFS position index has no safe insertion point for slot N key X` for nine ~277 KB tables. All 11 are
chessplayer-domain tables (`Chessplayer`, `Skill`, `Talent`, `Amulet`, `Scepter`, `Secret`); every one
of the 81 that survived is general UI, event or item text. `A336359CD92A858E` and `28D9F8B02CAA94E2`
were dropped on every run on disk, including the 1.3.0.4 run whose shard hash was verified installed, so
they have never reached a phone.

The user sees this as Chinese on a screen whose other strings are English — the Chessplayer screen shows
`Chessplayer`/`Combat Power` translated and its ten portraits named in Chinese. Nothing in the run
accounting points at a cause: `fit_summary.dropped_while_staging` holds the retry loop's victims but no
caller reads it, and `count_translated` counts only what landed. This is the same invisible-loss class
AGENTS.md already calls out for textures, and which `graphics_skipped` fixed there.

## [S2] Design

`build_patch` gains a top-level `text_skipped` list in the payload it returns and writes to
`output/device_patch_summary.json`, one entry per package that lost at least one translated table:

```json
"text_skipped": [
  {"package_id": "1", "mode": "full", "considered_count": 92, "dropped_count": 11,
   "dropped": ["28D9F8B02CAA94E2", "A336359CD92A858E", "..."]}
]
```

- `considered_count` is the number of translated tables the run had for that package: the `*.assets`
  files in the materialized plan. `dropped` is the sorted hashes of those that are not in what the
  package staged, and `dropped_count` is its length.
- The staged set is read from the directory the successful attempt staged from: `<work>/full-replacements/<id>`
  in `full` mode, `<work>/fit-replacements/<id>` in `fit-only`. The latter is the capacity-filtered
  subset, so a table that mode left out counts as dropped, which is correct: it is not in the package
  either.
- A package that staged nothing at all gets an entry too, with every table the run had for it in
  `dropped` and `considered_count == dropped_count`. That is the most severe case — the whole package's
  text is missing — and today it leaves no trace beyond a log line.
- Entries appear only for packages that lost something, so the list is empty on a clean run.
- The field names deliberately differ from `graphics_skipped`'s (`skipped_count`, `considered_count`,
  `skipped`): that list holds textures that were never translated, this one holds text that was
  translated and then not applied. Reusing the names would invite one accessor to sum them into a total
  that means nothing.
- `app/patcher_core.count_untranslated_text(summary) -> int` sums `dropped_count`, mirroring
  `count_untranslated_graphics`. `count_translated` keeps its documented `(text tables, textures)`
  contract.
- Both GUI count sites show it: the `translate` step's detail in `Patcher.build_translation`, and the
  final message in `App.worker`. Both phrase it as tables that stay in Chinese, and both read exactly as
  they do today when `text_skipped` is empty.
- The run log names each package that lost tables, beside the existing staging lines.
- Staging behaviour is untouched: the retry loop, the drop order and the choice of which tables are
  sacrificed all stay as they are, as does `fit_summary.dropped_while_staging` as the retry-loop
  diagnostic.

## [S3] Out of Scope

- **Making the dropped tables apply.** The fix for the chessplayer tables is a second staging pass over
  the rebuilt package, whose container grew from 26.8 MB to 29.1 MB and may now have room. This change
  only reports; until that lands the tables stay Chinese.
- **Text no localization table covers.** Package 4 carries 3 localization tables (520 records) that
  `adaptive.scan` never includes at all; package 10's chessplayer config is rejected by the runtime as
  `Not an unambiguous localization table`; package 1 has 631 assets the runtime cannot read. None of
  these are reachable from the staging loop and none appear in `text_skipped`.
- **Textures.** `graphics_skipped` already covers those, and this change does not touch it.
- **Coverage claims.** The textures the mobile build does not carry, and the catalog's narrower card
  coverage, are documented in README and stay as they are.

## Tasks

- [ ] T1: Add `text_skipped` to `build_patch`'s summary and log a line per package that lost tables — acceptance: on the 10:23 session dump a run writes `text_skipped` with one entry, `considered_count` 92 and 11 dropped hashes equal to the reproduced drop set, and the log names the package (covers: S2)
- [ ] T2: Add `count_untranslated_text` and wire both GUI sites — acceptance: the `translate` step detail and the final message each state how many text tables stay in Chinese, and with an empty `text_skipped` both read exactly as they do today (covers: S2; depends: T1)
- [ ] T3: Update AGENTS.md's `build_patch` contract and the README run description — acceptance: the documented payload lists `text_skipped` with its entry fields, and the constraints section says the text side reports what it could not apply (covers: S2; depends: T1)
