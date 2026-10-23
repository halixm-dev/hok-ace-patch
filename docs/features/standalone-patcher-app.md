---
feature: standalone-patcher-app
status: delivered
updated: 2026-10-17
branch: master
commits: 7b9769b..9f151a8
---

# Standalone Patcher App

## Report

**Versioning (2026-10-17):** the root `VERSION` file sets the Windows header version,
currently `1.7.1.3` (three game version numbers plus patch revision). PyInstaller bundles
the file so source and frozen builds read the same version. See
[patch versions](../../README.md#patch-versions) for increment rules.

**Branding update (2026-10-16):** the Windows window title, header and build output are now
`HOK ACE Language Patcher`. The settings path, working folder and taskbar identity stay
stable so existing preferences and working data remain available. The original delivery names
below are historical. The Android app uses the same product name.

**What was built** — `hok-ace-android-en` is now a standalone, buildable Windows patcher app with the
sibling project's layout and branding: `app/` (customtkinter GUI, USB device workflow, APK rewrite and
v2 signing, PyInstaller build, icon generator), `resources/` copied verbatim (808 files — adb, catalog,
re-signing key, Python 3.12 runtime bytecode), the three root `.bat` scripts, `requirements.txt`,
`README.md` and `AGENTS.md`. Branding is identical to the sibling: same window title and exe name
(`HOK ACE Mobile English Patcher`), same settings path, same `HOK ACE Patcher Data` working folder and
the same seven stepper keys.

The translation engine remains **this** repository's own pipeline. `tools/build_device_patch.py` gained
`build_patch()`, the single implementation now shared by the CLI and the GUI, and it calls
`qts_relocate.install_btree_slot_map()` before scanning so a re-run reads live chunks instead of
superseded copies. The reverse-engineering probes moved to `tools/research/`, off the runtime path.
Staging is text-tables-only — `full` mode with a `fit-only` fallback, no graphics mode — so
`count_translated` reports text tables and the GUI no longer mentions images. **Superseded:** the
`graphics` mode, the texture pass and the `(text tables, textures)` count were all added by
`docs/features/texture-translation.md`; see that document for what this one deferred.

**Verification** — run from the repo root; `.venv` is Python 3.12.13 with `requirements.txt` installed.

| Command | Result |
|---|---|
| `python -m py_compile` on all `app/`, `tools/` and relocated research modules | PASS (3.12) |
| 28-check verification script: import wiring, bundled-runtime load, `install_btree_slot_map()` attach, `count_translated`, APK entry rewrite, APK v2 sign + digest-chain recompute + RSA verify against the real key, AXML debuggable patch (insert and already-declared paths, plus idempotent re-patch) | PASS 28/28 |
| `python tools/build_device_patch.py --help` | PASS (exit 0) |
| All 7 relocated research scripts `--help` | PASS (0 failures) |
| `pip install -r requirements.txt` | PASS — every pin resolved and installed at the declared version |
| `python app/build_exe.py` | PASS — `dist/HOK ACE Mobile English Patcher.exe`, 48.2 MB |
| Frozen exe `--selftest <empty dir> <out>` | PASS (expected failure) — loaded the bundled runtime and reached `wxq_patch\adaptive.py` before `ValueError: WXQ_Data/Package/builtin was not found` |

At the original delivery, the real-dump self-test and end-to-end device flow were not run.
The 2026-10-04 real-dump self-test (journey log) supersedes that historical limitation. Later device
and graphics evidence is recorded in the corresponding feature records. The repository has no
general test suite.

**Journey log**

- This repo's `tools/` turned out to be an earlier fork of the sibling's pipeline, missing `build_patch()`, the `qts_relocate` re-run fix and the staging guards — adopted here; its coverage gaps were left by decision (lab notebook, 2026-09-29).
- Moving the research scripts broke `axml_add_provider.py`'s import of a `tools/` helper — a one-line parent-directory insert (lab notebook, 2026-09-29).
- A bytecode scan of `wxq_patch` trimmed the dependencies and the exe — right about the runtime, partly reverted when the texture pass needed four of them (lab notebook, 2026-09-29).
- Two initial verification failures — defects in the test fixtures, not the product (lab notebook, 2026-09-29).
- Review's four non-critical findings, all inherited from the sibling — left; re-check the first two if the app adopts the PC-side pipeline (lab notebook, 2026-09-29).
- Android signing adapter: `apk_tools.sign_v2` takes an optional RSA callable — byte-identical output, verified by `apksigner` (lab notebook, 2026-10-03).
- Summary accessors moved unchanged into `tools/patch_summary.py`, shared with Android — frozen exe `--selftest` on the pristine dump passed (lab notebook, 2026-10-04).

## [S1] Problem

