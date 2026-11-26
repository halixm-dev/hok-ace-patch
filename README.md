# HOK ACE Language Patcher

Repository: [halixm-dev/hok-ace-patch](https://github.com/halixm-dev/hok-ace-patch).

Install an English or Indonesian translation into 王者万象棋 (`com.tencent.tmgp.osgame`)
on an Android phone, without root, or into the game's PC edition (`WXQ.exe`) on the same computer.

| Patcher | Start here |
|---|---|
| Windows app, connected to the phone over USB | Follow the steps below |
| Windows app, for the PC edition on this computer | [Patch the PC edition](#patch-the-pc-edition) |
| Android app (Android 10+ on ARM64) | [Android setup and build guide](android/README.md); development build with device acceptance still pending |

The translation includes catalog text tables, catalog edits, two Career-atlas labels
(MY SKINS and TOTAL PROFIT), the 32 Secret Technique card titles, and one Lua label. Some content stays Chinese. See the
[coverage ledger](docs/translation-progress.md) for measured counts and known gaps;
each run reports what it actually applied and skipped.

## Use the Windows app

1. Install the game and let its in-game download finish at the login screen, then close it.
2. Enable **USB debugging** in the phone's Developer options. Connect it to Windows by USB
   and tap **Allow** on the phone's debugging prompt.
3. Open `dist\HOK ACE Language Patcher.exe`, or [run from source](#run-or-build-from-source).
   If the phone is missing in **Android USB** mode, click **Install Universal ADB Driver** under
   **Setup**. Follow the Windows installer, then reconnect the phone.
4. Under **Setup**, choose the translation and a
   **WORKING FOLDER** with at least 8 GB free. Keep working data outside this repository; the
   default folder is `HOK ACE Patcher Data` beside the exe.
5. Click **Start** and follow the installation prompts. Keep the game closed until
   the patch finishes and the normal APK is restored.
6. Open the game and use **Scan to login**. Direct WeChat/QQ login breaks when the APK is re-signed. With **Root**, the
   patcher installs no APK: if the game app on the phone is still the original, direct login keeps working.

### Updates and language changes

To switch languages or apply a newer translation, run the patcher again; there is no need
to clear the game's data. After each install the patcher keeps a **pristine delta**, the original
bytes it overwrote (about 5 MB, in `pristine\` in the working folder, or in the Android app's own
storage). The next run rebuilds the untranslated files from it before building the new translation,
and the log says `rebuilt N files from the pristine delta`. Each patcher keeps its own delta, so
switch with the patcher that translated the phone last. The Windows patcher can also make a first
delta from a working folder that still holds the session of an earlier install.

To go back to the untranslated game, use **Remove translation**. It appears when the patcher has
a pristine delta (Windows: in its working folder). It writes
the original files back the same way an install writes a translation; nothing is downloaded and no
game data is deleted. The patcher-signed app stays installed, so keep using **Scan to login**; for the
official app, reinstall the game from the store.

After a game update, run the patcher again. When the update rewrote a translated file, the patcher
checks that package asset by asset: if none of its translation is left in it, it builds from the
update's files and keeps a new delta against them. When some of the translation is still in it, the
Android patcher writes the original bytes of those assets back (asset restore), or, when it cannot,
deletes that package so the game downloads it again (Re-download, below). A run that cannot rebuild the
untranslated files otherwise stops before it writes anything and tells you to clear the game's data:
when the Windows patcher finds part of the translation left in a file an update changed, when the delta was made by patcher 1.6.1.5 or older (it has
no asset record), or on a phone another patcher (or a patcher version from before deltas) translated. Then clear the game's data,
let it download again to the login screen, close it and patch. Clearing data removes local game data
and requires another login.

If the game's own update stops on the translated files ("资源修复失败，请清理资源后重新下载资源"), the
Android patcher sees it on the next Start or Remove translation: the game lists those files as broken.
Start then deletes, without a review, only the translated packages the game listed, the mixed
packages it cannot restore (an update rewrote them while some of the translation is still in them),
any package with a texture slot it can no longer reach, and the game's update records (Re-download).
Open the game, let it download them and finish the update to the login screen, close it, then return
and tap **Downloads finished**: the translation continues in the same run. A package still damaged
after its own download is not deleted again by itself; the patcher shows it for review above
**Delete and re-download**. No other game data is deleted. The Windows
patcher does not detect this yet; clear the game's data instead.

Use the APK and game data from the phone's current version. An older staged package can
stall loading and cause the game to repair away the translation.

## Patch the PC edition

1. Let the launcher finish any update, then close the game and the launcher. Every PC action refuses
   while `wxq*.exe` or `王者万象棋.exe` runs.
2. Open the Windows app and choose **PC**. In **Setup**, choose the translation
   and a working folder on a drive with about 10 GB free. The receipts take about
   4 GB per install, and a job stages about 4 GB more while it runs.
3. The game folder is found from the launcher's records; otherwise use **Choose folder** and pick the
   folder that holds `WXQ.exe`. **Check** runs by itself and shows *installed*, *not installed*,
   *replaced by an update* or *partly installed*.
4. Click **Install**. A job takes several minutes and cannot be stopped part way; keep the window open
   until it finishes. Then start the game from its launcher.

Before each install the app keeps the original bytes of every file it changes as a **receipt**, in
`pc\receipts\` in the working folder. **Remove translation** writes them back. Installing the other
language or applying a new bundled translation restores from the receipts first, then installs,
in one job. When a launcher update replaces every translated file, Check shows *Replaced by an
update*. Click **Reapply translation** to patch the updated files. For a mix of translated and
updated files, or a translation from another patcher, use **Repair** in the launcher, close it,
then click **Check**. The window title stays 王者万象棋 because the
launcher repairs any listed file whose size changes
([ADR 0011](docs/adr/0011-keep-every-file-the-pc-launcher-lists-at-its-listed-size.md)).

## Patch versions

The root `VERSION` file sets the Windows and Android patcher version to **1.12.1.1**.
Use three numbers from the game's **data version**, omitting its extra middle zero,
then append the patch release number, starting at `1`. For example, game data
`1.0.6.1` becomes patch `1.6.1.X` and data `1.11.0.2` becomes
`1.11.2.X`. Increase `X` for each patch release. Reset it to `1` when the data version changes.

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

### Automated builds and releases

| Trigger | Result |
|---|---|
| Push to `master`, pull request, or **Actions → Android APK → Run workflow** | Full-codec development APK and check reports under the run's artifacts |
| Push to `master`, pull request, or **Actions → Windows exe → Run workflow** | Windows EXE build and smoke test |
| Push a tag matching `VERSION`, such as `android-v1.6.1.1` | One draft GitHub release with the signed Android APK, smoke-tested Windows EXE, codec source companion and SHA-256 checksums |

CI runs Android unit tests, lint, native ELF alignment, APK ZIP alignment and signer verification.
A separate `checks` job runs every repository-only check under [Verify changes](#verify-changes)
on each push and pull request. A tagged release waits for those checks and both platform builds.
`SHA256SUMS` covers the APK, EXE and codec source companion. Native alignment and
runtime dependency reports stay in the run's artifacts.
Artifacts expire after 14 days; draft release attachments remain. A draft's notes start from
`tools/ci/release_notes.sh`: a player-facing changelog seeded with the `feat:` and `fix:` subjects since
the previous `android-v` tag, to rewrite for players before publishing. Release drafts need review before
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
| Build only the native BC7 encoder | `.venv\Scripts\python.exe app\build_exe.py --native-only` | Creates `build\native\hok_bc7.pyd`, which source runs also load |

`build.bat` also needs Rust ([rustup](https://rustup.rs)): it builds the PC edition's native BC7
encoder (`crates/hok_bc7`, modes 6, 5, 4 and 7) with the toolchain pinned in its `rust-toolchain.toml`.
Source runs work without it and fall back to the Python encoder; set `HOK_BC7_ENCODER=native` or
`python` to require one or the other.

If `py -3.12` is unavailable, select your Python 3.12 executable before setup:

```bat
set PYTHON=C:\path\to\python3.12.exe
setup.bat
```

To check a built exe without a phone or a game dump, run
`"dist\HOK ACE Language Patcher.exe" --smoketest <out-dir>`: it imports the pipeline and the
runtime, reads both catalogs and runs each codec once, then writes `<out-dir>\smoketest.json`.
The **Windows exe** workflow builds the exe and runs this on each push to `master` and pull request.

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
| User-facing strings (either patcher) | `.venv\Scripts\python.exe tools\research\check_ui_strings.py` | Repository only |
| Staging contract | `.venv\Scripts\python.exe tools\research\check_staging_contract.py` | Repository only |
| Texture processing | `.venv\Scripts\python.exe tools\research\check_graphics.py` | Shipped assets; add `--game <game-dir>` to check a dump |
| Indonesian texture edits | `.venv\Scripts\python.exe tools\research\make_language_payloads.py --check` | Shipped assets |
| Pristine delta | `.venv\Scripts\python.exe tools\research\check_pristine_delta.py` | Repository only; add `--game <pristine game-dir> --apk <apk> --work <dir>` for the round trip and language switches |
| Append pass | `.venv\Scripts\python.exe tools\research\check_append.py` | Repository only; add `--game <game-dir> --apk <apk> [--package <id>]` to append to a real package twice |
| Shard B-tree splits | `.venv\Scripts\python.exe tools\research\check_btree_split.py` | Repository only; add `--game <game-dir>` to check every shard of a layer |
| Repatch without a clear (Windows) | `.venv\Scripts\python.exe tools\research\check_windows_repatch.py` | Repository only |
| Run artifact identities | `.venv\Scripts\python.exe tools\research\check_run_artifacts.py` | Repository only; also fails if a tracked file under `app/`, `tools/` or `resources/` has a non-ASCII name |
| Remove on real data (Windows) | `.venv\Scripts\python.exe tools\research\check_windows_remove.py --pristine <builtin-dir> --staged <build-output> --work <dir>` | A pristine layer and a build of it; about 5x the touched packages free |
| Windows interruption fixtures | `.venv\Scripts\python.exe tools\research\check_windows_recovery.py` | Synthetic private files only; expected failures track known recovery gaps |
| Baseline/change output controls | `.venv\Scripts\python.exe tools\research\compare_continuation_controls.py --help` | Capture external staging hashes, normalized summary and pristine delta; compare reports made with matching inputs |
| Changed engine or game against saved work | `.venv\Scripts\python.exe tools\research\check_changed_input_controls.py --help` | Two pristine dumps with their APKs; about 40 GB free under `--work` |
| Re-download over a real update | `.venv\Scripts\python.exe tools\research\check_update_redownload.py --cycle <cycle> --work <dir>` | An `update_cycle.py` capture set (`after-push`, `after-patch`, `after-update`, `after-finish`) on the same drive as `<dir>` |
| Control-capture normalization | `.venv\Scripts\python.exe tools\research\check_continuation_controls.py` | Repository only |
| PC edition workflow | `.venv\Scripts\python.exe tools\research\check_pc_install.py --game <game-copy> --work <dir>` | A copy of the PC edition's folder, never the installed game; about 8 GB free under `--work` |
| A change requiring screen verification | [Device cycle](docs/runbooks/device-cycle.md) | Phone and matching game data |
| A change requiring screen verification in the PC edition | [PC cycle](docs/runbooks/pc-cycle.md) | The PC edition and its launcher |

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

### Check the PC edition offline

Work on a **copy** of the PC edition's folder, never the installed game, with the game and its
launcher closed. `--pc-selftest` builds both languages' per-install catalogs and has the engine
stage and verify them without writing to the copy; it writes `<out-dir>\pc_selftest.json` and
`<out-dir>.log`:

```bat
"dist\HOK ACE Language Patcher.exe" --pc-selftest <game-copy> <out-dir>
```

`check_pc_install.py` runs the whole sequence on the copy in both language orders (install, Check,
install again, switch, Check, restore). It fails when a restore leaves any package file changed, a
repeat install changes anything, a switch skips the receipts, `replacements\` is not empty when the
engine starts, or `LocalFileList.json` or a listed file's size changes. It writes into the copy and
`<work-dir>`, and needs about 8 GB free there:

```bat
.venv\Scripts\python.exe tools\research\check_pc_install.py --game <game-copy> --work <work-dir>
```

The window runs each PC job as a child process,
`--pc-job <action> <game> <work> <answer.json> <language>` with `install`, `status` (Check) or
`restore`; it answers through `<answer.json>` and logs to `<answer.json>.log`. A PC cycle of a config
bin adds `--cycle-asset <hash>` after those five, run from source, and `--pc-selftest` takes the same
two words after `<out-dir>`; the hash must name one of `extra_text.CANDIDATE_ASSETS` (see
`docs/runbooks/pc-cycle.md`).

## Find the right file

| Task | Read or edit |
|---|---|
| Change the Windows interface or workflow | `app/`; [Windows patcher record](docs/features/standalone-patcher-app.md) |
| Change the PC edition workflow or its catalog | `app/pc_edition.py`, `tools/pc_catalog.py`, `tools/engine_hooks.py`; [PC cycle](docs/runbooks/pc-cycle.md) |
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
| `resources/catalog_supplement/` | Strings game data updates added after the catalog was built, English and Indonesian, merged as the catalog loads |
| `resources/sprites/` | Hand-finished atlas labels, per-language label textures and pristine restore crops |
| `resources/ui/` | Shared theme tokens (`theme.json`) and English/Indonesian strings (`strings.json`) for both patchers |
| `resources/fonts/` | Bundled interface fonts and their OFL licenses |
| `resources/adb/` | Bundled Android Debug Bridge |
| `resources/key/` | Stable re-signing key shipped with the patcher |
| `resources/qtsvfs/` | Tencent's package builder and its dependencies; kept for `--builder` runs from source, not shipped in the exe |
| `tools/research/` | Manual probes and offline checks; excluded from the shipped exe |

Local dumps, generated packages and device evidence are excluded from Git.
