# Translation Progress

The coverage ledger: what the catalog covers, what reaches the phone and by which path, what is
translated outside the catalog, and what is knowingly left Chinese. `AGENTS.md` carries the rules this
state obeys and `docs/features/` the reasoning behind each pass; this file carries the running
counts, so it is the one that moves when coverage moves.

Catalog counts verified 2026-10-01 at `cf1055e`. The per-layer counts are measurements over the override
layer against game data **1.4.0.1**, each recorded with its command in the spec record named beside it.
The phone has since updated to **1.4.0.2**, which changes two assets of package `1` and nothing else
(`prime-only-append.md`, the empty `REBUILD_PACKAGES` run); every count below is unaffected by that, and a re-measurement should use the
phone's own layer, not the 1.4.0.1 dump.

## How progress is counted

Coverage is **the staged text tables, the catalog's textures, one hard-coded Lua label**
(`extra_text.SCRIPT_LABELS`) **and one Lua format edit** (`extra_text.SCRIPT_EDITS`) — nothing else. The `extra_text` config-bin allowlist is empty since
2026-10-05. There is no percentage: the build's own totals for tables, textures and config bins are not
published, so progress is the counts a run prints, and the gap is what the sections below name.

A run reports four numbers through the app's `translate` step, all read from
`device_patch_summary.json`:

| reported | accessor | holds |
|---|---|---|
| text tables | `count_translated` | catalog tables the run applied |
| images | `count_translated` | catalog textures the run applied |
| text tables left in Chinese | `count_untranslated_text` | translated, then not applied — `text_skipped`, `append_skipped` |
| images left in Chinese | `count_untranslated_graphics` | found, then not translated or not added — `graphics_skipped`, `append_skipped` |

The earlier rebuild run (`prime-only-append.md`, `run-t4`) printed **392 text tables and 395 images
across 6 packages**, with `text_skipped`, `graphics_skipped` and `append_skipped` all empty. That is the
run `README.md` means by "a run applies all 395". A patch of that shape was put on the phone on
2026-10-02, where the game launched under it and read English; a 1.4.0.1-staged build pushed onto that same
phone stalled it at 0% and was repaired away by the game, which is why the layer's version is now a
pre-flight check (`docs/runbooks/device-cycle.md`).

`REBUILD_PACKAGES` is now empty, so no package is laid out again and `QtsVFS.dll` has no caller in a
normal run, the text pass is gated to the catalog's tables, and the append needs only the pulled APK,
not the builder (all three in `prime-only-append.md`), so a run given the APK and no DLL stages
byte-identical packages. The latest full run, staged from the fresh 1.4.0.2 snapshot and
device-verified on 2026-10-03, reports **391 text tables and 395 images across the same 6 packages** — one
table short of that rebuild, because the append's encoder cannot store `3A70308AAF6F18F8`, which
`append_skipped` counts as staying Chinese.

The first successful full Android/Shizuku run on 2026-10-05, using the Xiaomi Android 12's live **1.4.0.2** data, confirms the same counts:

| Android live result | Count |
|---|---:|
| Text tables applied | 391 |
| Textures applied | 395 |
| Text tables skipped | 1 |
| Textures skipped | 0 |
| Distinct patched packages | 6 |

The skip is one of package `1`'s 298 prime-only tables refused by the append encoder; `text_skipped` and `graphics_skipped` are empty, and `append_skipped` carries one text asset. The completed journal verifies the applied payload and restored normal APK, with no dirty packages or pending mutation. No candidate assets were enabled. This confirms existing coverage through the Android pipeline; it does not add catalog coverage or complete the watched-screen checklist. Session and summary evidence: `artifacts/android-live-patch-success-20261005.json`, recorded in `android-shizuku-patcher.md`.

### 2026-10-05: three device bugs fixed, counts moved

The Indonesian device report (`docs/lab-notebook.md`, 2026-10-05) moved every count. Staged from the phone's own
1.4.0.2 layer with its APK, device-verified on the Xiaomi:

| result | English | Indonesian |
|---|---:|---:|
| Text tables applied (`count_translated`) | 388 | 388 |
| Textures applied | **398** | **398** |
| Text tables left in Chinese | 1 | 1 |
| Textures left in Chinese | 0 | 0 |

