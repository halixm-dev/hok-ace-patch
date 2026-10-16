---
feature: prime-rebuild
status: delivered
updated: 2026-10-02
branch: feat/prime-rebuild
commits: e21ed33..9be8adb
---

# Prime Rebuild

## Report

**What was built** — the patcher can now reach the half of the game's data it never touched. The game
reads the packages baked into the APK (prime) when the downloaded ones (override) lack an asset, and
this repo staged into override alone, so prime-only content was untranslatable — no text table, no
texture. `tools/package_rebuild.py` now re-lays-out packages `1` and `1050016095` whole with Tencent's
own builder (`resources/qtsvfs/`, driven by ctypes in `tools/qts_builder.py`), so their override copies
carry the prime-only content, translated, while prime-only assets that need no change are left out.
Everything reads back byte-for-byte before a package is written, and the in-place stager and the
extension pass both skip a rebuilt id.

Measured on game data 1.4.0.1: a run stages 392 replacements for package `1` (94 downloaded assets
re-translated plus **298** catalog tables taken from the APK — 51,095 records, the chessplayer names
among them) and 72 textures for package `1050016095`. **394 of the catalog's 398 texture edits now
apply, where 323 did** — 395 with package `21` rebuilt as well, the state this feature left the
pipeline in; `21` has since left `REBUILD_PACKAGES`, and the append pass in `prime-only-append.md` is
what reaches that 395th edit today. The Chessplayer names reach the layer the screen reads, which is
what the override-only path could never do. (The count was 400 before the device round below withdrew
the assets it convicts: the six extras left in the allowlist are six fewer replacements.)

Two more passes came with it. A table the in-place stager cannot fit is appended to the end of the shard
instead of being dropped (`exclude_extra_chunks` / `write_assets` / `relocate_text`), which recovers the
11 chessplayer tables the drop report recorded as permanently lost; and `extra_text` + `pb_text` +
`unity_text` translate display strings the catalog has no table for, gated on an allowlist because some
Chinese in those assets is a lookup key — an allowlist the device round below cut from fourteen assets
to four, each withdrawal recorded with the screen that condemns it. `count_translated` classifies a
rebuilt package by the texture share the entry carries, not by its mode, because one entry now holds
both kinds.

A later measurement refined what the builder is the only source of, without changing a run. Comparing
this cycle's `work/prime/1` against `work/rebuild-1/out/1` showed both lookup keys are identity
functions — an entry key varies only with the asset it names, a chunk's `hash1` only with the asset and
the chunk index — so an asset a package already carries needs no key derived at all. `[S2]`'s "The keys
the builder derives" has the counts, and `tools/research/key_derivation_probe.py` reproduces them.

**Later still: no package is rebuilt at all.** `REBUILD_PACKAGES` is now empty. Both packages this
feature named — `1` for its 298 prime-only text tables and `1050016095` for its 71 prime-only textures —
are covered by the append pass, which adds records to the container the game already reads instead of
laying it out again, so QtsVFS.dll has no caller left in the pipeline. `prime-only-append.md`'s T11 and
T12 measure what that costs and what it gains, asset by asset: packages `1050016095` and `21` come out
holding exactly what their rebuilds held, and so does package `1` on every catalog table. The first
attempt reported **393 text tables against this rebuild's 392**, and the extra two were this rebuild's
own rule working as intended rather than a gap: `3914DBBFECD1E54D` and `63922EF4D4C86526` are tables
`adaptive.scan` recognizes and resolves although the catalog has no record for them — and one of them
cannot be given a verdict at all, because every one of the game's 277 packages has its key referenced by a
single row, a draw type windowed for a month that ended a year before this build. They are now dropped by
`build_device_patch._drop_uncatalogued_tables`, so the primary pass means the catalog's tables and
anything else needs a cycle, which is what `[S2]`'s transform was for; the run reports **391 text tables
and the same 395 images**, one short of the rebuild because the append's encoder cannot store
`3A70308AAF6F18F8`. The rebuild is otherwise untouched and reachable by name, which is what keeps it as
the path for a package that has to be re-laid out rather than added to.

**Verification** — all from the project root, on head `5bf1ab3` unless noted:

| command | result |
|---|---|
| `py_compile` on the 13 changed/new modules | PASS (exit 0) |
| `tools/research/check_graphics.py` | PASS, 91 s, "all checks passed" (324/324 `.blocks` ported, 74/74 `.assets` replayed) |
| `tools/research/check_graphics.py --game <dump>` | PASS, 95 s; `ported 321, replaced 1, spliced 1, absent 75` |
| `tools/research/prime_probe.py` | prints the `[S1]` table exactly |
| `build_device_patch.py --apk … --builder …` vs the 102304 dump | PASS, exit 0 in 128 s; packages `1` and `1050016095` `rebuilt` (400 / 72), `15`/`19`/`20` graphics, `4` extra-text; `text_skipped` and `graphics_skipped` both empty; **all 21 guarded files of the dump byte-identical afterwards** |
| frozen exe `app/build_exe.py` then `--selftest <dump> <out>` | PASS; exe contains `QtsVFS.dll`, `QtskDB.dll`, `pypinyin`, `package_rebuild` and not `prime_probe`; selftest exit 0 in 60 s with `relocated-text 11` for package `1` and `text_skipped` empty |
| `patcher_core.count_translated` on the run's summary | PASS — `text=402 images=394`; a mode-only classifier would have said `474 / 323` |
| extra-text probe: allowlist gating and a rewrite round-trip | PASS — only `SAFE_ASSETS` selected, 34 unallowlisted Chinese-bearing assets offered and none taken, second pass changed 0 strings |
| post-review probes: `read_raw` contract, per-package reconciliation, empty-transform guard | PASS — the guard was exercised by stubbing a prime-only table to `b""`: 700 assets, 297 added, no exception |
| `tools/research/key_derivation_probe.py` (added after this feature; the `3914DBBFECD1E54D` artifacts and session `20260929-191327`) | PASS — 679 shared assets: the entry key moved for 0, and 13 of 13 re-chunked assets kept every shared `hash1`; `--survey` over the dump's 278 packages: `hash1` differs per chunk in all 3462 multi-chunk assets, and the entry key is no `hash1` half in all 79,617; `--record` on `7B4CC5DF48336D2D`: the builder's record and prime's agree on every field but the record's own offset and the 16 bytes at `+52`, while the content differs; `--stager` on the phone-pushed session: the stager changed only `+44` (99 records) and `+80` (11 of those) and never the token, so a harvested record is a whole record |

