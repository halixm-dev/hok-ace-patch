//! `tools/catalog_supplement.py`: translations for text the game added after the catalog was built,
//! merged into the catalog as it loads. A supplied string never wins over the catalog's own, and every
//! target keeps its source's placeholders and tags.
//!
//! The literal pairs are data (`resources/catalog_supplement/texts.json` and `leaderboards.json`); the
//! generators (tiered titles, leaderboard ranks, the derived short forms) are code here as there.

use crate::pystr;
use indexmap::IndexMap;
use regex::Regex;
use serde::de::{self, Deserializer, MapAccess, SeqAccess, Visitor};
use serde_json::{Map, Value};
use std::fmt;
use std::path::Path;
use std::sync::OnceLock;

/// zh -> (English, Indonesian), in file order.
pub type Pairs = IndexMap<String, (String, String)>;

/// The two data files, as `_load` reads them.
#[derive(Debug)]
pub struct Supplement {
    pub texts: Pairs,
    pub leaderboards: Pairs,
}

/// A JSON value that refuses a repeated object key (`_unique_keys`), giving the key back.
struct Unique(Value);

impl<'de> serde::Deserialize<'de> for Unique {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        deserializer.deserialize_any(UniqueVisitor).map(Unique)
    }
}

struct UniqueVisitor;

impl<'de> Visitor<'de> for UniqueVisitor {
    type Value = Value;

    fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("a JSON value")
    }
    fn visit_bool<E>(self, value: bool) -> Result<Value, E> {
        Ok(Value::Bool(value))
    }
    fn visit_i64<E>(self, value: i64) -> Result<Value, E> {
        Ok(value.into())
    }
    fn visit_u64<E>(self, value: u64) -> Result<Value, E> {
        Ok(value.into())
    }
    fn visit_f64<E>(self, value: f64) -> Result<Value, E> {
        Ok(serde_json::Number::from_f64(value).map_or(Value::Null, Value::Number))
    }
    fn visit_str<E>(self, value: &str) -> Result<Value, E> {
        Ok(Value::String(value.to_owned()))
    }
    fn visit_string<E>(self, value: String) -> Result<Value, E> {
        Ok(Value::String(value))
    }
    fn visit_unit<E>(self) -> Result<Value, E> {
        Ok(Value::Null)
    }
    fn visit_seq<A: SeqAccess<'de>>(self, mut seq: A) -> Result<Value, A::Error> {
        let mut out = Vec::new();
        while let Some(Unique(value)) = seq.next_element()? {
            out.push(value);
        }
        Ok(Value::Array(out))
    }
    fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<Value, A::Error> {
        let mut out = Map::new();
        while let Some(key) = map.next_key::<String>()? {
            let Unique(value) = map.next_value()?;
            if out.contains_key(&key) {
                return Err(de::Error::custom(format!(
                    "catalog supplement repeats the source {}",
                    crate::catalog::py_repr(&key)
                )));
            }
            out.insert(key, value);
        }
        Ok(Value::Object(out))
    }
}

/// `_load`: a list of sections, each a `note` and its `{zh: [English, Indonesian]}` texts.
pub fn load(path: &Path) -> Result<Pairs, String> {
    let name = path
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("");
    let text = std::fs::read_to_string(path).map_err(|error| error.to_string())?;
    let Unique(sections) = serde_json::from_str(&text).map_err(|error| {
        // serde appends the position; Python's ValueError text is the message alone.
        let message = error.to_string();
        match message.rfind(" at line ") {
            Some(at) if message.starts_with("catalog supplement") => message[..at].to_owned(),
            _ => message,
        }
    })?;
    let mut out = Pairs::new();
    for section in sections.as_array().ok_or("sections must be a list")? {
        let texts = section
            .get("texts")
            .and_then(Value::as_object)
            .ok_or("a section's texts must be an object")?;
        for (zh, pair) in texts {
            if out.contains_key(zh) {
                return Err(format!(
                    "catalog supplement repeats the source {} in {name}",
                    crate::catalog::py_repr(zh)
                ));
            }
            match pair.as_array().map(Vec::as_slice) {
                Some([Value::String(english), Value::String(indonesian)]) => {
                    out.insert(zh.clone(), (english.clone(), indonesian.clone()));
                }
                _ => {
                    return Err(format!(
                        "catalog supplement entry {} in {name} is not [English, Indonesian]",
                        crate::catalog::py_repr(zh)
                    ));
                }
            }
        }
    }
    Ok(out)
}

impl Supplement {
    /// Both data files from <folder> (`_data_dir()`, which the caller resolves).
    pub fn load(folder: &Path) -> Result<Self, String> {
        Ok(Self {
            texts: load(&folder.join("texts.json"))?,
            leaderboards: load(&folder.join("leaderboards.json"))?,
        })
    }
}

