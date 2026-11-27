//! `tools/catalog_updates.py`: exact updates for earlier translations and untranslated format rows,
//! and the measured copies of catalog tables a mode reads, merged into the catalog in memory.

use serde_json::{Map, Value, json};

/// The card text tables ACE Quick Match reads (game data 1.11.0.2), with what each copies.
pub const MODE_TABLE_COPIES: &[(&str, &str)] = &[
    (
        "39E980368CABE4A4",
        "card names and effects; a copy of C13DF45E3492CA0C, 9C4EC654D5454B46, ...",
    ),
    (
        "FABFEBEB801B5CD9",
        "Chessplayer, faction and mode texts; a copy of 42E8DB43608C2FF1, 04F21C6735D0D555, ...",
    ),
];

/// Measured in both layers of package 1 on 2026-10-17 (game data 1.6.0.1).
pub const YAO_ROWS: &[(&str, [&str; 2])] = &[
    (
        "23C9A9DEBB3BF40C",
        ["#FCC727E86456E964#", "#FCC762A70B7CDE1F#"],
    ),
    (
        "28D9F8B02CAA94E2",
        ["#23F727E86456E964#", "#23F762A70B7CDE1F#"],
    ),
    (
        "3D889D9ABCEDE2A8",
        ["#5AD127E86456E964#", "#5AD162A70B7CDE1F#"],
    ),
    (
        "4476EC307E0F2142",
        ["#801D27E86456E964#", "#801D62A70B7CDE1F#"],
    ),
    (
        "57C03656175B0904",
        ["#6D3B27E86456E964#", "#6D3B62A70B7CDE1F#"],
    ),
    (
        "9799DF91AB4F4FA3",
        ["#5A2E27E86456E964#", "#5A2E62A70B7CDE1F#"],
    ),
    (
        "9C4EC654D5454B46",
        ["#182527E86456E964#", "#182562A70B7CDE1F#"],
    ),
    (
        "9CAA7228F782AB5A",
        ["#BC6D27E86456E964#", "#BC6D62A70B7CDE1F#"],
    ),
    (
        "A07B2B9F994FB0ED",
        ["#6E6027E86456E964#", "#6E6062A70B7CDE1F#"],
    ),
    (
        "A336359CD92A858E",
        ["#8E5527E86456E964#", "#8E5562A70B7CDE1F#"],
    ),
    (
        "C13DF45E3492CA0C",
        ["#FBF327E86456E964#", "#FBF362A70B7CDE1F#"],
    ),
];
pub const YAO_SOURCE: &str =
    "你的英雄<a href=13><color=#ffffff>╦<b>合成</b></color></a>提升的等级+1。";
pub const YAO_PREVIOUS: &str =
    "Your Heroes gain +1 Level when <a href=13><color=#ffffff>╦<b>upgraded</b></color></a>.";

/// The Card Stats panel's format row, which joins operation and card name with no space.
pub const CARD_OPERATE_ROW: (&str, &str) = ("DD5B5EDFBB69FEED", "Dps_CardOperate");
pub const CARD_OPERATE_PREVIOUS: &str = "<color=#ffffff>{0}</color><color=#FFFFFFB2>{1}</color>";
pub const CARD_OPERATE_TARGET: &str = "<color=#ffffff>{0}</color> <color=#FFFFFFB2>{1}</color>";

fn object(data: &mut Value) -> Result<&mut Map<String, Value>, String> {
    data.as_object_mut()
        .ok_or_else(|| "the catalog is not an object".to_owned())
}

fn list<'a>(data: &'a mut Value, key: &str) -> Result<&'a mut Vec<Value>, String> {
    object(data)?
        .entry(key)
        .or_insert_with(|| Value::Array(Vec::new()))
        .as_array_mut()
        .ok_or_else(|| format!("the catalog's {key} is not a list"))
}

/// `admit_tables`: list `MODE_TABLE_COPIES` among the catalog's tables; how many were added.
pub fn admit_tables(data: &mut Value) -> Result<u64, String> {
    let known = list(data, "table_hashes")?;
    let added: Vec<Value> = MODE_TABLE_COPIES
        .iter()
        .map(|(hash, _)| json!(hash))
        .filter(|hash| !known.contains(hash))
        .collect();
    let count = added.len() as u64;
    known.extend(added);
    Ok(count)
}

/// `row[:3]` as a key: Python compares the tuple of values.
fn head(row: &Value) -> Vec<Value> {
    row.as_array()
        .map(|row| row.iter().take(3).cloned().collect())
        .unwrap_or_default()
}

/// `apply`: add missing exact update rows after terminology; upstream rows win.
pub fn apply(data: &mut Value, code: &str) -> Result<u64, String> {
    let known: Vec<Value> = match object(data)?.get("table_hashes") {
        Some(Value::Array(hashes)) => hashes.clone(),
        _ => Vec::new(),
    };
    let target = data
        .get("unique")
        .and_then(|unique| unique.get(YAO_SOURCE))
        .and_then(Value::as_str)
        .map(str::to_owned);
    let rows = list(data, "english_updates")?;
    let mut existing: Vec<Vec<Value>> = rows.iter().map(head).collect();
    let mut added = 0;
    let mut add = |row: Vec<&str>| {
        let row = json!(row);
        let key = head(&row);
        if known.contains(&row[0]) && !existing.contains(&key) {
            rows.push(row);
            existing.push(key);
            added += 1;
        }
    };
    add(vec![
        CARD_OPERATE_ROW.0,
        CARD_OPERATE_ROW.1,
        CARD_OPERATE_PREVIOUS,
        CARD_OPERATE_TARGET,
    ]);
    let target = target.filter(|target| !target.is_empty());
    match target {
        Some(target) if code == "en" && target != YAO_PREVIOUS => {
            for (asset, keys) in YAO_ROWS {
                for key in keys {
                    add(vec![asset, key, YAO_PREVIOUS, &target, YAO_SOURCE]);
                }
            }
        }
        _ => {}
    }
    Ok(added)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rows_only_for_known_tables_and_once() {
        let mut data = json!({"table_hashes": ["DD5B5EDFBB69FEED", "C13DF45E3492CA0C"],
                              "unique": {YAO_SOURCE: "Combine!"}});
        assert_eq!(admit_tables(&mut data).unwrap(), 2);
        assert_eq!(apply(&mut data, "en").unwrap(), 3);
        assert_eq!(apply(&mut data, "en").unwrap(), 0);
        assert_eq!(
            apply(&mut json!({"table_hashes": ["DD5B5EDFBB69FEED"]}), "id").unwrap(),
            1
        );
    }
}
