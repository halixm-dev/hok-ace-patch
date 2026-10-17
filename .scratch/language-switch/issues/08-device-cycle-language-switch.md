# 08: Device cycle: switch languages without clearing

**What to build:** the device verdict for 03 and 04. On a phone with a fresh download: patch English, switch to Indonesian, switch back to English, with no clear in between.

- Each step: the lobby and the screens the [indonesian-language](../../../docs/features/indonesian-language.md) record lists read in the chosen language (MULAI GAME with Indonesian text, START GAME with English), no in-game repair on launch (`normal1.log` free of `QtsfFixer|FixFile|crc not match`), and the login survives.
- Run it once through the Windows patcher and once through the Android patcher.
- Record the verdict in `docs/lab-notebook.md`, close the spec's open question (a re-patched layer is accepted without a clear), and update `docs/features/indonesian-language.md` [S3], which lists switching as out of scope.

**Blocked by:** 03 or 04

**Status:** ready-for-human

- [ ] Windows patcher: EN → ID → EN without a clear
- [ ] Android patcher: EN → ID → EN without a clear
- [ ] Lab notebook verdict; indonesian-language record updated
