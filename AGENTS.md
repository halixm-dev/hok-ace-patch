# HOK ACE Language Patcher

Windows GUI that installs the English or Indonesian translation into 王者万象棋 (`com.tencent.tmgp.osgame`) on an Android phone over USB, without root. The Android app in `android/` runs the same pipeline on the phone through Shizuku.

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

After moving or renaming a doc, run `tools\research\check_references.py` and `tools\research\check_staging_contract.py`.

## Architecture

| Path | Role |
|---|---|
| `app/` | GUI (`hok_patcher.py`), device workflow (`patcher_core.py`), APK rewrite + v2 signing (`apk_tools.py`) |
| `tools/` | Pipeline: `languages`, `terminology`, staging (`build_device_patch`), rebuild (`package_rebuild`, `qts_builder`), append (`qts_insert`), textures (`device_extensions`, `sprite_table`, `mobile_graphics`), extra text (`extra_text`, `pb_text`, `unity_text`), relocation (`qts_relocate`) |
| `tools/research/` | Probes and offline checks, run by hand |
| `resources/runtime/` | Compiled `wxq_patch` translation runtime (from the PC patcher) |
| `resources/catalog/` | English catalog (`catalog.json.gz`) plus the English catalog edits (`.blocks` / `.assets`) |
| `resources/catalog_id/` | Indonesian catalog, plus only the catalog edits it re-draws (`<HASH>.blocks` + `previews/<HASH>.png`); every other payload is read from `catalog/` |
| `resources/sprites/` | This repo's own art for regioned atlases: `<HASH>/labels/` and `<HASH>/restore/` |
| `resources/qtsvfs/` | Tencent's own package builder (`QtsVFS.dll` + `QtskDB.dll` + VC runtimes), driven by ctypes |

Flow: `patcher_core` drives the seven device steps and calls `build_patch`; the GUI talks only to `patcher_core`.

`sys.path` is set in `patcher_core.py`: `tools/` is inserted for source runs; `resources/runtime/` is **appended** so the project stdlib wins.

### Staging contract

The staging summary contract (payload fields, `mode` values, skipped lists, pass order, APK/builder gating) is the `build_patch` docstring in `tools/build_device_patch.py`.
Read it before editing the pipeline, and change it in the same edit as the code; `tools/research/check_staging_contract.py` checks it stays there.

## Code style

Module docstring, `from __future__ import annotations`, type hints, `pathlib.Path`. Constants `UPPER_CASE` at module level. Private helpers `_name`. User-facing failures raise `PatchError`.

## Constraints

**Install and delivery**

- **Install path**: re-sign, install the access APK, write the override layer, reinstall the normal APK. The access APK never stays installed, nor is it cached as the normal APK. ([ADR 0001](docs/adr/0001-install-through-a-temporary-access-apk.md))
- **Update timing**: write the translation only after the in-game update finishes. ([ADR 0002](docs/adr/0002-write-the-translation-after-the-in-game-update.md))
- **Normal APK**: the game's own file with only `AndroidManifest.xml` rewritten (debug flag, launcher name `APP_NAME`); any further edit needs a device cycle. The rename must never fail a run. ([standalone-patcher-app](docs/features/standalone-patcher-app.md), [device-cycle](docs/runbooks/device-cycle.md))
- **Login**: re-signing breaks direct WeChat/QQ login; users log in via *Scan to login*, as expected.
- **Working data** (~8 GB) goes to the user-chosen folder, never into this repo. `build/`, `dist/`, `.venv/` are generated and disposable.

**Coverage and gating**

- **Coverage** is the staged text tables, the catalog edits, the two Career-atlas labels (`mobile_graphics.ATLAS_LABELS`) and one Lua label (`extra_text.SCRIPT_LABELS`). Never call it a complete translation; state the texture count as *applied*, never *covered*. ([translation-progress](docs/translation-progress.md))
- **Catalog only**: the text pass stages the catalog's tables and nothing else (`_drop_uncatalogued_tables`). ([prime-only-append](docs/features/prime-only-append.md))
- **Allowlist**: a config bin is translated only once a device cycle clears it onto `extra_text.SAFE_ASSETS` (empty today). `--cycle-asset` enables one `CANDIDATE_ASSETS` hash per run; `tools/extra_text.py` records each withdrawn hash with its failing screen. ([ADR 0004](docs/adr/0004-the-allowlist-is-the-only-gate-for-config-bins.md), [extra-text-cycles](docs/features/extra-text-cycles.md))
- **Uncatalogued config bins** are never rewritten, not even re-pointed at identical length. ([ADR 0005](docs/adr/0005-never-rewrite-an-uncatalogued-config-bin.md))
- **Card dictionaries** keep their chunk size and gain chunks only with keys in `device_extensions.NATIVE_CHUNK_KEYS`; unknown layouts are refused and reported. No text table gains rows past its existing chunks. ([prime-only-append](docs/features/prime-only-append.md))
- **Both data layers**: check the override layer and the prime layer before calling an asset unreachable. ([diagnose-untranslated](docs/runbooks/diagnose-untranslated.md))
- **Aliases**: an entry joins `mobile_graphics.DEVICE_REVISIONS` only on a measured match, never by guess. ([texture-translation](docs/features/texture-translation.md))

