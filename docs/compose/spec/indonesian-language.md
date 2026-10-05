---
feature: indonesian-language
status: delivered (device-verified: launch and lobby, 2026-10-05)
updated: 2026-10-05
branch: master
---

# Indonesian Language

## Report

**What was built** — a patch can now install Bahasa Indonesia instead of English, chosen on a language
setting in both front ends. The pipeline is unchanged in shape: `build_patch` still takes one catalog
path, and the path *is* the language.

- `tools/languages.py` names the languages (`en` → `resources/catalog/`, `id` → `resources/catalog_id/`),
  resolves a catalog directory to its language by name (`for_catalog`), and resolves a texture payload
  (`payload_path`): the language's own file when it ships one, the English catalog's beside it otherwise.
- `resources/catalog_id/catalog.json.gz` is the Indonesian catalog from the PC pipeline: same schema,
  same 499 tables and 398 graphics entries as the English one, Indonesian targets.
- The lobby's START GAME label is re-drawn as MULAI GAME. The art is
  `resources/catalog_id/previews/863114A42F12EF76.png` (the `mulai_game.png` the user supplied, renamed to
  the English catalog's `previews/<HASH>.png` convention), and `tools/research/make_language_payloads.py`
  turns it into payloads named exactly as the English ones they replace:
  `863114A42F12EF76.blocks` (the standalone 372x102 RGBA32 label) and `C9F49510F2F67402.blocks` (the BC7
  atlas whose `start_game` sprite is the same pixels). Every other texture edit is the English one.
- `{Energy}`/`{LordExp}`/`{LordHp}` expand to the language's terms (`Language.resource_terms`):
  Indonesian writes `Energy`, `EXP Chessplayer`, `HP Chessplayer`, the order its own catalog uses.
- `device_patch_summary.json` gains `language`, and the run logs `language: <name> (<catalog dir>)`.
- Windows: a LANGUAGE selector in `app/hok_patcher.py`, saved beside the working folder in
  `%APPDATA%\HOKAceEnglishPatcher\settings.json`; `Patcher(ui, work, language)`; `--selftest <game> <out>
  [language]`; `build_exe.py` ships `catalog_id/` beside `catalog/`.
- Android: a Language card on the home screen (`GuidedHome`, `PatchLanguage`), locked while work runs;
  `PatchCoordinator` reads it once per run, reports it, records it in the journal's `BUILDING` outcome and
  passes it to `estimate_snapshot_build` / `build_snapshot`; Gradle stages `engine/catalog_id/` into the
  verified engine manifest. The bridge's `language` argument defaults to `en`, so the existing
  instrumentation tests call it unchanged.

**Verification** — Python 3.12.13 (`.venv`), from the project root. The game dump is the pristine
1.4.0.2 snapshot `dist/HOK ACE Patcher Data/pristine/20261003-173730/game` with the cached
`installed.apk`; outputs went to disposable folders under `dist/`.

| Check | Result |
|---|---|
| Catalog identity: `catalog_id` vs `catalog` | same keys, 499 tables, 398 graphics entries (graphics list identical), 39 011 `unique` sources, 29 750 `english_updates` |
| Atlas sprite vs standalone label (`C9F49510F2F67402` `start_game` box vs `863114A42F12EF76`) | mean difference 0.83 at offset (0,0), 9.3 at the next best — the same pixels |
| BC7 mode-6 encoder round-trip through `texture2ddecoder` | gradient and edge blocks within 0.64/255; uniform random noise is inherently lossy in a single-subset mode |
| `make_language_payloads.py` then `--check` | both payloads `ok`; atlas sprite mean error 2.25/255 against the render |
| `english_raw` on synthetic device textures (6x6 and 4x4 for the label, 4x4 for the atlas) with `catalog_id` | all applied, all differ from the English result, renders read MULAI GAME; the atlas's BATTLE TRAINING keeps its English edit |
| Full offline build, `--catalog resources\catalog_id` with the APK | exit 0; `language: Bahasa Indonesia`; **391 tables, 395 textures**, `text_skipped` and `graphics_skipped` empty, `append_skipped` one table (`0196F0E230EC1C70`, the encoder refusal the English run also has); 3382 token expansions |
| Staged package `19`, decoded off the device ASTC | `863114A42F12EF76` (6x6) and `C9F49510F2F67402` (4x4) both read MULAI GAME |
| Staged tables decoded | 149 of 150 sampled Indonesian strings present; `EXP Chessplayer` 797x, `HP Chessplayer` 982x, `Chessplayer EXP`/`Chessplayer HP` 0x, no raw token left |
| English regression: `tools/` at HEAD (`e919a1d`) vs this change, `--catalog resources\catalog`, same dump and APK | **byte-identical** — all 12 staged `.db` files share SHA-256; the summary differs only by the new `"language": "en"` |
| Language switch: the Indonesian catalog's `translate_table` over the 387 tables of that English-staged output | **0 tables changed** (339 671 records: 96 860 `already_english`, 211 `unknown`, none translated) — text does not switch over an English install; the re-drawn textures would |
| Storage estimate (`build_storage.estimate`) | English 40 333 418 catalog bytes, Indonesian 40 730 543 — the borrowed English payloads are counted |
| GUI construct + picker (`hok_patcher.App`) | picker shows the saved language; choosing Indonesian writes `{"language": "id"}` without losing `work_dir`; `Patcher` resolves `resources\catalog_id` |
| `android\gradlew.bat -p android --offline :app:assembleDebug :app:assembleDebugAndroidTest` | BUILD SUCCESSFUL; the APK carries `engine/catalog_id/*` and `tools/languages.py`, all in `engine/manifest.json` |

**Device cycle (2026-10-05, Xiaomi M2007J3SG `f15a72e`, Android 12, game data 1.4.0.2)** — the phone
already carried the English patch from the Android app's live run, so the cycle followed `prime-rebuild.md`'s
device test loop with the Indonesian build rather than a normal app run (which would have changed no text,
T8). Evidence: `artifacts/indonesian-device-cycle-20261005.log`, `artifacts/indonesian-lobby-20261005.png`,
`artifacts/indonesian-popup-20261005.png`.

| Step | Result |
|---|---|
| Installed game APK | `29b3ee7e…` — not the cached `installed.apk` (`b0b08f…`): the two differ only in `AndroidManifest.xml`, all 1625 other entries (every prime package included) identical, signed with the project key, not debuggable. The phone's own APK was used as the restore target and the access APK built from it |
| First attempt, staged from the 10-03 pristine dump | **aborted before any write**: the phone held 731 package files against the dump's 653 — the game had downloaded more under the same `1.4.0.2` label, so a push from the dump would have reverted it. Normal APK restored and verified |
| Build base | the phone's own layer, with the six English-patched packages (`1`, `15`, `19`, `20`, `21`, `1050016095`) put back to the dump's copies: in all six every asset outside the translation is byte-identical to the dump and the only extra entries are our own appends, so the game had not touched them |
| Indonesian build on that base, `--apk phone.apk` | 391 tables, 395 textures, the same six packages; `append_skipped` the one known table. The newly downloaded packages hold no catalog content |
| Push | fresh backup matched the base except exactly the six packages; 6 packages written, Watchdog cleared, on-phone read-back **12/12** SHA-256 match; normal APK restored (`29b3ee7e…`, no `DEBUGGABLE` flag). Rollback material kept in `dist/HOK ACE Patcher Data/id-device/` (`device-backup-2.tar`, `access-phone.apk`, `phone.apk`) |
| Launch | game alive past 80 s (PID 11908); logcat has no QtsVFS error, fatal signal or `IsPrebuild` line; the session was still logged in |
| Lobby | **MULAI GAME** on the start button; Indonesian labels (Toko, Harapan, Top-up Pertama, Peringkat, Kartu, Kesejahteraan, "Undang ke tim", "2 hari 3 jam", "Jangan tampilkan hari ini"). Labels still in English — Menu, Event, Trading Post, Growth Path, Battle Pass, Precious Prayer, Lineup, Chessplayer — are the Indonesian catalog's own values for those sources |

**Journey log**

- The user supplied only `catalog.json.gz` and `mulai_game.png`. The catalog turned out to be a drop-in for
  the English one rather than a new format: `adaptive.load_catalog(folder)` reads `folder/catalog.json.gz`,
  and the `.blocks`/`.assets` files are texture payloads, not text.
- Two textures draw START GAME in package `19`. Which one the lobby uses cannot be read from the data, so
  both are re-drawn; they are the same pixels, so one render serves both.
- No BC7 encoder is installed (only `texture2ddecoder`'s decoder), so the converter carries a small mode-6
  encoder and re-encodes only the blocks the sprite touches. The device never sees BC7 — the texture pass
  decodes it and re-encodes ASTC — so its job is only to carry the render into the catalog's format.
- The user asked whether the token terms could be fixed in the catalog. They cannot: `translate_table`
  requires matching placeholders, so a pre-expanded target trips `placeholders_changed` and the record is
  dropped (`resource-token-expansion.md`). The terms became a per-language table instead.
- **Measured gap: game-shipped English stays English.** The Indonesian catalog translates Chinese
  sources (`unique`) and re-targets only the 29 750 `english_updates` rows the English catalog already had.
  Records the game itself ships in English have no row, so `translate_table` leaves them as they are:
  20 228 of 324 905 records in the staged tables (6%) are English text the English catalog maps from a
  Chinese source the Indonesian one also translates — mostly package `1`'s prime-only tables
  (`C40FFFB4C9180D66` alone holds 4522, e.g. "AI impersonates avatar 1181"). The fix belongs in the
  catalog (more `english_updates` rows), not in a pass here.

## [S1] Problem

The patcher installs one language. An Indonesian catalog exists; the lobby's START GAME button is a
texture and needs an Indonesian image; and the resource tokens expand to English word order.

## [S2] Design

- **The catalog directory is the language.** A `language` argument beside `catalog` could disagree with
  it; deriving one from the other cannot. Every caller already passes a catalog path, so only the callers
  that choose one (the two front ends) change.
- **A language ships only what it re-draws.** Copying the 40 MB of English payloads into each language
  would ship them twice; `payload_path` falls back by file name instead. The re-drawn payload keeps the
  English file's name and the catalog's own metadata (`format`, `patch_ranges`, geometry), so the texture
  pass needs no language-specific branch. `adaptive.scan` also reads a payload, but only for an asset whose
  SHA-256 is the PC source texture's, which a device ASTC texture never is.
- **Payloads are generated, the render is the source.** `make_language_payloads.py` rebuilds them from
  `previews/` and `--check` proves the shipped ones are current, the same relation the English previews
  have to their payloads.
- **One language per run.** Android reads the setting once per run and locks the picker while work is in
  progress; Windows disables it while a run is active.

## [S3] Out of Scope

- Translating the strings the game ships in English (the measured gap above): needs catalog rows.
- Re-drawing other English texture edits in Indonesian: each needs its own render under `previews/` and a
  `LABELS` entry.
- **Switching an already-patched install between languages.** The scanner only translates tables that
  still hold Chinese (`README.md`'s known limits), so text switches only after the game's data is reset;
  textures switch on any run, which would leave MULAI GAME over English text. Both pickers say to clear
  the game's data before switching (measured in T8).

## Tasks

- [x] T1 `tools/languages.py`; payload fallback in `mobile_graphics`; per-language token terms through
  `build_device_patch`, `package_rebuild`, `extra_text`, `device_extensions`; `language` in the summary.
- [x] T2 MULAI GAME render and payloads; `tools/research/make_language_payloads.py`.
- [x] T3 Windows language selector, saved setting, `--selftest` language, `build_exe.py` data.
- [x] T4 Android language card, coordinator/journal/bridge plumbing, Gradle staging, storage estimate.
- [x] T5 Offline Indonesian build against the 1.4.0.2 dump.
- [x] T6 Docs: `AGENTS.md`, `README.md`, `android/README.md`, `translation-progress.md`, this record.
- [x] T7 English regression byte-compare (HEAD `tools/` vs this change).
- [x] T8 Measure a language switch over an already-English install; picker hints added.
- [x] T9 Device cycle: Indonesian run on the phone; lobby shows MULAI GAME; the game starts and reads
  Indonesian (launch and lobby; see *Device cycle*).
- [ ] T10 Walk the remaining screens in Indonesian after login: loading tips, Chessplayer page, Card menu,
  arena artwork.
