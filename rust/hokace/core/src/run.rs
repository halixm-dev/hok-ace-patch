//! The PC engine's entry point: `wxq_patch.adaptive.run` and `_run`, ported from the bytecode
//! (ADR-003).
//!
//! `run(action, game, assets, work)` scans the installation, stages each package with
//! replacements, stages the package-hash metadata and the launcher's file list for what changed,
//! and on `install` commits it all as one transaction (`crate::transaction`). `status` and `stage`
//! report without writing the game; `restore` puts back the originals of the newest install still
//! live.
//!
//! What the port does not own goes through `RunHost`: the scan (whose catalog edits the PC edition
//! hooks in Python), the DLL-backed package staging and hash queries, the receipts root (which
//! `engine_hooks` moves into the work folder) and the running-game check.

use std::path::{Path, PathBuf};
use std::time::Instant;

use indexmap::IndexMap;
use serde_json::{Map, Value};

use crate::catalog::py_repr;
use crate::launcher::{self, LOCAL_FILE_LIST};
use crate::pyos;
use crate::scan::PyError;
use crate::transaction::{self, Change, MutationLock};

/// One package `scan` found replacements for: `(package, replacements, per_asset)`, the parts
/// `_run` reads.
#[derive(Debug, Clone)]
pub struct RunPlan<R> {
    pub package_id: String,
    pub package_dir: PathBuf,
    pub index_path: PathBuf,
    pub shard_paths: Vec<PathBuf>,
    pub replacements: R,
}

/// What `scan(game, assets, work, materialize=...)` returns.
#[derive(Debug, Clone)]
pub struct RunScan<R> {
    pub plans: Vec<RunPlan<R>>,
    /// `str(path.relative_to(game))` to its SHA-256.
    pub fingerprints: IndexMap<String, String>,
    pub counts: Map<String, Value>,
    pub skipped: Value,
}

/// The calls `_run` makes that the port does not own.
pub trait RunHost {
    /// What `scan` hands back for `stage_unity_package` to stage.
    type Replacements;

    /// `receipt_root(game)`, for the resolved game.
    fn receipt_root(&mut self, game: &Path) -> PathBuf;
    /// `_assert_game_stopped()`.
    fn assert_game_stopped(&mut self) -> Result<(), PyError>;
    /// `scan(game, assets, work, materialize=...)`.
    fn scan(
        &mut self,
        game: &Path,
        assets: &Path,
        work: &Path,
        materialize: bool,
    ) -> Result<RunScan<Self::Replacements>, PyError>;
    /// `stage_unity_package(game, replacements, stage, source_package_dir=...,
    /// global_donations=True, verify_all_unrelated=False, source_hashes=...)`.
    fn stage_unity_package(
        &mut self,
        game: &Path,
        replacements: &Self::Replacements,
        stage: &Path,
        source_package_dir: &Path,
        source_hashes: &IndexMap<String, String>,
    ) -> Result<Value, PyError>;
    /// `query_package_hash(game, package_dir)`.
    fn query_package_hash(&mut self, game: &Path, package_dir: &Path) -> Result<Value, PyError>;
    /// `stage_package_hash_metadata_batch(game, package_hashes, output)`.
    fn stage_package_hash_metadata_batch(
        &mut self,
        game: &Path,
        package_hashes: &Map<String, Value>,
        output: &Path,
    ) -> Result<Value, PyError>;
}

/// A staging step's report, and the change that installs what it staged when anything differs.
type Staged<T> = (Option<T>, Option<Change>);

fn runtime(message: impl Into<String>) -> PyError {
    PyError::new("RuntimeError", message)
}

/// `adaptive.run(action, game, assets, work)`: `_run`, under the installation's mutation lock for
/// `install` and `restore`.
pub fn run<H: RunHost>(
    action: &str,
    game: &Path,
    assets: &Path,
    work: &Path,
    host: &mut H,
) -> Result<Map<String, Value>, PyError> {
    if matches!(action, "install" | "restore") {
        let root = host.receipt_root(&pyos::resolve(game));
        let _lock = MutationLock::acquire(&root)?;
        return run_unlocked(action, game, assets, work, host);
    }
    run_unlocked(action, game, assets, work, host)
}

