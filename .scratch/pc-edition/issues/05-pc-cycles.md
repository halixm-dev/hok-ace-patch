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

- [x] English PC cycle: pass
- [x] Indonesian PC cycle: pass
- [ ] Feature record written, `.scratch/pc-edition/` removed

## Comments

2026-11-21, Claude (branch `feat/pc-edition-05-cycles`):

- **Both cycles pass** on the installed game `D:\WXQ`, launcher 26111.0.4.30004, data 1.11.0.2, run from
  source at `586fb71`: Install English (410.2 s), Install Indonesian through the receipts (509.4 s),
  Install English again (410.6 s, files byte-identical to the first), Remove translation (31.2 s, every
  file back to its starting SHA-256). The launcher started with no repair after each install and after
  Remove; the lobby read English and Indonesian; wrapping, token-expanded card text, the Career labels
  and the Secret Technique titles were in place (user's observations). Lab notebook, 2026-11-21, "PC
  edition ticket 05".
- **START GAME / MULAI GAME:** an event skin of the start button, not in the catalog, hides both lobby
  textures and stays Chinese (on the phone too). Both textures are read back from package `19` with the
  stage's `patched_sha256` in each language. User's decision: pass, the event button is a coverage gap
  outside this ticket.
- **Not yet possible:** *After a launcher update*. The launcher updated before any install, so no
  translated file was replaced.
