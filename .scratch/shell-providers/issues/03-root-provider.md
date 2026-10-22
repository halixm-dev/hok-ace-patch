# 03: Root provider: write the override layer directly

**What to build:** the patcher starts its worker through `su` as uid 0, and the worker writes the game's files itself, with no access APK, re-signing or APK install. See the [spec](../spec.md), *Root*, and [ADR 0007](../../../docs/adr/0007-on-a-rooted-phone-write-the-override-layer-directly.md).

- Start: `su -c` runs today's `ShellServiceStarter` command; accept any `su` whose `su -c id` reports uid 0.
- `PrivilegedDeviceService` at uid 0 takes the root path: no APK preparation, install or reinstall; force-stop the game; write each package file; set the game's owner and SELinux label.
- Shared with the shell path: snapshot, pristine delta (one per phone, whichever provider wrote it), verification, the applied-layer audit, the refusal before any game file is written.
- Settle the spec's open question on the six progress steps under root.
- Fill the provider's numbered guide, including the one line on anti-cheat and root hiding.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] uid-0 dispatch in the worker, with unit tests
- [ ] Direct write path, sharing the pristine delta and audits
- [ ] Progress steps under root decided and in `WorkerStep`
- [ ] Guide and strings; `tools/research/check_ui_strings.py` passes
