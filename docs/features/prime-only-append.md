---
feature: prime-only-append
status: delivered
updated: 2026-10-03
branch: feat/prime-only-append
commits: c3f23b3..e4c83ad, then uncommitted work on top of 1f07c10
---

# Prime-Only Append

## Report

**What was built** — Catalog assets that exist only in the APK can now reach an override package
without laying the container out again. `tools/qts_insert.add_assets` takes the asset's index record and
its chunk slots from the APK's own prime copy of the package, which already carries the asset, and
appends them to the target's shard and index, linking each into the B-tree that indexes it
(`qts_relocate.Shard.append_slot`, `append_record`). Nothing else in the target moves — its records,
existing asset records stay in place; tree pages gain keys and may use the measured root-leaf
split, while payloads grow at the end — so the
package keeps the shape the game already mounts. `package_rebuild.add_prime_only` finds what this
applies to (catalog entries present in the APK's prime package and absent from the device's override
copy) and `build_patch` runs it last, sharing the rebuild's transform and keyed on the packages a
rebuild already replaced.

On this build the pass resolves to exactly one package and one texture. Of the APK's 182 packages,
three hold catalog content in prime — package `1` (497 tables), `1050016095` (72 textures) and `21`
(the Central Plains panel) — and the first two are already rebuilt whole, so they are in `skip`. That
one asset is the Central Plains Card Info ribbon, the only catalog edit that could not previously be
applied: it exists only in package `21`, and rebuilding `21` costs the Factionless card. On the phone
the ribbon now reads `Central Plains` where the previous capture read `河洛`, and the Card grid still
draws Yixing with full art.

**Later: the builder left this pass.** The append used to have Tencent's builder make a throw-away
package holding the new asset and copy the record out of that. It now harvests the record from the APK's
prime copy, because the record's two lookup keys are identity functions — an entry key varies only with
the asset, a chunk's `hash1` only with the asset and the chunk index — and the 16-byte descriptor token
beside them, which does depend on the content, is never checked: the in-place stager rewrites content
and updates only the raw length and the chunk size, never the token
(`tools/research/key_derivation_probe.py --stager`, 99 rewritten records of a phone-pushed run). Offline
the result is the same package. Against the cycle's builder-produced `out/21`, the new run stages the
same 4867 entries with the same entry key `3E2FE941` and the same chunk `hash1` `4D90FAD807B56200`,
every asset reads back byte-identical, and no asset's bytes differ between the two runs. The staged
shard is 16384 bytes larger, because the payload is re-encoded the way `write_assets` re-encodes one —
Oodle stored blocks, since Python has no Oodle compressor.

**Later: a package whose tree is full can be appended to as well.** The append was limited to packages
whose index tree had room. Package `1`'s is one leaf of 404 keys and its 298 prime-only assets take it
to 702, so it was rebuilt whole instead. `qts_relocate.Shard.split_root_leaf` now grows a single-leaf
tree into two leaves plus an internal root — the shape Tencent's own builder produces — and `insert_key`
splits and retries instead of raising. The split reproduces a builder-made tree's page table **byte for
byte** (`artifacts/device-run/leaf_split_check.py`), and package `1`'s full prime-only set then appends
with **no builder at all**: 297 of 298 assets, zero pre-existing entries lost, zero read-back
differences, the index tree at 2 leaves of 342/359 against the builder's 351/351, and 700 entries
against the builder's real 701. One asset, `3A70308AAF6F18F8`, is refused rather than written: a 60-byte
table whose LZ4 block would land exactly on its own length, which this format cannot tell apart from a
*stored* chunk, so it is named in the log and stays Chinese. Rebuilding package `1` is therefore no
longer necessary; the section below empties `REBUILD_PACKAGES`, which is what puts that on the shipped
path.

**Later: `REBUILD_PACKAGES` is empty, so the append owns those packages.** With no package named for a
rebuild, `1` and `1050016095` take the in-place path first and are appended to last, and Tencent's builder
has no caller left in the pipeline. An offline run over the dump with `--apk` and `--builder` reports **no
`rebuilt` entry** and `added-from-apk` for `1` (297 assets), `1050016095` (71) and `21` (1); package `1`
is staged in place first (79 assets, 11 more relocated, 4 by the extra-text pass), and the append lands on
that copy rather than replacing it.

