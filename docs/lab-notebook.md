# Lab notebook — HOK ACE Language Patcher

This notebook is the single source for this repo's raw measurements and device verdicts: what went on a
phone, what the phone did, and which claim was withdrawn and why, including the attempts that failed.
Other docs cite its entries by date (for example "lab notebook, 2026-10-05") instead of copying the
numbers. A feature record carries the reasoning and this file carries the evidence; `AGENTS.md` carries
the rules that always apply, and this file is the record behind them, so **where the two disagree,
`AGENTS.md` wins**. Topic sections come first, dated entries after.

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

The triage steps are the runbook [`docs/runbooks/read-a-crash.md`](runbooks/read-a-crash.md). What
was measured behind them:

- The game suppresses tombstones. logcat says only `WIN DEATH` + `has died: fg TOP`; the `crash` buffer is
  empty and dropbox has no `data_app_crash` for the package. `dumpsys activity exit-info` does answer:
  `reason=2 (SIGNALED)`, `status=11` or `7`, and `pss` 1.2–1.3 GB in the replay crash.
- `Cache/Logs/*.logcompr` is encrypted. `bqLog/ccs_log/normal1.log` is the bq/ccs **network** log: it
  ends mid-ping at each crash and holds no stack. The same tree carries `TGPA/` (anti-cheat) and one
  `Cache/Replay/…record.<pid>.lock` per watched match.
- With the network off, TPGA anti-cheat quits early (`cloud.tgpa.qq.com` fails to resolve), which looks
  like a crash but is not one.
- `pkgHash` is **not** content-derived: identical before and after reverting a 68 MB shard change. A
  patched package mounts as `MountPackage 1, override, … pkgHash:<new> basePkgHash:<old>`; untouched
  packages mount with `pkgHash == basePkgHash`.
- toybox on this build has no `md5sum`, so hashing over `run-as` does not work.

## 2. Startup SIGBUS/SIGSEGV: two sufficient causes

Force-close ~10 s into startup, before the login screen, `signal 7 (Bus error)` or `signal 11
(Segmentation fault)`. **Two unrelated causes carry the same signature**, so a startup crash is not by
itself evidence about the patch — check `pkgFlags` first.

### Cause A — an incomplete game-data download (2026-09-30)

The game data was caught mid-update, and Tencent's GCloud updater reacted with a same-version "cures" repair
(`server.json`: `from_version` 1.4.0.1 → `to_version` 1.4.0.1, `cfilesize` 9032772, `cmd5`
`cd4f042483e9215e376b268fd147b7b6`), faulting while applying it. A fresh download is **2.86 GB**; the broken
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
culprit pass is **`extra_text`/`pb_text`**, which rewrites CJK strings inside the 14 non-table config bins.

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

The catalog holds **398 texture edits**. **323 are present in the override layer and 75 absent**; the APK's
prime layer adds **73** more (72 in prime `1050016095`, 1 in prime `21`), and `C9E29F61B9E73713` is in both.
Union = **395**, so only **three** exist in neither layer — `197CC5393D16E3CB`, `884E0B4581F47CF7`,
`89C771ECFCDC7FBE`, all 404x564 BC7 `.blocks`. The one present-but-not-applied-historically is
`7B4CC5DF48336D2D` (Central Plains' fourth wide panel) in prime package `21`; it reaches the phone by append
(§9). **State the texture count as *applied*, never as *covered*.**

Only 5 packages carry catalog hashes: `1` (text), `15` (299 card textures), `19` (22 UI), `20` (1),
`1050016095` (1).

Census of every package index in a full 2.86 GB dump (277 readable of 278 dirs):

| family | geometry | catalog | on device (override layer) | role |
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
`7B4CC5DF48336D2D` in prime `21`), and the Sunset panel the hunt found is the only one in the override
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
`34EF6DE1C7140D93`, `86DCBFEE914DBB7C`) are absent from all 277 prime packages.

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
  synthetic revision. With `--game` it takes ~90 s. It still prints `absent: 75`, deliberately worded to say
  the dump is the override layer only.
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

The procedures this section used to hold are now runbooks:
[`docs/runbooks/device-cycle.md`](runbooks/device-cycle.md) (order of operations, reading and writing the
override layer, one change per cycle) and [`docs/runbooks/read-a-crash.md`](runbooks/read-a-crash.md) (the
controls, bisecting, comparing builds). What was measured behind them:

- `pull_game_data` only asserts that `files/QtsVFSCache/packages/1/1.info` contains `"version"`: there is no
  completeness check for the in-game download, and patching an incomplete set is what poisoned the game
  (§2 Cause A, 2.12 GB against a complete 2.86 GB).
- `run-as com.tencent.tmgp.osgame` works only while the access APK is installed.
- A patcher session keeps both sides of the patch: `<work>/sessions/<ts>/game/WXQ_Data/Package/builtin/<id>/`
  is the pre-patch device dump (the rollback source), `staged/<id>/` the patched output.
- The two controls (unpatched + same APK, patched + clean APK) took ~2 minutes each and neither was run
  first, which cost two hours.
- Both the project memory and a subagent's report had been measured against the override layer only.
- Bisecting upward took four cycles that each grew the recovered set; bisecting down from the full build
  would have produced three "still broken" reports and been wrong about the first three assets.
- Reverting textures (three minutes) eliminated half the hypothesis space outright; more analysis of the
  suspect did not.
- `Start-Process -ArgumentList` with an array silently splits a path containing spaces, so a windowed
  PyInstaller exe falls through to its GUI branch and waits on a window forever; and `&` does not wait for a
  GUI-subsystem exe, so `$LASTEXITCODE` is empty. One pre-quoted argument string with `-Wait` works.

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
| 75 of the catalog's textures are absent from the mobile build | censused the **override layer only** | 73 more are inside the APK; only 3 exist in neither (§6) |
| the other factions' wide 568x304 panels are not in the build under any id; the gap is unfixable from this repo | same — override layer only | 26 of 27 are in the APK's prime layer under the catalog's own ids (§6) |
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


## 2026-09-29 — Standalone Windows app: delivery findings

From the standalone-patcher-app record's journey log (commits `7b9769b..9f151a8`).

- This repo's `tools/` is an *earlier fork* of the sibling's pipeline: `axml_set_debuggable.py` and
  `build_mobile_patch.py` are byte-identical, but `build_device_patch.py` had no `build_patch()`, no
  `qts_relocate` re-run fix, and no staging guards. Coverage gaps (resource tokens, extra text,
  textures) were left unadopted by explicit decision, not oversight; resource tokens were adopted
  later — see the standalone-patcher-app record's *Coverage difference from the reference*.
- `tools/research/axml_add_provider.py` imports `axml_set_debuggable` from `tools/`; running it as a
  script puts only `tools/research/` on `sys.path`, so the move needed a one-line parent-directory
  insert. Any future move of a script that shares helpers must check this.
- Scanning `wxq_patch`'s bytecode showed it references only `lz4` (vendored) and `httpx` (an unused
  `gemini` module) — none of UnityPy, `pypinyin`, `astc_encoder`, `ooz`, `texture2ddecoder` or
  `archspec`. `requirements.txt` and `build_exe.py` were trimmed accordingly; the exe is 48.2 MB
  against the sibling's 66.3 MB. **Partly reverted:** the texture pass does need `astc_encoder`, `ooz`,
  `texture2ddecoder` and `archspec` after all, so those four came back in
  `docs/features/texture-translation.md`. The scan was right about `wxq_patch` — the need is in the
  new pass, not the runtime.
- Two initial verification failures (embedded-certificate mismatch, debuggable attribute "missing")
  were defects in the *test fixtures*, not the product: an APK v2 certificates field needs a second
  length-prefix unwrap, and AXML requires resource-map entry *i* to name string-pool entry *i*. A
  failing check is worth re-reading before it is believed.
- Review left four non-critical findings, all pre-existing or inherited from the sibling rather than
  introduced here: (a) `patcher_core.push_translation` pushes every numeric directory under `staged`,
  so a package skipped via `report is None` could still have leftover files pushed to the phone;
  (b) `install_btree_slot_map()`'s wrapper signature is `(self)` while the stock method is
  `(self, wanted=None)`, safe only because `wxq_patch.pipeline` — its only 1-arg callers — is
  unreachable from this app; (c) `--selftest` opens its log file before redirecting stdout, so a
  missing output parent exits a windowed exe silently; (d) the relocated `apply_device_patch.sh`
  computes `ROOT` one level too shallow. Re-check (a) and (b) if the app ever adopts the PC-side
  pipeline.


## 2026-09-29 — resource-token expansion: three independent reviews

Read-only adversarial reviews (T7, T11, T13) of each round of `tools/resource_tokens.py`; their notes lived
under the retired `tasks` folder and were folded here on 2026-10-16. Corpus throughout: the 87 pre-fix
replacement assets of session `20260929-212059` (3067 `{Energy}` + 451 `{LordExp}` + 608 `{LordHp}`), since
pruned. Every round's verdict was **no critical finding**; the results the feature record does not carry:

- **First rule (`7cada8e..149e25e`).** A framing-only rewrite (parse and re-encode every length prefix, no
  substitution) is byte-identical on all 87 assets, so the corpus has no non-canonical varints. Error paths:
  field 0, wire types 3 and 6, a truncated varint, an overrunning length and truncated fixed64/fixed32 all
  raise `NotMessage`; 15 levels of nesting still expand, 20 do not (the depth-16 cap). Exactly one nested
  sub-message fails to walk and is left as is (`EBB4B2DDCD3E736F`, field path `[1,2]`, 1793 bytes, no
  tokens), so an asset can be partly expanded. `read_bytes`/`write_bytes` sat outside the hook's `try`, so
  an `OSError` still propagates: only a parse failure is contained.
- **Spacing amendment (`cc60205..b670d90`).** Of 4126 token sites, 2595 follow a letter, digit or `}` and 440
  precede a letter or `+`; all are spaced, and a second pass changes none of the 3384 strings. The cited
  `Energy-` evidence did not exist (`Energy +2` and `Energy-2` both 0×). Latent gaps, all 0× in the corpus: a
  following digit (`Energy5`), a non-ASCII letter, `%`, and brace-nested `{{Energy}}`, which is not a fixpoint.
  The rebuilt exe's `run3` was byte-identical to the source `run2` on all 87 assets.
- **Sign rule (`b670d90` + working tree).** All 165 token-side sign sites are followed by `{` or a digit, and
  none of the 464 catalog ` +{` / ` -{` sites follows a token, so the citation is independent. 67 sites keep a
  closing tag between term and sign (`{LordHp}</color>-10.`), which the one-character lookahead cannot reach;
  the catalog's own token-free text glues signs after a tag 56× (`</color></a>+10.`), so this was recorded as
  a convention collision, not a defect.

From the feature record's journey log (folded here 2026-10-16):

- **The oracle.** Session `dist\HOK ACE Patcher Data\sessions\20260929-212059` held both the game dump and a
  pre-fix `build\scan\replacements` tree: a bit-exact oracle (the 3067 + 451 + 608 tokens, reproducing the
  3384-field result). `Patcher.prune_old_sessions` (keeps the last two) deleted it during the install runs;
  the built outputs under `D:\hok-verify-tokenfix` are what survive.
- **An already-patched install cannot be re-patched by the normal flow.** `adaptive.scan` over the phone's
  patched data reported `already_english` 125408 against 2304 on the clean dump, staged nothing, and
  `build_patch` returned no packages, so the expansion had nothing to act on. The install pushed the shard
  built from the clean dump instead.
- **Grepping staged `*.db` shards says nothing about coverage:** the blobs are neither raw nor zlib/gzip, and
  they keep superseded container data (207 raw token bytes, all inside blocks byte-identical to the pre-fix
  build). Coverage is judged from `build\scan\replacements`.
- **The copied spacing rule** (space only before a digit/placeholder and before `+`) left 319 strings with
  the term glued to a word (`IfEnergyis negative`); it had been verified only as "the tokens are gone".
- **The `Energy-` citation.** It read `Energy-` 69×: 66 are `Energy-Saving`, 1 `Energy-saving`, 1 `Energy-G…`,
  and 1 a real glued sign. The catalog writes ` +{` 441× and ` -{` 23×, signs with a leading space, so the
  first rule spaced all 66 sign sites the wrong way until review re-counted the literal.
- **Build hazards.** `build_exe.py` runs PyInstaller with `--noconfirm` against `dist\`, where the app's
  ~7.5 GB working folder lives, and cannot replace the exe while the app runs (`PermissionError: WinError 5`
  in the final assembly). The folder was once moved under a live app; caught at once and reverted, nothing
  written.

## 2026-09-30 — texture port: the checker, the installer and the runtime

From the texture-translation record's journey log (folded here 2026-10-16). Dump: the already-patched
`dist/HOK ACE Patcher Data/sessions/20260929-224052/game`.

- **The installer pushes directories, not the summary.** When the drop loop runs out, `report` stays `None`
  but the last failed attempt has written `output/<id>/`. For package `1` that was a structurally valid
  package the size of its source with 1 of its 15 replacements applied; only `packages == []`
  short-circuiting the install kept it off the phone, and adding graphics entries would have shipped it.
- **Two of the new checker's three "failures" were its own.** It read only the first chunk of each asset,
  so the three multi-chunk 1024x1024 textures (1 048 576 B at 4x4 across four chunks) looked unresolvable,
  and it asserted the untouched-block invariant on `.assets` full replacements, which rewrite every byte.
- **The runtime cannot read the textures it patches.** `qtsvfs.QtsPackage.extract` raises `Unsupported
  compression 4` for Oodle (the scan's 612 `unreadable_assets`), so `native_verify._verify_structural` is
  unusable; reading the staged package back through its own B-tree verified all 299 textures of package
  `15` in 0.1 s.
- **`wxq_patch.adaptive`'s own graphics path is dead here.** An instrumented scan of the dump recorded 0
  calls to `apply_graphic_payload`, and `counts["graphics"]` stayed 0.
- **A frozen-exe timing anomaly, pre-existing.** `--selftest` against the reused session directory took
  over 560 s at about 2% CPU against 27–50 s elsewhere; a byte-identical fresh copy of the tree finished in
  40 s, and the base commit's exe reproduces it. Traps: a `--windowed` exe launched with `&` returns at
  once and its orphan competes with the timed run; an empty log proves nothing, because `selftest`
  redirects stdout to a block-buffered handle.

## 2026-09-30 — text drop report: the loss is at staging

From the text-drop-report record's journey log (folded here 2026-10-16); the drop counts are in §7.

- The chessplayer names were never a catalog gap: the catalog maps 瑶妹→Yaria, 白歌→Bai Ge, 姜导→Director
  Jiang, and the runtime translates every occurrence of each.
- Not chased: which record the Chessplayer screen actually renders, which needs the game's own code or a phone
  experiment. (The prime layer later answered it, §4.)
- `git worktree add` was blocked by that session's sandbox, so the branch was cut in place after committing
  the in-flight texture work.

## 2026-09-30 — prime rebuild: what the build measured

From the prime-rebuild record's journey log (folded here 2026-10-16); the device round is §2, §5 and §9.

- **The handoff's figures did not survive measurement:** override package `1` 26.8 MB per the handoff,
  29.3 MB on disk; 2494 prime-only per the handoff, 2492 counted.
- **`QtsPackage.entries` over-reports a rebuilt package:** 703 against 701 real entries, because the dropped
  builder records stay as dead space in the index. Count assets through the B-tree.
- **`56077AC5D3F0B677` declares fewer bytes than its stream holds.** The rebuild carries the stream whole
  and records what it carried.
- **A rebuild that staged nothing came from an already-patched dump:** `unreadable_assets: 701`,
  `translated: 4`, `already_english: 260426` against a pristine dump's `2303`.

## 2026-10-01 — package 21 rebuilt, read and withdrawn

From the prime-rebuild record's journey log (folded here 2026-10-16); the device result and the later
re-measure are §8.

- **It was left out on the wrong number.** The APK copy is 511 MB, but a rebuild lays out the downloaded
  copy: 4866 assets, 40.7 MB in, 48.1 MB out, 101 s. The reader was what refused it: `read_raw` dispatched on
  the compression id, which is 9 for 1285 of the 4866 entries. Across packages `19`, `20` and `21`, id 9 is
  LZ4 block data behind a 12-byte-longer descriptor: 62 of 62 sampled chunks decoded to their declared
  size, while id 4 (Oodle) refused LZ4.
- **Framing is per chunk.** Twelve assets of package `21` hold Zstandard frames; `7CCE483D88B236CF` is an
  LZ4 chunk followed by a zstd one, and three of the twelve declare id 1 or 4 while holding zstd.
- **Entries without bytes.** `B85AF970632CE322`, `C9ABDBDE9643A78C`, `CDE7C688F1E0185A` and
  `E5FBCD1C777EB18E` have no chunks in either layer; one used to abort the package. Left out, `21` rebuilds to
  4863 assets with 1 translated from the APK, and the pipeline went from 128 s to 219 s.
- **On the phone:** 4863 assets, 48.7 MB, mounted, the panel read back English and the English ribbon was
  seen; Yixing drew as the placeholder (§8). At the time the trigger was unidentified: the 3470 comparable
  entries were byte-identical and no asset named the card in text, which left the four dropped entries, the
  two u32 flag words `finalize` restores, and the descriptor layout. §8's re-measure supersedes that.

## 2026-10-01 — prime-only append: the first runs

From the prime-only-append record's journey log (folded here 2026-10-16).

- **A re-run duplicated the panel's index and shard B-tree key.** `QtsPackage.entries` is keyed by file
  hash, so the duplicate showed only as two offsets under one key in the tree.
- **The row-checksum guard's first reading was taken on our own output.** "The four validated assets are
  unguarded" came from `hok-device-cycle/phone/`, a snapshot of our patched build (since deleted), and our
  rewrite invalidates a bin's stored MD5. On a freshly pulled layer all of them answer true.
- **The pristine download layer the earlier cleanup deleted was recovered from the phone** in one `tar`
  stream over `run-as`.
- **The blast radius was one package** on that build, because the other two holding prime-only catalog
  content were rebuilt whole.
- **A vacuous assertion.** `t7_rerun.py` asserted `"21" not in packages or packages`, which is always true;
  review caught it. The real property is that the second run reports `21` not at all.

## 2026-10-01 — extra-text cycles made one variable

From the extra-text-cycles record's journey log (folded here 2026-10-16).

- **The knob first reached `plan_package` only.** The extra-text pass skipped the packages a rebuild
  replaced, package `1` among them, so a candidate enabled there alone was invisible. With `make_transform`
  wired too, package `1`'s `replacement_count` moves 392 → 393 per cycle.
- **A failed log capture is not a failed run.** PowerShell refused the log path (its parent did not
  exist) but the process still staged; the next run into that directory found the appended asset already
  there and correctly reported no `21`.
- **The note's hashes are prefixes.** 14 of the 15 eight-digit forms are prefixes of package `1` assets,
  and `3F4DD9B1` is in package `4`.
- **`rewrites` and `official` differ:** a label repeated across rows counts once for coverage and several
  times for rewriting.
- **`3F4DD9B1D383FD83` is reachable:** `plan_package` selects it, so package `4` has no multi-shard problem.
  It stays out of the queue because package `4` writes through `write_assets`, which does not read its
  write back (§5).

## 2026-10-02 — a cycle staged from an older game-data version

A cycle staged from the 1.4.0.1 `artifacts/game-dump` went onto a phone running 1.4.0.2. A staged package
is a revision of one layer, so the push reverted every asset the game had changed in between, among them a
34 KB Chinese config bin and a 13.5 KB English one. The load stopped at 0% and the game repaired itself
with a download, removing the translation; the cycle gave no verdict on the asset it was testing. The
same day a patch staged from the phone's own version launched and read English. Since then the dump's
`1.info` is compared with the phone's before a push (`docs/runbooks/device-cycle.md`).

The detail, from the extra-text-cycles record's journey log (folded here 2026-10-16): the candidate was
`3914DBBFECD1E54D`, pushed from `artifacts/cycles/3914DBBFECD1E54D/out`. Against a backup taken before the
push, the reverted assets were `9F3227B6D2226784` (34 832 B, 512 CJK either way), `0A3F6BAF53C9CA9D` (13 505 B,
English either way) and the builder's bookkeeping nodes. A 44-byte label table is no startup dependency, so
the stall says nothing about the candidate. Re-staged from the pristine 1.4.0.2 package `1`, the same cycle
differs from the phone's baseline in exactly three assets: the candidate and the two bookkeeping nodes.

## 2026-10-03 — Talent Card regression isolated and fixed

The former impossibility verdict was wrong. A fresh redownload (data 1.4.0.2; snapshot
`dist/HOK ACE Patcher Data/pristine/20261003-173730`, 653 files SHA-256 verified) draws the
grid's Chinese names. Reverting one dictionary while retaining other patched assets was
not a pristine control. Do not reuse that verdict.

Ruled out before the fresh baseline. Config `0AA59370241BFC22` was rewritten for 1811 of its
4064 refs, then for all 4064, re-pointed at `23C9A9DEBB3BF40C`; both kept 409,893 bytes and
chunk size 307200, and both emptied the grid. Changing the config also invalidated its stored
checksum, so the cycles cannot say whether the client rejects the namespace or the checksum.
Do not repeat either rewrite. The table-only revert reverted `C059EA43719099F1` (all 4064 refs)
but left the appended `A646ADD1CA0C1563` (3069 refs, APK prime) and the rest of the stage
installed, which is why it could not show that the client reads neither table. Arena Tiger
`#BE08801F0222C56A#`: `C059EA43719099F1` holds `擂台猛虎` in the pristine downloaded and APK
copies and `Arena Tiger` in the stage; `A646ADD1CA0C1563` still defines it as `Tiger in the
ring`, unchanged in the stage; config row `6363121`, field 4, references the key identically in
all three copies (`artifacts/device-cycle-t10/arena-tiger-check.json`; 403 pristine, 700 staged,
2873 prime entries, zero decode failures).

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
append refusal. Talent Card fix complete; no commit.

**Review and cleanup:** removed 18.1 GiB of obsolete generated artifact outputs, retaining
fresh controls, original APK/source dumps, final fixed packages, screenshots, reports and
reusable probes. See §12's local artifact retention; old full candidate builds must be restaged
from the phone's version. Normal build code now initializes Tencent DLLs only when a rebuild
package is named. With `REBUILD_PACKAGES=()`, an APK plus an absent builder directory passes
the old-package repair check. Graphics offline checks pass.

**The cycles in detail**, from the prime-only-append record (folded here 2026-10-16); scripts and evidence
under `artifacts/device-cycle-t10/`:

- **Arena Tiger's config row.** Field 4 of row `6363121` in `0AA59370241BFC22` sits beside
  `$/BP/BP_636312.gl` and `ArtHub/Icon/Talent/Icon_Talent_ltmh`; checked with `check_arena_tiger.py` (two
  entries without local bytes in each downloaded or staged copy). No device package was changed for it.
- **Fresh baseline.** `pull_pristine.py`, after the user redownloaded and the game reached its Chinese login
  screen: package `1` at version `1.4.0.2`, revision `0`; 653 package files across 252 directories SHA-256
  verified against hashes taken on the phone; archive 2.53 GiB. The installed APK matched the cached normal
  APK by SHA-256 before the access install. `compare_fresh_package.py`: all 401 readable assets
  byte-identical to the previous package-1 dump (two entries without local bytes in both); against the
  previous stage 307 identical, 94 differ, 297 only in the stage.
- **UI control:** all 24 visible Talent labels Chinese (`节能商店`, `日落海新援`, `复印机` among them) and the
  detail pane Chinese (`detail-captures/pristine-talent-grid.png`).
- **`translated-map`** (only `C059EA43719099F1` replaced; 403 entries, 4064 keys in order, no duplicates):
  **fails**, all 24 labels raw `#BE08...`, tabs and detail pane Chinese. No append and no extra-text in it.
