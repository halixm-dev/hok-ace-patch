---
feature: official-lineups
status: delivered
updated: 2026-10-21
---

# Official Recommendation Lineups

## Report

**Verdict, 2026-10-21: cleared.** `F79FB1A213A9DA90` (`ResSeasonAILineupDataBin`), the bin behind
Lineup → Official recommendation, is on `extra_text.SAFE_ASSETS`, so every run now translates it in
English and Indonesian. That covers 118 of 118 distinct strings in 264 fields: the lineup names, the
【Lineup ideas】 text and the 芈月 tactic-card text. It is the first config bin on the allowlist since
2026-10-05, and the first rewritten with its checksum resealed.

| what landed | where |
|---|---|
| the three bins mapped, each named as a table | `tools/research/lineup_bins.py`; lab notebook, "The three lineup bins mapped" |
| the config-bin checksum (fields 1 and 4) and its reseal | `tools/config_bin.py`; `tools/research/config_bin_checksum.py` |
| 198 lineup strings, English and Indonesian | `tools/catalog_supplement.py`, `TEXTS`, "Official lineups" |
| the share-code rewrite | `tools/lineup_codes.py` (`rewrite_bin`), called by `extra_text.rewrite_config` from both paths |
| the device verdict | `tools/extra_text.py`, `SAFE_ASSETS`, beside the hash |

### Verification

- **Device cycle** (`docs/runbooks/device-cycle.md`), Xiaomi M2007J3SG, Android 12, data 1.6.0.1 r0,
  builds from session `20261017-224744` with its cached `installed.apk`. Order: English control, then
  English cycle (`--cycle-asset F79FB1A213A9DA90`), then the same pair in Indonesian. Each cycle differs
  from its control only in that asset. The user walked each run: Newbie and Advanced, a lineup's detail,
  *Use* into a match, copy and import into My lineups, and a match to its end. The controls read Chinese.
  The cycles read English and Indonesian, and every screen and control behaved as on the control, with
  no QTS-failure popup. Package `1` read back equal to the build before and after play; the QtsVFS scan
  found 0 broken files; logcat held no `[DATABIN]`, `QTSFailure` or `errorCode:361` line. The backup
  was restored afterwards (745 of 745 files equal).
- **Offline, after the move:** a normal English build (no `--cycle-asset`) stages byte-identical
  packages to the cleared cycle build; the summary differs only in `cycle_assets`.
- **Offline, per bin:** `tools/research/check_lineup_cycle.py --game <dump> --prime <prime> [--control
  <out> --cycle <out> --language en|id]` reseals, decodes and reads back all three bins in both layers
  and both languages (lab notebook, "Lineup share-code pass built offline").

**What a user sees.** A lineup already in My lineups keeps the language it was added in. My lineups is
the server's copy (`CSQueryMyLineups`), so after a language switch a lineup has to be removed and added
again. Seen on the phone: a lineup added under the English cycle read English under the Indonesian one
until it was re-added.

**Still owed.** `6A2B886E5DCF22DC` (`ResRecommendLineup`, 94 strings) and `C0C56FEFDCA0EA5D`
(`ResHeroStrategyDataBin`, hero strategy videos) stay on `CANDIDATE_ASSETS`. Neither has a screen yet,
so neither has had a cycle. The longest name (*Central Plains Ancient Coin Build*, 33 characters) was
not checked against the card on a phone. `出击` reads *Strike* by guess (ticket 03). The three
catalog-owned strings keep weak Indonesian, a `catalog_rewrites.json` follow-up.

**Journey log**

- Where the tab reads from: a local config bin, decoded on the phone from share codes (base64 of raw
  deflate of `OSProto.OneLineup`), not Ying Di. Community lineups are server text, out of reach. Lab
  notebook, "Lineup screen: the official lineups are local".
- Mapping the bins (ticket 01): 51 codes and 201 distinct strings across three tables. Raw deflate at
  zlib's default reproduces every stream. Keeping each code's field order reproduces the untouched bytes.
- The checksum (ticket 02): field 1 is MD5 of the rows and field 4 is the value the native loader
  folds and checks. Both recompute on all 1,493 package-`1` bins. Verdict: recomputable.
- Translations (ticket 03): 198 strings, both languages, through the catalog supplement, with
  keywords as the terminology table reads them.
- The pass (ticket 04): `--cycle-asset` rewrites a lineup bin in both paths through one
  `rewrite_config`, reseals it, and is idempotent; four builds for the cycle.
- The cycle (ticket 05): cleared in both languages. A friend's report of a 5–6 MB lineup patch was
  checked against the measured 46–52 KB of lineup text. It matches a whole-game text patch, not the bins.

## [S1] Problem

Lineup → Official recommendation showed every lineup name and its strategy text in Chinese after a full
build. The text sits inside share codes in uncatalogued config bins of package `1`. `pb_text` cannot see
inside a code. Every config bin rewritten before was withdrawn, because the rewrite left a stored checksum
stale and the game dropped what the bin fed (ADR 0005).

## [S2] Design

1. **Map before changing.** Name each bin from the game's own registry and schema, measure `OneLineup`'s
   text fields, and prove a byte-exact round trip of protobuf, deflate and base64.
2. **Recompute the checksum.** Port the native loader's fold (field 4) and the rows' MD5 (field 1). Prove
   the port against every stored digest before a rewrite relies on it.
3. **Translate through the supplement.** The catalog files are not edited. Strings come from
   `catalog_supplement`, used only where the catalog has no entry. Keywords read as the terminology table
   reads them.
4. **Rewrite in place.** Decode each code, translate its text fields in its own field order, re-deflate,
   re-base64, translate the row text fields, rebuild the row and reseal. Anything that will not
   re-serialize identically is refused. A bin with nothing to translate keeps its bytes.
5. **Gate by a device cycle.** The bins queue on `CANDIDATE_ASSETS`. `--cycle-asset` turns one on for one
   run, and only a watched cycle moves a hash onto `SAFE_ASSETS` (ADR 0004).

## [S3] Out of Scope

- Community, master and player lineups: server text (`CSQueryPlayerLineupV2`, `CSQueryLineupDetail`).
  Writing files cannot change it. Fetching them from Ying Di would be a third party's private API with
  a user's account.
- Adding lineups the game does not ship.
- Resealing and re-cycling the withdrawn config bins: a lead this verdict opens, each its own cycle.
