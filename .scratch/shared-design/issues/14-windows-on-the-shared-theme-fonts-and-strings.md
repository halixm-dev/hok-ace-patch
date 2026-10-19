# 14: Windows on the shared theme, fonts and strings

**What to build:** The Windows patcher takes the shared look and words, while its layout stays as it is. A player sees the light theme, solid cards, 8 px corners, Barlow and the hero image, and the interface switches to Indonesian with the language choice. See the [spec](../spec.md), "Look" and "Shared files".

- Theme tokens replace the dark palette. Cards use the solid fallback, and the hero is a locally drawn gradient image.
- Barlow is loaded privately at startup, with no system install, and bundled into the exe.
- Every user-facing string comes from the shared strings file by key. Technical log lines stay raw.
- Dialogs are deep-indigo panels with the ice-blue confirm button. Danger dialogs use the error red.

**Blocked by:** 01, 05

**Status:** ready-for-agent

- [ ] Light theme, fonts and hero
- [ ] Every string from the shared file; Indonesian interface
- [ ] The shared strings contract check passes
- [ ] `run.bat` in both languages; `build.bat` and `--selftest` pass
