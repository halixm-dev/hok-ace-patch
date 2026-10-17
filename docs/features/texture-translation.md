---
feature: texture-translation
status: delivered
updated: 2026-10-10
branch: feat/texture-translation
commits: 290f5d8..46ed048
---

# Texture Translation

## Report

**What was built** — the patched game now renders the English textures. `tools/mobile_graphics.py`
applies one catalog edit to one device texture: a `.blocks` BC7 payload is ported block for block when
the device texture uses the 4x4 ASTC footprint, a `.blocks` RGBA32 payload is pasted onto the decoded
image and only the blocks its pixels touch are re-encoded, and an `.assets` payload replaces the whole
image. It returns `None` rather than raising for anything it cannot handle, and `MISSING_METADATA`
supplies the geometry six catalog entries omit, so the catalog itself stays untouched.

`tools/device_extensions.py` drives it. `port_graphics` reads each texture out of its Oodle chunk,
applies the edit, and appends the changed chunks to the package shard while repointing the B-tree, so
every asset keeps its chunk count and the index is never written. `extend_graphics` discovers the game
packages afresh — a texture-heavy package stages no text, so the text scan never lists it — and
returns `mode: "graphics"` summary entries totalling the textures written.

`build_patch` calls it after the text loop, and that is what makes a texture-only run install: an
empty package list used to short-circuit the push. `count_translated` returns `(text tables, textures)`
again and both GUI call sites report both. Two defects surfaced on the way and are fixed here. A
package whose staging ended with no report left its half-fitted copy in `output/` for the installer to
push, harmless only while no run got that far. And the pass needed four dependencies back in
`requirements.txt` and in `app/build_exe.py`, where omitting them builds a working exe that dies on the
first texture.

**Verification** — no device and no clean game dump were available. Everything below ran against
either the shipped catalog (398 payloads, 44 review renders) or the surviving dump at
`dist/HOK ACE Patcher Data/sessions/20260929-224052/game` — 2.6 GB, four discovered packages, and an
already-patched install. All commands from the repo root with `.venv` (Python 3.12.13).

| Command | Result |
|---|---|
| `py_compile` on every changed module | PASS |
| `tools/research/check_graphics.py` | PASS — 25 checks, 74.9 s. 44/44 previews at 0.000 mean pixel difference; 324/324 `.blocks` entries port with 0 bytes changed outside `patch_ranges`, deterministically and idempotently; 74/74 `.assets` entries replay deterministically and idempotently; ASTC round trip mean 0.796 max 4; 392 declared entries round-trip at all six footprints |
| `tools/research/check_graphics.py --game <dump copy>` | PASS — 29 checks, 101.2 s. 322 catalog textures present, 321 ported + 1 replaced wholesale, 0 skipped, 0 bytes outside `patch_ranges`; real device footprints 4x4 311, 6x6 10, 8x8 1 |
| `python app\hok_patcher.py --selftest <dump> <out>` | PASS exit 0, 37.9 s — `{"ok": true, "packages": [["15",299],["19",22],["20",1]]}`; `counts` identical to the recorded pre-change baseline (`tables` 87, `records` 184569, `translated` 58212, `already_english` 125408, `unreadable_assets` 612, `graphics` 0) |
| frozen `--selftest` after `app\build_exe.py` | PASS exit 0 — same package list; exe newer than every bundled source |
| staged shard SHA-256 across 6 runs (1 source, 5 frozen, different sessions and paths) | IDENTICAL, 6/6 shards, 0 mismatches — `15_0.db ec3bb57196cb277a`, `19_0.db b1e62138100434c5`, `20_0.db aebd4d6c0adddef1` |
| a second `port_graphics` pass over the first pass's own output | PASS — wrote 0 textures and created no output directory |
| numeric directories under `<out>` vs `summary["packages"]` | EQUAL (`15,19,20`); the half-fitted `1/` left by the old behaviour is gone |
| Independent review of `290f5d8..54bed01` | One critical — a stale claim in `resource-token-expansion.md` — plus two real gaps in the new checker: a circular `astc_layout` test, and no `install_btree_slot_map`, so a `--game` run against a patched dump silently read superseded chunks |
| Independent re-review of the fixes (`54bed01..46ed048`) | No critical findings; both gaps closed and verified independently; all four changed files accepted |

**On-device rendering is still owed.** No phone was available, so the ASTC port and the shard rewrite
are proven only against the shipped payloads, the review renders and the game dump. That is the one
thing this document does not claim.

**Journey log**

