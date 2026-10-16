# 01: Translate the Career atlas's win/loss badges

**What to build:** the two round match-result badges in the Career atlas `13C19E4E4486B31C` read in English. Today they still show `胜利` (`Image_1611657762`, gold) and `失败` (`Image_1795213190`, silver); the catalog has no edit for either. This was the one open item of the T15 art handoff when `tasks/` was retired (2026-10-16).

- Art: replace only the two Chinese characters (box x 18-108, y 30-80 of each 126x126 sprite), in the same metallic treatment; the ring, glow and script subtitle stay as they are. Default wording **WIN** / **LOSS** (the script already says Victory / Failure); a VICTORY / DEFEAT variant is the user's call. The full brief, starting copies and references are in `tools/research/career_atlas/` (`art_brief.md`, `edit/optional_badges/`, `originals/`).
- Code: add both sprites to `mobile_graphics.ATLAS_LABELS` with their wording and the art under `resources/sprites/13C19E4E4486B31C/labels/`; `port_atlas` draws a label over its whole device box.
- Check: `tools/research/career_atlas/validate_assets.py --delivered <dir>` passes, `atlas_sprites.py labels --check` and `check_graphics.py` (offline and `--game`) pass, the exe is rebuilt.
- Device cycle (`docs/features/prime-rebuild.md`, "The device test loop"): the Career screen in both switch states and the match-history badges.

**Blocked by:** nothing; optional work

**Status:** needs-triage

- [ ] Both badges drawn and passing `validate_assets.py`
- [ ] Wired through `ATLAS_LABELS` and shipped under `resources/sprites/`
- [ ] Device-verified on the screens that draw them
- [ ] `docs/features/texture-translation.md` and `docs/translation-progress.md` updated

## Notes

Two other Career-atlas items were left open by the T14 handoff and are recorded in `docs/lab-notebook.md` (2026-10-10): which other screens draw the sprites the offset port moved, and the untranslated `国服` badge of the "National server Chess Player" avatar frame, whose texture has not been located.
