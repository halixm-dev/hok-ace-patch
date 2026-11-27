//! Validation of translated localization records against the original text.

use crate::protobuf::{self, Error, LocalizationField};
use std::collections::{HashMap, HashSet};

type Sources = HashMap<String, String>;
type Context<T> = HashMap<String, HashMap<String, HashMap<String, T>>>;

#[derive(Debug, Default)]
pub struct Catalog {
    unique: Sources,
    context: Context<String>,
    english_updates: Context<(String, String)>,
    targets: HashSet<String>,
}

impl Catalog {
    /// Builds the text view of an already validated catalog.
    pub fn from_entries(
        unique: Sources,
        contextual: impl IntoIterator<Item = (String, String, String, String)>,
        english_updates: impl IntoIterator<Item = (String, String, String, String, String)>,
    ) -> Self {
        let targets = unique.values().cloned().collect();
        let mut catalog = Self {
            unique,
            targets,
            ..Self::default()
        };
        for (asset, key, source, target) in contextual {
            catalog.targets.insert(target.clone());
            catalog
                .context
                .entry(asset)
                .or_default()
                .entry(key)
                .or_default()
                .insert(source, target);
        }
        for (asset, key, previous, target, base_source) in english_updates {
            catalog.targets.insert(target.clone());
            catalog
                .english_updates
                .entry(asset)
                .or_default()
                .entry(key)
                .or_default()
                .insert(previous, (target, base_source));
        }
        catalog
    }
}

#[derive(Debug, PartialEq, Eq)]
pub enum TableError {
    Wire(Error),
    UnexpectedTopLevel,
    UnexpectedRecord,
    Empty,
}

impl From<Error> for TableError {
    fn from(error: Error) -> Self {
        Self::Wire(error)
    }
}

impl TableError {
    pub fn python_class(&self) -> &'static str {
        match self {
            Self::Wire(err) => err.python_class(),
            _ => "ProtobufError",
        }
    }
}

impl std::fmt::Display for TableError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Wire(err) => err.fmt(f),
            Self::UnexpectedTopLevel => f.write_str("Unexpected top-level field"),
            Self::UnexpectedRecord => f.write_str("Missing, duplicate, or unknown record fields"),
            Self::Empty => f.write_str("Empty table"),
        }
    }
}

impl std::error::Error for TableError {}

