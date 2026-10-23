---
feature: asset-restore
status: built, not device-tested
updated: 2026-10-22
branch: master
---

# Restore carried-over translated assets

## Report

When a game update rewrites a translated package but carries over assets this patcher modified (a mixed
package), the Android patcher now writes their original bytes back into a copy of the updated package and
builds from that, instead of refusing with `UPDATE_MIXED`. Only a package it cannot take still refuses, and
[Re-download](update-stuck-redownload.md) stays the way out for it. Decision: [ADR 0008](../adr/0008-restore-a-carried-over-translated-asset.md).

On the 2026-10-22 r815437 case (packages `10`, `15`, `19`, `20`, `21` mixed), restore takes `15`, `19` and
`20`; `10` and `21` hold an asset the install appended and still go to Re-download, now about 56 MB instead
of 927 MB. Checked offline only. The Windows patcher refuses a restorable package as before.

| what landed | where |
|---|---|
| the kept asset bodies (stored chunks and index record per modified asset) | `pristine_delta.make` (`asset_bodies`), `asset_fingerprints.asset_bodies` |
| the three-way decision | `pristine_delta.accept_replaced` → (accepted, restorable, refused) |
| the write-back and read-back | `pristine_delta.restore_assets` |
| the bridge | `android_bridge._decide_mixed` and `_restore_package`, shared by `_restore_pristine` and `_mixed_packages` |
| the space reserved for the copy | `android_bridge._copy_bytes`, from `estimate_snapshot_build` and `removal_bytes` |
| the log line | `PristineDelta.describe` (`assets_restored`) |
| the offline check | `tools/research/check_asset_restore.py` |

## [S1] Problem

`accept_replaced` refuses a package an update rewrote while assets this patcher changed are still at their
staged bytes. The delta kept only byte ranges of the files, and an update's merge moves everything around
them, so it could not rebuild such a package; the user had to re-download it whole (927 MB on 2026-10-22).

## [S2] Design

| Area | Behavior |
|---|---|
| Delta | With `fingerprint=True`, each asset the install modified (pristine SHA-256 not None) keeps its pristine stored chunks verbatim, in chunk-id order with each raw size, and its pristine index record. Header keys `asset_bodies`, `asset_body_bytes`, `asset_body_sha256`; the bytes follow the zlib body, uncompressed. `SCHEMA` stays 1; an older reader reads the ranges as before, and a delta without the keys refuses as before. Appended assets keep nothing |
| Decision | `accept_replaced` calls a package restorable when the only reason to refuse it is surviving recorded assets, every one of them modified and with a kept body. Every other refusal is unchanged |
| Restore | On a copy of the package: per asset still at its staged SHA-256, refuse unless the record keeps its shape and pristine check token (+52..+67) and the asset has its pristine chunk count; relocate each pristine chunk with `Shard.relocate`; write back the raw length (+44) and chunk size (head size + 24); read back through `QtsPackage`/`read_raw` and require the pristine SHA-256 and stored chunks. Any failure discards the copy and the package stays refused |
| Bridge | `_restore_pristine` copies each restorable package whole into `PRISTINE_COPY`, restores it, re-checks that no recorded asset is still at its staged SHA-256, and lists its files in `sha256` so `_link_build_input` reads them from the copy. `UPDATE_MIXED` names only the packages still refused. `_mixed_packages` runs the same restore on a trial copy (`restore-trial`, removed after), so Re-download deletes exactly those |
| Text signal | A build over restored packages must pass `text_not_pristine`. If it does not, the text pass cannot say which package holds the text, so every restored or replaced package goes into `restore-refused.json` beside the delta and the run refuses with `UPDATE_MIXED`; the next run and Re-download treat them as refused. The record is dropped once a run or a Re-download completes. Any exception during restore, not only a failed check, leaves the package refused |
| Output | A restored file the new build leaves alone is written as restored, so the phone never keeps the mixed bytes; Remove translation writes the restored files beside the rebuilt ones |
| Space | The copy of a package restore may take (kept bodies, files changed by the snapshot's manifest) is reserved as the package's size plus its kept chunks and slot overhead, in place of its pristine files |

## [S3] Out of Scope

Appended assets (no B-tree delete); the Windows patcher; using the orphaned pristine slots instead of kept
bytes; restoring before an update instead of after ([language-switch](language-switch.md), withdrawn).

## Verification

- `tools/research/check_asset_restore.py` on the 1.7.0.1 pristine snapshot and the English install
  (`D:\scratch\hok-1.7.0.1\out5-catalog`), with packages `10`, `15`, `19`, `20`, `21` faked mixed (a
  never-translated asset rewritten one byte shorter): bodies kept for exactly the 427 modified assets
  (`1`: 100, `10`: 1, `15`: 302, `19`: 22, `20`: 1, `1050016095`: 1); restorable `15`, `19`, `20`; refused
  `10`, `21` (appended survivors); restore puts back 302, 22 and 1 assets at their pristine SHA-256 and stored
  chunks, leaves every other asset untouched, grows the shards by 55.6 MB, 1.3 MB and 16 KB in 2–3 s each,
  and refuses a changed check token; the bridge's refusal and Re-download plan name only `10`, `21`; Remove
  writes the restored shards.
- Delta size for that install: 5 270 726 B → 69 084 027 B encoded (63 774 737 B of kept bodies).
- `check_update_repatch.py --skip-build` on session `20261017-224744`: every earlier decision holds for the
  Windows patcher; on Android the partial repair (151 of 302 textures left translated) now restores.
- With `--apk`: `build_snapshot` over the whole 1.7.0.1 layer with `15`, `19`, `20` mixed restores them,
  builds in 231 s, passes the text signal, and its new delta points at the restored copies as pristine.
- The offline mixed-package and Re-download bridge checks of [update-stuck-redownload](update-stuck-redownload.md) still pass; so do
  `check_pristine_delta.py`, `check_references.py`, `check_staging_contract.py` and `check_ui_strings.py`.
- Not run: device cycles 1–3 of the spec (patch and Remove over a restored layer on a phone, and the next
  real update over it). Cycle 3 decides the ADR.
