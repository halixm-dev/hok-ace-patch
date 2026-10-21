# 04: Share-code pass for a candidate bin

**What to build:** an offline build that can translate a lineup bin's share codes for one device cycle. The lineup bins join `extra_text.CANDIDATE_ASSETS` with their measurements. A run with `--cycle-asset` on one of them writes it with each code decoded, its text fields translated, then re-encoded, re-deflated and re-base64'd. A run without the flag leaves the bin untouched. Nothing goes onto `SAFE_ASSETS` here (ADR 0004).

- The generic protobuf rewrite does not see inside the codes, so the code transform is its own step. Every field other than the translated text stays byte-identical, at the protobuf and the bin level.
- If ticket 02 found a recomputable checksum, the pass recomputes it. If ticket 02 found none, record that it was checked.
- Idempotent: running the pass on its own output changes nothing. Every translated code decodes with the same steps the game's decoder uses, and the decoded fields read back as the targets.
- A bin present in only one layer reaches the override layer by append, like any other candidate.
- Update the staging contract (the `build_patch` docstring) in the same change, then run the contract and reference checks.

**Blocked by:** 01, 02, 03

**Status:** done

- [x] The lineup bins on `CANDIDATE_ASSETS` with their measured string counts
- [x] `--cycle-asset` build writes the translated codes; a build without it leaves them pristine
- [x] Translated codes decode and read back; a second run is a no-op
- [x] Checksum handled per ticket 02's verdict
- [x] Staging contract updated; `check_staging_contract.py` and `check_references.py` pass
- [x] Control and cycle builds in a working folder outside the repo, ready for ticket 05

## Comments

2026-10-21: done in `tools/lineup_codes.py` (`rewrite_bin`), `tools/config_bin.py` (`reseal`, the shipping port;
`tools/research/config_bin_checksum.py` now imports it and still reproduces all 1,493 stored digests) and
`extra_text.rewrite_config`, which both `plan_package` and `make_transform` now call. The three bins are on
`CANDIDATE_ASSETS`: `F79FB1A213A9DA90` 118 of 118 distinct strings (264 fields), `6A2B886E5DCF22DC` 94 of 94 (196),
`C0C56FEFDCA0EA5D` 36 of 36 (45) override / 35 of 35 (76) prime, the same in both languages. Checksum: resealed
(fields 1 and 4), per ticket 02's verdict. Evidence: `docs/features/extra-text-cycles.md`, 2026-10-21.
**Builds for ticket 05** (game data 1.6.0.1, session `20261017-224744`): `D:\scratch\hok-lineups\en-control\out`,
`D:\scratch\hok-lineups\en-cycle\out` (`--cycle-asset F79FB1A213A9DA90`), `D:\scratch\hok-lineups\id-control\out`,
`D:\scratch\hok-lineups\id-cycle\out`. Each cycle build differs from its control in package `1` only, and there
in that one asset. Check the phone's game-data version against 1.6.0.1 before pushing.