/// `_matching_package_hash_targets(game)`: the package folders of the files a complete install
/// left live.
fn matching_package_hash_targets(
    game: &Path,
    root: &Path,
) -> Result<IndexMap<String, PathBuf>, PyError> {
    let mut targets = IndexMap::new();
    for (relative, _) in transaction::matching_install_files(game, root)? {
        let replaced = relative.replace('\\', "/");
        let parts: Vec<&str> = replaced.split('/').collect();
        if parts.len() < 5 {
            continue;
        }
        let head: Vec<String> = parts[..3].iter().map(|p| pyos::casefold(p)).collect();
        if head != ["wxq_data", "package", "builtin"] {
            continue;
        }
        let name = parts[3];
        if name == "0" || !pyos::is_ascii_decimal(name) {
            continue;
        }
        let package_dir = game
            .join("WXQ_Data")
            .join("Package")
            .join("builtin")
            .join(name);
        if !pyos::is_dir(&package_dir)? {
            continue;
        }
        targets.insert(name.to_owned(), package_dir);
    }
    Ok(targets)
}

/// `_stage_package_hashes(game, package_dirs, work)`: the internal index with each package's
/// hash, and the change that installs it when it differs.
fn stage_package_hashes<H: RunHost>(
    game: &Path,
    package_dirs: &IndexMap<String, PathBuf>,
    work: &Path,
    host: &mut H,
) -> Result<Staged<Value>, PyError> {
    if package_dirs.is_empty() {
        return Ok((None, None));
    }
    let mut sorted: Vec<(&String, &PathBuf)> = package_dirs.iter().collect();
    sorted.sort_by(|a, b| a.0.cmp(b.0));
    let mut hashes = Map::new();
    for (name, dir) in sorted {
        hashes.insert(name.clone(), host.query_package_hash(game, dir)?);
    }
    let staged = work.join("staged").join("package-metadata").join("0.db");
    let result = host.stage_package_hash_metadata_batch(game, &hashes, &staged)?;
    if !pyos::truthy(pyos::subscript(&result, "updated")?) {
        return Ok((Some(result), None));
    }
    let index = transaction::internal_index();
    let before = pyos::sha256_file(&game.join(&index))?;
    let change = Change {
        relative: index.display().to_string(),
        staged: Some(staged),
        before: Value::String(before),
    };
    Ok((Some(result), Some(change)))
}

/// `_stage_launcher_manifest(game, work, changes, include_receipts=...)`: the launcher list with
/// the staged sizes, and the change that installs it when it differs.
fn stage_launcher_manifest(
    game: &Path,
    root: &Path,
    work: &Path,
    changes: &[Change],
    include_receipts: bool,
) -> Result<Staged<Map<String, Value>>, PyError> {
    let mut pairs: Vec<(String, Option<PathBuf>)> = changes
        .iter()
        .map(|c| (c.relative.clone(), c.staged.clone()))
        .collect();
    if include_receipts {
        let existing: Vec<String> = pairs.iter().map(|(r, _)| r.clone()).collect();
        for (relative, live) in transaction::matching_install_files(game, root)? {
            if !existing.contains(&relative) {
                pairs.push((relative, Some(live)));
            }
        }
    }
    if pairs.is_empty() {
        return Ok((None, None));
    }
    let output = work.join("staged").join(LOCAL_FILE_LIST);
    let result = launcher::stage_local_file_list(game, &pairs, &output)?;
    if !pyos::truthy(&result["updated"]) {
        return Ok((Some(result), None));
    }
    let staged = PathBuf::from(pyos::py_str(&result["path"]));
    let before = pyos::sha256_file(&game.join(LOCAL_FILE_LIST))?;
    let change = Change {
        relative: LOCAL_FILE_LIST.to_owned(),
        staged: Some(staged),
        before: Value::String(before),
    };
    Ok((Some(result), Some(change)))
}

fn merge_cleanup(report: &mut Map<String, Value>, extra: &Map<String, Value>) {
    if let Some(Value::Object(cleanup)) = report.get_mut("cleanup") {
        transaction::merge_watchdog_cleanup(cleanup, extra);
    }
}

fn update(report: &mut Map<String, Value>, pairs: &[(&str, Value)]) {
    for (key, value) in pairs {
        report.insert((*key).to_owned(), value.clone());
    }
}

fn count(counts: &Map<String, Value>, key: &str) -> Value {
    counts.get(key).cloned().unwrap_or(Value::from(0))
}

fn idle_state(counts: &Map<String, Value>) -> Value {
    let english = counts.get("already_english").is_some_and(pyos::truthy);
    Value::String(if english { "current" } else { "unsupported" }.to_owned())
}

const NO_NEW: &str = "No safe new replacements found. Unknown Chinese text is preserved.";