- **`one-name`** (only Arena Tiger's value, 277,697 B, one byte under the original): **works**; the tile
  reads `Aren...`, the detail `擂台猛虎`.
- **`append-legacy-map`** (appends only `A646ADD1CA0C1563`): built, never pushed.
- **Full baseline offline** (`grid-regression/full-baseline/`, APK, no builder): 79 tables in place, 11
  relocated, 4 allowlisted extras, 297 appended to package `1`; 395 textures; the one refusal
  `3A70308AAF6F18F8`. Not pushed.
- **`two-chunk-map`:** **works**; all 24 labels English (`Copier`, `Piggy`, `Duality`, `Prophet`, `Milestone`,
  longer names clipped), the other 401 readable assets unchanged.
- **Fix verification** (`grid-cycles/fix-verification.json`): 700 package-1 payloads byte-identical to the
  baseline English build; a rerun on the fixed package stages nothing. Frozen-exe `--selftest` on fresh data:
  79 in place, 11 relocated, 4 extras, 323 downloaded textures (no APK given).

**Android exposed an invalid synthetic fixture**, from the texture-translation record (folded here
2026-10-16). `check_graphics.py` filled its synthetic ASTC buffers with ramp bytes that are not valid ASTC
blocks; the ARM64 decoder crashed in `decode_intseq` / `decode_endpoints` at check 5, in a fresh process too.
With `device_bytes` encoding a known opaque background, the full `--game` check passed on Windows (130.4 s)
and on the Xiaomi Android 12 ARM64 spike (120.9 s; instrumentation 121.807 s): 321 ported, 1 replaced, 1
spliced, 0 skipped. It fixes the fixture only, and says nothing of decoder safety on malformed input.


## 2026-10-03 — Android Shizuku port: feasibility spike (records through 2026-10-05)

Moved from the android-shizuku-patcher record, where it was the Report's evidence. The table and the
paragraphs after it accumulated from 2026-10-03 to the 2026-10-05 live patch; rows keep their own dates.

An Android feasibility application has been built and installed alongside the Windows patcher.
On the Xiaomi M2007J3SG / Android 12 phone, the Shizuku UserService runs as UID 2000 in
`u:r:shell:s0`, discovers the unsplit game APK, and round-trips 4096 random bytes through a
disposable debuggable fixture. An ordinary patcher process receives EACCES when trying to
execute `run-as`. Shizuku authorization was granted by the user. The separately authorized
live-game diagnostic installed the access APK and read version 1.4.0.2, round-tripping 4096
temporary bytes as the game UID. No translation packages or Watchdog contents were changed.

The user separately authorized copying the pristine dump and matching normal APK into the
feasibility app's private scratch storage. The full DLL-free engine completed a build there,
with Python 3.12.12 and all five codec imports loading. The corrected full graphics oracle
also passed; its original malformed synthetic ASTC fixture caused a native decoder crash.
The staged asset comparison passed its numerical checks. The first normal-APK restore timed
out under the diagnostic's 30-second deadline; USB fallback restored the exact normal APK,
verified by streaming/hash and a cleared debug flag. The retry with 180-second installer
write/commit deadlines passed in 132.245 s, including normal APK hash/signature/debug checks.
The restored game reached its main lobby with the pre-existing English UI. Full coordinator
orchestration now passes private-scratch success and rollback tests with simulated installation
and game transport. The 2026-10-05 cycle (lab notebook, 2026-10-05) confirms normal-path live coordinator completion. Deliberate interrupted live-package recovery and release acceptance remain open.
The development UI offers an explicitly confirmed patch request for converted installs, now exercised against live game data. First-setup consent, foreground dispatch,
installation recovery and a fresh-update checkpoint are connected; actual first-official
conversion and release acceptance remain unfinished. Android-generated translation was applied in the successful 2026-10-05 cycle (lab notebook, 2026-10-05); its remaining visual/device gates stay open.

### Implemented spike and observed results (2026-10-03)

| Check | Observed result / evidence |
|---|---|
| Quantified low-storage guidance | Six host JVM checks pass (`artifacts/android-storage-message-build.log`, `android/app/build/test-results/testDebugUnitTest/TEST-dev.halixm.hokacepatcher.StorageMessageTest.xml`). Existing exact byte failures now render required/current/additional decimal GB, rounding required up and free down to 0.1 GB. Additional clearing advice is the difference of displayed values and never understates the measured deficit. Main screen refreshes current usable space and switches to retry advice once sufficient. Legacy saved byte messages, latest recovery shortage, tiny deficit, locale, invalid/unknown amounts and Long.MAX_VALUE/overflow refusal are checked; one test forces the real unchanged budget guard to refuse without allocating files. Unknown installer thresholds stay explicitly unknown. Byte thresholds, recovery reserve and files are unchanged; no live low-space patch/uninstall test. |
| Launcher branding and package identity | PASS: full-codec app/test compilation (`artifacts/android-launcher-branding-build.log`); renamed app installed as `dev.halixm.hokacepatcher`, launcher label **HOK ACE Patcher**. SDK badging and compiled XML/resources verify adaptive icon, foreground inset and exact `#ff9ebef7` background (`artifacts/android-launcher-branding-*.txt`). Attached foreground copy is byte-identical; packaged alpha and visible RGB pixels match the original. Installed APK SHA matches `artifacts/dev.halixm.hokacepatcher.apk`; receipt `artifacts/android-launcher-branding-receipt.json`. Old app remains installed with its recovery data; no migration, old-app uninstall or game operation. Home Test version badge removed. MIUI canceled the optional renamed test-APK install with INSTALL_FAILED_USER_RESTRICTED, so the focused device-resource instrumentation did not run; compiled-resource and installed-byte checks were used instead. |
| Automatic UI routing | PASS: final full-codec build (`artifacts/android-automatic-ui-final-build.log`), eleven actual checks in 24.903 s (`artifacts/android-automatic-ui-final-probes.log`). Seven routing/token checks cover emergency priority, interrupted patch/setup selection, ambiguity refusal, clean-state preparation and stale/live/unknown result refusal; actual home checks confirm voice/checklist/tutorial controls are absent, technical logs remain collapsed and large buttons survive recreation. Original patch-update and two first-setup consent gates still start unchecked; Cancel creates no requests. Read-only foreground verification survives activity recreation, independently verifies the retained/installed normal APK and echoes the exact request UUID; actual service retirement is confirmed before continuation. App-only view render `artifacts/android-automatic-ui-home.png` (window overlays excluded), identities/result receipt `artifacts/android-automatic-ui-final-receipt.json`. Initial read-only retry stopped because Shizuku was not running, with its flow token retained (`artifacts/android-automatic-ui-probes.log`); user restarted Shizuku before the passing final run. Only development/test APKs installed. No automatic live patch, uninstall or game data writes exercised; complete automatic live cycle and actual permission-dialog/revocation behavior remain separate acceptance gates. |
| Guided UI and consent (earlier UI, superseded by automatic flow) | PASS: full-codec debug build (`artifacts/android-guided-ui-build.log`) and three actual Xiaomi UI probes (`artifacts/android-guided-ui-probes-final.log`). Home hides technical logs, offers a large next action, visual phone/copy/English illustration, optional English speech, expandable checklist and recovery; step help navigates Back/Next. The real patch-update checkbox and separate first-setup data-loss/login checkboxes remain initially unchecked and gate positive buttons; cancelling creates no requests. Activity recreation preserves this behavior. Actual home/help screenshots were inspected (`artifacts/android-guided-ui-home.png`, `artifacts/android-guided-ui-help.png`); initial oversized help illustration was corrected with a fixed 80 dp height, and help scrolls for larger text. Only development/test APKs installed; no game mutation or live-patch acceptance. English voice output, TalkBack, large-font/OEM matrix and usability with low-literacy participants remain unmeasured. |
| New-platform harness and current-device control | PASS for harness/current 4 KiB device, not Android 15/16 KiB acceptance. `tools/research/check_android_platform.py` records specific model/API/ABI/page-size properties, validates fixed development APK package names, runs static native inspection, and matches actual installed development APK size/SHA to the inspected build before two codec/import/frame/font tests. Current control `artifacts/android-platform-harness-identity-xiaomi-control/report.json` passes on M2007J3SG / API 31 / arm64 / 4096-byte pages; no installation, game access or Shizuku change. Both codec checks pass and all packaged native alignments are inspected. The first control without installed identity binding is retained separately; final harness adds that required provenance check. User reports the Android 15 PixelOS phone is unavailable now; its actual properties, physical 16 KiB loading and newer worker acceptance remain open. |
| Authorization restored / independent normal verification | PASS, one read-only foreground/Activity recreation test in 14.741 s (`artifacts/android-worker-permission-restored-probes.log`). After the user re-enabled HOK ACE authorization, a fresh worker verifies full installed normal APK SHA `b0b08f...fc0a`, expected signer/version and cleared debug flag, without installation or game-data writes. Normal verification status remains visible after Activity recreation. This closes the denied-permission probe's temporary authorization change; no test emergency intent remains. |
| Actual denied Shizuku permission / foreground refusal | PASS, one test in 1.717 s (`artifacts/android-worker-permission-denial-probes.log`), prepared build `artifacts/android-worker-permission-denial-build.log`. User disabled only HOK ACE authorization while Shizuku stayed running. Probe directly checks denied API permission and dispatches only read-only normal-APK verification. Foreground result is error with `Authorize HOK ACE in Shizuku before starting`; no verified/completed result and raw base/backup emergency records remain byte-identical. Receipt `artifacts/android-worker-permission-denial-receipts.json`. No game writes or installer call. User has been asked to re-enable authorization; successful post-enable retry is not yet recorded. This is denial before binding, not revocation during patch/apply. |
| Connected foreground verification / own UserService loss | PASS, one actual test in 17.905 s (`artifacts/android-worker-service-loss-guidance-probes.log`), final build `artifacts/android-worker-service-loss-guidance-build.log`. Waits for the worker's connected verification progress, validates a unique UID-2000 process named `io.github.hokace.patcher:worker`, then stops only that process (PID 18576). The resulting `DeadObjectException` produces error status with a nonblank recovery instruction and preserves the seeded emergency request as verification-pending. A fresh worker connection independently verifies retained and installed normal SHA `b0b08f...fc0a`, actual signer/version/non-debug state, then resolves the same request. Case `6437a9bc-f8b4-40b9-a390-918ad182925f`; receipt `artifacts/android-worker-service-loss-guidance-receipt.json`; no test intent remains. No APK installation, game-data writes, Shizuku-server stop or permission changes. Earlier connected-stage test passed in 19.056 s but exposed a blank error; the worker now preserves exception type and a plain fallback explanation. |
| Foreground probe availability and initial interrupted setup | Initial test FAIL, 21.656 s (`artifacts/android-worker-service-loss-probes.log`): Shizuku was already stopped, no service process was killed, and the seeded read-only verification request remained pending. Probe now checks binder availability/authorization before seeding intent. After user restart, strictly owned read-only recovery PASS in 15.585 s (`artifacts/android-worker-service-loss-owned-recovery-probes.log`), independently verifying the unchanged normal APK before removing its resolved test intent. A subsequent pre-connection own-service kill passed in 38.904 s (`artifacts/android-worker-service-loss-ready-probes.log`) but produced a connection timeout, so it is not proof of connected service loss. These receipts are retained separately in `artifacts/android-worker-service-loss-receipts.json`. Connected-stage evidence is recorded above. |
| Fresh Shizuku fixture recovery after security-setting confirmation | PASS, one actual test in 11.235 s (`artifacts/android-fixture-installer-security-enabled-probes.log`). User confirmed MIUI USB debugging security option and Install via USB enabled. Fixed fixture uninstall, actual UserService death/reconnection, refusal of a truncated APK stream, fresh session installation and fixture binary round-trip all pass. Session `1977819978`; case `09c12d73-55e6-428b-832c-677aea1aa073`. Host independently streams the installed APK: exact original 12,365 bytes and SHA `1f77892b2142758937113d0522180e6434c27108d4f4f13bc262ecb36d12970d` (`artifacts/android-fixture-installer-security-enabled-receipts.json`). Fixture remains installed. Earlier rejected cycles remain failures; this passing run does not establish which setting or prompt timing caused them. No live game or translation packages targeted. Shizuku-server death, full worker recovery and first-official conversion remain separate gates. |
| Attended fixture retry and USB rescue | PARTIAL. Initial USB restoration succeeds in 4.222 s; installed 12,365-byte APK independently matches SHA `1f77892b2142758937113d0522180e6434c27108d4f4f13bc262ecb36d12970d` (`artifacts/android-fixture-installer-attended-restored.json`). Fresh Shizuku/service-loss retry still fails in 31.923 s, including finally restoration (`artifacts/android-fixture-installer-attended-probes.log`); the user explicitly reports accepting the prompt. A USB rescue request did not execute because automatic approval review timed out; its once-authorized retry succeeds in 3.977 s (`artifacts/android-fixture-installer-attended-fallback-retry.log`). Installed fixture is restored and independently matches the same SHA (`artifacts/android-fixture-installer-attended-fallback-restored.json`). No further uninstall cycle until MIUI's additional Shizuku permission setting is checked. The [official Shizuku manual](https://shizuku.rikka.app/guide/setup/#start-via-wireless-debugging-start-by-connecting-to-a-computer-the-permission-of-adb-is-limited) recommends the separate USB debugging security option on MIUI; this recommendation does not yet prove it resolves the measured installer rejection. Game was never targeted. |
| Diagnostic export with damaged recovery records | PASS; final build `artifacts/android-diagnostic-export-final-build.log`, eighteen combined private checks in 1.852 s (`artifacts/android-diagnostic-export-final-private-probes.log`). Export no longer loads journals or invokes AtomicFile recovery: base and backup are separate unvalidated records with exact Base64 bytes and exported SHA-256. Corrupt binary records remain byte-identical after export and still block journal loading. Links, oversized records and missing published journals are explicitly reported; valid unpublished initialization remains excluded. Tests exercise the 1 MiB record cap, 8 MiB total raw-byte cap, 256-entry cap, 256 KiB log tail and propagation of destination failure. UI uses this writer for the user-selected document. Actual SAF completion was not exercised by these private checks; no game/fixture mutation or recovery acceptance is claimed. |
| Emergency APK selection with damaged transaction records | PASS; build `artifacts/android-emergency-choice-build.log`, nine private checks in 0.150 s (`artifacts/android-emergency-choice-private-probes.log`). If patch/setup discovery throws, UI requires an explicit retained-APK selection. Normal metadata filters candidates; selection is not content verification. The selected file still passes `RecoveryStore.verify` before installer confirmation and the existing provider gate. Damaged published journals are untouched; no completion/launch permission is granted. Pending emergency intent takes precedence; damaged emergency intent cannot be replaced by fallback. Private probes reject dummy APK bytes, access/linked candidates and empty fallback. No installer opened or game/fixture mutated; actual external-installer acceptance remains open. |
| Fixture update retains data | PASS, one actual Shizuku replacement test in 3.124 s (`artifacts/android-fixture-replacement-ready-probes.log`). No uninstall; the fixed fixture target retains its marker, which is then cleaned. Installed APK read-back exactly matches the original 12,365-byte SHA `1f77892b2142758937113d0522180e6434c27108d4f4f13bc262ecb36d12970d`; receipt `artifacts/android-fixture-replacement-receipts.json`, session `381535829`. This verifies replacement of an existing fixture, not fresh installation or live-game recovery. |
| Fresh fixture installer prompt follow-up | PARTIAL. Subsequent fresh-install/service-loss cycles still report `INSTALL_FAILED_USER_RESTRICTED`, including their finally restoration (`artifacts/android-fixture-installer-unlocked-probes.log`, 31.922 s; `artifacts/android-fixture-installer-prompt-accepted-probes.log`, 31.792 s). The user confirmed missing/rejecting an earlier prompt; immediate USB restoration then succeeded in 4.203 s and installed bytes independently matched the original (`artifacts/android-fixture-installer-prompt-usb-restored.json`). The later filename containing `prompt-accepted` does not prove prompt acceptance. Later USB restoration attempts, including `artifacts/android-fixture-installer-missed-prompt-restore.log`, were rejected again. At this observation the fixture remains absent and restoration is awaiting an attended prompt. No further uninstall cycle is permitted before exact restoration; the live game was not targeted. |
| Desktop control | Git `982130dce99db7f77c0c087830b2b20f23d2033e`; Python 3.12.13; fresh data 1.4.0.2, snapshot `dist/HOK ACE Patcher Data/pristine/20261003-173730`; all 653 source files rehashed against the snapshot |
| Matching normal APK | SHA-256 `b0b08f4a77244d990ea22e4fbde73542028b4b5785d88243b62ac907fbe3fc0a`; stable game certificate verified, debug flag false; recovery file retained |
| DLL-free desktop build, no cycle assets | PASS; 391 staged text tables, 395 applied textures, one skipped prime table, no skipped textures; six numeric package directories match the unique reported IDs |
| Talent control | PASS; 313710 raw bytes, chunk size 307200, two chunks keyed `15A33357ECBFA5CC` and `29157589AC92F155`; raw SHA-256 `7ffab50754b00a1a4f78fcc8b7b97a473781db8e67dbffc88989b98883454b2c` |
| Windows graphics oracle | PASS, catalog-only 86.9 s; same pristine `--game` run 104.4 s, 321 ported + 1 replaced + 1 spliced, zero skipped; the 75 absent entries here refer only to downloaded data |
| Android build | PASS; Gradle 8.9 / AGP 8.7.3 / Kotlin 2.0.0 / Chaquopy 17.0.0 / Shizuku API 13.1.5, ARM64, minSdk 30, compile/targetSdk 35 |
| Installed Shizuku | 13.6.0.r1086.2650830c; started as shell; binder authorization and AIDL binding measured |
| Device boundary instrumentation | PASS for shell UID/context, game APK path/size, fixture binary round-trip and ordinary app denial; descriptor-streamed installed APK matches the control SHA-256; fixed force-stop leaves no game PID. Live-game access/restore sessions passed after the measured timeout fix |
| Fixture installer session | PASS; 7333-byte fixture replayed through create/write/commit, installed hash `e6cd8618fc78842a737d762725e1c34ef8ab993c18ef0ac58b5b77fa13002221`. Explicit session abandonment rejects subsequent commit, preserves installed APK hash/path and binary round-trip. Combined codec/install/abandon/binder probes pass in 8.761 s |
| UserService death | PASS; death callback clears the connected service and the retained binder rejects a new diagnostic call. Isolated 2.467 s and combined probes pass; this stops only the app's own service, not the Shizuku server |
| Android engine imports/core operations | PASS; Python 3.12.12 / `aarch64`, bytecode magic `cb0d0d0a`, 499 catalog tables / 398 texture edits; Android LZ4 wins resolution; real LZ4 and Zstd round-trips pass; Oodle, ASTC and texture decoder imports load |
| Published Maven source/notice follow-up | PASS for artifact inventory, not release clearance. After user continuation on 2026-10-05, all seven matching POM/source-JAR sets download from Google Maven or Maven Central (`artifacts/android-maven-sources/manifest.json`). Auditor rechecks selected binary hashes, published source size/SHA/CRC, equality with six cached POMs, and the seventh JetBrains annotations 13.0 POM declaring Apache-2.0 (`artifacts/android-maven-published-source-inventory.json`). No metadata gaps remain in these seven candidates; modified source is refused (`artifacts/android-maven-source-refusal.json`). Original source-header notices are retained; source identity is distinct from reproducible binary/source equivalence. Expanded companion includes six native sources, seven Maven source JARs and POMs, recipes/notices/provenance, CRC and exact read-back (`artifacts/android-codec-maven-source-companion.zip`). Final debug build and engine extraction/full-codec import PASS, one test in 2.150 s (`artifacts/android-maven-notices-engine-probes.log`). APK audit finds twelve Python distributions, thirty notice/provenance files and eighty-four unchanged native payloads (`artifacts/android-maven-notices-apk-inventory.json`). Broader embedded-runtime/native source inventory, manual notice completeness, application/runtime/catalog distribution and combined redistribution review remain open |
| Resolved Maven runtime inventory | PARTIAL; Gradle task PASS (`artifacts/android-maven-runtime-inventory.log`), seven release-runtime candidates recorded with size/SHA. Offline audit revalidates all seven actual cached binaries (`artifacts/android-maven-runtime-notice-inventory.json`): four Shizuku 13.1.5 POMs declare MIT; AndroidX annotation 1.3.0 and Kotlin stdlib 2.0.0 declare Apache-2.0. JetBrains annotations 13.0 has no cached POM and remains unresolved. None of the seven artifacts or AAR classes JARs embeds a license/notice. Exact source provenance and notice completeness remain open; annotation classes may not be packaged, and Chaquopy plugin-injected/runtime native components are separate. Attempted matching source-JAR/POM downloads were not executed because automatic approval review failed on an out-of-credits workspace; the failure is not a safety rejection, and no alternate route was used |
| Packaged notice/source inventory | PARTIAL; final debug build PASS; actual APK audit inventories twelve Python distributions, twenty-nine notice/provenance files and eighty-four native payloads (`artifacts/android-dependency-notices-final-inventory.json`). Native payload hashes are unchanged; final SDK ZIP alignment check passes (`artifacts/android-dependency-notices-zipalign.log`), without implying physical 16 KiB acceptance. Verified engine assets now retain unmodified Python 3.12.12, Chaquopy 17.0.0, Shizuku MIT, Apache/GPL and NDK toolchain notices plus original leading copyright/license comments from the three hash-pinned codec archives. Provenance and explicit scope are recorded in `android/native/licenses/sources.json`; Shizuku text matches the published POM repository URL at an immutable commit, not yet a version-specific source proof. Full-codec extraction/import check PASS, one test in 1.764 s (`artifacts/android-dependency-notices-engine-probes.log`). Six-source companion regenerated with notices, collector/auditor recipes, original archive hashes, provenance hashes, CRC and read-back verified (`artifacts/android-six-component-notice-sources.zip`). Maven/runtime native dependency inventory, manual notice completeness and application/runtime/catalog distribution review remain open; no release clearance is claimed |
| Android native builds | PASS for original pinned Ooz, ASTC scalar/NEON and texture decoder sources, NDK 28.2.13676358, Android API 24, CPython 3.12.12 headers; experimental wheels and SHA-256 report under ignored `android/wheels/` |
| Private scratch copy | PASS; 656 files verified individually for byte length and SHA-256, 174.855 s; session `files/scratch/control-1402-verified/`; game/APK copied only after explicit user authorization |
| Full Android scratch engine | PASS for `EngineScratchTest#testBuildBothLayers`, 121.209 s; each pristine input and APK rechecked against the desktop control, `builder_dir=None`, empty `cycle_assets`, numeric directories reconciled, append read-back preserved; scan counts and four counters exactly match desktop (391 tables / 395 applied textures / 1 skipped table / 0 skipped textures) |
| Staged file comparison | PASS numerical checks; all 12 outputs fetched and SHA-256 verified. Seven files byte-identical, including both package `1` files and all indices. All entries compared in the five differing shards: 59374 readable assets byte-identical, 192 differing catalog ASTC textures, zero unexpected raw differences; 1396 unreadable in both controls remain unverified. Maximum per-image decoded RGBA mean difference 0.0094021/255, maximum individual channel difference 46; no image exceeds the recorded 2.0 tolerance. This does not replace watched rendering |
| Android graphics oracle | PASS after correcting invalid synthetic ASTC input; isolated instrumentation 121.807 s, checker 120.9 s, 321 ported + 1 replaced + 1 spliced, zero skipped downloaded textures. Original and isolated uncorrected runs SIGSEGV in texture2ddecoder's endpoint reader; valid fixture also passes Windows in 130.4 s |
| Windows binaries excluded | PASS; generated runtime omits two Windows LZ4 `.pyd` files; APK inspection finds zero Windows runtime or research payloads. Updated codec/boundary instrumentation passes (4.181 s); source runtime unchanged |
| Prepared live-game diagnostic | COMPILED; user separately approved this cycle. Opt-in `probeGameCycle` verifies APK hashes, package, signer/debug flags, matching versions, installed normal APK hash and storage. Fixed `--pkg` sessions, game-UID temporary probe, unconditional normal reinstall in `finally`, restored hash/signer/debug checks. This diagnostic exposes no translation write/uninstall operation. Binder/process-loss recovery depends on the verified PC normal APK |
| First live-game diagnostic | PARTIAL; 96.549 s. Game-UID probe passed with matching `1.info` and 4096 bytes, then normal restore hit the 30-second command deadline. Authorized USB `adb install -r installed.apk` succeeded; independent stream/hash probe passed (8.287 s), installed debug flag cleared. Installer writes/commits now have bounded 180-second deadlines with progress logs |
| Live-game diagnostic retry | PASS; 132.245 s. Access APK installed, matching `1.info` read, 4096 bytes round-tripped/removed, normal APK restored and streamed/read-back SHA-256 `b0b08f…fc0a` verified; stable signer and cleared debug flag verified independently. Normal session `1479424385` committed. Game PID 3163 remains alive beyond 90 s and main lobby renders; screenshot `artifacts/android-game-cycle-startup.png`. The existing translation was retained; Android staged output was not applied |
| Stable-key Java RSA/v2 signer | PASS; tiny fixture output is byte-identical to the pre-change Windows control (1.997 s), independently verified by SDK apksigner. Re-signing the 2026631918-byte normal APK on Android takes 42.919 s and reproduces SHA-256 `b0b08f…fc0a` exactly. Android archive parser verifies the stable certificate. This exact APK was already installed and launched in the authorized access/restore control. Full private preparation is accepted below; installation of the newly generated access APK remains open |
| Full APK preparation and reload | PASS, one private test in 146.058 s: actual preparer streams the full approved source, preserves existing normal SHA-256 `b0b08f…fc0a`, generates the stable-key access APK, adopts/verifies protected recovery and reloads its durable receipt. All 1625 decoded ZIP entries match a fresh Windows access control; only `AndroidManifest.xml` differs from the normal APK. Android access SHA-256 `593ec269b36bee255bbbd99870e2b070ffd7a5599651be90faca502fec83547b` is independently SDK v2-verified for Android 11+. The archive bytes differ from Windows; decoded payloads match exactly. No Shizuku binding or installation; this tests an already-converted source, not first-official-install conversion |
| Durable recovery primitives | PASS; Android AtomicFile interruption test preserves unresolved mutation/dirty state and rejects completion. Fixed path tests reject traversal, mismatched package IDs and metadata writes. Private snapshot extraction rejects links/unknown paths and detects changed retained originals. Combined instrumentation: three tests, 1.753 s. No game operations in these tests |
| Recovery cache identity | PASS; full normal APK retained under its SHA-256, metadata/content/manifest/signer revalidated, repeat adoption remains identical, access APK adoption refused. On-device private-storage test 99.774 s; no game installation or data operations |
| Installed recovery pipe verification | PASS; 18.743 s combined shell/fixture check. Coordinator independently hashes the installed APK through a bounded descriptor pipe, then checks installed version, certificate and debug flag. Matches exact normal recovery SHA-256 without another 2 GB disk allocation; no reinstall/game data writes |
| Worker binding lifetime and ownership | PASS; debug build and four real binding/foreground checks in 19.973 s (`artifacts/android-worker-binding-probes.log`). Each foreground connection uses a fresh UUID service tag rather than sharing `hokace-worker`; pinned Shizuku API 13.1.5 bytecode confirms the tag participates in both add/remove requests (`artifacts/android-shizuku-service-args-bytecode.log`). Two simultaneously bound worker owners are tested: closing the first twice cannot kill the second; intentional close never emits recovery loss and later await refuses immediately. Actual own-UserService destruction emits one loss notification, later await refuses immediately, and late callbacks cannot resurrect a closed/failed connection. Binder death is monitored independently of whole-server death; loss wakes connection waiters. Read-only installed-normal/Activity recreation and missing-consent foreground refusal still pass. No game install/data operation. This removes a service-ownership reuse risk; it does not prove the earlier intermittent timeout had this cause or establish full server/process/reboot recovery |
| Foreground activity recreation | PASS for read-only verification: WorkerProbeTest completes exact installed-normal verification while MainActivity is recreated; result persists as `verified`. This does not prove process-death, timeout or interrupted live-write recovery. Combined run has one URI consumer failure and one worker pass, 143.062 s |
| Preparation/recovery UI and saved progress | PARTIAL; preparation now runs in the foreground worker; UI polls AtomicFile progress/results after recreation and offers unfinished-session recovery by date. Cancellation checkpoints and unfinished-recovery refusal run before device reads. Two UI/result checks pass in 20.679 s, including exact installed-normal read-only verification and visible recreated-screen result. Two preparation guard tests pass in 0.025 s. Full foreground preparation, cancellation during signing, recovery chooser execution and process/timeout acceptance remain unproved |
| Update checkpoint and patch request | Final combined run PASS, three tests in 30.821 s; missing confirmation, replay, expiry and changed receipts refused. Earlier dialog/source-guard retry also passes, two tests in 14.427 s: Start is disabled synchronously until the update-finished/game-closed checkbox is checked; Cancel creates no request. Wrong-version or official sources are refused before access. Worker patch input is a one-use request UUID bound to verified preparation identities, not arbitrary APK paths. Live patch invocation remains unaccepted |
| First-setup journal and controller | Final private simulation PASS, three tests in 0.209 s (`artifacts/android-first-setup-controller-final-probes.log`), including stricter stored identity/phase validation; earlier controller run 0.206 s and journal-only one-test run 0.078 s also pass. Separate AtomicFile states retain irreversible data-loss consent, uninstall/install intent, verified normal installation and fresh-update wait. Pending setup blocks preparation and translation. Controller uses the translation coordinator lock, verifies cached recovery/source before removal, and independently verifies normal installation before reporting update wait. Lost uninstall/install replies recover without repeating removal; a different installed app is refused. No translation/counts are reported. Tests use dummy identities and a fake installer: no Shizuku binding, uninstall, install or game-data mutation. Fixed production transport now compiles and is verified separately below; consent request/UI is now connected and checked below; first-official conversion acceptance remains unfinished |
| Fixed first-setup transport and guards | Final build PASS; six combined tests PASS in 26.764 s (`artifacts/android-first-setup-no-replace-probes.log`), earlier expanded run 30.426 s. Actual Shizuku checks discover retained game records, parse user profiles and hash the installed full APK; stale source hash, invalid removal identity and first-install over an existing game are refused. Shared independent installed verifier still matches normal SHA-256 `b0b08f...fc0a`, signer/version and cleared debug flag. Removal accepts only a source SHA for the fixed game, rejects another profile carrying the game, and intentionally omits data retention; this valid removal path has not been invoked. First installation uses explicit `-R` and fixed `--pkg`, with cache content verified by the device adapter. Disposable fixture verifies `-R` refusal and unchanged installed hash `1f77892b...12970d`. AIDL protocol bumped to 7; old UserService instances are replaced on binding. No live game mutation; first-official conversion and consent/worker wiring remain unaccepted |
| First-setup consent/UI/foreground wiring | Final combined PASS, nine tests in 36.427 s (`artifacts/android-first-setup-consent-final-probes.log`); earlier nine-test run 30.913 s and six-test UI/request run 17.153 s also pass. Both data-loss and Scan-to-login controls start unchecked; either alone leaves setup disabled, Cancel creates no request. Fresh-update confirmation also starts unchecked and does not start translation. One-use requests bind source/normal/access SHA and the receipt, expire after 15 minutes, reject changed receipts/replay, and cannot begin two mutation attempts. Consumed consent UUID is saved in the setup journal. Request test revalidates the actual private normal/access APKs but uses synthetic unconverted source metadata: no first-official PKI proof. Real foreground dispatch of a nonexistent consent UUID rejects before creating a setup journal; read-only foreground normal verification still passes after activity recreation. Private simulations cover cancellation before removal and refusal with the unchanged original app; terminal lifecycle callbacks do not rewrite completed journals. Setup/recovery/update actions, pending-setup recovery APK selection and journal export are connected. No valid live setup request or translation was started; actual conversion and full lifecycle/installer recovery acceptance remain open |
| Automatic first-setup restore priority | Final combined PASS, twelve tests in 35.995 s (`artifacts/android-first-setup-auto-restore-final-probes.log`); isolated private recovery/journal PASS, eight tests in 0.738 s. Lost uninstall reply triggers normal installation; lost commit reply verifies the already-installed normal APK without another install. A first installer rejection gets one recovery attempt; repeated rejection stops after two attempts total, retains INSTALL_INTENT/normal-unverified state, and later explicit recovery succeeds. Uninstall count remains one. Changed installed app and newly invalid recovery cache refuse further mutations. Cancellation after removal and failed progress callbacks still reach independently verified normal installation. An unchanged original after refused removal terminates safely without claiming local data recovery. Automatic success reports setup_waiting, no translation/counts, and a plain recovery message. Foreground missing-consent refusal, consent/replay checks, UI cancellation and actual read-only installed-normal/Activity recreation checks still pass; exact normal SHA `b0b08f...fc0a`, signer and cleared debug flag verified. Recovery simulations use a fake installer/dummy source identities; no valid live setup request or translation was started. Initial malformed selector executed no tests and is retained in `android-first-setup-auto-restore-probes.log` |
| First-setup journal publication | PASS; debug build and thirteen combined private recovery/status/foreground checks in 17.354 s (`artifacts/android-first-setup-publication-probes.log`). Initialization writes and syncs a reserved `.creating-<UUID>` directory before publishing and syncing the final UUID directory. Unpublished interrupted initialization is excluded from pending/history and cannot be loaded to authorize mutation; missing published journals still refuse recovery. The returned journal reloads the published path before any uninstall intent. Export uses the same history filter. Tests simulate initialization states in private storage; physical process-death acceptance remains open. Actual read-only normal-game verification after Activity recreation still passes; no live setup or translation started |
| Real fixture installer / service-loss recovery | PARTIAL, one real fixture test fails in 31.815 s (`artifacts/android-fixture-installer-probes.log`). Debug-only service fixes both APK/data targets to `io.github.hokace.fixture`; release APK excludes both fixture service classes (`artifacts/android-fixture-installer-release-boundary.json`). Exact original fixture APK is cached before removal, SHA `1f77892b2142758937113d0522180e6434c27108d4f4f13bc262ecb36d12970d`. Fixture uninstall and actual UserService death/reconnection occur; truncated install is refused. Normal and finally restoration fail, and USB fallback independently reports `INSTALL_FAILED_USER_RESTRICTED: Install canceled by user`. Exact original exported under `artifacts/android-fixture-installer-recovery/e640bb06-4266-4f12-894d-f694a19ca69c/`; After the user enabled installation, USB restoration succeeded (`artifacts/android-fixture-installer-ready-restore.log`); installed fixture SHA-256 independently matches the original exactly. Retry after user readiness still fails with the same Shizuku `INSTALL_FAILED_USER_RESTRICTED` in 32.132 s (`artifacts/android-fixture-installer-ready-probes.log`); USB fallback again succeeds (`artifacts/android-fixture-installer-ready-retry-restore.log`) and independent installed read-back matches SHA `1f77892b...12970d`. Both failed cycles remain partial evidence. Live game is never targeted. Installer failure reporting now retains bounded stdout as well as stderr; failed fixture restoration cannot skip service cleanup. Final debug/release builds PASS; read-only fixture target, fixed-package whitelist, private recovery/journal and actual normal-game foreground verification PASS, twelve tests in 16.505 s (`artifacts/android-fixture-installer-fixed-target-probes.log`). Exact game normal SHA `b0b08f...fc0a`, signer and non-debug state remain verified. This is not full installer-recovery or first-official conversion acceptance |
| Installer failure guidance | PASS, twelve combined status/private-recovery/foreground checks in 17.024 s (`artifacts/android-installer-failure-guidance-probes.log`). Saved worker results explain user-restricted installation, insufficient space, signer conflict and unexpected existing package with the correct setup or patch recovery action; raw errors remain unchanged for export. The last installer code selects instructions when automatic recovery failed differently from the original action. Unknown failures retain their original explanation. Actual read-only normal-game verification after Activity recreation still passes; no fixture install retry, live setup or translation was run. The later user-enabled USB fixture restoration succeeded with an independently matching original APK hash |
| Interrupted file transaction | PASS private fake-device fixture, 0.191 s: fail after index commit/before acknowledgment, retain dirty intent across journal reload, fail again during complete-set rollback, then retry restores original index/shard and Watchdog. Unverified normal APK still blocks completion. Byte rollback has no Python/native codec dependency. Real file adapter acceptance is recorded below |
| Actual fixture file adapter and orphan lock | PASS, 7.329 s: production snapshot/validation/atomic writer runs against the fixed disposable fixture through a debug-only subclass. Full tar/hash validation, wrong-hash refusal, dangling temporary symlink refusal, hidden Watchdog cleanup and complete restoration pass. A second writer remains blocked after the lock-owning shell is killed while its child lives, then proceeds after that child is killed. This tests kernel/command lifetime, not complete live coordinator or Shizuku-server-death recovery |
| Directory durability | PASS; Android journal/cache/preparation paths sync directory entries alongside file contents, snapshot extraction syncs directories after the manifest rename, signer syncs its fresh output and parent. Four private Android recovery tests pass in 2.146 s; fresh signing fixture remains byte-identical to desktop in 0.717 s. No game operations |
| Resource observations | PASS measured fresh offline build: 149.109 s including verification/setup, engine 127.906 s; 149 samples at one-second intervals. Observed filesystem free-space decrease 1616109568 bytes; maximum sampled RSS and process-lifetime high-water RSS 1837764 KiB (about 1.75 GiB); maximum thermal status 0, battery temperature 33.5 C, zero unavailable readings. All twelve staged hashes match the first Android control. This is one workload/device observation, not a full-workflow peak guarantee or sustained thermal acceptance |
| Offline build storage estimate | Debug build and metadata-only Android control PASS, three checks in 19.074 s (`artifacts/android-build-storage-probes.log`). Before work/output creation, coordinator estimates all APK prime extraction, every downloaded package twice (output and staging attempt), and four replacement trees using source descriptor lengths plus catalog payload as growth allowance. It separately retains normal-install reserve and existing 5 percent / 256 MiB margin. Current control estimates 7,497,769,750 additional bytes; with normal APK and margin, 10,000,621,751 bytes required at build start. Desktop metadata control agrees (`artifacts/android-build-storage-desktop-control.json`); duplicate prime files, traversal and wrong package names refuse (`artifacts/android-build-storage-refusals.json`). This is a conservative estimate, not a measured hard upper bound on translation/native temporary growth. Production bridge rehashes a temporary private 2.7 GB snapshot copy and returns the same estimate; its storage and forced-refusal checks pass in a 47.648 s combined run (`artifacts/android-build-storage-copy-probes.log`), whose separate foreground verification fails on a Shizuku connection timeout. The isolated read-only foreground retry passes in 15.329 s (`artifacts/android-build-storage-worker-retry.log`) and verifies unchanged normal SHA/signer/debug state. Temporary copied snapshot is removed by guarded cleanup. An earlier attempt to avoid copying through hard links is refused by Android (`artifacts/android-build-storage-bridge-probes.log`); it is not a passing check. Actual interrupted low-space coordinator, intermittent binding reliability and peak acceptance remain open. The 8 GiB snapshot cap and pre-access reserves are unchanged |
| Recovery space and completion state | Private storage/transaction/journal probes pass: overflow/negative budgets refused, installer recovery reserve included, interrupted empty-stage Watchdog cleanup restores originals, and a verified payload retains its forward-completion marker across final-install interruption. Normal APK verification remains required. Coordinator avoids a redundant installer allocation when the installed normal APK already hashes correctly. Full low-space and installer-failure coordinator acceptance remains open |
| Recovery result counters | PASS three private journal/transaction tests, 0.278 s: four counters persist before apply and survive journal reload/final-install interruption. Completed recovery returns retained counters without importing Python/native codecs; cancelled rollback reports recovered status and omits planned counts. Unresolved recovery cannot produce terminal results. Worker compilation passes; full recovered worker acceptance remains separate |
| Coordinator recovery fault injection | PASS five private coordinator/journal tests, 90.484 s: post-commit write loss, repeated rollback interruption, final normal-install acknowledgment loss and corrupted-original refusal. Uses the real recovery coordinator and actual retained APK bytes with simulated installation, installed identity and game files. No Shizuku binding or live game operations. Failed rollback restores the verified normal APK separately while preserving unresolved data intent; worker reports recovery required and launch disallowed |
| Restart applied-layer audit | PASS across the six passing checks of a seven-test run (133.308 s) and corrected changed-layer retry (one test, 27.393 s). Retained applied manifest is reconstructed from verified inputs/output and durably saved. Forward recovery reopens access, checks current hashes and restores normal. Changed simulated live data is refused, preserved without rollback writes, and cannot produce completion or launch permission |
| Static native page alignment | Source-built dependency variant PASS: all 84 libraries have 16 KiB ELF load alignment; SDK 35 zipalign `-c -P 16 4` also passes. Original repository-wheel variant has six failures (LZ4 three, Zstandard two, FreeType one). Reports `android-aligned-native-inventory.json` and historical `android-native-alignment.json`. Physical 16 KiB loader acceptance remains unproved |
| Source-built dependency pipeline | PASS, two tests in 141.805 s with source-built LZ4 4.3.2, both Zstandard 0.22.0 bindings and FreeType 2.9.1. Core codec operations and full both-layer offline build retain 391 tables/395 applied textures/one skipped table/no skipped textures. Earlier compression-only variant passes two tests in 142.092 s and all twelve staged hashes match the retained Android control. No live game writes |
| Full coordinator orchestration | PASS, two private tests in 700.46 s: real `run()` streams a complete snapshot of 653 pristine files and four synthetic Watchdog files, builds both layers, applies all twelve staged files and restores simulated normal identity. A post-first-write acknowledgment loss exercises complete-set rollback, including empty Watchdog directories. Default 8 GiB snapshot cap and production storage reserves remain unchanged. All twelve stage hashes match the first Android control; all 653 source files remain unchanged. Installation, game transport and installed verifier are simulated; no Shizuku binding or live game operations |
| Coordinator/foreground foundation | Private full-run and recovery acceptance pass; existing converted-install path includes immutable recovery identity, complete streamed snapshot/hash validation, normal restore before build, fresh DLL-free staging, live input revalidation, per-file intent/read-back, Watchdog cleanup, complete-set rollback and final installed identity verification. Game file commands use a kernel flock so orphaned writers serialize with recovery. Non-exported dataSync foreground worker owns its Shizuku binding independently of Activity and records timeout/disconnection recovery state. Preparation, recovery and converted-install confirmation are connected to UI; their full live execution is not accepted. The coordinator has not executed a live patch or rollback; lifecycle acceptance, actual first-install execution and emergency recovery remain unfinished |
| Release gate | NOT PASSED; production UI/foreground lifecycle, actual-transport coordinator recovery and live Android-generated translation acceptance remain unfinished |

Local evidence is ignored: `artifacts/android-control/control.json` includes catalog/runtime and
staged hashes, source identities, the summary, runtime import inventory and Talent keys.
`artifacts/android-control-build.log`, `android-control-graphics.log`,
`android-control-graphics-catalog.log`, `android-full-build.log`, `android-native-build.log`,
`android-scratch-transfer.log`, `android-all-probes.log` and `android-scratch-probes.log` retain
commands' results, including the superseded failures. On-phone results remain in the private
verified scratch session: `build.log`, `graphics.log`, `metrics.json`, `staged-hashes.json` and
`out/device_patch_summary.json`. Do not delete this session before retrieving those results.
Collected comparison inputs are `artifacts/android-staged-hashes.json` and
`artifacts/android-device-patch-summary.json`; native evidence is `artifacts/android-native-crash.log`
and `artifacts/android-exit-info.log`. The USB-debugging authorization was restored by the user,
so result collection subsequently succeeded.
Corrected oracle evidence is `artifacts/android-oracle-valid-fixture.log`,
`artifacts/android-graphics-valid-fixture.log` and
`artifacts/android-control-graphics-valid-fixture.log`; its private session
`oracle-valid-fixture` links only to the already verified scratch game's copy.
Full comparison is `artifacts/android-comparison.json` / `android-comparison.log`;
fetched outputs remain in `artifacts/android-staged/`. Stream/fixture evidence is
`android-stream-fixture-probes.log` / `android-stream-fixture-device.log`.
The opt-in diagnostic build and ordinary codec/fixture checks are
`android-game-cycle-build.log` / `android-final-feasibility-probes.log`.
APK preflight identities are in `artifacts/android-game-cycle-inputs.json`;
normal/access ZIP record inventories differ only at `AndroidManifest.xml`.
First live-cycle evidence: `android-game-access-transfer.log` (69.942 s),
`android-game-cycle-probes.log`, `android-game-cycle-device.log`,
`android-game-cycle-usb-restore.log`, `android-game-cycle-restored-probes.log`.
The timeout fix compiles in `android-game-cycle-timeout-build.log`; retry evidence is
`android-game-cycle-retry-probes.log`. Private `game-access-1402` retains the verified access
APK and links to the original verified normal/game inputs.
Retry installer progress is `android-game-cycle-retry-device.log`; launch evidence is
`android-game-cycle-launch.log` / `android-game-cycle-startup.png`.
Signing evidence: `android-signing-desktop-verify.log`, `android-signing-probes.log`,
`android-large-signing-probes.log`. Recovery foundations: `android-journal-probes.log`,
`android-recovery-primitives-probes.log`, `android-recovery-store-probes.log`;
coordinator compilation: `android-recovery-store-build.log`.
Read-only pipe proof: `android-recovery-pipe-probes.log`; foreground compilation:
`android-worker-build.log`. Worker/service interruption behavior remains unaccepted.
Emergency URI provider, installer confirmation/log-export UI and shared four-counter/result
state code compile. URI consumer instrumentation encountered MIUI background/KeyguardLocked
activity denials, then a test-only anonymous ResultReceiver class-loader crash. The callback is
now parcelled into the framework ResultReceiver type. The unlocked-screen retry passes in
54.021 s: the fixture reads all 2026631918 bytes through the granted URI with the expected
normal-APK SHA-256; writable descriptors are refused and the read grant is revoked afterwards.
Evidence is `artifacts/android-recovery-uri-unlocked-probes.log`. Emergency installer completion
remains unverified. The earlier combined run's independent read-only WorkerProbeTest passes
Activity recreation; its URI failure is superseded by this isolated consumer pass.

Emergency restoration now persists an AtomicFile intent, syncs its file and parent directory
before launching the public installer, and retains the normal APK SHA plus a unique attempt ID.
Retrying the same pending APK reuses its request; switching APKs while pending is refused.
The installed-normal foreground action binds verification to that request. Only a successful
full installed APK/hash/manifest/signer check resolves it, with a second request-ID check before
committing success. Failure, cancellation or process interruption leaves verification pending.
The UI displays the saved warning after recreation and log export includes the record. This
separate APK record never resolves dirty package intents, advances setup, or reports translation.
Opening the installer takes the shared coordinator lock while publishing its intent, refusing an
active patch/recovery. A pending request blocks new patch and first-setup mutation before device
use; existing recovery remains available. Final build PASS (`artifacts/android-emergency-restore-lock-build.log`).
Twelve private intent/guard/first-setup recovery tests PASS in 0.681 s
(`artifacts/android-emergency-restore-guard-private-probes.log`), including refusal before any
device call and installer-intent refusal while the coordinator lock is held. Earlier three
private checks PASS in 0.108 s (`artifacts/android-emergency-restore-private-final-probes.log`).
Initial combined run is partial: three private passes and two foreground failures in 122.941 s
(`artifacts/android-emergency-restore-probes.log`): Shizuku stopped and Activity cannot resume.
After user readiness, the new emergency foreground request test PASS, including actual installed
normal APK verification and Activity recreation; the separate baseline Activity test then fails
to reach RESUMED. The ready combined run is one pass/one failure in 64.057 s
(`artifacts/android-emergency-restore-ready-worker-probes.log`). This verifies a seeded private
request against the already-installed normal APK, not an actual public installer return.
Actual public installer-return and physical process-death acceptance remain open. No game
installation or data write was run.

The separate fixed-fixture physical app-death cycle now PASS in 15.016 s
(`artifacts/android-process-death-fixture-final-retry-cycle/report.json`); its fresh recovery
instrumentation passes one test in 5.584 s. The harness observes app PID 25025 alive after a
durably saved write intent and a real fixture index rename, force-stops only the feasibility
app, observes its process absent, then starts a new instrumentation process. Before rollback,
the real Shizuku adapter verifies the mixed layer: changed index, original shard and other
files. The new process reloads the journal with dirty packages and unresolved write intent,
then production `GameFileTransaction.rollback` restores and verifies all five original files
and the empty `Watchdog/src` directory. Final journal remains RESTORING/normal-unverified:
completion without independently verified normal APK is refused. No APK installation is
performed. Fixture APK stays exactly SHA `1f77892b2142758937113d0522180e6434c27108d4f4f13bc262ecb36d12970d`;
owned fixture files and marker are removed, with host-side cleanup verification. The test uses
a synthetic journal phase sequence, small disposable files and the real fixed-fixture file
adapter; it does not prove the full foreground coordinator, live-game or APK restore cycle.
The host refuses active patch/recovery services, unfinished published patch/setup journals
and pending emergency APK verification before starting instrumentation.

Earlier fresh fixture cycle PASS in 14.141 s
(`artifacts/android-process-death-fixture-fixed-cycle/report.json`). The first killed-app case
failed its recovery ownership assertion because test setup redirected the marker before
creating `files`; the five retained mixed files were independently matched against their
manifest before repairing that one marker. Recovery of the same case then PASS in 8.750 s,
one instrumentation test in 6.167 s (`artifacts/android-process-death-fixture-recovery/`).
The original failure remains under `artifacts/android-process-death-fixture-cycle/`.
Adding idle preflight initially refused before mutation due an exec-out quoting error
(`artifacts/android-process-death-fixture-final-cycle/report.json`); corrected argument
quoting is used by the final passing run. Build logs are
`android-process-death-fixture-fixed-build.log` and `android-process-death-fixture-final-build.log`.
Later discovery-only build PASS (`android-process-death-fixture-discovery-build.log`);
default instrumentation skips the two-phase test without explicit host arguments. The host
also refuses inconsistent terminal patch journals and a pending AtomicFile backup of the
emergency restore record. These guards do not broaden the physical fixture result.
Shizuku server death/revocation, screen-off, reboot, low space, installer restoration and
full-coordinator physical interruption remain separate acceptance gates.

Patch-session initial publication is now atomic too: `SessionJournal.create` writes and syncs
a reserved `.creating-<UUID>` directory, renames it to the final UUID, syncs the parent and
reloads the published journal before returning it to the coordinator. Unpublished empty,
partial or fully written drafts never authorize mutation and are excluded from pending/history.
Preparation, both consent stores, patch/first-setup coordinators, recovery selection, recovery
APK selection and diagnostic export share the same discovery helpers. A missing/damaged
published journal is refused rather than hidden. Loading also bounds file size before reading,
refuses linked published paths (including dangling directory links), validates required recovery,
engine and mutation state, and refuses terminal journals with unresolved recovery.

Final private publication/journal/transaction/setup/emergency checks PASS, 22 tests in 2.058 s
(`artifacts/android-session-publication-final-private-probes.log`); earlier 21 tests pass in
0.743 s before the dangling-link check. Tests verify draft refusal, corrupt published-session
refusal before device calls at every mutation entry point, malformed/missing stored fields,
false completion, oversized journals, and linked directories. Final build PASS
(`artifacts/android-session-publication-final-build.log`).
The physical fixture app-death/rollback cycle with this production journal version PASS in
15.282 s, recovery instrumentation one test in 6.007 s
(`artifacts/android-session-publication-process-death-cycle/report.json`).
It confirms new-process load of the published unresolved intent and exact five-file/Watchdog
restoration; APK and game remain untouched. Initial-write interruption states are simulated
in private directories; physical interruption during the rename/publication itself and full
foreground coordinator interruption remain unaccepted.
After the first performance cleanup, phone `/data` had 5237244 KiB available and conservative
coordinator preflight refused another large snapshot. Subsequent verified scratch compaction
freed enough space for the full private coordinator acceptance below. Neither observation is
a measured production peak-space requirement.
Whole-set fault injection is `android-transaction-probes.log`; foreground/URI combined results
are `android-worker-uri-probes.log` and MIUI/callback errors are retained in
`android-worker-uri-device.log`. Latest framework callback correction compiles in
`android-recovery-callback-build.log`; its corrected consumer passes in the isolated unlocked run above.
Streamed manifest-only APK preparation and SHA/manifest/certificate cache receipts initially
compiled in `android-apk-preparation-build.log`. Full private generation/reload now passes;
the newly generated access APK has not been installed. Shared counters now come from
`tools/patch_summary.py`, re-exported by Windows;
the retained summary still reports 391 / 395 / 1 / 0. Codec configuration and storage refusal
run before access installation. Fixed first-official source/profile preflight, hash-guarded
removal and absent-only normal-install endpoints now compile with a dedicated device adapter.
They are now connected to a one-use consent request and explicit first-setup UI. No valid
game uninstall has been run. Installation recovery never repeats removal; an unchanged original
app can terminate a refused/interrupted removal after independent verification, without claiming
deleted data was recovered. Both local-data-loss and Scan-to-login acknowledgments start unchecked.
The foreground action consumes the bound request, and its UUID is retained in the setup journal.
After new game downloads finish, the separate setup checkpoint verifies the normal APK and
unblocks preparation; a fresh preparation then enters the usual converted-install patch flow.
Setup errors now make one automatic recovery attempt before returning from the worker.
The controller reloads durable intent and revalidates cached recovery, checks any installed app
before retrying installation, and never repeats removal. Persistent failure retains the journal
for explicit later recovery. Progress-display failure cannot prevent a normal-app restore.
This passes private simulations; actual first-official conversion and interruption/recovery
through the real installer remain unaccepted.
First installation explicitly supplies `-R`: omitting `-r` still defaults to replacement in
[Android 12's package-manager implementation](https://raw.githubusercontent.com/aosp-mirror/platform_frameworks_base/android12-release/services/core/java/com/android/server/pm/PackageManagerShellCommand.java).
The phone's own help confirms the option (`artifacts/android-package-manager-help.log`).
A disposable-fixture install with `-R` is rejected as `INSTALL_FAILED_ALREADY_EXISTS`, with
its installed APK hash unchanged (`artifacts/android-first-setup-no-replace-fixture.json`).
Custom-codec source companion `artifacts/android-custom-codec-sources.zip` contains three
SHA-pinned original archives, build recipe, existing notice inventory and canonical GPL text;
archive contents are read back. Other dependency/application notices and sources remain open.
Real file-adapter proof is `artifacts/android-file-fixture-probes.log`; the corresponding build
is `artifacts/android-file-fixture-build.log`. Production keeps its fixed game target; only
`src/debug/FixtureFileService.kt` substitutes the disposable fixture for file operations.
Initial actual-command measurement found `flock: Bad file descriptor`; explicitly passing FD 9
fixed acquisition, but a grouped shell body still released the lock when its parent died.
`GameFileLock` now execs the protected shell with FD 9 explicitly inherited. The orphan-child
test verifies both the blocked interval and subsequent writer completion. The writer also
rejects dangling temporary symlinks before opening them. Watchdog cleanup recreates the fixed
directory, clearing hidden files too, and syncs directory entries; restoration syncs created
directories and ancestors. Updated Shizuku binding/private transaction regression passes two
tests in 1.850 s (`artifacts/android-file-adapter-regression-probes.log`). No live game files
or APKs were changed by these fixture and read-only tests.
Resource observation is `artifacts/android-performance-probes.log` (instrumentation 149.176 s)
and `artifacts/android-performance-retained/`: metrics, control, summary, stage hashes, build log
and cleanup receipt. `RunMetrics` also observes future coordinator runs. RSS high-water values
cover the whole process lifetime; sampled disk deltas can include other applications and miss
subsecond peaks. No absolute production storage/RAM bound is claimed. The research cleanup
tool validates the performance UUID and canonical app-private targets, exports/read-backs all
evidence, requires stage hashes identical to the retained control, then removes only generated
work/out; approved source links, input data and protected recovery remain retained.
`StorageBudget` adds checked arithmetic, 5-percent-or-256-MiB margin, and simultaneous normal
installer/file-write reserves to preparation, snapshot/extraction, apply and rollback checks.
The snapshot cap remains conservative at 8 GiB; full build-work estimation is still unfinished.
Recovery pre-verifies an already-installed normal APK to avoid allocating another installer copy
after an offline build exhausts space. Journaled `patch_payload_verified` distinguishes full
forward recovery from rollback/cancellation after the final normal install is interrupted.
Empty stage manifests can still require Watchdog rollback. Private acceptance is
`artifacts/android-storage-probes.log` and `artifacts/android-recovery-completion-probes.log`;
the final combined storage/transaction/journal run passes four tests in 0.282 s. These proofs
do not substitute for fault injection through the full coordinator.
Recovery counter evidence is `artifacts/android-recovery-results-build.log` and
`artifacts/android-recovery-results-probes.log`. `PatchWorkerService` persists the journal's
terminal recovery result instead of overwriting every successful recovery with `verified`.
`verified` remains the read-only normal-APK check's outcome.

Coordinator recovery evidence is `artifacts/android-coordinator-recovery-build.log` and
`artifacts/android-coordinator-recovery-probes.log`. `CoordinatorRecoveryProbeTest` isolates
the coordinator's files directory, reads the approved normal/access APKs without duplicating
them, and streams installer inputs through a fake device. Its in-process installed verifier
is injected only by tests; application calls retain independent installed-APK pipe and manifest
verification. Recovery does not start Python. A separate durable `recovery_normal_intent`
allows emergency normal restoration without clearing a failed package-write intent. Damaged
originals are rejected before changing that intent, and a verified normal APK alone cannot
resolve inconsistent data or grant launch permission. This is recovery-path acceptance with
simulated transport. Full private `run()` orchestration is now accepted below; actual
transport and process/server loss remain unproved.

Full orchestration evidence is `artifacts/android-full-coordinator-build.log`,
`android-full-coordinator-probes.log` and `android-full-coordinator-retained/`.
`FullCoordinatorProbeTest` uses the actual coordinator, full approved APK descriptor streams,
complete snapshot extraction and both-layer engine. Its isolated context borrows pristine
inputs read-only; fake file writes allocate and verify full output bytes in private scratch.
The success journal is `0188ec38-1d92-4e6d-a268-6ae0fd6611f7`; the fault/rollback journal is
`ef14718f-58b7-460e-bc0a-1acd1dfab43a`. Success retains 391 / 395 / 1 / 0; cancelled rollback
omits planned counts. Terminal receipts are retained after removing only verified test outputs.
Observed run metrics are 302.866 s success and 302.193 s fault, with free-space decreases
7477182464 and 7477055488 bytes respectively. Maximum sampled RSS is 1664940 KiB;
process-lifetime high-water RSS is 1821524 KiB, thermal status 0 and battery temperature
37.7 C. These deltas include fake override copies and exclude actual installer allocation;
they cannot establish the production peak budget.

Full preparation evidence is `artifacts/android-apk-preparation-final-probes.log`,
`android-apk-preparation-final-export.log`, `android-apk-preparation-access-signature.log`
and `android-apk-preparation-retained/`. Passing fixture
`e35858b5-ffdf-4fe6-b308-2db85cde3658` retains preparation receipt
`5b6215d9-b501-49f8-b587-33a25c8afedf`. Its access hash is identical to the separately
exported SDK-verified artifact from fixture `1909e078-43a5-4b87-98f6-1982e9c0d30c`.
Both device and independent Windows decompression/hash inventories agree for all 1625 entries.
SDK verification uses `--min-sdk-version 30`: default verification also requires v1 signing
for the game's older declared minimum and fails with missing `META-INF/MANIFEST.MF`;
Android 11+ is the patcher's supported range and the generated APK uses v2 signing.
The passing run observes 133.626 s within metrics, an 8164605952-byte free-space decrease,
202944 KiB maximum sampled RSS, 226596 KiB process-lifetime high-water RSS, thermal status 0
and battery temperature 33.7 C. This includes four simultaneous APK-size allocations and
engine extraction; it remains one device/workload observation.

The initial preparation test failed in 220.478 s because the bridge unnecessarily rewrote an
already-normal stable-key APK, changing its identity to `6b82774e…15b5e32`. The bridge now
copies that APK unchanged only when the manifest already matches and its signer is the stable
key; other sources still follow manifest rewrite/signing. The access APK is derived from the
prepared normal file. A 351.776 s retry passed payload/receipt checks but failed a test cleanup
guard that compared Android's `/data/user/0` and `/data/data` aliases literally. Canonical
parent containment and explicit symlink refusal fix that guard; the final complete test passes.
Failed copies were individually rehashed and removed only after retaining receipts. The
accepted test removes its duplicate source after verification, retaining the access file and
protected recovery. No APK was installed into the live game, and no live game data changed.

Preparation/recovery UI evidence is `artifacts/android-preparation-recovery-ui-state-build.log`,
`android-preparation-recovery-ui-probes.log`, `android-preparation-guards-probes.log` and the
final recovery-label compilation `android-preparation-recovery-ui-label-build.log`.
Preparation uses the worker's independent binding and cancellation checkpoints before/after
large operations. An unfinished journal prevents preparation before reading the device.
Cancellation may wait for the current copy/signing operation to reach a checkpoint; interrupted
private preparation files remain retained. Atomic worker-state writes are serialized, and late
progress/success cannot replace timeout state after the worker retires. `WorkerStatus` labels a
retained running record as last saved progress rather than evidence of a live process; unresolved
recovery hides planned counts and asks the user to keep the game closed. Activity polling stops
while paused and resumes after recreation. A date-based chooser starts the existing recovery
worker for a selected unfinished session. That chooser and full foreground preparation are
compiled but not device-accepted. The converted-install patch checkpoint is now connected;
initial conversion is still unavailable.

Update-checkpoint evidence is `artifacts/android-patch-request-probe-build.log`,
`android-update-checkpoint-probes.log`, `android-update-checkpoint-source-build.log`
`android-update-checkpoint-final-probes.log` and `android-update-checkpoint-combined-probes.log`
(all three tests pass in 30.821 s). The initial UI check found a brief enabled
Start button before Android delivered the dialog's OnShow callback. Button disabling and
listeners now run synchronously after `show()`, before returning to the event loop; cancellation
is asserted after Android's queued dismissal. The final complete UI/source guard run passes.
`PatchRequestStore` retains an AtomicFile confirmation bound to preparation UUID, receipt SHA,
normal/access SHA and a checked update-finished/game-closed acknowledgment. It expires after
15 minutes and is durably consumed before coordinator entry. Repeat claims, changed receipts,
unfinished recovery and first-official conversion are refused. Claim reload rehashes actual
normal/access APKs and requires the current engine identity. The foreground worker accepts only
this request UUID for patch start; it no longer accepts caller-supplied normal IDs/access paths.

Converted-source preflight independently verifies the installed original APK before access,
while retaining the prepared normal APK for restoration. This preserves the optional manifest
rename when a converted source still has an older label. Source and recovery must share version
and the stable signer, and neither may be debuggable. Version/signer refusal is device-tested
with an unavailable Binder and missing access file; the label-changing positive path remains
unaccepted. Existing direct coordinator tests retain the default normal-source overload.
These tests only read protected/private APK copies or cancel UI confirmation. No live worker
patch was invoked, no game APK was replaced and no game data changed.

`tools/research/prepare_android_workflow_space.py` exported/read-back the first twelve Android
outputs and metadata to `artifacts/android-workflow-retained/`, rehashed all pristine/rerun
inputs, and removed only verified disposable work/output and duplicate scratch APKs.
The original scratch normal APK now links to the independently verified protected recovery
cache. Pristine game inputs, access APK and PC recovery material remain intact.
`tools/research/restore_android_control_stage.py` subsequently restored all twelve archived
outputs through the token-authenticated loopback receiver and independently rehashed every
file before publishing `control-1402-verified/out`. Evidence is
`artifacts/android-control-stage-restore-harness.log`. Earlier restore attempts found no
`exec-in` receiver acknowledgment, a raw shell-stdin copy truncated at its first 0x1a byte,
and a base64 transfer timeout; those failed attempts do not prove an OEM tar defect.

Review identified that an earlier durable payload-verification marker cannot prove the current
layer after restart or an external update. The applied manifest now uses AtomicFile plus file
and directory sync. Forward recovery reconstructs its expected hashes from verified originals
and staged files, reopens matching access, validates the current full layer, then restores normal.
A mismatch retains recovery-required state and does not overwrite externally changed files.
Evidence is `artifacts/android-forward-recovery-build.log`,
`artifacts/android-forward-recovery-probes.log`,
`artifacts/android-forward-recovery-retry-build.log` and
`artifacts/android-forward-recovery-retry-probes.log`. The seven-test run has six passes and
one test-adapter failure: its expected live-layer refusal was wrapped in RuntimeException
instead of preserving IllegalStateException. The adapter now preserves runtime exceptions;
the isolated changed-layer retry passes in 27.393 s, including unchanged-data/no-new-write,
normal-restored and launch-disallowed assertions. The other six passing checks establish final
acknowledgment-loss audit, corrupted-original refusal, repeated rollback and journal/transaction
regressions. No full coordinator build/apply or actual restart was exercised by these fixtures.

On 2026-10-04 pinned upstream source builds replaced the five misaligned LZ4/Zstandard
bindings and FreeType in the complete-codec configuration. Versions remain 4.3.2/0.22.0/2.9.1;
upstream source is unchanged. `build_compression_wheels.py` preserves both Zstandard bindings
and explicitly configures the upstream CFFI generator's Android preprocessor; its first attempt
failed on missing Unix compiler settings in the Windows host. `build_freetype_wheel.py` uses
SDK CMake 3.22.1/NDK 28.2.13676358, API 24, position-independent source archive plus explicit
16 KiB shared linking. Original and rebuilt FreeType have the same `libfreetype.so` SONAME
and libc/libdl/libm/libz dependencies. Its feature selection follows the Chaquopy recipe.

The default `-PfullCodecs` now requires these three local dependency wheels alongside the
three graphics wheels; an early comparison run selected them with `-PalignedCompression`.
The minimal diagnostic build remains a repository-wheel baseline. Full source-built evidence
is `artifacts/android-compression-build-retry.log`, `android-freetype-build.log`,
`android-aligned-native-build.log`, `android-aligned-native-inventory.json` and
`android-aligned-native-probes.log`. Both-layer build engine time is 118.852 s; the surrounding
two-test run is 141.805 s. Measured free-space decrease is 1627836416 bytes, sampled RSS max
1679904 KiB, process-lifetime high-water RSS 1869372 KiB, thermal status max 0 and battery
temperature max 34.5 C. These samples are one observation on the existing Android 12 device,
not an upper bound or a physical 16 KiB loader proof.

`artifacts/android-aligned-native-retained/` exports source/control/result hashes, metrics and
build logs. All twelve staged files match the first Android control byte-for-byte. Only the
successful session's generated work/out were pruned after verified export; inputs and normal
recovery remain. Final default-build evidence is `android-native-dependency-final-build.log`,
`android-native-dependency-final-inventory.json` and `android-native-dependency-final-probes.log`:
84/84 aligned libraries and two passing codec/font checks in 1.982 s. The additional probe
round-trips LZ4 frames, confirms the CPython Zstandard C backend, and renders a nonempty glyph
mask with Pillow/FreeType 2.9.1. Optional CFFI runtime and physical 16 KiB acceptance remain
separate; the pipeline uses the verified C backend. The six-component source companion
`artifacts/android-six-codec-sources.zip` passes original-archive hashes, CRC and full read-back.
Its scope is these components; complete application/runtime redistribution inventory remains open.

The user reports a second Xiaomi device running Android 15 with the AOSP-based PixelOS custom
ROM. It is available for later platform testing; its model, ABI and actual page size have not
been inspected. This adds a distinct ROM/platform path, not another hardware OEM. Android 15
does not establish 16 KiB loading. The source-built dependency APK now fixes all six static
alignment failures, but this device's actual loader/page-size acceptance remains open.
On 2026-10-05 the user reports that phone is unavailable now. The prepared platform/codec
harness is validated only on the existing 4 KiB Xiaomi; do not close newer-device or 16 KiB gates.
Durability verification is `android-durable-directories-probes.log` and
`android-signing-durable-probes.log`; fresh signer output is `signing-rsa-1/java-signed-durable.apk`.

On 2026-10-04 `RerunProbeTest.testAlreadyEnglishHasNoDuplicateAppendOrFileDrift`
passes on the phone in 142.47 s (`artifacts/android-rerun-copy-probes.log`). A fresh private
scratch input combines the pristine layer with the first Android build's twelve staged files.
Every rerun output matches its already-English input hash; all pristine and retained first-build
files are rehashed unchanged. Android denied hard links in the initial probe; ordinary copies
and an APK symbolic link succeed. This is offline idempotence evidence, not a live-game rerun.
The Windows frozen application was rebuilt with Python 3.12 and passed `--selftest` against
the pristine downloaded dump, with `selftest.json` reporting `ok: true`. Evidence is
`artifacts/android-port-windows-build.log`, `artifacts/android-port-windows-selftest.log` and
`artifacts/android-port-windows-selftest/selftest.json`. This self-test does not supply the APK;
the earlier both-layer control remains the coverage comparison.

### Measured implementation corrections

- AAPT transparently decompresses a `.gz` asset and strips its suffix. Generated copies now use
  a `.payload` suffix, with unchanged bytes and original names restored only after verified extraction.
- AAPT's default directory filter omits Python `_backends` directories. The spike disables this
  filter so its verified resource manifest matches the actual packaged files.
- Archspec's filesystem-relative CPU JSON needs `extractPackages("archspec")`; without it the
  ASTC import fails before loading the NEON extension.
- Applying `-fms-extensions` globally collides with Ooz's `_rotl` helper under NDK Clang. That flag
  now follows the texture decoder's own build configuration only; upstream sources stay unchanged.
- The ordinary-app denial can occur before the `run-as` process starts. EACCES is an expected
  result, rather than a failed fixture test. The UserService round-trip itself passed.
- Both PAX and USTAR stdin transfers through this phone's Toybox tar truncated the scratch data.
  A passing transport exit was not evidence of a complete copy. A localhost-only instrumentation
  receiver now bounds the session/file counts and lengths, verifies SHA-256 per file, and acknowledges
  each successful write. It is absent from the main application; Internet permission is debug-only.
- The next device read was temporarily rejected because automatic approval review lacked credits.
  A retry after the user's “Continue” passed review but the phone reported `ADB unauthorized`.
  USB debugging must be authorized again to retrieve results; this is separate from Shizuku permission.
- The graphics oracle's synthetic ramp bytes were not valid ASTC blocks. A fresh process and
  line-buffered log isolated the native crash to check 5. Encoding a known background instead
  preserves the independent byte-range checks and passes both Windows and ARM64. Native decoder
  behavior on malformed input remains outside this proof.

### Immediate continuation

The deliberate permission-denial foreground probe and the post-enable independent normal-APK
verification now both pass. HOK ACE authorization is restored. Permission revocation during a
live patch remains a separate acceptance gate.

The application now includes the MIUI USB-debugging security option in user-restricted installer
guidance. Final debug/test build PASS (`artifacts/android-miui-security-guidance-build.log`);
two private worker-status checks PASS in 0.021 s (`artifacts/android-miui-security-guidance-probes.log`).
The installer code and raw recorded errors are unchanged by this guidance update.

1. The fresh Shizuku fixture/service-loss cycle now passes after user confirmation of both MIUI
   installation/security-debugging options. Exact installed fixture bytes are independently verified.
   Preserve the failed earlier cycles and continue the separate worker/server-loss acceptance;
   the tiny fixture does not prove large-game installation or first-official conversion.
2. Retain the verified normal game APK and USB fallback. Build-work estimation, private coordinator
   success/rollback, journal publication, foreground read-only verification, emergency selection
   and bounded diagnostic export are implemented and measured. Their narrow proofs do not accept
   a complete live patch or its interrupted installer recovery.
3. Complete the open acceptance gates below. Prepare a concrete live test and obtain its separate
   authorization before applying Android-generated translations or removing an official game.

### Same day: the Windows signer's RSA callback (standalone app)

- **Android signing adapter (2026-10-03).** `apk_tools.sign_v2` accepts an optional RSA callable
  and DER public key; its default still loads the existing PKCS#8 key through cryptography.
  Crypto imports now occur only in that default branch. ZIP rewriting and the v2 digest/block
  construction stay shared. The old implementation, new default and injected desktop RSA output
  are byte-identical on the disposable fixture control (SHA-256 `eeb33a4e…26d3854b`), and
  SDK `apksigner verify --verbose --print-certs` independently verifies v2 and the stable certificate.
  The Android port delegates the one RSA operation to Java; its separate device proof is recorded
  in `android-shizuku-patcher.md`.


## 2026-10-04 — Summary accessors shared with Android

On 2026-10-04 the three summary accessors moved unchanged into `tools/patch_summary.py` so
Android and Windows classify the four results identically. `patcher_core` re-exports the existing
names, preserving the GUI API. Python 3.12 import/control check returns 391 text tables, 395 applied
textures, one skipped table and zero skipped textures; accessor identity matches the shared module.
The frozen application was rebuilt with `.venv/Scripts/python.exe app/build_exe.py` and passed
`--selftest` against `dist/HOK ACE Patcher Data/pristine/20261003-173730/game`;
`artifacts/android-port-windows-selftest/selftest.json` reports `ok: true`. Build and self-test
logs are `artifacts/android-port-windows-build.log` and `artifacts/android-port-windows-selftest.log`.
The self-test covers the downloaded dump without an APK input.


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



## 2026-10-05 — Android app: first full live patch, and the fixes before it

### The live patch (Xiaomi M2007J3SG, data 1.4.0.2)

The user reports a successful full patch from the Android app. Read-only retrieval of its worker result, session journal, build summary and resource metrics confirms a completed live snapshot → build → apply → normal-APK restore cycle on the Xiaomi M2007J3SG / MIUI Android 12, using game data **1.4.0.2**. Evidence: `artifacts/android-live-patch-success-20261005.json`; session `8a804248-73fd-4b29-89f7-95fdca95f79c`. No new patch, installation or game-data write was performed while collecting this documentation evidence.

| Result | Recorded value |
|---|---|
| Worker / journal | `complete` / `COMPLETE` |
| Applied translation | 391 text tables; 395 textures across six packages |
| Known skipped content | One prime-only text table refused by the append encoder; zero skipped textures |
| Committed package files | 12 index/shard files in packages `1`, `15`, `19`, `20`, `21`, `1050016095` |
| Final safety state | `normal_verified=true`, `patch_payload_verified=true`, `packages_dirty=false`; no pending mutation or normal-restore intent |
| Retained normal APK SHA-256 | `29b3ee7e5a0d21de7d1282d704416402d341b651da95af2eeb5b274c818defdc` |
| Snapshot | 1,990,685,775 payload bytes; 501 files and 289 directories |
| Coordinator duration | 382.265 seconds (about 6 minutes 22 seconds) |
| Sampled free space | 11.39 GB initially; 5.25 GB minimum; 6.14 GB observed decrease |
| Sampled memory / temperature | Maximum sampled RSS 2,215,200 KiB; process high-water RSS 2,332,424 KiB; maximum battery temperature 38.0°C; thermal status 0 |
| Additional candidate assets | None (`cycle_assets=[]`); existing catalog/allowlist only |

This closes the first successful normal-path live coordinator cycle on the measured Xiaomi, including cached APK reuse, measured storage budgeting, updater-directory extraction and the foreground automatic flow. It does not establish a complete translation, watched-screen visual acceptance, first-official conversion acceptance, a repeat patch on the newly translated layer, deliberate live failure injection, another OEM, Android 15/16 KiB pages, or a cable-disconnected release cycle. Resource observations are one run, not minimum device requirements or guaranteed storage needs. The existing 391/395 coverage and one-table gap are unchanged.

### Corrections that preceded it (recorded with the 2026-10-05 commit)

Snapshot updater-directory correction: actual Xiaomi run fails at extraction with `ValueError: Unsupported package path`; worker then reinstalls and independently verifies normal APK recovery before reporting error. The saved archive inventory has 790 entries, including 84 previously unrecognized empty directories under `packages/builtin/Merge` and `packages/builtin/CleanCopy`. No file entry is outside the old allowlist. The Python reader now permits only these two directory roots and one unsigned 32-bit package-ID child; files under them, arbitrary nested names, traversal and links remain refused. The native writable-file policy is unchanged. Errors now include the rejected package path. Five offline regression cases pass, and all 790 actual archive member names/types validate (`artifacts/android-snapshot-path-regression.json`). APK-cache provenance no longer requires the current translation engine hash: independently verified APK hashes/versions/signers/debug flags remain the cache gate, so this Python-only update reuses the saved APKs instead of creating a new preparation. Engine preflight still runs for a patch. Full-codec debug build and six existing host storage checks pass (`artifacts/android-snapshot-path-final-build.log`); the updated APK was installed after confirming the failed worker retired. A standalone cache-only worker returns `prepared` using the same existing preparation and normal identity after the engine update, explicitly reporting no new APK copies (`artifacts/android-snapshot-fix-cache-receipt.json`). No patch/apply was launched during this fix.

Actual cache-only Xiaomi verification: app update installed with data retained. A fixed `prepare` operation launched under the app UID (UI automatic flow unarmed) reuses preparation `63afb12f-087f-48d1-9f30-e4bc1553a57a`, independently streams/verifies the installed normal APK, reports no signature conversion, and creates no new preparation folder. Initial hard-link attempts are denied by phone policy; private symbolic references succeed. Final pass rehashes each candidate and shared target before durable atomic replacement and reports 8.1 GB reclaimed. Free space becomes 13,403,295,744 bytes (`artifacts/android-cache-reuse-device-receipt.json`). Recovery normal/source/access paths remain; immutable content is retained, not regenerated or discarded. Standalone cache verification does not arm continuation, install the access game APK, or write game data. A second standalone preparation also returns `prepared`, loads the shared APKs through full manifest/hash checks, selects the installed normal identity (no first-setup conversion), and leaves exactly the same three preparation directories with no new APK copies (`artifacts/android-cache-reuse-repeat-receipt.json`). This verifies reuse after consolidation; the separate confirmation instrumentation probe remains unrun. Final APK is `artifacts/dev.halixm.hokacepatcher.apk`.

Cache/storage retry correction: the user reported repeated APK preparation and a 13.3 GB free-space refusal after downloading the game. The app-private inventory showed three preparation folders totaling 12.17 GB, plus a 2.03 GB normal recovery APK. The recorded refusal was 13,275,216,396 additional bytes with only 5,326,036,992 available, before any patch session/game access installation. Preparation previously always created a fresh UUID directory, and snapshot preflight reserved a fixed 8 GiB. Preparation now verifies/reuses matching cache content before storage allocation, retains historical source identity separately from the current installed source, and binds patch confirmation to the selected source. Byte-identical immutable APKs are durably linked (hard link or private symbolic reference to an immutable retained target) without dropping recovery paths, including per-session access files (space-checked copy fallback). The coordinator reserves installer recovery space first, then measures game files/directories under the existing lock after access installation and reserves archive plus extraction plus normal-APK install space. Any refusal uses existing restoration handling. The 8 GiB maximum and offline build/write reserves remain intact. Full-codec build, six existing host checks and Android-test compilation pass (`artifacts/android-cache-storage-build.log`, `artifacts/android-cache-storage-final-build.log`). Actual Android measurement command against tiny app-private synthetic files yields a 4,608-byte tar safely below the 16,792,809-byte budget (`artifacts/android-snapshot-estimate-shell-check.json`). Dedicated cache test APK installation was cancelled by MIUI; no instrumentation pass is claimed. At this checkpoint live patch/restore with the revised budget was unverified; the successful 2026-10-05 cycle (same entry) exercises its normal path.

The main screen now shows a scrollable live activity log, refreshed by the existing one-second status poll. Worker state retains the latest 40 timestamped progress/error messages (each capped at 2,000 characters), including terminal results, so reopening the activity preserves recent progress. Each admitted worker operation clears its history; scrolling up pauses automatic following until the user returns to the bottom. No synthetic percentage or device operation was added. Full-codec debug build and existing six host storage checks pass (`artifacts/android-live-progress-build.log`). After the user reconnected the Xiaomi, ADB confirmed no patcher service was running and installed the updated APK successfully with existing data retained. On-device log display during a live patch remains unverified; no patch or game operation was started.

### Remaining acceptance audit (2026-10-05)

| Requirement | Current evidence | Proof still required |
|---|---|---|
| Reliable OEM installation and restoration | Existing-fixture replacement and latest fresh Shizuku/service-loss cycle pass with exact installed read-back after both MIUI options were confirmed; earlier user-restricted failures retained | Reliability through the full large-APK worker/install/restore flow, including actual installer interruption; no broad OEM claim from the tiny fixture |
| Permission denial / stopped Shizuku | Deliberately denied foreground verification refuses before binding; post-enable actual normal verification passes. Connected foreground own-UserService loss, preserved intent and fresh retry pass; actual stopped-server failure and owned intent recovery recorded | Permission revocation and stopped-server recovery through the full supported patch workflow, without false completion |
| Complete mobile workflow | Full both-layer private coordinator success and rollback pass with simulated installation/transport | Actual Android-prepared access APK installation, full live snapshot/build/apply/normal restore, exact installed and pushed hashes; separate live-cycle authorization |
| Emergency public installer | URI consumption, durable intent and foreground independent verification pass separately; damaged-record selection/export private checks pass | Actual user-assisted public installer completion followed by saved-request verification; pending package rollback must remain pending |
| Lifecycle / interruption matrix | Actual app-process death at a fixed fixture file boundary and byte rollback pass; connected foreground read-only verification handles own-UserService death and fresh retry | Full patch worker process/server loss, revocation, screen-off, reboot, low-space and installer interruption across the real supported flow |
| First official conversion and updates | Consent, journal, restore-priority and transport simulations pass; current game is already converted | Separate data-loss authorization, actual differently signed official source, independently verified installation, full update and subsequent patch |
| Translation screens / repeat patch | Offline 391 tables / 395 applied textures and rerun parity; existing game UI predates Android output | Authorized watched `prime-rebuild.md` screens after Android output, prime-only checks, live rerun and repair acceptance |
| Native/device/resource acceptance | All 84 static native alignments pass; current 4 KiB Xiaomi offline codec/resource observations pass | Physical 16 KiB loading, Android 15 foreground behavior, actual device ABI/page size, another hardware OEM, complete-workflow peak/resource evidence |
| Distribution | Pinned component sources/notices and seven Maven source identities inventoried | Complete embedded-runtime/native inventory, manual notice/source completeness and application/runtime/catalog redistribution clearance |
| PC-free release gate | Development prototype and retained USB rescue; no live Android translation applied | A user completes installation, Shizuku startup, supported patch and verified non-debuggable game launch without PC/cable; usable interrupted-run recovery |

None of these remaining rows is closed by private tests or static alignment alone. Coverage counts
have not changed, so the translation coverage ledger remains unchanged.

## 2026-10-05 — Indonesian language: offline build findings and the device cycle

### Build findings

- The user supplied only `catalog.json.gz` and `mulai_game.png`. The catalog turned out to be a drop-in for
  the English one rather than a new format: `adaptive.load_catalog(folder)` reads `folder/catalog.json.gz`,
  and the `.blocks`/`.assets` files are catalog edits, not text.
- Two textures draw START GAME in package `19`. Which one the lobby uses cannot be read from the data, so
  both are re-drawn; they are the same pixels, so one render serves both.
- No BC7 encoder is installed (only `texture2ddecoder`'s decoder), so the converter carries a small mode-6
  encoder and re-encodes only the blocks the sprite touches. The device never sees BC7 — the texture pass
  decodes it and re-encodes ASTC — so its job is only to carry the render into the catalog's format.
- The user asked whether the token terms could be fixed in the catalog. They cannot: `translate_table`
  requires matching placeholders, so a pre-expanded target trips `placeholders_changed` and the record is
  dropped (`resource-token-expansion.md`). The terms became a per-language table instead.
- **Measured gap: game-shipped English stays English.** The Indonesian catalog translates Chinese
  sources (`unique`) and re-targets only the 29 750 `english_updates` rows the English catalog already had.
  Records the game itself ships in English have no row, so `translate_table` leaves them as they are:
  20 228 of 324 905 records in the staged tables (6%) are English text the English catalog maps from a
  Chinese source the Indonesian one also translates — mostly package `1`'s prime-only tables
  (`C40FFFB4C9180D66` alone holds 4522, e.g. "AI impersonates avatar 1181"). The fix belongs in the
  catalog (more `english_updates` rows), not in a pass here.

### Device cycle

**Device cycle (2026-10-05, Xiaomi M2007J3SG `f15a72e`, Android 12, game data 1.4.0.2)** — the phone
already carried the English patch from the Android app's live run, so the cycle followed `prime-rebuild.md`'s
device test loop with the Indonesian build rather than a normal app run (which would have changed no text;
see the Indonesian record's language-switch row). Evidence: `artifacts/indonesian-device-cycle-20261005.log`, `artifacts/indonesian-lobby-20261005.png`,
`artifacts/indonesian-popup-20261005.png`.

| Step | Result |
|---|---|
| Installed game APK | `29b3ee7e…` — not the cached `installed.apk` (`b0b08f…`): the two differ only in `AndroidManifest.xml`, all 1625 other entries (every prime package included) identical, signed with the project key, not debuggable. The phone's own APK was used as the restore target and the access APK built from it |
| First attempt, staged from the 10-03 pristine dump | **aborted before any write**: the phone held 731 package files against the dump's 653 — the game had downloaded more under the same `1.4.0.2` label, so a push from the dump would have reverted it. Normal APK restored and verified |
| Build base | the phone's own layer, with the six English-patched packages (`1`, `15`, `19`, `20`, `21`, `1050016095`) put back to the dump's copies: in all six every asset outside the translation is byte-identical to the dump and the only extra entries are our own appends, so the game had not touched them |
| Indonesian build on that base, `--apk phone.apk` | 391 tables, 395 textures, the same six packages; `append_skipped` the one known table. The newly downloaded packages hold no catalog content |
| Push | fresh backup matched the base except exactly the six packages; 6 packages written, Watchdog cleared, on-phone read-back **12/12** SHA-256 match; normal APK restored (`29b3ee7e…`, no `DEBUGGABLE` flag). Rollback material kept in `dist/HOK ACE Patcher Data/id-device/` (`device-backup-2.tar`, `access-phone.apk`, `phone.apk`) |
| Launch | game alive past 80 s (PID 11908); logcat has no QtsVFS error, fatal signal or `IsPrebuild` line; the session was still logged in |
| Lobby | **MULAI GAME** on the start button; Indonesian labels (Toko, Harapan, Top-up Pertama, Peringkat, Kartu, Kesejahteraan, "Undang ke tim", "2 hari 3 jam", "Jangan tampilkan hari ini"). Labels still in English — Menu, Event, Trading Post, Growth Path, Battle Pass, Precious Prayer, Lineup, Chessplayer — are the Indonesian catalog's own values for those sources |

### Device report and fixes

**Device report and fixes (2026-10-05, evening)** — walking the screens after login turned up four
bugs. Three were never Indonesian-specific: the English patch has them too.

| reported | cause | fix | device verdict |
|---|---|---|---|
| Effect Card type filter shows `通用` | hard-coded in the Lua script `9BD30F0DF58B1FBF` (package `10`, prime-only) | `extra_text.SCRIPT_LABELS`, appended | chip reads **General** |
| one effect card (Armed Power) keeps `-大河流域-` on its band | its catalog edit `884E0B4581F47CF7` is carried under `962747E1E5B73A93`; two more cards likewise | `mobile_graphics.DEVICE_REVISIONS` | band reads **Riverlands** |
| `/未翻译UI/QTSFailureTips` popup after a match | the client's QTS-failure notice, raised while three rewritten config bins are in place | `SAFE_ASSETS` emptied | 2 of 2 matches with them, 0 of 1 without |
| Announcement screen has no back arrow or title | rule pages `B5D856BFDF22400D` is `ResHelpSystemCfgDataBin`, read before the header is built | withdrawn from `SAFE_ASSETS` | "< pengumuman" with its back arrow |

Two builds were pushed, both staged from the phone's own layer with the six patched packages restored to
the pristine dump: A (both fixes, rule pages withheld) and B (A with every `SAFE_ASSETS` entry withheld).
B is byte-identical to what the committed code stages. Final counts: **388 text tables, 398 textures**,
one known table refusal. Evidence: the entry above, *Indonesian device report: four bugs, three causes*.


## 2026-10-06 — Android app: worker timeout on a MediaTek ROM, diagnostic trace, storage reclaim

### Worker connection timeout

Worker connection timeout on a second phone (2026-10-06): a user's friend got `Shizuku worker connection timed out` on four `prepare` attempts while the Shizuku app showed the server running (exported `hok-ace-recovery-log.txt`: the worker's last message comes 20 s after `Preparing verified recovery material`, and the activity never logged `Shizuku UserService connected`). Shizuku's `ServiceStarter` hands the new user-service binder back through the **Shizuku app's** content provider (`moe.shizuku.privileged.api.shizuku`, call `sendUserService`), not the server. If the provider is null it logs `provider is null` and exits with no retry. So a phone that will not start the Shizuku app in the background loses the handoff silently, while `pingBinder()` still succeeds. That fits the report and the earlier intermittent Xiaomi timeout, but no device log has confirmed it yet. The wait is now 45 s for a slow cold start. The timeout message carries the Shizuku version and uid, the phone's make, model and Android version, and the wait, so the next exported log identifies the phone. The home screen now tells the user to allow Shizuku to run in the background and keep it in Recents. Verified only by compiling: debug and release Kotlin builds and the unit tests pass. Not verified on the affected phone.

Measured on the affected phone (2026-10-06): the background-start guess above is **not** the cause there. The phone is an Infinix X6853 (XOS, MediaTek, Android 16 API 36), running Shizuku 13.6.0 as uid 2000. The new trace shows the bind issued at 12:15:15.475, no binder by 45 083 ms, and the server still answering pings. No user-service process appeared. Running Shizuku's own starter by hand (`CLASSPATH=<Shizuku apk> app_process64 /system/bin ... moe.shizuku.starter.ServiceStarter --package=dev.halixm.hokacepatcher --class=...PrivilegedDeviceService`) exits 1 after 0.4 s: `unable to start service`, caused by an NPE at `LoadedApk.makeApplicationInner(LoadedApk.java:1536)`. The phone's own `framework.jar` shows that line is MediaTek code: `Application.getProcessName().equals(mPackageName)` guarding `ResOptExt.preloadRes`. It runs for any non-system package, and the process name is null in a Shizuku user-service process. Shizuku's `UserService.create` calls `makeApplication(true, null)` before it loads the service class, so no code in this app runs and any Shizuku user service fails on this ROM. Upstream reports: RikkaApps/Shizuku#2048 (Transsion), #2561 (Android 16), #1198 (MediaTek); no upstream fix. This phone hides app and Shizuku log lines from logcat, so the app's own trace file was the only usable record.

### Own-starter fallback

Own-starter fallback (2026-10-06, device-verified on the Infinix):
- **Connection order.** `WorkerDeviceConnection` still asks Shizuku for the user service first. After 10 s with no binder it also launches `ShellServiceStarter` through Shizuku's shell-process API (`Shizuku.newProcess`, private in API 13.1.5 and reached by reflection): `CLASSPATH=<this APK> exec app_process /system/bin --nice-name=<pkg>:worker dev.halixm.hokacepatcher.ShellServiceStarter <token> <authority>`, passed as `sh -c` positional arguments rather than spliced into a string.
- **Skipped step.** The starter constructs `PrivilegedDeviceService` directly. It needs no Context, so it skips the `makeApplication` step that crashes.
- **Handoff.** The starter hands the binder to `WorkerBinderProvider` through `getContentProviderExternal` and `IContentProvider.call`, the same handoff Shizuku's own starter uses with its manager. Three gates protect it:
  - the provider is guarded by `INTERACT_ACROSS_USERS_FULL`, which only the shell holds;
  - `call` refuses any caller but uid 2000;
  - each connection's random token is single use and registered only while that connection waits.
- **First binder wins.** A late binder from the other path is refused. The starter exits when the app's client binder dies, and `close()` destroys it.
- **Remembered per phone.** The working path is saved under the ROM fingerprint plus the Shizuku server and app versions, so the next run on this phone starts the fallback at once. A new ROM build or Shizuku release tries Shizuku's starter again.

Measured:
- By hand from adb (uid 2000) with a dummy token, the starter loads, builds the service and reaches the provider, which answers `SecurityException: Unknown or used worker token` (exit 1 in 0.87 s; Shizuku's starter died there with the NPE).
- In the app, Start → prepare: no Shizuku binder after 10 016 ms, fallback launched at 10 028 ms, binder at 10 323 ms (`worker attached as uid 2000`). Preparation then completed (`prepared`, `requires_signature_conversion: true`; `prepare_game_apks` took 144.6 s). On close the starter exited with code 143 and left no worker process.

The first-setup consent that follows was left for the phone's owner, so no install or game-data step has run through this path yet. The Xiaomi path, where Shizuku's starter works, is unchanged in code but was not re-run.

### Diagnostic trace

Diagnostic trace (2026-10-06): the earlier export could not tell this phone apart. It held only untimed UI messages and the last 40 worker messages, and stack traces existed only in logcat. `DiagnosticTrace` now writes `trace.log`, rotated to `trace.log.1` past 1 MB. Each line has a timestamp, pid and tid, and errors carry full stack traces. It records:
- UI taps, home-screen changes and Activity lifecycle;
- Shizuku binder and permission events;
- worker start, progress, results, timeout and destruction;
- each step of the worker's Shizuku binding, with elapsed milliseconds;
- timing for every engine call;
- uncaught crashes.

It is evidence only: nothing reads it back, and a failed write is ignored. "Export diagnostic logs" adds:
- an environment section: app and build type, device, Android and ROM properties from a fixed allowlist, memory, battery-optimization and background state for this app and the Shizuku app, the Shizuku server's version, uid, SELinux context and permission, and the game's version and debuggable flag;
- the app's last 20 process exits from `getHistoricalProcessExitReasons`;
- per-folder storage use;
- the `build.log` and `metrics.json` of the three most recent runs;
- this app's own logcat, the last 5000 lines.

The trace and the build logs come after the recovery records, so the 8 MB export limit never drops a journal for them. Verified by compiling the app and the Android tests; not yet exported on a phone.

### Storage reclaim and build estimate

Storage reclaim and build estimate (2026-10-06): users reported running out of space after the first check had passed. Three causes, all in this app's own files. (1) Nothing removed a resolved session's bulk: every completed or cancelled run kept its game-data copy (about 2 GB on the 1.4.0.2 layer), `work/` and `out/` forever, so each repeat run started roughly 4 GB shorter. A session that reaches `COMPLETE` or `CANCELLED` now keeps only `journal.json`, the hash lists, logs, `snapshot/manifest.json` and `out/device_patch_summary.json`; the coordinator clears its bulk at the end of the run or recovery, and clears every earlier resolved session before a run's first budget. Rollback and forward recovery read only an unresolved session's files, and a damaged journal is left alone. (2) The saved official APK (`preparations/<id>/original.apk`, about 2 GB) was kept although nothing reads it after the normal and access APKs are derived; reuse, first setup and recovery go by the receipt's identity. `ApkPreparation.releaseUnneeded` deletes it once the installed game is verified as the stable-key normal build: after first setup installs the normal app, and at the start of every patch run. The same pass deletes every preparation folder whose receipt names another game version (its access APK, about 2 GB each): access is installed only over a normal build of the same version, and a new version prepares its own. The run's own preparation, a folder whose receipt will not read and anything a retained APK path links to (an unresolved session's access APK, a deduplicated copy) are kept, and it skips while a preparation runs. Recovery APKs in `recovery/` are not touched. (3) The offline-build estimate reserved every downloaded package twice and the whole APK prime, 7.50 GB on the 2.72 GB control whose actual build left 1.62 GB (`out/` 0.99 GB, `work/` 0.63 GB, `artifacts/android-control`). `build_storage.estimate` (schema 2) now reserves, twice, only the packages that hold a catalog table, texture, device revision, allowlisted or script asset, and extracts only the APK packages whose catalog content the downloaded copy lacks, as `add_prime_only` does: 2,668,538,356 bytes on the same control (prime index 37.7 MB, prime extraction 588.7 MB, staged 916.6 MB twice, replacement work 208.9 MB). On the 2026-10-05 live run, the build check reserved 6.04 GB plus installer space while the lowest sampled free space showed about 4.14 GB used from build start through the apply installs. `work/` is deleted once the build stages, before both apply installs. The snapshot check also reserves the latest completed run's schema-2 build estimate, so a copy that fits is not followed by a build that cannot. The build step still checks its own measured estimate. Verified offline: Kotlin and Android-test compilation, the six `StorageMessageTest` checks, and the estimate against the desktop control. Not yet verified: a device run, the updated `BuildStorageProbeTest` numbers on the phone, and the interrupted low-space path.

## 2026-10-06 — Android visual theme and its interface-language follow-up

Verification on 2026-10-06:

| Check | Result |
|---|---|
| `android\\gradlew.bat -p android :app:assembleDebug :app:assembleDebugAndroidTest -PfullCodecs --offline` | PASS; final incremental build completed in 44 seconds |
| Whitespace check on changed tracked UI files | PASS |
| Deliverable | `artifacts/dev.halixm.hokacepatcher.apk` copied from the successful full-codec build |
| Visual and existing `GuidedHomeProbeTest` runtime check | Not run: Medium_Phone_API_36 emulator repeatedly refused installation with `device is still booting`; connected physical phone was offline |

No phone or game operation was performed. Visual acceptance, including large-font layout,
remains unverified. The temporary headless emulator was stopped after the failed installation attempts.

Follow-up (interface language, Shizuku installation and logs):

| Follow-up verification, 2026-10-06 | Result |
|---|---|
| Full-codec app and test APK build | PASS, 54 seconds; Kotlin and test sources compiled |
| Changed tracked UI files whitespace check | PASS |
| Connected Xiaomi activity-service check | No patcher service running before installation |
| `adb -s f15a72e install -r` app update | Success, existing app data retained |
| Separate test APK installation | Refused by phone: `INSTALL_FAILED_USER_RESTRICTED: Install canceled by user`; not retried |
| Runtime interface and route probes | Not run because test APK installation was refused; behavior remains runtime-unverified |

The updated full-codec deliverable is `artifacts/dev.halixm.hokacepatcher.apk`.
No game patch, game installation, Shizuku uninstall, or game-data write was started.


## 2026-10-08 — Diamond Frenzy Effect Cards print raw `#23F7...` refs: the other ten card dictionaries

Reported on the Indonesian build installed by the Android patcher (Infinix X6853, session `c1a2e7d8`,
388 tables / 398 textures); the user says the English build shows the same. Encyclopedia → Diamond Frenzy →
Kartu Efek: every grid caption and the detail pane's name and description are raw refs
(`#23F7C87B1B68DA1C#`, `#23F7CDBFA1846C57#`), while the tabs and the "Terkait" line are translated.

- **Cause: the 2026-10-03 Talent Card failure, on the other card dictionaries.** Both refs are defined in `28D9F8B02CAA94E2`
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

### Same day: the Indonesian catalog review

- **Catalog review and remediation (2026-10-08).** A review of the Indonesian catalog found its ~1 069
  reviewed strings sound and much of the rest unvetted machine translation: Quranic verses and Tafsir
  commentary injected into skill and rule descriptions, context-blind false friends, `≥`/`≤` corrupted
  to `£`, and drifting terms (`Kerusakan` beside `Damage`, the typo `Chesplains`). `c64281e` purged 52
  hallucinated entries with curated ones, replaced the false friends, restored the symbols, normalized the
  terms and shortened two lobby labels that wrapped or clipped (`Pemain`, `Hadiah`), validating all 39 011
  entries; `90c952b` purged the remaining hallucinations and kept the Talent and combat-stat terms in
  English; `9a265ff` added `tools/research/apply_catalog_fixes.py` so the fixes survive an upstream
  re-import. The standalone review doc that drove this was folded into the Indonesian record's [S2].


## 2026-10-09 — Transsion phones: a Dual App profile, then a missing game

Unlistable profile on two Transsion phones (2026-10-09), the same failure in two users' exported `hok-ace-recovery-log.txt`: an Infinix X678B (XOS, Android 14 API 34 build `250217V838`) and a TECNO KL7 (HiOS, Android 14 API 34 build `260701V1096`), both with Shizuku 13.6.0 as uid 2000, game 1.1.1 / 774472 and language `id`. On each, `prepare` succeeds with `requires_signature_conversion: true`, then `first_setup` stops twice (about 32 s in on the Infinix, about 65 s on the TECNO) with `Device command failed (255)` and `java.lang.SecurityException: Shell does not have permission to access user 999` from `pm list packages --user 999`; only the framework line numbers differ between the two builds. On the TECNO, `pm list users` names it as `UserInfo{999:Ruang Ganda:1010} running` (the Dual App profile; flags `PROFILE | INITIALIZED`), and the refusal is AOSP `UserController.handleIncomingUser`'s shell check, which fires only for a target user carrying `DISALLOW_DEBUGGING_FEATURES` (the ` ...handleIncomingUser:14469 ...` caller line after the message, `:14398` on the Infinix, is that check's `Debug.getCallers(3)`). So shell cannot name user 999 in any `--user` command, while `dumpsys package` and `pm uninstall` with no `--user` (all users, -1) never reach that check. `requireNoOtherGameUsers` failed before any removal; the game stayed installed and unchanged. The TECNO user's own report confirms the cause on that device: switching Dual App off left user 999 `running`, and patching succeeded only after `pm remove-user 999`. The UI turned that into the Shizuku-permission advice because the raw error contains "permission", although Shizuku was working. On both phones a later `verify` against the prepared normal APK reported `Installed APK stream is incomplete`: the installed app was still the original, which is shorter than the normal one, so it was a different app rather than a truncated read. Fix, unit-tested offline (`app/src/test/.../FirstSetupProfileTest.java`) but **not yet device-verified**: when `pm list packages --user N` fails with exactly that SecurityException for N, the guard reads every profile's state from `dumpsys package <game>` (written by system_server, grep-filtered to the `Package [..]` and `User N: .. installed=` lines so the 16 KiB diagnostic cap cannot cut it off). An installed copy is still refused (`The game is installed in another Android profile`); a profile the dump does not list is refused as `Cannot check another Android profile for the game`; a dump with no record of the package counts as absent only when `pm list packages -u` agrees. `friendlyFailure` now has its own messages for those two refusals, for an installed app that is not the expected one (`InstalledGameVerifier.DIFFERENT_APP`, replacing the stream, length, hash and identity messages) and for any other `Device command failed`, ahead of the Shizuku branch. Two follow-ups from the TECNO user's report, also compiled and unit-tested only: `prepare` now runs the same read-only profile check (`IPrivilegedDeviceService.checkGameProfiles`, transaction 19, `PROTOCOL_VERSION` 9) before it copies anything, whenever the installed game's signer is not the stable key (or Android will not say), so a phone that will be refused at first setup learns it before the 3–4 minute preparation rather than after; first setup keeps its own check. And the screen no longer buries the cause: the live log stores `ErrorSummary.cause` of each message (stack frames, `... N more` and Android's appended caller list dropped, at most 8 lines), because a 30-line trace in the 180 dp log scrolled the `SecurityException` line out of view, and a failed run shows an Error details box under the notice with that summary and a Copy error details button that copies the worker's full raw `error` (`ErrorSummaryTest`).

Game missing for the main user (2026-10-09, same Infinix X678B, on the build above): the next exported log shows `prepare` stopping 0.2 s after the worker attached with only `Device command failed (1):` from `gameApkInfo`, which the new fallback above turned into "The phone refused a step". The environment block reads `game: not installed`, and the patcher's own data was fresh (no `preparations/` or `recovery/`), so the patcher had been reinstalled or cleared since the morning's runs; the earlier `first_setup` refusals stopped before any removal, so the patcher did not remove the game. `pm path --user 0 <game>` exits 1 and prints nothing when the package is not installed for user 0, including when it exists only in a Dual App profile. `gameApk` now raises `PrivilegedDeviceService.GAME_MISSING` for exactly that result, and `friendlyFailure` tells the user to install the game in the phone's main space, open it once and finish downloads, then try again. Compiled and unit-tested only. The user then reported the game **is** installed in the main space. Both lookups that said otherwise (the app's `getPackageInfo(game, 0)` and `pm path --user 0`) skip a package that is installed but hidden (XOS/HiOS Hide apps) or disabled until used, exactly as they skip an absent one, and XOS shows Dual App icons on the same home screen, so the log alone cannot tell the three apart. The missing-game error now carries each profile's `installed / hidden / suspended / enabled` state from the filtered `dumpsys package` (`FirstSetupPackagePolicy.userStates`), `friendlyFailure` names the case it finds (`missingReason`: hidden, only in another profile, or absent), and the export's `game:` line asks again with `MATCH_UNINSTALLED_PACKAGES` and says whether the record is installed for this user but unavailable, or held only elsewhere. The next log from this phone settles which it is.

It settled it as absent (2026-10-09, same Infinix X678B, exported 18:58): the first `prepare` stopped with `not installed for the phone's main user (com.tencent.tmgp.osgame; no package record)`, so no profile held the game at all. The user then installed it (`installed 2026-10-09 18:24:05`). The next two `prepare` runs got through `Checking other Android profiles for the game` in 0.4 s, copied the installed APK, and then stopped at `engine_preflight` with `Android requires all codecs and an empty package rebuild configuration`. That was the build, not the phone: the APK handed out from this branch had been built without `-PfullCodecs`, so its `requirements-arm64-v8a.imy` was empty and it carried no `astc_encoder`, `texture2ddecoder`, `ooz` or Pillow, which `REQUIRED_CODECS` gates on. The same phone had passed the preflight that morning on a full-codec build. The full-codec build is now Gradle's default and `-PfullCodecs=false` selects the minimal baseline, so a plain `assembleDebug` can no longer produce an APK that refuses every patch. The log does not say whether user 999 was still present when the profile check passed, so the fallback's device verification is still open.


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

- **Report.** User screenshot (`tools/research/career_atlas/evidence/career_screen_2026-10-10.png`): `我的棋手` beside the
  chessplayer count on the Career screen. Only the count is `TimiText`; the label is the sprite
  `Image_1904551913` of `CareerAtlas` = texture **`13C19E4E4486B31C`** (package `19`, override layer only,
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
  (216 sprites) was laid out differently from both, so the bug predates the update. The run had reported
  the edit as applied with 0 skipped. Among the misplaced labels: `MY CHESSPLAYERS` over `SUPREME STAR`,
  `VIENTIANE KING` over the `我的皮肤` label, `ACHIEVEMENT POINTS` over the QQ icon and a dashed rule.
- **How the pixel asset was found** (from the texture-translation record, folded here 2026-10-16). No
  path→QTS hash scheme matched the `.resS` name (xxh64, FNV, MD5, SHA-1, CRC64 over the usual forms), so
  every 1 MB asset of both layers was decoded at 1024x1024 4x4 and a sprite rect cropped. Tencent's
  SerializedFile header defeats UnityPy, but a Sprite record is plain: a length-prefixed `Image_<id>`,
  4-byte aligned, then `m_Rect` as four floats with y from the bottom.
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
  `tools/research/career_atlas/validate_assets.py` and fixed. The user then polished both in `tools/research/career_atlas/edit/` (new K, bolder
  SKINS, native L/R/F, 5 alpha pixels touched in MY's M); those PNGs ship and are no longer regenerated. An
  earlier image-agent delivery in `tools/research/career_atlas/delivered/` (a hand-drawn K, per its NOTES.md) was overwritten
  by a copy without looking first and is lost.
- **Device verdict (2026-10-10): the Career screen looks right.** `patcher_core` run headless (English,
  session pruning off): fresh pull of game data 1.5.0.1 into session `20261010-151438` (backup
  `device-backup.tar` there), the build staged exactly one texture — the atlas, package `19` — since
  the phone already held everything else, pushed it and restored the normal APK. The pushed atlas is
  byte-identical to `port_atlas`'s output with the hand-polished labels; the sprite layout matched the
  morning's. Other screens that draw the moved sprites were not walked.
- **Handoff detail (T14, folded here 2026-10-16 when `tasks` was retired).** The label is drawn by
  `UICarrerLordAndSkinDetaiSwitchItem` (prefab `E82B9527804B3DD5`, package `19`;
  `SetSimilarSpriteByIndex(0)`, index 1 is `我的皮肤`), found from the Career Lua in package `10`
  (`3A1EA40DF80897BF` AutoBind, `361A7A1C745B580E` class, `22DD0A0DE668B0BF` panel). The atlas's
  SpriteAtlas is `BAE55973AA41FF81`; `4AA2B26FF28CB65D` holds 218 Sprites and points at
  `assets/d8/d8e44faed20ba201548914e4792e1045.resS`. The device rects of both layouts are
  `tools/research/career_atlas/evidence/13C19E4E4486B31C_rects.json` (10-10) and
  `13C19E4E4486B31C_rects_pre-update-2026-10-03.json` beside it, each rendered with the catalog's PC boxes
  (its `regions`) in yellow; `atlas_sprites.py table` reprints the comparison. The round badges sit around 760,150–830,220 (`胜利`, `Image_1611657762`) and
  235,210–300,270 (`失败`, `Image_1795213190`). Two items stayed open: walking the other screens that draw the
  moved sprites, and the `国服` badge of the "National server Chess Player" avatar frame (`国服骑手头像框`),
  which has no catalog edit and whose texture was not located (method: frame prefab → sprite table → crop
  scan). The badge translation is `.scratch/career-atlas-badges/issues/01-win-loss-badges.md`.
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

## 2026-10-16 — Terminology table: the first direction, and an already-patched layer

- **Direction.** The first version of the change pointed `夺取` and `整备` at Plunder and Readiness, the
  unofficial community translation's names. The user corrected it the same day to Steal and Prepare, the
  names the catalog already uses most; the record's verification table measures the corrected version.
- **Already-patched session layer** (first version), from the record's verification table:

| Check | Result |
|---|---|
| `adaptive.scan` over an already-patched session layer (first version) | the scanner loads the terminology-corrected catalog through the wrapper: `already_english` moved, everything else equal |
| Full `build_device_patch.py` run on that session layer | stops in `_drop_uncatalogued_tables` on `counts["unknown"]` **with or without** this change: an already-English layer gives the scanner no unknown strings, so the key is absent. Not this feature's bug; a pristine run was not possible (that day's `pristine/` tar is truncated) |


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
- **Cycle detail** (from the card-pack-covers record, folded here 2026-10-16). Infinix X6853, Android 16,
  English. Phone and dump `1.info` both `{"version":"1.6.0.1","revision":"0"}`; the backup (`packages` +
  `Watchdog`) is 2.4 GB. Control push: `ScanJob done ... errorCode=0`. Cycle push: scan `errorCode=0`, and
  Starting Lineup still empty after a further 6 s. Offline, `append_skipped` held the same single refusal
  with its denominator 294 → 295, and the log read 293 → 294 "translated assets added from the APK". The
  appended asset is byte-equal to a fresh `pb_text.rewrite` of the APK's copy and re-parses; the two CJK
  code points a raw decode finds (`榑`, `贐`) are binary bytes the APK's copy holds too. Each record of the
  bin pairs a cover icon (`ArtHub/Icon/CardCover/lcon_CardCover_NiTianGaiMing_BaiLiXuanCe`) with its group
  label and its hero label; English and Indonesian measure the same 60 strings and 252 fields.
- **Control match, 2026-10-16: passes.** The user played a match to its end on the control build, with no
  `QTSFailureTips` popup; the phone's logcat holds no QTS-failure line either. Achievement titles read in
  English (user, same day). Still owed: the weekly leaderboards, King of Kings.
- **Disk:** C: had 240 MB free and an offline build died there (`WinError 112`). Builds now go on D:.

## 2026-10-17 — Public repository and Android release automation

The GitHub repository was renamed to `halixm-dev/hok-ace-patch` and made public at the user's
request. GitHub secret scanning, push protection, private vulnerability reporting, dependency
alerts and automated dependency security fixes are enabled. Game re-signing material remains
unchanged and intentionally public. A separately approved private patcher release signer is
stored in Actions secrets; the ignored local backup is in `artifacts/release-signing/`.

| Check | Evidence and verdict |
|---|---|
| Before public visibility | Gitleaks 8.30.1 scanned 107 commits across all fetched refs. Two findings were the same prose, `stable-key access APK, adopts/verifies `, rather than credentials. The exact-match exception passes the rescan. |
| Committed source snapshot | Gitleaks directory scan of a `git archive` export passes with no detected credentials. Compiled/native binaries are not established safe by this scan. |
| Gradle wrapper | Wrapper JAR and Gradle 8.9 distribution hashes match the upstream checksums; distribution checksum enforcement is now configured. |
| Local Android build | `:app:testDebugUnitTest :app:lintDebug :app:assembleRelease` passes. All 18 unit tests pass; all 84 packaged native libraries pass the static ELF alignment check. No device cycle was performed. |
| First clean-runner attempt | Failed because the Python target URL used the obsolete Chaquopy Maven location. Maven Central serves the pinned archive; its SHA-256 matches the existing verified local target. |
| First signed candidate, `android-v0.1.0-rc.1` | Clean Windows build, tests, lint, ELF/ZIP alignment and APK v2 signature verification pass. Certificate fingerprint matches `SECURITY.md`. Source-companion packaging then refuses CRLF-converted upstream notice files; no draft release is created. |
| Windows checkout correction | `.gitattributes` preserves notice bytes. A `core.autocrlf=true` checkout simulation matches every pinned notice hash; local packaging verifies all six original native source archives. |
| Corrected clean development CI | [Run 38980046025](https://github.com/halixm-dev/hok-ace-patch/actions/runs/38980046025) passes, including full native builds, unit tests, lint, ELF/ZIP alignment, signer verification and source-companion packaging. APK and report artifacts uploaded. |
| Corrected signed candidate, `android-v0.1.0-rc.2` | [Run 38980049065](https://github.com/halixm-dev/hok-ace-patch/actions/runs/38980049065) passes both build and release jobs. The draft contains `hok-ace-patch.apk`, `SHA256SUMS`, `hok-ace-patch-codec-sources.zip`, `android-native-alignment.json` and `release-runtime-dependencies.json`. Publication remains withheld for the documented release review. |

Actions use pinned commits and read-only build tokens. Only the separate draft-release job
has repository write permission. Tag builds use the private signer; unsigned local releases
never fall back to the development key. Existing debug installations cannot update directly
to the private signer. Device acceptance, complete redistribution/source review and the
compiled-runtime/dependency security audit remain separate work.


## 2026-10-17 — Android patcher update checker

Manual home-screen release lookup is implemented in `AppUpdateChecker` and `MainActivity`.
It uses public GitHub access and opens the exact newer release APK in a browser. English and
Indonesian UI messages are included; the patch worker and translation pipeline are unchanged.

| Check | Evidence and verdict |
|---|---|
| Public API, no credentials | Latest tag is `android-v1.6.0.1.1`, draft/prerelease false; `hok-ace-patch.apk` is uploaded and its exact GitHub URL matches the checker policy. |
| First offline build | App sources compiled; unit-test dependency resolution refused because `org.json:json:20180813` was not cached. Retried with network access. |
| Unit tests | `:app:testDebugUnitTest` passes all 26 tests, including 8 new checker tests: numeric version comparison, malformed metadata, current/older/newer releases, missing/unready/foreign APK, transport headers and cleanup, API failures, response cap, offline/timeouts and Indonesian result text. |
| Debug APK | `:app:assembleDebug` passes with full codec assets. |
| Android lint | `:app:lintDebug` passes. Combined tests/lint/debug build finished successfully. |
| Device acceptance | No phone installation, browser download or installer acceptance was performed. |

## 2026-10-17 — Restore previous patcher signer for compatible updates

The user requested the previous patcher key for CI releases. All four release signing secrets
now reference `android/signing/debug.keystore`, alias `androiddebugkey`. The key was already
public; keeping it in Actions secrets does not make it private. No game signing material or
installation/consent flow was changed. Earlier private-signer APKs remain a different identity.

| Check | Evidence and verdict |
|---|---|
| Compatible APK | The checksum-verified published `android-v1.6.0.1.1` APK was re-signed locally as `artifacts/hok-ace-patch-compatible.apk`; no unfinished source changes were built into it. |
| Signer | SDK apksigner verifies v2 and certificate SHA-256 `aa67f1993e3a335ff798d085a3e818b12988739dd3d5e69f8bdd1be97f01c249`, matching the previous patcher key. |
| Contents and alignment | Every decoded ZIP entry matches the published original; SDK `zipalign -c -P 16 4` passes. |
| Compatible APK SHA-256 | `17caa4fc20a1a5dd7380a346733e47810e8b8f428f23ed313c3d2e9059b03f61` |
| Device acceptance | No phone install was performed. Matching signer/package/version permits updating legacy installs; this does not remove Android installation prompts or the patcher's explicit consent. |


## 2026-10-17 — Chano description and Yao Combine label

The user reported Chano's untranslated card and requested that Yao's keyword read Combine.
ADB screenshots from Xiaomi M2007J3SG show Chano's English name with a Chinese 30-damage description,
and Yao's description saying `upgraded` while its footer says `Combine`.

| Evidence | Result |
|---|---|
| Screenshots | `.scratch/untranslated-card/screen.png` (Chano), `.scratch/untranslated-card/yao-before.png` (Yao) |
| Both-layer scan | `probe.py` reads the saved pristine 1.6.0.1 override layer and cached prime package 1. Updated 30/60 sources occur in catalog tables including `A07B2B9F994FB0ED` and `A336359CD92A858E`; the prime copies retain 25/50. |
| Chano cause | Both catalogs lack the exact updated numeric placeholders. The real `adaptive.translate_table` leaves 30/60 Chinese before the fix. `catalog_supplement.TEXTS` now supplies both measured variants for both languages using the catalog's older wording with the new placeholders. |
| Yao cause | English catalog maps `合成`, `href=13`, to `upgraded` once. Indonesian already uses Combine. A source-keyed terminology rule changes the measured label to Combine; other prose Upgrade wording is preserved. |
| Targeted verification | `.venv/Scripts/python.exe -X utf8 .scratch/untranslated-card/verify_fixes.py` passes for both languages: 23 table copies across both layers, all 55 updated Chano occurrences translated, Yao checked in 22 table copies. Baseline assertions reproduce the missing Chano entries and English upgraded label. Placeholder/tag checks, validation of both new pairs, and terminology idempotence pass. |
| Documentation references | `check_references.py` passes. |
| Phone state | Normal APK is not debuggable; current private package bytes could not be read. Screenshots/search only; no APK replacement, data push or device cycle. These saved-layer checks do not establish the phone's current data revision. |
| Full English staging | `build_device_patch.py` succeeds on the pristine 1.6.0.1 dump with the cached APK; output `artifacts/chano-yao-fix/out`. No skipped text tables; the existing single append encoder refusal remains. |
| Staged read-back | `verify_staged.py` reads package 1 through `QtsPackage` / `read_raw`: all 55 updated Chano occurrences translated, Yao's corrected description present in all 11 override tables carrying it. Summary: 94 tables, 186735 records, 183250 translated, 214 unknown. This is an offline run, not phone acceptance. |
| Android artifact | `android/gradlew.bat -p android --offline :app:assembleDebug` succeeds. ZIP verification confirms both modified Python modules match source byte-for-byte. Debug APK: `artifacts/chano-yao-fix/hok-ace-patch-chano-yao-debug.apk`, SHA-256 `c07ac0763d8ec0da5fbcd29f50d318e4e9f70bcf2a6dff49bce263d6d5d59a29`. No installation performed. |

The correction adds no tables or textures and changes no allowlist or package layout policy.

## 2026-10-17 — Rerun support for Yao's installed English description

The user requested updating the existing translation by rerunning, without resetting game data.
`tools/catalog_updates.py`, called after terminology at catalog load, adds 22 exact English update
rows in memory: the two measured Yao keys in each of 11 package-1 catalog tables. Each update checks
asset hash, row key and the full old English sentence; its target is the current catalog translation.
Existing upstream update identities win. Indonesian already says Combine and gains no update rows.

| Check | Evidence and verdict |
|---|---|
| Red reproduction | `check_rerun.py` translates actual pristine tables with the original catalog, then reruns with the corrected catalog. Before the update rows it fails: `23C9A9DEBB3BF40C: rerun kept upgraded`. |
| Real-table regression | The same command passes all 11 old-English tables / 22 Yao rows; second translation is byte-identical. Different asset, key and previous sentence remain unchanged. |
| Update safeguards | All new targets pass runtime validation. Reapplying the merge adds zero rows; an existing upstream identity is preserved; Indonesian data is unchanged. |
| Actual rerun staging | Copied the already-patched package 1 from the 2026-10-16 control into `artifacts/rerun-translation/game`; it contains all 22 old upgraded sentences. Normal `build_device_patch.py` succeeds against it, with no APK and no pristine restore. The no-APK run intentionally leaves other prime-only content alone. |
| Staged read-back | All 22 Yao descriptions now equal the current Combine translation, read through `QtsPackage` / `read_raw`. `text_skipped` empty. The staged rerun also picks up other current text corrections (274 records total, including Chano); no new catalog table or texture coverage. |
| Android build | Offline `:app:assembleDebug` succeeds. ZIP contents of `catalog_updates.py`, `catalog_supplement.py` and `terminology.py` exactly match source. APK: `artifacts/rerun-translation/hok-ace-patch-rerun-debug.apk`, SHA-256 `e8ebd9b0d7b059f670307a8de981212638515aabc2992cbe36191a94d93765bb`. |
| Repository checks | `check_references.py` and `git diff --check` pass. |
| Device status | No installation or phone data write. On-phone acceptance of this rerun remains pending. |

This supports the measured Yao correction, not arbitrary old wording or language switching. Further
installed-text corrections need their own measured exact update identities.

## 2026-10-17 — Offline staging performance baseline

The staging-performance scripts and receipts left the tree once PR #11 merged. Paths below written
`1aa2573:.scratch/staging-performance/<file>` are read with `git show 1aa2573:.scratch/staging-performance/<file>`;
restore the folder with `git restore -s 1aa2573 -- :/.scratch/staging-performance` before running a
command that names one.

The user requested stage measurements before considering Rust for text/package processing.
`1aa2573:.scratch/staging-performance/measure.py` wraps the real `build_patch` functions without
changing shipping code. Python 3.12.13, Windows 11 build 26200, English catalog, saved pristine
1.6.0.1 override layer (`dist/HOK ACE Patcher Data/pristine/20261016-101124/game`), cached
`dist/HOK ACE Patcher Data/installed.apk`. Each invocation uses a fresh directory under
`D:/scratch/hok-staging-performance/`; no phone access, source-dump write, or whole-package rebuild.

Stage wall times below exclude nested measured stages, so catalog loading and extra text are
not counted twice. Total excludes interpreter/import startup, USB transfers and installation.
These are two sequential runs with normal Windows caching, not controlled cold-cache trials.
They use lightweight timing wrappers, without cProfile. Raw results are
`1aa2573:.scratch/staging-performance/run1.json` and `run2.json`; generated packages and full logs
remain outside the repository. Timing variation is substantial; do not treat one run as a guarantee.

| Stage (seconds elapsed) | Run 1 | Run 2 |
|---|---:|---:|
| Catalog loading and terminology, three loads | 1.280 | 1.329 |
| Scan and translate text, excluding catalog load | 15.490 | 10.135 |
| Catalog-only filtering | 0.006 | 0.003 |
| Resource token expansion | 4.471 | 3.961 |
| Text chunk eligibility | 0.290 | 0.225 |
| Write text packages | 5.914 | 5.350 |
| Relocate overflow text | 1.538 | 1.056 |
| Extra text pass | 26.646 | 14.812 |
| Texture pass and discovery, excluding catalog/extra text | 70.915 | 59.500 |
| Repair card dictionaries | 12.786 | 8.817 |
| Append APK-only assets, including their text and textures | 90.931 | 78.242 |
| APK transform preparation | <0.001 | <0.001 |
| Remaining orchestration/logging | 0.666 | 0.250 |
| **Total elapsed** | **230.933** | **183.681** |
| Process CPU time (not another elapsed stage) | 115.266 | 83.766 |

Nested measurements below are already included above and must not be added to stage totals.
Run 1 groups nested detail under the outer stage; run 2 groups it under the immediate measured
stage to separate extra text from textures. Exclusive stage accounting is the same in both.

| Measured work | Run 1 | Run 2 |
|---|---:|---:|
| Actual `adaptive.translate_table`, 503 calls across both layers | 5.978 s | 4.448 s |
| `QtsPackage.build_slot_map`, 274 calls | 74.891 s | 61.341 s |
| ASTC encoding, override textures | 7.498 s | 4.099 s |
| ASTC encoding, APK-only textures | 50.727 s | 33.122 s |
| APK extraction inside append | 11.262 s | 7.454 s |
| Append and read-back verification | 7.166 s | 12.066 s |

The extra-text pass makes 238 slot-map calls; run 2 spends 14.204 of its 14.812 s there.
Card repair spends 8.165 of 8.817 s building five maps. Source inspection shows `plan_scripts`
and `plan_package` build maps before establishing whether the package has any eligible asset;
card repair similarly builds maps before checking whether a dictionary needs repair. These
are candidates for filtering earlier, preserving all current gates and read-back verification.
This measurement does not establish an optimization's safe behavior or achievable speedup.

**Verdict:** actual table translation is only about 2.4–2.6% of total staging time on these
inputs. Even eliminating that work entirely would save under 3%. Repeated package scanning,
file handling and existing native texture encoding deserve investigation before a language
rewrite. This Windows baseline does not measure Android/Shizuku performance.

A third run with cProfile succeeds (191.746 s elapsed, 100.391 s process CPU). Its
function timings are diagnostic only: profiling substantially inflates frequently called
Python functions, and caching/scheduling also change between runs. `calls.prof` remains in
`D:/scratch/hok-staging-performance/profile/`; the text export and stage timings are saved as
`1aa2573:.scratch/staging-performance/calls.txt` and `profile.json`.

| Profile evidence | Observation |
|---|---|
| Package maps | 274 calls; underlying chunk iterator yields 886,749 times; repeated parsing performs millions of integer reads. |
| Extra-text planning | 120 `plan_scripts` calls and 118 `plan_package` calls, matching the 238 slot-map calls. |
| File operations | Buffered writes 33.573 s, buffered reads 22.552 s, Windows file copy 13.499 s and file opens 12.343 s of internal time in this profiled run. These are not CPU-only timings. |
| Native encoding | 3,654 calls to the existing ASTC compressor; 27.530 s internal time in this profiled run. |
| Output equivalence | All three runs produce identical SHA-256 hashes for all 14 staged `.db` files, identical text counts, and identical text/append skip reports; `1aa2573:.scratch/staging-performance/verification.json`. |
| Staging result | Each run stages 94 override text tables (183,250 translated records); no text tables skipped. Existing APK append encoder refusal `3A70308AAF6F18F8` remains. The scan's `graphics: 0` is not the texture-applied count. |
| Scope | Measurement only. No optimization, Rust port, phone install or device cycle. |

Reproduce from the repository root with Python 3.12, choosing a new external run directory:

```powershell
.venv/Scripts/python.exe -X utf8 1aa2573:.scratch/staging-performance/measure.py --game 'dist/HOK ACE Patcher Data/pristine/20261016-101124/game' --apk 'dist/HOK ACE Patcher Data/installed.apk' --run D:/scratch/hok-staging-performance/new-run
```

Add `--profile` only for call attribution; compare normal stage times without it.

## 2026-10-17 — Skip unnecessary extra-text and card-repair chunk scans

The user authorized optimizing the unnecessary scans identified above. `extra_text.plan_scripts`
and `plan_package` now check the index for eligible, non-skipped assets with supported compression
before building a slot map. Config eligibility remains `SAFE_ASSETS | candidates`. The config
planner retains slot iteration order for jobs it does translate. `repair_card_dictionaries` checks
the selected package index for non-native dictionary chunk sizes first, still preferring a staged
package over the source. No slot-map cache is shared across package writes; required scans, layout
checks, allowlist gates and read-back verification retain their existing paths.

Two fresh offline English runs use the same dump, APK and timing script as the baseline above.
Raw timings are `1aa2573:.scratch/staging-performance/optimized1.json` and `optimized2.json`. Working
packages/logs remain under `D:/scratch/hok-staging-performance/optimized1` and `optimized2`.

| Measurement | Baseline runs | Optimized runs |
|---|---:|---:|
| Slot-map calls, full staging | 274 / 274 | 31 / 31 |
| Extra-text slot-map calls | 238 / 238 | 0 / 0 |
| Card-repair slot-map calls | 5 / 5 | 0 / 0 |
| Extra-text checks | 26.646 / 14.812 s | 0.996 / 0.744 s |
| Card-repair checks | 12.786 / 8.817 s | 0.645 / 0.746 s |
| Total offline staging elapsed | 230.933 / 183.681 s | 164.056 / 188.715 s |
| Total process CPU | 115.266 / 83.766 s | 82.547 / 111.609 s |

**Verdict:** removes 243 of 274 chunk scans (88.7%) on this input. The two targeted stages drop
from 23.6–39.4 s combined to 1.5–1.6 s. Overall timing remains variable: the second optimized run
spends 56.134 s in APK texture encoding, versus 25.222 s in the first optimized run. These are
ordinary sequential Windows runs, not controlled paired trials, so claim the scan reduction and
measured stage savings rather than a guaranteed overall percentage.

| Verification | Result |
|---|---|
| Full staged-package equivalence | Both optimized runs match all 14 baseline `.db` SHA-256 hashes; full summary matches after normalizing only the per-run APK source paths. Evidence: `1aa2573:.scratch/staging-performance/optimized-verification.json`. |
| Eligible-path and skip regressions | `.venv/Scripts/python.exe -X utf8 1aa2573:.scratch/staging-performance/check_scan_guards.py` passes nine checks: missing/skipped/unsupported scripts, eligible Lua read/rewrite, missing script chunks, config allowlist/candidate gates, eligible config translation, native card skip, staged-index precedence, required card repair, and unreadable-card reporting. |
| Contract and references | `check_staging_contract.py` and `check_references.py` pass. |
| Scope | Source change verified offline on Windows. No APK/executable rebuilt and no phone/device cycle performed. Coverage and skip verdicts are unchanged. |

## 2026-10-17 — Optimized Android APK and PC pristine snapshot restored to Xiaomi

The user requested building the optimized APK and restoring the PC's saved pristine data so their
next patching run starts from that layer. Target: Xiaomi M2007J3SG, serial `f15a72e`. The phone's
current data was patched; it was backed up, not used as the pristine source.

| Check | Evidence and verdict |
|---|---|
| Build | Offline `:app:assembleDebug -PpatchVersionCode=30` passes; version `1.6.1.3`, code 30 matches the installed patcher for an in-place update. |
| Packaged source | `extra_text.py`, `device_extensions.py` and `build_device_patch.py` inside the APK match source byte-for-byte. Content-addressed engine extraction selects the updated resource manifest. |
| APK | `artifacts/staging-performance/hok-ace-patch-optimized-debug.apk`; SHA-256 `9ea6af25da9299b753810ec43c2d8109ac3d6635c86e156810865afa50852a61`. ADB update succeeds; installed APK has the same hash. |
| Signer and native alignment | APK v2 signature verifies; certificate SHA-256 `aa67f1993e3a335ff798d085a3e818b12988739dd3d5e69f8bdd1be97f01c249`. All 84 native libraries pass ELF alignment; `zipalign -c -P 16 4` passes. |
| Pristine source | PC snapshot `dist/HOK ACE Patcher Data/pristine/20261016-101124/device-backup.tar`. Its package hashes match the saved snapshot record; phone and source marker both `1.6.0.1`, revision `0`. |
| Recovery backup | Current phone `packages` and `Watchdog`: 745 files archived and hash-verified before overwrite. Retained at `D:/scratch/hok-staging-performance/phone-pristine-20261017-retry/before-pristine.tar`, SHA-256 `c60d380b1c1aa2b19815bfb79bd1360a29a8e83acf96f724c84e7d008e638799`. |
| Restore | Transferred archive hash verified, old directories moved aside, pristine archive extracted, all 553 restored file hashes and the full file set match the PC archive. Temporary phone files removed after verification; PC recovery backup retained. |
| Normal game | Reinstalled normal APK; installed SHA-256 `29b3ee7e5a0d21de7d1282d704416402d341b651da95af2eeb5b274c818defdc` matches the saved recovery APK. `DEBUGGABLE` absent. Access APK is no longer installed. Phone reports 15 GB free. |
| Next-run state | Existing patch session is `COMPLETE`, `normal_verified: true`, `packages_dirty: false`. Fresh patching takes a live snapshot of the restored pristine layer. No patch run or game launch was started by the agent. Phone timing and screen acceptance remain for the user's rerun. |

The initial stdout-stream recovery backup hit its 300 s timeout before any game-data write; the
normal APK was restored. Retry created the recovery archive on the phone and used ADB file transfer,
which succeeded. Full restore receipt remains in the external retry directory; concise receipt is
`1aa2573:.scratch/staging-performance/phone-restore.json`. The partial archive from the timed-out attempt
is not a verified recovery backup.

## 2026-10-17 — User's phone patch completed; optimized patcher restored afterward

After reconnecting the Xiaomi, the patcher's visible log reports verified patch/normal-APK recovery
after an interrupted final installation. Retained session `174600da-38c5-4b2e-abf2-0e791f8f2f04`
is `COMPLETE`, `normal_verified: true`, `packages_dirty: false`. The game data was not rewritten
again during this verification. The normal game APK's installed hash remains the verified
`29b3ee7e5a0d21de7d1282d704416402d341b651da95af2eeb5b274c818defdc`; `DEBUGGABLE` is absent.

| Evidence | Result |
|---|---|
| Retained run metrics | Status `complete`, elapsed 768.868 s (12 min 49 s), sampled RSS peak 1,655,092 KiB, process-lifetime high-water RSS 1,801,792 KiB, observed free-space decrease 5,887,877,120 bytes, maximum battery temperature 42.2 C, maximum thermal status 0. Lifetime high-water is not necessarily this run's peak; sampling can miss peaks. |
| Visible phase log | Build begins 10:06:32, next access install begins 10:11:13: approximately 4 min 41 s for build. This is a log-derived interval, not an internal stage profile. Final recovery verified at 10:16:24. |
| Staging summary | Same override census as the offline control: 94 tables, 183,250 translated records; no skipped text or textures; existing single APK-append encoder refusal remains. |
| Build actually used | On reconnection the installed patcher hash is `956ec3a29e259e6f4495793f74032ade6d77a8a34f45af601e6161dfbb38724e`. Its packaged `extra_text.py`, `device_extensions.py` and contract lack the scan optimization, even after newline normalization. The cause of this intervening APK replacement is not established. These timings are therefore an older-code baseline, not an optimized phone benchmark. |
| Optimized patcher reinstated | ADB in-place update succeeds; installed APK hash is again `9ea6af25da9299b753810ec43c2d8109ac3d6635c86e156810865afa50852a61`. Completed game data and retained session are preserved. No second patch run was started. |
| Startup observation | Game process exists after launch; sampled AndroidRuntime/Unity error log has no lines. The screenshot shows the launcher, so this does not establish login/lobby or translated-screen acceptance. User screen checks remain pending. |

Evidence is retained under `artifacts/staging-performance/phone-completed-session/` (journal,
resource metrics and staging summary), with completion UI XML and the inspected installed APK
beside it. The earlier cancelled session remains a separate record; its cancellation is not
the completed session's final verdict.

**User verdict, 2026-10-17: works.** After the completed patch was verified and the user was asked
to open the game and check the translated screens, the user replied "Works". This establishes
user-reported success for this phone/run; individual screens were not enumerated. The completed
patch ran the older engine code, so this is not an optimized phone timing result. The optimized
patcher remains installed for future runs.

## 2026-10-17 — Read B-tree pages without loading shard payloads

Continued the offline staging optimization from the saved profile. The live-slot wrapper called
`btree_offsets(Shard(path))` on every single-shard slot-map build. `Shard` reads the whole file and
copies it into a mutable bytearray, although this check needs only the page table and tree pages.
`qts_relocate._read_btree_offsets` now reads those pages with seeks. The writable `Shard`, runtime
chunk scanner, stale-slot replacement and append read-back verification retain their existing paths.
Every check opens the current file afresh; there is no cache across package writes.

| Targeted evidence | Result |
|---|---|
| Red reproduction | `.venv/Scripts/python.exe -X utf8 1aa2573:.scratch/staging-performance/check_btree_reads.py` initially fails only the bounded-read assertion: 1,048,576 bytes read for a tiny synthetic tree, against a 32,768-byte ceiling. |
| Focused checks after change | Eight checks pass: active versus superseded physical pages, duplicate keys, bounded reads, fresh values after a write, absent leaves, truncated tree, wrong logical self-id, unreadable-tree fallback, and relocated-slot selection (some checks cover multiple properties). |
| Real-shard differential | `measure_btree_reads.py` compares all 120 pristine shards plus seven verified staged shards from `optimized1/out`: all 127 live-offset maps equal the legacy implementation. |
| Bytes returned by reads | Legacy 3,246,702,592 bytes; page reads 2,126,888 bytes (99.93% fewer). These are Python read bytes, not measured physical disk traffic. |
| Paired elapsed time | Legacy 10.170 s; page reads 2.275 s. Alternating implementation order per shard; ordinary Windows cache and scheduling, one pass. This is the tree check alone, not total staging. |

Raw per-shard paths, bytes and timings: `1aa2573:.scratch/staging-performance/tree-read-comparison.json`.
Reproduce with Python 3.12 using `measure_btree_reads.py` with the pristine game directory and
`D:/scratch/hok-staging-performance/optimized1/out` as positional directories, plus `--output <json>`.

The first full English staging run uses the same pristine dump, cached APK and `measure.py` command
as the baseline, with fresh external directory `D:/scratch/hok-staging-performance/tree-pages1`.
Raw timings are `1aa2573:.scratch/staging-performance/tree-pages1.json`; verification is
`1aa2573:.scratch/staging-performance/tree-pages-verification.json`. The real-shard comparison and small
regression checks ran concurrently during part of this first run; it is not an isolated timing trial.

| Full-run evidence | Result |
|---|---|
| Output equivalence | All 14 `.db` SHA-256 hashes equal the original `run1` baseline. Complete summary equals the previously baseline-verified `optimized1` control, normalizing only each run's prime-source path prefix. Counts and all skip lists are included. |
| Gates retained | 31 slot-map calls; 94 staged override text tables; 183,250 translated records; no skipped text or textures; existing single append encoder refusal unchanged. |
| First total elapsed / CPU | 270.807 s / 163.688 s. Earlier scan-optimized totals were 164.056 / 188.715 s. |
| Native ASTC encoding | 118.960 s, versus 30.551 / 63.865 s in the earlier scan-optimized runs. These nested times are already included in total elapsed. |
| Whole slot-map builds | 36.079 s, versus 43.157 / 32.854 s previously; this includes the unchanged chunk scanner and stale-slot recovery, not just the optimized tree check. |
| Repository verification | Eight focused tree checks, nine existing scan-guard checks, reference check, staging-contract check and diff whitespace check pass. |

A second full run, `D:/scratch/hok-staging-performance/tree-pages2`, ran without the concurrent
real-shard benchmark. Raw timings are `1aa2573:.scratch/staging-performance/tree-pages2.json` and full
verification is `1aa2573:.scratch/staging-performance/tree-pages2-verification.json`.

| Measurement | Second run |
|---|---:|
| Total elapsed / process CPU | 200.174 / 129.578 s |
| Whole slot-map builds, still 31 calls | 13.938 s |
| Native ASTC encoding, both layers combined | 88.703 s |
| Output equivalence | All 14 original package hashes and the complete normalized summary match again. |

**Verdict:** removes whole-shard reads and mutable copies from the live-offset check, with measured
paired read/time reduction and byte-identical staged output in both runs. Both full runs are slower
overall than the earlier scan-optimized runs; native encoding and other work vary substantially.
The repeat reduces whole slot-map time, but this establishes no end-to-end speedup or Android
timing claim. Source-only optimization: no executable/APK build, phone install or device cycle.

## 2026-10-17 — Small ASTC reuse

The user requested investigating duplicate texture encoding next. `audit_astc.py` wraps the real
encoder during full English staging against the same pristine dump and cached APK, preserving
every native call. It saves exact RGBA inputs, geometry, encoded outputs and call order under
`D:/scratch/hok-staging-performance/astc-audit1/`. That audit output matches all 14 original
baseline package hashes and the full normalized summary (`astc-audit-verification.json`). Audit
recording adds overhead, so its full elapsed time is diagnostic, not a fair uncached speed control.

| Audit evidence | Result |
|---|---:|
| Native requests / exact unique inputs | 3,654 / 1,481 |
| Repeated requests | 2,173 |
| Total native encode time / repeated native time | 26.634 / 1.324 s |
| Unique captured RGBA bytes / encoded bytes | 81,493,984 / 6,048,016 |
| Model: 512 entries, inputs no larger than 4096 bytes | 2,035 hits; 1,679,360 bytes peak retained input + output payload |

The repeats are mostly cheap strips. Most large images are unique on this input; the follow-up
below identifies two repeated full-image inputs. Caching all large images would retain much more
memory with little additional benefit. `mobile_graphics.encode_astc`
now uses an LRU of at most 512 small results. Exact pixel bytes, width, height and both footprint
dimensions are the key. Large images use the unchanged native function, encoder settings stay
unchanged, and failures are not cached. Pixel input retention is bounded to 2 MiB, plus encoded
outputs and Python overhead. The cache lives only in this process and stores no mutable package state.

`check_astc_reuse.py` first fails its duplicate-request assertion (two native calls instead of one).
After the change all eight focused checks pass: identical requests, changed pixels, changed geometry,
changed footprint, large-image bypass, the 4096-byte boundary, failure retry and LRU eviction/capacity.

The first isolated replay failed on sample 240 even with reuse disabled. Its native output differs
when the audit's initial large 8x8-footprint image is omitted. A fresh process encoding that large
image first reproduces the recorded bytes; beginning with a small 4x4-footprint strip does not.
The cause inside the native library is not established; this first-request dependency was not changed.
The corrected replay preserves the first
native request (sample 0) before timing, empties the result cache each round, and alternates native
versus reuse order. All 3,362 small requests match their recorded encoded bytes in all six passes.

| Replay round | Uncached small encoding | Reused small encoding | Native calls before → after |
|---|---:|---:|---:|
| 1 | 1.764 s | 0.968 s | 3,362 → 1,327 |
| 2 | 1.783 s | 0.950 s | 3,362 → 1,327 |
| 3 | 1.738 s | 0.923 s | 3,362 → 1,327 |

These are the small-input sequence only, excluding initial native setup and the expensive large
images. The measured saving is about 0.8 s, not the majority of texture encoding or full staging.
Evidence and reproduction scripts live in `1aa2573:.scratch/staging-performance/`: `astc-audit-summary.json`,
`astc-replay.json`, `analyze_astc_audit.py` and `replay_astc.py`. The replay takes the external audit
run directory and `--output <json>`; the audit accepts the existing `measure.py` arguments.

The optimized full run uses a fresh `D:/scratch/hok-staging-performance/astc-reuse1` directory with
the normal `measure.py` command, without audit recording or cProfile. The harness now includes the
small-result cache counters in its timing JSON, outside the shipping staging summary.

| Full-run verification | Result |
|---|---|
| Package bytes | All 14 `.db` SHA-256 hashes equal the original baseline. |
| Complete summary | Equals the already baseline-verified control, normalizing only per-run prime-source paths; all counts, skips and package reports unchanged. |
| Encoder work | 3,654 requests, 2,035 cache hits, 1,327 small misses and 292 larger native requests: 1,619 actual encodes instead of 3,654. Cache ends at its 512-entry limit. |
| Full elapsed / CPU | 108.716 / 51.172 s. The audit run took 130.670 / 54.281 s, but recording and ordinary cache/scheduling differences prevent attributing that total difference to reuse. |
| Regression and repo checks | Eight cache-boundary checks, eight tree-read checks and nine scan-guard checks pass; reference, staging-contract and diff whitespace checks pass. |
| Evidence | `1aa2573:.scratch/staging-performance/astc-reuse1.json` and `astc-reuse-verification.json`. |

**Verdict:** keep the bounded small-result reuse. It removes 2,035 native calls on this input,
preserves all staged bytes and saves about 0.8 s in the paired small-input replay. It does not remove
the expensive unique full-image work or establish an overall staging speedup. Coverage is unchanged.
Source-only change: no executable/APK build, phone install or device cycle.

## 2026-10-17 — Remaining duplicate encoding after bounded reuse

The user requested continuing the offline duplicate-encoding investigation. Replayed the saved
audit's call order through the existing 512-entry, 4096-byte LRU policy, without encoding again
or staging another package. `remaining_astc_duplicates.py` reproduces the already verified 2,035
hits and explains every repeated request that still reaches the native encoder.

| Remaining reason | Duplicate calls | Recorded native work |
|---|---:|---:|
| Small input was evicted | 111 | 0.061 s |
| Input exceeds the size limit | 27 | 0.261 s |
| **Total** | **138** | **0.322 s** |

Two of the 27 oversized repeats are full 568x304 images, 690,688 RGBA bytes each: sample 1438,
seen again for texture `8479F18546A1B9B7`, costs 0.143 s; sample 1441, seen again for
`BD31CADEBB589D0C`, costs 0.118 s. The other 25 oversized repeats cost just 0.000293 s combined.
This corrects the earlier blanket statement that large images were all unique; most are unique,
and these two repeated full images offer only 0.260 s of recorded work to avoid.

**Verdict:** keep the current cache limit. Even eliminating every remaining duplicate would avoid
only 0.322 s of encoder work in this audit, before reuse overhead; this is a recorded-work estimate,
not a measured additional speedup. No further shipping-code change is justified by duplicate encoding.
Package reads/writes and unique-image encoding remain better candidates for the next investigation.
Evidence: `1aa2573:.scratch/staging-performance/astc-remaining-duplicates.json`; reproduction:
`remaining_astc_duplicates.py <external-audit-run>/astc-audit.json --output <json>` with Python 3.12.
No package writes, APK/executable build or phone access in this follow-up.

## 2026-10-17 — Remove full-file temporary copies from writable shard I/O

The user requested implementing the package-read/write optimization next. The saved profile
identified substantial file handling costs; source inspection found `Shard.__init__` loaded an
immutable full-file buffer and copied it into a bytearray, while `save` copied a full bytearray
slice and then copied it again into bytes before writing. These temporary copies are unnecessary
for the package writer's mutable buffer.

`Shard` now determines the size through its open file handle, allocates one bytearray, and fills it
with `readinto`. Short reads continue filling the remaining view; premature EOF or an extra byte
after the expected end refuses a file that changed size during loading. Saving retains the original
header updates, growth rounding, padding and bounded file length, but passes a memoryview to the
existing write path. The view is released before returning so later appends can resize the data.
No package state is shared across writers, no on-disk write is skipped, and append read-back stays.

| Focused verification | Result |
|---|---|
| Red reproduction | `check_shard_io.py` fails two memory assertions before the change: loading a 4 MiB fixture peaks at 8,389,002 Python bytes; saving allocates 8,388,726 additional bytes. Byte/lifecycle checks already pass. |
| After change | Seven I/O checks pass: load/save memory bounds, legacy bytes with growth and excess tail, repeated save/reload, failure-path outer-view release, short reads and changed-size refusal, zero padding and header growth. |
| Real file benchmark | `measure_shard_io.py` generates one valid 64 MiB synthetic shard plus two disposable copies under `D:/scratch/hok-staging-performance/shard-io-pairs1`; three alternating legacy/direct trials, same last-byte edit. Every saved SHA-256 matches; source unchanged. Setup, copies and hashes are outside timings. |

| 64 MiB shard measurement | Legacy | Direct buffer |
|---|---:|---:|
| Python allocation peak while loading | 128.001 MiB | 64.010 MiB |
| Additional Python allocation peak while saving, no growth needed | 128.000 MiB | 9.32 KiB |
| Load elapsed range, three trials | 0.132–0.424 s | 0.130–0.317 s |
| Save elapsed range, three trials | 0.779–0.912 s | 0.764–0.812 s |
| Load CPU range | 0.047–0.078 s | 0.031 s |
| Save CPU range | 0.094–0.141 s | 0.047–0.078 s |

Memory measurements use `tracemalloc`, not total process RSS; save peaks exclude the already
allocated mutable shard and the benchmark needs no growth padding. The original buffer and other
pipeline objects remain live. Wall times include normal Windows caching/scheduling and no fsync;
the benchmark supports eliminating memory copies, not a guaranteed overall speedup.
Raw paired evidence: `1aa2573:.scratch/staging-performance/shard-io-pairs.json`. Reproduce with Python 3.12:
`measure_shard_io.py --work <new-external-directory> --output <json>`. The full staging harness now
records nested `Load writable shards` and `Save writable shards` timings, already included in
the exclusive stages and never added to them.

Full English staging uses the same pristine dump and cached APK in a fresh
`D:/scratch/hok-staging-performance/shard-io1` directory. Raw timings are
`1aa2573:.scratch/staging-performance/shard-io1.json`; package hashes and full-summary verdict are
`1aa2573:.scratch/staging-performance/shard-io-verification.json`.

| Full-run verification | Result |
|---|---|
| Package bytes and summary | All 14 original baseline `.db` SHA-256 hashes match. Complete summary equals the previously baseline-verified control after normalizing only per-run prime-source paths. Counts, package reports and every skip list unchanged. |
| Writable shard I/O | 13 loads, 1.683 s combined; 13 saves, 21.661 s combined. These nested values are already included in stage totals. |
| Full elapsed / process CPU | 110.152 / 48.734 s, versus the preceding ASTC-reuse run's 108.716 / 51.172 s. Ordinary sequential runs, not controlled wall-time trials. |
| Regression checks | All 32 pass: seven I/O, eight tree-read, nine scan-guard and eight ASTC-reuse checks. Reference, staging-contract and diff whitespace checks also pass. |

**Verdict:** keep direct-buffer package I/O for the proven removal of full-size temporary copies
and byte-identical results. No overall elapsed-time improvement established. No claim about total
pipeline RSS or Android memory/performance; the allocation benchmark is a focused Windows check.
Coverage unchanged; no executable/APK build, phone install or device cycle.

## 2026-10-17 — Save only changed 64 KiB shard regions

The user authorized continuing offline to investigate reduced disk writes. A deterministic 4 MiB
fixture shows that the preceding `Shard.save` submits 4 MiB even when unchanged, and the same amount
for a one-byte edit. `check_changed_writes.py` initially fails three write-volume/idempotence assertions;
its byte-preservation checks already pass.

`Shard.save` now opens the staged file for read/write, compares bounded 64 KiB regions with the full
intended output buffer and writes only differing regions. It recreates a missing file, preserves
the former writer's padding/header behavior and final length, and truncates an excess disk tail.
An unchanged repeat save submits no writes. It compares current disk bytes afresh, so arbitrary
in-memory edits and external disk differences need no dirty-range cache or write bookkeeping.
Short writes raise; parent and per-write views release even when an exception traceback is retained.
This changes staged-file I/O only; package layout, gates and read-back verification are unchanged.

Nine changed-write checks pass: unchanged save, one-byte write bound and second-save idempotence,
growth/header/distant edits against legacy bytes, missing-file recreation, extra-tail truncation,
external same-size disk mutation, 600 appended records causing a root split, relocation live-slot
repointing, and write-error/short-write buffer release. Together with the earlier checks, 41 pass.
The old save-memory guard is updated from 128 to 256 KiB to allow bounded comparison buffers;
full-file temporary copies remain prohibited by the assertion.

`measure_shard_io.py --control whole` compares against the immediate preceding whole-buffer writer,
without reintroducing the older whole-file memory copies. Three trials alternate implementation
order, with setup/copies/hashes excluded. Every saved SHA-256 matches and source bytes stay unchanged.

| 64 MiB fixture save, three trials | Whole-buffer writer | Changed-region writer |
|---|---:|---:|
| One-byte edit elapsed | 0.131–0.138 s | 0.027–0.031 s |
| One-byte edit plus 8 MiB appended | 0.154–0.205 s | 0.036–0.077 s |
| Extra Python allocation peak, one-byte edit | ~9.3 KiB | ~137.3 KiB |

These ordinary Windows-cache measurements show the focused save improvement and its bounded-memory
tradeoff; they exclude fsync and do not establish an Android or overall staging speedup. Evidence:
`1aa2573:.scratch/staging-performance/changed-write-pairs.json` and `changed-write-growth.json`. Reproduce
with `measure_shard_io.py --control whole [--append-mib 8] --work <new-external-dir> --output <json>`.

Scratch housekeeping before this experiment: removed only the agent-generated, baseline-equivalent
`D:/scratch/hok-staging-performance/shard-io1` and `astc-reuse1` directories after validating their
saved receipts and checking resolved paths/reparse points. Their timing JSON and hash receipts remain
in `1aa2573:.scratch/staging-performance/`. Original baseline controls, the pristine dump, all recovery
backups and `astc-audit1` input recordings are retained. This freed space for a fresh full experiment;
the removed package outputs were duplicates that can be regenerated, not recovery sources.

Full English staging with the same pristine dump and cached APK runs in a fresh
`D:/scratch/hok-staging-performance/changed-writes1` directory. `audit_shard_writes.py` wraps file
handles only during `Shard.save`, counting reads and submitted writes without changing their bytes.
For each save it records the final file size, which is exactly what the preceding whole-file writer
would have submitted. This counterfactual does not require another legacy staging run. It excludes
package copies, the compiled text stager's I/O, other index writes and APK extraction; these are
shard-save counters, not total pipeline or physical disk traffic.

| Full-run evidence | Result |
|---|---|
| Byte equivalence | All 14 original baseline `.db` SHA-256 hashes equal; the full normalized summary matches the verified control, including all counts, package reports and skip lists. |
| Saves / whole-file equivalent | 13 / 1,033,682,944 write bytes |
| Actual submitted writes | 86,491,136 bytes in 1,323 calls; **91.633% fewer write bytes** |
| Comparison reads | 950,321,152 bytes returned by file reads |
| Combined shard-save elapsed | 2.266 s, versus 21.661 s in the preceding whole-buffer staging run. Nested in stage totals; ordinary sequential Windows runs, not controlled paired staging trials. |
| Full staging elapsed / CPU | 134.643 / 84.141 s, versus 110.152 / 48.734 s previously. |
| APK ASTC encoding | 49.177 s, versus 20.930 s previously. Native encoding variation outweighs the save-time reduction; no overall speedup established. |
| Regression and repo checks | All 41 pass (nine changed-write, seven I/O, eight tree-read, nine scan-guard, eight ASTC-reuse); references, staging contract and diff whitespace pass. |

Raw evidence: `1aa2573:.scratch/staging-performance/changed-write-audit.json`, `changed-writes1.json` and
`changed-writes-verification.json`. Reproduce the full audit using `audit_shard_writes.py` with the
existing `measure.py` arguments and a new external run directory.

**Verdict:** keep changed-region saves. The paired file benchmarks improve, actual staged bytes are
identical, and submitted shard-save writes fall 91.6% on this input. It costs bounded comparison
memory and extra reads; no Android or end-to-end performance claim. Coverage unchanged. No
executable/APK build, phone install or device cycle.

## 2026-10-17 — Optimized Android APK installed; isolated engine checks pass

The user asked the agent to perform the next useful step after the offline optimizations. Built
and verified the Android artifact, checked live update compatibility and clean retained sessions,
updated only the development patcher, then ran app-private engine probes on the connected Xiaomi.
The normal game APK was never replaced and no game-data command or patch coordinator was run.

| Artifact / compatibility check | Result |
|---|---|
| Main build | Offline `:app:assembleDebug -PpatchVersionCode=30` passes; version 1.6.1.3/code 30 matches the installed development patcher for an in-place update. |
| APK | `artifacts/staging-performance/hok-ace-patch-all-optimizations-debug.apk`; SHA-256 `28f8be573e882d96953cbfddb54611114d023de8c7eab3ca7f81530b8855e68e`. Installed hash matches. |
| Packaged engine | All 855 manifest payloads match both manifest hashes and repository bytes. `qts_relocate.py`, `mobile_graphics.py` and `build_device_patch.py` extracted on the phone match source hashes; content-addressed engine id `ff5d8aa28fad5fc986033a2845e50bc8825e3ebd37239a448be41249437240db`. Research files are excluded. |
| Signer / alignment | APK v2 signature verifies. Certificate SHA-256 `aa67f1993e3a335ff798d085a3e818b12988739dd3d5e69f8bdd1be97f01c249` matches the copied installed patcher. All 84 native libraries pass static 16 KiB ELF alignment; `zipalign -c -P 16 4` passes. This is not acceptance on a physical 16 KiB-page device. |
| Test artifact | Offline `:app:assembleDebugAndroidTest -PpatchVersionCode=30` passes. `artifacts/staging-performance/package-io-androidTest.apk`, SHA-256 `b41afa784bedce2cc117779e4bc2152ae26a0de2f3a8157ac07561f1235a0322`; same signer. |

Added `PackageIoProbeTest` under `androidTest`, using only a temporary directory in the target app's
cache. The runner invokes this plus the existing `EngineProbeTest` and `NativeDependencyProbeTest`:

| Android check | Result |
|---|---|
| Embedded runtime / core codecs | Pass: Python 3.12, full codec gate, catalog count, LZ4 and Zstandard round trips. |
| Other native dependencies | Pass: frame codec, native Zstandard backend and FreeType rendering. |
| Writable shard I/O | Pass: a one-byte edit submits 65,536 bytes; unchanged repeat submits zero. A 600-record root split saves byte-identically to the former full writer; both live-offset readers agree and buffer resizing works after save. |
| Small ASTC reuse | Pass: repeated small input produces a cache hit and identical bytes to a fresh native encode on this phone. |
| Runner | `OK (4 tests)`, 5.399 s reported test time. This is fixture runtime, not full patch/staging time. |

MIUI initially rejected the separate test APK with `INSTALL_FAILED_USER_RESTRICTED` after the main
patcher update succeeded. The user explicitly chose retry and approved installation on the phone;
the retry succeeded. Both retained session journals are byte-identical to the initial pre-update
state: the completed session remains `COMPLETE`, the cancelled session remains `CANCELLED`, both
have `normal_verified: true`, `packages_dirty: false` and no mutation intent. The normal APK hash
remains `29b3ee7e5a0d21de7d1282d704416402d341b651da95af2eeb5b274c818defdc`.

Evidence: `1aa2573:.scratch/staging-performance/android-optimized-artifact.json`, `android-optimized-native.json`,
`android-installed-engine.json`, `android-optimization-verification.json`, and raw before/after
receipts plus `instrumentation.log` under `artifacts/staging-performance/android-optimization-checks-retry/`.
The initial pre-update receipt and copied prior patcher APK are retained beside them. Build and
isolated-check commands are documented in `android/README.md`; no test-only code is bundled into
the normal app APK. Reference, staging-contract and diff whitespace checks pass.

**Verdict:** optimized development patcher is installed and the targeted Android runtime checks
pass. This is not a full patch run, pristine restore, device cycle, game-screen verdict or Android
end-to-end performance measurement. Existing translated game data was left alone.

## 2026-10-17 — Optimized phone benchmark preparation

The user explicitly requested a phone benchmark, authorizing a verified backup of the working
translation, restoration of the matching pristine layer and a real patch run. The fresh recovery
archive is kept outside the repository. To reserve PC space, removed only the regenerable
`D:/scratch/hok-staging-performance/tree-pages1` and `tree-pages2` output directories after checking
their saved hash receipts, resolved allowlisted paths and absence of reparse points. Timing JSON
and verification receipts remain in `1aa2573:.scratch/staging-performance/`; pristine and recovery data remain.

The first restore preflight stopped before package writes because it searched private `files/` for
the update receipt. It restored and hash-verified the normal APK. The actual receipt is
`/sdcard/Android/data/com.tencent.tmgp.osgame/files/Cache/Update/NewVersionInfo.json`; its
`needDownloadSize` is zero. `phone_benchmark_restore.py` now checks that exact external receipt.
Both APK signers, installed optimized patcher identity, clean retained session journals and the
pristine archive were verified before the retry. Live package 1 is version `1.6.0.1`, revision `0`,
matching the pristine snapshot. No benchmark timing is established by these preparation steps.

## 2026-10-17 — Optimized phone benchmark completes with identical staged bytes

Restored all 553 pristine archive files and verified the normal APK before starting the real
production patch flow on Xiaomi M2007J3SG (`f15a72e`, Android 12). Shizuku was stopped; started it
with the command displayed by its own app, then the user explicitly granted HOK ACE access.
Preparation reused verified cached APKs. The new session is
`bbf81617-5ac4-4ad8-aaa2-3a295e27db8c`, engine
`ff5d8aa28fad5fc986033a2845e50bc8825e3ebd37239a448be41249437240db`.

The fresh pre-restore recovery archive contains 745 hash-verified files and remains at
`D:/scratch/hok-staging-performance/phone-benchmark-20261017-run2/before-benchmark.tar`, SHA-256
`f4551082144e41acc3bedbabfcfa53eb4168dfab1868e3d73f97ada0bd10e584`. Its receipt is
`1aa2573:.scratch/staging-performance/phone-benchmark-restore.json`. The earlier recovery archive is retained too.

| Measurement | Earlier phone run | Optimized phone run |
|---|---:|---:|
| Internal build timer (`metrics.json`) | 202.430 s | 174.746 s (13.7% less time) |
| `build_snapshot` bridge, including input verification | 261.326 s | 233.408 s |
| Patch resource timer | 768.868 s | 554.604 s (9 min 15 s) |
| Maximum sampled RSS | 1,655,092 KiB (1,616.3 MiB) | 771,200 KiB (753.1 MiB; 53.4% lower) |
| Process-lifetime high-water RSS | 1,801,792 KiB | 953,016 KiB |
| Observed free-space decrease | 5,887,877,120 bytes | 5,762,338,816 bytes |
| Maximum battery temperature / thermal status | 42.2 C / 0 | 42.0 C / 0 |
| Resource samples / unavailable readings | 768 / 0 | 554 / 0 |

These are single sequential runs, not controlled paired phone trials. The earlier total includes
interrupted final-install recovery; do not attribute the total-time difference entirely to the engine
optimizations. The resource timer starts after engine/APK preflight and session creation; it excludes
the PC backup/pristine restore and initial APK preparation. This run's worker start to destruction is
about 590 s (9 min 50 s). The internal build timer excludes snapshot/APK verification that precedes
`build_scratch`. RSS is sampled once per second and can miss peaks; process high-water is lifetime-wide.
Free-space observations can include other apps. USB charging was active; before patching, battery
temperature was 38.7 C and charge 45%.

| Correctness / recovery check | Result |
|---|---|
| Staged bytes | All 14 staged `.db` SHA-256 hashes exactly match the earlier phone run. |
| Staging report | Entire summary matches after replacing only session UUIDs in paths. Override census remains 94 tables / 183,250 translated records. |
| App counters | 388 text tables, 398 applied textures; one skipped table, zero skipped textures. The known APK-append encoder refusal remains; coverage is unchanged. |
| Final journal | `COMPLETE`, `normal_verified: true`, `packages_dirty: false`; no mutation/recovery-normal intent. |
| Installed game | SHA-256 `29b3ee7e5a0d21de7d1282d704416402d341b651da95af2eeb5b274c818defdc`; `DEBUGGABLE` absent. |
| Installed optimized patcher | SHA-256 `28f8be573e882d96953cbfddb54611114d023de8c7eab3ca7f81530b8855e68e`. |
| Startup observation | Normal game launches and process is still present afterward. Recent sampled AndroidRuntime/Unity error output is empty. User subsequently confirmed the translation looks right. |

Raw small receipts, original/optimized sessions, logs and internal timers are retained under
`artifacts/staging-performance/phone-benchmark-optimized/`. Reproduce read-only collection with
`1aa2573:.scratch/staging-performance/capture_phone_benchmark.py`; the result checks are in
`verify_phone_benchmark.py` and `1aa2573:.scratch/staging-performance/phone-benchmark-verification.json`.
The receipt collector was corrected to treat legacy ADB `exec-out` missing-file messages as absent
optional metrics, because that protocol can merge stderr and return zero. This affected local
collection only; it did not interrupt the patch worker.

**Verdict:** real optimized phone patch completed with identical output bytes and verified normal
APK restoration. This run measured a shorter internal build and substantially lower sampled peak
memory. After being asked to check login, lobby and cards, the user replied
"Works — translation looks right" on 2026-10-17. This is user-reported screen acceptance for this
optimized run; individual screens were not separately enumerated. The benchmark and device check
are complete.

## 2026-10-17 — Reuse texture chunk offsets only for an immediately created package copy

After the user accepted the optimized phone run and requested further offline work, inspected the
saved profile. Texture staging scanned each source package and then its newly copied output before
relocation. That second scan discovers the same offsets in byte-identical files. `port_graphics` now
retargets the pending source slots' paths to the copy if this call created it. If output already
exists, the original fresh scan remains mandatory: earlier passes may have relocated chunks.
There is no persistent slot-map cache, and package writers, codecs, texture gates and summary fields
are unchanged. The `build_patch` contract and texture feature record were updated together.

| Verification / measurement | Result |
|---|---|
| Targeted checks before the change | Four pass; the fresh-copy check fails on the unwanted second scan. |
| Targeted checks after the change | All five pass: every chunk gets the output path and source offset for a new copy; an existing output uses its distinct current offsets; unchanged, refused and wrong-length textures do not copy/write. |
| Full staging | Fresh external `D:/scratch/hok-staging-performance/graphics-copy-slots1`, English, the same pristine dump and cached normal APK. |
| Output correctness | All 14 `.db` hashes match the original verified baseline. Full normalized summary, counts, package reports and skip lists match the retained control. Coverage is unchanged. |
| Texture-stage slot scans | **8 → 4**; total measured slot-map calls **31 → 27**. |
| Texture-stage slot-scan time | 11.256 s in preceding changed-write run; 4.589 s now. Ordinary sequential Windows runs, not controlled paired timing. |
| Texture stage, exclusive of other measured stages | 38.915 s before; 37.016 s now. Nested slot-scan savings cannot simply be added to other stage measurements. |
| Full elapsed / CPU | 102.033 / 47.703 s, versus 134.643 / 84.141 s before. APK ASTC time also changed from 49.177 to 20.951 s; do not attribute the overall difference to slot reuse. |
| Regression checks | All 46 pass: previous 41 plus five fresh-copy checks. |

Receipts: `1aa2573:.scratch/staging-performance/graphics-copy-slots1.json` and
`graphics-copy-slots-verification.json`. Reproduce the focused checks with
`.venv/Scripts/python.exe 1aa2573:.scratch/staging-performance/check_graphics_copy_slots.py`; reproduce
full staging with the existing `measure.py` arguments and a new external run directory.

For disk space, removed only the agent-generated `D:/scratch/hok-staging-performance/run2` after
re-hashing all 14 outputs against its retained receipt and checking the resolved exact path and
absence of reparse points. Its timing/hash receipts remain in `1aa2573:.scratch/staging-performance/`, and
its log was saved to `artifacts/staging-performance/run2-staging-before-cleanup.log`. Original
`run1`, normalized control `optimized1`, latest changed-write output, pristine data and every phone
recovery backup remain. No phone commands, Android builds or installations were performed here.

**Verdict:** keep this narrow fresh-copy optimization. It removes four proven duplicate scans
without changing staged bytes. Existing output still gets a fresh scan. Android timing and screen
acceptance for this additional change are unmeasured; the accepted phone installation retains the
previous optimized engine.

## 2026-10-17 — Reuse the read-only prime slot map during append

Continued offline at the user's request. `add_prime_only` already builds a prime package's slot map
to read and translate its wanted assets, then `qts_insert.add_assets` scanned the same unchanged
source again. It now passes that local map through the optional keyword-only `source_slots`.
Direct callers that omit the keyword still scan their source normally. Output is still reopened
through `QtsPackage`, scanned afresh and decoded for the mandatory appended-asset read-back. No
cross-call cache, package layout, encoding setting, allowlist or append gating changed. Updated
the staging contract and prime-only append feature record in the same edit.

| Verification / measurement | Result |
|---|---|
| Targeted checks | Four pass: supplied source map avoids rescan and still uses fresh output slots for read-back; direct-call fallback scans; read-back mismatch raises; encoder refusal still skips the asset. Before implementation, the direct-call case passed and the three supplied-map cases failed on the unsupported keyword. |
| Full offline staging | New external `D:/scratch/hok-staging-performance/append-source-slots1`, same English catalog, pristine dump and cached normal APK. |
| Output | All 14 `.db` hashes match the original baseline. Full normalized summary, all counts and skip lists equal the verified control. |
| Append slot scans | **12 → 8**; total measured slot-map calls **27 → 23**. Four mandatory fresh output scans remain. |
| Append slot-scan time | 4.554 s before; 3.836 s now. Sequential Windows observations, not a controlled timing comparison. |
| Full elapsed / CPU | 169.410 / 120.969 s, versus 102.033 / 47.703 s before. |
| APK ASTC encode time | 76.586 s now, versus 20.951 s before; encoding inputs/settings and final output hashes are unchanged. Encoding variation dominates the total difference. No overall speedup established. |
| Regression checks | All 50 pass: previous 46 plus four source-map checks. |

Evidence: `1aa2573:.scratch/staging-performance/append-source-slots1.json` and
`append-source-slots-verification.json`. Focused command:
`.venv/Scripts/python.exe 1aa2573:.scratch/staging-performance/check_append_source_slots.py`.
Full run uses the existing `measure.py` command with a fresh external run directory.

Freed space only by removing the regenerable `D:/scratch/hok-staging-performance/optimized2`
directory after re-hashing its 14 outputs against the retained verification receipt, checking the
resolved exact path and refusing reparse points. Its timing/hash receipts remain, and its log was
copied to `artifacts/staging-performance/optimized2-staging-before-cleanup.log`. Original baseline
`run1`, normalized control `optimized1`, current experiment outputs, pristine inputs and all phone
recovery archives remain. No phone commands, APK build or install were run.

**Verdict:** keep removal of four duplicate source scans, with unchanged output and read-back
verification. No end-to-end speedup claim. Android timing and screen acceptance of this additional
offline change remain unmeasured. The large observed ASTC timing variation remains a useful next
offline investigation target.

## 2026-10-17 — CPU core placement reproduces the ASTC timing swing

The user requested investigation of image-encoding time variation. Used the diagnosing-bugs
workflow against the retained real RGBA/ASTC audit recordings, without rebuilding packages or
touching the phone. The replay invokes the unchanged native `_encode_astc`, preserving the audit's
first 8x8 encode before the chosen inputs. All 72 final audit calls are the APK image sequence:
70 unique inputs, none at or below the small-result cache's 4096-byte limit. Every replayed image
is compared byte-for-byte with its recorded native output.

The initial isolated large image (sample 1475) took 0.819–0.961 s over nine calls in three fresh
processes. Three unrestricted full 72-image batches took 21.028, 22.066 and 21.925 s, so this quiet
replay did not initially reproduce the saved staging profile's 20.951–76.586 s swing. Ranked
suspects before controlled testing: CPU placement, power/contention, then initialization order.
Changing only benchmark-process affinity reproduced the large difference, including in reversed
order; this was then confirmed with the full image sequence.

| Controlled replay | Result |
|---|---|
| Host | Intel Core i5-1235U; Windows `GetSystemCpuSetInformation` reports logical CPUs 0–3 in efficiency class 1, CPUs 4–11 in class 0. CPU 0 is the higher-performance class; CPU 11 is the efficiency class. |
| One image, three encodes per fresh process; CPU order 0, 11, 11, 0 | Batch wall times 2.404, 8.535, 8.524, 2.581 s. Same output bytes in every case. |
| Full 72-image replay, CPU 0 | **20.490 s wall / 19.203 s CPU**. |
| Full 72-image replay, CPU 11 | **76.255 s wall / 73.172 s CPU**; **3.72×** the CPU-0 wall time. |
| Encoder identity / settings | Both use astc-encoder-py 0.1.12, the identical `_encoder_avx2.pyd` SHA-256 `d4cd289885af9f0b05d2043d5ab7dbbaa590cccf4615f8f32cebe8531549d769`, one encoder thread, existing quality 85 and identical recorded configuration fields. |
| Output | All 72 hashes equal between the two CPU placements and match the retained audit; no quality or content change. |
| Repeat with fixed CPU 0, three identical encodes per process | 2.316 and 2.333 s totals; individual-call max/min ratio 1.025. Timing-variation detector passes at the 1.5 threshold. |

`probe_astc_variation.py` deliberately exits nonzero when the comparable timing ratio exceeds 1.5,
after saving all evidence. The mixed-core probes therefore fail that diagnostic assertion as
intended; the fixed-core control passes. This is the reproducible performance signal, not a patcher
test failure. Affinity is set only on disposable replay children and expires when they exit. No
system power setting or production process affinity was changed. The Windows topology is captured
read-only by `capture_cpu_topology.py`; the installed encoder's `encoder.py` and `encoder.pyi`
provide local evidence for AVX2 dispatch and the default one-thread context.

Evidence in `1aa2573:.scratch/staging-performance/`: `astc-variation-baseline.json`,
`astc-variation-prime.json`, `astc-variation-affinity.json`, `astc-variation-prime-affinity.json`,
`astc-variation-fixed-core.json`, `astc-cpu-topology.json`, and `astc-variation-verification.json`.
Reproduce the intentionally red full comparison with:
`.venv/Scripts/python.exe 1aa2573:.scratch/staging-performance/probe_astc_variation.py D:/scratch/hok-staging-performance/astc-audit1 --prime-sequence --cpus 0,11 --output <receipt.json>`.
For a short stable control, use `--cpus 0,0 --repeats 3` without `--prime-sequence`.
The CPU ids are measured for this PC only; other machines require their own topology/allowed mask.

**Verdict:** CPU placement alone reproduces the magnitude of the Windows encoder-time swing
with identical inputs, binary, settings and output. This supports CPU scheduling as an explanation
of the earlier timing variation; those historical runs did not record their cores, so their exact
placement cannot be proven retrospectively. Compare future PC performance on the same CPU class
and record process affinity. No codec-quality change or shipping fix is justified by this evidence.
This is not an Android timing result, and no phone, APK or translation payload was changed.

## 2026-10-17 — Final combined optimization build for PR preparation

At the user's request to open one PR for the work, built the final combined source (including the
two later slot-map reuse changes) offline with
`android/gradlew.bat -p android --offline :app:assembleDebug :app:assembleDebugAndroidTest -PpatchVersionCode=30`.
Both tasks pass. The resulting development APK SHA-256 is
`6dcf4c62b1f9234f745897ae6a01a30d9b90811b50e5372b99c2e258089edd47`; engine manifest id is
`d689b1bd5f47891650a64195652433e19bdeba6564c2c2fff95b806582b0fadd`.
All 855 packaged payloads match their manifest and repository bytes, and research is excluded.
Receipt: `1aa2573:.scratch/staging-performance/android-pr-artifact.json`. Reference, staging-contract and
diff checks pass. This final build was not installed; the accepted phone benchmark remains evidence
for the earlier engine, and the two later scan-reuse changes retain offline byte-equivalence evidence.

## 2026-10-17 — Multi-threaded ASTC encoding

Continuing the PR #11 optimization work. After the earlier changes, the 72 large APK-only images
dominate staging (single-threaded native encoding). `astc_encoder.ASTCContext` takes a `threads`
argument; `mobile_graphics` now passes `ASTC_THREADS = os.cpu_count()`. Settings (LDR, footprint,
quality 85, swizzle) are unchanged.

`probe_astc_threads.py` replays all 3,654 audited calls in order in a fresh process per thread count
(the context keeps state between calls) and compares each output with the recorded native bytes.

| Threads (i5-1235U, 12 logical CPUs) | Encode wall, two orders | Mismatches |
|---|---|---:|
| 1 | 27.64 / 26.95 s | 0 |
| 2 | 16.64 / 15.91 s | 0 |
| 4 | 15.17 / 15.30 s | 0 |
| 8 | 13.09 / 12.74 s | 0 |
| 12 | 11.42 s | 0 |

Full offline staging (`D:/scratch/hok-staging-performance/astc-threads1`, same English catalog,
pristine dump and cached APK): all 14 staged `.db` hashes and the complete normalized summary match
the verified control. Total wall 118.5 s (previous receipt `append-source-slots1`: 169.4 s); APK-only
encoding 9.0 s versus 76.6 s. That earlier 76.6 s matches the efficiency-core placement found above,
so the fair comparison is roughly 20 s on performance cores to 9 s. Process CPU rose 121 → 136 s from
thread overhead. `check_graphics.py` passes. A new Android probe,
`PackageIoProbeTest.testThreadedAstcMatchesSingleThread`, requires identical bytes between a
1-thread and an `ASTC_THREADS` context over three random images; it passes on Windows and compiles
in `:app:assembleDebugAndroidTest`, but has **not** run on a phone (none attached).

Evidence in `1aa2573:.scratch/staging-performance/`: `astc-threads1.json`, `astc-threads2.json`,
`astc-threads3.json`, `astc-threads-run1.json`, `astc-threads-verification.json`. Reproduce:
`.venv/Scripts/python.exe 1aa2573:.scratch/staging-performance/probe_astc_threads.py D:/scratch/hok-staging-performance/astc-audit1 --threads 1,2,4,8 --output <receipt.json>`.

**Verdict:** threaded encoding is byte-identical on Windows and cuts encode time about 2.3× at 12
threads. ARM64 determinism and phone timing are not yet measured; run the probe test and a phone
patch before claiming an Android speedup.

## 2026-10-17 — Threaded ASTC phone benchmark

The user requested a phone test of the threaded ASTC build: restore this PC's pristine layer and
repatch. Xiaomi M2007J3SG (`f15a72e`, Android 12). To make room for the recovery archive, removed the
regenerable offline outputs `changed-writes1`, `graphics-copy-slots1` and `append-source-slots1` at
the user's instruction; their receipts remain in `1aa2573:.scratch/staging-performance/`.

| Step | Result |
|---|---|
| Patcher | `artifacts/staging-performance/hok-ace-patch-threaded-astc-debug.apk`, SHA-256 `b737a2d6d58534f189232229eaaa0efc04928425a67fe066890e783c4400396e`, installed in place; engine `550cf67a7ddb16b50c9e61bf801af200789ccd03f221adc90584654f5671372a`. |
| Android probes | `OK (5 tests)`. `testThreadedAstcMatchesSingleThread` used `ASTC_THREADS = 8`; 1-thread and 8-thread bytes match, and their SHA-256 `0d944ed8…` equals the Windows result for the same fixture. |
| Recovery backup | Current translated layer, 745 files, hash-verified: `D:/scratch/hok-staging-performance/phone-benchmark-threaded/before-benchmark.tar`, SHA-256 `e40a03e79d92c133b607fbf4d4a539c8203965e11f9b5f16acb569e0b9601713`. |
| Pristine restore | All 553 files of snapshot `20261016-101124` verified on the phone; data version `1.6.0.1` revision `0`; update receipt `needDownloadSize` 0; normal APK reinstalled. |
| Patch | Production flow, English, session `3b54213f-01aa-4a83-baf9-f29ccdb78e26`. The final normal-APK install was interrupted; the patcher re-entered access, reinstalled and verified the normal APK, and reported recovery. |

| Measurement | Previous optimized run (`bbf81617`) | Threaded ASTC run |
|---|---:|---:|
| Internal build timer (`metrics.json`) | 174.746 s | **63.252 s** (63.8% less) |
| Visible build interval | 12:56:39 → 13:00:55 (4 min 16 s) | 15:41:05 → 15:42:54 (1 min 49 s) |
| Patch resource timer | 554.604 s | 474.790 s, including about 2.6 min of final-install recovery |
| Maximum sampled RSS | 771,200 KiB | 738,352 KiB |
| Process-lifetime high-water RSS | 953,016 KiB | 1,026,392 KiB |
| Maximum battery temperature / thermal status | 42.0 C / 0 | 37.0 C / 0 |

| Correctness | Result |
|---|---|
| Staged bytes | All 14 staged `.db` SHA-256 hashes equal the previous phone run. |
| Staging summary | Equal after replacing only session ids. |
| App counters | 388 text tables, 398 applied textures; 1 skipped table, 0 skipped textures (unchanged). |
| Final state | Journal `COMPLETE`, `normal_verified: true`, `packages_dirty: false`, no intents. Normal APK `29b3ee7e…`, `DEBUGGABLE` absent. |

Single sequential runs, not paired trials; the resource-timer total includes the interrupted-install
recovery, so compare the internal build timer. Receipts: `artifacts/staging-performance/phone-benchmark-threaded/`,
`artifacts/staging-performance/android-threaded-astc-checks/`, and
`1aa2573:.scratch/staging-performance/phone-threaded-verification.json`.

**Verdict:** on the phone, threaded ASTC is byte-identical end to end and cuts the internal build
from 174.7 s to 63.3 s. **User verdict, 2026-10-17:** after opening the game, the user replied
"Works — translation looks right." Individual screens were not separately enumerated.


## 2026-10-17 — Android 15 access APK not debuggable (moto g45 5G)

A user's exported log (moto g45 5G, Android 15 API 35, app 1.6.1.3, game 1.1.1 `774472` sideloaded
2026-09-15 through the package installer) failed APK preparation the way the Infinix X6851 did:
`access not debuggable per Android (its manifest declares debuggable: false; normal manifest: false)`.

| Finding | Evidence |
|---|---|
| The manifest half of that message was always `false` | Kotlin passed the manifest as a Java `byte[]`; Chaquopy hands Python a `jarray`, and `patch(x) == x` against it is never true. It said nothing about the bytes. `is_debuggable` now copies its argument to `bytes` first. |
| The manifest edit is sound on our builds | On the cached `installed.apk` manifest and on rebuilt official, renamed and debug-cleared variants, `patch(…, True)` reads as debuggable both to `is_debuggable` and to a replica of Android's `RetrieveAttributes` walk; a 2 GB `rewrite_apk` reads the patched manifest back unchanged. |
| A flag out of resource-id order is invisible to Android | Android walks `<application>`'s attributes once in ascending resource-id order. A manifest whose `android:debuggable` sits after higher ids (as a tool that appends without sorting leaves it) kept it there: the old `patch` flipped the value in place, and the replica walk still read **not debuggable** — the phone's symptom. `AttributeResolution.cpp` is identical in Android 14, 15 and 16, so the trigger is the phone's game APK, not Android 15. |

Fix: `patch` now treats every `<application>` attribute carrying the debuggable resource id as the flag
and always re-sorts the attributes; already-sorted manifests stay byte-identical (all four variants
above). `prepare_game_apks` reads each written APK's manifest back and refuses an access manifest that
is not debuggable. **Not device-verified**: the phone's own manifest was not in the log, so the
out-of-order flag is the explanation that fits, not a measurement. If the next log still fails, its
manifest line is now meaningful.

## 2026-10-17 — Reverse delta from a staged layer back to the pristine one

Asked whether a language switch could skip clearing the game's data by keeping only what the patch
changed. Offline, `HEAD` `6974ba4`: `build_device_patch.py` over the pristine 1.6.0.1 snapshot
`dist/HOK ACE Patcher Data/pristine/20261016-101124/game` with the cached `installed.apk`
(`29b3ee7e…`), `--catalog resources\catalog`; exit 0 in 75 s, 10 packages, `text_skipped` and
`graphics_skipped` empty, `append_skipped` one table (unchanged). The 14 staged `.db` files were each
compared with their pristine original in 4 KiB blocks, then 64-byte sub-blocks, coalescing changed
runs closer than 256 bytes. The reverse delta is the pristine bytes of every overwritten range, the
pristine bytes past the staged length, and the pristine length; sizes are zlib level 6.

| Staged file | Pristine | Staged | Ranges | Overwritten | Appended | Delta (zlib) |
|---|---:|---:|---:|---:|---:|---:|
| `1/1_0.db` | 29.1 MB | 35.4 MB | 89 | 6.02 MB | 6.29 MB | 5.09 MB |
| `15/15_0.db` | 297.6 MB | 366.5 MB | 12 | 0.03 MB | 68.83 MB | 0.01 MB |
| `19/19_0.db` | 333.2 MB | 336.6 MB | 31 | 0.01 MB | 3.38 MB | <0.01 MB |
| `20/20_0.db` | 204.8 MB | 204.8 MB | 3 | <0.01 MB | 0.05 MB | <0.01 MB |
| `1050016095/1050016095_0.db` | 0.2 MB | 4.9 MB | 5 | 0.02 MB | 4.75 MB | <0.01 MB |
| the other 9: `1/1.db`, `10/10.db`, `10/10_0.db`, `15/15.db`, `19/19.db`, `20/20.db`, `21/21.db`, `21/21_0.db`, `1050016095/1050016095.db` | 60.8 MB | 60.9 MB | 0–56 each | 0.07 MB | 0.07 MB | 0.01 MB |
| **All 14** | **925.7 MB** (zlib 898.3 MB) | | | **6.14 MB** | **83.36 MB** | **5.12 MB** (raw 6.14 MB) |

Round trip: each pristine file rebuilt from its staged file plus the delta alone (truncate to the
pristine length, re-append the pristine tail, write back each range) matches the pristine SHA-256,
14 of 14. No staged file is shorter than its pristine original, and 83 of the 89 MB the patch adds
is appended past the pristine end; the in-place 6.1 MB is almost all `1_0.db`.

The same build with `--catalog resources\catalog_id` (exit 0, 10 packages, the same skip lists)
stages the same 14 files: 76 ranges in `1/1_0.db` instead of 89, **4.67 MB** overwritten, 84.48 MB
appended, delta **3.87 MB** zlib (raw 4.67 MB), round trip 14 of 14. The two languages overwrite
different ranges of `1/1_0.db`, so a delta made for one does not describe the other's install. (A first
Indonesian attempt failed with `WinError 112`: the C: scratchpad ran out of disk; re-run on D:.)

Scripts and output: the session scratchpad's `delta/measure_delta.py` and `delta/roundtrip.py`, not
kept in the repo.

**Verdict:** keeping the pristine layer under a patch costs about 4–5 MB per install, against 898 MB for
copies of the touched files. Offline only: nothing went on a phone, and whether the game accepts a
re-patch over a restored layer without clearing its data is unmeasured.

## 2026-10-17 — What the game's updater records, and what it checks

Offline, for the repatch-after-update design (`.scratch/language-switch/spec.md`). Sources: the
`Watchdog/` of the pristine 1.6.0.1 backup `dist/HOK ACE Patcher Data/pristine/20261016-101124/device-backup.tar`
(taken right after a full re-download), strings in `resources/qtsvfs/QtsVFS.dll`, and
`grid-regression/old-patched-game/1` (10-02, patched) against that pristine package `1`.

| Question | Finding | Grade |
|---|---|---|
| Format of `Watchdog/*.db` | Not SQLite: the QtsVFS shard slot layout (`u32` self offset, `-1`, size, `u64` key, payload) behind a `qtsvfs-watchdog` header record at 0x3630. The repo's package readers do not open them; a slot scan does. | measured |
| `BrokenList.db` | Header only, empty. | measured |
| `PatchList.db` | 214 package names, nothing else; the backup holds 214 package `.db` files. | measured |
| `StorageStatus.db` | 120 package names, each with a timestamp (2026-10-16 10:05:58 +07). | measured |
| `History.db` | 214 merge events, 10:05:35–10:06:03, each `pkg|primeHash|baseHash|curHash|curHash|1|1`; 88 packages moved through 1–7 merges from their prime hash. The other 126 have no merge record (probably downloaded whole). 89 empty `builtin/Merge/<pkg>/` folders and one `CleanCopy/1060000000/`. | measured (field meanings inferred) |
| Per-file checksum, size or version anywhere in `Watchdog` | None. It cannot say which files an update changed or expects. | measured |
| How a diff applies | In place, asset by asset (`VFS_MergeDiffToPackage`, `PatchDiffPage`, `AddNodesAndBlocksAndMove`, `DelNodes`). Each asset is checked against the CRC the package stores for it: `PreCheck hdiff src crc mismatch`, then `dest crc mismatch`, then `Result package-hash mismatch`; the diff's source package hash must equal the package's current hash (`diffHeader_.GetSrcPackageHash() == overridePackage_->GetCurPackageHash()`). | inferred from DLL strings |
| Does our write change a package's hash | No. Package `21` reads `8591676242410099349` in `0/0.db`'s INGQ table (277 packages), the value the 10-01 append cycle logged after our append. | measured |
| Does our write change an asset's stored token | No: the stager never writes the 16-byte token at +52..+67. In the 10-02/10-16 pair, 188 of 404 shared assets changed that token (the updater's doing) and 34 kept it with different bytes (our translations). The token is not CRC32, any CRC64 variant or XXH64 of the raw or compressed bytes. | measured (algorithm unknown) |
| What the updater does when a diff fails | Not logged anywhere in this repo. The repair path in the DLL is `BrokenList` → `fixfilelist.json` → `QtsfFixer::FixFile`, against each asset's stored CRC. | inferred |

`errorCode:361` and the "binary diff" wording in ADR 0002 come from the upstream PC patcher's README
(`9f151a8`) and entered this repo's docs in `732af5d`; no `QtsVFS.log`, `normal1.log` or repair log of a
failed diff was ever saved here, and the force close after an update is a user report. No clean pair of
pre- and post-update bytes of one package exists locally (the 10-16 copy is a fresh download).

**Verdict:** our writes keep each package's hash and each asset's stored check values pristine while the
bytes are ours, so a diff aimed at a patched asset would fail on its bytes; putting pristine bytes back
before the update is what the design needs. Unverified until a device cycle captures an update over a
patched layer.

## 2026-10-17 — The pristine delta shipped

Offline, uncommitted on `fd1a279`, for `.scratch/language-switch` tickets 02–05. Pristine 1.6.0.1 snapshot
`dist/HOK ACE Patcher Data/pristine/20261016-101124` with the cached `installed.apk`; no phone touched.

| Check | Result |
|---|---|
| `tools/research/check_pristine_delta.py` (synthetic) | 13 cases OK |
| Same, `--game` round trip | English: 11 files rebuilt + 3 staged unchanged of 14, delta **5.12 MB** encoded (6.14 MB raw); Indonesian: 11 + 3 of 14, **3.87 MB** (4.67 MB raw). Equal to the reverse-delta entry above. |
| Switches via `rebuild`, then a build | English → Indonesian, Indonesian → English, English → English: each stages byte-identical files to a build from pristine |
| Refusals | one byte changed and truncated → `changed`, deleted → `missing`; none touched |
| Text signal (`text_not_pristine`) | from pristine: 94 of 94 catalog tables planned, both languages (reads pristine). Over an English layer: English and Indonesian builds plan none of the tables they read (scan census 389 tables, 2 planned before the uncatalogued drop) → refused |
| `tools/research/check_windows_repatch.py` | 9 cases OK (first install, switch and back, changed file, translated layer without delta, other patcher's layer, bootstrap from a pristine session and not from a translated one, push cut off part way, stale delta after a clear onto newer data) |
| Android bridge on desktop (scratchpad `android_e2e.py`) | English first install from a snapshot of the pristine backup equals the desktop build; `keep_delta` 14 files; Indonesian over a snapshot of that English layer reserves `pristine_copy_bytes` 925 663 232, rebuilds 11 (3 already pristine) and stages byte-identical to Indonesian from pristine; an English layer with no delta is refused by the text signal |
| Android `:app:assembleDebug :app:assembleDebugAndroidTest :app:testDebugUnitTest` | BUILD SUCCESSFUL; `PristineDeltaProbeTest`'s Python body passes on desktop, and on the Xiaomi M2007J3SG (Android 12): `am instrument -e class ...PristineDeltaProbeTest` OK (1 test, 3.0 s). Gradle's `connectedDebugAndroidTest` install failed with `INSTALL_FAILED_VERSION_DOWNGRADE` although no `dev.halixm.hokacepatcher` was installed; `adb install -r -d -t` of both APKs, approved on the phone, worked |

The first desktop end-to-end run failed with `TypeError: build_snapshot() takes from 4 to 5 positional
arguments`: an older `build_snapshot` had been left below the new one in `android_bridge.py`. Removed;
the rerun is the row above. Scripts and output: `dist/delta-check/`, not kept in the repo.

**Verdict:** offline, a language switch over a layer this patcher wrote rebuilds the pristine files
exactly and stages what a cleared phone would get. Whether the game accepts the re-patched layer
without a repair is still unmeasured (ticket 08).

## 2026-10-17 — Remove translation

Ticket 06 of `.scratch/language-switch`. `tools/research/check_windows_repatch.py`: 11 cases OK, including
Remove after an English install (both files back at pristine, empty delta kept, a second Remove writes
nothing, a following Indonesian patch builds from the pristine layer) and Remove with no record refused.
On the Xiaomi M2007J3SG (Android 12), `am instrument` of `RemovalRollbackProbeTest` and
`PristineDeltaProbeTest`: OK (2 tests, 6.8 s). The removal probe cuts the write-back off after its first
file (that file already pristine on the fake device), and rollback restores all three translated
fixture files; a complete write-back leaves every named file at its pristine SHA-256, and `keep_delta`
then keeps an empty delta. Fixture files only, with a fake device: no game file was written.

**Verdict:** Remove translation reuses each patcher's install path and rolls back like a patch. Whether
the game launches from the restored layer with no repair is unmeasured (the ticket's device cycle).

## 2026-10-17 — Remove translation deletes the delta

The spec owner changed one decision from the entry above: after Remove, each patcher deletes its delta
instead of keeping an empty one. `tools/research/check_windows_repatch.py`: 11 cases OK. After Remove,
neither `delta.bin` nor `delta.pending.bin` is left, a second Remove is refused ("nothing to remove"), and
the following patch run is a first install. That run is refused by a translated summary and builds
Indonesian from a pristine one. `tools/research/check_pristine_delta.py`: 13 OK. `RemovalRollbackProbeTest`
now expects `keep_delta` to delete `delta.bin`. On the Xiaomi M2007J3SG (Android 12), `am instrument` of
`RemovalRollbackProbeTest` and `PristineDeltaProbeTest`: OK (2 tests, 4.4 s).

**Verdict:** offline, Remove leaves the patcher in the same state as one that never translated the phone.

## 2026-10-17 — Language switch without a clear (Windows patcher)

Ticket 08 of `.scratch/language-switch`, Windows half. Xiaomi M2007J3SG (`f15a72e`, Android 12). The
patcher ran from source (`run.bat`, `master` at `ca2f190`, then `f1ec4de`), working folder
`D:\HOK ACE Patcher Data\cache\HOK ACE Patcher Data`.

| Step | Result |
|---|---|
| Starting layer | English from the Android patcher's benchmark run (no delta on either patcher). A scratch script pushed the pristine snapshot `20261016-101124` (1.6.0.1 r0) back through the access APK instead of a clear: all 549 package files equal `snapshot.json`; `Watchdog/` from the same tar; `needDownloadSize` 0; normal APK reinstalled. Previous layer saved: `D:\scratch\hok-ticket08\before-restore.tar` (2 936 564 736 B). |
| 1. English (session `20261017-214255`) | First install; text signal read the layer as pristine. 388 text tables and 398 textures applied, 1 table left Chinese. Delta 14 files, 6.14 MB of pristine ranges (5 124 701 B file). Launcher `Honor of Kings: ACE`; no repair; Scan to login; START GAME. `normal1.log` +19.6 KB, 0 hits for `QtsfFixer\|FixFile\|crc not match\|errorCode:361`. |
| 2. Indonesian, attempt 1 (`20261017-215340`) | Stopped in `pull_game_data`: renaming the extracted `packages/` to `builtin/` failed; the same rename succeeded minutes later (a transient Windows file lock). Nothing written. The pull grew to 2.76 GB from 2.29 GB after the game's first launch. Fixed in `f1ec4de` (extract straight into `builtin/`). |
| 2. Indonesian (`20261017-220303`) | Rebuilt from the delta. The 14 staged files are byte-identical to `dist/delta-check/from-pristine-id`. New delta 14 files, 4.67 MB (3 870 198 B). No repair, **still logged in**, MULAI GAME with Indonesian text. `normal1.log` +29 KB, 0 hits. |
| 3. English (`20261017-224744`) | Rebuilt from the delta. Catalog commits `20692b0`, `1e7845b`, `90ad4ae` landed between steps 2 and 3, so this English differs from step 1's in `1/1.db` and `1/1_0.db`. Its 14 staged files are byte-identical to English built from the pristine snapshot with the same catalog (`D:\scratch\hok-ticket08\from-pristine-en-now`). Delta 14 files, 6.14 MB. No repair, still logged in, START GAME. `normal1.log` +38 KB, 0 hits. |

Each build writes 14 files. 3 of them (`15/15.db`, `19/19.db`, `20/20.db`) stay at their pristine bytes
in both languages, and English and Indonesian differ in `1/1.db`, `1/1_0.db` and `19/19_0.db`.

**Verdict:** pass. The game accepts a re-patched override layer without a clear: no repair on launch,
and the login survives a switch. A switch stages exactly what a cleared phone would get, including a
newer catalog over the same language. The Android patcher's cycle is still owed.

## 2026-10-18 — Language switch without a clear (Android patcher)

Ticket 08's Android half and ticket 06's device cycle, Xiaomi M2007J3SG (`f15a72e`, Android 12),
continuing from the Windows cycle above. The debug Android patcher was built from `1c0cc28`, and its
catalogs equal the repo's at that commit. `9220c1b` landed afterwards and is not in it.

| Step | Result |
|---|---|
| Remove translation (Windows, session `20261017-230156`) | `delta.bin` and `delta.pending.bin` deleted, `staged-hashes.json` kept. The 14 rebuilt files it wrote back equal `snapshot.json`'s pristine SHA-256. No repair, still logged in, Chinese lobby. `normal1.log` +20.6 KB, 0 hits for `QtsfFixer\|FixFile\|crc not match\|errorCode:361`. |
| 1. English, Android (session `c16050a2…`) | First install (no delta on the Android patcher). Delta 14 files, 6.14 MB of ranges; its pristine side equals the snapshot for all 14, so Remove had left the layer pristine. No repair, still logged in, START GAME. `normal1.log` +21 KB, 0 hits. Ticket 06's last check: a new patch run after Remove succeeded without a clear. |
| 2. Indonesian, Android | Rebuilt from the delta. Delta 14 files, 4.67 MB. The 9 files outside the texture packages are byte-identical to Indonesian built on the desktop from the pristine snapshot with the `1c0cc28` catalog. No repair, still logged in, MULAI GAME. `normal1.log` +27.7 KB, 0 hits. |
| 3. English, Android | Rebuilt from the delta. All 14 staged files are byte-identical to step 1. No repair, still logged in, START GAME. The log rotated at midnight; `normal2.log` (00:00:49–00:19:16) has 0 hits. |

Side finding: the Android patcher's output differs from the Windows patcher's in five texture
packages, `15/15_0.db`, `19/19_0.db`, `20/20_0.db`, `21/21_0.db` and `1050016095/1050016095_0.db`.
Sizes are equal and the bytes differ. The phone engine is deterministic: its English equals the
benchmark run's phone layer (`D:\scratch\hok-ticket08\before-restore.tar`) in 12 of 14 files, and only
package `1` differs, which carries the catalog fixes. The difference predates the delta (the earlier
desktop end-to-end ran the bridge on x86, not on the phone). Each patcher keeps its own delta, so it
does not affect a switch. Which codec step differs is unmeasured.

**Verdict:** pass for both. The Android patcher switches EN → ID → EN without a clear, with no repair
and the login kept, and returns to the same bytes. Remove translation leaves a pristine, launchable
layer, and the next patch run is an ordinary first install.

## 2026-10-18 — Rotate the patcher signer with a v3 lineage

The previous patcher key (`aa67f199…c249`) was committed to public history, so it was rotated to a
new private key (RSA 4096, CN=HOK ACE Patch, SHA-256 `555f2ff4…8ae5`) kept outside the repository.
`apksigner rotate` wrote `android/signing/patcher.lineage`; the previous signer keeps the installed-data
capability and has shared-UID, permission, rollback and auth withheld. Release CI re-signs with
`tools/ci/sign_android.ps1`: v3 only, `--rotation-min-sdk-version 28`, alignment preserved.

| Check | Evidence and verdict |
|---|---|
| Lineage | `apksigner lineage --print-certs` lists signer 1 `aa67f199…` (installed data only) then signer 2 `555f2ff4…`. PASS. |
| Re-signed APK | A copy of `artifacts/dev.halixm.hokacepatcher.apk` (1.6.1.4, previous key) re-signed by the script verifies with `--min-sdk-version 30`: v3 true, v1/v2/v3.1 false, one signer `555f2ff4…`, lineage `aa67f199…` → `555f2ff4…`. PASS. |
| Alignment | `zipalign -c -P 16 4` passes on the re-signed copy. PASS. |
| Device update | Not yet run: installing the rotated APK over the phone's 1.6.1.4 (previous key) without uninstalling, then refusing a previous-key APK over it. |

## 2026-10-18 — Partial pull on the Windows patcher

Question: an install writes 14 files, so why does every run pull the whole override layer (about 2.9 GB)?
The build reads every package, and the pristine checks (`files_at`, the text signal) read the whole
layer. What a run needs is the phone's exact bytes, not a fresh transfer of them. `Patcher.pull_changed`
has the phone hash its layer (`run-as … find . -type f -exec sha256sum {} +`; toybox on this phone has
`sha256sum`, only `md5sum` is missing) and copies each file that the previous session's `staged/` or
layer copy holds at that SHA-256. It pulls the rest with `tar` in batches of at most
`PULL_BATCH_CHARS` characters of names and checks each pulled file against the phone's hash. The
session layer then equals the phone, so every later step reads the same bytes a full pull gives it.
A session with no earlier `pull.json`, hash output that does not parse (any line that is not a digest
and a plain layer path), or a failed or short transfer falls back to the full pull. Only the full
pull writes `device-backup.tar`, so `bootstrap_delta` never picks a partial session.

Offline, `tools/research/measure_partial_pull.py` against the working folder's session
`20261017-224744` (1.6.0.1 r0):

| Stand-in phone | Files | Reused | Pulled | Local cost |
|---|---|---|---|---|
| That session's layer with its `staged/` laid over it (a re-run after its install) | 741, 3031.7 MB | 741 | 0 | hash phone 4.5 s, match 3.5 s, copy 5.7 s |
| The pristine snapshot `pristine/20261016-101124` (a phone after Remove translation) | 549, 2286.6 MB | 549 | 0 | match 3.8 s |

`check_windows_repatch.py` (14 checks) runs the real `pull_game_data` against a fake phone. A first
pull is full; a re-run after an install pulls nothing; a data update pulls exactly the changed and
added files; a file the phone dropped is not carried over; garbled hashes, a `..` path and a truncated
tar each fall back to the full pull and leave no `pull-*.tar`; 400 changed files go in several batches.
The fallback check found a bug, fixed before commit: after a failed partial pull, the full pull's
`mkdir` of `game/WXQ_Data/Package` raised `FileExistsError`.

A file the previous session holds only in its pristine form, while the phone holds the translation, is
pulled again. That happens after a run stopped between `restore_pristine` and the push. It costs one
transfer and does not affect correctness.

On the phone (Xiaomi M2007J3SG, Android 12, 1.6.0.1 r0), source runs of `Patcher.run` (English), each
from the working tree, in order. The phone started translated by the Android patcher, which the Windows
patcher has no delta for, so the first two runs refused; the Android patcher's Remove translation then
gave it back pristine.

| Run | Pull | Pristine | Push |
|---|---|---|---|
| `20261018-021756` | Full: 741 files, 3032.5 MB tar, 209 s (no earlier `pull.json`) | Refused: 6 files at recorded staged hashes, no delta, no bootstrap source | Nothing (refused) |
| `20261018-022517` | Partial: 741 of 741 unchanged, pulling 0, 17 s (phone `sha256sum` plus local copy) | Refused, as above | Nothing (refused) |
| *Android Remove translation (1.6.1.4)* | | 11 files restored, its delta deleted | |
| `20261018-025809` | Partial: 730 unchanged, pulling 11, 919.2 MB, 57 s | No delta: first install | 3 already on the phone, 9 written; package 1050016095 (2 files) failed: the `adb` server dropped (cannot connect to daemon). The pending delta stayed |
| `20261018-030412` | Partial: 0 pulled (the 9 written files matched the last session's `staged/`) | Rebuilt 9 from the pending delta, 5 already untranslated | 12 already on the phone, package 1050016095 written; delta of 14 files kept |
| `20261018-030800` | Partial: 0 pulled, 23 s | Rebuilt 11, 3 already untranslated | 14 already on the phone, nothing written, `Watchdog/` left alone |
| `20261018-031204` (Remove translation) | Partial: 0 pulled | Rebuilt 11, 3 already untranslated | 11 written back; delta deleted |

Each build took 40 to 50 s and gave 388 text tables, 398 images and 1 table left in Chinese, the same
counts as the Android patcher's install. The adb drop was outside the patcher (no other adb was running
afterwards); it showed the pending delta working on a phone: the next run rebuilt the half-written
layer and finished the install.

Why the first runs refused: `bootstrap_delta` found no source. `20261017-224744`'s own backup holds 11
files at recorded staged hashes (it was pulled from a phone already translated), and 5 of its staged
`_0.db` files differ from the phone. `20261017-230156` has no `staged/`.

Afterwards the Android patcher translated the phone to English again, so it holds its own delta as before.

**Android patcher: not changed.** Its snapshot is a copy inside the phone, not a USB transfer, and
it is also the rollback source: `GameFileTransaction.verifyOriginals` checks the whole file set,
`Watchdog/` included, before it restores. Since the 2026-10-06 storage reclaim, a resolved session
keeps no game data, so there is no earlier copy to reuse. Reusing one would mean keeping about 3 GB
across runs, and that space is what the reclaim gave back to users. It would also need a rollback
built from the files a run writes rather than the whole set.

**Verdict:** shipped for the Windows patcher. A same-version re-run transfers only the phone's hash
list instead of about 2.9 GB. The first run after updating the patcher, and any run the check cannot
trust, still does the full pull.

## 2026-10-18 — Repatch after an in-game update, offline

Question: after an update the game finished over a patched layer, can a run repatch without a clear,
and when must it still refuse? Until now, any file the delta names at neither its staged nor its
pristine bytes refused the run while some file still held this patcher's bytes. Text has a witness, the
text signal, but textures have none, so the delta now records per staged package each asset the
install changed: the SHA-256 of its uncompressed bytes on both sides (`tools/asset_fingerprints.py`,
the header's `assets`). Old readers ignore the key. `pristine_delta.accept_replaced` takes a package
the update changed as its new pristine only when none of its files is still at the staged bytes,
index and shards are present (or the whole package is gone), and no recorded asset is still at its
staged bytes. The run must then pass the text signal. Both patchers call it.

The record on the real install of session `20261017-224744` (1.6.0.1): 787 assets in 7 packages
(`1`: 387, `15`: 302, `1050016095`: 72, `19`: 22, `10`, `20`, `21`: 1 each). It takes 12.7–14.1 s on
this PC, because stored chunks are compared first and only differing assets are decoded (43 s when
decoding everything).

`tools/research/check_update_repatch.py` fakes updates on copies of those real packages. It writes
asset bytes in place with `device_extensions.write_assets`, which moves chunks and rewrites the index
as a merge does:

| Faked update | Decision |
|---|---|
| None | Rebuilds all 11 files the install changed |
| A Chinese asset merged into package `10` over the patched copy | Refused: `10/10.db` still at staged bytes |
| Packages `1` and `15` replaced (pristine plus a merged Chinese asset) | Accepted `1/1_0.db`, `15/15_0.db` (their indexes read as pristine) |
| Repair put back 151 of the 302 textures in `15`, then a merge | Refused: 151 assets still translated |
| Repair put back all 302, then a merge | Accepted `15/15_0.db` |
| `21/21.db` still at staged bytes, its shard changed | Refused |
| Package `1050016095` removed | Accepted |
| `19/19_0.db` missing beside its index | Refused |
| The replaced case with a delta made without the asset record | Refused for `1` and `15` |

The Android bridge's `_restore_pristine` gives the same six decisions it was run on. Its pristine copy
holds exactly the files in `sha256` at those hashes, and replaced files are left out, so the build reads
them from the snapshot.

The Windows patcher's own steps over the replaced case, with a fake phone, the real build and the
cached APK:

| Run | Pull | Rebuild | Build and checks | Push |
|---|---|---|---|---|
| 1 | Partial: 21 of 24 files copied from the install's session, 3 pulled (327.2 MB) | 2 replaced accepted, 8 rebuilt (4 already untranslated) | 49 s; text signal pristine; the new delta's pristine side of both replaced files equals the update's bytes | 3 files written, 11 already on the phone |
| 2 | Partial: 0 pulled | 11 rebuilt from the new delta, nothing replaced | text signal pristine | Nothing written |

Limits: the updates are faked. Whether a real update leaves packages clean (every translated asset
repaired, or the package downloaded whole) or mixed, which still refuses, is ticket 01's open
question. Not measured here: the asset record's time on the phone, and a device run.

**Verdict:** shipped in both patchers, offline. After an update that leaves no trace of the translation
in the packages it changed, a run repatches without a clear and pulls and pushes only what changed.
Mixed packages and deltas made before the record still refuse.

## 2026-10-18 — Lobby "match" tab and rank-title spacing (Windows patcher, device)

The Xiaomi M2007J3SG lobby (data 1.6.0.1) read `Ranking  match  Training  Custom` and `Supreme StarIII`.

- `娱乐` was `match` upstream; `catalog_rewrites.json` now gives `Match` / `Pertandingan`.
- The rank title is not a catalog string. `PVPRankDataClass` (Lua `6CB505C6553141B4`, package `10`, in the
  override layer) builds it as `string.format("%s%s", Localize.GetString("RankLevel<n>"), romanCArray[level])`
  in `vGetRankTitle` and `vGetTitleByRankOrLevel`; Chinese reads `至尊星耀III`. `extra_text.SCRIPT_EDITS` makes
  both `"%s %s"`. Read back through the B-tree slot map (`qts_relocate.install_btree_slot_map`): the
  runtime's plain `build_slot_map` returns the stale slot after an in-place relocation and reads the old bytes.
- Install: the work folder had staged hashes but no pristine delta, so the patcher refused a translated
  phone. The phone's layer matched the kept session `20261017-230156` (1.6.0.1) in all but 11 files, every one
  in a staged package, and none of that session's files sits at a staged hash. The patcher ran headless with
  those 11 swapped in after the pull; its text signal read pristine, it wrote 7 packages (389 text tables,
  398 textures, 1 table left Chinese) and kept a pristine delta of 14 files (6.15 MB). One earlier attempt
  lost USB mid-pull (`device offline`) before writing anything; the normal APK was reinstalled by hand.

**Verdict:** pass. After *Scan to login* the lobby reads `Ranking  Match  Training  Custom` and
`Supreme Star III | 80/120`.
