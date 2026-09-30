---
feature: prime-rebuild
status: in-progress
updated: 2026-09-30
branch: feat/prime-rebuild
commits:
---

# Prime Rebuild

## Report

## [S1] Problem

The game's data has two layers, and this repo only ever writes to one of them.

| layer | where | contents |
|---|---|---|
| **prime**, baked into the APK | `assets/bin/Data/Package/builtin/<id>/` | every asset as the APK was built |
| **override**, downloaded | `files/QtsVFSCache/packages/<id>/` | only the assets that changed since that build |

The game reads override first and falls back to prime. `Patcher.pull_game_data` pulls
`files/QtsVFSCache packages Watchdog` and nothing else, `build_device_patch` stages only into that
layer, and `device_extensions.extend_graphics` reads only override packages. **An asset that exists
only in the APK cannot be translated by this repo at all** — no text table and no texture.

Measured on this machine, game data 1.4.0.1, `dist/HOK ACE Patcher Data/installed.apk` against the
session dump `sessions/20260930-102304/game` (the measurement is recorded as
`tools/research/prime_probe.py`, added with this change):

| | package `1` | package `1050016095` |
|---|---|---|
| prime entries | 2873 (45.9 MB) | 608 (5.2 MB) |
| override entries | 403 (29.3 MB) | 2 (0.3 MB) |
| shared | 381 | 2 |
| **prime-only** | **2492** | **606** |
| of those, `catalog.known` | 408 | 0 |
| of those, **translate** | **298** (51 095 records) | 0 |
| of those, `catalog.graphics` | 0 | **71** |

Package `1`'s prime-only translated tables are the chessplayer domain in bulk — the names on the
Chessplayer screen among them — and package `1050016095`'s 71 prime-only textures are arena and map
art the texture pass currently cannot reach. 2084 of package `1`'s prime-only assets and 535 of
`1050016095`'s are covered by neither the catalog's tables nor its textures.

The user sees this as Chinese on screens whose neighbours are English: the Chessplayer page shows
`Chessplayer` and `Combat Power` translated and its portraits named in Chinese. The screen draws from
the prime layer, so no amount of override-layer translation could fix it — every chessplayer name
already had English label records staged into the override tables that *were* applied.

Separately, and already reported rather than fixed, the in-place stager loses tables at the container:
package `1` stages 81 of its 92 translated override tables and drops 11. That loss is real but it is
not the cause of the Chessplayer screen; the prime layer is.

## [S2] Design

### The builder

`resources/qtsvfs/` ships Tencent's own package builder — `QtsVFS.dll`, `QtskDB.dll` and the three VC
runtimes they load — beside `resources/adb/`, `resources/key/` and the catalog. `tools/qts_builder.py`
drives `VFS_BuildPackage` by ctypes, then aligns the output with the package it replaces:

- `Builder(bin_dir)` resolves the folder and loads both DLLs through `os.add_dll_directory`, calls
  `VFS_Initialize_Scripted` when the export exists;
- `build(package_id, assets, work)` writes each asset to `BatchAssets/<hash>.assets`, a
  `qts_layout_desc.json` and a `qts_package_desc_<id>.txt` line per block, then calls the DLL and
  returns its output folder;
- `finalize(built, package_id, file_hashes, template_node, entry_words)` drops the records only the
  builder writes (the `INGQ` global-index node, the export-setting and remain-dir node files), copies
  the original `QTSF_PACKAGE` node over the builder's, restores the per-entry flag words, and removes
  the dropped keys from the B-tree leaves.

Contracts the code must keep, each already paid for once:

- `MaxStorageSize` **must** be set (1 GiB). Left unset the builder reads uninitialised memory and
  writes one storage file per asset.
- The packed compression flag is `level << 16 | type`, level 5 — the game's own recorded level.
- Every asset handed to the builder must be non-empty; the builder cannot store a zero-byte file.
- `finalize` must find exactly the entries it was given, and a B-tree leaf must not be emptied.

### Which packages are rebuilt

`package_rebuild.REBUILD_PACKAGES = ("1", "1050016095")` — the two packages measured above to keep
translatable content only in the APK. Every other package keeps the in-place path: a rebuild lays the
whole container out again, so it must be reserved for packages that gain something.

### `rebuild_package`

For a rebuilt package the output override package holds

- **every asset the override package already has**, translated where the transform changes it and
  byte-identical otherwise, and
- **every prime-only asset the transform actually changes.**

A prime-only asset that needs no change is deliberately **left out**, so the game keeps reading it
from the APK instead of carrying a second copy.

