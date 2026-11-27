# Research: the Flutter app on the Rust core

Researched 2026-11-27 for the whole-repo migration's Flutter wave (rust/DECISIONS.md ADR-009, 015, 016,
018, 019). Each claim names its source: a URL, or `file:line` in this repo. Claims marked **unverified**
had no primary source that settled them and need a measurement before anyone relies on them.

## 1. flutter_rust_bridge v2

### Version

- The latest stable release is **2.13.0**, and **2.14.0-beta.2** is a prerelease
  (https://pub.dev/packages/flutter_rust_bridge, read 2026-11-27). Pin the Dart package, the Rust crate
  and `flutter_rust_bridge_codegen` to the same version (see trap T1).
- The current Flutter stable release is **3.50.0** (https://docs.flutter.dev/release/release-notes, page
  updated 2026-11-23).

### Integration backends: Cargokit and Native Assets

- FRB has two integration backends. **Cargokit** is the default for `flutter_rust_bridge_codegen
  create/integrate`. **Native Assets** is selected with `--integration-backend native-assets`, and FRB
  suggests it for new projects that can require a recent SDK
  (https://cjycode.com/flutter_rust_bridge/manual/integrate/cargokit).
- Cargokit's source "has to be copied into the target repository"
  (https://cjycode.com/flutter_rust_bridge/manual/integrate/builtin). Upstream irondash/cargokit is
  archived, and FRB maintains a fork (https://cjycode.com/flutter_rust_bridge/manual/integrate/cargokit).
- Native Assets needs codegen `>= 2.13.0-beta.2`. Its generated `hook/build.dart` uses
  `flutter_rust_bridge_hooks`, which wraps `native_toolchain_rust`. The backend needs `crate-type =
  ["staticlib", "cdylib"]` and a `rust-toolchain.toml` that pins a concrete toolchain and lists its targets
  (https://cjycode.com/flutter_rust_bridge/manual/integrate/native-assets).
- Build hooks arrived in Dart 3.10. Hooks run in a "semi-hermetic environment" that strips every
  environment variable not on an allow list. The NDK is found through `ANDROID_HOME` / `ANDROID_NDK*`
  (https://dart.dev/tools/hooks).
- The FRB page names no Android NDK or Windows specifics for Native Assets. Whether it honours a pinned NDK
  (28.2.13676358) and arm64-only output is **unverified**, so Cargokit is the measured path below.

### Cargokit on Android

From Cargokit's Gradle plugin (https://raw.githubusercontent.com/irondash/cargokit/main/gradle/plugin.gradle):

- **ABIs**: taken from Flutter's target platforms
  (`FlutterPluginUtils.getTargetPlatforms(project)`). **Debug builds always add `android-x86` and
  `android-x64`.** Release builds therefore need `flutter build apk --release --target-platform
  android-arm64`.
- **NDK**: `ndkVersion = plugin.project.android.ndkVersion`, exported as `CARGOKIT_NDK_VERSION`. The build
  fails when it is unset. This is the **plugin's** Android project (the generated `rust_builder` package),
  not the app module.
- **minSdk / compileSdk**: read from the plugin project and passed as `CARGOKIT_MIN_SDK_VERSION` /
  `CARGOKIT_COMPILE_SDK_VERSION`.
- The build tool "installs NDK if needed, configures the Rust environment for cross compilation" and "acts a
  linker driver" (https://github.com/irondash/cargokit/blob/main/docs/architecture.md).
- `cargokit.yaml` sets the toolchain and `extra_flags` for debug and release, plus precompiled binaries
  (`url_prefix`, `public_key`). The consuming app's `cargokit_options.yaml` sets `use_precompiled_binaries`
  and `verbose_logging` (same source).

### 16 KiB page alignment (ADR-002, rust/DECISIONS.md:22-23)

- "NDK version r28 and higher compile 16 KB-aligned by default." With NDK r27 or lower, use
  `-Wl,-z,max-page-size=16384 -Wl,-z,common-page-size=16384`
  (https://developer.android.com/guide/practices/page-sizes).
- Uncompressed `.so` files must be 16 KB zip-aligned, which needs AGP 8.5.1 or higher (same source).
- **Checks**: `llvm-objdump -p x.so | Select-String LOAD` must show `align 2**14`, and `zipalign -c -P 16
  -v 4 app.apk` must pass. RELRO's end must be 16 KB-aligned too (same source).
- Today's CMake build sets the flags explicitly (`android/app/src/main/cpp/CMakeLists.txt:9`).
- Rust links through the NDK's clang (Cargokit "acts a linker driver"), so r28's default should apply.
  Set the flag explicitly anyway in `rust/.cargo/config.toml`:
  ```toml
  [target.aarch64-linux-android]
  rustflags = ["-C", "link-arg=-Wl,-z,max-page-size=16384", "-C", "link-arg=-Wl,-z,common-page-size=16384"]
  ```
  Then gate the release on the two checks above. Whether Flutter's own `libflutter.so` is 16 KB-aligned on
  3.50 is **unverified**: blog posts disagree and no docs.flutter.dev page says. The zipalign and objdump
  gate covers it.

### Cargokit on Windows (MSVC)

- Cargokit's `build-cmake` command, called from `cargokit.cmake`, builds the crate "into a dynamic library
  on Linux and Windows" (https://github.com/irondash/cargokit/blob/main/docs/architecture.md). The DLL
  ships beside the runner exe.
- The Rust target is `x86_64-pc-windows-msvc`. Flutter's Windows build already needs the Visual Studio C++
  workload.
- Consider `-C target-feature=+crt-static` for the Rust DLL. The Flutter runner itself still needs the VC++
  runtime (§4).

### Long-running calls, streams, cancel, logs, errors

- **Off the UI thread by default.** Generated Dart functions are asynchronous by default. A plain Rust `fn`
  becomes a Dart `Future` and runs on FRB's thread pool
  (https://cjycode.com/flutter_rust_bridge/guides/concurrency). The pool can be resized or replaced through
  a custom `Handler`, or any `BaseThreadPool` (`execute` only)
  (https://cjycode.com/flutter_rust_bridge/guides/concurrency/sync-rust).
- **Never use `#[frb(sync)]` for pipeline work.** Sync-Dart functions run on the caller's (UI) thread (same
  source).
- **Streams**: `fn run(sink: StreamSink<Progress>, ..) -> Result<()>` becomes `Stream<Progress>` in Dart.
  The stream is usable at once, and Rust is not awaited unless the function has `#[frb(stream_dart_await)]`.
  The sink may be kept and used after the function returns. Errors are sent with `sink.add_error(anyhow!(..))`
  and arrive in Dart as an exception
  (https://cjycode.com/flutter_rust_bridge/guides/types/translatable/stream). That page does not say what
  happens when Dart cancels the subscription, so design cancellation separately.
- **Cancel**: FRB ships no cancel API. It points to a copied `CancelToken` (PR #333), `tokio_util`'s
  `CancellationToken`, or any token crate (https://cjycode.com/flutter_rust_bridge/guides/how-to/cancel).
  For this repo, pass an opaque `JobHandle` that holds an `AtomicBool` checked at the pipeline's safe
  points. That matches today's *Stop safely*, which happens only at checkpoints (DESIGN.md "Task status").
- **Logs**: add `flutter_rust_bridge::enable_frb_rust_to_dart_logging!();` and use the `log` crate. Replace
  `setup_default_user_utils()` with `setup_backtrace()`, because `log` allows only one global logger. The
  default level is Info (https://cjycode.com/flutter_rust_bridge/guides/how-to/logging). The activity log
  the user sees (Save log for help) should be its own typed stream, not the `log` bridge.
- **Errors**: Rust errors reach Dart as Dart errors
  (https://cjycode.com/flutter_rust_bridge/guides/how-to/report-error). `anyhow::Result` and panics become
  Dart exceptions, and panics carry Rust stack traces. That comes from a third-party docs mirror and FRB
  changelog entries (https://trdthg.github.io/flutter_rust_bridge/feature/lang_exceptions.html,
  https://pub.dev/packages/flutter_rust_bridge/versions/2.0.0-dev.18/changelog) and is **unverified** on the
  official site for v2.
- **Error mapping for this repo**: return `Result<T, PatchFailure>`, where `PatchFailure` is a plain enum or
  struct carrying a `strings.json` key and its placeholder values. That mirrors `PatchError(key, ..)`
  (AGENTS.md, "User-facing failures raise `PatchError`; ... takes keys from `resources/ui/strings.json`,
  never text"). Dart then shows `l10n.lookup(key, values)`. Never send English text across the bridge.

### A Cargo workspace with a shared core crate (ADR-012)

- To use FRB in a workspace, create the project with `--rust-crate-dir ../my_flutter_bridge`, or run
  `integrate --rust-crate-dir ..`. Delete the bridge crate's own `Cargo.lock`, add the crate to the root's
  `members`, and customise library loading if FRB cannot find the output directory (issue #2460)
  (https://cjycode.com/flutter_rust_bridge/guides/how-to/cargo-workspaces).
- `flutter_rust_bridge.yaml` holds `rust_root` (the crate directory), `rust_input` (for example
  `crate::api,another-third-party-crate`), `dart_output`, `c_output`, `dart_entrypoint_class_name` and
  `stop_on_error` (https://cjycode.com/flutter_rust_bridge/guides/custom/codegen/full-list).
- Keep a thin `hokace-bridge` crate whose `crate::api` alone faces Dart. It depends on `hokace-core`, so the
  core never depends on FRB, and the Android wheels and PyO3 modules of ADR-019 stay buildable from the
  same core.

## 2. The current Android app: what is native, and where it goes

Measured with `wc -l` over `android/app/src/main/java/dev/halixm/hokacepatcher/*.kt`: **12,873 Kotlin
lines in 72 files**, plus 32 AIDL lines and 87 C++/CMake lines (the full listing totals 12,992). The
manifest is `android/app/src/main/AndroidManifest.xml`.

| Area | Files (Kotlin lines) | Native Android API used | Verdict |
|---|---|---|---|
| **Shizuku, worker start, Binder service** | ShizukuWorkerStarter 119, ShizukuLauncher 34, ShellServiceStarter 89, WorkerBinderProvider 48, WorkerDeviceConnection 214, RootWorkerStarter 68, ShellProvider 65, PrivilegedDeviceService 641, FirstSetupDeviceTransport 32, NormalRunAsProbe 25: **1,335**; AIDL 32 | `Shizuku.UserServiceArgs`/`bindUserService` (MainActivity.kt:104,745; ShizukuWorkerStarter.kt:61); `ShizukuRemoteProcess` (ShizukuWorkerStarter.kt:11); `ShizukuProvider` and `WorkerBinderProvider` (AndroidManifest.xml:34-41); `app_process` with this APK as class path (WorkerDeviceConnection.kt:131-137); AIDL with `ParcelFileDescriptor` (IPrivilegedDeviceService.aidl:5-31) | **Stays Kotlin** (ADR-016). Shizuku's API is a Java/JNI and Binder library. A user service is a class extending the AIDL `Stub`, and `destroy` must be transaction `16777114` (https://raw.githubusercontent.com/RikkaApps/Shizuku-API/master/README.md). The shell-script bodies inside `PrivilegedDeviceService` (`run-as`, `pm install-*`, `tar`; PrivilegedDeviceService.kt:55,257,265,366,442) could later become a Rust executable, but that changes the worker protocol; keep it out of the Flutter wave. |
| **Package installer, APK identity** | RecoveryInstaller 60, RecoveryApkProvider 51, InstalledGameVerifier 108, InstallerFailure 26, ApkIdentity 94, GameSigner 40, RecoveryStore 65, EmergencyRestoreStore 93: **537** | The emergency installer is `ACTION_VIEW` on a `FileProvider`-style content URI, behind `canRequestPackageInstalls` and `ACTION_MANAGE_UNKNOWN_APP_SOURCES` (RecoveryInstaller.kt:45-53; AndroidManifest.xml:32-33). Game installs go through `pm install-create/-write` in the worker (PrivilegedDeviceService.kt:257-265). | **Kotlin**: the intent, the provider and the permission check (~110 lines). **Rust**: ApkIdentity, GameSigner (RSA; ADR-017 already moves re-signing to the core), InstallerFailure's code table, RecoveryStore and EmergencyRestoreStore (pure files and JSON). |
| **Wireless debugging** | AdbClient 123, AdbKey 185, AdbMdns 117, AdbPairing 172, AdbProtocol 76, WirelessDebugging 203: **876**; cpp 87 | Conscrypt TLS and `Conscrypt.exportKeyingMaterial` (AdbPairing.kt:55-61; AdbClient.kt:50); BoringSSL SPAKE2 over JNI (adb_pairing.cpp; AdbPairing.kt:152-154); `NsdManager` mDNS (AdbMdns.kt:30); a pairing notification with `RemoteInput` (WirelessDebugging.kt:80-87,138) | **Rust**: AdbProtocol, AdbClient, AdbKey, AdbPairing's HKDF/AES-GCM, and TLS with rustls (`ConnectionCommon::export_keying_material`, https://docs.rs/rustls/latest/rustls/struct.ConnectionCommon.html#method.export_keying_material). **SPAKE2 is the open risk** in ADR-016: RustCrypto `spake2` is documented as compatible with python-spake2, not BoringSSL (https://docs.rs/crate/spake2/latest). ADB uses BoringSSL's variant (https://android.googlesource.com/platform/packages/modules/adb/+/a9b3987d/pairing_auth/pairing_auth.cpp), and other ports re-implement that variant (https://github.com/flyfish233/spake2-java). Port BoringSSL's `spake25519.c` to Rust on `curve25519-dalek` and test it against a real `adbd`. **Kotlin**: the notification with RemoteInput and its receiver (~60 lines), and `NsdManager` (117 lines). Rust mDNS would need a Wi-Fi `MulticastLock` from Kotlin anyway. |
| **Foreground service, notifications, shortcuts** | PatchWorkerService 381, RunNotification 78, LauncherShortcuts 49: **508** | A `dataSync` foreground service (AndroidManifest.xml:6,27-28; PatchWorkerService.kt:134,150), `onTimeout` (PatchWorkerService.kt:357), `POST_NOTIFICATIONS` (RunNotification.kt:53,74), dynamic shortcuts and `.ShortcutEntry` (AndroidManifest.xml:23-24) | **Stays Kotlin**, shrunk to the service lifecycle (~150 lines): start/stop, notification updates fed from Rust progress, `onTimeout`, and cancel. The work itself becomes a Rust thread. The 6-hour `dataSync` limit for targetSdk 35 applies (https://developer.android.com/develop/background-work/services/fgs/timeout), and the existing `onTimeout` handling must survive. |
| **Storage access** | (inside MainActivity and the stores) | `filesDir` throughout (ApkPreparation.kt:47-264); `ACTION_CREATE_DOCUMENT` for the log export (MainActivity.kt:301-303,714-720); `StatFs` budget (StorageBudget.kt) | **Rust** for every file under `filesDir`; Kotlin passes the path once at start. **Kotlin** (~20 lines) or the `file_selector`/`file_picker` plugin for the SAF document (the URI's stream needs a `ContentResolver`). Free space can be read in Rust with `statvfs`. |
| **UI** | MainActivity 827, GuidedHome 796, MainActivityDialogs 181, PanelDialog 102, StopCard 88, StepPicture 38, UiText 147, UiTaskRunner 31, AppUpdatePrompt 61: **2,271** | Views, `AlertDialog`, Activity results, `getLaunchIntentForPackage` (MainActivity.kt:223,674) | **Dart/Flutter** (ADR-009). Open game, Shizuku's Play listing (ShizukuLauncher.kt:25-26) and the update URL become small intents in the plugin or `url_launcher`. |
| **Logic and state** (journals, stores, coordinator, policies, receipts, delta, routing, update check) | 36 files: **7,346** (PatchCoordinator 1,534, RunStore 602, ApkPreparation 504, SessionJournal 395, AutomaticFlow 392, ArtifactReceipts 359, DiagnosticLogExport 323, GameFileTransaction 315, …) | `AtomicFile`, `org.json`, `java.nio` and `SharedPreferences` (`ShellProvider.kt:30-38`); Chaquopy calls (ApkPreparation.kt:386-392,445) | **Rust**. These are file formats and decisions, not platform calls. The on-disk formats (`sessions/`, `runs/`, `recovery/`, `preparations/`, shell-provider and worker-starter preferences) must be read unchanged, so a phone that upgrades in place keeps its saved work (trap T6). |

**Rough end state:** about 1,700 to 1,900 Kotlin lines stay. That is the Shizuku and worker block
(1,335), the service lifecycle (~150), the installer intent and provider (~110), mDNS and the pairing
notification (~180), and the SAF export. Everything else (~11,000 lines) moves to Rust or Dart.

**Rust ↔ Kotlin direction.** The pipeline calls the worker (snapshot, write a game file, reinstall) in the
middle of a run. If those calls went through Dart (FRB callback, then a platform channel, then Kotlin),
the run would depend on a live Flutter isolate. Call Kotlin from Rust through JNI instead (`jni` crate),
and pass file descriptors as the AIDL already does. The process-wide context is needed for that:
`JNI_OnLoad` with `ndk-context`, or a plugin method that hands Rust the application context. Without it,
Rust panics with "android context was not initialized" when the Dart VM loads the library
(https://cjycode.com/flutter_rust_bridge/guides/how-to/ndk-init).

## 3. Same applicationId and signing key

Today:

- `applicationId = "dev.halixm.hokacepatcher"`, `minSdk = 29`, `targetSdk = 35`, `ndkVersion =
  "28.2.13676358"` and `abiFilters += "arm64-v8a"` (android/app/build.gradle.kts:153-165).
- The `privateRelease` signing config reads `ANDROID_RELEASE_KEYSTORE`, `_STORE_PASSWORD`, `_KEY_ALIAS` and
  `_KEY_PASSWORD` and signs debug and release alike (build.gradle.kts:166-178).
- `tools/ci/sign_android.ps1` then re-signs with apksigner 35.0.0 using `--lineage
  android/signing/patcher.lineage --rotation-min-sdk-version 28 --alignment-preserved true` and **v3 only**
  (v1, v2 and v4 off) (sign_android.ps1:7,17-26).

For the Flutter app's `android/app/build.gradle.kts`:

1. Keep `namespace` and `applicationId` as `dev.halixm.hokacepatcher`. Keep the activity as
   `dev.halixm.hokacepatcher.MainActivity`, which now extends `FlutterActivity`. Flutter warns that a
   changed `applicationId`/`namespace` means moving `MainActivity` to the matching package
   (https://docs.flutter.dev/deployment/android). Keep `.ShortcutEntry`, the two providers and their
   authorities, `allowBackup="false"`, the `<queries>` and every permission (AndroidManifest.xml:1-43).
   Pinned shortcuts and Shizuku's authorisation are tied to these.
2. Replace Flutter's `flutter.minSdkVersion`/`flutter.ndkVersion` defaults ("Any value starting with
   'flutter.' gets its value from the Flutter Gradle plugin", same source) with fixed values: `minSdk = 29`,
   `ndkVersion = "28.2.13676358"`, `targetSdk = 35`. Set the same `ndkVersion` in the `rust_builder`
   plugin's Gradle file, because Cargokit reads the plugin project's value (§1).
3. **versionCode** must be greater than or equal to the installed app's version for an in-place upgrade.
   Flutter takes `versionCode` from `pubspec.yaml`'s `version: x+N` or `--build-number`, and
   `--split-per-abi` adds `ABI_VERSION * 1000` (https://docs.flutter.dev/deployment/android). Pass
   `--build-number` from the same source CI uses for `patchVersionCode` today (build.gradle.kts:161), and
   build with `--target-platform android-arm64` rather than `--split-per-abi`.
4. **Signing**: Flutter's documented pattern is a `signingConfigs.create("release")` that reads
   `key.properties` (same source). Keep the environment-variable version instead
   (build.gradle.kts:168-178), so no `key.properties` file exists to leak. AGP cannot apply a rotation
   lineage, so keep `sign_android.ps1` as the post-build step. apksigner's `--lineage` and
   `--rotation-min-sdk-version 28` put the rotated key in the v3 block rather than v3.1 (API 33+), and "If
   you sign your APK using apksigner and make further changes to the APK, the APK's signature is
   invalidated" (https://developer.android.com/tools/apksigner). Run it on the output of `flutter build
   apk`, then check with `apksigner verify --print-certs -v`.
5. **R8 is always on** for Flutter release builds: "The `--[no-]shrink` flag has no effect. Code shrinking
   is always enabled in release builds" (https://docs.flutter.dev/deployment/android). Today's app does not
   minify (no `isMinifyEnabled` in build.gradle.kts). `ShellServiceStarter` is started by name through
   `app_process` (WorkerDeviceConnection.kt:131-137), Shizuku resolves `PrivilegedDeviceService` by class,
   and the AIDL `Stub` is used over Binder. These need `-keep` rules in `proguard-rules.pro`, or the worker
   fails only in release builds (trap T3).

## 4. Windows

- **No single exe.** Flutter documents three ways to distribute: MSIX, a zip of the build folder, or an
  installer such as Inno Setup or WiX. The folder holds the exe, every `.dll` (`flutter_windows.dll`, the
  Rust DLL, plugins), the `data\` directory (`app.so`, `icudtl.dat`), and the VC++ runtime (or
  `msvcp140.dll`, `vcruntime140.dll` and `vcruntime140_1.dll` copied application-local)
  (https://docs.flutter.dev/platform-integration/windows/building). That page gives the output folder as
  `build\windows\runner\<mode>\`; current tools write `build\windows\x64\runner\Release`, so check the path
  in CI.
- **MSIX**: use the `msix` pub package. A self-hosted MSIX needs a certificate signed by a CA that Windows
  trusts; the Store signs for you (same source). For a GitHub-released community tool, that is a cost that
  today's PyInstaller one-file exe (app/build_exe.py:73) does not have.
- **What replaces PyInstaller's one-file exe**: a zipped portable folder (`HOK ACE Language Patcher\` with
  the exe inside), optionally with an Inno Setup installer. A self-extracting wrapper would reproduce
  PyInstaller's extract-to-temp behaviour and its antivirus false positives, so it is not recommended.
- **Headless modes and the PC job child.** `--selftest`, `--smoketest`, `--pc-selftest` and the `--pc-job`
  child (AGENTS.md "Jobs run in the `--pc-job` child") cannot stay flags of the Flutter runner, which is a
  GUI-subsystem exe. Ship a Rust `hokace-cli.exe` beside it for those modes. The GUI's core spawns
  `hokace-cli --pc-job`, reads its progress lines and forwards them through a `StreamSink`. That keeps the
  child-process isolation that makes the engine's commit recoverable.
- **Long jobs without blocking.** Use FRB's async calls, which run on FRB's thread pool, with a Rust thread
  or child process per job and a `StreamSink` for progress (§1). **Dart isolates are not needed**: an
  isolate (https://dart.dev/language/isolates) only helps CPU-heavy Dart, and all the heavy work is Rust.
  Keep the job's state in the Rust core (a job registry keyed by id), not in the isolate. A Dart hot restart
  (debug) or a recreated Android Activity then re-subscribes to a running job rather than losing it.

## 5. Theme and strings from resources/ui (ADR-018)

### Inputs

- `resources/ui/theme.json`: `colors` (29 hex tokens, no `rgba` today), `typography` (six roles with
  `fontFamily`, `fontWeight`, `fontSize` in px and an optional `letterSpacing` in em), `rounded` (3) and
  `spacing` (7) (resources/ui/theme.json:1-79). Today Gradle turns these into Android resources
  (android/app/build.gradle.kts:99-151), and the Windows patcher reads them directly (DESIGN.md:259-260).
- `resources/ui/strings.json`: `{version, languages: [en, id], about, strings: {key: {platforms, en, id,
  draft?}}}`. Measured 2026-11-27: 495 keys (274 Android-only, 173 Windows-only, 48 both), 286 marked
  `draft`, 49 with `{name}` placeholders (32 distinct names), 22 with `\n`, 32 with an apostrophe, and 3
  English texts that repeat.
- `resources/fonts/`: Barlow Regular/Medium/SemiBold/Bold, BarlowCondensed ExtraBold, Commissioner Regular
  and SemiBold, FragmentMono Regular, AceHeading Bold, and four OFL licence files. The Android wordmark is
  a PNG drawn from `honor-of-kings-ace-title.otf` (DESIGN.md:179).

### Generator

Write one generator (a `rust/crates/hokace-gen-ui` bin, or a Python script under `tools/` until the
lift). It runs before `flutter build` and in CI's checks job, and writes:

1. **`lib/src/generated/tokens.g.dart`** with:
   - `abstract final class AceColors { static const pageTop = Color(0xFF3F459A); ... }` (token
     `page-top` becomes lowerCamel `pageTop`);
   - `AceRadius`, `AceSpace` (double constants);
   - `AceType` (`TextStyle` per role: `fontFamily`, `FontWeight.w800` from `"800"`, `fontSize`);
   - a `ThemeData aceTheme()` that builds a `ColorScheme` (primary from `panel-bottom`, surface from
     `surface`, error from `error`, and so on) and a `TextTheme` from those styles.
   - **Convert units**: `letterSpacing` in em becomes logical px (`0.025em × 12 = 0.3`), because Flutter's
     `TextStyle.letterSpacing` is in logical pixels. Px values become logical px on both platforms.
     DESIGN.md:181 asks to "Follow Android font settings and Windows display scaling", which Flutter's
     `TextScaler` does on Android.
2. **pubspec `fonts:`** entries per family, with `weight:` 400/500/600/700/800 matching the files. The
   generator copies `resources/fonts/*.ttf` and the licences into `flutter/assets/fonts/` (generated and
   git-ignored) and registers the licences through `LicenseRegistry`. Whether pubspec may reference
   `../resources/fonts` directly is **unverified**; copying avoids the question.
3. **Localisation.** Choose one of two routes.
   - **(a) gen-l10n with ARB.** `l10n.yaml` takes `arb-dir`, `template-arb-file`,
     `output-localization-file`, and `output-dir` with `synthetic-package: false`. Placeholders are
     declared in `@key.placeholders`, and simple messages need no metadata. `use-escaping: true` makes `'`
     an escape character. Getter names come from the keys
     (https://docs.flutter.dev/ui/internationalization). Hazards measured in strings.json: **11 keys start
     with a digit** (`01_your_translation`, `02_*`, `03_*`) and one key is the Dart keyword **`continue`**.
     Both are invalid getter names, so the generator must rename them, for example to lowerCamel with a
     prefix (`s01YourTranslation`, `continueAction`). ICU syntax also makes `{`, `}`, `'` and plural
     forms significant. Leave `use-escaping` off so the 32 apostrophes stay literal.
   - **(b) Recommended: a generated Dart table.** Write `strings.g.dart` with a `const Map<String,
     Map<String, String>>` filtered to the build's platform, plus a typed accessor per key with named
     placeholder parameters (`String freedAmounts({required String freed, required String free})`). Add a
     runtime `lookup(key, values)` for keys that arrive from Rust errors. This keeps `strings.json`'s
     keys, its `{name}` syntax and the `PatchError(key, ..)` model exactly, and has no ICU escaping. It
     also lets `check_ui_strings.py` stay the single gate after it learns to scan `*.dart` call sites, as
     it scans `*.kt` and the Windows `.py` files today (tools/research/check_ui_strings.py:35-63,127-162).
   - **Either way**, the interface language follows the **selected translation**, not the device locale
     (DESIGN.md "The selected translation sets the interface language"). Set `MaterialApp.locale` from app
     state, list `supportedLocales: [en, id]`, and include `GlobalMaterialLocalizations` so built-in
     widgets follow. The `draft` flag stays data; it is not shown.
   - **Do not port Android's English-text lookup.** `UiText.translate` (UiText.kt:28-31) finds a key by its
     English text. Dart should look strings up by key only.

## Traps

- **T1 FRB versions**: keep the Dart `flutter_rust_bridge`, the Rust crate and the codegen at one pinned
  version (2.13.0) and regenerate after every bump. This is FRB's usual practice; no single docs page
  states it.
- **T2 Cargokit debug ABIs**: debug builds add `android-x86`/`android-x64` (plugin.gradle). Either install
  those rustup targets or always pass `--target-platform android-arm64`. The NDK version is read from
  `rust_builder`'s Gradle project, not the app's.
- **T3 R8**: Flutter release builds always shrink. Add keep rules for the `app_process` entry point, the
  Shizuku user service, the AIDL stubs and the providers (§3.5).
- **T4 v3-only signing**: `sign_android.ps1:19` says "minSdk is 30", but the app's `minSdk` is 29
  (build.gradle.kts:159). v3 needs API 28 or higher, so v3-only signing still covers 29, but the comment is
  wrong. Do not let Flutter's default `minSdk` (`flutter.minSdkVersion`) drop below 28, or devices below
  API 28 will refuse a v3-only APK.
- **T5 Upgrade in place**: the applicationId, the lineage-signed key, a versionCode at least the
  installed one, `MainActivity`'s component name and the provider authorities must all match.
  `--split-per-abi` silently adds 2000 to the versionCode for arm64.
- **T6 Saved state**: a phone can upgrade mid-recovery. The Rust core must read every record the Kotlin
  app wrote under `filesDir` (RunStore, SessionJournal, FirstSetupJournal, RecoveryStore, the pristine
  delta, receipts) and its SharedPreferences keys (`shell-provider/provider`, `worker-starter`). Record
  fixtures from the Kotlin app before the lift. `tools/research/fixtures/run_artifacts` is already shared
  test data (build.gradle.kts:189).
- **T7 Worker process**: the `app_process` worker runs this APK's dex as uid 2000 or 0, with no Context
  (ShellServiceStarter.kt:12-22). It must not touch Flutter or FRB classes. If it ever loads the Rust
  library, the `.so` sits uncompressed inside the APK (AGP 8.5.1 and later) rather than in an extracted
  `lib/` folder.
- **T8 Shizuku `newProcess`**: the app uses `ShizukuRemoteProcess` as the fallback starter
  (ShizukuWorkerStarter.kt:11,75-78). Shizuku 13.1.1 announced `newProcess` is being prepared for removal
  (Shizuku-API README). Track it; do not widen its use in the plugin.
- **T9 SPAKE2**: no off-the-shelf Rust crate is documented as interoperating with BoringSSL's SPAKE2 (§2).
  Until a Rust port passes a real-device pairing, keep `adb_pairing.cpp` (73 lines) as the fallback. ADR-005
  ("No C or C++ is bound") then needs a recorded exception, or the pairing waits.
- **T10 Rust → Kotlin calls** need the JVM and Context initialised for Rust (`ndk-context`), because the
  Dart VM loads the library without running Android's usual path (FRB ndk-init page).
- **T11 FGS timeout**: `dataSync` gets 6 hours per 24 hours at targetSdk 35. `onTimeout` must call
  `stopSelf` within seconds, and a Rust job must save its checkpoint when the plugin signals it.
- **T12 Windows output path and runtime**: ship the VC++ runtime DLLs or require the redistributable. The
  documented output path differs from the current tool's (§4).
- **T13 l10n names**: 11 digit-leading keys and `continue` break gen-l10n getters (§5).
- **T14 16 KB**: check `libflutter.so` and the Rust `.so` with `zipalign -c -P 16` and `llvm-objdump` on
  every release; do not assume.
- **T15 No large byte arrays over the bridge**: pass paths, as the AIDL passes descriptors
  (IPrivilegedDeviceService.aidl:5). FRB copies `Vec<u8>` across.

## Recommended layout

```
rust/                              Cargo workspace (ADR-012)
  Cargo.toml                       [workspace] members = ["crates/*", existing unit crates]
  rust-toolchain.toml              pinned toolchain; targets aarch64-linux-android, x86_64-pc-windows-msvc
  .cargo/config.toml               16 KiB link args (aarch64-linux-android); optional crt-static (msvc)
  crates/
    hokace-core/                   pipeline, runtime port, codecs, stores and journals (no FRB, no JNI)
    hokace-adb/                    ADB protocol, client, key, TLS (rustls), SPAKE2 port, pairing
    hokace-android/                JNI glue: calls into the Kotlin worker plugin; ndk-context init (cfg android)
    hokace-bridge/                 crate-type ["staticlib","cdylib"]; src/api/*.rs = the only Dart-facing API
    hokace-cli/                    --selftest, --smoketest, --pc-selftest, --pc-job child
    hokace-gen-ui/                 theme.json + strings.json -> Dart tokens, strings table, pubspec fonts
  research/flutter-app.md          this file
flutter/                           the one Flutter app (ADR-009)
  pubspec.yaml                     flutter_rust_bridge: 2.13.0 (pinned); fonts: (generated block)
  flutter_rust_bridge.yaml         rust_root: ../rust/crates/hokace-bridge; rust_input: crate::api;
                                   dart_output: lib/src/rust
  rust_builder/                    FRB/Cargokit plugin (cargokit/ copied in); android ndkVersion 28.2.13676358
  lib/
    main.dart
    src/rust/                      generated by flutter_rust_bridge_codegen
    src/generated/                 tokens.g.dart, strings.g.dart (from hokace-gen-ui; git-ignored)
    src/ui/                        screens: home, setup, status, activity, dialogs (per DESIGN.md)
    src/platform/                  Dart side of the Android plugin (Pigeon-generated API)
  assets/fonts/                    copied from resources/fonts (generated; git-ignored)
  packages/hokace_android/         local Flutter plugin, Kotlin (ADR-016)
    android/src/main/aidl/dev/halixm/hokacepatcher/IPrivilegedDeviceService.aidl
    android/src/main/kotlin/dev/halixm/hokacepatcher/
      shizuku/ worker/             ShizukuWorkerStarter, ShellServiceStarter, WorkerBinderProvider,
                                   WorkerDeviceConnection, RootWorkerStarter, PrivilegedDeviceService
      service/                     PatchWorkerService (lifecycle only), RunNotification, LauncherShortcuts
      install/                     RecoveryInstaller intent, RecoveryApkProvider
      wireless/                    NsdManager discovery, pairing notification and RemoteInput receiver
    pigeons/messages.dart          typed channel definitions
  android/app/
    build.gradle.kts               applicationId/namespace dev.halixm.hokacepatcher, minSdk 29, targetSdk 35,
                                   ndkVersion 28.2.13676358, abiFilters arm64-v8a, env-var signing
    proguard-rules.pro             keep worker, user service, AIDL, providers
    src/main/AndroidManifest.xml   carried over from android/app/src/main/AndroidManifest.xml
  windows/runner/                  Flutter runner; product name "HOK ACE Language Patcher"
tools/ci/sign_android.ps1          unchanged: v3 + lineage after flutter build
```

## Build steps

1. **Prerequisites**: Flutter 3.50 stable; Rust (pinned in `rust-toolchain.toml`) with
   `aarch64-linux-android` and `x86_64-pc-windows-msvc`; Android SDK with build-tools 35.0.0 and NDK
   28.2.13676358; Visual Studio C++ workload.
2. **Generate**: `cargo run -p hokace-gen-ui -- --theme resources/ui/theme.json --strings
   resources/ui/strings.json --fonts resources/fonts --out flutter`, then `flutter_rust_bridge_codegen
   generate` (from `flutter/`).
3. **Checks**: `tools/research/check_ui_strings.py`, extended to `flutter/lib/**/*.dart`; `cargo test
   --workspace`; `flutter analyze`; `flutter test`.
4. **Android**: `flutter build apk --release --target-platform android-arm64 --build-name <x.y.z.r>
   --build-number <code>`, then `tools/ci/sign_android.ps1 -Apk build/app/outputs/flutter-apk/app-release.apk`.
   Verify with `apksigner verify --print-certs -v`, `zipalign -c -P 16 -v 4`, and `llvm-objdump -p` on each
   `.so`. Then run a device cycle that installs over the Kotlin app and checks that saved work and the
   Shizuku permission survive (ADR-007, ADR-019).
5. **Windows**: `flutter build windows --release`, then `cargo build -p hokace-cli --release
   --target x86_64-pc-windows-msvc`. Copy `hokace-cli.exe` and the VC++ runtime DLLs into
   `build\windows\x64\runner\Release\`, run `hokace-cli --smoketest <dir>`, and zip the folder (optionally
   wrap it in Inno Setup).
