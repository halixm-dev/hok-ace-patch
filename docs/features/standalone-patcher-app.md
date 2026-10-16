---
feature: standalone-patcher-app
status: delivered
updated: 2026-10-04
branch: master
commits: 7b9769b..9f151a8
---

# Standalone Patcher App

## Report

On 2026-10-04 the three summary accessors moved unchanged into `tools/patch_summary.py` so
Android and Windows classify the four results identically. `patcher_core` re-exports the existing
names, preserving the GUI API. Python 3.12 import/control check returns 391 text tables, 395 applied
textures, one skipped table and zero skipped textures; accessor identity matches the shared module.
The frozen application was rebuilt with `.venv/Scripts/python.exe app/build_exe.py` and passed
`--selftest` against `dist/HOK ACE Patcher Data/pristine/20261003-173730/game`;
`artifacts/android-port-windows-selftest/selftest.json` reports `ok: true`. Build and self-test
logs are `artifacts/android-port-windows-build.log` and `artifacts/android-port-windows-selftest.log`.
The self-test covers the downloaded dump without an APK input.

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
The 2026-10-04 real-dump self-test above supersedes that historical limitation. Later device
and graphics evidence is recorded in the corresponding feature records. The repository has no
general test suite.

**Journey log**

- **Android signing adapter (2026-10-03).** `apk_tools.sign_v2` accepts an optional RSA callable
  and DER public key; its default still loads the existing PKCS#8 key through cryptography.
  Crypto imports now occur only in that default branch. ZIP rewriting and the v2 digest/block
  construction stay shared. The old implementation, new default and injected desktop RSA output
  are byte-identical on the disposable fixture control (SHA-256 `eeb33a4e…26d3854b`), and
  SDK `apksigner verify --verbose --print-certs` independently verifies v2 and the stable certificate.
  The Android port delegates the one RSA operation to Java; its separate device proof is recorded
  in `android-shizuku-patcher.md`.
- This repo's `tools/` is an *earlier fork* of the sibling's pipeline: `axml_set_debuggable.py` and
  `build_mobile_patch.py` are byte-identical, but `build_device_patch.py` had no `build_patch()`, no
  `qts_relocate` re-run fix, and no staging guards. Coverage gaps (resource tokens, extra text,
  textures) were left unadopted by explicit decision, not oversight; resource tokens were adopted
  later — see *Coverage difference from the reference*.
- `tools/research/axml_add_provider.py` imports `axml_set_debuggable` from `tools/`; running it as a
  script puts only `tools/research/` on `sys.path`, so the move needed a one-line parent-directory
  insert. Any future move of a script that shares helpers must check this.
- Scanning `wxq_patch`'s bytecode showed it references only `lz4` (vendored) and `httpx` (an unused
  `gemini` module) — none of UnityPy, `pypinyin`, `astc_encoder`, `ooz`, `texture2ddecoder` or
  `archspec`. `requirements.txt` and `build_exe.py` were trimmed accordingly; the exe is 48.2 MB
  against the sibling's 66.3 MB. **Partly reverted:** the texture pass does need `astc_encoder`, `ooz`,
  `texture2ddecoder` and `archspec` after all, so those four came back in
  `docs/features/texture-translation.md`. The scan was right about `wxq_patch` — the need is in the
  new pass, not the runtime.
- Two initial verification failures (embedded-certificate mismatch, debuggable attribute "missing")
  were defects in the *test fixtures*, not the product: an APK v2 certificates field needs a second
  length-prefix unwrap, and AXML requires resource-map entry *i* to name string-pool entry *i*. A
  failing check is worth re-reading before it is believed.
- Review left four non-critical findings, all pre-existing or inherited from the sibling rather than
  introduced here: (a) `patcher_core.push_translation` pushes every numeric directory under `staged`,
  so a package skipped via `report is None` could still have leftover files pushed to the phone;
  (b) `install_btree_slot_map()`'s wrapper signature is `(self)` while the stock method is
  `(self, wanted=None)`, safe only because `wxq_patch.pipeline` — its only 1-arg callers — is
  unreachable from this app; (c) `--selftest` opens its log file before redirecting stdout, so a
  missing output parent exits a windowed exe silently; (d) the relocated `apply_device_patch.sh`
  computes `ROOT` one level too shallow. Re-check (a) and (b) if the app ever adopts the PC-side
  pipeline.

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
| `hok_patcher.py` | customtkinter GUI, seven-step stepper, log pane, working-folder picker |
| `patcher_core.py` | device workflow: adb, APK re-sign, data pull, translation, push, reinstall |
| `apk_tools.py` | APK entry rewrite and APK Signature Scheme v2 signing (no Java / build-tools) |
| `build_exe.py` | PyInstaller one-file build |
| `make_icon.py` | regenerates `resources/icon.*` |

Branding is taken verbatim from the reference: window title and exe name
`HOK ACE Mobile English Patcher`, saved settings at
`%APPDATA%\HOKAceEnglishPatcher\settings.json`, default working folder
`HOK ACE Patcher Data` beside the executable, and the same `STEPS` stepper keys
(`device`, `apk`, `access`, `pull`, `translate`, `install`, `restore`).

`patcher_core` sets module search paths the same way the reference does: `tools/` is inserted for
source runs (the frozen exe gets it via PyInstaller `--paths`), and `resources/runtime/` is
**appended** so the project's own stdlib wins over the runtime's bundled copy.

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

Copied verbatim from `hok-ace-mobile-en`: `adb/`, `catalog/`, `key/`, `runtime/`, `icon.ico`,
`icon.png`. These are consumed, never regenerated here. `catalog/` and `runtime/` must stay in
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
describe the repository: `tools/` also holds `resource_tokens.py` (so the T1 acceptance listing is
short by one file), the `[S3]` entry below is superseded, and the reference's `RESOURCE_TOKEN_FIX.md`
is now attached rather than deferred.

The app's own name is now written from the manifest as well: `tools/axml_label.py` names the app
(`<application android:label>` and every component sharing that reference), so the T1 acceptance
listing above is short by two files. `README.md` describes what that edit does and `AGENTS.md` what it
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
