# 04: Restyle the Android patcher

**What to build:** the Android patcher follows `DESIGN.md` (see [spec](../spec.md) and the [home screen brief](../home-screen-brief.md), which sets the layout and every state).

- Colours, glass cards and 8 px corners from `resources/ui/theme.json`, replacing the values in `GuidedHome.kt`, `AceHeroDrawable.kt` and `res/values/styles.xml` (system bars, window background, accent).
- Barlow and Barlow Condensed from `resources/fonts/`, copied into the APK by Gradle.
- `UiText` reads `resources/ui/strings.json` instead of its Kotlin table; keys, protocol strings and raw logs are unchanged.
- Progress shows "Step N of 7 · <step>" where a step applies; recovery and setup flows keep their own wording.
- Place the newer controls as the brief sets: notices as a line inside ②, not a loose `friendly-notice` view under the log; the error card and the "Game won't open?" warning card directly under ②, above the log; Free up space with Check for updates in the footer. Remove translation stays in ① as a secondary button.
- Critique fixes (2026-10-19):
  - Use the four `DESIGN.md` type steps (title, heading, body, label) in place of the eight sizes now in use (11 to 32 sp). Mark headings explicitly, not by `size >= 23`.
  - Disabled language choices use `disabled-text`, not `alpha = 0.55`.
  - The hero eyebrow reads `COMMUNITY PATCHER  /  HOK ACE`, not `HONOR OF KINGS  /  ACE`. Drop the "Your next move" tagline (the brief allows one line), and remove the footer copy of the eyebrow.
  - Make Remove translation an outlined secondary button below the choices, not above them.
  - Group the footer and recovery options as the spec says.
  - Give the success states the run's counts as a short list, not one muted paragraph.
  - The progress bar is determinate once ticket 07 lands.
- Behaviour is unchanged: action tags (`remove-translation`, `free-space`, `free-space-recovery`, `copy-error` included), callbacks, consent checkboxes, button heights (60 dp minimum) and the language lock during work stay as they are.
- Check: unit tests and `InterfaceProbeTest`; a visual check on a phone (`docs/runbooks/device-cycle.md`), including large font size, with screenshots looked at. No game operation is needed.

**Blocked by:** 01, 05, 06, 07

**Status:** wontfix (superseded by 08, 09, 10, 12 and 13)

- [ ] Theme, glass cards and fonts
- [ ] `UiText` on the shared strings
- [ ] Notices, error and warning cards placed per the brief
- [ ] Tests pass
- [ ] Visual check on a phone

## Comments

2026-10-19: split into vertical slices; superseded by tickets 08, 09, 10, 12 and 13.
