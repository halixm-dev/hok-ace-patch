# Android patcher update checker

## Report

Added a manual update checker to the home screen, below Technical tools, with the installed
patcher version. The button, progress state and result dialogs support English and Indonesian.
Checks run on a separate executor and never use the patch worker or Shizuku. Duplicate taps
are disabled until the check finishes; destroyed activities discard results and dismiss dialogs.

Local verification is recorded in the lab notebook under **2026-10-17 — Android patcher update
checker**. Phone installation, browser download and Android installer acceptance require a device
and have not been tested.

`android/gradlew.bat -p android :app:testDebugUnitTest :app:lintDebug :app:assembleDebug`
passes. The first offline attempt compiled the app but lacked the test-only JSON dependency;
retrying with network access completed verification. The public API's current APK name, upload
state and exact download URL were also checked without credentials.

## [S1] Problem

Android users need to find newer patcher releases from inside the app without interrupting
the translation workflow. Patcher versions have five numeric components, so string comparison
would incorrectly rank revision 10 below revision 9.

## [S2] Design

| Area | Behavior |
|---|---|
| Trigger | Manual Check for updates button; no startup check or reminders |
| Source | Unauthenticated HTTPS GET to the repository's latest-release endpoint |
| Version | Require android-v plus five numeric components; compare each numerically |
| Stable releases | Refuse draft, prerelease, unrelated tags and malformed metadata |
| Download | Offer only a newer release with an uploaded, nonempty hok-ace-patch.apk |
| Destination | Exact HTTPS GitHub asset URL for the returned repository/tag |
| Installation | Browser handles download; Android handles user-approved installation |
| Busy patcher | Ask the user to finish patching/recovery before opening the download |
| Failures | Explain offline, timeout, rate limit, missing release/APK or invalid response; allow retry |
| Limits | 10-second connect/read timeouts, 1 MiB response cap; disable HTTP redirects and caching |

The endpoint and public unauthenticated access follow the official
[GitHub latest-release documentation](https://docs.github.com/en/rest/releases/releases#get-the-latest-release).
The request sets the recommended Accept header, API version and a product User-Agent. No token
is embedded. INTERNET is a normal Android permission and needs no runtime prompt. Download links
use the specific returned tag, avoiding a moving latest/download target after a check.

The handoff left UI and download policy open. This implementation chooses the recommended small
manual checker and a browser download. No earlier publication authorization is carried forward.

## [S3] Out of Scope

Automatic checks, reminder scheduling, managed APK downloads, silent installation, release
publication and version bumps. This checks the patcher release, not the game's in-game updates.
