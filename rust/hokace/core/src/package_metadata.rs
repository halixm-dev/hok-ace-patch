//! The PC edition's package hashes: `wxq_patch.package_metadata`.
//!
//! [`find_package_hash_entry`] reads a package's record from the internal index,
//! [`stage_package_hash_metadata_batch`] rewrites hashes into a staged copy of it, and
//! [`query_package_hash`] asks the game's own QtsVFS for a staged package's hash (ADR-021) through
//! [`Loader`] and [`QtsVfs`], which `hokace-qtsvfs` implements over the installed DLLs.
//!
//! The port's own: the temporary folder is removed with its errors raised, where the runtime's
//! `TemporaryDirectory` retries; a hash given as a float or a bool is refused as a `TypeError`.

use std::collections::BTreeSet;
use std::fs;
use std::path::{Path, PathBuf};

use serde_json::{Map, Value, json};
use sha2::{Digest, Sha256};

use crate::catalog::py_repr;
use crate::pyos::{self, Call};
use crate::scan::PyError;
use crate::transaction::internal_index;

const PACKAGE_MARKER: &[u8] = b"QTSF_PACKAGE";
const MAX_PACKAGE_NAME: usize = 64;

#[derive(Debug, PartialEq, Eq)]
pub struct Entry<'a> {
    pub name: &'a str,
    pub offset: usize,
    pub hash_offset: usize,
    pub next_offset: usize,
    pub hash: u64,
}

#[derive(Debug, PartialEq, Eq)]
pub enum LookupError {
    EmptyName,
    MissingMarker,
    MissingTable,
    EntryCount(usize),
}

pub fn record(data: &[u8], offset: usize) -> Option<Entry<'_>> {
    let (size, body) = data.get(offset..)?.split_at_checked(4)?;
    let size = u32::from_le_bytes(size.try_into().ok()?) as usize;
    if !(1..=MAX_PACKAGE_NAME).contains(&size) {
        return None;
    }
    let padded_size = size.next_multiple_of(4);
    let (name, rest) = body.split_at_checked(size)?;
    let (padding, rest) = rest.split_at_checked(padded_size - size)?;
    if padding.iter().any(|byte| *byte != 0)
        || name
            .iter()
            .any(|byte| !byte.is_ascii() || matches!(byte, b'\t'..=b'\r' | 0x1c..=b' '))
    {
        return None;
    }
    let hash = u64::from_le_bytes(rest.get(..8)?.try_into().ok()?);
    let hash_offset = offset + 4 + padded_size;
    Some(Entry {
        name: std::str::from_utf8(name).ok()?,
        offset,
        hash_offset,
        next_offset: hash_offset + 8,
        hash,
    })
}

/// Finds the unique record, scanning byte by byte as the engine does.
pub fn find_package_hash_entry<'a>(data: &'a [u8], name: &str) -> Result<Entry<'a>, LookupError> {
    if name.is_empty() {
        return Err(LookupError::EmptyName);
    }
    let marker = data
        .windows(PACKAGE_MARKER.len())
        .position(|window| window == PACKAGE_MARKER)
        .ok_or(LookupError::MissingMarker)?
        + PACKAGE_MARKER.len();
    let start = data[marker..]
        .windows(4)
        .position(|window| window == b"INGQ")
        .ok_or(LookupError::MissingTable)?
        + marker
        + 4;
    let mut matches = (start..data.len().saturating_sub(16))
        .filter_map(|offset| record(data, offset))
        .filter(|entry| entry.name == name);
    let first = matches.next().ok_or(LookupError::EntryCount(0))?;
    let extra = matches.count();
    if extra != 0 {
        return Err(LookupError::EntryCount(extra + 1));
    }
    Ok(first)
}

impl LookupError {
    /// The runtime's `ValueError` text for a lookup of `name` in `source`.
    pub fn message(&self, source: &Path, name: &str) -> String {
        match self {
            Self::EmptyName => "Package name is empty".into(),
            Self::MissingMarker => {
                format!(
                    "QtsVFS package metadata is missing from {}",
                    source.display()
                )
            }
            Self::MissingTable => format!(
                "QtsVFS package metadata table is missing from {}",
                source.display()
            ),
            Self::EntryCount(count) => format!(
                "QtsVFS package metadata has {count} entries for {}",
                py_repr(name)
            ),
        }
    }
}

