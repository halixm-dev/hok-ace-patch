# 02: The PC workflow and its child job

**What to build:** `app/pc_edition.py`, the one module the GUI calls for the PC edition, plus its headless entry points. See the [spec](../spec.md): *Receipts, state and undo* and *Running a PC job*.

- **Actions:** `run(action, game, work, language)` for `install`, `status` and `restore`, through `engine_hooks.install(pc=True)` and `pc_catalog`.
- **Before each job:**
  - the receipts root is `<work>\pc\receipts\<game-id>\`;
  - `<work>\replacements\` is emptied before Install and Check.
- **State:** `<work>\pc\<game-id>\state.json` holds the installed language and the verified patched hashes.
- **Check's four states:** installed, not installed, replaced by an update, partly installed.
- **Language switch:** restore first, then install. It goes ahead when no receipts remain, and refuses with repair advice when receipts don't match the files.
- **A foreign install:** a game found translated (or with a changed title) with no receipts of ours is refused with repair advice. Nothing is imported from the fork or upstream.
- **Process guard:** the engine's `wxq*.exe` check plus `王者万象棋.exe` through `CreateToolhelp32Snapshot`.
- **Errors:** every failure is a `PatchError` with a key in `resources/ui/strings.json`. That covers WinError 32, no matching receipt, an engine `error` state and a missing catalog.
- **Finding the game:** `installation.discover_installations` plus `resolve_game_root` for a picked folder, which is remembered. No drive scan.
- **Headless entry points:**
  - `--pc-job <action> <game> <work> <answer.json> <language>`: a low-priority child that answers atomically;
  - `--pc-selftest <game-copy> <out>`;
  - `--smoketest`, which imports the three modules, checks the engine attributes and encodes one BC7 block.
- **`tools/research/check_pc_install.py`:** the sequence in the spec's *Testing*, on a scratch copy, in each language.

**Blocked by:** 01

**Status:** needs-triage

- [x] `check_pc_install.py` passes in both languages: restore returns the original bytes, a second install changes nothing, the switch goes through the receipts, no `LocalFileList.json` file changes
- [x] `--smoketest` passes on the frozen exe (`app/build_exe.py` carries the new modules; check `HIDDEN_IMPORTS`)
- [x] `tools/research/check_ui_strings.py` passes

## Comments

2026-11-20, Claude (branch `feat/pc-edition-02-pc-workflow`, on top of ticket 01's branch):

- **`check_pc_install.py`, both languages:** `.venv\Scripts\python.exe tools\research\check_pc_install.py
  --game C:/scratch/pc-edition-02/game --work C:/scratch/pc-edition-02/work` on a full copy of the PC
  edition, launcher closed. It printed `OK` for both orders (`en:id`, `id:en`): install A, Check, install
  A again, install B, Check, restore. Restore gave every file under `builtin` its starting SHA-256 back,
  the second install changed nothing, each switch ran the engine's restore and then its install in one
  job, and `replacements` was empty at every engine start.
- **The launcher list, changed from the box above (user's decision):** every package file the engine
  patches is listed in `LocalFileList.json`, so "no listed file changes" cannot hold with this engine.
  The check instead asserts that `LocalFileList.json` keeps its bytes and every listed file keeps its
  listed size. Both held at every step. ADR 0011 is reworded and renamed to match; a PC cycle confirms
  the launcher accepts it.
- **`--smoketest` on the frozen exe:** `.venv\Scripts\python.exe app\build_exe.py`, then
  `"dist\HOK ACE Language Patcher.exe" --smoketest <out>` gives `ok: true`, with `import engine_hooks`,
  `import pc_catalog`, `import pc_edition`, `engine hook attributes` and `bc7 round trip` among the
  checks. `app/build_exe.py` names `pc_edition`, `pc_catalog`, `engine_hooks`, `bc7_mode6` and `etcpak`
  as hidden imports; `HIDDEN_IMPORTS` (the runtime's stdlib) needed nothing new.
- **`check_ui_strings.py`:** passes (412 strings). It now reads `app/pc_edition.py` too. Ten `pc_*`
  keys are new, Indonesian marked `draft`. A child's error comes back through `PatchError.rebuilt`.
- **Behaviour the spec left open, settled here:**
  - A switch whose receipts all still match restores first; one whose receipts match none of the files
    (a launcher update) goes ahead; one with some matching and some not refuses with the repair advice.
  - After a restore, the engine keeps the undone install receipt until its next run prunes it, so a
    completed restore cancels the install receipts before it.
  - The engine's `staged` folder (4 GB) is removed after every job, beside emptying `replacements`.
  - *Foreign* is "no receipts of ours and more strings already in the language than left to translate",
    or a changed window title. Install refuses it.
- **Timings:** in `docs/lab-notebook.md`, 2026-11-20, "PC edition ticket 02". Two jobs' times include
  Modern Standby and are void. Not run: the fork on the same copy, a launcher start, the interface.
- **Left for later tickets:** the GUI target (03), and README, AGENTS.md's Flow and Architecture lines,
  `docs/runbooks/pc-cycle.md` (04).
