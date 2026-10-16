# T14 — Handoff: redraw the Career atlas in English, sprite by sprite

Written 2026-10-10 from a session that started on a user screenshot (`evidence/career_screen_2026-10-10.png`)
showing `我的棋手` beside the chessplayer count on the **Career** screen. Nothing in `app/`, `tools/` or
`resources/` has been changed yet. Everything below was measured on this machine's dumps and can be
reproduced with `tasks/T14/sprite_table.py`.

## TL;DR

- `我的棋手` is a **sprite**, not text: `Image_1904551913` in the `CareerAtlas` texture
  **`13C19E4E4486B31C`** (package `19`, downloaded layer only, 1024×1024 ASTC 4×4). It is drawn by
  `UICarrerLordAndSkinDetaiSwitchItem` (`self.type:SetSimilarSpriteByIndex(0)`; index 1 is `我的皮肤`).
  Only the `9` beside it is text.
- The catalog **has** an edit for this texture: 13 labelled sprites, applied every run with nothing skipped.
  But the edit is a `.blocks` patch drawn on the **PC atlas layout**. The mobile atlas packs the same
  sprites at different positions, and the texture pass ports block-for-block at the same offsets
  (`mobile_graphics.english_raw`, the `fmt == "bc7"` `.blocks` branch). **9 of the 13 English labels land
  on other sprites.** Only `glory_gold` and `total_achievement_points` match exactly. `stubborn_bronze` and
  `order_silver` are off by 1 px.
- This is **not** new with the October update: the pristine 2026-10-03 atlas (pre-update) was also laid
  out differently from the catalog. Since this edit shipped, it has overwritten other sprites. One example
  is the **My Skins** label (`我的皮肤`, `Image_410780920`), which the patch overwrites with
  "VIENTIANE KING" on today's layout and with "MY CHESSPLAYERS" on the 10-03 one.
