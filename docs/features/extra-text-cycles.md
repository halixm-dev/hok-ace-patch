# Device-cycle the extra-text candidates

## Report

**2026-10-21: `F79FB1A213A9DA90` cleared, the first candidate on `SAFE_ASSETS` (official-lineups ticket
05).** Control and cycle builds, English then Indonesian, on a Xiaomi M2007J3SG with data 1.6.0.1. With the
bin rewritten and resealed, the Official recommendation reads translated, and the detail, *Use*, copy and
import, and a match's end behave as on the control, with no QTS-failure popup. A resealed config bin loads,
which fits the stale checksum being what dropped the withdrawn bins; none of those has been resealed and
re-cycled, so that stays a lead. The other two lineup bins
stay candidates. Record: `docs/features/official-lineups.md`; evidence: lab notebook, 2026-10-21.

**2026-10-21: the three lineup bins join the queue, resealed (official-lineups ticket 04).**
`F79FB1A213A9DA90` (`ResSeasonAILineupDataBin`, Lineup → Official recommendation), `6A2B886E5DCF22DC`
(`ResRecommendLineup`) and `C0C56FEFDCA0EA5D` (`ResHeroStrategyDataBin`) are on `CANDIDATE_ASSETS`, ahead
of the fifteen. Their text sits inside share codes (base64 of raw deflate of `OSProto.OneLineup`), which
`pb_text` cannot see, and each bin stores a checksum over its rows. Both paths now rewrite an enabled
asset through one `extra_text.rewrite_config`; for a lineup bin it calls `lineup_codes.rewrite_bin`. That
decodes each code, translates its text fields in place with the code's own field order kept, re-deflates
at zlib's default, re-base64s, translates the row text fields, rebuilds the row and reseals fields 1 and 4
(`config_bin.reseal`, the shipping port of `tools/research/config_bin_checksum.py`, which now imports it).
Resource tokens are expanded per string before the seal. A code, row or bin with nothing to translate
keeps its bytes, so the pass is idempotent. A bin, row or code whose framing would not re-serialize
identically, a code that does not decode back, or a bin that does not pass its own checksum is refused. Without `--cycle-asset` the bins are not touched (ADR 0004);
`SAFE_ASSETS` stays empty, and ADR 0005 holds for every normal run. Whether the game loads a resealed
bin is ticket 05's device cycle.

| asset | distinct Chinese strings (fields) | translated, English and Indonesian |
|---|---|---|
| `F79FB1A213A9DA90` | 118 (264), both layers | 118 |
| `6A2B886E5DCF22DC` | 94 (196), both layers | 94 |
| `C0C56FEFDCA0EA5D` | 36 (45) override, 35 (76) prime | all |