- **+3 textures:** the three catalog edits no layer carries under their own hash are reached through their
  cards' device revisions (`mobile_graphics.DEVICE_REVISIONS`), which fixed the Armed Power band.
- **−4 text assets:** the `extra_text` allowlist was emptied. The rule pages hid the Announcement header,
  and the nicknames / display-text table / compliments caused the post-match QTS-failure popup.
- **+1 text asset:** the Effect Card filter's hard-coded `通用` (`SCRIPT_LABELS`, package `10`'s Lua),
  appended from the APK, so the count is 79 in place + 11 relocated + 297 appended in package `1` + 1
  appended in package `10`.

### 2026-10-10: an in-game update left 1 092 strings Chinese, now in the catalog

The phone (Xiaomi M2007J3SG, data still reporting **1.5.0.1**) took an in-game update that rewrote card and
skill texts and added the tiered achievements, the weekly leaderboard titles, the Line Puppy Sky Screen
Prayer, King-rank Diamond rewards, Ace Duel support dividends and the King of Kings sub-account rules. A scan
of the pulled layer's catalog tables (`Catalog.lookup` misses with Chinese in the source) found **1 673
records, 1 092 distinct strings, in 60 tables**, all in package `1` and none in the APK's prime-only tables;
the 2026-10-03 snapshot had 129. They are added to both catalogs by
`tools/research/apply_catalog_fixes.py` from `tools/research/catalog_additions.json`: 300 leaderboard titles,
540 tiered names (`<name> I`…`X`, the base name being the catalog's) and 21 `<name>上大分` titles (the
catalog's `<name>这波上大分`) generated by rule, the other 231 translated one by one, every entry accepted by
`validate_translation`. Offline runs over that layer with its
APK, English and Indonesian:

| result | English | Indonesian |
|---|---:|---:|
| records translated (`counts.translated`) | 1 673 | 1 673 |
| records the catalog could not translate (`counts.unknown`) | 0 (was 1 673) | 40 |
| `text_skipped` / `graphics_skipped` | empty | empty |
| `append_skipped` | `3A70308AAF6F18F8` | empty |

The Indonesian 40 are English rows a previous English patch left on that phone (three distinct
`Fleeting` card texts), which no Chinese layer carries. The layer was already patched, so the run's
table and texture totals measure only what that phone still lacked and are not comparable with the counts
above. **Device-verified 2026-10-10:** pushed by the patcher (session `20261010-115042`, 60 tables, 194
images), and the user reports the updated screens read English.

## What the catalog holds

`resources/catalog/` is produced by the PC patcher pipeline; this repo consumes it, so a record is
corrected in this repo's code rather than in the catalog. The one exception is strings a game update
added that the upstream catalog has no entry for: `tools/research/apply_catalog_fixes.py` adds them from
`tools/research/catalog_additions.json`, and re-running it after an upstream re-import puts them back.
The same script rewrites entries upstream carries as garbled machine translation from
`tools/research/catalog_rewrites.json` (582 English, 885 Indonesian entries, 969 keys). It covers all
121 Diamond Frenzy talent texts and a review of the 1,544 card texts (hero, effect, equipment, tactics
and Chessplayer cards, and hero skills), plus keyword-link names (`╪Clash`, `╈Exit`, `╉Afterlife Totem`,
…), "Little Daji", "Guardian's Armor" and Faction for 阵营 wherever they appear. It changes wording
only, so no count below moves.

| what | count | where |
|---|---|---|
| text tables (`catalog.known`) | **499** | `catalog.json.gz` → `table_hashes` |
| texture edits (`catalog.graphics`) | **398** | 324 `.blocks` block patches + 74 `.assets` whole-image replacements |
| distinct Chinese → English strings (`catalog.unique`) | **40 103** | `catalog.json.gz` → `unique`: 39 011 upstream + 1 092 from `catalog_additions.json` |
| review renders | 44 | `previews/` |

The pipeline does not use `unique` exactly as shipped: `tools/terminology.py` gives each keyword one
name as the catalog loads (`docs/features/terminology-table.md`): the default *Steal* (`夺取`) and
*Prepare* (`整备`), replacing the community names Plunder and Readiness and the stray variants. On the
English catalog that rewrites 40 targets to Steal, 9 to Prepare and 1 to Deploy; on the Indonesian one 36, 7
and 1, and it also puts 107 Indonesian series labels in the Indonesian order ("Seri Prepare"). It changes words inside tables that are already counted, so no count below moves.

Before the terminology table, `tools/catalog_supplement.py` adds the strings the game introduced after the catalog
was built, into tables the catalog already covers, and only where `unique` has no entry of its own. Game
data **1.6.0.1** (2026-10-16) left **2073 rows / 1184 distinct strings** of package `1`'s catalog tables
Chinese, against 146 rows on the pristine 1.4.0.2 layer: an achievement-title system with numbered tiers
(167 base titles, translated from the catalog's own names plus a Roman numeral), four weekly leaderboards
ranked 1-100, King of Kings, the Line Puppy event, Ace Duel guessing, and reworded card texts. The
supplement supplies **2314** English / **2313** Indonesian strings (the Indonesian catalog already had one
of the 1.5.0.1 card fixes), every one passing `adaptive.validate_translation`; an offline build of the
pristine 1.6.0.1 dump with the APK then leaves **0** Chinese rows in the catalog's tables, in both
languages, with `text_skipped` empty. It adds rows to tables already counted, so no table count moves.

On 2026-10-17, Chano's live card exposed two missing numeric variants (30/60 damage, where the
catalog has 25/50). Both languages now receive these two supplement entries. A targeted check across
23 text-table copies in the saved override and prime layers translates all 55 occurrences of the
updated descriptions per language. This does not add tables or textures. Yao's English `upgraded`
keyword label now reads `Combine`; Indonesian already used `Combine`. These checks refine the
earlier zero-leftover claim above; current device acceptance remains pending. Evidence is in the
2026-10-17 Chano/Yao entry of `docs/lab-notebook.md`.

On 2026-10-18 the Seer Totem card (先知图腾) showed its *Initiate* skill in Chinese: the game now writes
"己方英雄" (allied heroes) where the catalog's two variants say 【大河流域】. The `{HPtuteng31080:2}` form is
in 11 package-`1` tables of the saved override layer (the `:4` form was not found), and both languages now
receive one supplement entry for it. It adds rows to tables already counted, so no count moves. The same
screen's `出装` (Build) button stays Chinese: it is a package-19 prefab label, which no pass rewrites.

The same day Meng Ya's skill (*Missile Support*) read Chinese: the game now fires 12 missiles, where the
catalog has the 6- and 8-missile forms. The 12-missile form is in 3 package-`1` tables of the override layer
and in none of the prime layer; both languages now receive one supplement entry for it. The card update
announcement (卡牌更新公告) stays Chinese. Its change notes (`初始法力值30→0`, `新增天赋`, ...) are in
neither data layer, and the only match for its title is a Lua comment beside `CLTSTS_NEWS`. That points to
text the server sends. Its 削弱/优化/调整/增强/新增 tags are a package-19 prefab (`073A9BC1840032F3`).

Also on 2026-10-18 the Tide Cycle talent card showed its description in Chinese. The game now opens it with
"战斗开始时" where the catalog has "开战时"; the rest of the sentence is unchanged. Both of the card's
variants (`临时等级100级` and `100级`) are in 11 package-`1` tables of the saved override layer. A sweep of
that layer for the same opening found one more reworded string: Arthur's Templar text now restores 生命值 (HP)
where the catalog's form restores 最大生命值 (Max HP). All three now receive supplement entries in both
languages, reusing the catalog's own English and Indonesian. They add rows to tables already counted, so no
count moves.

The Global Resonance talent card read Chinese for the same reason. The game now grants 星源装备 where the
catalog's form grants 火鹰装备 (Fire Hawk Equipment). The new form is in 10 package-`1` tables of the saved
override layer. Its supplement entry reuses the catalog's Fire Hawk sentence and names the set *Star Source*,
as four of the catalog's five 星源 items do (the fifth reads *Starcore*).

The Event > 万象头条 (Headlines) screen stays Chinese, and no pass can change that. The tab label `万象头条` is
only in the quiz bin `A3B34BE9879BE25B`, which was withdrawn from the allowlist (`extra_text.py`: no game
button, blank encyclopedia). The rest of the screen is in neither data layer: the `领官号福利` tab, the
weekly items (`本周热门棋手`, `强势英雄推荐`, `本周新鲜事儿` and their subtitles) and `向下翻页`. That was checked across
packages 0, 1, 3, 4, 14, 19 and 21 of the saved override layer and package 1 of the prime layer. The screen is the
Gamelet mini-program `weeklydigest4` (`files/Gamelet/program/archive/12539`, issue 04 of 2026.10.13),
whose code holds none of these strings, so the server sends them with each issue.

The Event > 智勇双王 (Twin Kings) screen stays Chinese for the same reasons. It is the gamelet `doubleking`
(`archive/9295`). Its body text (`王者万象棋|未完成`, `暂无段位`, the 最强王者 rule sentence, `双王未达成`) is in neither data layer.
The gamelet fetches it from Tencent's server function (`publicfaas.game.qq.com`, `pdr_appid=9295`), and its title
and badges are PNGs inside the gamelet. The tab label `智勇双王` is in no table a pass translates: the title table
`55EC8FF338904581` holds it as the achievement title (translated *Twin Kings*), and on this screen it matches only
four package-19 prefabs (`0BF1D76F6466CF9D`, `6E4722CF41EA9F3D`, `92287B2520A2B497`, `F8C63032EB91C360`), which no
pass rewrites.

Yao's old English description can now be corrected by rerunning with the updated patcher.
`catalog_updates` adds exact old-to-current mappings for 22 measured rows in 11 existing catalog
tables. This changes installed wording without clearing game data or adding asset coverage.

`.blocks` and `.assets` are the two porting *kinds*, not text versus texture: every payload file in the
catalog directory is a texture, and all 398 of them are in `catalog.graphics`.

`catalog.json.gz` also carries the catalog's own history: `english_updates` (29 750 keys, each holding
the previous and the new official English), and `resources/catalog/english_sibling_audit.json` records
the merge behind it — 12 605 exact-key updates, 1 899 reviewed English-only updates, and no ambiguous key
or unreadable asset preserved.