Independent review of `e21ed33..1341055` found no critical issue, three low-severity ones and one
documentation error; the fixes are `263631b`, re-reviewed as `1341055..263631b` and found correct and
complete with no regression. `5bf1ab3` follows that re-review and its guard is verified by the stub run
above.

**Device test** — on the phone (Xiaomi M2007J3SG, Android 12, game data 1.4.0.1), reverting the six
packages to a pristine download between runs:

| run | package data | APK | result |
|---|---|---|---|
| control A | pristine download | debuggable | **died**, signal 7 (bus error), ~14 s after launch |
| control B | pristine download | normal | **ran**, `MountPackage 1 / 1050016095, override => succeed!` |
| patched | this run's six packages | normal | **ran**, same pid past 90 s, `BulkExportFromPackageJob done, result=1, errorCode=0` |

Control A is what settles the earlier crash: a debuggable build kills the game on its own, with no
patch present, so both crashes seen earlier — and the "reverting the packages still crashes" test —
describe the debug build, not this feature. The `GCloud` / `QTS_LOG` lines that were read as a crash
signature (`CheckLocalPatchDiffFiles blModified = [1]`, `GetAllSubpatchInfo ArraySize:[552]`) appear on
the unpatched control too. That is now a constraint in `AGENTS.md`, and the cache bug it exposed is
`9be8adb`.

The installed data was checked below the UI: package `1` as staged holds **388 catalog tables with
`translated: 0`** against 90 in the pristine download — the delta of 298 is the APK-only tables — and
`00BF2528D217FFFA` (`战队` / `最强王者达成次数` in the APK, translatable there) reads English. So the
tables this feature exists for did reach the layer the game mounts, and the device build reproduced the
offline run exactly (701 assets, 298 from the APK; `402 text tables, 394 images`).

**Not yet seen on screen** by that test: it covered boot and the installed data only.

**Device test, second round** — the user logged in, and the text and textures *were* there; four
regressions came with them, and all four were the `extra_text` pass, not the rebuild:

| symptom | cause | how it was found |
|---|---|---|
| no game button after pressing start | mail / quiz / notices | not the textures (reverting every texture package left all four), not the catalog tables (a build with `extra_text` off fixed them while 388 tables stayed English) |
| encyclopedia blank | mail / quiz / notices | as above |
| chessplayer skill-description button gone | the four skill assets | same |
| **tournament replay force-closes** | **task names `5214339F97C419ED`** | see below |

The replay crash is not a scripted quit: `adb shell dumpsys activity exit-info com.tencent.tmgp.osgame`
reports `reason=2 (SIGNALED)`, `status=11` — SIGSEGV — with `pss` 1.2–1.3 GB, 2–3½ minutes into each
session, and it never reaches logcat (`WIN DEATH` and `has died: fg TOP` only), the `crash` buffer is
empty and dropbox has no `data_app_crash`. So the search rested on the user's reports, and the reports
had to be single-variable:

| package 1 content (textures and package 4 identical on both sides) | replay |
|---|---|
| 388 tables (90 override + 298 prime-only), `extra_text` off | works |
| + `1C8F7FFF7BDEF14D` compliments | works |
| + `A1987F488164E53A` display-text table | works |
| + `5214339F97C419ED` task names | **SIGSEGV** |
| + `B5D856BFDF22400D` rule pages and `2D1113B0AD51A562` nicknames (task names left out) | works |

So the pass is content-specific rather than unsound, the shipping `SAFE_ASSETS` is those four assets,
and the rebuild is cleared: the tables-only build replays fine, which matches the user's own history —
the install they had been playing predates this port and had no `extra_text` pass at all.

The last row also settles the earlier deduction that the four assets were "exonerated". They were not:
those deductions treated *not changed in the staged package* as *disabled*, and an enabled asset that
rewrites nothing looks identical to a disabled one — which is exactly what `A1987F488164E53A` did in
one build. Only a pair of staged builds, differing in one asset, supports a causal claim.

**Journey log**

- The handoff's own figures did not survive measurement: it gave the override package as 26.8 MB where
  disk says 29.3 MB, and 2494 prime-only where the count is 2492. Measuring before designing is what
  produced `[S1]`, which is why the probe is committed rather than left in `%TEMP%`.
- Two durable claims were wrong for the same reason — `check_graphics.py --game` prints `absent: 75` and
  both `README.md` and project memory read that as "not in the mobile build". It is a census of the
  downloaded layer, and the APK carries 73 more, including 26 of the 27 wide faction panels the Card
  Info ribbon is drawn from. The tool's own wording was what invited the mistake, so the wording was
  fixed too. Never conclude an asset is absent without counting `assets/bin/Data/Package/builtin/`.
- The relocation pass was expected to be inert once package `1` is rebuilt, and it is — on the path where
  the APK is available. On the path without one it is not, and that is the run that proves it recovers
  the 11 tables. A pass can be worth porting precisely because it is dormant on today's data.