const ROMAN: [&str; 11] = [
    "", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
];
pub const TIERS: u32 = 10;
pub const RANKS: u32 = 100;
const SCORES_SUFFIX: &str = "上大分";

/// "<Chessplayer>上大分" titles; the catalog only has the longer "<Chessplayer>这波上大分".
pub const SCORES_BIG: &[&str] = &[
    "乔汐",
    "姜导",
    "嬴律",
    "孙小宾",
    "安琪拉",
    "小妲己",
    "常小娥",
    "庄小鱼",
    "弈星",
    "明先生",
    "昭君",
    "武凤",
    "玉环",
    "班叔",
    "瑶妹",
    "白歌",
    "镜",
    "闹闹",
    "阿离",
    "香香",
    "马可",
];

/// The base titles whose numbered tiers 1.6.0.1 added (before the `SCORES_BIG` ones).
pub const TIERED_TITLES: &[&str] = &[
    "E人聚集",
    "一刹光辉",
    "一直合成一直爽",
    "万众瞩目",
    "万象启幕",
    "万象棋天天见",
    "万象答王",
    "不差钱",
    "临危受命",
    "买它！买它！",
    "人形印钻",
    "人气新星",
    "人见人爱",
    "以武会友",
    "众人拾柴",
    "传说卡皇",
    "你是懂表情的",
    "停不下来",
    "光彩夺目",
    "全员百分百",
    "八方来财",
    "兵器谱",
    "冠绝天下",
    "刷到停不下",
    "刷到天荒地老",
    "勤修不辍",
    "包发财",
    "包大人",
    "千招百式",
    "印记收集者",
    "口令专家",
    "史诗卡佬",
    "同享常驻",
    "启程之证",
    "命中之神",
    "啥都试试",
    "善财童子",
    "嗨起来",
    "夜以继日",
    "大腿带飞",
    "大额开张",
    "天下英雄",
    "头号闺蜜",
    "奶妈的自我修养",
    "好礼相赠",
    "完美橱窗",
    "带飞队长",
    "常胜将军",
    "常驻粉丝",
    "幻梦星彩",
    "开黑团长",
    "彩戏师",
    "彩虹屁大师",
    "得心应手",
    "心路历程",
    "忠实观众",
    "快聊选手",
    "快速成长",
    "成长之路",
    "我就要它",
    "我有钥",
    "我爱我家",
    "我要验牌",
    "戳到你了",
    "扩容一下",
    "扶我起来",
    "抄作业大师",
    "披星戴月",
    "拉拉队教练",
    "拍卖大师",
    "拍卖新秀",
    "持家有道",
    "指法芬芳",
    "挚爱亲朋",
    "整点活儿",
    "无限后手",
    "星耀无忧者",
    "显眼包",
    "最佳搭子",
    "最强大脑",
    "来啥打啥",
    "来打我呀",
    "框王",
    "步步高升",
    "水晶收集者",
    "永不言六",
    "泡言泡语",
    "洒洒水啦",
    "海内存知己",
    "清仓",
    "游戏人生",
    "满勤王",
    "炉火纯青",
    "热情观众",
    "牌界中坚",
    "特邀大使",
    "独树一帜",
    "王牌选手",
    "王者之路",
    "王者无忧者",
    "生意头脑",
    "登峰之路",
    "白手起家",
    "省钱新手",
    "眼光独到",
    "眼花缭乱",
    "稀有卡痴",
    "竞拍强者",
    "红包收割机",
    "纳税大户",
    "翻一番",
    "肝胆相照",
    "花钱不眨眼",
    "荣光追迹者",
    "荣耀会员",
    "行走的能量黑洞",
    "认真学习",
    "豪气干云",
    "豪气抵扣",
    "财大气粗",
    "财源滚滚",
    "贴贴",
    "赢赢赢！",
    "路漫漫",
    "躺赢",
    "轻拳出击",
    "输出拉满",
    "过命兄弟",
    "还活着",
    "这波不亏",
    "连看之巅",
    "逐宝问珍",
    "钞能力玩家",
    "钻石大亨",
    "钻石无忧者",
    "钻石蒸发术",
    "铁杆死党",
    "铂金无忧者",
    "长安舞榭",
    "随叫随到",
    "集卡新秀",
    "零元GO",
    "颜艺",
    "高光时刻",
    "黄金无忧者",
    "鼓励师",
];

pub const FACTION_HEROES: &[&str] = &[
    "河洛-李白",
    "河洛-李信",
    "日落海-艾琳",
    "日落海-莱西奥",
    "三分-诸葛亮",
    "三分-甄姬",
    "逐鹿-蒙犽",
    "逐鹿-嬴政",
    "逐鹿-扁鹊",
    "大河-韩信",
    "大河-刘邦",
    "大河-大司命",
];
const CONTRACT_PREFIX: &str = "Contract: ";
const SERIES: &str = "系列";