An asset listed in the override index whose bytes cannot be read (the flag-word entries whose payload
is the APK's are read from prime instead) aborts the package: `rebuild_package` logs and returns
`None`, and the package falls back to the in-place path. One unreadable asset must not cost the
package its patch. Two of package `1`'s 403 entries are prime-backed this way (`92D3EE5696C9D644`,
`5B905F540C9F7046`), and an entry whose bytes are empty counts as unreadable too, because the builder
cannot store a zero-byte file.

One entry, `56077AC5D3F0B677`, arrives declaring 7,597,568 bytes while its 28-chunk stream holds
8,519,168. The builder derives an entry's chunking from the bytes it is handed, so a rebuilt package
cannot both carry that stream whole and record the device's shorter figure. The stream is carried —
dropping 921,600 bytes of data we do not understand is the worse guess — and the length it actually
holds is recorded, which leaves the rebuilt entry self-consistent where the device's own copy is not.
That length and the 16-byte token derived from it are the only values the rebuilt package differs from
the device's copy in for any entry: every other entry keeps its bytes and its declared size, and the one
field that differs elsewhere is the record's own offset, which necessarily moves when the index is
re-laid-out. The stream itself — what the game decompresses — is byte-identical, and only a device run
settles whether the recorded length matters.

Before anything is staged, every asset is read back through the same `QtsPackage` code path the game
data goes through and compared byte-for-byte, and the package node must equal the original's; any
difference raises rather than producing a package to install.

### The transform, and what it reports

`make_transform(catalog, catalog_dir, log)` builds the per-asset decision shared by both layers:

| asset | action |
|---|---|
| `catalog.known` | `adaptive.translate_table`; a table the runtime refuses is logged and left alone |
| `catalog.graphics` | `mobile_graphics.english_raw`; must return the same length |
| `extra_text.SAFE_ASSETS` | `pb_text.rewrite` with the catalog's official English |
| anything else | no change |

It returns `bytes \| None`, where `None` means "leave the bytes as they are". Those bytes were left
alone for two different reasons, and the texture pass's accounting depends on telling them apart — a
texture that is already English is done, a texture the codec refuses is a skip. The caller therefore
passes in a `refused: set[int]` the transform adds to for a `catalog.graphics` asset whose
`english_raw` returned `None` or a different length. The set is single-threaded and the caller clears
it between packages.

### Skipping the rebuilt ids

A rebuilt package no longer matches the device's copy, so no other pass may touch it: the in-place
loop skips a package whose id is in `rebuilt`, and the extension pass takes `skip=rebuilt`. Without
that the in-place stager would re-derive a package the rebuild already replaced, and the extension
pass would apply textures to a container it did not build.

### The relocation pass

v1's second staging path, ported into `device_extensions.py`: text that the in-place stager cannot fit
is appended to the end of the shard instead of being dropped.

- `exclude_extra_chunks(package, replacements, work, log)` copies the plan without the tables that
  would need more chunks than the original holds. New chunks need lookup keys only the game's builder
  can derive; the stock stager would invent them. It returns the pruned directory and the excluded
  hashes.
- `write_assets(package_dir, jobs)` writes new raw bytes for assets of an already staged package,
  keeping each asset's chunk count and enlarging its chunk size instead, and adjusting the entry's raw
  length and chunk-size words in the index. It returns the hashes it wrote and the ones it refused.
- `relocate_text` is `write_assets` over the tables the loop did not stage; `relocate_assets` is
  `write_assets` over the extra-text pass's jobs.

`extend_graphics` stays the single entry point for the extension passes and keeps its two-list return,
gaining `dropped_text` and `skip` arguments. In order it runs `relocate_text` over the collected
tables, the graphics pass over every discovered package, and the extra-text pass.

### How relocation and `text_skipped` interact

`text_skipped` means text that was **translated and then not applied**, and relocation is a way of
applying it, so the two must be reconciled or the report will claim a loss that did not happen.

`note_missing` currently runs inside the loop over `plan - staged`. It moves after the extension pass,
and the set it reports is `plan - staged - relocated`, where `relocated` is the set of hashes
`write_assets` actually wrote. A table excluded from the in-place plan and then relocated end-to-end
is therefore not reported at all, and a table that relocation also refused is.

On the 1.4.0.1 data this machinery is expected to be **inert for package `1`**: the rebuild absorbs
the whole package before the loop reaches it, so the 11 previously dropped tables arrive through the
rebuild and `text_skipped` becomes empty. It is ported because the drop is data-dependent — 1.3.0.4
lost 15 of 92 — and because it is the only path that recovers a table for a package the rebuild does
not cover.

