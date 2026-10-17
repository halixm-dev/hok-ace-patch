# 03: Windows patcher repatches from the pristine delta

**What to build:** the Windows patcher keeps a pristine delta after each verified install and, on a later run, builds from the rebuilt pristine layer, so a language switch or a newer translation needs no clear.

- After `push_translation` succeeds: `make` the delta from the session's pulled layer (or its rebuilt pristine files) against `staged/`, written atomically to `<working folder>/pristine/delta.bin`, replacing the old one only once durable. Also record the staged hashes of every install.
- After `pull_game_data`: `rebuild` into `sessions/<stamp>/game` in place; `device-backup.tar` keeps the phone's bytes.
- First delta only from a pristine layer: no pulled file matches a recorded staged hash, and the text pass translated records in every text table it staged.
- Any file matching neither its staged nor its pristine values (until 07 adds the update rules), or an already-patched layer with no delta: `PatchError` with the clear-data message (or "patch with the patcher that patched it last"), raised before the access APK is installed.
- Log `rebuilt N files from the pristine delta` or the refusal reason. The LANGUAGE picker text and `README.md` "Updates and language changes" drop the clear-first step when a delta applies.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] Delta kept after a verified install; staged-hash record kept
- [ ] Rebuild before build; refusals before the access APK
- [ ] Picker text and `README.md` updated
- [ ] `run.bat` / `--selftest` checks of an offline switch

## Notes

Update `docs/translation-progress.md` only if a count moves (it should not).
