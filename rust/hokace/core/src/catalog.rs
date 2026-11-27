//! The runtime's catalog: `wxq_patch.adaptive.Catalog` (`__init__`, `lookup`) and `load_catalog`.
//!
//! Ported from the bytecode (ADR-003) and held to `rust/harness/runtime_tap.py --catalog`. The
//! catalog is read as JSON with its key order kept, because the runtime's dicts keep insertion order.
//! Every error the runtime raises on purpose is reproduced with its class and message, and so are
//! the `KeyError`, `ValueError` and `TypeError` a well-shaped but wrong catalog meets. Text the runtime
//! would accept in another JSON type (a number where a string belongs) is refused here as a
//! `TypeError` of the port's own: the shipped catalogs hold strings only.

use std::collections::HashSet;
use std::fmt;
use std::fs::File;
use std::io::{BufReader, Read};
use std::path::Path;

use flate2::read::MultiGzDecoder;
use indexmap::IndexMap;
use serde_json::{Map, Value};

/// `(asset, key, source)`, the identity `Catalog.context` and `english_updates` are keyed by.
pub type Identity = (String, String, String);

/// A Python exception: its class and `str()`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CatalogError {
    pub class: &'static str,
    pub message: String,
}

impl CatalogError {
    fn new(class: &'static str, message: impl Into<String>) -> Self {
        Self {
            class,
            message: message.into(),
        }
    }

    fn key(key: &str) -> Self {
        Self::new("KeyError", py_repr(key))
    }

    fn value(message: &str) -> Self {
        Self::new("ValueError", message)
    }
}

impl fmt::Display for CatalogError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}: {}", self.class, self.message)
    }
}

impl std::error::Error for CatalogError {}

/// `adaptive.Catalog` after `__init__`.
#[derive(Debug, Clone, Default)]
pub struct CatalogData {
    pub unique: IndexMap<String, String>,
    pub context: IndexMap<Identity, String>,
    pub english_updates: IndexMap<Identity, String>,
    pub english_sources: IndexMap<Identity, String>,
    /// `table_hashes` as `int(h, 16)`.
    pub known: HashSet<i128>,
    /// `graphics` by `int(g["hash"], 16)`, the last entry for a hash at its first position.
    pub graphics: IndexMap<i128, Map<String, Value>>,
    pub targets: HashSet<String>,
}

impl CatalogData {
    /// `Catalog(data)`.
    pub fn from_value(data: &Value) -> Result<Self, CatalogError> {
        if !is_one(getitem(data, "schema")?) {
            return Err(CatalogError::value("Unsupported catalog schema"));
        }
        let mut catalog = Self {
            unique: string_map(getitem(data, "unique")?)?,
            ..Self::default()
        };
        for row in rows(getitem(data, "contextual")?)? {
            let [asset, key, source, target] = unpack4(row)?;
            let identity = (text(asset)?, text(key)?, text(source)?);
            let target = text(target)?;
            if catalog
                .context
                .get(&identity)
                .is_some_and(|known| *known != target)
            {
                return Err(CatalogError::value("Conflicting catalog identity"));
            }
            catalog.context.insert(identity, target);
        }
        let empty = Value::Array(Vec::new());
        let updates = match data {
            Value::Object(map) => map.get("english_updates").unwrap_or(&empty),
            // INFALLIBLE: `getitem(data, "schema")` above already refused every non-object.
            _ => &empty,
        };
        for row in rows(updates)? {
            let items = row.as_array().ok_or_else(|| {
                CatalogError::new("TypeError", "English update rows must be lists")
            })?;
            if !matches!(items.len(), 4 | 5) {
                return Err(CatalogError::value("Invalid English update record"));
            }
            let identity = (text(&items[0])?, text(&items[1])?, text(&items[2])?);
            let target = text(&items[3])?;
            if catalog
                .english_updates
                .get(&identity)
                .is_some_and(|known| *known != target)
            {
                return Err(CatalogError::value("Conflicting English update identity"));
            }
            let base = if items.len() == 5 {
                text(&items[4])?
            } else {
                identity.2.clone()
            };
            catalog.english_updates.insert(identity.clone(), target);
            catalog.english_sources.insert(identity, base);
        }
        for hash in rows(getitem(data, "table_hashes")?)? {
            catalog.known.insert(int_base16(hash)?);
        }
        for graphic in rows(getitem(data, "graphics")?)? {
            let hash = int_base16(getitem(graphic, "hash")?)?;
            let Value::Object(entry) = graphic else {
                // INFALLIBLE: `getitem` refuses every value but an object holding "hash".
                continue;
            };
            catalog.graphics.insert(hash, entry.clone());
        }
        catalog.targets = catalog
            .unique
            .values()
            .chain(catalog.context.values())
            .chain(catalog.english_updates.values())
            .cloned()
            .collect();
        Ok(catalog)
    }

