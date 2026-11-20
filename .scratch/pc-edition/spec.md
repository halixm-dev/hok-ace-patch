# PC edition: the Windows patcher installs the translation into the game on the same computer

Status: needs-triage

Tickets: [`issues/`](issues/) 01–05. Settled through grilling rounds 1–3 and a round on code shape and speed (2026-11-20). Decision record: [ADR 0011](../../docs/adr/0011-keep-every-file-the-pc-launcher-lists-at-its-listed-size.md). Vocabulary: **PC edition**, **mobile edition**, **receipt**, **PC cycle** in [`GLOSSARY.md`](../../GLOSSARY.md).

## Problem

The Windows patcher only patches a phone. Players with the PC edition (`WXQ.exe`) have two options today, and neither is this project's:

- the upstream PC patcher, which installs English only;
- the azydev fork (`hok-ace-patcher` 1.10.1.3), which adds an Indonesian interface and a PC page on top of a copy of this repo.

The fork's PC page works, but it copies this repo's engine and catalogs by hand and has to be re-synced with every release. It hard-codes Indonesian messages and swaps runtime attributes in place. It also misses token expansion.

The goal is to add the PC edition to this repo's Windows patcher, in both languages, from the same catalogs. It should add as little new code as possible and reuse the runtime engine, the catalogs and the texture pipeline that already exist.

## Evidence

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

## Solution

The Windows patcher gets a target choice, *Phone over USB* or *PC game on this computer*. The language card is shared, and it still sets the interface language.

The PC target has a game-folder row and three actions: **Install**, **Check** and **Remove translation**. Check runs by itself when the target opens and shows one of four states: *installed*, *not installed*, *replaced by an update* or *partly installed*.

Behind it, the runtime engine writes the files. This repo builds the per-install catalog the engine reads, holds the receipts in the working folder, and owns every hook into the engine.

## Implementation Decisions

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
- **Lua:** the Lua label and the nine Lua edits (`extra_text.SCRIPT_ASSETS`), each a whole-file entry with no `patch_ranges`, rewritten by `extra_text.rewrite_script`.

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

## Testing

No test suite. Each slice proves itself with the offline checks below; the PC edition itself is proved by a PC cycle (`docs/runbooks/pc-cycle.md`, written in ticket 04).

- **`tools/research/check_pc_install.py --game <scratch copy> --work <dir>`** drives `pc_edition.run` against a scratch copy of the PC edition's `builtin` packages, in each language. The run goes install → check → install → restore → install the other language → restore, and asserts each of these:
  - restore returns every file to its original bytes;
  - a second install changes nothing;
  - the language switch goes through the receipts;
  - `replacements\` is empty before each job;
  - no file listed in `LocalFileList.json` changes.
- **`tools/research/check_graphics.py`** BC7 case: a ported atlas round-trips, and a re-run re-encodes nothing.
- **Mobile unchanged:** `--selftest` on a mobile dump gives an identical `device_patch_summary.json` and identical staged bytes before and after slice 1.
- **`--smoketest`** imports `engine_hooks`, `pc_catalog` and `pc_edition`, checks the three engine attributes exist, and encodes one BC7 block.
- **Speed:** wall time of Install, a repeat Install and Check, fork vs this repo, on the same scratch copy. Recorded in `docs/lab-notebook.md`.

Measured in a PC cycle, never assumed:
- in-game English and Indonesian;
- text wrapping (the line-break Lua edit);
- the regioned atlases and Secret Technique titles at their PC sprite rects;
- MULAI GAME on both lobby textures;
- token-expanded card text;
- the launcher starting without a repair;
- a launcher update followed by Check (*replaced by an update*) and Install.

## Out of Scope

- Translating the PC window title, or changing the size of any file the launcher lists (ADR 0011).
- Any config bin on the PC edition, the lineup bin included, until a PC cycle clears it.
- Importing the fork's or the upstream PC patcher's receipts or state.
- Stop safely and automatic continuation for PC jobs.
- A drive scan to find the game.
- Patching the PC edition from the Android patcher, or a phone from the PC target.
- A separate PC-only exe.
- A native BC7 encoder, unless ticket 01 measures the pure-Python one as the slow step.
