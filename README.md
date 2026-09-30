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
| `tools/research/` | Reverse-engineering probes (hash emulation, descriptor probes, AXML provider injection, archive extractors) and the offline graphics tools: `check_graphics.py`, `render_texture.py`, `ribbon_id_hunt.py`, `browse_assets.py`. Off the runtime path; nothing here ships in the exe |
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
323 of the catalog's 398 edits are present and all 323 are applied.

A whole-image replacement can also land when the device revision of the same art is a different size
from the catalog's record — a build re-cutting a card by one block row changes the raw size, which by
itself would reject the edit. The texture pass then measures the alignment between the two images and
copies only the label across, leaving the rest of the device's own pixels alone; an image that does not
align is still skipped rather than rescaled. On the game data used to develop this, one replacement
(`C9E29F61B9E73713`, Three Kingdoms, 592x816 in the catalog and 592x824 on the device) is recovered this
way. Which screen draws that asset has not been established, so treat the recovery as a correctness fix
rather than a visible one.

The other 75 catalog edits have **no counterpart on the device at all**: their asset ids are not in the
mobile build, so no code change can apply them. They are the art behind much of what stays Chinese,
and the clearest case is the Card Info view's faction ribbon. That ribbon is **not** the card's own art:
the grid card `F72420296646DC5B` is in the catalog, on the device, and the pass rewrites its ribbon to
`Central Plains`, yet the Card Info view for that same card still shows `河洛`. The ribbon comes from a
wide-format per-faction panel instead — the catalog keys 27 of them at 568x304, four art variants per
faction and three for Mecha — and the device carries that family for one faction only, the Sunset panel
behind `BCCC8C957621FA27`. So the faction ribbon inside a card is translated everywhere it is baked
into the card art, and stays Chinese in the views that draw it from the separate wide panel.

That gap was measured rather than inferred, because this is the one family that could plausibly have
been on the device all along under an id the catalog does not key. `tools/research/ribbon_id_hunt.py`
scores every device texture whose raw size could hold a 568x304 panel — each of the six ASTC footprints,
and every height inside the 16 px the label splice is able to absorb — against all 27 English payloads.
The test separates the family by an order of magnitude: a genuine sibling of it measures between 0.05
and 2.5 depending on the footprint, while an unrelated texture of the same shape measures about 14. The
Sunset panel matches its own payload at 1.1, inside that floor, and the next-closest entry scores 4.3.
The best of the other 54 candidates scores 11.0, more than four times the floor, and rendering every one
of them shows black frames, gradients, event banners and buttons rather than panels. The other factions'
wide panels are therefore not in this build under any id, and the Card Info ribbon for them cannot be
fixed from this repo.

The ribbon is art rather than text: in that same Card Info view every other string, including the
faction name inside a card's rules text, is already English.

The catalog's card coverage is also narrower than it looks. Package `15` holds 3990 textures, 1994 of
them card-shaped, and the catalog's 299 entries at that shape are the **hero** cards — the rest are
Talent, skill and effect cards, whose bottom band carries a type word or a card name rather than a
faction, and which the catalog does not translate at all.

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
payload and compares it to its review render, round-trips the ASTC codec, asserts that a byte patch
changes nothing outside its patch ranges, and builds a synthetic device revision to exercise the
label splice:

```bat
.venv\Scripts\python.exe tools\research\check_graphics.py
```

Add `--game <game-dir>` to repeat those assertions on the real textures read out of a game dump, and to
print the per-entry table of what the dump carries. By default that table lists only the entries the run
cannot translate — the ones that are absent from the build or were skipped — because the 320-odd applied
rows are not what needs looking at; `--table` prints all of them.

`tools/research/render_texture.py` renders one payload or device texture to PNG, for identifying a
texture by eye when the hash alone does not say what it is:

```bat
.venv\Scripts\python.exe tools\research\render_texture.py --hash C9E29F61B9E73713 --out <dir>
.venv\Scripts\python.exe tools\research\render_texture.py --game <game-dir> --size 121952 --out <dir>
```

`tools/research/ribbon_id_hunt.py` is the record of the search for the mobile build's own ids for the
wide Card Info panels. `--floor-only` needs no dump: it reprints the family and measures what a genuine
sibling of it scores at each device footprint, which is the baseline the search is judged against. With
`--game` it censuses the dump and scores every 568x304-shaped texture in it against all 27 payloads,
near-misses included, so a weak match is visible as a weak match:

```bat
.venv\Scripts\python.exe tools\research\ribbon_id_hunt.py --floor-only
.venv\Scripts\python.exe tools\research\ribbon_id_hunt.py --game <game-dir> --render <dir>
```

`tools/research/browse_assets.py` browses the device's textures as images, for finding one by eye. It
caches an index of every asset (package, id, uncompressed size) on first run — about a minute, instant
after — and then renders a size family or a whole package into contact sheets. The catch it exists to
make explicit is that an ASTC texture's geometry is not stored anywhere: the byte count fixes only the
*block count*, so the same bytes can be a 568x304 texture at 8x8 or an 852x456 one at 12x12. `--diagnose`
measures how the device resolves that, and the answer is useful — of the 322 catalogued textures the
build carries, 311 are 4x4, 10 are 6x6 and one is 8x8 — so 4x4 is the default footprint. Pinning it
leaves little but the axis split, which `--guess` settles two ways: a geometry matching a catalogued
dimension is trusted outright, since the catalog knows the game's real texture sizes, and otherwise the
candidates are decoded and the most coherent one kept — a wrong grid breaks continuity at every block
edge, which the pixels themselves show. `--candidates <size>` renders one asset at every geometry that
size admits, and remains the authoritative check when a family looks wrong:

```bat
.venv\Scripts\python.exe tools\research\browse_assets.py --game <game-dir> --sizes --packages
.venv\Scripts\python.exe tools\research\browse_assets.py --game <game-dir> --candidates 227856 --out <dir>
.venv\Scripts\python.exe tools\research\browse_assets.py --game <game-dir> --package 19 --render ^
    --guess --out <dir>
```

`--manifest` writes a CSV inventory of the selection — one line per asset id, with the geometry it would
be rendered at and how that geometry was decided — and `--all --manifest` covers the whole build.
`--all --render` renders every texture in it into sheets captioned with the full 16-character id. On the
game data used to develop this that is 25,053 of the 83,131 assets drawn on 522 sheets: the other 56,707
are config blobs a few hundred bytes long, and 1,369 do not decompress. Two more crash the ASTC decoder
outright, which no in-process code can catch — `--trace` logs each id just before it is decoded so the
offender can be named, and `--skip <id>` with `--resume` carries on past it. Rendering everything takes a
few minutes and writes about 350 MB.

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
