# Game data 1.10.0.1 translations

## Report

The saved phone snapshot from 2026-11-12 reports data `1.10.0.1`, revision `0`. The census reads
107 catalogued override tables from package `1` and 391 prime-only tables from the cached APK.
Both languages lacked the same 158 Chinese sources in 929 rows across 44 override tables.
All now have English and Indonesian entries in `catalog_supplement.TEXTS`.

| Offline check | English | Indonesian |
|---|---:|---:|
| New sources translated | 158 | 158 |
| New rows read back from staged packages | 929 | 929 |
| Tables holding those rows | 44 | 44 |
| New rows still Chinese | 0 | 0 |
| Literal supplement pairs passing runtime and markup validation | 1523 | 1523 |

Fresh offline builds stage package `1` without an APK: 96 tables in place and 11 relocated, with
`unknown` zero and empty `text_skipped` lists. Read-back checks the actual saved bytes, without
translating them a second time, against the catalog's final targets. Every checked table keeps its row
keys. These are package-`1` checks, not full installs or new texture counts. The APK is used for the
initial census only; prime-only encoding and other override packages were not re-tested.

The allowed Official recommendation lineups have no missing translations. The existing ambiguous
asset `4B15FC0D7596513F` stays refused. Uncatalogued tables and other assets stay outside this change.
No phone game files were written. Screen acceptance remains pending.

Sources, row locations, source hashes, reviewed pairs and read-back results are retained in
[the evidence folder](../../.scratch/data-1.10.0.1/). Large inputs and outputs are under
`D:/scratch/hok-data-1.10.0.1`; the phone source was the saved snapshot of patcher session
`63ff0ad4-1b7e-44a8-9ed1-bbbe1dcb63fb` on `f15a72e`.

Verification (Python 3.12, project root):

```bat
.venv\Scripts\python.exe tools\research\census_catalog.py --game D:\scratch\hok-data-1.10.0.1\game --apk "dist\HOK ACE Patcher Data\installed.apk" --work <scratch-dir> --output <census.json>
.venv\Scripts\python.exe tools\build_device_patch.py --runtime resources\runtime --game D:\scratch\hok-data-1.10.0.1\game --catalog resources\catalog --work <fresh-work-dir> --output <fresh-out-dir>
.venv\Scripts\python.exe .scratch\data-1.10.0.1\verify.py D:\scratch\hok-data-1.10.0.1\out-en D:\scratch\hok-data-1.10.0.1\out-id
```

Repeat staging with `resources/catalog_id` for Indonesian. Always use fresh generated output folders.

## [S1] Problem

The data update adds Duo Festival, Super Weekend, Quick Match, Intimacy gifting, passive-play warnings,
cosmetics, and changed card and talent effects. Sources absent from the catalog remained Chinese.

## [S2] Design

Supply measured missing sources through the existing supplement. Catalog entries continue to win.
Preserve tags, placeholders and formulas, and use existing catalog names for Heroes, factions and items.
The eight stat variants are separate literal records with the values measured in each source.

## [S3] Out of Scope

No pipeline changes, catalog-file edits, new catalog tables, config-bin permissions, texture edits,
APK changes, phone installation or release. This does not claim a complete translation.
