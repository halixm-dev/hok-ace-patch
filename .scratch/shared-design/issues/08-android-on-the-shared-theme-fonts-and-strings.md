# 08: Android on the shared theme, fonts and strings

**What to build:** The Android patcher reads its look and its words from the shared files, while its layout stays as it is. A player sees the new colours, 8 dp corners, Barlow type and the corrected hero, in English or Indonesian. Every string comes from the shared strings file, and the in-code translation table goes. See the [spec](../spec.md), "Look" and "Shared files".

- Theme tokens replace the hard-coded colours in the home screen, the hero drawable and the window style: system bars, window background and accent.
- Barlow and Barlow Condensed ship in the APK, copied in by Gradle.
- Use the four type steps (title, heading, body, label) in place of the eight sizes in use now. Mark headings explicitly.
- The hero eyebrow reads `COMMUNITY PATCHER  /  HOK ACE`, and the hero keeps one line on the partial translation and Scan to login. The tagline and the footer copy of the eyebrow go.
- `UiText` resolves every string, and every built text, through the shared strings file by key. Action tags, protocol keys and raw logs are unchanged.

**Blocked by:** 01, 05

**Status:** ready-for-agent

- [ ] Theme tokens, fonts and the corrected hero in place
- [ ] `UiText` reads the shared strings file; the Kotlin table is gone
- [ ] The shared strings contract check passes
- [ ] `InterfaceProbeTest` passes in both languages, with its screenshot looked at
