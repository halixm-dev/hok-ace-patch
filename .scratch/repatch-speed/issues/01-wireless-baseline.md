# Capture the current master re-patch on Wireless debugging

Status: needs-info

- Install a signed build from `master` on `ebad528e`.
- Restore the old pristine snapshot, patch English, and capture the game after it updates itself.
- Time the automatic Re-download journey on Wireless debugging. Capture the trace, staged hashes and summary, and confirm the normal APK reaches login without game repair.
- Record the baseline in the lab notebook. Use its stage timings to pick the first optimization.

## Comments

- 2026-11-20: Signed build `121` from `2938ec2` is installed. English setup and the real update to
  game data 1.11.0.2 reached login. The timed run `140b468b` waits for storage before its first
  snapshot. The normal APK is verified. Resume the saved run after the phone has 3 GB more free.
