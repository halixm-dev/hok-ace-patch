//! The Rust port of `outside_ranges` from `tools/research/pixel_diff/__init__.py`.
//!
//! `ranges` arrives in the bridge's JSON form of a Python object (`{"$tuple": [...]}`). Python reads
//! it only at a differing byte and stops at the first range that holds the index, so each range is
//! parsed once into what `start <= index < end` gives or raises, raised only where Python gets to it.

#![forbid(unsafe_code)]

use serde_json::Value;

type Bound = Result<f64, String>;

/// A Python value as `outside_ranges` sees it: its type name, what iterating it yields (`None`
/// where Python cannot iterate it) and its number (`None` where comparing it with an int raises).
/// Numbers are compared as `f64`, exact for every index, which stays below 2^53.
fn view(value: &Value) -> (&'static str, Option<Vec<Value>>, Option<f64>) {
    let tag = value
        .as_object()
        .filter(|m| m.len() == 1)
        .and_then(|m| m.iter().next());
    let names = |keys: Vec<String>| Some(keys.into_iter().map(Value::String).collect::<Vec<_>>());
    match (value, tag.filter(|(key, _)| key.starts_with('$'))) {
        (_, Some((tag, inner))) => match (tag.as_str(), inner) {
            ("$tuple", Value::Array(items)) => ("tuple", Some(items.clone()), None),
            ("$set", Value::Array(items)) => ("set", Some(items.clone()), None),
            ("$bytes", Value::Array(items)) => ("bytes", Some(items.clone()), None),
            ("$dict", Value::Array(pairs)) => {
                let keys = pairs.iter().map(|p| p.get(0).cloned().unwrap_or_default());
                ("dict", Some(keys.collect()), None)
            }
            ("$int", Value::String(text)) => ("int", None, text.parse().ok()),
            ("$num", Value::String(text)) => ("float", None, text.parse().ok()),
            _ => ("object", None, None),
        },
        (Value::Null, _) => ("NoneType", None, None),
        (Value::Bool(b), _) => ("bool", None, Some(f64::from(u8::from(*b)))),
        (Value::Number(n), _) => (if n.is_f64() { "float" } else { "int" }, None, n.as_f64()),
        (Value::String(s), _) => ("str", names(s.chars().map(String::from).collect()), None),
        (Value::Array(items), _) => ("list", Some(items.clone()), None),
        (Value::Object(map), _) => ("dict", names(map.keys().cloned().collect()), None),
    }
}

/// One bound of a range, or the error comparing it raises: `start <= index` when `left`, else `index < end`.
fn bound(value: &Value, left: bool) -> Bound {
    let (name, _, number) = view(value);
    let (op, l, r) = if left {
        ("<=", name, "int")
    } else {
        ("<", "int", name)
    };
    number.ok_or_else(|| {
        format!("TypeError: '{op}' not supported between instances of '{l}' and '{r}'")
    })
}

/// `start, end = range_`: an unpack error, or both bounds.
fn parse(range: &Value) -> Result<(Bound, Bound), String> {
    let (name, items, _) = view(range);
    let items =
        items.ok_or_else(|| format!("TypeError: cannot unpack non-iterable {name} object"))?;
    match items.as_slice() {
        [start, end] => Ok((bound(start, true), bound(end, false))),
        [] | [_] => Err(format!(
            "ValueError: not enough values to unpack (expected 2, got {})",
            items.len()
        )),
        _ => Err("ValueError: too many values to unpack (expected 2)".into()),
    }
}

/// Port of `outside_ranges` (`tools/research/pixel_diff/__init__.py:15`).
pub fn outside_ranges(
    raw: Vec<u8>,
    new: Vec<u8>,
    ranges: serde_json::Value,
) -> Result<i64, String> {
    let differing: Vec<usize> = (0..raw.len().min(new.len()))
        .filter(|&i| raw[i] != new[i])
        .collect();
    if differing.is_empty() {
        return Ok(0);
    }
    let (name, ranges, _) = view(&ranges);
    let ranges = ranges.ok_or_else(|| format!("TypeError: '{name}' object is not iterable"))?;
    let ranges: Vec<_> = ranges.iter().map(parse).collect();
    let mut count = 0;
    for index in differing {
        count += 1;
        for range in &ranges {
            let (start, end) = range.clone()?;
            if start? <= index as f64 && end? > index as f64 {
                count -= 1;
                break;
            }
        }
    }
    Ok(count)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn counts_only_outside_the_ranges() {
        let (raw, new) = (vec![0, 0, 0, 0, 0, 0], vec![1, 1, 0, 1, 1, 1]);
        assert_eq!(
            outside_ranges(raw.clone(), new.clone(), json!([{"$tuple": [1, 4]}])),
            Ok(3)
        );
        assert_eq!(outside_ranges(raw.clone(), new.clone(), json!([])), Ok(5));
        assert_eq!(outside_ranges(raw, new, json!([[0, 2], [1, 6]])), Ok(0));
    }

    #[test]
    fn raises_only_where_python_reaches() {
        let err = |r: Value| {
            outside_ranges(vec![1], vec![2], r)
                .err()
                .unwrap_or_default()
        };
        assert_eq!(outside_ranges(vec![1], vec![1], json!(true)), Ok(0));
        assert_eq!(err(json!(true)), "TypeError: 'bool' object is not iterable");
        assert_eq!(
            err(json!([[0]])),
            "ValueError: not enough values to unpack (expected 2, got 1)"
        );
        assert_eq!(
            err(json!([[0, 1, 2]])),
            "ValueError: too many values to unpack (expected 2)"
        );
        assert_eq!(
            err(json!([["a", 1]])),
            "TypeError: '<=' not supported between instances of 'str' and 'int'"
        );
        assert_eq!(
            err(json!([[0, null]])),
            "TypeError: '<' not supported between instances of 'int' and 'NoneType'"
        );
        assert_eq!(
            outside_ranges(vec![1], vec![2], json!([[1, null], [0, 1]])),
            Ok(0)
        );
        assert_eq!(
            outside_ranges(vec![1], vec![2], json!([[0, 1], null])),
            Ok(0)
        );
    }
}