### The extra-text pass

Non-catalog display text that the PC catalog has no table for, ported as three modules:

- `pb_text.py` — schema-less protobuf string rewriting. Length-delimited fields are classified
  heuristically: valid UTF-8 without control characters is text, a field that parses completely as a
  message is recursed into, anything else stays opaque.
- `unity_text.py` — Unity 2022.3 `SerializedFile` string swap. Tencent sets the "type tree enabled"
  flag but writes zero nodes, so only the object table is parsed; only MonoBehaviour (class 114)
  objects are touched, because GameObject names can be lookup keys.
- `extra_text.py` — the allowlist and the romanisation.

`SAFE_ASSETS` is an **allowlist**, not a blocklist: rewriting every matching string in the config
assets broke the login screen, because some Chinese there is a lookup key rather than a label. It is
`BOT_NAME_ASSETS` plus `DISPLAY_ASSETS`. AI opponent names (~11 000) are romanised with `pypinyin`
because the catalog has no official translation for them. Packages `10` (skill-editor labels) and `14`
(gameplay scripts) are excluded: Chinese there is logic. `UNITY_TEXT_PACKAGES` stays empty — rewriting
package 19's prefab labels hangs the lobby, and rewriting only the faction labels in the 15 prefabs
that show them crashes the game with `stack corruption detected`.

The hashes already tested and their failures stay in the comments beside the allowlist, so the next
addition starts from the record rather than repeating it.

### What the run reports

The summary keeps both existing loss lists and gains a `rebuilt` mode.

```json
"packages": [
  {"package_id": "1", "mode": "rebuilt", "source_package": "<device override dir>",
   "fit_summary": null, "stage_report": {"status": "rebuilt", "replacement_count": 400},
   "assets": 701, "translated_downloaded": 102, "added_from_apk": 298, "textures": 0},
  {"package_id": "1050016095", "mode": "rebuilt", "source_package": "<device override dir>",
   "fit_summary": null, "stage_report": {"status": "rebuilt", "replacement_count": 72},
   "assets": 73, "translated_downloaded": 1, "added_from_apk": 71, "textures": 72}
]
```

- A rebuilt package's `replacement_count` counts the assets the transform **changed** — translated
  override assets plus prime-only assets it added — not the assets it carried. `assets` is the total
  the rebuilt package holds. On this data that is 400 of package `1`'s 701 and 72 of
  `1050016095`'s 73.
- `textures` is how many of those `replacement_count` assets were `catalog.graphics`.
- `count_translated` must therefore not classify a rebuilt package by mode alone: for
  `mode == "rebuilt"` it adds `replacement_count - textures` to the text count and `textures` to the
  image count. Package `1` is text-only and `1050016095` is texture-only, so classifying on the mode
  alone would report one of them as the other kind.
- `fit_summary` is `null` for a rebuilt package: the builder lays the container out, so nothing
  competes for slack and the in-place retry loop's diagnostic does not apply.
- A texture the rebuilt package's transform refused is reported in the existing `graphics_skipped`
  list, with the same entry shape the texture pass uses (`skipped_count`, `considered_count`,
  `skipped`). Its meaning is unchanged — a texture that was never translated — and the
  `refused` set above is what makes the distinction from "already English" possible.
- `text_skipped` keeps its exact meaning: text that was translated and then **not applied**. A table
  the rebuild's transform refused was never translated, so it is logged per asset and does not enter
  either list; a table the in-place loop could not stage but relocation wrote is not a loss either.
  See the reconciliation above. On this data there are no refusals in package `1`.
- When `apk` or `builder_dir` is missing, `build_patch` logs that prime-only content stays Chinese and
  stages exactly as it does today. That keeps `--selftest` and the offline CLI usable without the
  DLLs.

### Where the prime layer comes from

`Patcher.prepare_normal_apk` already pulls the installed APK to `work/installed.apk` — or builds
`work/normal.apk` from it when it has to re-sign — and the `apk` step runs before `translate`. So
`build_translation` passes `apk=self.normal_apk` and `builder_dir=BUNDLE / "qtsvfs"`. The APK that
supplies the prime layer is the one installed on the phone.

`build_patch` gains keyword-only `apk: Path | None = None` and `builder_dir: Path | None = None`, and
`main()` gains `--apk` and `--builder`.

### Packaging

`resources/qtsvfs/` joins the shipped resources and `app/build_exe.py` adds it with `--add-data`, so
the frozen exe can rebuild on any machine. `pypinyin` joins `requirements.txt` and `HIDDEN_IMPORTS`.

