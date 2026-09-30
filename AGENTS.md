# HOK ACE Mobile English Patcher

Windows GUI that installs the English translation into 王者万象棋 (`com.tencent.tmgp.osgame`) on an Android phone over USB, without root.

Python **3.12 only**. `resources/runtime/` is 3.12 bytecode and will not load on any other version.

## Commands

Run from the project root:

```bat
setup.bat      :: .venv + requirements.txt  (fallback: set PYTHON=C:\path\to\python3.12.exe first)
build.bat      :: -> dist\HOK ACE Mobile English Patcher.exe
run.bat        :: run from source
```

Headless runtime check (needs a dumped game directory):

```bat
dist\HOK ACE Mobile English Patcher.exe --selftest <game-dir> <out-dir>
```

No test suite. Verify changes with `run.bat` or `--selftest`. The texture codec has its own offline check, which needs neither a device nor a game dump:

```bat
.venv\Scripts\python.exe tools\research\check_graphics.py [--game <game-dir>]
```

The whole pipeline also runs offline against a dumped game directory. Add the cached APK and the builder to include the packages that keep translatable content only inside the APK:

```bat
.venv\Scripts\python.exe tools\build_device_patch.py --runtime resources\runtime --game <game-dir> ^
    --catalog resources\catalog --work <work-dir> --output <out-dir> ^
    --apk <path>\installed.apk --builder resources\qtsvfs
```

## Architecture

| Path | Role |
|---|---|
| `app/` | GUI (`hok_patcher.py`), device workflow (`patcher_core.py`), APK rewrite + v2 signing (`apk_tools.py`) |
| `tools/` | Translation build pipeline: text staging (`build_device_patch.build_patch`), prime rebuild (`package_rebuild`, `qts_builder`), texture pass (`device_extensions.port_graphics`), extra-text pass (`extra_text`, `pb_text`, `unity_text`), ASTC/Oodle codec (`mobile_graphics`), shard relocation (`qts_relocate`) |
| `tools/research/` | Reverse-engineering probes and the offline graphics check; never imported by the app or the pipeline |
| `resources/runtime/` | Compiled `wxq_patch` translation runtime (from the PC patcher) |
| `resources/catalog/` | Translation catalog (`.blocks` / `.assets`) plus the English payloads the texture pass applies |
| `resources/qtsvfs/` | Tencent's own package builder (`QtsVFS.dll` + `QtskDB.dll` + VC runtimes), driven by ctypes to lay out a package whole |

Flow: `patcher_core` drives the seven device steps and calls `build_patch`. `apk_tools` rewrites and re-signs the APK. The GUI talks only to `patcher_core`.

`sys.path` is set in `patcher_core.py`: `tools/` is inserted for source runs; `resources/runtime/` is **appended** so the project stdlib wins.

### `build_patch` contract

`tools/build_device_patch.py` exposes both a CLI and the programmatic entry the app uses:

```python
def build_patch(game: Path, catalog: Path, work: Path, output: Path,
                *, fit_only_mode: bool = False, apk: Path | None = None,
                builder_dir: Path | None = None, log=print) -> dict:
```

