---
feature: card-pack-covers-cycle
status: withdrawn
updated: 2026-10-16
---

# Card-Pack Covers Device Cycle

## Report

**Verdict, 2026-10-16: withdrawn.** With the bin appended, Diamond Frenzy's Starting Lineup grid draws
**empty**: no section header and no covers, only the search and filter bar. The control, the same build
without `--cycle-asset`, draws the grid (still Chinese) on the same phone minutes earlier. Pushing the
control's package `1` back brought the grid back. This is the reseal failure `AGENTS.md` records for the
encyclopedia withdrawals: the rewritten content is fine (it reads back and re-parses offline); the bin's
stored checksum is not, so the client drops what it feeds. The hash is withdrawn in `tools/extra_text.py`
and gone from `CANDIDATE_ASSETS`. T2 (`transform.config`) and T3 (the short forms) stay: both are inert
without a cycle, and a way to reseal a bin would need both.

T1-T4 landed on 2026-10-16 and both builds passed the offline acceptance below before they went on the
phone.

### Device log (Infinix X6853, Android 16, game data 1.6.0.1, English)

| step | build | watched | result |
|---|---|---|---|
| version check | — | phone `packages/1/1.info` vs the dump | both `{"version":"1.6.0.1","revision":"0"}` |
| backup | — | `packages` + `Watchdog` | `D:\scratch\hok-cycle\backup\device-backup.tar`, 2.4 GB |
| T5 | control, all 7 packages | startup, QtsVFS scan | `ScanJob done ... errorCode=0`, no crash |
| T5 | control | Encyclopedia DF: Basic Rules, Effect Card, Talent Card, Starting Lineup | all draw; Starting Lineup Chinese as expected |
| T6 | cycle, package `1` only | startup, login, lobby, Card menu, ACE Encyclopedia | all normal, scan `errorCode=0` |
| T6 | cycle | Encyclopedia DF → Starting Lineup | **empty grid**, still empty after a further 6 s |
| rollback | control's package `1` | Encyclopedia DF → Starting Lineup | grid back |

Not watched: a match, the achievement titles, the weekly leaderboards and King of Kings. The control's
own verdict on the 1.6.0.1 supplement is therefore still partial (`MEMORY.md`).

| what landed | where |
|---|---|
| the queue entry, with its measurement | `tools/extra_text.py` → `CANDIDATE_ASSETS[0x9E45602F1857539D]` |
| the enabled config set, offered to the append | `package_rebuild.make_transform` → `transform.config`, read by `add_prime_only` |
| the 34 short forms, EN + ID, generated from the catalog's own strings | `tools/catalog_supplement.py` → `derived`, `FACTION_HEROES` |

### Offline acceptance (English, pristine 1.6.0.1 dump, cached APK)

Two builds with one command, the second adding `--cycle-asset 9E45602F`. Outputs are in
`D:\scratch\hok-cycle\{control,cycle}\out`, logs beside them.

- `cycle_assets`: `[]` for the control, `["9E45602F1857539D"]` for the cycle.
- `text_skipped` and `graphics_skipped` are empty in both. `append_skipped` holds the same single refusal
  (`3A70308AAF6F18F8`, the known LZ4-equals-length table); only its denominator moves, 294 → 295.
- The only differing files are `1/1.db` and `1/1_0.db`. Package `1` gains one entry (720 → 721,
  `9E45602F1857539D`), and none of the other 720 assets changes by a byte. The log reads 293 → 294
  "translated assets added from the APK".
- The appended asset reads back at 30,414 bytes in one 307,200-byte chunk. It is byte-equal to a fresh
  `pb_text.rewrite` of the APK's copy, re-parses as protobuf, and no string field in it holds CJK. The two
  CJK code points a raw decode finds (`榑`, `贐`) are binary bytes the APK's copy holds too.
- The supplement check over both catalogs reports 0 placeholder changes and 0 `validate_translation`
  failures. `tools/research/extra_text_candidates.py` lists the new candidate as "not in the downloaded
  layer" and confirms that a run with no cycle still plans 0 assets.

The supplement's 34 short forms are in **both** builds, so the control is not byte-identical to a build
from before this change wherever a catalog table holds one of them as a whole value. That is on purpose
(`[S2]` 3): they are catalog-wording strings and need no cycle. It is also why the control goes on first.