fn py_len(value: &Value) -> Result<usize, PyError> {
    match value {
        Value::Array(items) => Ok(items.len()),
        Value::Object(map) => Ok(map.len()),
        Value::String(text) => Ok(text.chars().count()),
        other => Err(PyError::new(
            "TypeError",
            format!("object of type '{}' has no len()", pyos::type_name(other)),
        )),
    }
}

fn source_read_fallbacks(stage: &Value) -> Result<usize, PyError> {
    let verification = pyos::get(stage, "native_verification")?
        .cloned()
        .unwrap_or(Value::Object(Map::new()));
    let fallbacks = pyos::get(&verification, "source_read_fallbacks")?
        .cloned()
        .unwrap_or(Value::Array(Vec::new()));
    py_len(&fallbacks)
}

fn key_error(key: &str) -> PyError {
    PyError::new("KeyError", py_repr(key))
}

fn run_restore(
    game: &Path,
    root: &Path,
    recovered: usize,
    cleanup: Map<String, Value>,
) -> Result<Map<String, Value>, PyError> {
    let items = transaction::matching_restore_items(game, root)?;
    if items.is_empty() {
        if recovered > 0 {
            return Ok(pyos::object([
                ("state", Value::from("clean")),
                (
                    "message",
                    Value::from(
                        "Interrupted operation recovered; previous files restored and verified.",
                    ),
                ),
                ("restore_available", Value::Bool(false)),
                ("cleanup", Value::Object(cleanup)),
            ]));
        }
        return Err(runtime(
            "No matching restore backup. Updated game files will not be overwritten.",
        ));
    }
    let mut changes = Vec::new();
    let mut staged_hashes: IndexMap<String, Value> = IndexMap::new();
    for (path, item) in &items {
        let relative = pyos::subscript(item, "relative")?;
        let before = pyos::get_or_null(item, "before")?;
        if before.is_null() {
            changes.push(Change {
                relative: pyos::py_str(relative),
                staged: None,
                before: pyos::get_or_null(item, "after")?,
            });
            continue;
        }
        let parent = path.parent().map(Path::to_path_buf).unwrap_or_default();
        let original = transaction::safe_path(&parent.join("originals"), relative)?;
        if Value::String(pyos::sha256_file(&original)?) != *pyos::subscript(item, "before")? {
            return Err(runtime("Restore backup verification failed"));
        }
        let relative = pyos::py_str(relative);
        changes.push(Change {
            relative: relative.clone(),
            staged: Some(original),
            before: pyos::subscript(item, "after")?.clone(),
        });
        staged_hashes.insert(relative, pyos::subscript(item, "before")?.clone());
    }
    transaction::commit(game, root, &changes, "restore", None, Some(&staged_hashes))?;
    let mut cleanup = cleanup;
    transaction::merge_watchdog_cleanup(&mut cleanup, &transaction::clear_watchdog_state(game)?);
    Ok(pyos::object([
        ("state", Value::from("clean")),
        (
            "message",
            Value::from("Saved originals restored and verified."),
        ),
        ("restore_available", Value::Bool(false)),
        ("cleanup", Value::Object(cleanup)),
    ]))
}

