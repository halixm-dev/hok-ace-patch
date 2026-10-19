# 05: Shared strings for the newer controls

**What to build:** `resources/ui/strings.json` holds every string the controls added after ticket 01 use, so that tickets 03 and 04 can switch to the file without losing any (see [spec](../spec.md), "Remove translation", "Language note", "Free up space", "Result states").

- Add the 18 `UiText` entries missing from the file, with the Indonesian the Android patcher already ships, not marked `draft`:
  - Remove translation: `Remove translation`, `Remove the translation`, `Translation removed`, and the two "nothing to remove" notices (no record on this phone; official build).
  - Language note: the two variants (pristine delta held; another patcher or an older version translated the phone).
  - Free up space: `Free up space`, `Free up space?`, `Free space`, the confirmation message, `Finish the current work before freeing space.`, `Space freed`, and the kept-saved-apps line.
  - Recovery close: `Translation written`, and the two closed-run lines.
  - Hero: `Some game text will stay Chinese.\nUse Scan to login after setup.`
- Add templates with `{name}` placeholders for the text `UiText` builds in code: `freed`, `removeSavedApks`, `removeConfirmation`, and the removal branch of `completed`.
- Replace `switching_languages_clear_the_games_data` with the two language-note keys. Windows uses the same two strings in place of its own wording in `show_language_note`.
- Windows: one key each for its removal strings (the confirmation, "Done! Translation removed.", the restored-files count), shared with Android wherever the meaning matches. Use sentence case: "Remove translation", not "Remove Translation".
- Add the shared strings contract check (`tools/research/check_ui_strings.py`, see the spec's Testing Decisions): every string `UiText` and `hok_patcher.py` show resolves to a key, every key has `en` and `id`, and placeholders match. It fails today on the 18 missing strings.
- Check: the new check passes; `tools/research/check_references.py` passes.

**Blocked by:** nothing

**Status:** ready-for-agent

- [ ] Missing `UiText` entries added
- [ ] Templates for the built text
- [ ] Language note as two keys, used by both patchers
- [ ] Windows removal strings shared
- [ ] `check_ui_strings.py` added and passing
