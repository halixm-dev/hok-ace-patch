//! `tools/resource_tokens.py`: expand `{Energy}`/`{LordExp}`/`{LordHp}` in the staged replacements, which
//! the client would otherwise fill with Chinese labels. The catalog keeps the tokens, because
//! `translate_table` compares placeholders between source and target.

use crate::pyos;
use crate::pystr;
use crate::scan::PyError;
use std::path::{Path, PathBuf};

const MAX_DEPTH: u32 = 16;

/// `NotMessage`: the bytes are not a well-formed protobuf message. Its `str()` is empty.
#[derive(Debug, PartialEq, Eq)]
pub struct NotMessage;

/// The terms of one language, `(token, term)` in its dict order.
pub type Terms<'a> = &'a [(&'a str, &'a str)];

fn space_before(c: char) -> bool {
    c.is_ascii_alphanumeric() || c == '}'
}

/// `_tail`: the space <text> needs after a term ending at byte <end>.
fn tail(text: &str, end: usize) -> &'static str {
    let mut rest = text[end..].chars();
    let Some(following) = rest.next() else {
        return "";
    };
    if following.is_ascii_alphabetic() {
        return " ";
    }
    if matches!(following, '+' | '-')
        && rest
            .next()
            .is_some_and(|next| pystr::is_digit(next) || next == '{')
    {
        return " ";
    }
    ""
}

/// `expand_resource_tokens`: <text> with the tokens replaced by <terms>, spaced where a term would
/// run into a letter, digit or placeholder before it, or a word or signed value after it.
pub fn expand_resource_tokens(text: &str, terms: Terms<'_>) -> String {
    if text.is_empty() || !text.contains('{') {
        return text.to_owned();
    }
    let mut out = String::with_capacity(text.len() + 16);
    let mut index = 0;
    while index < text.len() {
        let mut found: Option<(usize, &str, usize)> = None;
        for (token, name) in terms {
            if let Some(at) = text[index..].find(token).map(|at| at + index)
                && found.is_none_or(|(best, _, _)| at < best)
            {
                found = Some((at, name, token.len()));
            }
        }
        let Some((at, term, width)) = found else {
            out.push_str(&text[index..]);
            break;
        };
        let end = at + width;
        let lead = if text[..at].chars().next_back().is_some_and(space_before) {
            " "
        } else {
            ""
        };
        out.push_str(&text[index..at]);
        out.push_str(lead);
        out.push_str(term);
        out.push_str(tail(text, end));
        index = end;
    }
    out
}

fn varint(data: &[u8], mut pos: usize) -> Result<(u128, usize), NotMessage> {
    let (mut result, mut shift) = (0u128, 0u32);
    loop {
        if pos >= data.len() || shift > 63 {
            return Err(NotMessage);
        }
        let byte = data[pos];
        pos += 1;
        result |= u128::from(byte & 0x7f) << shift;
        if byte & 0x80 == 0 {
            return Ok((result, pos));
        }
        shift += 7;
    }
}

fn encode_varint(mut value: usize, out: &mut Vec<u8>) {
    loop {
        let byte = (value & 0x7f) as u8;
        value >>= 7;
        if value == 0 {
            out.push(byte);
            return;
        }
        out.push(byte | 0x80);
    }
}

/// `_as_text`: strict UTF-8 holding no control character but tab, newline and carriage return.
fn as_text(value: &[u8]) -> Option<&str> {
    let text = std::str::from_utf8(value).ok()?;
    let control = |c: char| matches!(c, '\x00'..='\x08' | '\x0b' | '\x0c' | '\x0e'..='\x1f');
    (!text.contains(control)).then_some(text)
}

/// `_TOKEN_RE.search`: any `{Name}` brace token.
fn has_token(text: &str) -> bool {
    let bytes = text.as_bytes();
    bytes.iter().enumerate().any(|(open, &byte)| {
        if byte != b'{' || !bytes.get(open + 1).is_some_and(u8::is_ascii_alphabetic) {
            return false;
        }
        let rest = &bytes[open + 2..];
        let run = rest
            .iter()
            .take_while(|c| c.is_ascii_alphanumeric() || **c == b'_')
            .count();
        rest.get(run) == Some(&b'}')
    })
}

fn walk(data: &[u8], depth: u32, terms: Terms<'_>) -> Result<(Vec<u8>, u64), NotMessage> {
    let mut out = Vec::with_capacity(data.len());
    let (mut pos, mut changed) = (0usize, 0u64);
    let past = |end: u128| end > data.len() as u128;
    while pos < data.len() {
        let (key, after_key) = varint(data, pos)?;
        let (field, wire) = (key >> 3, key & 7);
        if field == 0 {
            return Err(NotMessage);
        }
        let end = match wire {
            0 => varint(data, after_key)?.1,
            1 | 5 => {
                let end = after_key as u128 + if wire == 1 { 8 } else { 4 };
                if past(end) {
                    return Err(NotMessage);
                }
                end as usize
            }
            2 => {
                let (length, start) = varint(data, after_key)?;
                let end = start as u128 + length;
                if past(end) {
                    return Err(NotMessage);
                }
                let end = end as usize;
                let raw = &data[start..end];
                let mut value: Vec<u8> = raw.to_vec();
                match as_text(raw) {
                    Some(text) if has_token(text) => {
                        let replacement = expand_resource_tokens(text, terms);
                        if replacement != text {
                            value = replacement.into_bytes();
                            changed += 1;
                        }
                    }
                    Some(_) => {}
                    None if depth < MAX_DEPTH && !raw.is_empty() => {
                        if let Ok((nested, count)) = walk(raw, depth + 1, terms) {
                            value = nested;
                            changed += count;
                        }
                    }
                    None => {}
                }
                // The expansion changes the encoded length, so the prefix is re-encoded too.
                out.extend_from_slice(&data[pos..after_key]);
                encode_varint(value.len(), &mut out);
                out.extend_from_slice(&value);
                pos = end;
                continue;
            }
            _ => return Err(NotMessage),
        };
        out.extend_from_slice(&data[pos..end]);
        pos = end;
    }
    Ok((out, changed))
}