`hok-ace-android-en` holds a single directory, `tools/`, and nothing else. Getting an English
translation onto a phone therefore means running `tools/apply_device_patch.sh` by hand, and that
script points at a machine layout that no longer exists: an APK Editor Studio install, a
`work/patcher-pyz` runtime, a `vendor/` directory, and pre-pulled `hok ace mobile *.apk` files.
None of those are in the repository, so the script cannot run as committed.

The sibling project `hok-ace-mobile-en` solves the same problem for the same game
(`com.tencent.tmgp.osgame`) with a packaged Windows GUI: it pulls the APK and game data over USB,
builds the English packages, pushes them back and reinstalls. This change gives `hok-ace-android-en`
that same application surface, while keeping **its own** `tools/` pipeline as the translation engine.

## [S2] Design

The repository gains the reference project's layout: `app/` for the application, `resources/` for
consumed data, root build scripts, and documentation. Branding is identical to the reference, so the
app is the same product surface; only the translation pipeline behind it differs.

### Application layer (`app/`)

| File | Role |
|---|---|
| `hok_patcher.py` | customtkinter GUI on the shared design (`DESIGN.md`): one column with ① Language, ② Start (device, working folder, progress and results in place), the error card and the log |
| `patcher_core.py` | device workflow: adb, APK re-sign, data pull, translation, push, reinstall |
| `apk_tools.py` | APK entry rewrite and APK Signature Scheme v2 signing (no Java / build-tools) |
| `build_exe.py` | PyInstaller one-file build |
| `make_icon.py` | regenerates `resources/icon.*` from the Android launcher artwork |

Branding is taken verbatim from the reference: window title and exe name
`HOK ACE Mobile English Patcher`, saved settings at
`%APPDATA%\HOKAceEnglishPatcher\settings.json`, default working folder
`HOK ACE Patcher Data` beside the executable, and the same `STEPS` stepper keys
(`device`, `apk`, `access`, `pull`, `translate`, `install`, `restore`).

`patcher_core` sets module search paths the same way the reference does: `tools/` is inserted for
source runs (the frozen exe gets it via PyInstaller `--paths`), and `resources/runtime/` is
**appended** so the project's own stdlib wins over the runtime's bundled copy.

### Repatch from the pristine delta (2026-10-17)

From [`.scratch/language-switch`](../../.scratch/language-switch/spec.md), tickets 03 and 05. The delta
is `tools/pristine_delta.py`, shared with the Android patcher; `patcher_core` drives it.

- `<working folder>/pristine/` holds `delta.bin` and `staged-hashes.json` (every hash an install of
  this patcher wrote); sessions are pruned, this folder never is.
- `restore_pristine` runs right after the pull: it rebuilds the files the delta names in
  `sessions/<stamp>/game` in place (a full pull's `device-backup.tar` keeps the phone's bytes) and logs `rebuilt N
  files from the pristine delta`. It refuses with the clear-data message when a named file is at
  neither its staged nor its pristine bytes while some file still holds this patcher's translation,
  or when a file is at a recorded staged hash with no delta entry behind it. When no file holds this
  patcher's translation the delta is stale (the data was cleared, possibly onto a newer version) and
  the run goes on as a first install.
- A first install (no delta) is allowed only when `check_first_delta` finds the build read the layer
  as pristine (`pristine_delta.text_not_pristine`); otherwise it refuses before the push, naming the
  Android patcher as the one to use if it patched last.
- `bootstrap_delta` (no delta kept) makes one from a kept session whose staged files equal the
  phone's and whose backup reads as pristine, so a phone patched before deltas needs no clear.
  Sessions are pruned after it, so it sees the two kept before the current one.
- `push_translation` writes the new delta as `delta.pending.bin` before the first push and moves it
  over `delta.bin` after the last, since Windows has no rollback; the next run accepts each file at
  either delta's staged bytes. A file the previous delta named and this build no longer stages is
  pushed back at its pristine bytes, so no file keeps the old language.
- The LANGUAGE card says no clear is needed while the working folder keeps a delta.
- **Remove translation** (ticket 06; since [shared-design](shared-design.md) ticket 16 a secondary button in ① Language, shown only while the working folder keeps a delta, behind a plain confirmation):
  `Patcher(remove=True)` runs the same steps up to `restore_pristine`, skips the build and pushes the
  rebuilt pristine files through `push_translation`, which then deletes the delta (and the pending
  one), so the next patch run is a first install under both pristine signals. It refuses, before any
  write, an official-signature game, a phone this patcher has no record of, and the clear-data cases
  above; a phone already untranslated writes nothing. The final message says to keep using Scan to
  login and to reinstall from the store for the official app.
