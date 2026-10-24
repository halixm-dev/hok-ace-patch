---
feature: android-shell-providers
status: building; ticket 03 device test requested
updated: 2026-10-24
---

# Android patcher shell providers

## Report

**Where it stands (2026-10-24).** Shizuku, Wireless debugging and Root built and device-tested. The Android patcher offers three shell
providers: Shizuku (today's), Wireless debugging and Root, picked by the user on the home screen. The
work in flight is [`.scratch/shell-providers/`](../../.scratch/shell-providers/spec.md), tickets 01–04;
the root write path is decided in [ADR 0007](../adr/0007-on-a-rooted-phone-write-the-override-layer-directly.md).
Shizuku's own history stays in [android-shizuku-patcher](android-shizuku-patcher.md). Ticket 01 passed on a phone;
ticket 02 passed on the same phone. No coverage count moves.

### Journey log

- Feasibility read of the code: the worker needs only a shell process, and `ShellServiceStarter` already
  starts it without Shizuku, so any provider that can run one shell command can start it — settled by
  reading, not measured (2026-10-22).
- Grilling rounds 1–3 settled the design (2026-10-22). Round 4 kept the six progress steps under root (two skipped), put KernelSU first and set the device-test handshake (2026-10-23).
- Ticket 01 built: the home screen's ② Shell provider picker, the `WorkerStarter` seam with Shizuku as its one implementation, and the refusal of Shizuku running as root; device test requested (2026-10-24).
- Ticket 01 passed its device test on the Redmi Note 9 Pro (2026-10-24).
- Ticket 02 built: the Wireless debugging provider, an ADB client ported from Shizuku (pairing by notification reply, the worker started over an ADB shell stream, a lost connection as a worker loss), plus Conscrypt and a BoringSSL SPAKE2 library, about 3.7 MB; pairing and the worker start verified on an emulator; device test requested (2026-10-24).
- Ticket 02 passed its device test on the Redmi Note 9 Pro: pairing by notification, a full patch, a loss mid-write recovered, and the three refusals (2026-10-24).
- Ticket 03 built: the Root provider. `su -c` starts the worker as uid 0, which runs the same locked scripts in the game's data directory and gives what it creates the owner and SELinux label of `files/QtsVFSCache` (`chown`, `chcon`, umask 000 to match `run-as`; measured as root on KernelSU, see the ticket). A root preparation copies only the installed game app for the build; a root run installs nothing, records the installed app in its journal (`root_installed`) and verifies it is still installed at the end. Unlock access and Restore game app are skipped with a log line each. A run recovers only through the kind of provider that started it. Device test requested (2026-10-24).
- Ticket 03 device test failed on eb1943d: KernelSU's `su` runs in the patcher's mount namespace, where app data isolation hides `/data/user/0/<game>`. A root run now falls back to `/data_mirror/data_ce/null/0/<game>`, and the KernelSU grant lines say to reopen HOK ACE, since a grant reaches only processes started after it. Device test requested again (2026-10-24).
- Ticket 03 device test passed on `75a7f69` (KernelSU): patch, game start, loss mid-write and recovery. A dead worker's call is now journalled as *Worker disconnected* rather than `null` (2026-10-24).

## [S1] Problem

The Android patcher needs a second app, Shizuku, installed, started and authorized before it can do
anything. The goal is one app instead of two; Shizuku stays as a third provider through early testing.
Full statement: the spec's *Problem*.

## [S2] Design

Lives in the spec's *Implementation Decisions* while the work is in flight, and moves here when the
last ticket lands.

## [S3] Out of Scope

Removing Shizuku; hiding root; wireless debugging without Wi-Fi; restoring the original signature on a
phone with a re-signed normal APK; the Windows patcher. Full list: the spec's *Out of Scope*.
