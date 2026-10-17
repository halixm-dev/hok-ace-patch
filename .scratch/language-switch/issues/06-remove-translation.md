# 06: Remove translation

**What to build:** an action in both patchers that writes every patched file's pristine bytes back to the phone, with no new patch. It is the write-back transaction the update flow (07) reuses.

- Pull, `rebuild` from the delta, then write the rebuilt pristine files through the normal install path: access APK, write, Watchdog handling as an install does, normal APK. Android goes through `GameFileTransaction`, with `snapshot/` (the phone's translated bytes) as its rollback target.
- Afterwards the phone's files are pristine; the delta has no entries to rebuild from, and the next patch run makes a fresh one (the pristine signals pass).
- The re-signed normal APK stays installed. The screen says to keep using Scan to login and to reinstall from the store for the official app.
- Files matching neither staged nor pristine values: refuse before the access APK, with the clear-data message.

**Blocked by:** 03, 04

**Status:** ready-for-agent

- [x] Remove translation in the Windows patcher and the Android patcher
- [x] Android rollback verified on an interrupted write-back (fixture probe)
- [ ] Device cycle: after Remove, the lobby is Chinese, the game launches with no repair, and a new patch run succeeds without a clear

## Comments

2026-10-17, implemented. Windows: `Patcher(remove=True)`, `write_back_pristine`, the Remove
Translation button (`check_windows_repatch.py`: remove then patch again; remove with no record
refused). Android: `android_bridge.removal_bytes` / `build_removal`, `PatchCoordinator.run(remove =)`,
the worker's `remove` action, the Language-card button and the remove form of the confirmation;
`RemovalRollbackProbeTest` passes on the Xiaomi M2007J3SG (with `PristineDeltaProbeTest`, 2 tests in
6.8 s).

- Afterwards the kept delta is empty rather than absent: the next patch run rebuilds nothing, builds
  from the pristine layer and keeps a fresh delta. It skips the text signal, which only a run with no
  delta needs; the staged-hash check still runs.
- Refusals come after the pull and before any game file is written (the same timing as 03/04).
- A phone already untranslated: Windows writes nothing and says so; Android stops with that message
  (no apply cycle).
- The device cycle is still owed.
