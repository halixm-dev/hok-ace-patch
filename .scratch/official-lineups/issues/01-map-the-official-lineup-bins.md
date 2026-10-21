# 01: Map the official lineup bins

**What to build:** an offline measurement of the three package-`1` config bins whose entries carry lineup share codes (`F79FB1A213A9DA90`, `6A2B886E5DCF22DC`, `C0C56FEFDCA0EA5D`), so the later tickets know what they are changing. The Official recommendation tab reads `ResSeasonAILineupDataBin` and decodes each entry's `FormationDataCode` (base64 of raw deflate of `OSProto.OneLineup`) on the phone. Which bin is that table, and what the other two are, is not yet known. Evidence: `docs/lab-notebook.md`, 2026-10-21.

- Name each bin's table from the game's own data-bin registry and schema in package `10`, not by guess.
- Measure `OneLineup`'s text fields against the Lua schema and the decoder (`EmbattleFormationDataClass:_decode`): `Name`, `SimpleDesc`, `PositionDesc`, `EquipDesc`, `TalentDesc`, `EffectCardDesc`, and any nested message that holds Chinese (operation details, per-round notes).
- List every distinct Chinese string per field and per bin, in both data layers, with how many codes use it.
- Round trip: decode a code and re-encode it unchanged. Record whether the protobuf bytes, the deflate stream and the base64 text come back identical, and if not, which layer differs. A decode the game accepts is enough for the deflate layer, but say which compressor settings reproduce it.
- Note anything else in an entry that is derived from the code's bytes (`LineupKey`, a hash, a length).

**Blocked by:** None (can start immediately)

**Status:** done

- [x] Each of the three bins named as a table, with the evidence
- [x] `OneLineup` text fields and their field numbers measured
- [x] Per-bin string list written to this folder, both layers
- [x] Round-trip result recorded per layer (protobuf, deflate, base64)
- [x] Findings added to `docs/lab-notebook.md`

## Comments

2026-10-21: done offline with `tools/research/lineup_bins.py` (lab notebook, "The three lineup bins mapped").
`F79FB1A213A9DA90` is `ResSeasonAILineupDataBin`, `6A2B886E5DCF22DC` is `ResRecommendLineup`, `C0C56FEFDCA0EA5D` is `ResHeroStrategyDataBin`; 51 codes, 201 distinct strings. Strings: `../lineup-strings.json`; per-bin measurements: `../lineup-bins.json`. For ticket 04: raw deflate at zlib's default settings reproduces every shipped stream; keeping each code's stored field order reproduces the untouched bytes; `ResHeroStrategyDataBin`'s codes differ between the layers. For ticket 03: `TalentDesc` / `EffectCardDesc` are empty in every shipped code.
