---
feature: terminology-table
status: delivered
updated: 2026-10-16
branch: master
---

# Terminology Table

## Report

**What was built** — one game keyword now reads one way, the default way. `tools/terminology.py` holds a
terminology table per language (`languages.Language.terms`) and `install()` wraps `adaptive.load_catalog`, so
every catalog the pipeline loads has its targets corrected in memory before the runtime's `Catalog` is
built from them. `build_patch` installs it next to `install_btree_slot_map()` and logs
`glossary: N catalog strings now read 'Prepare', M … 'Steal'`. `catalog.json.gz` is not edited.

| Chinese | keyword | variants in the catalog | now |
|---|---|---|---|
| `夺取` | `href=200`, icon `╊` | Plunder, Seizure, Capture, Snatch(ed), Siphon, drain, "to capture" | **Steal** (and steals / stolen / stealing) |
| `整备` | `href=11`, icon `╬` | Ready, Readiness, Maintenance | **Prepare** (series: **Prepare Series**) |
| `登场` | `href=1`, icon `╨` | one series label, "Showtime series" | **Deploy** |

Steal and Prepare are the default names — the ones the catalog already uses most (the `夺取` link label
reads Steal 7 times in 11, the `整备` label Prepare 45 times in 55). Plunder and Readiness are the
unofficial community translation's names and are what the terminology table removes.

