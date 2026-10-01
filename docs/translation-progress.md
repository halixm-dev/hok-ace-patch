# Translation Progress

The coverage ledger: what the catalog covers, what reaches the phone and by which path, what is
translated outside the catalog, and what is knowingly left Chinese. `AGENTS.md` carries the rules this
state obeys and `docs/compose/spec/` the reasoning behind each pass; this file carries the running
counts, so it is the one that moves when coverage moves.

Catalog counts verified 2026-10-01 at `cf1055e`. The per-layer counts are device measurements against
game data **1.4.0.1**, each recorded with its command in the spec record named beside it.

## How progress is counted

Coverage is **the staged text tables, the catalog's textures, and four `extra_text` assets** — nothing
else. There is no percentage: the build's own totals for tables, textures and config assets are not
published, so progress is the counts a run prints, and the gap is what the sections below name.

A run reports four numbers through the app's `translate` step, all read from
`device_patch_summary.json`:

| reported | accessor | holds |
|---|---|---|
| text tables | `count_translated` | catalog tables the run applied |
| images | `count_translated` | catalog textures the run applied |
| text tables left in Chinese | `count_untranslated_text` | translated, then not applied — `text_skipped`, `append_skipped` |
| images left in Chinese | `count_untranslated_graphics` | found, then not translated or not added — `graphics_skipped`, `append_skipped` |

The last full run recorded (`prime-only-append.md`, `run-t4`) printed **392 text tables and 395 images
across 6 packages**, with `text_skipped`, `graphics_skipped` and `append_skipped` all empty. That is the
run `README.md` means by "a run applies all 395".

## What the catalog holds

`resources/catalog/` is produced by the PC patcher pipeline; this repo consumes it, so a record is
corrected in this repo's code rather than in the catalog.

| what | count | where |
|---|---|---|
| text tables (`catalog.known`) | **499** | `catalog.json.gz` → `table_hashes` |
| texture edits (`catalog.graphics`) | **398** | 324 `.blocks` block patches + 74 `.assets` whole-image replacements |
| distinct Chinese → English strings (`catalog.unique`) | **39 011** | `catalog.json.gz` → `unique` |
| review renders | 44 | `previews/` |

`.blocks` and `.assets` are the two porting *kinds*, not text versus texture: every payload file in the
catalog directory is a texture, and all 398 of them are in `catalog.graphics`.

`catalog.json.gz` also carries the catalog's own history: `english_updates` (29 750 keys, each holding
the previous and the new official English), and `resources/catalog/english_sibling_audit.json` records
the merge behind it — 12 605 exact-key updates, 1 899 reviewed English-only updates, and no ambiguous key
or unreadable asset preserved.

Re-measure with no phone and no dump:

```bat
set PYTHONPATH=tools;resources\runtime
.venv\Scripts\python.exe -c "from pathlib import Path; from wxq_patch import adaptive; c = adaptive.load_catalog(Path('resources/catalog')); print(len(c.known), len(c.graphics), len(c.unique))"
```

## What reaches the phone

The game reads **override** (downloaded) first and falls back to **prime** (inside the APK), and every
pass here writes into override. An asset that exists only in prime is therefore unreachable by an
in-place edit, which is what the rebuild and the append pass exist to close. `prime_probe.py` censuses
both layers; a search for a missing asset has to run over both.

### Textures — 395 of 398 applied

| where the edit exists | count | applied by |
|---|---|---|
| downloaded layer only | 322 | texture pass, in place |
| both layers | 1 | whichever pass owns its package — once |
| prime only — package `1050016095` | 71 | prime rebuild — `REBUILD_PACKAGES` |
| prime only — package `21` | 1 | append — `qts_insert.add_assets` |
| **applied** | **395** | |
| neither layer | 3 | unreachable: `197CC5393D16E3CB`, `884E0B4581F47CF7`, `89C771ECFCDC7FBE` |

The one appended edit is `7B4CC5DF48336D2D`, the wide Central Plains panel the Card Info view draws. Its
package `21` stays out of `REBUILD_PACKAGES` on purpose: a rebuild applies it too and the game mounts it,
but on the phone the Factionless hero Yixing then draws as the game's grey placeholder. Append adds one
record to `21`'s override copy and leaves the container's shape alone.

One of those 395 is recovered rather than ported: `C9E29F61B9E73713` (Three Kingdoms) is 592x816 in the
catalog and 592x824 on the device, so the pass aligns the two images and copies only the label across
(`splice_label`). It counts as applied, but as a correctness fix: which screen draws it is not
established, so it is not evidence of anything visible.

### Text — the staged tables plus package `1`'s prime layer

Text applies three ways: staged in place (`full`, falling back to `fit-only`), relocated to the end of the
shard when a longer table has no room (`relocated-text`), and carried out of the APK by a rebuild
(`rebuilt`). The rebuild is what the prime layer needs, and only two packages have one:

