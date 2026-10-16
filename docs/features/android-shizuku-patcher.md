---
feature: android-shizuku-patcher
status: device-validation-in-progress
updated: 2026-10-05
---

# Android patcher using Shizuku

## Report

### Current acceptance: successful Xiaomi full patch (2026-10-05)

The user reports a successful full patch from the Android app. Read-only retrieval of its worker result, session journal, build summary and resource metrics confirms a completed live snapshot → build → apply → normal-APK restore cycle on the Xiaomi M2007J3SG / MIUI Android 12, using game data **1.4.0.2**. Evidence: `artifacts/android-live-patch-success-20261005.json`; session `8a804248-73fd-4b29-89f7-95fdca95f79c`. No new patch, installation or game-data write was performed while collecting this documentation evidence.

| Result | Recorded value |
|---|---|
| Worker / journal | `complete` / `COMPLETE` |
| Applied translation | 391 text tables; 395 textures across six packages |
| Known skipped content | One prime-only text table refused by the append encoder; zero skipped textures |
| Committed package files | 12 index/shard files in packages `1`, `15`, `19`, `20`, `21`, `1050016095` |
| Final safety state | `normal_verified=true`, `patch_payload_verified=true`, `packages_dirty=false`; no pending mutation or normal-restore intent |
| Retained normal APK SHA-256 | `29b3ee7e5a0d21de7d1282d704416402d341b651da95af2eeb5b274c818defdc` |
| Snapshot | 1,990,685,775 payload bytes; 501 files and 289 directories |
| Coordinator duration | 382.265 seconds (about 6 minutes 22 seconds) |
| Sampled free space | 11.39 GB initially; 5.25 GB minimum; 6.14 GB observed decrease |
| Sampled memory / temperature | Maximum sampled RSS 2,215,200 KiB; process high-water RSS 2,332,424 KiB; maximum battery temperature 38.0°C; thermal status 0 |
| Additional candidate assets | None (`cycle_assets=[]`); existing catalog/allowlist only |

This closes the first successful normal-path live coordinator cycle on the measured Xiaomi, including cached APK reuse, measured storage budgeting, updater-directory extraction and the foreground automatic flow. It does not establish a complete translation, watched-screen visual acceptance, first-official conversion acceptance, a repeat patch on the newly translated layer, deliberate live failure injection, another OEM, Android 15/16 KiB pages, or a cable-disconnected release cycle. Resource observations are one run, not minimum device requirements or guaranteed storage needs. The existing 391/395 coverage and one-table gap are unchanged.

### Journey log: earlier fixes and feasibility evidence

Unlistable profile on two Transsion phones (2026-10-09), the same failure in two users' exported `hok-ace-recovery-log.txt`: an Infinix X678B (XOS, Android 14 API 34 build `250217V838`) and a TECNO KL7 (HiOS, Android 14 API 34 build `260701V1096`), both with Shizuku 13.6.0 as uid 2000, game 1.1.1 / 774472 and language `id`. On each, `prepare` succeeds with `requires_signature_conversion: true`, then `first_setup` stops twice (about 32 s in on the Infinix, about 65 s on the TECNO) with `Device command failed (255)` and `java.lang.SecurityException: Shell does not have permission to access user 999` from `pm list packages --user 999`; only the framework line numbers differ between the two builds. On the TECNO, `pm list users` names it as `UserInfo{999:Ruang Ganda:1010} running` (the Dual App profile; flags `PROFILE | INITIALIZED`), and the refusal is AOSP `UserController.handleIncomingUser`'s shell check, which fires only for a target user carrying `DISALLOW_DEBUGGING_FEATURES` (the ` ...handleIncomingUser:14469 ...` caller line after the message, `:14398` on the Infinix, is that check's `Debug.getCallers(3)`). So shell cannot name user 999 in any `--user` command, while `dumpsys package` and `pm uninstall` with no `--user` (all users, -1) never reach that check. `requireNoOtherGameUsers` failed before any removal; the game stayed installed and unchanged. The TECNO user's own report confirms the cause on that device: switching Dual App off left user 999 `running`, and patching succeeded only after `pm remove-user 999`. The UI turned that into the Shizuku-permission advice because the raw error contains "permission", although Shizuku was working. On both phones a later `verify` against the prepared normal APK reported `Installed APK stream is incomplete`: the installed app was still the original, which is shorter than the normal one, so it was a different app rather than a truncated read. Fix, unit-tested offline (`app/src/test/.../FirstSetupProfileTest.java`) but **not yet device-verified**: when `pm list packages --user N` fails with exactly that SecurityException for N, the guard reads every profile's state from `dumpsys package <game>` (written by system_server, grep-filtered to the `Package [..]` and `User N: .. installed=` lines so the 16 KiB diagnostic cap cannot cut it off). An installed copy is still refused (`The game is installed in another Android profile`); a profile the dump does not list is refused as `Cannot check another Android profile for the game`; a dump with no record of the package counts as absent only when `pm list packages -u` agrees. `friendlyFailure` now has its own messages for those two refusals, for an installed app that is not the expected one (`InstalledGameVerifier.DIFFERENT_APP`, replacing the stream, length, hash and identity messages) and for any other `Device command failed`, ahead of the Shizuku branch. Two follow-ups from the TECNO user's report, also compiled and unit-tested only: `prepare` now runs the same read-only profile check (`IPrivilegedDeviceService.checkGameProfiles`, transaction 19, `PROTOCOL_VERSION` 9) before it copies anything, whenever the installed game's signer is not the stable key (or Android will not say), so a phone that will be refused at first setup learns it before the 3–4 minute preparation rather than after; first setup keeps its own check. And the screen no longer buries the cause: the live log stores `ErrorSummary.cause` of each message (stack frames, `... N more` and Android's appended caller list dropped, at most 8 lines), because a 30-line trace in the 180 dp log scrolled the `SecurityException` line out of view, and a failed run shows an Error details box under the notice with that summary and a Copy error details button that copies the worker's full raw `error` (`ErrorSummaryTest`).

Game missing for the main user (2026-10-09, same Infinix X678B, on the build above): the next exported log shows `prepare` stopping 0.2 s after the worker attached with only `Device command failed (1):` from `gameApkInfo`, which the new fallback above turned into "The phone refused a step". The environment block reads `game: not installed`, and the patcher's own data was fresh (no `preparations/` or `recovery/`), so the patcher had been reinstalled or cleared since the morning's runs; the earlier `first_setup` refusals stopped before any removal, so the patcher did not remove the game. `pm path --user 0 <game>` exits 1 and prints nothing when the package is not installed for user 0, including when it exists only in a Dual App profile. `gameApk` now raises `PrivilegedDeviceService.GAME_MISSING` for exactly that result, and `friendlyFailure` tells the user to install the game in the phone's main space, open it once and finish downloads, then try again. Compiled and unit-tested only. The user then reported the game **is** installed in the main space. Both lookups that said otherwise (the app's `getPackageInfo(game, 0)` and `pm path --user 0`) skip a package that is installed but hidden (XOS/HiOS Hide apps) or disabled until used, exactly as they skip an absent one, and XOS shows Dual App icons on the same home screen, so the log alone cannot tell the three apart. The missing-game error now carries each profile's `installed / hidden / suspended / enabled` state from the filtered `dumpsys package` (`FirstSetupPackagePolicy.userStates`), `friendlyFailure` names the case it finds (`missingReason`: hidden, only in another profile, or absent), and the export's `game:` line asks again with `MATCH_UNINSTALLED_PACKAGES` and says whether the record is installed for this user but unavailable, or held only elsewhere. The next log from this phone settles which it is.

It settled it as absent (2026-10-09, same Infinix X678B, exported 18:58): the first `prepare` stopped with `not installed for the phone's main user (com.tencent.tmgp.osgame; no package record)`, so no profile held the game at all. The user then installed it (`installed 2026-10-09 18:24:05`). The next two `prepare` runs got through `Checking other Android profiles for the game` in 0.4 s, copied the installed APK, and then stopped at `engine_preflight` with `Android requires all codecs and an empty package rebuild configuration`. That was the build, not the phone: the APK handed out from this branch had been built without `-PfullCodecs`, so its `requirements-arm64-v8a.imy` was empty and it carried no `astc_encoder`, `texture2ddecoder`, `ooz` or Pillow, which `REQUIRED_CODECS` gates on. The same phone had passed the preflight that morning on a full-codec build. The full-codec build is now Gradle's default and `-PfullCodecs=false` selects the minimal baseline, so a plain `assembleDebug` can no longer produce an APK that refuses every patch. The log does not say whether user 999 was still present when the profile check passed, so the fallback's device verification is still open.

Worker connection timeout on a second phone (2026-10-06): a user's friend got `Shizuku worker connection timed out` on four `prepare` attempts while the Shizuku app showed the server running (exported `hok-ace-recovery-log.txt`: the worker's last message comes 20 s after `Preparing verified recovery material`, and the activity never logged `Shizuku UserService connected`). Shizuku's `ServiceStarter` hands the new user-service binder back through the **Shizuku app's** content provider (`moe.shizuku.privileged.api.shizuku`, call `sendUserService`), not the server. If the provider is null it logs `provider is null` and exits with no retry. So a phone that will not start the Shizuku app in the background loses the handoff silently, while `pingBinder()` still succeeds. That fits the report and the earlier intermittent Xiaomi timeout, but no device log has confirmed it yet. The wait is now 45 s for a slow cold start. The timeout message carries the Shizuku version and uid, the phone's make, model and Android version, and the wait, so the next exported log identifies the phone. The home screen now tells the user to allow Shizuku to run in the background and keep it in Recents. Verified only by compiling: debug and release Kotlin builds and the unit tests pass. Not verified on the affected phone.

Measured on the affected phone (2026-10-06): the background-start guess above is **not** the cause there. The phone is an Infinix X6853 (XOS, MediaTek, Android 16 API 36), running Shizuku 13.6.0 as uid 2000. The new trace shows the bind issued at 12:15:15.475, no binder by 45 083 ms, and the server still answering pings. No user-service process appeared. Running Shizuku's own starter by hand (`CLASSPATH=<Shizuku apk> app_process64 /system/bin ... moe.shizuku.starter.ServiceStarter --package=dev.halixm.hokacepatcher --class=...PrivilegedDeviceService`) exits 1 after 0.4 s: `unable to start service`, caused by an NPE at `LoadedApk.makeApplicationInner(LoadedApk.java:1536)`. The phone's own `framework.jar` shows that line is MediaTek code: `Application.getProcessName().equals(mPackageName)` guarding `ResOptExt.preloadRes`. It runs for any non-system package, and the process name is null in a Shizuku user-service process. Shizuku's `UserService.create` calls `makeApplication(true, null)` before it loads the service class, so no code in this app runs and any Shizuku user service fails on this ROM. Upstream reports: RikkaApps/Shizuku#2048 (Transsion), #2561 (Android 16), #1198 (MediaTek); no upstream fix. This phone hides app and Shizuku log lines from logcat, so the app's own trace file was the only usable record.

Own-starter fallback (2026-10-06, device-verified on the Infinix):
- **Connection order.** `WorkerDeviceConnection` still asks Shizuku for the user service first. After 10 s with no binder it also launches `ShellServiceStarter` through Shizuku's shell-process API (`Shizuku.newProcess`, private in API 13.1.5 and reached by reflection): `CLASSPATH=<this APK> exec app_process /system/bin --nice-name=<pkg>:worker dev.halixm.hokacepatcher.ShellServiceStarter <token> <authority>`, passed as `sh -c` positional arguments rather than spliced into a string.
- **Skipped step.** The starter constructs `PrivilegedDeviceService` directly. It needs no Context, so it skips the `makeApplication` step that crashes.
- **Handoff.** The starter hands the binder to `WorkerBinderProvider` through `getContentProviderExternal` and `IContentProvider.call`, the same handoff Shizuku's own starter uses with its manager. Three gates protect it:
  - the provider is guarded by `INTERACT_ACROSS_USERS_FULL`, which only the shell holds;
  - `call` refuses any caller but uid 2000;
  - each connection's random token is single use and registered only while that connection waits.
- **First binder wins.** A late binder from the other path is refused. The starter exits when the app's client binder dies, and `close()` destroys it.
- **Remembered per phone.** The working path is saved under the ROM fingerprint plus the Shizuku server and app versions, so the next run on this phone starts the fallback at once. A new ROM build or Shizuku release tries Shizuku's starter again.

