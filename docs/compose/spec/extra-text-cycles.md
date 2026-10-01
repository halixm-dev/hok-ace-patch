# Device-cycle the extra-text candidates

## Report

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
| four cycles built and verified offline, ready to push | `artifacts/cycles/<hash>/out/` (gitignored) |

### What the measurement says

`extra_text_candidates.py` over the downloaded layer (game data 1.4.0.1, `artifacts/game-dump`). Counts are
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
artifacts\selftest-out` → `{"ok": true, "packages": [["1", 81], ["1", 11], ["1050016095", 1], ["15", 299],
["19", 22], ["20", 1], ["1", 4]]}`. The final `["1", 4]` is the extra-text pass reporting the four
allowlisted assets, which is what the no-APK path does instead of the rebuild. And
`tools/research/check_graphics.py` → `all checks passed`, unaffected.

**Journey log**

- The knob first went into `plan_package` only, and that was wrong for fourteen of the fifteen. The
  extra-text pass skips the packages a rebuild replaced whole — and package `1` is one — so a candidate
  enabled there alone would have been invisible. The four allowlisted assets reach package `1` through
  `rebuild_package`'s transform, which is why `make_transform` takes the same `candidates` set. The
  signature of the fix is in the numbers: package `1`'s `replacement_count` moves 392 → 393 per cycle,
  where before the fix it would not have moved at all.
- A verification run looked like a regression and was not. The first cycle build reused an output
  directory whose earlier invocation had lost its log capture (PowerShell refused the path because the
  parent did not exist, but the process still ran and staged), so the second run found the staged copy
  already holding the appended asset and — correctly — reported no `21` entry. `AGENTS.md` already says
  an output directory reused across runs can hold a package the later run does not report; the lesson
  here is just that a *failed log capture is not a failed run*, so a cycle needs a fresh directory.
- The note's list is written in eight hex digits and the packages carry sixteen. Fourteen of the fifteen
  are prefixes of assets in package `1` and one, `3F4DD9B1`, is in package `4`. Resolving them was the
  first measurement, and it is why `resolve_candidates` matches on a prefix and refuses an ambiguous one
  rather than requiring the full hash from whoever is running the cycle.
- The census tool reports a candidate's `rewrites` (every field the pass would touch, duplicates
  included) as well as its `official` (distinct strings that have a translation). The two differ — a
  label repeated across rows counts once for coverage and several times for rewriting — and it is the
  distinct count that says what a cycle changes on a screen.
- `3F4DD9B1D383FD83` is **reachable**: `plan_package` selects it, so package `4` does not have the
  multi-shard problem the note's other package-4 entries implied. It stays out of the queue anyway, for
  the reason the note gives — package `4` writes through `write_assets`, which does not read its own
  write back — and the measurement is recorded so the next attempt does not re-derive it.

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
cycle starts. The cycles' builds are pre-built under `artifacts/cycles/<hash>/out/`; each one is a
complete patch (the six packages a normal run stages) plus the one asset, so pushing it *is* the cycle.

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

- **Adding any candidate to `SAFE_ASSETS`.** Nothing here has been on a phone. The knob exists so the
  verdict can be produced; the allowlist moves only after it is.
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

## Tasks

- [x] T1: Resolve the note's fifteen short hashes against a dump and measure each one — acceptance: every hash resolves to exactly one asset, 14 in package `1` and `3F4DD9B1` in package `4`, and each asset's distinct/field/official counts are recorded (covers: S2)
- [x] T2: Add `CANDIDATE_ASSETS` and `resolve_candidates` — acceptance: every 8-digit prefix in the queue resolves uniquely, an ambiguous or unknown token raises `UnknownCandidate` with the queue named, and a normal run plans exactly `SAFE_ASSETS` (covers: S1, S2)
- [x] T3: Thread the enablement through both paths — acceptance: with `candidates={h}` package `1`'s rebuild reports 393 replacements against a 392 baseline, and with no candidates the summary is byte-for-byte the pre-change run's (covers: S1, S2)
- [x] T4: Wire the CLI and the summary — acceptance: `--cycle-asset <hash>` enables it and logs what it is, `--cycle-asset` with an unknown hash exits with the queue printed, and `device_patch_summary.json` carries `cycle_assets` (covers: S2)
- [x] T5: Record the census as `tools/research/extra_text_candidates.py` — acceptance: it reprints the report's table from a dump, ends with the plan-without-a-cycle check, and nothing in `app/` or `tools/` imports it (covers: S2)
- [x] T6: Verify offline, per candidate — acceptance: four cycle runs differ from the baseline in exactly one content asset each (`1D13F7315D89BAC3` and `AF1FB540A2B8CB52` are the builder's path-carrying nodes), that asset is the one the cycle named, and its strings read back English (covers: S2)
- [x] T7: Keep the app path working — acceptance: `app/hok_patcher.py --selftest` reports `ok: true`, `check_graphics.py` reports `all checks passed`, and `patcher_core.build_translation` is unchanged (covers: S2)
- [x] T8: Build the four cycles and document the loop — acceptance: `artifacts/cycles/<hash>/out/` holds a complete patch per candidate, and `[S2]`'s loop names the backup, the cache-label pre-flight and the log to read (covers: S2)
