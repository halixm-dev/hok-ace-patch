//! Python 3.12 `str` predicates the pipeline leans on, measured from CPython's Unicode 15.0 tables.
//!
//! Rust's `char::is_whitespace` and `char::is_numeric` draw other lines: Python's `isspace` also holds
//! the four information separators `\x1c`-`\x1f`, and `isdigit` holds the decimal digits plus the
//! superscript, circled and other digits whose numeric type is Digit, not every `No` character.

/// `str.isspace()` for one character.
pub fn is_space(c: char) -> bool {
    matches!(c, '\t'..='\r' | '\x1c'..='\x20' | '\u{85}' | '\u{a0}' | '\u{1680}' | '\u{2000}'..='\u{200a}'
        | '\u{2028}' | '\u{2029}' | '\u{202f}' | '\u{205f}' | '\u{3000}')
}

/// `str.strip()` with no argument.
pub fn strip(text: &str) -> &str {
    text.trim_matches(is_space)
}

/// The `str.isdigit()` ranges, from `[c for c in range(0x110000) if chr(c).isdigit()]` on 3.12.10.
const DIGITS: &[(u32, u32)] = &[
    (0x30, 0x39),
    (0xb2, 0xb3),
    (0xb9, 0xb9),
    (0x660, 0x669),
    (0x6f0, 0x6f9),
    (0x7c0, 0x7c9),
    (0x966, 0x96f),
    (0x9e6, 0x9ef),
    (0xa66, 0xa6f),
    (0xae6, 0xaef),
    (0xb66, 0xb6f),
    (0xbe6, 0xbef),
    (0xc66, 0xc6f),
    (0xce6, 0xcef),
    (0xd66, 0xd6f),
    (0xde6, 0xdef),
    (0xe50, 0xe59),
    (0xed0, 0xed9),
    (0xf20, 0xf29),
    (0x1040, 0x1049),
    (0x1090, 0x1099),
    (0x1369, 0x1371),
    (0x17e0, 0x17e9),
    (0x1810, 0x1819),
    (0x1946, 0x194f),
    (0x19d0, 0x19da),
    (0x1a80, 0x1a89),
    (0x1a90, 0x1a99),
    (0x1b50, 0x1b59),
    (0x1bb0, 0x1bb9),
    (0x1c40, 0x1c49),
    (0x1c50, 0x1c59),
    (0x2070, 0x2070),
    (0x2074, 0x2079),
    (0x2080, 0x2089),
    (0x2460, 0x2468),
    (0x2474, 0x247c),
    (0x2488, 0x2490),
    (0x24ea, 0x24ea),
    (0x24f5, 0x24fd),
    (0x24ff, 0x24ff),
    (0x2776, 0x277e),
    (0x2780, 0x2788),
    (0x278a, 0x2792),
    (0xa620, 0xa629),
    (0xa8d0, 0xa8d9),
    (0xa900, 0xa909),
    (0xa9d0, 0xa9d9),
    (0xa9f0, 0xa9f9),
    (0xaa50, 0xaa59),
    (0xabf0, 0xabf9),
    (0xff10, 0xff19),
    (0x104a0, 0x104a9),
    (0x10a40, 0x10a43),
    (0x10d30, 0x10d39),
    (0x10e60, 0x10e68),
    (0x11052, 0x1105a),
    (0x11066, 0x1106f),
    (0x110f0, 0x110f9),
    (0x11136, 0x1113f),
    (0x111d0, 0x111d9),
    (0x112f0, 0x112f9),
    (0x11450, 0x11459),
    (0x114d0, 0x114d9),
    (0x11650, 0x11659),
    (0x116c0, 0x116c9),
    (0x11730, 0x11739),
    (0x118e0, 0x118e9),
    (0x11950, 0x11959),
    (0x11c50, 0x11c59),
    (0x11d50, 0x11d59),
    (0x11da0, 0x11da9),
    (0x11f50, 0x11f59),
    (0x16a60, 0x16a69),
    (0x16ac0, 0x16ac9),
    (0x16b50, 0x16b59),
    (0x1d7ce, 0x1d7ff),
    (0x1e140, 0x1e149),
    (0x1e2f0, 0x1e2f9),
    (0x1e4f0, 0x1e4f9),
    (0x1e950, 0x1e959),
    (0x1f100, 0x1f10a),
    (0x1fbf0, 0x1fbf9),
];

/// `str.isdigit()` for one character.
pub fn is_digit(c: char) -> bool {
    let c = u32::from(c);
    DIGITS
        .binary_search_by(|&(low, high)| {
            if high < c {
                std::cmp::Ordering::Less
            } else if low > c {
                std::cmp::Ordering::Greater
            } else {
                std::cmp::Ordering::Equal
            }
        })
        .is_ok()
}

/// `text[:1].upper() + text[1:]`.
pub fn capitalize_first(text: &str) -> String {
    let mut chars = text.chars();
    match chars.next() {
        Some(first) => first.to_uppercase().chain(chars).collect(),
        None => String::new(),
    }
}

/// `text[:1].lower() + text[1:]`.
pub fn lower_first(text: &str) -> String {
    let mut chars = text.chars();
    match chars.next() {
        Some(first) => first.to_lowercase().chain(chars).collect(),
        None => String::new(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn space_holds_the_separators() {
        assert!(is_space('\x1f') && is_space('\u{3000}') && !is_space('\u{200b}'));
        assert_eq!(strip("\x1c a. \u{a0}"), "a.");
    }

    #[test]
    fn digit_holds_superscripts_not_fractions() {
        assert!(is_digit('7') && is_digit('²') && is_digit('①') && is_digit('٣'));
        assert!(!is_digit('½') && !is_digit('Ⅻ') && !is_digit('一'));
    }
}