struct Patterns {
    markup: Regex,
    pack_header: Regex,
    colored: Regex,
    contract: Regex,
    hero_pack: Regex,
    tag: Regex,
}

fn patterns() -> &'static Patterns {
    static PATTERNS: OnceLock<Patterns> = OnceLock::new();
    PATTERNS.get_or_init(|| {
        let full = |pattern: &str| {
            Regex::new(&format!(r"\A(?:{pattern})\z")).expect("a supplement pattern")
        };
        Patterns {
            markup: Regex::new(r"\{[^{}]*\}|%[sd]|<[^<>]*>").expect("the markup pattern"),
            pack_header: full(r"<color=[^>]+>([^<]+卡包)</color>"),
            colored: full(r"<color=[^>]+>([^<]+)</color>"),
            contract: full(r"契约·([^()]+\([^()]+\))"),
            hero_pack: full(r"逆天改命\(([^()]+)\)"),
            tag: Regex::new(r"<[^<>]*>").expect("the tag pattern"),
        }
    })
}

/// `chinese_number`: <value> (1..100) the way the game writes it: 七, 十八, 七十五, 一百.
pub fn chinese_number(value: u32) -> String {
    if value == 100 {
        return "一百".to_owned();
    }
    let digits: Vec<char> = "一二三四五六七八九".chars().collect();
    let (tens, ones) = (value / 10, value % 10);
    let mut out = String::new();
    match tens {
        0 => {}
        1 => out.push('十'),
        _ => {
            out.push(digits[tens as usize - 1]);
            out.push('十');
        }
    }
    if ones != 0 {
        out.push(digits[ones as usize - 1]);
    }
    out
}

type Unique_ = Map<String, Value>;

/// `unique.get(zh)` as Python's truthiness reads it: a non-empty string, else `None`.
fn lookup<'a>(unique: &'a Unique_, zh: &str) -> Option<&'a str> {
    unique
        .get(zh)
        .and_then(Value::as_str)
        .filter(|text| !text.is_empty())
}

/// `_title`: the catalog's name for title <zh>, tidied for use with a tier suffix.
fn title(unique: &Unique_, zh: &str) -> Option<String> {
    if let Some(base) = zh.strip_suffix(SCORES_SUFFIX)
        && !unique.contains_key(zh)
    {
        return lookup(unique, base).map(|name| format!("{name} Scores Big"));
    }
    let text = lookup(unique, zh)?;
    let text = pystr::strip(text).trim_end_matches('.');
    Some(pystr::capitalize_first(text))
}

/// `_inner`: the part of <target> where `()` wraps it in the source's longer form.
fn inner<'a>(target: &'a str, prefix: &str) -> Option<&'a str> {
    let rest = target.strip_prefix(prefix)?;
    // A one-character rest cannot both start with "(" and end with ")".
    if rest.len() >= 2 && rest.starts_with('(') && rest.ends_with(')') {
        Some(&rest[1..rest.len() - 1])
    } else {
        Some(rest)
    }
}

/// `derived`: short forms whose translation the catalog carries only inside a longer string.
pub fn derived(unique: &Unique_) -> IndexMap<String, String> {
    let p = patterns();
    let mut out: IndexMap<String, String> = IndexMap::new();
    let strings = || {
        unique
            .iter()
            .filter_map(|(zh, target)| target.as_str().map(|target| (zh, target)))
    };
    for (zh, target) in strings() {
        if let Some(found) = p.pack_header.captures(zh) {
            if let Some(inner) = p.colored.captures(target) {
                out.insert(found[1].to_owned(), inner[1].to_owned());
            }
        } else if let Some(found) = p.contract.captures(zh) {
            if let Some(rest) = target.strip_prefix(CONTRACT_PREFIX) {
                out.insert(found[1].to_owned(), rest.to_owned());
            }
        } else if let Some(found) = p.hero_pack.captures(zh) {
            let hero =
                lookup(unique, "逆天改命").and_then(|pack| inner(target, &format!("{pack} ")));
            if let Some(hero) = hero.filter(|hero| !hero.is_empty()) {
                out.insert(found[1].to_owned(), hero.to_owned());
            }
        }
    }
    for zh in FACTION_HEROES {
        let (faction, hero) = zh.split_once('-').expect("a faction hero has a dash");
        let faction = lookup(unique, faction).map(str::to_owned);
        let hero = lookup(unique, hero)
            .map(str::to_owned)
            .or_else(|| out.get(hero).filter(|text| !text.is_empty()).cloned());
        if let (Some(faction), Some(hero)) = (faction, hero) {
            out.insert((*zh).to_owned(), format!("{faction} - {hero}"));
        }
    }
    for (zh, target) in strings() {
        let (head, body) = zh.split_once('\n').unwrap_or((zh, ""));
        let (target_head, target_body) = target.split_once('\n').unwrap_or((target, ""));
        let series = p.tag.replace_all(head, "");
        if !series.ends_with(SERIES)
            || target_body.is_empty()
            || body.matches('\n').count() != target_body.matches('\n').count()
        {
            continue;
        }
        let target_series = p.tag.replace_all(target_head, "");
        for (source, text) in [
            (body, target_body),
            (series.as_ref(), target_series.as_ref()),
        ] {
            if !pystr::strip(text).is_empty() && markup_matches(source, text) {
                out.entry(source.to_owned())
                    .or_insert_with(|| pystr::strip(text).to_owned());
            }
        }
    }
    out
}

