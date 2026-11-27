//! The PC launcher's file list: `wxq_patch.launcher_metadata` (`stage_local_file_list`,
//! `local_file_list_mismatches`), ported from the bytecode (ADR-003).
//!
//! The launcher lists every file it installed with its size in `LocalFileList.json`. The engine never
//! writes the live list (ADR-0011 in `docs/adr/`): it stages a copy with the sizes the staged files
//! will have, and `commit` swaps it in with them. Entries are matched by their name with `/` as `\`,
//! leading separators dropped and casefolded (`_name_key`).

use std::path::{Path, PathBuf};

use serde_json::{Map, Value};

use crate::pyos::{self, Layout};
use crate::scan::PyError;

/// `launcher_metadata.LOCAL_FILE_LIST`.
pub const LOCAL_FILE_LIST: &str = "LocalFileList.json";

/// `_name_key`.
fn name_key(value: &str) -> String {
    pyos::casefold(value.replace('/', "\\").trim_start_matches('\\'))
}

fn value_error(message: String) -> PyError {
    PyError::new("ValueError", message)
}

/// `_load_entries`: the list, each entry a dict with a string `file` and an int `file_size`.
fn load_entries(path: &Path) -> Result<Vec<Value>, PyError> {
    let shown = path.display();
    let value = match pyos::read_json(path, true) {
        Ok(value) => value,
        Err(error) if error.class == "JSONDecodeError" || is_os(&error) => {
            return Err(value_error(format!("Invalid launcher file list: {shown}")));
        }
        Err(error) => return Err(error),
    };
    let Value::Array(entries) = value else {
        return Err(value_error(format!(
            "Launcher file list is not an array: {shown}"
        )));
    };
    for item in &entries {
        let file_ok =
            matches!(item, Value::Object(map) if matches!(map.get("file"), Some(Value::String(_))));
        if !file_ok {
            return Err(value_error(format!(
                "Launcher file list has an invalid entry: {shown}"
            )));
        }
        if !item.get("file_size").is_some_and(pyos::is_int) {
            return Err(value_error(format!(
                "Launcher file list has an invalid size: {shown}"
            )));
        }
    }
    Ok(entries)
}

fn is_os(error: &PyError) -> bool {
    error.class.ends_with("Error")
        && matches!(
            error.class,
            "OSError"
                | "FileNotFoundError"
                | "PermissionError"
                | "FileExistsError"
                | "NotADirectoryError"
                | "IsADirectoryError"
                | "BlockingIOError"
                | "ChildProcessError"
                | "BrokenPipeError"
        )
}

fn entry_file(item: &Value) -> &str {
    item.get("file").and_then(Value::as_str).unwrap_or_default()
}

fn entry_size(item: &Value) -> Value {
    item.get("file_size").cloned().unwrap_or(Value::Null)
}

/// `entry['file_size'] == size`, where a bool compares as the int it is in Python.
fn same_size(value: &Value, size: u64) -> bool {
    match value {
        Value::Bool(flag) => u64::from(*flag) == size,
        Value::Number(number) => number.as_u64() == Some(size),
        _ => false,
    }
}

fn change(file: &str, before: Value, after: Value) -> Value {
    Value::Object(pyos::object([
        ("file", Value::String(file.to_owned())),
        ("before", before),
        ("after", after),
    ]))
}

/// `{_name_key(item['file']): item for item in entries}` as indexes into `entries`.
fn by_name(entries: &[Value]) -> indexmap::IndexMap<String, usize> {
    let mut map = indexmap::IndexMap::new();
    for (index, item) in entries.iter().enumerate() {
        map.insert(name_key(entry_file(item)), index);
    }
    map
}

/// `stage_local_file_list(game, staged_files, output)`: the list with each staged file's size, a
/// removed file's entry dropped and a new file's added, written to `output` when anything changed.
pub fn stage_local_file_list(
    game: &Path,
    staged_files: &[(String, Option<PathBuf>)],
    output: &Path,
) -> Result<Map<String, Value>, PyError> {
    let source = game.join(LOCAL_FILE_LIST);
    let mut entries = load_entries(&source)?;
    let mut names = by_name(&entries);
    let mut updates = Vec::new();
    for (relative, staged) in staged_files {
        let key = name_key(relative);
        let found = names.get(&key).copied();
        let Some(staged) = staged else {
            let Some(index) = found else {
                return Err(value_error(format!(
                    "Launcher file list contains no {relative} to remove"
                )));
            };
            let item = entries[index].clone();
            updates.push(change(entry_file(&item), entry_size(&item), Value::Null));
            // `entries.remove(item)` drops the first entry equal to it.
            let first = entries.iter().position(|e| *e == item).unwrap_or(index);
            entries.remove(first);
            names.shift_remove(&key);
            for slot in names.values_mut() {
                if *slot > first {
                    *slot -= 1;
                }
            }
            continue;
        };
        let size = pyos::size(staged)?;
        match found {
            None => {
                let file = relative
                    .replace('/', "\\")
                    .trim_start_matches('\\')
                    .to_owned();
                entries.push(Value::Object(pyos::object([
                    ("file", Value::String(file.clone())),
                    ("file_size", Value::from(size)),
                ])));
                names.insert(key, entries.len() - 1);
                updates.push(change(&file, Value::Null, Value::from(size)));
            }
            Some(index) => {
                let before = entry_size(&entries[index]);
                if !same_size(&before, size) {
                    let file = entry_file(&entries[index]).to_owned();
                    updates.push(change(&file, before, Value::from(size)));
                    if let Value::Object(map) = &mut entries[index] {
                        map.insert("file_size".to_owned(), Value::from(size));
                    }
                }
            }
        }
    }
    if updates.is_empty() {
        return Ok(pyos::object([
            ("updated", Value::Bool(false)),
            ("path", pyos::path_value(&source)),
            ("changes", Value::Array(Vec::new())),
        ]));
    }
    if let Some(parent) = output.parent() {
        pyos::mkdir(parent, true)?;
    }
    pyos::write_text(output, &pyos::dumps(&Value::Array(entries), Layout::Inline))?;
    Ok(pyos::object([
        ("updated", Value::Bool(true)),
        ("path", pyos::path_value(output)),
        ("changes", Value::Array(updates)),
    ]))
}

/// `local_file_list_mismatches(source, staged_files)`: the list's entries, and each staged file
/// whose size the list does not record.
pub fn local_file_list_mismatches(
    source: &Path,
    staged_files: &[(String, Option<PathBuf>)],
) -> Result<(Vec<Value>, Vec<Value>), PyError> {
    let entries = load_entries(source)?;
    let names = by_name(&entries);
    let mut updates = Vec::new();
    for (relative, staged) in staged_files {
        let Some(&index) = names.get(&name_key(relative)) else {
            return Err(value_error(format!(
                "Launcher file list is missing {relative}"
            )));
        };
        let item = &entries[index];
        let Some(staged) = staged else {
            updates.push(change(entry_file(item), entry_size(item), Value::Null));
            continue;
        };
        let size = pyos::size(staged)?;
        if !same_size(&entry_size(item), size) {
            updates.push(change(
                entry_file(item),
                entry_size(item),
                Value::from(size),
            ));
        }
    }
    Ok((entries, updates))
}