**Later: the shipped configuration ran on the phone.** The staged package `1` — 700 entries, the index
tree at 2 leaves of 342/359, every one of its 297 prime-only tables appended and read back — was pushed
onto the 1.4.0.2 device layer and the game launched on it: it gets past startup, and the content that
only ever existed inside the APK now reads English. The Chessplayer Card page, whose names are among
those 297, is the page that proves it. That is this pass's acceptance, and it answers the question the
empty `REBUILD_PACKAGES` left open: with no package laid out whole and no `QtsVFS.dll` in the run, the
appended package mounts and behaves. The same device round turned up one symptom that is **not** this
pass's: on the ACE Tournament encyclopedia's Talent Card grid every tile prints its raw `#BE08...` ref
where a name belongs, while the same card's detail pane, its description and every other tab render
English. The Talent Card sections below record this regression: a fresh unpatched baseline captured on 2026-10-03 renders the grid
names in Chinese, overturning the earlier claim that the client cannot resolve them.
**Fixed 2026-10-03:** the same full English dictionary works with its original 307200-byte chunk size
and a measured native key for a second chunk. The complete patch is installed and device-verified:
grid names, Arena Tiger's English details, and the neighboring card tabs all work. The updated patcher
also repairs an older already-English package, without loading the builder during a normal run.

That first run also exposed a disagreement between the two paths, and closing it is part of this change.
`adaptive.scan` recognizes a localization table by shape and resolves one the catalog has no `.blocks` for
whenever every string it holds is in the catalog's string map, so the in-place path staged two tables the
rebuilt path never would: `3914DBBFECD1E54D` and `63922EF4D4C86526`, both in package `1`, neither in
`catalog.known`, and neither cleared by a device cycle. The run reported 393 text tables against the
rebuild's 392 — two gained, one lost. No cycle could have justified the two, because
`3914DBBFECD1E54D` turns out to be **unobservable**: a sweep of all 277 packages finds its one key
`#07B0CCFD72A346C9#` referenced by exactly one asset, `3644C4ACF0410B1E`, a 日月行者 draw-type row windowed
2025-09-10 to 2025-10-10, so no live screen can draw that label and no phone can give it a verdict.

`build_device_patch._drop_uncatalogued_tables` therefore drops every replacement the catalog does not
list, which makes the primary pass mean *the catalog's tables* and returns anything else to the
`extra_text` allowlist, where the cycle rule lives. The census in the summary is adjusted with it
(`tables` 92 → 90, `records` and `translated` −4 each), so a shortened plan cannot leave the census
claiming more than the run staged.

Against the cycle's builder-produced rebuild the result is now the same package wherever the two can be
compared. Packages `1050016095` (73 entries) and `21` (4867) hold exactly the assets the rebuild holds,
and so does package `1` on every catalog table — **`3914DBBFECD1E54D` and `63922EF4D4C86526` are Chinese
in both, and byte-identical**. Three differences remain, and each one is a rule rather than a defect:

- **`3A70308AAF6F18F8` is the one asset the rebuild applies and the append cannot** — the unencodable
  60-byte table above, and the whole of the 392 against this change's 391.
- **`5B905F540C9F7046` and `92D3EE5696C9D644` are entries the override index lists with no bytes of
  their own.** `read_raw` returns nothing for them in the download and in the append's copy; the rebuild
  materialized them out of prime. Neither is in the catalog and the rebuild did not translate them (135
  and 126 Chinese characters), so the game reads them from the APK either way. The append is the copy
  that leaves the entry pointing where it always pointed.
- **`1D13F7315D89BAC3` and `AF1FB540A2B8CB52`** are the builder's own bookkeeping nodes, which only a
  rebuild carries.

