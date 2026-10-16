# Read a crash

Run this when the game dies on the phone: a force-close at startup, in a match or in a replay. The game
suppresses tombstones, so logcat is not where a crash is answered, and a startup crash is not by itself
evidence about the patch. The measurements behind these steps are in
[`docs/lab-notebook.md`](../lab-notebook.md), §1–§3 and §11.

## Steps

1. **Read the exit record.** `adb shell dumpsys activity exit-info com.tencent.tmgp.osgame`:
   `reason=2 (SIGNALED)` with `status=11` (SIGSEGV) or `7` (SIGBUS), plus `pss`. logcat shows only
   `WIN DEATH` and dropbox has nothing, so do not look there for a stack.
2. **Check which APK is installed.** If the access APK is still installed, that alone kills Unity
   startup with `signal 7`, and logcat shows only prime mounts with **no** `MountPackage … override` line.
   Reinstall the normal APK and launch again before anything else.
3. **Check the game data is complete.** A startup crash on the normal APK with incomplete game data looks
   the same. Confirm `Cache/Update/NewVersionInfo.json` reads `needDownloadSize == 0` and the game data is
   not well under ~2.8 GB. If it is short: `pm clear com.tencent.tmgp.osgame`, let the game download to the
   login screen, then patch again.
4. **Check the client could read the files.** With the access APK installed, read
   `files/QtsVFSCache/QtsVFS.log` and `Watchdog/BrokenList.db` through `run-as`: every package mounted,
   `ScanJob … result=1, errorCode=0`, an empty broken list. A patched package mounts as
   `MountPackage <id>, override, … pkgHash:<new> basePkgHash:<old>`. Do not use `pkgHash` as a content check
   (it is not content-derived), and compare sizes with `ls -l`, since `md5sum` is missing over `run-as`.
   Reinstall the normal APK afterwards.
5. **Do not launch with the network off** to isolate the patch: anti-cheat then quits early, which looks
   like a crash but is not one. The plain-text `files/bqLog/ccs_log/normal1.log` (under
   `/sdcard/Android/data/com.tencent.tmgp.osgame/`, readable without `run-as`) is a network log that ends
   mid-ping at a crash; it dates the crash but holds no stack.
6. **Run the controls in both directions before blaming the change**: unpatched data with the same APK, and
   the patched data with a clean APK. Each takes about two minutes.
7. **Narrow it down.** Revert a whole class first (for example every texture) to halve the hypotheses; when
   the answer is a subset, bisect **upward** from the last known good build, growing the set each cycle;
   compare builds **asset by asset**, not file by file. Re-measure the load-bearing part of any report that
   contradicts a recorded claim, and check what the claim measured (often only the override layer).
8. **Record it.** Each cycle of the narrowing is a device cycle (`device-cycle.md`); the verdict goes beside
   the hash in the code and the raw evidence into the lab notebook as a dated entry.

## Done when

The crash is attributed to one cause — the access APK, incomplete game data, or one named asset or
change — by a control that reproduces it and one that does not, and that is recorded in the lab notebook.
