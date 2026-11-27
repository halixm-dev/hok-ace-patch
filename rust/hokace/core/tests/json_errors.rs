//! `pyjson::decode_error` against the messages CPython 3.12's `json.loads` gave
//! (`rust/generators/json_errors.py`).

use hokace_core::pyjson::decode_error;

#[test]
fn matches_python_json_errors() {
    let mut failures = Vec::new();
    let mut total = 0;
    for line in include_str!("json_errors.jsonl").lines() {
        let row: serde_json::Value = serde_json::from_str(line).unwrap();
        let text = row[0].as_str().unwrap();
        let want = row[1].as_str();
        let got = decode_error(text);
        total += 1;
        if got.as_deref() != want {
            failures.push(format!("{text:?}\n  got  {got:?}\n  want {want:?}"));
        }
    }
    assert!(
        failures.is_empty(),
        "{} of {total} differ:\n{}",
        failures.len(),
        failures[..failures.len().min(15)].join("\n")
    );
}