- `QtsPackage.entries` over-reports a rebuilt package (703 against 701 real entries) because the dropped
  builder records stay as dead space in the index. Asset counts have to go through the B-tree.
- One entry, `56077AC5D3F0B677`, declares fewer bytes than its stream holds. Carrying the stream whole and
  recording what was carried is the only self-consistent option, and truncating bytes we do not
  understand would be the worse guess; it is named in `README.md` as the thing a device run has to settle.
- Two hours went into a crash that was never this feature: run 1's launch *and* its revert test both ran
  on the debuggable access APK, because the restore before them had failed and the failure was reported
  only through `ui.log`, which the harness had stubbed to a no-op. The lesson is not "test on device" but
  that any failure announced through a UI callback can be swallowed by a headless caller, so nothing that
  decides whether the run worked may live there.
- A rebuild that stages nothing is not evidence of a broken rebuild. `unreadable_assets: 701` plus
  `translated: 4` came from a dump that was already patched, so every table was English and the transform
  had nothing to change — `already_english: 260426` against a pristine dump's `2303` says so outright. A
  dump's provenance has to be established before its build is believed, which is why the session from
  21:31 was preserved: it is the only pristine copy of 1.4.0.1 this repo holds.
- Restoring packages from such a dump is not the same as a fresh `pm clear`, and the difference is
  measurable: the restored download pulls 2.667 GB where patched data pulls 2.737 GB, and control B boots
  on it. That is what makes a revert test sound here, where the earlier one was not — it reverted to the
  *previous patch's* output and so could neither convict nor clear anything.
- The allowlist bisect was worth one device cycle per asset because each cycle started from the
  configuration last known good rather than from the failing one. That makes the recovered set grow
  monotonically and every verdict usable on its own, where bisecting down from the full build would have
  produced a run of "still broken" and one usable answer at the end.
- Ask for symptoms one at a time. "All four still broken" is one bit that costs a full cycle; the report
  that split the start button and the encyclopedia from the skill button and the replay halved the search
  in one message. The same report is what showed the four symptoms were two unrelated asset groups.
- A failure that arrives *after* a screen has been up for thirty seconds needs the exit record, not
  logcat: `dumpsys activity exit-info <pkg>` names the reason, the signal and the pss, while the client
  suppresses tombstones and the game's own log (`Android/data/<pkg>/files/bqLog/...`, readable with plain
  adb and no `run-as`) stops mid-network-ping.
- Verifying a code change against a device-validated build has to compare **asset by asset**. The rebuilt
  container is re-laid out on every build, so `1.db` and `1_0.db` differ between two builds with identical
  content — 701 of 703 entries byte-identical, no metadata difference at all. The two that did differ are
  the builder's own bookkeeping nodes, which carry the build machine's **absolute output path**
  (`...\shipped` against `...\probe-final`); Tencent's builder embeds it, so no two rebuilds agree unless
  they share an output directory.
- Package `21` was left out of `REBUILD_PACKAGES` on the grounds that its APK copy is 511 MB and a rebuild
  "recompresses all of it". That was the wrong number twice over. A rebuild lays out the *downloaded* copy:
  4866 assets, 40.7 MB in, 48.1 MB out, 101 s. And cost was never what stopped it — the reader refused the
  package. `read_raw` dispatched on the entry's compression id, which is 9 for 1285 of those 4866 entries,
  and 9 was not in its list. Measured across packages 19, 20 and 21, id 9 is the same LZ4 block data as id
  1 behind a 12-byte-longer entry descriptor: 62 of 62 sampled chunks decoded to exactly their declared
  size, while id 4 (Oodle) refused LZ4 outright.
- The chunk framing is per chunk and self-describing, so no list of ids can be complete. Twelve assets of
  package `21` hold Zstandard frames — one of them, `7CCE483D88B236CF`, is an LZ4 chunk followed by a zstd
  one, and three of the twelve declare id 1 or 4 while holding zstd. `read_raw` reads the payload's magic
  first now, which is why `zstandard` is a run-time dependency. An entry's id is a hint; the payload is the
  fact.
- Rebuilding `21` exercised two behaviours for the first time. Four entries
  (`B85AF970632CE322`, `C9ABDBDE9643A78C`, `CDE7C688F1E0185A`, `E5FBCD1C777EB18E`) have no chunks in either
  layer, and one of them used to abort the whole package; they are now left out and named in
  `entries_without_bytes`, which loses nothing the game could load, since an index entry pointing at
  nothing is unreadable there too. Bytes that exist but will not decode still abort instead of being
  dropped, because dropping those would revert the assets to the APK's revisions with nothing in the log to
  say so. On this data `21` rebuilds to 4863 assets with 1 translated from the APK — the wide Central Plains
  panel whose absence left the Card Info ribbon showing `❖ 河洛 ❖` while the grid card beside it was already
  English — and the pipeline as a whole went from 128 s to 219 s.

- Package `21` was rebuilt, put on the phone and withdrawn in the same session. It carries the wide
  Central Plains panel `7B4CC5DF48336D2D`, so its rebuild is what turns that card's Card Info ribbon from
  `❖ 河洛 ❖` into `Central Plains`, and it does: 4863 assets, 48.7 MB, mounted by the game, the panel read
  back as English, the English ribbon seen on the phone. What it also does is break one card. With the
  rebuilt package the Factionless hero Yixing draws as the game's grey placeholder — `TimiText`, a stray
  `朵莉亚`, no art, no faction bar — and its Card Info panel comes out equally blank; restoring Tencent's
  own copy of `21` draws that card correctly again, which is how the two states were told apart. So the
  panel stays Chinese and `21` stays out of `REBUILD_PACKAGES`. The tempting explanation is the 511 MB,
  and it is wrong: cost was never what stopped this, and for a package this size the rebuild is cheap.
