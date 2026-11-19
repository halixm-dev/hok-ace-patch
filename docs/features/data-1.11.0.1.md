# Game data 1.11.0.1 translations

## Report

Package `1` as the game re-downloaded it on 2026-11-19 reports data `1.11.0.1`, revision `0`. The
census reads 109 catalogued override tables from it and 389 prime-only tables from the cached APK.
Before this change both languages lacked the same 203 Chinese sources in 292 rows across 49 override
tables. All now have English and Indonesian entries in `catalog_supplement.TEXTS`. Re-run with the
change, the census finds no catalogued string left Chinese in either language.

| Offline check | English | Indonesian |
|---|---:|---:|
| New sources translated | 203 | 203 |
| New rows read back from staged packages | 292 | 292 |
| Tables holding those rows | 49 | 49 |
| New rows still Chinese | 0 | 0 |
| Literal supplement pairs passing runtime and markup validation | 1726 | 1726 |

Fresh offline builds stage package `1` without an APK: 98 tables in place and 11 relocated, with
`unknown` zero. The eight uncatalogued tables stay unstaged, as before. Read-back checks the saved
bytes against the catalog's final targets without translating them a second time. Every checked table
keeps its row keys. These are package-`1` checks, not full installs or new texture counts.

The allowed Official recommendation lineups have no missing translations. The ambiguous asset
`4B15FC0D7596513F` stays refused.

On the Root phone, an English patch with this change completed on the re-downloaded data (398 text
tables, 318 images). Its patched package `1` leaves none of the 203 new sources Chinese; the one
Chinese row left is the known refused prime row in `3A70308AAF6F18F8`. Indonesian was checked offline
only, and no screen was inspected in the game.

### How the pristine package was obtained

The phone's live package `1` was a mixed layer after the in-game update. Seven large text tables
(`04F21C6735D0D555`, `27BBF8CDFFFA177F`, `42E8DB43608C2FF1`, `5EB61A0269CD8550`,
`A336359CD92A858E`, `C4E32B49AE8B7FFB`, `F628F40CE23D983E`) held the update's new Chinese chunks
spliced with chunks of the earlier Indonesian translation, so they no longer parsed as tables. The
saved originals could not restore them, because the update had replaced their records. The patcher
refused the build as a stuck update and Re-downloaded packages `1`, `10` and `21`, as designed. The
census uses the package the game downloaded then, before any patch was written.

Sources, row locations, source hashes, reviewed pairs and read-back results are in
[the evidence folder](../../.scratch/data-1.11.0.1/). Large inputs and outputs are under
`D:/scratch/hok-data-1.11.0.1`.

Verification (Python 3.12, project root):

```bat
.venv\Scripts\python.exe tools\research\census_catalog.py --game D:\scratch\hok-data-1.11.0.1\game --apk "dist\HOK ACE Patcher Data\installed.apk" --work <scratch-dir> --output <census.json>
.venv\Scripts\python.exe tools\build_device_patch.py --runtime resources\runtime --game D:\scratch\hok-data-1.11.0.1\game --catalog resources\catalog --work <fresh-work-dir> --output <fresh-out-dir>
.venv\Scripts\python.exe .scratch\data-1.11.0.1\verify.py D:\scratch\hok-data-1.11.0.1\out-en D:\scratch\hok-data-1.11.0.1\out-id
```

Repeat staging with `resources/catalog_id` for Indonesian. Always use fresh generated output folders.

## [S1] Problem

The data update adds the Starry Brocade Wish with its Wish Box, Points and gifting shop, ACE Quick
Match, the Weaving the Stars mansion event, a Super Weekend and top-up event, team queue settings,
Overtime, new cosmetics and titles, and two reworded card texts. Sources absent from the catalog
remained Chinese.

## [S2] Design

Supply the measured missing sources through the existing supplement. Catalog entries continue to win.
Preserve tags and placeholders, and reuse the catalog's and supplement's names: Wish and Points,
Coupons, Love Delivery, Treasure Coin and Key, Shared Score, Honor points, ACE Tournament. The
reworded Pluck card text keeps its 1.10.0.1 twin's wording. The seven mansions are named by their
traditional English names (Dipper, Ox, Girl, Emptiness, Rooftop, Encampment, Wall).

## [S3] Out of Scope

No pipeline changes, catalog-file edits, new catalog tables, config-bin permissions or texture edits.
This does not claim a complete translation.
