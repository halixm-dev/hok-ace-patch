# 03: Root provider: write the override layer directly

**What to build:** the patcher starts its worker through `su` as uid 0, and the worker writes the game's files itself, with no access APK, re-signing or APK install. See the [spec](../spec.md), *Root*, and [ADR 0007](../../../docs/adr/0007-on-a-rooted-phone-write-the-override-layer-directly.md).

- Start: `su -c` runs today's `ShellServiceStarter` command; accept any `su` whose `su -c id` reports uid 0.
- `PrivilegedDeviceService` at uid 0 takes the root path: no APK preparation, install or reinstall; force-stop the game; write each package file; set the game's owner and SELinux label.
- Shared with the shell path: snapshot, pristine delta (one per phone, whichever provider wrote it), verification, the applied-layer audit, the refusal before any game file is written.
- Under root, keep the six progress steps; *Unlock access* and *Restore game app* show as skipped with a reason (spec, *Root*).
- Fill the provider's numbered guide, including the one line on anti-cheat and root hiding.

**Blocked by:** 01

**Status:** resolved

**Device test:** pass 1f5301a

- [x] uid-0 dispatch in the worker, with unit tests
- [x] Direct write path, sharing the pristine delta and audits
- [x] Skipped progress steps under root in `WorkerStep`
- [x] Guide and strings; `tools/research/check_ui_strings.py` passes

## Build notes

- **Start:** `RootWorkerStarter` runs `su -c id` (an exit other than 0 or no `uid=0(` is refused with the root manager named), then `su -c` with the starter command. The worker ends when `su`'s standard input closes, which `close()` and the app's death both do: the app cannot signal a uid-0 process.
- **Worker:** at uid 0 every game script runs as `sh -c "cd /data/user/0/<game> || exit 1; …"` instead of `run-as`. `GameFileLock.script(body, root = true)` adds `own`, which copies the owner (`stat -c %u:%g`) and label (`stat -c %C`) of `files/QtsVFSCache` onto the lock file, each written file's temporary before its `mv`, the recreated Watchdog directory and restored Watchdog directories; umask 000 matches `run-as`'s, so modes come out as the game's own (666 files, 777 directories). It refuses an owner of uid or gid 0. APK installs and removals are refused at uid 0.
- **Measured on the test phone as root (`adb shell su -c`, KernelSU):** game uid `u0_a246` (10246), every game file labelled `u:object_r:app_data_file:s0:c246,c256,c512,c768`; `own` on a new file and a new directory gave `-rw-rw-rw-`/`drwxrwxrwx u0_a246 u0_a246` with that label. Not yet measured: whether the game reads files written this way, and whether the worker's binder hand-off works from KernelSU's `su` context.
- **Preparation and run:** a root preparation keeps one copy of the installed game app (`preparations/<id>/original.apk`, receipt `root: true`), reused while the installed app still matches it. `PatchCoordinator.runRoot` shares the run body with the shell path; the journal's `recovery_id` is the installed app's sha256 and `root_installed` its identity, and the run ends by verifying that app is still installed. A shell journal is not recovered through root, nor the reverse (`OTHER_PROVIDER`); an installed access build is refused (`ROOT_ACCESS_INSTALLED`).
- **Steps:** under root a patch, removal or re-download runs steps 4 and 5; `WorkerStep.ROOT_SKIPS_ACCESS` and `ROOT_SKIPS_RESTORE` are the log lines that say why 3 and 6 are skipped.
- **Guide:** four lines; no manager is marked tested until this ticket passes on KernelSU.

## Device findings

**2026-10-24, `eb1943d`, Redmi Note 9 Pro (`ebad528e`, Android 15, PixelAge, KernelSU): fail.** Run by the implementing session at the user's request. Evidence in `docs/lab-notebook.md` (2026-10-24, ticket 03) and `D:\hokace-work\redmi-ebad528e\t03\`.

- Unit tests pass. `check_ui_strings.py`: OK (342 strings).
- Root picked: the guide shows its four lines, the hiding-root line included.
- Before HOK ACE had root in KernelSU, *Check restored game app* refused with *Root access is not available to HOK ACE…* and started no worker.
- **The grant needs a fresh app process.** With Superuser turned on in KernelSU, the running patcher still got `Cannot run program "su": error=2`; after HOK ACE was closed and reopened, `su -c id` gave `uid=0 … context=u:r:ksu:s0`. The refusal line says only *tap Start again*.
- Worker start: `su` started the starter in 213 ms, the binder came back after 1.2 s, the worker attached as uid 0, *Check restored game app* verified the installed game app, and the worker exited with code 0 when closed; no worker process was left.
- **Fail: the worker cannot reach the game's data.** Prepare made the root copy of the game app (step 1, step 2) and the patch went from step 2 to step 4 with *Skipped Unlock access…* in the log, but the first game script failed: `cd: /data/user/0/com.tencent.tmgp.osgame: No such file or directory`. `su` started from an app runs in the app's mount namespace, where Android's app data isolation hides every other app's data directory (`/data/user/0` and `/data/data` list only the patcher and GMS). In that namespace the game's data is at `/data_mirror/data_ce/null/0/com.tencent.tmgp.osgame`. KernelSU's `su` also has `-M` / `--mount-master` for the global namespace.
- The failed run wrote nothing: it recovered at once (*Game app verified; interrupted session recovered*), and ③ showed *The phone refused a step, although Root is working…*.
- The *Start translation* confirmation was confirmed on the phone by hand, not by this session.

