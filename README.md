# HOK ACE Mobile English Patcher

Windows app that installs the English translation into 王者万象棋 (`com.tencent.tmgp.osgame`)
on an Android phone over USB, without root. The translation is written into the game data
**after** the in-game update finishes, because Tencent's updater applies binary diffs that break
if the language packages were modified inside the APK.

## Layout

| Path | Contents |
|---|---|
| `app/` | GUI (`hok_patcher.py`), workflow (`patcher_core.py`), APK signing (`apk_tools.py`), `build_exe.py`, `make_icon.py` |
| `tools/` | Translation build pipeline: `build_device_patch.py` (entry `build_patch`), `device_extensions.py` (texture pass), `mobile_graphics.py` (ASTC/Oodle codec), `build_mobile_patch.py`, `qts_relocate.py`, `resource_tokens.py`, `axml_set_debuggable.py` |
| `tools/research/` | Reverse-engineering probes (hash emulation, descriptor probes, AXML provider injection, archive extractors) and `check_graphics.py`, the offline texture check. Off the runtime path; nothing here ships in the exe |
| `resources/runtime/` | Compiled `wxq_patch` translation runtime, extracted from the PC patcher (Python 3.12 bytecode) |
| `resources/catalog/` | Translation catalog (`.blocks` / `.assets`) — the English texture payloads the texture pass applies, plus `previews/` |
| `resources/adb/` | `adb.exe` + DLLs |
| `resources/key/` | Re-signing key: `key.pk8` + `cert.der` |
| `resources/icon.*` | App icon (regenerate with `app\make_icon.py`) |

## Build

Requires Python **3.12** (the runtime bytecode only loads on 3.12).

```bat
setup.bat      :: creates .venv and installs requirements.txt
build.bat      :: -> dist\HOK ACE Mobile English Patcher.exe
run.bat        :: run from source without building
```

If `py -3.12` is not available: `set PYTHON=C:\path\to\python3.12.exe` before `setup.bat`.

`build\` (PyInstaller scratch), `dist\` and `.venv\` are generated and can be deleted anytime.

## What the patcher does on the phone

1. Pulls the installed APK, re-signs it with the project key, and builds a temporary
   `android:debuggable` copy for data access via `run-as`.
2. Reads the language packages from the game data, builds the English packages
   (`tools/build_device_patch.py`), pushes them back and verifies them.
3. Reinstalls the normal re-signed APK.

The patcher's own working data (~8 GB: pulled APK, packages, sessions) goes to the folder chosen in the app
(default `HOK ACE Patcher Data` next to the exe), not into this project.

## Translation coverage

The pipeline translates **text tables and textures**. Text is staged in `full` mode and falls back to
`fit-only` when replacements compete for slack, dropping the tables that will not fit. Textures are a
second pass that ports each reviewed edit in `resources/catalog/` onto the device's ASTC textures,
which the game stores Oodle-compressed; the changed chunks are appended to the package shard and
repointed in its B-tree, so every asset keeps its chunk count. On the game data used to develop this,
322 of the catalog's 398 edits are present and all 322 are applied.

Resource tokens such as `{Energy}`, `{LordExp}` and `{LordHp}` are expanded to English terms
(`Energy`, `Chessplayer EXP`, `Chessplayer HP`) in the staged packages, so the client no longer
expands them to Chinese. A space is inserted wherever the term would otherwise run into a preceding
word or placeholder, or into a following word or signed value. Beyond that the pipeline deliberately
does not extend:

- Extra text tables outside the staged packages are not translated, and no texture outside
  `resources/catalog/` is.

Re-running the patcher is safe: `qts_relocate.install_btree_slot_map()` makes the scanner follow the
shard's B-tree, so a second run reads the live chunks instead of superseded copies of relocated ones,
and the texture pass treats a texture that already matches its English payload as done.

## Checking the texture pass

`tools/research/check_graphics.py` needs neither a phone nor a game dump. It decodes every shipped
payload and compares it to its review render, round-trips the ASTC codec, and asserts that a byte patch
changes nothing outside its patch ranges:

```bat
.venv\Scripts\python.exe tools\research\check_graphics.py
```

Add `--game <game-dir>` to repeat those assertions on the real textures read out of a game dump.

## Known limits

- Direct WeChat/QQ login does not work on a re-signed APK; use *Scan to login*.
- After a game update: clear the game's data, let it re-download to the login screen, then patch again.
- Re-running over an **already patched** install translates no more text: the scanner only translates
  tables that still hold Chinese, and it reports nearly everything else as already English. To pick up
  a newer translation build, reset the game's data first (previous bullet) so the tables are Chinese
  again. Textures are not affected by that limit — the texture pass compares each device texture
  against its English payload, so a re-run picks up any texture the previous run did not write.
- Code injection into the APK and a "prebaked" APK with translated assets were both tried and fail
  (anti-cheat kill / `IsPrebuild errorCode:151`).