- Career-atlas sprite investigation and sprite-aware port (T14, 2026-10-10): the offset port had put 9
  labels on other sprites; fixed and device-verified on the Career screen. Lab notebook, 2026-10-10; its
  evidence is in `tools/research/career_atlas/evidence/`. Its prototype `sprite_table.py` was superseded by
  `tools/sprite_table.py` plus `atlas_sprites.py table` and deleted.
- Porting a regioned atlas block for block at the catalog's PC offsets: wrong from the day it shipped, since "applied, 0 skipped" says nothing about where a label lands; now ported by the device's sprite table (*Regioned atlases* below). Lab notebook, 2026-10-10.
- The checker's synthetic ASTC fixture on Android: not valid ASTC, it crashed the ARM64 decoder; it now encodes a known background, which fixes the fixture only. Lab notebook, 2026-10-03.
- Trusting the summary to say what the installer pushes: it pushes directories, and a half-fitted package was left in `output/`; fixed. Lab notebook, 2026-09-30.
- The new checker's first failures: two of three were the checker's own; verify a checker against a case already reasoned about. Lab notebook, 2026-09-30.
- Verifying patched textures through the runtime: it cannot read Oodle, so the staged package is read back through its own B-tree. Lab notebook, 2026-09-30.
- `wxq_patch.adaptive`'s own graphics path: dead on this content, left alone. Lab notebook, 2026-09-30.
- A slow frozen-exe `--selftest`: a pre-existing environment artefact, not the change; A/B a same-flags replica against the base commit first. Lab notebook, 2026-09-30.

## [S1] Problem

The patched game still renders Chinese on every texture: region banners, map select art, mode labels
and footers. The English images already exist — `resources/catalog/` carries **398** reviewed texture
edits and `resources/catalog/previews/` holds **44** rendered previews of them — but no code in this
repo applies any of it. `tools/build_device_patch.py` stages text tables and stops there, and
`app/patcher_core.py:51` says so in its docstring: *"This pipeline stages text packages only."*

Measured on this repo's own catalog and on the surviving 5.29 GB game dump at
`dist/HOK ACE Patcher Data/sessions/20260929-224052/game`:

| Fact | Value |
|---|---|
| Catalog texture edits (`catalog.graphics`) | 398, keyed by integer asset hash |
| Block-patch payloads (`.blocks`) | 324, all with `patch_ranges` |
| Full-replacement payloads (`.assets`) | 74, none with `patch_ranges` |
| Texture edits actually present in the dump | **322** across packages 15 (299), 19 (22), 20 (1) |
| Preview renders shipped | 44 |

Two payload families need two different code paths, and the device stores the images in a third
format again: the PC patches are **BC7** (or RGBA32) while Android stores **ASTC**, both inside
**Oodle**-compressed chunks that the current pipeline never decompresses.

The consequence is user-visible and total for textures. It is also why the app cannot install a
texture-only change even when one is produced: `patcher_core.build_translation`
(`app/patcher_core.py:351`) treats an empty `summary["packages"]` as "nothing new to translate" and
skips the push step entirely.

Three documents record the gap as accepted rather than open: `README.md` (*Translation coverage*,
*Known limits*), `AGENTS.md` (*Constraints*, *build_patch contract*), and
`docs/features/standalone-patcher-app.md` (`[S3] Out of Scope`, plus its *Coverage difference from
the reference* section). This change falsifies all three.

## [S2] Design

Add a second patch pass that runs after text staging, inside the same `build_patch` call, and
contributes `mode: "graphics"` entries to the summary.

```
game packages ──adaptive.scan──> text staging ──> output/<id>/          (today)
                                                      │
                        adaptive.discover ──> port_graphics()  <-- new pass
                                                      │  read Oodle chunk
                                                      │  english_raw()  (BC7 -> ASTC)
                                                      │  oodle_stored() (raw Oodle blocks)
                                                      │  qts_relocate.Shard.relocate()
                                                      └──> output/<id>/  shard + index
                                                      │
                                            count_translated(summary) -> (text, images)
```

### Why a `.blocks` patch maps block-for-block

BC7 and ASTC 4x4 both store 16-byte blocks on a 4x4 grid, so a PC patch that rewrites byte range
`[offset, offset+length)` maps to the same byte range of the Android texture **only when the device
texture also uses the 4x4 footprint**. Every block-patch entry present in the dump satisfies this:
`0111F5872C9B2275` is declared 404x564 and its decompressed chunk is 227 856 B, and
`ceil(404/4) * ceil(564/4) * 16 == 227856`. `astc_layout` re-derives the footprint from the raw size
and returns `(4, 4)` for it, and `None` when no footprint fits — which is the signal to skip.

