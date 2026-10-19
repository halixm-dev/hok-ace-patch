# 06: Record the newer controls in the design docs

**What to build:** `DESIGN.md` and `PRODUCT.md` describe the home screen both patchers now have, so the restyle tickets follow one written source (see [spec](../spec.md) and the amended [home screen brief](../home-screen-brief.md)).

- `DESIGN.md`, Layout:
  - ① Language gains the language note and the secondary **Remove translation**, shown only while a pristine delta is held.
  - ② Start gains the notice line and the result states (added, removed, written, space freed).
  - Under ②: the warning card (Android "Game won't open?" with folded recovery options), and the error card with *Copy error details* and *Save log for help*.
- `DESIGN.md`, Components: Remove translation and Free up space confirm with a plain dialog, not a danger one. Free up space's optional checkbox starts unchecked.
- `PRODUCT.md`: "Repatching after an update without a clear is specced, not shipped" is stale. `e59ff8a` shipped it in both patchers, checked offline but not yet on a real update. Say that, and name the remaining cases that still need a clear (mixed packages, deltas without fingerprints).
- `PRODUCT.md`, Operating Context: the Android patcher also offers Remove translation and Free up space. The Windows patcher offers Remove translation.
- Check: `tools/research/check_references.py` passes. `resources/ui/theme.json` still matches the front matter (no token change is expected).

**Blocked by:** nothing

**Status:** done (2026-10-19)

- [x] `DESIGN.md` Layout and Components
- [x] `PRODUCT.md` update-repatch line and Operating Context
- [x] Reference check passes

## Comments

2026-10-19: `DESIGN.md` Layout now lists ① Language's order (title, note, choices, Remove translation), ② Start's states and notice line, the warning and error cards under ②, and the footer row; Components adds the plain dialog for Remove translation and Free up space. `PRODUCT.md` says update repatching shipped in both patchers, checked offline, and names the two cases that still need a clear (a package mixing updated and translated files, a delta without the asset record). No token changed, so `theme.json` still matches. `check_references.py` passes.
