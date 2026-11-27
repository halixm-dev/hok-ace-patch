//! `tools/terminology.py`: one Chinese game term, one translation everywhere, applied to the catalog
//! in memory as it loads.
//!
//! A rule is keyed on the Chinese source: it rewrites a target only when its source holds the term,
//! and within it only the measured variant words, never inside a `{placeholder}`, a `<tag>` or a
//! phrase another word of the same source owns (`keep`).
//!
//! The patterns are Python's, run by `fancy-regex` for their lookarounds, with `\b` and `\w` rewritten
//! to Python's word class (`PY_WORD`): the English catalog's "④chess player" keeps its words only
//! because Python counts `④` as a word character.

use fancy_regex::{Captures, Regex};
use indexmap::IndexMap;
use serde_json::Value;
use std::sync::OnceLock;

/// What a variant writes in place of its match.
#[derive(Clone, Copy, Debug)]
pub enum Replacement {
    /// The text as given, cased after the `w` group when the pattern names one.
    Text(&'static str),
    /// `_indonesian_series`: "Prepare Series" -> "Seri Prepare".
    IndonesianSeries,
}

/// One Chinese term and the English it always reads as (`terminology.Term`).
#[derive(Debug)]
pub struct Term {
    pub source: &'static str,
    pub canonical: &'static str,
    pub keep: &'static [&'static str],
    pub proper: bool,
    variants: Vec<(Regex, Replacement)>,
    protected: Regex,
}

const PROTECTED: &str = r"\{[^{}]*\}|<[^<>]*>";

type Variant = (&'static str, Replacement);

impl Term {
    fn new(
        source: &'static str,
        canonical: &'static str,
        variants: &[Variant],
        keep: &'static [&'static str],
        proper: bool,
    ) -> Self {
        let kept: String = keep
            .iter()
            .map(|phrase| format!("|{}", fancy_regex::escape(phrase)))
            .collect();
        Self {
            source,
            canonical,
            keep,
            proper,
            variants: variants
                .iter()
                .map(|(pattern, replacement)| (compile(pattern), *replacement))
                .collect(),
            protected: compile(&format!("({PROTECTED}{kept})")),
        }
    }

    /// `Term.rewrite`: <target> with this term's variants replaced, or <target> when <source> lacks it.
    pub fn rewrite(&self, source: &str, target: &str) -> String {
        if !source.contains(self.source) || target.is_empty() {
            return target.to_owned();
        }
        let mut out = String::with_capacity(target.len());
        let mut last = 0;
        for found in self.protected.find_iter(target) {
            let found = found.expect("the protected pattern needs no backtracking limit");
            out.push_str(&self.rewrite_run(&target[last..found.start()]));
            out.push_str(found.as_str());
            last = found.end();
        }
        out.push_str(&self.rewrite_run(&target[last..]));
        out
    }

    /// The variants, in order, over one unprotected run (Python's `re.split` part).
    fn rewrite_run(&self, run: &str) -> String {
        let mut text = run.to_owned();
        for (pattern, replacement) in &self.variants {
            let mut out = String::with_capacity(text.len());
            let mut last = 0;
            for captures in pattern.captures_iter(text.as_str()) {
                let captures =
                    captures.expect("a variant pattern stays within the backtrack limit");
                let whole = captures.get(0).expect("group 0 is the match");
                out.push_str(&text[last..whole.start()]);
                out.push_str(&self.cased(&text, &captures, *replacement));
                last = whole.end();
            }
            if last == 0 && out.is_empty() {
                continue;
            }
            out.push_str(&text[last..]);
            text = out;
        }
        text
    }

    fn cased(&self, text: &str, captures: &Captures<'_, str>, replacement: Replacement) -> String {
        let replacement = match replacement {
            Replacement::IndonesianSeries => {
                let name = captures.name("name").map_or("", |name| name.as_str());
                return format!("Seri {}", crate::pystr::capitalize_first(name));
            }
            Replacement::Text(text) => text,
        };
        let Some(word) = captures.name("w") else {
            return replacement.to_owned();
        };
        let start = captures.get(0).expect("group 0 is the match").start();
        let upper = word.as_str().chars().next().is_some_and(char::is_uppercase);
        if self.proper || upper || after_icon(text, start) {
            return replacement.to_owned();
        }
        crate::pystr::lower_first(replacement)
    }
}