### Two paths, selected by payload family

| Payload | Condition | Path |
|---|---|---|
| `.blocks`, `format == "bc7"`, footprint `(4, 4)` | 324 catalog entries | decode each patched run of BC7 rows to RGBA, re-encode those rows as ASTC 4x4, splice them into the copied Android texture at the **same offsets**. Untouched bytes stay bit-identical. |
| `.blocks`, `format == "rgba32"` | partial RGBA patch | decode the whole Android texture, paste the PC pixels at their offsets, re-encode the **whole** texture, then copy back only the 16-byte blocks those pixels touch. |
| `.assets`, either format, device size matches | full replacement | decode the PC payload wholesale, re-encode the entire image as ASTC at the resolved footprint. |
| `.assets`, device size does not match | the device revision moved | align the two images, copy the `label_box` pixels across, re-encode only the blocks that touch — see below. |

### The label splice

`astc_layout` requires an exact width and height, so a device revision that re-cuts the art by a block
row is refused outright and the texture stays Chinese. That is a whole-image replacement failing on
geometry alone, and rescaling the payload to fit would resample every glyph, so the fix is to move the
label instead.

The precondition is that the two images are the same art. The catalog records
`unrelated_blocks_identical` for exactly this reason, and it is checkable rather than assumed: compare
the two decodes row by row, leaving the label band out, and a real alignment dips sharply while
unrelated art scores flat.

- `label_rows` mirrors `label_box` into the payload's row order. `label_box` is stated in display order
  like the review renders, and the payload buffer is bottom-up. Cropping the payload at the raw
  `label_box` rows returns a blank band; mirroring first returns the text.
- `offset_layouts` derives the device geometry. A block count pins the geometry to within a block, so it
  returns the band's tallest height: every height in the band covers the same block grid, so they share
  one decode and one encode and the choice cannot change the output bytes.
- `align_rows` searches ±`ALIGNMENT_SEARCH` pixels and accepts the winner only if it stays under
  `ALIGNMENT_MAX_MEAN` **and** dips to `ALIGNMENT_MIN_GAIN` of the median offset. The second test is
  what refuses a wrong footprint or unrelated art, which score flat.
- The paste touches only the blocks the label overlaps, and `splice_label` returns `mobile_raw` untouched
  when the label already matches. That second part is what keeps a re-run idempotent: re-encoding the
  same region from a lossy decode perturbs the blocks along the label's edge, so the bytes would drift
  on every run. `LABEL_MATCH_MEAN` separates the two cases with a wide margin — measured 64.0 while the
  label is Chinese and 3.5 once spliced.

Measured on `C9E29F61B9E73713` (Three Kingdoms, catalog 592x816, device 592x824 = one extra 8px block
row): alignment offset +2, 210 blocks changed across block rows 2..8, everything else byte-identical.
Section `[9]` of `tools/research/check_graphics.py` exercises the whole path on a synthetic revision, so
none of this needs a phone or a dump.

What this does *not* do is rescue an asset the build does not carry. Of the catalog's 398 texture edits,
75 have no counterpart on the device under that hash at all — measured by scanning every package index in
a 2.86 GB dump, not inferred — and those stay Chinese however the code is written.

*Later (2026-10-05):* 72 of the 75 turned out to be in the APK's prime layer (`prime-rebuild.md`), and the
last three are reached by **device revision**. They are 404x564 effect-card band edits whose `.blocks`
payload is shared by 7-8 cards each, and package `15` carries each card under another hash. A census of all
1994 card-shaped textures there, decoding only the patch-range blocks and comparing them with the bands of
the 299 catalogued cards, finds exactly three uncatalogued cards at a mean difference of 0.01-0.02, one per
missing edit and each inside that edit's payload group; the next closest is 0.38, a blank band.
`mobile_graphics.DEVICE_REVISIONS` maps each device hash to its catalog edit and `catalog_graphics` merges
them into the set both texture paths use, so a run applies 398. `962747E1E5B73A93` is the Riverlands card
Armed Power, whose band read `大河流域` on the phone and reads *Riverlands* after the fix (device-verified,
Indonesian build). An alias is a measurement, not a guess: one joins only with a band match like these.

### Regioned atlases: port by sprite (2026-10-10)

Three catalog textures carry `regions` — `{label, sprite, box}` per sprite of a Unity atlas — and their
`.blocks` patches were drawn on the PC layout. Block-for-block porting assumes the device atlas puts each
sprite where the PC one does, which holds for the lobby atlases `C9F49510F2F67402` and
`E86DF43167CA2143` and fails for the Career atlas `13C19E4E4486B31C` (*Journey log*). So:

