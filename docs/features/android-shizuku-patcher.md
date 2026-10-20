---
feature: android-shizuku-patcher
status: device-validation-in-progress
updated: 2026-10-19
---

# Android patcher using Shizuku

## Report

**Versioning (2026-10-17):** local and CI builds default to the root `VERSION` file,
currently `1.6.1.12` (three game version numbers plus patch revision). Release tags must
match that file. Android's install `versionCode` remains separate and increasing;
see [patch versions](../../README.md#patch-versions). The launcher name is
**HOK ACE Patch**. The update checker compares four-part versions and normalizes
legacy five-part tags by omitting the extra middle zero.

**Where it stands (2026-10-05).** The user ran a full patch from the Android app on the Xiaomi
M2007J3SG (MIUI, Android 12, game data 1.4.0.2): live snapshot, build, apply and normal-APK restore
completed, with the same coverage as the Windows control. It is one normal-path run. It does not
establish a complete translation, watched-screen acceptance, a first official conversion, a repeat
patch on the translated layer, deliberate failure injection, another OEM, 16 KiB pages or a
cable-free release cycle. The run's counts, identities and resource samples are in the lab notebook,
2026-10-05; the gates still open are under *Still owed*.

Developer build/test commands and harness usage are in [`android/README.md`](../../android/README.md).
Native source hashes, build flags and redistribution inventory are in
[`android/native/THIRD_PARTY.md`](../../android/native/THIRD_PARTY.md). The port edited neither the
translation engine nor the catalog, runtime or key resources, and the coverage ledger's counts did not move.

### Journey log

- Feasibility app: the Shizuku UserService runs as shell UID 2000 and round-trips bytes through a debuggable fixture, while an ordinary app process is refused `run-as` — passed (lab notebook, 2026-10-03).
- The DLL-free engine on the phone (Chaquopy, Python 3.12, Android codec builds) over both data layers of a private copy of the pristine dump — passed, outputs matched the desktop control (lab notebook, 2026-10-03).
- Live-game diagnostic (access APK in, game-UID round trip, normal APK back) — failed on a 30 s installer deadline, passed at 180 s (lab notebook, 2026-10-03).
- Installer, recovery, foreground, signing, native-alignment and coordinator checks, one row each — fixture and private proofs pass, release gate not passed (lab notebook, 2026-10-03).
- Packaging and transport corrections (AAPT `.gz` stripping and `_backends` filter, archspec extraction, `-fms-extensions` scope, Toybox tar truncation, an invalid synthetic ASTC fixture) — each fixed (lab notebook, 2026-10-03).
- Snapshot extraction refused the updater's empty `Merge` / `CleanCopy` directories — the reader admits those two roots and nothing else (lab notebook, 2026-10-05).
- Repeated APK preparation and a free-space refusal after a game download — preparation reuses verified cache content and budgets are measured; cache reuse device-verified (lab notebook, 2026-10-05).
- Live activity log on the main screen — built; display during a live patch unverified (lab notebook, 2026-10-05).
- First full live patch from the app — complete, coverage equal to the Windows control (lab notebook, 2026-10-05).
- Acceptance audit — ten gates still open, carried into *Still owed* (lab notebook, 2026-10-05).
- `Shizuku worker connection timed out` on a second phone: a lost background-start handoff was suspected and the wait raised to 45 s — not the cause on that phone (lab notebook, 2026-10-06).
- Infinix X6853 (MediaTek, Android 16): every Shizuku user service dies in the ROM's `makeApplicationInner` — the app's own shell starter is the fallback ([S2]), device-verified through preparation (lab notebook, 2026-10-06).
- Diagnostic trace and a fuller log export — compiled; not yet exported on a phone (lab notebook, 2026-10-06).
- Users ran out of space after the first check passed: resolved sessions, the saved official APK and other versions' preparations are reclaimed, and the build estimate reserves only what the build writes ([S2]) — verified offline only (lab notebook, 2026-10-06).
- Android 15 Infinix X6851 fails APK preparation on the access APK's debug identity — cause not yet measured (lab notebook, 2026-10-08).
- The same failure on a moto g45 5G: the manifest diagnostic was always `false` (a `jarray` compared to `bytes`), and an `android:debuggable` out of resource-id order is never read by Android — the edit now re-sorts it ([S2]); not device-verified (lab notebook, 2026-10-17).
- Cause of both, and of a realme RMX3830 (all three Android 15): the first Android 15 release never derives an APK file's `ApplicationInfo.flags`, so `FLAG_DEBUGGABLE` always reads false. `ApkIdentity` now resolves `android:debuggable` through `Resources.obtainAttributes` ([S2]); verified against Android's own flag on an Android 16 emulator, not yet on an Android 15 phone (lab notebook, 2026-10-19).
- Dual App profile on two Transsion phones: shell may not name user 999 — the profile check falls back to `dumpsys package` ([S2]); unit-tested, not device-verified (lab notebook, 2026-10-09).
- Game reported missing for the main user — the error now names hidden, other-profile or absent; the next log showed it absent (lab notebook, 2026-10-09).
- vivo V2561 (Android 16) refuses user 10 with a plain `Error:` line, no `SecurityException`, so the profile check never reached its fallback; it now does, and a stop with no saved records no longer offers recovery ([S2]) — unit-tested, not device-verified (lab notebook, 2026-10-19).
- `engine_preflight` refused every patch from an APK built without `-PfullCodecs` — full codecs became Gradle's default (lab notebook, 2026-10-09).
- A written translation stuck in recovery on the realme RMX3830: the UI's once-a-second journal read deleted the worker's in-flight write (`Session journal read-back differs`), and once the game had run the applied-layer audit could never pass (`Game file set changed`). Reads no longer touch `AtomicFile`'s files; such a run closes unconfirmed and keeps its pristine delta; *Free up space* added ([S2]) — compiled and unit-tested, not device-verified (lab notebook, 2026-10-19).

### Still owed

Several gates are still open. Permission denial, a stopped Shizuku and OEM install prompts have not been
tested through the full flow, so their exact failures and the settings each needs are not recorded. The
reachable imports have not been fully inventoried: every native dependency for ARM64 and CPython 3.12
still needs its version, NDK configuration and redistribution notices or source obligations recorded.
Peak disk and RAM, thermal effects and elapsed time have not been measured, and 16 KB native loading has
not been exercised on its own. The saved emergency installer request has not been accepted through a
real user-assisted restore with independent installed-APK verification, which must leave a pending
package rollback intact. The workflow does not yet refuse stale live layers, unsupported layouts, split
APKs or a non-empty rebuild configuration explicitly.

On the translation side, the [device cycle](../runbooks/device-cycle.md) has not been run on Android output with
fresh matching data and watched screens: login, Chessplayer names and skills, the Central Plains
ribbon, Yixing's art, the Talent Card grid, search and detail (Arena Tiger), and populated Hero, Effect
and Equipment tabs. Each run's pushed file hashes, prime-only content, skipped-counter parity and normal
APK identity and debug flag are not yet verified after every run. A rerun on already-English data still
has to show no duplicate append, no lossy texture drift and no unexplained staged packages, and repair of
an older broken dictionary has to pass in scratch data before a live repair cycle.

The lifecycle matrix is also open: activity recreation, screen-off, app process death, Shizuku death,
permission revocation, low space, installation failure and interruption between the index and shard
commits, each needing rollback or resume plus restore, with reboot testing that keeps the recovery
files. A first official install is to be tested only with explicit data-loss consent, followed by the
normal update and repeat-patch paths, on the measured Xiaomi/MIUI Android 12 phone first and then on
another OEM and a newer Android and page-size environment before any broad support is claimed. When
those land, this Report takes the actual commands and results, README takes the Android setup and build
instructions, and the coverage ledger changes only if measured counts move; the Windows source and
offline checks keep passing throughout.

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

**Verdict:** a fully on-phone patcher is technically plausible. Shizuku is a suitable candidate for replacing the Windows ADB transport and shell execution, provided the device probes below pass. It does not port the Python engine, provide root on an unrooted phone, or grant direct access to the release game's private data. Full parity also requires Android builds of the native codecs. Treat this as a gated port, not a confirmed working replacement.

The proposed first release targets **Android 11+ and arm64-v8a**, with Shizuku started through wireless debugging. End users should need neither a PC nor a USB cable. Developer options and wireless-debugging setup remain necessary; some OEMs also require their USB-debugging/security settings to be enabled. Shizuku must be started again after reboot. Android 10 and older are outside the PC-free first-release scope. These startup constraints are documented in the [Shizuku manual](https://shizuku.rikka.app/guide/setup/).

### What was inspected

- `app/patcher_core.py`: detection, APK caching/re-signing, first-run uninstall, temporary access APK, `run-as` snapshot, translation, package writes, Watchdog cleanup and normal-APK restore.
- `app/apk_tools.py`: streaming ZIP rewrite, 4-byte stored-entry alignment, certificate matching and APK v2 signing.
- `tools/build_device_patch.py`, `package_rebuild.py`, `device_extensions.py`, `qts_relocate.py`, `mobile_graphics.py`, `qts_builder.py`: engine entry points and native dependency boundaries.
- `requirements.txt` and `resources/runtime/`: Python 3.12 requirement; bundled LZ4 includes `_block.cp312-win_amd64.pyd` and `_version.cp312-win_amd64.pyd`.
- Existing feature records, `docs/lab-notebook.md` and `docs/translation-progress.md`: measured restrictions, both data layers, append behavior and Talent Card repair.

The normal pipeline is DLL-free because `REBUILD_PACKAGES = ()`. It still needs the APK for prime-only assets. Removing the APK input would lose parity even if downloaded text and textures worked. Do not bundle Tencent's Windows builder into the Android app or invent a replacement builder.

## [S2] Design

### Launcher identity (2026-10-05)

Launcher name and notification title are **HOK ACE Language Patcher**; application ID, code namespace and
instrumentation identity are `dev.halixm.hokacepatcher`. Current Android helpers and command examples
follow that identity; older evidence in the lab notebook retains its measured package/process names. The launcher
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

**Shortcuts (2026-10-20).** A result that leaves the game ready to play (*Translation added*,
*removed* or *written*) leads with **Open game**, the same launch the home screen's `game` action
does, with **Start another patch** under it. Long-pressing the launcher icon offers *Start patch*,
*Save log for help* and *Check for updates* (`LauncherShortcuts`): dynamic shortcuts in the
patcher's own language, republished whenever the activity is created, so a language switch follows.
Each taps the same home-screen action, with the same guards, so *Start patch* is a deliberate Start,
not the app opening: reopening from Recents does not repeat it, and it is refused while ② offers only
*Save log for help*. On a cold start it waits up to 3 s for Shizuku's binder before treating Shizuku
as stopped. They open the non-exported `ShortcutEntry` alias, which only the launcher can start on the
app's behalf. A shortcut tapped during a run starts the activity afresh, as process loss does: the
worker keeps running and the screen reads its record. Not yet tried on a phone.

**Notifications (2026-10-20).** Android 13+ shows the worker's progress notification, with its
*Cancel and recover* action, only once the player allows notifications, and the patcher never asked.
It now asks once (`RunNotification.askOnce`), when its first run is under way: Shizuku's access
dialog is settled by then, so the two never stack. A muted notice in ② says why, and the run goes
on whatever the answer; a refusal is never asked again. When a run finishes while the patcher is
not on screen, the worker posts its result (`RunNotification`): *Translation added*, *removed* or
*written* with an **Open game** action, or *Work stopped*, which opens the patcher. Intermediate
steps of the automatic flow (verify, prepare), a stop the player asked for and *Space freed* post
nothing. Not yet tried on a phone.

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
3. Force-stop game. Install access APK. Read package version, create and verify a complete snapshot including Watchdog, and collect file hashes. The privileged tar streams through a pipe straight into the extraction (`unpack_snapshot_stream`); both ends hash the stream and must agree, and no archive file is written.
4. Keep the access APK installed through the build, as the Windows patcher does. Keep the game closed; record this requirement clearly. Until 2026-10-18 the normal APK was restored and verified here and the access APK reinstalled after the build; that pair cost about 2.5 minutes and ~2.4 GB of transient install space on a Redmi Note 9 Pro, and is gone (lab notebook, 2026-10-18, "Android patch run: stage timings and five fewer passes"). A process killed during the build leaves the access APK installed until recovery restores the normal one, as during the snapshot and the apply.
5. Build from the snapshot with `apk=normal_apk`, `builder_dir=None` and empty `cycle_assets`. Fail preflight if `REBUILD_PACKAGES` is nonempty. Verify staged payloads and summary before entering the write phase. The snapshot and APK are verified once, by `build_snapshot`, immediately before the build reads them; the storage estimate reads the manifest only.
6. Force-stop again and compare the live layer with the snapshot (`validateGameSnapshot`, which also fails unless the access APK is still installed). No writing across a changed input layer.
7. Back up affected files, write verified temporary siblings, commit replacements with the game stopped, read back SHA-256 and journal each file/package. Index and shard files must remain a consistent set; individual rename atomicity is not a transaction across several files. On partial apply, recover or roll back the entire affected set before allowing launch.
8. Clear Watchdog in the same intended scope as desktop, restore normal APK, verify installed identity and no DEBUGGABLE flag, then report applied tables/images and both skipped counters.

For the initial device spike, the shorter desktop sequence is acceptable solely to measure capabilities; always restore immediately afterwards. Benchmark the production sequence's extra APK I/O before deciding whether to optimize it. Do not trade restore reliability for a speculative speedup.

Journal states should include PREPARED, WAITING_FOR_GAME_UPDATE, SNAPSHOT_ACCESS_INSTALLED, SNAPSHOT_READY, BUILDING, STAGED, APPLYING, RESTORING, COMPLETE and RECOVERY_REQUIRED; a run goes SNAPSHOT_READY → BUILDING and STAGED → APPLYING directly. NORMAL_RESTORED_FOR_BUILD and APPLY_ACCESS_INSTALLED remain valid so journals of older runs still recover. Persist intent before destructive transitions and verified outcome afterwards. On restart inspect actual installed APK and partially written files; a `finally` block cannot recover a killed process or reboot.

Cancel before access freely. During access/apply, cancellation becomes a controlled restore/rollback operation. Binder loss stops new writes and retains journal/backups. If access remains installed, present immediate normal-APK recovery; if packages are partially committed, explain that restoring the APK alone does not repair them and require rollback/resume before launch. Never mark a run complete while restore or file consistency is unresolved.

Use a user-started foreground worker with visible progress, serialized engine work and bounded codec threads. Evaluate the appropriate service type: local package modification may need documented `specialUse`, while file transfer fits `dataSync`; declare only justified types. The [foreground-service type documentation](https://developer.android.com/develop/background-work/services/fgs/service-types) describes these cases. Include timeout handling and durable checkpoints; [Android 15 behavior changes](https://developer.android.com/about/versions/15/behavior-changes-15) limit some service types. A foreground service improves survival but does not guarantee it.

### 6. Storage and output parity

Use app-private session directories and a fresh staging directory for every run. Offer user-selected export for logs/recovery APK/backups; SAF is not a way to bypass the game's private storage permissions. Confirm the recovery installer can consume its provided URI before entering access mode.

The desktop 8 GiB check is not an Android guarantee. Estimate space for original/normal/access APKs, unsigned rewrite temporary files, backup/snapshot, prime extraction, staged packages and rollback copies, plus filesystem margin. Check before every large operation. Measure the actual peak and reduce duplicate retention only after recoverability is proven. Recoverability bounds retention: a resolved session keeps receipts only, `work/` goes once the build stages, and the saved official APK goes once the installed game is the stable-key normal build. Stream archives/APKs and process textures individually with bounded parallelism; never load a whole APK or game dump into memory.

Preserve the exact `device_patch_summary.json` contract and package modes. Keep translated tables, applied textures, skipped tables and skipped textures separate. Cross-check staged numeric directories against the unique reported package IDs. Preserve prime append read-back, per-chunk compression framing, B-tree guards, Talent dictionary identity keys/307200-byte chunk size, resource-token expansion and rerun idempotence.

Catalog and runtime are immutable consumed resources. Default `cycle_assets` remains empty; no new extra-text allowlist entries, dictionary rows, protected config edits, APK content injection or package rebuilds belong in this port. Coverage changes require the existing watched device cycle and ledger updates.

### Worker connection fallback (2026-10-06)

Shizuku's own starter cannot start a user service on some ROMs (lab notebook, 2026-10-06), so the
app carries its own; it is device-verified on the Infinix X6853.

- **Connection order.** `WorkerDeviceConnection` still asks Shizuku for the user service first. After 10 s with no binder it also launches `ShellServiceStarter` through Shizuku's shell-process API (`Shizuku.newProcess`, private in API 13.1.5 and reached by reflection): `CLASSPATH=<this APK> exec app_process /system/bin --nice-name=<pkg>:worker dev.halixm.hokacepatcher.ShellServiceStarter <token> <authority>`, passed as `sh -c` positional arguments rather than spliced into a string.
- **Skipped step.** The starter constructs `PrivilegedDeviceService` directly. It needs no Context, so it skips the `makeApplication` step that crashes.
- **Handoff.** The starter hands the binder to `WorkerBinderProvider` through `getContentProviderExternal` and `IContentProvider.call`, the same handoff Shizuku's own starter uses with its manager. Three gates protect it:
  - the provider is guarded by `INTERACT_ACROSS_USERS_FULL`, which only the shell holds;
  - `call` refuses any caller but uid 2000;
  - each connection's random token is single use and registered only while that connection waits.
- **First binder wins.** A late binder from the other path is refused. The starter exits when the app's client binder dies, and `close()` destroys it.
- **Remembered per phone.** The working path is saved under the ROM fingerprint plus the Shizuku server and app versions, so the next run on this phone starts the fallback at once. A new ROM build or Shizuku release tries Shizuku's starter again.

### Profile check (2026-10-09)

- Shell may not name a profile that carries `DISALLOW_DEBUGGING_FEATURES` (a Dual App profile, for
  one) in any `--user` command, while `dumpsys package` and an all-users `pm uninstall` never reach
  that check. When `pm list packages --user N` fails with exactly that `SecurityException`, the guard
  reads every profile's state from `dumpsys package <game>`, grep-filtered so the diagnostic cap
  cannot cut it off.
- An installed copy in another profile is refused; a profile the dump does not list is refused as
  uncheckable; a dump with no record counts as absent only when `pm list packages -u --user 0` agrees.
- Every absence listing names the main user (`FirstSetupPackagePolicy.gameAbsent`). On vivo Android 16
  the listing without `--user` returned a line that is not a package right after first setup's
  uninstall, which stopped setup and every recovery with the game already removed (2026-10-19).
- The denial has two forms: Transsion's `java.lang.SecurityException: Shell does not have permission
  to access user N`, and vivo Android 16's plain `Error: Shell does not have permission to access user
  N` as the command's whole output (2026-10-19). `FirstSetupPackagePolicy.profileDenied` matches each
  for its own user id only; any other failure still stops the check. The guard itself is
  `FirstSetupPackagePolicy.requireNoOtherUsers`, which takes the device commands as functions so
  `FirstSetupProfileTest` runs it against a fake read-only device.
- `prepare` runs the same read-only check (`IPrivilegedDeviceService.checkGameProfiles`) before it
  copies anything whenever the installed game is not on the stable key, so a phone that first setup
  will refuse learns it before the preparation.
- A failed run shows the error's cause, not its stack: the live log keeps `ErrorSummary.cause`, and an
  error card directly under ② Start (`error-card`, error colours) copies the worker's full raw error
  and offers Save log for help (`error-export-log`). The "Game won't open?" card (`recovery-card`,
  warning colours) follows it, both above the log (shared-design ticket 10).
- After a stop, the recovery card appears only when `RecoveryMaterial` finds something to recover (an
  interrupted patch, a first setup in progress, or a retained normal APK), and shows only the actions
  those records serve; records that cannot be read keep every action. A stop in the read-only checks
  says *Tap Try again* instead of pointing at recovery options (2026-10-19).
- ② Start rewrites itself for each result (`UiText.result`): *Translation added*, *Translation
  removed*, *Translation written* and *Space freed* show a summary line, the run's own counts as
  rows (`result-items`) and, after an added or removed translation, the Scan to login note
  (`result-note`). A notice is one muted line inside ② (`friendly-notice`), hidden when it only
  repeats the instruction.

### Storage reclaim (2026-10-06)

- A session that reaches `COMPLETE` or `CANCELLED` keeps only its journal, hash lists, logs, snapshot
  manifest and summary; the coordinator clears the bulk at the end of a run and clears earlier
  resolved sessions before a run's first budget. An unresolved session and a damaged journal are left
  alone, because rollback and forward recovery read them.
- `ApkPreparation.releaseUnneeded` deletes the saved official APK once the installed game is verified
  as the stable-key normal build, and every preparation whose receipt names another game version. The
  run's own preparation, an unreadable receipt and anything a retained APK path links to are kept.
- `build_storage.estimate` (schema 2) reserves, twice, only the packages that hold catalog content,
  and extracts only the APK packages whose catalog content the override layer lacks, as
  `add_prime_only` does. The snapshot check also reserves the latest completed run's estimate.
- The home app keeps each game APK an install replaced (~2.4 GB) on storage until it restarts; on a
  Redmi Note 9 Pro one launcher force-stop freed 9.45 GiB (lab notebook, 2026-10-18, "Android patch run:
  stage timings and five fewer passes"). `PrivilegedDeviceService.releaseReplacedGameApks` force-stops the
  default home app after every game install, and `StorageBudget.releaseReplacedGameApks` calls it before
  the patch run's, recovery's and the preparation's first budget. It never fails the caller and skips an
  unresolved home (the chooser), the game, the patcher, Settings and Shizuku. Protocol version 10.

### Unconfirmed close and Free up space (2026-10-19)

- A run with no package mid-change (`packages_dirty` false) has nothing to roll back. When forward
  recovery's applied-layer audit reports that the game changed the layer (`Game file set changed`,
  `Game file changed:`), the run closes `CANCELLED` with `layer_unconfirmed` and reports
  `recovered_unconfirmed`, and the Start flow stops there instead of patching again. Any other audit
  failure still leaves the run `RECOVERY_REQUIRED`.
- `promoteSessionDelta` treats such a run as completed: its delta was made from the run's own snapshot
  and staged output, and each entry applies only while its file holds the staged bytes it records.
  Recovery that resolves a run now promotes its delta at once (`keepResolvedDelta`).
- *Free up space* (`PatchCoordinator.freeSpace`, worker action `free_space`), on the main screen under
  *Check for updates* and in the recovery options. It refuses while an emergency restore or first setup
  is pending, or when a run has a package mid-change. Each other unfinished run closes by
  `SessionJournal.closeUnconfirmed` once its normal APK is verified installed. Then it promotes the
  newest delta and frees resolved sessions, replaced game APKs and `releaseUnneeded`'s APKs. It keeps
  the pristine delta, the saved normal APKs and this game version's preparation.
- Its opt-in, unchecked by default and offered only while saved APKs exist, removes every preparation
  (the access APK) and every saved normal APK as well (`ApkPreparation.removeSaved`), about 4 GB. It
  runs only once the installed game is verified byte-identical to a saved normal APK, with no run, first
  setup, emergency restore or preparation in flight; otherwise it keeps them and says so. Nothing needs
  them until the next patch, whose preparation copies the installed app and derives both again, so it
  then needs four APK sizes free (`APK preparation`), not the reuse path's nothing.
- Every `AtomicFile` record is read through `DurableFiles.readCommitted`, which never deletes `.new` or
  moves `.bak` as `AtomicFile.readFully()` does.

### Repatch from the pristine delta (2026-10-17)

From [`.scratch/language-switch`](../../.scratch/language-switch/spec.md), ticket 04. The engine makes
and applies the delta (`tools/pristine_delta.py`, staged into `engine/tools` with the other tools);
Kotlin only names the files (`PristineDelta.kt`).

- The delta lives in `filesDir/pristine/delta.bin`, with the staged-hash record
  `staged-hashes.json` beside it, outside `sessions/`, so no release reclaims it.
- `estimate_snapshot_build` takes the kept folder and reserves `pristine_copy_bytes`, the pristine size of
  every file the delta names; `requireSpace` checks it before the build makes the copy.
- `build_snapshot` rebuilds those files from `snapshot/packages` into the session's `pristine/` copy;
  `snapshot/` keeps the phone's actual bytes, so rollback is unchanged. The build reads a layer of
  symlinks: the snapshot, with the named files taken from the copy, and `control.json` names their
  pristine SHA-256. A file the previous install translated and this build leaves alone is copied into
  `out/` at its pristine bytes and written back like any staged file. The copy is deleted after the
  build, with `work/`.
- Refusals, all raised by `build_snapshot` before the first write, so no game file is written (recovery
  then restores the normal APK): a named file at neither its staged nor its pristine bytes; a
  file at a hash this patcher staged with no delta (or no entry) behind it; and, with no delta, a
  build whose text pass does not read the layer as pristine (`pristine_delta.text_not_pristine`).
- A delta that no longer matches while no file is at a hash this patcher staged is stale (the data
  was cleared and a newer version downloaded): the run builds as a first install, under the text
  signal, and its delta replaces the stale one. The Windows patcher does the same.
- After an in-game update (2026-10-18), a package the update changed is accepted as the new pristine
  when `pristine_delta.accept_replaced` finds none of its files at the staged bytes and none of the
  delta's recorded assets still translated in `snapshot/packages`. `_restore_pristine` returns those
  files as `replaced`: they are left out of the pristine copy and its `sha256`, so the build reads them
  from the snapshot. `build_snapshot` then requires the text signal, and `PristineDelta.describe` logs
  the count. The session delta is made with `fingerprint=True`. Same rule as the Windows patcher.
- `build_snapshot` writes the staged install's delta to the session (`pristine-delta.bin`).
  `promoteSessionDelta` makes the newest completed session's delta the patcher's own, right after the
  run completes and again at the next run's start (for a run whose last step recovery finished); a
  delta older than the newest completed session is discarded, never promoted. An interrupted run is
  rolled back to `snapshot/`, which the old delta still describes.
- **Remove translation** (ticket 06): a Language-card button below the two choices, shown while a
  delta is kept and locked with them while work runs, runs the
  automatic flow with `removing` set; after preparation it shows the patch confirmation in its remove
  form (a plain panel dialog, `PanelDialog`, with its consent checkbox) and sends the worker `remove`. `PatchCoordinator.run(remove = true)` swaps the estimate and
  build for `removal_bytes` (reserved) and `build_removal`, which moves the rebuilt pristine files into
  `out/` with an empty session delta; the write-back, its `snapshot/` rollback and the delta promotion
  are the patch run's. Promoting an empty delta deletes the kept one (`keep_delta`), so the next patch
  run is a first install and the button hides. The result reads "Translation removed" with the Scan to login and store note.
  `RemovalRollbackProbeTest` cuts a write-back off after its first file and checks the rollback
  restores the translated bytes, then checks a complete one leaves every file pristine (passes on a
  phone).
- The Language card says no clear is needed while a delta is kept, and otherwise to clear on a phone
  another patcher translated (both UI languages).
- Not done: a layer patched before this shipped has no delta and no snapshot left to build one from
  (`releaseSession` deleted it), so its first repatch still needs a clear. `PristineDeltaProbeTest`
  covers rebuild, the build-input layer and the refusals on fixture files and passes on a phone (lab notebook, "The pristine delta shipped"),
  and no switch has run on a phone (ticket 08).

### The phased plan and its stop conditions

The port was planned in five phases, each with an exit condition that had to hold before the next
began. Phase 0 captured a reproducible, version-matched desktop control (commit, game and APK versions
and SHA-256s, catalog and runtime hashes, the DLL-free offline run with the APK and no builder, and
`check_graphics.py` with its `--game` form), with no Android writes; its run recorded 391 staged text
tables, 395 applied textures and one known prime table refusal, numbers that depend on the data
version. Phase 1 proved the Shizuku boundary: its exit was Shizuku controlling the existing access and
restore chain on the target phone, and the plan's stop rule was to **stop the full-port path if `run-as`
or the restore cannot be made reliable, and not to infer a workaround from shell UID alone**. Phase 2
proved the engine and codecs offline: its exit was the full offline pipeline working on the phone with
both data layers and no Windows binaries, and a text-only spike could diagnose progress but was not the
Android deliverable. Phase 3 built the durable workflow: its exit was complete scratch-data runs, with
deliberate failure injection recovering safely, before any live translation write. Phase 4 was device
acceptance and release, behind the release gate (the acceptance audit, lab notebook, 2026-10-05): a user installs the patcher, starts
Shizuku on the phone, completes the supported patch flow and launches the verified non-debuggable game
without a PC or cable; translation on both layers matches the version-matched control; and an
interrupted run has a usable recovery path.

The implementation brief set four standing limits that still apply: keep `AGENTS.md`'s restrictions,
the immutable catalog and runtime, Python 3.12, the game signing key, an empty `REBUILD_PACKAGES` and an
empty `cycle_assets`; prove Shizuku `run-as`, install and restore and Android codec loading before
building out the UI; run no destructive first-install or live game cycle without explicit authorization
for that cycle; and claim no PC-free or full-pipeline support before the release gate passes.

## [S3] Out of Scope

- Root-only access as the required path; Android <=10 PC-free setup; split APK or secondary-profile support in v1.
- A complete Kotlin rewrite of the translation engine, cloud translation/building or prepatched game APK distribution.
- Removing signature conversion, fixing direct WeChat/QQ authentication, changing Tencent's updater or expanding translation coverage.
- Assuming Shizuku makes the game data publicly readable, or treating `/sdcard/Android/data` logs as the private Qts package store.
- Windows builder emulation, generic package-key derivation, or enabling previously withdrawn extra-text assets.
