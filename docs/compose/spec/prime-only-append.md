---
feature: prime-only-append
status: delivered
updated: 2026-10-01
branch: feat/prime-only-append
commits: c3f23b3..e4c83ad
---

# Prime-Only Append

## Report

**What was built** — Catalog assets that exist only in the APK can now reach an override package
without laying the container out again. `tools/qts_insert.add_assets` has Tencent's builder produce a
throw-away package holding just the new asset, then appends that asset's chunk slot to the target's
shard and its index record to the target's index, linking each into the B-tree that indexes it
(`qts_relocate.Shard.insert_key`, `append_record`). Nothing else in the target moves — its records,
page table and tree pages are untouched, and it gains bytes at the end plus one key per tree — so the
package keeps the shape the game already mounts. `package_rebuild.add_prime_only` finds what this
applies to (catalog entries present in the APK's prime package and absent from the device's override
copy) and `build_patch` runs it last, sharing the rebuild's transform and builder, keyed on the
packages a rebuild already replaced.

On this build the pass resolves to exactly one package and one texture. Of the APK's 182 packages,
three hold catalog content in prime — package `1` (497 tables), `1050016095` (72 textures) and `21`
(the Central Plains panel) — and the first two are already rebuilt whole, so they are in `skip`. That
one asset is the Central Plains Card Info ribbon, the only catalog edit that could not previously be
applied: it exists only in package `21`, and rebuilding `21` costs the Factionless card. On the phone
the ribbon now reads `Central Plains` where the previous capture read `河洛`, and the Card grid still
draws Yixing with full art.

Things that go wrong are reported rather than fatal: a B-tree leaf already holding 510 keys, a device
copy split over several shards, or a staged copy that will not read are recorded in the run's
`append_skipped` list and counted by the app as images and as tables that stay in Chinese. A read-back
that disagrees **raises**, because a record linked under the wrong key is invisible until the game
fails to find it.

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
| device cycle | lobby in English, Card grid with Yixing's art, ribbon `Central Plains`; `QtsVFS.log` — `MountPackage 21, override, 0 => succeed! pkgHash:8591676242410099349 basePkgHash:14935366421268903059 state:4 prebuild:0`, `ScanJob ... [after]brokenFiles count 0, size 0 ... errorCode=0`, `VFS_GetBrokenFileCount builtin, 0 size 0`; `normal1.log` has 0 lines matching `errorCode:[1-9]|QtsfFixer|FixFile|crc not match|corruptedPackages|IsPrebuild` (`artifacts\device-cycle-t8\normal1-repair-lines.txt`). Phone file check: `21_0.db` 40 747 008 B (pristine 40 730 624) |

An independent review of `c3f23b3..e4c83ad` found no critical defect. Three of its findings were fixed
before this document was finalized: `AGENTS.md` claimed `append_skipped` covers a staged copy that will
not read, which the pass logs and skips without an entry; the counters' skipped-append half had no
artifact feeding a non-empty list, which `t3_skip.py` now supplies; and the app's summary was gated on
translated text alone, so a run that only skipped images would have called itself "already installed".
Its remaining point stands as a release note: the built exe has to be rebuilt from this branch before it
ships, which the build above does.

**Journey log**

1. A re-run into the same output duplicated the panel's index **and** shard B-tree key. `QtsPackage.entries`
   is keyed by file hash, so the duplicate was invisible there and showed only as two offsets under one
   key in the tree. The pass now subtracts what the staged copy already holds.
2. The source fork's row-checksum guard was measured, dropped, and then re-measured. The first reading
   (the four validated assets "unguarded") came from a device-cycle snapshot an earlier session left
   behind — `hok-device-cycle/phone/`, our own patched build, since deleted with the rest of that
   session's evidence — and rewriting one of those bins invalidates its stored MD5. On a freshly pulled
   layer all of them answer true, so the guard cannot separate the withdrawn set from the validated one.