- **The device's sprite table is a run-time input.** `sprite_table.REGION_SPRITE_ASSETS` maps each
  regioned atlas to the asset holding its Sprite objects (all three in package `19`: `4AA2B26FF28CB65D`,
  `22BD565B3703EDA9`, `9F240FDA0FA58988`), and `port_graphics` reads the rects from the device's copy each
  run with `sprite_table.sprite_rects`. The layout has changed at least once (10-03 and 10-10 differ), so
  no rect is hard-coded. Without a table, or with a region absent or a different size in it,
  `english_raw` returns None and the texture is reported in `graphics_skipped`. There is no fallback to
  the PC offsets: that fallback is the bug.
- **Port by sprite** (`mobile_graphics.port_atlas`). Each region's English pixels are decoded out of the
  payload's own runs at the region's PC box — refused if any of its blocks lies outside `patch_ranges` —
  and composited into the same sprite's device box. Device boxes are not 4-aligned (589, 731, 466…), so
  only the touched blocks are re-encoded, from the decoded device texture with the new pixels laid over
  it. When nothing moved and there is no repo art to draw, `port_atlas` returns the offset port itself,
  which keeps the two lobby atlases byte-identical to before.
- **The old port's damage is repaired from data.** A patched phone already carries the offset port's
  footprint, and the pass reads what the phone holds. The blocks of `patch_ranges` are therefore redrawn:
  transparent, then each non-region sprite in them from `resources/sprites/<HASH>/restore/<sprite>.png`,
  pristine crops from the 10-03 dump of every sprite the footprint meets under either known layout (19).
  The 10-03 sprites are today's art: of 215 shared sprites, all but the damaged ones agree within a
  premultiplied mean of 5.3 (ASTC phase noise), the same size every one. A crop is used only while the
  device's pixels of that sprite *outside* the footprint still match it (`RESTORE_MATCH_MEAN` 12), so a
  sprite Tencent redraws is left as the device has it rather than painted over with stale art; a sprite
  with no crop keeps the device's pixels.
- **Labels the catalog never had** (`mobile_graphics.ATLAS_LABELS`): `Image_410780920` `我的皮肤` → MY SKINS
  (no catalog entry; a free translation) and `Image_920603129` `总盈利` → TOTAL PROFIT (the text table's
  "Total profit"). They are `resources/sprites/<HASH>/labels/<sprite>.png`, assembled by
  `tools/research/atlas_sprites.py labels` from the catalog's own ACHIEVEMENT POINTS glyphs (white, the
  shape all in alpha), with K, L, R and F built from that face's own strokes. Fitting 40-odd system serif
  fonts to the catalog glyphs left a mean alpha error of 48+ for the best, so no font was used. MY SKINS
  keeps MY CHESSPLAYERS' first line pixel for pixel, so the Career switch's two states share it. Every
  language uses them: the atlas's rank names are English in Indonesian too. The round `胜利` / `失败`
  badges are not drawn. The renders are straight alpha, white to the edge: the first ones were composited
  over transparent black, which greyed every antialiased edge pixel (205 and 412 of them) and would have
  shown as a dark fringe; `tools/research/career_atlas/validate_assets.py` caught it and `render_label` no longer does it.
  The user then polished both renders by hand (`tools/research/career_atlas/edit/`): a proper K and bolder SKINS, and
  native L, R and F in a tighter TOTAL PROFIT, plus 5 touched-up alpha pixels in the M of MY (two
  half-covered joins filled; nothing moved). Those PNGs are what ships; `atlas_sprites.py labels` now
  writes drafts to `--out` only, and its `--check` verifies the shipped labels' format instead of
  regenerating them. Checked: `tools/research/career_atlas/validate_assets.py` passes, `[10]` draws them at their
  device boxes (worst mean 0.34 after ASTC), `--game` on today's layer passes, and the rebuilt exe's `--selftest` stages
  exactly that atlas.
- **Re-runs.** A touched block is re-encoded only when its decoded pixels do not already show the target
  within `BLOCK_MATCH_MEAN` (6), which keeps a pristine block's own bytes. About 1500 blocks of the Career
  atlas stay above that after encoding (ASTC gets no closer than a mean of 25 at some glyph edges), so a
  re-run re-encodes them and gets the same bytes only because the encoder is deterministic for the same
  input on one platform — the same property the offset port always had.

Measured (all with `.venv`, Python 3.12):

