---
feature: indonesian-language
status: delivered (device-verified: launch and lobby, 2026-10-05)
updated: 2026-10-16
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

**Journey log**

- The supplied catalog is a drop-in for the English one; its `.blocks`/`.assets` files are texture payloads, not text (lab notebook, 2026-10-05).
- Two package-`19` textures draw START GAME and the data does not say which the lobby uses — both re-drawn from one render (lab notebook, 2026-10-05).
- No BC7 encoder is installed — the converter carries a small mode-6 encoder for the blocks the sprite touches (lab notebook, 2026-10-05).
- Fixing the token terms in the catalog — impossible, `placeholders_changed` drops the record; a per-language table instead (lab notebook, 2026-10-05).
- Records the game itself ships in English stay English in Indonesian — measured at 6% of staged records; a catalog fix, not a pass ([S3]) (lab notebook, 2026-10-05).
- Device cycle from the 10-03 pristine dump — aborted before any write, the phone held newer data under the same version label (lab notebook, 2026-10-05).
- Device cycle from the phone's own layer — launch clean, lobby reads MULAI GAME and Indonesian labels (lab notebook, 2026-10-05).
- Device report's four bugs (`通用` filter label, Armed Power's band, the QTS-failure popup, the Announcement header), three of them in English too — all fixed and verified on their screens (lab notebook, 2026-10-05).
- Catalog review: hallucinated religious text, false friends, corrupted `≥`/`≤` and drifting terms — purged and normalized, made re-applicable by `tools/research/apply_catalog_fixes.py`; the wording rules are in [S2] (lab notebook, 2026-10-08).

### Still owed

The device cycle covered launch and the lobby, and the device report's four fixes were verified on
their own screens. The other screens have not yet been walked in Indonesian
after login: the loading tips, the Chessplayer page, the Card menu and the arena artwork. Each walk
follows the [device cycle](../runbooks/device-cycle.md).

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

- **Indonesian catalog wording** (from the 2026-10-08 review; corrections go through
  `tools/research/apply_catalog_fixes.py`, never a hand edit of the gzip):
  - *Kept in English:* `Deploy`, `Combine`, `Level`/`Lv.`, `Hero`, `Skin`, `Skill`, `Passive`, `Ultimate`,
    `Damage`, `True Damage`, `Physical Attack`, `Magic Attack`, `Physical Defense`, `Magic Defense`,
    `Shield`, `Lifesteal`, `Spell Vamp`, `Crit`, `Buff`, `Debuff`, `Stack`, `Stun`, `Knockup`,
    `Knockback`, `Stealth`, `Lineup`, `Tier`, `Reroll`, `Refresh`, `Shop`, `Diamond`, `Token`, `Coupon`,
    `Chessplayer`.
  - *Indonesian:* `Pemain` (player), `Ronde` (round), `Pengguna`/`Pemakai` (an item's wearer),
    `Memberikan`/`Memperoleh` (grants, gains).
  - *False friends, never written:* `hibah` (grants), `pemutar` (player), `kulit` (skin),
    `kolam renang` (card pool), `wajik` (diamond), `pembawa berita` (wearer), `kebakaran rubah`
    (Fox Fire), `cairan darah mantra` (Spell Vamp), `ruang suai` (Custom Room).
  - *`使用`:* an imperative is `Gunakan`, a verb after `bisa`/`dapat`/`untuk` is `menggunakan`, a genuine
    noun is `penggunaan`; a raw English `Usage` never stays in an Indonesian sentence.
  - *Symbols:* a `£` the machine translation left in a condition is `≥` (or `≤` where the source reads
    `<=`), and a corrupted circled digit is restored from the source.
  - *Series labels* read `Seri <keyword>` (`Seri General`, `Seri Effect Card`), the order the terminology
    table also writes.

## [S3] Out of Scope

- Translating the strings the game ships in English (the measured gap above): needs catalog rows.
- Re-drawing other English texture edits in Indonesian: each needs its own render under `previews/` and a
  `LABELS` entry.
- **Switching an already-patched install between languages.** The scanner only translates tables that
  still hold Chinese (`README.md`'s known limits), so text switches only after the game's data is reset;
  textures switch on any run, which would leave MULAI GAME over English text. Both pickers say to clear
  the game's data before switching (measured: the Report's language-switch row).
