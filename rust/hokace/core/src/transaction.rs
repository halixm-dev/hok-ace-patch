//! The PC engine's transactions: `wxq_patch.adaptive`'s receipts, `commit`, `recover`, the stale
//! state prune and the launcher's Watchdog cleanup, ported from the bytecode (ADR-003).
//!
//! A transaction is a receipt folder under the game's receipts root, named
//! `<time_ns>-<8 hex>`, holding `receipt.json` (`schema`, `state`, `action`, `files`) and the
//! `originals` it backed up. `commit` writes the receipt as `preparing`, backs the originals up
//! (hard links where the volume allows them), marks it `pending`, swaps each file through
//! `<name>.ace-new` and `<name>.ace-old`, verifies, and marks it `complete`; any failure in between
//! rolls back through `recover` and is raised again. A process that dies mid-swap leaves a
//! `pending` receipt for `recover_pending` to roll back on the next run.
//!
//! Every exception the runtime raises keeps its class and message; an `OSError` is worded as
//! `pyos::os_error` words it. The port's own: `shutil.rmtree` removes read-only files here, where
//! CPython 3.12 on Windows would stop at the first one.

use std::fs::{self, File, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use indexmap::IndexMap;
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};

use crate::pyos::{self, Call, Layout};
use crate::scan::PyError;

/// `adaptive.INTERNAL_INDEX`, as `str()` gives it on this platform.
pub fn internal_index() -> PathBuf {
    ["WXQ_Data", "Package", "builtin", "0", "0.db"]
        .iter()
        .collect()
}

/// `adaptive.WATCHDOG_DB_NAMES`.
pub const WATCHDOG_DB_NAMES: [&str; 4] = [
    "BrokenList.db",
    "PatchList.db",
    "StorageStatus.db",
    "History.db",
];

const OLD: &str = ".ace-old";
const NEW: &str = ".ace-new";
const ENGINE_TEMPORARY: &str = ".wxq-engpatch.tmp";
const RECEIPT: &str = "receipt.json";

fn runtime(message: impl Into<String>) -> PyError {
    PyError::new("RuntimeError", message)
}

/// The engine's identity for an installation: `sha256(str(game.resolve()).casefold())[:24]`.
pub fn game_identity(game: &Path) -> String {
    let text = pyos::casefold(&pyos::resolve(game).display().to_string());
    let digest = Sha256::digest(text.as_bytes());
    digest
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect::<String>()[..24]
        .to_owned()
}

/// `adaptive.receipt_root` as the runtime defines it (the upstream patcher's folder); the PC
/// edition replaces it with `<work>\pc\receipts\<identity>` (`engine_hooks._receipt_root`).
pub fn default_receipt_root(game: &Path) -> PathBuf {
    let base = std::env::var_os("LOCALAPPDATA")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            std::env::var_os(if cfg!(windows) { "USERPROFILE" } else { "HOME" })
                .map(PathBuf::from)
                .unwrap_or_default()
        });
    base.join("HoK Ace English Patch")
        .join("adaptive")
        .join(game_identity(game))
}

/// `adaptive.write_json`: `<path>` with the `.pending` suffix written, synced and moved over it.
pub fn write_json(path: &Path, value: &Value) -> Result<(), PyError> {
    let temporary = path.with_extension("pending");
    let mut file =
        File::create(&temporary).map_err(|e| pyos::os_error(&e, Call::Crt, &[&temporary]))?;
    let fail = |e: io::Error| pyos::os_error(&e, Call::Crt, &[&temporary]);
    file.write_all(&pyos::text_bytes(&pyos::dumps(value, Layout::Indent2)))
        .map_err(fail)?;
    file.flush().map_err(fail)?;
    file.sync_all().map_err(fail)?;
    drop(file);
    pyos::replace(&temporary, path)
}

/// `root / relative` for a value read from a receipt.
fn join(root: &Path, relative: &Value) -> Result<PathBuf, PyError> {
    match relative {
        Value::String(text) => Ok(root.join(text)),
        other => Err(PyError::new(
            "TypeError",
            format!(
                "unsupported operand type(s) for /: '{}' and '{}'",
                if cfg!(windows) {
                    "WindowsPath"
                } else {
                    "PosixPath"
                },
                pyos::type_name(other)
            ),
        )),
    }
}

