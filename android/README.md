# HOK ACE Patcher for Android

Launcher name: **HOK ACE Patcher**. Application ID: `dev.halixm.hokacepatcher`.
The attached foreground artwork is packaged unchanged, inset 15% for adaptive-mask headroom;
its background is `#9EBEF7`. The home screen no longer has the Test version badge.
The old `io.github.hokace.patcher` package and private recovery data are retained separately;
there is no automatic data migration. New Shizuku authorization is required for the new identity.
The deliverable copy is `artifacts/dev.halixm.hokacepatcher.apk`; Gradle's build output stays
`android/app/build/outputs/apk/debug/app-debug.apk`.

This is a development Android patcher alongside the Windows app. A full live patch succeeded on the Xiaomi Android 12 on 2026-10-05; broader device and release acceptance remains open.
It targets Android 11+ / ARM64 and uses a Shizuku AIDL UserService with fixed operations.
The home screen's **Language** card chooses English or Bahasa Indonesia (`PatchLanguage`, saved
on the phone). The same choice immediately switches the patcher's interface between English and
Indonesian, including confirmations, recovery controls and notification actions. Raw technical logs
stay unchanged for diagnosis. A run reads it once when it starts and records it in the session journal, and the card
is locked while work is in progress. The engine carries `catalog/` and `catalog_id/` side by side,
because the Indonesian catalog reads the English texture payloads it does not re-draw.
The home screen has one **Start** button. The visual theme follows [wxq.qq.com](https://wxq.qq.com/): lavender and
ice-blue backgrounds, a geometric gradient hero, translucent white cards and violet-blue buttons.
The hero is drawn locally; it needs no network or downloaded website artwork. Language choices,
disabled states, recovery controls and scrolling retain their existing behavior.
Shizuku permission is requested automatically when
its server is available. If it is stopped, Start opens Shizuku and continues when you return.
If Shizuku is missing, the button opens its official Google Play listing; a browser opens that
listing when the Play Store app is unavailable. If neither can open, the app explains how to install it.
The live activity log and technical log each scroll independently inside the home page.
After Start, pending emergency verification comes first, followed by interrupted patch recovery,
setup recovery or the fresh-download checkpoint. Clean state starts preparation automatically.
Fresh preparation is fully loaded/verified before automatically choosing first-setup consent or
the final translation update confirmation. No preparation-date picker is needed in this flow.
After a recovery or setup checkpoint succeeds, the flow continues automatically; failure/cancel
stops continuation. Download completion and data-loss/login consent still require unchecked
acknowledgments. **Open game** is available at the setup download checkpoint only when the
normal installation is verified and other recovery is clear; returning restores that checkpoint.
Voice and all-step/tutorial buttons are removed. Progress, safe stopping, technical tools and
emergency recovery remain. Multiple unfinished records require manual selection; damaged records
stop the flow. Only a matching per-operation token and a retired service permit continuation,
so old results cannot start another operation. Opening the app never starts a patch by itself.
Storage-budget errors show the required free GB, currently available GB and additional GB to clear.
Required GB rounds up, free GB rounds down and clearing advice matches those displayed numbers;
GB uses 1,000,000,000 bytes. The screen rechecks free space while showing the error. Once enough
space is available it asks you to retry, without starting work automatically. Existing byte-valued
errors are supported; unknown installer thresholds are explicitly unknown rather than guessed.
Storage reserves, byte-level refusal and recovery-file retention are unchanged.

The development UI offers a confirmed patch request for converted installs.
The converted-install full patch flow is now device-verified on the measured Xiaomi. First-official conversion acceptance and deliberate live recovery tests remain open; destructive device tests require separate consent.
First-setup journal/controller simulations preserve uninstall/install intent and wait for a
fresh game download before allowing translation. The fixed Shizuku transport is implemented;
source/profile checks and existing-game refusal are tested without game mutation. First-setup
UI requires two initially unchecked acknowledgments: local data loss and Scan-to-login.
A one-use request binds the receipt and APK identities to its mutation journal before removal.
Foreground setup, installation recovery and fresh-update confirmation are connected; actual
first-official conversion remains untested. Cancel stops before removal, or normal installation
continues to a safe checkpoint after removal has begun. Setup errors now make one automatic
recovery attempt using saved intent and freshly verified cache material. A lost installer reply
is checked before another installation; removal is never repeated. Persistent failures retain
the journal for the recovery action. After all new downloads finish, return to the patcher and confirm the update checkpoint. It verifies and reuses matching cached APKs before the translation confirmation.
An explicitly selected development diagnostic can replace/restore the game APK.
If patch/setup records cannot be read, the emergency installer offers an explicit retained-APK
choice. Candidate metadata is only a selection aid: the chosen APK still undergoes full content,
manifest and stable-signer verification before installer access. Damaged transaction records remain
untouched and continue to block new patching. A pending emergency request keeps its original APK
identity; a damaged emergency request is refused rather than replaced.
Diagnostic export reads raw journal/base-backup bytes without AtomicFile recovery or journal loading.
It marks them unvalidated, includes SHA-256 and Base64 for exact bytes, limits each record to 1 MiB,
all raw bytes to 8 MiB and each session directory to 256 entries. Oversized/linked/missing records
produce explicit messages. The readable application log is limited to its last 256 KiB.
This export neither repairs records nor grants permission to resume the game.
The current gate and measured results are in
[`android-shizuku-patcher.md`](../docs/compose/spec/android-shizuku-patcher.md).


## Latest live result (2026-10-05)

| Result | Xiaomi Android 12 / game data 1.4.0.2 |
|---|---|
| Full patch | Completed; normal APK and applied package payload verified |
| Translation | 391 text tables and 395 textures applied across six packages |
| Known gap | One text table skipped; zero textures skipped |
| Coordinator time | About 6 minutes 22 seconds |
| Observed free-space decrease | 6.14 GB; lowest sampled free space 5.25 GB |

The user reports full patch success; the retained session is `COMPLETE`, has no dirty packages or mutation intent, and records verified normal restoration. Evidence and the remaining acceptance gates are in the feature report. These are measurements from one run, not fixed minimum storage/RAM requirements. The watched-screen checklist, repeat-patch behavior, deliberate live interruption tests, another OEM and Android 15/16 KiB testing remain open.

For normal use, install **HOK ACE Patcher** and **Shizuku**. The probe fixture and `androidTest` APK are development tools and are not needed for patching.

## Build on Windows

Install Android SDK platform 35, JDK 17+, and run the repository's `setup.bat` with Python 3.12.
Set `ANDROID_HOME` to the SDK and `JAVA_HOME` to the JDK. The checked-in Gradle 8.9 wrapper
pins AGP 8.7.3, Kotlin 2.0.0, Chaquopy 17.0.0 and Shizuku API/provider 13.1.5.
The Chaquopy build interpreter is the repository's `.venv/Scripts/python.exe`.

```bat
android\gradlew.bat -p android :app:assembleDebug :fixture:assembleDebug :app:assembleDebugAndroidTest
```

This default build diagnoses available Python/native modules and refuses full scratch builds
unless every codec loads. To include the three locally cross-built graphics bindings:

```bat
.venv\Scripts\python.exe android\native\build_wheels.py --ndk <SDK>\ndk\28.2.13676358 ^
    --python-target <Gradle-cache>\target-3.12.12-0-arm64-v8a.zip ^
    --work <native-work-dir> --output android\wheels
```

The complete-codec build also requires locally built pinned LZ4, both Zstandard bindings
and FreeType. Run the two additional recipes in
[`native/THIRD_PARTY.md`](native/THIRD_PARTY.md), then build:

```bat
android\gradlew.bat -p android -PfullCodecs :app:assembleDebug :app:assembleDebugAndroidTest
.venv\Scripts\python.exe tools\research\check_android_native.py android\app\build\outputs\apk\debug\app-debug.apk --report artifacts\android-aligned-native-inventory.json
```

The measured source-built APK passes the static ELF check for all 84 libraries and SDK ZIP
alignment. Neither check proves loading on a physical 16 KiB device. Compression codec and
full both-layer offline checks pass on the existing 4 KiB Android 12 phone; no live translation
acceptance or broad page-size support follows from those checks.
The minimal build without `fullCodecs` still uses repository compression wheels and is a
diagnostic baseline. Earlier complete-codec builds used those wheels too; their six static
alignment failures are retained as historical evidence rather than shipped in the current
complete-codec configuration.

For a new device, the platform harness records model/API/ABI/page size, inspects all packaged
native alignment, verifies the actual installed development APK hashes, and requires both
codec/import and frame/font tests to pass. Use a fresh output directory. `--install` updates
only the built development app/test APKs after checking their fixed package names; omit it
when the exact build is already installed:

```bat
.venv\Scripts\python.exe tools\research\check_android_platform.py --adb <SDK>\platform-tools\adb.exe ^
    --serial <device-serial> --output artifacts\<fresh-platform-check> --install
```

It uses no game data or Shizuku operation. The current Xiaomi Android 12 control passes with
4096-byte pages; actual installed APK hashes match the inspected build and both checks pass.
The Android 15 PixelOS device is unavailable as of 2026-10-05; its model/ABI/page size and
loader acceptance remain unmeasured. A 16 KiB result records codec loading on that device;
physical device identity, full pipeline/visual parity and Android 15 worker lifecycle are
separate requirements.

Find the target ZIP under `%USERPROFILE%\.gradle\caches\modules-2\files-2.1\com.chaquo.python\target\`.
The packaged-notice auditor in `native/audit_notices.py` checks actual APK metadata, notice hashes
and native payloads. Current inventory: twelve Python distributions, thirty notice/provenance
files and eighty-four native payloads. Core license texts and pinned codec source-header notices
are retained; broader redistribution review remains open.

Maven runtime candidates are recorded by `:app:writeRuntimeDependencyInventory`;
`native/audit_maven.py` rechecks those artifact hashes and reads cached POM license metadata
without network access. The published-source option verifies the matching downloaded POMs/source
JARs: seven binaries and seven license declarations now verify, including JetBrains annotations
13.0. Source/attribution completeness, binary/source equivalence and plugin-injected runtime
components remain separate. Commands and the current gaps are in `native/THIRD_PARTY.md`.

The first build populates this cache. Native build source hashes and redistribution requirements
are recorded in [`native/THIRD_PARTY.md`](native/THIRD_PARTY.md). Generated wheels are ignored.
No Tencent builder DLL is included. Catalog/runtime files are consumed unchanged, hashed,
packaged with a `.payload` suffix to defeat AAPT gzip transformations, and verified during
versioned extraction. Python directory names beginning with `_` must survive AAPT filtering.
Archspec is extracted to supply its filesystem-based CPU metadata. Android's installed LZ4
precedes the bundled runtime in `sys.path`.

## Device boundary checks

Install `app/build/outputs/apk/debug/app-debug.apk`, the debug fixture APK, and the app's
`androidTest` APK. MIUI may require **Install via USB**, the separate **USB debugging
(Security settings)** option, and a prompt for each APK. Start Shizuku
through wireless debugging, open **HOK ACE Patcher**, and authorize it. The normal process
must fail to invoke `run-as`; an EACCES failure before exec is an expected denial on MIUI.

```bat
adb shell am instrument -w -r -e requireFullCodecs true ^
    -e class dev.halixm.hokacepatcher.EngineProbeTest,dev.halixm.hokacepatcher.NativeDependencyProbeTest,dev.halixm.hokacepatcher.ShizukuProbeTest ^
    dev.halixm.hokacepatcher.test/androidx.test.runner.AndroidJUnitRunner
```

The fixture round-trips 4096 random binary bytes as its own UID and removes its scratch directory.
APK discovery is read-only. Copy/hash and force-stop are explicit UI actions. A copied installed
APK is a diagnostic specimen, never automatically adopted as a recovery APK.
Add `-e probeFirstSetupReadOnly true` with `-e expectedApkSha256 <matching-control-hash>`
to check retained package discovery, source/profile preflight, stale hash and invalid removal
refusal, and refusal to install over an existing game. This option invokes no valid uninstall
and its first-install request must fail before installer session creation.
To exercise descriptor streaming and reinstallation of the fixture's own installed APK, add
`-e probeApkStream true -e probeFixtureInstall true`. Supply
`-e expectedApkSha256 <matching-control-hash>` to check the streamed game APK's identity.
The installer probe accepts no caller-supplied APK or path. It creates/writes/commits a session,
verifies the installed fixture's hash, and abandons an unsuccessful session. The two game
operations remain separate: streaming is read-only; `-e probeForceStop true` closes the game.
Add `-e probeFixtureAbort true` to prove an abandoned fixture session cannot commit and leaves
its APK/hash/round-trip intact. `-e probeBinderLoss true` stops only the app's own UserService,
requires its disconnect callback and rejects a stale binder call; the Shizuku server stays running.

The live-game diagnostic is disabled by default. Only after explicit authorization, supply
`-e probeGameCycle true -e gameCycleSession <name>` and the three expected SHA-256 arguments
`expectedApkSha256`, `expectedAccessSha256`, `expectedCertSha256`. The private session requires
the verified `normal.apk`, `access.apk` and matching `game/` dump. APK package/signature/debug
flags, versions and current installed hash are checked before replacement. Sessions enforce
the fixed game package; only a 4096-byte temporary file and `1.info` are accessed. The normal
APK is restored in `finally` and its hash/signature/debug flag checked. This is a feasibility
probe with USB recovery available, not a durable recovery implementation.

Retain the independently verified normal PC APK and the USB connection throughout the test.
If the app/service dies or restore fails, restore that exact file with
`adb install -r <verified-normal.apk>`, verify the debug flag is cleared and recheck its hash
before launch. Do not adopt the access APK as the recovery source. The first measured restore
exceeded the initial 30-second deadline; large APK writes/commits now allow 180 seconds.

## Full engine checks in private scratch storage

First run the desktop DLL-free build and graphics checks from the feature record, then capture
its matching input identities and output hashes:

```bat
.venv\Scripts\python.exe tools\research\android_control.py --snapshot <pristine-snapshot> ^
    --apk <matching-normal.apk> --output <desktop-output> --report <control.json>
.venv\Scripts\python.exe tools\research\android_harness.py --adb <adb.exe> --serial <serial> ^
    --session <fresh-name> --game <pristine-snapshot>\game --apk <matching-normal.apk> ^
    --control <control.json>
adb shell am instrument -w -r -e class dev.halixm.hokacepatcher.EngineScratchTest ^
    -e session <fresh-name> dev.halixm.hokacepatcher.test/androidx.test.runner.AndroidJUnitRunner
```

The development harness forwards an ephemeral host port to a localhost-only test receiver.
A one-use token, bounded file counts/lengths, private paths and per-file SHA-256 checks guard the
copy. The receiver exists only in the instrumentation APK; only the debug app declares Internet
permission. This avoids the truncated transfers observed with the earlier stdin harness. Inputs consume about
4.7 GB on the tested data, plus engine work/output; a fresh session is required on every run.
The engine rechecks all pristine file and APK hashes against the desktop control before staging.
For an individually supplied development file, use `--file <source> <private-relative-name>`
instead of the full bundle arguments. This still requires a fresh private session and per-file
hash verification; it grants no permission for a live-game operation.

`build.log`, `graphics.log`, `metrics.json`, `staged-hashes.json` and `out/device_patch_summary.json`
live under the app's private `files/scratch/<name>/`. The graphics oracle is supplied separately
by the harness and never included in shipping imports. `work/` and `out/` must be absent when
starting a build. These tests use copies only; they grant no authorization for a live-game cycle.

The separately authorized live-game access/restore control passes. Java RSA produces byte-identical
v2 signatures for the fixture and full normal APK. Recovery journal/path/snapshot tests pass on
Android. The coordinator has not executed a live patch or rollback. The UI now offers foreground-owned
APK preparation, saved progress/results and recovery selection for unfinished sessions. Public
patch invocation remains unaccepted and initial conversion is unfinished. Private post-commit/rollback interruption tests pass, and a read-only
foreground worker survives Activity recreation. The diagnostic UI can verify cached recovery,
export logs and explicitly open the normal APK installer. Cross-UID recovery URI consumption
passes with an exact full-APK hash. Opening the emergency installer now saves a verification-pending
record before dispatch. The record survives app recreation and is included in log export. After
finishing or cancelling the installer, use **Verify installed normal APK with foreground worker**:
only independent full installed-APK verification resolves that exact saved request. A failed
check keeps the warning; this never clears interrupted game-data writes or reports patch completion.
Pending verification blocks new patch/first-setup mutation, and installer opening refuses an
already-active coordinator. Twelve private intent/guard/setup-recovery checks pass in 0.681 s.
After the user restarted Shizuku and unlocked the phone, the emergency foreground verification
test passes with Activity recreation and the actual normal APK. The separate baseline Activity
test then fails to resume; that combined run has one pass and one failure. Actual public
installer-return and physical process-death acceptance remain open.
Actual first-install execution, full worker
lifecycle failures and live Android-generated translation acceptance remain separate gates. Do not advertise
PC-free patching, complete translation, or 16 KiB support from this spike.

Private emergency intent/guard and first-setup recovery checks (no game mutation):

```bat
adb shell am instrument -w -r -e class dev.halixm.hokacepatcher.EmergencyRestoreProbeTest,dev.halixm.hokacepatcher.FirstSetupCoordinatorProbeTest dev.halixm.hokacepatcher.test/androidx.test.runner.AndroidJUnitRunner
```

The physical process-death diagnostic uses the installed disposable fixture and the debug
app/test APKs. Start Shizuku and authorize the development app first. The host refuses active
patch/recovery and unfinished real sessions before instrumentation. It force-stops only the
feasibility app after a real fixture index rename, then restarts instrumentation to reload
the saved journal and restore five files plus the empty Watchdog directory through Shizuku.
The latest cycle passes in 15.016 s; fixture APK identity stays unchanged and owned test files
are cleaned. The journal correctly refuses completion without normal APK verification.
This exercises real file rollback across app death, with synthetic phases and small fixture
files; full foreground coordinator, live-game and installer interruption acceptance remains open.

```bat
.venv\Scripts\python.exe tools\research\check_android_process_death.py --adb <adb.exe> ^
    --serial <device-id> --output artifacts\android-process-death-new-cycle
```

The output directory must be new. Expected arm instrumentation ends with a crashed-process
message after the host confirms its durable receipt and kills the app; that message alone
is not a pass. The final report requires a new PID, exact rollback, unchanged fixture APK,
no false normal-APK completion and cleanup. If a case has an armed receipt but recovery
fails, retain its fixture and snapshot; retry with `--recover-case <case-UUID>` and a fresh
output directory. Neither phase installs or writes the live game.
Ordinary test discovery skips this two-phase test unless the host supplies its phase and UUID.

Patch-journal initialization now publishes only after its first durable write. Reserved
unpublished drafts cannot authorize mutation and do not block recovery or export. Damaged
published journals, missing mutation state, false terminal state, oversized files and linked
published paths refuse further work. Preparation, consent, both coordinators and recovery/export
use the same discovery rules. Twenty-two private checks pass; the physical fixture app-death
cycle still passes with the new journal version (15.282 s). Physical interruption of initial
publication itself and the full foreground coordinator remain separate gates.

Foreground worker connections now have unique service tags. Closing one owner cannot remove
another owner's service; repeated close is harmless. Actual UserService death is observed once,
wakes waiters and prevents later use. Four binding/foreground checks pass in 19.973 seconds.
This addresses service ownership; the earlier intermittent timeout cause remains unproved, and
whole Shizuku-server/process/reboot recovery remains a separate gate. Read-only binding checks
(destroy only the patcher's own UserService, never the game):

```bat
adb shell am instrument -w -r -e class dev.halixm.hokacepatcher.WorkerBindingProbeTest,dev.halixm.hokacepatcher.WorkerProbeTest,dev.halixm.hokacepatcher.FirstSetupWorkerGuardProbeTest dev.halixm.hokacepatcher.test/androidx.test.runner.AndroidJUnitRunner
```

Actual connected foreground verification probe:

Actual denied-permission dispatch passes in 1.717 s with Shizuku running and only HOK ACE's
authorization disabled. The worker refuses before binding and changes no emergency records.
Re-enabled authorization then passes full read-only installed-normal verification with Activity
recreation in 14.741 s. To repeat, explicitly disable only HOK ACE authorization, keep the phone
unlocked and Shizuku running, and select `WorkerPermissionProbeTest`; re-enable afterward and run
`WorkerProbeTest#testReadOnlyVerificationSurvivesActivityRecreation`. Neither result accepts
permission revocation during a patch.

The actual foreground read-only verification loss probe waits for the connected checking phase,
stops only the uniquely identified UID-2000 `dev.halixm.hokacepatcher:worker` process, and requires
an error plus unchanged pending intent. A fresh worker must independently verify the normal APK
before resolving the same intent. Final check passes in 17.905 s; no game installation/data writes,
server stop or permission changes. Blank Binder exceptions now save a plain retry explanation and
their exception type. Shizuku must be running/authorized and the phone unlocked. No other worker
or emergency intent may be active:

```bat
adb shell am instrument -w -r -e class dev.halixm.hokacepatcher.WorkerServiceLossProbeTest#testActualForegroundServiceLossKeepsIntentThenFreshVerificationResolves dev.halixm.hokacepatcher.test/androidx.test.runner.AndroidJUnitRunner
```

If that probe retains its own unresolved read-only intent, restart/authorize Shizuku and run
`WorkerServiceLossProbeTest#testRecoverOnlyOwnedReadOnlyVerificationIntent`. It refuses unrelated
requests and clears its own intent only after independent normal-APK verification. The initial
stopped-Shizuku failure and successful owned recovery are retained; this is not whole-patch,
permission-revocation, server-death or reboot acceptance.

First-setup consent/private recovery checks (never start a valid live setup request):

```bat
adb shell am instrument -w -r -e class dev.halixm.hokacepatcher.FirstSetupConsentProbeTest,dev.halixm.hokacepatcher.FirstSetupRequestProbeTest,dev.halixm.hokacepatcher.FirstSetupCoordinatorProbeTest,dev.halixm.hokacepatcher.FirstSetupJournalProbeTest,dev.halixm.hokacepatcher.FirstSetupWorkerGuardProbeTest dev.halixm.hokacepatcher.test/androidx.test.runner.AndroidJUnitRunner
```

First-setup journals publish only after their initial file and directory are synced. Reserved
`.creating-<UUID>` directories left before publication cannot authorize mutation and are excluded
from pending history/export. Corrupt published journals still stop recovery. Thirteen combined
private recovery/status/foreground checks pass in 17.354 seconds; physical process-death testing
remains open.

The request probe uses the retained full private normal/access APKs and synthetic unconverted
source metadata. It checks consent binding and replay, not first-official signature conversion.
The worker guard submits only a nonexistent consent UUID. Actual setup needs a separately
authorized data-loss device cycle; do not press its positive setup button during these checks.

`FixtureInstallerService` exists only in the debug source set. Its APK and data targets are
fixed to the disposable fixture, and release DEX inspection excludes it. Its real uninstall /
service-death / invalid-install / restore probe now passes in 11.235 seconds after the user
confirmed both MIUI installation/security-debugging options. The installed fixture matches its
original 12,365-byte APK exactly; receipt and independent read-back are in
`artifacts/android-fixture-installer-security-enabled-receipts.json`. Earlier user-restricted
failures and USB rescues remain recorded. This accepts the tiny fixed fixture cycle, not
large-game installation, Shizuku-server death, full worker recovery or first-official conversion.
The fixture's exact original APK remains on the phone and exported to
`artifacts/android-fixture-installer-recovery/`; the live game was never targeted by these probes.

Saved worker failures now translate installer codes into recovery steps while retaining the
original error in journals/logs. Installation restrictions point to unlocking and allowing
prompts; low storage preserves recovery files; signer conflicts do not suggest uninstalling.
When recovery fails differently from the first action, the latest installer code decides the
instructions. Setup and translation failures keep their separate recovery actions.

The read-only fixture target selector is safe while it is absent:

```bat
adb shell am instrument -w -r -e class dev.halixm.hokacepatcher.FixtureInstallerProbeTest#testFixedFixtureTargetReadOnly dev.halixm.hokacepatcher.test/androidx.test.runner.AndroidJUnitRunner
```

Private recovery primitive checks (no game operations):

```bat
adb shell am instrument -w -r -e class dev.halixm.hokacepatcher.JournalProbeTest,dev.halixm.hokacepatcher.SnapshotProbeTest dev.halixm.hokacepatcher.test/androidx.test.runner.AndroidJUnitRunner
```

`ApkPreparationProbeTest` runs the complete preparer against the approved full normal APK in
private storage. It preserves an already-normal stable-key APK unchanged, generates the access
APK, verifies recovery/cache identities and reloads the receipt. All 1625 decoded entries match
the fresh Windows control; only the manifest differs from normal. The access APK's archive hash
differs from Windows, but independent SDK v2 verification for Android 11+ passes. Installation
of this newly generated APK remains a separate device gate. The test needs the protected normal
and approved access control, plus four APK-size allocations and storage margin. It binds no
Shizuku service and exposes no installer operation.

```bat
adb shell am instrument -w -r -e class dev.halixm.hokacepatcher.ApkPreparationProbeTest dev.halixm.hokacepatcher.test/androidx.test.runner.AndroidJUnitRunner
```

The passing test takes 146.058 s and retains receipts/entry inventories/resource metrics under
`files/apk-preparation-probes/<uuid>/`. Its duplicate source is removed after verification;
the access APK remains available for independent signature checks. Retained evidence is under
`artifacts/android-apk-preparation-retained/`. For these v2-only APKs, SDK verification uses
`apksigner verify --min-sdk-version 30 --verbose --print-certs <apk>`; default verification also
demands legacy v1 signing for the game's older declared minimum.

`RecoveryStoreProbeTest` additionally needs the approved `control-1402-verified` and
`game-access-1402` scratch APK copies. It retains the exact normal APK in `files/recovery/`,
checks full content/manifest/certificate identity and refuses access APK adoption. These tests
do not authorize any game writes or official-signature conversion.

`TransactionProbeTest` uses a private fake device to interrupt an index commit and a rollback,
then verifies whole-set restoration and the remaining normal-APK completion gate. It never
binds Shizuku or accesses game files. `WorkerProbeTest` is a read-only installed-APK verification
while the Activity is recreated. UI harnesses need the phone unlocked; MIUI blocks background
and keyguard activity launches. `RecoveryProviderProbeTest` passes its unlocked retry in 54.021 s,
reading all normal-APK bytes through another UID and refusing a writable descriptor.

The development UI's preparation action runs in the foreground worker and never installs the
game. Saved progress/results refresh automatically and survive Activity recreation. The recovery
chooser lists unfinished runs by date. Preparation refuses pending recovery and observes
cancellation at boundaries around large operations; a current copy/sign may finish before it
stops. Full foreground preparation and recovery chooser execution remain unaccepted.

```bat
adb shell am instrument -w -r -e class dev.halixm.hokacepatcher.PreparationGuardProbeTest,dev.halixm.hokacepatcher.WorkerStatusProbeTest,dev.halixm.hokacepatcher.WorkerProbeTest dev.halixm.hokacepatcher.test/androidx.test.runner.AndroidJUnitRunner
```

The guard/result tests operate privately; WorkerProbeTest streams the installed normal APK
read-only and checks that the recreated screen displays its verification result. None of these
checks installs an APK over the game or changes game data.

The converted-install patch button requires a verified preparation and an unchecked-by-default
confirmation that every in-game update finished and the game is closed. Start becomes enabled
only after that checkbox is checked. Confirmation is bound to the preparation receipt and APK
identities, expires after 15 minutes and is one-use. The worker takes only the request UUID;
changed preparations, old/replayed confirmations and unfinished recovery are refused. Installing
the development app does not authorize a live cycle; do not trigger this action through tools
without separate cycle approval.

```bat
adb shell am instrument -w -r -e class dev.halixm.hokacepatcher.PatchRequestProbeTest,dev.halixm.hokacepatcher.UpdateCheckpointProbeTest,dev.halixm.hokacepatcher.CoordinatorSourceGuardProbeTest dev.halixm.hokacepatcher.test/androidx.test.runner.AndroidJUnitRunner
```

Request tests need the retained approved full preparation fixture. They rehash normal/access
material in an isolated context; UI tests toggle the checkbox and Cancel without pressing Start.
Source tests use an unavailable Binder to prove version/signer refusal before access. No test
invokes the live patch worker. Full live patch and changed-label source acceptance remain open.

`CoordinatorRecoveryProbeTest` exercises the real recovery coordinator with an isolated private
context, simulated game files/installation, and an injected installed verifier. It needs the
approved protected normal APK and `game-access-1402/access.apk`; installer simulation streams
and hashes those existing files without installing them. It tests interrupted whole-set rollback,
corrupt-backup refusal, normal restore priority, final installer acknowledgment loss, and changed
live-layer refusal during forward recovery. Application code uses the production independent
installed verifier. These recovery-only tests do not establish full `run()` or live process-loss acceptance.

```bat
adb shell am instrument -w -r -e class dev.halixm.hokacepatcher.CoordinatorRecoveryProbeTest,dev.halixm.hokacepatcher.JournalProbeTest,dev.halixm.hokacepatcher.TransactionProbeTest dev.halixm.hokacepatcher.test/androidx.test.runner.AndroidJUnitRunner
```

Offline-build storage preflight now reads verified snapshot sizes, package descriptors, APK ZIP
metadata, APK prime indexes and immutable catalog sizes before creating `work/` or `out/`. It
reserves the APK packages the append actually reads, each package holding catalog content plus a
staging-attempt copy, four replacement trees, normal-APK recovery and margin. The 2.72 GB control
estimates 2,668,538,356 additional bytes (it was 7,497,769,750 when every package was counted; the
actual build left 1.62 GB). The snapshot check also reserves the latest completed run's build
estimate. This is an estimate; measured peak and interrupted low-space acceptance remain open.
Read-only control and forced refusal checks:

```bat
adb shell am instrument -w -r -e class dev.halixm.hokacepatcher.BuildStorageProbeTest,dev.halixm.hokacepatcher.StorageProbeTest,dev.halixm.hokacepatcher.WorkerProbeTest dev.halixm.hokacepatcher.test/androidx.test.runner.AndroidJUnitRunner
```

The build-storage probe needs the retained pristine control and prior full-coordinator manifest.
It copies and rehashes the approved 2.7 GB inputs into a private temporary snapshot, then removes
that copy after checking the production bridge and forced refusal. Those two checks pass; the
combined foreground check times out connecting to Shizuku, then passes alone in 15.329 seconds.
Intermittent binding reliability remains open.

`FullCoordinatorProbeTest` runs the complete production coordinator with all approved pristine
inputs, four synthetic Watchdog files and real full APK streams. File transport, installation
and installed verification are private simulations. Both success and post-commit failure/rollback
pass in 700.46 s; all twelve staged hashes match the first Android control. Default storage
reserves and the 8 GiB snapshot cap are unchanged; allow about 13 GiB free before these tests.
It retains receipts and removes only its verified generated files after terminal acceptance.
It never binds Shizuku or modifies the live game.

```bat
adb shell am instrument -w -r -e class dev.halixm.hokacepatcher.FullCoordinatorProbeTest dev.halixm.hokacepatcher.test/androidx.test.runner.AndroidJUnitRunner
```

For the measured control, `prepare_android_workflow_space.py` archives generated scratch outputs
with full SHA read-back before compacting disposable copies. To restore the first output needed
by a fresh already-English rerun after compaction:

```bat
.venv\Scripts\python.exe tools\research\restore_android_control_stage.py --adb <adb.exe> --serial <serial> --archive artifacts\android-workflow-retained
```

The helper requires the compacted control with `out/` absent, checks archive/input identities,
uses the loopback receiver, independently rehashes all received files and publishes the output
directory only after verification. These research helpers do not grant live-game authorization.

`FixtureFileProbeTest` binds the debug-only `FixtureFileService`, exercising the production
file adapter against `io.github.hokace.fixture` only. Snapshot/hash validation, atomic write,
wrong-hash and dangling-temporary-link refusal, hidden Watchdog cleanup/restoration and an
orphan-child lock test pass in 7.329 s. The child retains the lock after its parent shell dies;
the next writer proceeds only after the child exits. Fixture setup and cleanup use instrumentation
stdin pipes. The production service's target remains fixed to the game. This does not establish
full live coordinator or stopped-Shizuku recovery acceptance.

`PerformanceProbeTest` creates a fresh offline session with source links to the approved control,
runs both layers and retains `resource-metrics.json`. The measured run takes 149.109 s including
verification/setup (127.906 s engine), observes 1616109568 bytes less filesystem free space and
1837764 KiB maximum resident memory. One-second samples report thermal status 0 and maximum
battery temperature 33.5 C. These observations are not production limits: high-water RSS includes
process lifetime and disk changes may include other apps. The coordinator records the same metrics.
`StorageProbeTest` checks recovery reserves and arithmetic refusal; private transaction tests include
empty-stage Watchdog rollback and final-install forward completion. Full low-space/lifecycle
acceptance and the complete build-work estimator remain unfinished.
Four counters are retained in the session journal before applying files. Completed recovery
returns these counters without needing the Python engine; a rolled-back session reports
`recovered` and omits its planned translation counts. Private persisted-result tests pass;
full recovery-worker acceptance remains open.

```bat
adb shell am instrument -w -r -e class dev.halixm.hokacepatcher.PerformanceProbeTest dev.halixm.hokacepatcher.test/androidx.test.runner.AndroidJUnitRunner
```

After a successful performance run, the research cleanup tool exports and reads back its evidence,
requires every staged hash to match the first Android control, then removes only canonical generated
work/out directories. It preserves inputs and recovery caches:

```bat
.venv\Scripts\python.exe tools\research\android_scratch_cleanup.py --adb <adb.exe> --serial <serial> --session performance-<uuid> --output artifacts\performance-retained
```

```bat
adb shell am instrument -w -r -e class dev.halixm.hokacepatcher.FixtureFileProbeTest dev.halixm.hokacepatcher.test/androidx.test.runner.AndroidJUnitRunner
```

Static 16 KiB ELF inventory currently refuses six dependency libraries even though the APK's
SDK ZIP-alignment check passes. See `native/THIRD_PARTY.md` for the checker, source companion
command and remaining dependency notice/source work.

Compare fetched staging with the retained desktop control:

```bat
.venv\Scripts\python.exe tools\research\android_compare.py --desktop <desktop-output> ^
    --android <fetched-output> --hashes <android-staged-hashes.json> --report <comparison.json> ^
    --adb <adb.exe> --serial <serial> --session <completed-scratch-name>
```

The fetch uses binary subprocess streams and validates each output hash. Every asset in a
differing package is compared, with unexplained raw differences rejected and decoded ASTC
differences recorded. A passing numerical tolerance is evidence for encoder parity; watched
game rendering remains a separate acceptance gate. Windows native runtime files are excluded
from generated Android assets; the source runtime files remain untouched.

The home screen shows the latest 40 timestamped worker messages while patching. It refreshes every second, follows new messages when you are at the bottom, and lets you scroll back. Messages remain visible after completion, failure, or reopening the app; each new worker operation starts a fresh list. Progress shows actual activity rather than an estimated percentage.

APK preparation now checks the retained cache before allocating new files. Matching installed and cached APKs must pass full SHA-256, manifest, signer/version, recovery identity checks. Identical immutable APKs share an inode through a durable hard link (or a verified private symbolic reference when SELinux blocks hard links); recovery/source/access paths remain available. A patch session links its access APK too, with a space-checked copy fallback. Snapshot storage is measured only after data access is installed: reserve archive plus extracted files and normal-install space. A measurement/storage failure follows existing restore handling. The 8 GiB snapshot limit remains a maximum, not a required allocation for every run.

The app removes what recovery no longer needs. A completed or cancelled session keeps its journal and small receipts, while its game-data copy, build work and staged packages are deleted at the end of the run and before the next run's first space check. Build work is deleted as soon as the packages are staged. Once the installed game is verified as the stable-key normal build (after first setup and at the start of each patch), the saved official APK (`original.apk`, about 2 GB) and every preparation made for another game version are deleted. The current version's access APK and every recovery APK are kept.

Snapshots accept the measured empty updater directory trees `packages/builtin/Merge/<package-id>` and `packages/builtin/CleanCopy/<package-id>`. These are directory-only exceptions; unknown files, traversal and archive links still fail closed. Python-only engine updates retain independently verified APK preparations.