3. The pristine download layer the earlier cleanup deleted was recovered from the phone itself (one
   `tar` stream over `run-as`), which is what let every offline check here run against the real append
   target instead of a package we synthesized.
4. The handoff's "for every prime package" loop collapses to one package on this build, because the two
   other packages holding prime-only content are already rebuilt whole. The blast radius is a property
   of the catalog, not of the loop — worth re-measuring, not assuming, on another build.
5. A passing assertion is not evidence. `t7_rerun.py` asserted `"21" not in packages or packages`, which
   is vacuously true, and the review caught it; the run's real property is that the second run reports
   `21` *not at all*, because its staged copy already holds the panel. Write the property that would
   fail, and check a claim against the artifact rather than against a summary of it.

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

Insertion, not rebuilding. Tencent's builder is used only to produce a **throw-away** package holding
the single new asset; every key it carries (entry key, chunk `hash1`, integrity tokens) was derived by
Tencent's own code and is valid on Android. Its chunk slot and its index record are then **appended**
to the target package's shard and index and linked into the respective B-trees. The target's existing
records, page table and B-tree pages are never rewritten — it only gains bytes at the end and one key
per tree.

This is the same "append and repoint" shape `device_extensions.write_assets` already uses for chunks,
extended to the index file, which no existing path grows.

### Blast radius, measured on 1.4.0.1

Of the APK's 182 prime packages, three hold catalog content: package `1` (497 tables), package
`1050016095` (72 textures) and package `21` (1 texture, the panel). The first two are in
`REBUILD_PACKAGES`, so the append pass skips them. **On this build the pass reduces to exactly one
package and one texture** — the intended card fix. The pass is nevertheless written generally, because
that reduction is a property of the catalog, not of the loop.

### Acceptance of an append

`add_assets` ends by reading **every** appended asset back through `QtsPackage` and raising on
mismatch. This is the only verification the append path has: a record appended with a wrong key or a
wrong self-offset would read back as something else or not at all.

### Contracts

`tools/qts_insert.py` (new)

```python
def add_assets(package_id: str, target: Path, assets: list[dict], builder, work: Path, log) -> None
```

`<assets>` are `{file_hash, raw, flag, chunk_size}` as `qts_builder.Builder.build` takes them.
`<target>` is a single-shard package directory (`<id>.db` + `<id>_0.db`) that is written in place.
Imports `read_raw` from `qts_relocate` (the codec-9- and Zstandard-aware reader), **not** from
`extra_text` as the source fork does.

`tools/qts_relocate.py` — three `Shard` methods, alongside `relocate`/`_repoint`:

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
- `add_prime_only(game, apk, transform, builder, work, output, skip, log) -> list[dict]` — for each
  prime package index: `wanted = (prime entries ∩ (transform.graphics ∪ transform.tables)) − (device
  override entries)`. Skips an empty result, anything in `skip` (already rebuilt whole), a package
  with no `<id>_0.db`, one whose device copy is not single-shard, and one whose device index will not
  read. Otherwise extracts that prime package in full, transforms each wanted asset, and appends them
  to `device_extensions._package_output(QtsPackage(device_dir), output)` — the same staged copy the
  in-place and texture passes build on, so an append lands on top of their work rather than replacing
  it. Returns one entry per package that appended something.

`tools/build_device_patch.py`:

- `official_builder` and `transform` move out of `rebuild_prime_packages` into `build_patch`, which
  passes both in. `refused` stays per-run and shared.
- After the extension pass, when the APK and builder are both available:
  `packages += add_prime_only(game, apk, transform, official_builder, work, output, rebuilt, log)`.
- `rebuilt` stays `{entry["package_id"] for entry in packages}` computed **before** the scan, so the
  append pass runs after `extend_graphics` and never touches a package that pass replaced whole.

### Failure behaviour

