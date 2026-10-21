# 03: Lineup translations in both languages

**What to build:** English and Indonesian for every lineup string ticket 01 lists, so the share-code pass has something to write. None of these strings are in either catalog today.

- Add them through the catalog supplement, which only fills sources the catalog has no entry for. The catalog files themselves are not edited (`AGENTS.md`).
- Every target passes `adaptive.validate_translation` and keeps its source's placeholders and tags.
- Hero, faction and keyword names read as the terminology table and the catalog already read them (the 芈月 tactic-card text says *Tactic Card* the way card texts do). Reuse the catalog's own wording for phrases it already translates.
- Keep names short: the lineup name sits on a narrow card and in the share code's `【name】` prefix.
- Check that the supplement's own check passes for both languages.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Every string from ticket 01 has an English and an Indonesian target
- [ ] All targets validate; the supplement check passes
- [ ] Keyword names match the terminology table on both catalogs
