---
feature: pc-edition
status: built; PC-cycle-tested in English and Indonesian (switch and Remove translation included) on launcher 26111.0.4.30004, data 1.11.0.2
updated: 2026-11-21
branch: feat/pc-edition-05-cycles
commits: 4b01ed9..291404f
---

# PC edition: the Windows patcher installs the translation into the game on the same computer

Vocabulary: **PC edition**, **mobile edition**, **receipt**, **PC cycle** in [`GLOSSARY.md`](../../GLOSSARY.md).
Decision record: [ADR 0011](../adr/0011-keep-every-file-the-pc-launcher-lists-at-its-listed-size.md).
Runbook: [PC cycle](../runbooks/pc-cycle.md). Receipts and the language switch:
[language-switch](language-switch.md#the-pc-edition-receipts-restore-then-install). BC7 ports:
[texture-translation](texture-translation.md).

## Windows patch 1.11.2.1

The PC workspace places status and patch actions beside the game folder, working folder and language.
The activity log spans the window below. The setup moves below the actions in a narrow window.

PC preflight hashes each distinct game file once when comparing the saved state and receipts.
Post-install verification reads the new bytes. The Windows UI receives log lines and results from
a worker that monitors the child process.

| What Check finds | Next action |
|---|---|
| The whole translation was replaced | **Reapply translation** builds against the updated game files. |
| An older bundled translation is installed | **Update translation** restores its saved originals, then installs the bundled patch. |
| Another language is installed | **Switch language** restores its saved originals, then installs the selected language. |
| A patch job was interrupted and its recovery is available | **Recover and install** lets the engine recover before retrying. |
| The launcher left a mix of translated and updated files, or Check finds another patcher's files | Use **Repair** in the game launcher, close it and run **Check**. |

## Report

### What landed

The runtime can read QtsVFS indexes and shard slots and translate localization tables through
`hok_codecs`. The Python runtime still drives the PC job and verifies staged packages.

Five slices, stacked (halixm-dev/hok-ace-patch #41, #43, #44, #45 and ticket 05's PR):

1. **Offline pipeline**: `tools/engine_hooks.py` (terminology on `load_catalog`, token expansion on
   `scan`, our `receipt_root`), `tools/pc_catalog.py` (the per-install catalog, staged once, hard-linked
   and cached), `tools/bc7_mode6.py` and `mobile_graphics.port_atlas(codec="bc7")`, with etcpak as the
   first BC7 encoder.
2. **PC workflow**: `app/pc_edition.py` (finding the game, the process guard, receipts in
   `<work>\pc\receipts\<game-id>\`, `state.json`, the `--pc-job` child, `--pc-selftest`) and
   `tools/research/check_pc_install.py`.
3. **Interface**: the target choice and the PC card in `app/hok_patcher.py`, every string a key in
   `resources/ui/strings.json`.
4. **Docs**: AGENTS.md's *PC edition* constraints, README, the PC cycle runbook, the PC column in
   `translation-progress.md`.
5. **PC cycles** on the installed game.

### Verification

| Check | Result |
|---|---|
| `check_graphics.py` BC7 case (ticket 01) | All sections pass; a re-run over its own output re-encodes 0 blocks |
| Mobile `--selftest` before and after slice 1 | `selftest.json` and all 14 staged files identical, both languages |
| `check_pc_install.py` on a full copy, `en:id` and `id:en` (ticket 02) | `OK`: restore returns every file, a second install changes nothing, each switch restores then installs, `replacements` empty at each start, `LocalFileList.json` and every listed size held |
| `--smoketest` on the frozen exe | `ok`, with `import pc_edition`, `engine hook attributes`, `bc7 round trip` and `bc7 native search` |
| `--pc-selftest` on the frozen exe | `ok` in both languages, 359 graphics each, the ready atlas `E86DF43167CA2143` refused at this sprite table |
| The window from source on the copy (ticket 03) | Check, Install (6:52), Remove (0:29) and every state drawn as designed |
| PC cycle, English (2026-11-21) | Install 410 s; the launcher started with no repair; lobby English; wrapping, token-expanded card text, the Career labels and the Secret Technique titles in place. **Pass** |
| PC cycle, Indonesian | Install through the receipts 509 s; the launcher started with no repair; lobby Indonesian; the same screens in place. **Pass** |
| Switch back to English | 411 s; every file under `builtin` byte-identical to the first English install. **Pass** |
| Remove translation | 31 s; every file back to its starting SHA-256; Check *not installed*; the launcher accepted the files with no repair. **Pass** |

The numbers are in the [lab notebook](../lab-notebook.md), 2026-11-20 "PC edition ticket 01" and
"ticket 02", and 2026-11-21 "PC edition ticket 05". `check_references.py`, `check_staging_contract.py`
and `check_ui_strings.py` pass on the final branch.

### Journey

- **BC7 was the slow step** (ticket 01): etcpak 0.9.15 was added as the first encoder, and BC7 blocks
  are judged by `BC7_MATCH_MEAN` = 14 while ASTC keeps 6, because no encoder brought the alpha'd
  title-edge blocks within 6 levels (user's decisions). The pure-Python `bc7_mode6` stays as the fallback.
- **Mode 7 went native** (2026-11-26, `.scratch/pc-bc7-rust/`): the Python modes' mode 7 was the rest of
  the cold build. `crates/hok_bc7` (Rust, PyO3) is a bit-exact port of `bc7_mode6._mode7_python`, frozen into
  the exe as `hok_bc7`. etcpak and modes 6, 5 and 4 are unchanged. Source runs use it when
  `build\native\hok_bc7.pyd` is built and fall back to Python otherwise. Cold builds fell from 80 s to
  28 s (English) and from 78 s to 31 s (Indonesian), with byte-identical catalogs.
- **Modes 6, 5 and 4 went native** (2026-11-26, `.scratch/pc-bc7-search/`, on the user's request): after
  mode 7 they were over half of the cold build. `crates/hok_bc7` now runs `encode_block`'s whole search
  past etcpak (`encode_search`), each mode a bit-exact port of the Python reference, which stays for
  source runs without the extension. `HOK_BC7_ENCODER=native|python` (formerly `HOK_BC7_MODE7`)
  requires one or the other. Cold builds fell again, from 28 s to 15 s (English) and from 31 s to 13 s
  (Indonesian), with byte-identical catalogs. Parity is checked by `tools/research/check_bc7_native.py`
  and `bc7_corpus.py replay --backend native --final`.
- The full BC7 encoder now runs through `hok_codecs`, including the first block candidate and its
  pixel comparison. Source runs can still use `hok_bc7` for the search and etcpak for the first
  candidate. `HOK_BC7_ENCODER=python` selects the Python reference.
- **ADR 0011 was reworded** (ticket 02): every package file the engine patches is listed in
  `LocalFileList.json`, contrary to the fork's note, so *never write a listed file* became *keep every
  listed file at its listed size*. The PC cycles confirmed the launcher compares sizes.
- **Restore receipts**: the engine keeps an undone install receipt until its next run, so a completed
  restore cancels the install receipts before it, and the engine's 4 GB `staged` folder is removed after
  every job.
- **The start button's event skin**: in the PC cycles the lobby showed an event skin of the start button
  (开始游戏, "Super Weekend Perks Are Here!") that the catalog does not carry. It stays Chinese in both
  editions and hides the two START GAME textures, which are verified on disk in each language (read
  back from package `19` with the stage's `patched_sha256`). User's decision: the cycles pass, and the
  event button is a coverage gap of its own.

### Still owed

*After a launcher update* (Check reads *replaced by an update*, then Install reaches the lobby
translated) waits for an update that ships while a translation is installed: the one update during the
cycles came before any install. The PC cycles ran from source, not from the frozen exe, and did not
include a match start and end. MULAI GAME is verified on disk, not on screen, until the event skin
leaves the lobby.

## [S1] Problem

The Windows patcher only patches a phone. Players with the PC edition (`WXQ.exe`) have two options today, and neither is this project's:

- the upstream PC patcher, which installs English only;
- the azydev fork (`hok-ace-patcher` 1.10.1.3), which adds an Indonesian interface and a PC page on top of a copy of this repo.

The fork's PC page works, but it copies this repo's engine and catalogs by hand and has to be re-synced with every release. It hard-codes Indonesian messages and swaps runtime attributes in place. It also misses token expansion.

The goal is to add the PC edition to this repo's Windows patcher, in both languages, from the same catalogs. It should add as little new code as possible and reuse the runtime engine, the catalogs and the texture pipeline that already exist.

### Evidence

Read from the fork and from `resources/runtime/` on 2026-11-20. Not yet measured in the PC edition by this repo.

- **The engine already installs into the PC edition.** `wxq_patch.adaptive.run(action, game, assets, work)` takes `install`, `restore` and `status`. It writes packages in place under `WXQ_Data\Package\builtin\<id>\`, keeps receipts, verifies each texture against the catalog's `patched_sha256`, and recovers its own pending files (`recover_pending`). `installation.discover_installations` and `resolve_game_root` find the game. The fork drives exactly this.
- **The fork's runtime and catalog match ours.** `resources/runtime/` is byte-identical to ours, and so is `catalog/catalog.json.gz`.
- **Receipts default to a shared folder.** `adaptive.receipt_root(game)` returns `%LOCALAPPDATA%\HoK Ace English Patch\adaptive\<sha256(path)[:24]>`. That's the upstream PC patcher's folder.
- **Token expansion has a hook point.** `adaptive._run` calls `scan` through its module attribute, so a wrapper can expand tokens after the scan. This is the same mechanism `terminology.install` already uses on `load_catalog`.
- **The PC edition re-packed the regioned atlases, as the mobile edition did.** The fork found the Career atlas moved in 1.5.0.1, and the lobby atlas's START GAME sprite moved in 1.10.1.2. Its PC sprite table is in package 19. The fork ports the atlases with `mobile_graphics.port_atlas(..., codec="bc7")` and its `tools/bc7_mode6.py` encoder. Our `port_atlas` decodes only ASTC on the device side.
- **The Lua scripts are the same.** The PC edition carries the same Lua scripts in package 10 (fork, 2026-11-18). The fork adds each edited script as a whole-file catalog entry with no `patch_ranges`, and the engine accepts it.
- **Indonesian re-draws ship as payloads already.** `catalog_id/` already carries the MULAI GAME payloads for the button `863114A42F12EF76` (raw RGBA) and the lobby atlas `C9F49510F2F67402`. The engine checks each texture against `patched_sha256`, so on the PC edition a re-drawn payload needs its hashes recomputed from the installed original. The fork does this in `_redrawn_payloads`.
- **The fork learned these from user reports:**
  - The launcher repairs any file it lists in `LocalFileList.json`, and a repair also empties `builtin` (ADR 0011).
  - A running game or launcher makes the engine fail with WinError 32.
  - The engine never empties `<work>\replacements\`. A file left there for an asset a game update removed stops the next install (`... is absent from package 19`, 2026-11-18).
  - After a launcher update, the engine drops receipts that no longer describe the files. A language switch then has nothing to restore.

## [S2] Design

The Windows patcher gets a target choice, *Phone over USB* or *PC game on this computer*. The language card is shared, and it still sets the interface language.

The PC target has a game-folder row and three actions: **Install**, **Check** and **Remove translation**. Check runs by itself when the target opens and shows one of four states: *installed*, *not installed*, *replaced by an update* or *partly installed*.

Behind it, the runtime engine writes the files. This repo builds the per-install catalog the engine reads, holds the receipts in the working folder, and owns every hook into the engine.

### Code shape

Three new modules. `patcher_core` stays untouched; the GUI talks to `patcher_core` for the phone and to `pc_edition` for the PC edition, and AGENTS.md's *Flow* line says so.

- **`tools/engine_hooks.py`** holds every hook into the runtime:
  - `load_catalog`: terminology. `terminology.install` moves here, and the mobile pipeline calls it from here.
  - `scan`: token expansion, PC edition only.
  - `receipt_root`: our receipts folder, PC edition only.

  `install()` puts them in place once and is idempotent. `--smoketest` fails if any of the three attributes is missing from the runtime.
- **`tools/pc_catalog.py`** builds the per-install catalog: pure pipeline code with no GUI.
- **`app/pc_edition.py`** holds everything else for the PC target:
  - finding the game;
  - the process guard;
  - the receipts root;
  - the state file;
  - engine failures mapped to `PatchError` keys from `strings.json`;
  - the ~20-line `--pc-job` child entry.

Token expansion is shared, not copied. `build_device_patch._expand_staged_tokens` moves into `resource_tokens` as one function. The mobile pipeline keeps calling it where it does today, and the PC `scan` hook calls the same function. Mobile staged bytes stay identical.

### What the per-install catalog carries

It starts from the language's catalog (`catalog/`, or `catalog_id/` with its payloads over `catalog/`) and adds these:

- **Text tables:** the catalog's own, with the catalog supplement and the terminology table through `load_catalog`, and resource tokens expanded through `scan`.
- **Catalog edits:** as the catalog has them; the engine places them at their PC offsets.
- **Regioned atlases:** every atlas in `sprite_table.REGION_SPRITE_ASSETS`, ported at the PC edition's own sprite table from package 19. That covers the Career, lobby, ready and Secret Technique title atlases, with the art in `resources/sprites/`. As on the mobile edition, a missing or moved region refuses the texture (ADR 0006).
  - The result replaces the catalog entry: payload, `patch_ranges` and all three hashes describe exactly the blocks this installation needs.
- **Indonesian re-drawn payloads:** their `payload_sha256` and `patched_sha256` are recomputed from the installed original. An entry whose source matches neither the catalog's `source_sha256` nor this patcher's last result is left for the engine to skip.
- **Lua:** the Lua label and the Lua edits (`extra_text.SCRIPT_ASSETS`), each a whole-file entry with no `patch_ranges`, rewritten by `extra_text.rewrite_script`.

Not carried:
- append (there is no prime layer);
- card-dictionary chunk gains;
- any config bin.

The **allowlist is per edition**: a bin a device cycle cleared is still untranslated on the PC edition until a PC cycle clears it there. `translation-progress.md` gets a PC column, and it states textures as *applied*, never *covered*.

### Shared texture code

- `mobile_graphics.port_atlas` gains `codec: "astc" | "bc7"`. It decodes and re-encodes in the texture's own codec, and everything else stays shared. The 4×4 block grid and 16-byte blocks are the same in both.
- `tools/bc7_mode6.py` comes over as the BC7 encoder.
- `tools/research/check_graphics.py` gains a BC7 case.
- The pure-Python encoder stays unless ticket 01 measures it as the slow step. A native encoder would be a new dependency for the freeze.

### Speed

Each item is timed against the fork in the lab notebook.

1. **One stage per run, hard-linked.** The per-install folder `<work>\pc\<game-id>\catalog\` is built once:
   - bundle payloads are hard-linked, and copied only when the working folder is on another drive;
   - only the overrides and `catalog.json.gz` are written.

   It is named after the language's catalog folder, because `languages.for_catalog` reads the language from that name.
2. **Open only the packages the catalog names.** Catalog edits carry their package. The Lua scripts' PC package (10) is recorded next to `extra_text.SCRIPT_EDITS`. A full index scan runs only when a script isn't there, and it logs that it did.
3. **Cache the stage.** It is keyed by `VERSION`, the language, and the hashes of the game assets it read. Check, and an Install with nothing changed, reuse it: no atlas decode, no BC7 encode.

### Receipts, state and undo

- **Receipts live in `<work>\pc\receipts\<game-id>\`**, owned by this patcher alone and never in the engine's default folder. Receipts are the PC edition's only undo record; the pristine delta stays mobile-only.
- **One state file per game:** `<work>\pc\<game-id>\state.json`, holding the installed language and the patched hashes from the last verified install. `<game-id>` is the engine's own identity, `sha256(resolved path, casefolded)[:24]`.
- **`<work>\replacements\` is emptied** before every Install and Check. It is engine build output; the originals are in the receipts.
- **Language switch:**
  - It restores from the receipts first, then installs.
  - When no receipts remain, because a launcher update replaced the files, it goes ahead.
  - When receipts exist but don't match the files, it stops before any write. The player is told to use the launcher's *repair* and then Install again.
- **Nothing is imported** from the fork (`receipts\`, `pc-installed-language.json`, `pc-graphics-state.json`) or from the upstream PC patcher (`%LOCALAPPDATA%` receipts). When Check finds the game already translated, or its window title changed, with no receipts of ours, Install refuses with the same repair advice. We never write the title back ourselves (ADR 0011).

### Running a PC job

- **Process guard:** Install, Check and Remove translation run only while neither `wxq*.exe` (the engine's own check) nor `王者万象棋.exe` is running. Processes are listed through `CreateToolhelp32Snapshot`, because `tasklist` mangles the launcher's name. This also keeps an install from starting while the launcher updates, mirroring ADR 0002 for the PC edition.
- **Check in the window:** pending recovery, saved file hashes and the window title establish the state where possible. A fresh or updated game is scanned with the bundled catalog to detect translations installed by another patcher. The per-install catalog is built for Install and for detailed command-line checks.
- **Child process:** each job runs as a low-priority child, the exe re-invoked as `--pc-job <action> <game> <work> <answer.json> <language>`. It answers through a JSON file written atomically. The engine holds the GIL for minutes and would freeze the window.
- **Selftest:** the same entry point gives a headless `--pc-selftest <game-copy> <out>`.
- **No Stop safely or automatic continuation** for PC jobs. The engine's `commit` is transactional and recovers its own pending files on the next run. Closing the window during a PC job asks the player to wait. ADR 0010's checkpoints stay mobile-only.
- **Finding the game:**
  - from the engine's launcher records (`installation.discover_installations`), or from a manual folder pick checked by `resolve_game_root`;
  - the chosen folder is remembered;
  - there is no drive scan.

### Interface

- **Target choice** at the top of the window. The phone steps are unchanged under *Phone over USB*.
- **PC target:** a game-folder row (found or picked) and **Install**, **Check** and **Remove translation**.
- **Strings:** every PC string is a key in `resources/ui/strings.json`, in both interface languages. Run `tools/research/check_ui_strings.py`.
- **Docs:** `DESIGN.md` and `PRODUCT.md` describe the PC target in the same change.

### Build order

Four slices, each its own branch and PR off `master`:

1. offline pipeline;
2. PC workflow;
3. interface;
4. docs.

Then one PC cycle per language before release.

## [S3] Out of Scope

- Translating the PC window title, or changing the size of any file the launcher lists (ADR 0011).
- Any config bin on the PC edition, the lineup bin included, until a PC cycle clears it.
- Importing the fork's or the upstream PC patcher's receipts or state.
- Stop safely and automatic continuation for PC jobs.
- A drive scan to find the game.
- Patching the PC edition from the Android patcher, or a phone from the PC target.
- A separate PC-only exe.
