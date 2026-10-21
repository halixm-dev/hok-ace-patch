# 03: Lineup translations in both languages

**What to build:** English and Indonesian for every lineup string ticket 01 lists, so the share-code pass has something to write. None of these strings are in either catalog today.

- Add them through the catalog supplement, which only fills sources the catalog has no entry for. The catalog files themselves are not edited (`AGENTS.md`).
- Every target passes `adaptive.validate_translation` and keeps its source's placeholders and tags.
- Hero, faction and keyword names read as the terminology table and the catalog already read them (the 芈月 tactic-card text says *Tactic Card* the way card texts do). Reuse the catalog's own wording for phrases it already translates.
- Keep names short: the lineup name sits on a narrow card and in the share code's `【name】` prefix.
- Check that the supplement's own check passes for both languages.

**Blocked by:** 01

**Status:** done

- [x] Every string from ticket 01 has an English and an Indonesian target
- [x] All targets validate; the supplement check passes
- [x] Keyword names match the terminology table on both catalogs

## Comments

2026-10-21: done in `tools/catalog_supplement.py` (`TEXTS`, section "Official lineups"). 198 strings gain an
English and an Indonesian target; the other three (`召唤自爆流`, `核心输出`, `核心坦克`) already have catalog entries,
which win. Checked offline on both catalogs: `catalog_supplement.check` is empty, every target passes
`adaptive.validate_translation`, keeps its `【...】` brackets and has no Chinese left, and the terminology table
rewrites none of them. Names follow the catalog: heroes and Chessplayers by their catalog names (`小明` is Ming,
`东皇` Donghuang, `干将` Gan), factions as Three Kingdoms / Riverlands / Sunset / Central Plains / Zhulu Plateau,
keywords as Prepare, Deploy, Combine, Sacrifice, Initiate, Clash, Totem, Ancient Coin, Temporary Level. Measured
choices where the catalog splits: `战术牌` is *Tactics Card* (54 of 54 English uses, 50 of 54 Indonesian), `秘技牌` /
`秘技卡` *Secret Skill Card* (the catalog's `秘技` and most `秘技卡` uses; *Secret Technique* is the other half), `宝藏牌`
*Treasure Card* / *Kartu Treasure*. `出击` has no keyword entry in either catalog; it reads *Strike* (`飞行器出击`).
`流` names end in *Build*, as the catalog's own lineup names do (Indonesian: *Build X*, its majority order).
For ticket 04: the targets are reached by `entries(unique, code)` or a loaded catalog's `unique`, keyed by the
exact Chinese.