/// `_after_icon`: the client draws each keyword's icon as a box-drawing glyph just before its name.
fn after_icon(text: &str, start: usize) -> bool {
    text[..start]
        .chars()
        .next_back()
        .is_some_and(|c| ('─'..='╿').contains(&c))
}

/// Python's `\w` on `str`: `isalnum()` or `_`, which on Unicode 15.0 is exactly letters and numbers
/// (measured over every code point). Rust's own `\w` holds combining marks and the joiners instead of
/// `No`/`Nl`, so "④chess player" would gain a boundary Python does not see.
const PY_WORD: &str = r"\p{L}\p{N}_";

/// <pattern> with `\b` and `\w` spelled as Python reads them.
fn python_classes(pattern: &str) -> String {
    let boundary = format!("(?:(?<=[{PY_WORD}])(?![{PY_WORD}])|(?<![{PY_WORD}])(?=[{PY_WORD}]))");
    let mut out = String::with_capacity(pattern.len() * 4);
    let mut chars = pattern.chars();
    while let Some(c) = chars.next() {
        if c != '\\' {
            out.push(c);
            continue;
        }
        match chars.next() {
            Some('b') => out.push_str(&boundary),
            // Every `\w` in the glossary sits inside a class, so it joins that class.
            Some('w') => out.push_str(PY_WORD),
            Some(other) => {
                out.push('\\');
                out.push(other);
            }
            None => out.push('\\'),
        }
    }
    out
}

fn compile(pattern: &str) -> Regex {
    Regex::new(&python_classes(pattern))
        .unwrap_or_else(|error| panic!("terminology pattern {pattern:?}: {error}"))
}

const fn text(replacement: &'static str) -> Replacement {
    Replacement::Text(replacement)
}

const CHESSPLAYER: &[Variant] = &[
    (r"(?i:\bchess[ -]*players\b)", text("Chessplayers")),
    (r"(?i:\bchess[ -]*player\b)", text("Chessplayer")),
];
const CHESSPLAYER_SOURCES: &[&str] = &[
    "棋手",
    "骑手",
    "棋友",
    "hess player",
    "hess Player",
    "参赛选手",
    "角色语音",
];

