# 04: Restyle the Android patcher

**What to build:** the Android patcher follows `DESIGN.md` (see [spec](../spec.md) and the [home screen brief](../home-screen-brief.md), which sets the layout and every state).

- Colours, glass cards and 8 px corners from `resources/ui/theme.json`, replacing the values in `GuidedHome.kt`, `AceHeroDrawable.kt` and `res/values/styles.xml` (system bars, window background, accent).
- Barlow and Barlow Condensed from `resources/fonts/`, copied into the APK by Gradle.
- `UiText` reads `resources/ui/strings.json` instead of its Kotlin table; keys, protocol strings and raw logs are unchanged.
- Progress shows "Step N of 7 · <step>" where a step applies; recovery and setup flows keep their own wording.
- Behaviour is unchanged: action tags, callbacks, consent checkboxes, button heights (60 dp minimum) and the language lock during work stay as they are.
- Check: unit tests and `InterfaceProbeTest`; a visual check on a phone (`docs/runbooks/device-cycle.md`), including large font size, with screenshots looked at. No game operation is needed.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Theme, glass cards and fonts
- [ ] `UiText` on the shared strings
- [ ] Tests pass
- [ ] Visual check on a phone
