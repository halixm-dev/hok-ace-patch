# HOK ACE Language Patcher

Windows GUI that installs the English or Indonesian translation into 王者万象棋: the mobile edition (`com.tencent.tmgp.osgame`) on an Android phone over USB, without root, or the PC edition (`WXQ.exe`) on the same computer. The Android app in `android/` runs the phone pipeline on the phone through Shizuku.

Python **3.12 only**. `resources/runtime/` is 3.12 bytecode and will not load on any other version.

## Commands

Run from the project root:

```bat
setup.bat      :: .venv + requirements.txt  (fallback: set PYTHON=C:\path\to\python3.12.exe first)
build.bat      :: -> dist\HOK ACE Language Patcher.exe
run.bat        :: run from source
```

Headless runtime check (needs a dumped game directory):

```bat
"dist\HOK ACE Language Patcher.exe" --selftest <game-dir> <out-dir>
```

Without a dump, `--smoketest <out-dir>` checks that the freeze carries every module and codec (the Windows exe workflow runs it on each pull request).

The PC edition's headless check stages both languages against a copy of the game and writes nothing to it; `tools\research\check_pc_install.py --game <copy> --work <dir>` drives the whole install, switch and restore sequence on a copy:

```bat
"dist\HOK ACE Language Patcher.exe" --pc-selftest <game-copy> <out-dir>
```

No test suite. Verify changes with `run.bat` or `--selftest`. The texture codec has its own offline check, which needs neither a device nor a game dump:

```bat
.venv\Scripts\python.exe tools\research\check_graphics.py [--game <game-dir>]
```

The whole pipeline also runs offline against a dumped game directory. Add the cached APK to include prime-only content. The builder is optional and needed only when `REBUILD_PACKAGES` names a package:

```bat
.venv\Scripts\python.exe tools\build_device_patch.py --runtime resources\runtime --game <game-dir> ^
    --catalog resources\catalog --work <work-dir> --output <out-dir> ^
    --apk <path>\installed.apk
```

After changing a user-facing string in either patcher, run `tools\research\check_ui_strings.py`.

After moving or renaming a doc, run `tools\research\check_references.py` and `tools\research\check_staging_contract.py`.

## Architecture

| Path | Role |
|---|---|
| `app/` | GUI (`hok_patcher.py`), device workflow (`patcher_core.py`, with its ADB client `adb_device.py`, its pristine layer `pristine_layer.py`, APK preparation `apk_preparation.py`, game-data pull `game_data_pull.py` and translation payload `translation_payload.py` (all four mixed into `Patcher`), and the interface strings and `PatchError` in `ui_strings.py`, all re-exported), APK rewrite + v2 signing (`apk_tools.py`), PC edition workflow (`pc_edition.py`: finding the game, the process guard, receipts, state, the `--pc-job` child) |
| `tools/` | Pipeline: `languages`, `terminology`, staging (`build_device_patch`), rebuild (`package_rebuild`, `qts_builder`), append (`qts_insert`), textures (`device_extensions`, `sprite_table`, `mobile_graphics`, its block scan `block_scan`), extra text (`extra_text`, `pb_text`, `unity_text`; lineup bins `lineup_codes`, `config_bin`), relocation (`qts_relocate`), PC edition (`engine_hooks`: every hook into the runtime; `pc_catalog`: the per-install catalog; `bc7_mode6`: the BC7 encoder for its atlas ports) |
| `tools/research/` | Probes and offline checks, run by hand |
| `rust/stale-blocks-rs/` | The block scan before every atlas re-encode (`block_scan.stale_blocks`) in Rust (PyO3), a rust-anything port switched on by the marked block in `tools/block_scan/__init__.py`; built by `app/build_exe.py` into `build/native/stale_blocks_rs/` |
| `rust/outside-ranges-rs/`, `rust/mean-abs-diff-rs/` | `check_graphics.py`'s byte comparisons (`tools/research/pixel_diff.outside_ranges` and `.mean_abs_diff`) in Rust (PyO3), one rust-anything port each, switched on by its marked block in `tools/research/pixel_diff/__init__.py`; each crate's recording fingerprints the file with the other's block in it, so after enabling or disabling one, re-record both with `--inputs <crate>/test-inputs.jsonl`; research only, built by hand (`rust-anything build`), the Python runs where it is not built |
| `rust/hokace/`, `rust/MAP.md` | The whole-repo Rust migration: its Cargo workspace (`core`), plan and unit states (`MAP.md`), decisions (`DECISIONS.md`), handoff, pipeline baselines (`app-cases/`, checked by `harness/pipeline_case.py`) and generators; Python stays the reference until the lift |
| `crates/hok_bc7/` | The PC edition's BC7 modes 6, 5, 4 and 7 and the search over them in Rust (PyO3), a bit-exact port of `bc7_mode6`'s Python modes; built by `app/build_exe.py` into `build/native/hok_bc7.pyd` |
| `resources/runtime/` | Compiled `wxq_patch` translation runtime (from the PC patcher) |
| `resources/catalog/` | English catalog (`catalog.json.gz`) plus the English catalog edits (`.blocks` / `.assets`) |
| `resources/catalog_id/` | Indonesian catalog, plus only the catalog edits it re-draws (`<HASH>.blocks` + `previews/<HASH>.png`); every other payload is read from `catalog/` |
| `resources/sprites/` | This repo's own art for regioned atlases (`<HASH>/labels/` and `<HASH>/restore/`) and for label textures (`<HASH>/labels/<language>/`) |
| `resources/ui/`, `resources/fonts/` | The shared design's theme tokens, strings and fonts, read by both patchers (`DESIGN.md`) |
| `resources/qtsvfs/` | Tencent's own package builder (`QtsVFS.dll` + `QtskDB.dll` + VC runtimes), driven by ctypes; kept in the repo for `--builder` runs from source, not shipped |

