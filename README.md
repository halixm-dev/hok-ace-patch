# HOK ACE Mobile English Patcher

Windows app that installs the English translation into 王者万象棋 (`com.tencent.tmgp.osgame`)
on an Android phone over USB, without root. The translation is written into the game data
**after** the in-game update finishes, because Tencent's updater applies binary diffs that break
if the language packages were modified inside the APK.

## Layout

| Path | Contents |
|---|---|
| `app/` | GUI (`hok_patcher.py`), workflow (`patcher_core.py`), APK signing (`apk_tools.py`), `build_exe.py`, `make_icon.py` |
| `tools/` | Translation build pipeline: `build_device_patch.py` (entry `build_patch`), prime rebuild against the APK (`package_rebuild.py`, `qts_builder.py`), `device_extensions.py` (texture and relocation passes), extra-text pass (`extra_text.py`, `pb_text.py`, `unity_text.py`), `mobile_graphics.py` (ASTC/Oodle codec), `build_mobile_patch.py`, `qts_relocate.py`, `resource_tokens.py`, `axml_set_debuggable.py` |
| `tools/research/` | Reverse-engineering probes (hash emulation, descriptor probes, AXML provider injection, archive extractors) and the offline tools: `check_graphics.py`, `render_texture.py`, `ribbon_id_hunt.py`, `browse_assets.py`, `prime_probe.py`. Off the runtime path; nothing here ships in the exe |
| `resources/runtime/` | Compiled `wxq_patch` translation runtime, extracted from the PC patcher (Python 3.12 bytecode) |
| `resources/catalog/` | Translation catalog (`.blocks` / `.assets`) — the English texture payloads the texture pass applies, plus `previews/` |
| `resources/adb/` | `adb.exe` + DLLs |
| `resources/key/` | Re-signing key: `key.pk8` + `cert.der` |
| `resources/qtsvfs/` | Tencent's own package builder (`QtsVFS.dll`, `QtskDB.dll`, VC runtimes), driven by ctypes to re-lay-out a package whole |
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

The game's data has two layers, and the patcher writes to the second one:

| layer | where | contents |
|---|---|---|
| **prime**, built into the APK | `assets/bin/Data/Package/builtin/<id>/` | every asset as the APK was built |
| **override**, downloaded | `files/QtsVFSCache/packages/<id>/` | only the assets that changed since that build |

The game reads override first and falls back to prime, so an asset that exists only in prime is
unreachable by an in-place edit. The pulled APK is therefore a patch input, not just something to
re-sign: packages `1` and `1050016095` are laid out again with Tencent's own builder
(`resources/qtsvfs/`) so the override copies of them can carry the prime-only content, translated.
Nothing else is rebuilt — re-laying-out a package means recompressing all of it.

The patcher's own working data (~8 GB: pulled APK, packages, sessions) goes to the folder chosen in the app
(default `HOK ACE Patcher Data` next to the exe), not into this project.

## Translation coverage

The pipeline translates **text tables and textures**. Text is staged in `full` mode and falls back to
`fit-only` when replacements compete for slack, dropping the tables that will not fit; a table the stager
cannot fit is then appended to the end of the shard rather than lost. Textures are a second pass that
ports each reviewed edit in `resources/catalog/` onto the device's ASTC textures, which the game stores
Oodle-compressed; the changed chunks are appended to the package shard and repointed in its B-tree, so
every asset keeps its chunk count.

Of the catalog's 398 texture edits, 395 exist somewhere in the mobile build — 323 in the downloaded layer
and 73 in the APK's built-in layer, one asset keyed in both — and a run applies 394 of them. The ones it
does not:

- `7B4CC5DF48336D2D`, Central Plains' fourth wide faction panel, sits in the APK's package `21`. Applying
  it means rebuilding that package, which recompresses all 511 MB of it — 85,211 assets — on every run,
  for that one texture. Package `21` is deliberately not rebuilt.
- `197CC5393D16E3CB`, `884E0B4581F47CF7` and `89C771ECFCDC7FBE` are in neither layer: their asset ids are
  not in the mobile build, so no code change can apply them.

A whole-image replacement can also land when the device revision of the same art is a different size
from the catalog's record — a build re-cutting a card by one block row changes the raw size, which by
itself would reject the edit. The texture pass then measures the alignment between the two images and
copies only the label across, leaving the rest of the device's own pixels alone; an image that does not
align is still skipped rather than rescaled. On the game data used to develop this, one replacement
(`C9E29F61B9E73713`, Three Kingdoms, 592x816 in the catalog and 592x824 on the device) is recovered this
way. Which screen draws that asset has not been established, so treat the recovery as a correctness fix
rather than a visible one.

The catalog keys 27 wide per-faction panels at 568x304 — four art variants per faction and three for
Mecha — and the Card Info view draws its faction ribbon from that family rather than from the card's own
art: the grid card `F72420296646DC5B` is in the catalog and on the device, and the pass rewrites its
ribbon, yet the Card Info view for that same card still shows `河洛`. So the faction ribbon is translated
wherever it is baked into the card art, and comes from the separate wide panel in the views that draw it
that way. It is art rather than text, so no text table can reach it: in that same Card Info view every
other string, including the faction name inside a card's rules text, is already English.