### What was measured (2026-10-16, game data 1.6.0.1, APK 1.1.1 / 774472)

- **The screen.** Encyclopedia → Diamond Frenzy → Starting Lineup draws its section header
  (`逆天改命卡包`) and the hero label under every card cover (`百里玄策`, `狄仁杰`, …) in Chinese. The
  side panel's pack name, "Defy Fate (Xuance)", is already English: it comes from the catalog table
  `492C173C523F74EE`.
- **The source.** `9E45602F1857539D`, package `1`, 29,529 bytes raw, one Oodle chunk (compression `4`).
  It is a protobuf config bin and **not** a catalog table, and it exists **only in the APK** (prime). The
  pristine 1.6.0.1 downloaded layer `pristine/20261016-101124` does not carry it. Each record pairs a
  cover icon (`ArtHub/Icon/CardCover/lcon_CardCover_NiTianGaiMing_BaiLiXuanCe`) with its group label
  (`逆天改命卡包`) and its hero label (`百里玄策`). A scan of every package in both layers finds the bare
  header in this asset alone; everywhere else it is part of a longer string.
- **What a rewrite would translate.** `pb_text.rewrite` with `extra_text.translator_for` finds 60
  distinct Chinese strings. `catalog.unique` has an official English for 27, all hero names.
  The other 33 are short forms whose wording the catalog already carries in a longer string:

  | short form | count | derived from the catalog's own | example |
  |---|---|---|---|
  | `<pack>卡包` group header | 5 | `<color=#97DFFFFF><pack>卡包</color>`, tags dropped | `逆天改命卡包` → Defy Fate Card Pack |
  | `<faction>-<hero>` | 12 | faction name + hero name, joined with ` - ` as the source's hyphen reads | `河洛-李白` → Central Plains - Li Bai |
  | `<contract>(<faction>)` | 13 | `契约·<contract>(<faction>)` minus its `Contract: ` | `起舞(三分)` → Dance (Three Kingdoms) |
  | bare hero name | 3 | `逆天改命(<hero>)` | `后裔` → Hou Yi, `哪吒`, `杨戬` |

  With all 60 translated the rewrite touches 252 fields and grows the asset to 30,414 bytes, still one
  chunk at its 307,200-byte chunk size. English and Indonesian measure the same.
- **Why it is a cycle and not a fix.** The asset is a config bin outside the catalog. `AGENTS.md` forbids
  rewriting one without a device cycle, and every such bin tried so far was withdrawn. One of those
  failures blanked **this same Encyclopedia**. The asset is also prime-only, so it can reach the phone
  only through the append. Today that pass never offers a config asset: `add_prime_only` filters on
  `transform.graphics | transform.tables | transform.scripts`. So `--cycle-asset` alone would be a silent
  no-op for it.

## [S1] Problem

The Starting Lineup grid is the one Diamond Frenzy screen that stays Chinese after a full 1.6.0.1 build.
The strings it draws come from a config bin that no catalog table and no allowlisted pass reaches.

## [S2] Design

Three code changes plus one cycle. On a normal run all three are inert: `SAFE_ASSETS` stays empty and
the asset is only offered when `--cycle-asset 9E45602F` names it.

1. **Queue it.** Add `0x9E45602F1857539D` to `extra_text.CANDIDATE_ASSETS`, recording the measurement
   above (60 distinct, 27 official, 60 with the derived forms, 252 fields). `resolve_candidates` then accepts it.
2. **Let the append offer an enabled config asset.** `make_transform` exposes `transform.config`, the
   `SAFE_ASSETS | candidates` set it already decides against. `add_prime_only` adds that set to
   `wanted`. With no cycle and an empty allowlist, the set is empty, so a normal run stages
   byte-identical packages. The `AGENTS.md` line that says the append "never asks about the
   `SAFE_ASSETS` config assets" changes in the same commit.
3. **Supply the 33 short forms**, generated in `tools/catalog_supplement.py` from the catalog's own
   longer strings, in English and Indonesian. The file's rules apply: never override a catalog entry,
   and keep markup intact. These entries also help any catalog table that holds the same short form,
   with no cycle needed. `check` must pass with 0 `validate_translation` failures.

### The cycle (one variable: this asset)