Measured:
- By hand from adb (uid 2000) with a dummy token, the starter loads, builds the service and reaches the provider, which answers `SecurityException: Unknown or used worker token` (exit 1 in 0.87 s; Shizuku's starter died there with the NPE).
- In the app, Start → prepare: no Shizuku binder after 10 016 ms, fallback launched at 10 028 ms, binder at 10 323 ms (`worker attached as uid 2000`). Preparation then completed (`prepared`, `requires_signature_conversion: true`; `prepare_game_apks` took 144.6 s). On close the starter exited with code 143 and left no worker process.

The first-setup consent that follows was left for the phone's owner, so no install or game-data step has run through this path yet. The Xiaomi path, where Shizuku's starter works, is unchanged in code but was not re-run.

Diagnostic trace (2026-10-06): the earlier export could not tell this phone apart. It held only untimed UI messages and the last 40 worker messages, and stack traces existed only in logcat. `DiagnosticTrace` now writes `trace.log`, rotated to `trace.log.1` past 1 MB. Each line has a timestamp, pid and tid, and errors carry full stack traces. It records:
- UI taps, home-screen changes and Activity lifecycle;
- Shizuku binder and permission events;
- worker start, progress, results, timeout and destruction;
- each step of the worker's Shizuku binding, with elapsed milliseconds;
- timing for every engine call;
- uncaught crashes.

It is evidence only: nothing reads it back, and a failed write is ignored. "Export diagnostic logs" adds:
- an environment section: app and build type, device, Android and ROM properties from a fixed allowlist, memory, battery-optimization and background state for this app and the Shizuku app, the Shizuku server's version, uid, SELinux context and permission, and the game's version and debuggable flag;
- the app's last 20 process exits from `getHistoricalProcessExitReasons`;
- per-folder storage use;
- the `build.log` and `metrics.json` of the three most recent runs;
- this app's own logcat, the last 5000 lines.

The trace and the build logs come after the recovery records, so the 8 MB export limit never drops a journal for them. Verified by compiling the app and the Android tests; not yet exported on a phone.

Storage reclaim and build estimate (2026-10-06): users reported running out of space after the first check had passed. Three causes, all in this app's own files. (1) Nothing removed a resolved session's bulk: every completed or cancelled run kept its game-data copy (about 2 GB on the 1.4.0.2 layer), `work/` and `out/` forever, so each repeat run started roughly 4 GB shorter. A session that reaches `COMPLETE` or `CANCELLED` now keeps only `journal.json`, the hash lists, logs, `snapshot/manifest.json` and `out/device_patch_summary.json`; the coordinator clears its bulk at the end of the run or recovery, and clears every earlier resolved session before a run's first budget. Rollback and forward recovery read only an unresolved session's files, and a damaged journal is left alone. (2) The saved official APK (`preparations/<id>/original.apk`, about 2 GB) was kept although nothing reads it after the normal and access APKs are derived; reuse, first setup and recovery go by the receipt's identity. `ApkPreparation.releaseUnneeded` deletes it once the installed game is verified as the stable-key normal build: after first setup installs the normal app, and at the start of every patch run. The same pass deletes every preparation folder whose receipt names another game version (its access APK, about 2 GB each): access is installed only over a normal build of the same version, and a new version prepares its own. The run's own preparation, a folder whose receipt will not read and anything a retained APK path links to (an unresolved session's access APK, a deduplicated copy) are kept, and it skips while a preparation runs. Recovery APKs in `recovery/` are not touched. (3) The offline-build estimate reserved every downloaded package twice and the whole APK prime, 7.50 GB on the 2.72 GB control whose actual build left 1.62 GB (`out/` 0.99 GB, `work/` 0.63 GB, `artifacts/android-control`). `build_storage.estimate` (schema 2) now reserves, twice, only the packages that hold a catalog table, texture, device revision, allowlisted or script asset, and extracts only the APK packages whose catalog content the downloaded copy lacks, as `add_prime_only` does: 2,668,538,356 bytes on the same control (prime index 37.7 MB, prime extraction 588.7 MB, staged 916.6 MB twice, replacement work 208.9 MB). On the 2026-10-05 live run, the build check reserved 6.04 GB plus installer space while the lowest sampled free space showed about 4.14 GB used from build start through the apply installs. `work/` is deleted once the build stages, before both apply installs. The snapshot check also reserves the latest completed run's schema-2 build estimate, so a copy that fits is not followed by a build that cannot. The build step still checks its own measured estimate. Verified offline: Kotlin and Android-test compilation, the six `StorageMessageTest` checks, and the estimate against the desktop control. Not yet verified: a device run, the updated `BuildStorageProbeTest` numbers on the phone, and the interrupted low-space path.

Snapshot updater-directory correction: actual Xiaomi run fails at extraction with `ValueError: Unsupported package path`; worker then reinstalls and independently verifies normal APK recovery before reporting error. The saved archive inventory has 790 entries, including 84 previously unrecognized empty directories under `packages/builtin/Merge` and `packages/builtin/CleanCopy`. No file entry is outside the old allowlist. The Python reader now permits only these two directory roots and one unsigned 32-bit package-ID child; files under them, arbitrary nested names, traversal and links remain refused. The native writable-file policy is unchanged. Errors now include the rejected package path. Five offline regression cases pass, and all 790 actual archive member names/types validate (`artifacts/android-snapshot-path-regression.json`). APK-cache provenance no longer requires the current translation engine hash: independently verified APK hashes/versions/signers/debug flags remain the cache gate, so this Python-only update reuses the saved APKs instead of creating a new preparation. Engine preflight still runs for a patch. Full-codec debug build and six existing host storage checks pass (`artifacts/android-snapshot-path-final-build.log`); the updated APK was installed after confirming the failed worker retired. A standalone cache-only worker returns `prepared` using the same existing preparation and normal identity after the engine update, explicitly reporting no new APK copies (`artifacts/android-snapshot-fix-cache-receipt.json`). No patch/apply was launched during this fix.

Actual cache-only Xiaomi verification: app update installed with data retained. A fixed `prepare` operation launched under the app UID (UI automatic flow unarmed) reuses preparation `63afb12f-087f-48d1-9f30-e4bc1553a57a`, independently streams/verifies the installed normal APK, reports no signature conversion, and creates no new preparation folder. Initial hard-link attempts are denied by phone policy; private symbolic references succeed. Final pass rehashes each candidate and shared target before durable atomic replacement and reports 8.1 GB reclaimed. Free space becomes 13,403,295,744 bytes (`artifacts/android-cache-reuse-device-receipt.json`). Recovery normal/source/access paths remain; immutable content is retained, not regenerated or discarded. Standalone cache verification does not arm continuation, install the access game APK, or write game data. A second standalone preparation also returns `prepared`, loads the shared APKs through full manifest/hash checks, selects the installed normal identity (no first-setup conversion), and leaves exactly the same three preparation directories with no new APK copies (`artifacts/android-cache-reuse-repeat-receipt.json`). This verifies reuse after consolidation; the separate confirmation instrumentation probe remains unrun. Final APK is `artifacts/dev.halixm.hokacepatcher.apk`.

Cache/storage retry correction: the user reported repeated APK preparation and a 13.3 GB free-space refusal after downloading the game. The app-private inventory showed three preparation folders totaling 12.17 GB, plus a 2.03 GB normal recovery APK. The recorded refusal was 13,275,216,396 additional bytes with only 5,326,036,992 available, before any patch session/game access installation. Preparation previously always created a fresh UUID directory, and snapshot preflight reserved a fixed 8 GiB. Preparation now verifies/reuses matching cache content before storage allocation, retains historical source identity separately from the current installed source, and binds patch confirmation to the selected source. Byte-identical immutable APKs are durably linked (hard link or private symbolic reference to an immutable retained target) without dropping recovery paths, including per-session access files (space-checked copy fallback). The coordinator reserves installer recovery space first, then measures game files/directories under the existing lock after access installation and reserves archive plus extraction plus normal-APK install space. Any refusal uses existing restoration handling. The 8 GiB maximum and offline build/write reserves remain intact. Full-codec build, six existing host checks and Android-test compilation pass (`artifacts/android-cache-storage-build.log`, `artifacts/android-cache-storage-final-build.log`). Actual Android measurement command against tiny app-private synthetic files yields a 4,608-byte tar safely below the 16,792,809-byte budget (`artifacts/android-snapshot-estimate-shell-check.json`). Dedicated cache test APK installation was cancelled by MIUI; no instrumentation pass is claimed. At this checkpoint live patch/restore with the revised budget was unverified; the successful 2026-10-05 cycle above now exercises its normal path.

The main screen now shows a scrollable live activity log, refreshed by the existing one-second status poll. Worker state retains the latest 40 timestamped progress/error messages (each capped at 2,000 characters), including terminal results, so reopening the activity preserves recent progress. Each admitted worker operation clears its history; scrolling up pauses automatic following until the user returns to the bottom. No synthetic percentage or device operation was added. Full-codec debug build and existing six host storage checks pass (`artifacts/android-live-progress-build.log`). After the user reconnected the Xiaomi, ADB confirmed no patcher service was running and installed the updated APK successfully with existing data retained. On-device log display during a live patch remains unverified; no patch or game operation was started.

An Android feasibility application has been built and installed alongside the Windows patcher.
On the Xiaomi M2007J3SG / Android 12 phone, the Shizuku UserService runs as UID 2000 in
`u:r:shell:s0`, discovers the unsplit game APK, and round-trips 4096 random bytes through a
disposable debuggable fixture. An ordinary patcher process receives EACCES when trying to
execute `run-as`. Shizuku authorization was granted by the user. The separately authorized
live-game diagnostic installed the access APK and read version 1.4.0.2, round-tripping 4096
temporary bytes as the game UID. No translation packages or Watchdog contents were changed.

The user separately authorized copying the pristine dump and matching normal APK into the
feasibility app's private scratch storage. The full DLL-free engine completed a build there,
with Python 3.12.12 and all five codec imports loading. The corrected full graphics oracle
also passed; its original malformed synthetic ASTC fixture caused a native decoder crash.
The staged asset comparison passed its numerical checks. The first normal-APK restore timed
out under the diagnostic's 30-second deadline; USB fallback restored the exact normal APK,
verified by streaming/hash and a cleared debug flag. The retry with 180-second installer
write/commit deadlines passed in 132.245 s, including normal APK hash/signature/debug checks.
The restored game reached its main lobby with the pre-existing English UI. Full coordinator
orchestration now passes private-scratch success and rollback tests with simulated installation
and game transport. The 2026-10-05 cycle above now confirms normal-path live coordinator completion. Deliberate interrupted live-package recovery and release acceptance remain open.
The development UI offers an explicitly confirmed patch request for converted installs, now exercised against live game data. First-setup consent, foreground dispatch,
installation recovery and a fresh-update checkpoint are connected; actual first-official
conversion and release acceptance remain unfinished. Android-generated translation was applied in the successful 2026-10-05 cycle above; its remaining visual/device gates stay open.

### Implemented spike and observed results (2026-10-03)

| Check | Observed result / evidence |
|---|---|
| Quantified low-storage guidance | Six host JVM checks pass (`artifacts/android-storage-message-build.log`, `android/app/build/test-results/testDebugUnitTest/TEST-dev.halixm.hokacepatcher.StorageMessageTest.xml`). Existing exact byte failures now render required/current/additional decimal GB, rounding required up and free down to 0.1 GB. Additional clearing advice is the difference of displayed values and never understates the measured deficit. Main screen refreshes current usable space and switches to retry advice once sufficient. Legacy saved byte messages, latest recovery shortage, tiny deficit, locale, invalid/unknown amounts and Long.MAX_VALUE/overflow refusal are checked; one test forces the real unchanged budget guard to refuse without allocating files. Unknown installer thresholds stay explicitly unknown. Byte thresholds, recovery reserve and files are unchanged; no live low-space patch/uninstall test. |
| Launcher branding and package identity | PASS: full-codec app/test compilation (`artifacts/android-launcher-branding-build.log`); renamed app installed as `dev.halixm.hokacepatcher`, launcher label **HOK ACE Patcher**. SDK badging and compiled XML/resources verify adaptive icon, foreground inset and exact `#ff9ebef7` background (`artifacts/android-launcher-branding-*.txt`). Attached foreground copy is byte-identical; packaged alpha and visible RGB pixels match the original. Installed APK SHA matches `artifacts/dev.halixm.hokacepatcher.apk`; receipt `artifacts/android-launcher-branding-receipt.json`. Old app remains installed with its recovery data; no migration, old-app uninstall or game operation. Home Test version badge removed. MIUI canceled the optional renamed test-APK install with INSTALL_FAILED_USER_RESTRICTED, so the focused device-resource instrumentation did not run; compiled-resource and installed-byte checks were used instead. |
| Automatic UI routing | PASS: final full-codec build (`artifacts/android-automatic-ui-final-build.log`), eleven actual checks in 24.903 s (`artifacts/android-automatic-ui-final-probes.log`). Seven routing/token checks cover emergency priority, interrupted patch/setup selection, ambiguity refusal, clean-state preparation and stale/live/unknown result refusal; actual home checks confirm voice/checklist/tutorial controls are absent, technical logs remain collapsed and large buttons survive recreation. Original patch-update and two first-setup consent gates still start unchecked; Cancel creates no requests. Read-only foreground verification survives activity recreation, independently verifies the retained/installed normal APK and echoes the exact request UUID; actual service retirement is confirmed before continuation. App-only view render `artifacts/android-automatic-ui-home.png` (window overlays excluded), identities/result receipt `artifacts/android-automatic-ui-final-receipt.json`. Initial read-only retry stopped because Shizuku was not running, with its flow token retained (`artifacts/android-automatic-ui-probes.log`); user restarted Shizuku before the passing final run. Only development/test APKs installed. No automatic live patch, uninstall or game data writes exercised; complete automatic live cycle and actual permission-dialog/revocation behavior remain separate acceptance gates. |
| Guided UI and consent (earlier UI, superseded by automatic flow) | PASS: full-codec debug build (`artifacts/android-guided-ui-build.log`) and three actual Xiaomi UI probes (`artifacts/android-guided-ui-probes-final.log`). Home hides technical logs, offers a large next action, visual phone/copy/English illustration, optional English speech, expandable checklist and recovery; step help navigates Back/Next. The real patch-update checkbox and separate first-setup data-loss/login checkboxes remain initially unchecked and gate positive buttons; cancelling creates no requests. Activity recreation preserves this behavior. Actual home/help screenshots were inspected (`artifacts/android-guided-ui-home.png`, `artifacts/android-guided-ui-help.png`); initial oversized help illustration was corrected with a fixed 80 dp height, and help scrolls for larger text. Only development/test APKs installed; no game mutation or live-patch acceptance. English voice output, TalkBack, large-font/OEM matrix and usability with low-literacy participants remain unmeasured. |
| New-platform harness and current-device control | PASS for harness/current 4 KiB device, not Android 15/16 KiB acceptance. `tools/research/check_android_platform.py` records specific model/API/ABI/page-size properties, validates fixed development APK package names, runs static native inspection, and matches actual installed development APK size/SHA to the inspected build before two codec/import/frame/font tests. Current control `artifacts/android-platform-harness-identity-xiaomi-control/report.json` passes on M2007J3SG / API 31 / arm64 / 4096-byte pages; no installation, game access or Shizuku change. Both codec checks pass and all packaged native alignments are inspected. The first control without installed identity binding is retained separately; final harness adds that required provenance check. User reports the Android 15 PixelOS phone is unavailable now; its actual properties, physical 16 KiB loading and newer worker acceptance remain open. |
| Authorization restored / independent normal verification | PASS, one read-only foreground/Activity recreation test in 14.741 s (`artifacts/android-worker-permission-restored-probes.log`). After the user re-enabled HOK ACE authorization, a fresh worker verifies full installed normal APK SHA `b0b08f...fc0a`, expected signer/version and cleared debug flag, without installation or game-data writes. Normal verification status remains visible after Activity recreation. This closes the denied-permission probe's temporary authorization change; no test emergency intent remains. |
| Actual denied Shizuku permission / foreground refusal | PASS, one test in 1.717 s (`artifacts/android-worker-permission-denial-probes.log`), prepared build `artifacts/android-worker-permission-denial-build.log`. User disabled only HOK ACE authorization while Shizuku stayed running. Probe directly checks denied API permission and dispatches only read-only normal-APK verification. Foreground result is error with `Authorize HOK ACE in Shizuku before starting`; no verified/completed result and raw base/backup emergency records remain byte-identical. Receipt `artifacts/android-worker-permission-denial-receipts.json`. No game writes or installer call. User has been asked to re-enable authorization; successful post-enable retry is not yet recorded. This is denial before binding, not revocation during patch/apply. |
| Connected foreground verification / own UserService loss | PASS, one actual test in 17.905 s (`artifacts/android-worker-service-loss-guidance-probes.log`), final build `artifacts/android-worker-service-loss-guidance-build.log`. Waits for the worker's connected verification progress, validates a unique UID-2000 process named `io.github.hokace.patcher:worker`, then stops only that process (PID 18576). The resulting `DeadObjectException` produces error status with a nonblank recovery instruction and preserves the seeded emergency request as verification-pending. A fresh worker connection independently verifies retained and installed normal SHA `b0b08f...fc0a`, actual signer/version/non-debug state, then resolves the same request. Case `6437a9bc-f8b4-40b9-a390-918ad182925f`; receipt `artifacts/android-worker-service-loss-guidance-receipt.json`; no test intent remains. No APK installation, game-data writes, Shizuku-server stop or permission changes. Earlier connected-stage test passed in 19.056 s but exposed a blank error; the worker now preserves exception type and a plain fallback explanation. |
| Foreground probe availability and initial interrupted setup | Initial test FAIL, 21.656 s (`artifacts/android-worker-service-loss-probes.log`): Shizuku was already stopped, no service process was killed, and the seeded read-only verification request remained pending. Probe now checks binder availability/authorization before seeding intent. After user restart, strictly owned read-only recovery PASS in 15.585 s (`artifacts/android-worker-service-loss-owned-recovery-probes.log`), independently verifying the unchanged normal APK before removing its resolved test intent. A subsequent pre-connection own-service kill passed in 38.904 s (`artifacts/android-worker-service-loss-ready-probes.log`) but produced a connection timeout, so it is not proof of connected service loss. These receipts are retained separately in `artifacts/android-worker-service-loss-receipts.json`. Connected-stage evidence is recorded above. |
| Fresh Shizuku fixture recovery after security-setting confirmation | PASS, one actual test in 11.235 s (`artifacts/android-fixture-installer-security-enabled-probes.log`). User confirmed MIUI USB debugging security option and Install via USB enabled. Fixed fixture uninstall, actual UserService death/reconnection, refusal of a truncated APK stream, fresh session installation and fixture binary round-trip all pass. Session `1977819978`; case `09c12d73-55e6-428b-832c-677aea1aa073`. Host independently streams the installed APK: exact original 12,365 bytes and SHA `1f77892b2142758937113d0522180e6434c27108d4f4f13bc262ecb36d12970d` (`artifacts/android-fixture-installer-security-enabled-receipts.json`). Fixture remains installed. Earlier rejected cycles remain failures; this passing run does not establish which setting or prompt timing caused them. No live game or translation packages targeted. Shizuku-server death, full worker recovery and first-official conversion remain separate gates. |
| Attended fixture retry and USB rescue | PARTIAL. Initial USB restoration succeeds in 4.222 s; installed 12,365-byte APK independently matches SHA `1f77892b2142758937113d0522180e6434c27108d4f4f13bc262ecb36d12970d` (`artifacts/android-fixture-installer-attended-restored.json`). Fresh Shizuku/service-loss retry still fails in 31.923 s, including finally restoration (`artifacts/android-fixture-installer-attended-probes.log`); the user explicitly reports accepting the prompt. A USB rescue request did not execute because automatic approval review timed out; its once-authorized retry succeeds in 3.977 s (`artifacts/android-fixture-installer-attended-fallback-retry.log`). Installed fixture is restored and independently matches the same SHA (`artifacts/android-fixture-installer-attended-fallback-restored.json`). No further uninstall cycle until MIUI's additional Shizuku permission setting is checked. The [official Shizuku manual](https://shizuku.rikka.app/guide/setup/#start-via-wireless-debugging-start-by-connecting-to-a-computer-the-permission-of-adb-is-limited) recommends the separate USB debugging security option on MIUI; this recommendation does not yet prove it resolves the measured installer rejection. Game was never targeted. |
| Diagnostic export with damaged recovery records | PASS; final build `artifacts/android-diagnostic-export-final-build.log`, eighteen combined private checks in 1.852 s (`artifacts/android-diagnostic-export-final-private-probes.log`). Export no longer loads journals or invokes AtomicFile recovery: base and backup are separate unvalidated records with exact Base64 bytes and exported SHA-256. Corrupt binary records remain byte-identical after export and still block journal loading. Links, oversized records and missing published journals are explicitly reported; valid unpublished initialization remains excluded. Tests exercise the 1 MiB record cap, 8 MiB total raw-byte cap, 256-entry cap, 256 KiB log tail and propagation of destination failure. UI uses this writer for the user-selected document. Actual SAF completion was not exercised by these private checks; no game/fixture mutation or recovery acceptance is claimed. |
| Emergency APK selection with damaged transaction records | PASS; build `artifacts/android-emergency-choice-build.log`, nine private checks in 0.150 s (`artifacts/android-emergency-choice-private-probes.log`). If patch/setup discovery throws, UI requires an explicit retained-APK selection. Normal metadata filters candidates; selection is not content verification. The selected file still passes `RecoveryStore.verify` before installer confirmation and the existing provider gate. Damaged published journals are untouched; no completion/launch permission is granted. Pending emergency intent takes precedence; damaged emergency intent cannot be replaced by fallback. Private probes reject dummy APK bytes, access/linked candidates and empty fallback. No installer opened or game/fixture mutated; actual external-installer acceptance remains open. |
| Fixture update retains data | PASS, one actual Shizuku replacement test in 3.124 s (`artifacts/android-fixture-replacement-ready-probes.log`). No uninstall; the fixed fixture target retains its marker, which is then cleaned. Installed APK read-back exactly matches the original 12,365-byte SHA `1f77892b2142758937113d0522180e6434c27108d4f4f13bc262ecb36d12970d`; receipt `artifacts/android-fixture-replacement-receipts.json`, session `381535829`. This verifies replacement of an existing fixture, not fresh installation or live-game recovery. |
| Fresh fixture installer prompt follow-up | PARTIAL. Subsequent fresh-install/service-loss cycles still report `INSTALL_FAILED_USER_RESTRICTED`, including their finally restoration (`artifacts/android-fixture-installer-unlocked-probes.log`, 31.922 s; `artifacts/android-fixture-installer-prompt-accepted-probes.log`, 31.792 s). The user confirmed missing/rejecting an earlier prompt; immediate USB restoration then succeeded in 4.203 s and installed bytes independently matched the original (`artifacts/android-fixture-installer-prompt-usb-restored.json`). The later filename containing `prompt-accepted` does not prove prompt acceptance. Later USB restoration attempts, including `artifacts/android-fixture-installer-missed-prompt-restore.log`, were rejected again. At this observation the fixture remains absent and restoration is awaiting an attended prompt. No further uninstall cycle is permitted before exact restoration; the live game was not targeted. |
| Desktop control | Git `982130dce99db7f77c0c087830b2b20f23d2033e`; Python 3.12.13; fresh data 1.4.0.2, snapshot `dist/HOK ACE Patcher Data/pristine/20261003-173730`; all 653 source files rehashed against the snapshot |
| Matching normal APK | SHA-256 `b0b08f4a77244d990ea22e4fbde73542028b4b5785d88243b62ac907fbe3fc0a`; stable game certificate verified, debug flag false; recovery file retained |
| DLL-free desktop build, no cycle assets | PASS; 391 staged text tables, 395 applied textures, one skipped prime table, no skipped textures; six numeric package directories match the unique reported IDs |
| Talent control | PASS; 313710 raw bytes, chunk size 307200, two chunks keyed `15A33357ECBFA5CC` and `29157589AC92F155`; raw SHA-256 `7ffab50754b00a1a4f78fcc8b7b97a473781db8e67dbffc88989b98883454b2c` |
| Windows graphics oracle | PASS, catalog-only 86.9 s; same pristine `--game` run 104.4 s, 321 ported + 1 replaced + 1 spliced, zero skipped; the 75 absent entries here refer only to downloaded data |
| Android build | PASS; Gradle 8.9 / AGP 8.7.3 / Kotlin 2.0.0 / Chaquopy 17.0.0 / Shizuku API 13.1.5, ARM64, minSdk 30, compile/targetSdk 35 |
| Installed Shizuku | 13.6.0.r1086.2650830c; started as shell; binder authorization and AIDL binding measured |
| Device boundary instrumentation | PASS for shell UID/context, game APK path/size, fixture binary round-trip and ordinary app denial; descriptor-streamed installed APK matches the control SHA-256; fixed force-stop leaves no game PID. Live-game access/restore sessions passed after the measured timeout fix |
| Fixture installer session | PASS; 7333-byte fixture replayed through create/write/commit, installed hash `e6cd8618fc78842a737d762725e1c34ef8ab993c18ef0ac58b5b77fa13002221`. Explicit session abandonment rejects subsequent commit, preserves installed APK hash/path and binary round-trip. Combined codec/install/abandon/binder probes pass in 8.761 s |
| UserService death | PASS; death callback clears the connected service and the retained binder rejects a new diagnostic call. Isolated 2.467 s and combined probes pass; this stops only the app's own service, not the Shizuku server |
| Android engine imports/core operations | PASS; Python 3.12.12 / `aarch64`, bytecode magic `cb0d0d0a`, 499 catalog tables / 398 texture edits; Android LZ4 wins resolution; real LZ4 and Zstd round-trips pass; Oodle, ASTC and texture decoder imports load |
| Published Maven source/notice follow-up | PASS for artifact inventory, not release clearance. After user continuation on 2026-10-05, all seven matching POM/source-JAR sets download from Google Maven or Maven Central (`artifacts/android-maven-sources/manifest.json`). Auditor rechecks selected binary hashes, published source size/SHA/CRC, equality with six cached POMs, and the seventh JetBrains annotations 13.0 POM declaring Apache-2.0 (`artifacts/android-maven-published-source-inventory.json`). No metadata gaps remain in these seven candidates; modified source is refused (`artifacts/android-maven-source-refusal.json`). Original source-header notices are retained; source identity is distinct from reproducible binary/source equivalence. Expanded companion includes six native sources, seven Maven source JARs and POMs, recipes/notices/provenance, CRC and exact read-back (`artifacts/android-codec-maven-source-companion.zip`). Final debug build and engine extraction/full-codec import PASS, one test in 2.150 s (`artifacts/android-maven-notices-engine-probes.log`). APK audit finds twelve Python distributions, thirty notice/provenance files and eighty-four unchanged native payloads (`artifacts/android-maven-notices-apk-inventory.json`). Broader embedded-runtime/native source inventory, manual notice completeness, application/runtime/catalog distribution and combined redistribution review remain open |
| Resolved Maven runtime inventory | PARTIAL; Gradle task PASS (`artifacts/android-maven-runtime-inventory.log`), seven release-runtime candidates recorded with size/SHA. Offline audit revalidates all seven actual cached binaries (`artifacts/android-maven-runtime-notice-inventory.json`): four Shizuku 13.1.5 POMs declare MIT; AndroidX annotation 1.3.0 and Kotlin stdlib 2.0.0 declare Apache-2.0. JetBrains annotations 13.0 has no cached POM and remains unresolved. None of the seven artifacts or AAR classes JARs embeds a license/notice. Exact source provenance and notice completeness remain open; annotation classes may not be packaged, and Chaquopy plugin-injected/runtime native components are separate. Attempted matching source-JAR/POM downloads were not executed because automatic approval review failed on an out-of-credits workspace; the failure is not a safety rejection, and no alternate route was used |
| Packaged notice/source inventory | PARTIAL; final debug build PASS; actual APK audit inventories twelve Python distributions, twenty-nine notice/provenance files and eighty-four native payloads (`artifacts/android-dependency-notices-final-inventory.json`). Native payload hashes are unchanged; final SDK ZIP alignment check passes (`artifacts/android-dependency-notices-zipalign.log`), without implying physical 16 KiB acceptance. Verified engine assets now retain unmodified Python 3.12.12, Chaquopy 17.0.0, Shizuku MIT, Apache/GPL and NDK toolchain notices plus original leading copyright/license comments from the three hash-pinned codec archives. Provenance and explicit scope are recorded in `android/native/licenses/sources.json`; Shizuku text matches the published POM repository URL at an immutable commit, not yet a version-specific source proof. Full-codec extraction/import check PASS, one test in 1.764 s (`artifacts/android-dependency-notices-engine-probes.log`). Six-source companion regenerated with notices, collector/auditor recipes, original archive hashes, provenance hashes, CRC and read-back verified (`artifacts/android-six-component-notice-sources.zip`). Maven/runtime native dependency inventory, manual notice completeness and application/runtime/catalog distribution review remain open; no release clearance is claimed |
| Android native builds | PASS for original pinned Ooz, ASTC scalar/NEON and texture decoder sources, NDK 28.2.13676358, Android API 24, CPython 3.12.12 headers; experimental wheels and SHA-256 report under ignored `android/wheels/` |
| Private scratch copy | PASS; 656 files verified individually for byte length and SHA-256, 174.855 s; session `files/scratch/control-1402-verified/`; game/APK copied only after explicit user authorization |
| Full Android scratch engine | PASS for `EngineScratchTest#testBuildBothLayers`, 121.209 s; each pristine input and APK rechecked against the desktop control, `builder_dir=None`, empty `cycle_assets`, numeric directories reconciled, append read-back preserved; scan counts and four counters exactly match desktop (391 tables / 395 applied textures / 1 skipped table / 0 skipped textures) |
| Staged file comparison | PASS numerical checks; all 12 outputs fetched and SHA-256 verified. Seven files byte-identical, including both package `1` files and all indices. All entries compared in the five differing shards: 59374 readable assets byte-identical, 192 differing catalog ASTC textures, zero unexpected raw differences; 1396 unreadable in both controls remain unverified. Maximum per-image decoded RGBA mean difference 0.0094021/255, maximum individual channel difference 46; no image exceeds the recorded 2.0 tolerance. This does not replace watched rendering |
| Android graphics oracle | PASS after correcting invalid synthetic ASTC input; isolated instrumentation 121.807 s, checker 120.9 s, 321 ported + 1 replaced + 1 spliced, zero skipped downloaded textures. Original and isolated uncorrected runs SIGSEGV in texture2ddecoder's endpoint reader; valid fixture also passes Windows in 130.4 s |
| Windows binaries excluded | PASS; generated runtime omits two Windows LZ4 `.pyd` files; APK inspection finds zero Windows runtime or research payloads. Updated codec/boundary instrumentation passes (4.181 s); source runtime unchanged |
| Prepared live-game diagnostic | COMPILED; user separately approved this cycle. Opt-in `probeGameCycle` verifies APK hashes, package, signer/debug flags, matching versions, installed normal APK hash and storage. Fixed `--pkg` sessions, game-UID temporary probe, unconditional normal reinstall in `finally`, restored hash/signer/debug checks. This diagnostic exposes no translation write/uninstall operation. Binder/process-loss recovery depends on the verified PC normal APK |
| First live-game diagnostic | PARTIAL; 96.549 s. Game-UID probe passed with matching `1.info` and 4096 bytes, then normal restore hit the 30-second command deadline. Authorized USB `adb install -r installed.apk` succeeded; independent stream/hash probe passed (8.287 s), installed debug flag cleared. Installer writes/commits now have bounded 180-second deadlines with progress logs |
| Live-game diagnostic retry | PASS; 132.245 s. Access APK installed, matching `1.info` read, 4096 bytes round-tripped/removed, normal APK restored and streamed/read-back SHA-256 `b0b08f…fc0a` verified; stable signer and cleared debug flag verified independently. Normal session `1479424385` committed. Game PID 3163 remains alive beyond 90 s and main lobby renders; screenshot `artifacts/android-game-cycle-startup.png`. The existing translation was retained; Android staged output was not applied |
| Stable-key Java RSA/v2 signer | PASS; tiny fixture output is byte-identical to the pre-change Windows control (1.997 s), independently verified by SDK apksigner. Re-signing the 2026631918-byte normal APK on Android takes 42.919 s and reproduces SHA-256 `b0b08f…fc0a` exactly. Android archive parser verifies the stable certificate. This exact APK was already installed and launched in the authorized access/restore control. Full private preparation is accepted below; installation of the newly generated access APK remains open |
| Full APK preparation and reload | PASS, one private test in 146.058 s: actual preparer streams the full approved source, preserves existing normal SHA-256 `b0b08f…fc0a`, generates the stable-key access APK, adopts/verifies protected recovery and reloads its durable receipt. All 1625 decoded ZIP entries match a fresh Windows access control; only `AndroidManifest.xml` differs from the normal APK. Android access SHA-256 `593ec269b36bee255bbbd99870e2b070ffd7a5599651be90faca502fec83547b` is independently SDK v2-verified for Android 11+. The archive bytes differ from Windows; decoded payloads match exactly. No Shizuku binding or installation; this tests an already-converted source, not first-official-install conversion |
| Durable recovery primitives | PASS; Android AtomicFile interruption test preserves unresolved mutation/dirty state and rejects completion. Fixed path tests reject traversal, mismatched package IDs and metadata writes. Private snapshot extraction rejects links/unknown paths and detects changed retained originals. Combined instrumentation: three tests, 1.753 s. No game operations in these tests |
| Recovery cache identity | PASS; full normal APK retained under its SHA-256, metadata/content/manifest/signer revalidated, repeat adoption remains identical, access APK adoption refused. On-device private-storage test 99.774 s; no game installation or data operations |
| Installed recovery pipe verification | PASS; 18.743 s combined shell/fixture check. Coordinator independently hashes the installed APK through a bounded descriptor pipe, then checks installed version, certificate and debug flag. Matches exact normal recovery SHA-256 without another 2 GB disk allocation; no reinstall/game data writes |
| Worker binding lifetime and ownership | PASS; debug build and four real binding/foreground checks in 19.973 s (`artifacts/android-worker-binding-probes.log`). Each foreground connection uses a fresh UUID service tag rather than sharing `hokace-worker`; pinned Shizuku API 13.1.5 bytecode confirms the tag participates in both add/remove requests (`artifacts/android-shizuku-service-args-bytecode.log`). Two simultaneously bound worker owners are tested: closing the first twice cannot kill the second; intentional close never emits recovery loss and later await refuses immediately. Actual own-UserService destruction emits one loss notification, later await refuses immediately, and late callbacks cannot resurrect a closed/failed connection. Binder death is monitored independently of whole-server death; loss wakes connection waiters. Read-only installed-normal/Activity recreation and missing-consent foreground refusal still pass. No game install/data operation. This removes a service-ownership reuse risk; it does not prove the earlier intermittent timeout had this cause or establish full server/process/reboot recovery |
| Foreground activity recreation | PASS for read-only verification: WorkerProbeTest completes exact installed-normal verification while MainActivity is recreated; result persists as `verified`. This does not prove process-death, timeout or interrupted live-write recovery. Combined run has one URI consumer failure and one worker pass, 143.062 s |
| Preparation/recovery UI and saved progress | PARTIAL; preparation now runs in the foreground worker; UI polls AtomicFile progress/results after recreation and offers unfinished-session recovery by date. Cancellation checkpoints and unfinished-recovery refusal run before device reads. Two UI/result checks pass in 20.679 s, including exact installed-normal read-only verification and visible recreated-screen result. Two preparation guard tests pass in 0.025 s. Full foreground preparation, cancellation during signing, recovery chooser execution and process/timeout acceptance remain unproved |
| Update checkpoint and patch request | Final combined run PASS, three tests in 30.821 s; missing confirmation, replay, expiry and changed receipts refused. Earlier dialog/source-guard retry also passes, two tests in 14.427 s: Start is disabled synchronously until the update-finished/game-closed checkbox is checked; Cancel creates no request. Wrong-version or official sources are refused before access. Worker patch input is a one-use request UUID bound to verified preparation identities, not arbitrary APK paths. Live patch invocation remains unaccepted |
| First-setup journal and controller | Final private simulation PASS, three tests in 0.209 s (`artifacts/android-first-setup-controller-final-probes.log`), including stricter stored identity/phase validation; earlier controller run 0.206 s and journal-only one-test run 0.078 s also pass. Separate AtomicFile states retain irreversible data-loss consent, uninstall/install intent, verified normal installation and fresh-update wait. Pending setup blocks preparation and translation. Controller uses the translation coordinator lock, verifies cached recovery/source before removal, and independently verifies normal installation before reporting update wait. Lost uninstall/install replies recover without repeating removal; a different installed app is refused. No translation/counts are reported. Tests use dummy identities and a fake installer: no Shizuku binding, uninstall, install or game-data mutation. Fixed production transport now compiles and is verified separately below; consent request/UI is now connected and checked below; first-official conversion acceptance remains unfinished |
| Fixed first-setup transport and guards | Final build PASS; six combined tests PASS in 26.764 s (`artifacts/android-first-setup-no-replace-probes.log`), earlier expanded run 30.426 s. Actual Shizuku checks discover retained game records, parse user profiles and hash the installed full APK; stale source hash, invalid removal identity and first-install over an existing game are refused. Shared independent installed verifier still matches normal SHA-256 `b0b08f...fc0a`, signer/version and cleared debug flag. Removal accepts only a source SHA for the fixed game, rejects another profile carrying the game, and intentionally omits data retention; this valid removal path has not been invoked. First installation uses explicit `-R` and fixed `--pkg`, with cache content verified by the device adapter. Disposable fixture verifies `-R` refusal and unchanged installed hash `1f77892b...12970d`. AIDL protocol bumped to 7; old UserService instances are replaced on binding. No live game mutation; first-official conversion and consent/worker wiring remain unaccepted |
| First-setup consent/UI/foreground wiring | Final combined PASS, nine tests in 36.427 s (`artifacts/android-first-setup-consent-final-probes.log`); earlier nine-test run 30.913 s and six-test UI/request run 17.153 s also pass. Both data-loss and Scan-to-login controls start unchecked; either alone leaves setup disabled, Cancel creates no request. Fresh-update confirmation also starts unchecked and does not start translation. One-use requests bind source/normal/access SHA and the receipt, expire after 15 minutes, reject changed receipts/replay, and cannot begin two mutation attempts. Consumed consent UUID is saved in the setup journal. Request test revalidates the actual private normal/access APKs but uses synthetic unconverted source metadata: no first-official PKI proof. Real foreground dispatch of a nonexistent consent UUID rejects before creating a setup journal; read-only foreground normal verification still passes after activity recreation. Private simulations cover cancellation before removal and refusal with the unchanged original app; terminal lifecycle callbacks do not rewrite completed journals. Setup/recovery/update actions, pending-setup recovery APK selection and journal export are connected. No valid live setup request or translation was started; actual conversion and full lifecycle/installer recovery acceptance remain open |
| Automatic first-setup restore priority | Final combined PASS, twelve tests in 35.995 s (`artifacts/android-first-setup-auto-restore-final-probes.log`); isolated private recovery/journal PASS, eight tests in 0.738 s. Lost uninstall reply triggers normal installation; lost commit reply verifies the already-installed normal APK without another install. A first installer rejection gets one recovery attempt; repeated rejection stops after two attempts total, retains INSTALL_INTENT/normal-unverified state, and later explicit recovery succeeds. Uninstall count remains one. Changed installed app and newly invalid recovery cache refuse further mutations. Cancellation after removal and failed progress callbacks still reach independently verified normal installation. An unchanged original after refused removal terminates safely without claiming local data recovery. Automatic success reports setup_waiting, no translation/counts, and a plain recovery message. Foreground missing-consent refusal, consent/replay checks, UI cancellation and actual read-only installed-normal/Activity recreation checks still pass; exact normal SHA `b0b08f...fc0a`, signer and cleared debug flag verified. Recovery simulations use a fake installer/dummy source identities; no valid live setup request or translation was started. Initial malformed selector executed no tests and is retained in `android-first-setup-auto-restore-probes.log` |
| First-setup journal publication | PASS; debug build and thirteen combined private recovery/status/foreground checks in 17.354 s (`artifacts/android-first-setup-publication-probes.log`). Initialization writes and syncs a reserved `.creating-<UUID>` directory before publishing and syncing the final UUID directory. Unpublished interrupted initialization is excluded from pending/history and cannot be loaded to authorize mutation; missing published journals still refuse recovery. The returned journal reloads the published path before any uninstall intent. Export uses the same history filter. Tests simulate initialization states in private storage; physical process-death acceptance remains open. Actual read-only normal-game verification after Activity recreation still passes; no live setup or translation started |
| Real fixture installer / service-loss recovery | PARTIAL, one real fixture test fails in 31.815 s (`artifacts/android-fixture-installer-probes.log`). Debug-only service fixes both APK/data targets to `io.github.hokace.fixture`; release APK excludes both fixture service classes (`artifacts/android-fixture-installer-release-boundary.json`). Exact original fixture APK is cached before removal, SHA `1f77892b2142758937113d0522180e6434c27108d4f4f13bc262ecb36d12970d`. Fixture uninstall and actual UserService death/reconnection occur; truncated install is refused. Normal and finally restoration fail, and USB fallback independently reports `INSTALL_FAILED_USER_RESTRICTED: Install canceled by user`. Exact original exported under `artifacts/android-fixture-installer-recovery/e640bb06-4266-4f12-894d-f694a19ca69c/`; After the user enabled installation, USB restoration succeeded (`artifacts/android-fixture-installer-ready-restore.log`); installed fixture SHA-256 independently matches the original exactly. Retry after user readiness still fails with the same Shizuku `INSTALL_FAILED_USER_RESTRICTED` in 32.132 s (`artifacts/android-fixture-installer-ready-probes.log`); USB fallback again succeeds (`artifacts/android-fixture-installer-ready-retry-restore.log`) and independent installed read-back matches SHA `1f77892b...12970d`. Both failed cycles remain partial evidence. Live game is never targeted. Installer failure reporting now retains bounded stdout as well as stderr; failed fixture restoration cannot skip service cleanup. Final debug/release builds PASS; read-only fixture target, fixed-package whitelist, private recovery/journal and actual normal-game foreground verification PASS, twelve tests in 16.505 s (`artifacts/android-fixture-installer-fixed-target-probes.log`). Exact game normal SHA `b0b08f...fc0a`, signer and non-debug state remain verified. This is not full installer-recovery or first-official conversion acceptance |
| Installer failure guidance | PASS, twelve combined status/private-recovery/foreground checks in 17.024 s (`artifacts/android-installer-failure-guidance-probes.log`). Saved worker results explain user-restricted installation, insufficient space, signer conflict and unexpected existing package with the correct setup or patch recovery action; raw errors remain unchanged for export. The last installer code selects instructions when automatic recovery failed differently from the original action. Unknown failures retain their original explanation. Actual read-only normal-game verification after Activity recreation still passes; no fixture install retry, live setup or translation was run. The later user-enabled USB fixture restoration succeeded with an independently matching original APK hash |
| Interrupted file transaction | PASS private fake-device fixture, 0.191 s: fail after index commit/before acknowledgment, retain dirty intent across journal reload, fail again during complete-set rollback, then retry restores original index/shard and Watchdog. Unverified normal APK still blocks completion. Byte rollback has no Python/native codec dependency. Real file adapter acceptance is recorded below |
| Actual fixture file adapter and orphan lock | PASS, 7.329 s: production snapshot/validation/atomic writer runs against the fixed disposable fixture through a debug-only subclass. Full tar/hash validation, wrong-hash refusal, dangling temporary symlink refusal, hidden Watchdog cleanup and complete restoration pass. A second writer remains blocked after the lock-owning shell is killed while its child lives, then proceeds after that child is killed. This tests kernel/command lifetime, not complete live coordinator or Shizuku-server-death recovery |
| Directory durability | PASS; Android journal/cache/preparation paths sync directory entries alongside file contents, snapshot extraction syncs directories after the manifest rename, signer syncs its fresh output and parent. Four private Android recovery tests pass in 2.146 s; fresh signing fixture remains byte-identical to desktop in 0.717 s. No game operations |
| Resource observations | PASS measured fresh offline build: 149.109 s including verification/setup, engine 127.906 s; 149 samples at one-second intervals. Observed filesystem free-space decrease 1616109568 bytes; maximum sampled RSS and process-lifetime high-water RSS 1837764 KiB (about 1.75 GiB); maximum thermal status 0, battery temperature 33.5 C, zero unavailable readings. All twelve staged hashes match the first Android control. This is one workload/device observation, not a full-workflow peak guarantee or sustained thermal acceptance |
| Offline build storage estimate | Debug build and metadata-only Android control PASS, three checks in 19.074 s (`artifacts/android-build-storage-probes.log`). Before work/output creation, coordinator estimates all APK prime extraction, every downloaded package twice (output and staging attempt), and four replacement trees using source descriptor lengths plus catalog payload as growth allowance. It separately retains normal-install reserve and existing 5 percent / 256 MiB margin. Current control estimates 7,497,769,750 additional bytes; with normal APK and margin, 10,000,621,751 bytes required at build start. Desktop metadata control agrees (`artifacts/android-build-storage-desktop-control.json`); duplicate prime files, traversal and wrong package names refuse (`artifacts/android-build-storage-refusals.json`). This is a conservative estimate, not a measured hard upper bound on translation/native temporary growth. Production bridge rehashes a temporary private 2.7 GB snapshot copy and returns the same estimate; its storage and forced-refusal checks pass in a 47.648 s combined run (`artifacts/android-build-storage-copy-probes.log`), whose separate foreground verification fails on a Shizuku connection timeout. The isolated read-only foreground retry passes in 15.329 s (`artifacts/android-build-storage-worker-retry.log`) and verifies unchanged normal SHA/signer/debug state. Temporary copied snapshot is removed by guarded cleanup. An earlier attempt to avoid copying through hard links is refused by Android (`artifacts/android-build-storage-bridge-probes.log`); it is not a passing check. Actual interrupted low-space coordinator, intermittent binding reliability and peak acceptance remain open. The 8 GiB snapshot cap and pre-access reserves are unchanged |
| Recovery space and completion state | Private storage/transaction/journal probes pass: overflow/negative budgets refused, installer recovery reserve included, interrupted empty-stage Watchdog cleanup restores originals, and a verified payload retains its forward-completion marker across final-install interruption. Normal APK verification remains required. Coordinator avoids a redundant installer allocation when the installed normal APK already hashes correctly. Full low-space and installer-failure coordinator acceptance remains open |
| Recovery result counters | PASS three private journal/transaction tests, 0.278 s: four counters persist before apply and survive journal reload/final-install interruption. Completed recovery returns retained counters without importing Python/native codecs; cancelled rollback reports recovered status and omits planned counts. Unresolved recovery cannot produce terminal results. Worker compilation passes; full recovered worker acceptance remains separate |
| Coordinator recovery fault injection | PASS five private coordinator/journal tests, 90.484 s: post-commit write loss, repeated rollback interruption, final normal-install acknowledgment loss and corrupted-original refusal. Uses the real recovery coordinator and actual retained APK bytes with simulated installation, installed identity and game files. No Shizuku binding or live game operations. Failed rollback restores the verified normal APK separately while preserving unresolved data intent; worker reports recovery required and launch disallowed |
| Restart applied-layer audit | PASS across the six passing checks of a seven-test run (133.308 s) and corrected changed-layer retry (one test, 27.393 s). Retained applied manifest is reconstructed from verified inputs/output and durably saved. Forward recovery reopens access, checks current hashes and restores normal. Changed simulated live data is refused, preserved without rollback writes, and cannot produce completion or launch permission |
| Static native page alignment | Source-built dependency variant PASS: all 84 libraries have 16 KiB ELF load alignment; SDK 35 zipalign `-c -P 16 4` also passes. Original repository-wheel variant has six failures (LZ4 three, Zstandard two, FreeType one). Reports `android-aligned-native-inventory.json` and historical `android-native-alignment.json`. Physical 16 KiB loader acceptance remains unproved |
| Source-built dependency pipeline | PASS, two tests in 141.805 s with source-built LZ4 4.3.2, both Zstandard 0.22.0 bindings and FreeType 2.9.1. Core codec operations and full both-layer offline build retain 391 tables/395 applied textures/one skipped table/no skipped textures. Earlier compression-only variant passes two tests in 142.092 s and all twelve staged hashes match the retained Android control. No live game writes |
| Full coordinator orchestration | PASS, two private tests in 700.46 s: real `run()` streams a complete snapshot of 653 pristine files and four synthetic Watchdog files, builds both layers, applies all twelve staged files and restores simulated normal identity. A post-first-write acknowledgment loss exercises complete-set rollback, including empty Watchdog directories. Default 8 GiB snapshot cap and production storage reserves remain unchanged. All twelve stage hashes match the first Android control; all 653 source files remain unchanged. Installation, game transport and installed verifier are simulated; no Shizuku binding or live game operations |
| Coordinator/foreground foundation | Private full-run and recovery acceptance pass; existing converted-install path includes immutable recovery identity, complete streamed snapshot/hash validation, normal restore before build, fresh DLL-free staging, live input revalidation, per-file intent/read-back, Watchdog cleanup, complete-set rollback and final installed identity verification. Game file commands use a kernel flock so orphaned writers serialize with recovery. Non-exported dataSync foreground worker owns its Shizuku binding independently of Activity and records timeout/disconnection recovery state. Preparation, recovery and converted-install confirmation are connected to UI; their full live execution is not accepted. The coordinator has not executed a live patch or rollback; lifecycle acceptance, actual first-install execution and emergency recovery remain unfinished |
| Release gate | NOT PASSED; production UI/foreground lifecycle, actual-transport coordinator recovery and live Android-generated translation acceptance remain unfinished |

Local evidence is ignored: `artifacts/android-control/control.json` includes catalog/runtime and
staged hashes, source identities, the summary, runtime import inventory and Talent keys.
`artifacts/android-control-build.log`, `android-control-graphics.log`,
`android-control-graphics-catalog.log`, `android-full-build.log`, `android-native-build.log`,
`android-scratch-transfer.log`, `android-all-probes.log` and `android-scratch-probes.log` retain
commands' results, including the superseded failures. On-phone results remain in the private
verified scratch session: `build.log`, `graphics.log`, `metrics.json`, `staged-hashes.json` and
`out/device_patch_summary.json`. Do not delete this session before retrieving those results.
Collected comparison inputs are `artifacts/android-staged-hashes.json` and
`artifacts/android-device-patch-summary.json`; native evidence is `artifacts/android-native-crash.log`
and `artifacts/android-exit-info.log`. The USB-debugging authorization was restored by the user,
so result collection subsequently succeeded.
Corrected oracle evidence is `artifacts/android-oracle-valid-fixture.log`,
`artifacts/android-graphics-valid-fixture.log` and
`artifacts/android-control-graphics-valid-fixture.log`; its private session
`oracle-valid-fixture` links only to the already verified scratch game's copy.
Full comparison is `artifacts/android-comparison.json` / `android-comparison.log`;
fetched outputs remain in `artifacts/android-staged/`. Stream/fixture evidence is
`android-stream-fixture-probes.log` / `android-stream-fixture-device.log`.
The opt-in diagnostic build and ordinary codec/fixture checks are
`android-game-cycle-build.log` / `android-final-feasibility-probes.log`.
APK preflight identities are in `artifacts/android-game-cycle-inputs.json`;
normal/access ZIP record inventories differ only at `AndroidManifest.xml`.
First live-cycle evidence: `android-game-access-transfer.log` (69.942 s),
`android-game-cycle-probes.log`, `android-game-cycle-device.log`,
`android-game-cycle-usb-restore.log`, `android-game-cycle-restored-probes.log`.
The timeout fix compiles in `android-game-cycle-timeout-build.log`; retry evidence is
`android-game-cycle-retry-probes.log`. Private `game-access-1402` retains the verified access
APK and links to the original verified normal/game inputs.
Retry installer progress is `android-game-cycle-retry-device.log`; launch evidence is
`android-game-cycle-launch.log` / `android-game-cycle-startup.png`.
Signing evidence: `android-signing-desktop-verify.log`, `android-signing-probes.log`,
`android-large-signing-probes.log`. Recovery foundations: `android-journal-probes.log`,
`android-recovery-primitives-probes.log`, `android-recovery-store-probes.log`;
coordinator compilation: `android-recovery-store-build.log`.
Read-only pipe proof: `android-recovery-pipe-probes.log`; foreground compilation:
`android-worker-build.log`. Worker/service interruption behavior remains unaccepted.
Emergency URI provider, installer confirmation/log-export UI and shared four-counter/result
state code compile. URI consumer instrumentation encountered MIUI background/KeyguardLocked
activity denials, then a test-only anonymous ResultReceiver class-loader crash. The callback is
now parcelled into the framework ResultReceiver type. The unlocked-screen retry passes in
54.021 s: the fixture reads all 2026631918 bytes through the granted URI with the expected
normal-APK SHA-256; writable descriptors are refused and the read grant is revoked afterwards.
Evidence is `artifacts/android-recovery-uri-unlocked-probes.log`. Emergency installer completion
remains unverified. The earlier combined run's independent read-only WorkerProbeTest passes
Activity recreation; its URI failure is superseded by this isolated consumer pass.

Emergency restoration now persists an AtomicFile intent, syncs its file and parent directory
before launching the public installer, and retains the normal APK SHA plus a unique attempt ID.
Retrying the same pending APK reuses its request; switching APKs while pending is refused.
The installed-normal foreground action binds verification to that request. Only a successful
full installed APK/hash/manifest/signer check resolves it, with a second request-ID check before
committing success. Failure, cancellation or process interruption leaves verification pending.
The UI displays the saved warning after recreation and log export includes the record. This
separate APK record never resolves dirty package intents, advances setup, or reports translation.
Opening the installer takes the shared coordinator lock while publishing its intent, refusing an
active patch/recovery. A pending request blocks new patch and first-setup mutation before device
use; existing recovery remains available. Final build PASS (`artifacts/android-emergency-restore-lock-build.log`).
Twelve private intent/guard/first-setup recovery tests PASS in 0.681 s
(`artifacts/android-emergency-restore-guard-private-probes.log`), including refusal before any
device call and installer-intent refusal while the coordinator lock is held. Earlier three
private checks PASS in 0.108 s (`artifacts/android-emergency-restore-private-final-probes.log`).
Initial combined run is partial: three private passes and two foreground failures in 122.941 s
(`artifacts/android-emergency-restore-probes.log`): Shizuku stopped and Activity cannot resume.
After user readiness, the new emergency foreground request test PASS, including actual installed
normal APK verification and Activity recreation; the separate baseline Activity test then fails
to reach RESUMED. The ready combined run is one pass/one failure in 64.057 s
(`artifacts/android-emergency-restore-ready-worker-probes.log`). This verifies a seeded private
request against the already-installed normal APK, not an actual public installer return.
Actual public installer-return and physical process-death acceptance remain open. No game
installation or data write was run.

The separate fixed-fixture physical app-death cycle now PASS in 15.016 s
(`artifacts/android-process-death-fixture-final-retry-cycle/report.json`); its fresh recovery
instrumentation passes one test in 5.584 s. The harness observes app PID 25025 alive after a
durably saved write intent and a real fixture index rename, force-stops only the feasibility
app, observes its process absent, then starts a new instrumentation process. Before rollback,
the real Shizuku adapter verifies the mixed layer: changed index, original shard and other
files. The new process reloads the journal with dirty packages and unresolved write intent,
then production `GameFileTransaction.rollback` restores and verifies all five original files
and the empty `Watchdog/src` directory. Final journal remains RESTORING/normal-unverified:
completion without independently verified normal APK is refused. No APK installation is
performed. Fixture APK stays exactly SHA `1f77892b2142758937113d0522180e6434c27108d4f4f13bc262ecb36d12970d`;
owned fixture files and marker are removed, with host-side cleanup verification. The test uses
a synthetic journal phase sequence, small disposable files and the real fixed-fixture file
adapter; it does not prove the full foreground coordinator, live-game or APK restore cycle.
The host refuses active patch/recovery services, unfinished published patch/setup journals
and pending emergency APK verification before starting instrumentation.

Earlier fresh fixture cycle PASS in 14.141 s
(`artifacts/android-process-death-fixture-fixed-cycle/report.json`). The first killed-app case
failed its recovery ownership assertion because test setup redirected the marker before
creating `files`; the five retained mixed files were independently matched against their
manifest before repairing that one marker. Recovery of the same case then PASS in 8.750 s,
one instrumentation test in 6.167 s (`artifacts/android-process-death-fixture-recovery/`).
The original failure remains under `artifacts/android-process-death-fixture-cycle/`.
Adding idle preflight initially refused before mutation due an exec-out quoting error
(`artifacts/android-process-death-fixture-final-cycle/report.json`); corrected argument
quoting is used by the final passing run. Build logs are
`android-process-death-fixture-fixed-build.log` and `android-process-death-fixture-final-build.log`.
Later discovery-only build PASS (`android-process-death-fixture-discovery-build.log`);
default instrumentation skips the two-phase test without explicit host arguments. The host
also refuses inconsistent terminal patch journals and a pending AtomicFile backup of the
emergency restore record. These guards do not broaden the physical fixture result.
Shizuku server death/revocation, screen-off, reboot, low space, installer restoration and
full-coordinator physical interruption remain separate acceptance gates.

Patch-session initial publication is now atomic too: `SessionJournal.create` writes and syncs
a reserved `.creating-<UUID>` directory, renames it to the final UUID, syncs the parent and
reloads the published journal before returning it to the coordinator. Unpublished empty,
partial or fully written drafts never authorize mutation and are excluded from pending/history.
Preparation, both consent stores, patch/first-setup coordinators, recovery selection, recovery
APK selection and diagnostic export share the same discovery helpers. A missing/damaged
published journal is refused rather than hidden. Loading also bounds file size before reading,
refuses linked published paths (including dangling directory links), validates required recovery,
engine and mutation state, and refuses terminal journals with unresolved recovery.

Final private publication/journal/transaction/setup/emergency checks PASS, 22 tests in 2.058 s
(`artifacts/android-session-publication-final-private-probes.log`); earlier 21 tests pass in
0.743 s before the dangling-link check. Tests verify draft refusal, corrupt published-session
refusal before device calls at every mutation entry point, malformed/missing stored fields,
false completion, oversized journals, and linked directories. Final build PASS
(`artifacts/android-session-publication-final-build.log`).
The physical fixture app-death/rollback cycle with this production journal version PASS in
15.282 s, recovery instrumentation one test in 6.007 s
(`artifacts/android-session-publication-process-death-cycle/report.json`).
It confirms new-process load of the published unresolved intent and exact five-file/Watchdog
restoration; APK and game remain untouched. Initial-write interruption states are simulated
in private directories; physical interruption during the rename/publication itself and full
foreground coordinator interruption remain unaccepted.
After the first performance cleanup, phone `/data` had 5237244 KiB available and conservative
coordinator preflight refused another large snapshot. Subsequent verified scratch compaction
freed enough space for the full private coordinator acceptance below. Neither observation is
a measured production peak-space requirement.
Whole-set fault injection is `android-transaction-probes.log`; foreground/URI combined results
are `android-worker-uri-probes.log` and MIUI/callback errors are retained in
`android-worker-uri-device.log`. Latest framework callback correction compiles in
`android-recovery-callback-build.log`; its corrected consumer passes in the isolated unlocked run above.
Streamed manifest-only APK preparation and SHA/manifest/certificate cache receipts initially
compiled in `android-apk-preparation-build.log`. Full private generation/reload now passes;
the newly generated access APK has not been installed. Shared counters now come from
`tools/patch_summary.py`, re-exported by Windows;
the retained summary still reports 391 / 395 / 1 / 0. Codec configuration and storage refusal
run before access installation. Fixed first-official source/profile preflight, hash-guarded
removal and absent-only normal-install endpoints now compile with a dedicated device adapter.
They are now connected to a one-use consent request and explicit first-setup UI. No valid
game uninstall has been run. Installation recovery never repeats removal; an unchanged original
app can terminate a refused/interrupted removal after independent verification, without claiming
deleted data was recovered. Both local-data-loss and Scan-to-login acknowledgments start unchecked.
The foreground action consumes the bound request, and its UUID is retained in the setup journal.
After new game downloads finish, the separate setup checkpoint verifies the normal APK and
unblocks preparation; a fresh preparation then enters the usual converted-install patch flow.
Setup errors now make one automatic recovery attempt before returning from the worker.
The controller reloads durable intent and revalidates cached recovery, checks any installed app
before retrying installation, and never repeats removal. Persistent failure retains the journal
for explicit later recovery. Progress-display failure cannot prevent a normal-app restore.
This passes private simulations; actual first-official conversion and interruption/recovery
through the real installer remain unaccepted.
First installation explicitly supplies `-R`: omitting `-r` still defaults to replacement in
[Android 12's package-manager implementation](https://raw.githubusercontent.com/aosp-mirror/platform_frameworks_base/android12-release/services/core/java/com/android/server/pm/PackageManagerShellCommand.java).
The phone's own help confirms the option (`artifacts/android-package-manager-help.log`).
A disposable-fixture install with `-R` is rejected as `INSTALL_FAILED_ALREADY_EXISTS`, with
its installed APK hash unchanged (`artifacts/android-first-setup-no-replace-fixture.json`).
Custom-codec source companion `artifacts/android-custom-codec-sources.zip` contains three
SHA-pinned original archives, build recipe, existing notice inventory and canonical GPL text;
archive contents are read back. Other dependency/application notices and sources remain open.
Real file-adapter proof is `artifacts/android-file-fixture-probes.log`; the corresponding build
is `artifacts/android-file-fixture-build.log`. Production keeps its fixed game target; only
`src/debug/FixtureFileService.kt` substitutes the disposable fixture for file operations.
Initial actual-command measurement found `flock: Bad file descriptor`; explicitly passing FD 9
fixed acquisition, but a grouped shell body still released the lock when its parent died.
`GameFileLock` now execs the protected shell with FD 9 explicitly inherited. The orphan-child
test verifies both the blocked interval and subsequent writer completion. The writer also
rejects dangling temporary symlinks before opening them. Watchdog cleanup recreates the fixed
directory, clearing hidden files too, and syncs directory entries; restoration syncs created
directories and ancestors. Updated Shizuku binding/private transaction regression passes two
tests in 1.850 s (`artifacts/android-file-adapter-regression-probes.log`). No live game files
or APKs were changed by these fixture and read-only tests.
Resource observation is `artifacts/android-performance-probes.log` (instrumentation 149.176 s)
and `artifacts/android-performance-retained/`: metrics, control, summary, stage hashes, build log
and cleanup receipt. `RunMetrics` also observes future coordinator runs. RSS high-water values
cover the whole process lifetime; sampled disk deltas can include other applications and miss
subsecond peaks. No absolute production storage/RAM bound is claimed. The research cleanup
tool validates the performance UUID and canonical app-private targets, exports/read-backs all
evidence, requires stage hashes identical to the retained control, then removes only generated
work/out; approved source links, input data and protected recovery remain retained.
`StorageBudget` adds checked arithmetic, 5-percent-or-256-MiB margin, and simultaneous normal
installer/file-write reserves to preparation, snapshot/extraction, apply and rollback checks.
The snapshot cap remains conservative at 8 GiB; full build-work estimation is still unfinished.
Recovery pre-verifies an already-installed normal APK to avoid allocating another installer copy
after an offline build exhausts space. Journaled `patch_payload_verified` distinguishes full
forward recovery from rollback/cancellation after the final normal install is interrupted.
Empty stage manifests can still require Watchdog rollback. Private acceptance is
`artifacts/android-storage-probes.log` and `artifacts/android-recovery-completion-probes.log`;
the final combined storage/transaction/journal run passes four tests in 0.282 s. These proofs
do not substitute for fault injection through the full coordinator.
Recovery counter evidence is `artifacts/android-recovery-results-build.log` and
`artifacts/android-recovery-results-probes.log`. `PatchWorkerService` persists the journal's
terminal recovery result instead of overwriting every successful recovery with `verified`.
`verified` remains the read-only normal-APK check's outcome.

Coordinator recovery evidence is `artifacts/android-coordinator-recovery-build.log` and
`artifacts/android-coordinator-recovery-probes.log`. `CoordinatorRecoveryProbeTest` isolates
the coordinator's files directory, reads the approved normal/access APKs without duplicating
them, and streams installer inputs through a fake device. Its in-process installed verifier
is injected only by tests; application calls retain independent installed-APK pipe and manifest
verification. Recovery does not start Python. A separate durable `recovery_normal_intent`
allows emergency normal restoration without clearing a failed package-write intent. Damaged
originals are rejected before changing that intent, and a verified normal APK alone cannot
resolve inconsistent data or grant launch permission. This is recovery-path acceptance with
simulated transport. Full private `run()` orchestration is now accepted below; actual
transport and process/server loss remain unproved.

Full orchestration evidence is `artifacts/android-full-coordinator-build.log`,
`android-full-coordinator-probes.log` and `android-full-coordinator-retained/`.
`FullCoordinatorProbeTest` uses the actual coordinator, full approved APK descriptor streams,
complete snapshot extraction and both-layer engine. Its isolated context borrows pristine
inputs read-only; fake file writes allocate and verify full output bytes in private scratch.
The success journal is `0188ec38-1d92-4e6d-a268-6ae0fd6611f7`; the fault/rollback journal is
`ef14718f-58b7-460e-bc0a-1acd1dfab43a`. Success retains 391 / 395 / 1 / 0; cancelled rollback
omits planned counts. Terminal receipts are retained after removing only verified test outputs.
Observed run metrics are 302.866 s success and 302.193 s fault, with free-space decreases
7477182464 and 7477055488 bytes respectively. Maximum sampled RSS is 1664940 KiB;
process-lifetime high-water RSS is 1821524 KiB, thermal status 0 and battery temperature
37.7 C. These deltas include fake override copies and exclude actual installer allocation;
they cannot establish the production peak budget.

Full preparation evidence is `artifacts/android-apk-preparation-final-probes.log`,
`android-apk-preparation-final-export.log`, `android-apk-preparation-access-signature.log`
and `android-apk-preparation-retained/`. Passing fixture
`e35858b5-ffdf-4fe6-b308-2db85cde3658` retains preparation receipt
`5b6215d9-b501-49f8-b587-33a25c8afedf`. Its access hash is identical to the separately
exported SDK-verified artifact from fixture `1909e078-43a5-4b87-98f6-1982e9c0d30c`.
Both device and independent Windows decompression/hash inventories agree for all 1625 entries.
SDK verification uses `--min-sdk-version 30`: default verification also requires v1 signing
for the game's older declared minimum and fails with missing `META-INF/MANIFEST.MF`;
Android 11+ is the patcher's supported range and the generated APK uses v2 signing.
The passing run observes 133.626 s within metrics, an 8164605952-byte free-space decrease,
202944 KiB maximum sampled RSS, 226596 KiB process-lifetime high-water RSS, thermal status 0
and battery temperature 33.7 C. This includes four simultaneous APK-size allocations and
engine extraction; it remains one device/workload observation.

The initial preparation test failed in 220.478 s because the bridge unnecessarily rewrote an
already-normal stable-key APK, changing its identity to `6b82774e…15b5e32`. The bridge now
copies that APK unchanged only when the manifest already matches and its signer is the stable
key; other sources still follow manifest rewrite/signing. The access APK is derived from the
prepared normal file. A 351.776 s retry passed payload/receipt checks but failed a test cleanup
guard that compared Android's `/data/user/0` and `/data/data` aliases literally. Canonical
parent containment and explicit symlink refusal fix that guard; the final complete test passes.
Failed copies were individually rehashed and removed only after retaining receipts. The
accepted test removes its duplicate source after verification, retaining the access file and
protected recovery. No APK was installed into the live game, and no live game data changed.

Preparation/recovery UI evidence is `artifacts/android-preparation-recovery-ui-state-build.log`,
`android-preparation-recovery-ui-probes.log`, `android-preparation-guards-probes.log` and the
final recovery-label compilation `android-preparation-recovery-ui-label-build.log`.
Preparation uses the worker's independent binding and cancellation checkpoints before/after
large operations. An unfinished journal prevents preparation before reading the device.
Cancellation may wait for the current copy/signing operation to reach a checkpoint; interrupted
private preparation files remain retained. Atomic worker-state writes are serialized, and late
progress/success cannot replace timeout state after the worker retires. `WorkerStatus` labels a
retained running record as last saved progress rather than evidence of a live process; unresolved
recovery hides planned counts and asks the user to keep the game closed. Activity polling stops
while paused and resumes after recreation. A date-based chooser starts the existing recovery
worker for a selected unfinished session. That chooser and full foreground preparation are
compiled but not device-accepted. The converted-install patch checkpoint is now connected;
initial conversion is still unavailable.

Update-checkpoint evidence is `artifacts/android-patch-request-probe-build.log`,
`android-update-checkpoint-probes.log`, `android-update-checkpoint-source-build.log`
`android-update-checkpoint-final-probes.log` and `android-update-checkpoint-combined-probes.log`
(all three tests pass in 30.821 s). The initial UI check found a brief enabled
Start button before Android delivered the dialog's OnShow callback. Button disabling and
listeners now run synchronously after `show()`, before returning to the event loop; cancellation
is asserted after Android's queued dismissal. The final complete UI/source guard run passes.
`PatchRequestStore` retains an AtomicFile confirmation bound to preparation UUID, receipt SHA,
normal/access SHA and a checked update-finished/game-closed acknowledgment. It expires after
15 minutes and is durably consumed before coordinator entry. Repeat claims, changed receipts,
unfinished recovery and first-official conversion are refused. Claim reload rehashes actual
normal/access APKs and requires the current engine identity. The foreground worker accepts only
this request UUID for patch start; it no longer accepts caller-supplied normal IDs/access paths.

Converted-source preflight independently verifies the installed original APK before access,
while retaining the prepared normal APK for restoration. This preserves the optional manifest
rename when a converted source still has an older label. Source and recovery must share version
and the stable signer, and neither may be debuggable. Version/signer refusal is device-tested
with an unavailable Binder and missing access file; the label-changing positive path remains
unaccepted. Existing direct coordinator tests retain the default normal-source overload.
These tests only read protected/private APK copies or cancel UI confirmation. No live worker
patch was invoked, no game APK was replaced and no game data changed.

`tools/research/prepare_android_workflow_space.py` exported/read-back the first twelve Android
outputs and metadata to `artifacts/android-workflow-retained/`, rehashed all pristine/rerun
inputs, and removed only verified disposable work/output and duplicate scratch APKs.
The original scratch normal APK now links to the independently verified protected recovery
cache. Pristine game inputs, access APK and PC recovery material remain intact.
`tools/research/restore_android_control_stage.py` subsequently restored all twelve archived
outputs through the token-authenticated loopback receiver and independently rehashed every
file before publishing `control-1402-verified/out`. Evidence is
`artifacts/android-control-stage-restore-harness.log`. Earlier restore attempts found no
`exec-in` receiver acknowledgment, a raw shell-stdin copy truncated at its first 0x1a byte,
and a base64 transfer timeout; those failed attempts do not prove an OEM tar defect.

Review identified that an earlier durable payload-verification marker cannot prove the current
layer after restart or an external update. The applied manifest now uses AtomicFile plus file
and directory sync. Forward recovery reconstructs its expected hashes from verified originals
and staged files, reopens matching access, validates the current full layer, then restores normal.
A mismatch retains recovery-required state and does not overwrite externally changed files.
Evidence is `artifacts/android-forward-recovery-build.log`,
`artifacts/android-forward-recovery-probes.log`,
`artifacts/android-forward-recovery-retry-build.log` and
`artifacts/android-forward-recovery-retry-probes.log`. The seven-test run has six passes and
one test-adapter failure: its expected live-layer refusal was wrapped in RuntimeException
instead of preserving IllegalStateException. The adapter now preserves runtime exceptions;
the isolated changed-layer retry passes in 27.393 s, including unchanged-data/no-new-write,
normal-restored and launch-disallowed assertions. The other six passing checks establish final
acknowledgment-loss audit, corrupted-original refusal, repeated rollback and journal/transaction
regressions. No full coordinator build/apply or actual restart was exercised by these fixtures.

On 2026-10-04 pinned upstream source builds replaced the five misaligned LZ4/Zstandard
bindings and FreeType in the complete-codec configuration. Versions remain 4.3.2/0.22.0/2.9.1;
upstream source is unchanged. `build_compression_wheels.py` preserves both Zstandard bindings
and explicitly configures the upstream CFFI generator's Android preprocessor; its first attempt
failed on missing Unix compiler settings in the Windows host. `build_freetype_wheel.py` uses
SDK CMake 3.22.1/NDK 28.2.13676358, API 24, position-independent source archive plus explicit
16 KiB shared linking. Original and rebuilt FreeType have the same `libfreetype.so` SONAME
and libc/libdl/libm/libz dependencies. Its feature selection follows the Chaquopy recipe.

The default `-PfullCodecs` now requires these three local dependency wheels alongside the
three graphics wheels; an early comparison run selected them with `-PalignedCompression`.
The minimal diagnostic build remains a repository-wheel baseline. Full source-built evidence
is `artifacts/android-compression-build-retry.log`, `android-freetype-build.log`,
`android-aligned-native-build.log`, `android-aligned-native-inventory.json` and
`android-aligned-native-probes.log`. Both-layer build engine time is 118.852 s; the surrounding
two-test run is 141.805 s. Measured free-space decrease is 1627836416 bytes, sampled RSS max
1679904 KiB, process-lifetime high-water RSS 1869372 KiB, thermal status max 0 and battery
temperature max 34.5 C. These samples are one observation on the existing Android 12 device,
not an upper bound or a physical 16 KiB loader proof.

`artifacts/android-aligned-native-retained/` exports source/control/result hashes, metrics and
build logs. All twelve staged files match the first Android control byte-for-byte. Only the
successful session's generated work/out were pruned after verified export; inputs and normal
recovery remain. Final default-build evidence is `android-native-dependency-final-build.log`,
`android-native-dependency-final-inventory.json` and `android-native-dependency-final-probes.log`:
84/84 aligned libraries and two passing codec/font checks in 1.982 s. The additional probe
round-trips LZ4 frames, confirms the CPython Zstandard C backend, and renders a nonempty glyph
mask with Pillow/FreeType 2.9.1. Optional CFFI runtime and physical 16 KiB acceptance remain
separate; the pipeline uses the verified C backend. The six-component source companion
`artifacts/android-six-codec-sources.zip` passes original-archive hashes, CRC and full read-back.
Its scope is these components; complete application/runtime redistribution inventory remains open.

The user reports a second Xiaomi device running Android 15 with the AOSP-based PixelOS custom
ROM. It is available for later platform testing; its model, ABI and actual page size have not
been inspected. This adds a distinct ROM/platform path, not another hardware OEM. Android 15
does not establish 16 KiB loading. The source-built dependency APK now fixes all six static
alignment failures, but this device's actual loader/page-size acceptance remains open.
On 2026-10-05 the user reports that phone is unavailable now. The prepared platform/codec
harness is validated only on the existing 4 KiB Xiaomi; do not close newer-device or 16 KiB gates.
Durability verification is `android-durable-directories-probes.log` and
`android-signing-durable-probes.log`; fresh signer output is `signing-rsa-1/java-signed-durable.apk`.

On 2026-10-04 `RerunProbeTest.testAlreadyEnglishHasNoDuplicateAppendOrFileDrift`
passes on the phone in 142.47 s (`artifacts/android-rerun-copy-probes.log`). A fresh private
scratch input combines the pristine layer with the first Android build's twelve staged files.
Every rerun output matches its already-English input hash; all pristine and retained first-build
files are rehashed unchanged. Android denied hard links in the initial probe; ordinary copies
and an APK symbolic link succeed. This is offline idempotence evidence, not a live-game rerun.
The Windows frozen application was rebuilt with Python 3.12 and passed `--selftest` against
the pristine downloaded dump, with `selftest.json` reporting `ok: true`. Evidence is
`artifacts/android-port-windows-build.log`, `artifacts/android-port-windows-selftest.log` and
`artifacts/android-port-windows-selftest/selftest.json`. This self-test does not supply the APK;
the earlier both-layer control remains the coverage comparison.

Developer build/test commands and harness usage are in [`android/README.md`](../../android/README.md).
Native source hashes, build flags and redistribution inventory are in
[`android/native/THIRD_PARTY.md`](../../android/native/THIRD_PARTY.md).
The Windows APK signer now accepts an optional RSA callback; the default and callback outputs
are byte-identical to its pre-change control. Translation engine and catalog/runtime/key resources
were not edited. Coverage ledger counts did not move.

### Measured implementation corrections

- AAPT transparently decompresses a `.gz` asset and strips its suffix. Generated copies now use
  a `.payload` suffix, with unchanged bytes and original names restored only after verified extraction.
- AAPT's default directory filter omits Python `_backends` directories. The spike disables this
  filter so its verified resource manifest matches the actual packaged files.
- Archspec's filesystem-relative CPU JSON needs `extractPackages("archspec")`; without it the
  ASTC import fails before loading the NEON extension.
- Applying `-fms-extensions` globally collides with Ooz's `_rotl` helper under NDK Clang. That flag
  now follows the texture decoder's own build configuration only; upstream sources stay unchanged.
- The ordinary-app denial can occur before the `run-as` process starts. EACCES is an expected
  result, rather than a failed fixture test. The UserService round-trip itself passed.
- Both PAX and USTAR stdin transfers through this phone's Toybox tar truncated the scratch data.
  A passing transport exit was not evidence of a complete copy. A localhost-only instrumentation
  receiver now bounds the session/file counts and lengths, verifies SHA-256 per file, and acknowledges
  each successful write. It is absent from the main application; Internet permission is debug-only.
- The next device read was temporarily rejected because automatic approval review lacked credits.
  A retry after the user's “Continue” passed review but the phone reported `ADB unauthorized`.
  USB debugging must be authorized again to retrieve results; this is separate from Shizuku permission.
- The graphics oracle's synthetic ramp bytes were not valid ASTC blocks. A fresh process and
  line-buffered log isolated the native crash to check 5. Encoding a known background instead
  preserves the independent byte-range checks and passes both Windows and ARM64. Native decoder
  behavior on malformed input remains outside this proof.

### Immediate continuation

The deliberate permission-denial foreground probe and the post-enable independent normal-APK
verification now both pass. HOK ACE authorization is restored. Permission revocation during a
live patch remains a separate acceptance gate.

The application now includes the MIUI USB-debugging security option in user-restricted installer
guidance. Final debug/test build PASS (`artifacts/android-miui-security-guidance-build.log`);
two private worker-status checks PASS in 0.021 s (`artifacts/android-miui-security-guidance-probes.log`).
The installer code and raw recorded errors are unchanged by this guidance update.

1. The fresh Shizuku fixture/service-loss cycle now passes after user confirmation of both MIUI
   installation/security-debugging options. Exact installed fixture bytes are independently verified.
   Preserve the failed earlier cycles and continue the separate worker/server-loss acceptance;
   the tiny fixture does not prove large-game installation or first-official conversion.
2. Retain the verified normal game APK and USB fallback. Build-work estimation, private coordinator
   success/rollback, journal publication, foreground read-only verification, emergency selection
   and bounded diagnostic export are implemented and measured. Their narrow proofs do not accept
   a complete live patch or its interrupted installer recovery.
3. Complete the open acceptance gates below. Prepare a concrete live test and obtain its separate
   authorization before applying Android-generated translations or removing an official game.

### Remaining acceptance audit (2026-10-05)

| Requirement | Current evidence | Proof still required |
|---|---|---|
| Reliable OEM installation and restoration | Existing-fixture replacement and latest fresh Shizuku/service-loss cycle pass with exact installed read-back after both MIUI options were confirmed; earlier user-restricted failures retained | Reliability through the full large-APK worker/install/restore flow, including actual installer interruption; no broad OEM claim from the tiny fixture |
| Permission denial / stopped Shizuku | Deliberately denied foreground verification refuses before binding; post-enable actual normal verification passes. Connected foreground own-UserService loss, preserved intent and fresh retry pass; actual stopped-server failure and owned intent recovery recorded | Permission revocation and stopped-server recovery through the full supported patch workflow, without false completion |
| Complete mobile workflow | Full both-layer private coordinator success and rollback pass with simulated installation/transport | Actual Android-prepared access APK installation, full live snapshot/build/apply/normal restore, exact installed and pushed hashes; separate live-cycle authorization |
| Emergency public installer | URI consumption, durable intent and foreground independent verification pass separately; damaged-record selection/export private checks pass | Actual user-assisted public installer completion followed by saved-request verification; pending package rollback must remain pending |
| Lifecycle / interruption matrix | Actual app-process death at a fixed fixture file boundary and byte rollback pass; connected foreground read-only verification handles own-UserService death and fresh retry | Full patch worker process/server loss, revocation, screen-off, reboot, low-space and installer interruption across the real supported flow |
| First official conversion and updates | Consent, journal, restore-priority and transport simulations pass; current game is already converted | Separate data-loss authorization, actual differently signed official source, independently verified installation, full update and subsequent patch |
| Translation screens / repeat patch | Offline 391 tables / 395 applied textures and rerun parity; existing game UI predates Android output | Authorized watched `prime-rebuild.md` screens after Android output, prime-only checks, live rerun and repair acceptance |
| Native/device/resource acceptance | All 84 static native alignments pass; current 4 KiB Xiaomi offline codec/resource observations pass | Physical 16 KiB loading, Android 15 foreground behavior, actual device ABI/page size, another hardware OEM, complete-workflow peak/resource evidence |
| Distribution | Pinned component sources/notices and seven Maven source identities inventoried | Complete embedded-runtime/native inventory, manual notice/source completeness and application/runtime/catalog redistribution clearance |
| PC-free release gate | Development prototype and retained USB rescue; no live Android translation applied | A user completes installation, Shizuku startup, supported patch and verified non-debuggable game launch without PC/cable; usable interrupted-run recovery |

None of these remaining rows is closed by private tests or static alignment alone. Coverage counts
have not changed, so the translation coverage ledger remains unchanged.

**Verdict:** a fully on-phone patcher is technically plausible. Shizuku is a suitable candidate for replacing the Windows ADB transport and shell execution, provided the device probes below pass. It does not port the Python engine, provide root on an unrooted phone, or grant direct access to the release game's private data. Full parity also requires Android builds of the native codecs. Treat this as a gated port, not a confirmed working replacement.

The proposed first release targets **Android 11+ and arm64-v8a**, with Shizuku started through wireless debugging. End users should need neither a PC nor a USB cable. Developer options and wireless-debugging setup remain necessary; some OEMs also require their USB-debugging/security settings to be enabled. Shizuku must be started again after reboot. Android 10 and older are outside the PC-free first-release scope. These startup constraints are documented in the [Shizuku manual](https://shizuku.rikka.app/guide/setup/).

### What was inspected

- `app/patcher_core.py`: detection, APK caching/re-signing, first-run uninstall, temporary access APK, `run-as` snapshot, translation, package writes, Watchdog cleanup and normal-APK restore.
- `app/apk_tools.py`: streaming ZIP rewrite, 4-byte stored-entry alignment, certificate matching and APK v2 signing.
- `tools/build_device_patch.py`, `package_rebuild.py`, `device_extensions.py`, `qts_relocate.py`, `mobile_graphics.py`, `qts_builder.py`: engine entry points and native dependency boundaries.
- `requirements.txt` and `resources/runtime/`: Python 3.12 requirement; bundled LZ4 includes `_block.cp312-win_amd64.pyd` and `_version.cp312-win_amd64.pyd`.
- Existing feature records, repository `MEMORY.md` and `docs/translation-progress.md`: measured restrictions, both data layers, append behavior and Talent Card repair.

The normal pipeline is DLL-free because `REBUILD_PACKAGES = ()`. It still needs the APK for prime-only assets. Removing the APK input would lose parity even if downloaded text and textures worked. Do not bundle Tencent's Windows builder into the Android app or invent a replacement builder.

### Still owed

- Test permission denial, stopped Shizuku and OEM install prompts. Record exact failures and settings needed.
- Inventory reachable imports; resolve every required native dependency for ARM64/CPython 3.12, recording versions, NDK configuration and applicable redistribution notices/source requirements.
- Measure peak disk/RAM, thermal effects and elapsed time. Exercise 16 KB native loading separately.
- Accept the saved emergency installer request through an actual user-assisted restore and independent installed-APK verification; APK verification must leave pending package rollback intact.
- Refuse stale live layers, unsupported layouts, split APKs and nonempty rebuild configuration explicitly.
- Run the existing `prime-rebuild.md` device loop with fresh matching data and watched screens: login, Chessplayer names/skills, Central Plains ribbon, Yixing art, Talent Card grid/search/detail (Arena Tiger), and populated Hero/Effect/Equipment tabs.
- Verify actual pushed file hashes, prime-only content, skipped-counter parity and normal APK identity/debug flag after every run.
- Rerun on already-English data: no duplicate append, no lossy texture drift, no unexplained staged packages. Test older broken dictionary repair in scratch data before a live repair cycle.
- Test activity recreation, screen-off, app process death, Shizuku death, permission revocation, low space, installation failure and interruption between index/shard commits. Verify rollback/resume plus restore; reboot testing must preserve recovery files.
- Test first official install only with explicit data-loss consent; then normal update and repeat-patch paths. Test the existing measured Xiaomi/MIUI Android 12 device first if available, plus another OEM and newer Android/page-size environment before claiming broad support.
- Update this Report with actual commands/results, README with Android setup/build instructions, and coverage ledger only if measured counts move. Keep the Windows source/offline checks passing.

## [S1] Problem

The existing product runs all computation on Windows and uses `adb.exe` for discovery, file transfer, package installation and shell commands. The user wants those operations and translation generation to run on the same Android phone as the game, with Shizuku supplying the privileged device operations.

This changes the application platform and transport. It must preserve the existing translation scope, signing identity, package format and device-measured fixes.

### Feasibility and evidence

| Requirement | Research result | Remaining proof |
|---|---|---|
| PC-free privilege startup | Shizuku supports on-device wireless-debugging startup on Android 11+ | Actual OEM setup and reliability |
| Privileged device operations | Shizuku UserService executes Java/JNI as shell UID 2000 when started with ADB | Installation, force-stop and process probes |
| Release-game private files | Shell cannot directly read another app's private directory | Preserve access APK plus `run-as`; measure SELinux transition |
| Python 3.12 engine | Chaquopy supports Python 3.12 | Existing sourceless bytecode and imported modules on Android |
| Texture pipeline | Upstream codecs have portable source / ARM paths | Android Python 3.12 builds, correct results and acceptable performance |
| DLL-free append and repair | Already implemented in this repository | Same output semantics on ARM and device acceptance |
| APK install and restore | Android provides installer sessions; shell commands are another route | OEM prompts, source streaming and interrupted-session recovery |

Shizuku's [API documentation](https://github.com/RikkaApps/Shizuku-API) describes shell/root identity and UserService. Use UserService rather than the deprecated `Shizuku.newProcess` interface. Binder death and permission denial need explicit handling. Its process is not a normal Android application process; keep UI and application lifecycle work in the patcher app.

Android's [run-as implementation](https://android.googlesource.com/platform/system/core.git/+/refs/heads/master/run-as/run-as.cpp) requires a shell/root caller, rejects non-debuggable packages and sets an app SELinux context. Therefore Shizuku is not a way to skip re-signing or the access APK. UID equivalence alone does not establish that a particular OEM allows the entire execution chain: test it.

## [S2] Design

### Launcher identity (2026-10-05)

Launcher name and notification title are **HOK ACE Patcher**; application ID, code namespace and
instrumentation identity are `dev.halixm.hokacepatcher`. Current Android helpers and command examples
follow that identity; older evidence below retains its measured package/process names. The launcher
uses the user-supplied `foreground-icon.png` unchanged inside a 15% inset, an adaptive icon and
white `#FFFFFF` background (was `#9EBEF7` until 2026-10-08), for both normal and round launcher requests. The home Test version badge is
removed; required consent and incomplete-acceptance explanations remain. This changes patcher
branding only. The game's package, stable signing identity and translation content are unchanged.
The old app's recovery/scratch files stay in its old sandbox. No automatic migration or uninstall is
performed; the new app must receive its own Shizuku permission. Build/install/resource verification
is recorded in the Report; removal of the badge does not establish release acceptance.

### Automatic interaction (implemented development UI)

The user taps **Start** once. `MainActivity` automatically requests Shizuku permission when the
server is available; a stopped server requires starting Shizuku outside the app. The flow continues
on return. `AutomaticRoute` selects pending emergency verification first, interrupted patch recovery
next, then first-setup recovery/download confirmation, otherwise fresh preparation. More than one
candidate of a type requires manual selection; journal discovery errors stop instead of guessing.
Fresh `ApkPreparation.load` still fully verifies the receipt and APK identities before automatically
choosing first-setup consent or the patch update checkpoint. Old preparation receipts are not reused
for a new Start. Successful verification/recovery/setup checkpoints continue into the next operation.
Failure or cancellation disarms continuation; no automatic retry loop clears damaged records.

Only unavoidable actions are shown: Shizuku startup/authorization, data-loss and Scan-to-login
consent, finishing actual in-game downloads and the final finished-update acknowledgment.
The setup checkpoint offers **Open game** only after validated normal installation and clear other
recovery. Returning restores the confirmation. All consent checkboxes start clear; backend request
claim and identity gates remain intact. Voice/checklist/tutorial buttons are removed. Recovery and
technical tools remain available, with actual progress and the existing safe-cancel command.

Each automatic worker operation receives a fresh UUID `flow` token, echoed into atomic progress
and terminal state. Continuation requires that exact token and a retired process-local service;
old results and saved running records cannot advance. Activity recreation carries only outstanding
work or an outside-app Shizuku/download wait. Cancel/Back disarms automatic continuation; Open game retains the download checkpoint;
process loss or stale running status requires another Start, which rechecks durable recovery.
A missing admission response stops after 30 seconds. Opening the app alone never starts game changes.
Actual automatic live patch/first conversion, permission dialog/OEM matrix and low-literacy user
acceptance remain separate device gates.

### 1. Application and engine boundaries

Create an additional Android application under `android/`; keep the Windows application available. Proposed components:

| Component | Responsibility |
|---|---|
| Kotlin UI, preferably Compose | Shizuku setup, preflight, explicit first-run data-loss consent, progress, recovery, logs and counts |
| `PatchCoordinator` | Persisted workflow, operation serialization, cancellation, restore priority and session ownership |
| `PrivilegedDeviceService` (AIDL UserService) | Fixed package discovery, APK stream reads, install/uninstall, force-stop, `run-as` streams, hashes and version checks |
| Python worker in the ordinary patcher process | Existing `build_patch`, catalog loading, append, relocation and graphics |
| `android_bridge.py` | Explicit filesystem paths, runtime loading and structured progress/summary conversion |
| Android codec builds | ARM64 LZ4, Zstandard, ASTC and Ooz/texture decode dependencies |
| Session journal and verified cache | Source identity, recovery APK, snapshot, staged files and applied-file progress |

Do not import `patcher_core` into the Android app: its import path also brings desktop concerns. Reuse the engine directly. Extract the three summary accessors into a shared platform-neutral module if useful, retaining Windows behavior. Shared code changes require the existing Windows/offline checks.

Keep privileged service methods narrow and typed. Accept only the fixed game package, validated numeric package IDs, known filenames and selected user profile. Do not expose an unrestricted command execution endpoint. Use argument arrays and controlled scripts, validate stream lengths, bound diagnostics and enforce one patch session at a time.

### 2. Python and native dependencies

Start with Chaquopy and explicitly select **Python 3.12**. Its [version matrix](https://chaquo.com/chaquopy/doc/current/versions.html) includes 3.12; pin the Gradle plugin, compatible Android Gradle plugin and build Python once the proof of concept works. Never move to Python 3.13 to solve a wheel problem: the consumed bytecode requires 3.12.

Extract consumed runtime assets unchanged into a versioned read-only runtime directory and append it after Android's stdlib and installed native packages. In particular, Android LZ4 must resolve before the runtime's Windows LZ4 package. Confirm `lz4.__file__`, `lz4.block.__file__`, `sys.version` and bytecode magic in diagnostics. Test real `wxq_patch` imports and operations, not only `import wxq_patch`. Keep the source resource directory immutable. Chaquopy has filesystem extraction options and documents unsupported stdlib operations in its [Gradle guide](https://chaquo.com/chaquopy/doc/current/android.html); audit reachable subprocess/multiprocessing use before choosing a worker model.

| Dependency | Initial approach | Gate |
|---|---|---|
| `wxq_patch` | Consume existing `.pyc` files unchanged | Catalog load, scan, stage and read-back succeed |
| `lz4` | Android CPython 3.12 wheel or cross-built extension | Real block framing and compressed-size behavior match |
| `zstandard` | Android wheel or NDK/cross-built extension | Mixed stored/Zstd/LZ4/Oodle asset fixtures decode identically |
| `astc-encoder-py` | Cross-build the existing binding and its matching encoder source | Six footprints, patch-range preservation, idempotence and speed |
| `texture2ddecoder` | Cross-build its existing wrapper | BC7/ASTC byte order and color channels match |
| `pyooz` (`ooz`) | Cross-build existing wrapper and ARM-compatible decoder path | Real game's Oodle assets decode byte-identically |
| `pypinyin` | Package library and dictionary data | AI opponent names match desktop output |
| `cryptography` | Android wheel if available | Existing signing path works, or use the alternative below |
| Pillow / `archspec` | Include only where actual runtime imports require them | No hidden desktop-only dependency |
| Tkinter, darkdetect, PyInstaller | Exclude from Android | Engine import path stays independent of GUI/build tools |

Android wheels are not established by a Linux aarch64 or Windows ARM64 wheel. Test build/install/load for each pinned dependency. [ASTC binding source](https://github.com/K0lb3/astc-encoder-py), [Arm encoder source](https://github.com/ARM-software/astc-encoder), [texture decoder wrapper](https://github.com/K0lb3/texture2ddecoder) and [pyooz metadata](https://pypi.org/project/pyooz/) are the starting points. ARM support makes a port plausible, not already verified. If a Python binding is impractical, a small JNI or CPython adapter exposing the exact functions used by this engine is a fallback; measure it with the same fixtures.

Test both 4 KB and 16 KB page-size environments. Chaquopy's [changelog](https://chaquo.com/chaquopy/doc/current/changelog.html) warns that native wheels can remain incompatible with 16 KB devices even when the embedding runtime supports them. Check every shipped native library, including dependencies, rather than declaring support from the Python runtime alone.

### 3. Map the existing ADB operations

| Current operation | Android/Shizuku counterpart |
|---|---|
| `adb devices` / USB wait | Binder availability, authorization, UID and service capability probe |
| `pm path` | Privileged package query or controlled `pm path`; reject split APKs initially |
| `adb pull` of APK | Open source in UserService and transfer through a file descriptor/pipe |
| `adb install -r` | Shell installer session with streamed input, or tested privileged installer API |
| First-run uninstall | Explicit consent, targeted uninstall, verify absence, install normal APK |
| `am force-stop` | Privileged force-stop API or controlled command |
| `exec-out run-as ... tar` | UserService child process with binary stdout pipe and separately drained stderr |
| `adb push` to shell temporary path | Prefer input streams to `run-as` writer; shell staging only if measured necessary |
| `run-as ... cp` | Write temporary sibling files as game UID, verify, then rename under controlled stopped-game state |
| Watchdog cleanup | Fixed-path `run-as` operation after successful apply |
| Final normal APK reinstall | Same installer adapter, followed by certificate/version/debug-flag verification |

Do not assume the shell service can read the patcher's private cache pathname, or that the app can open `/data/local/tmp`. Pass `ParcelFileDescriptor` handles or pipes. Carry large APKs and backups outside Binder transaction payloads. For command-backed installation, derive and validate the device's supported create/write/commit syntax, stream the declared number of bytes to install-write stdin, and abandon incomplete sessions. An API-backed implementation needs equivalent session ownership and failure handling.

Handle prompts without claiming silent installation on every ROM. Keep a public installer/FileProvider route for emergency normal-APK restoration if Shizuku dies. Android's [installer session reference](https://developer.android.com/reference/android/content/pm/PackageInstaller.Session) documents asynchronous session results and user interaction; use installed-package verification rather than treating a launched intent as success.

### 4. Signing and cache identity

Keep `resources/key/key.pk8` and `cert.der` unchanged for game APK signing. The patcher Android app uses its own application signing key. Never regenerate the existing game key or substitute Android debug keystore signing.

Initially reuse streaming ZIP rewrite and APK v2 signing. If Android `cryptography` is a blocker, separate the RSA PKCS#1 v1.5 SHA-256 operation behind an adapter implemented with Java `Signature`, loading the existing PKCS#8 key and certificate. Keep the v2 digest and ZIP rules intact. Verify with desktop `apksigner verify --verbose --print-certs`, then actual device installation. Do not ship an alternative signer merely because it emits an APK.

Preserve an already-normal stable-key source byte-for-byte when its manifest requires no edit,
as the Windows cache does. Derive the access APK from the prepared normal APK. Check decoded
entry hashes independently when cross-platform ZIP rewriting changes archive bytes; only the
manifest may change. Verify v2 signatures for the supported Android 11+ range with
`apksigner verify --min-sdk-version 30 --verbose --print-certs` before device installation.

Fingerprint original, normal and access APKs by SHA-256, package/version, certificate and manifest debug flag. Do not reproduce the desktop cache's size-only identity heuristic on Android. Recovery must never adopt an access APK as the normal source. Normal manifest content changes remain exactly the debug flag and optional launcher label; app content inside the APK remains original. Inspect native-library alignment/install behavior on representative devices before claiming broad APK compatibility.

### 5. Workflow and recovery

Preferred production flow shortens the time the game stays debuggable:

1. Preflight: Shizuku alive/authorized, supported UID and user, game installed unsplit, enough storage, no unresolved earlier session. Capture installed identity and complete normal-APK recovery material.
2. First run only: show the existing data-loss and Scan-to-login explanation; obtain explicit in-app consent before uninstall. Install the patcher-signed normal game and wait for the full in-game update/login screen. Do not attempt to preserve official-signature private data by assumption.
3. Force-stop game. Install access APK. Read package version, create and verify a complete snapshot including Watchdog, and collect file hashes.
4. Restore and verify the normal APK before the potentially long engine build. Keep the game closed; record this requirement clearly. This costs additional large APK installations but improves recovery during computation.
5. Build from the snapshot with `apk=normal_apk`, `builder_dir=None` and empty `cycle_assets`. Fail preflight if `REBUILD_PACKAGES` is nonempty. Verify staged payloads and summary before entering the write phase.
6. Force-stop again, reinstall access APK and compare the live input version/hashes with the snapshot. If the user launched or updated the game, discard stale output and resnapshot. No writing across a changed input layer.
7. Back up affected files, write verified temporary siblings, commit replacements with the game stopped, read back SHA-256 and journal each file/package. Index and shard files must remain a consistent set; individual rename atomicity is not a transaction across several files. On partial apply, recover or roll back the entire affected set before allowing launch.
8. Clear Watchdog in the same intended scope as desktop, restore normal APK, verify installed identity and no DEBUGGABLE flag, then report applied tables/images and both skipped counters.

For the initial device spike, the shorter desktop sequence is acceptable solely to measure capabilities; always restore immediately afterwards. Benchmark the production sequence's extra APK I/O before deciding whether to optimize it. Do not trade restore reliability for a speculative speedup.

Journal states should include PREPARED, WAITING_FOR_GAME_UPDATE, SNAPSHOT_ACCESS_INSTALLED, SNAPSHOT_READY, NORMAL_RESTORED_FOR_BUILD, BUILDING, STAGED, APPLY_ACCESS_INSTALLED, APPLYING, RESTORING, COMPLETE and RECOVERY_REQUIRED. Persist intent before destructive transitions and verified outcome afterwards. On restart inspect actual installed APK and partially written files; a `finally` block cannot recover a killed process or reboot.

Cancel before access freely. During access/apply, cancellation becomes a controlled restore/rollback operation. Binder loss stops new writes and retains journal/backups. If access remains installed, present immediate normal-APK recovery; if packages are partially committed, explain that restoring the APK alone does not repair them and require rollback/resume before launch. Never mark a run complete while restore or file consistency is unresolved.

Use a user-started foreground worker with visible progress, serialized engine work and bounded codec threads. Evaluate the appropriate service type: local package modification may need documented `specialUse`, while file transfer fits `dataSync`; declare only justified types. The [foreground-service type documentation](https://developer.android.com/develop/background-work/services/fgs/service-types) describes these cases. Include timeout handling and durable checkpoints; [Android 15 behavior changes](https://developer.android.com/about/versions/15/behavior-changes-15) limit some service types. A foreground service improves survival but does not guarantee it.

### 6. Storage and output parity

Use app-private session directories and a fresh staging directory for every run. Offer user-selected export for logs/recovery APK/backups; SAF is not a way to bypass the game's private storage permissions. Confirm the recovery installer can consume its provided URI before entering access mode.

The desktop 8 GiB check is not an Android guarantee. Estimate space for original/normal/access APKs, unsigned rewrite temporary files, backup/snapshot, prime extraction, staged packages and rollback copies, plus filesystem margin. Check before every large operation. Measure the actual peak and reduce duplicate retention only after recoverability is proven. Recoverability bounds retention: a resolved session keeps receipts only, `work/` goes once the build stages, and the saved official APK goes once the installed game is the stable-key normal build. Stream archives/APKs and process textures individually with bounded parallelism; never load a whole APK or game dump into memory.

Preserve the exact `device_patch_summary.json` contract and package modes. Keep translated tables, applied textures, skipped tables and skipped textures separate. Cross-check staged numeric directories against the unique reported package IDs. Preserve prime append read-back, per-chunk compression framing, B-tree guards, Talent dictionary identity keys/307200-byte chunk size, resource-token expansion and rerun idempotence.

Catalog and runtime are immutable consumed resources. Default `cycle_assets` remains empty; no new extra-text allowlist entries, dictionary rows, protected config edits, APK content injection or package rebuilds belong in this port. Coverage changes require the existing watched device cycle and ledger updates.

## [S3] Out of Scope

- Root-only access as the required path; Android <=10 PC-free setup; split APK or secondary-profile support in v1.
- A complete Kotlin rewrite of the translation engine, cloud translation/building or prepatched game APK distribution.
- Removing signature conversion, fixing direct WeChat/QQ authentication, changing Tencent's updater or expanding translation coverage.
- Assuming Shizuku makes the game data publicly readable, or treating `/sdcard/Android/data` logs as the private Qts package store.
- Windows builder emulation, generic package-key derivation, or enabling previously withdrawn extra-text assets.