The refused asset also sits in a package the pass *did* add to, which the old `append_skipped` had no
shape for: it was raised only when a package gained nothing. `add_prime_only` now reports the refused
share of a package it added to as well, so the summary carries the one table that stays Chinese — without
it the run reads as if all 298 had been applied.

**Later: the gate in front of the append is gone.** The pass used to run only when a QtsVFS builder was
available, because it once needed one to mint each record. It harvests the record from the APK's own prime
copy now, so it is gated on the **APK** — the thing it actually reads — and a run given the APK without
the DLLs stages the same patch. Measured: the same command over the same dump, with and without
`--builder`, produces **byte-identical `.db` files for all six packages** and identical values for every
field of the summary — `counts`, each package's id, mode and replacement count, and all three skip lists.
With no package named in `REBUILD_PACKAGES` the builder was only ever constructed and never called, so
nothing changed except that `resources/qtsvfs/` is no longer needed to reach the primed content.
`patcher_core.build_translation` now passes the APK whether or not it found a builder.

Things that go wrong are reported rather than fatal. A B-tree leaf already holding 510 keys, a device
copy split over several shards, or the encoder refusing a payload land in the run's `append_skipped` list
and are counted by the app as images and as tables that stay in Chinese: one entry per package the pass
could not add to at all, plus the refused share of a package it did. A staged copy, a device index or a
prime package that will not read is logged and skipped with no entry, because there is no count to give
it. A read-back that disagrees **raises**, because a record linked under the wrong key is invisible until
the game fails to find it.

**Verification** — every command below ran from the worktree; scripts are research scratch under
`artifacts/probe-append/` (gitignored).