**2026-10-24, `75a7f69`, Redmi Note 9 Pro (`ebad528e`, Android 15, PixelAge, KernelSU): pass.** Run by the implementing session at the user's request. Evidence in `docs/lab-notebook.md` (2026-10-24, ticket 03 retest) and `D:\hokace-work\redmi-ebad528e\t03\`.

- Unit tests pass. `check_ui_strings.py`: OK (342 strings). The guide's KernelSU line now says to close and reopen HOK ACE.
- **Patch through Root:** `su -c id` gave uid 0 (`u:r:ksu:s0`), the starter came up in 212 ms and the worker attached as uid 0. The snapshot ran in the `/data_mirror` path, and the run applied 391 text tables and 398 images (1 table skipped), rebuilt 11 files from the pristine delta and kept a 14-file delta. The log shows *Skipped Unlock access…* and *Skipped Restore game app…*, and no APK was installed. ③ read *Translation added*.
- **Files:** all 1314 entries under the game's `files/` are `u0_a246:u0_a246` with `u:object_r:app_data_file:s0:c246,c256,c512,c768`, and none is owned by root. No worker process was left.
- **Game:** started to an English login screen (`run2-login.png`) with no QtsVFS errors. A second Root patch over the translated layer also completed.
- **Loss mid-write:** `pkill -9` of the uid-0 worker during *Applying package file* (after `15/15_0.db`, before `19`) → `recovery_required`, `packages_dirty`. *Restore interrupted patch* → `recovered` (phase `CANCELLED`) in 95 s, with no install. The game started English again (`run3-recovered-login.png`, QTS scan `errorCode=0`), and all 1322 entries kept the game's owner and label.
- **Minor: the loss line read `null; recovery: null`.** The `DeadObjectException` from `writeGameFile` reached the journal before the disconnect callback, so ③ showed the generic *Work stopped* line rather than *Root access stopped…*. This is the same as ticket 02's `null` loss reasons. Fixed after this test: a dead worker's call is journalled as *Worker disconnected*. That fix is not device-tested.
- **Minor:** the recovery tools still offer *Reinstall saved game app* under Root, because of a normal APK retained from an earlier Shizuku run. ③'s *Patch complete. Normal game app verified.* reads as shell wording under Root.
- The *Start translation* confirmations were ticked by this session. The *Recover interrupted patch* chooser was confirmed on the phone by hand.

**2026-10-24, `1f5301a`, Redmi Note 9 Pro (`ebad528e`, Android 15, PixelAge, KernelSU): pass.** Independent retest by a separate test session, on master with the *Worker disconnected* fix. Evidence in `docs/lab-notebook.md` (2026-10-24, tickets 02 and 03 retest) and `D:\hokace-work\redmi-ebad528e\retest\`.

**Device test:** pass 1f5301a

- Unit tests pass (`testDebugUnitTest`). `check_ui_strings.py`: OK (342 strings). HOK ACE already granted in KernelSU; `su -c id` gave `uid=0 … u:r:ksu:s0`.
- **Patch:** started from *Ready when you are*; the saved copy of the game app was reused, *Skipped Unlock access…* and *Skipped Restore game app…* both logged. `complete` at 14:27:43: 391 text tables, 398 images applied, 1 table skipped, 11 files rebuilt from the pristine delta, a 14-file delta kept; no APK installed. ③ read *Translation added*. No worker process left.
- **Files:** all 1320 entries under the game's `files/` are `u0_a246:u0_a246` with `u:object_r:app_data_file:s0:c246,c256,c512,c768`; none root-owned (`root-run1-files-stat.txt`).
- **Game:** English login screen (`root-run1-game.png`), no QtsVFS errors, QTS scan `errorCode=0`.
- **Loss mid-write (the fix under test):** a second patch, `su -c 'pkill -9 -f hokacepatcher:worker'` right after *Applying package file 15/15_0.db* (14:38:15). The journal read *Worker disconnected; recovery: Worker disconnected*, and ③ showed *Root access stopped. Keep the game closed. Check HOK ACE in your root manager, then check recovery options below.*, not the generic line and not `null; recovery: null` (`root-run2-loss-screen.png`). `recovery_required`, `packages_dirty`.
- **Recovery:** *Restore interrupted patch* → `recovered` (phase `CANCELLED`) at 14:41:07, no install. All 1327 entries kept the game's owner and label (`root-run2-recovered-files-stat.txt`); the game started English (`root-run2-recovered-game.png`), no QtsVFS errors, QTS scan `errorCode=0`.
- Still open from the first test: the recovery tools offer *Reinstall saved game app* under Root, and ③'s *Patch complete. Normal game app verified.* reads as shell wording under Root.
- The *Start translation* confirmations and the *Recover interrupted patch* chooser were driven by this session through `uiautomator`.

**Resolved (2026-10-24).** Device test pass on `75a7f69` and again, independently, on `1f5301a`. The wording and recovery-tools findings are fixed in `fd071d1`: root results say *The game app was not replaced*, and a retained normal APK alone no longer offers *Reinstall saved game app* under Root. Magisk, APatch, direct login and the cross-provider runs are ticket 04.
