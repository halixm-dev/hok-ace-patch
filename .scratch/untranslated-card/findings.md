# Chano untranslated description — 2026-10-17

Screenshot: `screen.png` (Xiaomi M2007J3SG, captured through ADB).

The screenshot shows Chano, ACE Tournament > Encyclopedia > Hero Card, with an English name and Chinese description dealing 30 physical damage.

The saved pristine override layer from 2026-10-16 has the updated 30/60 descriptions in catalog text tables in package 1, including `A07B2B9F994FB0ED` and `A336359CD92A858E`. Both layers were searched by `probe.py`; the cached prime layer has the older 25/50 descriptions in these tables. These cached files do not establish the current phone package hashes. Direct current-phone data access refused because the normal APK is not debuggable; no APK was replaced.

Reproduction: `.venv\Scripts\python.exe -X utf8 .scratch\untranslated-card\check_translation.py`.

Both English and Indonesian catalogs, loaded through the shipping terminology hooks, lack the updated 30/60 source strings. Calling the real `adaptive.translate_table` on `A07B2B9F994FB0ED` leaves both descriptions Chinese (8128 records, 8112 translated, 13 unknown).

Cause: changed numeric placeholders make these different source strings from the reviewed 25/50 descriptions. The owning pass is catalog text-table translation. Proposed fix: add measured 30/60 variants for both languages through `tools/catalog_supplement.py`, preserve placeholders, validate, then run a device cycle. No shipping code or phone data changed during diagnosis.