- What the rebuild does *not* explain is why one card goes, and the honest state of that is: unidentified.
  Every asset of the rebuilt package is byte-identical to Tencent's for the 3470 entries that could be
  compared, every entry's declared codec decodes its own payload, and no asset of the package mentions the
  card in text at all — so the trigger is in the container, not the content: the four entries the rebuild
  dropped (index entries with no chunks in either layer, `B85AF970632CE322`, `C9ABDBDE9643A78C`,
  `CDE7C688F1E0185A`, `E5FBCD1C777EB18E`), the two u32 flag words `finalize` restores per entry, or the
  descriptor layout the builder writes where Tencent's updater wrote a 12-byte-longer one. Narrowing that
  is where a further attempt would start.

## [S1] Problem

The game's data has two layers, and this repo only ever writes to one of them.

| layer | where | contents |
|---|---|---|
| **prime**, baked into the APK | `assets/bin/Data/Package/builtin/<id>/` | every asset as the APK was built |
| **override**, downloaded | `files/QtsVFSCache/packages/<id>/` | only the assets that changed since that build |

The game reads override first and falls back to prime. `Patcher.pull_game_data` pulls
`files/QtsVFSCache packages Watchdog` and nothing else, `build_device_patch` stages only into that
layer, and `device_extensions.extend_graphics` reads only override packages. **An asset that exists
only in the APK cannot be translated by this repo at all** — no text table and no texture.

Measured on this machine, game data 1.4.0.1, `dist/HOK ACE Patcher Data/installed.apk` against the
session dump `sessions/20260930-102304/game` (the measurement is recorded as
`tools/research/prime_probe.py`, added with this change):

| | package `1` | package `1050016095` |
|---|---|---|
| prime entries | 2873 (45.9 MB) | 608 (5.2 MB) |
| override entries | 403 (29.3 MB) | 2 (0.3 MB) |
| shared | 381 | 2 |
| **prime-only** | **2492** | **606** |
| of those, `catalog.known` | 408 | 0 |
| of those, **translate** | **298** (51 095 records) | 0 |
| of those, `catalog.graphics` | 0 | **71** |

Package `1`'s prime-only translated tables are the chessplayer domain in bulk — the names on the
Chessplayer screen among them — and package `1050016095`'s 71 prime-only textures are arena and map
art the texture pass currently cannot reach. 2084 of package `1`'s prime-only assets and 535 of
`1050016095`'s are covered by neither the catalog's tables nor its textures.

The user sees this as Chinese on screens whose neighbours are English: the Chessplayer page shows
`Chessplayer` and `Combat Power` translated and its portraits named in Chinese. The screen draws from
the prime layer, so no amount of override-layer translation could fix it — every chessplayer name
already had English label records staged into the override tables that *were* applied.

Separately, and already reported rather than fixed, the in-place stager loses tables at the container:
package `1` stages 81 of its 92 translated override tables and drops 11. That loss is real but it is
not the cause of the Chessplayer screen; the prime layer is.

## [S2] Design

### The builder

`resources/qtsvfs/` ships Tencent's own package builder — `QtsVFS.dll`, `QtskDB.dll` and the three VC
runtimes they load — beside `resources/adb/`, `resources/key/` and the catalog. `tools/qts_builder.py`
drives `VFS_BuildPackage` by ctypes, then aligns the output with the package it replaces:

- `Builder(bin_dir)` resolves the folder and loads both DLLs through `os.add_dll_directory`, calls
  `VFS_Initialize_Scripted` when the export exists;
- `build(package_id, assets, work)` writes each asset to `BatchAssets/<hash>.assets`, a
  `qts_layout_desc.json` and a `qts_package_desc_<id>.txt` line per block, then calls the DLL and
  returns its output folder;
- `finalize(built, package_id, file_hashes, template_node, entry_words)` drops the records only the
  builder writes (the `INGQ` global-index node, the export-setting and remain-dir node files), copies
  the original `QTSF_PACKAGE` node over the builder's, restores the per-entry flag words, and removes
  the dropped keys from the B-tree leaves.

Contracts the code must keep, each already paid for once:

- `MaxStorageSize` **must** be set (1 GiB). Left unset the builder reads uninitialised memory and
  writes one storage file per asset.
- The packed compression flag is `level << 16 | type`, level 5 — the game's own recorded level.
- Every asset handed to the builder must be non-empty; the builder cannot store a zero-byte file.
- `finalize` must find exactly the entries it was given, and a B-tree leaf must not be emptied.

### The keys the builder derives

Both B-trees order a package by a key the builder mints: the index by each entry's key (record `+12`),
the shard by each chunk's `hash1` (slot `+12`, ordered on its low 32 bits). Neither key depends on the
content it points at. `tools/research/key_derivation_probe.py` measured it on this cycle's own
`work/prime/1` against `work/rebuild-1/out/1`, the 679 assets both hold — content compared after
decompression, so a re-compression is not read as an edit:

| what changed | assets | keys identical |
|---|---|---|
| content bytes | 677 | 664 |
| byte length | 653 | 640 |
| chunk count | 13 | 13, for every chunk index the two share |

The entry key moved for none of the 679: `C779022CBA18BDBE` was re-chunked from 146 chunks to 153 and
kept it, and `0058049528CF2027`, whose content grew 47,973 → 52,795 bytes, kept every `hash1`. The 13
whose byte length changed *and* whose keys moved are exactly the 13 that were re-chunked, and for the
chunk indices they share they kept `hash1` as well. So an entry key varies only with the asset it names,
and a chunk's `hash1` only with the asset and the chunk index.

