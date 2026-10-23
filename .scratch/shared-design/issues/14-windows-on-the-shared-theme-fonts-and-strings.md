# 14: Windows on the shared theme, fonts and strings

**What to build:** The Windows patcher takes the shared look and words, while its layout stays as it is. A player sees the light theme, solid cards, 8 px corners, Barlow and the hero image, and the interface switches to Indonesian with the language choice. See the [spec](../spec.md), "Look" and "Shared files".

- Theme tokens replace the dark palette. Cards use the solid fallback, and the hero is a locally drawn gradient image.
- Barlow is loaded privately at startup, with no system install, and bundled into the exe.
- Every user-facing string comes from the shared strings file by key. Technical log lines stay raw.
- Dialogs are deep-indigo panels with the ice-blue confirm button. Danger dialogs use the error red.

**Blocked by:** 01, 05

**Status:** ready-for-agent (only the `PatchError` messages remain)

- [x] Light theme, fonts and hero
- [ ] Every string from the shared file; Indonesian interface (all but the `PatchError` messages)
- [x] The shared strings contract check passes
- [x] `run.bat` in both languages; `build.bat` and `--selftest` pass

## Comments

2026-10-23: Landed with 15 and 16 in one change, since 15 replaces the layout this ticket would have restyled. `hok_patcher.py` reads `resources/ui/theme.json` (cards on `card-solid` with the `#E4E3F2` edge, a flat `page-top` page) and loads Barlow from `resources/fonts/` with `AddFontResourceExW(FR_PRIVATE)` at startup; `build_exe.py` bundles the fonts and `theme.json`. The hero and the dialog panels are drawn with PIL at 2x: the panel gradient, the hero's diagonal bands, and their text in Barlow. Dialogs: ice-blue confirm, error-red for a danger confirmation (reinstall, closing mid-run). `patcher_core` now holds `ui_text` and `set_interface_language`; the language choice sets the interface language and redraws every text at once. Its dialogs and device hints come from the strings file (new `device_*` keys, drafts). `check_ui_strings.py` now also reads `patcher_core.py`. Still English: the `PatchError` messages the error card shows. They are not in the strings file yet, so an Indonesian player reads the cause of a failure in English.

2026-10-23, after review: the device hints are logged as one raw English line (adb's states), not in the interface language. *Retry install?* is a plain question (`Ui.ask(..., danger=False)`); only the reinstall and closing mid-run stay danger dialogs. Left open for the ~20 `PatchError` messages in `patcher_core.py`: each needs a key in the strings file with its placeholders (paths, adb output), then `check_ui_strings.py` covers them.