/// `adaptive.safe_path(root, relative)`: the resolved path, which must lie strictly inside `root`.
pub fn safe_path(root: &Path, relative: &Value) -> Result<PathBuf, PyError> {
    let path = pyos::resolve(&join(root, relative)?);
    let base = pyos::resolve(root);
    if !pyos::is_relative_to(&path, &base) || pyos::same_path(&path, &base) {
        return Err(PyError::new("ValueError", "Invalid receipt path"));
    }
    Ok(path)
}

fn safe(root: &Path, relative: &str) -> Result<PathBuf, PyError> {
    safe_path(root, &Value::String(relative.to_owned()))
}

/// `adaptive._matches_hash(path, expected)`: absent when `expected` is `None`, else a file with
/// that SHA-256.
pub fn matches_hash(path: &Path, expected: &Value) -> Result<bool, PyError> {
    if expected.is_null() {
        return Ok(!pyos::exists(path)?);
    }
    if !pyos::is_file(path)? {
        return Ok(false);
    }
    let digest = pyos::sha256_file(path)?;
    Ok(matches!(expected, Value::String(s) if *s == digest))
}

fn with_suffix(live: &Path, suffix: &str) -> PathBuf {
    let name = live
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_default();
    live.with_file_name(format!("{name}{suffix}"))
}

/// `adaptive.recover(game, folder, receipt)`: put every file of an interrupted transaction back
/// as it was before, verify it, and mark the receipt `rolled_back`.
pub fn recover(game: &Path, folder: &Path, receipt: &mut Value) -> Result<(), PyError> {
    let changed = "Recovery refused because a game update changed an interrupted transaction";
    let items = pyos::iterate(pyos::subscript(receipt, "files")?)?;
    for item in &items {
        let live = safe_path(game, pyos::subscript(item, "relative")?)?;
        let old = with_suffix(&live, OLD);
        let new = with_suffix(&live, NEW);
        let before = pyos::get_or_null(item, "before")?;
        let after = pyos::get_or_null(item, "after")?;
        if before.is_null() {
            if pyos::exists(&old)? || (pyos::exists(&live)? && !matches_hash(&live, &after)?) {
                return Err(runtime(changed));
            }
        } else {
            if pyos::exists(&old)? && !matches_hash(&old, &before)? {
                return Err(runtime(changed));
            }
            if !pyos::exists(&old)?
                && !matches_hash(&live, &before)?
                && !matches_hash(&live, &after)?
            {
                return Err(runtime(
                    "Interrupted operation has conflicting live files; originals were retained",
                ));
            }
            if pyos::exists(&old)?
                && pyos::exists(&live)?
                && !matches_hash(&live, &before)?
                && !matches_hash(&live, &after)?
            {
                return Err(runtime(changed));
            }
        }
        if !pyos::exists(&new)? {
            continue;
        }
        if after.is_null() || !matches_hash(&new, &after)? {
            return Err(runtime(
                "Recovery refused because a staged transaction file is corrupt",
            ));
        }
    }
    for item in items.iter().rev() {
        let live = safe_path(game, pyos::subscript(item, "relative")?)?;
        let old = with_suffix(&live, OLD);
        let new = with_suffix(&live, NEW);
        if pyos::exists(&old)? {
            pyos::replace(&old, &live)?;
        } else if pyos::get_or_null(item, "before")?.is_null() && pyos::exists(&live)? {
            if !matches_hash(&live, &pyos::get_or_null(item, "after")?)? {
                return Err(runtime("Recovery verification failed"));
            }
            pyos::unlink(&live)?;
        }
        if pyos::exists(&new)? {
            pyos::unlink(&new)?;
        }
        if !matches_hash(&live, &pyos::get_or_null(item, "before")?)? {
            return Err(runtime("Recovery verification failed"));
        }
    }
    set_state(receipt, "rolled_back")?;
    write_json(&folder.join(RECEIPT), receipt)
}

fn set_state(receipt: &mut Value, state: &str) -> Result<(), PyError> {
    match receipt {
        Value::Object(map) => {
            map.insert("state".to_owned(), Value::String(state.to_owned()));
            Ok(())
        }
        other => Err(PyError::new(
            "TypeError",
            format!(
                "'{}' object does not support item assignment",
                pyos::type_name(other)
            ),
        )),
    }
}