Offline builds, game data 1.6.0.1 (session `20261017-224744`, its cached `installed.apk`), under
`D:\scratch\hok-lineups\`: `en-control`, `en-cycle` (`--cycle-asset F79FB1A213A9DA90`), `id-control`,
`id-cycle`, each with `out\` and `work\`. In both languages the cycle build differs from its control in
package `1`'s `1.db` and `1_0.db` and in the summary (`cycle_assets: ["F79FB1A213A9DA90"]`, one more
`1` `extra-text` entry), and nowhere else. Read through `QtsPackage` + `read_raw`, package `1` has 720 entries
in both and **one** asset differs, the candidate. The control's copy is byte-identical to the game's. The
cycle's copy (37,266 → 39,582 B English, 40,040 B Indonesian) passes `config_bin.is_sealed`, and its old
field 4 would not. Its index (field 3) is kept. All 28 codes decode by the game's steps. All 264 text fields
read back as their targets (`Three Kingdoms Deploy Build`; Indonesian `Build Deploy Three Kingdoms`), and
the other 3,151 fields of the codes and rows are byte-identical, in their stored order. No Chinese is
left, and the pass run on its own output changes nothing. `tools/research/extra_text_candidates.py`, which
now loads the catalog as a run does (terminology and supplement) and measures a lineup bin through
`lineup_codes`, gives the table above and still ends `without a cycle the pass plans 0 assets`.
`tools/research/check_lineup_cycle.py` reproduces all of this. It also checks the other two bins
(not built): in both layers and both languages they are sealed, every text field reads back as its target,
every other field is byte-identical and no Chinese is left. All three bins sit in both layers on 1.6.0.1,
so no lineup bin has yet reached the override layer by append (`transform.config`); that path is the one
every candidate uses, untested here for these bins.

**2026-10-17: skip scans without eligible assets.** Script and config planners check the package
index, skip set and supported codecs before building a chunk-slot map. Config planning still requires
`SAFE_ASSETS` or that run's enabled candidates. Eligible assets follow the existing read/translate/write
path; the script pass still runs in excluded config packages. Performance and output-equivalence
evidence are recorded in the lab notebook's offline staging performance sections.

The extra-text allowlist (`tools/extra_text.py` → `SAFE_ASSETS`) is device-gated: an asset joins it only
after one cycle has put it on a phone and looked at the screen it feeds. The note beside it names
fifteen further assets that have never been cycled, and until now a cycle meant editing the allowlist in
the working tree, building, and putting the edit back — with nothing in the repo recording what each of
the fifteen is worth.

This change makes a cycle one variable by construction and records the measurement the order comes from.

| what landed | where |
|---|---|
| the measured queue of the fifteen, full hashes, with each one's payoff | `tools/extra_text.py` → `CANDIDATE_ASSETS` |
| a cycle's enablement resolved from a hash prefix, refusing anything not on that queue | `tools/extra_text.py` → `resolve_candidates`, `UnknownCandidate` |
| the enablement reaching **both** paths that can translate an asset | `extra_text.plan_package`, `package_rebuild.make_transform` |
| the CLI that builds one cycle | `tools/build_device_patch.py --cycle-asset`, `build_patch(cycle_assets=...)` |
| a staged build saying which cycle produced it | `device_patch_summary.json` → `cycle_assets` |
| the census a cycle starts from, and the check that the knob is inert without one | `tools/research/extra_text_candidates.py` |
| four cycles originally built and verified offline; obsolete outputs removed 2026-10-03 | `artifacts/cycles/<hash>/out/` (gitignored) |

**2026-10-05: the allowlist is empty.** All four assets it held were withdrawn after device cycles on the
Indonesian build (1.4.0.2). Rewriting the rule pages `B5D856BFDF22400D`, which is `ResHelpSystemCfgDataBin`,
removed the Announcement screen's back arrow and title. Rewriting the nicknames, display-text table and
compliments (`2D1113B0AD51A562`, `A1987F488164E53A`, `1C8F7FFF7BDEF14D`) made every match end in the client's
QTS-failure popup, `/未翻译UI/QTSFailureTips`: 2 of 2 matches with them, none without. Their 2026-10-01
verdicts had watched the replay crash only. The three were not bisected, so each may come back through this
queue. The pass now also carries `SCRIPT_LABELS`, an exact literal in a Lua UI script (the Effect Card
filter's `通用`), which is not a config bin, was verified on its screen and across a match, and reaches the
phone through the append because the script is prime-only. `SCRIPT_EDITS` carries exact literal edits
to a Lua script's own formatting or behaviour under the same once-only rule: the rank title's `"%s%s"` in
`6CB505C6553141B4`, which joined "Supreme Star" and "III" with no space, and the line-break flag reset at
the top of `UIPrefabClass:Create` (`3482BF89614B5ABB`, `.scratch/latin-line-breaks/`). Symptoms and dates are beside the allowlist in
`tools/extra_text.py`; the evidence is in `docs/lab-notebook.md`'s 2026-10-05 section.

**Those four staged builds are bound to game data 1.4.0.1** — the layer they were staged from — and the
phone has since updated to 1.4.0.2, so they are no longer pushable as they stand. See the journey log's
last entry: a staged package is a revision of one layer, and the phone's version has to be checked against
the dump's before a hand-driven push.

### What the measurement says

`extra_text_candidates.py` over the override layer (game data 1.4.0.1, `artifacts/game-dump`). Counts are
distinct Chinese strings the asset holds, and how many of those `catalog.unique` has an official English
for — the share a cycle would translate.

| asset | package | what it is | distinct | official |
|---|---|---|---|---|
| `63922EF4D4C86526` | 1 | Transmog / Treasure Hunt / Limited Time — a 90-byte table | 3 | **3** |
| `4CEF98BEC79CB48C` | 1 | Tier / Hero Faction / Keyword / Wanxiang Quiz | 12 | **4** |
| `7E3F57D727FA8625` | 1 | Props | 1 | **1** |
| `3914DBBFECD1E54D` | 1 | Highlight Expression | 1 | **1** |
| `41974B124E0053E0` | 1 | the newbie unlock-reward list | 25 | 15 |
| `7B40D34D9DF271FF`, `1BAEBF0F2F2454FD`, `EAF9962143676693` | 1 | damage-type tables; Damage / Invincible / Magic Damage Can Crit among 50-odd designer shorthand strings | 49-53 | 3 each |
| `A07BC11BA94A5969` | 1 | no screen identified | 10 | 5 |
| `14DEEB2E14F20E3C` | 1 | two labels in a 115 KB asset | 3 | 2 |
| `8B5C239421E23186` | 1 | guide **step names** (`S1 lineup - use button`) — logic, not labels | 283 | 9 |
| `9E141D556DA884E7` | 1 | guide triggers — the same class | 596 | 23 |
| `C11D0D1498204926` | 1 | buff definitions, mostly designer shorthand | 587 | 35 |
| `87C2793FEEDCA60D` | 1 | nickname parts | 678 | 20 |
| `3F4DD9B1D383FD83` | **4** | 2 strings, and package 4 is the one the note withdrew | 2 | 1 |

So the note's fifteen are not fifteen equal opportunities. Four are display-label tables the catalog
mostly or entirely covers; the other eleven are step, buff, nickname and damage **identifiers** that the
catalog reaches 1.5-9% of, where a cycle buys a handful of strings and risks a screen the note already
lists a synonym of. The whole set is worth about 130 strings, and the label tables are 9 of them — which
is why the order in `CANDIDATE_ASSETS` is the four labels first and the rest only after a cycle says the
class is safe.

Two of those four label tables carry a measured screen fact beside their hash since 2026-10-02, and it
changes what a cycle on them can buy: `3914DBBFECD1E54D` **cannot be cycled at all** — its one key is
referenced by a single row, a draw type windowed for a month that ended a year before this build, so no
live screen draws it — while `63922EF4D4C86526` is referenced with no date window and is cycleable. Both
are now dropped from a normal run's plan, because the text pass stages the catalog's tables and nothing
else (`prime-only-append.md`, the catalog gate): a diagnostic cycle enables it with `--cycle-asset`; promotion
to `extra_text.SAFE_ASSETS` still requires a watched successful device verdict.

Placeholder normalisation was measured as a way to reach more of them and added **nothing**: replacing
every `{...}`/`%d` form and dropping colour tags before looking a string up matched no additional string
in any candidate, so the residue is not a lookup-shape problem. The catalog genuinely does not carry
these strings.

### Verification

```
.venv\Scripts\python.exe tools\research\extra_text_candidates.py --game artifacts\game-dump
```
Prints the table above, and ends with the mechanism's own invariant — `without a cycle the pass plans 4
assets, all of them from the allowlist` (the four `SAFE_ASSETS`, on this dump). Nothing else is planned
unless a cycle names it.

```
.venv\Scripts\python.exe tools\build_device_patch.py --runtime resources\runtime --game artifacts\game-dump ^
    --catalog resources\catalog --work <w> --output <o> ^
    --apk "dist\HOK ACE Patcher Data\installed.apk" --builder resources\qtsvfs
