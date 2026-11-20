# PC cycle

Run this before a PC-edition change ships: a change to the per-install catalog (`tools/pc_catalog.py`),
to a hook (`tools/engine_hooks.py`), to the workflow (`app/pc_edition.py`), a config bin proposed for the
PC edition's allowlist, or anything whose effect on a screen or on the launcher is known only by
watching it. A PC cycle tests **one** change in the PC edition itself and ends in a verdict, recorded
before the next cycle starts. It is the PC edition's counterpart of the
[device cycle](device-cycle.md); the offline checks come first, because they prove the files, and the
cycle proves what the launcher accepts and what the game shows. The measurements behind these steps are
in [`docs/lab-notebook.md`](../lab-notebook.md), 2026-11-20, "PC edition ticket 01" and "ticket 02".

## Steps

1. **Let the launcher finish its update, then close the game and the launcher.** Every PC job refuses
   while `wxq*.exe` or `王者万象棋.exe` runs (`pc_close_game`); the launcher keeps several processes open,
   so check Task Manager's Details tab, not only the taskbar.
2. **Record both versions.** The cycle's verdict holds for these two and no others:
   - the **launcher's version**: the folder name in `launcherConfig.json`'s `launcherExePath` at the game
     root (`C:\Program Files\WXQLauncher\<version>\王者万象棋.exe`, for example `26102.0.2.30004`);
   - the **game's data version**: `Version` in `WXQ_Data\StreamingAssets\Config\Version.txt` (for example
     `1.11.0.2`), which `QtsDataFolder\Export\MiscExport\QtsPackageConfig.json` repeats as `version`.
3. **Start from the launcher's own files.** For a first cycle in a language, or when Check shows
   *partly installed* or *translated by another patcher*, run **Repair** in the launcher, let it finish,
   and close it again. Check must then read *not installed*.
4. **Prove the change offline first, on a copy.** Copy the game folder to a scratch folder (never point
   a check at the installed game), then run, with Python 3.12:

   ```bat
   "dist\HOK ACE Language Patcher.exe" --pc-selftest <game-copy> <out-dir>
   .venv\Scripts\python.exe tools\research\check_pc_install.py --game <game-copy> --work <work-dir>
   ```

   `pc_selftest.json` must read `"ok": true` in both languages, and `check_pc_install.py` must print `OK`.
   Note each language's `skipped_atlases`: a regioned atlas refused at this installation's sprite table
   stays Chinese by design (ADR 0006).
5. **Install the one change.** Open the patcher built from the change, choose **PC game on this
   computer**, the language and a working folder with about 10 GB free, then **Install**, and keep the
   window open until it reports *Translation added*. The job's own log is
   `<work>\pc\jobs\install.json.log`; keep it with the cycle's evidence. The receipts in
   `<work>\pc\receipts\` are the rollback.

   **A config bin** has no switch in the window. Run the jobs from source with the candidate added:
   `.venv\Scripts\python.exe app\hok_patcher.py --pc-job install <game> <work> <answer.json> <language>
   --cycle-asset <hash>`, and the same for Check (`status`). The hash must name one of
   `extra_text.CANDIDATE_ASSETS`; the job's log reads `<hash>: config bin translated`, and its answer
   lists it under `cycle_assets`. Step 4's `--pc-selftest` takes `--cycle-asset <hash>` after
   `<out-dir>` too.
6. **Start the launcher and watch it.** It must reach its start button with no repair or file check.
   A repair means the launcher refused a file: it empties `WXQ_Data\Package\builtin` and the translation
   goes with it (ADR 0011). Before starting it, `LocalFileList.json` must have the same bytes as before the
   install.
7. **Start the game and walk the screens.** Log in, then walk every screen the change could reach, and
   the screen it targets:
   - the lobby, with MULAI GAME on both lobby textures in Indonesian;
   - the Card menu and token-expanded card text;
   - text wrapping (the line-break Lua edit);
   - the Career atlas labels and the Secret Technique titles at their PC sprite rects;
   - a match start and a match end.

   A staged file that the engine verified is not evidence about a screen.
8. **Run Check** from the patcher with the game and launcher closed again. It must read
   *Installed: <language>*.
9. **Record the verdict.** Pass or fail, the symptom with the screen named, the date, the launcher's
   version and the game's data version, as a dated entry in the lab notebook. A config bin's verdict also
   goes beside its hash in `tools/extra_text.py`, marked for the PC edition: the allowlist is per edition.
10. **Roll back** with **Remove translation**, or with the launcher's Repair when the receipts no longer
    match the files. After a Remove, start the launcher once more: it must accept the restored files
    without a repair.

## A launcher update

When the launcher updates while a translation is installed, run Check after the update finishes. It must
read *Replaced by an update* (the update replaced the translated files and the engine drops receipts that
no longer describe them), and a new Install must reach the lobby translated. Record the new launcher and
data versions with that verdict.

## Done when

The user has seen the changed screen in the game, the launcher started without a repair, Check reads
*Installed* in the cycle's language, and the verdict is dated in the lab notebook with the launcher's
version and the game's data version.
