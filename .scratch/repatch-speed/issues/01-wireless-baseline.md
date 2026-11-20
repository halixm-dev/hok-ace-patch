# Capture the current master re-patch on the Redmi

Status: resolved

- Install a signed build from `master` on `ebad528e`.
- Restore the old pristine snapshot, patch English, and capture the game after it updates itself.
- Time the automatic Re-download journey on Root. Capture the trace, staged hashes and summary, and confirm the normal APK reaches login without game repair.
- Record the baseline in the lab notebook. Use its stage timings to pick the first optimization.

## Comments

- 2026-11-20: Signed build `121` from `2938ec2` is installed. English setup and the real update to
  game data 1.11.0.2 reached login. The timed run `140b468b` waits for storage before its first
  snapshot. The normal APK is verified. Resume the saved run after the phone has 3 GB more free.
- 2026-11-20: The phone cannot free 3 GB more. The user approved Root for both timed runs. The
  Wireless debugging run stopped safely before package deletion, and the Root baseline started on
  the same installed build and updated layer.
- 2026-11-20: Root run `43db02ab` reached the download card in 14 min 39.363 s. The game reached
  login. *Downloads finished* failed at the Root preparation claim because shortage cleanup had
  made `original.apk` a symlink. With both apps stopped, the saved path was restored as a hard
  link to the same verified, read-only recovery APK. *Try again* resumed the same run and started
  its second snapshot. Record the manual recovery interval separately from stage timings.

## Answer

Master completed the Root cycle in 38 min 39 s, including 1 min 56 s of manual recovery.
The after-complete capture matched all 14 staged hashes and the game reached English login
with no `errorCode:361`. The full timing table is in the lab notebook.
