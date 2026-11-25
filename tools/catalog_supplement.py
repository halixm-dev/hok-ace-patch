"""Translations for text the game added after the catalog was built, merged into the catalog as it loads.

The catalog is the PC pipeline's file and is not edited here (`AGENTS.md`), so data updates that add or
reword strings in tables the catalog already covers leave those rows Chinese until upstream catches up.
Game data 1.5.0.1 and 1.6.0.1 added about 1200 such strings to package `1`: an achievement-title system
whose titles come in numbered tiers (`完美橱窗(二)`), four weekly leaderboards ranked 1 to 100, the King of
Kings sub-account, the Line Puppy event, and card texts whose numbers changed. Game data 1.7.0.1 added 335
more: the Super Hero mode, room settings, the reworked Lineup Recommendation, strategy tags, and talent texts
split from their series header. Game data 1.7.0.2 added six Lineup Recommendation hints and errors, and
1.8.0.1 added 108: Wu Feng's event, team and Invisible-mode prompts, and reworded card texts.
Game data 1.9.0.1 added 213 catalog-table strings: the Black & White Central Plains blind boxes,
Faction Highlights, Double Energy Storage missions, and reworded card and skill texts, plus two
missing descriptions in the allowed Official recommendation lineup bin.
Game data 1.10.0.1 added 158 catalog-table strings: the Duo Festival, Super Weekend,
Quick Match, Intimacy gifting, and reworded card and talent effects.
Game data 1.11.0.1 added 203 catalog-table strings: the Starry Brocade Wish and its gifting shop,
ACE Quick Match, the Weaving the Stars mansions, team queue settings, and two reworded card texts.
Game data 1.12.0.1 added 68 measured catalog-table strings for the Hall of Glory, Quick Match,
Surprise Gacha, Super Weekend, Starry Brocade gifting, and cross-game status.
`apply` fills them in.
The pairs are data, not code: `resources/catalog_supplement/texts.json` (`TEXTS`) and `leaderboards.json`
(`LEADERBOARDS`), each a list of sections, a `note` and its `{zh: [English, Indonesian]}` texts, read once
at import. Both patchers ship the folder beside the catalogs. The generators below stay code.

A string a game data update adds goes here, as a new section at the end of `texts.json` (`AGENTS.md`,
"Update strings"): it never touches the shipped catalog file, the catalog's own entry wins as soon as
upstream has one, and `check` guards its markup. `tools/research/catalog_additions.json` writes into both
catalog files instead; it holds the October 2026 update's 1 092 strings, added before this supplement
existed, and is only corrected, never extended, so the catalog files stay upstream's plus the fixes.
The official lineups' strategy text is here too: it lives in config bins the catalog does not cover, inside
their share codes, for the share-code pass to write.
`derived` adds the short forms the card-pack covers label each cover with (`逆天改命卡包`, `河洛-李白`),
whose wording the catalog carries only inside its own longer strings; that bin itself was withdrawn. It
also splits the catalog's two-line talent texts into the effect and the series name the new tables hold.

Three rules keep this from becoming a second catalog:

- An entry is added only when the catalog has **no** translation for its Chinese source; a catalog entry
  always wins, so an upstream re-import supersedes this file one string at a time.
- Every target keeps its source's `{placeholders}`, `%s` and `<tags>` exactly; `translate_table` drops a
  record whose placeholders changed, and `check` proves none did.
- Tiered titles and leaderboard ranks are generated, not listed: a tier is the catalog's own name for the
  base title plus a Roman numeral, and a rank is the catalog's own sentence for that leaderboard.

It runs before the glossary (`terminology.apply`), so a supplied string obeys the same one-name-per-keyword
rule as the catalog's.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# Chinese numerals as the game writes them in tier suffixes and ranks (一 .. 一百).
_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_ROMAN = ("", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X")
# translate_table compares these between source and target.
_MARKUP = re.compile(r"\{[^{}]*\}|%[sd]|<[^<>]*>")

# The literal pairs are data: resources/catalog_supplement/, beside the catalogs.
_DATA = "catalog_supplement"


def _data_dir() -> Path:
    """The supplement's data folder: beside this module in the frozen exe, beside `tools/` in the Android
    engine, and under `resources/` in the source tree."""
    here = Path(__file__).resolve().parent
    for folder in (here / _DATA, here.parent / _DATA, here.parent / "resources" / _DATA):
        if folder.is_dir():
            return folder
    raise FileNotFoundError(f"catalog supplement data ({_DATA}/) is missing beside {here}")


def _unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """A JSON object that refuses a repeated key instead of keeping the last one."""
    out: dict[str, object] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"catalog supplement repeats the source {key!r}")
        out[key] = value
    return out


def _load(name: str) -> dict[str, tuple[str, str]]:
    """zh -> (English, Indonesian) from <name>: a list of sections, each a `note` and its `texts`
    (`{zh: [English, Indonesian]}`), kept in file order."""
    sections = json.loads((_data_dir() / name).read_text(encoding="utf-8"), object_pairs_hook=_unique_keys)
    out: dict[str, tuple[str, str]] = {}
    for section in sections:
        for zh, pair in section["texts"].items():
            if zh in out:
                raise ValueError(f"catalog supplement repeats the source {zh!r} in {name}")
            if not (isinstance(pair, list) and len(pair) == 2 and all(isinstance(text, str) for text in pair)):
                raise ValueError(f"catalog supplement entry {zh!r} in {name} is not [English, Indonesian]")
            out[zh] = (pair[0], pair[1])
    return out


# zh -> (English, Indonesian), grouped by where the game shows them; each data update adds a section.
TEXTS: dict[str, tuple[str, str]] = _load("texts.json")
# The weekly leaderboards, ranked 第一 .. 第一百: `{n}` is the rank, `%s%s` the season and the Chessplayer.
LEADERBOARDS: dict[str, tuple[str, str]] = _load("leaderboards.json")

# "<Chessplayer>上大分" titles; the catalog only has the longer "<Chessplayer>这波上大分" (Scores Big).
SCORES_BIG = ("乔汐", "姜导", "嬴律", "孙小宾", "安琪拉", "小妲己", "常小娥", "庄小鱼", "弈星", "明先生", "昭君",
              "武凤", "玉环", "班叔", "瑶妹", "白歌", "镜", "闹闹", "阿离", "香香", "马可")

# The base titles whose numbered tiers 1.6.0.1 added, each translated by the catalog under its own name.
TIERED_TITLES = (
    "E人聚集", "一刹光辉", "一直合成一直爽", "万众瞩目", "万象启幕", "万象棋天天见", "万象答王", "不差钱", "临危受命",
    "买它！买它！", "人形印钻", "人气新星", "人见人爱", "以武会友", "众人拾柴", "传说卡皇", "你是懂表情的", "停不下来",
    "光彩夺目", "全员百分百", "八方来财", "兵器谱", "冠绝天下", "刷到停不下", "刷到天荒地老", "勤修不辍", "包发财",
    "包大人", "千招百式", "印记收集者", "口令专家", "史诗卡佬", "同享常驻", "启程之证", "命中之神", "啥都试试",
    "善财童子", "嗨起来", "夜以继日", "大腿带飞", "大额开张", "天下英雄", "头号闺蜜", "奶妈的自我修养", "好礼相赠",
    "完美橱窗", "带飞队长", "常胜将军", "常驻粉丝", "幻梦星彩", "开黑团长", "彩戏师", "彩虹屁大师", "得心应手",
    "心路历程", "忠实观众", "快聊选手", "快速成长", "成长之路", "我就要它", "我有钥", "我爱我家", "我要验牌",
    "戳到你了", "扩容一下", "扶我起来", "抄作业大师", "披星戴月", "拉拉队教练", "拍卖大师", "拍卖新秀", "持家有道",
    "指法芬芳", "挚爱亲朋", "整点活儿", "无限后手", "星耀无忧者", "显眼包", "最佳搭子", "最强大脑", "来啥打啥",
    "来打我呀", "框王", "步步高升", "水晶收集者", "永不言六", "泡言泡语", "洒洒水啦", "海内存知己", "清仓",
    "游戏人生", "满勤王", "炉火纯青", "热情观众", "牌界中坚", "特邀大使", "独树一帜", "王牌选手", "王者之路",
    "王者无忧者", "生意头脑", "登峰之路", "白手起家", "省钱新手", "眼光独到", "眼花缭乱", "稀有卡痴", "竞拍强者",
    "红包收割机", "纳税大户", "翻一番", "肝胆相照", "花钱不眨眼", "荣光追迹者", "荣耀会员", "行走的能量黑洞",
    "认真学习", "豪气干云", "豪气抵扣", "财大气粗", "财源滚滚", "贴贴", "赢赢赢！", "路漫漫", "躺赢", "轻拳出击",
    "输出拉满", "过命兄弟", "还活着", "这波不亏", "连看之巅", "逐宝问珍", "钞能力玩家", "钻石大亨", "钻石无忧者",
    "钻石蒸发术", "铁杆死党", "铂金无忧者", "长安舞榭", "随叫随到", "集卡新秀", "零元GO", "颜艺", "高光时刻",
    "黄金无忧者", "鼓励师",
) + tuple(f"{name}上大分" for name in SCORES_BIG)
TIERS = 10
RANKS = 100

# The card-pack covers bin `9E45602F1857539D` (Encyclopedia > Diamond Frenzy > Starting Lineup) labels
# each cover with a short form of a name the catalog only has inside a longer string. Its device cycle
# was withdrawn (2026-10-16, `extra_text`), so these reach only a catalog table that holds the same short
# form; they stay because a catalog string never needs a cycle, and a resealed bin would need them. `derived` generates
# the targets from those longer strings: a pack header from the catalog's coloured header, a contract
# from its `契约·` form, a hero from its `逆天改命(<hero>)` pack name. The faction-hero labels have no
# longer form anywhere, so their sources are listed and their targets joined from the catalog's own
# faction and hero names.
_PACK_HEADER = re.compile(r"<color=[^>]+>([^<]+卡包)</color>")
_COLORED = re.compile(r"<color=[^>]+>([^<]+)</color>")
_CONTRACT = re.compile(r"契约·([^()]+\([^()]+\))")
_HERO_PACK = re.compile(r"逆天改命\(([^()]+)\)")
_CONTRACT_PREFIX = "Contract: "
FACTION_HEROES = (
    "河洛-李白", "河洛-李信", "日落海-艾琳", "日落海-莱西奥", "三分-诸葛亮", "三分-甄姬",
    "逐鹿-蒙犽", "逐鹿-嬴政", "逐鹿-扁鹊", "大河-韩信", "大河-刘邦", "大河-大司命",
)
# Game data 1.7.0.1 split each talent's text: the catalog has "<series header>\n<effect>" as one string,
# the new tables hold the effect alone and the series name (`╬整备系列`) without its tags. `derived`
# takes both from the catalog's two-line form.
_SERIES = "系列"
_TAG = re.compile(r"<[^<>]*>")


def chinese_number(value: int) -> str:
    """<value> (1..100) the way the game writes it: 七, 十八, 七十五, 一百."""
    if value == 100:
        return "一百"
    tens, ones = divmod(value, 10)
    digits = "一二三四五六七八九"
    head = "" if tens == 0 else ("十" if tens == 1 else digits[tens - 1] + "十")
    return head + (digits[ones - 1] if ones else "")


def _title(unique: dict[str, str], zh: str) -> str | None:
    """The catalog's name for title <zh>, tidied for use with a tier suffix."""
    if zh.endswith("上大分") and zh not in unique:
        name = unique.get(zh[:-3])
        return f"{name} Scores Big" if name else None
    text = unique.get(zh)
    if not text:
        return None
    text = text.strip().rstrip(".")
    return text[:1].upper() + text[1:]


