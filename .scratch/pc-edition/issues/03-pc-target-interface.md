# 03: The PC target in the Windows patcher's window

**What to build:** the target choice and the PC target's page in `app/hok_patcher.py`, on the shared design. See the [spec](../spec.md), *Interface*. Read `PRODUCT.md` and `DESIGN.md` first.

- **Target choice** at the top: *Phone over USB* (today's steps, unchanged) or *PC game on this computer*. The language card is shared and still sets the interface language.
- **PC target:**
  - a game-folder row: the found folder, or *Choose folder*;
  - **Install**, **Check** and **Remove translation**.
- **Check** runs when the target opens and after each job, and shows its four states.
- **Jobs:** each one runs through `pc_edition`'s child process, with elapsed time in the progress view. The actions lock while it runs.
  - Stop safely is not shown for a PC job.
  - Closing the window during a PC job asks the player to wait.
- **Strings:** every string is a key in `strings.json`, in both interface languages.
- **Docs:** `DESIGN.md` and `PRODUCT.md` describe the PC target in the same change.

**Blocked by:** 02

**Status:** needs-triage

- [x] `run.bat`: the target choice, both targets, and a PC Install, Check and Remove translation on a scratch copy pointed at by the folder pick
- [x] Phone target unchanged: one phone run end to end, or `--selftest` plus a look at every phone step
- [x] `tools/research/check_ui_strings.py` passes

## Comments

### 2026-11-20, implemented (`app/hok_patcher.py`)

**The window, from source, on the scratch copy.** `run.bat` runs `app\hok_patcher.py`; the window was
driven by a script that builds the same `App`, with `APPDATA` pointed at a scratch folder whose
settings name the scratch copy `C:\scratch\pc-edition-02\game` and the working folder
`C:\scratch\pc-edition-02\work`, so the player's settings and the installed game were never read or
written. The launcher was closed (`pc_edition.blocking_processes()` empty). The folder pick ran through
`choose_game` with the dialog answering the scratch copy, so `pc_edition.resolve` and
`remember_game` ran as on a click.

    .venv\Scripts\python.exe <scratchpad>\drive_gui.py . <out> --jobs

| Step | What the card showed |
|---|---|
| Phone target | target card above ①, phone ② unchanged |
| PC, no game found | `02 / READY TO PLAY`, *Choose the game folder*, Install, Check and Remove disabled |
| Folder pick, Check (18 s) | *Checking…* with the bar, elapsed time and the child's last log line, no Stop safely; then *Not installed*, `READY TO PLAY` |
| Language to Indonesian | the whole window redrawn in Indonesian at once |
| Install (6:52) | *Installing the translation*; closing the window showed *Please wait* and the window stayed open; then *Translation added, Finished in 6:52*, and the follow-up Check *Installed: English*, `DONE` |
| Remove translation (0:29) | the plain confirmation dialog; *Removing the translation*; then *Translation removed* and the follow-up Check *Not installed* |

*Replaced by an update*, *partly installed*, *translated by another patcher* (heading *The game needs a
repair first*, with the launcher's Repair as advice), *not checked yet* and a failed job (`pc_close_game`
in the error card under `NEEDS ATTENTION`) were drawn from injected states, not from a game in
that state. After Remove translation the working folder holds 8.0 GB of receipts (the restore receipt
beside the install receipt it undid), which the engine prunes on its next run, as ticket 02 measured.

**Phone target.** The phone code is unchanged apart from the card rows moving down one and the target
choice locking with the language choices. `--selftest` from source on the 1.10.1.2 pristine layer:

    .venv\Scripts\python.exe app\hok_patcher.py --selftest "dist\HOK ACE Patcher Data\pristine\20261118-1.10.1.2\game" D:\scratch\pc03-selftest\out

gave `ok: true` with packages `1` (96, 11, 1), `1050016095` (1), `15` (222), `19` (22), `20` (1),
`10` (3), in 43 s. No phone run was made.

**Checks:** `tools\research\check_ui_strings.py` (456 strings), `check_references.py` and
`check_staging_contract.py` pass. 44 new keys, all `windows`, Indonesian `"draft": true`.

**Left for ticket 04:** `AGENTS.md`'s *Flow* line still says the GUI talks only to `patcher_core`.
