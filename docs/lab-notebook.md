# Lab notebook — HOK ACE Mobile English Patcher

This notebook is the single source for raw measurements and device verdicts. Other docs cite its
entries by date (for example "lab notebook, 2026-10-05") instead of copying the numbers; a feature
record carries the reasoning, this file carries the evidence. Topic sections come first, dated
entries after.

Measured evidence for this repo: what went on a phone, what the phone did, and which claim was withdrawn and
why. `AGENTS.md` carries the rules that always apply; **where the two disagree, `AGENTS.md` wins**. This file
is the record behind those rules, including the attempts that failed.

Distilled 2026-10-03 from this project's MiMoCode memory (`projects/be3989bb-…`, 719 lines, last written
2026-10-01), reordered by subject. Dates in parentheses are when the measurement was made. Device of record
throughout: **`f15a72e` / Xiaomi M2007J3SG, Android 12 / MIUI 14**; game data **1.4.0.1** unless stated.

| § | | § | |
|---|---|---|---|
| 1 | Reading a crash | 8 | Why package 21 is not rebuilt |
| 2 | Startup SIGBUS/SIGSEGV: two sufficient causes | 9 | The prime rebuild and the append path |
| 3 | The debuggable APK that stays installed | 10 | Offline tooling |
| 4 | The two data layers | 11 | Operating discipline |
| 5 | The `extra_text` allowlist | 12 | Machine and housekeeping facts |
| 6 | Texture coverage | 13 | Superseded claims |
| 7 | Text staging: the drop loop and relocation | | |

## 1. Reading a crash

The game suppresses tombstones, so logcat is not where a crash is answered.

- `adb shell dumpsys activity exit-info com.tencent.tmgp.osgame` is the tool: `reason=2 (SIGNALED)` with
  `status=11` (SIGSEGV) or `7` (SIGBUS), plus `pss` — 1.2–1.3 GB in the replay crash.
- logcat says only `WIN DEATH` + `has died: fg TOP`; the `crash` buffer is empty and dropbox has no
  `data_app_crash` for the package.
- `Cache/Logs/*.logcompr` is encrypted. `bqLog/ccs_log/normal1.log` is plain text and readable with plain
  adb, no `run-as`, under `/sdcard/Android/data/com.tencent.tmgp.osgame/files/` — but it is the bq/ccs
  **network** log: it ends mid-ping at each crash and holds no stack. Same tree: `TGPA/` (anti-cheat) and
  `Cache/Replay/<matchid>_<uid>_200_<build>_<date>.record.<pid>.lock`, one per watched match.
- The client's `BrokenList.db` and `QtsVFS.log` are readable while the debuggable access APK is installed and
  say whether it could read the files at all. Check that before assuming corruption.
- **Launching with the network off is a poor diagnostic**: it also makes TPGA anti-cheat quit early
  (`cloud.tgpa.qq.com` fails to resolve), which looks like a crash but is not one.
- `pkgHash` is **not** content-derived — identical before and after reverting a 68 MB shard change — so it
  cannot be used as a content-integrity check. A patched package does mount as an override:
  `MountPackage 1, override, … pkgHash:<new> basePkgHash:<old>`; untouched packages mount with
  `pkgHash == basePkgHash`.
- `md5sum` over `run-as` does not work on this build (toybox has none); use `ls -l` sizes.

## 2. Startup SIGBUS/SIGSEGV: two sufficient causes

Force-close ~10 s into startup, before the login screen, `signal 7 (Bus error)` or `signal 11
(Segmentation fault)`. **Two unrelated causes carry the same signature**, so a startup crash is not by
itself evidence about the patch — check `pkgFlags` first.

### Cause A — an incomplete game-data set (2026-09-30)

The data set was caught mid-update, and Tencent's GCloud updater reacted with a same-version "cures" repair
(`server.json`: `from_version` 1.4.0.1 → `to_version` 1.4.0.1, `cfilesize` 9032772, `cmd5`
`cd4f042483e9215e376b268fd147b7b6`), faulting while applying it. A fresh data set is **2.86 GB**; the broken
one was **2.12 GB** (~700 MB of packages missing). The game had updated 1.3.0.4 → 1.4.0.1 at ~08:32; the
08:39 patch run pulled a 229 MB tar mid-update and was killed, and the 09:26 run patched the incomplete set.

**Resolution, verified on device:** `pm clear com.tencent.tmgp.osgame` → let the game re-download to the
login screen → run the patcher. Result: 81 text tables + 322 textures staged, the restore installed the
non-debuggable APK, and the game ran stable past 3 minutes at an **English** login screen ("Scan to login",
"WeChat", "QQ"). The patch *is* compatible with 1.4.0.1 — but only on a complete, consistent set.

Proof the translation was not the cause: with packages `1`, `15`, `19`, `20` restored byte-for-byte to
pre-patch state the crash was unchanged. Only two things ever changed the outcome: clearing the data, and
(unreliably) launching with the network off.

### Cause B — a debuggable APK, on pristine data (2026-09-30, resolved 22:20)

On *complete* pristine 1.4.0.1 data a debuggable APK **alone** reproduces it: `signal 7 (Bus error)` ~14 s
in, with **no** `MountPackage … override` line — the patch was never reached before the fault. The same data
on the normal build runs. "In the 09:26 episode the non-debuggable APK did not help" does not contradict
this — the data was still incomplete then.

| package data | APK | result |
|---|---|---|
| pristine download | debuggable | **died**, `signal 7`, ~14 s in, **no** override mount |
| pristine download | normal | **ran** past 90 s, `MountPackage 1 / 1050016095, override => succeed!` |
| patched by this run | normal | **ran**, same pid past 90 s, `BulkExportFromPackageJob done, result=1, errorCode=0` |

`GCloud CheckLocalPatchDiffFiles blModified = [1]` and `GetAllSubpatchInfo ArraySize:[552]` appear on the
unpatched control too — updater noise, not a crash signature. **"Only prime mounts, no override mount" is the
debuggable-build signature.**

### Ruled out along the way

- The `Watchdog/*` wipe in `push_translation` is not the trigger: patched packages plus an intact,
  game-rebuilt Watchdog still crashed. Clearing `Cache/iips_download` + `Cache/Update` did not help either.
- QtsVFS is happy throughout: every package mounts, `ScanJob done … result=1, errorCode=0`,
  `Watchdog/BrokenList.db` stays empty.
- Not corruption in general: all four bug sessions (§5) logged `[after]brokenFiles count 0` and
  `ScanJob … result=1, errorCode=0` — the client reads every file and then behaves differently.

## 3. The debuggable APK that stays installed

**Fixed in `9be8adb`.** Before that, `prepare_normal_apk` adopted the *installed* APK whenever its signature
already matched (`apk_tools.signed_with`), so a run killed after `install(access.apk)` but before the restore
made every later run adopt that debuggable build and re-install it permanently. **It is not just untidy: it
kills the game** (§2 Cause B), so an interrupted run presents as "the patch broke the game" — which is how
2026-09-30's two hours were spent.

The fix keeps the cached APK while the phone runs the access APK it built (matched by size against
`access.apk`), and clears the flag out of a cache an older run already poisoned. Only the debug flag
separates that file from the game's own APK, so clearing it rebuilds the original: `is_debuggable(manifest)`
is exact, because `patch()` leaves a manifest byte-identical only when it already holds the value asked for.

Verified in place: `prepare_normal_apk` with the access APK installed logged "the phone is still running the
temporary access APK; using the cached game APK", installed 2,026,631,888 B, and `pkgFlags` had no
`DEBUGGABLE`. The rebuilt APK is 29 bytes larger because the now-unused `debuggable` string stays in the
string pool — harmless. The repair is now automatic rather than a manual 2 GB rebuild.

Two habits that would have prevented the detour: **never stub out `ui.log` when driving `Patcher`
headlessly** (a failed restore is reported only there — a failure announced only through a callback can be
swallowed by whatever drives the code, and the harness that stubs it is usually written by the same person
who then trusts the run), and check `pkgFlags` after any scripted run.

## 4. The two data layers

The game reads override first and falls back to prime:

| layer | where | contents |
|---|---|---|
| prime (baked into the APK) | `assets/bin/Data/Package/builtin/<id>/` | every asset as the APK was built |
| override (downloaded) | `files/QtsVFSCache/packages/<id>/` | only the assets that changed since that build |

`pull_game_data` (`app/patcher_core.py`) pulls `files/QtsVFSCache/packages` + `Watchdog` and nothing else,
and the stager writes only into that layer. **A prime-only asset can never be translated by the in-place
path alone** — that is the real reason the Chessplayer screen showed Chinese names, not the drop loop (§7).

Measured on this machine on 1.4.0.1 (`tools/research/prime_probe.py`; dump
`dist/HOK ACE Patcher Data/sessions/20260930-102304/game`, APK `dist/HOK ACE Patcher Data/installed.apk` —
182 prime package dirs, 364 entries):

| package | prime | override | shared | prime-only |
|---|---|---|---|---|
| `1` | 2873 assets / 141.6 MB | 401 / 98.7 MB (403 later) | 379 (381) | 2494 (2492) |
| `1050016095` | 608 | 2 | 2 | 606 |

Override-only on package `1`: 22 assets. The prime shard carries the chessplayer names in bulk (瑶妹 ×62,
白歌 ×41, 姜导 ×61, 常小娥 ×14 …), which is why every name had English records in the *staged override*
tables and the screen still showed Chinese. Of package `1`'s 2492 prime-only assets, **408 are catalog tables
and 298 translate (51095 records)** — 0 refused, 110 already English. Of `1050016095`'s 606, **71 are catalog
textures** (plus 1 shared).