    /// `Catalog.lookup(asset, key, source)`.
    pub fn lookup(&self, asset: i128, key: &str, source: &str) -> Option<&str> {
        let identity = (format_016x(asset), key.to_owned(), source.to_owned());
        self.context
            .get(&identity)
            .or_else(|| self.unique.get(source))
            .map(String::as_str)
    }
}

/// `adaptive.load_catalog(folder)`: `<folder>/catalog.json.gz`, gzip, UTF-8, JSON.
pub fn load_catalog(folder: &Path) -> Result<CatalogData, CatalogError> {
    let path = folder.join("catalog.json.gz");
    let file = File::open(&path).map_err(|error| io_error(&error, &path))?;
    let mut text = String::new();
    MultiGzDecoder::new(BufReader::new(file))
        .read_to_string(&mut text)
        .map_err(|error| io_error(&error, &path))?;
    let data: Value = serde_json::from_str(&text)
        .map_err(|error| CatalogError::new("JSONDecodeError", error.to_string()))?;
    CatalogData::from_value(&data)
}

fn io_error(error: &std::io::Error, path: &Path) -> CatalogError {
    match error.kind() {
        std::io::ErrorKind::NotFound => CatalogError::new(
            "FileNotFoundError",
            format!(
                "[Errno 2] No such file or directory: {}",
                py_repr(&path.to_string_lossy())
            ),
        ),
        std::io::ErrorKind::InvalidData => {
            CatalogError::new("UnicodeDecodeError", error.to_string())
        }
        _ => CatalogError::new("OSError", error.to_string()),
    }
}

/// `value == 1` in Python: `1`, `1.0` and `True`.
fn is_one(value: &Value) -> bool {
    match value {
        Value::Bool(flag) => *flag,
        Value::Number(number) => number.as_i64() == Some(1) || number.as_f64() == Some(1.0),
        _ => false,
    }
}

fn type_name(value: &Value) -> &'static str {
    match value {
        Value::Null => "NoneType",
        Value::Bool(_) => "bool",
        Value::Number(number) if number.is_f64() => "float",
        Value::Number(_) => "int",
        Value::String(_) => "str",
        Value::Array(_) => "list",
        Value::Object(_) => "dict",
    }
}

/// `value[key]` for a JSON value, with the exception Python raises.
fn getitem<'a>(value: &'a Value, key: &str) -> Result<&'a Value, CatalogError> {
    match value {
        Value::Object(map) => map.get(key).ok_or_else(|| CatalogError::key(key)),
        Value::Array(_) => Err(CatalogError::new(
            "TypeError",
            "list indices must be integers or slices, not str",
        )),
        Value::String(_) => Err(CatalogError::new(
            "TypeError",
            "string indices must be integers, not 'str'",
        )),
        other => Err(CatalogError::new(
            "TypeError",
            format!("'{}' object is not subscriptable", type_name(other)),
        )),
    }
}