/// `adaptive._run(action, game, assets, work)`.
fn run_unlocked<H: RunHost>(
    action: &str,
    game: &Path,
    assets: &Path,
    work: &Path,
    host: &mut H,
) -> Result<Map<String, Value>, PyError> {
    let start = Instant::now();
    let game = pyos::resolve(game);
    let game = game.as_path();
    let root = host.receipt_root(game);
    let mut recovered = 0;
    let mut cleanup = None;
    if matches!(action, "install" | "restore") {
        host.assert_game_stopped()?;
        recovered = transaction::recover_pending(game, &root)?;
        cleanup = Some(transaction::prune_stale_state(game, &root)?);
    }
    if action == "restore" {
        return run_restore(game, &root, recovered, cleanup.unwrap_or_default());
    }
    let scan = host.scan(game, assets, work, action != "status")?;
    let counts = scan.counts.clone();
    let restore_available =
        transaction::pending_recovery(&root)? || transaction::find_restore(game, &root)?.is_some();
    let mut report = pyos::object([
        ("counts", Value::Object(counts.clone())),
        ("skipped", scan.skipped.clone()),
        ("restore_available", Value::Bool(restore_available)),
    ]);
    if let Some(cleanup) = cleanup {
        report.insert("cleanup".to_owned(), Value::Object(cleanup));
    }
    let mut stages: Vec<Value> = Vec::new();
    let mut staged_run = false;
    if scan.plans.is_empty() {
        let mut launcher_manifest: Option<Map<String, Value>> = None;
        if action == "status" {
            let receipt_files = transaction::matching_install_files(game, &root)?;
            if !receipt_files.is_empty() {
                let pairs: Vec<(String, Option<PathBuf>)> = receipt_files
                    .into_iter()
                    .map(|(r, live)| (r, Some(live)))
                    .collect();
                let (_, updates) =
                    launcher::local_file_list_mismatches(&game.join(LOCAL_FILE_LIST), &pairs)?;
                let manifest = pyos::object([
                    ("updated", Value::Bool(!updates.is_empty())),
                    ("changes", Value::Array(updates)),
                ]);
                report.insert(
                    "launcher_manifest".to_owned(),
                    Value::Object(manifest.clone()),
                );
                launcher_manifest = Some(manifest);
            }
        }
        if action == "install" {
            let mut changes = Vec::new();
            let targets = matching_package_hash_targets(game, &root)?;
            let (package_metadata, metadata_change) =
                stage_package_hashes(game, &targets, work, host)?;
            changes.extend(metadata_change);
            let (manifest, manifest_change) =
                stage_launcher_manifest(game, &root, work, &changes, true)?;
            changes.extend(manifest_change);
            if changes.is_empty() {
                update(
                    &mut report,
                    &[
                        ("state", idle_state(&counts)),
                        ("message", Value::from(NO_NEW)),
                    ],
                );
            } else {
                host.assert_game_stopped()?;
                transaction::commit(game, &root, &changes, "install", None, None)?;
                merge_cleanup(&mut report, &transaction::clear_watchdog_state(game)?);
                report.insert(
                    "launcher_manifest".to_owned(),
                    manifest.map_or(Value::Null, Value::Object),
                );
                if let Some(metadata) = package_metadata {
                    report.insert("package_metadata".to_owned(), metadata);
                }
                update(
                    &mut report,
                    &[
                        ("state", Value::from("current")),
                        ("restore_available", Value::Bool(true)),
                        (
                            "message",
                            Value::from(
                                "Installed package metadata repaired; translated files were already installed.",
                            ),
                        ),
                    ],
                );
            }
        } else {
            let drift = launcher_manifest
                .as_ref()
                .is_some_and(|m| pyos::truthy(&m["updated"]));
            let has_new = counts.get("translated").is_some_and(pyos::truthy)
                || counts.get("graphics").is_some_and(pyos::truthy);
            let state = if drift || (action == "status" && has_new) {
                Value::from("clean")
            } else {
                idle_state(&counts)
            };
            let message = if drift {
                "English files are installed, but launcher file-size metadata needs repair."
            } else {
                NO_NEW
            };
            update(
                &mut report,
                &[("state", state), ("message", Value::from(message))],
            );
        }
    } else if action == "status" {
        update(
            &mut report,
            &[
                ("state", Value::from("clean")),
                (
                    "message",
                    Value::from("Known translations found in the current files."),
                ),
            ],
        );
    } else {
        staged_run = true;
        let mut changes: Vec<Change> = Vec::new();
        let mut staged_hashes: IndexMap<String, Value> = IndexMap::new();
        let mut package_hash_targets: IndexMap<String, PathBuf> = IndexMap::new();
        for plan in &scan.plans {
            let stage = work.join("staged").join(&plan.package_id);
            let mut source_hashes = IndexMap::new();
            for path in std::iter::once(&plan.index_path).chain(&plan.shard_paths) {
                let name = path
                    .file_name()
                    .map(|n| n.to_string_lossy().into_owned())
                    .unwrap_or_default();
                let relative = pyos::relative_to(path, game)?;
                let hash = scan
                    .fingerprints
                    .get(&relative)
                    .ok_or_else(|| key_error(&relative))?;
                source_hashes.insert(name, hash.clone());
            }
            let staged_report = host.stage_unity_package(
                game,
                &plan.replacements,
                &stage,
                &plan.package_dir,
                &source_hashes,
            )?;
            stages.push(staged_report.clone());
            let mut staged_names: Vec<Value> = Vec::new();
            for item in pyos::iterate(pyos::subscript(&staged_report, "files")?)? {
                let name = pyos::subscript(&item, "name")?.clone();
                if !staged_names.contains(&name) {
                    staged_names.push(name.clone());
                }
                let name = name_text(&name)?;
                let source = plan.package_dir.join(&name);
                let relative = pyos::relative_to(&source, game)?;
                let expected = scan.fingerprints.get(&relative).cloned();
                let source_hash = pyos::get_or_null(&item, "source_sha256")?;
                let staged = stage.join(&plan.package_id).join(&name);
                let Some(expected) = expected else {
                    if pyos::exists(&source)? || !source_hash.is_null() {
                        return Err(runtime("Staged package reported an unknown source file"));
                    }
                    changes.push(Change {
                        relative,
                        staged: Some(staged),
                        before: Value::Null,
                    });
                    continue;
                };
                let expected = Value::String(expected);
                if source_hash != expected {
                    return Err(runtime("Game updated between scanning and staging"));
                }
                let staged_sha = pyos::subscript(&item, "staged_sha256")?;
                if source_hash == *staged_sha {
                    continue;
                }
                let staged_sha = staged_sha.clone();
                changes.push(Change {
                    relative: relative.clone(),
                    staged: Some(staged),
                    before: expected,
                });
                staged_hashes.insert(relative, staged_sha);
            }
            let removed = pyos::get(&staged_report, "removed_files")?
                .cloned()
                .unwrap_or(Value::Array(Vec::new()));
            for name in pyos::iterate(&removed)? {
                if staged_names.contains(&name) {
                    return Err(runtime(format!(
                        "Staged package reports both present and removed: {}",
                        pyos::py_str(&name)
                    )));
                }
                let source = plan.package_dir.join(name_text(&name)?);
                let relative = pyos::relative_to(&source, game)?;
                let expected = scan.fingerprints.get(&relative).cloned();
                let current = match &expected {
                    Some(expected) if pyos::is_file(&source)? => {
                        pyos::sha256_file(&source)? == *expected
                    }
                    _ => false,
                };
                if !current {
                    return Err(runtime("Game updated before removing a package shard"));
                }
                changes.push(Change {
                    relative,
                    staged: None,
                    before: Value::String(expected.unwrap_or_default()),
                });
            }
            package_hash_targets.insert(plan.package_id.clone(), stage.join(&plan.package_id));
        }
        let (package_metadata, metadata_change) =
            stage_package_hashes(game, &package_hash_targets, work, host)?;
        changes.extend(metadata_change);
        let (manifest, manifest_change) =
            stage_launcher_manifest(game, &root, work, &changes, false)?;
        changes.extend(manifest_change);
        report.insert(
            "launcher_manifest".to_owned(),
            manifest.map_or(Value::Null, Value::Object),
        );
        if let Some(metadata) = package_metadata {
            report.insert("package_metadata".to_owned(), metadata);
        }
        report.insert("stages".to_owned(), Value::Array(stages.clone()));
        if action == "install" {
            host.assert_game_stopped()?;
            transaction::commit(game, &root, &changes, "install", None, Some(&staged_hashes))?;
            merge_cleanup(&mut report, &transaction::clear_watchdog_state(game)?);
            update(
                &mut report,
                &[
                    ("state", Value::from("current")),
                    ("restore_available", Value::Bool(true)),
                    (
                        "message",
                        Value::from("English installed and verified. Unknown text was preserved."),
                    ),
                ],
            );
        } else {
            update(
                &mut report,
                &[
                    ("state", Value::from("clean")),
                    (
                        "message",
                        Value::from("Offline stage verified; game files unchanged."),
                    ),
                ],
            );
        }
    }
    let mut message = pyos::py_str(&report["message"]);
    if staged_run {
        let mut fallback_count = 0;
        for stage in &stages {
            fallback_count += source_read_fallbacks(stage)?;
        }
        if fallback_count > 0 {
            message.push_str(&format!(
                "\nIndependent package verification passed for {fallback_count} assets that the native reader could not open in the originals."
            ));
        }
    }
    message.push_str(&format!(
        "\n{} known strings; {} unknown left Chinese; {} graphics; {} strings skipped for capacity.",
        pyos::thousands(&count(&counts, "translated")),
        pyos::thousands(&count(&counts, "unknown")),
        pyos::py_str(&count(&counts, "graphics")),
        pyos::thousands(&count(&counts, "capacity_skipped")),
    ));
    report.insert("message".to_owned(), Value::String(message));
    let seconds = (start.elapsed().as_secs_f64() * 1000.0).round() / 1000.0;
    report.insert("seconds".to_owned(), Value::from(seconds));
    Ok(report)
}

/// A staged report's file name, which the runtime joins onto a path.
fn name_text(name: &Value) -> Result<String, PyError> {
    match name {
        Value::String(text) => Ok(text.clone()),
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