| Condition | Behaviour |
|---|---|
| A target B-tree leaf already holds 510 keys | Skip that package, log the leaf, record it in `append_skipped`. Measured headroom on Tencent's package 21: index 81.1% full, shard 80.7%, worst leaf 509/510 — a live but unlikely case, and not worth the whole run. |
| Device package is not single-shard | Skip and log: the append writes `<id>_0.db` by name. |
| Device index will not read | Skip and log. |
| Appended asset reads back differently | **Raise.** A silently wrong record is worse than a failed run, and there is no second check on this path. |
| No APK or no QtsVFS builder | The pass does not run at all, exactly as the rebuild behaves today, which keeps `--selftest` and the offline CLI usable without the DLLs. |

### Reporting

A staged append is `{"package_id", "mode": "added-from-apk", "textures", "assets", "stage_report"}`
with `stage_report["replacement_count"]` counting both kinds and `textures` the share of it that was
catalog textures — the same split `rebuilt` carries and for the same reason. `count_translated` must
classify this mode on `textures`, not on the mode alone: without that, appended textures are reported
to the user as text tables.

A skipped append goes in a new `append_skipped` list of
`{"package_id", "mode": "added-from-apk", "reason", "assets", "textures"}`, and both GUI counters read
it: `textures` as images that stay Chinese, `assets - textures` as tables. `text_skipped` and
`graphics_skipped` keep their present meanings and are not folded together.

## [S3] Out of Scope

- **L4**: `qts_builder.entry_flag` reads a fixed `+76`, correct only for 56-byte heads. It is wrong for
  the 24 386 codec-9 entries of prime 21 (`0x50001` where `0x90009` is meant), but the panel this pass
  appends is a 56-byte/codec-4 entry, so the bug does not affect it. Left as an open lead.
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
- Hand-writing a record or a B-tree layout. The one thing the append path must have from Tencent is the
  record its builder derives (`qts_insert.add_assets`); nothing here composes a lookup key itself.
- The game force-closing before the lobby (the handoff's L1/L2).
- Re-signing, the manifest rename, and the APK rewrite path.
- Page splits in the B-trees: a full leaf is reported, not solved.

## Tasks

- [x] T1: Add `_active_page`, `insert_key` and `append_record` to `Shard` — acceptance: a key inserted into copies of Tencent's prime-21 index and shard is found by that tree's own lookup, and a leaf at 510 keys raises (covers: S2)
- [x] T2: Add `qts_insert.add_assets` — acceptance: appending a translated asset to a copy of Tencent's prime 21 reads back byte-identical, every pre-existing entry of that package still reads, and the container's other records and page table are unchanged (covers: S2)
- [x] T3: Extend `extract_prime` (`index_only`, `package_ids=None`), `make_transform` (`tables`) and add `add_prime_only` — acceptance: an override package lacking the panel gains it translated; one already carrying it is left alone; a full leaf and a multi-shard package are skipped and reported rather than raised (covers: S2)
- [x] T4: Wire the pass into `build_patch` with the builder and transform lifted out of `rebuild_prime_packages` — acceptance: an offline CLI run over a game dir with an APK and builder reports a `added-from-apk` entry for the package that gained the panel, and reports none when the APK or builder is missing (covers: S2)
- [x] T5: Report the pass and classify it — acceptance: `count_translated` on a summary carrying an `added-from-apk` entry returns the appended textures as images, and a skipped append is counted as untranslated images and tables (covers: S2)
- [x] T7: Offline verification over a real device layer — acceptance: `tools/build_device_patch.py` run against the phone's own override packages writes a translated panel into that package's staged copy, a second run reaches the same state, and the summary's counts are consistent (covers: S2)
- [x] T8: Device cycle — acceptance: on the phone the Card grid still draws Yixing **and** the Central Plains Card Info ribbon is English; `files/QtsVFSCache/QtsVFS.log` and `normal1.log` show no new fix set naming the appended package (covers: S2; device-gated)

T6 (the `pb_text.has_row_checksum` guard) was dropped during implementation; see Out of Scope.