/// `root.glob('*/receipt.json')`, sorted (or reversed) when the runtime sorts it.
fn receipts(root: &Path, order: Option<bool>) -> Vec<PathBuf> {
    let mut found = pyos::glob_children(root, RECEIPT);
    if let Some(reverse) = order {
        pyos::sort_paths(&mut found, reverse);
    }
    found
}

fn folder_of(path: &Path) -> PathBuf {
    path.parent().map(Path::to_path_buf).unwrap_or_default()
}

/// `adaptive.recover_pending(game)`: roll back every `pending` transaction, drop each `complete`
/// one's leftover `.ace-old` backups, and count the rollbacks.
pub fn recover_pending(game: &Path, root: &Path) -> Result<usize, PyError> {
    let mut recovered = 0;
    if !pyos::exists(root)? {
        return Ok(0);
    }
    for path in receipts(root, Some(false)) {
        let mut receipt = pyos::read_json(&path, false)?;
        let state = pyos::subscript(&receipt, "state")?.clone();
        if state == "pending" {
            recover(game, &folder_of(&path), &mut receipt)?;
            recovered += 1;
            continue;
        }
        if state != "complete" {
            continue;
        }
        for item in pyos::iterate(pyos::subscript(&receipt, "files")?)? {
            let live = safe_path(game, pyos::subscript(&item, "relative")?)?;
            let old = with_suffix(&live, OLD);
            if !pyos::exists(&old)? || pyos::get_or_null(&item, "before")?.is_null() {
                continue;
            }
            if matches_hash(&old, pyos::subscript(&item, "before")?)? {
                pyos::unlink(&old)?;
            }
        }
    }
    Ok(recovered)
}

/// `adaptive.pending_recovery(game)`: whether a transaction is still `pending`.
pub fn pending_recovery(root: &Path) -> Result<bool, PyError> {
    if !pyos::exists(root)? {
        return Ok(false);
    }
    for path in receipts(root, None) {
        let receipt = pyos::read_json(&path, false)?;
        if *pyos::subscript(&receipt, "state")? == "pending" {
            return Ok(true);
        }
    }
    Ok(false)
}

fn is_caught(error: &PyError, classes: &[&str]) -> bool {
    classes.contains(&error.class)
        || (classes.contains(&"OSError") && is_os_class(error.class))
        || (classes.contains(&"ValueError")
            && matches!(error.class, "JSONDecodeError" | "UnicodeDecodeError"))
}