Re-measure with no phone and no dump:

```bat
set PYTHONPATH=tools;resources\runtime
.venv\Scripts\python.exe -c "from pathlib import Path; from wxq_patch import adaptive; c = adaptive.load_catalog(Path('resources/catalog')); print(len(c.known), len(c.graphics), len(c.unique))"
```

## What reaches the phone

The game reads **override** (downloaded) first and falls back to **prime** (inside the APK), and every
pass here writes into override. An asset that exists only in prime is therefore unreachable by an
in-place edit, which is what the **append** pass closes: it adds records to the override copy without
changing the container's shape, so it needs the APK and nothing else. `rebuild_package` reaches the same
content by laying the package out whole, which nothing asks for today (`REBUILD_PACKAGES` is empty) and
which only Tencent's builder can do. `prime_probe.py` censuses both layers; a search for a missing asset
has to run over both.

### Textures — 398 of 398 applied

| where the edit exists | count | applied by |
|---|---|---|
| override layer only | 322 | texture pass, in place |
| both layers | 1 | whichever pass owns its package — once |
| prime only — package `1050016095` | 71 | append — `qts_insert.add_assets` |
| prime only — package `21` | 1 | append — `qts_insert.add_assets` |
| neither layer under its own hash — package `15`, through `DEVICE_REVISIONS` | 3 | texture pass, in place: `197CC5393D16E3CB`, `884E0B4581F47CF7`, `89C771ECFCDC7FBE` |
| **applied** | **398** | |