**Pipeline**

- **Append, not rebuild**: `REBUILD_PACKAGES` stays empty (package `21` in particular); prime-only content reaches the override layer by append. ([ADR 0003](docs/adr/0003-reach-prime-only-content-by-append-not-rebuild.md))
- **Append pass** rewrites nothing it did not add, keeps the read-back through `QtsPackage`, stays idempotent, and reports a full B-tree leaf (`TreeFull`) in `append_skipped` instead of failing the run. A new asset kind it may carry goes into `package_rebuild.make_transform`. ([prime-only-append](docs/features/prime-only-append.md))
- **APK gating**: without the APK a run still succeeds and leaves prime-only content Chinese; check the log for the `added from the APK` lines. ([prime-rebuild](docs/features/prime-rebuild.md))
- **Reading chunks**: `qts_relocate.read_raw` follows each chunk's own framing, not the entry's compression id. A rebuild omits entries with no bytes (`entries_without_bytes`) but aborts on bytes that will not decode. ([prime-rebuild](docs/features/prime-rebuild.md))
- **Regioned atlas**: placed by the device's sprite table; a missing or moved region refuses the texture, with no fallback to the PC offsets. ([ADR 0006](docs/adr/0006-place-a-regioned-atlas-by-the-sprite-table.md), [texture-translation](docs/features/texture-translation.md))
- **Skipped textures**: a texture `english_raw` cannot handle returns `None` and counts as skipped, never raised. `splice_label` stays idempotent. ([texture-translation](docs/features/texture-translation.md))
- **Counters**: the GUI shows untranslated counts beside `count_translated`'s `(text tables, textures)` (see the staging contract).
- **Terminology table**: one game keyword reads one way, the default name (`夺取` is *Steal*, never the community *Plunder*). It applies in memory as the catalog loads. Add a term only with its variants measured on both catalogs. ([terminology-table](docs/features/terminology-table.md))
- **Tokens**: `{Energy}`/`{LordExp}`/`{LordHp}` are expanded in the staged replacements by `resource_tokens.expand_tokens`; the catalog keeps the tokens. ([resource-token-expansion](docs/features/resource-token-expansion.md))
- **Update strings**: strings a data update adds come from `tools/catalog_supplement.py`, only where the catalog has no entry, and must pass `adaptive.validate_translation`.

**Freezing**

- **Runtime bytecode**: `resources/runtime/` is binary. A stdlib import it needs at freeze time goes in `HIDDEN_IMPORTS` in `app/build_exe.py`.
- **Codec modules**: `app/build_exe.py` collects `astc_encoder`, `ooz` and `texture2ddecoder` explicitly and `pypinyin` with `--collect-all`; without them the exe builds but dies on the first texture. ([texture-translation](docs/features/texture-translation.md))

## Boundaries

- `resources/key/` holds the re-signing key and ships on purpose. Keep it stable across releases; never regenerate it.
- `resources/qtsvfs/` is Tencent's builder and ships on purpose. Treat the DLLs as immutable; never hand-write a package layout in their place. ([prime-rebuild](docs/features/prime-rebuild.md), "The keys the builder derives")
- `resources/catalog/`, `resources/catalog_id/catalog.json.gz` and `resources/runtime/` come from the PC patcher pipeline. Fix a record in this repo's code (as `mobile_graphics.MISSING_METADATA` does); the one sanctioned catalog write is `tools/research/apply_catalog_fixes.py`, re-run after every upstream import and extended through `tools/research/catalog_additions.json`. `catalog/` ships beside every other catalog, because a language falls back to its payloads; `resources/catalog_id/`'s own payloads come from `tools/research/make_language_payloads.py` (`--check` proves them current). ([indonesian-language](docs/features/indonesian-language.md))
- `resources/sprites/`: `restore/` is generated by `tools/research/atlas_sprites.py` from a pristine layer only. `labels/` is hand-finished art and the source of truth; never regenerate over it, and run `labels --check` and `tools/research/career_atlas/validate_assets.py --delivered <dir>` before shipping a change. ([texture-translation](docs/features/texture-translation.md))
- `tools/research/` is a research record, not shipping code: nothing imports or bundles it.

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