**Before calling any asset unreachable, count the APK's `assets/bin/Data/Package/builtin/` too.** An earlier
count of 75 missing textures was measured against the downloaded dump alone; `tools/research/prime_probe.py`
is the census that covers both layers.

## 5. The `extra_text` allowlist

Four UI failures reported on device after login (2026-09-30): (1) no game button after pressing start,
(2) encyclopedia blank, (3) chessplayer skill-description button gone, (4) forced close while spectating.

They were **not** the updater (`total_need_download_size = 0 KB`), **not** the textures (every texture package
reverted to pristine left all four), **not** the catalog tables (disabling every `extra_text` asset fixed 1–3
while 388 tables stayed English), and **not** corruption (§2). A translated string is being used as data. The
culprit pass is **`extra_text`/`pb_text`**, which rewrites CJK strings inside the 14 non-table config assets.

### Symptoms 1–3: the display assets

Bisected with per-symptom reports, which is what made it tractable. Groups 1+2 and 3+4 are independent, so
one build can halve both.

| verdict | assets |
|---|---|
| **causes 3** (skill button) | the four `# chessplayer skills`: `10271B050169A7B7`, `0FDA07B7C51E4AC5`, `DEE91C1DE999F3AF`, `D9A68213BB843F61` |
| **causes 1+2** (game button, encyclopedia) | mail `5B7E509D10BD722F`, quiz `A3B34BE9879BE25B`, notices `721918D44EDAB146` |
| **safe to keep** | display-text table `A1987F488164E53A` (holds `棋手技能`/`免控`/`无敌`/`能量`), compliments `1C8F7FFF7BDEF14D`, rule pages `B5D856BFDF22400D`, bot names `2D1113B0AD51A562`, the two package-4 assets |

Why the pass is risky at all — a record of a chessplayer-skill asset: `{.2 id, .4 skill id, .6 name ('空' for
a slot with no skill), .7 '空技能', .16 '$/LordSkill_Empty.gl', .21 '领主技能世界观短句' (identical in every
record), .23 '空技能', .29 'ArtHub/Icon/Lord/JiNeng/…'}`. **`pb_text.rewrite` has no field awareness** — it
rewrites every CJK string field it finds — so a shared grouping value like `.21`, or a name the client
matches on, gets replaced along with the labels.

### Symptom 4: the replay crash

Force-close while spectating a **tournament replay**, reproducible every time. Native `SIGSEGV`: `reason=2
(SIGNALED)`, `status=11`, `pss` 1.2–1.3 GB, 2–3½ minutes after launch; each crash lands ~30 s after a
`Cache/Replay/…lock` appears.

Per-cycle reports recovered from the transcript, with the `extra_text` set each build actually rewrote
(measured with `hok_classify.py`, not inferred):

| build | package 1 `extra_text` assets actually rewritten | report |
|---|---|---|
| `nodisplay` (22:51) | `2D1113B0AD51A562` (BOT only) | none recovered |
| `grp5` (23:25) | 4 × skill assets + `A1987F488164E53A` + BOT | **1,2 fixed; 3,4 present** |
| `mix1` (23:38) | 4 × skills + mail + quiz + notices + BOT | **all four present** |
| `safe1` (23:54) | `A1987F488164E53A`, `1C8F7FFF7BDEF14D`, `5214339F97C419ED`, `B5D856BFDF22400D`, BOT | **1,2,3 fixed; 4 present** |

Settled by a **single-variable pair** on device — package 1 pushed from two builds differing only in that
pass, textures and package 4 identical:

| package 1 content | replay |
|---|---|
| 388 tables (90 override + 298 prime-only), no `extra_text` | **works** |
| identical plus the four then-thought-safe `extra_text` assets | **SIGSEGV** |

So the prime rebuild (298 prime-only tables, chessplayer names included, plus the rebuilt container) is *not*
the cause, and neither are the textures. The user's own history agrees: the older patched install had no
`extra_text` pass at all and replays worked there.

Then one asset per cycle, each starting from the last known good (`hok_run.py probe <staged-root>` pushes
package 1 from an arbitrary build with textures and package 4 fixed, so package 1 is the only variable):

| added to the working build | replay |
|---|---|
| `1C8F7FFF7BDEF14D` post-match compliments (13 strings) | works |
| + `A1987F488164E53A` display-text table (474 replacements) | works |
| + `5214339F97C419ED` **task names** | **SIGSEGV** |
| + `B5D856BFDF22400D` rule pages and `2D1113B0AD51A562` pinyin nicknames | works |

**The pass is content-specific, not blanket-unsafe.** Shipping `SAFE_ASSETS` is `{BOT_NAME_ASSETS =
2D1113B0AD51A562} | {A1987F488164E53A, 1C8F7FFF7BDEF14D, B5D856BFDF22400D}` — nicknames, display-text table,
compliments, rule pages. Excluded, each with the screen that condemns it: task names (the replay), the four
chessplayer-skill assets (the skill button), mail/quiz/notices (start button, encyclopedia), both package-4
assets.

### The separate real defect: `write_assets` does not verify its own write

`device_extensions.write_assets` does no read-back check, and package 4's two rewritten assets do **not** read
back in the built output — the index is updated to the new raw size (4,398 / 77,794) while the shard still
yields the original payload (3,748 / 66,175). The same code against a copy of the pristine package works and
persists, so it needs the copy the compiled stager made first. It was not the cause of the four symptoms
(package 4 pristine still showed all four), but it leaves an index and shard that disagree — which is why
package 4 ships pristine and the defect is latent rather than live.

### Method

- For a rebuilt package the pass runs **inline** from `package_rebuild.make_transform`, so an empty
  `build/safe-replacements/` does **not** mean it did nothing. Diff the staged package against the pristine
  one and classify each changed asset as catalog table / catalog texture / `SAFE_ASSETS` / other.
- **"The staged package did not change this asset" does not mean "the asset was disabled."** An enabled asset
  that rewrites nothing looks identical to a disabled one — exactly what `A1987F488164E53A` did in the
  `nodisplay` build, and how four assets got exonerated while being present in every crash. **Only a
  single-variable pair, both sides staged and compared, supports a causal claim.**
- Compare **asset by asset, not file by file**: the rebuilt container is re-laid out on every build, so
  `1.db`/`1_0.db` hashes differ between builds carrying identical content. Across 703 entries: 0 metadata
  differences, 701 byte-identical. The two that differed are the **builder's own bookkeeping** —
  `(qts-exportsetting-node-index).data` / `(qts-remaindir-node-index).data`, holding the **absolute output
  path** (`…\shipped` vs `…\probe-final`). Tencent's builder embeds the build directory in the package:
  inert (every build handed to the user contains it, including the working ones) but it means two rebuilds
  are never byte-identical unless they share an output path.
- Two structural checks came back clean and are not worth repeating: every entry of every built package reads
  back in a **fresh** process (`entries == slots`, no unreadable, no empty) for pristine, noextras, nobot and
  safe1 alike — so the crash is not an index/shard disagreement — and the four rewritten assets carry the
  same entry shape as the translated tables.
- Two loose ends, not to be re-opened: the four assets `classify` reports as "added other"
  (`5B905F540C9F7046`, `92D3EE5696C9D644`, `AF1FB540A2B8CB52`, `1D13F7315D89BAC3`) are override-index
  entries with no override data — `rebuild_package` reads their bytes from prime and carries them verbatim,
  and `classify` calls any index entry missing from the *slot map* "added" rather than "changed". And
  `2D1113B0AD51A562` being "always kept" by the bisect builder is why BOT stayed in the intersection.
- **A comment saying "verified on device" is only as good as the screens it was verified on.** This pass was
  labelled verified while its own comments already recorded breaking the Card menu and the login screen the
  same way; the note checked as far as "loading reaches Click to Enter Game, the Card menu renders", and the
  four screens the user cared about were never in the sample.
- **Ask for symptoms one at a time.** "All four still broken" cost several extra cycles; the report that split
  #1/#2 from #3/#4 is what ended the search. Symptom names mislead too: four chessplayer-sounding symptoms
  were two unrelated asset groups.

Mail, quiz and notices were only ever tested together, so separating them costs one device cycle each.

## 6. Texture coverage

The catalog holds **398 texture edits**. **323 are present in the downloaded layer and 75 absent**; the APK's
prime layer adds **73** more (72 in prime `1050016095`, 1 in prime `21`), and `C9E29F61B9E73713` is in both.
Union = **395**, so only **three** exist in neither layer — `197CC5393D16E3CB`, `884E0B4581F47CF7`,
`89C771ECFCDC7FBE`, all 404x564 BC7 `.blocks`. The one present-but-not-applied-historically is
`7B4CC5DF48336D2D` (Central Plains' fourth wide panel) in prime package `21`; it reaches the phone by append
(§9). **State the texture count as *applied*, never as *covered*.**

Only 5 packages carry catalog hashes: `1` (text), `15` (299 card textures), `19` (22 UI), `20` (1),
`1050016095` (1).

Census of every package index in a full 2.86 GB dump (277 readable of 278 dirs):

| family | geometry | catalog | on device (downloaded layer) | role |
|---|---|---|---|---|
| grid card art | 404x564 `.blocks` | 302 | 299 | the card, faction ribbon baked in — why the **grid** is English |
| card-info portrait | 592x816 `.assets` | 15 | **1** | the tall card with the "Hero" band |
| card-info landscape | 568x304 `.assets` | 27 | **1** | the wide panel |
| ribbon strip | 568x70 `.assets` | 6 | **0** | the ribbon band on its own, one per faction |
| tab banner | 420x44 `.assets` | 7 | **0** | the ribbon band, tab-sized |
| panels | 384x532 / 568x792 / 582x804 | 20 | **0** | small / tall / wide card panels |

The two downloaded-layer survivors are exactly `BCCC8C957621FA27` (Sunset 568x304, pkg `20`) and
`C9E29F61B9E73713` (Three Kingdoms 592x816 catalog, **592x824** on device, pkg `1050016095`) — precisely why
the user saw English on the **Sunset** card only.

### The Card Info ribbon is the wide 568x304 family, proven by elimination (2026-09-30)

Layout reasoning misleads here: the two views look alike and only the asset ids settle it. An earlier claim
that Card Info renders the `592x816` portrait frame was inferred from layout and is **wrong**.

1. `F72420296646DC5B` is **Fang's card** — a `404x564` hero card, in the catalog (label Central Plains, 11
   `patch_ranges` covering exactly its `label_box`), present in the dump. `render_texture.py`'s before/after
   of that texture is pixel-identical to the user's screenshot in the BEFORE state, artwork and `河洛` ribbon
   both.
