# 02: Wireless debugging provider

**What to build:** the patcher starts its worker over its own ADB connection to the phone, without Shizuku. See the [spec](../spec.md), *Wireless debugging*.

- Port Shizuku's Apache-2.0 ADB client: mDNS discovery, SPAKE2 pairing over TLS, the ADB protocol over TLS. Add Conscrypt. Record both in `android/native/THIRD_PARTY.md` and the license inventory.
- Pairing once per phone through a notification inline reply; the ADB key pair kept in private storage.
- Each run: connect, start `ShellServiceStarter` over an ADB shell stream, keep the connection open for the run. A lost connection is a worker loss handled by existing recovery.
- No Wi-Fi: refuse with a message; no hotspot or `adb tcpip` workaround.
- Fill the provider's numbered guide.

**Blocked by:** 01

**Status:** ready-for-agent

**Device test:** requested

- [x] Client ported, builds at `minSdk 30` for every shipped ABI; APK size change recorded
- [x] Pairing by notification reply works on an emulator
- [x] Worker starts as uid 2000 over ADB; the rest of the run is unchanged
- [x] Guide and strings; `tools/research/check_ui_strings.py` passes

## Comments

**Implementation (2026-10-24).** The ADB client is ported from Shizuku's manager (`AdbProtocol`, `AdbKey`, `AdbPairing`, `AdbClient`, `AdbMdns`, native `cpp/adb_pairing.cpp` for SPAKE2 against the BoringSSL prefab), with Conscrypt 2.7.0 for TLS 1.3 and its keying-material export. Differences from Shizuku: the RSA-2048 key is a PKCS#8 file in no-backup storage, the TLS certificate is written as DER without BouncyCastle, HKDF and AES-128-GCM run in Kotlin. `WirelessDebugging` holds pairing (notification inline reply → `PairingReceiver` → mDNS `_adb-tls-pairing._tcp` on this phone → pair) and the paired flag; a key `adbd` refuses clears it. `WirelessWorkerStarter` checks Wi-Fi, pairing and the switch, finds `_adb-tls-connect._tcp`, connects to 127.0.0.1 and runs `ShellServiceStarter` as the ADB shell stream's command; the stream's end is reported as `link.disconnected`, so it reaches the existing worker-loss recovery. ③ gains *Connect to Wi-Fi* and *Pair wireless debugging* (button *Pair*), and refusals and the disconnect have their own lines. Unit tests: `WirelessDebuggingTest` (10). Probe: `WirelessProviderProbeTest`.

Size: `libconscrypt_jni.so` 2,754,312 bytes and `libhokace_adb.so` 268,672 bytes (arm64-v8a, the only shipped ABI; 16 KiB-aligned), dex +693,988 bytes: about 3.7 MB. Recorded in `android/native/THIRD_PARTY.md`. BoringSSL's license text for this build is still to be retained (noted in the NOTICES file).

Emulator (API 36, x86_64 with arm64 translation): pairing by notification reply works (*Paired with wireless debugging*, flag set); `WirelessProviderProbeTest` passes: the worker reports uid 2000 and closes without a loss, and closing the ADB connection under it is a worker loss within 15 s. No game on the emulator, so the run past the worker start is untested there.

What to check on the phone: pair through the notification with Settings' code; a full patch run with Wireless debugging; switching Wireless debugging off mid-run shows the disconnected lines and recovery; Wi-Fi off refuses with *Wireless debugging needs Wi-Fi*; removing the pairing in Settings gives the *no longer trusts* line and asks to pair again. Pairing probe: `am instrument -e class dev.halixm.hokacepatcher.WirelessProviderProbeTest -e pairingCode <code> …` while the code is shown.