The phone also owes a verdict on the 1.6.0.1 supplement build (`MEMORY.md`, 2026-10-16), so that build
goes first as the **control**, and the cycle build differs from it only by `--cycle-asset`.

1. **Disk.** The work and output directories go on `D:`, e.g. `D:\scratch\hok-cycle\{control,cycle}`.
   Drive C is too full for an 8 GB work tree.
2. **Version check.** Compare the phone's `files/QtsVFSCache/packages/1/1.info` with
   `pristine/20261016-101124/game/WXQ_Data/Package/builtin/1/1.info`. If they differ, stop: the dump
   is stale and must be redumped first.
3. **Build both offline** with the same command, the second adding `--cycle-asset 9E45602F`:

   ```bat
   .venv\Scripts\python.exe tools\build_device_patch.py --runtime resources\runtime ^
       --game "dist\HOK ACE Patcher Data\pristine\20261016-101124\game" --catalog resources\catalog ^
       --work D:\scratch\hok-cycle\cycle\work --output D:\scratch\hok-cycle\cycle\out ^
       --apk "dist\HOK ACE Patcher Data\installed.apk" --cycle-asset 9E45602F
   ```

   Offline acceptance, before anything goes on the phone:
   - The cycle summary's `cycle_assets` is `["9E45602F1857539D"]`, and the control summary's is empty.
   - `append_skipped` and `text_skipped` match between the two.
   - The two output trees differ in package `1` alone, by exactly one appended record: the index, the
     shard, the tree pages and the header's data-end words. Nothing else in package `1` differs.
   - Read the appended asset back through `QtsPackage` and `qts_relocate.read_raw`. It must re-parse with
     `pb_text`, hold no CJK in the 252 rewritten fields, and keep every non-string field byte-identical
     to the prime copy.
4. **Back up** `files/QtsVFSCache/packages` and `Watchdog` from the phone, then push the **control**.
   Watch it per the device loop in `prime-rebuild.md`, plus the supplement's owed screens (achievement
   titles, the weekly leaderboards, King of Kings). Record that verdict on its own.
5. **Push the cycle build's package `1`** (`Watchdog/*` cleared), then log in with *Scan to login* and
   watch:
   - Encyclopedia → Diamond Frenzy → Starting Lineup: the header and the hero labels are English, and
     every cover still draws. A blank grid or a missing back arrow or title means the asset fails.
   - The other Encyclopedia tabs (Effect Card, Equipment Card, Talent Card, Special Event), and the same
     tabs under ACE Tournament. A blank grid anywhere there also means the asset fails.
   - A Diamond Frenzy match: the initial lineup pick (three packs), then the match **to its end**. The
     `/未翻译UI/QTSFailureTips` popup, or any crash, means the asset fails. The 10-01 verdicts were
     wrong because they watched only the start.
   - `adb logcat` for QtsVFS errors during startup and the match.
6. **Verdict.**
   - **Pass:** move the hash from `CANDIDATE_ASSETS` to `SAFE_ASSETS` and write the screens watched beside
     it.
   - **Fail:** push the backup back, confirm the grid returns, and record the hash and its symptom among
     the withdrawn assets in `tools/extra_text.py`. The supplement entries from step 3 stay; they are
     harmless.
   - **Either way:** update this record's Report, `MEMORY.md` and `docs/translation-progress.md`.

## [S3] Out of Scope

- Resealing the bin's stored checksum. The way to reseal one is not known here (`AGENTS.md`), and
  this cycle measures whether this bin needs it.
- Moving or rebuilding package `1` (`REBUILD_PACKAGES` stays empty).
- The other per-mode encyclopedia copies, if a different mode carries its own covers bin. A pass on this
  one is not evidence for another hash.

## Tasks

- [x] T1 `CANDIDATE_ASSETS` entry for `9E45602F1857539D` with its measurement
- [x] T2 `transform.config`, consumed by `add_prime_only`; `AGENTS.md` sentence updated
- [x] T3 derived short forms in `catalog_supplement.py`, EN + ID, `check` clean
- [x] T4 control and cycle builds on `D:`, offline acceptance in step 3 met (English)
- [~] T5 control pushed and watched: startup and the Encyclopedia only; a match and the supplement's own screens are still owed
- [x] T6 cycle pushed and watched: **withdrawn**, empty Starting Lineup grid
