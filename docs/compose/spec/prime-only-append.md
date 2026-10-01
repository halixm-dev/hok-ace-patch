---
feature: prime-only-append
status: in-progress
updated: 2026-10-01
branch: feat/prime-only-append
commits:
---

# Prime-Only Append

## Report

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

`tools/pb_text.py` — `has_row_checksum(data) -> bool`, with private helpers `_top_level` and
`_row_digest`: true when field 1 is the uppercase MD5 of the concatenated field-2 rows. A ResData
config bin is validated by the game at load, and on rejection it falls back to a rawassets file that
does not exist on Android, which empties whole menus. Wired into `make_transform` (prime rebuild and
append) and `extra_text.plan_package`.

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
- The `extra_text.SAFE_ASSETS` allowlist itself. `has_row_checksum` is added as a guard beside it;
  the allowlist keeps exactly the assets HEAD has.
- The game force-closing before the lobby (the handoff's L1/L2).
- Re-signing, the manifest rename, and the APK rewrite path.
- Page splits in the B-trees: a full leaf is reported, not solved.

## Tasks

- [ ] T1: Add `_active_page`, `insert_key` and `append_record` to `Shard` — acceptance: a key inserted into copies of Tencent's prime-21 index and shard is found by that tree's own lookup, and a leaf at 510 keys raises (covers: S2)
- [ ] T2: Add `qts_insert.add_assets` — acceptance: appending a translated asset to a copy of Tencent's prime 21 reads back byte-identical, every pre-existing entry of that package still reads, and the container's other records and page table are unchanged (covers: S2)
- [ ] T3: Extend `extract_prime` (`index_only`, `package_ids=None`), `make_transform` (`tables`) and add `add_prime_only` — acceptance: an override package lacking the panel gains it translated; one already carrying it is left alone; a full leaf and a multi-shard package are skipped and reported rather than raised (covers: S2)
- [ ] T4: Wire the pass into `build_patch` with the builder and transform lifted out of `rebuild_prime_packages` — acceptance: an offline CLI run over a game dir with an APK and builder reports a `added-from-apk` entry for the package that gained the panel, and reports none when the APK or builder is missing (covers: S2)
- [ ] T5: Report the pass and classify it — acceptance: `count_translated` on a summary carrying an `added-from-apk` entry returns the appended textures as images, and a skipped append is counted as untranslated images and tables (covers: S2)
- [ ] T6: Add `pb_text.has_row_checksum` and wire it into both translation paths — acceptance: the eight withdrawn package-1 assets read back true and are left untranslated, while the four device-validated assets read back false and still translate (covers: S2)
- [ ] T7: Offline verification over a real device layer — acceptance: `tools/build_device_patch.py` run against the phone's own override packages writes a translated panel into that package's staged copy, a second run reaches the same state, and the summary's counts are consistent (covers: S2)
- [ ] T8: Device cycle — acceptance: on the phone the Card grid still draws Yixing **and** the Central Plains Card Info ribbon is English; `files/QtsVFSCache/QtsVFS.log` and `normal1.log` show no new fix set naming the appended package (covers: S2; device-gated)