| case | result |
|---|---|
| today's phone layer (already carrying the offset port) | every region at its device box (worst mean 2.8); labels drawn (0.4, 0.6 before the fringe fix; 0.22 worst after, `[10]`); damaged sprites from mean 11-221 apart from their crops to ≤0.1; 4164 blocks change; a second run changes nothing; 0.9 s |
| same layer with the offset port applied again first | ends 4 blocks apart from the first, decoded mean 0.000 |
| pristine 10-03 layer (its own layout) vs. it after the offset port | 2082 blocks apart (the pristine input kept blocks already within 6 of the target), decoded mean 0.025; 224 isolated antialiased edge pixels differ by more than 16 |
| `C9F49510F2F67402`, `E86DF43167CA2143`, both layers | byte-identical to the offset port |
| a full offline `build_device_patch` run over today's layer with its APK | package `19` stages 14 textures, `graphics_skipped` empty; the staged atlas read back through the staged B-tree is exactly `port_atlas`'s output, and re-porting it changes nothing; index byte-identical |
| frozen exe (`app\build_exe.py`) `--selftest` over today's layer | exit 0, `19` 14 textures; its staged atlas is byte-identical to the source run's, so the exe carries `sprites/`; re-run after the hand-polished labels landed, with the same result |
| `check_graphics.py`; `--game` on today's layer; `--skip-slow --game` on the 10-03 layer | PASS (offline 95.5 s; today 156.8 s: 140 ported, 3 ported by sprite, 67 replaced, 185 already English, 3 absent; 10-03 45.1 s: 318 ported, 3 by sprite, 1 replaced, 1 spliced, 75 absent) |

Out of reach here: `package_rebuild.make_transform` sees only `(hash, raw)` and has no package to read a
sprite table from, so a rebuild of package `19` would refuse the atlas. Nothing rebuilds `19`
(`REBUILD_PACKAGES` is empty), and refusing is the safe answer.

**Device-verified 2026-10-10 on the Career screen.** Pushed by `patcher_core` as a single change — a
fresh pull (game data 1.5.0.1, backup in session `20261010-151438`) staged exactly one texture, the
Career atlas in package `19`, byte-identical to `port_atlas`'s output with the hand-polished labels,
and the normal APK was restored. The user reports the Career screen looks right (Xiaomi M2007J3SG,
Android 12, English). Other screens that may draw the moved sprites were not walked, so nothing is
claimed about them.

### `english_raw` contract

`english_raw(mobile_raw: bytes, graphic: dict, catalog: Path, sprites: dict | None = None) -> bytes | None`
returns **None**, not an exception, for anything it cannot handle: an unknown format, a raw size that no
ASTC footprint fits, a mismatched `.assets` that will not align, a `.blocks` payload that is neither a BC7
4x4 port nor an RGBA32 patch, or a regioned atlas without a device sprite table that carries every region
at its own size. `port_graphics` counts those as skipped and the run continues. A silently skipped texture
is strictly better than a failed patch run — the same reasoning the previous feature applied to
unparseable text assets.

### Missing metadata: six entries get an in-module table

Six `.assets` entries carry no `format`, `width` or `height`, so `english_raw`'s first guard rejects
them and they can never be applied:

| Hash | Label | Payload bytes |
|---|---|---|
| `04D47725DE379AD7` | The First Lands | 159 040 |
| `078D65B9906EAB4B` | Sunset | 159 040 |
| `6A7F8C75A66ADE07` | Three Kingdoms | 159 040 |
| `CAB4D44F77EE39BD` | Central Plains | 159 040 |
| `D2317B3C316126EE` | Riverlands | 159 040 |
| `EA2F803D955BE24F` | Zhulu Plateau | 159 040 |

The reading is **RGBA32 568x70**, from four independent facts:

- `568 * 70 * 4 == 159040` exactly, and the `.assets` payload of a full replacement *is* the raw
  texture. The same identity holds for every declared RGBA32 entry: `582*804*4 == 1871712` (4 entries),
  `120*46*4 == 22080` (8), `372*102*4 == 151776` (10).
- 568 is the width of 33 other catalog textures — 27 at 568x304 and 6 at 568x792 — while **568x70 is
  declared nowhere else** in the catalog.
- All six are the same map-banner family and carry no `label_box`, `capture_row` or `footer_group`;
  only 28 of the 398 entries lack a `label_box`.
- The four with a review render decode to it at **mean absolute difference 0.000**.

`MISSING_METADATA` is keyed by the `graphic["hash"]` hex string, because that is what the loaded
catalog dict actually carries and it avoids re-parsing an integer back out of it.