The one appended edit is `7B4CC5DF48336D2D`, the wide Central Plains panel the Card Info view draws. Its
package `21` stays out of `REBUILD_PACKAGES` on purpose: a rebuild applies it too and the game mounts it,
but on the phone the Factionless hero Yixing then draws as the game's grey placeholder. Append adds one
record to `21`'s override copy and leaves the container's shape alone.

One of those 398 is recovered rather than ported: `C9E29F61B9E73713` (Three Kingdoms) is 592x816 in the
catalog and 592x824 on the device, so the pass aligns the two images and copies only the label across
(`splice_label`). It counts as applied, but as a correctness fix: which screen draws it is not
established, so it is not evidence of anything visible.

"Applied" also never said *where*. The Career atlas `13C19E4E4486B31C` counted as one applied texture
from the day its edit shipped while 9 of its 13 English labels landed on other sprites: the catalog drew
the patch on the PC atlas layout and the port wrote it at the PC offsets (`我的棋手` stayed Chinese on the
Career screen). Since 2026-10-10 a regioned atlas is placed by the device's own sprite table, the sprites
the old port overwrote are redrawn, and the count is unchanged: still one texture, now with its 13
labels at their own sprites plus the two this repo draws (*Translated outside the catalog*).
**Device-verified 2026-10-10 on the Career screen**: pushed alone (package `19`, one texture, session
`20261010-151438`), and the user reports the screen reads right. Other screens drawing the moved
sprites were not walked.