| command | result |
|---|---|
| `python artifacts\probe-append\t1_btree.py` | PASS — keys inserted into copies of the phone's own package `21` are found by a search walked from the tree's root, and the bytes at the offset it returns are the record that was appended; nothing outside the tree pages, the header's data-end words and the new record changed (0 bytes); a leaf padded to 510 keys raises `TreeFull` |
| `python artifacts\probe-append\t2_append.py` | PASS — the real append into a copy of the phone's override `21`: the panel reads back translated (43 168 B ASTC, geometry preserved), all 4866 pre-existing entries read identically, one key added per tree, no leaf over 510 |
| `python artifacts\probe-append\t3_pass.py` | PASS — `add_prime_only` over the phone's 278-package layer and the patcher's own APK: one package, one texture; the device's copy is untouched; a second run reports nothing and adds no key |
| `python artifacts\probe-append\t3_skip.py` | PASS — both skip paths driven end to end: an index whose leaves are padded to 510 keys and a device copy with two shards each come back as one `append_skipped` entry naming the package, the reason and the one texture it would have written, leave no staged directory behind, and reach the counters as one image and no tables |
| `python artifacts\probe-append\t4_gate.py` | PASS — with no APK or builder the pass does not run and the pipeline logs the same line it always did |
| `build_device_patch.py` over the phone's layer (`--apk installed.apk --builder resources\qtsvfs`) | 6 packages staged, `21` reported as `added-from-apk` with `textures: 1`, `append_skipped`/`text_skipped`/`graphics_skipped` all empty, output directories exactly the reported packages |
| `python artifacts\probe-append\t7_verify.py run-t4` | PASS — 13 checks, including the game dump's own `1.db`/`21.db`/`21_0.db` unchanged by MD5 after the run |
| `python artifacts\probe-append\t7_rerun.py` | PASS — a second run into the same output does not report `21` again, leaves the panel byte-identical (md5 `9525ef58…`), adds no duplicate B-tree key, and does not grow the package |
| `python artifacts\probe-append\summary.py run-t4` | `count_translated` = (392 tables, 395 images) — the appended texture counted as an image; before the classification fix it read (393, 394) |
| `python app\build_exe.py`, then `--selftest artifacts\game-dump` | the frozen exe builds, carries `qts_insert` in its archive, and stages 5 packages (1, 1050016095, 15, 19, 20) — no `21`, which is the gate: the headless check passes no APK or builder |
| `build_device_patch.py --apk artifacts\tencent-pristine-1.1.1.apk --builder resources\qtsvfs` over `artifacts\game-dump`, with `REBUILD_PACKAGES = ()` | PASS, exit 0 in ~75 s; **no `rebuilt` entry**; `1` `full` 79 + `relocated-text` 11 + `extra-text` 4 + `added-from-apk` 297, `1050016095` `graphics` 1 + `added-from-apk` 71, `15`/`19`/`20` graphics, `21` `added-from-apk` 1; `text_skipped` and `graphics_skipped` empty; `append_skipped` one entry naming the refused table in `1` |
| the same run before the gate, against `artifacts\cycles\base2\out` (the DLL rebuild) | package `1` differing in 4 assets: `3914DBBFECD1E54D` and `63922EF4D4C86526` English here and Chinese under the rebuild, `3A70308AAF6F18F8` the reverse, and 2 prime-backed entries the rebuild materialized. That disagreement is what the gate below closes |
| `_drop_uncatalogued_tables` — offline run over the same dump | PASS — names and drops exactly `3914DBBFECD1E54D` (1 string) and `63922EF4D4C86526` (3), leaves package `1`'s staged tables at 90, and takes the census with it: `tables` 92 → 90, `records` 185 043 → 185 039, `translated` 181 617 → 181 613, `unknown` unchanged |
| the same run against `artifacts\cycles\base2\out` | PASS — packages `15`, `19`, `20` and `21` identical (0 differing of 3990/22 364/29 668/4867 shared), `1050016095` identical on all 73, and package `1` differing only in the 3 rules above (`3A70308AAF6F18F8` plus the 2 prime-backed entries), with `3914DBBFECD1E54D` and `63922EF4D4C86526` **byte-identical and Chinese in both** |
| `app\hok_patcher.py --selftest artifacts\game-dump artifacts\selftest-out` | PASS — `{"ok": true, "packages": [["1", 79], ["1", 11], ["1050016095", 1], ["15", 299], ["19", 22], ["20", 1], ["1", 4]]}`; `79` is the gated plan, the rest unchanged |
| `tools\research\check_graphics.py` | PASS, 114 s, `all checks passed` |
| `patcher_core.count_translated` / `count_untranslated_text` on the gated summary | `(391, 395)` and `1` — the appended texture counted as an image, and the refused table counted as one that stays Chinese |
| `python artifacts\device-cycle-t9\locate_label.py --asset 3914DBBFECD1E54D --asset 7E3F57D727FA8625` | PASS — sweeps all 277 packages for those keys; `3914DBBFECD1E54D`'s key is referenced by one asset (`3644C4ACF0410B1E`, windowed 2025-09-10 to 2025-10-10, icon `Icon_Draw_Type_RYXZ`), `7E3F57D727FA8625`'s by two with no window |
| the same command over the same dump, with and without `--builder` | PASS — all six packages' `.db` files **byte-identical**, and every summary field equal (`counts`, each package's id/mode/count, `text_skipped`, `graphics_skipped`, `append_skipped`). The no-builder run logs `no QtsVFS builder given: no package is laid out whole; the append covers the rest` and still reports `added-from-apk` for `1` (297), `1050016095` (71) and `21` (1) |
| device cycle | lobby in English, Card grid with Yixing's art, ribbon `Central Plains`; `QtsVFS.log` — `MountPackage 21, override, 0 => succeed! pkgHash:8591676242410099349 basePkgHash:14935366421268903059 state:4 prebuild:0`, `ScanJob ... [after]brokenFiles count 0, size 0 ... errorCode=0`, `VFS_GetBrokenFileCount builtin, 0 size 0`; `normal1.log` has 0 lines matching `errorCode:[1-9]|QtsfFixer|FixFile|crc not match|corruptedPackages|IsPrebuild` (`artifacts\device-cycle-t8\normal1-repair-lines.txt`). Phone file check: `21_0.db` 40 747 008 B (pristine 40 730 624) |

