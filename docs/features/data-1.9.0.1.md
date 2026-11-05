# Game data 1.9.0.1 translations

## Report

The 2026-11-05 pristine snapshot reports data `1.9.0.1`, revision `0`. Both data layers were checked:
101 readable catalogued tables in the override layer and 397 prime-only tables. Before this change,
213 distinct Chinese strings (640 rows) had no translation in either language. The supplement now
supplies all 213 in English and Indonesian. The measured sources and row locations are retained in
[the census](../../.scratch/data-1.9.0.1/leftovers.json).

Every supplement entry passes `adaptive.validate_translation` and the markup check. All 213 new
entries also preserve their numeric bracket expressions. Offline builds with the cached APK succeed
in both languages. Read-back censuses of each staged output, combined with the untouched prime layer,
find zero Chinese strings outside resource tokens in the 498 readable catalogued tables.

One catalogued asset (`4B15FC0D7596513F`) is refused as an ambiguous localization table and is reported
separately. Each build also reports one existing prime-only encoder refusal; its surviving prime bytes
introduce no Chinese rows in this census. Uncatalogued tables, prefabs, server text and textures are
outside the zero-leftover result. No game files were written for these checks; screen acceptance on
this data version remains pending. See the dated evidence in [the lab notebook](../lab-notebook.md).

Verification commands (Python 3.12):

```bat
.venv\Scripts\python.exe tools\research\census_catalog.py --game <game-dir> --apk <apk> --work <scratch-dir> --output <before.json>
.venv\Scripts\python.exe tools\build_device_patch.py --runtime resources\runtime --game <game-dir> --catalog resources\catalog --work <work-dir> --output <out-dir> --apk <apk>
.venv\Scripts\python.exe tools\research\census_catalog.py --game <game-dir> --apk <apk> --work <scratch-dir> --overlay <out-dir> --output <after.json>
```

Repeat the build with `resources\catalog_id` for Indonesian. `check_ui_strings.py` and
`check_staging_contract.py` also pass. Release version: `1.9.1.1`.

## [S1] Problem

The new data adds Black & White Central Plains blind boxes, Faction Highlights, Double Energy Storage
missions, item errors, and reworded card and skill effects. Sources absent from the catalog stayed Chinese.

## [S2] Design

Add only measured missing sources to `catalog_supplement.TEXTS`, with both target languages. Preserve
markup, placeholders and numeric expressions; use the catalog's existing Hero and keyword names.
Upstream catalog entries still win. Keep the reusable census under `tools/research/`, outside shipping code.

## [S3] Out of Scope

No new catalog tables, config-bin permissions, texture aliases, prefab edits or pipeline changes. The
source catalogs and pristine snapshot stay unchanged. This does not claim a complete translation.