### Text — the staged tables plus what the append takes out of package `1`'s prime layer

Text applies four ways: staged in place (`full`, falling back to `fit-only`), relocated to the end of the
shard when a longer table has no room (`relocated-text`), rewritten outside the catalog by the `extra-text`
pass, and carried out of the APK by the append (`added-from-apk`, `qts_insert.add_assets`). The last two
are what the prime layer needs; two packages carry text there, and one carries a texture:

| package | prime entries | override entries | prime only | of those, catalog tables | translate |
|---|---|---|---|---|---|
| `1` | 2873 (45.9 MB) | 403 (29.3 MB) | 2492 | 408 | **298** offered, 297 applied — 51 095 records |
| `1050016095` | 608 (5.2 MB) | 2 (0.3 MB) | 606 | 0 | 0 — but 71 catalog textures |

On this data a run reports **387 text tables for package `1`**, one of which stays Chinese: 79 assets
staged in place, 11 relocated and 297 appended out of the APK (until 2026-10-05 it was 391, with 4 more
rewritten by the `extra-text` pass); package `10`'s appended Lua label makes the run's total 388. The
chessplayer names, skills, talents and secret skills are in that 297 — the screens that draw them read
prime, so no override-only path could reach them. Package `1050016095`'s 71 prime-only textures go the
same way and are counted as images.

The refused table is `3A70308AAF6F18F8`, a 60-byte table whose LZ4 block lands exactly on its own length,
which this format cannot tell apart from a *stored* chunk; it is named in the log and counted in
`append_skipped`. The pass stages **the catalog's tables and nothing else**: `adaptive.scan` recognizes a
localization table by shape and can resolve one the catalog has no record for, and two such tables in
package `1` — `3914DBBFECD1E54D` and `63922EF4D4C86526` — were being staged by it while the rebuild path
it replaced never would have. `build_device_patch._drop_uncatalogued_tables` drops them, so a normal run
translates nothing outside the catalog; see *Knowingly left Chinese* for the two.

Relocation is why the stager no longer loses these: it used to drop 11 of package `1`'s 92 translated
override tables at the container, every one a chessplayer skill, talent or secret-skill table.

Re-measure:

```bat
.venv\Scripts\python.exe tools\research\prime_probe.py --apk "dist\HOK ACE Patcher Data\installed.apk" ^
    --game <dump> --packages 1 1050016095 21
.venv\Scripts\python.exe tools\research\check_graphics.py --game <dump> --table
```

`check_graphics.py` sees the override layer only; the APK's `assets/bin/Data/Package/builtin/` is
`prime_probe.py`'s half of the census.

## Translated outside the catalog

`extra_text` (over `pb_text` and `unity_text`) translates display strings the catalog has no
localization table for. Its config-asset allowlist, `SAFE_ASSETS`, is device-gated and **empty**. The four
assets it held until 2026-10-05 were each withdrawn after a device cycle:

| asset | what it is | why it was withdrawn |
|---|---|---|
| `2D1113B0AD51A562` | ~11 000 AI opponent nicknames (pinyin) | with these three rewritten, every match ends in the `/未翻译UI/QTSFailureTips` popup |
| `A1987F488164E53A` | display-text table (`{id, text, #key#}`) | same cycle; not bisected |
| `1C8F7FFF7BDEF14D` | post-match compliments | same cycle; not bisected |
| `B5D856BFDF22400D` | rule pages (`ResHelpSystemCfgDataBin`) | the Announcement screen loses its back arrow and title |

What the pass still writes is `SCRIPT_LABELS`: exact literals in Lua UI scripts, today one, the Effect
Card filter's hard-coded `通用` in `9BD30F0DF58B1FBF` (package `10`, prime-only, so it is appended). It
reads **General** on the phone and survived a full match without the popup. Beside it, `SCRIPT_EDITS`
holds exact literal edits to a script's own formatting, today one: `PVPRankDataClass`
(`6CB505C6553141B4`, package `10`) joins a rank's tier and numeral with `"%s%s"`, which read
"Supreme StarIII" in the lobby; the edit makes both rank-title formats `"%s %s"` ("Supreme Star III").
Device-verified on 1.6.0.1 on 2026-10-18: the lobby reads "Supreme Star III" and its tabs "Ranking  Match".

Three narrower gates sit beside the allowlist in `tools/extra_text.py`:

- `OFFICIAL_FIXES` overrides one catalog translation that reads a name as a word (`蝉儿` → `Chan'er`).
- `SKIPPED_STRINGS` guards `空`, a skill-config value the client reads back rather than displays.
- `UNITY_TEXT_PACKAGES` is **empty** — package `19`'s Unity prefab labels stay untouched — and
  `EXCLUDED_PACKAGES` is `{"10", "14"}`, the skill editor's labels and the gameplay scripts, where the
  Chinese is logic rather than display text.

