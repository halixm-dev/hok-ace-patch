# Edit these by hand

Starting copies of the Career-atlas art, for manual polishing. Edit the PNGs in place, keep the file
names, then ask Claude to recheck: it compares them with `.start_sha256.json` to see which you changed,
runs the validator, shows you the previews, and integrates the changed ones.

| file | text | size | replaces |
|---|---|---|---|
| `Image_410780920.png` | MY / SKINS | 117 x 45 | `我的皮肤` |
| `Image_920603129.png` | TOTAL / PROFIT | 87 x 45 | `总盈利` |
| `optional_badges/Image_1611657762.png` | 胜利 → e.g. WIN | 126 x 126 | the gold Victory badge (still Chinese: edit only if you want it translated) |
| `optional_badges/Image_1795213190.png` | 失败 → e.g. LOSS | 126 x 126 | the silver Failure badge (same) |

## Rules (the validator checks them)

- **Do not change the canvas size.** The game draws each sprite into a fixed box.
- **Keep transparency.** Use an editor that saves RGBA PNG with alpha: GIMP, Krita, Aseprite, Photoshop,
  Photopea. MS Paint drops alpha.
- **Labels are white, shaped by alpha.** Paint glyphs pure white and shape them with opacity/eraser; no
  shadow, outline or colour. The game supplies the dark background.
- **MY SKINS: don't move the MY line** (rows 0-21): it must match MY CHESSPLAYERS (a few touched-up
  pixels at most), because the two labels swap in the same spot. Polish SKINS (the K is the weakest letter).
- **TOTAL PROFIT:** L, R and F were built from other letters' parts; those are the ones worth fixing.
- Cap height 14-17 px per line, outermost 1-px ring transparent, solid strokes (the game compresses the
  atlas in 4x4-pixel blocks, so 1-px hairlines and speckles blur away).
- **Badges:** change only the middle (x 18-108, y 30-80) where the Chinese is; leave the ring, glow and
  the script word as they are. Metallic gold/silver like the original characters.

Style references and 8x enlargements are in `../reference_english/` and `../originals/`;
`../context_atlas_after_port.png` shows the whole atlas as it ships now. More detail: `../handoff.md`.

## Check your work yourself (optional)

```bash
python tasks/T15/validate_assets.py --delivered tasks/T15/edit
```

It writes `tasks/T15/preview_sheet.png` and `tasks/T15/preview_in_context.png`.
