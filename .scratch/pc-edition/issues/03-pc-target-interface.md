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

- [ ] `run.bat`: the target choice, both targets, and a PC Install, Check and Remove translation on a scratch copy pointed at by the folder pick
- [ ] Phone target unchanged: one phone run end to end, or `--selftest` plus a look at every phone step
- [ ] `tools/research/check_ui_strings.py` passes

## Comments