An independent review of `c3f23b3..e4c83ad` found no critical defect. Three of its findings were fixed
before this document was finalized: `AGENTS.md` claimed `append_skipped` covers a staged copy that will
not read, which the pass logs and skips without an entry; the counters' skipped-append half had no
artifact feeding a non-empty list, which `t3_skip.py` now supplies; and the app's summary was gated on
translated text alone, so a run that only skipped images would have called itself "already installed".
Its remaining point stands as a release note: the built exe has to be rebuilt from this branch before it
ships, which the build above does.

**Journey log**

- Re-running into the same output: duplicated the panel's B-tree key, so the pass now subtracts what the staged copy holds. Lab notebook, 2026-10-01.
- The source fork's row-checksum guard: measured, dropped, re-measured on a fresh layer, and it cannot separate the withdrawn set from the validated one. Lab notebook, 2026-10-01.
- Running the offline checks against the real append target: possible because the deleted pristine layer was recovered from the phone. Lab notebook, 2026-10-01.
- The handoff's "for every prime package" loop: one package on that build; the blast radius is the catalog's, so re-measure it per build. Lab notebook, 2026-10-01.
- A passing assertion as evidence: `t7_rerun.py`'s was vacuous; write the property that would fail. Lab notebook, 2026-10-01.

### The Talent Card grid regression: what was ruled out first

