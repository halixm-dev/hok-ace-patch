# 08: Android on the shared theme, fonts and strings

**What to build:** The Android patcher reads its look and its words from the shared files, while its layout stays as it is. A player sees the new colours, 8 dp corners, Barlow type and the corrected hero, in English or Indonesian. Every string comes from the shared strings file, and the in-code translation table goes. See the [spec](../spec.md), "Look" and "Shared files".

- Theme tokens replace the hard-coded colours in the home screen, the hero drawable and the window style: system bars, window background and accent.
- Barlow and Barlow Condensed ship in the APK, copied in by Gradle.
- Use the four type steps (title, heading, body, label) in place of the eight sizes in use now. Mark headings explicitly.
- The hero eyebrow reads `COMMUNITY PATCHER  /  HOK ACE`, and the hero keeps one line on the partial translation and Scan to login. The tagline and the footer copy of the eyebrow go.
- `UiText` resolves every string, and every built text, through the shared strings file by key. Action tags, protocol keys and raw logs are unchanged.

**Blocked by:** 01, 05

**Status:** ready-for-human (run `InterfaceProbeTest` on a device)

- [x] Theme tokens, fonts and the corrected hero in place
- [x] `UiText` reads the shared strings file; the Kotlin table is gone
- [x] The shared strings contract check passes
- [ ] `InterfaceProbeTest` passes in both languages, with its screenshot looked at

## Comments

2026-10-19: Gradle's `stageUiResources` turns `theme.json` into `values/theme.xml` (colours, corners, spacing, type sizes), copies the fonts to `res/font/`, and packs `strings.json` and the font licence as class resources, so `UiText` and the JVM tests read the same file. `assembleDebug`, `assembleDebugAndroidTest` and `testDebugUnitTest` (27 tests) pass. The probe now also checks the hero eyebrow in both languages, that the tagline is gone and the Indonesian built texts, and saves `interface-en.png` beside `interface-id.png`. It has not run yet: the attached phone holds the release patcher signed with the private key, which a debug build cannot replace without an uninstall, and this PC lacks the disk space for the emulator.
