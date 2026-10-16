# Android website-inspired visual theme

## Report

The Android home screen adopts the visual direction observed at https://wxq.qq.com/ on
2026-10-06: lavender/ice-blue gradients, oversized bold type, diagonal glass geometry,
light cards and violet-blue actions. `AceHeroDrawable` draws the artwork locally.
No website images, fonts, network dependency or new library are required.

Verification on 2026-10-06:

| Check | Result |
|---|---|
| `android\\gradlew.bat -p android :app:assembleDebug :app:assembleDebugAndroidTest -PfullCodecs --offline` | PASS; final incremental build completed in 44 seconds |
| Whitespace check on changed tracked UI files | PASS |
| Deliverable | `artifacts/dev.halixm.hokacepatcher.apk` copied from the successful full-codec build |
| Visual and existing `GuidedHomeProbeTest` runtime check | Not run: Medium_Phone_API_36 emulator repeatedly refused installation with `device is still booting`; connected physical phone was offline |

No phone or game operation was performed. Visual acceptance, including large-font layout,
remains unverified. The temporary headless emulator was stopped after the failed installation attempts.

### Still owed

The existing UI probe has not been run against this theme, and nobody has inspected its rendered
screenshots; both wait for a test device.

## [S1] Problem

The plain utility screen did not resemble the game's website. Language selection, starting
the patch and support controls needed a clearer visual hierarchy.

## [S2] Design

- A gradient hero introduces the patcher and keeps partial-translation and Scan-to-login guidance.
- Numbered language and start cards separate the two main tasks.
- Existing action tags and callbacks remain stable. Buttons keep their 60 dp minimum height;
  disabled buttons and locked language choices have distinct visual states.
- System bars, native dialog accents and the launch background share the palette.
- System-bar insets protect scroll content on Android versions enforcing edge-to-edge layouts.
- Text remains native, selectable where previously supported, and scales with system font size.

## [S3] Out of Scope

Windows styling, patch pipeline changes, game assets, signing identity, permissions and recovery
routing are unchanged. This is a design adaptation, not an official Tencent application.

### Follow-up: interface language, Shizuku installation and logs

The saved patch-language choice now also selects the interface language. An idle language change
recreates the Activity immediately; changing it during an active operation remains refused.
`UiText` translates only the presentation layer, including confirmations, user guidance, completion
counts, measured storage messages and notification controls. Protocol keys, technical tool dispatch
keys, durable records and raw diagnostic logs remain unchanged. Both languages retain the same
unchecked consent requirements and data-loss warnings. Setup copy now says “translation” instead
of incorrectly promising English when Indonesian is selected.

`ShizukuLauncher` opens the installed app, then tries the explicit Google Play app, then the official
HTTPS listing. Missing/blocked handlers produce an actionable message. The home action distinguishes
installing Shizuku from starting an installed copy. No installation or permission is accepted automatically.

Both log panels are height-bounded nested scroll views. They reserve touch gestures before their
selectable text receives them; the main page remains scrollable outside the panels. Existing live-log
tail following is retained, including pausing follow when the user scrolls back.

`InterfaceProbeTest` checks picker persistence/recreation, consent wording, storage-number retention,
long-log scrolling and injected installed-app/Play/browser/failure routes without uninstalling Shizuku
or invoking game operations.

| Follow-up verification, 2026-10-06 | Result |
|---|---|
| Full-codec app and test APK build | PASS, 54 seconds; Kotlin and test sources compiled |
| Changed tracked UI files whitespace check | PASS |
| Connected Xiaomi activity-service check | No patcher service running before installation |
| `adb -s f15a72e install -r` app update | Success, existing app data retained |
| Separate test APK installation | Refused by phone: `INSTALL_FAILED_USER_RESTRICTED: Install canceled by user`; not retried |
| Runtime interface and route probes | Not run because test APK installation was refused; behavior remains runtime-unverified |

The updated full-codec deliverable is `artifacts/dev.halixm.hokacepatcher.apk`.
No game patch, game installation, Shizuku uninstall, or game-data write was started.