Two images are this repo's own, not the catalog's: on the Career atlas `13C19E4E4486B31C`,
`Image_410780920` `我的皮肤` → **MY SKINS** (no catalog entry) and `Image_920603129` `总盈利` → **TOTAL
PROFIT** (the text table's "Total profit"), in `resources/sprites/` (`mobile_graphics.ATLAS_LABELS`). They
are drawn into a texture the catalog already edits, so they add no texture to the count. Every language
uses them. Device-verified on the Career screen, 2026-10-10 (English).

Resource tokens `{Energy}`, `{LordExp}` and `{LordHp}` are expanded to `Energy`, `Chessplayer EXP` and
`Chessplayer HP` in the staged replacements and in the assets the rebuild and extra-text passes
translate. The catalog keeps the tokens, because `translate_table` requires matching placeholders.

### Withdrawn and untried

Ten assets were enabled, watched on a phone and withdrawn, each with the screen that showed the damage;
the hashes and symptoms are beside the allowlist. Task names `5214339F97C419ED` make a tournament replay
SIGSEGV, the four chessplayer-skill assets remove the skill-description button, and mail / quiz /
"not open yet" notices remove the game button after pressing start and blank the encyclopedia. Both sets
stay out until a device cycle says otherwise.

Fifteen further assets are named there as *not tried*. They were resolved to full hashes and measured
against the override layer (`tools/research/extra_text_candidates.py`, `extra-text-cycles.md`), and the
measurement says the fifteen are not fifteen equal opportunities. Four are display-label tables the
catalog mostly or entirely covers, worth a cycle: `63922EF4D4C86526` 3 of 3 strings
(Transmog / Treasure Hunt / Limited Time), `4CEF98BEC79CB48C` 4 of 12, `7E3F57D727FA8625` 1 of 1 (Props)
and `3914DBBFECD1E54D` 1 of 1 (Highlight Expression). The other eleven are step, buff, nickname and damage
**identifiers** the catalog reaches 1.5-9% of — `8B5C239421E23186` is 283 guide step names
(`S1 lineup - use button`), `9E141D556DA884E7` 596 guide triggers, `C11D0D1498204926` 587 buff
definitions, `87C2793FEEDCA60D` 678 nickname parts, the three damage tables 3 of 49-53 each with the rest
designer shorthand, `41974B124E0053E0` 15 of 25, `A07BC11BA94A5969` 5 of 10, `14DEEB2E14F20E3C` 2 of 3,
and `3F4DD9B1D383FD83`, which is reachable but in package `4`, the package the note withdrew. The whole
set is about **131 strings, of which the four label tables are 9**, so those four are the cycles worth
running and the rest wait until a cycle says the class is safe.

A sixteenth candidate joined the queue on 2026-10-16: `9E45602F1857539D`, the card-pack covers behind
Encyclopedia → Diamond Frenzy → Starting Lineup (the `逆天改命卡包` header and the hero label under every
cover). It is prime-only, so it reaches the phone through the append, which now offers a config bin a
cycle enabled (`transform.config`). The catalog translates 27 of its 60 strings; the other 33 are short
forms of its own longer strings that `catalog_supplement.derived` generates, so a cycle would translate
all 60. **Withdrawn the same day:** appended, it empties the Starting Lineup grid; the control without it
draws the grid (`docs/features/card-pack-covers-cycle.md`).

A cycle is now one variable by construction: `--cycle-asset <hash>` enables exactly one queued candidate,
the run records it in `device_patch_summary.json`'s `cycle_assets`, and the hash joins `SAFE_ASSETS` only
once a cycle has looked at the screen it feeds. Four cycles were built offline; none has a verdict. A
cycle must now also watch a match end and the Announcement screen, which is what the 2026-10-01 verdicts
missed.

The **Talent Card grid regression is fixed and device-verified on 2026-10-03**. The full
4064-row English dictionary keeps the game's original 307,200-byte chunk size and uses a measured
native key for its added second chunk. Grid names resolve again, including `Arena Tiger`; its
detail pane and the Hero, Effect and Equipment tabs also work in the full English patch. Longer
tile names still use the client's normal ellipsis. Rerunning the updated patcher repairs an older
already-English copy. Counts remain **391 text tables and 395 applied textures**, with the one
known append refusal below. Evidence and the withdrawn impossibility verdict are recorded in
`docs/features/prime-only-append.md`'s Talent Card sections.

## Bahasa Indonesia

`resources/catalog_id/` holds the Indonesian catalog (`docs/features/indonesian-language.md`). It has
the same 499 tables and 398 graphics entries as the English one, so its coverage counts are the English
counts, and it carries the same 2026-10-10 update strings (1 089 added; its own 1.5.0.1 fixes already held
the other three). An offline run against the pristine 1.4.0.2 snapshot and APK (2026-10-05), and the same counts from
the build pushed onto the Xiaomi M2007J3SG that day, where the game launched and the lobby read Indonesian
with MULAI GAME on its start button (`indonesian-language.md`, *Device cycle*):

| Indonesian offline result | Count |
|---|---:|
| Text tables applied | 388 (391 before 2026-10-05's withdrawals) |
| Textures applied | 398 (395 before the device revisions) |
| Text tables skipped | 1 (`0196F0E230EC1C70`, the append encoder's refusal) |
| Textures skipped | 0 |
| Textures re-drawn in Indonesian | 2 (`863114A42F12EF76`, `C9F49510F2F67402`: the lobby's START GAME → MULAI GAME) |

The other 396 applied textures carry the English edit. Two gaps are specific to the language:

- **Game-shipped English stays English.** The catalog translates Chinese sources and re-targets only the
  29 750 `english_updates` rows the English catalog had, so 20 228 of the 324 905 records in the staged
  tables (6%) are English the game itself ships, left as it is — mostly package `1`'s prime-only tables.
  Closing it needs `english_updates` rows in the catalog.
- **Switching an already-translated install changes no text.** The Indonesian catalog over the 387
  English-staged tables changes none of them; only the re-drawn textures would switch. Clear the game's
  data first, as for any newer translation build.

## Knowingly left Chinese

- **Two tables in package `1` the catalog has no record for**, which a normal run no longer stages:
  `3914DBBFECD1E54D` (`高光表情` → Highlight Expression) and `63922EF4D4C86526` (`幻化`/`夺宝`/`限时` →
  Transmog / Treasure Hunt / Limited Time). Both sit in `extra_text.CANDIDATE_ASSETS`. `3914DBBFECD1E54D`
  **cannot be cycled at all**: the only asset in the game's 277 packages that references its key is a
  日月行者 draw-type row windowed 2025-09-10 to 2025-10-10, so no live screen can draw it. `63922EF4D4C86526`
  is referenced with no date window, so a cycle for it is possible.
- **The Announcement screen's notices** (patch notes such as `10月8日版本更新v1.5.1`, and the `谨防诈骗` /
  `处罚公告` tabs). Tencent's server sends them at run time: the text is in no package of either layer, and
  the only local trace is `Cache/News/NewsCenterAllNews.pb`, an index of titles and URLs.
- **The card encyclopedia's Special Notes** for Inheritance and Legacy (`每局游戏，每名玩家通过效果锦囊获得的
  <b>传承</b>不会超过2张。` and the `遗志` / 1 note). They are inline text in the eleven per-mode card config
  bins (`41B38BE39A60C211` and its siblings, ~1 MB each, the only two real Chinese strings in them), not refs
  into a dictionary, so only rewriting the bin would change them, and a rewritten card config bin empties the
  encyclopedia grid (the reseal problem in `AGENTS.md`). Present in the 1.4.0.2 layer too; not an update
  regression.
- **The Starting Lineup card-pack covers** (`9E45602F1857539D`, prime-only config bin): the section
  header and the hero labels under each cover. Its device cycle was withdrawn on 2026-10-16: the rewritten
  bin empties the grid, the reseal problem the other encyclopedia withdrawals hit. The side panel's pack
  name is already English.
- The one catalog table the append's encoder cannot store: `3A70308AAF6F18F8`, a 60-byte table whose LZ4
  block lands exactly on its own length, which this format cannot tell apart from a *stored* chunk.
- What the four withdrawn `extra_text` assets used to translate: the ~11 000 AI opponent nicknames (now
  Chinese again), the display-text table, the post-match compliments and the rule pages.
- Package `19`'s Unity prefab labels (the lobby hangs; only the faction names, rewritten, crash at start
  with "stack corruption detected"), and the chessplayer definition `A8BC70BB87700709` field 37 (lobby
  loading stalls even with every reference renamed alongside it).
- Package `15`: 3990 textures, 1994 of them card-shaped, and the catalog's 299 entries at that shape are
  the hero cards. The rest carry a type word or a card name on the bottom band and are not catalogued.
  Counted exactly: package `15` holds **1695** entries the catalog does not cover at the hero-card
  geometry (404x564, ASTC 4x4, 227 856 B), and they are the Talent, skill and effect cards — decoding
  two of them shows `技能` beside an already-English `SKILL` (`000847DC117D3C4E`) and a `TALENT` card whose
  band reads `钻石狂澜` (`0143B73B5071A289`). The English for those names is in `catalog.unique` and, in
  several, already drawn in the art, so nothing is missing but the *rendering*: this is the largest
  visible gap left and it needs a pass that draws text in the band's own font, colour and position,
  because no catalog payload exists to copy. Nothing in this repo draws text.
- The Career atlas's round `胜利` / `失败` badges (`13C19E4E4486B31C`, around 760,150 and 235,210; their
  sprite names are not looked up). The catalog has no edit for them and this repo draws none.
- The `国服` badge on the "National server Chess Player" avatar frame (`国服骑手头像框`): no catalog edit,
  texture not located.
- Every texture outside `resources/catalog/` (bar the two Career labels above) and every text table outside
  the staged packages.
- The prime-only remainder no catalog entry covers at all: **2084** of package `1`'s 2492 prime-only
  assets and **535** of package `1050016095`'s 606. This is the honest measure of what is not merely
  untranslated but uncatalogued, and it is what a future catalog import would have to grow into.

## Keeping this file true

Update it in the same change as the work when any of these moves a count:

- the catalog is re-imported — the four numbers in *What the catalog holds* change together;
- a pass gains or loses a translated asset kind, or a package enters or leaves `REBUILD_PACKAGES`;
- a device cycle adds or withdraws an `extra_text` allowlist entry;
- a run comes back with `text_skipped`, `graphics_skipped` or `append_skipped` non-empty, which moves a
  count out of the applied column.

Take the numbers from the run's own summary and from the record in `docs/features/`; never from
memory. Where a number here disagrees with a run, the run is right and this file is stale.