English and Indonesian both take it: the Indonesian catalog keeps these keywords in English ("Seri
Steal", "Efek Prepare") with the same variants. Its table adds its own misreadings — "Efek Kejang"
(Seizure in its medical sense), "PIunder" (Plunder with a capital I), "Efek steal╊" (lower case before
the icon) and "╬Siap" (Indonesian for Ready) — and puts every **series** label in the Indonesian order,
as the user chose: "╬Prepare Series" → "╬Seri Prepare", "═Temporary Level Series" → "═Seri Temporary
Level", "Shield seri" → "Seri Shield". The catalog already wrote "Seri General" 55 times and "Seri
Summon" 8, but "Prepare Series", "Initiate Series", "Deploy Series" and a dozen more the English way. The
rule (`系列` in the source, the run of capitalised words before "Series") rebuilds the label rather than
replacing a word, which is why a replacement may be a function of the match.

**Verification** — Python 3.12 (`.venv`), no test suite. Scratch scripts, not shipped.

| Check | Result |
|---|---|
| English catalog, `apply` over `unique` + `english_updates` | 40 targets now read Steal, 9 Prepare, 1 Deploy |
| Same, Indonesian catalog with its own terminology table | 36 Steal, 7 Prepare, 1 Deploy, 107 series labels to "Seri X"; 145 changed pairs |
| Indonesian `系列` strings still in the English order afterwards | none as a label. Left: Indonesian prose that already reads "seri X" ("talent seri Prepare"), and one garbled card line, "4 Summon atau ╉Totem`</a>` seri Kartu Hero", whose name sits inside a link tag the terminology table may not move |
| Markup and placeholders (`{…}`, `<…>`) of every changed pair | identical to the catalog's, both languages |
| `adaptive.validate_translation(source, target)` on every changed pair | 0 pairs the catalog passed and the terminology table fails, both languages |
| Second `apply` over the result | 0 changes (idempotent) |
| Entries containing `夺取` / `整备` with no Steal / Prepare | English 0 / 0; Indonesian 3 / 0, all Indonesian prose verbs (`curi`, `sedot`, `menyerap`), not the keyword's name |
| `installed.apk` prime package `1`, all 497 catalog tables through `translate_table`, plain vs terminology-corrected catalog | 29 tables differ; "Readiness" 6 → 0, "Steal" 935 → 1062, "Prepare" 2607 → 2639, "Plunder" 166 → 118 (the rest are `掠夺`, see [S3]) |
| Full `build_device_patch.py` on the pristine **1.6.0.1** layer (`pristine/20261016-101124/game`, `installed.apk` sha `29b3ee7e…`), English, against the same run with `terminology.install` stubbed out | exit 0 in 197 s; log `glossary: 9 catalog strings now read 'Prepare', 40 … 'Steal'`. Summaries identical apart from the words: `counts` (tables 94, records 186 735, translated 180 925, unknown 2539), every package's mode and `replacement_count` (package `1` full 83, relocated-text 11, added-from-apk 293; textures 302 + 22 + 1 + 1), `text_skipped`/`graphics_skipped` empty, `append_skipped` the same one asset (`3A70308AAF6F18F8`, encoder refusal) |
| Same two runs, every staged asset read back through `QtsPackage` (62 401 assets) | name after the `╊` icon: Steal 203 → 291, Seizure 33 / Plunder 26 / Capture 25 / Snatch(ed) 4 / capturing 2 → 0 (Stolen 2); after `╬`: Prepare 1298 → 1326, Ready 22 / Readiness 6 → 0. "Soul Snatch" (`摄灵`) and "Spirit Extraction" unchanged |
| Full `build_device_patch.py` on the same 1.6.0.1 layer, **Indonesian**, after the series rule | exit 0; log `glossary: 1 … 'Deploy', 7 … 'Prepare', 107 … 'Seri', 36 … 'Steal'`; tables 94, translated 180 949, `text_skipped`/`graphics_skipped` empty, `append_skipped` the same one asset. Staged labels after an icon: `╊` Steal 300 (no Plunder, Snatch, Capture), `╬` Prepare 1316 (no Ready, Readiness, Siap), no English-order "X Series" after any icon; series read `╪Seri Initiate` 10, `╫Seri Sacrifice` 10, `╬Seri Prepare` 10, `╨Seri Deploy` 8, `═Seri Temporary Level` 8, `╋Seri Flash` 4, `╉Seri Totem` 4, `╊Seri Steal` 4 |
| Chinese `夺取`/`整备` still in the staged 1.6.0.1 packages | 114 occurrences, all in assets the pipeline does not translate (config bins outside the catalog, several withdrawn or candidates in `extra_text`) except one: table `EE5CF72D67A94C1F` carries 1.6.0.1's new wording of an achievement (`…英雄均与【整备】相关并最终夺冠`), which the catalog does not have yet |

Not yet device-verified. The change is text inside tables the pipeline already translates — no new
asset, no new kind — so it carries the same risk as a catalog re-import.

**Journey log**

- First version pointed the keywords at Plunder and Readiness, the community names — the user corrected it to the default names the same day (lab notebook, 2026-10-16).
- Full build on an already-patched session layer — stopped in `_drop_uncatalogued_tables` with or without this change, a latent bug fixed separately; the pristine 1.6.0.1 runs above replace it (lab notebook, 2026-10-16).

### Still owed

No device cycle on a pristine layer has run yet. It would show a card carrying `╊` and one carrying `╬`
reading Steal and Prepare on the phone, and the encyclopedia's keyword pages reading the same.

## [S1] Problem

The catalog was translated string by string, so the same keyword reads differently from one card to the
next. On the English catalog the `夺取` link label is "Steal" 7 times, "Plunder" 2, "Snatch" and
"Snatched" once each, and its free text adds "Seizure", "Capture", "Siphon" and "drain". `整备` is
"Prepare" 45 times, "Ready" 6, and "Readiness" in its series name. A player reading "Readiness Series:
… triggers Ready" cannot tell that one keyword is meant.

## [S2] Design

- **Keyed on the Chinese.** A `Term` rewrites a target only when its source contains the term, so a
  word in a string that never says `夺取` is untouched. `english_updates` rows carry their Chinese
  source at index 4 and are covered the same way; `contextual` rows have none and are empty anyway.
- **Only measured variants**, phrases first, and never inside `{placeholder}` or `<tag>`:
  `translate_table` compares both against the source, and a changed one would drop the record. A
  `keep` phrase is protected the same way, for a word of the same source another term owns (`摄灵` →
  "Soul Snatch").
- **Case.** A variant in a named group `w` passes its case on ("drains" → "steals"); a keyword right
  after its box-drawing icon keeps its capital; `proper=True` (Prepare) is always capitalised.
- **In memory, at load.** The scanner calls `load_catalog` by its module name, so the wrapper replaces
  the runtime's function (`_terminology` marks it, `install()` is idempotent) — the same move as
  `install_btree_slot_map()`. Building `Catalog` from the corrected JSON keeps `targets` consistent
  with the corrected strings. Every pass reads the catalog through it: scan, `make_transform` and the
  append, `extend_graphics` and the extra-text pass.
- **Per language.** `Language.terms`; Indonesian is `ENGLISH_TERMS` plus its own two fixes.

### Consequences to expect

- **A phone already patched keeps the old words.** The scanner translates Chinese; a layer that is
  already English is left as it is, exactly as a newer catalog behaves. Clear the game's data (or
  redownload it) before patching to get the terminology table — the same rule as switching language.
- Counts in the summary do not move: the terminology table changes words inside tables that were already staged.

## [S3] Out of Scope

- **`掠夺` keeps "Plunder"** ("Plunder Blade", "Tactics: Plunder", the Factionless series' "plunder 30
  Levels"). It is a different word from the keyword, and the terminology table is keyed on the keyword.
- **`偷取` keeps "Steal"** and **`备战` / `准备` keep "Prepare"** (the preparation phase) — different words
  that already read the default names.
- **Other inconsistent keyword labels** measured on the same pass and not changed: `登场` beyond its one
  "Showtime series" label (a "Let's go." label remains), `复生` (Revive / Recovery / Revival / Resurrect), `退场` (Exit /
  Retire / Retreat), `合成` (Combine / upgraded), `往生图腾` / `因缘图腾` (several names). Each needs a
  chosen name before it can join the terminology table.
- Textures: a keyword drawn into an image is not text and is not reached here.
- Editing `catalog.json.gz`: the catalog is the PC pipeline's file (`AGENTS.md`, *Boundaries*).
