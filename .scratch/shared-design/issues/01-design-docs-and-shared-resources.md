# 01: Design docs and shared resources

**What to build:** one written design both patchers follow, and the shared files they read it from (see [spec](../spec.md)).

- Rewrite `DESIGN.md` from the rendered wxq.qq.com page, replacing the CSS-only extraction, with the colour roles, corners, fonts, layout and hero rules of the spec, and the Windows fallbacks.
- Add a `DESIGN.md` row to the Docs table in `AGENTS.md`; delete `docs/features/android-visual-theme.md` (its rules move into `DESIGN.md`; its history is not kept).
- Add `resources/ui/theme.json` with the `DESIGN.md` tokens.
- Add `resources/ui/strings.json`: every user-facing string of both patchers in English and Indonesian, seeded from the Android patcher's `UiText` and the Windows patcher's `hok_patcher.py`.
- Add `resources/fonts/` with Barlow (Regular, Medium, SemiBold, Bold) and Barlow Condensed ExtraBold, plus the OFL licence text, and list them in `android/native/THIRD_PARTY.md`.
- Check: `tools/research/check_references.py` and `tools/research/check_staging_contract.py` pass.

**Blocked by:** nothing

**Status:** ready-for-human (review the Indonesian drafts)

- [x] `DESIGN.md` rewritten from the site
- [x] `AGENTS.md` Docs row added, `android-visual-theme.md` deleted
- [x] `resources/ui/theme.json` (generated from `DESIGN.md`'s front matter)
- [x] `resources/ui/strings.json` (190 strings, 20 shared; 41 Indonesian drafts marked `"draft": true` for native review)
- [x] `resources/fonts/` with the licence, listed in `android/native/THIRD_PARTY.md`
