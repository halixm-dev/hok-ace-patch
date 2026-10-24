# 03: Root provider: write the override layer directly

**What to build:** the patcher starts its worker through `su` as uid 0, and the worker writes the game's files itself, with no access APK, re-signing or APK install. See the [spec](../spec.md), *Root*, and [ADR 0007](../../../docs/adr/0007-on-a-rooted-phone-write-the-override-layer-directly.md).

- Start: `su -c` runs today's `ShellServiceStarter` command; accept any `su` whose `su -c id` reports uid 0.
- `PrivilegedDeviceService` at uid 0 takes the root path: no APK preparation, install or reinstall; force-stop the game; write each package file; set the game's owner and SELinux label.
- Shared with the shell path: snapshot, pristine delta (one per phone, whichever provider wrote it), verification, the applied-layer audit, the refusal before any game file is written.
- Under root, keep the six progress steps; *Unlock access* and *Restore game app* show as skipped with a reason (spec, *Root*).
- Fill the provider's numbered guide, including the one line on anti-cheat and root hiding.

**Blocked by:** 01

**Status:** ready-for-agent

**Device test:** fail eb1943d

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