fn is_os_class(class: &str) -> bool {
    matches!(
        class,
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

/// `adaptive._receipt_matches_live(game, receipt)`: a complete install whose every file is live.
fn receipt_matches_live(game: &Path, receipt: &Value) -> Result<bool, PyError> {
    if pyos::get_or_null(receipt, "state")? != "complete"
        || pyos::get_or_null(receipt, "action")? != "install"
    {
        return Ok(false);
    }
    let items = pyos::get_or_null(receipt, "files")?;
    if !pyos::truthy(&items) {
        return Ok(false);
    }
    let check = || -> Result<bool, PyError> {
        for item in pyos::iterate(&items)? {
            let live = safe_path(game, pyos::subscript(&item, "relative")?)?;
            if !matches_hash(&live, &pyos::get_or_null(&item, "after")?)? {
                return Ok(false);
            }
        }
        Ok(true)
    };
    match check() {
        Err(error) if is_caught(&error, &["KeyError", "OSError", "TypeError", "ValueError"]) => {
            Ok(false)
        }
        other => other,
    }
}

/// `adaptive._watchdog_dirs(game)`: the launcher's Watchdog folders, each once.
fn watchdog_dirs(game: &Path) -> Result<Vec<PathBuf>, PyError> {
    let candidates = [
        game.join("QtsDataFolder")
            .join("QtsVFSCache")
            .join("Watchdog"),
        game.join("WXQ_Data")
            .join("QtsDataFolder")
            .join("QtsVFSCache")
            .join("Watchdog"),
        game.join("WXQ_Data").join("QtsVFSCache").join("Watchdog"),
    ];
    let mut seen = Vec::new();
    let mut result = Vec::new();
    for path in candidates {
        let key = if pyos::exists(&path)? {
            pyos::resolve(&path).display().to_string()
        } else {
            path.display().to_string()
        };
        if seen.contains(&key) {
            continue;
        }
        seen.push(key);
        result.push(path);
    }
    Ok(result)
}

fn bump(report: &mut Map<String, Value>, key: &str, by: u64) {
    let current = report.get(key).and_then(Value::as_u64).unwrap_or(0);
    report.insert(key.to_owned(), Value::from(current + by));
}

fn push_error(report: &mut Map<String, Value>, text: String) {
    if let Some(Value::Array(errors)) = report.get_mut("errors") {
        errors.push(Value::String(text));
    }
}

fn watchdog_report() -> Map<String, Value> {
    pyos::object([
        ("directories", Value::from(0)),
        ("removed_files", Value::from(0)),
        ("removed_directories", Value::from(0)),
        ("removed_databases", Value::from(0)),
        ("freed_bytes", Value::from(0)),
        ("errors", Value::Array(Vec::new())),
    ])
}

fn remove_child(child: &Path) -> Result<Option<(u64, bool)>, PyError> {
    if pyos::is_file(child)? || pyos::is_symlink(child)? {
        let size = pyos::size(child)?;
        pyos::make_writable(child)?;
        pyos::unlink(child)?;
        return Ok(Some((size, false)));
    }
    if pyos::is_dir(child)? {
        pyos::make_writable(child)?;
        fs::remove_dir_all(child).map_err(|e| pyos::os_error(&e, Call::Win, &[child]))?;
        return Ok(Some((0, true)));
    }
    Ok(None)
}

/// `adaptive.clear_watchdog_state(game)`: empty the launcher's Watchdog folders, whose records of
/// the files it saw would make it re-download the patched packages.
pub fn clear_watchdog_state(game: &Path) -> Result<Map<String, Value>, PyError> {
    let mut report = watchdog_report();
    for watchdog in watchdog_dirs(game)? {
        if !pyos::is_dir(&watchdog)? {
            continue;
        }
        bump(&mut report, "directories", 1);
        let shown = watchdog.display().to_string();
        if let Err(error) = pyos::make_writable(&watchdog) {
            if !is_os_class(error.class) {
                return Err(error);
            }
            push_error(&mut report, format!("{shown}: {}", error.message));
        }
        let children = match pyos::iterdir(&watchdog) {
            Ok(children) => children,
            Err(error) if is_os_class(error.class) => {
                push_error(&mut report, format!("{shown}: {}", error.message));
                continue;
            }
            Err(error) => return Err(error),
        };
        for child in children {
            let (size, removed_directory) = match remove_child(&child) {
                Ok(Some(done)) => done,
                Ok(None) => continue,
                Err(error) if is_os_class(error.class) => {
                    push_error(
                        &mut report,
                        format!("{}: {}", child.display(), error.message),
                    );
                    continue;
                }
                Err(error) => return Err(error),
            };
            bump(
                &mut report,
                if removed_directory {
                    "removed_directories"
                } else {
                    "removed_files"
                },
                1,
            );
            let name = child
                .file_name()
                .map(|n| n.to_string_lossy().into_owned())
                .unwrap_or_default();
            if !removed_directory && WATCHDOG_DB_NAMES.contains(&name.as_str()) {
                bump(&mut report, "removed_databases", 1);
            }
            bump(&mut report, "freed_bytes", size);
        }
        if fs::read_dir(&watchdog).is_ok_and(|rest| rest.count() == 0) {
            let _ = fs::remove_dir(&watchdog);
        }
    }
    Ok(report)
}

fn add_value(current: &mut Map<String, Value>, key: &str, extra: &Map<String, Value>) {
    let total = current.get(key).and_then(Value::as_u64).unwrap_or(0)
        + extra.get(key).and_then(Value::as_u64).unwrap_or(0);
    current.insert(key.to_owned(), Value::from(total));
}

/// `adaptive._merge_watchdog_cleanup(cleanup, extra)`: add a later Watchdog cleanup to the
/// report's `cleanup['watchdog']`.
pub fn merge_watchdog_cleanup(cleanup: &mut Map<String, Value>, extra: &Map<String, Value>) {
    let current = cleanup
        .entry("watchdog")
        .or_insert_with(|| Value::Object(watchdog_report()));
    let Value::Object(current) = current else {
        return;
    };
    for key in [
        "directories",
        "removed_files",
        "removed_directories",
        "removed_databases",
        "freed_bytes",
    ] {
        add_value(current, key, extra);
    }
    if let (Some(Value::Array(errors)), Some(Value::Array(more))) =
        (current.get_mut("errors"), extra.get("errors"))
    {
        errors.extend(more.iter().cloned());
    }
}

/// `adaptive.prune_stale_state(game)`: drop every finished receipt whose files are no longer
/// live, every leftover transaction or engine temporary beside a file a receipt names, and the
/// Watchdog state.
pub fn prune_stale_state(game: &Path, root: &Path) -> Result<Map<String, Value>, PyError> {
    let mut result = pyos::object([
        ("removed_receipts", Value::from(0)),
        ("freed_bytes", Value::from(0)),
        ("removed_temporary_files", Value::from(0)),
        ("freed_temporary_bytes", Value::from(0)),
        ("errors", Value::Array(Vec::new())),
    ]);
    // A set of resolved paths: `WindowsPath` equality ignores case.
    let mut tracked: IndexMap<String, PathBuf> = IndexMap::new();
    if pyos::is_dir(root)? {
        let mut folders = pyos::iterdir(root)?;
        pyos::sort_paths(&mut folders, false);
        for folder in folders {
            if !pyos::is_dir(&folder)? {
                continue;
            }
            let receipt_path = folder.join(RECEIPT);
            if !pyos::is_file(&receipt_path)? {
                continue;
            }
            let receipt = match pyos::read_json(&receipt_path, false) {
                Ok(receipt) => receipt,
                Err(error)
                    if is_caught(&error, &["OSError", "UnicodeDecodeError", "ValueError"]) =>
                {
                    continue;
                }
                Err(error) => return Err(error),
            };
            if pyos::get_or_null(&receipt, "state")? == "pending" {
                continue;
            }
            let files = pyos::get_or_null(&receipt, "files")?;
            let files = if pyos::truthy(&files) {
                files
            } else {
                Value::Array(Vec::new())
            };
            for item in pyos::iterate(&files)? {
                let relative = match &item {
                    Value::Object(map) => map.get("relative").cloned().unwrap_or(Value::Null),
                    _ => Value::Null,
                };
                if !relative.is_string() {
                    continue;
                }
                match safe_path(game, &relative) {
                    Ok(path) => {
                        tracked.entry(pyos::normcase(&path)).or_insert(path);
                    }
                    Err(error) if error.class == "ValueError" => {}
                    Err(error) => return Err(error),
                }
            }
            if receipt_matches_live(game, &receipt)? {
                continue;
            }
            let state = pyos::get_or_null(&receipt, "state")?;
            if state != "complete" && state != "rolled_back" {
                continue;
            }
            let removed = pyos::tree_size(&folder).and_then(|size| {
                fs::remove_dir_all(&folder)
                    .map(|()| size)
                    .map_err(|e| pyos::os_error(&e, Call::Win, &[&folder]))
            });
            match removed {
                Ok(size) => {
                    bump(&mut result, "removed_receipts", 1);
                    bump(&mut result, "freed_bytes", size);
                }
                Err(error) if is_os_class(error.class) => {
                    let name = folder
                        .file_name()
                        .map(|n| n.to_string_lossy().into_owned())
                        .unwrap_or_default();
                    push_error(&mut result, format!("{name}: {}", error.message));
                }
                Err(error) => return Err(error),
            }
        }
    }
    let remove_temporary =
        |temporary: &Path, result: &mut Map<String, Value>| -> Result<(), PyError> {
            if !pyos::is_file(temporary)? {
                return Ok(());
            }
            match pyos::size(temporary).and_then(|size| pyos::unlink(temporary).map(|()| size)) {
                Ok(size) => {
                    bump(result, "removed_temporary_files", 1);
                    bump(result, "freed_temporary_bytes", size);
                    Ok(())
                }
                Err(error) if is_os_class(error.class) => {
                    push_error(
                        result,
                        format!("{}: {}", temporary.display(), error.message),
                    );
                    Ok(())
                }
                Err(error) => Err(error),
            }
        };
    for live in tracked.values() {
        for suffix in [OLD, NEW, ENGINE_TEMPORARY] {
            remove_temporary(&with_suffix(live, suffix), &mut result)?;
        }
    }
    let builtin = game.join("WXQ_Data").join("Package").join("builtin");
    if pyos::is_dir(&builtin)? {
        for temporary in pyos::glob_suffix(&builtin, ENGINE_TEMPORARY) {
            remove_temporary(&temporary, &mut result)?;
        }
    }
    result.insert(
        "watchdog".to_owned(),
        Value::Object(clear_watchdog_state(game)?),
    );
    Ok(result)
}

/// The complete install receipts under `root`, in the order `glob` lists them.
fn install_receipts(root: &Path, order: Option<bool>) -> Result<Vec<(PathBuf, Value)>, PyError> {
    let mut out = Vec::new();
    for path in receipts(root, order) {
        let receipt = pyos::read_json(&path, false)?;
        if pyos::get_or_null(&receipt, "state")? != "complete"
            || pyos::get_or_null(&receipt, "action")? != "install"
        {
            continue;
        }
        out.push((path, receipt));
    }
    Ok(out)
}

/// `adaptive._matching_install_files(game)`: each file a complete install wrote that is still
/// live with what it wrote, sorted by its relative path (the launcher list left out).
pub fn matching_install_files(game: &Path, root: &Path) -> Result<Vec<(String, PathBuf)>, PyError> {
    if !pyos::exists(root)? {
        return Ok(Vec::new());
    }
    let mut candidates: IndexMap<String, Vec<String>> = IndexMap::new();
    for (_, receipt) in install_receipts(root, None)? {
        let files = pyos::get(&receipt, "files")?
            .cloned()
            .unwrap_or(Value::Array(Vec::new()));
        for item in pyos::iterate(&files)? {
            let Some(Value::String(relative)) = pyos::get(&item, "relative")? else {
                continue;
            };
            if relative == crate::launcher::LOCAL_FILE_LIST {
                continue;
            }
            let Some(Value::String(after)) = pyos::get(&item, "after")? else {
                continue;
            };
            let afters = candidates.entry(relative.clone()).or_default();
            if !afters.contains(after) {
                afters.push(after.clone());
            }
        }
    }
    let mut matches = Vec::new();
    for (relative, afters) in candidates {
        let live = safe(game, &relative)?;
        if !pyos::is_file(&live)? {
            continue;
        }
        if afters.contains(&pyos::sha256_file(&live)?) {
            matches.push((relative, live));
        }
    }
    matches.sort_by(|a, b| a.0.cmp(&b.0));
    Ok(matches)
}

/// `adaptive._matching_restore_items(game)`: for each file the newest still-live install wrote,
/// that receipt and its item, sorted by relative path.
pub fn matching_restore_items(game: &Path, root: &Path) -> Result<Vec<(PathBuf, Value)>, PyError> {
    if !pyos::exists(root)? {
        return Ok(Vec::new());
    }
    let mut found = Vec::new();
    for (path, receipt) in install_receipts(root, Some(true))? {
        let items = pyos::get(&receipt, "files")?
            .cloned()
            .unwrap_or(Value::Array(Vec::new()));
        if !pyos::truthy(&items) {
            continue;
        }
        let items = pyos::iterate(&items)?;
        for item in &items {
            pyos::subscript(item, "relative")?;
        }
        found.push((path, items));
    }
    let mut candidates: IndexMap<String, (PathBuf, Value)> = IndexMap::new();
    for (path, items) in found {
        let mut stale = false;
        for item in &items {
            let live = safe_path(game, pyos::subscript(item, "relative")?)?;
            if !matches_hash(&live, &pyos::get_or_null(item, "after")?)? {
                stale = true;
                break;
            }
        }
        if stale {
            continue;
        }
        for item in items {
            let key = pyos::py_str(pyos::subscript(&item, "relative")?);
            candidates.entry(key).or_insert((path.clone(), item));
        }
    }
    let mut values: Vec<(PathBuf, Value)> = candidates.into_values().collect();
    values.sort_by_cached_key(|(_, item)| pyos::py_str(&item["relative"]));
    Ok(values)
}

/// `adaptive.find_restore(game)`: the newest complete install whose every file is still live.
pub fn find_restore(game: &Path, root: &Path) -> Result<Option<(PathBuf, Value)>, PyError> {
    if !pyos::exists(root)? {
        return Ok(None);
    }
    for path in receipts(root, Some(true)) {
        let receipt = pyos::read_json(&path, false)?;
        if *pyos::subscript(&receipt, "state")? != "complete"
            || *pyos::subscript(&receipt, "action")? != "install"
        {
            continue;
        }
        let mut live_all = true;
        for item in pyos::iterate(pyos::subscript(&receipt, "files")?)? {
            let live = safe_path(game, pyos::subscript(&item, "relative")?)?;
            if !matches_hash(&live, &pyos::get_or_null(&item, "after")?)? {
                live_all = false;
                break;
            }
        }
        if live_all {
            return Ok(Some((path, receipt)));
        }
    }
    Ok(None)
}

/// One file of a transaction: `(relative, staged, before)`, where `staged` is `None` to remove the
/// file and `before` is the live file's SHA-256, `None` when it must not exist yet.
#[derive(Debug, Clone)]
pub struct Change {
    pub relative: String,
    pub staged: Option<PathBuf>,
    pub before: Value,
}

/// The Win32 codes whose errno makes `commit` copy rather than hard-link (`EXDEV`, `EACCES`,
/// `EPERM`, `EOPNOTSUPP`), plus `ERROR_NOT_SAME_DEVICE`.
fn copy_instead(error: &io::Error) -> bool {
    let errno = pyos::errno(error);
    if cfg!(windows) {
        matches!(errno, Some(18 | 13 | 1 | 10045)) || error.raw_os_error() == Some(17)
    } else {
        matches!(errno, Some(18 | 13 | 1 | 95))
    }
}

fn link_or_else(
    source: &Path,
    target: &Path,
    copy: impl FnOnce() -> Result<(), PyError>,
) -> Result<bool, PyError> {
    match fs::hard_link(source, target) {
        Ok(()) => Ok(true),
        Err(error) if copy_instead(&error) => copy().map(|()| false),
        Err(error) => Err(pyos::os_error(&error, Call::Win, &[source, target])),
    }
}

/// A receipt folder's name: `f"{time.time_ns()}-{uuid.uuid4().hex[:8]}"`.
fn folder_name() -> String {
    use std::hash::{BuildHasher, Hasher};
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or_default();
    let mut hasher = std::collections::hash_map::RandomState::new().build_hasher();
    hasher.write_u128(nanos);
    format!("{nanos}-{:08x}", hasher.finish() as u32)
}

fn swap(
    game: &Path,
    items: &[Value],
    changes: &[Change],
    fail_after: Option<usize>,
    receipt: &mut Value,
    folder: &Path,
) -> Result<(), PyError> {
    for (item, change) in items.iter().zip(changes) {
        let Some(staged) = &change.staged else {
            continue;
        };
        let live = safe(game, &change.relative)?;
        let new = with_suffix(&live, NEW);
        let linked = link_or_else(staged, &new, || {
            let fail_new = |e: io::Error| pyos::os_error(&e, Call::Crt, &[&new]);
            let mut out = OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(&new)
                .map_err(fail_new)?;
            let mut source =
                File::open(staged).map_err(|e| pyos::os_error(&e, Call::Crt, &[staged]))?;
            io::copy(&mut source, &mut out).map_err(fail_new)?;
            out.flush().map_err(fail_new)?;
            out.sync_all().map_err(fail_new)
        })?;
        if !linked && Value::String(pyos::sha256_file(&new)?) != item["after"] {
            return Err(runtime("Staged copy verification failed"));
        }
    }
    for (index, item) in items.iter().enumerate() {
        let relative = pyos::py_str(&item["relative"]);
        let live = safe(game, &relative)?;
        if !matches_hash(&live, &item["before"])? {
            return Err(runtime("Game file changed during commit"));
        }
        if item["before"].is_null() {
            pyos::replace(&with_suffix(&live, NEW), &live)?;
        } else {
            pyos::replace(&live, &with_suffix(&live, OLD))?;
            if !item["after"].is_null() {
                pyos::replace(&with_suffix(&live, NEW), &live)?;
            }
        }
        if fail_after == Some(index + 1) {
            return Err(runtime("Injected transaction failure"));
        }
    }
    for item in items {
        let live = safe(game, &pyos::py_str(&item["relative"]))?;
        if !matches_hash(&live, &item["after"])? {
            return Err(runtime("Installed file verification failed"));
        }
    }
    set_state(receipt, "complete")?;
    write_json(&folder.join(RECEIPT), receipt)
}

/// `adaptive.commit(game, changes, action=..., fail_after=..., staged_hashes=...)`: apply the
/// changes as one transaction and return its receipt folder.
pub fn commit(
    game: &Path,
    root: &Path,
    changes: &[Change],
    action: &str,
    fail_after: Option<usize>,
    staged_hashes: Option<&IndexMap<String, Value>>,
) -> Result<PathBuf, PyError> {
    let folder = root.join(folder_name());
    let mut items = Vec::new();
    let mut seen: Vec<&str> = Vec::new();
    for change in changes {
        let live = safe(game, &change.relative)?;
        if seen.contains(&change.relative.as_str()) {
            return Err(runtime(format!(
                "Duplicate transaction path: {}",
                change.relative
            )));
        }
        seen.push(&change.relative);
        if change.before.is_null() {
            if pyos::exists(&live)? {
                return Err(runtime("New game file already exists; no files changed"));
            }
        } else if !matches_hash(&live, &change.before)? {
            return Err(runtime("Game updated before commit; no files changed"));
        }
        for suffix in [OLD, NEW] {
            if pyos::exists(&with_suffix(&live, suffix))? {
                return Err(runtime("Pending recovery files found; no files changed"));
            }
        }
        let after = match &change.staged {
            None if change.before.is_null() => {
                return Err(runtime(
                    "Transaction cannot remove a file that is already absent",
                ));
            }
            None => Value::Null,
            Some(staged) => {
                if !pyos::is_file(staged)? {
                    return Err(PyError::new(
                        "FileNotFoundError",
                        staged.display().to_string(),
                    ));
                }
                match staged_hashes.and_then(|h| h.get(&change.relative)) {
                    Some(hash) => hash.clone(),
                    None => Value::String(pyos::sha256_file(staged)?),
                }
            }
        };
        items.push(Value::Object(pyos::object([
            ("relative", Value::String(change.relative.clone())),
            ("before", change.before.clone()),
            ("after", after),
        ])));
    }
    pyos::mkdir(&folder, false)?;
    let mut receipt = Value::Object(pyos::object([
        ("schema", Value::from(1)),
        ("state", Value::String("preparing".to_owned())),
        ("action", Value::String(action.to_owned())),
        ("files", Value::Array(items.clone())),
    ]));
    write_json(&folder.join(RECEIPT), &receipt)?;
    for item in &items {
        if item["before"].is_null() {
            continue;
        }
        let relative = pyos::py_str(&item["relative"]);
        let live = safe(game, &relative)?;
        let backup = safe(&folder.join("originals"), &relative)?;
        if let Some(parent) = backup.parent() {
            pyos::mkdir(parent, true)?;
        }
        let linked = link_or_else(&live, &backup, || {
            fs::copy(&live, &backup)
                .map(|_| ())
                .map_err(|e| pyos::os_error(&e, Call::Win, &[&live, &backup]))
        })?;
        if !linked && Value::String(pyos::sha256_file(&backup)?) != item["before"] {
            return Err(runtime("Backup verification failed; no game files changed"));
        }
    }
    set_state(&mut receipt, "pending")?;
    write_json(&folder.join(RECEIPT), &receipt)?;
    if let Err(error) = swap(game, &items, changes, fail_after, &mut receipt, &folder) {
        recover(game, &folder, &mut receipt)?;
        return Err(error);
    }
    for item in &items {
        let old = with_suffix(&safe(game, &pyos::py_str(&item["relative"]))?, OLD);
        if pyos::exists(&old)? {
            pyos::unlink(&old)?;
        }
    }
    Ok(folder)
}

/// `adaptive.mutation_lock(game)`, held while the returned guard lives: an exclusive lock on
/// `<root>\operation.lock`, so two patch operations never mutate one installation at once.
pub struct MutationLock {
    file: File,
}

impl MutationLock {
    /// Take the lock, or fail as the runtime does when another operation holds it.
    pub fn acquire(root: &Path) -> Result<Self, PyError> {
        pyos::mkdir(root, true)?;
        let path = root.join("operation.lock");
        let fail = |e: io::Error| pyos::os_error(&e, Call::Crt, &[&path]);
        let mut file = OpenOptions::new()
            .read(true)
            .append(true)
            .create(true)
            .open(&path)
            .map_err(fail)?;
        if file.metadata().map_err(fail)?.len() == 0 {
            file.write_all(b"0").map_err(fail)?;
            file.flush().map_err(fail)?;
        }
        if file.try_lock().is_err() {
            return Err(runtime(
                "Another patch operation is using this installation",
            ));
        }
        Ok(Self { file })
    }
}

impl Drop for MutationLock {
    fn drop(&mut self) {
        let _ = self.file.unlock();
    }
}