**The two entries without a render (`6A7F8C75A66ADE07`, `D2317B3C316126EE`) are an inference, not a
measurement.** They are covered on the strength of the identical payload length and the same family;
if that inference is wrong the pass would re-encode a misread payload and the banner would render as
noise. This is the one knowingly-unverified decision in the change and it is called out in the Report.

`resources/catalog/` is **not** edited to carry this metadata. `AGENTS.md` records the catalog as
produced by the PC patcher pipeline and consumed here; the correction belongs in this repo's code.

### Relocation, not re-layout

New chunk slots would need lookup keys only the game's own builder can derive, so the pass keeps
**every asset's chunk count** and relocates whole chunks:

- The device texture is read as `slot.compressed_size` bytes, decompressed with `ooz.decompress`
  against `slot.uncompressed_size`.
- The changed texture is re-wrapped as **uncompressed Oodle blocks** via `oodle_stored` — a `0xCC`
  header byte followed by the raw bytes — because no Oodle compressor exists in Python, only `ooz`'s
  decompressor. The game's decoder accepts stored blocks.
- `qts_relocate.Shard.relocate` appends the new slot and repoints the shard's B-tree entry for that
  chunk's `hash1`. Keys never change, so B-tree ordering stays valid.
- The package's **index is never written**. Every asset keeps its chunk count and the *uncompressed*
  size of each chunk, so the descriptor's raw length and chunk size stay correct, and the moved bytes
  are found through the shard's own B-tree rather than through the index. The staged index the pass
  produces is therefore byte-identical to the source's. The shard itself does grow — package 15 goes
  from 297 MB to 365 MB, because the replacement data is stored rather than compressed — which is why
  the change is confined to the shard.
- Chunks are reassembled and re-split in `chunk_id` order, so that order is **assumed** to be byte
  order within an asset. Not measured: the three multi-chunk (1024x1024, four chunks each) textures in
  the game data have chunk sizes that are multiples of the row pitch, which is consistent with
  row-order splitting but does not establish it.

### Hook contract

`tools/build_device_patch.py` gains one call, after the text staging loop and before the summary is
assembled:

```python
    graphics, graphics_skipped = extend_graphics(game, catalog, output, log)
    packages += graphics
```

`tools/device_extensions.py` exposes:

```python
def port_graphics(package, catalog, catalog_dir: Path, output: Path, log) -> dict:
    """Apply every catalog texture edit that exists in <package>.

    Returns {"considered": n, "written": n, "skipped": [hash, ...]}.
    """

def extend_graphics(game: Path, catalog_dir: Path, output: Path, log) -> tuple[list[dict], list[dict]]:
    """Apply texture edits across every discovered package; return (reports, skipped)."""
```

`extend_graphics` re-runs `adaptive.discover(game, catalog)` rather than reusing `adaptive.scan`'s
plans: those plans hold only packages that produced **text** replacements, while the textures live in
packages 15/19/20, which stage no text at all. Each package that actually wrote something contributes

```python
{"package_id": ..., "mode": "graphics",
 "stage_report": {"status": "relocated", "replacement_count": count}}
```

Packages where nothing changed contribute nothing, matching `build_patch`'s existing rule that only
packages that staged appear in `packages`.

A package whose **every** texture was skipped wrote no directory, so it must not appear in
`packages` — the installer pushes by directory. It is returned in the second list instead, which
`build_patch` writes to the summary as `graphics_skipped`:

```python
{"package_id": ..., "mode": "graphics", "skipped_count": n,
 "considered_count": n, "skipped": [hash, ...]}
```

Without that list a texture the codec refuses is reported nowhere a caller can read. The concrete
cost: package `1050016095` holds exactly one catalog texture, `C9E29F61B9E73713`, whose device
revision is 592x824 while the catalog records 592x816. The geometry check skips it, the package wrote
nothing, and the run's summary therefore said nothing about it — so the Three Kingdoms card kept its
Chinese ribbon through several patch runs with no visible signal.

Ordering is load-bearing in two ways. The pass runs **after** the text loop so that a package needing
both is written once — `_package_output` reuses `output/<id>/` when text staging already created it,
and copies index + shards from the game dump when it did not. And it runs **before** the summary is
written, so its entries are counted and pushed.

### Re-run safety

`port_graphics` treats `new == raw` as already English and drops the texture before writing anything,
which keeps a second run idempotent. This holds for both paths: the full-replacement path is a pure
function of the catalog payload, and the block-patch path starts from the bytes already on disk and
only splices its ranges. Two consequences to state plainly:

- An already-patched install yields `0` textures and no summary entry, so `build_patch` reports no
  packages and the app logs "already installed" — the same behaviour as text today.
