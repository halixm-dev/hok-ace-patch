//! `wxq_patch.native_verify`: a staged PC package read back through the game's own QtsVFS, with an
//! independent structural check when QtsVFS cannot read an asset.
//!
//! [`verify_staged_package`] mounts the internal package and the staged package (and, to check
//! every unrelated asset, the source package) in their own QtsVFS systems, through [`Loader`]
//! (ADR-021). An asset QtsVFS will not open or read is a [`ReadError::Native`]: the first
//! unreadable source asset runs [`verify_structural`] over the whole package, and each is listed
//! in `source_read_fallbacks`.
//!
//! Every exception the runtime raises keeps its class and message; a staged asset QtsVFS cannot
//! read raises `NativeReadError` itself, since only the source read falls back.
//!
//! The port's own: a shard offset past 4 GiB is refused, and the runtime's systems, like
//! its, are never destroyed.

use std::collections::{BTreeMap, HashMap, HashSet};
use std::fs::{self, File};
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};

use serde_json::{Value, json};

use crate::package_metadata::{Loader, QtsVfs, path_bytes, qtsvfs_bin_dir};
use crate::pyos;
use crate::qts::{self, ChunkSlot};
use crate::scan::{self, Package, PyError, Slot};

/// The QtsVFS calls `verify_staged_package` makes, in the order the runtime binds them.
pub const VERIFY_SYMBOLS: [&str; 9] = [
    "VFS_GetLastError",
    "VFS_CreateSystem",
    "VFS_CreatePackageDescription",
    "VFS_PackageDescriptionSetHasPrimePackge",
    "VFS_MountPackage",
    "VFS_GetFileLengthByHash",
    "VFS_OpenFileByHash",
    "VFS_Read",
    "VFS_CloseFile",
];

const LEAF_TAG: u32 = 3 << 16;

fn runtime(message: impl Into<String>) -> PyError {
    PyError::new("RuntimeError", message)
}

/// Why an asset was not read: QtsVFS could not read it (`NativeReadError`), or anything else.
#[derive(Debug)]
pub enum ReadError {
    Native(String),
    Other(PyError),
}

impl From<PyError> for ReadError {
    fn from(error: PyError) -> Self {
        Self::Other(error)
    }
}

/// `struct.unpack_from('<I', data, offset)[0]`.
fn word(data: &[u8], offset: usize) -> Result<u32, PyError> {
    data.get(offset..offset + 4)
        .map(|b| u32::from_le_bytes([b[0], b[1], b[2], b[3]]))
        .ok_or_else(|| {
            PyError::new(
                "error",
                format!(
                    "unpack_from requires a buffer of at least {} bytes for unpacking 4 bytes at \
                     offset {offset} (actual buffer size is {})",
                    offset + 4,
                    data.len()
                ),
            )
        })
}

fn read_file(path: &Path) -> Result<Vec<u8>, PyError> {
    fs::read(path).map_err(|e| pyos::os_error(&e, pyos::Call::Crt, &[path]))
}

fn name_of(path: &Path) -> String {
    path.file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_default()
}

fn offset32(offset: u64) -> Result<u32, PyError> {
    u32::try_from(offset)
        .map_err(|_| PyError::value(format!("slot offset {offset} is past 4 GiB")))
}