Flow: two cores. For the phone, `patcher_core` drives the seven device steps and calls `build_patch`; for the PC edition, `pc_edition` builds the per-install catalog (`pc_catalog`) and runs the runtime engine (`wxq_patch.adaptive.run`) in a `--pc-job` child process. The GUI talks only to these two.

`sys.path` is set in `patcher_core.py`: `tools/` is inserted for source runs; `resources/runtime/` is **appended** so the project stdlib wins.

### Staging contract

The staging summary contract (payload fields, `mode` values, skipped lists, pass order, APK/builder gating) is the `build_patch` docstring in `tools/build_device_patch.py`.
Read it before editing the pipeline, and change it in the same edit as the code; `tools/research/check_staging_contract.py` checks it stays there.

## Code style

Module docstring, `from __future__ import annotations`, type hints, `pathlib.Path`. Constants `UPPER_CASE` at module level. Private helpers `_name`. User-facing failures raise `PatchError`; in `patcher_core` it takes keys from `resources/ui/strings.json`, never text.

## Constraints

**Install and delivery**

- **Install path**: re-sign, install the access APK, write the override layer, reinstall the normal APK. The access APK never stays installed, nor is it cached as the normal APK. ([ADR 0001](docs/adr/0001-install-through-a-temporary-access-apk.md)) The Root shell provider, in flight, writes the override layer directly as uid 0 and installs no APK. ([ADR 0007](docs/adr/0007-on-a-rooted-phone-write-the-override-layer-directly.md), [android-shell-providers](docs/features/android-shell-providers.md))
- **Update timing**: write the translation only after the in-game update finishes. ([ADR 0002](docs/adr/0002-write-the-translation-after-the-in-game-update.md))
- **Normal APK**: the game's own file with only `AndroidManifest.xml` rewritten (debug flag, launcher name `APP_NAME`); any further edit needs a device cycle. The rename must never fail a run. ([standalone-patcher-app](docs/features/standalone-patcher-app.md), [device-cycle](docs/runbooks/device-cycle.md))
- **Pristine delta**: after a verified install each patcher keeps the pristine bytes it overwrote (`tools/pristine_delta.py`), and a later run rebuilds the pristine layer from it before building. A run that can neither rebuild nor read the layer as pristine refuses before any game file is written. The delta always points at pristine; the two patchers never share one. ([language-switch](docs/features/language-switch.md))
- **Mixed packages**: the Android patcher restores carried-over modified assets into a copy from the delta's kept bodies, and every package it cannot take falls back to Re-download. ([ADR 0008](docs/adr/0008-restore-a-carried-over-translated-asset.md), [asset-restore](docs/features/asset-restore.md))
- **Login**: re-signing breaks direct WeChat/QQ login; users log in via *Scan to login*, as expected. A Root run installs no APK, so a game app that was never re-signed keeps direct login (user's report, 2026-11-19).
- **Working data** (~8 GB) goes to the user-chosen folder, never into this repo. `build/`, `dist/`, `.venv/` are generated and disposable.

**Coverage and gating**

- **Coverage** is the staged text tables, the catalog edits, 37 repo-drawn atlas labels (`mobile_graphics.ATLAS_LABELS`: two on the Career atlas, three for the Super Weekend start button (on the lobby atlas START GAME / MULAI GAME, drawn per language, and SUPER WEEKEND; SUPER WEEKEND again on the ready atlas), the 32 Secret Technique card titles in `LABEL_ATLASES`; all but the lobby's START GAME English in both languages), one repo-drawn label texture drawn per language (`mobile_graphics.LABEL_TEXTURES`: the same button's GameCenter twin, START GAME / MULAI GAME), one Lua label (`extra_text.SCRIPT_LABELS`), twenty-two Lua edits (`extra_text.SCRIPT_EDITS`: the rank title's spacing, the line-break flag turned off, the "Exit now" label on the two match-end ranking toasts, across the faction tab item and its bar, one shared size for the Card screen's faction tab names that fits every tab, and in the lobby, one size for the bottom-right button names and the Menu and top-bar names kept clear of their icons, and one size for the Menu panel's entry names, on the Chessplayer page, wider tabs for its two names and the sort toggle clear of the back title, the Career tabs and stat labels, the Activate Privilege icon, the Encyclopedia mode tabs and Talent Card series heading, the Chessplayer detail panel, and in the room, the Lineup and Settings names kept clear of their icons and one size for the friend panel's tab names and the Super Weekend perks joined with an English comma, and on the match-end ranking screen, tab cells wide enough for their names and the All Things Moment tip's server-sent highlight title translated from `extra_text.SCRIPT_TRANSLATIONS`, or dropped when unknown) and two config bins (`extra_text.SAFE_ASSETS`, the Official recommendation lineups and the Super Weekend room perks; mobile edition only). Never call it a complete translation; state the texture count as *applied*, never *covered*. ([translation-progress](docs/translation-progress.md))
- **Catalog only**: the text pass stages the catalog's tables and nothing else (`_drop_uncatalogued_tables`). A mode's copy of catalog tables joins them only once measured onto `catalog_updates.MODE_TABLE_COPIES` (ACE Quick Match's two card tables), admitted as the catalog loads. ([prime-only-append](docs/features/prime-only-append.md))
- **Allowlist**: a config bin is translated only once a device cycle clears it onto `extra_text.SAFE_ASSETS` (two today, the Official recommendation lineup bin and the Super Weekend room perks bin). `--cycle-asset` enables one `CANDIDATE_ASSETS` hash per run; `tools/extra_text.py` records each withdrawn hash with its failing screen. ([ADR 0004](docs/adr/0004-the-allowlist-is-the-only-gate-for-config-bins.md), [extra-text-cycles](docs/features/extra-text-cycles.md))
- **Uncatalogued config bins** are never rewritten, not even re-pointed at identical length. ([ADR 0005](docs/adr/0005-never-rewrite-an-uncatalogued-config-bin.md))
- **Card dictionaries** keep their chunk size and gain chunks only with keys in `device_extensions.NATIVE_CHUNK_KEYS`; unknown layouts are refused and reported. No text table gains rows past its existing chunks. ([prime-only-append](docs/features/prime-only-append.md))
- **Both data layers**: check the override layer and the prime layer before calling an asset unreachable. ([diagnose-untranslated](docs/runbooks/diagnose-untranslated.md))
- **Aliases**: an entry joins `mobile_graphics.DEVICE_REVISIONS` only on a measured match, never by guess. ([texture-translation](docs/features/texture-translation.md))

**Pipeline**

- **Append, not rebuild**: `REBUILD_PACKAGES` stays empty (package `21` in particular); prime-only content reaches the override layer by append. ([ADR 0003](docs/adr/0003-reach-prime-only-content-by-append-not-rebuild.md))
- **Append pass** rewrites nothing it did not add, keeps the read-back through `QtsPackage`, stays idempotent, and reports a full B-tree leaf (`TreeFull`) in `append_skipped` instead of failing the run. A new asset kind it may carry goes into `package_rebuild.make_transform`. ([prime-only-append](docs/features/prime-only-append.md))
- **APK gating**: without the APK a run still succeeds and leaves prime-only content Chinese; check the log for the `added from the APK` lines. ([prime-rebuild](docs/features/prime-rebuild.md))
- **Reading chunks**: `qts_relocate.read_raw` follows each chunk's own framing, not the entry's compression id. A rebuild omits entries with no bytes (`entries_without_bytes`) but aborts on bytes that will not decode. ([prime-rebuild](docs/features/prime-rebuild.md))
- **Regioned atlas**: placed by the device's sprite table; a missing table or a resized region refuses the texture, a region whose sprite the table dropped is left out, and nothing falls back to the PC offsets. ([ADR 0006](docs/adr/0006-place-a-regioned-atlas-by-the-sprite-table.md), [texture-translation](docs/features/texture-translation.md))
- **Skipped textures**: a texture `english_raw` cannot handle returns `None` and counts as skipped, never raised. `splice_label` stays idempotent. ([texture-translation](docs/features/texture-translation.md))
- **Counters**: the GUI shows untranslated counts beside `count_translated`'s `(text tables, textures)` (see the staging contract).
- **Terminology table**: one game keyword reads one way, the default name (`夺取` is *Steal*, never the community *Plunder*). It applies in memory as the catalog loads. Add a term only with its variants measured on both catalogs. ([terminology-table](docs/features/terminology-table.md))
- **Tokens**: `{Energy}`/`{LordExp}`/`{LordHp}` are expanded in the staged replacements by `resource_tokens.expand_tokens`; the catalog keeps the tokens. ([resource-token-expansion](docs/features/resource-token-expansion.md))
- **Update strings**: strings a data update adds come from the supplement (`resources/catalog_supplement/texts.json`, one section per update, loaded by `tools/catalog_supplement.py`), only where the catalog has no entry, and must pass `adaptive.validate_translation`.

**PC edition**

- **Receipts** live in `<work>\pc\receipts\<game-id>\` (`engine_hooks` moves the engine's `receipt_root` there), owned by this patcher alone, never in the engine's default folder (the upstream PC patcher's `%LOCALAPPDATA%`). They are the PC edition's only undo record; nothing is imported from the fork or the upstream patcher. A language switch restores from the receipts, then installs, in one job. ([language-switch](docs/features/language-switch.md))
- **Allowlist per edition**: a config bin a device cycle cleared stays untranslated on the PC edition until a PC cycle clears it there; the PC catalog carries none today (`extra_text.PC_SAFE_ASSETS` is empty), both mobile bins included. ([pc-cycle](docs/runbooks/pc-cycle.md))
- **Launcher list**: never write `LocalFileList.json` and keep every file it lists at its listed size, so the window title stays 王者万象棋. ([ADR 0011](docs/adr/0011-keep-every-file-the-pc-launcher-lists-at-its-listed-size.md))
- **Process guard**: every PC job refuses while `wxq*.exe` or `王者万象棋.exe` runs, listed through `CreateToolhelp32Snapshot`.
- **Replacements**: empty `<work>\replacements\` before each Install and Check; the engine never empties it, and a leftover file stops the next install.
- **Hooks**: every hook into the runtime goes through `engine_hooks.install`, and the PC-only ones (`scan`, `receipt_root`) only in a PC job.
- **Per-install catalog** (`pc_catalog`): the language's catalog plus the regioned atlases ported at the PC edition's own sprite table (a refused atlas is dropped from the copy), the re-hashed re-drawn payloads and the Lua entries; no append, no card-dictionary chunk gain. Its stage folder keeps the language's catalog folder name, because `languages.for_catalog` reads the language from it. ([pc-edition](docs/features/pc-edition.md))
- **Jobs** run in the `--pc-job` child, with no Stop safely or automatic continuation: the engine's commit recovers its own pending files on its next run. The game is found from the launcher's records or a picked folder, never by a drive scan.

**Freezing**

- **Native BC7**: `crates/hok_bc7` must give the bytes and decoded pixels of `bc7_mode6`'s Python modes (`_mode6`, `_separate`, `_mode7_python`) and `encode_block`'s Python search; check any change to either with `tools/research/check_bc7_native.py` and `tools/research/bc7_corpus.py replay --backend native --final` (lab notebook, 2026-11-26). The frozen `--smoketest` fails unless the native search ran through mode 7. Source runs fall back to Python when it is not built; `HOK_BC7_ENCODER=native|python` requires one.
- **Native block scan**: `rust/stale-blocks-rs` must match `tools/block_scan` on every recorded case; after any change to either, re-record and run `rust-anything gate rust/stale-blocks-rs` (lab notebook, 2026-11-27). The switch-on block falls back to Python where the module is missing (a source run without it, an Android build without the `stale_blocks_rs` wheel `android/native/build_rust_wheels.py` makes); the frozen `--smoketest` fails unless the native scan loaded. Change that block only with `rust-anything enable` / `disable`.
- **Runtime bytecode**: `resources/runtime/` is binary. A stdlib import it needs at freeze time goes in `HIDDEN_IMPORTS` in `app/build_exe.py`.
- **Codec modules**: `app/build_exe.py` keeps `--collect-all` for `astc_encoder`, `ooz`, `texture2ddecoder` and `pypinyin` as margin. On PyInstaller 6.22 the `astc_encoder` and `pypinyin` flags are measured unneeded, the other two unmeasured; an emptied `HIDDEN_IMPORTS` is what fails. Check any freeze change with `--smoketest`. ([lab notebook](docs/lab-notebook.md), 2026-11-17)

## Boundaries

- `resources/key/` holds the re-signing key and ships on purpose. Keep it stable across releases; never regenerate it.
- `resources/qtsvfs/` is Tencent's builder, kept in the repo for `--builder` runs from source, not shipped. Treat the DLLs as immutable; never hand-write a package layout in their place. ([prime-rebuild](docs/features/prime-rebuild.md), "The keys the builder derives")
- `resources/catalog/`, `resources/catalog_id/catalog.json.gz` and `resources/runtime/` come from the PC patcher pipeline. Fix a record in this repo's code (as `mobile_graphics.MISSING_METADATA` does); the one sanctioned catalog write is `tools/research/apply_catalog_fixes.py`, re-run after every upstream import and extended through `tools/research/catalog_additions.json` (the October 2026 update's strings, corrected only, never extended), `tools/research/catalog_rewrites.json` (garbled ones) and `tools/research/catalog_english_fixes.json` (one English slip repeated across many strings, such as "Usage" as a verb). `catalog/` ships beside every other catalog, because a language falls back to its payloads; `resources/catalog_id/`'s own payloads come from `tools/research/make_language_payloads.py` (`--check` proves them current). ([indonesian-language](docs/features/indonesian-language.md))
- `resources/sprites/`: `restore/` is generated by `tools/research/atlas_sprites.py` from a pristine layer only. `labels/` is hand-finished art and the source of truth; never regenerate over it, and run `labels --check` and `tools/research/career_atlas/validate_assets.py --delivered <dir>` before shipping a change. ([texture-translation](docs/features/texture-translation.md))
- `tools/research/` is a research record, not shipping code: the exe, the APK and `tools/` never import or bundle it. Only CI (its repository-only checks) and the Android unit tests (`tools/research/fixtures/run_artifacts`) read it.

## Docs

Every kind of doc has one home. Write prose in the vocabulary of `GLOSSARY.md`.

| Kind | Home | Read it when |
|---|---|---|
| Rules for every turn | `AGENTS.md` | always loaded |
| Vocabulary | `GLOSSARY.md` | naming a concept |
| Product | `PRODUCT.md`: users, purpose, voice | changing either patcher's interface or copy |
| Design | `DESIGN.md`, for both patchers | changing either patcher's interface |
| Decisions | `docs/adr/` | changing an area an ADR names |
| Feature records | `docs/features/` | changing a pass; update it in the same change |
| Device cycle | `docs/runbooks/device-cycle.md` | testing a change on a phone |
| PC cycle | `docs/runbooks/pc-cycle.md` | testing a change in the PC edition |
| Untranslated string | `docs/runbooks/diagnose-untranslated.md` | a string stays Chinese |
| Crash | `docs/runbooks/read-a-crash.md` | the game crashes |
| Evidence | `docs/lab-notebook.md`, the single source for numbers and verdicts | before re-running an experiment |
| Coverage | `docs/translation-progress.md` | a change moves a count; update it in the same change |
| Staging contract | the `build_patch` docstring | editing the pipeline |
| Work in flight | `.scratch/<feature>/`, committed | working a ticket |
| Skill configuration | `docs/agents/` | read by the skills |

Where a record and this file disagree, this file wins; a run's own summary outranks the coverage ledger.

## Git

Conventional commits: `feat:`, `fix:`, `chore:`, `docs:`. Update `README.md` in the same change when commands or layout change.

## Agent skills

### Issue tracker

Issues and specs live as local markdown files under `.scratch/<feature>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

The five default triage roles, each label the same as its role name, written as a `Status:` line in each issue file. See `docs/agents/triage-labels.md`.

### Domain docs

One `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