2. `english_raw` on it produces **`Central Plains`** in the ribbon, and the *staged* package 15 the patcher
   pushed carries that patched chunk (sha `4574250141e21b67` vs the dump's `c300156c78d09412`) — the pipeline
   is not at fault.
3. The user's screenshot of the **same card's Card Info view still shows `河洛`**.

So Card Info does not draw the card's own texture. Combined with Sunset's Card Info ribbon being **English**
while the device carries no Sunset `592x816`, `384x532`, `568x70` or `420x44` at all, the only
present-and-patched asset left holding a `Sunset` ribbon is `BCCC8C957621FA27` (pkg `20`) — the wide `568x304`
family. The 39 Sunset `404x564` cards are ruled out by Fang's card being patched yet still Chinese in that
view.

`C9E29F61B9E73713` belongs to some **other** surface: translating it is still correct, but it does not fix the
Card Info view and must not be described as doing so.

### The wide-panel id hunt: method, and why a best-match test alone is not enough

Reproducible offline with `tools/research/ribbon_id_hunt.py --game <dump>`.

- The family is 27 catalog entries at 568x304, all `label_box [168, 244, 400, 296]`, all a 172672-byte BC7
  `.assets` payload, and **25 distinct payloads** — four art variants per faction, three for Mecha. Not a set
  of duplicates, so "absent" is a real absence.
- Census over all 174 non-empty package directories (278 dirs; 103 hold only a stub `.db`/`.info`) finds
  **55** assets whose uncompressed size admits a 568x304 texture at any of the six ASTC footprints, or at any
  height inside the 16 px `align_rows` can absorb. Nothing sits at `172672` B or `111264` B, so the 4x4 and
  5x5 exact geometries are absent outright.
- **The metric is calibrated against the one pair known to be genuine.** Re-encoding a catalog payload as
  device ASTC at each footprint and scoring it against its own entry gives the floor a real sibling must
  reach: **0.05 at 4x4, 0.76 at 5x5, 1.02 at 6x6, 1.59 at 8x8, 2.04 at 10x10, 2.45 at 12x12**. A *different*
  family entry scores **~14.3** against the same art, so the family discriminates by an order of magnitude.
  Any threshold test that does not know this floor is guessing.
- Of the 55 candidates exactly one behaves like a member: `BCCC8C957621FA27` (pkg `20`, 43168 B, 568x304@8x8)
  scores **1.09**, inside the floor; the next-closest entry scores 4.30 and is its own catalog payload. Every
  *other* family entry's best device-side match is 10.97 or worse, with the alignment pinned at the ±16 px
  search boundary — a boundary-pinned offset is what a failed match looks like. All 54 decodable candidates
  were rendered and looked at: exactly one is a Card Info panel; the rest are noise, gradients, `COMEBACK` /
  `三星连珠` / `双雄对决` event banners and buttons.
- Two entries, `607814F25B9BBDE0` (Riverlands) and `63918D8465BB8B16` (Central Plains), are returned as "best
  match" for dozens of unrelated textures because they carry the family's least distinctive art. **The margin
  *and* the measured floor are both required.**
- The sweep covers the whole usable search space: `splice_label` aligns the two decodes at the **catalog's
  width**, so a sibling at a different width could not be applied even if one existed, and a difference
  beyond the ±16 px `ALIGNMENT_SEARCH` is not findable by `align_rows` either.

**The negative was superseded the same day.** The hunt censused the *downloaded dump only*: **26 of the 27**
wide panels are in the APK's prime layer under the catalog's own ids (25 in prime `1050016095`,
`7B4CC5DF48336D2D` in prime `21`), and the Sunset panel the hunt found is the only one in the downloaded
layer. The method, the metric and the `0.05..2.45` floor are all still valid — what was wrong is the search
space, not the search.

### What the catalog covers of the card-shaped textures (2026-09-30)

pkg `15` holds **3990** assets, **1994** at exactly `227856` B (`404x564` @ 4x4, one chunk each). The catalog
covers **299** of those; the other **1695** are **Talent / skill / effect cards** — contact sheets of both
sets in `dist/HOK ACE Patcher Data/graphics-diagnosis/sheet_*.png`. The catalogued 299 are hero cards whose
bottom band carries a **faction**; the uncatalogued ones carry a type word (`技能`) or a card name
(`钻石狂潮`). So "the catalog covers the card art" is false in general: it covers hero-card faction ribbons
only, and spot-checking a hero card is the only safe way to claim a view is covered.

### `label_box` is in display order, not payload order

The catalog's `label_box` is top-down like `previews/*.png`, while `mobile_graphics.decode_pc` returns the
payload buffer bottom-up. To index the buffer the rows must be mirrored: `height - box[3] .. height - box[1]`.
Cropping at the raw `label_box` rows returns a blank band; mirroring first returns the text. Getting this
wrong moves the label to the wrong end of the image.

### A device revision can re-cut the art by a block row

`C9E29F61B9E73713` is 592x816 in the catalog but **592x824** on the device — one extra 8px ASTC block row, so
`astc_layout` (which needs an exact width and height) refused it and the card stayed Chinese through several
patch runs. `mobile_graphics.splice_label` now handles this: align the two decodes with the label band
excluded, copy only the `label_box` pixels, re-encode only the touched blocks. Measured for that card:
alignment offset +2, 210 blocks changed in block rows 2..8, everything else identical. It refuses unless the
images genuinely align (`ALIGNMENT_MAX_MEAN` + a dip below the median offset), and returns its input
untouched once the label matches — **without that guard a re-run is not idempotent**, because re-encoding the
same region from a lossy decode perturbs the label's edge blocks.

A size-derived geometry is only pinned to a *block band*, so the exact device height is unknowable (7622
blocks at 8x8 is 74x103 blocks = 585..592 x 817..824 px). It does not matter: every height in the band shares
one block grid, hence one decode and one encode.

### The faction tab labels exist twice, and the two disagree

The faction names are in the catalog as **text** (`Project8CampCareerName111/115/116/117/_NoneCamp` in table
`DD5B5EDFBB69FEED`, e.g. `逐鹿 -> Zhulu Plateau`, `无阵营 -> Factionless`) and **is** translated and staged
into package 1 — and separately as **baked art** (the 420x44 tab banners and 568x70 strips). **All 13 banner
textures are absent from the device.**

The Card Info screenshot resolves which is which: `[Central Plains]` renders **English** inside a card's rules
text, so the text path does work for faction names, and the Chinese `河洛` sits in the ribbon of the same
card. The text records serve rules-text references; the ribbon and the tabs are the absent art, and driving
the tabs from the catalog would need the mobile build's banner ids, which the catalog does not carry. Of the 8
catalog tables carrying faction labels, only `DD5B5EDFBB69FEED` exists on the device; the other 7
(`6B020594DCDC6806`, `B87B3E23D0591FD1`, `6649BBDD0B5C956F`, `6F2B902FC9DD911D`, `9F4541C6A6177C14`,
`34EF6DE1C7140D93`, `86DCBFEE914DBB7C`) are absent from all 277 `builtin` packages.

The Factionless faction has **no English name**, so its card bar reads the fallback `FACTION OF HERO 16` while
the tab reads `Factionless`. No alias table was added for any of this: it is a reviewed record, and there was
nothing verified to record.

## 7. Text staging: the drop loop and relocation

An **override-layer** loss, independent of the prime-layer gap in §4. The staging loop in `build_patch`
deletes any translated table the QtsVFS container will not take and restages, then reported the package as
`verified`. On a fresh 1.4.0.1 pull, package `1` staged **81 of 92** translated tables and dropped **11**
(the "81 text tables" the 10:23 run recorded *is* that 81 of 92); on the older 1.3.0.4 data it was 15 of 92.
**Every dropped table is chessplayer domain** (`Chessplayer`, `Skill`, `Talent`, `Amulet`, `Scepter`,
`Secret`); the 81 that survive are general UI, event and item text. Reproduced exactly, with the errors the
code never logged: `Additional QtsVFS chunks require one contiguous physical window` for the two 600 KB tables
(`28D9F8B02CAA94E2`, `A336359CD92A858E`), and `QtsVFS position index has no safe insertion point for slot N
key X` for nine ~277 KB ones. **Not a text-length problem:** mean expansion is 1.121 for the dropped set and
1.123 for the staged set, and the staged set holds the largest table of all. A rebuilt package removes the
constraint entirely, because the official builder re-lays out the package instead of fitting into it.

**Fixed as reporting only:** `build_patch` writes `text_skipped` (one entry per package that lost a table:
`package_id`, `mode`, `considered_count`, `dropped_count`, `dropped`), logs a line per package, and
`count_untranslated_text` feeds both GUI sites. `dropped` is the plan minus what the staged directory holds,
and it agrees set-for-set with `fit_summary.dropped_while_staging` — use that field as the cross-check.
Feature doc `docs/features/text-drop-report.md`.

**`b5cd724`'s commit message and that feature's `[S1]` attribute the Chessplayer screen to this drop loop. That
attribution is wrong** (the real cause is the prime layer, §4) — amend it.

The **relocation pass** (`device_extensions.exclude_extra_chunks` / `write_assets` / `relocate_text`) appends a
table the stager cannot fit to the end of the shard instead of dropping it. **It recovers the 11 chessplayer
tables**, verified through the frozen exe's `--selftest` on the no-APK path: `relocated-text 11` for package
`1` and an empty `text_skipped`.

Verification note: `build_patch` leaves the dump byte-identical, so a pulled session `game/` directory can be
pointed at directly — expose it to a scratch session dir through a Windows directory junction rather than
copying 2.8 GB.

## 8. Why package 21 is not rebuilt

The Central Plains Card Info ribbon was made English by rebuilding package `21` to carry the wide panel
`7B4CC5DF48336D2D`. **That rebuild blanks the Factionless card (Yixing):** in the grid its cell renders the
engine's grey placeholder, showing the internal name `朵莉亚` and the font `TimiText`, and its Card Info panel
comes out grey. With Tencent's own package `21` in place the card is correct (art, name, "Yixing", rules
text). Reproduced the same day, so it is not a one-off.

