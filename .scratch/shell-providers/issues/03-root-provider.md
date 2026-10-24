# 03: Root provider: write the override layer directly

**What to build:** the patcher starts its worker through `su` as uid 0, and the worker writes the game's files itself, with no access APK, re-signing or APK install. See the [spec](../spec.md), *Root*, and [ADR 0007](../../../docs/adr/0007-on-a-rooted-phone-write-the-override-layer-directly.md).

- Start: `su -c` runs today's `ShellServiceStarter` command; accept any `su` whose `su -c id` reports uid 0.
- `PrivilegedDeviceService` at uid 0 takes the root path: no APK preparation, install or reinstall; force-stop the game; write each package file; set the game's owner and SELinux label.
- Shared with the shell path: snapshot, pristine delta (one per phone, whichever provider wrote it), verification, the applied-layer audit, the refusal before any game file is written.
- Under root, keep the six progress steps; *Unlock access* and *Restore game app* show as skipped with a reason (spec, *Root*).
- Fill the provider's numbered guide, including the one line on anti-cheat and root hiding.

**Blocked by:** 01

**Status:** ready-for-agent

**Device test:** requested

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