```
Baseline, into a fresh output directory: `cycle_assets: []`, six packages —
`1` rebuilt, `1050016095` rebuilt, `15`/`19`/`20` graphics, `21` added-from-apk — and `text_skipped`,
`graphics_skipped` and `append_skipped` all empty. That is the run the ledger records, reproduced.

The same command with `--cycle-asset <hash>`, once per candidate, gave:

| cycle | `cycle_assets` | package 1 | everything else |
|---|---|---|---|
| `63922EF4D4C86526` | `["63922EF4D4C86526"]` | rebuilt, **393** | identical to the baseline |
| `4CEF98BEC79CB48C` | `["4CEF98BEC79CB48C"]` | rebuilt, **393** | identical |
| `7E3F57D727FA8625` | `["7E3F57D727FA8625"]` | rebuilt, **393** | identical |
| `3914DBBFECD1E54D` | `["3914DBBFECD1E54D"]` | rebuilt, **393** | identical |

392 is the baseline, so each cycle adds exactly the one asset it names. At asset level, reading every
entry of the staged package 1 through `QtsPackage` + `read_raw` and diffing against the baseline:
**one** content asset differs, and it is always the candidate. The cycle's strings then read back
English and none of the candidate's strings are left Chinese — these four are pure label tables, so a
cycle on one of them is a complete change:

| cycle | strings that became English |
|---|---|
| `63922EF4D4C86526` | `夺宝` → Treasure Hunt, `幻化` → Transmog, `限时` → Limited Time |
| `4CEF98BEC79CB48C` | `万象竞答` → Wanxiang Quiz, `关键词` → Keyword, `品阶` → Tier, `英雄阵营` → Hero Faction |
| `7E3F57D727FA8625` | `道具` → Props |
| `3914DBBFECD1E54D` | `高光表情` → Highlight Expression |

Two further assets differ in every cycle — `1D13F7315D89BAC3` and `AF1FB540A2B8CB52` — and both are
Tencent's builder writing its own **build path** into the package: `AF1FB540A2B8CB52` holds
`...\work\rebuild-1\src\BatchAssets\<hash>.assets` verbatim, so no two builds in different directories
agree there. They are named as `BUILDER_BOOKKEEPING` in the verification script.

The app path still runs: `.venv\Scripts\python.exe app\hok_patcher.py --selftest artifacts\game-dump
artifacts\selftest-out` → `{"ok": true, "packages": [["1", 79], ["1", 11], ["1050016095", 1], ["15", 299],
["19", 22], ["20", 1], ["1", 4]]}`. The final `["1", 4]` is the extra-text pass reporting the four
allowlisted assets, which is what the no-APK path does instead of the rebuild; `79` was `81` until the text
pass was gated to the catalog's tables (`prime-only-append.md`, the catalog gate). And
`tools/research/check_graphics.py` → `all checks passed`, unaffected.

**Journey log**

- Wiring the knob into `plan_package` alone: invisible for fourteen of the fifteen, which sat in a rebuilt package, so `make_transform` takes the same set. Lab notebook, 2026-10-01.
- A verification run that looked like a regression: a reused output directory behind a failed log capture; a cycle needs a fresh directory. Lab notebook, 2026-10-01.
- Resolving the note's eight-digit hashes: they are prefixes, so `resolve_candidates` matches a prefix and refuses an ambiguous one. Lab notebook, 2026-10-01.
- Measuring a candidate by `rewrites` or by `official`: the distinct `official` count is what a cycle changes on screen. Lab notebook, 2026-10-01.
- Whether `3F4DD9B1D383FD83` is reachable: it is, and stays out of the queue because package `4`'s write is not read back. Lab notebook, 2026-10-01.
- The first real push of a cycle, staged from 1.4.0.1 onto a 1.4.0.2 phone: no verdict, the stale layer stalled loading; versions are now compared before a push. Lab notebook, 2026-10-02.

## [S1] Problem

Three things are true at once, and together they blocked the next translation step:

1. **The pass's reach is gated on device cycles, and cycles are expensive.** A cycle costs the user a
   cleared data directory, a ~2.7 GB re-download, a login, and a walk through the screens. Fifteen
   assets are named as untried and none of them had a measured value, so the order could only be
   guessed at.
2. **Nothing could turn one asset on for one run.** The only mechanism was editing `SAFE_ASSETS` in the
   working tree, which is the shipped allowlist: an edit that is easy to leave in, and one that leaves no
   record of which build a verdict belongs to.
3. **A candidate is not necessarily reachable through the pass that owns it.** Package `1` is rebuilt, and
   `extend_text` skips rebuilt packages, so the four allowlisted assets already reach package `1` through
   `make_transform` instead. A cycle that did not know this would test nothing.

## [S2] Design

**The queue is code, not a note.** `CANDIDATE_ASSETS` holds the fifteen resolved to full hashes, in the
order the cycles should run, each with what it is and its measured payoff. `SAFE_ASSETS` stays exactly the
four assets a cycle has cleared, so the rule in `AGENTS.md` is unchanged: the allowlist grows on a
verdict, never on a measurement.

**`resolve_candidates` is the only way in.** It takes comma-separated hexadecimal prefixes, requires each
to match exactly one candidate, and raises `UnknownCandidate` otherwise; `--cycle-asset` turns that into
an argparse error that prints the queue. A cycle therefore cannot enable something that was never
measured, which is the failure mode an allowlist edit invites.

**The enablement has to reach every path that translates an asset.** It is threaded to `plan_package`
(the in-place and relocated paths) *and* to `make_transform` (the rebuilt path), and `build_patch` hands
the same set to both. This is the whole reason the change touches `package_rebuild` at all; a candidate
that reaches one path and not the other is a silent no-op for whichever packages the other path owns.

**One candidate per run.** The pass takes a set because the mechanism is the same either way, but a
cycle enables one asset: the previous bisect's lesson, recorded in `prime-rebuild.md`, is that each cycle
has to start from the configuration last known good for its verdict to be usable on its own.

**The run says which cycle it is.** `device_patch_summary.json` gains `cycle_assets`, a list of the
hashes the run enabled (empty on a normal run), and `main` logs each one with its description before the
build starts. A staged build that reaches a phone therefore names its own variable, which is what makes a
verdict's evidence self-describing.

**The census is the keeper.** `tools/research/extra_text_candidates.py` reprints the table above against
any dump, and ends by planning a run with no candidates and checking that the result is the allowlist —
the invariant that says the knob is inert on a normal build. It is off the runtime path, like the other
`tools/research/` scripts.

### The device test loop for a cycle

One candidate per cycle, and the verdict written beside the hash in `CANDIDATE_ASSETS` before the next
cycle starts. Build a fresh cycle under a new work/output directory from the phone's own
game-data version. The old `artifacts/cycles/<hash>/out/` builds were staged from 1.4.0.1 and their
obsolete generated outputs were removed on 2026-10-03. A cycle is a complete patch plus the one asset;
the version-checking push tool can send only the package that differs.

1. **Prerequisites.** The game's data must be fully downloaded (open the game to the login screen once
   after any update), and nothing may be installed that the patcher did not put there. The account has to
   have the screen the label appears on — a newbie reward list is invisible to a levelled account.
2. **Back up `packages` and `Watchdog`** so the cycle can be rolled back:
   `adb exec-out run-as com.tencent.tmgp.osgame tar -cf - -C files/QtsVFSCache packages Watchdog > backup.tar`.
3. **Run the patcher once (`run.bat`) before a hand-driven cycle.** Its `apk` step is what rewrites the
   cached `installed.apk`'s launcher label; without it, step 6 below puts the **Chinese name back on the
   launcher**. Check with `set_label(apk_manifest(cache), APP_NAME) != apk_manifest(cache)`
   (`dist\HOK ACE Patcher Data\installed.apk` answers `False` as of this writing, `access.apk` `True`).
4. **Push**, which needs the debuggable access APK for `run-as` — and the game cannot run under it:
   `adb install -r "dist\HOK ACE Patcher Data\access.apk"`, then per package directory
   `adb push <out>\<id>\*.db /data/local/tmp/hokace/<id>/`, `chmod -R 755`, and
   `run-as com.tencent.tmgp.osgame sh -c 'cp /data/local/tmp/hokace/<id>/* files/QtsVFSCache/packages/<id>/'`.
   Then `run-as ... rm -rf files/QtsVFSCache/Watchdog/*` and `rm -rf /data/local/tmp/hokace`. This is
   `patcher_core.push_translation`'s sequence.
5. **Reinstall the game APK**: `adb install -r "dist\HOK ACE Patcher Data\installed.apk"`, and confirm the
   launcher still says `Honor of Kings: ACE`.
6. **Launch, read the logs, and find the string.** `adb logcat` for QtsVFS errors,
   `files/QtsVFSCache/QtsVFS.log` and
   `/storage/emulated/0/Android/data/com.tencent.tmgp.osgame/files/bqLog/ccs_log/normal1.log` for the
   game's own repair (`errorCode:361` is the failure mode a rebuilt container invites), then log in —
   *Scan to login* — and look for the Chinese string the cycle should have replaced.
7. **Verdict.** The cycle passes if the label reads English and no screen the cycle could reach changed
   behaviour; it fails with the screen named, the way every withdrawn hash is recorded. A pass moves the
   hash into `SAFE_ASSETS` with its date; a failure stays in `CANDIDATE_ASSETS` with its symptom. Neither
   is a code change to any other pass.

## [S3] Out of Scope

- **Adding any candidate to `SAFE_ASSETS`.** Nothing here had been on a phone. The knob exists so the
  verdict can be produced; the allowlist moves only after it is (the first did on 2026-10-21, in
  `official-lineups.md`).
- **The package-4 candidate** `3F4DD9B1D383FD83`. Reachable, and deliberately not in the queue while
  package `4` writes through a path that does not verify its own write.
- **The eleven non-label candidates.** Measured and deprioritised, not withdrawn: each needs a cycle to
  enter the allowlist, and at 1.5-9% catalog coverage the cycle is worth a handful of strings. The damage
  tables are the borderline case and are in the queue behind the labels.
- **The GUI.** `--cycle-asset` is on the offline CLI on purpose: a device cycle is hand-driven, and an
  untested enablement must not be reachable from the app a normal user runs.
- **Package `15`'s card bands.** The bigger remaining gap — 1695 card-shaped textures the catalog does not
  cover, whose bottom band carries a type word or a card name (`000847DC117D3C4E` shows `技能` beside an
  already-English `SKILL`; `0143B73B5071A289` a `TALENT` card with `钻石狂澜`). The English exists — in
  `catalog.unique`, and in the art itself — but it is *drawn*, so this needs a renderer that reproduces
  the band's font, colour and position, not an asset edit. Nothing in this repo draws text yet.
- **The `extra_text` coverage of assets the catalog does not carry.** Placeholder normalisation was
  measured and adds nothing (see the report), so the pass's reach is the catalog's, not an artefact of
  how it looks a string up.