**The rebuild is content-faithful, so this is structural.** Re-measured exhaustively (an earlier "3470
identical, 0 differ" figure had swept under half of Tencent's 4866 entries): of the 4862 shared hashes, 3470
match Tencent's override bytes exactly and 1392 carry prime's bytes exactly — the assets whose bytes only the
APK holds, which the rebuild materialises. All four dropped entries have no bytes in either layer of package
`21` (two of them, `CDE7C688F1E0185A` and `E5FBCD1C777EB18E`, have bytes in package `20`), and nothing
requests them. The English panel keeps the original geometry exactly (43168 B = 568x304 at ASTC 8x8, as
prime's does).

**The only identified difference is the index entry shape, and Tencent's PC builder cannot reproduce it.**

| | record sizes | head sizes | codecs |
|---|---|---|---|
| Tencent's `21` | `{92: 3578, 104: 1288, 156: 1}` | `{56: 3581, 68: 1285}` | `{4: 3192, 9: 1285, 1: 389}` |
| the DLL's rebuild | `{92: 4865, 156: 1}` | all 56 | `{4: 3191, 1: 1674}` |

Index record layout: a 28-byte header, then a head of 56 or 68 bytes, then the 8-byte file hash repeated. So
`head_size = record_size - 36`, and the packed compression flag (`level << 16 | type`) sits at
`28 + head_size - 8` — `+76` for a 56-byte head, **`+88`** for a 68-byte one. `qts_builder.entry_flag` reads a
fixed `+76`, so for a 68-byte head it reads a neighbouring field and the builder is told "level 5, codec 1"
instead of "level 9, codec 9". Verified directly: told codec 9 explicitly, the DLL honours the **codec** but
still writes a **56-byte head and a 92-byte record**. For 68-byte heads `w11` (`+44`) is a *reservation*
larger than the payload and `w17` (`+68`) is 2; the rebuild normalises both to the 56-byte shape's values. The
package still mounts cleanly (`MountPackage 21, override, … state:4 prebuild:0`, `brokenFiles count 0`) and
every entry decodes, so **the game rejects something subtler than a read failure**.

**`7B4CC5DF48336D2D` has exactly one home: prime package `21`** — confirmed across all 182 prime indexes and
all 278 downloaded packages. An override package that is *not* `21` cannot supply it: rebuilt `1050016095`
with the panel added as its only change (verified as the pipeline's own output plus one asset) left Su Lie's
ribbon Chinese, `❖ 河洛 ❖`. **Resolution is per-package**, and a foreign override package cannot claim another
package's hash.

**Cost is not the reason** — a rebuild lays out the *downloaded* copy, 4866 assets and about 40 MB, not the
APK's 511 MB over 85,211 assets, so a future attempt should be judged on what it costs the screens rather
than on recompression.

**Ruled out, so they are not re-opened:** stale VFS cache (moving `files/QtsVFSCache/Watchdog/` and
`PackageStats/` aside, which the game then rebuilds by itself, changed nothing — the card was still the
placeholder with a fresh cache); a codec-9 asset explaining it (package `21` holds no card- or panel-shaped
codec-9 entry at all); texture geometry changes; and the dropped entries. The two layers can legitimately
differ in geometry: `C9E29F61B9E73713` is 592x816 in prime but 592x824 (121952 B) in the override, and the
pipeline carries the override's revision through unchanged.

### A latent bug found on the way

`1D13F7315D89BAC3` and `AF1FB540A2B8CB52` are the builder's own export-setting and remain-dir **node
payloads**, listed as ordinary entries in a staged package. Handing those two to `QtsVFS.dll` as assets makes
it write **no nodes at all** — no `QTSF_PACKAGE`, no `INGQ` — and `finalize` then raises `builder wrote no
package node`. The pipeline only avoids this by accident: `transform` returns None for them, so the prime loop
skips them and they never reach the builder's asset list. A rebuild driven from a *device* package that lists
them (which the phone's own patched packages do) would fail. **Fixing it means excluding those two hashes in
`package_rebuild`.**

### Device facts

- The VFS logs a failed lookup as `Res no found in db <decimal hash> <n>`. The only one ever seen is
  `7558170000148913571` = `0x68E40391FAE3DDA3`, which is in **no** package in either layer — Tencent's own
  gap.
- `QtsVFSCache` holds no explicit global-index file. The derived state is
  `Watchdog/{BrokenList,History,PatchList,StorageStatus}.db` and `PackageStats/PackageSize.db`, all rebuilt by
  the game when removed.
- Prime packages extract from the APK in seconds (`assets/bin/Data/Package/builtin/<id>/` is stored, not
  deflated): package `21` is 9,928,704 + 501,448,704 B, `1050016095` is 180,224 + 5,046,272 B.

## 9. The prime rebuild and the append path

Branch `feat/prime-rebuild`, base `e21ed33` (the tip of the also-unlanded `feat/text-drop-report`), head
`c0581cb` — `1341055` the port, `263631b` and `5bf1ab3` the post-review fixes, `c0581cb` the finalized
document. **Deliberately left unlanded**: the user chose to keep the branch and test on a phone first, so
nothing was merged into `master` (then still at `290f5d8`, four features behind). Feature doc
`docs/features/prime-rebuild.md`; the method guide `docs/agent-guide-untranslated-strings.md` was
rewritten in English in place. **Not verified on a phone at the time** — do not read the branch's existence as
a device-tested result.

What it does: rebuilds override packages `1` and `1050016095` whole with Tencent's builder
(`resources/qtsvfs/QtsVFS.dll` + `QtskDB.dll`, driven by ctypes from `tools/qts_builder.py`), so the
downloaded copy can carry the prime-only content, translated. `REBUILD_PACKAGES` was `("1",
"1050016095")`; every other package kept the in-place path because a rebuild recompresses all of it. The
in-place loop and the extension pass both skip a rebuilt id (`skip=rebuilt`). A run staged package `1` = 400
replacements (102 downloaded + 298 from the APK, 701 assets) and package `1050016095` = 72 textures (73
assets), which took **394 of the catalog's 398 texture edits from 323**.

### The first device test (~20:38, from an already-patched install)

**The patch itself did exactly what it was supposed to.** It skipped the APK copy (cached size matched the
phone exactly), rebuilt, and pushed six packages. `package 1: rebuilt with 701 assets (23 downloaded assets
translated, 298 translated from the APK)` — 23 rather than 102 because most of package 1 was already English
from the previous patch, while the 298 from the APK are the headline and come from the APK regardless of the
phone's patch state. `1050016095: rebuilt with 73 assets (1 + 71)`, `15: 14 textures`, `19: 7`, `20: 1`,
`package 4: 2 extra assets` — small counts are the re-run effect on already-English packages. The GUI
reported `323 text tables and 94 images translated`, exactly what `count_translated` should return on that
summary (321 + 2 text, 72 + 14 + 7 + 1 images).

**Then the game would not boot** — `signal 11` about 7 s after Unity starts rendering, right after
`CheckLocalPatchDiffFiles … blModified = [1]` then `GetAllSubpatchInfo ArraySize:[552]`, with only `builtin`
mounts and no `override` mount. **Resolved: the crash was the debuggable build, not the patch** (§2 Cause B).
Both that crash and the "reverting the packages still crashes" test ran while a debuggable build was
installed, because the restore that should have replaced it had failed silently.

The patched run reproduced the offline numbers exactly: `701 assets (102 downloaded + 298 from the APK)`,
`1050016095: 73 (1 + 71)`, `402 text tables, 394 images`. Below the UI, the staged package `1` holds **388
catalog tables with `translated: 0`** against 90 in the pristine download — the delta of 298 is the APK-only
tables — and `00BF2528D217FFFA` (`战队` / `最强王者达成次数` in the APK) now reads English. The tables this
feature exists for do reach the layer the game mounts; what it *looks* like in game still needs the user's
eyes after login.

**Baseline:** the dump pulled at 21:31 is the only pristine 1.4.0.1 copy this repo holds, preserved at
`D:\hok-verify-prime-rebuild\pristine-213152` because the patcher's session pruner would have deleted it.
Restoring its six packages is a faithful baseline — the next pull measured 2.667 GB and the unpatched control
boots on it (patched data pulls 2.737 GB). A file-level revert is still not the same as `pm clear`, so confirm
a baseline with an unpatched launch before trusting it.

### Builder pitfalls, all load-bearing

`MaxStorageSize` must be set (1 GiB) or the builder reads uninitialised memory. The packed compression flag is
`level << 16 | type` (level 5). The builder reports exactly 3 records to drop per package. The read-back must
cover every asset and the `QTSF_PACKAGE` node must be preserved, or the package is not pushed. `lz4.block`
reaches the frozen exe through `resources/runtime/`, not through a PyInstaller flag — but `pypinyin` needs
`--collect-all` (the extra-text pass added `pypinyin==0.55.0`).

### The append path, which replaced the rebuild

Rebuilding package `21` costs the Factionless card (§8), so the panel it holds reaches the phone by **append**
instead. `qts_insert.add_assets` is the general technique — *grow a package without re-laying-it-out*:
Tencent's builder makes a throw-away package holding only the new assets (so every derived key is genuine),
and those records and slots are appended to the target's index and shard and linked into its B-trees. **The
target's shape is never rewritten.** It supersedes an earlier cross-package-injection lead, which failed
because panel resolution is per-package.

- `Shard.insert_key` does **no page splits** and raises `TreeFull` when the leaf the search reaches already
  holds 510 keys. `add_prime_only` catches that per package and reports it in `append_skipped` rather than
  failing the run, because one full leaf should not cost the whole patch. Measured headroom on Tencent's own
  package `21`: its override index has 12 leaves at 333–491 keys and its shard 15 leaves at 344–464, none full.
- `add_assets` writes `<id>_0.db` by name, so a device copy split over several shards is skipped rather than
  guessed at, and it reads every appended asset back through `QtsPackage` before returning — **that read-back
  is the only check this path has.**
- Idempotent against its own output: an asset the staged copy already holds is not appended again, because a
  second record would index the same B-tree key twice. The staged copy is left in place rather than deleted,
  so an output directory reused across runs can hold a package the later run does not report; the app never
  reuses one (each run stages into its own session), which keeps `packages` and the directories in step.

Since `REBUILD_PACKAGES` was emptied, packages `1` and `1050016095` reach the phone the same way — **297 of
package `1`'s 298 prime-only tables and all 71 of `1050016095`'s prime-only textures** — and no package is
laid out again. Nothing in a normal run calls the builder at all.

## 10. Offline tooling

All of this runs with no phone and, except where noted, no game dump.

- `tools/research/check_graphics.py` is the texture codec's own offline check: section `[8]` prints a
  per-entry table (absent/skipped by default, `--table` for all), `[9]` exercises `splice_label` on a
  synthetic revision. With `--game` it takes ~90 s. It still prints `absent: 75`, deliberately worded as "not
  in this dump (the downloaded layer)".
- `tools/research/render_texture.py` renders a catalog payload or a device ASTC texture to PNG. Building
  contact sheets from it is how the 1994-vs-299 split in §6 was established — far cheaper than reasoning about
  previews.
- `tools/research/browse_assets.py` (2026-09-30) indexes every asset and renders textures into contact sheets
  captioned with the **full 16-character asset id**. `--manifest` writes a CSV inventory of the whole build;
  `--all --render` draws it. **Geometry is never stored in a package**, which is what the tool exists to make
  explicit.
- `tools/research/ribbon_id_hunt.py` is the record of the wide-ribbon id hunt (§6);
  `tools/research/prime_probe.py` is the two-layer census (§4).

The full-build render reconciles the mobile build's **83,131 assets** exactly: **56,707 are not textures** (a
few hundred bytes of config each; their size admits no geometry at any ASTC footprint), **25,053 render** onto
522 contact sheets in `dist/HOK ACE Patcher Data/graphics-diagnosis/browse/all/`, **1,369 will not
decompress** (Oodle raises "Could not decompress requested amount"), and **2 crash the ASTC decoder outright**
with an access violation (`0xC0000005`, process exit `-1073741819`) that no Python `try`/`except` can catch:
`B42899B3179ABE81` (pkg 19, 1024 B) and `EDA4FB6CC02B76BE`.

Both decode perfectly in isolation, so the fault needs the accumulated state of a longer run, and it hits at
the same point every time. `browse_assets.py --trace` logs each id to stderr immediately *before* decoding it,
so the last line names the offender; `--skip <id>` with `--resume` carries the run past it. **Do not try to
fix this by reordering the work or catching exceptions — it is a native fault in the codec.** The full
inventory with ids is `…/browse/all_assets.csv` (83,131 rows).

Two engineering facts, each of which cost a wasted run to find: **never rebuild a package's slot map per
asset** (`QtsPackage.build_slot_map()` on a package like `20` parses 29,670 entries; once per texture made the
render cost 2.2 s per asset — 23 sheets in 40 minutes — instead of 4.5 ms; cache it per package), and **never
collect rendered images and write the sheets at the end** (26,424 decoded textures is hundreds of GB of RGBA
buffers, so the first attempt thrashed and produced *nothing at all* after an hour — flush each page as it
fills, downscale on arrival, and write a sidecar of the ids on each sheet so an interrupted build can be
resumed rather than restarted).

## 11. Operating discipline

**Order of operations.** The patcher has **no completeness check** for the in-game download: `pull_game_data`
only asserts that `files/QtsVFSCache/packages/1/1.info` contains `"version"`, and patching an incomplete set
is what poisoned the game (§2 Cause A). Run the patcher only when the game has reached the login screen on its
own; use `Cache/Update/NewVersionInfo.json` (`needDownloadSize == 0`) plus the downloaded package set as a
sanity check, and treat a device data set well under ~2.8 GB as suspect. Write the translation **after** the
in-game update finishes.

**Reading and writing game data.** `run-as com.tencent.tmgp.osgame` works **only while the debuggable access
APK is installed**; pull or push `files/QtsVFSCache/packages/<id>/` before restoring the normal APK, or
reinstall the access APK first. A patcher session keeps both sides of the patch:
`<work>/sessions/<ts>/game/WXQ_Data/Package/builtin/<id>/` is the pre-patch device dump (the rollback source),
`staged/<id>/` the patched output.

**Habits this project paid for.**

- **Run the control in the other direction before attributing a device failure to a change**: unpatched +
  same APK, patched + clean APK. Both controls here were ~2 minutes each and neither was run first, which is
  what cost two hours.
- **Re-measure the load-bearing part** of a report that contradicts a durable claim — and re-read a confident
  durable claim for *what it measured*, not just its answer. Both the project memory and a subagent's report
  had been measured, against the downloaded layer only.
- **Bisect upward** from the last known good when the answer is a subset: four cycles that each grew the
  recovered set beat bisecting down from the full build, which would have produced three "still broken"
  reports and been wrong about the first three assets.
- Reverting textures (three minutes) eliminated half the hypothesis space outright; more analysis of the
  suspect did not. And compare **asset by asset, not file by file**, when checking a code change against a
  device-validated build.
- `Start-Process -ArgumentList` with an array silently splits a path containing spaces, so a windowed
  PyInstaller exe falls through to its GUI branch and waits on a window forever; and `&` does not wait for a
  GUI-subsystem exe, so `$LASTEXITCODE` is empty. Use one pre-quoted argument string with `-Wait`.

**Open and unconfirmed.** Whether the Card Info view follows the 26 newly-applied wide panels **is for the
device to show** — do not claim it. "Chessplayer" overlapping "Combat Power" in the header is a **text-length**
problem in the mobile layout, not a missing string. The Card-menu faction tab was listed as unresolved via
prefab rewrites (`stack corruption detected`) while the user reported it working — likely through the
prime-only table route the method guide suggested (that guide is since folded into `prime-rebuild.md`);
**confirm which mechanism before copying it**. Mail, quiz and notices were only ever tested together (§5), so
separating them costs one device cycle each.

## 12. Machine and housekeeping facts

- The exe calls `adb kill-server` on exit, which also tears down any other adb client's server on 5037 — expect
  "daemon not running; starting now" on the next command.
- `prune_old_sessions` keeps only the last two sessions, so a rollback dump older than two runs is deleted.
- The patcher's ~8 GB working data goes to the user-chosen folder (default `HOK ACE Patcher Data` beside the
  exe), never into this repo. On this machine: `dist\HOK ACE Patcher Data`.
- The staged driver used for the device cycles is `%TEMP%\hok_run.py`, one stage per command
  (`fixapk|normal|access|pull|patch|restore|launch|unpatch`) — one step per command is what stopped it
  hanging. `%TEMP%\hok-patcher-backup.exe` is the user's pre-change exe.
- `D:\hok-verify-prime-rebuild\pristine-213152` is the only pristine 1.4.0.1 dump and must be kept;
  `dist\HOK ACE Patcher Data\sessions\20260930-203818` is 6.5 GB and disposable.
- Cleanup of 2026-10-01: `D:\` held ~40 GB of `hok-*` / `rv-*` scratch; 38.97 GB was deleted and the keepers
  (414 MB) moved to the repo's gitignored `artifacts\`. Two junctions under `hok-verify-textdrop*` had to be
  unlinked before any recursive delete — **`rmdir /s` must never meet a reparse point.** `hok-base-ab` (an
  older, `.git`-less repo copy) was verified fully recoverable from history (5 differing tools at `e21ed33`,
  `9947ed1`, `c0581cb`, `c3f23b3`) before deletion.

### Local artifact retention (2026-10-03)

Cleanup on 2026-10-03 removed **18.1 GiB** of obsolete outputs. `artifacts/` remains gitignored;
game dumps, APKs and generated patch packages are local inputs and evidence, not release source.

Retained:

| Material | Location | Purpose |
|---|---|---|
| Fresh 1.4.0.2 snapshot and its verified hashes | `dist/HOK ACE Patcher Data/pristine/20261003-173730/` | Known working Chinese control; future checksum research |
| Current normal/access APKs and updated patcher executable | `dist/` and `dist/HOK ACE Patcher Data/` | Supported installation and restore path |
| Full fixed patch, repair/rerun checks and native chunk-key donor | `dist/HOK ACE Patcher Data/grid-regression/` | Reproduce and verify the Talent Card fix |
| Screenshots, device push hashes, logs and small measurement reports | `artifacts/shots/`, `artifacts/device-cycle-t10/`, other cycle evidence directories | Preserve successful and failed device verdicts |
| Device push/capture tools and research probes | `artifacts/device-cycle-t9/`, `artifacts/device-cycle-t10/`, `artifacts/device-run/` | Reusable diagnostics; no imports from shipping code |
| Older source dumps and original APK | `artifacts/game-dump*`, `artifacts/tencent-pristine-1.1.1.apk` | Historical comparisons; never treat a patched dump as pristine |
| Small package-1 comparison specimens and key-probe inputs | `artifacts/cycles/base2/out/1`, `artifacts/cycles/3914DBBFECD1E54D/`, `artifacts/device-run/empty-rebuild/out/1`, `artifacts/device-cycle-t9/shipped-stage/` | Preserve the inputs needed by retained measurements |

Removed repeated prime extractions, replacement scans, superseded full rebuilds, obsolete 1.4.0.1
candidate patch outputs, duplicate selftest outputs, failed build logs, an unused PC installer, the
old full-cycle diagnostic backup archive, and scratch commit/diff text. Small reports and screenshots
were retained. The verified deletion inventory is `artifacts/cleanup-plan.json`.

Older spec commands remain historical verification records. Their removed outputs must be rebuilt
before reuse. In particular, an extra-text candidate needs a fresh build staged from the phone's own
game-data version; the old candidate packages are neither retained as complete patches nor ready to
push. This cleanup does not change candidate verdicts or the four-asset allowlist.

Before deleting more, retain a reproducible source, the current restore APK, and the evidence behind
device-gated decisions. Resolve every deletion target inside the intended artifact root and use native
PowerShell file operations. Never delete the generated runtime/catalog resources or signing key.

## 13. Superseded claims

Claims that were believed, acted on, and turned out wrong — kept because the middle column is the real lesson.

| superseded claim | why it was wrong | corrected to |
|---|---|---|
| 75 of the catalog's textures are absent from the mobile build | censused the **downloaded layer only** | 73 more are inside the APK; only 3 exist in neither (§6) |
| the other factions' wide 568x304 panels are not in the build under any id; the gap is unfixable from this repo | same — downloaded layer only | 26 of 27 are in the APK's prime layer under the catalog's own ids (§6) |
| Card Info renders the `592x816` portrait frame | inferred from layout; the views look alike | the wide `568x304` family, settled by ids and elimination (§6) |
| the Chessplayer screen shows Chinese because the drop loop drops its tables (`b5cd724`) | that screen draws from the **prime** layer, which the in-place path never writes | the prime-layer gap; the drop loop is a separate real loss (§4, §7) |
| the `extra_text` pass is blanket-unsafe | swept every asset at once | content-specific; four assets ship (§5) |
| the four `SAFE_ASSETS` are safe | each was cleared against the **replay crash only**; nobody opened the Announcement screen or watched a match end | all four withdrawn 2026-10-05: rule pages hide the news header, the other three end every match in the QTS-failure popup (2026-10-05 section) |
| `197CC5…`, `884E0B…`, `89C771…` cannot be applied by any code change | searched by the catalog's hash only | the cards exist under other hashes; their bands match at 0.01-0.02 (2026-10-05 section) |
| these four assets are exonerated | "not changed in the staged package" was read as "disabled" — an enabled asset that rewrites nothing looks identical to a disabled one | only a single-variable pair, both sides staged, supports a causal claim (§5) |
| the `nodisplay` build had every `extra_text` asset disabled | it kept BOT and still enabled `A1987F488164E53A` | measured with `hok_classify.py`, not inferred (§5) |
| reverting the packages exonerates the rebuild | sound reasoning, **wrong variable** — reverting `.db` files cannot help while the installed APK is a debug build | the debuggable APK was the cause (§2) |
| incomplete data explains the startup crash | one **sufficient** cause, not the only one | a debuggable APK alone reproduces it on pristine data (§2) |
| `pkgHash` can serve as a content-integrity check | not content-derived — identical before and after a 68 MB shard revert | it cannot (§1) |
| launching with the network off isolates the patch | it also makes TPGA anti-cheat quit early, which looks like a crash | a poor diagnostic (§1) |
| `GCloud blModified = [1]` / `GetAllSubpatchInfo ArraySize:[552]` are crash signatures | both appear on the unpatched control too | updater noise; the debug-build signature is *only prime mounts, no override mount* (§2) |
| the DLL rebuild is content-identical: 3470 identical, 0 differ | the sweep covered under half of Tencent's 4866 entries | 3470 override-exact **and** 1392 prime-exact; the real difference is the index entry shape (§8) |


## 2026-10-03 — Talent Card regression isolated and fixed

The former impossibility verdict was wrong. A fresh redownload (data 1.4.0.2; snapshot
`dist/HOK ACE Patcher Data/pristine/20261003-173730`, 653 files SHA-256 verified) draws the
grid's Chinese names. Reverting one dictionary while retaining other patched assets was
not a pristine control. Do not reuse that verdict.

`C059EA43719099F1` already defines all 4064 BE08 keys. Arena Tiger's
`#BE08801F0222C56A#` is `擂台猛虎` in fresh data and `Arena Tiger` in our English table.
Changing only that value works. Translating only the full dictionary fails when its
277698-byte payload becomes 313710 bytes and its single chunk becomes 315392 bytes.
The same full English bytes work as two chunks at the original 307200-byte size.
With explicit user authorization, the bundled builder generated an offline one-asset
donor: native keys are `15A33357ECBFA5CC` (chunk 0, matches fresh) and
`29157589AC92F155` (chunk 1). Existing container preserved, every other asset unchanged,
device hash read-back verified, normal APK restored. Screenshot evidence is under
`artifacts/device-cycle-t10/grid-cycles/{translated-map,one-name,two-chunk-map}`.

The shipping relocation path uses those measured identity keys with codec/framing guards
and read-back verification; it needs no builder DLL at runtime. The explicit repair pass
also fixes an older already-English package that the translation scanner would skip.
Full fresh build and old-package repair preserve all 700 English asset payloads; corrected
dictionary has 4064 rows, two chunks, 307200-byte chunk size. A rerun on the fixed package
stages nothing. Do not rewrite the checksum-protected grid config or expand any allowlist.

**Full device acceptance completed:** all six fixed packages pushed and SHA-256 verified.
Talent grid names and details are English; searching Arena Tiger finds its tier-2 tile,
whose detail title is exactly `Arena Tiger` (grid caption uses normal `Aren...` clipping).
Hero/Effect/Equipment tabs remain populated and translated. Normal APK restored and
`dumpsys package` shows no DEBUGGABLE flag. Evidence: `grid-cycles/full-fixed/`.
Updated frozen exe selftests pass on fresh data and on the old patched package (one repair).
Coverage counts unchanged: 391 staged text tables, 395 applied textures, one known table
append refusal. T15 complete; no commit.

**Review and cleanup:** removed 18.1 GiB of obsolete generated artifact outputs, retaining
fresh controls, original APK/source dumps, final fixed packages, screenshots, reports and
reusable probes. See §12's local artifact retention; old full candidate builds must be restaged
from the phone's version. Normal build code now initializes Tencent DLLs only when a rebuild
package is named. With `REBUILD_PACKAGES=()`, an APK plus an absent builder directory passes
the old-package repair check. Graphics offline checks pass.


## 2026-10-05 — Indonesian device report: four bugs, three causes

Reported on the Indonesian build (1.4.0.2, Xiaomi `f15a72e`). Each verdict below is a pushed build,
14/14 files read back on the phone, normal APK `29b3ee7e…` restored, screens watched.

- **Effect Card filter showed `通用`** (chip, filter button, section title). Not a table: the Lua script
  `9BD30F0DF58B1FBF` (package `10`, prime-only) hard-codes `name = "通用"` for a card with no faction
  (`CardClassifyCriterionEffectCardType:vClassIdToDescriptor`, id -1). The faction labels around it come from
  `6649BBDD0B5C956F`, which was already translated. Fixed by `extra_text.SCRIPT_LABELS`, appended to package
  `10`'s override copy (`MountPackage 10, override … succeed`); the chip reads **General** on the phone.
- **Armed Power kept `-大河流域-` on its band.** The catalog's three "neither layer" edits are effect-card band
  edits whose payloads are shared by 7-8 cards each. A census of package `15`'s 1994 card-shaped textures
  (404x564 ASTC 4x4) against the bands of the 299 catalogued cards found exactly three uncatalogued cards at
  mean difference 0.01-0.02, one per missing edit and each matching that edit's payload group; the next
  closest is 0.38 (44 blank-band cards). `962747E1E5B73A93` is Armed Power → `884E0B4581F47CF7`;
  `C71FEF8D6BE03BBF` → `89C771ECFCDC7FBE` (Sunset); `29B6B1724CC28DE0` → `197CC5393D16E3CB` (Three Kingdoms).
  `mobile_graphics.DEVICE_REVISIONS`; package `15` now applies 302 textures; the band reads **Riverlands**.
- **Announcement screen lost its back arrow and title** (the system back key then offers to quit the game).
  `UINewsMainClass:InitUI` evaluates `PBDataManager.ResHelpSystemCfgDataBin.Get(NEWS_CENTER)` before it
  builds the header, and `B5D856BFDF22400D` — the allowlisted "rule pages" — *is* `ResHelpSystemCfgDataBin`
  (fields ID, Title, TabCount, TabData…). Build A = the fixes above with only that asset left out: header back
  ("< pengumuman"). Strictly A also added the script and three textures, neither on this screen.
- **`/未翻译UI/QTSFailureTips` popup after every match.** `GameplayClass:vOnPostLeaveGameBattle` shows
  `Localize.GetString("QTSFailureTips")` when the C# `Doctor.QtsFailure` flag is set ("QTS exception, ask the
  user to restart"); the key has no string anywhere, hence the raw path. Not a broken file: QtsVFS logs no
  read error during the match and `Watchdog/BrokenList.db` stays empty. Build A (three config bins still
  rewritten): popup in 2 of 2 matches. Build B (all `SAFE_ASSETS` left out): no popup. Not bisected further
  at the user's choice, so `SAFE_ASSETS` is empty.
- The game's own logging is off in release (`dc.Log.ShowLog(False)`); `[QTS_LOG]` still reaches logcat under
  `Unity`, and the main buffer is only 256 KB, so a match has to be streamed live
  (`adb logcat -v time Unity:V GCloud:V '*:E'`), with a reconnect loop — USB dropped twice in one evening.
- The stored 32-hex MD5 at the head of these bins is **not** `md5(rest of the bin)`, so resealing is still
  unknown. `ResData.ResActivityHelpSystemCfgDataBin` and `ResNBGuideTipCfg` "Does NOT exist" lines are the
  game's own (absent from the pristine dump and the APK too).
- Machine: `/data/local/tmp` held 6 GB of 09-28 research APKs (`exp2c2.apk`, `osgame_exp2_crcpatch.apk`,
  `osgame_gadget.apk`, `frida-server`); with 4.2 GB free the normal-APK restore failed with
  `INSUFFICIENT_STORAGE`, leaving the debuggable APK installed. Deleted with the user's approval (10 GB free).
  A cycle script must keep the restore inside `finally` for the access install itself too.



## 2026-10-08 — Diamond Frenzy Effect Cards print raw `#23F7...` refs: the other ten card dictionaries

Reported on the Indonesian build installed by the Android patcher (Infinix X6853, session `c1a2e7d8`,
388 tables / 398 textures); the user says the English build shows the same. Encyclopedia → Diamond Frenzy →
Kartu Efek: every grid caption and the detail pane's name and description are raw refs
(`#23F7C87B1B68DA1C#`, `#23F7CDBFA1846C57#`), while the tabs and the "Terkait" line are translated.

- **Cause: the T15 failure on the other card dictionaries.** Both refs are defined in `28D9F8B02CAA94E2`
  (600 767 B, 2 chunks x 307200; `41B38BE39A60C211` is a 1.2 MB asset that references them). Each game mode
  carries its own copy of the card dictionary under its own ref prefix, and the relocation pass enlarged the
  chunk size of the ten that are not the Talent one. Offline Indonesian build on the 1.4.0.1 dump
  (`cache/base-1401`): `28D9F8B02CAA94E2` and `A336359CD92A858E` 600 767 → 658 309 B at chunk size 331 776
  (2 chunks); `666DC40230B31A30`, `F628F40CE23D983E`, `42E8DB43608C2FF1`, `9BE81CD52C660467`,
  `27BBF8CDFFFA177F`, `C4E32B49AE8B7FFB`, `5EB61A0269CD8550`, `04F21C6735D0D555` ~277 KB → ~319 KB at
  319 488 / 323 584 (1 chunk). Prefixes `#23F7` `#8E55` `#A40D` `#0977` `#9344` `#BF5A` `#75CA` `#1632`
  `#31CF` `#BCDE`; `C059EA43719099F1` (`#BE08`) was the only one already fixed.
- **Keys minted offline, user-authorized.** One throwaway one-asset `Builder.build` per dictionary with the
  staged bytes at chunk size 307200, flag `0x50001`. Every chunk index the device already has reproduced its
  device hash1 (11/11), the Talent dictionary reproduced exactly `15A33357ECBFA5CC` / `29157589AC92F155`, and
  every build read back byte-identical. The new keys are `device_extensions.NATIVE_CHUNK_KEYS`.
- **Offline verification.** Indonesian and English fresh builds: all eleven at chunk size 307200 with native
  keys (3 chunks for the two 600 KB dictionaries, 2 for the rest), no non-standard chunk size left in package
  `1`. Repair path: a build over the old broken output repairs ten dictionaries and its package `1` is
  byte-identical, asset for asset, to the fresh build.
- **Owed: the device verdict** for the ten new dictionaries (Diamond Frenzy Effect Cards first), and the
  Android APK rebuild that carries the fix (no Android SDK on the machine that made it).

### Same day: 1.5.0.1 on the phone, catalog fixes, an Android 15 preparation failure

- **Device verdict for the card dictionaries.** The phone moved to data 1.5.0.1; a USB run through
  `patcher_core` (same `build_patch` as the Android engine) staged all eleven at 307200 with their native keys
  (keys of 1.5.0.1's chunks matched the minted ones). Diamond Frenzy's Effect Card grid and detail pane now read
  as text (screenshot of Build Snowman's tile and name). One more enlarged chunk remains, on the **append** path:
  `218D140500F68F37` (prime-only hero skill text, `#CE46` refs, 259 450 → 311 786 B at chunk 315 392). Not fixed.
- **1.5.0.1 rewrote card texts the catalog keyed by their old wording** (`+3`→`+4`, `3/5/7/9`→`3/6/9/12`,
  `+10`→`+{0|10}`…), so those rows stay Chinese. A rough scan of package `1`'s catalog tables found ~1300 distinct
  Chinese values left, ~100 of them near-identical to a catalog source. Only the ones the user reported are fixed.
- **Indonesian catalog fixes**, re-applied over each upstream catalog by `tools/research/apply_catalog_fixes.py`:
  `棋手` Chessplayer (upstream wrote Pemain), `传承` Inheritance, `阵营祝福` Faction Blessing, Yao's Combine keyword
  link, and the 1.5.0.1 wording of Shared Fortune, Inheritance and Build Snowman.
- **Android 15 (Infinix X6851) fails APK preparation** with `Prepared APK version/signer/debug identity differs`
  on game 1.1.1 (774472), three retries, 18 GB of unfinished preparations left behind. The normal APK passed
  `requireRecovery`, so the access APK failed; the game manifest has **no** `android:debuggable`, so access gets the
  attribute inserted, which Android 16 on the X6853 honours. Cause not yet measured: the Android build now names
  each differing field and Android's vs the manifest's debuggable view, and removes unfinished preparations.
- **Android build.** JDK 17 + SDK 35 live outside the repo (`..\toolchain`). A clean Gradle build reproduced the
  installed APK's three dex files byte for byte, so the sideload APK is the installed build with `classes3.dex`
  and the engine assets replaced, signed with a new key in `artifacts/android-sideload-key/` (not the original
  debug key: installing it over the original build needs an uninstall).

## 2026-10-10 — an in-game update left 1 092 strings Chinese

- **Pull.** Xiaomi M2007J3SG, Android 12, game APK 1.1.1 (774472, our signature, already renamed); `1.info`
  still reports data **1.5.0.1** although the content changed, so the version string is not evidence that
  nothing moved. Pulled through `patcher_core`'s own steps (access APK in, `tar` out, normal APK restored;
  old-session pruning disabled for the pull) into `sessions/20261010-112510`. The phone was patched in
  **English** before the update. The phone's APK is 67 613 B smaller than the 2026-10-01 cache, which is kept as
  `installed-20261001.apk`; the phone's file is now `installed.apk`.
- **What changed.** Scanning every catalog table in the layer for `Catalog.lookup` misses with Chinese in the
  source: **1 673 records, 1 092 distinct strings, 60 tables, all package `1`, nothing in prime**. The bulk:
  `55EC8FF338904581` (625, new weekly leaderboard titles `上周{战力巅峰,钻石狂潮,成就大师}排行榜排名第N`, N 1-100)
  and `EE5CF72D67A94C1F` (550, achievements now tiered as `name(一)`…`name(十)`, half-width parentheses).
  The rest is new content (Line Puppy Sky Screen Prayer `XianTiaoDraw_*`, King-rank Diamond rewards, Ace Duel
  support dividends with 1st-3rd place caps, King of Kings sub-account rules, a surrender confirmation) and
  rewordings: the eleven per-mode card dictionaries took 3/6/9/12 Energy, Fate Gift on Round 6/11 and
  `吸血`→`护盾效果`; the Water Moon illusion deals magic instead of true damage.
- **Fix.** `tools/research/catalog_additions.json` (en + id per source) applied by `apply_catalog_fixes.py`,
  which now writes both catalogs. 300 + 540 + 21 entries generated by rule from the catalog's own names, 231
  translated by hand; all pass `validate_translation`. After it: English `unknown` 0, Indonesian 40 (English
  rows the earlier English patch left on this phone).
- **Latent crash found and fixed.** `_drop_uncatalogued_tables` subtracted from `counts["unknown"]`, and the
  scanner's census omits a zero count: the first catalog to translate every string the scan met made
  `build_patch` raise `KeyError: 'unknown'`. It now treats a missing key as zero.
- **Device verdict.** Pushed through `patcher_core` (session `20261010-115042`, English); the user reports the
  updated screens read English. Offline and on that run: package `1` stages in full (49 in place + 11 relocated card
  dictionaries), `text_skipped`/`graphics_skipped` empty, `append_skipped` the known `3A70308AAF6F18F8`.
- **Still Chinese after it, by design:** the Encyclopedia card detail's *Special Notes* for Inheritance
  (`…获得的<b>传承</b>不会超过2张。`) and Legacy (`遗志`, 1). Inline text in the eleven card config bins
  (`41B38BE39A60C211`, `AA06930C85212ABE`, `83AD9A9B054F80E9`, `75C9DA8F5072E6BD`, `081C8B45D95412F7`,
  `719A494DF65AD4FF`, `31A2AF4D5A21BEFF`, `1A4B63021F13E830`, `EF9FF947AAE75675`, `BDD9AF8384B15BF1`,
  `20490C29132CD09B`), the only two real CJK strings in them, with no ref; already there in the 10-03 1.4.0.2
  layer. Not rewritten: these are the checksum-protected bins whose rewrite empties the encyclopedia grid.
  The card art's bottom-band `效果` on the same screen is the uncatalogued package-`15` band text.

## 2026-10-10 — the Career atlas: the offset port put 9 English labels on other sprites

- **Report.** User screenshot (`tasks/T14/evidence/career_screen_2026-10-10.png`): `我的棋手` beside the
  chessplayer count on the Career screen. Only the count is `TimiText`; the label is the sprite
  `Image_1904551913` of `CareerAtlas` = texture **`13C19E4E4486B31C`** (package `19`, downloaded layer only,
  1024x1024 ASTC 4x4, 1 048 576 B). Its Sprite objects and Texture2D header are **`4AA2B26FF28CB65D`**;
  the lobby atlases' are `22BD565B3703EDA9` (`C9F49510F2F67402`) and `9F240FDA0FA58988` (`E86DF43167CA2143`).
  Package `0` `55989B6B5917A7D9` (10 MB) looks like the path→hash manifest (its row for `4AA2B26FF28CB65D`
  lists pathID `B0975C8A83A08957`) but was not decoded; no hash of the `.resS` path matched.
- **Cause.** The catalog's 13-region `.blocks` edit is drawn on the PC layout; the port wrote it at the PC
  offsets. Device rects (today): 11 of 13 regions moved (stubborn_bronze and order_silver by 1 px; glory_gold
  and total_achievement_points in place). Overwritten non-region sprites today: `Image_981211366` (dashed
  rules, 75 %), `Image_1134586325` (dark circle, 46 %), `Image_410780920` (`我的皮肤`, 100 %),
  `Image_1343071809` (QQ icon, 50 %), `Image_1487341597`, `Image_1281642236`, `Image_1862878375`,
  `Image_1434219398`, `Image_494086371`, `Image_2043579572`, `Image_1136439694`. The 10-03 pristine atlas
  (216 sprites) was laid out differently from both, so the bug predates the update.
- **No clean post-update atlas exists.** Both 10-10 pulls (11:25, 11:50) are byte-identical and carry the
  10-08 patch. The 10-03 sprites are the same art: of 215 shared sprites every one has the same size, and
  all but the damaged ones agree within a premultiplied mean of 5.3 (126 under 1); only 34 are pixel-exact,
  because the atlas was re-packed at other block phases.
- **The port itself is not deterministic across platforms.** Re-porting today's layer (patched on 10-08)
  differs from it in 6 blocks, and from that day's 11:50 staged copy in 1: a re-run over an atlas another
  encoder wrote re-encodes some blocks. Same-process runs are byte-identical.
- **Fix (offline, 2026-10-10).** Sprite-aware port (`mobile_graphics.port_atlas`, rects read each run by
  `sprite_table.sprite_rects`), restoration crops of 19 sprites from the 10-03 dump, and two repo-drawn
  labels: MY SKINS (`我的皮肤`, no catalog entry) and TOTAL PROFIT (`总盈利`). Labels are assembled from the
  catalog's ACHIEVEMENT POINTS glyphs; the best of ~40 Windows serif fonts fitted to those glyphs still
  had a mean alpha error of 48, so no font is used. The two lines of ACHIEVEMENT POINTS sit 19.5 rows apart;
  a half-pixel resample to align them blurred every stem and was dropped for a whole-row offset.
  Numbers in `docs/features/texture-translation.md`, *Regioned atlases*.
- **Labels hand-polished (2026-10-10, later).** The glyph-assembled renders first shipped with a grey fringe
  (composited over transparent black: 205 and 412 edge pixels below RGB 245), caught by
  `tasks/T15/validate_assets.py` and fixed. The user then polished both in `tasks/T15/edit/` (new K, bolder
  SKINS, native L/R/F, 5 alpha pixels touched in MY's M); those PNGs ship and are no longer regenerated. An
  earlier image-agent delivery in `tasks/T15/delivered/` (a hand-drawn K, per its NOTES.md) was overwritten
  by a copy without looking first and is lost.
- **Device verdict (2026-10-10): the Career screen looks right.** `patcher_core` run headless (English,
  session pruning off): fresh pull of game data 1.5.0.1 into session `20261010-151438` (backup
  `device-backup.tar` there), the build staged exactly one texture — the atlas, package `19` — since
  the phone already held everything else, pushed it and restored the normal APK. The pushed atlas is
  byte-identical to `port_atlas`'s output with the hand-polished labels; the sprite layout matched the
  morning's. Other screens that draw the moved sprites were not walked.
## 2026-10-16 — 1.6.0.1: 2073 untranslated rows, supplied in code

- **Phone on data 1.6.0.1** (APK still 1.1.1 / 774472). Pristine dump: `pristine/20261016-101124` (full
  redownload). The offline build works on it unchanged (11 tables relocated, 293 + 71 appended, same
  append refusal `3A70308AAF6F18F8` in English, `0196F0E230EC1C70` in Indonesian).
- **Leftover census** (each catalog table in the staged output, rows whose value still holds CJK):
  1.4.0.2 pristine 146 rows; 1.6.0.1 **2073 rows / 1184 distinct**, all in package `1`. Biggest:
  `55EC8FF338904581` 627 and `F1034D3BC743ED49` 400 (leaderboard ranks 第一..第一百), `EE5CF72D67A94C1F`
  553 (achievement titles `X(一)`..`X(十)`; 146 of the 167 bases are in the catalog, the rest are
  `<Chessplayer>上大分`, which the catalog has only as `<Chessplayer>这波上大分`), `DD5B5EDFBB69FEED` 100
  (UI). The 1.5.0.1 card rewordings recur in every per-mode card dictionary (6-13 rows each).
- **Fix: `tools/catalog_supplement.py`**, merged by `terminology.install`'s loader, never overriding the
  catalog. 2314 EN / 2313 ID strings, 0 `validate_translation` failures. Builds of the pristine 1.6.0.1
  dump leave 0 CJK rows in catalog tables, `text_skipped` empty; package `1` keeps every chunk at
  307200/16384 except the pre-existing `218D140500F68F37` in Indonesian (same as a no-supplement build).
- **Fixed in passing:** `_drop_uncatalogued_tables` raised `KeyError: 'unknown'` on an already-English
  layer (the 1.5.0.1 session dump), because the census omits keys it never counted.
- **Owed: the device verdict.** Not pushed: the on-phone patcher app was mid-run when this was measured.
  Screens to watch: achievement titles, the four weekly leaderboard rewards, King of Kings, a card
  dictionary screen (Effect/Talent grid must still draw).

## 2026-10-16 — Starting Lineup covers: a prime-only config bin, queued for a cycle

- **Screen:** Encyclopedia → Diamond Frenzy → Starting Lineup. The header `逆天改命卡包` and every hero label
  under a cover are Chinese; the side panel ("Defy Fate (Xuance)", catalog table `492C173C523F74EE`) is
  English. Phone on 1.6.0.1, but still carrying an older patch.
- **Source: `9E45602F1857539D`**, package `1`, **APK only** (absent from the pristine 1.6.0.1 download),
  29,529 B, one Oodle chunk at 307,200, not a catalog table. A substring sweep of both layers finds the
  bare header nowhere else. Other hits were longer strings: `23套逆天改命卡包` in `B941DD41DB3C7A73` and the
  newbie-reward candidate `41974B124E0053E0`, and an achievement sentence in `EE5CF72D67A94C1F`.
- **Coverage:** 60 distinct strings; `catalog.unique` has 27 (hero names). The other 33 are short forms
  of catalog strings: 5 `X卡包` headers from `<color=#97DFFFFF>X卡包</color>`, 13 contracts from `契约·X(Y)`,
  3 heroes (`后裔`/`哪吒`/`杨戬`) from `逆天改命(H)`, and 12 `faction-hero` labels joined from the parts.
  `catalog_supplement.derived` generates 34 new pairs per language (one extra: `神巫·云中神君`), with 0
  validation failures. With them, 60/60, 252 fields, 30,414 B.
- **Built:** control and `--cycle-asset 9E45602F` builds in `D:\scratch\hok-cycle`. They differ only by one
  appended record in package `1` (720 → 721 entries, no other asset changed).
- **Device verdict: WITHDRAWN.** Control (all 7 packages): startup clean, and the DF Encyclopedia Basic
  Rules / Effect / Talent / Starting Lineup tabs all draw. Cycle (package `1` only): startup, lobby, Card
  menu and ACE Encyclopedia normal, but **DF Starting Lineup draws empty**. The control's package `1`
  pushed back restores the grid. Content-correct offline, so this is the stale-checksum class again. The
  phone now runs the control build; device backup is in `D:\scratch\hok-cycle\backup\device-backup.tar`.
- **Control match, 2026-10-16: passes.** The user played a match to its end on the control build, with no
  `QTSFailureTips` popup; the phone's logcat holds no QTS-failure line either. Achievement titles read in
  English (user, same day). Still owed: the weekly leaderboards, King of Kings.
- **Disk:** C: had 240 MB free and an offline build died there (`WinError 112`). Builds now go on D:.