- Rewriting config `0AA59370241BFC22` to re-point its refs: emptied the grid twice; it is a reseal problem, so nothing here may rewrite that bin. Lab notebook, 2026-10-03.
- Reverting only `C059EA43719099F1` as a control: insufficient, the rest of the stage stayed installed. Lab notebook, 2026-10-03.
- Checking the user's example ref, Arena Tiger: translated and referenced in every copy, so neither a catalog gap nor an unreferenced key. Lab notebook, 2026-10-03.
- A fresh unpatched baseline: its grid draws Chinese names, withdrawing the "the client cannot resolve them" verdict. Lab notebook, 2026-10-03.
- Replacing only the dictionary with its full English bytes (`translated-map`): fails, so the dictionary alone reproduces the regression. Lab notebook, 2026-10-03.
- Changing one value within the original chunk size (`one-name`): works, so the dictionary is read and English resolves without a reseal. Lab notebook, 2026-10-03.
- The full English dictionary as two 307200-byte chunks with a builder-minted key (`two-chunk-map`): works; that is the shipped fix in `write_assets`. Lab notebook, 2026-10-03.
- The full fixed patch on the phone: Talent grid and detail English, the other card tabs intact, normal APK restored. Lab notebook, 2026-10-03.
- Review and cleanup: the builder now loads only when `REBUILD_PACKAGES` names a package; 18.1 GiB of outputs removed (retention in the notebook's housekeeping section). Lab notebook, 2026-10-03.
- The planned `pb_text.has_row_checksum` guard: dropped during implementation; see Out of Scope.
- The other ten card dictionaries, enlarged the same way: keys minted offline for all eleven, offline-verified, then device-verified on Diamond Frenzy's Effect Cards. Lab notebook, 2026-10-08.

What shipped from it: `device_extensions.write_assets` keeps every card dictionary at 307200 bytes per
chunk and gives a new chunk the measured identity key in `NATIVE_CHUNK_KEYS`. It verifies the existing
keys, codec and slot framing, refuses an unmeasured layout or a chunk index it holds no key for, and reads
the result back; other assets keep their staging path, and config `0AA59370241BFC22` stays byte-identical.
`exclude_extra_chunks` always routes these dictionaries to relocation, so the runtime stager cannot invent
a key, and `repair_card_dictionaries` repairs an older patch's enlarged chunk even when the already-English
dictionary yields no translation plan. A normal run loads no builder DLL.

### Still owed

The device cycle on the shipped configuration is only half watched. Package `1`, pushed as staged onto
the 1.4.0.2 layer with no rebuild and no `QtsVFS.dll`, gets the game past startup, and the Chessplayer
Card page, whose names are prime-only tables, reads English. Nobody has yet checked that the Card grid
still draws Yixing with full art on that build, or read `files/QtsVFSCache/QtsVFS.log` and `normal1.log`
for a new fix set naming package `1`.

Adding new rows to dictionaries beyond the catalog has not been attempted. A missing chunk-index key
cannot be invented, and no matching spare was found in either data layer. The user-authorized offline
builder diagnostic supplied one measured exception for the existing `C059EA43719099F1` dictionary,
which adds no rows and keeps all 4064 translated entries; it does not license arbitrary dictionary
expansion. The earlier inference that all eleven enlarged chunks were accepted came from startup rather
than from a per-table lookup, and it is withdrawn for this dictionary: the one-chunk/two-chunk
comparison above proves its layout caused the regression.

## [S1] Problem

The wide Central Plains Card Info ribbon, texture `7B4CC5DF48336D2D`, exists **only** in the APK's
prime package `21`. The device's override package for `21` does not carry it, and the game reads
override before prime, so the ribbon draws in Chinese while every neighbouring panel is English.

The repo's only route to it was `rebuild_package("21", ...)`, which lays Tencent's container out again
from scratch. That works and the game mounts it, but it costs the Factionless card: Yixing then draws
as the game's grey placeholder. The user rejected trading one goal for the other, so `21` was removed
from `REBUILD_PACKAGES` and the ribbon stayed Chinese.

Two measured facts make a rebuild the wrong tool. Tencent's own package `21` index uses record sizes
`{92: 3578, 104: 1288, 156: 1}` and head sizes `{56: 3581, 68: 1285}` (`tools/qts_builder.py`
`BUILDER_VERSION 1.0.6.65` emits only 56-byte heads / 92-byte records, so those shapes are
unreachable), and the game's own repair cannot converge on a re-laid-out container: it downloads
binary diffs against the original package contents and every one fails CRC (`errorCode:361`).

What is needed is a way to get one translated asset into an override package **without changing the
container's existing shape**.

## [S2] Design

### Mechanism

Insertion, not rebuilding. The asset's index record and its chunk slots are taken from a package that
already carries it — the APK's prime copy — so every key the game derives (entry key, chunk `hash1`)
arrives with them, derived by Tencent's own code and valid on Android. The chunking arrives with them
too: the chunk count is kept and the chunk size adjusted (`qts_relocate.chunk_size_for`), because a chunk
index that does not exist yet would need a key only the game derives. The payload is re-encoded with the
encoder `device_extensions.write_assets` uses, and the record's raw length at `+44` and chunk size at
`head_size + 24` are set exactly the way that pass sets them. The slot and the record are then
**appended** to the target package's shard and index and linked into the respective B-trees. The
target's existing asset records remain in place. The B-tree pages are updated when keys are
inserted; only the measured single-root-leaf split is supported when a leaf fills.

The record also carries a 16-byte descriptor token that depends on the content, and nothing checks it.
`write_assets` states it in a comment ("keeps its integrity token; only the raw length changes") and
`key_derivation_probe.py --stager` measures it on a real run: across package `1`'s 99 rewritten records
in a phone-pushed session only `+44` and `+80` ever changed, never the token, 70 of those with their
content replaced outright. A harvested record that no longer describes its bytes is therefore what the
in-place stager already writes, which is what let the builder go.

This is the same "append and repoint" shape `device_extensions.write_assets` already uses for chunks,
extended to the index file, which no existing path grows.

### Blast radius, measured on 1.4.0.1

Of the APK's 182 prime packages, three hold catalog content: package `1` (497 tables), package
`1050016095` (72 textures) and package `21` (1 texture, the panel). The first two were in
`REBUILD_PACKAGES` when this was written, so the append pass skipped them and **reduced to exactly one
package and one texture** — the intended card fix. `REBUILD_PACKAGES` has since been emptied, so on this
build all three go through the pass (297 + 71 + 1 assets). The pass was written generally for that reason:
the reduction is a property of the catalog, not of the loop.

### Acceptance of an append

`add_assets` ends by reading **every** appended asset back through `QtsPackage` and raising on
mismatch. This is the only verification the append path has: a record appended with a wrong key or a
wrong self-offset would read back as something else or not at all.

### Contracts

`tools/qts_insert.py`

```python
def add_assets(package_id: str, target: Path, assets: list[dict], source, log) -> None
```

`<assets>` are `{file_hash, raw}`; `<source>` is a `QtsPackage` that already carries every one of them
and is only read. `<target>` is a single-shard package directory (`<id>.db` + `<id>_0.db`) that is
written in place. Returns the hashes written. Imports `read_raw` from `qts_relocate` (the codec-9- and
Zstandard-aware reader), **not** from `extra_text` as the source fork does.

`tools/qts_relocate.py` — `chunk_size_for(length, chunk_size, chunk_count)`, the chunk size that keeps
the chunk count, shared with `write_assets`, which had it as a private helper; and two `Shard` methods
alongside `relocate`/`_repoint`:

- `append_slot(slot, payload, raw_size, reserved=None) -> int` — the same slot framing `relocate` writes,
  extracted into `_slot_bytes`, but keyed by `insert_key` rather than repointed, because the key is new
  to this shard. `<slot>` supplies the `hash1`, flags, file hash and chunk id; `<payload>` replaces the
  bytes.

- `_active_page(logical) -> int` — the page table at `+0x30` maps a logical page to its active
  physical page; raises when the logical page is absent.
- `insert_key(key, value) -> None` — descends from the root page at `+0x10`; internal pages are type
  `2` and store each child's lowest key; the key/value pair is inserted in order into the leaf's
  parallel arrays and the tail count is bumped. **No page splits**: raises
  `"...: B-tree leaf {page:#x} is full"` when the leaf already holds `KEYS_PER_PAGE` (510) keys.
  Refreshes `self.leaves` through `_active_leaf_pages()`.
- `append_record(record, key) -> int` — aligns `data_end` to 4, writes `<record>` with its self-offset
  patched at `+0`, extends `self.data`, then `insert_key(key, offset)`.

`tools/package_rebuild.py`:

- `extract_prime(apk, package_ids, target, index_only=False)` — `package_ids=None` means *all*
  packages; `index_only=True` copies only `<id>.db`, which is enough to enumerate a package's entries
  without pulling its shards (the scan covers 182 packages, 37.7 MB of indexes).
- `make_transform` also exposes `transform.tables = set(catalog.known)`, so the append pass can tell a
  translated table from any other asset.
- `add_prime_only(game, apk, transform, work, output, skip, log) -> list[dict]` — for each
  prime package index: `wanted = (prime entries ∩ (transform.graphics ∪ transform.tables)) − (device
  override entries)`. Skips an empty result, anything in `skip` (already rebuilt whole), a package
  with no `<id>_0.db`, one whose device copy is not single-shard, and one whose device index will not
  read. Otherwise extracts that prime package in full, transforms each wanted asset, and appends them
  to `device_extensions._package_output(QtsPackage(device_dir), output)` — the same staged copy the
  in-place and texture passes build on, so an append lands on top of their work rather than replacing
  it. Returns one entry per package that appended something.

`tools/build_device_patch.py`:

- `official_builder` and `transform` move out of `rebuild_prime_packages` into `build_patch`, which
  passes both in. `refused` stays per-run and shared. The transform is built whenever there is an APK, and
  the append takes no builder at all — it reads the record from the prime package it already extracts.
- After the extension pass, when there is an APK:
  `packages += add_prime_only(game, apk, transform, work, output, rebuilt, log)`. The builder is only
  constructed when one was given, and `rebuild_prime_packages` only runs then.
- `rebuilt` stays `{entry["package_id"] for entry in packages}` computed **before** the scan, so the
  append pass runs after `extend_graphics` and never touches a package that pass replaced whole.

### Failure behaviour

| Condition | Behaviour |
|---|---|
| A target B-tree leaf already holds 510 keys | Skip that package, log the leaf, record it in `append_skipped`. Measured headroom on Tencent's package 21: index 81.1% full, shard 80.7%, worst leaf 509/510 — a live but unlikely case, and not worth the whole run. |
| Device package is not single-shard | Skip and log: the append writes `<id>_0.db` by name. |
| Device index will not read | Skip and log. |
| Appended asset reads back differently | **Raise.** A silently wrong record is worse than a failed run, and there is no second check on this path. |
| The new bytes need more chunks than the asset has | Leave the asset out and name it in the log. A chunk index that does not exist yet would need a key only the game derives, so `chunk_size_for` re-cuts the payload against the chunk count instead, and only fails when no rounding of the size splits the bytes into that many chunks. |
| Asset stored under a compression this pass cannot re-encode | Leave the asset out and name it in the log, rather than writing a payload the entry's own flag misdescribes. Two cases: an id the pass does not write at all, and (measured, on package 1's 298) an LZ4 block whose length lands exactly on the piece's — a chunk whose stored and decompressed sizes agree is how this format says *stored*, so that block would read back as itself. Measured: the 570 catalog assets that reach prime are stored under id `1` (497) or `4` (73) and nothing else, and **exactly one of package 1's 298 hits the ambiguous case** (`3A70308AAF6F18F8`, a 60-byte table) and stays Chinese. |
| No APK | The pass does not run at all, and the primed content stays Chinese — 297 of package `1`'s tables and 71 of package `1050016095`'s textures on this data. This is what keeps `--selftest` and the offline CLI usable with no game data layer to read. |
| No QtsVFS builder | Nothing changes: the append does not use it. Only a package named in `REBUILD_PACKAGES` needs one, and the run says so when it is missing. |