fn english_terms() -> Vec<Term> {
    let mut terms = vec![
        Term::new(
            "合成",
            "Combine",
            &[(r"\bupgraded\b", text("Combine"))],
            &[],
            true,
        ),
        Term::new(
            "夺取",
            "Steal",
            &[
                (r"(?i:\bto capture\b)", text("Steal")),
                (r"(?i:\bcapturing the entry\b)", text("Steal Trait")),
                (r"(?i:\bsteal the blessing\b)", text("Steal Blessing")),
                (
                    r"(?i:\bto steal reinforcements\b)",
                    text("Steal Reinforcements"),
                ),
                (r"\bCaptureCard\b", text("Steal Card")),
                (
                    r"(?P<w>\b(?i:plunder|captur|snatch|siphon|drain)ing\b)",
                    text("Stealing"),
                ),
                (
                    r"(?P<w>\b(?i:plundered|seized|captured|snatched|siphoned|drained)\b)",
                    text("Stolen"),
                ),
                (
                    r"(?P<w>\b(?i:plunders|captures|snatches|siphons|drains)\b)",
                    text("Steals"),
                ),
                (
                    r"(?P<w>\b(?i:plunder|capture|seizure|snatch|siphon|drain)\b)",
                    text("Steal"),
                ),
            ],
            &["Soul Snatch", "soul snatch"],
            false,
        ),
        Term::new(
            "整备",
            "Prepare",
            &[
                (r"(?P<w>\b(?i:readiness|maintenance)\b)", text("Prepare")),
                (r"(?P<w>\bReady\b)", text("Prepare")),
                (r"\bPrepare series\b", text("Prepare Series")),
            ],
            &[],
            true,
        ),
        Term::new(
            "登场",
            "Deploy",
            &[(r"\bShowtime\b", text("Deploy"))],
            &[],
            true,
        ),
        Term::new(
            "祈愿",
            "Wish",
            &[
                (r"(?P<w>\b(?i:prayers)\b)", text("Wishes")),
                (r"(?P<w>\b(?i:prayer)\b)", text("Wish")),
                (r"(?P<w>\b(?i:praying)\b)", text("Wishing")),
                (r"(?P<w>\b(?i:pray)\b)", text("Wish")),
            ],
            &[],
            false,
        ),
    ];
    terms.extend(
        CHESSPLAYER_SOURCES
            .iter()
            .map(|source| Term::new(source, "Chessplayer", CHESSPLAYER, &[], true)),
    );
    terms.extend([
        Term::new(
            "最高决策者",
            "Ultimate Decree Maker",
            &[(r"\bSupreme Decision Maker\b", text("Ultimate Decree Maker"))],
            &[],
            true,
        ),
        Term::new(
            "决策颁布者",
            "Decree Maker",
            &[
                (
                    r"(?i:\bfor decision-makers\b)",
                    text("for the Decree Maker"),
                ),
                (
                    r"(?i:\bfor the policy issuer\b)",
                    text("for the Decree Maker"),
                ),
                (
                    r"(?i:\bdecision[- ](?:maker|issuer)\b)",
                    text("Decree Maker"),
                ),
                (r"(?i:\bedict (?:enactor|issuer)\b)", text("Decree Maker")),
            ],
            &[],
            true,
        ),
        Term::new(
            "战略决策",
            "Strategic Decree",
            &[
                (r"\bStrategic Decisions\b", text("Strategic Decrees")),
                (r"\bStrategic Decision\b", text("Strategic Decree")),
            ],
            &[],
            true,
        ),
        Term::new(
            "特权决策",
            "Privileged Decree",
            &[
                (r"\bPrivileged Decisions\b", text("Privileged Decrees")),
                (r"\bPrivileged Decision\b", text("Privileged Decree")),
            ],
            &[],
            true,
        ),
    ]);
    terms
}

