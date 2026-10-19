# HOK ACE Language Patcher

Repository: [halixm-dev/hok-ace-patch](https://github.com/halixm-dev/hok-ace-patch).

Install an English or Indonesian translation into 王者万象棋 (`com.tencent.tmgp.osgame`)
on an Android phone, without root.

| Patcher | Start here |
|---|---|
| Windows app, connected to the phone over USB | Follow the steps below |
| Android app, using Shizuku on the phone | [Android setup and build guide](android/README.md); development build with device acceptance still pending |

The translation includes catalog text tables, catalog edits, two Career-atlas labels
(MY SKINS and TOTAL PROFIT), and one Lua label. Some content stays Chinese. See the
[coverage ledger](docs/translation-progress.md) for measured counts and known gaps;
each run reports what it actually applied and skipped.

## Use the Windows app

1. Install the game and let its in-game download finish at the login screen, then close it.
2. Enable **USB debugging** in the phone's Developer options. Connect it to Windows by USB
   and tap **Allow** on the phone's debugging prompt.
3. Open `dist\HOK ACE Language Patcher.exe`, or [run from source](#run-or-build-from-source).
4. Choose **LANGUAGE** and a **WORKING FOLDER** with at least 8 GB free. Keep working data
   outside this repository; the default folder is `HOK ACE Patcher Data` beside the exe.
5. Click **Start Patch** and follow the installation prompts. Keep the game closed until
   the patch finishes and the normal APK is restored.
6. Open the game and use **Scan to login**. Direct WeChat/QQ login breaks when the APK is re-signed.

### Updates and language changes

To switch languages or apply a newer translation, run the patcher again; there is no need
to clear the game's data. After each install the patcher keeps a **pristine delta**, the original
bytes it overwrote (about 5 MB, in `pristine\` in the working folder, or in the Android app's own
storage). The next run rebuilds the untranslated files from it before building the new translation,
and the log says `rebuilt N files from the pristine delta`. Each patcher keeps its own delta, so
switch with the patcher that translated the phone last. The Windows patcher can also make a first
delta from a working folder that still holds the session of an earlier install.

To go back to the untranslated game, use **Remove Translation** (Windows, under Start Patch) or
**Remove translation** (Android, on the Language card, shown while the patcher keeps a delta). It writes
the original files back the same way an install writes a translation; nothing is downloaded and no
game data is deleted. The patcher-signed app stays installed, so keep using **Scan to login**; for the
official app, reinstall the game from the store.

After a game update, run the patcher again. When the update rewrote a translated file, the patcher
checks that package asset by asset: if none of its translation is left in it, it builds from the
update's files and keeps a new delta against them. A run that cannot rebuild the untranslated files
stops before it writes anything and tells you to clear the game's data: when an update left part of
the translation in a file it changed, when the delta was made by patcher 1.6.1.5 or older (it has
no asset record), or on a phone another patcher (or a patcher version from before deltas) translated. Then clear the game's data,
let it download again to the login screen, close it and patch. Clearing data removes local game data
and requires another login.

Use the APK and game data from the phone's current version. An older staged package can
stall loading and cause the game to repair away the translation.

## Patch versions

The root `VERSION` file sets the Windows and Android patcher version: **1.6.1.9**.
Use three numbers from the game's **data version**, omitting its extra middle zero,
then append the patch release number, starting at `1`. For example, game data
`1.0.6.1` becomes patch `1.6.1.X`; the currently measured data `1.6.0.1` also becomes
`1.6.1.X`. Increase `X` for each patch release; reset it to `1` when the data version changes.

| Change | Example version |
|---|---|
| First patch for data 1.6.0.1 | `1.6.1.1` |
| Next patch for the same data | `1.6.1.2` |
| First patch after a data update to 1.6.0.2 | `1.6.2.1` |

Edit `VERSION` before building a release; use the matching Android tag, such as
`android-v1.6.1.1`. This labels the patch's target data version; it does not check
the phone's data version. Android's numeric `versionCode` stays separate and must
increase across releases, including when the last patch number resets. CI uses its
increasing workflow run number; local builds can set `-PpatchVersionCode=<number>`.

## Run or build from source

### Automated Android builds

| Trigger | Result |
|---|---|
| Push to `master`, pull request, or **Actions → Android APK → Run workflow** | Full-codec development APK and check reports under the run's artifacts |
| Push a tag matching `VERSION`, such as `android-v1.6.1.1` | Release APK signed with the current patcher key and its rotation lineage, SHA-256, codec source companion and a draft GitHub release |

CI runs Android unit tests, lint, native ELF alignment, APK ZIP alignment and signer verification.
The release attaches only the APK, `SHA256SUMS` and the codec source companion; the native
alignment and runtime dependency reports stay in the run's artifacts.
Artifacts expire after 14 days; draft release attachments remain. Release drafts need review before
publication: device acceptance and redistribution checks in [Android dependency notices](android/native/THIRD_PARTY.md)
remain open. See [signing and security](SECURITY.md) before switching from a development APK.

### Windows build

Use **Python 3.12**: the compiled translation runtime cannot load on another Python version.
Run these commands from the repository root in Windows Command Prompt:

| Goal | Command | Result |
|---|---|---|
| Install dependencies | `setup.bat` | Creates `.venv` and installs `requirements.txt` |
| Run the Windows app | `run.bat` | Opens the GUI from source |
| Build the Windows exe | `build.bat` | Creates `dist\HOK ACE Language Patcher.exe` |

If `py -3.12` is unavailable, select your Python 3.12 executable before setup:

```bat
set PYTHON=C:\path\to\python3.12.exe
setup.bat
```

`build/`, `dist/` and `.venv/` are generated. Recreate them with the commands above as needed.
Keep any game data or recovery files stored beside the exe before deleting `dist/`.

## How installation works

The Windows app pulls the installed APK, changes its manifest and re-signs it. It temporarily
installs an **access APK** so it can read and write the game's data, stages the translation,
then reinstalls the **normal APK**. The normal APK stays installed; the access APK cannot run
the game safely. Launcher renaming is cosmetic: a failed rename leaves the name unchanged
and installation continues. See the [Windows patcher record](docs/features/standalone-patcher-app.md)
for installation and recovery details.

The game reads two data layers:

| Layer | Contents | Translation path |
|---|---|---|
| Prime layer | Packages inside the APK | Translatable prime-only assets are appended to the override layer |
| Override layer | Packages downloaded by the game | Existing assets are translated here, after the in-game update finishes |

A normal run uses append; `REBUILD_PACKAGES` stays empty. The APK supplies prime-only content.
Without it, an offline run still succeeds, but prime-only content stays Chinese. See
[prime-only append](docs/features/prime-only-append.md) for the mechanism and
[prime rebuild](docs/features/prime-rebuild.md) for the optional builder path.

## Verify changes

There is no general test suite. Choose the check that matches your change:

| Change | Check | Needs |
|---|---|---|
| Windows GUI or device workflow | `run.bat` | A phone for device operations |
| Documentation or paths | `.venv\Scripts\python.exe tools\research\check_references.py` | Repository only |
| Staging contract | `.venv\Scripts\python.exe tools\research\check_staging_contract.py` | Repository only |
| Texture processing | `.venv\Scripts\python.exe tools\research\check_graphics.py` | Shipped assets; add `--game <game-dir>` to check a dump |
| Indonesian texture edits | `.venv\Scripts\python.exe tools\research\make_language_payloads.py --check` | Shipped assets |
| Pristine delta | `.venv\Scripts\python.exe tools\research\check_pristine_delta.py` | Repository only; add `--game <pristine game-dir> --apk <apk> --work <dir>` for the round trip and language switches |
| Repatch without a clear (Windows) | `.venv\Scripts\python.exe tools\research\check_windows_repatch.py` | Repository only |
| A change requiring screen verification | [Device cycle](docs/runbooks/device-cycle.md) | Phone and matching game data |

Run both documentation checks after moving or renaming a doc. Offline checks verify file
processing; a device cycle verifies what the game displays.

### Stage a translation offline

Use a dumped game directory and matching APK. Keep work and output folders outside the repo:

```bat
.venv\Scripts\python.exe tools\build_device_patch.py --runtime resources\runtime --game <game-dir> ^
    --catalog resources\catalog --work <work-dir> --output <out-dir> ^
    --apk <path>\installed.apk
```

For Indonesian, use `--catalog resources\catalog_id`. Read `device_patch_summary.json` for
applied counts and skipped assets. The builder is needed only when `REBUILD_PACKAGES` names
a package; the normal append path does not need it.

### Check the frozen runtime

```bat
"dist\HOK ACE Language Patcher.exe" --selftest <game-dir> <out-dir>
```

Add `id` after `<out-dir>` for Indonesian. Check `<out-dir>\selftest.json` for `"ok": true`
and the adjacent `<out-dir>.log` for failures. This check runs without an APK, so it does
not exercise prime-only append.

## Find the right file

| Task | Read or edit |
|---|---|
| Change the Windows interface or workflow | `app/`; [Windows patcher record](docs/features/standalone-patcher-app.md) |
| Change staging or its result fields | `tools/build_device_patch.py`, including the `build_patch` contract docstring |
| Change texture processing or Career-atlas art | [Texture translation](docs/features/texture-translation.md); [Career-atlas art brief](tools/research/career_atlas/art_brief.md) |
| Change languages or regenerate language-specific catalog edits | [Indonesian language](docs/features/indonesian-language.md) |
| Investigate untranslated content | [Diagnose an untranslated string](docs/runbooks/diagnose-untranslated.md) |
| Investigate a game crash | [Read a crash](docs/runbooks/read-a-crash.md) |
| Find asset browsing, rendering and research commands | [Lab notebook: offline tooling](docs/lab-notebook.md#10-offline-tooling) |
| Check past measurements or retained artifacts | [Lab notebook](docs/lab-notebook.md) |
| Work on the Android app | [Android README](android/README.md); [app-private engine checks](android/README.md#device-boundary-checks); [dependency notices and release requirements](android/native/THIRD_PARTY.md) |
| Learn project terms or constraints | [Glossary](GLOSSARY.md), [agent instructions](AGENTS.md), [decisions](docs/adr/) |
| Continue unfinished work | `.scratch/`; [local issue tracker](docs/agents/issue-tracker.md) |

### Resource layout

| Path | Role |
|---|---|
| `resources/runtime/` | Compiled Python 3.12 translation runtime from the PC patcher |
| `resources/catalog/` | English catalog and shared catalog edits |
| `resources/catalog_id/` | Indonesian catalog and its own catalog edits; other edits fall back to English |
| `resources/sprites/` | Hand-finished atlas labels and pristine restore crops |
| `resources/adb/` | Bundled Android Debug Bridge |
| `resources/key/` | Stable re-signing key shipped with the patcher |
| `resources/qtsvfs/` | Tencent's package builder and its dependencies |
| `tools/research/` | Manual probes and offline checks; excluded from the shipped exe |

Local dumps, generated packages and device evidence are excluded from Git.
