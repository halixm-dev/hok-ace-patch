# 02: Wireless debugging provider

**What to build:** the patcher starts its worker over its own ADB connection to the phone, without Shizuku. See the [spec](../spec.md), *Wireless debugging*.

- Port Shizuku's Apache-2.0 ADB client: mDNS discovery, SPAKE2 pairing over TLS, the ADB protocol over TLS. Add Conscrypt. Record both in `android/native/THIRD_PARTY.md` and the license inventory.
- Pairing once per phone through a notification inline reply; the ADB key pair kept in private storage.
- Each run: connect, start `ShellServiceStarter` over an ADB shell stream, keep the connection open for the run. A lost connection is a worker loss handled by existing recovery.
- No Wi-Fi: refuse with a message; no hotspot or `adb tcpip` workaround.
- Fill the provider's numbered guide.

**Blocked by:** 01

**Status:** ready-for-agent

**Device test:** pass 9aa1b4e

- [x] Client ported, builds at `minSdk 30` for every shipped ABI; APK size change recorded
- [x] Pairing by notification reply works on an emulator
- [x] Worker starts as uid 2000 over ADB; the rest of the run is unchanged
- [x] Guide and strings; `tools/research/check_ui_strings.py` passes

## Comments

**Implementation (2026-10-24).** The ADB client is ported from Shizuku's manager (`AdbProtocol`, `AdbKey`, `AdbPairing`, `AdbClient`, `AdbMdns`, native `cpp/adb_pairing.cpp` for SPAKE2 against the BoringSSL prefab), with Conscrypt 2.7.0 for TLS 1.3 and its keying-material export. Differences from Shizuku: the RSA-2048 key is a PKCS#8 file in no-backup storage, the TLS certificate is written as DER without BouncyCastle, HKDF and AES-128-GCM run in Kotlin. `WirelessDebugging` holds pairing (notification inline reply → `PairingReceiver` → mDNS `_adb-tls-pairing._tcp` on this phone → pair) and the paired flag; a key `adbd` refuses clears it. `WirelessWorkerStarter` checks Wi-Fi, pairing and the switch, finds `_adb-tls-connect._tcp`, connects to 127.0.0.1 and runs `ShellServiceStarter` as the ADB shell stream's command; the stream's end is reported as `link.disconnected`, so it reaches the existing worker-loss recovery. ③ gains *Connect to Wi-Fi* and *Pair wireless debugging* (button *Pair*), and refusals and the disconnect have their own lines. Unit tests: `WirelessDebuggingTest` (10). Probe: `WirelessProviderProbeTest`.

Size: `libconscrypt_jni.so` 2,754,312 bytes and `libhokace_adb.so` 268,672 bytes (arm64-v8a, the only shipped ABI; 16 KiB-aligned), dex +693,988 bytes: about 3.7 MB. Recorded in `android/native/THIRD_PARTY.md`. BoringSSL's license text for this build is still to be retained (noted in the NOTICES file).

Emulator (API 36, x86_64 with arm64 translation): pairing by notification reply works (*Paired with wireless debugging*, flag set); `WirelessProviderProbeTest` passes: the worker reports uid 2000 and closes without a loss, and closing the ADB connection under it is a worker loss within 15 s. No game on the emulator, so the run past the worker start is untested there.

What to check on the phone: pair through the notification with Settings' code; a full patch run with Wireless debugging; switching Wireless debugging off mid-run shows the disconnected lines and recovery; Wi-Fi off refuses with *Wireless debugging needs Wi-Fi*; removing the pairing in Settings gives the *no longer trusts* line and asks to pair again. Pairing probe: `am instrument -e class dev.halixm.hokacepatcher.WirelessProviderProbeTest -e pairingCode <code> …` while the code is shown.

## Device findings

**2026-10-24, `9aa1b4e`, Redmi Note 9 Pro (`ebad528e`, Android 15, PixelAge, KernelSU): pass.** Run by the implementing session at the user's request. Evidence in `docs/lab-notebook.md` (2026-10-24, ticket 02) and `D:\hokace-work\redmi-ebad528e\t02\`.

- Unit tests pass. `check_ui_strings.py`: OK (324 strings).
- Probes: `WirelessProviderProbeTest` 3 of 3 (paired, worker uid 2000 with a clean close, a dropped connection reported as a worker loss), before and after re-pairing; `GuidedHomeProbeTest`, `InterfaceProbeTest`, `DiagnosticLogExportProbeTest` 12 of 12.
- Shizuku's server was stopped for the whole test, so every worker came from Wireless debugging.
- Pairing by notification reply: Pair posts the notification and opens Developer options; the code typed into the inline reply paired in 350 ms (*Paired with wireless debugging*); the paired device shows in Settings as `hokace-patcher`.
- End to end: the worker started over ADB in 112–284 ms and attached as uid 2000. Patch `complete` (391 text tables, 398 textures applied): 11 files rebuilt from the pristine delta, normal APK restored and verified, a 14-file pristine delta kept. The game started (no `errorCode:361`, no QtsVFS errors in logcat) to an English login screen.
- Wireless debugging switched off during prepare: the loss is caught, the run is cancelled, *No game files changed*.
- Switched off during the patch's write step (package 10): worker loss at once, `recovery_required` 22 s later, and ③ shows *Wireless debugging disconnected. Keep the game closed. Turn Wi-Fi and Wireless debugging back on, then check recovery options below.* Back on, *Restore interrupted patch* over Wireless debugging: `recovered`, normal APK verified.
- Wi-Fi off: ③ reads *Connect to Wi-Fi*; Start refuses with *Wireless debugging needs Wi-Fi…*, no worker.
- Wireless debugging off: Start refuses with *Wireless debugging is off…*, no worker.
- Pairing forgotten in Settings: Start refuses in 400 ms with *Wireless debugging no longer trusts the patcher. Tap Pair to pair it again.*, the paired flag clears, ③ returns to *Pair wireless debugging*; pairing again through the notification works.

Not failures of this ticket, for whoever touches them next:

- The connection log reads `Wireless debugging port -1`: `environment()` is logged before `start` finds the port.
- A dropped connection is logged as `connection lost (null)`, and the run's raw error starts `null; normal APK restore: …`: the exceptions carry no message.
- A loss during prepare shows the generic *Work stopped…* notice, not the wireless line: that run ends `cancelled`, not with a *disconnected* error.
- This ROM ignores the Wireless debugging highlight: Pair opened Developer options at the top the first time.
- ③ reads *Ready when you are* while Wireless debugging is off; the switch is checked only on Start.
- The *Start translation* confirmation of the first run was confirmed on the phone by hand, not by this session.
- The game came up logged out, so the lobby was not checked; the login screen is English.
- `WorkerProbeTest`'s leftover error state from ticket 01 (`worker-state.json`) was removed before the run.
