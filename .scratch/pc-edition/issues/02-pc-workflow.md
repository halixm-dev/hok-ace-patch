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

- [ ] `check_pc_install.py` passes in both languages: restore returns the original bytes, a second install changes nothing, the switch goes through the receipts, no `LocalFileList.json` file changes
- [ ] `--smoketest` passes on the frozen exe (`app/build_exe.py` carries the new modules; check `HIDDEN_IMPORTS`)
- [ ] `tools/research/check_ui_strings.py` passes

## Comments
