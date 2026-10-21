# 01: Map the official lineup bins

**What to build:** an offline measurement of the three package-`1` config bins whose entries carry lineup share codes (`F79FB1A213A9DA90`, `6A2B886E5DCF22DC`, `C0C56FEFDCA0EA5D`), so the later tickets know what they are changing. The Official recommendation tab reads `ResSeasonAILineupDataBin` and decodes each entry's `FormationDataCode` (base64 of raw deflate of `OSProto.OneLineup`) on the phone. Which bin is that table, and what the other two are, is not yet known. Evidence: `docs/lab-notebook.md`, 2026-10-21.

- Name each bin's table from the game's own data-bin registry and schema in package `10`, not by guess.
- Measure `OneLineup`'s text fields against the Lua schema and the decoder (`EmbattleFormationDataClass:_decode`): `Name`, `SimpleDesc`, `PositionDesc`, `EquipDesc`, `TalentDesc`, `EffectCardDesc`, and any nested message that holds Chinese (operation details, per-round notes).
- List every distinct Chinese string per field and per bin, in both data layers, with how many codes use it.
- Round trip: decode a code and re-encode it unchanged. Record whether the protobuf bytes, the deflate stream and the base64 text come back identical, and if not, which layer differs. A decode the game accepts is enough for the deflate layer, but say which compressor settings reproduce it.
- Note anything else in an entry that is derived from the code's bytes (`LineupKey`, a hash, a length).

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Each of the three bins named as a table, with the evidence
- [ ] `OneLineup` text fields and their field numbers measured
- [ ] Per-bin string list written to this folder, both layers
- [ ] Round-trip result recorded per layer (protobuf, deflate, base64)
- [ ] Findings added to `docs/lab-notebook.md`
