# 08: Device cycle: switch languages without clearing

**What to build:** the device verdict for 03 and 04. On a phone with a fresh download: patch English, switch to Indonesian, switch back to English, with no clear in between.

- Each step: the lobby and the screens the [indonesian-language](../../../docs/features/indonesian-language.md) record lists read in the chosen language (MULAI GAME with Indonesian text, START GAME with English), no in-game repair on launch (`normal1.log` free of `QtsfFixer|FixFile|crc not match`), and the login survives.
- Run it once through the Windows patcher and once through the Android patcher.
- Record the verdict in `docs/lab-notebook.md`, close the spec's open question (a re-patched layer is accepted without a clear), and update `docs/features/indonesian-language.md` [S3], which lists switching as out of scope.

**Blocked by:** 03 or 04

**Status:** ready-for-human

- [x] Windows patcher: EN → ID → EN without a clear
- [ ] Android patcher: EN → ID → EN without a clear
- [x] Lab notebook verdict; indonesian-language record updated (Windows half)

## Comments

2026-10-17, Windows half passed on the Xiaomi M2007J3SG (lab notebook, "Language switch without a
clear"). The phone was first put back on the pristine 1.6.0.1 snapshot through the access APK instead
of a clear. Each step launched with no repair, the login survived both switches, and each switch staged
bytes identical to a build from the pristine snapshot. The first Indonesian attempt failed in the pull
(a transient Windows lock on the extracted folder's rename), fixed in `48391f7` before the retry.
Catalog fixes landed between the Indonesian and the second English step, so that step also covered a
newer translation without a clear. The Android half is still owed.