- Checks: `tools/research/check_pristine_delta.py` (with `--game` for the real round trip and
  switches) and `tools/research/check_windows_repatch.py`. Not run against a phone (ticket 08).

### Partial pull (2026-10-18)

`pull_game_data` writes `sessions/<stamp>/pull.json` once the session's layer equals the phone's
(`mode` `full` or `changed`). With such an earlier session, `pull_changed` has the phone `sha256sum` its
layer, copies every file the earlier session's `staged/` or layer holds at that SHA-256, pulls only the
rest in `tar` batches, and checks each pulled file against the phone's hash. Hash output it cannot
parse, a failed transfer, or a pulled file at the wrong hash falls back to the full tar of `packages`
and `Watchdog`. Only that full tar becomes `device-backup.tar`, so a partial session never qualifies
for `bootstrap_delta`. A re-run on the same data pulls nothing. A data update pulls the files it
changed. Measured offline and on a phone in the lab notebook (2026-10-18, "Partial pull on the Windows
patcher"); checked by
`tools/research/check_windows_repatch.py`.

`push_translation` skips every file `pull.json` records the phone holding at the same SHA-256, and
clears `Watchdog/` only when it writes something. A re-run of the same language and catalog writes
nothing.

### Repatch after an in-game update (2026-10-18)

The delta carries an asset record (`pristine_delta.make(..., fingerprint=True)`, through
`tools/asset_fingerprints.py`): per staged package, each asset the install changed, with the SHA-256 of
its uncompressed bytes on both sides. When the rebuild leaves files unmatched, `restore_pristine` asks
`pristine_delta.accept_replaced`, package by package. A package the update changed is taken as the new
pristine, read as the update left it, only when none of its files is still at its staged bytes, its
index and shards are all present (or the whole package is gone), and none of the recorded assets is
still at its staged bytes. Any other package refuses the run with the clear-data message, as before.
A run that accepted a replaced file must then pass the text signal (`check_first_delta`), and its new
delta's pristine side is the update's bytes. A delta from before the asset record accepts no replaced
file. Checked offline on the real 1.6.0.1 packages by `tools/research/check_update_repatch.py` (lab
notebook, 2026-10-18, "Repatch after an in-game update, offline").

### Pipeline adaptation (`tools/`)

`tools/build_device_patch.py` currently exposes only an argparse `main()`. It gains a programmatic
entry point, becoming the single implementation that both `main()` and the app call:

```python
def build_patch(game: Path, catalog: Path, work: Path, output: Path,
                *, fit_only_mode: bool = False, log=print) -> dict:
```

- `main()` keeps its existing flags (`--runtime`, `--game`, `--catalog`, `--work`, `--output`,
  `--fit-only`) and now inserts the runtime path and then delegates to `build_patch`.
- `build_patch` imports `wxq_patch` from whatever runtime directory the caller placed on
  `sys.path`; it does not add paths itself. This keeps the function usable from the frozen exe,
  where the runtime ships inside the bundle.
- `log` is called with progress lines, allowing the GUI to stream them into its log pane.
- The return value is exactly the payload written to `output/device_patch_summary.json`:
  `{"counts": dict, "skipped_count": int, "fit_only": bool, "packages": [...]}` where each package
  carries `package_id`, `mode`, `source_package`, `fit_summary` and `stage_report`, and
  `stage_report` carries `status` and `replacement_count`.

Two robustness guards are folded into `build_patch` while writing it fresh, matching the sibling
project's current implementation:

1. Each staging loop runs `while any(directory.glob("*.assets"))` instead of `while True`, so a
   package whose every asset was dropped stops rather than calling `stage` again with nothing left
   to stage.
2. A `None` report — reached when nothing is left that fits in place, as on a re-run over an
   already-patched package — is logged and the package is skipped, so `packages` never carries a
   `None` `stage_report`. This is also what stops `report['status']` from being read on a `None`.

Consequence worth knowing: a full-mode package whose every asset is dropped is skipped outright
rather than retried in `fit-only` mode, so that narrow retry no longer happens.

`tools/qts_relocate.py` joins the shipping pipeline. Its `install_btree_slot_map()` monkey-patches
the runtime's `QtsPackage.build_slot_map` so it follows the shard's B-tree. Without it the stock
scanner can return a superseded copy of a relocated chunk, which makes a **second** run over an
already-patched install read the old Chinese data. `build_patch` calls it before scanning.

The rest of the reference's newer pipeline — `device_extensions`, `pb_text`, `mobile_graphics`,
`extra_text`, `unity_text` — is deliberately **not** adopted. Coverage is exactly what android-en's
tools produce: text tables that fit, with the `full` → `fit-only` fallback. **Partly superseded:**
`device_extensions`' graphics half (`port_graphics`) and `mobile_graphics` were adopted later by the
`texture-translation` feature; `pb_text`, `extra_text` and `unity_text` still are not.

### Reverse-engineering tools (`tools/research/`)

`axml_add_provider.py`, `emulate_arm64_hash.py`, `extract_patcher.py`, `extract_pyz.py`,
`find_arm64_xrefs.py`, `hash_probe.py`, `probe_descriptor_hashes.py`, `replace_apk_entries.py`,
`apply_device_patch.sh` and `smali-probe/` are research artifacts on no runtime path. They move to
`tools/research/`. `check_graphics.py` joined them later, added by the `texture-translation` feature as
the offline check for the texture codec.

`axml_add_provider.py` imports helpers from `axml_set_debuggable`, which stays in `tools/` because
the app needs it. Running it as a script would put `tools/research/` — not `tools/` — on
`sys.path`, breaking that import, so the module gains one line inserting its parent directory:

```python
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
```

### Resources (`resources/`)

Copied verbatim from `hok-ace-mobile-en`: `adb/`, `catalog/`, `key/`, `runtime/`. These are
consumed, never regenerated here. `icon.ico` and `icon.png` are the Android patcher's launcher
artwork (`android/app/src/main/res/drawable-nodpi/ic_launcher_artwork.png`) on a transparent
square, written by `app/make_icon.py`; re-run it when that artwork changes. `catalog/` and `runtime/` must stay in
lockstep; the catalog is compatible because `build_mobile_patch.py` and `axml_set_debuggable.py` are
byte-identical between the two repositories.

`runtime/` is Python 3.12 bytecode and loads on no other version, so the project requires 3.12.

### Coverage difference from the reference

Still not adopted: `extra_text`, `unity_text` and `pb_text`, so extra text tables outside the staged
packages are not translated.

Textures and the image count were adopted afterwards. The `texture-translation` feature added
`tools/device_extensions.py` and `tools/mobile_graphics.py`, gave the pipeline a `graphics` package
mode, and returned `patcher_core.count_translated` to `(text tables, textures)` so the GUI and its
completion message report both. See `docs/features/texture-translation.md`. The five statements
above that this invalidates are marked in place.

Resource tokens were adopted afterwards by the `resource-token-expansion` feature:
`tools/resource_tokens.py` expands `{Energy}`/`{LordExp}`/`{LordHp}` in the staged replacements after
translation, so card text no longer renders hybrid. Three statements above therefore no longer
describe the repository: `tools/` also holds `resource_tokens.py` (so the original listing of `tools/` —
`axml_set_debuggable.py`, `build_device_patch.py`, `build_mobile_patch.py`, `qts_relocate.py` plus
`research/` — is short by one file), the `[S3]` entry below is superseded, and the reference's `RESOURCE_TOKEN_FIX.md`
is now attached rather than deferred.

The app's own name is now written from the manifest as well: `tools/axml_label.py` names the app
(`<application android:label>` and every component sharing that reference), so that original
listing of `tools/` is short by two files. `README.md` describes what that edit does and `AGENTS.md` what it
is allowed to cost a run; the device cycle that would confirm the name on a launcher has not been run
yet, so nothing here claims it.

### Verification boundary

There is no test suite, and no Android device or dumped game directory is available in this
environment, so the end-to-end device flow cannot be exercised. Verification is limited to what is
mechanically checkable: every Python file compiles under 3.12; the bundled runtime imports under
3.12 and `install_btree_slot_map()` attaches to it; `build_patch` is importable and resolves its
helpers; and the `apk_tools` signing round-trip is exercised on a synthetic APK. The `--selftest`
path needs a dumped game directory and is therefore reported as unverified rather than claimed.

## [S3] Out of Scope

- Adopting the reference's `device_extensions`, `pb_text`, `mobile_graphics`, `extra_text` or
  `unity_text` modules, or matching the reference's translation coverage. (`resource_tokens` is the one
  exception: adopted later by the `resource-token-expansion` feature. `device_extensions`' graphics
  half and `mobile_graphics` are a second: **superseded** for those two by the `texture-translation`
  feature; `pb_text`, `extra_text` and `unity_text` remain out of scope.)
- Attaching the reference's `RESOURCE_TOKEN_FIX.md` work, which documents that unadopted change.
  **Superseded** — attached by the later `resource-token-expansion` feature.
- Regenerating `resources/catalog/` or `resources/runtime/`; both are consumed as-is.
- Solving the missing `py -3.12` interpreter on this machine, or producing a `.venv` / built exe as
  part of this change.
- Deleting the reverse-engineering tools; they are relocated, not removed.
- Changing the game package (`com.tencent.tmgp.osgame`) or adding split-APK support.