def _inner(target: str, prefix: str, wrapped: str) -> str | None:
    """The part of <target> that sits where <wrapped> does in the source's longer form, or None."""
    if not target.startswith(prefix):
        return None
    rest = target[len(prefix):]
    return rest[1:-1] if wrapped == "()" and rest.startswith("(") and rest.endswith(")") else rest


def derived(unique: dict[str, str]) -> dict[str, str]:
    """Short forms whose translation the catalog carries only inside a longer string of its own."""
    out: dict[str, str] = {}
    for zh, target in unique.items():
        if match := _PACK_HEADER.fullmatch(zh):
            inner = _COLORED.fullmatch(target)
            if inner:
                out[match[1]] = inner[1]
        elif match := _CONTRACT.fullmatch(zh):
            if target.startswith(_CONTRACT_PREFIX):
                out[match[1]] = target[len(_CONTRACT_PREFIX):]
        elif match := _HERO_PACK.fullmatch(zh):
            pack = unique.get("逆天改命")
            hero = _inner(target, f"{pack} ", "()") if pack else None
            if hero:
                out[match[1]] = hero
    for zh in FACTION_HEROES:
        faction, hero = zh.split("-", 1)
        parts = unique.get(faction), unique.get(hero) or out.get(hero)
        if all(parts):
            out[zh] = f"{parts[0]} - {parts[1]}"
    for zh, target in unique.items():
        head, _, body = zh.partition("\n")
        target_head, _, target_body = target.partition("\n")
        series = _TAG.sub("", head)
        if not series.endswith(_SERIES) or not target_body or body.count("\n") != target_body.count("\n"):
            continue
        for source, text in ((body, target_body), (series, _TAG.sub("", target_head))):
            if text.strip() and not check({source: text}):
                out.setdefault(source, text.strip())
    return out