| package | prime entries | override entries | prime only | of those, catalog tables | translate |
|---|---|---|---|---|---|
| `1` | 2873 (45.9 MB) | 403 (29.3 MB) | 2492 | 408 | **298** — 51 095 records |
| `1050016095` | 608 (5.2 MB) | 2 (0.3 MB) | 606 | 0 | 0 — but 71 catalog textures |

On this data a run stages **392 replacements for package `1`**: 94 downloaded assets re-translated plus
the 298 tables taken out of the APK, which is where the run's 392 text tables come from. The chessplayer
names, skills, talents and secret skills are in that 298 — the screens that draw them read prime, so no
override-only path could reach them. Package `1` goes 29.3 MB → 30.6 MB in the process and package
`1050016095` 0.3 MB → 2.5 MB, which is the whole cost of the rebuild.

Relocation is why the stager no longer loses these: it used to drop 11 of package `1`'s 92 translated
override tables at the container, every one a chessplayer skill, talent or secret-skill table.

Re-measure:

```bat
.venv\Scripts\python.exe tools\research\prime_probe.py --apk "dist\HOK ACE Patcher Data\installed.apk" ^
    --game <dump> --packages 1 1050016095 21
.venv\Scripts\python.exe tools\research\check_graphics.py --game <dump> --table
```

`check_graphics.py` sees the downloaded layer only; the APK's `assets/bin/Data/Package/builtin/` is
`prime_probe.py`'s half of the census.

## Translated outside the catalog

`extra_text` (over `pb_text` and `unity_text`) translates display strings in config assets the catalog
has no localization table for. Its allowlist is device-gated and exactly four assets:

| asset | what it is | translated by |
|---|---|---|
| `2D1113B0AD51A562` | ~11 000 AI opponent nicknames | pinyin romanisation — the catalog has no official translation |
| `A1987F488164E53A` | display-text table (`{id, text, #key#}`) | the catalog's official English, exact matches only |
| `1C8F7FFF7BDEF14D` | post-match compliments | same |
| `B5D856BFDF22400D` | rule pages | same |

Three narrower gates sit beside the allowlist in `tools/extra_text.py`:

- `OFFICIAL_FIXES` overrides one catalog translation that reads a name as a word (`蝉儿` → `Chan'er`).
- `SKIPPED_STRINGS` guards `空`, a skill-config value the client reads back rather than displays.
- `UNITY_TEXT_PACKAGES` is **empty** — package `19`'s Unity prefab labels stay untouched — and
  `EXCLUDED_PACKAGES` is `{"10", "14"}`, the skill editor's labels and the gameplay scripts, where the
  Chinese is logic rather than display text.

Resource tokens `{Energy}`, `{LordExp}` and `{LordHp}` are expanded to `Energy`, `Chessplayer EXP` and
`Chessplayer HP` in the staged replacements and in the assets the rebuild and extra-text passes
translate. The catalog keeps the tokens, because `translate_table` requires matching placeholders.

### Withdrawn and untried

Ten assets were enabled, watched on a phone and withdrawn, each with the screen that showed the damage;
the hashes and symptoms are beside the allowlist. Task names `5214339F97C419ED` make a tournament replay
SIGSEGV, the four chessplayer-skill assets remove the skill-description button, and mail / quiz /
"not open yet" notices remove the game button after pressing start and blank the encyclopedia. Fifteen
further assets are named there as *not tried* — guide triggers, buff definitions, nickname parts,
damage-type tables, newbie unlock rewards and six small label tables. Both sets stay out until a device
cycle says otherwise.

## Knowingly left Chinese

- The three catalog texture edits that exist in neither layer.
- Package `19`'s Unity prefab labels (the lobby hangs; only the faction names, rewritten, crash at start
  with "stack corruption detected"), and the chessplayer definition `A8BC70BB87700709` field 37 (lobby
  loading stalls even with every reference renamed alongside it).
- Package `15`: 3990 textures, 1994 of them card-shaped, and the catalog's 299 entries at that shape are
  the hero cards. The rest carry a type word or a card name on the bottom band and are not catalogued.
- Every texture outside `resources/catalog/` and every text table outside the staged packages.
- The prime-only remainder no catalog entry covers at all: **2084** of package `1`'s 2492 prime-only
  assets and **535** of package `1050016095`'s 606. This is the honest measure of what is not merely
  untranslated but uncatalogued, and it is what a future catalog import would have to grow into.

## Keeping this file true

Update it in the same change as the work when any of these moves a count:

- the catalog is re-imported — the four numbers in *What the catalog holds* change together;
- a pass gains or loses a translated asset kind, or a package enters or leaves `REBUILD_PACKAGES`;
- a device cycle adds or withdraws an `extra_text` allowlist entry;
- a run comes back with `text_skipped`, `graphics_skipped` or `append_skipped` non-empty, which moves a
  count out of the applied column.

Take the numbers from the run's own summary and from the record in `docs/compose/spec/`; never from
memory. Where a number here disagrees with a run, the run is right and this file is stale.
