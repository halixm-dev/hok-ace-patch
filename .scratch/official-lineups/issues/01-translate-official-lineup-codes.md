# 01: Translate the official lineups' share codes

**What to build:** the Lineup screen's *Official recommendation* tab (Newbie and Advanced) reads in English: each lineup's name, its 【Lineup ideas】 text, its position and equipment analysis. Today they are Chinese (`三分登场流`, `大河图腾流`, `日落海整备流`, `功能英雄芈月，上阵后使用战术牌…`). Evidence: `docs/lab-notebook.md`, 2026-10-21.

- Source: the config bin `F79FB1A213A9DA90` in package `1` (`ResSeasonAILineupDataBin`, 28 codes, 15 distinct lineups), in both data layers. Two more package-`1` bins hold codes of the same kind: `6A2B886E5DCF22DC` (10) and `C0C56FEFDCA0EA5D` (4). Name each table before touching it.
- Format: each entry's `FormationDataCode` is base64 of raw deflate of `OSProto.OneLineup`. The text fields are `Name`, `SimpleDesc`, `PositionDesc`, `EquipDesc`, `TalentDesc` and `EffectCardDesc`. The decoder is `EmbattleFormationDataClass:_decode` in package `10` (`2AA6E0613FA44093`). Measure the field numbers against that schema, and check that nothing else in the record (a hash, `LineupKey`, a length) depends on the code's bytes.
- Strings: none are in the catalog. Translations come through `tools/catalog_supplement.py` for both languages, must pass `adaptive.validate_translation`, and must keep hero, faction and keyword names as the terminology table reads them.
- Pass: decode, translate the text fields, re-encode the protobuf, deflate and base64, then write the bin. Leave every other field byte-identical, keep it idempotent, and record it in the staging contract (`build_patch` docstring) in the same change.
- Gate: the bin is an uncatalogued config bin. Under ADR 0005 it is never rewritten, and under ADR 0004 it is translated only once a device cycle clears it onto `extra_text.SAFE_ASSETS`. Doing this means first deciding how a share-code bin enters the catalog or the allowlist. That decision is the user's.
- Out of scope: *More lineups*, master and *My lineups* text. The game server and Ying Di send it, not the game files.
- Device cycle (`docs/runbooks/device-cycle.md`), with `--cycle-asset`: Official recommendation in both tabs, opening a lineup, *Use* on one (the lineup must still load onto the board), copying its code and importing it into My lineups, then a match to its end. Watch for the stale-checksum class: the Diamond Frenzy Starting Lineup bin drew empty when appended (lab notebook, 2026-10-16).

**Blocked by:** the gate decision above

**Status:** needs-triage

- [ ] The three bins' tables named, and every text field in their codes measured
- [ ] A round-trip check: decode → re-encode with no changes gives identical bytes, or a decode the game accepts
- [ ] Translations for both languages added and validated
- [ ] The pass written and documented in the staging contract
- [ ] Device-verified on the screens above
- [ ] `docs/translation-progress.md` and a feature record updated

## Notes

Ying Di's APK (`com.tencent.gamehelper.smoba`) holds no lineup text, so it is no source for these strings.
