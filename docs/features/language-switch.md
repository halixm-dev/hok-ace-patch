---
feature: language-switch
status: built; device-tested in both patchers (switch, Remove) and the Android patcher (game update)
updated: 2026-10-23
branch: master
commits: f428002..3bcae14
---

# Repatch without clearing the game's data

## Report

A translated phone can now be patched again without clearing the game's data, in all three cases that
used to need a clear: a language switch, a newer translation of the same data, and an in-game update.
After each verified install, each patcher keeps a **pristine delta** (`tools/pristine_delta.py`): the
pristine bytes of every range it overwrote, about 5 MB. A later run rebuilds the pristine layer from it
in its own copy and builds the new language from that, so the phone gets one write per staged file, as
on a first install. Both patchers also gained **Remove translation**, which writes the pristine bytes
back with no new patch.

After an in-game update, the Android patcher recovers without a clear: a package the update left stuck
or mixed is deleted and downloaded again by the game (**Re-download damaged files**,
[update-stuck-redownload](update-stuck-redownload.md)), one it left partly translated is written back
from the delta's kept asset bodies ([asset-restore](asset-restore.md)), and the next Start patches.

| what landed | where |
|---|---|
| the delta: `make`, `write`/`read`, `rebuild`, the staged-hash record, `text_not_pristine`, `accept_replaced` | `tools/pristine_delta.py` |
| Windows repatch from the delta, the pending delta, Remove | `patcher_core` (`restore_pristine`, `check_first_delta`, `push_translation`, `write_back_pristine`) |
| Windows first delta from a kept session | `Patcher.bootstrap_delta` |
| Android repatch, delta promotion, Remove | `android_bridge` (`build_snapshot`, `keep_delta`, `build_removal`), `PristineDelta.kt`, `PatchCoordinator` |
| Android build-input copy budget | `build_storage.estimate(pristine_copy_bytes=)` |
| an updated package accepted as the new pristine, per package | `pristine_delta.accept_replaced` |
| Re-download of stuck and mixed packages in one run | `android_bridge.plan_redownload` |
| the Language card / LANGUAGE picker text, Remove buttons | both front ends |
| offline checks | `tools/research/check_pristine_delta.py`, `check_windows_repatch.py`, `check_update_repatch.py`, `check_update_redownload.py` |
| device cycle tooling | `tools/research/update_cycle.py`, `watchdog_history.py` |

### Verification

- `check_pristine_delta.py --game` on pristine 1.6.0.1: English 11 rebuilt + 3 unchanged of 14 files,
  delta 5.12 MB; Indonesian 11 + 3 of 14, 3.87 MB. EN → ID, ID → EN and EN → EN each stage bytes identical
  to a build from pristine. One byte changed, truncated and missing files are reported, never rebuilt.
- `check_windows_repatch.py`: bootstrap from a pristine kept session, refusal over a translated one,
  Remove then patch again, Remove with no record refused (11 OK).
- `PristineDeltaProbeTest` and `RemovalRollbackProbeTest` pass on the Xiaomi M2007J3SG (2 tests, 6.8 s).
- `check_update_repatch.py`: replaced-file acceptance and the mixed-file refusal on the real 1.6.0.1
  packages with faked updates, both patchers.
- Device, Xiaomi M2007J3SG (lab notebook):
  - 2026-10-17, "Language switch without a clear": Windows EN → ID → EN, no repair, login kept, each
    switch byte-identical to a build from pristine; catalog fixes landed mid-cycle, so a newer translation
    was covered too.
  - 2026-10-17/18, "Language switch without a clear (Android patcher)": Remove through Windows left a
    Chinese lobby with no repair; Android EN → ID → EN, no repair, login kept.
  - 2026-10-23, "An update over a patched layer, captured end to end": update 1.6.0.1 → 1.7.0.1 over an
    English install; two Re-downloads and one asset restore, then a patch, no clear.
  - 2026-10-23, "One Re-download takes a stuck package and the mixed ones together": update 1.6.0.1 →
    1.7.0.2; one Re-download (`1`, `10`, `21`), asset restore (`15`, `19`, `20`), patch, no clear, English
    in game, login kept. Shipped in Android patcher 1.7.2.1.

### Journey

- The delta's measurement came first (lab notebook, 2026-10-17, "Reverse delta from a staged layer back
  to the pristine one"): 5.12 MB against 898.3 MB for compressed full copies. The two languages overwrite
  different ranges of `1/1_0.db`, which is why a delta always points at pristine and never chains.
- The Windows patcher has no rollback, so its new delta is written as `delta.pending.bin` before the first
  push and promoted after the last; the next run accepts either delta's staged bytes per file.
- Remove first left an empty delta; the spec owner changed it the same day to delete it, so "no delta"
  means one thing everywhere and the next run is a first install under both pristine signals.
