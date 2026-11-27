//! Where `json.loads` refuses a document and how it words it: the error paths of CPython 3.12's C
//! scanner (`Modules/_json.c`) and `json.decoder.JSONDecoder.decode`, for `pyos::read_json` to raise
//! the runtime's `JSONDecodeError` text. Parsing itself stays with serde; this walks the text only
//! after serde has refused it.
//!
//! Positions count characters, not bytes, as Python's do. Checked against messages Python gave
//! (`rust/generators/json_errors.py`, `tests/json_errors.rs`).

/// `json.loads(text)`'s `JSONDecodeError` message, or `None` where Python would accept the text.
pub fn decode_error(text: &str) -> Option<String> {
    let chars: Vec<char> = text.chars().collect();
    let (message, pos) = find(&chars)?;
    let before = &chars[..pos.min(chars.len())];
    let line = before.iter().filter(|&&c| c == '\n').count() + 1;
    let column = match before.iter().rposition(|&c| c == '\n') {
        Some(newline) => pos - newline,
        None => pos + 1,
    };
    Some(format!(
        "{message}: line {line} column {column} (char {pos})"
    ))
}

type Fail = (&'static str, usize);

/// A failed `scan_once`: `StopIteration(idx)`, which `raw_decode` turns into "Expecting value".
enum Error {
    Stop(usize),
    Message(Fail),
}

fn find(s: &[char]) -> Option<Fail> {
    if s.first() == Some(&'\u{feff}') {
        return Some(("Unexpected UTF-8 BOM (decode using utf-8-sig)", 0));
    }
    let start = skip(s, 0);
    match scan_once(s, start) {
        Err(Error::Stop(idx)) => Some(("Expecting value", idx)),
        Err(Error::Message(fail)) => Some(fail),
        Ok(end) => {
            let end = skip(s, end);
            (end != s.len()).then_some(("Extra data", end))
        }
    }
}

fn is_space(c: char) -> bool {
    matches!(c, ' ' | '\t' | '\n' | '\r')
}

fn skip(s: &[char], mut idx: usize) -> usize {
    while idx < s.len() && is_space(s[idx]) {
        idx += 1;
    }
    idx
}

fn at(s: &[char], idx: usize) -> Option<char> {
    s.get(idx).copied()
}

fn literal(s: &[char], idx: usize, word: &str) -> bool {
    let word: Vec<char> = word.chars().collect();
    idx + word.len() <= s.len() && s[idx..idx + word.len()] == word[..]
}

/// `scan_once_unicode`: the index after the term at `idx`.
fn scan_once(s: &[char], idx: usize) -> Result<usize, Error> {
    let Some(c) = at(s, idx) else {
        return Err(Error::Stop(idx));
    };
    match c {
        '"' => return scan_string(s, idx + 1),
        '{' => return object(s, idx + 1),
        '[' => return array(s, idx + 1),
        _ => {}
    }
    for word in ["null", "true", "false", "NaN", "Infinity", "-Infinity"] {
        if word.starts_with(c) && literal(s, idx, word) {
            return Ok(idx + word.chars().count());
        }
    }
    number(s, idx)
}

/// `_match_number_unicode`.
fn number(s: &[char], start: usize) -> Result<usize, Error> {
    let digit = |i: usize| at(s, i).is_some_and(|c| c.is_ascii_digit());
    let mut idx = start;
    if at(s, idx) == Some('-') {
        idx += 1;
        if idx >= s.len() {
            return Err(Error::Stop(start));
        }
    }
    match at(s, idx) {
        Some('1'..='9') => {
            idx += 1;
            while digit(idx) {
                idx += 1;
            }
        }
        Some('0') => idx += 1,
        _ => return Err(Error::Stop(start)),
    }
    if idx + 1 < s.len() && s[idx] == '.' && digit(idx + 1) {
        idx += 2;
        while digit(idx) {
            idx += 1;
        }
    }
    if idx + 1 < s.len() && matches!(s[idx], 'e' | 'E') {
        let e_start = idx;
        idx += 1;
        if idx + 1 < s.len() && matches!(s[idx], '-' | '+') {
            idx += 1;
        }
        while digit(idx) {
            idx += 1;
        }
        if !digit(idx - 1) {
            idx = e_start;
        }
    }
    Ok(idx)
}

/// `_parse_object_unicode`, from just after `{`.
fn object(s: &[char], start: usize) -> Result<usize, Error> {
    let mut idx = skip(s, start);
    if at(s, idx) != Some('}') {
        loop {
            if at(s, idx) != Some('"') {
                return Err(Error::Message((
                    "Expecting property name enclosed in double quotes",
                    idx,
                )));
            }
            idx = skip(s, scan_string(s, idx + 1)?);
            if at(s, idx) != Some(':') {
                return Err(Error::Message(("Expecting ':' delimiter", idx)));
            }
            idx = skip(s, idx + 1);
            idx = skip(s, scan_once(s, idx)?);
            if at(s, idx) == Some('}') {
                break;
            }
            if at(s, idx) != Some(',') {
                return Err(Error::Message(("Expecting ',' delimiter", idx)));
            }
            idx = skip(s, idx + 1);
        }
    }
    Ok(idx + 1)
}

/// `_parse_array_unicode`, from just after `[`.
fn array(s: &[char], start: usize) -> Result<usize, Error> {
    let mut idx = skip(s, start);
    if at(s, idx) != Some(']') {
        loop {
            idx = skip(s, scan_once(s, idx)?);
            if at(s, idx) == Some(']') {
                break;
            }
            if at(s, idx) != Some(',') {
                return Err(Error::Message(("Expecting ',' delimiter", idx)));
            }
            idx = skip(s, idx + 1);
        }
    }
    Ok(idx + 1)
}

fn hex4(s: &[char], from: usize) -> Option<u32> {
    let mut value = 0;
    for &c in &s[from..from + 4] {
        value = (value << 4) | c.to_digit(16)?;
    }
    Some(value)
}

/// `scanstring_unicode(pystr, end, strict=True)`, from just after the opening quote.
fn scan_string(s: &[char], mut end: usize) -> Result<usize, Error> {
    let begin = end - 1;
    let len = s.len();
    loop {
        let mut next = end;
        let mut c = '\0';
        while next < len {
            c = s[next];
            if c == '"' || c == '\\' {
                break;
            }
            if c <= '\u{1f}' {
                return Err(Error::Message(("Invalid control character at", next)));
            }
            next += 1;
        }
        if next >= len || (c != '"' && c != '\\') {
            return Err(Error::Message(("Unterminated string starting at", begin)));
        }
        next += 1;
        if c == '"' {
            return Ok(next);
        }
        if next == len {
            return Err(Error::Message(("Unterminated string starting at", begin)));
        }
        if s[next] != 'u' {
            end = next + 1;
            if !matches!(s[next], '"' | '\\' | '/' | 'b' | 'f' | 'n' | 'r' | 't') {
                return Err(Error::Message(("Invalid \\escape", end - 2)));
            }
            continue;
        }
        next += 1;
        end = next + 4;
        if end >= len {
            return Err(Error::Message(("Invalid \\uXXXX escape", next - 1)));
        }
        let Some(code) = hex4(s, next) else {
            return Err(Error::Message(("Invalid \\uXXXX escape", end - 5)));
        };
        next = end;
        if (0xD800..0xDC00).contains(&code)
            && end + 6 < len
            && s[next] == '\\'
            && s[next + 1] == 'u'
        {
            end += 6;
            match hex4(s, next + 2) {
                None => return Err(Error::Message(("Invalid \\uXXXX escape", end - 5))),
                Some(low) if (0xDC00..0xE000).contains(&low) => {}
                Some(_) => end -= 6,
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::decode_error;

    #[test]
    fn known_messages() {
        assert_eq!(
            decode_error("{not json").as_deref(),
            Some("Expecting property name enclosed in double quotes: line 1 column 2 (char 1)")
        );
        assert_eq!(
            decode_error("{\"a\": }").as_deref(),
            Some("Expecting value: line 1 column 7 (char 6)")
        );
        assert_eq!(decode_error("[1, 2]"), None);
        assert_eq!(
            decode_error("[1]\n x").as_deref(),
            Some("Extra data: line 2 column 2 (char 5)")
        );
    }
}