/// `_verify_changed_positions(source, staged)`: each slot the staged shard adds is listed in
/// exactly two B-tree leaves, each run of positions sized as its leaf footer says, keyed by the
/// slot's own `hash1`.
pub fn verify_changed_positions(source: &Package, staged: &Package) -> Result<(), PyError> {
    for path in &staged.shard_paths {
        let shard = name_of(path);
        let before = scan::iter_chunk_slots(&source.package_dir.join(&shard), true)?;
        let after = scan::iter_chunk_slots(path, true)?;
        let identity = |s: &ChunkSlot| (s.slot_offset, s.hash1, s.file_hash, s.chunk_id);
        let existing: HashSet<_> = before.iter().map(identity).collect();
        let changed: Vec<&ChunkSlot> = after
            .iter()
            .filter(|s| !existing.contains(&identity(s)))
            .collect();
        if changed.is_empty() {
            continue;
        }
        let data = read_file(path)?;
        let positions: HashSet<u32> = after
            .iter()
            .map(|s| offset32(s.slot_offset))
            .collect::<Result<_, _>>()?;
        let wanted: Vec<u32> = changed
            .iter()
            .map(|s| offset32(s.slot_offset))
            .collect::<Result<_, _>>()?;
        let references = qts::find_position_references(&data, &positions, wanted);
        for slot in changed {
            let refs = &references[&offset32(slot.slot_offset)?];
            if refs.len() != 2 {
                return Err(runtime(format!(
                    "Structural lookup failed in {shard} at {}: expected two indexes",
                    slot.slot_offset
                )));
            }
            for &reference in refs {
                let mut start = reference;
                while start >= 4 && positions.contains(&word(&data, start - 4)?) {
                    start -= 4;
                }
                let mut end = reference + 4;
                while end + 4 <= data.len() && positions.contains(&word(&data, end)?) {
                    end += 4;
                }
                let footer = start + 4092 - 2040;
                let count = (end - start) / 4;
                let fits = footer + 4 <= data.len()
                    && count <= 510
                    && word(&data, footer)? == LEAF_TAG | count as u32
                    && word(&data, reference - 2040)? == (slot.hash1 & 0xFFFF_FFFF) as u32;
                if !fits {
                    return Err(runtime(format!(
                        "Structural lookup page/count mismatch in {shard} at {reference}"
                    )));
                }
            }
        }
    }
    Ok(())
}

/// `auxiliary_slots(package)`: per asset, its reserved-variant slots by chunk.
fn auxiliary_slots(package: &Package) -> Result<HashMap<u64, BTreeMap<u32, Slot>>, PyError> {
    let mut result: HashMap<u64, BTreeMap<u32, Slot>> = HashMap::new();
    for path in &package.shard_paths {
        for slot in scan::iter_chunk_slots(path, true)? {
            if slot.reserved != 1 {
                continue;
            }
            let chunks = result.entry(slot.file_hash).or_default();
            if chunks.contains_key(&slot.chunk_id) {
                return Err(runtime(format!(
                    "Ambiguous auxiliary chunks for {:016X}",
                    slot.file_hash
                )));
            }
            chunks.insert(
                slot.chunk_id,
                Slot {
                    shard_path: path.clone(),
                    slot,
                },
            );
        }
    }
    Ok(result)
}

fn contiguous(chunks: &BTreeMap<u32, Slot>) -> bool {
    chunks.keys().copied().eq(0..chunks.len() as u32)
}

/// An asset's chunks and its reserved-variant chunks, read off the shards.
type Content = (Vec<u8>, Vec<Vec<u8>>);

