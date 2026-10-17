# 03: Restyle the Windows patcher

**What to build:** the Windows patcher follows `DESIGN.md` (see [spec](../spec.md) and the [home screen brief](../home-screen-brief.md), which sets the layout and every state).

- Light theme from `resources/ui/theme.json`; solid cards (`#F1F0FA`), 8 px corners, the hero as a locally drawn gradient image with the tagline and title.
- One centred column: hero, ① Language, ② Start (device status and working folder above the Start button), log. The seven-row sidebar goes; progress is a bar and "Step N of 7 · <step>".
- Barlow from `resources/fonts/`, loaded privately at startup (no system install); bundled by `app/build_exe.py`.
- Every user-facing string from `resources/ui/strings.json`; the interface switches to Indonesian with the language choice. Technical log lines stay raw.
- Dialogs: deep-indigo panel, ice-blue confirm button; danger dialogs use the patcher-only error red.
- Check: `run.bat` in both languages, at 100 % and 150 % Windows scaling; `build.bat` and `--selftest`.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Theme, fonts and hero
- [ ] Single-column layout and progress line
- [ ] Shared strings and Indonesian interface
- [ ] Checked from source and from the exe