#[derive(Debug)]
pub struct Translation {
    pub output: Option<Vec<u8>>,
    // Counter insertion order reaches the scan report.
    pub counts: Vec<(&'static str, usize)>,
}

fn increment(counts: &mut Vec<(&'static str, usize)>, key: &'static str) {
    if let Some((_, count)) = counts.iter_mut().find(|(existing, _)| *existing == key) {
        *count += 1;
    } else {
        counts.push((key, 1));
    }
}

fn record_parts(
    nested: &[u8],
) -> Result<(LocalizationField<'_>, LocalizationField<'_>), TableError> {
    let mut parts = protobuf::localization_fields(nested);
    let first = parts.next().transpose()?;
    let second = parts.next().transpose()?;
    let mut extra = false;
    for part in parts {
        part?;
        extra = true;
    }
    match (first, second) {
        (Some(a), Some(b)) if !extra && a.tag != b.tag => Ok((a, b)),
        _ => Err(TableError::UnexpectedRecord),
    }
}

pub fn translate_table(
    raw: &[u8],
    asset: u64,
    catalog: &Catalog,
    build_output: bool,
) -> Result<Translation, TableError> {
    let asset = format!("{asset:016X}");
    let contextual = catalog.context.get(&asset);
    let english_updates = catalog.english_updates.get(&asset);
    let mut output = build_output.then(|| Vec::with_capacity(raw.len()));
    let mut record = Vec::new();
    let mut counts = Vec::new();
    for outer in protobuf::localization_fields(raw) {
        let outer = outer?;
        if outer.tag != 10 {
            return Err(TableError::UnexpectedTopLevel);
        }
        let (first, second) = record_parts(outer.payload)?;
        let (key_field, source_field) = if first.tag == 10 {
            (&first, &second)
        } else {
            (&second, &first)
        };
        let key = protobuf::decode_str(key_field.payload)?;
        let source = protobuf::decode_str(source_field.payload)?;
        increment(&mut counts, "records");
        let candidate = if let Some((target, base)) = english_updates
            .and_then(|keys| keys.get(key))
            .and_then(|sources| sources.get(source))
        {
            Some((target.as_str(), base.as_str()))
        } else if catalog.targets.contains(source) {
            increment(&mut counts, "already_english");
            None
        } else if contains_cjk(source) {
            let target = contextual
                .and_then(|keys| keys.get(key))
                .and_then(|sources| sources.get(source))
                .or_else(|| catalog.unique.get(source));
            if target.is_none() {
                increment(&mut counts, "unknown");
            }
            target.map(|target| (target.as_str(), source))
        } else {
            None
        };
        let target = candidate.and_then(|(target, base)| {
            if validate_translation(base, Some(target)).0 {
                Some(target)
            } else {
                increment(&mut counts, "invalid_translation");
                None
            }
        });
        if let Some(target) = target.filter(|target| *target != source) {
            if let Some(output) = &mut output {
                record.clear();
                for field in [first, second] {
                    if field.tag == 10 {
                        record.extend_from_slice(field.raw);
                    } else {
                        protobuf::put_field(&mut record, 18, target.as_bytes());
                    }
                }
                protobuf::put_field(output, 10, &record);
            }
            increment(&mut counts, "translated");
        } else if let Some(output) = &mut output {
            output.extend_from_slice(outer.raw);
        }
    }
    if counts.is_empty() {
        return Err(TableError::Empty);
    }
    Ok(Translation { output, counts })
}

pub fn contains_cjk(text: &str) -> bool {
    text.chars()
        .any(|c| matches!(c, '\u{3400}'..='\u{4dbf}' | '\u{4e00}'..='\u{9fff}' | '\u{f900}'..='\u{faff}'))
}

fn tags(text: &str) -> impl Iterator<Item = (usize, &str)> {
    matches_at(text, |suffix| {
        let body = suffix.strip_prefix('<')?;
        if body.starts_with("/>") {
            return Some(3);
        }
        if !body
            .strip_prefix('/')
            .unwrap_or(body)
            .as_bytes()
            .first()?
            .is_ascii_alphabetic()
        {
            return None;
        }
        Some(body.find('>')? + 2)
    })
}

fn placeholders(text: &str) -> impl Iterator<Item = (usize, &str)> {
    matches_at(text, |suffix| {
        if let Some(body) = suffix.strip_prefix('{') {
            let end = body.find(['{', '}'])?;
            return body[end..].starts_with('}').then_some(end + 2);
        }
        let body = suffix.strip_prefix('%')?;
        let digits = decimal_prefix(body);
        if digits > 0
            && let Some(positional) = body[digits..].strip_prefix('$')
            && let Some(len) = printf_body(positional)
        {
            return Some(digits + 2 + len);
        }
        printf_body(body).map(|len| len + 1)
    })
}

fn matches_at(
    text: &str,
    mut matcher: impl FnMut(&str) -> Option<usize>,
) -> impl Iterator<Item = (usize, &str)> {
    let mut end = 0;
    text.char_indices().filter_map(move |(index, _)| {
        if index < end {
            return None;
        }
        let len = matcher(&text[index..])?;
        end = index + len;
        Some((index, &text[index..end]))
    })
}

fn printf_body(text: &str) -> Option<usize> {
    let flags = text.trim_start_matches(['-', '+', '0', ' ', '#']);
    let width = flags
        .strip_prefix('*')
        .unwrap_or(&flags[decimal_prefix(flags)..]);
    let mut conversion = width;
    if let Some(precision) = width.strip_prefix('.') {
        let digits = decimal_prefix(precision);
        if digits == 0 {
            return None;
        }
        conversion = &precision[digits..];
    }
    let bytes = conversion.as_bytes();
    if !b"diuoxXfFeEgGaAcspn%".contains(bytes.first()?)
        || bytes.get(1).is_some_and(u8::is_ascii_alphabetic)
    {
        return None;
    }
    Some(text.len() - conversion.len() + 1)
}

fn decimal_prefix(text: &str) -> usize {
    text.find(|c: char| !is_decimal(c)).unwrap_or(text.len())
}

fn is_decimal(c: char) -> bool {
    if c.is_ascii() {
        return c.is_ascii_digit();
    }
    // Unicode 15.0 Nd ranges used by CPython 3.12's regex \d. The mathematical block
    // contains five consecutive sets of digits. All the other ranges contain ten.
    const STARTS: &[u32] = &[
        0x660, 0x6f0, 0x7c0, 0x966, 0x9e6, 0xa66, 0xae6, 0xb66, 0xbe6, 0xc66, 0xce6, 0xd66, 0xde6,
        0xe50, 0xed0, 0xf20, 0x1040, 0x1090, 0x17e0, 0x1810, 0x1946, 0x19d0, 0x1a80, 0x1a90,
        0x1b50, 0x1bb0, 0x1c40, 0x1c50, 0xa620, 0xa8d0, 0xa900, 0xa9d0, 0xa9f0, 0xaa50, 0xabf0,
        0xff10, 0x104a0, 0x10d30, 0x11066, 0x110f0, 0x11136, 0x111d0, 0x112f0, 0x11450, 0x114d0,
        0x11650, 0x116c0, 0x11730, 0x118e0, 0x11950, 0x11c50, 0x11d50, 0x11da0, 0x11f50, 0x16a60,
        0x16ac0, 0x16b50, 0x1e140, 0x1e2f0, 0x1e4f0, 0x1e950, 0x1fbf0,
    ];
    let c = u32::from(c);
    let index = STARTS.partition_point(|start| *start <= c);
    (0x1d7ce..=0x1d7ff).contains(&c) || (index > 0 && c - STARTS[index - 1] < 10)
}

fn remove_tags(text: &str) -> String {
    let mut visible = String::with_capacity(text.len());
    let mut start = 0;
    for (index, tag) in tags(text) {
        visible.push_str(&text[start..index]);
        start = index + tag.len();
    }
    visible.push_str(&text[start..]);
    visible
}

fn visible_cjk(text: &str) -> bool {
    let visible = remove_tags(text);
    let mut start = 0;
    for (index, token) in placeholders(&visible) {
        if contains_cjk(&visible[start..index]) {
            return true;
        }
        start = index + token.len();
    }
    contains_cjk(&visible[start..])
}

fn counts<T: Eq + std::hash::Hash>(items: impl Iterator<Item = T>) -> HashMap<T, usize> {
    let mut counts = HashMap::new();
    for item in items {
        *counts.entry(item).or_default() += 1;
    }
    counts
}

fn controls(text: &str) -> impl Iterator<Item = char> {
    text.chars()
        .filter(|c| matches!(c, '\u{2540}'..='\u{257f}'))
}

/// Returns the same validation reason as the reference runtime.
pub fn validate_translation(source: &str, translated: Option<&str>) -> (bool, &'static str) {
    let Some(translated) = translated else {
        return (false, "empty");
    };
    if translated
        .chars()
        .all(|c| c.is_whitespace() || matches!(c, '\u{1c}'..='\u{1f}'))
    {
        return (false, "empty");
    }
    if visible_cjk(translated) {
        return (false, "still_chinese");
    }
    if !(tags(source)
        .map(|(_, tag)| tag)
        .eq(tags(translated).map(|(_, tag)| tag))
        || (source.starts_with("<{") && source.ends_with('>')))
    {
        return (false, "tags_changed");
    }
    if counts(placeholders(source).map(|(_, token)| token))
        != counts(placeholders(translated).map(|(_, token)| token))
    {
        return (false, "placeholders_changed");
    }
    if counts(controls(source)) != counts(controls(translated)) {
        return (false, "control_tokens_changed");
    }
    if source.contains(';') && source.matches(';').count() != translated.matches(';').count() {
        return (false, "semicolons_changed");
    }
    let source_len = source.chars().count();
    if source_len >= 4 && translated.chars().count() > source_len.saturating_mul(8).max(48) {
        return (false, "extreme_expansion");
    }
    (true, "ok")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn placeholder_boundaries_allow_adjacent_tokens_and_unicode_digits() {
        let input = "%d%% %０.２f {%汉} %dmg %2$*s";
        assert_eq!(
            placeholders(input)
                .map(|(_, text)| text)
                .collect::<Vec<_>>(),
            ["%d", "%%", "%０.２f", "{%汉}", "%2$*s"]
        );
    }
}
