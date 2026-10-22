# 02: Wireless debugging provider

**What to build:** the patcher starts its worker over its own ADB connection to the phone, without Shizuku. See the [spec](../spec.md), *Wireless debugging*.

- Port Shizuku's Apache-2.0 ADB client: mDNS discovery, SPAKE2 pairing over TLS, the ADB protocol over TLS. Add Conscrypt. Record both in `android/native/THIRD_PARTY.md` and the license inventory.
- Pairing once per phone through a notification inline reply; the ADB key pair kept in private storage.
- Each run: connect, start `ShellServiceStarter` over an ADB shell stream, keep the connection open for the run. A lost connection is a worker loss handled by existing recovery.
- No Wi-Fi: refuse with a message; no hotspot or `adb tcpip` workaround.
- Fill the provider's numbered guide.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Client ported, builds at `minSdk 30` for every shipped ABI; APK size change recorded
- [ ] Pairing by notification reply works on an emulator
- [ ] Worker starts as uid 2000 over ADB; the rest of the run is unchanged
- [ ] Guide and strings; `tools/research/check_ui_strings.py` passes