/// A hash map value as the runtime's `0 <= package_hash <= 2**64 - 1` check meets it.
fn package_hash(value: &Value) -> Result<u64, PyError> {
    if let Some(hash) = value.as_u64() {
        return Ok(hash);
    }
    // A Python int past `u64` reaches JSON as a whole number serde reads as a float.
    let outside = value.as_i64().is_some()
        || value
            .as_f64()
            .is_some_and(|f| value.is_f64() && f.fract() == 0.0 && (f < 0.0 || f >= 2f64.powi(64)));
    if outside {
        return Err(PyError::value("Package hash is outside uint64 range"));
    }
    let class = match value {
        Value::Null => "NoneType",
        Value::String(_) => "str",
        Value::Array(_) => "list",
        Value::Object(_) => "dict",
        // `True`/`False` and floats compare in Python; the PC flow only passes integers.
        Value::Bool(_) | Value::Number(_) => {
            return Err(PyError::new(
                "TypeError",
                format!("package hash {value} is not an integer"),
            ));
        }
    };
    Err(PyError::new(
        "TypeError",
        format!("'<=' not supported between instances of 'int' and '{class}'"),
    ))
}

/// `package_metadata.stage_package_hash_metadata_batch(game, package_hashes, output)`: the
/// internal index with each named package's hash rewritten, written to `output` only when any
/// changes. Every byte the rewrite changes must lie inside the hash fields it rewrote: a new hash
/// that keeps one of the old hash's bytes in place is refused, as the runtime refuses it.
pub fn stage_package_hash_metadata_batch(
    game: &Path,
    package_hashes: &Map<String, Value>,
    output: &Path,
) -> Result<Value, PyError> {
    if package_hashes.is_empty() {
        return Err(PyError::value("Package hash map is empty"));
    }
    let mut hashes = Vec::with_capacity(package_hashes.len());
    for (name, value) in package_hashes {
        if name.is_empty() {
            return Err(PyError::value("Package name is empty"));
        }
        hashes.push((name.as_str(), package_hash(value)?));
    }
    hashes.sort_by(|a, b| a.0.cmp(b.0));
    let source = game.join(internal_index());
    let source_data = fs::read(&source).map_err(|e| pyos::os_error(&e, Call::Crt, &[&source]))?;
    let mut data = source_data.clone();
    let mut packages = Map::new();
    let mut changed_offsets = BTreeSet::new();
    for (name, after) in hashes {
        let entry = find_package_hash_entry(&source_data, name)
            .map_err(|error| PyError::value(error.message(&source, name)))?;
        packages.insert(
            name.to_owned(),
            json!({
                "before": entry.hash, "after": after,
                "offset": entry.offset, "hash_offset": entry.hash_offset,
            }),
        );
        if entry.hash != after {
            data[entry.hash_offset..entry.hash_offset + 8].copy_from_slice(&after.to_le_bytes());
            changed_offsets.extend(entry.hash_offset..entry.hash_offset + 8);
        }
    }
    let actual_changed: BTreeSet<usize> = source_data
        .iter()
        .zip(&data)
        .enumerate()
        .filter(|(_, (before, after))| before != after)
        .map(|(index, _)| index)
        .collect();
    if actual_changed != changed_offsets {
        return Err(PyError::value(
            "Package metadata update changed bytes outside hash fields",
        ));
    }
    let changes: Vec<Value> = packages
        .iter()
        .filter(|(_, item)| item["before"] != item["after"])
        .map(|(name, item)| {
            json!({
                "package": name, "offset": item["hash_offset"],
                "before": item["before"], "after": item["after"],
            })
        })
        .collect();
    let updated = !changes.is_empty();
    let mut result = pyos::object([
        ("updated", Value::Bool(updated)),
        (
            "path",
            pyos::path_value(if updated { output } else { &source }),
        ),
        ("packages", Value::Object(packages)),
        ("changes", Value::Array(changes)),
    ]);
    if updated {
        if let Some(parent) = output.parent() {
            pyos::mkdir(parent, true)?;
        }
        fs::write(output, &data).map_err(|e| pyos::os_error(&e, Call::Crt, &[output]))?;
        result.insert(
            "source_sha256".into(),
            Value::String(sha256_hex(&source_data)),
        );
        result.insert("staged_sha256".into(), Value::String(sha256_hex(&data)));
    }
    Ok(Value::Object(result))
}

