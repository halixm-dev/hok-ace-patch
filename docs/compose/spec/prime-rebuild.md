---
feature: prime-rebuild
status: delivered
updated: 2026-09-30
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
apply, where 323 did.** The Chessplayer names reach the layer the screen reads, which is what the
override-only path could never do. (The count was 400 before the device round below withdrew the
assets it convicts: the six extras left in the allowlist are six fewer replacements.)

Two more passes came with it. A table the in-place stager cannot fit is appended to the end of the shard
instead of being dropped (`exclude_extra_chunks` / `write_assets` / `relocate_text`), which recovers the
11 chessplayer tables the drop report recorded as permanently lost; and `extra_text` + `pb_text` +
`unity_text` translate display strings the catalog has no table for, gated on an allowlist because some
Chinese in those assets is a lookup key — an allowlist the device round below cut from fourteen assets
to four, each withdrawal recorded with the screen that condemns it. `count_translated` classifies a
rebuilt package by the texture share the entry carries, not by its mode, because one entry now holds
both kinds.

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

### Which packages are rebuilt

`package_rebuild.REBUILD_PACKAGES = ("1", "1050016095")` — the two packages measured above to keep
translatable content only in the APK. Every other package keeps the in-place path: a rebuild lays the
whole container out again, so it must be reserved for packages that gain something.

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

### Documentation

`docs/agent-guide-untranslated-strings.md` is the method this design ports, and it is currently
Indonesian — the only non-English artifact in the chain. It is rewritten in English in place.

## [S3] Out of Scope

- **Code injection into the APK, and prebaked APKs with translated assets.** Both were tried and
  fail (anti-cheat kill / `IsPrebuild errorCode:151`).
- **Package 19's Unity prefabs, and the Card Info faction ribbon.** Rewriting the prefabs hangs the
  lobby; rewriting only the faction labels in the 15 that show them crashes the game.
  `UNITY_TEXT_PACKAGES` stays empty. The ribbon is a known limit documented in `README.md` and this
  change does not address it.
- **The chessplayer definition `A8BC70BB87700709` field 37.** Changing it stalls lobby loading even
  when every exact reference in packages 1 and 14 is renamed.
- **Assets neither the catalog nor the allowlists cover.** 2084 of package `1`'s prime-only assets
  and 535 of `1050016095`'s are uncovered and stay as they are; the extra-text pass only reaches
  allowlisted display assets.
- **The three catalog edits no layer carries.** `197CC5393D16E3CB`, `884E0B4581F47CF7` and
  `89C771ECFCDC7FBE` are in neither the downloaded layer nor the APK, so no code change can apply them.
  The design phase put this number at 75, from a census of the downloaded dump alone; 72 of those were
  in the APK all along. `7B4CC5DF48336D2D` is a fourth kind — present in the APK's package `21` and
  deliberately left unapplied, because reaching it means rebuilding that package and recompressing
  511 MB for one texture, and package `21` holds no other catalog edit.
- **Coverage claims.** The result is the staged text tables plus the catalog's textures. The texture
  count is reported as *applied*, never as *covered*, and no run is described as a complete
  translation.
- **Verified devices.** Nothing here is confirmed on a phone by this document. The device loop in the
  guide's §6 runs after the port, one change per test, and no string or texture is claimed translated
  until the user has seen it after login.

## Tasks

- [x] T1: Ship Tencent's builder in `resources/qtsvfs/` and port `tools/qts_builder.py` — acceptance: `Builder(resources/qtsvfs)` loads both DLLs, `VFS_Initialize_Scripted` returns 1, and `package_node` on a real override index returns the package node bytes (covers: S2)
- [x] T2: Port `tools/package_rebuild.py` and `read_raw` — acceptance: rebuilding package `1` from `installed.apk` against the 102304 dump produces a package whose every asset reads back byte-identical and whose `QTSF_PACKAGE` node equals the override's, and a prime-only asset the transform leaves alone is absent from it (covers: S2; depends: T1)
- [x] T3: Port the relocation pass into `tools/device_extensions.py` — acceptance: a text asset too large for its chunks is relocated with its chunk count preserved, its entry's raw length and chunk size updated, and its bytes read back identical (covers: S2; depends: T2)
- [x] T4: Port the extra-text layer as `tools/pb_text.py`, `tools/unity_text.py` and `tools/extra_text.py`, and add `pypinyin` to `requirements.txt` — acceptance: `pb_text.rewrite` round-trips a known allowlisted asset and `extra_text.plan_package` selects only hashes in `SAFE_ASSETS` (covers: S2)
- [x] T5: Rewire `tools/build_device_patch.py` — acceptance: on the 102304 dump the run reports `mode: "rebuilt"` for packages `1` and `1050016095`, package `1`'s entry carries `added_from_apk: 298` and `textures: 0`, `1050016095`'s carries a `textures` equal to the number of catalog textures the rebuild changed, any texture either rebuild refuses appears in `graphics_skipped`, `text_skipped` is empty, and every file of the dump is byte-identical afterwards (covers: S2; depends: T2, T3, T4)
- [x] T6: Wire the app — acceptance: `patcher_core.build_translation` passes the APK and the bundled builder, `count_translated` splits a rebuilt package by `textures`, `--selftest` still runs and logs the fallback when no APK is given, and `app/build_exe.py` ships `resources/qtsvfs` and collects `pypinyin` (covers: S2; depends: T5)
- [x] T7: Update the documentation — acceptance: AGENTS.md's `build_patch` contract lists `mode: rebuilt`, the `textures` field, the `graphics_skipped` interaction and the new arguments; README's coverage section describes the prime layer and what rebuilding it applies; and `docs/compose/spec/text-drop-report.md`'s `[S1]` attributes the Chessplayer screen to the prime layer while keeping the drop-loop finding (covers: S2; depends: T5)
- [x] T8: Rewrite `docs/agent-guide-untranslated-strings.md` in English in place — acceptance: the file is English, its sections keep their order and their tested-hash records, and the commit notes the change (covers: S2)
- [x] T9: Record the measurement as `tools/research/prime_probe.py` — acceptance: running it from the project root reprints the `[S1]` table's numbers for packages `1` and `1050016095` without a phone, and nothing in `app/` or `tools/` imports it (covers: S1)
