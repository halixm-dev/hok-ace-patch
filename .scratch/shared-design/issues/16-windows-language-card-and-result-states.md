# 16: Windows ① Language and result states

**What to build:** ① Language on Windows matches Android, and the results use the shared headings. See the [spec](../spec.md), "Screen".

- ① shows the two-variant language note, the choices, then **Remove translation** as a secondary button in sentence case. It shows only while the working folder keeps a pristine delta, and locks while work runs. It leaves the Start row.
- Its confirmation becomes a plain dialog, not a danger one. No consent checkbox is added.
- Results read *Translation added* (with the counts) or *Translation removed* (with the restored-file count), then the Scan to login note.

**Blocked by:** 15, 06

**Status:** ready-for-agent

- [ ] Remove translation in ①, gated by the pristine delta
- [ ] Plain removal dialog
- [ ] Shared result headings
- [ ] `run.bat` checked: patch and remove on a phone, or the dialogs and states driven from source

## Comments

2026-10-20: Android's ② eyebrow now follows the state (`02_working`, `02_done`, `02_needs_attention`, Android-only strings today). When the Windows result and failure states land here, give them the same eyebrows: add `windows` to those keys' platforms (DESIGN.md, ② Start).
