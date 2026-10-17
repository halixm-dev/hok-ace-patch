# 06: Remove translation

**What to build:** an action in both patchers that writes every patched file's pristine bytes back to the phone, with no new patch. It is the write-back transaction the update flow (07) reuses.

- Pull, `rebuild` from the delta, then write the rebuilt pristine files through the normal install path: access APK, write, Watchdog handling as an install does, normal APK. Android goes through `GameFileTransaction`, with `snapshot/` (the phone's translated bytes) as its rollback target.
- Afterwards the phone's files are pristine; the delta has no entries to rebuild from, and the next patch run makes a fresh one (the pristine signals pass).
- The re-signed normal APK stays installed. The screen says to keep using Scan to login and to reinstall from the store for the official app.
- Files matching neither staged nor pristine values: refuse before the access APK, with the clear-data message.

**Blocked by:** 03, 04

**Status:** ready-for-agent

- [ ] Remove translation in the Windows patcher and the Android patcher
- [ ] Android rollback verified on an interrupted write-back (fixture probe)
- [ ] Device cycle: after Remove, the lobby is Chinese, the game launches with no repair, and a new patch run succeeds without a clear