- It imports `wxq_patch` from whatever runtime directory the caller already put on `sys.path`; it never adds paths itself. That is what lets the frozen exe run it.
- It calls `qts_relocate.install_btree_slot_map()` before scanning, so a re-run reads live chunks rather than superseded copies of relocated ones.
- It returns exactly the payload written to `output/device_patch_summary.json`: `counts`, `skipped_count`, `fit_only`, `packages`, `text_skipped`, and `graphics_skipped` — each `packages` entry carrying `package_id`, `mode`, `source_package`, `fit_summary`, `stage_report`. Callers read `stage_report["replacement_count"]`.
- `apk` and `builder_dir` are what make the game's **other data layer** reachable. The game reads the packages baked into the APK (prime) first only when the downloaded layer (override) lacks an asset, and package `1` keeps most of its text — the chessplayer names among it — only in prime. Given both, `package_rebuild.rebuild_prime_packages` re-lays out those packages whole before the in-place loop runs. Given neither, it logs that prime-only content stays Chinese and stages exactly as it did before, which is what keeps `--selftest` and the offline CLI usable without the DLLs.
- Only packages that actually staged appear in `packages`. A package with nothing left that fits is logged and skipped, not reported as a result, and its directory is removed from `output/` so the directories there are exactly the reported packages — the installer pushes by directory, not by summary.
- A graphics package whose **every** texture was skipped also writes no directory, so it stays out of `packages`; it is reported instead in `graphics_skipped` (`package_id`, `mode`, `skipped_count`, `considered_count`, `skipped`). Without that list a skipped texture is invisible in the summary, which is how `C9E29F61B9E73713` stayed Chinese unnoticed. `count_untranslated_graphics` reads it so the GUI can say how many images were left alone. A rebuilt package reports the textures its transform refused the same way, with `mode: rebuilt`.
- The drop loop gives ground until the container takes what is left, so a package that stages successfully can still be missing part of its plan — and a package that stages nothing is missing all of it. Those tables are reported in `text_skipped` (`package_id`, `mode`, `considered_count`, `dropped_count`, `dropped`), one entry per package that lost something; `dropped` is the plan minus what the staged directory holds minus what `relocate_text` wrote afterwards, because relocation applies a table rather than losing it. `count_untranslated_text` reads it so the GUI can say how many tables stay in Chinese. The field names stay distinct from `graphics_skipped`'s on purpose: that list is textures that were never translated, this one is text that was translated and then not applied, and one accessor must not sum them into a total that means nothing.
- `mode` is `full`, `fit-only`, `rebuilt`, `relocated-text`, `graphics`, or `extra-text`. A `graphics` entry's `replacement_count` counts textures, not tables. A `rebuilt` entry counts both and carries `textures`, the share of its `replacement_count` that was catalog textures, plus `assets`, `translated_downloaded` and `added_from_apk`; `count_translated` must use `textures`, because classifying a rebuilt package by mode alone reports one of its two kinds as the other.
- After the text loop it calls `device_extensions.extend_graphics(game, catalog, output, log, skip=rebuilt)`, which discovers the game packages afresh (a texture-heavy package usually stages no text), ports every catalog texture edit present in them onto the device ASTC textures, and runs the extra-text pass. `skip` keeps it off a package the rebuild already replaced whole, which no longer matches the device's container. It returns `(reports, skipped)`: the reports become `packages`, the skips become `graphics_skipped`.

## Code style

Module docstring, `from __future__ import annotations`, type hints, `pathlib.Path`. Constants `UPPER_CASE` at module level. Private helpers `_name`. User-facing failures raise `PatchError`.

```python
"""One-line description of the module's job."""
from __future__ import annotations

from pathlib import Path

PACKAGE = "com.tencent.tmgp.osgame"


def free_space(path: Path) -> int | None:
    """Free bytes on the drive holding <path> (or its nearest existing parent)."""
    ...
```

## Constraints