- The fix is a **sprite-aware port**: place each catalog sprite's English pixels at the sprite's **device**
  rect (read from the device's own Sprite table), and restore or redraw every device sprite the old
  offset-for-offset port damaged. Then add English for the Career sprites the catalog never covered
  (`我的皮肤`, `总盈利`, and optionally `胜利` / `失败`).

## How the asset was found (so the next one is faster)

1. Screenshot → the string is in no catalog table and in no asset as UTF-8 except Lua comments. The
   Career Lua (package `10`: `3A1EA40DF80897BF` AutoBind, `361A7A1C745B580E` class, `22DD0A0DE668B0BF`
   panel) shows that the label is a `TimiImage` sprite and only the count is `TimiText`.
2. Prefab `UIPrefab/Career/Item/UICarrerLordAndSkinDetaiSwitchItem` = package `19` `E82B9527804B3DD5`.
   It names its sprites as `UIResources/Career` + `Image_1904551913` / `Image_410780920`.
3. Those names occur in `BAE55973AA41FF81` (the `CareerTimiAtlas` SpriteAtlas,
   `UIResources/Career/Atlas/CareerAtlas`) and in **`4AA2B26FF28CB65D`**, which holds the 218 Sprite
   objects **and** the Texture2D header: `CareerAtlas`, 1024×1024, format 48 (ASTC 4×4), pixels streamed
   from `assets/d8/d8e44faed20ba201548914e4792e1045.resS`, 1 048 576 bytes.
4. No path→QTS-hash scheme was found for the `.resS` name: xxh64, FNV, MD5, SHA-1 and CRC64 over the
   usual path forms all missed. The pixel asset was found by decoding every 1 MB asset in both layers
   at 1024×1024 4×4 and cropping the sprite rect: **`13C19E4E4486B31C`**. Package `0`
   `55989B6B5917A7D9` (10 MB) is a manifest whose row for `4AA2B26FF28CB65D` lists the texture's pathID
   `B0975C8A83A08957`. It is likely the real map, but it was not decoded.
5. Tencent's SerializedFile header is modified and UnityPy cannot read it. A Sprite record is still
   plain, though: a length-prefixed `Image_<id>`, 4-byte aligned, then `m_Rect` as four LE floats, with
   y measured from the **bottom**. `sprite_table.py` reads only that.

## The layout mismatch (today's phone, game data after the October update)

Boxes are top-down pixels, the convention of the catalog's `regions[].box`. "Device" is from
`evidence/13C19E4E4486B31C_rects.json`.

| catalog label | sprite | catalog (PC) box | device box | what the PC box overwrites on the device |
|---|---|---|---|---|
| apprentice_rookie | `Image_1142424185` | 732,251–852,297 | 590,216–710,262 | `eternal_diamond`'s sprite |
| stubborn_bronze | `Image_2027757545` | 590,314–710,360 | 589,314–709,360 | itself (1 px off) |
| order_silver | `Image_2128636029` | 467,315–587,361 | 466,315–586,361 | itself (1 px off) |
| glory_gold | `Image_922761653` | 467,216–587,263 | same | itself |
| noble_platinum | `Image_1524762867` | 467,266–587,312 | 590,265–710,311 | `vientiane_king`'s sprite |
| eternal_diamond | `Image_1228855450` | 590,265–710,311 | 732,251–852,297 | `noble_platinum`'s sprite |
| supreme_star | `Image_863215355` | 724,349–844,395 | 589,363–709,409 | `achievement_points` (95 %) |
| strongest_king | `Image_101164595` | 590,216–710,262 | 206,308–326,354 | `apprentice_rookie`'s sprite |
| vientiane_king | `Image_2002968821` | 725,300–845,346 | 466,266–586,312 | **`我的皮肤` `Image_410780920`** (97 %) |
| my_chessplayers | `Image_1904551913` | 590,363–707,408 | 464,364–581,409 | `supreme_star`'s sprite (95 %) |
| achievement_points | `Image_1965595528` | 847,383–963,429 | 731,348–847,394 | `Image_981211366` (70 %), QQ icon `Image_1343071809` (39 %), two dots |
| total_power | `Image_255772017` | 914,97–1010,147 | 731,397–827,447 | dark circle `Image_1134586325` (44 %), portrait `Image_1487341597` (4 %) |
| total_achievement_points | `Image_1227545714` | 1,1–464,136 | same | itself |

Damaged sprites that are **not** in the catalog, cropped from the pristine 10-03 atlas into
`evidence/pre-update-sprites/`: `Image_410780920` (我的皮肤), `Image_981211366` (dashed lines),
`Image_1343071809` (QQ icon), `Image_1434219398` (WeChat icon, 1 %), `Image_1134586325` (dark circle),
`Image_1487341597` (portrait), `Image_1281642236` (vertical bar, ≤5 %), `Image_2043579572` and
`Image_494086371` (dots).

Still Chinese and **not in the catalog at all**: `Image_920603129` `总盈利` (device 376,308–463,353),
plus the round `胜利` and `失败` badges (around 760,150–830,220 and 235,210–300,270 today; their sprite
names have not been looked up yet).

The other two catalog textures with `regions`, `C9F49510F2F67402` (sprites in `22BD565B3703EDA9`) and
`E86DF43167CA2143` (sprites in `9F240FDA0FA58988`), match the device rects exactly. The 19 single-sprite
120×46 and 372×102 RGBA32 textures have nothing to move.

**Not verified on the device:** which screens draw the misplaced labels. The user's Career screen showed
"APPRENTICE ROOKIE II" and "SUPREME STAR" correctly, so the rank badge there probably comes from the
standalone 120×46 textures rather than this atlas. Find where each moved sprite is drawn before you claim
a visible regression for it. The one in-atlas case already seen on the phone is the `我的棋手` label on
the Career screen.

## Data on this machine

| what | where |
|---|---|
| today's device layer (already patched on 2026-10-08) | `dist/HOK ACE Patcher Data/sessions/20261010-115042/game/WXQ_Data/Package/builtin/19` |
| today's staged output (what is on the phone now) | `…/sessions/20261010-115042/staged/19` |
| pristine pre-update layer, 2026-10-03 | `dist/HOK ACE Patcher Data/pristine/20261003-173730/game/WXQ_Data/Package/builtin/19` |
| the APK's built-in layer (does **not** hold this atlas) | `dist/HOK ACE Patcher Data/prime-1005/builtin` |

There is **no clean copy of the post-update atlas**: both of today's pulls (11:25, 11:50) are
byte-identical and were already patched on 10-08. Original pixels for a damaged sprite therefore come
from the 10-03 pristine dump by sprite name. 215 of today's 218 sprites exist there, all at the same
size. Before you rely on that, check that undamaged sprites match pixel for pixel across the two dumps.

## Design (recommended; change it if the evidence says otherwise)

Read `docs/compose/spec/texture-translation.md` first, especially `[S2]` "Why a `.blocks` patch maps
block-for-block", "The label splice" and "`english_raw` contract". Its rule that a skipped texture beats
a failed run still applies.

1. **The device sprite table is a run-time input.** The layout has already changed at least once, so
   never hard-code device rects. Map each regioned atlas to the asset that holds its Sprite objects (a
   measured constant, `{0x13C19E4E4486B31C: 0x4AA2B26FF28CB65D}`, is acceptable), then read the rects
   from the device's copy of that asset each run with the parser in `sprite_table.py`. If the sprite
   asset is missing, or a region's sprite is absent or a different size, skip that texture into
   `graphics_skipped`. Never fall back to the PC offsets: that fallback is today's bug.
2. **Port by sprite, not by offset.** For a `.blocks` entry with `regions`, decode the English pixels
   inside each region's PC box from the BC7 payload. The blocks covering a box lie in `patch_ranges`;
   check that, and refuse rather than guess if they do not. Then composite those pixels into the
   **device** box of the same sprite, and re-encode only the ASTC blocks the device boxes touch. Device
   boxes are not 4-aligned (589, 731, 466…), so decode each touched block, overwrite only the box's
   pixels, then re-encode, leaving neighbouring sprites' pixels intact. When a region's PC box equals its
   device box, the result must stay byte-identical to today's port. `check_graphics.py` asserts that for
   the 324 `.blocks` entries; keep it true for every unregioned entry.
3. **Every touched pixel must be decided by our data, never by what the device copy holds.** The phone
   already carries the damage, and the pass reads whatever the phone has. So:
   - write the English for each of the 13 catalog sprites at its device box;
   - write **restoration pixels** for each non-catalog sprite listed above that the old port damaged.
     They come from the pristine crops, or from an English redraw where the sprite is a label;
   - the result is then identical whether the input atlas is pristine or carries the old damage, which
     is also what keeps the pass idempotent (`texture-translation.md`, "Re-run safety").
4. **New English labels are this repo's art**, as `catalog_id/previews/<HASH>.png` already is (see the
   header of `tools/research/make_language_payloads.py`). Never edit `resources/catalog/`. Put the new
   renders and restoration crops in a repo-owned place, for example `resources/sprites/<texture>/<sprite>.png`,
   which `build_exe.py` and `android/app/build.gradle.kts` must then stage too. Size each render to its
   sprite (117×45, 87×45…) and match the existing English labels' font and white-with-shadow style;
   crop "MY CHESSPLAYERS" out of the catalog's payload as the reference. Labels to draw:
   - `Image_410780920` 我的皮肤 → **MY SKINS**. The catalog has no entry, so record the wording as a
     free translation, the way `OFFICIAL_FIXES` does;
   - `Image_920603129` 总盈利 → **TOTAL PROFIT** (catalog: "Total profit"; Indonesian "Total keuntungan");
   - optional: the `胜利` / `失败` badges → VICTORY / DEFEAT (the catalog's "fail" is poor; choose and record).
   The Indonesian catalog has no payload for this atlas and falls back to English
   (`languages.payload_path`). Decide whether `catalog_id` gets its own renders for the new labels or
   uses English; the rank names are English in both.
5. **Device cycle.** This is a texture change on a reviewed edit, so it follows the device test loop in
   `docs/compose/spec/prime-rebuild.md` ("The device test loop"): build offline against a dump of the
   phone's own game-data version, back up `packages` + `Watchdog`, push, and walk the screens. The
   minimum walk is the Career screen with both switch states (My Chessplayers / My Skins), the rank
   badges, Total Power, Total Profit and Achievement Points, plus whatever screens step 0 below finds.

## Tasks

- [ ] T14.0 Find where each of the 9 moved sprites and the damaged non-catalog sprites are drawn in
      game, and screenshot the current (wrong) state. This sets the regression scope and the cycle's
      walk list. *Needs the phone; not started.*
- [x] T14.1 `tools/sprite_table.py` (all three regioned atlases mapped) and
      `tools/research/atlas_sprites.py table`. Reproduces both evidence tables exactly.
- [x] T14.2 `mobile_graphics.port_atlas`, wired through `port_graphics`. `check_graphics.py` green
      (new `[10]`; `--game` on both dumps). *Deviation:* output is not byte-identical from pristine and
      from already-patched input — a block whose pixels already show the target keeps its own bytes,
      so the two end 4 blocks apart on today's layer (decoded mean 0.000) and 2082 on the 10-03 one
      (decoded mean 0.025). Re-runs change nothing; unmoved atlases are byte-identical to the old port.
- [x] T14.3 19 restoration crops from the 10-03 dump (sprites the old footprint meets under either
      layout), used only while the device's art outside the footprint still matches the crop.
- [x] T14.4 MY SKINS and TOTAL PROFIT in `resources/sprites/13C19E4E4486B31C/labels/`, built from the
      catalog's own glyphs; staged by `build_exe.py` and `build.gradle.kts`. VICTORY / DEFEAT not done.
      Both languages use the English renders.
- [x] T14.5 Device cycle: the Career screen looks right (2026-10-10, session `20261010-151438`, one-texture
      push). Recorded in `sprite_table.py`, `mobile_graphics.py`, the spec and `docs/lab-notebook.md`.
- [x] T14.6 Docs: `texture-translation.md`, `translation-progress.md`, `AGENTS.md`, `README.md`,
      `docs/lab-notebook.md`. The 398 figure's meaning is unchanged.

## Separate, still open

The `国服` badge on the user's avatar frame belongs to the "National server Chess Player" avatar frame
(`国服骑手头像框`). The catalog has no texture edit for it and its texture has not been located. Use the
same method: frame prefab → sprite table → crop scan.

## Reproduce

```bat
.venv\Scripts\python.exe tasks\T14\sprite_table.py --package "dist\HOK ACE Patcher Data\sessions\20261010-115042\game\WXQ_Data\Package\builtin\19" --texture 13C19E4E4486B31C --sprites 4AA2B26FF28CB65D --out tasks\T14\evidence
```

`evidence/` holds: the user's screenshot; today's atlas with every device rect (red) and the catalog
boxes (yellow); the same for the 10-03 pristine atlas; both rect tables as JSON; and the pristine crops
of the damaged non-catalog sprites plus `总盈利`.
