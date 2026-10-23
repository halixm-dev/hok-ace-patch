# 01: Capture a real game update over a patched layer

**What to build:** evidence, not code. At the next real in-game update, record what the updater does to a patched override layer, and whether writing the pristine bytes back first lets it finish. The update flow (07) is designed on the [spec](../spec.md)'s inferences (per-asset CRC checks in `QtsVFS.dll`, lab notebook 2026-10-17); this ticket measures them.

- Before the update reaches the phone: a patched phone (English), its layer and `Watchdog` pulled, and the install's staged hashes kept.
- Let the update run untouched. Save `QtsVFS.log`, `bqLog/ccs_log/normal1.log`, `Watchdog/` and the layer afterwards. Record: did the update finish, crash, or loop; which package files changed and how (whole file or regions); what `History.db` and `BrokenList.db` logged; which text came back Chinese.
- Then the write-back trial, on a second patched phone or on the same phone after a clear and a repatch onto the old data (when old pristine data is still obtainable): write each patched file's pristine bytes back before the update, let it run, and compare.
- Record every result in `docs/lab-notebook.md`, and update the spec's "What is known" list from inferred to measured where it applies.

**Blocked by:** the next real game update (no offline stand-in: the only older local layer, `grid-regression/old-patched-game`, is already patched)

**Status:** ready-for-human

- [x] Update over a patched layer captured (logs, `Watchdog`, layer before and after)
- [ ] Pristine write-back before the update tried and compared (not run: see Notes, 2026-10-23)
- [x] Lab notebook entry with the verdict; spec's update section updated

## Notes

Follow [device-cycle](../../../docs/runbooks/device-cycle.md). The signals ticket 07 relies on (a changed file hash, `History.db` merge events after the install) should be checked here against what the update actually leaves.

2026-10-23: captured on the Xiaomi M2007J3SG with `tools/research/update_cycle.py`, pristine 1.6.0.1 pushed,
Android patcher English, then the game's own update to 1.7.0.1 (lab notebook, "An update over a patched
layer, captured end to end"). The update gives no prompt and leaves no trace before it runs
(`NewVersionInfo.json` unchanged throughout); it merged diffs into 38 packages, the translated ones among
them, then stuck on package `1` (`detected db corruption 1_0`, the repair's `put page failed`) and left
`10`, `15`, `19`, `20`, `21` mixed. `History.db` logged the merges after the install (signal (ii) holds;
`tools/research/watchdog_history.py` read the 38 merges). Re-download, then asset restore, recovered without a clear.

The write-back trial was not run: nothing on the phone shows an update before the game opens and runs
it, so the patcher has no moment to write the pristine bytes back first. The spec owner chose the
after-update path for ticket 07 instead (2026-10-23). Done.
