# 10: Android ② states, notices and cards

**What to build:** ② Start rewrites itself in place for every state the [brief](../home-screen-brief.md) lists, and anything that needs the player sits directly under it. See the [spec](../spec.md), "Screen".

- Result states: *Translation added*, *Translation removed*, *Translation written* and *Space freed*. Each shows the run's own counts as a short list, then the Scan to login note where the game app changed.
- Notices become one muted line inside ②, replacing the loose notice view under the log.
- The error card (cause, Copy error details, Save log for help) and the "Game won't open?" warning card move directly under ②, above the log. They use the error and warning colours.
- Behaviour is unchanged: the `copy-error`, `show-recovery` and recovery option tags, and their callbacks.

**Blocked by:** 08, 06

**Status:** ready-for-human (run `InterfaceProbeTest` on a device)

- [x] Four result states with count lists
- [x] Notice line inside ②
- [x] Error and warning cards under ②, above the log
- [ ] Probe checks the result headings in both languages

## Comments

2026-10-19: `UiText.result` turns a worker record into ②'s result: heading, summary line, count rows and login note, for *Translation added*, *Translation removed*, *Translation written* and *Space freed*; `ResultStateTest` (JVM) checks each in English and Indonesian. `GuidedHome.result` draws the counts as label/value rows with the value at the end; *Translation added* and *Translation removed* end with the Scan to login note (new string `added_login_note`, Indonesian marked `draft`). The notice line now sits inside ② under the instruction and hides when it repeats it, as a failure's friendly text does. The error card (`error-card`: cause, Copy error details, Save log for help) and the "Game won't open?" card (`recovery-card`) sit directly under ②, above the log, in the error and warning colours. Tags and callbacks are unchanged; Save log for help in the error card is a new `error-export-log` button calling the existing `export` action. `InterfaceProbeTest.startCardShowsResultStatesAndCardsSitAboveTheLog` checks the four headings in both languages, the rows, the notice's place and colour, and the card order. `testDebugUnitTest`, `assembleDebug`, `assembleDebugAndroidTest` and `check_ui_strings.py` pass. Not run on a phone: the attached one holds the release patcher, which a debug build cannot replace without an uninstall.