/// `expand_tokens_in_message`: (<data> with the tokens expanded, string fields changed). Bytes that
/// hold none of the tokens come back as they are, unwalked.
pub fn expand_tokens_in_message(
    data: &[u8],
    terms: Terms<'_>,
) -> Result<(Vec<u8>, u64), NotMessage> {
    let holds = terms.iter().any(|(token, _)| {
        data.windows(token.len().max(1))
            .any(|window| window == token.as_bytes())
    });
    if !holds {
        return Ok((data.to_vec(), 0));
    }
    walk(data, 0, terms)
}

/// `expand_tokens`: <data> expanded, or unchanged when it is not a message we can walk.
pub fn expand_tokens(data: &[u8], log: Option<&mut dyn FnMut(&str)>, terms: Terms<'_>) -> Vec<u8> {
    match expand_tokens_in_message(data, terms) {
        Ok((expanded, _)) => expanded,
        Err(NotMessage) => {
            if let Some(log) = log {
                log("  token expand skipped: ");
            }
            data.to_vec()
        }
    }
}

/// `expand_staged`: bake <terms> into every `*.assets` of each replacements folder, in Python's sorted
/// order; how many strings changed.
pub fn expand_staged(
    replacements: &[PathBuf],
    log: &mut dyn FnMut(&str),
    terms: Terms<'_>,
) -> Result<u64, PyError> {
    let mut changed = 0;
    for folder in replacements {
        let mut paths = glob_assets(folder);
        pyos::sort_paths(&mut paths, false);
        for path in paths {
            changed += expand_file(&path, log, terms)?;
        }
    }
    if changed != 0 {
        log(&format!(
            "expanded resource tokens in {changed} replacement strings"
        ));
    }
    Ok(changed)
}

/// `folder.glob("*.assets")`: its entries named so, case-insensitively on Windows.
fn glob_assets(folder: &Path) -> Vec<PathBuf> {
    let Ok(reader) = std::fs::read_dir(folder) else {
        return Vec::new();
    };
    reader
        .flatten()
        .filter(|entry| {
            let name = entry.file_name().to_string_lossy().into_owned();
            let name = if cfg!(windows) {
                name.to_lowercase()
            } else {
                name
            };
            name.ends_with(".assets")
        })
        .map(|entry| entry.path())
        .collect()
}

fn expand_file(path: &Path, log: &mut dyn FnMut(&str), terms: Terms<'_>) -> Result<u64, PyError> {
    let raw =
        std::fs::read(path).map_err(|error| pyos::os_error(&error, pyos::Call::Crt, &[path]))?;
    match expand_tokens_in_message(&raw, terms) {
        Ok((expanded, count)) => {
            if count != 0 {
                std::fs::write(path, expanded)
                    .map_err(|error| pyos::os_error(&error, pyos::Call::Crt, &[path]))?;
            }
            Ok(count)
        }
        Err(NotMessage) => {
            let name = path
                .file_name()
                .map(|name| name.to_string_lossy())
                .unwrap_or_default();
            log(&format!("token expand skipped {name}: "));
            Ok(0)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::languages::RESOURCE_TOKENS;

    #[test]
    fn terms_are_spaced_at_boundaries() {
        let cases = [
            ("获得{0|1}{Energy}。", "获得{0|1} Energy。"),
            ("{LordExp}+{3|2}", "Chessplayer EXP +{3|2}"),
            ("{Energy}-Saving", "Energy-Saving"),
            ("Gain{LordHp}now", "Gain Chessplayer HP now"),
            ("{Energy}+²", "Energy +²"),
        ];
        for (text, want) in cases {
            assert_eq!(expand_resource_tokens(text, RESOURCE_TOKENS), want);
        }
    }

    #[test]
    fn message_lengths_are_re_encoded() {
        let mut data = vec![0x0a, 8];
        data.extend_from_slice(b"{Energy}");
        let (out, count) = expand_tokens_in_message(&data, RESOURCE_TOKENS).unwrap();
        assert_eq!((out, count), ([&[0x0a, 6][..], b"Energy"].concat(), 1));
        assert_eq!(
            expand_tokens_in_message(b"\x00{Energy}", RESOURCE_TOKENS),
            Err(NotMessage)
        );
    }
}