/// `extract(package, slots, auxiliary, index, h)` inside `_verify_structural`.
fn structural_extract(
    package: &Package,
    slots: &HashMap<u64, BTreeMap<u32, Slot>>,
    auxiliary: &HashMap<u64, BTreeMap<u32, Slot>>,
    index: &[u8],
    hash: u64,
) -> Result<Content, PyError> {
    let shown = package.package_dir.display();
    if let Some(chunks) = slots.get(&hash)
        && !chunks.is_empty()
        && !contiguous(chunks)
    {
        return Err(runtime(format!(
            "Structural chunks missing/noncontiguous in {shown} for {hash:016X}"
        )));
    }
    let raw = scan::extract(package, slots, hash)?;
    let empty = BTreeMap::new();
    let aux = auxiliary.get(&hash).unwrap_or(&empty);
    if !contiguous(aux) {
        return Err(runtime(format!(
            "Structural auxiliary chunks missing for {hash:016X}"
        )));
    }
    let entry = &package.entries[&hash];
    let mut extra = Vec::with_capacity(aux.len());
    for slot in aux.values() {
        let mut file = File::open(&slot.shard_path)
            .map_err(|e| pyos::os_error(&e, pyos::Call::Crt, &[&slot.shard_path]))?;
        let io = |e: std::io::Error| pyos::os_error(&e, pyos::Call::Crt, &[&slot.shard_path]);
        file.seek(SeekFrom::Start(slot.slot.payload_offset))
            .map_err(io)?;
        let mut payload = Vec::new();
        file.take(slot.slot.compressed_size.into())
            .read_to_end(&mut payload)
            .map_err(io)?;
        if payload.len() != slot.slot.compressed_size as usize {
            return Err(runtime(format!(
                "Structural auxiliary short read for {hash:016X}"
            )));
        }
        if entry.compression == 1 {
            let size = slot.slot.uncompressed_size as usize;
            payload = hokace_codecs::lz4::decompress(&payload, size).map_err(|_| {
                PyError::new(
                    "LZ4BlockError",
                    "Decompression failed: corrupt input or insufficient space in destination \
                     buffer",
                )
            })?;
            if payload.len() != size {
                return Err(runtime(format!(
                    "Structural auxiliary size mismatch for {hash:016X}"
                )));
            }
        }
        extra.push(payload);
    }
    let expected = word(index, entry.entry_offset as usize + 44)? as usize;
    let size = raw.len() + extra.iter().map(Vec::len).sum::<usize>();
    if size != expected {
        return Err(runtime(format!(
            "Structural asset length mismatch in {shown} for {hash:016X}: {size}/{expected}"
        )));
    }
    Ok((raw, extra))
}

/// `_verify_structural(source, staged, replacements)`: the staged package's index, shards and
/// every asset compared with the source's, read off disk without QtsVFS. Returns the asset count.
pub fn verify_structural(
    source: &Package,
    staged: &Package,
    replacements: &BTreeMap<u64, Vec<u8>>,
) -> Result<usize, PyError> {
    let keys = |p: &Package| p.entries.keys().copied().collect::<HashSet<u64>>();
    let source_keys = keys(source);
    if source_keys != keys(staged) || !replacements.keys().all(|h| source_keys.contains(h)) {
        return Err(runtime("Structural package index key set changed"));
    }
    let shards = |p: &Package| p.shard_paths.iter().map(|s| name_of(s)).collect::<HashSet<_>>();
    if shards(source) != shards(staged) {
        return Err(runtime("Structural package shard set changed"));
    }
    let source_slots = scan::stock_slot_map(source)?;
    let staged_slots = scan::stock_slot_map(staged)?;
    let source_index = read_file(&source.index_path)?;
    let staged_index = read_file(&staged.index_path)?;
    let source_aux = auxiliary_slots(source)?;
    let staged_aux = auxiliary_slots(staged)?;
    for (&hash, entry) in &source.entries {
        let staged_entry = &staged.entries[&hash];
        let before_shard = word(&source_index, entry.entry_offset as usize + 48)?;
        let after_shard = word(&staged_index, staged_entry.entry_offset as usize + 48)?;
        if before_shard != after_shard {
            return Err(runtime(format!(
                "Structural shard selector changed for {hash:016X}"
            )));
        }
        let replacement = replacements.get(&hash);
        if replacement.is_none() && staged_entry != entry {
            return Err(runtime(format!(
                "Structural unrelated index entry changed for {hash:016X}"
            )));
        }
        let original =
            structural_extract(source, &source_slots, &source_aux, &source_index, hash)?;
        let actual = structural_extract(staged, &staged_slots, &staged_aux, &staged_index, hash)?;
        let matches = match replacement {
            Some(bytes) => actual.0 == *bytes && actual.1.is_empty(),
            None => actual == original,
        };
        if !matches {
            return Err(runtime(format!(
                "Structural content mismatch for {hash:016X}"
            )));
        }
    }
    verify_changed_positions(source, staged)?;
    Ok(source.entries.len())
}