/// The items a `for` loop over a JSON list walks.
fn rows(value: &Value) -> Result<&[Value], CatalogError> {
    value
        .as_array()
        .map(Vec::as_slice)
        .ok_or_else(|| match value {
            Value::Object(_) | Value::String(_) => {
                CatalogError::new("TypeError", "catalog rows must be lists")
            }
            other => CatalogError::new(
                "TypeError",
                format!("'{}' object is not iterable", type_name(other)),
            ),
        })
}

fn unpack4(row: &Value) -> Result<[&Value; 4], CatalogError> {
    let items = row
        .as_array()
        .ok_or_else(|| CatalogError::new("TypeError", "catalog rows must be lists"))?;
    match items.as_slice() {
        [a, b, c, d] => Ok([a, b, c, d]),
        short if short.len() < 4 => Err(CatalogError::value(&format!(
            "not enough values to unpack (expected 4, got {})",
            short.len()
        ))),
        _ => Err(CatalogError::value(
            "too many values to unpack (expected 4)",
        )),
    }
}

fn text(value: &Value) -> Result<String, CatalogError> {
    value
        .as_str()
        .map(str::to_owned)
        .ok_or_else(|| CatalogError::new("TypeError", "catalog text must be a string"))
}

fn string_map(value: &Value) -> Result<IndexMap<String, String>, CatalogError> {
    let map = value.as_object().ok_or_else(|| {
        CatalogError::new("TypeError", "the catalog's unique table must be a dict")
    })?;
    map.iter()
        .map(|(key, value)| Ok((key.clone(), text(value)?)))
        .collect()
}

/// `int(value, 16)` for a JSON value: ASCII digits only (Python also takes other Unicode digits).
fn int_base16(value: &Value) -> Result<i128, CatalogError> {
    let Value::String(raw) = value else {
        return Err(CatalogError::new(
            "TypeError",
            "int() can't convert non-string with explicit base",
        ));
    };
    let invalid = || {
        let shown: String = py_repr(raw).chars().take(200).collect();
        CatalogError::value(&format!("invalid literal for int() with base 16: {shown}"))
    };
    // `int()` maps Unicode spaces to ASCII ones, then trims only ASCII whitespace, so unlike
    // `str.strip()` it keeps `\x1c`-`\x1f`: exactly Rust's `White_Space` (recorded).
    let trimmed = raw.trim_matches(char::is_whitespace);
    let (negative, rest) = match trimmed.as_bytes().first() {
        Some(b'-') => (true, &trimmed[1..]),
        Some(b'+') => (false, &trimmed[1..]),
        _ => (false, trimmed),
    };
    let (prefixed, digits) = match rest.get(..2) {
        Some("0x" | "0X") => (true, &rest[2..]),
        _ => (false, rest),
    };
    // An underscore may follow the prefix or a digit, never another underscore, and never ends it.
    let mut value: i128 = 0;
    let mut seen_digit = false;
    let mut after_underscore = false;
    for c in digits.chars() {
        if c == '_' {
            if after_underscore || !seen_digit && !prefixed {
                return Err(invalid());
            }
            after_underscore = true;
            continue;
        }
        let digit = c.to_digit(16).ok_or_else(invalid)?;
        value = value
            .checked_mul(16)
            .and_then(|v| v.checked_add(i128::from(digit)))
            .ok_or_else(|| {
                CatalogError::new("OverflowError", "catalog hash too large for the port")
            })?;
        seen_digit = true;
        after_underscore = false;
    }
    if !seen_digit || after_underscore {
        return Err(invalid());
    }
    Ok(if negative { -value } else { value })
}

/// `f"{asset:016X}"`: the sign counts toward the width.
fn format_016x(asset: i128) -> String {
    if asset < 0 {
        format!("-{:015X}", asset.unsigned_abs())
    } else {
        format!("{asset:016X}")
    }
}

