# Re-lay the Secret Technique title sprites to fit the English

Status: accepted. Device-tested 2026-11-11 (Xiaomi M2007J3SG, Android 12, game data 1.9.2.4, English), first as a prototype and then from the pipeline's own package `19` output.

The Secret Technique card titles are sprites in `LordSkillCardAtlas` (`0B4DA7A85D27E87A`), sized to the Chinese, and each card draws its title at its prefab's `Title` RectTransform size. English set in those boxes read far smaller than the Chinese, and the user asked for one size for every title, as tall as possible, never squeezed: 36 pt, with MAGICAL DEERIE and GRACEFUL STEPS on two lines. Those boxes cannot be had by redrawing pixels alone. So the run re-packs the title sprites in the atlas and moves, in place, every record that names their rects: the Sprite table, Tencent's TimiAtlas index, and the `Title` box of each card prefab that draws one title. The new places are repo data (`resources/sprites/0B4DA7A85D27E87A/layout.json`), generated from a pristine layer and checked against the device's own assets on every run. This is the first time the texture pass writes assets that are not textures. Evidence: [texture-translation](../features/texture-translation.md#atlases-the-catalog-lacks-labels-alone-2026-11-11) and the lab notebook entries of 2026-11-11.

## Consequences

- Package `19` gains 35 written assets beside the atlas (one Sprite table, one TimiAtlas, 33 prefabs). They are floats rewritten in place, no asset changes length, and they are not counted as textures.
- `card_titles.relayout` refuses unless every art sprite, title rect and `Title` box sits at its pristine or its new value. A refusal leaves the old rects, which refuses the atlas, so the titles stay Chinese together and nothing is half moved.
- The shared template prefab `UICardLordSkill_Secret` (`8A2936518633CA63`), which sets one box for every title, is left alone. A screen that draws titles through it shows the new sprite scaled into the old 196x44 box. No such screen has been seen.
- A game update that moves the art or the boxes stops the titles (skipped, reported) until `atlas_sprites.py layout` is re-run on the new pristine layer.
- The pristine delta keeps these assets' pristine bytes like any other modified asset, so a language switch or a restore covers them.
