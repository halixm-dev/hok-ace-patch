# Event start button: the Super Weekend skin of START GAME

Status: ready-for-human (button implemented and verified offline; room line and on-screen cycles waiting for the user)

## Problem

Since the latest game data, the lobby's start button shows an event skin: 开始游戏 over the line
"Super Weekend Perks Are Here!". The label stays Chinese on the phone and on the PC edition. The catalog's
two START GAME edits (`863114A42F12EF76`, `C9F49510F2F67402`, package `19`) are applied and verified on
disk, but this skin draws over them (lab notebook, 2026-11-21, "PC edition ticket 05"). The room screen's
event line `翻牌钻石翻倍 0/3，有分同享不限亲密度` stays Chinese too.

## Findings (offline, 2026-11-21; nothing read from `D:\WXQ` or the phone)

Sources: the PC scratch copy `D:\scratch\pc-edition-01\pc-game`. Its package `19` files hash equal to the
1.11.0.2 starting state in `D:\scratch\pc-edition-05\evidence\builtin.start.sha256`, so it is pristine
1.11.0.2. Phone pristine snapshots `20261029-1.8.0.1` and `20261118-1.10.1.2` under
`dist\HOK ACE Patcher Data\pristine\`.

### 1. The skin's label is `A71C734D3EFAFBFF`, package `19`

- Package `19` holds twelve 151,776 B assets, the size of a 372x102 RGBA32 label. Ten are catalog edits
  (START GAME, START MATCH, CONTINUE GAME, BATTLE TRAINING, READY UP, WAITING TO START, MATCHING, RANK
  MISMATCH, START TRAINING, CANCEL MATCH). Two are not:
  - **`A71C734D3EFAFBFF`: 开始游戏 in a warm cream gradient, with no iridescent sheen.** This is the event
    skin's label.
  - `0915100A62E078D8`: 确认选择 (CONFIRM CHOICE) as a standalone label. Unrelated to this ticket; see
    "Noticed in passing".
  Render: `pc-package19-372x102-labels.png` (bottom-up rows flipped; hash above each label).
- All twelve are loose sprites under `UIResources/GameCenter` (`751B471494DC6BC6` lists them by path;
  `C3B9AF45924422F7` is the global atlas/sprite registry). The Texture2D header of each is a separate
  ~2 KB asset that names only an anonymous `Image_<id>` and a `.resS` path. The header-to-pixels mapping was
  not resolved, because none of xxh64, FNV-1a, MD5, SHA-1, SHA-256 or the path's own hex gives the pixel
  hash. Only `Image_2023783232` also appears in the lobby atlas table (`22BD565B3703EDA9`) and a lobby
  prefab (`770C8EA0BD10E1F2`), which fits the plain START GAME. No prefab names the event sprite, so the
  event code swaps it in at run time.
- **Phone:** `A71C734D3EFAFBFF` is in package `19` of the 1.10.1.2 override layer, 16,864 B. That is the
  same ASTC 6x6 size as the phone's `863114A42F12EF76`. Decoded at 372x102@6x6, it is the same warm
  开始游戏 (`phone-1.10.1.2-event-vs-catalog.png`: event on the left, catalog START GAME on the right).
  It is absent at 1.8.0.1. So the skin arrived between 1.8 and 1.10 on the phone and is in 1.11.0.2 on PC.
- **Not a recolor of START GAME.** Against `863114A42F12EF76`'s pristine pixels, only 57% of alpha values
  are equal (max difference 255), and the colour is a warm vertical gradient (row means about
  (233,224,221) at the bottom to (255,244,234) at the top) instead of the cool sheen. A mechanical tint of
  the existing English art is therefore an approximation, not a port.
- **The subtitle is text, and it is already translated.** "Super Weekend Perks Are Here!" is the
  supplement's `超级周末，特权开启！`. Only the 开始游戏 label is baked art.

### 2. The room line is an uncatalogued, sealed config bin, so it is not supplement-able on its own

- Source: package `1`, asset **`9E924AAB5066EE19`** (293 B; on the phone at 1.10.1.2, absent at 1.8.0.1).
  It is a config bin, sealed: `config_bin.is_sealed` reads it true, with field 1 an MD5 string and field 4
  a checksum. It holds 7 perk rows (id, name, sort): `首胜额外加分 %d/%d`, `对局失败不扣分 %d/%d`,
  `翻牌钻石翻倍 %d/%d`, `有分同享不限亲密度`, `前3局亲密度加成`, `组排不掉分 %d/%d`, `全棋手限免`. The room
  screen joins the active perks with `，` and fills `%d/%d`.
- It is not in the catalog's `table_hashes`, so the text pass never stages it (`_drop_uncatalogued_tables`),
  and a supplement entry alone changes nothing on screen. None of the 7 strings is in the catalog's
  `unique`. The supplement has related wordings (`超级周末：有分同享不限亲密度`, `限时福利：每天前{1}次翻出钻石翻倍（{0} / {1}）`)
  but not these 7.
- The only route the rules allow is the allowlist (ADR 0004): add the 7 strings to the supplement, put
  `9E924AAB5066EE19` on `extra_text.CANDIDATE_ASSETS`, and clear it with a device cycle (`--cycle-asset`)
  and, for the PC edition, a PC cycle. One code gap is in the way: `rewrite_config` sends every bin except
  the lineup bins through `pb_text.rewrite`, which does not reseal. A generic rewrite would leave field 4
  stale, which is the failure that withdrew the earlier bins (ADR 0005). Sealed bins need a
  `config_bin.reseal` step first.

## Proposal (3): translate `A71C734D3EFAFBFF` as a repo-drawn label texture

`DEVICE_REVISIONS` is ruled out. `A71C734D3EFAFBFF` is a different image from `863114A42F12EF76`, not a
revision of it (see above), so aliasing would paint the cool START GAME art into the warm skin, and that
is not a measured match.

Recommended: **a standalone label texture drawn from this repo's art**, the whole-texture counterpart of
`LABEL_ATLASES`. `resources/catalog/` stays untouched.

- **Art** in `resources/sprites/A71C734D3EFAFBFF/labels/`, one top-down 372x102 RGBA PNG per language:
  `en/start_game.png` (START GAME) and `id/start_game.png` (MULAI GAME). This is the first per-language
  label, because every existing `labels/` render is English in both languages. The art is
  hand-finished and the source of truth, like the other `labels/`. A first draft can come from the
  catalog's English START GAME and `catalog_id/previews/863114A42F12EF76.png`, re-shaded with the event's
  measured gradient and without the sheen, for the user to approve or replace (as with `mulai_game.png`).
- **Code** (one ticket):
  - `mobile_graphics.LABEL_TEXTURES = {0xA71C734D3EFAFBFF: (372, 102)}` plus `label_texture(raw, texture,
    language)`. On the phone it decodes the ASTC at the layout its size gives (6x6), pastes the art, and
    re-encodes only the blocks the art changes, as the RGBA32 `.blocks` path does. On the PC it writes
    RGBA32 rows bottom-up.
  - `device_extensions` stages it where it stages `LABEL_ATLASES`, counted as a texture, and the append
    pass carries it where package `19` is append-only.
  - `pc_catalog` adds an in-code entry, as `_title_atlas` does: a `.blocks` payload with `source_sha256`
    from the installed bytes, refused when the installed size is not 151,776 B.
  - Nothing is drawn when the texture is absent (older data), and a size other than the expected one is
    refused and counted as skipped, never raised.
- **Docs in the same change:** `docs/features/texture-translation.md` and `indonesian-language.md`;
  `docs/translation-progress.md` (+1 repo-drawn texture; Indonesian re-draws 2 → 3); AGENTS.md
  **Coverage** ("34 repo-drawn atlas labels" gains a standalone label texture, and the "English in both
  languages" clause gets an exception); a lab-notebook entry; `check_graphics.py` coverage if it counts
  labels.
- **Verification:** `check_graphics.py` offline. Offline staging against the 1.10.1.2 snapshot (the phone),
  with read-back that only blocks under the art changed. `--pc-selftest` on the PC scratch copy. Then one
  device cycle and one PC cycle, each **with the user's permission**, while the Super Weekend skin is
  live, because it shows only during the event.

Alternative, not recommended: add a graphics record and payload to the catalogs through
`apply_catalog_fixes.py` (a new `catalog_graphics_additions.json`). It is literally a "catalog edit", but
it writes payload files into upstream-owned `resources/catalog/` and widens the one sanctioned catalog
write from text to graphics. An upstream import could also later collide with a real upstream edit of
the same hash.

## Decisions for the user

1. ~~Mechanism for the button~~ **Decided 2026-11-21 (user): repo-drawn label texture.** The catalog
   addition through `apply_catalog_fixes.py` is not pursued.
2. Art. Drafts for review are in `drafts/`: `draft-en.png` and `draft-id.png` (top-down 372x102). They take
   the catalog's English and Indonesian START GAME art and re-shade each row to the event label's measured
   colour, with alpha kept. `compare.png` shows them over a dark and a warm background next to the game's
   event label and the catalog art. Known difference: the catalog art has a dark bevelled edge, which the
   re-shade turns brown, and the event label has only a soft shadow. **Decided 2026-11-21 (user): ship the drafts.** They are `resources/sprites/A71C734D3EFAFBFF/labels/en|id/start_game.png`.
3. Room line: queue `9E924AAB5066EE19` as a candidate (supplement strings + a reseal path in
   `rewrite_config` + device and PC cycles), or leave it Chinese.
4. The AGENTS.md Coverage rule change that the chosen mechanism needs (a standalone repo-drawn label
   texture, re-drawn per language). It lands with the implementation, in the same change.

## Noticed in passing

- `0915100A62E078D8` (确认选择, standalone 372x102 label, package `19`, PC and phone 1.10.1.2) has no
  catalog edit either. The catalog covers CONFIRM CHOICE only inside the atlas `E86DF43167CA2143`. If a
  screen draws it, it is a gap of the same kind.

## Out of scope

Anything on `D:\WXQ` or the phone until the user allows a cycle; other event skins not yet seen.

## Comments

- 2026-11-21: implemented as `mobile_graphics.LABEL_TEXTURES` / `label_texture`, staged by
  `device_extensions.port_graphics` and `pc_catalog._label_textures`. Verified offline on the phone's 1.10.1.2
  layer and the PC scratch copy (lab notebook, "Event start button"). Still owed: a phone cycle and a PC cycle
  while the event is live, both with the user's permission; the room line (decision 3).
