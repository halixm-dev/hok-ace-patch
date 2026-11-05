# Game data 1.9.0.1 translations

## Report

The 2026-11-05 pristine snapshot reports data `1.9.0.1`, revision `0`. Both data layers were checked:
101 readable catalogued tables in the override layer and 397 prime-only tables. Before this change,
213 distinct Chinese strings (640 rows) had no translation in either language. The supplement now
supplies all 213 in English and Indonesian. The measured sources and row locations are retained in
[the census](../../.scratch/data-1.9.0.1/leftovers.json).

Every supplement entry passes `adaptive.validate_translation` and the markup check. All 213 new
catalog-table entries also preserve their numeric bracket expressions. Offline builds with the cached
APK succeed in both languages. Fresh outputs apply 391 text tables and 398 textures in each language.
The corrected read-back census checks the actual effective bytes of 498 readable catalogued tables,
without translating them a second time. One existing encoder-refused row remains Chinese in each
language; there are no remaining missing catalog translations.

One catalogued asset (`4B15FC0D7596513F`) is refused as an ambiguous localization table and is reported
separately. The surviving prime row is `“兴之所至，心之所安。”` in `3A70308AAF6F18F8` for English and
`通关{0}回合后返还` in `0196F0E230EC1C70` for Indonesian. Each has a catalog translation, but its encoded
payload is refused. Uncatalogued tables, prefabs and server text are outside this census. No game files
were written for these checks; screen acceptance on
this data version remains pending. See the dated evidence in [the lab notebook](../lab-notebook.md).

Verification commands (Python 3.12):

```bat
.venv\Scripts\python.exe tools\research\census_catalog.py --game <game-dir> --apk <apk> --work <scratch-dir> --output <before.json>
.venv\Scripts\python.exe tools\build_device_patch.py --runtime resources\runtime --game <game-dir> --catalog resources\catalog --work <work-dir> --output <out-dir> --apk <apk>
.venv\Scripts\python.exe tools\research\census_catalog.py --game <game-dir> --apk <apk> --work <scratch-dir> --overlay <out-dir> --output <after.json>
```

Repeat the build with `resources\catalog_id` for Indonesian. `check_ui_strings.py` and
`check_staging_contract.py` also pass. Initial release: `1.9.1.1`; follow-up: `1.9.1.2`.

## [S1] Problem

The follow-up release `1.9.1.2` also supplies two measured missing descriptions in the already-allowed
Official recommendation lineup bin. They are separate from the 213 catalog-table strings. Its creator
nicknames stay as written; see [Official recommendation lineups](official-lineups.md).

The new data adds Black & White Central Plains blind boxes, Faction Highlights, Double Energy Storage
missions, item errors, and reworded card and skill effects. Sources absent from the catalog stayed Chinese.

## [S2] Design

Add only measured missing sources to `catalog_supplement.TEXTS`, with both target languages. Preserve
markup, placeholders and numeric expressions; use the catalog's existing Hero and keyword names.
Upstream catalog entries still win. Keep the reusable census under `tools/research/`, outside shipping code.

## [S3] Out of Scope

No new catalog tables, config-bin permissions, texture aliases, prefab edits or pipeline changes. The
source catalogs and pristine snapshot stay unchanged. This does not claim a complete translation.