fn markup_matches(source: &str, target: &str) -> bool {
    let p = patterns();
    let mut left: Vec<&str> = p
        .markup
        .find_iter(source)
        .map(|found| found.as_str())
        .collect();
    let mut right: Vec<&str> = p
        .markup
        .find_iter(target)
        .map(|found| found.as_str())
        .collect();
    left.sort_unstable();
    right.sort_unstable();
    left == right
}

/// `entries`: every supplementary (Chinese -> target) pair for language <code>.
pub fn entries(supplement: &Supplement, unique: &Unique_, code: &str) -> IndexMap<String, String> {
    let pick = |pair: &(String, String)| {
        if code == "id" {
            pair.1.clone()
        } else {
            pair.0.clone()
        }
    };
    let mut out: IndexMap<String, String> = supplement
        .texts
        .iter()
        .map(|(zh, pair)| (zh.clone(), pick(pair)))
        .collect();
    for (prefix, pair) in &supplement.leaderboards {
        let text = pick(pair);
        for rank in 1..=RANKS {
            out.insert(
                format!("{prefix}{}", chinese_number(rank)),
                text.replace("{n}", &rank.to_string()),
            );
        }
    }
    let scores: Vec<String> = SCORES_BIG
        .iter()
        .map(|name| format!("{name}{SCORES_SUFFIX}"))
        .collect();
    for zh in TIERED_TITLES
        .iter()
        .copied()
        .chain(scores.iter().map(String::as_str))
    {
        let Some(title) = title(unique, zh) else {
            continue;
        };
        if zh.ends_with(SCORES_SUFFIX) {
            out.entry(zh.to_owned()).or_insert_with(|| title.clone());
        }
        for tier in 1..=TIERS {
            out.insert(
                format!("{zh}({})", chinese_number(tier)),
                format!("{title} ({})", ROMAN[tier as usize]),
            );
        }
    }
    for (zh, target) in derived(unique) {
        out.entry(zh).or_insert(target);
    }
    out
}

/// `check`: the sources whose target does not carry exactly the source's placeholders and tags.
pub fn check(pairs: &IndexMap<String, String>) -> Vec<&str> {
    pairs
        .iter()
        .filter(|(zh, target)| !markup_matches(zh, target))
        .map(|(zh, _)| zh.as_str())
        .collect()
}

/// `apply`: add the supplement to a loaded catalog in place; how many sources were added.
pub fn apply(supplement: &Supplement, data: &mut Value, code: &str) -> Result<u64, String> {
    let object = data.as_object_mut().ok_or("the catalog is not an object")?;
    let unique = object
        .entry("unique")
        .or_insert_with(|| Value::Object(Map::new()))
        .as_object_mut()
        .ok_or("the catalog's unique is not an object")?;
    let pairs = entries(supplement, unique, code);
    let bad = check(&pairs);
    if !bad.is_empty() {
        let shown: Vec<String> = bad
            .iter()
            .take(3)
            .map(|zh| crate::catalog::py_repr(zh))
            .collect();
        return Err(format!(
            "catalog supplement changes the placeholders of [{}]",
            shown.join(", ")
        ));
    }
    let mut added = 0;
    for (zh, target) in pairs {
        if !unique.contains_key(&zh) {
            unique.insert(zh, Value::String(target));
            added += 1;
        }
    }
    Ok(added)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn numbers_as_the_game_writes_them() {
        let got: Vec<String> = [1, 7, 10, 18, 20, 75, 100]
            .into_iter()
            .map(chinese_number)
            .collect();
        assert_eq!(got, ["一", "七", "十", "十八", "二十", "七十五", "一百"]);
    }

    #[test]
    fn repeated_key_is_refused() {
        let dir = std::env::temp_dir().join(format!("hokace-supplement-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("texts.json");
        std::fs::write(
            &path,
            r#"[{"note": "", "texts": {"a": ["x", "y"], "a": ["x", "y"]}}]"#,
        )
        .unwrap();
        assert_eq!(
            load(&path).unwrap_err(),
            "catalog supplement repeats the source 'a'"
        );
        std::fs::remove_dir_all(dir).unwrap();
    }
}
