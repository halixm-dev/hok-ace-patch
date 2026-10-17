# 03: Windows patcher repatches from the pristine delta

**What to build:** the Windows patcher keeps a pristine delta after each verified install and, on a later run, builds from the rebuilt pristine layer, so a language switch or a newer translation needs no clear.

- After `push_translation` succeeds: `make` the delta from the session's pulled layer (or its rebuilt pristine files) against `staged/`, written atomically to `<working folder>/pristine/delta.bin`, replacing the old one only once durable. Also record the staged hashes of every install.
- After `pull_game_data`: `rebuild` into `sessions/<stamp>/game` in place; `device-backup.tar` keeps the phone's bytes.
- First delta only from a pristine layer: no pulled file matches a recorded staged hash, and the text pass translated records in every text table it staged.
- Any file matching neither its staged nor its pristine values (until 07 adds the update rules), or an already-patched layer with no delta: `PatchError` with the clear-data message (or "patch with the patcher that patched it last"), raised before the access APK is installed.
- Log `rebuilt N files from the pristine delta` or the refusal reason. The LANGUAGE picker text and `README.md` "Updates and language changes" drop the clear-first step when a delta applies.

**Blocked by:** 02

**Status:** ready-for-agent

- [x] Delta kept after a verified install; staged-hash record kept
- [x] Rebuild before build; refusals before any game file is written (see Comments)
- [x] Picker text and `README.md` updated
- [x] Offline switch checks (`check_pristine_delta.py --game`, `check_windows_repatch.py`); `run.bat` against a phone is ticket 08

## Notes

Update `docs/translation-progress.md` only if a count moves (it should not).

## Comments

2026-10-17, implemented in `app/patcher_core.py` (`restore_pristine`, `check_first_delta`,
`push_translation`) and the GUI note (`show_language_note`).

- Refusal timing: the check reads the pulled files, and `run-as` needs the access APK, so a refused run
  installs it and restores the normal APK as usual; nothing is written to the game's data. The spec now
  says "before any game file is written".
- Windows has no rollback, so the new install's delta is written as `pristine/delta.pending.bin` before
  the first push and replaces `delta.bin` after the last; the next run accepts each file at either
  delta's staged bytes. A run cut off twice in a row can still leave a file neither describes, which
  refuses.
- A file the previous delta named and this build no longer stages is pushed back at its pristine bytes.
- Sessions are pruned after `restore_pristine`, so the bootstrap (05) sees the two kept before this one.
- Not run against a phone (ticket 08).
