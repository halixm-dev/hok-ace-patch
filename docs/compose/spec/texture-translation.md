---
feature: texture-translation
status: designed
updated: 2026-09-30
branch: feat/texture-translation
commits:
---

# Texture Translation

## Report

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
`docs/compose/spec/standalone-patcher-app.md` (`[S3] Out of Scope`, plus its *Coverage difference from
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
| `.assets`, either format | full replacement | decode the PC payload wholesale, re-encode the entire image as ASTC at the resolved footprint. |

### `english_raw` contract

`english_raw(mobile_raw: bytes, graphic: dict, catalog: Path) -> bytes | None` returns **None**, not an
exception, for anything it cannot handle: an unknown format, a raw size that no ASTC footprint fits, or
a `.blocks` payload that is neither a BC7 4x4 port nor an RGBA32 patch. `port_graphics` counts those as
`skipped (format not supported)` and the run continues. A silently skipped texture is strictly better
than a failed patch run — the same reasoning the previous feature applied to unparseable text assets.

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
- The package's index keeps its integrity token; only the raw length and the chunk size move, exactly
  as `device_extensions.write_assets` does in the reference.

### Hook contract

`tools/build_device_patch.py` gains one call, after the text staging loop and before the summary is
assembled:

```python
    packages += extend_graphics(game, catalog, output, log)
```

`tools/device_extensions.py` exposes:

```python
def port_graphics(package, catalog, catalog_dir: Path, output: Path, log) -> int:
    """Apply every catalog texture edit that exists in <package>; return textures written."""

def extend_graphics(game: Path, catalog_dir: Path, output: Path, log) -> list[dict]:
    """Apply texture edits across every discovered package; return summary entries."""
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
  with the same cached context, and T8 measures it rather than assuming it.

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

Skipping the build-exe half is invisible at source-run time and fatal in the frozen exe, so T5 verifies
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

## Tasks

- [ ] T1: Add `tools/mobile_graphics.py` — the ASTC/Oodle codec (`english_raw`, `astc_layout`,
      `encode_astc`, `decode_astc`, `decode_pc`, `oodle_stored`, `oodle_decompress`) with the
      `MISSING_METADATA` fallback for the six metadata-less hashes — acceptance: `english_raw` returns
      changed bytes of the same length for a real `.blocks` BC7 4x4 entry, a `.blocks` RGBA32 entry and
      a `.assets` entry from the catalog; returns `None` for a raw size no footprint fits; and resolves
      all six metadata-less hashes to RGBA32 568x70 (covers: S2)
- [ ] T2: Add `tools/device_extensions.py` with `port_graphics` and `extend_graphics` — acceptance:
      `port_graphics` over the dump's package 15 stages 299 textures into a fresh output directory while
      the source package's index and shard are byte-identical before and after (covers: S2; depends: T1)
- [ ] T3: Call `extend_graphics(game, catalog, output, log)` in `build_patch` after the text staging
      loop — acceptance: a full `build_patch` run over the dump returns `mode == "graphics"` entries for
      packages 15/19/20 whose `replacement_count` totals 322, and the summary written to
      `output/device_patch_summary.json` contains them (covers: S2; depends: T2)
- [ ] T4: Restore `count_translated` to `(text, images)` and update `patcher_core.build_translation`
      and `hok_patcher.App.worker` — acceptance: given a summary holding both modes, text and images are
      counted separately; a summary with only a `graphics` entry reports `0 text tables` and a non-zero
      image count rather than being treated as "already installed" (covers: S2; depends: T3)
- [ ] T5: Restore the graphics dependencies in `requirements.txt` and the four PyInstaller flags in
      `app/build_exe.py`, then rebuild — acceptance: `.venv` imports `astc_encoder`, `ooz` and
      `texture2ddecoder`; `app/build_exe.py` succeeds; and the frozen exe's `--selftest` over the dump
      completes with 322 textures staged instead of dying on the first one (covers: S2; depends: T3)
- [ ] T6: Add `tools/research/check_graphics.py` — acceptance: it compares all 44 previews (0.000), round-trips
      `encode_astc`/`decode_astc`, resolves `astc_layout` for the dump's real raw sizes, and asserts that
      a BC7 `.blocks` port changes no byte outside `patch_ranges`; it exits non-zero on any failure and
      nothing in `app/` or `tools/` imports it (covers: S2; depends: T1)
- [ ] T7: Update `README.md`, `AGENTS.md` and `docs/compose/spec/standalone-patcher-app.md` —
      acceptance: no document still claims textures are not translated, that the pipeline has no
      `graphics` mode, or that the app reports text tables only; the app spec's `[S3]` deferral is marked
      superseded (covers: S2; depends: T4)
- [ ] T8: Measure re-run safety and determinism — acceptance: a second `port_graphics` pass with the
      first pass's output as its source reports 0 textures written, and two independent `build_patch`
      runs over the same dump produce byte-identical shards (covers: S2; depends: T3)
- [ ] T9: In `build_patch`, remove `output/<package_id>` when a package ends with no `report` —
      acceptance: after a run over the dump, the numeric directories under `<output>` are exactly the
      package ids in `summary["packages"]`, and the previously-leaked package 1 directory is gone
      (covers: S2; depends: T3)