fn card_names() -> Vec<Term> {
    vec![
        Term::new(
            "朋友多多",
            "Friends Galore",
            &[(
                r"(?i:\b(?:many|plenty of|lots of) friends\b)",
                text("Friends Galore"),
            )],
            &[],
            true,
        ),
        Term::new(
            "为我所用",
            "Make It My Way",
            &[(
                r"(?i:\buse for (?:my own|myself)\b)",
                text("Make It My Way"),
            )],
            &[],
            true,
        ),
        Term::new(
            "小菟送福",
            "Bunny's Blessing",
            &[
                (
                    r"(?i:\b(?:little )?rabbit's blessing\b)",
                    text("Bunny's Blessing"),
                ),
                (r"(?i:\blittle rabbit gift\b)", text("Bunny's Blessing")),
                (r"(?i:\bxiaotu[’']s blessing\b)", text("Bunny's Blessing")),
            ],
            &[],
            true,
        ),
        Term::new(
            "如梦似幻",
            "Dream Illusion",
            &[
                (r"(?i:\bdreamlike(?: fantasy)?\b)", text("Dream Illusion")),
                (r"(?i:\blike a dream\b)", text("Dream Illusion")),
            ],
            &[],
            true,
        ),
        Term::new(
            "构筑升级",
            "Construct Upgrade",
            &[
                (
                    r"(?i:\b(?:build|construction|construct) upgrades\b)",
                    text("Construct Upgrades"),
                ),
                (
                    r"(?i:\b(?:build|construction) upgrade\b)",
                    text("Construct Upgrade"),
                ),
            ],
            &[],
            true,
        ),
        Term::new(
            "驭势",
            "Harness Momentum",
            &[
                (r"\bMomentum Controls\b", text("Harness Momentum cards")),
                (r"\bMomentum Control\b", text("Harness Momentum")),
                (
                    r"(?<!Harness )\bMomentum\b(?= Secret Technique)",
                    text("Harness Momentum"),
                ),
            ],
            &[],
            true,
        ),
        Term::new(
            "封神一瞬",
            "Moment of Sanctification",
            &[
                (
                    r"(?i:\bmoment of apotheosis\b)",
                    text("Moment of Sanctification"),
                ),
                (
                    r"\bGod(?:-Making|-Sealing|'s) Moment\b",
                    text("Moment of Sanctification"),
                ),
            ],
            &[],
            true,
        ),
        Term::new(
            "至高决策",
            "Ultimate Decree",
            &[
                (r"\bSupreme Decisions\b", text("Ultimate Decrees")),
                (r"\bSupreme Decision\b", text("Ultimate Decree")),
                (r"(?i:\bfinal decisions\b)", text("Ultimate Decrees")),
            ],
            &[],
            true,
        ),
        Term::new(
            "灵异探测大改装",
            "Paranormal Detection Mod",
            &[(
                r"(?i:\bsupernatural detector overhaul\b)",
                text("Paranormal Detection Mod"),
            )],
            &[],
            true,
        ),
        Term::new(
            "神奇小鹿",
            "Magical Deerie",
            &[(r"(?i:\bmagic(?:al)? deer\b)", text("Magical Deerie"))],
            &[],
            true,
        ),
        Term::new(
            "小菟助力",
            "Bunny's Aid",
            &[
                (
                    r"(?i:\blittle (?:rabbit|dodder) assist\b)",
                    text("Bunny's Aid"),
                ),
                (r"\bLittle Tu's Assist\b", text("Bunny's Aid")),
                (
                    r"\bXiaotu[’']s (?:Aid|assistance|boost)\b",
                    text("Bunny's Aid"),
                ),
                (r"\b(?:The |the )?Rabbit Aid\b", text("Bunny's Aid")),
            ],
            &[],
            true,
        ),
    ]
}

fn indonesian_only() -> Vec<Term> {
    let mut terms = vec![
        Term::new(
            "夺取",
            "Steal",
            &[
                (r"\bKejang\b", text("Steal")),
                (r"\bPIunder\b", text("Steal")),
                (r"\bsteal(?=╊)", text("Steal")),
            ],
            &[],
            false,
        ),
        Term::new(
            "整备",
            "Prepare",
            &[(r"(?<=╬)Siap\b", text("Prepare"))],
            &[],
            false,
        ),
        Term::new(
            "至高决策",
            "Ultimate Decree",
            &[
                (r"\bSupreme Decisions?\b", text("Ultimate Decree")),
                (r"(?i:\bkeputusan final\b)", text("Ultimate Decree")),
            ],
            &[],
            true,
        ),
        Term::new(
            "决策颁布者",
            "Decree Maker",
            &[
                (
                    r"(?i:\b(?:penerima|pengambil) keputusan\b)",
                    text("Decree Maker"),
                ),
                (r"(?i:\bpenerbit kebijakan\b)", text("Decree Maker")),
            ],
            &[],
            true,
        ),
    ];
    terms.extend(CHESSPLAYER_SOURCES.iter().map(|source| {
        Term::new(
            source,
            "Chessplayer",
            &[
                (r"(?i:\bpemain catur\b)", text("Chessplayer")),
                (r"\bChessplayers\b", text("Chessplayer")),
            ],
            &[],
            true,
        )
    }));
    terms.push(Term::new(
        "系列",
        "Seri",
        &[
            (
                r"(?P<name>(?:[A-Z][\w'-]* )*[A-Z][\w'-]*|[a-z][\w'-]*) [Ss]eries\b",
                Replacement::IndonesianSeries,
            ),
            (
                r"(?P<name>(?:[A-Z][\w'-]* )*[A-Z][\w'-]*) seri\b",
                Replacement::IndonesianSeries,
            ),
        ],
        &[],
        false,
    ));
    terms
}

