# Career atlas art brief: the new English labels and the optional badges (image-generation agent)

> **Status 2026-10-10: labels done.** The user polished MY SKINS and TOTAL PROFIT by hand in `edit/`;
> they passed `validate_assets.py` and now ship in `resources/sprites/13C19E4E4486B31C/labels/`. Only
> the optional badges remain open, tracked as `.scratch/career-atlas-badges/issues/01-win-loss-badges.md`.
> `delivered/` holds just an earlier agent's NOTES.md: its PNGs were overwritten and lost. This brief was
> the T15 handoff under the retired `tasks` folder (moved here 2026-10-16).

Written 2026-10-10. You are an AI agent with image generation. Your job is **art only**: produce up to four
small PNG sprites that a mobile game will draw. Another (coding) agent integrates them afterwards. Everything
you need is in this folder; you do not need the rest of the repository, a phone, or the game.

## Context in one paragraph

王者万象棋 (Honor of Kings: ACE) is a Chinese mobile game this project translates. Its Career screen draws
labels from a texture atlas: a 1024x1024 sheet of small sprites, each at a fixed pixel box. The project
already ships English for 13 of those sprites (taken from an upstream catalog), and on 2026-10-10 it added
two labels the catalog never had — **MY SKINS** and **TOTAL PROFIT** — assembled letter by letter from the
catalog's own English glyphs. They are faithful but rough: K, L, R and F had to be built from other letters'
strokes. Your task is to make them look as if the same artist drew them, and optionally to translate two
round Victory/Defeat badges. Look at `context_atlas_after_port.png` first: it is the atlas as it ships now.

## Deliverables

Put each file in `tools/research/career_atlas/delivered/`, named exactly as below. Sizes are exact and non-negotiable — the
game draws each sprite into a fixed box, and a wrong size is refused.

| priority | file | size (px) | replaces | text | style reference |
|---|---|---|---|---|---|
| 1 | `Image_410780920.png` | 117 x 45 | `originals/zh_Image_410780920_我的皮肤.png` | MY / SKINS (two lines) | `reference_english/my_chessplayers.png` |
| 1 | `Image_920603129.png` | 87 x 45 | `originals/zh_Image_920603129_总盈利.png` | TOTAL / PROFIT (two lines) | `reference_english/achievement_points.png` |
| 2 (optional) | `Image_1611657762.png` | 126 x 126 | `originals/zh_Image_1611657762_badge_胜利.png` | WIN | the badge itself |
| 2 (optional) | `Image_1795213190.png` | 126 x 126 | `originals/zh_Image_1795213190_badge_失败.png` | LOSS | the badge itself |

Plus `tools/research/career_atlas/delivered/NOTES.md`: for each file, how it was made (model/tool, prompts, any manual pixel
work), and a provenance statement — no font file or third-party artwork is embedded, and the output may be
redistributed inside this open-source patcher.

Every folder here has 1x originals and `@8x_on_navy.png` enlargements on the game's panel colour
(RGB 38,40,62). Judge by the 8x files; deliver at 1x.

## The labels (priority 1)

**Match these, measured from the catalog's own labels:**

- **Colour:** pure white `#FFFFFF` everywhere. The glyph shape lives **entirely in the alpha channel**
  (straight, not premultiplied, alpha). No shadow, outline, glow, gradient, or tint — the screen supplies
  the background. A pixel with alpha ≥ 30 must have RGB ≥ 245. Do not composite onto black and keep the
  result: that greys every antialiased edge and shows as a dark fringe in game (the first renders had
  exactly this bug).
- **Face:** a condensed, slightly flared serif in capitals, stroke weight about 3 px at cap height, small
  wedge serifs, upright. It is *not* any common system font: the best of ~40 Windows serif fonts fitted
  to these glyphs was still visibly off. Use the reference glyphs, not a font, as the authority —
  `achievement_points@8x_on_navy.png` shows every stroke type you need (diagonals in A, V, M, N; bowls in
  P, O, C; serifs on E, T, I, H).
- **Size and layout:** two lines, each centred horizontally; cap height **15-16 px** of solid ink per line
  (the validator accepts 14-17). Line 1 sits on rows ~4-21, line 2 on rows ~22-40. Letters are set about
  one clear pixel apart, as in the references. Keep the outermost pixel ring transparent.
- **Survives compression:** the game stores the atlas as ASTC 4x4 (lossy, 4x4-pixel blocks). Avoid 1-px
  hairlines, isolated speckles and texture inside the strokes; clean solid strokes with 1 px of antialias
  survive best.

**Specific to each:**

- **MY SKINS** (`Image_410780920`): the Career screen toggles between this label and MY CHESSPLAYERS in
  the same spot, so line 1 **MY must not move**: rows 0-21 of your alpha channel equal to rows 0-21
  of `my_chessplayers.png`'s alpha, bar at most 10 touched-up pixels (`current/Image_410780920.png` already satisfies this; start from it).
  Polish only line 2, SKINS. Its K in `current/` is the weakest letter: a stem with
  a mirrored leg for an arm. Give it a proper K in this face, with the arm and leg meeting the stem at
  mid-height.
