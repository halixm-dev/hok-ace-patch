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

**Status:** done (2026-10-19)

- [x] Missing `UiText` entries added
- [x] Templates for the built text
- [x] Language note as two keys, used by both patchers
- [x] Windows removal strings shared
- [x] `check_ui_strings.py` added and passing

## Comments

2026-10-19: 29 keys added; `switching_languages_clear_the_games_data` is replaced by the two language-note keys, and the tagline key is dropped (ticket 08). The 18 strings and the four built texts carry the Indonesian the Android patcher shipped. `update_shizuku_before_starting` (shown on Android, never translated before) and four Windows removal lines are new and marked `draft`. The Windows patcher reads its language note and removal text through `ui_text(key)`, in English until ticket 14; the exe bundles `resources/ui/strings.json`. The check reads Android literals from the calls that put text on screen, and every `UiText.string` and `ui_text` lookup; text that arrives in a variable is outside it.
