# Patch speed: where the Android run's time goes (investigation, 2026-10-18)

Status: done. Measured and shipped in source: lab notebook, 2026-10-18, "Android patch run: stage timings
and five fewer passes". Proposals 1–5 below are implemented (6 was not measured). Phone runs: 906 s → 616–621 s
on a Redmi Note 9 Pro. The launcher keeping each replaced game APK (~2.4 GB) until it restarts, which made
two runs fail their storage check, is fixed in source (`releaseReplacedGameApks`, see "Launcher-pinned APKs"
below) and checked on the phone: a run ends with no net loss of free space.

## Starting point

- Staging is already optimized (lab notebook, 2026-10-17 entries "Skip unnecessary extra-text…" through
  "Threaded ASTC phone benchmark"). The handoff's leads 1–4 (ASTC cache/threads, slot maps, append source
  scans, shard I/O) are done and measured. Duplicate ASTC work left: 0.32 s of recorded encode time.
- Threaded phone run: internal build **63 s** out of a **~475 s** patch resource timer (including ~2.6 min
  of final-install recovery). The remaining ~250–400 s have never been broken down by stage.
- Windows build is 40–50 s, and a same-version re-run's pull is ~17–23 s. No large Windows lead is left.

## One full pass costs about 13–15 s on the Xiaomi

From the notebook's optimized phone run: the `build_snapshot` bridge took 233.4 s against a 174.7 s internal
build timer. The 58.7 s gap is `verify_snapshot` (layer, L) + APK hash (A) + `build_scratch` re-hashing
every source (≈L) + APK hash again (A): four ~2–3 GB passes, about 13–15 s each. This is derived, not
measured per pass.

## Full-file reads per Android run (from source, `PatchCoordinator.run`)

L = game layer, packages + Watchdog (~2.3–3 GB). A = game APK (~2 GB).

| Step | Layer passes | APK passes | Notes |
|---|---:|---:|---|
| Pre-session: `store.verify`, `ApkIdentity.read(accessApk)`, `verifyInstalled(source)` | | 3 | |
| Session `access.apk` hard link re-read | | 1 | same inode, already read-only |
| Install access #1: identity read, `pm install-write`, `verifyInstalled` | | 3 | |
| `snapshotGame` tar (in-transit hash) | 1 (+1 write) | | |
| `ApkIdentity.digest(archive)` | 1 | | re-hashes what the transfer just hashed |
| `unpack_snapshot` extract + per-file hash | 1 (+1 write) | | |
| `validateLayer` #1 (toybox `sha256sum` on device) | 1 | | |
| Install normal (for the build) | | 3 | |
| `estimate_snapshot_build` → `verify_snapshot` | 1 | | |
| `build_snapshot` → `verify_snapshot` again, APK hash | 1 | 1 | back to back with the line above |
| `build_scratch` control re-hash of sources, APK hash | ~1 | 1 | same process, nothing in between |
| `verifyOriginals` before apply | 1 | | |
| Install access #2 | | 3 | Windows never does this: it keeps access through the build |
| `validateLayer` #2 | 1 | | |
| Writes: digest each staged file, device hash ×2 | ~0.4 ×3 | | 14 files, ~0.93 GB |
| `finishApply` → `verifyOriginals` again, `validateLayer` #3 | 2 | | |
| Install normal #2 | | 3 | |
| **Total** | **~13** | **~19** | about 32 full passes of 2–3 GB |

## Ranked proposals (written before the measurements; 1–5 done, measured savings in the notebook)

1. **Done.** **Hash each build input once.** `estimate_snapshot_build`, `build_snapshot` and `build_scratch` verify the
   same snapshot and APK three times in a row, with nothing in between that could change them. Keep the
   first full check and drop the two repeats. About 3 passes, **~40 s**. Risk: low. The trust check still
   runs before the build reads anything, and rollback keeps its own `verifyOriginals`.
2. **Done.** **Keep the access APK through the build, as Windows does.** This drops install normal #1, install
   access #2 and `validateLayer` #2: about 6 APK passes, 2 installs and 1 layer pass, **~90 s or more**.
   Risk: medium. ADR 0001 only forbids opening the game while access is installed, and Windows already
   holds access through its build. But the Android journal states (`NORMAL_RESTORED_FOR_BUILD`), recovery
   and the process-death probes assume the normal APK during the build. The reason Android chose it is
   not recorded. It needs a device cycle and the user's call.
3. **Done.** **Extract the snapshot straight from the pipe.** Today the tar goes to `snapshot.tar`, gets re-hashed,
   then gets extracted. Streaming saves ~1 write and 2 reads of L (**~30–40 s**) and halves the ~6 GB
   free-space dip. Risk: medium. The transport check moves to "in-transit hash and per-file hashes
   agree"; it has the same fail-closed rules as `extract_snapshot`.
4. **Done.** **Drop the re-hash in `finishApply`.** `expectedApplied` calls `verifyOriginals` only to rebuild the
   manifest, which was just verified before apply. `rollback` still verifies independently. 1 pass,
   **~15 s**. Risk: low.
5. **Done.** **Carry the APK identity forward.** The same read-only, app-private APK is hashed 2–3 times before each
   install (`read(accessApk)`, the session link, `install()`). Hash it once per run, and check
   size and mtime unchanged before each install. About 3–4 passes, **~45 s**. Risk: low to medium.
   The installed-APK verification on the device stays.
6. **Measure toybox `sha256sum`.** `validateLayer` runs it three times over L. Toybox's SHA-256 may lack ARM
   crypto extensions and run much slower than Java/OpenSSL. Measure before proposing anything.

Not proposed: anything that removes the one trust check before a consuming step, the device-side
read-back of each written file, or `verifyInstalled` after each install.

## Measured result

Rebuild from delta on a Redmi Note 9 Pro: 905.8 s at HEAD `d749ac3`, 616–621 s with 1–5 (−32%). Counts
unchanged. Proposal 6 (toybox `sha256sum`) is not measured.

## Launcher-pinned APKs (found during the runs, fixed)

The home app keeps each replaced ~2.4 GB game APK on storage until it restarts; one
`am force-stop` of the launcher freed 9.45 GiB. This caused two storage refusals during the runs. The
privileged worker now force-stops the default home app after each game install, and the patch run,
recovery and APK preparation release once more before their first budget
(`releaseReplacedGameApks`). On the phone a run now ends where it started (15.66 GiB),
and a manual launcher force-stop afterwards frees nothing (lab notebook, same entry).

## Still open

- `CoordinatorRecoveryProbeTest`, `FullCoordinatorProbeTest`, `ApkPreparationProbeTest` and
  `CoordinatorSourceGuardProbeTest` need the 1.4.0.2 fixtures, which only the Xiaomi `f15a72e` has. Run them there.
- Other launchers are unmeasured.
