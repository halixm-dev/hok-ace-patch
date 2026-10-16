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
and gone from `CANDIDATE_ASSETS`. `transform.config` and the derived short forms stay: both are inert
without a cycle, and a way to reseal a bin would need both.

The candidate entry, `transform.config`, the short forms and both builds landed on 2026-10-16, and
both builds passed the offline acceptance below before they went on the phone.

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

**Journey log**

- Finding the screen's source: `9E45602F1857539D`, a prime-only protobuf config bin outside the catalog, the only asset holding the bare header. Lab notebook, 2026-10-16.
- Translating it from the catalog alone: 27 of its 60 strings; the other 33 are short forms of catalog strings, now derived in `catalog_supplement.py`. Lab notebook, 2026-10-16.
- Treating it as a fix rather than a cycle: ruled out, it is an uncatalogued config bin, and prime-only, so the append had to learn to offer it (`transform.config`). Lab notebook, 2026-10-16.
- The control build on the phone (Infinix X6853, 1.6.0.1): startup, the Diamond Frenzy Encyclopedia tabs, a full match and the achievement titles pass. Lab notebook, 2026-10-16.
- The cycle build's package `1` on the phone: Starting Lineup draws empty, and the control's package `1` brings it back; withdrawn. Lab notebook, 2026-10-16.

### Still owed

The control build has been pushed and watched only in part: startup, the Encyclopedia and a full match
pass, but the 1.6.0.1 supplement's own screens, the weekly leaderboards and King of Kings, have not been
looked at.

## [S1] Problem

The Starting Lineup grid is the one Diamond Frenzy screen that stays Chinese after a full 1.6.0.1 build.
The strings it draws come from a config bin that no catalog table and no allowlisted pass reaches.

## [S2] Design

Three code changes plus one cycle. On a normal run all three are inert: `SAFE_ASSETS` stays empty and
the asset is only offered when `--cycle-asset 9E45602F` names it.

1. **Queue it.** Add `0x9E45602F1857539D` to `extra_text.CANDIDATE_ASSETS`, recording the measurement
   (60 distinct, 27 official, 60 with the derived forms, 252 fields; lab notebook, 2026-10-16). `resolve_candidates` then accepts it.
2. **Let the append offer an enabled config bin.** `make_transform` exposes `transform.config`, the
   `SAFE_ASSETS | candidates` set it already decides against. `add_prime_only` adds that set to
   `wanted`. With no cycle and an empty allowlist, the set is empty, so a normal run stages
   byte-identical packages. The `AGENTS.md` line that says the append "never asks about the
   `SAFE_ASSETS` config assets" changes in the same commit.
3. **Supply the 33 short forms**, generated in `tools/catalog_supplement.py` from the catalog's own
   longer strings, in English and Indonesian. The file's rules apply: never override a catalog entry,
   and keep markup intact. These entries also help any catalog table that holds the same short form,
   with no cycle needed. `check` must pass with 0 `validate_translation` failures.

### The cycle (one variable: this asset)

The phone also owes a verdict on the 1.6.0.1 supplement build (`docs/lab-notebook.md`, 2026-10-16), so that build
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
   - **Either way:** update this record's Report, `docs/lab-notebook.md` and `docs/translation-progress.md`.

## [S3] Out of Scope

- Resealing the bin's stored checksum. The way to reseal one is not known here (`AGENTS.md`), and
  this cycle measures whether this bin needs it.
- Moving or rebuilding package `1` (`REBUILD_PACKAGES` stays empty).
- The other per-mode encyclopedia copies, if a different mode carries its own covers bin. A pass on this
  one is not evidence for another hash.