- **TOTAL PROFIT** (`Image_920603129`): both lines are yours. Match ACHIEVEMENT POINTS' letterforms
  (that label's P, O, I, T and A are the ones `current/` reuses). L, R and F in `current/` are built from
  E, P and A parts; make them look native. "PROFIT" is the widest line: it must fit 87 px with the
  outermost column clear.

Spelling is part of the spec. Image models misspell small text: check every letter at 8x.

## The badges (priority 2, optional)

Round medallions: a gold ring around `胜利` (victory) with a handwritten "Victory" script across its lower
edge, and a silver ring around `失败` (defeat) with "Failure". Replace **only the two Chinese characters**,
in the same metallic treatment as the characters you replace (gold gradient, silver gradient), centred
where they were. Leave the ring, its glow and the script subtitle exactly as they are: the validator
compares everything outside the box x 18-108, y 30-80 with the original and allows a mean difference of 6.

Wording: **WIN** / **LOSS** is the default, because the script already says Victory and Failure and two
short words fit the space the two characters leave. If you think VICTORY / DEFEAT reads better, deliver
that as an extra variant named `Image_<id>.alt.png` and say why in NOTES.md; the user decides.

Unlike the labels, the badges keep their colours and their own soft glow, so the white-only rule does not
apply to them.

## Suggested workflow

1. Study `reference_english/*@8x_on_navy.png` and `current/*@8x_on_navy.png` side by side.
2. Generate or draw at 8x (936x360 for MY SKINS, 696x360 for TOTAL PROFIT, 1008x1008 for a badge), with
   the references as image prompts or style guides, on a transparent or flat known background.
3. Reduce to the exact size with an area (box) filter, then set RGB to white and keep the coverage as
   alpha (labels). Clean the result at 1x by hand if needed. At this size, pixel cleanup usually matters
   more than the generation.
4. Run the validator (Pillow only):

   ```bash
   python tools/research/career_atlas/validate_assets.py --delivered tools/research/career_atlas/delivered
   ```

   It prints PASS/FAIL per rule and writes `preview_sheet.png` (original | yours | current | style
   reference | after an ASTC round trip, when the `astc-encoder-py` and `texture2ddecoder` packages are
   installed) and `preview_in_context.png` (your files pasted into the shipping atlas). Iterate until it
   passes **and** the previews look right at 4x and at 1x.

## Acceptance

- `validate_assets.py` passes for every delivered file.
- At 1x on navy, a reader cannot pick out the new labels from the catalog's own labels in
  `preview_in_context.png` by style alone.
- Spelling is exact; MY is unchanged from MY CHESSPLAYERS.
- NOTES.md records how each file was made and states its provenance.

## Do not

- Do not change any file outside `tools/research/career_atlas/delivered/`. In particular, never touch `resources/catalog/`
  (upstream data) or `resources/sprites/` (the coding agent integrates from your delivery).
- Do not resize the canvas, add a background, or bake in a shadow.
- Do not redraw other sprites, even if you think they could be better.

## For the coding agent, after delivery

Not part of the art task; recorded so the handoff is complete.

1. Review `preview_sheet.png`, `preview_in_context.png` and NOTES.md with the user.
2. Done 2026-10-10 for the labels: `atlas_sprites.py labels` writes drafts to `--out` only, and its
   `--check` verifies the shipped hand-finished labels' format instead of regenerating them.
3. Badges: add `Image_1611657762` / `Image_1795213190` to `mobile_graphics.ATLAS_LABELS` with their wording.
   `port_atlas` draws a label over its whole device box, so the delivered PNG replaces the sprite as is.
4. Run `check_graphics.py` (offline and `--game`), rebuild the exe, and run a device cycle
   (`docs/runbooks/device-cycle.md`): the Career screen in both switch
   states, Total Profit, and the match-history badges.

## Files here

| path | what |
|---|---|
| `context_atlas_after_port.png` | the shipping Career atlas (region x 190-1024, y 100-460) on navy |
| `sprite_boxes.json` | each target sprite's box in the 1024x1024 atlas (x0, y0, x1, y1) |
| `reference_english/` | the catalog's English labels: the style authority |
| `originals/` | the Chinese sprites being replaced, from the unpatched 2026-10-03 game data |
| `current/` | the shipping glyph-assembled renders of MY SKINS and TOTAL PROFIT |
| `validate_assets.py` | the checker and preview renderer |
| `build_reference_pack.py` | regenerates everything above from the repo and the game dumps (coding agent only) |
| `edit/` | the user's hand-finished labels as shipped, the optional badge starting copies, and `.start_sha256.json` (the starting hashes) |
| `delivered/NOTES.md` | provenance notes from an earlier image-agent delivery whose PNGs were lost |
| `final_in_atlas_after_astc.png` | the atlas with the new labels after an ASTC round trip |
| `evidence/` | the Career-atlas investigation of 2026-10-10: the user's Career screenshot, both atlases with device rects (red) and catalog boxes (yellow), both rect tables as JSON, and pristine crops of the damaged non-catalog sprites. `13C19E4E4486B31C_rects.json` (and its render) is regenerated by `tools/research/atlas_sprites.py table --package <pkg19> --out tools/research/career_atlas/evidence`; the `pre-update-2026-10-03` files are a fixed record and are not regenerated |
