# 05: One PC cycle per language before release

**What to do:** prove the PC edition in the game itself, following `docs/runbooks/pc-cycle.md`. See the [spec](../spec.md), *Testing*. Each verdict and its numbers go in `docs/lab-notebook.md`.

- **English and Indonesian, each from a launcher-repaired game:**
  - Install;
  - the launcher starts with no repair;
  - the game reaches the lobby translated.
- **Look at each of these:**
  - text wrapping;
  - the regioned atlases and Secret Technique titles at their PC sprite rects;
  - MULAI GAME on both lobby textures (Indonesian);
  - token-expanded card text.
- **Language switch:** English → Indonesian → English through the receipts.
- **Remove translation:** returns the original files, and the launcher accepts them.
- **After a launcher update** (when one ships): Check shows *replaced by an update*, and Install works again.
- **When done:** promote the spec to `docs/features/pc-edition.md` and delete `.scratch/pc-edition/` (`docs/agents/issue-tracker.md`).

**Blocked by:** 04

**Status:** needs-triage

- [ ] English PC cycle: pass
- [ ] Indonesian PC cycle: pass
- [ ] Feature record written, `.scratch/pc-edition/` removed

## Comments