- Write the translation **after** the in-game update finishes. Tencent's updater applies binary diffs that break if language packages were modified inside the APK.
- `resources/runtime/` is precompiled bytecode — treat it as binary. When the runtime needs an extra stdlib import at freeze time, add it to `HIDDEN_IMPORTS` in `app/build_exe.py`.
- Coverage is **the staged text tables plus the catalog's textures**: no extra text tables, and no graphics beyond the reviewed edits in `resources/catalog/`. Do not describe the result as a complete translation. State the texture count as *applied*, never as *covered*, and check **both** data layers before calling an edit unreachable: of the catalog's 398 texture edits, 395 exist in the mobile build — 323 downloaded, 73 inside the APK — 394 are applied by a run, and only `197CC5393D16E3CB`, `884E0B4581F47CF7` and `89C771ECFCDC7FBE` exist in neither. An earlier count of 75 was measured against the downloaded dump alone, so a search for a missing asset must cover `assets/bin/Data/Package/builtin/` too; `tools/research/prime_probe.py` is that census. `{Energy}`/`{LordExp}`/`{LordHp}` are expanded to English terms in the staged replacements (`tools/resource_tokens.py`). The catalog must keep the tokens: `translate_table` requires matching placeholders, so expanding the catalog instead trips `placeholders_changed` and drops the records. The same expansion has to be applied to the assets the prime-rebuild and extra-text passes translate, which is what `resource_tokens.expand_tokens` is for.
- `count_translated` returns `(text tables, textures)`. Classify on `packages[].mode == "graphics"` for the texture pass, and on the entry's own `textures` field for `mode == "rebuilt"`, which holds both kinds in one entry. Keep both halves wired through the GUI. Do not report an image count without a texture pass behind it. `count_untranslated_graphics` reads `graphics_skipped` for the textures a run found but could not translate, and `count_untranslated_text` reads `text_skipped` for the tables the drop loop left out; the GUI shows both, because "N translated" alone reads as "all of them".
- The texture pass reads BC7/RGBA32 payloads, encodes ASTC and unpacks Oodle chunks, which needs `astc_encoder`, `ooz` and `texture2ddecoder` at run time. `wxq_patch` never references them, so PyInstaller cannot find them on its own: `app/build_exe.py` collects each one explicitly. Dropping those flags still builds a working exe that dies on the first texture.
- The prime rebuild needs `resources/qtsvfs/` (Tencent's builder) and the pulled APK. `build_exe.py` ships the first with `--add-data`; the second arrives as `Patcher.normal_apk`. Lose either and the run still works, it just logs that prime-only content stays Chinese — so a "successful" run is not evidence that the rebuild ran. Check the log for the rebuild lines.
- `pypinyin` is needed by the extra-text pass alone (they romanise the AI opponent names, which the catalog does not translate). It carries its own dictionary data, so `build_exe.py` uses `--collect-all` rather than `--hidden-import`.
- A texture `english_raw` cannot handle returns `None` and is counted as skipped, never raised. Keep it that way: a skipped texture is better than a failed patch run. The one rescue path is `splice_label`, for a whole-image replacement whose device revision moved geometry: it copies only the label across, and refuses unless the two images actually align. It must stay idempotent — it returns its input untouched once the label matches, because re-encoding from a lossy decode perturbs the label's edge blocks.
- Code injection into the APK and prebaked APKs with translated assets both fail (anti-cheat kill / `IsPrebuild errorCode:151`). The supported path is: re-sign → debuggable data-access copy → replace packages in game data → reinstall.
- Re-signing breaks direct WeChat/QQ login. Users log in via *Scan to login*. That limit is expected.
- The patcher's ~8 GB working data goes to the user-chosen folder (default `HOK ACE Patcher Data` beside the exe), never into this repo.
- `build/`, `dist/`, `.venv/` are generated and disposable.

## Boundaries

- `resources/key/` holds the re-signing key (`key.pk8`, `cert.der`) and ships with the app on purpose. Keep the key stable across releases; do not regenerate it.
- `resources/qtsvfs/` holds Tencent's own `QtsVFS.dll` and `QtskDB.dll` and ships on purpose too: it is the only thing that derives a package's lookup keys, so a rebuilt package cannot be produced without it, and the frozen exe has to carry it. They are third-party binaries — treat them as immutable, and never hand-write a package layout in their place.
- `resources/catalog/` and `resources/runtime/` are produced by the PC patcher pipeline. This repo consumes them. Never edit the catalog to fix a record: corrections belong in this repo's code, which is why `mobile_graphics.MISSING_METADATA` supplies the geometry six entries omit.
- `tools/research/` is a research record, not shipping code. Nothing imports it and `app/build_exe.py` does not bundle it. Moving or deleting it must not break `app/` or `tools/`. Its scripts are run by hand from the project root.

## Git

Conventional commits: `feat:`, `fix:`, `chore:`, `docs:`. Update `README.md` in the same change when commands or layout change.
