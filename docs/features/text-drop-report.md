---
feature: text-drop-report
status: delivered
updated: 2026-09-30
branch: feat/text-drop-report
commits: 9a276c3..8d0704c
---

# Text Drop Report

## Report

**What was built** — a run now says which translated text tables it could not stage. `build_patch`
writes `text_skipped` into the payload it returns and into `output/device_patch_summary.json`: one
entry per package that lost at least one of its translated tables, carrying `package_id`, `mode`,
`considered_count`, `dropped_count` and the dropped hashes, plus a log line per such package. A package
that stages nothing gets an entry covering its whole plan, so the case that previously left only a log
line is in the summary too. `count_untranslated_text` sums it, and both GUI count sites report it: the
`translate` step's detail and the final message. The field names stay distinct from `graphics_skipped`'s
so that no accessor sums textures and tables into a total that means nothing.

Staging is untouched: the retry loop, the drop order and which tables are sacrificed are exactly as they
were, and `fit_summary.dropped_while_staging` keeps its meaning as the retry loop's diagnostic. The one
reporting change beyond the new field is that a run which installs nothing no longer says "already
installed" while it lost tables — `Patcher.build_translation` reports the counts it has, and
`App.worker` opens with "Nothing new to install." in that state.

**Verification** — `.venv\Scripts\python.exe -m py_compile` on the three changed Python files: PASS.
`Patcher.build_translation` driven through a stub `Ui` against the freshly pulled 1.4.0.1 data
(`sessions/20260930-102304/game`, ~4 minutes): `text_skipped` = one entry, package `1`, `full`,
`considered_count` 92, `dropped_count` 11, `dropped` equal to the independently reproduced drop set;
`count_translated` (81, 323); `count_untranslated_text` 11; step detail `81 text tables, 323 images, 11
text tables left in Chinese`; the on-disk summary carries the field; and every file of packages 1/15/19/20
was byte-identical before and after the run (sha256 compared). The same procedure against the
already-patched dump: package `1` stages nothing, its entry reads 15 of 15, the step detail reads
`0 text tables, 322 images, 15 text tables left in Chinese`, and the game data is again byte-identical.
12 wording assertions through the real `Patcher.build_translation` and the real `App.worker` with stubbed
inputs: PASS, covering the no-loss and textures-only cases (unchanged), singular and plural, a summary
with no `text_skipped` key at all, and the nothing-staged-with-loss path. Independent review of
`9a276c3..b5cd724` found no critical issues, and of the follow-up `b5cd724..9c39a1d` found no regression;
`8d0704c` is prose only and changes no logic.

**Journey log**

- The names were never a catalog gap: the catalog maps 瑶妹→Yaria, 白歌→Bai Ge, 姜导→Director Jiang, and
  the runtime translates every occurrence of each. The loss happens at staging, which is why the
  catalog and the runtime both looked innocent.
- Every table the drop loop gives up on is chessplayer domain: 11 of 92 on a fresh pull and 15 of 92 on
  the older data, all Chessplayer/Skill/Talent/Secret text, with the two 600 KB tables dropped on every
  run on disk. That domain-shaped loss is what makes one screen Chinese while its neighbours are English.
- `fit_summary.dropped_while_staging` already held the answer and nothing read it. Its victim list agrees
  set-for-set with plan-minus-staged, which is the cross-check that makes `dropped` trustworthy.
- Deliberately not chased: which record the screen actually renders. That needs the game's own code or a
  phone experiment, and the report is worth having without it.
- `git worktree add` is blocked by this session's sandbox, so the branch was cut in place — after
  committing the in-flight texture work, which is what kept the tree clean enough to do that.

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

**Amended 2026-09-30.** The drop is real, is reported, and is *not* the cause of the Chessplayer
screen. Attribution was wrong: the game reads two data layers and this repo writes only the downloaded
one, while package `1` keeps 2492 of its 2873 assets — 298 of them catalog tables that translate, 51 095
records, the chessplayer names among them — only in the APK. So every chessplayer name already had
English label records staged into the override tables that *were* applied, and the screen read Chinese
anyway because it draws from the APK's copy. The only remaining action here was the reporting; the
screen is `prime-rebuild.md`'s job. The drop-loop finding below stands on its own: 11 of 92 tables never
reached the phone, and the run no longer hides it.

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
  they do today when `text_skipped` is empty. The one widening is when a run stages nothing at all and
  yet lost text: `Patcher.build_translation` no longer leaves the step at `already installed` in that
  case, and `App.worker` opens with "Nothing new to install." instead of "The translation was already
  installed." That state is reachable — an install whose textures are all done and whose remaining
  Chinese tables still cannot fit stages nothing — and it is the state where hiding the loss would
  matter most, since the losses found so far are permanent until something changes.
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

- [x] T1: Add `text_skipped` to `build_patch`'s summary and log a line per package that lost tables — acceptance: on the 10:23 session dump a run writes `text_skipped` with one entry, `considered_count` 92 and 11 dropped hashes equal to the reproduced drop set, and the log names the package (covers: S2)
- [x] T2: Add `count_untranslated_text` and wire both GUI sites — acceptance: the `translate` step detail and the final message each state how many text tables stay in Chinese, and with an empty `text_skipped` both read exactly as they do today (covers: S2; depends: T1)
- [x] T3: Update AGENTS.md's `build_patch` contract and the README run description — acceptance: the documented payload lists `text_skipped` with its entry fields, and the constraints section says the text side reports what it could not apply (covers: S2; depends: T1)
