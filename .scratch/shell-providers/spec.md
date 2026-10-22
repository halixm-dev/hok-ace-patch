# Shell providers: wireless debugging and root beside Shizuku

Status: needs-triage

Tickets: [`issues/`](issues/) 01–04. Settled through grilling rounds 1–3 (2026-10-22). Decision record: [ADR 0007](../../docs/adr/0007-on-a-rooted-phone-write-the-override-layer-directly.md).

## Problem

The Android patcher needs a second app, Shizuku, before it can do anything: the user installs it, starts it (by wireless debugging or root), then authorizes the patcher in it. That install-and-start step is where most first runs stall. The goal is one app instead of two. For early testing, Shizuku stays as a third choice in the same app; removing it is a later ticket, decided only once both new providers have each passed a device cycle on at least two phones.

## Evidence

- **The worker needs only a shell process.** `PrivilegedDeviceService` checks uid 2000 and runs `pm`, `am` and `run-as`; nothing in it calls Shizuku (`PrivilegedDeviceService.requireShell`).
- **A Shizuku-free starter exists.** `ShellServiceStarter` is an `app_process` entry point, added for the Infinix X6853 whose ROM kills every Shizuku user service (lab notebook, 2026-10-06). It hands its binder to `WorkerBinderProvider` with a one-time token. Anything that can run one shell command as uid 2000 can start the worker (`WorkerDeviceConnection` builds that command).
- **Wireless debugging exists on every supported phone.** It arrived in Android 11; the app's `minSdk` is 30 (Android 11).
- **Shizuku started with root is likely refused today.** Its user services and processes run as the server's uid, 0 under root, and `requireShell` refuses any uid but 2000. Inferred from Shizuku's design, not measured.

## Solution

The user picks a **shell provider** on the home screen: Shizuku, Wireless debugging or Root.

- **Wireless debugging** pairs the patcher with the phone's own `adbd` once, then each run connects over ADB and starts the existing `ShellServiceStarter` as uid 2000. Everything after the worker starts is today's path, access APK included (ADR 0001).
- **Root** starts the same worker through `su` as uid 0, and the worker writes the override layer itself: no access APK, no re-signing, no APK install (ADR 0007).
- **Shizuku** is unchanged, except that Shizuku running as root is refused with a message naming the Root provider.

## Implementation Decisions

### Choosing a provider

- The user chooses; the app never picks one by detection. The choice is remembered, written in the diagnostic log header, and can be changed whenever no run is in progress.
- Each provider has its own numbered guide on the home screen.
- Wireless debugging and Root carry a **Beta** tag in the picker while in early testing. Shizuku stays the default, and stays selected for a phone that already has a patch.

### Wireless debugging

- **Client:** a port of Shizuku's own Apache-2.0 ADB code (mDNS discovery of the pairing and connect services, SPAKE2 pairing over TLS, the ADB protocol over TLS to the phone itself), with Conscrypt for the TLS key export pairing needs. Credit and license go in `android/native/THIRD_PARTY.md`'s inventory beside the existing entries.
- **Pairing:** once per phone. The user opens *Wireless debugging → Pair device with pairing code*; the patcher posts a notification with an inline reply, and the user types the six-digit code there. The ADB key pair lives in the app's private storage.
- **Each run:** connect to the advertised port, run the `ShellServiceStarter` command over an ADB shell stream, and keep the connection open for the whole run. Losing it (wireless debugging switched off, Wi-Fi lost) is a worker loss and goes through the existing recovery. The worker is never detached with `setsid`.
- **No Wi-Fi:** Android only enables wireless debugging on Wi-Fi. The patcher refuses with a message saying so, and supports no workaround (the phone's own hotspot, a USB-tethered `adb tcpip`).

### Root

- **Start:** `su -c` runs the same `app_process` command `ShellServiceStarter` uses today; the worker runs as uid 0.
- **One worker:** `PrivilegedDeviceService` stays the only worker class. It reads its uid at start: 2000 takes today's path, 0 takes the root path, anything else is refused. Snapshot, pristine delta, verification and the applied-layer audit are shared.
- **Root path:** no APK is prepared, installed or reinstalled; whatever is installed stays. The worker force-stops the game, writes each package file directly, then gives it the game's owner and SELinux label. A phone first patched through root keeps the game's signature, so WeChat/QQ direct login keeps working, and keeps the game's own launcher name.
- **Root managers:** any `su` whose `su -c id` reports uid 0 is accepted. The guide marks a manager *tested* only once it has passed a device cycle; Magisk first, then KernelSU and APatch.
- **Anti-cheat:** hiding root from the game is the user's job. The patcher never touches it; the guide says so in one line.

### Shared by all providers

- One pristine delta per phone, whichever provider wrote it. A phone patched through Shizuku can be repatched or restored through root, and the reverse. The refusal before any game file is written applies unchanged.
- Shizuku running as uid 0 is refused: *Shizuku is running with root. Choose the Root provider instead.* Each provider keeps one write path, so logs and bug reports stay clear.
- User-facing strings that name Shizuku today (`Start Shizuku before starting a patch or recovery`, the authorization prompt) become provider-specific. `GAME_MISSING` stays free of any provider name. Run `tools/research/check_ui_strings.py` after the change.

### Build order

Wireless debugging first, then root. Both ship together in one early-testing release.

## Testing

Unit tests sit beside the existing ones in `android/app/src/test/` (provider choice persistence, uid dispatch, string selection); device proof follows [device-cycle](../../docs/runbooks/device-cycle.md) and lands in the lab notebook. Measured on a phone, never assumed:

- Wireless: pairing by notification reply on at least two OEMs; a run with the screen off; wireless debugging switched off mid-run (expect worker-loss recovery).
- Root: whether files written as uid 0 need an explicit `chown` and `restorecon` before the game reads them; a full patch, a repatch and a restore on Magisk; Shizuku-then-root and root-then-Shizuku on one phone, sharing one pristine delta.
- Build: Conscrypt and the ported client build at `minSdk 30` for every shipped ABI; the size each adds.

## Out of Scope

- Removing Shizuku (a later ticket, after the device evidence above).
- Hiding root, or any other anti-cheat handling.
- Wireless debugging without Wi-Fi, and any USB `adb tcpip` bootstrap.
- Restoring the game's original signature on a phone that already has a re-signed normal APK.
- The Windows patcher, which keeps its USB ADB connection.

## Open questions

- What the six progress steps show under root, where *Unlock access* and *Restore game app* have nothing to do: skipped with a reason, or the step list shortened for that provider.