/// `ENGLISH_TERMS + CARD_NAMES`, the English language's glossary.
pub fn english_terms_and_card_names() -> &'static [Term] {
    static TERMS: OnceLock<Vec<Term>> = OnceLock::new();
    TERMS.get_or_init(|| {
        let mut terms = english_terms();
        terms.extend(card_names());
        terms
    })
}

/// `INDONESIAN_TERMS`: the English glossary plus the Indonesian catalog's own misreadings.
pub fn indonesian_terms() -> &'static [Term] {
    static TERMS: OnceLock<Vec<Term>> = OnceLock::new();
    TERMS.get_or_init(|| {
        let mut terms = english_terms();
        terms.extend(indonesian_only());
        terms
    })
}

/// `terminology.apply`'s refusal of a catalog it cannot read: Python's `TypeError` there.
#[derive(Debug, PartialEq, Eq)]
pub struct NotText(pub &'static str);

fn rewrite_all(
    terms: &[Term],
    changed: &mut IndexMap<&'static str, u64>,
    source: &str,
    target: &str,
) -> String {
    if !terms.iter().any(|term| source.contains(term.source)) {
        return target.to_owned();
    }
    let mut target = target.to_owned();
    for term in terms {
        let new = term.rewrite(source, &target);
        if new != target {
            *changed.entry(term.canonical).or_insert(0) += 1;
        }
        target = new;
    }
    target
}

/// `terminology.apply`: <terms> over a loaded catalog in place; the targets changed, per canonical term
/// in the order Python's `Counter` first counts them.
pub fn apply(data: &mut Value, terms: &[Term]) -> Result<IndexMap<&'static str, u64>, NotText> {
    let mut changed = IndexMap::new();
    if terms.is_empty() {
        return Ok(changed);
    }
    if let Some(unique) = data.get_mut("unique") {
        let unique = unique.as_object_mut().ok_or(NotText("unique"))?;
        for (source, target) in unique.iter_mut() {
            let text = target.as_str().ok_or(NotText("unique"))?;
            let new = rewrite_all(terms, &mut changed, source, text);
            if new != text {
                *target = Value::String(new);
            }
        }
    }
    if let Some(rows) = data.get_mut("english_updates") {
        let rows = rows.as_array_mut().ok_or(NotText("english_updates"))?;
        for row in rows {
            let row = row.as_array_mut().ok_or(NotText("english_updates"))?;
            if row.len() >= 5 {
                let source = row[4]
                    .as_str()
                    .ok_or(NotText("english_updates"))?
                    .to_owned();
                let target = row[3].as_str().ok_or(NotText("english_updates"))?;
                let new = rewrite_all(terms, &mut changed, &source, target);
                if new != target {
                    row[3] = Value::String(new);
                }
            }
        }
    }
    Ok(changed)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn steal_variants_keep_case_and_protected_runs() {
        let terms = english_terms_and_card_names();
        let mut data = json!({"unique": {
            "夺取摄灵": "Plunders <b>plunder</b> {drain} and drains, Soul Snatch",
            "其他": "drain",
            "╬整备": "Readiness ready Ready",
        }});
        let changed = apply(&mut data, terms).unwrap();
        assert_eq!(
            data["unique"]["夺取摄灵"],
            "Steals <b>steal</b> {drain} and steals, Soul Snatch"
        );
        assert_eq!(data["unique"]["其他"], "drain");
        assert_eq!(data["unique"]["╬整备"], "Prepare ready Prepare");
        assert_eq!(changed.get("Steal"), Some(&1));
    }

    #[test]
    fn indonesian_series_reorders() {
        let terms = indonesian_terms();
        let mut data = json!({"unique": {"整备系列": "Prepare Series and blazing series"}});
        apply(&mut data, terms).unwrap();
        assert_eq!(data["unique"]["整备系列"], "Seri Prepare and Seri Blazing");
    }
}