### Documentation

`docs/agent-guide-untranslated-strings.md` is the method this design ports, and it is currently
Indonesian — the only non-English artifact in the chain. It is rewritten in English in place.

## [S3] Out of Scope

- **Code injection into the APK, and prebaked APKs with translated assets.** Both were tried and
  fail (anti-cheat kill / `IsPrebuild errorCode:151`).
- **Package 19's Unity prefabs, and the Card Info faction ribbon.** Rewriting the prefabs hangs the
  lobby; rewriting only the faction labels in the 15 that show them crashes the game.
  `UNITY_TEXT_PACKAGES` stays empty. The ribbon is a known limit documented in `README.md` and this
  change does not address it.
- **The chessplayer definition `A8BC70BB87700709` field 37.** Changing it stalls lobby loading even
  when every exact reference in packages 1 and 14 is renamed.
- **Assets neither the catalog nor the allowlists cover.** 2084 of package `1`'s prime-only assets
  and 535 of `1050016095`'s are uncovered and stay as they are; the extra-text pass only reaches
  allowlisted display assets.
- **The catalog's 75 edits with no device counterpart.** Their asset ids are not in the mobile build,
  so no code change can apply them.
- **Coverage claims.** The result is the staged text tables plus the catalog's textures. The texture
  count is reported as *applied*, never as *covered*, and no run is described as a complete
  translation.
- **Verified devices.** Nothing here is confirmed on a phone by this document. The device loop in the
  guide's §6 runs after the port, one change per test, and no string or texture is claimed translated
  until the user has seen it after login.

## Tasks

- [ ] T1: Ship Tencent's builder in `resources/qtsvfs/` and port `tools/qts_builder.py` — acceptance: `Builder(resources/qtsvfs)` loads both DLLs, `VFS_Initialize_Scripted` returns 1, and `package_node` on a real override index returns the package node bytes (covers: S2)
- [ ] T2: Port `tools/package_rebuild.py` and `read_raw` — acceptance: rebuilding package `1` from `installed.apk` against the 102304 dump produces a package whose every asset reads back byte-identical and whose `QTSF_PACKAGE` node equals the override's, and a prime-only asset the transform leaves alone is absent from it (covers: S2; depends: T1)
- [ ] T3: Port the relocation pass into `tools/device_extensions.py` — acceptance: a text asset too large for its chunks is relocated with its chunk count preserved, its entry's raw length and chunk size updated, and its bytes read back identical (covers: S2; depends: T2)
- [ ] T4: Port the extra-text layer as `tools/pb_text.py`, `tools/unity_text.py` and `tools/extra_text.py`, and add `pypinyin` to `requirements.txt` — acceptance: `pb_text.rewrite` round-trips a known allowlisted asset and `extra_text.plan_package` selects only hashes in `SAFE_ASSETS` (covers: S2)
- [ ] T5: Rewire `tools/build_device_patch.py` — acceptance: on the 102304 dump the run reports `mode: "rebuilt"` for packages `1` and `1050016095`, package `1`'s entry carries `added_from_apk: 298` and `textures: 0`, `1050016095`'s carries a `textures` equal to the number of catalog textures the rebuild changed, any texture either rebuild refuses appears in `graphics_skipped`, `text_skipped` is empty, and every file of the dump is byte-identical afterwards (covers: S2; depends: T2, T3, T4)
- [ ] T6: Wire the app — acceptance: `patcher_core.build_translation` passes the APK and the bundled builder, `count_translated` splits a rebuilt package by `textures`, `--selftest` still runs and logs the fallback when no APK is given, and `app/build_exe.py` ships `resources/qtsvfs` and collects `pypinyin` (covers: S2; depends: T5)
- [ ] T7: Update the documentation — acceptance: AGENTS.md's `build_patch` contract lists `mode: rebuilt`, the `textures` field, the `graphics_skipped` interaction and the new arguments; README's coverage section describes the prime layer and what rebuilding it applies; and `docs/compose/spec/text-drop-report.md`'s `[S1]` attributes the Chessplayer screen to the prime layer while keeping the drop-loop finding (covers: S2; depends: T5)
- [ ] T8: Rewrite `docs/agent-guide-untranslated-strings.md` in English in place — acceptance: the file is English, its sections keep their order and their tested-hash records, and the commit notes the change (covers: S2)
- [ ] T9: Record the measurement as `tools/research/prime_probe.py` — acceptance: running it from the project root reprints the `[S1]` table's numbers for packages `1` and `1050016095` without a phone, and nothing in `app/` or `tools/` imports it (covers: S1)
