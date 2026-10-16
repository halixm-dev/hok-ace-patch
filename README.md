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

Before applying a newer translation, switching languages, or patching after a game update,
clear the game's data, let it download again to the login screen, then close it and patch.
Clearing data removes local game data and requires another login. Re-running over translated
text does not refresh those text tables.

Use the APK and game data from the phone's current version. An older staged package can
stall loading and cause the game to repair away the translation.

## Run or build from source

### Automated Android builds

| Trigger | Result |
|---|---|
| Push to `master`, pull request, or **Actions → Android APK → Run workflow** | Full-codec development APK and check reports under the run's artifacts |
| Push a tag such as `android-v0.1.0` | Privately signed release APK, SHA-256, codec source companion and a draft GitHub release |

CI runs Android unit tests, lint, native ELF alignment, APK ZIP alignment and signer verification.
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
| Work on the Android app | [Android README](android/README.md); [dependency notices and release requirements](android/native/THIRD_PARTY.md) |
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