/// `_verify_contents(...)`: each replacement (or, with `verify_all_unrelated`, every asset) read
/// back through `read_staged` and compared; `read_source` gives the source's bytes in that mode.
pub fn verify_contents(
    source: &Package,
    staged: &Package,
    replacements: &BTreeMap<u64, Vec<u8>>,
    mut read_source: impl FnMut(u64) -> Result<Vec<u8>, ReadError>,
    mut read_staged: impl FnMut(u64) -> Result<Vec<u8>, ReadError>,
    verify_all_unrelated: bool,
) -> Result<Value, PyError> {
    let hashes: Vec<u64> = if verify_all_unrelated {
        source.entries.keys().copied().collect()
    } else {
        replacements.keys().copied().collect()
    };
    let mismatch = |hash: u64| {
        runtime(format!(
            "Native content mismatch for {hash:016X} in staged package {}",
            staged.package_id
        ))
    };
    let mut checked = 0usize;
    let mut fallback = Vec::new();
    let mut structural: Option<usize> = None;
    for hash in hashes {
        let staged_read = |read: &mut dyn FnMut(u64) -> Result<Vec<u8>, ReadError>| {
            read(hash).map_err(|error| match error {
                ReadError::Native(message) => PyError::new("NativeReadError", message),
                ReadError::Other(error) => error,
            })
        };
        if !verify_all_unrelated {
            if staged_read(&mut read_staged)? != replacements[&hash] {
                return Err(mismatch(hash));
            }
            checked += 1;
            continue;
        }
        // Only the source read is inside the runtime's `try`: a source asset QtsVFS cannot read
        // is checked structurally instead, and a staged one that will not read stops the run.
        let original = match read_source(hash) {
            Ok(bytes) => bytes,
            Err(ReadError::Other(error)) => return Err(error),
            Err(ReadError::Native(reason)) => {
                if structural.is_none() {
                    let count = verify_structural(source, staged, replacements).map_err(|e| {
                        runtime(format!(
                            "{reason}; independent verification also failed: {}. Installation                              stopped before committing game files.",
                            e.message
                        ))
                    })?;
                    structural = Some(count);
                }
                fallback.push(json!({"hash": format!("{hash:016X}"), "reason": reason}));
                continue;
            }
        };
        let actual = staged_read(&mut read_staged)?;
        if actual != *replacements.get(&hash).unwrap_or(&original) {
            return Err(mismatch(hash));
        }
        checked += 1;
    }
    Ok(json!({
        "status": "passed",
        "method": if fallback.is_empty() { "native" } else { "native+structural" },
        "assets_verified": checked + fallback.len(),
        "native_assets_verified": checked,
        "structural_assets_verified": structural.unwrap_or(0),
        "replacements_verified": replacements.len(),
        "source_read_fallbacks": fallback,
    }))
}