- Idempotence depends on `encode_astc` being deterministic for identical input. It is the same encoder
  with the same cached context, and the Report's six-run shard comparison measures it rather than
  assuming it.

### The unreported staged package

Making the summary non-empty exposes a latent defect in the staging loop that texture work turns into
a shipping bug.

`build_patch` drops tables one at a time until a package stages or runs out of tables. When it runs
out, `report` stays `None` and the package is deliberately left out of `packages` — but the *last*
failed attempt has already written its own copy under `output/<id>/`. Measured on the dump, that
directory for package 1 is a structurally valid package of the source's exact size with **one** of
its 15 intended replacements applied and 2 index bytes changed: 381 entries, 380 slot maps, 0.6% of
the shard differing across 2 435 runs from `0x18f0330`. It is not a result, and nothing in the
pipeline claims it is.

That was harmless only because `packages == []` made the run short-circuit before installing. With
graphics entries in the summary the install now proceeds, and `patcher_core.push_translation` pushes
**every numeric directory under `<output>`**, not the summary — so the half-fitted package would be
copied onto the phone over the user's own package 1.

The fix is at the point of failure, so the invariant holds for any consumer: when `report is None`,
`build_patch` removes `output/<package_id>` before continuing. The directory then holds exactly the
packages the summary reports, and a package whose text staging failed but whose textures change gets
a clean copy taken from the game dump by `_package_output` rather than having textures grafted onto a
half-staged text package.

### Failure modes

Only a texture `english_raw` cannot handle is skipped. Anything unexpected — a payload that will not
read, an encode that raises — is **not** caught and aborts the run, the same rule the token expansion
applies to I/O failures. Containment would be the wrong trade here: a silently mangled texture renders
as noise, which a user cannot tell apart from a wrong translation.

Two facts worth recording, both surfaced by review:

- **This pass is the first caller of the shard writer.** `qts_relocate.Shard.relocate` and
  `Shard.save` had no callers at the base commit — the text pipeline stages through
  `unity_package_installer` instead. The shard-writing path is exercised by these runs and nothing
  else, so it has no independent history to lean on.
- **`fit_only_mode` does not gate the graphics pass.** That mode exists to keep text replacements
  inside the slots they already occupy; textures are always relocated, so there is nothing for it to
  restrict. A `fit_only` run still applies every texture.

### GUI reporting

`count_translated` returns to the reference shape — a **pair**, classified on the summary's own `mode`
field:

```python
def count_translated(summary: dict) -> tuple[int, int]:
    """(text tables, textures) written by build_patch."""
    text = images = 0
    for package in summary.get("packages", []):
        count = package["stage_report"]["replacement_count"]
        if package.get("mode") == "graphics":
            images += count
        else:
            text += count
    return text, images
```

Both call sites move with it: `patcher_core.build_translation` reports `f"{text} text tables, {images}
images"`, and `hok_patcher.App.worker`'s completion message reads `f"{text} text tables and {images}
images translated. "`.

This also fixes the texture-only install path: with graphics entries in `packages`, a run whose text
staging produced nothing no longer short-circuits at `build_translation`, so the built shards get
pushed.

### Packaging

`astc_encoder` and `ooz` are native extension modules, so PyInstaller's module graph does not find them
on its own. They were removed from this repo when `wxq_patch` was found not to reference them; the
graphics pass now does, so **both** places come back:

- `requirements.txt`: `astc-encoder-py==0.1.12` (which pulls `archspec>=0.2`), `pyooz==0.0.8`,
  `texture2ddecoder==1.0.6`, `archspec==0.2.6`. Not `pypinyin`, `numpy` or `UnityPy` — those belong to
  the reference's third pass, which is out of scope.
- `app/build_exe.py`: `--collect-all astc_encoder`, `--collect-all texture2ddecoder`, `--collect-all ooz`,
  `--collect-data archspec`.

Skipping the build-exe half is invisible at source-run time and fatal in the frozen exe, so the Report verifies it
with a real build and a frozen `--selftest`, not `py_compile`.

### `install_btree_slot_map` re-check

`qts_relocate.install_btree_slot_map` replaces `QtsPackage.build_slot_map(self, wanted=None,
wanted_set=None)` with a `(self)`-only wrapper. Re-checked against the bundled bytecode, because this
pass reaches deeper into the runtime than the text pipeline: **every** caller on the device path uses
`CALL 0` — `qtsvfs.extract`, `adaptive.scan`, `unity_package_installer` (4 sites), `installer.stage_patch`
(2), `native_verify._verify_structural` (3) — and both `port_graphics` and `_package_output` call it
with no arguments. The only 1-argument callers are three functions inside `wxq_patch.pipeline`
(`load_source_tables`, `load_pc_settings_tables`, `load_content_group_tables`), all of which are called
only from `pipeline`'s own PC-side entry points. The narrowing is therefore safe here and no change is
made to it.

