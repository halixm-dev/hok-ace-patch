//! `tools/pb_text.py`: generic protobuf string rewriting for config assets the catalog has no table for.
//!
//! A length-delimited field is text when it is UTF-8 without control characters; otherwise a field that
//! parses completely as a message is recursed into (to depth 16), and anything else stays opaque. A
//! nested parse that fails is dropped, but the strings it offered `translate` before failing were
//! offered, so `collect` keeps them, as Python's does.

use crate::resource_tokens::NotMessage;

/// `CJK`: `[㐀-鿿豈-﫿]`.
pub fn is_cjk(c: char) -> bool {
    matches!(c, '\u{3400}'..='\u{9fff}' | '\u{f900}'..='\u{faff}')
}

fn is_control(c: char) -> bool {
    matches!(c, '\x00'..='\x08' | '\x0b' | '\x0c' | '\x0e'..='\x1f')
}

fn varint(data: &[u8], mut pos: usize) -> Result<(u128, usize), NotMessage> {
    let (mut result, mut shift) = (0u128, 0u32);
    loop {
        if pos >= data.len() || shift > 63 {
            return Err(NotMessage);
        }
        let byte = data[pos];
        pos += 1;
        result |= u128::from(byte & 0x7F) << shift;
        if byte & 0x80 == 0 {
            return Ok((result, pos));
        }
        shift += 7;
    }
}

fn as_text(value: &[u8]) -> Option<&str> {
    let text = std::str::from_utf8(value).ok()?;
    (!text.chars().any(is_control)).then_some(text)
}

pub type Translate<'a> = &'a mut dyn FnMut(&str) -> Option<String>;

/// `rewrite`: (message with translated strings, number of strings replaced).
pub fn rewrite(
    data: &[u8],
    translate: Translate<'_>,
    depth: u32,
) -> Result<(Vec<u8>, u64), NotMessage> {
    let len = data.len() as u128;
    let mut out = Vec::with_capacity(data.len());
    let (mut pos, mut changed) = (0usize, 0u64);
    while pos < data.len() {
        let (key, after_key) = varint(data, pos)?;
        let (field, wire) = (key >> 3, key & 7);
        if field == 0 {
            return Err(NotMessage);
        }
        let end: u128 = match wire {
            0 => {
                let (_, end) = varint(data, after_key)?;
                out.extend_from_slice(&data[pos..end]);
                end as u128
            }
            1 | 5 => {
                let end = after_key as u128 + if wire == 1 { 8 } else { 4 };
                if end > len {
                    return Err(NotMessage);
                }
                out.extend_from_slice(&data[pos..end as usize]);
                end
            }
            2 => {
                let (length, start) = varint(data, after_key)?;
                let end = start as u128 + length;
                if end > len {
                    return Err(NotMessage);
                }
                let raw = &data[start..end as usize];
                let mut value = raw.to_vec();
                match as_text(raw) {
                    Some(text) if text.chars().any(is_cjk) => {
                        if let Some(replacement) = translate(text)
                            && replacement != text
                        {
                            value = replacement.into_bytes();
                            changed += 1;
                        }
                    }
                    None if depth < 16 && !raw.is_empty() => {
                        if let Ok((nested, count)) = rewrite(raw, translate, depth + 1) {
                            value = nested;
                            changed += count;
                        }
                    }
                    _ => {}
                }
                // A replaced string can encode to a different length, so the length prefix is rewritten.
                out.extend_from_slice(&data[pos..after_key]);
                crate::config_bin::put_varint(value.len() as u128, &mut out);
                out.extend_from_slice(&value);
                end
            }
            _ => return Err(NotMessage),
        };
        pos = end as usize;
    }
    Ok((out, changed))
}

/// `collect`: every Chinese-bearing string field in <data>, by `rewrite`'s classification.
pub fn collect(data: &[u8], depth: u32) -> Result<Vec<String>, NotMessage> {
    let mut found = Vec::new();
    rewrite(
        data,
        &mut |text: &str| {
            found.push(text.to_owned());
            None
        },
        depth,
    )?;
    Ok(found)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn strings_are_replaced_and_lengths_rewritten() {
        let data = [b"\x0a\x06".as_slice(), "王者".as_bytes(), b"\x10\x01"].concat();
        let (out, changed) = rewrite(&data, &mut |_| Some("King".to_owned()), 0).unwrap();
        assert_eq!((out, changed), (b"\x0a\x04King\x10\x01".to_vec(), 1));
        assert_eq!(collect(&data, 0).unwrap(), ["王者"]);
        assert!(rewrite(b"\x0a\x09", &mut |_| None, 0).is_err());
    }
}