/// `native_verify.verify_staged_package(game, source, staged, replacements, work,
/// verify_all_unrelated=...)`.
pub fn verify_staged_package<L: Loader>(
    loader: &mut L,
    game: &Path,
    source: &Path,
    staged: &Path,
    replacements: &BTreeMap<u64, Vec<u8>>,
    work: &Path,
    verify_all_unrelated: bool,
) -> Result<Value, PyError> {
    pyos::mkdir(work, true)?;
    let mut internal = source
        .parent()
        .unwrap_or(Path::new(""))
        .join("0");
    if !pyos::is_dir(&internal)? {
        internal = game.join("WXQ_Data").join("Package").join("builtin").join("0");
        if !pyos::is_dir(&internal)? {
            return Err(runtime("Native verification requires internal package 0"));
        }
    }
    let mut packages = Vec::new();
    if verify_all_unrelated {
        packages.push(("source", source));
    }
    packages.push(("staged", staged));
    let mut roots: Vec<PathBuf> = Vec::new();
    for (label, package) in packages {
        let root = work.join(label);
        fs::create_dir(&root).map_err(|e| pyos::os_error(&e, pyos::Call::Win, &[&root]))?;
        pyos::copytree(&internal, &root.join("0"), false)?;
        let target = root.join(name_of(package));
        if verify_all_unrelated {
            pyos::copytree(package, &target, false)?;
        } else if let Err(error) = pyos::copytree(package, &target, true) {
            if !is_os_error(&error) {
                return Err(error);
            }
            if pyos::exists(&target)? {
                pyos::rmtree(&target)?;
            }
            pyos::copytree(package, &target, false)?;
        }
        roots.push(root);
    }
    let bin_dir = qtsvfs_bin_dir(&pyos::resolve(game))?;
    let mut api = loader.load(&bin_dir)?;
    api.require(&VERIFY_SYMBOLS)?;
    let source_id = name_of(source);
    let mut systems: Vec<Vec<u8>> = Vec::new();
    for root in &roots {
        let system = format!("verify_{}", pyos::random_hex()).into_bytes();
        let scratch = root.join("scratch");
        fs::create_dir(&scratch).map_err(|e| pyos::os_error(&e, pyos::Call::Win, &[&scratch]))?;
        let scratch = path_bytes(&pyos::resolve(&scratch));
        if !api.create_system(&system, &path_bytes(&pyos::resolve(root)), &scratch) {
            return Err(runtime(format!(
                "Native CreateSystem failed: {}",
                last_error(&mut api)
            )));
        }
        systems.push(system.clone());
        for package_id in ["0", source_id.as_str()] {
            let handle = api.describe(&system, package_id.as_bytes(), package_id == "0");
            if handle < 0 || !api.set_prime(handle, true) || !api.mount(handle) {
                return Err(runtime(format!(
                    "Native mount failed for {package_id}: {}",
                    last_error(&mut api)
                )));
            }
        }
    }
    let source_package = Package::open(source)?;
    let staged_package = Package::open(staged)?;
    let api = std::cell::RefCell::new(api);
    let content = |system: &[u8], hash: u64, label: &str| -> Result<Vec<u8>, ReadError> {
        let mut api = api.borrow_mut();
        let size = api.file_length(system, hash);
        let file = api.open_file(system, hash);
        let place = format!(
            "({label}, package {source_id}, root {})",
            work.join(label).display()
        );
        if file == 0 {
            return Err(ReadError::Native(format!(
                "Native open failed for {hash:016X}: {} {place}",
                last_error(&mut *api)
            )));
        }
        let mut buffer = vec![0; size as usize];
        let count = api.read(&mut buffer, file);
        let result = if count != size {
            Err(ReadError::Native(format!(
                "Native read failed for {hash:016X}: {count}/{size}, error {} {place}",
                last_error(&mut *api)
            )))
        } else {
            Ok(buffer)
        };
        api.close_file(file);
        result
    };
    let source_system = systems[0].clone();
    let staged_system = systems[systems.len() - 1].clone();
    verify_contents(
        &source_package,
        &staged_package,
        replacements,
        |hash| content(&source_system, hash, "source"),
        |hash| content(&staged_system, hash, "staged"),
        verify_all_unrelated,
    )
}

/// `error()`: the code `VFS_GetLastError` returns.
fn last_error(api: &mut impl QtsVfs) -> i32 {
    api.last_error()
}

/// `except OSError` (`shutil.Error` is one).
fn is_os_error(error: &PyError) -> bool {
    matches!(
        error.class,
        "OSError"
            | "Error"
            | "FileNotFoundError"
            | "FileExistsError"
            | "PermissionError"
            | "NotADirectoryError"
            | "IsADirectoryError"
    )
}