- The per-file "replaced file becomes its new pristine" rule became per package and stricter
  (2026-10-18): textures have no text signal, so the delta records each changed asset's uncompressed
  SHA-256 on both sides.
- **Withdrawn after the first real update (ticket 01, 2026-10-23):** the update-flow signals before the
  update ((i) a delta file changed, (ii) `History.db` merges after the install, (iii) asking the user), the
  pristine write-back before the update, and the two-access-cycle run. The game updates the moment it
  opens, with no prompt, and nothing on the phone changes before then (`NewVersionInfo.json` stays the
  same), so the patcher has no moment to write first. The update merges diffs into the translated
  packages rather than failing on them; the spec owner chose the after-update path instead. ADR 0002 still
  allows that one write, unused. Signal (ii) holds after the fact (`watchdog_history.py`).
- Re-download first took only the stuck packages, so the 1.7.0.1 update needed two runs; since `48f10fa`
  one run also takes the mixed packages asset restore cannot.

Still owed: the Windows patcher does not detect a stuck update (Re-download is Android-only); a phone the
Android patcher translated before the delta shipped still needs one clear, since `releaseSession` had
deleted its snapshot bulk.

## [S1] Problem

A phone that is already translated could not be patched again without clearing the game's data, at the
cost of a ~2.7 GB re-download and a login. Three cases hit this, the first most often:

1. **After an in-game update.** The update brings back Chinese text, or the repatch fails or the game
   force-closes.
2. **A newer translation** of the data already on the phone.
3. **A language switch**, English to Indonesian or back.

The cause is the text pass: it translates only records that are still Chinese. Over an English install
the Indonesian catalog changed 0 of 387 tables while the textures still switched, leaving MULAI GAME over
English text. The patcher kept no copy of the pristine bytes it overwrote, so clearing was the only way
back to the Chinese source.

## [S2] Design

| Area | Decision |
|---|---|
| Module | One shared `tools/pristine_delta.py`; Windows calls it from `patcher_core`, Android through `android_bridge`. No Kotlin reimplementation |
| Format | One file per install: schema-versioned JSON header plus a zlib body. Per package file: path under `packages/`, pristine and staged length and SHA-256, overwritten ranges with their pristine bytes, and each changed asset's uncompressed SHA-256 on both sides. A created file records pristine length 0 |
| Ranges | 4 KiB blocks, then 64-byte sub-blocks, runs closer than 256 bytes coalesced; both files read whole from disk, never from staging state |
| Points at pristine | A run from a rebuilt layer makes its new delta against the rebuilt pristine files. One delta per patcher, no chain; the two patchers never share one |
| Valid per file | An entry holds while its file is at the staged SHA-256; the data version is only logged, because an update can change content under an unchanged `1.info` |
| Self-verifying | `rebuild` takes a file only at its staged length and SHA-256 and checks each result against the pristine SHA-256 |
| When made | Only after a verified install (Windows after `push_translation`, Android once the run is `COMPLETE`), written atomically. An interrupted install keeps the old delta |
| First delta | Only from a pristine layer: no pulled file at a staged hash this patcher ever recorded, and the text pass planned every catalog table it read (`text_not_pristine`). A stale delta with no file at a recorded staged hash (data cleared) builds as a first install |
| Windows bootstrap | With no delta, try once to make one from a kept session whose backup passes the pristine signals and whose staged files equal the phone's |
| Where kept | Windows `<working folder>/pristine/delta.bin`; Android `filesDir/pristine/delta.bin`, outside `sessions/` |
| Android build input | `snapshot/` keeps the phone's bytes for rollback; the rebuilt files go into a separate copy of only the files the delta names (~0.9 GB), which `build_storage.estimate` reserves |
| Refusals | After the pull and before any game file is written, with the clear-data message (or "patch with the patcher that patched it last") |
| Dropped files | A file the last install translated and the new build no longer stages goes back at its rebuilt pristine bytes |
| Remove translation | Writes the rebuilt pristine files through the install path (Android through `GameFileTransaction`), then deletes the delta. The re-signed normal APK stays; the screen says to keep using Scan to login |
| After an update | A package the update replaced becomes its new pristine when none of its files and none of the recorded assets is at staged bytes, and the text signal holds (`accept_replaced`); asset restore takes a partly translated one; the rest refuse with `UPDATE_MIXED`, and a stuck one with `UPDATE_STUCK`, both offering Re-download on Android |

## [S3] Out of Scope

- Layers the Android patcher translated before the delta shipped: their snapshot bulk is gone, so the
  first repatch still needs a clear.
- Detecting or preparing for an update before it runs, and the pristine write-back before it (withdrawn:
  no signal precedes an update).
- A stuck update in the Windows patcher.