Surveying all 278 packages of the dump (79,617 assets, 87,527 chunks) agrees: `hash1` differs per chunk
in all 3,462 multi-chunk assets, and in all 79,617 assets the entry key equals neither half of any of
that asset's `hash1` values — so there is no arithmetic shortcut between the two keys. The shard agrees
with what `qts_relocate` already assumes: 91,941 of its 102,790 active leaf keys are a slot's
`hash1 & 0xFFFFFFFF`. 101 packages of the dump have an index and no shard, so they carry no chunk to
check.

Neither function has been named, and naming them is not needed: being identity functions, both are
recoverable from data. `hash_probe.py`'s XXH64 and `probe_descriptor_hashes.py`'s `qts_hash` were tested
over the packed inputs (`<QI`, `<IQ`, the 16-hex-digit form, each half folded) against 2,873 entry keys
and 3,197 `hash1` values, with no match.

What this buys is that an asset a package already carries needs no key derived at all — its keys are in
the package — and a chunk index that did not exist before is the only *key* work the builder still owns
(re-chunking is the only thing here that creates one: 13 of 679 assets, or a table keyed on
`(file_hash, chunk_id)` covering the dump's 87,527 chunks, on the order of 2 MB).

**The keys are not all a record carries, and what else it carries is inherited from the stager.**
Measured on the asset the append pass actually uses — `7B4CC5DF48336D2D`, the one catalog edit that lives
only in the APK's package `21`, `work/prime/21` against `work/insert-21/out/21` through
`key_derivation_probe.py --record` — the builder's minted record and the prime package's shipped record
disagree on exactly five u32s: `+00`, the record's own offset in the index, which is positional, and the
16 bytes at `+52..+67`. Everything else agrees byte-for-byte while the content is entirely different: the
same entry key `3E2FE941`, the same chunk `0` `hash1` `4D90FAD807B56200`, one chunk, the same declared
size 43168, chunk size 307200 and packed flag `00050004`. Those 16 bytes are content-derived — the same
file hash, the same byte length and the same keys still give different tokens — and no stdlib digest
(MD5, SHA-1 and SHA-256 truncated to 16, BLAKE2b-16, BLAKE2s-16) named them.

They do not have to be named, because nothing checks them. `device_extensions.write_assets` states it in
a comment — "Descriptor (32 bytes at entry+28) keeps its integrity token; only the raw length changes" —
and `key_derivation_probe.py --stager` measures it on a real run rather than trusting the comment:
session `20260929-191327`, `mode: full`, status `verified`, whose staged package was pushed to a phone.
Package `1`'s source and staged indexes over their 381 shared entries differ in exactly two fields, the
raw length at `+44` (99 records) and the chunk size at `+80` (11 of those), and **the token at `+52..+67`
moved in none of the 99, including the 70 whose content was replaced outright.** So the game loads an
entry whose token does not describe its content.

That is what makes the harvest a whole record rather than most of one: a record taken from prime matches
a builder-minted record in every field the stager itself writes. The append path has since dropped the
builder for this reason (`prime-only-append.md`, T9): the keys come from prime, the payload is re-encoded
by the encoder `write_assets` already uses, and the token rides along unused. What the builder remains
the only source of is a chunk index the package does not already carry, which is why `write_assets` keeps
the chunk count instead of adding one and why an append keeps prime's chunking. The measured
Talent Card exception in `prime-only-append.md` T15 uses one offline-derived identity key to keep
its original chunk size, without adding dictionary rows or loading the builder during normal runs.

### Which packages are rebuilt

`package_rebuild.REBUILD_PACKAGES` names the packages to lay out whole. It is **empty**: both packages
this feature named — `1` for its 298 prime-only text tables and `1050016095` for its 71 prime-only
textures — are now covered by the append pass, which adds records to the container the game already reads
instead of rebuilding it (`prime-only-append.md`, T11). The rebuild stays for a package that has to be
re-laid out rather than added to, and it is the only caller of QtsVFS.dll left. `21`, which holds the wide
Central Plains panel, reaches the phone by append; a rebuild of it costs the Factionless card, and the
journey log has the screen.

### `rebuild_package`

For a rebuilt package the output override package holds

- **every asset the override package already has**, translated where the transform changes it and
  byte-identical otherwise, and
- **every prime-only asset the transform actually changes.**

A prime-only asset that needs no change is deliberately **left out**, so the game keeps reading it
from the APK instead of carrying a second copy.

An asset listed in the override index whose bytes cannot be read (the flag-word entries whose payload
is the APK's are read from prime instead) aborts the package: `rebuild_package` logs and returns
`None`, and the package falls back to the in-place path. One unreadable asset must not cost the
package its patch. Two of package `1`'s 403 entries are prime-backed this way (`92D3EE5696C9D644`,
`5B905F540C9F7046`), and an entry whose bytes are empty counts as unreadable too, because the builder
cannot store a zero-byte file.

One entry, `56077AC5D3F0B677`, arrives declaring 7,597,568 bytes while its 28-chunk stream holds
8,519,168. The builder derives an entry's chunking from the bytes it is handed, so a rebuilt package
cannot both carry that stream whole and record the device's shorter figure. The stream is carried —
dropping 921,600 bytes of data we do not understand is the worse guess — and the length it actually
holds is recorded, which leaves the rebuilt entry self-consistent where the device's own copy is not.
That length and the 16-byte token derived from it are the only values the rebuilt package differs from
the device's copy in for any entry: every other entry keeps its bytes and its declared size, and the one
field that differs elsewhere is the record's own offset, which necessarily moves when the index is
re-laid-out. The stream itself — what the game decompresses — is byte-identical, and only a device run
settles whether the recorded length matters.

Before anything is staged, every asset is read back through the same `QtsPackage` code path the game
data goes through and compared byte-for-byte, and the package node must equal the original's; any
difference raises rather than producing a package to install.

### The transform, and what it reports

`make_transform(catalog, catalog_dir, log)` builds the per-asset decision shared by both layers:

| asset | action |
|---|---|
| `catalog.known` | `adaptive.translate_table`; a table the runtime refuses is logged and left alone |
| `catalog.graphics` | `mobile_graphics.english_raw`; must return the same length |
| `extra_text.SAFE_ASSETS` | `pb_text.rewrite` with the catalog's official English |
| anything else | no change |

It returns `bytes \| None`, where `None` means "leave the bytes as they are". Those bytes were left
alone for two different reasons, and the texture pass's accounting depends on telling them apart — a
texture that is already English is done, a texture the codec refuses is a skip. The caller therefore
passes in a `refused: set[int]` the transform adds to for a `catalog.graphics` asset whose
`english_raw` returned `None` or a different length. The set is single-threaded and the caller clears
it between packages.

### Skipping the rebuilt ids

A rebuilt package no longer matches the device's copy, so no other pass may touch it: the in-place
loop skips a package whose id is in `rebuilt`, and the extension pass takes `skip=rebuilt`. Without
that the in-place stager would re-derive a package the rebuild already replaced, and the extension
pass would apply textures to a container it did not build.

### The relocation pass

v1's second staging path, ported into `device_extensions.py`: text that the in-place stager cannot fit
is appended to the end of the shard instead of being dropped.

- `exclude_extra_chunks(package, replacements, work, log)` copies the plan without the tables that
  would need more chunks than the original holds. New chunks need lookup keys only the game's builder
  can derive; the stock stager would invent them. It returns the pruned directory and the excluded
  hashes.
- `write_assets(package_dir, jobs)` writes new raw bytes for assets of an already staged package,
  keeping each asset's chunk count and enlarging its chunk size instead, and adjusting the entry's raw
  length and chunk-size words in the index. It returns the hashes it wrote and the ones it refused.
- `relocate_text` is `write_assets` over the tables the loop did not stage; `relocate_assets` is
  `write_assets` over the extra-text pass's jobs.

`extend_graphics` stays the single entry point for the extension passes and keeps its two-list return,
gaining `dropped_text` and `skip` arguments. In order it runs `relocate_text` over the collected
tables, the graphics pass over every discovered package, and the extra-text pass.

### How relocation and `text_skipped` interact

`text_skipped` means text that was **translated and then not applied**, and relocation is a way of
applying it, so the two must be reconciled or the report will claim a loss that did not happen.

`note_missing` currently runs inside the loop over `plan - staged`. It moves after the extension pass,
and the set it reports is `plan - staged - relocated`, where `relocated` is the set of hashes
`write_assets` actually wrote. A table excluded from the in-place plan and then relocated end-to-end
is therefore not reported at all, and a table that relocation also refused is.

On the 1.4.0.1 data this machinery is expected to be **inert for package `1`**: the rebuild absorbs
the whole package before the loop reaches it, so the 11 previously dropped tables arrive through the
rebuild and `text_skipped` becomes empty. It is ported because the drop is data-dependent — 1.3.0.4
lost 15 of 92 — and because it is the only path that recovers a table for a package the rebuild does
not cover.

### The extra-text pass

Non-catalog display text that the PC catalog has no table for, ported as three modules:

- `pb_text.py` — schema-less protobuf string rewriting. Length-delimited fields are classified
  heuristically: valid UTF-8 without control characters is text, a field that parses completely as a
  message is recursed into, anything else stays opaque.
- `unity_text.py` — Unity 2022.3 `SerializedFile` string swap. Tencent sets the "type tree enabled"
  flag but writes zero nodes, so only the object table is parsed; only MonoBehaviour (class 114)
  objects are touched, because GameObject names can be lookup keys.
- `extra_text.py` — the allowlist and the romanisation.

`SAFE_ASSETS` is an **allowlist**, not a blocklist: rewriting every matching string in the config
assets broke the login screen, because some Chinese there is a lookup key rather than a label.

After the device round below it is exactly four assets, and none of them may be added to without a
device cycle:

| asset | what it is |
|---|---|
| `2D1113B0AD51A562` | AI opponent nicknames (~11 000), romanised with `pypinyin` — the catalog has no official translation for them |
| `A1987F488164E53A` | display-text table `{id, text, #key#}`, 474 replacements |
| `1C8F7FFF7BDEF14D` | post-match compliments, 13 strings |
| `B5D856BFDF22400D` | rule pages, 16 strings |

Withdrawn, each by the screen it breaks: task names `5214339F97C419ED` (a tournament replay SIGSEGVs),
the four chessplayer-skill assets `10271B050169A7B7` / `0FDA07B7C51E4AC5` / `DEE91C1DE999F3AF` /
`D9A68213BB843F61` (the skill-description button disappears), mail `5B7E509D10BD722F` / quiz
`A3B34BE9879BE25B` / notices `721918D44EDAB146` (no game button after pressing start; blank
encyclopedia), and both package-4 assets `E0FF23C02C95D892` / `13429059252DC6EB` — package 4 stays
pristine because its path is the in-place `write_assets`, which does not verify its own write.

Packages `10` (skill-editor labels) and `14` (gameplay scripts) are excluded: Chinese there is logic.
`UNITY_TEXT_PACKAGES` stays empty — rewriting package 19's prefab labels hangs the lobby, and rewriting
only the faction labels in the 15 prefabs that show them crashes the game with
`stack corruption detected`.

The hashes already tested and their failures stay in the comments beside the allowlist, so the next
addition starts from the record rather than repeating it.

### What the run reports

The summary keeps both existing loss lists and gains a `rebuilt` mode.

```json
"packages": [
  {"package_id": "1", "mode": "rebuilt", "source_package": "<device override dir>",
   "fit_summary": null, "stage_report": {"status": "rebuilt", "replacement_count": 400},
   "assets": 701, "translated_downloaded": 102, "added_from_apk": 298, "textures": 0},
  {"package_id": "1050016095", "mode": "rebuilt", "source_package": "<device override dir>",
   "fit_summary": null, "stage_report": {"status": "rebuilt", "replacement_count": 72},
   "assets": 73, "translated_downloaded": 1, "added_from_apk": 71, "textures": 72}
]
```

- A rebuilt package's `replacement_count` counts the assets the transform **changed** — translated
  override assets plus prime-only assets it added — not the assets it carried. `assets` is the total
  the rebuilt package holds. On this data that is 400 of package `1`'s 701 and 72 of
  `1050016095`'s 73.
- `textures` is how many of those `replacement_count` assets were `catalog.graphics`.
- `count_translated` must therefore not classify a rebuilt package by mode alone: for
  `mode == "rebuilt"` it adds `replacement_count - textures` to the text count and `textures` to the
  image count. Package `1` is text-only and `1050016095` is texture-only, so classifying on the mode
  alone would report one of them as the other kind.
- `fit_summary` is `null` for a rebuilt package: the builder lays the container out, so nothing
  competes for slack and the in-place retry loop's diagnostic does not apply.
- A texture the rebuilt package's transform refused is reported in the existing `graphics_skipped`
  list, with the same entry shape the texture pass uses (`skipped_count`, `considered_count`,
  `skipped`). Its meaning is unchanged — a texture that was never translated — and the
  `refused` set above is what makes the distinction from "already English" possible.
- `text_skipped` keeps its exact meaning: text that was translated and then **not applied**. A table
  the rebuild's transform refused was never translated, so it is logged per asset and does not enter
  either list; a table the in-place loop could not stage but relocation wrote is not a loss either.
  See the reconciliation above. On this data there are no refusals in package `1`.
- When `apk` or `builder_dir` is missing, `build_patch` logs that prime-only content stays Chinese and
  stages exactly as it does today. That keeps `--selftest` and the offline CLI usable without the
  DLLs.

### Where the prime layer comes from

`Patcher.prepare_normal_apk` already pulls the installed APK to `work/installed.apk` — or builds
`work/normal.apk` from it when it has to re-sign — and the `apk` step runs before `translate`. So
`build_translation` passes `apk=self.normal_apk` and `builder_dir=BUNDLE / "qtsvfs"`. The APK that
supplies the prime layer is the one installed on the phone.

`build_patch` gains keyword-only `apk: Path | None = None` and `builder_dir: Path | None = None`, and
`main()` gains `--apk` and `--builder`.

### Packaging

`resources/qtsvfs/` joins the shipped resources and `app/build_exe.py` adds it with `--add-data`, so
the frozen exe can rebuild on any machine. `pypinyin` joins `requirements.txt` and `HIDDEN_IMPORTS`.

### Which pass owns a string, and how to find out

A string that is still Chinese is diagnosed from the data, in this order, rather than guessed at:

1. **Capture the exact Chinese** — from the user's report, or `adb exec-out screencap -p > s.png`.
2. **Look it up in the catalog**: `resources/catalog/catalog.json.gz`, where `unique` maps Chinese to
   the PC patcher's official English. Set `PYTHONIOENCODING=utf-8` on Windows, or printing CJK raises
   through cp1252.

   ```python
   import gzip, json
   cat = json.load(gzip.open("resources/catalog/catalog.json.gz"))
   print(cat["unique"].get("瑶妹"))   # -> "Yaria"
   ```

3. **Find the asset that holds it, in both layers**: the phone's dump for override, and
   `package_rebuild.extract_prime` for prime. Read each candidate through
   `QtsPackage(...).build_slot_map()` and `qts_relocate.read_raw`, then search those bytes for the
   UTF-8 string. That gives the **package id** and the **file hash** (16 hex digits).
4. **Classify what you found**:

   | finding | the pass that owns it |
   |---|---|
   | `catalog.known`, asset prime-only | the append pass — it reaches the device copy without changing the container's shape; a rebuild (`REBUILD_PACKAGES`) is the fallback for a package that has to be re-laid out whole |
   | `catalog.known`, asset in override | it should already apply; ask whether the stager dropped it for not fitting (`text_skipped`) and whether relocation recovered it |
   | not a catalog table, protobuf display text | the extra-text allowlist, after a device cycle |
   | a package-19 prefab, or a definition table | nothing safe — `[S3]` |
   | not in either layer | the launcher or native code; it cannot be patched through game data |

Beyond the prime layer, four things leave a string Chinese, and none of them is a missing
translation: no catalog table covers the asset (the extra-text pass, or nothing); it is a prefab or a
definition table, where a rewrite is unsafe; it comes from the launcher — the login title,
`正在初始化游戏` — and is not in game data at all; or the translation exists and is **too long** for the
mobile layout, which is a text-length problem rather than a missing string.

### The device test loop

The game's data has to be fully updated to the login screen before a patch goes on — after a game
update that means clearing the data, downloading it again, and only then patching. One change per
cycle, and the cycle's verdict recorded before the next one starts:

1. Build offline against a dump first: `tools/build_device_patch.py --runtime resources/runtime --game
   <dump> --catalog resources/catalog --work <w> --output <o> --apk <apk> --builder resources/qtsvfs`.
   It needs Python **3.12** — `resources/runtime/` is 3.12 bytecode. **The dump has to be the game-data
   version the phone is running** — `<dump>/WXQ_Data/Package/builtin/1/1.info` against the phone's own
   `files/QtsVFSCache/packages/1/1.info`. A staged package is a *revision of one layer*, so pushing one
   from an older version reverts every asset the game changed in between, and the symptom is a load that
   stops at 0% followed by the game repairing itself with a download. Tried on 2026-10-02: a cycle
   staged from the 1.4.0.1 `artifacts/game-dump` went onto a 1.4.0.2 phone, reverting a 34 KB Chinese
   config asset and a 13.5 KB English one, and produced no verdict on the asset being tested. Check the
   version before the push, or the cycle is wasted and the phone loses its translation.
2. Back up `packages` **and** `Watchdog`, so the cycle can be rolled back.
3. Push the staged directories to `files/QtsVFSCache/packages/<id>/` and delete
   `files/QtsVFSCache/Watchdog/*`; `app/patcher_core.py` holds the sequence.
4. Open the game, read `adb logcat` for QtsVFS errors, and screenshot the login screen.
5. Log in — *Scan to login*, since a re-signed APK cannot do direct WeChat/QQ login — and walk the
   screens the change should have touched: the loading tips, the Chessplayer page, the lobby, the Card
   menu, the arena artwork.
6. Nothing is "translated" until the user has seen it after logging in. A staged file that reads back
   correctly is not evidence about a screen.

### Working rules

- One change per device test, and the verdict — success or failure, symptom, date — recorded beside
  the hash it concerns, in the code, not in a session log.
- Use the PC catalog's official English. Translate freely only where no equivalent exists, and put
  that in `OFFICIAL_FIXES` with its reason.
- Never change the length or the structure of a binary asset whose format is not understood, and
  always read a staged asset back before pushing it.
- Check **both** layers before calling an asset unreachable. `check_graphics.py --game`'s `absent`
  count is a census of the downloaded layer alone; `tools/research/prime_probe.py` is the census that
  includes `assets/bin/Data/Package/builtin/`.

### Documentation

The method above is ported from a handoff guide, `docs/agent-guide-untranslated-strings.md`, written
from the predecessor project's experience on game data 1.3.0.4. It was rewritten in English in place
during this work, and its lasting content — the diagnosis flow, the test loop and the working rules
above, and the faction-tab next steps in `[S3]` — has since been folded into this document, so the
guide itself is gone: its 1.3.0.4 figures are superseded by `[S1]` and the report, which are measured
on this repo's own 1.4.0.1 data.

## [S3] Out of Scope

- **Code injection into the APK, and prebaked APKs with translated assets.** Both were tried and
  fail (anti-cheat kill / `IsPrebuild errorCode:151`).
- **Modifying the language packages inside the APK before the in-game update finishes.** Tencent's
  updater applies binary diffs and the diff breaks, which is why a run writes the translation after
  the update completes. It is a constraint in `AGENTS.md`.
- **Package 19's Unity prefabs, and the Card Info faction ribbon.** Rewriting the prefabs hangs the
  lobby; rewriting only the faction labels in the 15 that show them crashes the game.
  `UNITY_TEXT_PACKAGES` stays empty. The ribbon is a known limit documented in `README.md` and this
  change does not address it.

  The Card menu's faction tab is **not safely solved** through the prefabs, and this is where a
  further attempt starts:

  1. Check first whether the faction names are also in a **prime-only catalog table** of package `1`.
     If they are, the rebuild may already have translated them — verify on the phone before touching
     a prefab.
  2. If the label exists only in a package-19 prefab, do not rewrite its serialized string at a new
     length: that is what crashes. Untried are a replacement of the **same or shorter byte length,
     padded** so the serialized layout does not shift, and establishing whether the prefab reads its
     text from a table key, which would move the job to that table. Test one prefab first.
  3. If neither is safe, the tab stays a documented limit.
- **The chessplayer definition `A8BC70BB87700709` field 37.** Changing it stalls lobby loading even
  when every exact reference in packages 1 and 14 is renamed.
- **Assets neither the catalog nor the allowlists cover.** 2084 of package `1`'s prime-only assets
  and 535 of `1050016095`'s are uncovered and stay as they are; the extra-text pass only reaches
  allowlisted display assets.
- **The three catalog edits no layer carries.** `197CC5393D16E3CB`, `884E0B4581F47CF7` and
  `89C771ECFCDC7FBE` are in neither the downloaded layer nor the APK *under their own hash*. Their cards
  are in package `15` under other hashes, and since 2026-10-05 `mobile_graphics.DEVICE_REVISIONS` applies
  them there (`texture-translation.md`).
  The design phase put this number at 75, from a census of the downloaded dump alone; 72 of those were
  in the APK all along. `7B4CC5DF48336D2D` is a fourth kind — present only in the APK's package `21`,
  which this rebuild deliberately omits: the rebuild works and the game mounts it, but it draws the
  Factionless card Yixing as the game's grey placeholder. **Its size is not the reason** — a rebuild
  lays out the *downloaded* copy, 4866 assets and about 40 MB, not the APK's 511 MB over 85 211 assets —
  so a future attempt is judged on the screens it costs, not on recompression. Package `21` holds no
  other catalog edit, so that one card is the whole price; `prime-only-append.md` is the change that
  applies this texture without rebuilding it.
- **Coverage claims.** The result is the staged text tables plus the catalog's textures. The texture
  count is reported as *applied*, never as *covered*, and no run is described as a complete
  translation.
- **Verified devices.** Nothing here is confirmed on a phone by this document. The device test loop in
  `[S2]` runs after the port, one change per test, and no string or texture is claimed translated
  until the user has seen it after login.