An earlier measurement concluded the panel family was absent from the build. That conclusion was drawn
against the **downloaded** layer only, and is superseded. `tools/research/ribbon_id_hunt.py` scores every
texture in that layer whose raw size could hold a 568x304 panel — each of the six ASTC footprints, and
every height inside the 16 px the label splice is able to absorb — against all 27 English payloads; the
test separates the family by an order of magnitude, a genuine sibling measuring between 0.05 and 2.5
depending on the footprint while an unrelated texture of the same shape measures about 14. Within that
layer its negative result held: the Sunset panel behind `BCCC8C957621FA27` matched its own payload at
1.1, and the best of the other 54 candidates scored 11.0, rendering as black frames, gradients, event
banners and buttons rather than panels.

Counting the APK's built-in layer as well changes the answer: 26 of the 27 panels are there under the
catalog's own ids — 25 of them in package `1050016095` and `7B4CC5DF48336D2D` in package `21` — and the
Sunset panel the hunt did find is in the downloaded layer. A run now applies 26 of the 27, so every
faction's wide panel is translated except Central Plains' fourth variant. Whether the Card Info view
follows is for the device to show; this document does not claim it.

`tools/research/prime_probe.py` prints that census: what each package keeps only in the APK, and how much
of it the catalog covers. A search for a missing asset has to run over both layers, which is the lesson
the earlier measurement paid for.

The catalog's card coverage is also narrower than it looks. Package `15` holds 3990 textures, 1994 of
them card-shaped, and the catalog's 299 entries at that shape are the **hero** cards — the rest are
Talent, skill and effect cards, whose bottom band carries a type word or a card name rather than a
faction, and which the catalog does not translate at all.

Package `1` is where the two layers matter most for text. It holds 2492 of its 2873 assets only in the
APK, 408 of them catalog text tables, of which 298 translate — 51,095 records, the chessplayer names and
their skills, talents and secret skills among them. The rebuild carries all 298 into the downloaded copy
of the package, which is the layer the game reads first, together with the 102 downloaded assets it
re-translates.

That rebuild is also why the stager no longer loses package `1`'s tables. Replacing a table with a longer
one needs room in the package's shard, and when the shard has none the staging loop drops that table and
restages with what is left — on this data it used to drop 11 of package `1`'s 92, every one of them a
chessplayer skill, talent or secret-skill table. A package the rebuild replaces never reaches that loop.
For every other package the drop is now a relocation instead: a table that will not fit its slot is
appended to the end of the shard, keeping its chunk count, so it is applied rather than lost. Whatever
still cannot be applied is reported rather than looking like a clean run: `text_skipped` in
`device_patch_summary.json`, a line in the run log, and the count in the app's `translate` step and in
its final message. On this data both loss lists are empty.

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
  Patch with the APK the phone has now: the prime layer comes from the pulled APK, so a package that was
  rebuilt against an older build's built-in assets is rebuilt again against the current one. The pull is
  skipped when the cached copy's size already matches, and re-taken when it does not.
- A rebuilt package is larger than the one it replaces, because it carries the APK's translatable content
  as well: on this data package `1` goes from 29.3 MB to 30.6 MB and package `1050016095` from 0.3 MB to
  2.5 MB. Rebuilding recompresses the package, so it is done for the two packages that gain by it and no
  others — see the coverage section for the one texture package `21` is left out for.
- Re-running over an **already patched** install translates no more text: the scanner only translates
  tables that still hold Chinese, and it reports nearly everything else as already English. To pick up
  a newer translation build, reset the game's data first (previous bullet) so the tables are Chinese
  again. Textures are not affected by that limit — the texture pass compares each device texture
  against its English payload, so a re-run picks up any texture the previous run did not write.
- Not reachable by any patch through the game data, each tried and failed on the phone: rewriting package
  `19`'s Unity prefab labels (the lobby hangs, and rewriting only the 15 prefabs that show faction names
  crashes at start with `stack corruption detected`), and the chessplayer definition `A8BC70BB87700709`
  field 37 (lobby loading stalls even when every reference in packages 1 and 14 is renamed with it).
- Two entries of package `1` sit in the downloaded index with no payload of their own — their bytes are
  the APK's — so the rebuild reads those from the APK. One further entry, `56077AC5D3F0B677`, arrives
  declaring 7,597,568 bytes while its chunk stream holds 8,519,168. The rebuild carries the stream whole
  and records the length it carries, so that entry's declared size differs from the device's by 921,600
  bytes even though the stream itself is byte-identical. It is the one place the rebuilt package differs
  from the device's copy in a value the game may read, and only a device run settles whether it matters.
- Code injection into the APK and a "prebaked" APK with translated assets were both tried and fail
  (anti-cheat kill / `IsPrebuild errorCode:151`).