def entries(unique: dict[str, str], code: str) -> dict[str, str]:
    """Every supplementary (Chinese -> target) pair for language <code>, given the catalog's <unique> map."""
    index = 1 if code == "id" else 0
    out = {zh: pair[index] for zh, pair in TEXTS.items()}
    for prefix, pair in LEADERBOARDS.items():
        for rank in range(1, RANKS + 1):
            out[prefix + chinese_number(rank)] = pair[index].replace("{n}", str(rank))
    for zh in TIERED_TITLES:
        title = _title(unique, zh)
        if title is None:
            continue
        if zh.endswith("上大分"):
            out.setdefault(zh, title)
        for tier in range(1, TIERS + 1):
            out[f"{zh}({chinese_number(tier)})"] = f"{title} ({_ROMAN[tier]})"
    for zh, target in derived(unique).items():
        out.setdefault(zh, target)
    return out


def check(pairs: dict[str, str]) -> list[str]:
    """The sources in <pairs> whose target does not carry exactly the source's placeholders and tags."""
    return [zh for zh, target in pairs.items()
            if sorted(_MARKUP.findall(zh)) != sorted(_MARKUP.findall(target))]


def apply(data: dict, code: str) -> int:
    """Add this module's translations to a loaded `catalog.json.gz` in place; returns how many were added.

    Only sources the catalog does not translate are added, so the catalog always wins.
    """
    unique = data.setdefault("unique", {})
    pairs = entries(unique, code)
    bad = check(pairs)
    if bad:
        raise ValueError(f"catalog supplement changes the placeholders of {bad[:3]}")
    added = 0
    for zh, target in pairs.items():
        if zh not in unique:
            unique[zh] = target
            added += 1
    return added