### Reporting

A staged append is `{"package_id", "mode": "added-from-apk", "textures", "assets", "stage_report"}`
with `stage_report["replacement_count"]` counting both kinds and `textures` the share of it that was
catalog textures — the same split `rebuilt` carries and for the same reason. `count_translated` must
classify this mode on `textures`, not on the mode alone: without that, appended textures are reported
to the user as text tables.

A skipped append goes in a new `append_skipped` list of
`{"package_id", "mode": "added-from-apk", "reason", "assets", "textures"}`, and both GUI counters read
it: `textures` as images that stay Chinese, `assets - textures` as tables. Its entries carry two shapes —
a package the pass could not add to at all, which has no output directory behind it, and the refused
share of a package it did add to, which is also in `packages` for the part that was written. `text_skipped`
and `graphics_skipped` keep their present meanings and are not folded together.

## [S3] Out of Scope

- **L4**: `qts_builder.entry_flag` reads a fixed `+76`, correct only for 56-byte heads. It is wrong for
  the 24 386 codec-9 entries of prime 21 (`0x50001` where `0x90009` is meant), but the panel this pass
  appends is a 56-byte/codec-4 entry, so the bug does not affect it. **The append no longer calls it** —
  the harvested record keeps prime's own `+76` — so the bug now reaches the rebuild alone, where the
  helper lives.