**2026-10-17: read only tree pages for the live-offset check.** The wrapper now reads the current
page-table pointer, rows and tree pages through `qts_relocate._read_btree_offsets`, rather than
constructing a writable `Shard` and loading its entire payload into a bytearray. Active-leaf type
and logical self-id checks, duplicate-key offset sets, stale-slot replacement and the existing
unreadable-tree fallback remain. Each map build opens the file afresh; no tree state survives a
write. This changes only the live-offset check, not the runtime chunk scanner or package writers.
Measurements and full offline output comparison are recorded in the lab notebook.

**2026-10-17: reuse small identical ASTC results.** `encode_astc` retains at most 512 results
whose RGBA input is at most 4096 bytes. The exact pixel bytes, width, height and block footprint
form the key. The native encoder's profile, quality and swizzle stay fixed at their existing
values. Larger images take the same native path, exceptions are not retained, and least-recently
used results are evicted. Retained pixel inputs are bounded to 2 MiB, plus compressed results and
Python overhead; no package or catalog state is retained. This process-local reuse also works
across the override and prime texture passes. Audit, replay and staging evidence are in the
lab notebook's small ASTC reuse section.
The Android `PackageIoProbeTest` checks the packaged cache against the native encoder on the phone;
this small app-private fixture does not establish full texture staging or screen acceptance.

**2026-10-17: avoid scanning an identical fresh texture-package copy.** `port_graphics` already
scans the source to read the catalog textures. When `_package_output` creates the output package
in this call, it copies those exact index/shard bytes; the pending chunks keep their source
offsets and every `ChunkSlot.shard_path` is retargeted to the copy. If the output directory already
exists, the pass scans that package afresh, because text or another pass may have relocated its
chunks. No slot map is retained across a write or between calls. Already-English and refused
textures still create no output directory. Full offline staging removes four duplicate scans,
with all 14 package hashes and the complete normalized summary unchanged. Evidence and timing
limits are in the lab notebook; this change has not been built or installed on Android.

### Verification boundary

This repo has no test suite, and the reference's own `unrelated_blocks_identical` field is the
statement this pass must satisfy for the block path. Three ground truths make that checkable without a
device:

1. **Preview fixtures.** For each of the 44 previews, decode the entry's `.assets` payload at its
   declared 568x70-and-friends dimensions, flip vertically, and compare to the PNG. Measured at
   **0.000** mean absolute difference for all 44 in a pre-implementation spike.
2. **The ASTC codec itself.** `encode_astc` then `decode_astc` must round-trip to within ASTC
   quantisation (spike: mean 0.80, max 4 on a synthetic 64x64), and `astc_layout` must resolve the
   dump's real raw sizes.
3. **The surviving game dump.** 322 texture edits are present and reachable, so a real `build_patch`
   run exercises the block path 321 times and the full-replacement path once.

Ground truth moves to `tools/research/check_graphics.py`, which is off the runtime path: nothing in
`app/` or `tools/` imports it and `app/build_exe.py` does not bundle it.

## [S3] Out of Scope

- The reference's third pass: `extra_text`, `unity_text`, `pb_text`, `pypinyin` romanised opponent
  names, Unity prefab text. This change keeps the codec and the graphics driver separable so those can
  be added as their own pass later.
- The reference's text-relocation machinery: `relocate_text`, `relocate_assets`,
  `exclude_extra_chunks` and `write_assets`' LZ4 branch. Text tables the in-place stager cannot fit are
  still dropped, as they are today.
- Reading `graphics_manifest.json` or `previews/` at run time. The manifest is the PC-side authoring
  artifact; the pass reads `catalog.graphics` only. `previews/` is a verification fixture, not an input.
- The PC runtime's own `wxq_patch.adaptive.apply_graphic_payload` path. It applies `patch_ranges` and
  verifies `patched_sha256` over a whole asset, which only holds for PC-format textures; instrumenting
  a scan of the dump shows it is called **0** times and `counts["graphics"]` stays 0. Nothing here
  depends on it and nothing here changes it.
- Editing `resources/catalog/` or `resources/runtime/`.
- Rewriting the graphics pass to emit compressed Oodle blocks. No Python Oodle compressor exists.
- **On-device confirmation.** No phone is available this session, so the rendered result is unproven
  and the Report says so.
