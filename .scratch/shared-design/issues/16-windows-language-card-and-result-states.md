# 16: Windows ① Language and result states

**What to build:** ① Language on Windows matches Android, and the results use the shared headings. See the [spec](../spec.md), "Screen".

- ① shows the two-variant language note, the choices, then **Remove translation** as a secondary button in sentence case. It shows only while the working folder keeps a pristine delta, and locks while work runs. It leaves the Start row.
- Its confirmation becomes a plain dialog, not a danger one. No consent checkbox is added.
- Results read *Translation added* (with the counts) or *Translation removed* (with the restored-file count), then the Scan to login note.

**Blocked by:** 15, 06

**Status:** done (2026-10-23)

- [x] Remove translation in ①, gated by the pristine delta
- [x] Plain removal dialog
- [x] Shared result headings
- [x] `run.bat` checked: patch and remove on a phone, or the dialogs and states driven from source

## Comments

2026-10-20: Android's ② eyebrow now follows the state (`02_working`, `02_done`, `02_needs_attention`, Android-only strings today). When the Windows result and failure states land here, give them the same eyebrows: add `windows` to those keys' platforms (DESIGN.md, ② Start).

2026-10-23: ① shows the two-variant note, the two choices (the chosen one as the primary fill), then *Remove translation*, shown only while `holds_delta(work_dir)`; all three take the disabled colours while a run works. The removal dialog is plain (`remove_the_translation_question`, `remove_confirmation`, confirm *Remove the translation*), with no checkbox. Results: *Translation added* with text tables and images applied and skipped as a list, then `result_open_game`; *Translation removed* with the restored-file count, then `removed_login_note`. The ② eyebrow follows the state, so `02_working`, `02_done` and `02_needs_attention` gain `windows`. The added counts drop `completed_counts`' first line ("Normal game app verified"): the Windows patcher installs the normal APK but never verifies it. Driven from source, not on a phone.

2026-10-23, after review: the added counts now come from a Windows-only `applied_counts` (the four count lines of `completed_counts`, same Indonesian, not drafts), so nothing slices the Android string; `completed_counts` is Android-only again.