/// Characters `repr()` escapes beyond ASCII control codes: the C1 controls and the common
/// non-printable spaces and format characters (`str.isprintable()` is false for them).
fn escaped(c: char) -> bool {
    matches!(c, '\u{80}'..='\u{a0}' | '\u{ad}' | '\u{1680}' | '\u{2000}'..='\u{200f}' | '\u{2028}'..='\u{202f}'
        | '\u{205f}'..='\u{2064}' | '\u{3000}' | '\u{feff}')
}

/// Python's `repr()` of a `str`.
pub fn py_repr(text: &str) -> String {
    let quote = if text.contains('\'') && !text.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut out = String::with_capacity(text.len() + 2);
    out.push(quote);
    for c in text.chars() {
        match c {
            '\\' => out.push_str("\\\\"),
            '\t' => out.push_str("\\t"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            c if c == quote => {
                out.push('\\');
                out.push(c);
            }
            c if c < ' ' || c == '\x7f' => out.push_str(&format!("\\x{:02x}", u32::from(c))),
            c if escaped(c) && u32::from(c) <= 0xff => {
                out.push_str(&format!("\\x{:02x}", u32::from(c)))
            }
            c if escaped(c) => out.push_str(&format!("\\u{:04x}", u32::from(c))),
            c => out.push(c),
        }
    }
    out.push(quote);
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn base() -> Value {
        json!({"schema": 1, "unique": {"源": "Source"}, "contextual": [], "table_hashes": ["00BF2528D217FFFA"],
               "graphics": [{"hash": "0A", "label": "x"}]})
    }

    #[test]
    fn hex_follows_python_int() {
        for (text, value) in [
            ("0A", 10),
            (" 0a\n", 10),
            ("0x0A", 10),
            ("+f", 15),
            ("-1", -1),
            ("0_a", 10),
            ("0x_a", 10),
        ] {
            assert_eq!(int_base16(&json!(text)), Ok(value), "{text}");
        }
        for text in ["", "_0a", "0a_", "0__a", "0x", "0x__a", "g", "0X_"] {
            assert_eq!(
                int_base16(&json!(text)).map_err(|e| e.class),
                Err("ValueError"),
                "{text}"
            );
        }
        assert_eq!(int_base16(&json!(1)).map_err(|e| e.class), Err("TypeError"));
    }

    #[test]
    fn catalog_checks_and_lookup() {
        let catalog = CatalogData::from_value(&base()).unwrap();
        assert!(catalog.known.contains(&0x00BF_2528_D217_FFFA));
        assert_eq!(catalog.lookup(1, "k", "源"), Some("Source"));
        assert_eq!(catalog.lookup(1, "k", "x"), None);
        let mut data = base();
        data["schema"] = json!(2);
        assert_eq!(
            CatalogData::from_value(&data).unwrap_err().to_string(),
            "ValueError: Unsupported catalog schema"
        );
        let mut data = base();
        data["contextual"] = json!([["A", "k", "s", "t"], ["A", "k", "s", "u"]]);
        assert_eq!(
            CatalogData::from_value(&data).unwrap_err().message,
            "Conflicting catalog identity"
        );
        let mut data = base();
        data.as_object_mut().unwrap().remove("graphics");
        assert_eq!(
            CatalogData::from_value(&data).unwrap_err().to_string(),
            "KeyError: 'graphics'"
        );
    }

    #[test]
    fn asset_format_keeps_the_sign_in_the_width() {
        assert_eq!(format_016x(10), "000000000000000A");
        assert_eq!(format_016x(-1), "-000000000000001");
    }

    #[test]
    fn repr_picks_quotes_and_escapes() {
        assert_eq!(py_repr("a'b"), "\"a'b\"");
        assert_eq!(py_repr("a'\"b"), "'a\\'\"b'");
        assert_eq!(py_repr("\\\n\x01\u{a0}名"), "'\\\\\\n\\x01\\xa0名'");
    }
}
