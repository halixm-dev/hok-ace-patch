# 01: Capture a real game update over a patched layer

**What to build:** evidence, not code. At the next real in-game update, record what the updater does to a patched override layer, and whether writing the pristine bytes back first lets it finish. The update flow (07) is designed on the [spec](../spec.md)'s inferences (per-asset CRC checks in `QtsVFS.dll`, lab notebook 2026-10-17); this ticket measures them.

- Before the update reaches the phone: a patched phone (English), its layer and `Watchdog` pulled, and the install's staged hashes kept.
- Let the update run untouched. Save `QtsVFS.log`, `bqLog/ccs_log/normal1.log`, `Watchdog/` and the layer afterwards. Record: did the update finish, crash, or loop; which package files changed and how (whole file or regions); what `History.db` and `BrokenList.db` logged; which text came back Chinese.
- Then the write-back trial, on a second patched phone or on the same phone after a clear and a repatch onto the old data (when old pristine data is still obtainable): write each patched file's pristine bytes back before the update, let it run, and compare.
- Record every result in `docs/lab-notebook.md`, and update the spec's "What is known" list from inferred to measured where it applies.

**Blocked by:** the next real game update (no offline stand-in: the only older local layer, `grid-regression/old-patched-game`, is already patched)

**Status:** ready-for-human

- [ ] Update over a patched layer captured (logs, `Watchdog`, layer before and after)
- [ ] Pristine write-back before the update tried and compared
- [ ] Lab notebook entry with the verdict; spec's update section updated

## Notes

Follow [device-cycle](../../../docs/runbooks/device-cycle.md). The signals ticket 07 relies on (a changed file hash, `History.db` merge events after the install) should be checked here against what the update actually leaves.