/// `package_metadata.stage_package_hash_metadata(game, package_name, package_hash, output)`.
pub fn stage_package_hash_metadata(
    game: &Path,
    package_name: &str,
    package_hash: &Value,
    output: &Path,
) -> Result<Value, PyError> {
    let mut hashes = Map::new();
    hashes.insert(package_name.to_owned(), package_hash.clone());
    let Value::Object(mut result) = stage_package_hash_metadata_batch(game, &hashes, output)?
    else {
        unreachable!("the batch returns an object")
    };
    let item = result["packages"][package_name].clone();
    result.insert("package".into(), Value::from(package_name));
    result.insert("before".into(), item["before"].clone());
    result.insert("after".into(), item["after"].clone());
    result.insert("offset".into(), item["hash_offset"].clone());
    Ok(Value::Object(result))
}

fn sha256_hex(data: &[u8]) -> String {
    Sha256::digest(data)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

/// The QtsVFS calls `query_package_hash` makes, in the order the runtime binds them.
pub const QUERY_SYMBOLS: [&str; 11] = [
    "VFS_GetLastError",
    "VFS_CreateSystem",
    "VFS_CreatePackageDescription",
    "VFS_PackageDescriptionSetHasPrimePackge",
    "VFS_MountPackage",
    "VFS_QueryPackageInfo",
    "CSharp_new_QTSPatchInfo",
    "CSharp_delete_QTSPatchInfo",
    "CSharp_QTSPatchInfo_cur_package_hash_get",
    "VFS_ReleasePackageDescription",
    "VFS_DestorySystem",
];

/// `package_metadata.query_package_hash(game, package_dir)`: the hash the game's own QtsVFS gives
/// `package_dir` once mounted beside the internal package, both copied into a temporary folder.
/// The working folder is the DLL folder for the calls, as the runtime sets it.
pub fn query_package_hash<L: Loader>(
    loader: &mut L,
    game: &Path,
    package_dir: &Path,
) -> Result<u64, PyError> {
    let game = pyos::resolve(game);
    let package_dir = pyos::resolve(package_dir);
    let internal_dir = game
        .join("WXQ_Data")
        .join("Package")
        .join("builtin")
        .join("0");
    if !pyos::is_dir(&internal_dir)? {
        return Err(PyError::new(
            "FileNotFoundError",
            format!(
                "QtsVFS internal package is missing from {}",
                internal_dir.display()
            ),
        ));
    }
    let name = package_dir
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_default();
    if !pyos::is_dir(&package_dir)? || !pyos::is_ascii_decimal(&name) {
        return Err(PyError::value(format!(
            "Invalid QtsVFS package directory: {}",
            package_dir.display()
        )));
    }
    let root = std::env::temp_dir().join(format!("ace-package-hash-{}", &pyos::random_hex()[..8]));
    pyos::mkdir(&root, false)?;
    let result = query_in(loader, &game, &internal_dir, &package_dir, &name, &root);
    let cleanup = pyos::rmtree(&root);
    let hash = result?;
    cleanup?;
    Ok(hash)
}

fn query_in<L: Loader>(
    loader: &mut L,
    game: &Path,
    internal_dir: &Path,
    package_dir: &Path,
    name: &str,
    root: &Path,
) -> Result<u64, PyError> {
    pyos::copytree(internal_dir, &root.join("0"), false)?;
    pyos::copytree(package_dir, &root.join(name), false)?;
    let scratch = root.join("scratch");
    fs::create_dir(&scratch).map_err(|e| pyos::os_error(&e, Call::Win, &[&scratch]))?;
    let bin_dir = qtsvfs_bin_dir(game)?;
    let mut api = loader.load(&bin_dir)?;
    let old_cwd = std::env::current_dir().map_err(|e| pyos::os_error(&e, Call::Win, &[]))?;
    let system = format!("ace_query_{}", pyos::random_hex()).into_bytes();
    let mut handles = Vec::new();
    let mut info = 0;
    let result = (|| {
        std::env::set_current_dir(&bin_dir)
            .map_err(|e| pyos::os_error(&e, Call::Win, &[&bin_dir]))?;
        api.require(&QUERY_SYMBOLS)?;
        let root = path_bytes(root);
        let scratch = path_bytes(&scratch);
        if !api.create_system(&system, &root, &scratch) {
            return Err(runtime(format!(
                "QtsVFS system creation failed: {}",
                api.last_error()
            )));
        }
        for package in ["0", name] {
            let handle = api.describe(&system, package.as_bytes(), package == "0");
            if handle < 0 {
                return Err(runtime(format!(
                    "QtsVFS package description failed for {package}: {}",
                    api.last_error()
                )));
            }
            handles.push(handle);
            if !(api.set_prime(handle, true) && api.mount(handle)) {
                return Err(runtime(format!(
                    "QtsVFS mount failed for {package}: {}",
                    api.last_error()
                )));
            }
        }
        info = api.new_info();
        let last = handles[handles.len() - 1];
        if info == 0 || !api.query_info(last, info) {
            return Err(runtime(format!(
                "QtsVFS package hash query failed: {}",
                api.last_error()
            )));
        }
        Ok(api.info_hash(info))
    })();
    // The runtime's `finally`: each release is attempted, whatever failed before it.
    if info != 0 {
        api.delete_info(info);
    }
    for &handle in handles.iter().rev() {
        api.release(handle);
    }
    api.destroy(&system);
    let restored =
        std::env::set_current_dir(&old_cwd).map_err(|e| pyos::os_error(&e, Call::Win, &[&old_cwd]));
    drop(api);
    let hash = result?;
    restored?;
    Ok(hash)
}

fn runtime(message: String) -> PyError {
    PyError::new("RuntimeError", message)
}

/// `str(path).encode()`: the path's UTF-8 bytes, as the runtime hands them to QtsVFS.
pub fn path_bytes(path: &Path) -> Vec<u8> {
    path.display().to_string().into_bytes()
}

/// `installer._qtsvfs_bin_dir(game)`: the folder holding the game's `QtsVFS.dll` and `QtskDB.dll`.
pub fn qtsvfs_bin_dir(game: &Path) -> Result<PathBuf, PyError> {
    let path = game.join("WXQ_Data").join("Plugins").join("x86_64");
    if !pyos::is_file(&path.join("QtsVFS.dll"))? || !pyos::is_file(&path.join("QtskDB.dll"))? {
        return Err(PyError::new(
            "FileNotFoundError",
            format!("QtsVFS runtime was not found under {}", path.display()),
        ));
    }
    Ok(path)
}

/// Loads the game's QtsVFS (`installer._load_qtsvfs`): `QtskDB.dll`, then `QtsVFS.dll` from
/// `bin_dir`, each initializer that exists called once per load. The DLLs stay loaded.
pub trait Loader {
    type Api: QtsVfs;
    fn load(&mut self, bin_dir: &Path) -> Result<Self::Api, PyError>;
}

/// The QtsVFS entry points the runtime calls, with ctypes' argument types. A system and a
/// package are named by NUL-free byte strings; `info` and `file` are opaque, `0` for NULL.
pub trait QtsVfs {
    /// Fails with ctypes' `AttributeError` for the first of `symbols` the DLL lacks.
    fn require(&mut self, symbols: &[&str]) -> Result<(), PyError>;
    fn last_error(&mut self) -> i32;
    /// `VFS_CreateSystem(name, root, scratch, scratch)`.
    fn create_system(&mut self, system: &[u8], root: &[u8], scratch: &[u8]) -> bool;
    /// `VFS_CreatePackageDescription(system, package, internal)`.
    fn describe(&mut self, system: &[u8], package: &[u8], internal: bool) -> i32;
    /// `VFS_PackageDescriptionSetHasPrimePackge(handle, prime)`.
    fn set_prime(&mut self, handle: i32, prime: bool) -> bool;
    /// `VFS_MountPackage(handle, 0, 0)`.
    fn mount(&mut self, handle: i32) -> bool;
    /// `CSharp_new_QTSPatchInfo()`.
    fn new_info(&mut self) -> usize;
    /// `VFS_QueryPackageInfo(handle, 0, info)`.
    fn query_info(&mut self, handle: i32, info: usize) -> bool;
    /// `CSharp_QTSPatchInfo_cur_package_hash_get(info)`.
    fn info_hash(&mut self, info: usize) -> u64;
    /// `CSharp_delete_QTSPatchInfo(info)`.
    fn delete_info(&mut self, info: usize);
    /// `VFS_ReleasePackageDescription(handle)`.
    fn release(&mut self, handle: i32);
    /// `VFS_DestorySystem(system)`.
    fn destroy(&mut self, system: &[u8]);
    /// `VFS_GetFileLengthByHash(system, hash)`.
    fn file_length(&mut self, system: &[u8], hash: u64) -> u32;
    /// `VFS_OpenFileByHash(system, hash, b"rb")`.
    fn open_file(&mut self, system: &[u8], hash: u64) -> usize;
    /// `VFS_Read(buffer, 1, len(buffer), file)`.
    fn read(&mut self, buffer: &mut [u8], file: usize) -> u32;
    /// `VFS_CloseFile(file)`.
    fn close_file(&mut self, file: usize);
}