- Putting package `21` back into `REBUILD_PACKAGES`. It stays out.
- The `extra_text.SAFE_ASSETS` allowlist itself. A row-checksum guard (`pb_text.has_row_checksum`,
  which the source fork carries) was to be added beside it and was **dropped after measurement**: on a
  pristine layer every one of those assets answers true — the eight withdrawn bins *and* the four the
  allowlist translates — so the guard cannot tell them apart, and since both call sites already sit
  inside `file_hash in SAFE_ASSETS` branches its only effect would be to make the pass apply nothing.
  An earlier reading of four falses came from a previous session's device-cycle snapshot (our own
  patched build, deleted with the rest of that evidence): rewriting one of those assets invalidates the
  stored MD5, so a patched copy answers false and the pristine one true. Measure this class of question
  on a freshly pulled layer, never on a copy this project has already written to.
- Hand-writing a record or a B-tree layout. The keys in an appended record are Tencent's own, read out
  of the package that already carries the asset (`qts_insert.add_assets`); nothing here composes a
  lookup key itself.
- The game force-closing before the lobby (the handoff's L1/L2).
- Re-signing, the manifest rename, and the APK rewrite path.
- Splitting a leaf beneath an existing internal root, or an unmeasured page-table layout. Only
  the measured single-root-leaf split (`Shard.split_root_leaf`) is supported; other full trees are reported.
