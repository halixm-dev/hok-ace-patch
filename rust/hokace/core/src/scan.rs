//! The runtime's package scan: `wxq_patch.adaptive.discover`, `scan` and `apply_graphic_payload`.
//!
//! Ported from the bytecode (ADR-003) and held to `rust/harness/runtime_tap.py --scan-runtime`.
//! `scan` reads each package through the slot map the pipeline installs before scanning
//! (`tools/qts_relocate.install_btree_slot_map`): the stock map, with a single shard's superseded
//! chunks repointed at the slot its B-tree names. A B-tree that will not read keeps the stock map
//! and is reported in [`ScanReport::fallbacks`], as `qts_relocate.BTREE_FALLBACKS` records it.
//!
//! Every exception the runtime raises or catches on purpose keeps its class and message. Three
//! things are the port's own:
//! - a package folder named in non-ASCII digits, which `str.isdecimal` would accept, is refused;
//! - two live slots for one chunk, which the reference settles by Python's set order, are refused;
//! - an `OSError` other than a missing file or a refused permission, and an LZ4 block that will not
//!   decompress, carry Rust's text, not Python's (the mobile summary keeps only their count).
//!
//! A graphic whose hashes or patch ranges are not the strings and integers the shipped catalogs
//! hold is refused as a `TypeError` of the port's own.

use std::collections::{BTreeMap, HashMap};
use std::fmt;
use std::fs::{self, File};
use std::io::{self, Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};

use indexmap::IndexMap;
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};

use crate::catalog::{CatalogData, py_repr};
use crate::qts::{self, ChunkSlot, ExtractError, IndexEntry, Payload};
use crate::translation::{self, Catalog};

const BUILTIN: [&str; 3] = ["WXQ_Data", "Package", "builtin"];
const PAGE: u64 = 0x1000;
const KEYS_PER_PAGE: u64 = 510;
const LEAF_TYPE: u32 = 3;

/// A Python exception: its class and `str()`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PyError {
    pub class: &'static str,
    pub message: String,
}

impl PyError {
    fn new(class: &'static str, message: impl Into<String>) -> Self {
        Self {
            class,
            message: message.into(),
        }
    }

    fn value(message: impl Into<String>) -> Self {
        Self::new("ValueError", message)
    }

    /// `OSError` as `open()` raises it for `path`.
    fn os(error: &io::Error, path: &Path) -> Self {
        let name = py_repr(&path.display().to_string());
        match error.kind() {
            io::ErrorKind::NotFound => Self::new(
                "FileNotFoundError",
                format!("[Errno 2] No such file or directory: {name}"),
            ),
            io::ErrorKind::PermissionDenied => Self::new(
                "PermissionError",
                format!("[Errno 13] Permission denied: {name}"),
            ),
            _ => Self::new("OSError", format!("{error}: {name}")),
        }
    }

    fn is_os(&self) -> bool {
        matches!(
            self.class,
            "OSError" | "FileNotFoundError" | "PermissionError"
        )
    }
}

impl fmt::Display for PyError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}: {}", self.class, self.message)
    }
}

impl std::error::Error for PyError {}

/// `qtsvfs.QtsPackage` as `__init__` leaves it.
#[derive(Debug)]
pub struct Package {
    pub package_id: String,
    pub package_dir: PathBuf,
    pub index_path: PathBuf,
    /// `sorted(<id>_*.db)`, files only, as Windows or POSIX globs and sorts them.
    pub shard_paths: Vec<PathBuf>,
    /// `parse_index` in its dictionary order.
    pub entries: IndexMap<u64, IndexEntry>,
}

impl Package {
    /// `QtsPackage(package_dir)`.
    pub fn open(package_dir: &Path) -> Result<Self, PyError> {
        let package_id = file_name(package_dir);
        let index_path = package_dir.join(format!("{package_id}.db"));
        if !index_path.is_file() {
            return Err(PyError::new(
                "FileNotFoundError",
                index_path.display().to_string(),
            ));
        }
        let shown = index_path.display().to_string();
        let file = File::open(&index_path).map_err(|error| PyError::os(&error, &index_path))?;
        let entries = match qts::parse_index(file) {
            Ok(entries) => entries,
            Err(qts::Error::SmallIndex) => {
                return Err(PyError::value(format!(
                    "QtsVFS index is too small: {shown}"
                )));
            }
            Err(qts::Error::MissingEntries) => {
                return Err(PyError::value(format!(
                    "No QtsVFS entries found in {shown}"
                )));
            }
            Err(qts::Error::EmptyShard) => {
                return Err(PyError::value("cannot mmap an empty file"));
            }
            Err(qts::Error::Io(error)) => return Err(PyError::os(&error, &index_path)),
        };
        let shard_paths =
            shards(package_dir, &package_id).map_err(|error| PyError::os(&error, package_dir))?;
        Ok(Self {
            entries: entries.into_iter().map(|e| (e.file_hash, e)).collect(),
            package_id,
            package_dir: package_dir.to_owned(),
            index_path,
            shard_paths,
        })
    }
}

/// One slot of the map `build_slot_map` returns, with the shard it was read from.
#[derive(Debug)]
pub struct Slot {
    pub shard_path: PathBuf,
    pub slot: ChunkSlot,
}

/// A skipped package (`asset` is `None`) or asset, with `str(exc)`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Skip {
    pub package: String,
    pub asset: Option<String>,
    pub reason: String,
}

/// A package the scan staged replacements for.
#[derive(Debug)]
pub struct Plan {
    pub package: Package,
    pub replacements: PathBuf,
    /// Per asset, in sorted order, its counts in their `Counter` order.
    pub per_asset: Vec<(u64, Vec<(&'static str, usize)>)>,
}

/// What `scan` returns, plus the shards whose B-tree would not read.
#[derive(Debug, Default)]
pub struct ScanReport {
    pub plans: Vec<Plan>,
    /// `str(path.relative_to(game))` to its SHA-256, in insertion order.
    pub fingerprints: IndexMap<String, String>,
    /// `dict(total)`: the `Counter` in first-increment order.
    pub total: IndexMap<&'static str, usize>,
    pub skipped: Vec<Skip>,
    /// `qts_relocate.BTREE_FALLBACKS` entries this scan added: shard path and reason.
    pub fallbacks: Vec<(String, String)>,
}

fn file_name(path: &Path) -> String {
    path.file_name()
        .map(|name| name.to_string_lossy().into_owned())
        .unwrap_or_default()
}

/// The path as `pathlib` normalizes it: native separators, no `.` parts, no trailing separator.
pub fn python_path(path: &Path) -> PathBuf {
    path.components().collect()
}

/// `name.isdecimal()`, refusing the non-ASCII decimal digits the port does not compare.
fn is_decimal(name: &str) -> Result<bool, PyError> {
    if !name.is_empty() && name.bytes().all(|b| b.is_ascii_digit()) {
        return Ok(true);
    }
    if !name.is_empty() && !name.is_ascii() && name.chars().all(char::is_numeric) {
        return Err(PyError::new(
            "ValueError",
            format!("package folder {} is not in ASCII digits", py_repr(name)),
        ));
    }
    Ok(false)
}

/// The sort key `sorted()` gives a `WindowsPath` (case-insensitive) or a `PosixPath`.
fn sort_key(name: &str) -> String {
    if cfg!(windows) {
        name.to_lowercase()
    } else {
        name.to_owned()
    }
}

/// `sorted(p for p in package_dir.glob(f"{id}_*.db") if p.is_file())`.
fn shards(package_dir: &Path, package_id: &str) -> io::Result<Vec<PathBuf>> {
    let prefix = sort_key(&format!("{package_id}_"));
    let mut found = Vec::new();
    for item in fs::read_dir(package_dir)? {
        let path = item?.path();
        let name = sort_key(&file_name(&path));
        if name.len() >= prefix.len() + 3
            && name.starts_with(&prefix)
            && name.ends_with(".db")
            && path.is_file()
        {
            found.push((name, path));
        }
    }
    found.sort();
    Ok(found.into_iter().map(|(_, path)| path).collect())
}

/// `adaptive.discover(game, catalog)`: every package folder, and why one would not open.
pub fn discover(game: &Path, catalog: &CatalogData) -> Result<(Vec<Package>, Vec<Skip>), PyError> {
    let builtin: PathBuf = BUILTIN
        .iter()
        .fold(python_path(game), |path, part| path.join(part));
    if !builtin.is_dir() {
        return Err(PyError::value("WXQ_Data/Package/builtin was not found"));
    }
    let mut folders = Vec::new();
    for item in fs::read_dir(&builtin).map_err(|error| PyError::os(&error, &builtin))? {
        let path = item.map_err(|error| PyError::os(&error, &builtin))?.path();
        folders.push((sort_key(&file_name(&path)), path));
    }
    folders.sort();
    let (mut packages, mut skipped) = (Vec::new(), Vec::new());
    for (_, directory) in folders {
        let name = file_name(&directory);
        if !directory.is_dir() || !is_decimal(&name)? {
            continue;
        }
        let package = match Package::open(&directory) {
            Ok(package) => package,
            Err(error) if error.class == "PermissionError" => return Err(error),
            Err(error) if error.is_os() || error.class == "ValueError" => {
                skipped.push(Skip {
                    package: name,
                    asset: None,
                    reason: error.message,
                });
                continue;
            }
            Err(error) => return Err(error),
        };
        let wanted = package.entries.keys().any(|&hash| {
            let hash = i128::from(hash);
            catalog.known.contains(&hash) || catalog.graphics.contains_key(&hash)
        });
        if name == "1" || wanted {
            packages.push(package);
        }
    }
    Ok((packages, skipped))
}

/// `QtsPackage.build_slot_map` as `qts_relocate.install_btree_slot_map` replaces it.
pub fn build_slot_map(
    package: &Package,
    fallbacks: &mut Vec<(String, String)>,
) -> Result<HashMap<u64, BTreeMap<u32, Slot>>, PyError> {
    let mut map: HashMap<u64, BTreeMap<u32, Slot>> = HashMap::new();
    for shard_path in &package.shard_paths {
        let file = File::open(shard_path).map_err(|error| PyError::os(&error, shard_path))?;
        let slots = match qts::chunk_slots(file, false) {
            Ok(slots) => slots,
            Err(qts::Error::EmptyShard) => {
                return Err(PyError::value("cannot mmap an empty file"));
            }
            Err(qts::Error::Io(error)) => return Err(PyError::os(&error, shard_path)),
            Err(error) => return Err(PyError::value(error.to_string())),
        };
        for slot in slots {
            map.entry(slot.file_hash)
                .or_default()
                .entry(slot.chunk_id)
                .or_insert_with(|| Slot {
                    shard_path: shard_path.clone(),
                    slot,
                });
        }
    }
    let [path] = package.shard_paths.as_slice() else {
        return Ok(map);
    };
    let live = match btree_offsets(path) {
        Ok(live) => live,
        Err(reason) => {
            fallbacks.push((path.display().to_string(), reason));
            return Ok(map);
        }
    };
    let stale = |slot: &ChunkSlot| {
        let key = (slot.hash1 & 0xFFFF_FFFF) as u32;
        !u32::try_from(slot.slot_offset)
            .is_ok_and(|offset| live.get(&key).is_some_and(|set| set.contains(&offset)))
    };
    if !map
        .values()
        .flat_map(BTreeMap::values)
        .any(|s| stale(&s.slot))
    {
        return Ok(map);
    }
    let file = File::open(path).map_err(|error| PyError::os(&error, path))?;
    let mut by_offset: HashMap<u64, ChunkSlot> = match qts::chunk_slots(file, false) {
        Ok(slots) => slots.into_iter().map(|s| (s.slot_offset, s)).collect(),
        Err(qts::Error::Io(error)) => return Err(PyError::os(&error, path)),
        Err(error) => return Err(PyError::value(error.to_string())),
    };
    for chunks in map.values_mut() {
        for current in chunks.values_mut() {
            if !stale(&current.slot) {
                continue;
            }
            let key = (current.slot.hash1 & 0xFFFF_FFFF) as u32;
            let (file_hash, chunk_id) = (current.slot.file_hash, current.slot.chunk_id);
            let mut matches = live.get(&key).into_iter().flatten().filter(|&&offset| {
                by_offset
                    .get(&u64::from(offset))
                    .is_some_and(|c| c.file_hash == file_hash && c.chunk_id == chunk_id)
            });
            let Some(&offset) = matches.next() else {
                continue;
            };
            if matches.next().is_some() {
                return Err(PyError::new(
                    "RuntimeError",
                    format!("{file_hash:016X} chunk {chunk_id} has more than one live slot"),
                ));
            }
            if let Some(slot) = by_offset.remove(&u64::from(offset)) {
                current.slot = slot;
            }
        }
    }
    Ok(map)
}

/// `qts_relocate._read_btree_offsets`, with `str(error)` for every way it fails.
fn btree_offsets(path: &Path) -> Result<HashMap<u32, Vec<u32>>, String> {
    let mut file = File::open(path).map_err(|error| PyError::os(&error, path).message)?;
    let mut read = |offset: u64, size: usize| -> Result<Vec<u8>, String> {
        file.seek(SeekFrom::Start(offset))
            .map_err(|error| error.to_string())?;
        let mut data = Vec::with_capacity(size);
        (&mut file)
            .take(size as u64)
            .read_to_end(&mut data)
            .map_err(|error| error.to_string())?;
        Ok(data)
    };
    let word = |data: &[u8], at: usize| {
        u32::from_le_bytes([data[at], data[at + 1], data[at + 2], data[at + 3]])
    };
    let unpack = |data: Vec<u8>, size: usize| {
        if data.len() == size {
            Ok(data)
        } else {
            Err(format!("unpack requires a buffer of {size} bytes"))
        }
    };
    let table = u64::from(word(&unpack(read(0x30, 4)?, 4)?, 0));
    let rows = word(&unpack(read(table + 4, 4)?, 4)?, 0);
    let mut offsets: HashMap<u32, Vec<u32>> = HashMap::new();
    let mut leaves = 0;
    for row in 0..u64::from(rows) {
        let pair = unpack(read(table + 24 + row * 24, 8)?, 8)?;
        let (logical, active) = (word(&pair, 0), word(&pair, 4));
        let page = read(u64::from(active), PAGE as usize)?;
        if page.len() < PAGE as usize {
            return Err(format!(
                "unpack_from requires a buffer of at least {PAGE} bytes for unpacking 16 bytes \
                 at offset {} (actual buffer size is {})",
                PAGE - 16,
                page.len()
            ));
        }
        let footer = (PAGE - 16) as usize;
        let (self_id, tail) = (word(&page, footer), word(&page, footer + 12));
        if tail >> 16 != LEAF_TYPE || self_id != logical {
            continue;
        }
        leaves += 1;
        let count = u64::from(tail & 0xFFFF);
        for start in [0, KEYS_PER_PAGE * 4] {
            if start + count * 4 > PAGE {
                return Err(format!(
                    "unpack_from requires a buffer of at least {} bytes for unpacking {} bytes \
                     at offset {start} (actual buffer size is {PAGE})",
                    start + count * 4,
                    count * 4
                ));
            }
        }
        for i in 0..count as usize {
            let key = word(&page, i * 4);
            let value = word(&page, (KEYS_PER_PAGE as usize + i) * 4);
            let set = offsets.entry(key).or_default();
            if !set.contains(&value) {
                set.push(value);
            }
        }
    }
    if leaves == 0 {
        return Err(format!(
            "{}: no active B-tree leaf pages found",
            file_name(path)
        ));
    }
    Ok(offsets)
}

/// `installer.sha256_file`.
fn sha256_file(path: &Path) -> Result<String, PyError> {
    let mut file = File::open(path).map_err(|error| PyError::os(&error, path))?;
    let mut digest = Sha256::new();
    let mut buffer = vec![0; 1 << 20];
    loop {
        let read = file
            .read(&mut buffer)
            .map_err(|error| PyError::os(&error, path))?;
        if read == 0 {
            break;
        }
        digest.update(&buffer[..read]);
    }
    Ok(hex(&digest.finalize()))
}

fn hex(data: &[u8]) -> String {
    data.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn graphic_text<'a>(graphic: &'a Map<String, Value>, key: &str) -> Result<&'a str, PyError> {
    match graphic.get(key) {
        None => Err(PyError::new("KeyError", py_repr(key))),
        Some(Value::String(text)) => Ok(text),
        Some(_) => Err(PyError::new(
            "TypeError",
            format!("graphic {} is not a string", py_repr(key)),
        )),
    }
}

fn previous_hashes(graphic: &Map<String, Value>) -> Result<Vec<&str>, PyError> {
    let refused = || {
        PyError::new(
            "TypeError",
            "graphic 'previous_sha256' is not a list of strings",
        )
    };
    match graphic.get("previous_sha256") {
        None => Ok(Vec::new()),
        Some(Value::Array(items)) => items
            .iter()
            .map(|i| i.as_str().ok_or_else(refused))
            .collect(),
        Some(_) => Err(refused()),
    }
}

/// `adaptive.apply_graphic_payload(raw, payload, graphic)`.
pub fn apply_graphic_payload(
    raw: &[u8],
    payload: &[u8],
    graphic: &Map<String, Value>,
) -> Result<Vec<u8>, PyError> {
    let translated = match graphic.get("patch_ranges") {
        None => payload.to_vec(),
        Some(ranges) => {
            let refused =
                || PyError::new("TypeError", "graphic 'patch_ranges' is not a list of pairs");
            let mut translated = raw.to_vec();
            let (mut cursor, mut previous_end) = (0i128, 0i128);
            for range in ranges.as_array().ok_or_else(refused)? {
                let pair = range.as_array().ok_or_else(refused)?;
                let [start, size] = pair.as_slice() else {
                    return Err(refused());
                };
                let number = |value: &Value| {
                    value
                        .as_i64()
                        .map(i128::from)
                        .or_else(|| value.as_u64().map(i128::from))
                        .ok_or_else(refused)
                };
                let (start, size) = (number(start)?, number(size)?);
                let end = start + size;
                if start < previous_end
                    || size <= 0
                    || end > raw.len() as i128
                    || cursor + size > payload.len() as i128
                {
                    return Err(PyError::value("Invalid embedded graphics patch range"));
                }
                // INFALLIBLE: the checks above keep 0 <= start < end <= len(raw) and the cursor in payload.
                let (s, e, c) = (start as usize, end as usize, cursor as usize);
                translated[s..e].copy_from_slice(&payload[c..c + (e - s)]);
                cursor += size;
                previous_end = end;
            }
            if cursor != payload.len() as i128 {
                return Err(PyError::value("Unexpected embedded graphics patch bytes"));
            }
            translated
        }
    };
    if hex(&Sha256::digest(&translated)) != graphic_text(graphic, "patched_sha256")? {
        return Err(PyError::value("Embedded graphics integrity check failed"));
    }
    Ok(translated)
}

/// A `collections.Counter` keeping first-increment order.
#[derive(Default)]
struct Counter(IndexMap<&'static str, usize>);

impl Counter {
    fn add(&mut self, key: &'static str, count: usize) {
        *self.0.entry(key).or_default() += count;
    }
}

fn get(counts: &[(&'static str, usize)], key: &str) -> usize {
    counts
        .iter()
        .find(|(name, _)| *name == key)
        .map_or(0, |(_, count)| *count)
}

/// Reads one asset as the scan's first `try` does: chunks, payload, descriptor size.
fn read_asset(
    package: &Package,
    slots: &HashMap<u64, BTreeMap<u32, Slot>>,
    index_data: &[u8],
    hash: u64,
) -> Result<Vec<u8>, PyError> {
    let chunk_map = slots.get(&hash);
    let contiguous = chunk_map.is_some_and(|chunks| {
        !chunks.is_empty() && chunks.keys().copied().eq(0..chunks.len() as u32)
    });
    let Some(chunk_map) = chunk_map.filter(|_| contiguous) else {
        return Err(PyError::value("Missing or non-contiguous asset chunks"));
    };
    let entry = &package.entries[&hash];
    let chunks: HashMap<u32, Payload> = chunk_map
        .iter()
        .map(|(&id, slot)| {
            let payload = Payload {
                path: slot.shard_path.clone(),
                offset: slot.slot.payload_offset,
                compressed_size: slot.slot.compressed_size,
                uncompressed_size: slot.slot.uncompressed_size,
            };
            (id, payload)
        })
        .collect();
    let raw = qts::extract(entry.compression, &chunks).map_err(|error| match error {
        ExtractError::Io(error) => PyError::os(&error, &package.index_path),
        ExtractError::MissingChunks => PyError::value(format!("No chunks found for {hash:016X}")),
        ExtractError::ShortRead(path) => {
            PyError::new("OSError", format!("Short read from {}", path.display()))
        }
        ExtractError::UnsupportedCompression(codec) => {
            PyError::value(format!("Unsupported compression {codec} for {hash:016X}"))
        }
        ExtractError::Decompression => PyError::new(
            "LZ4BlockError",
            "Decompression failed: corrupt input or insufficient space in destination buffer",
        ),
        ExtractError::UnexpectedSize(chunk) => {
            PyError::value(format!("Chunk {chunk} decompressed to an unexpected size"))
        }
    })?;
    let at = entry.entry_offset as usize + 44;
    let expected = index_data
        .get(at..at + 4)
        .map(|b| u32::from_le_bytes([b[0], b[1], b[2], b[3]]))
        .ok_or_else(|| {
            PyError::new("error", "unpack_from requires a buffer of at least 4 bytes")
        })?;
    if raw.len() != expected as usize {
        return Err(PyError::value(
            "Asset length differs from its current index descriptor",
        ));
    }
    Ok(raw)
}

/// `adaptive.scan(game, assets, work, materialize=...)` on a catalog already loaded from
/// `assets` (`load_catalog(assets)`, the scan's first call) and its text view.
pub fn scan(
    game: &Path,
    assets: &Path,
    catalog: &CatalogData,
    text: &Catalog,
    work: &Path,
    materialize: bool,
) -> Result<ScanReport, PyError> {
    let game = python_path(game);
    let (packages, skipped) = discover(&game, catalog)?;
    let mut report = ScanReport::default();
    let mut total = Counter::default();
    let mut details = Vec::new();
    for package in packages {
        let mut before = IndexMap::new();
        if materialize {
            for path in std::iter::once(&package.index_path).chain(&package.shard_paths) {
                let relative = path.strip_prefix(&game).unwrap_or(path);
                before.insert(relative.display().to_string(), sha256_file(path)?);
            }
        }
        let slots = build_slot_map(&package, &mut report.fallbacks)?;
        let index_data =
            fs::read(&package.index_path).map_err(|e| PyError::os(&e, &package.index_path))?;
        let replacements = work.join("replacements").join(&package.package_id);
        let mut per_asset = Vec::new();
        let scan_tables = package.package_id == "1"
            || package
                .entries
                .keys()
                .any(|&hash| catalog.known.contains(&i128::from(hash)));
        let mut hashes: Vec<u64> = package.entries.keys().copied().collect();
        hashes.sort_unstable();
        for hash in hashes {
            let graphic = catalog.graphics.get(&i128::from(hash));
            if !scan_tables && graphic.is_none() {
                continue;
            }
            let raw = match read_asset(&package, &slots, &index_data, hash) {
                Ok(raw) => raw,
                Err(error) if error.class == "PermissionError" => return Err(error),
                Err(error)
                    if error.is_os()
                        || matches!(error.class, "ValueError" | "KeyError" | "LZ4BlockError") =>
                {
                    details.push(Skip {
                        package: package.package_id.clone(),
                        asset: Some(format!("{hash:016X}")),
                        reason: error.message,
                    });
                    total.add("unreadable_assets", 1);
                    continue;
                }
                Err(error) => return Err(error),
            };
            let (translated, counts) = if let Some(graphic) = graphic {
                let digest = hex(&Sha256::digest(&raw));
                if digest == graphic_text(graphic, "patched_sha256")? {
                    total.add("graphics_already", 1);
                    continue;
                }
                let source = graphic_text(graphic, "source_sha256")?;
                let previous = previous_hashes(graphic)?;
                if digest != source && !previous.contains(&digest.as_str()) {
                    total.add("graphics_changed", 1);
                    continue;
                }
                let translated = if materialize {
                    let payload = assets.join(graphic_text(graphic, "payload")?);
                    let bytes = fs::read(&payload).map_err(|e| PyError::os(&e, &payload))?;
                    Some(apply_graphic_payload(&raw, &bytes, graphic)?)
                } else {
                    None
                };
                (translated, vec![("graphics", 1)])
            } else {
                let result = match translation::translate_table(&raw, hash, text, materialize) {
                    Ok(result) => result,
                    Err(error)
                        if matches!(
                            error.python_class(),
                            "ProtobufError" | "UnicodeDecodeError"
                        ) =>
                    {
                        if catalog.known.contains(&i128::from(hash)) {
                            total.add("unrecognized_tables", 1);
                        }
                        continue;
                    }
                    Err(error) => {
                        return Err(PyError::new(error.python_class(), error.to_string()));
                    }
                };
                total.add("tables", 1);
                for &(key, count) in &result.counts {
                    if key != "translated" {
                        total.add(key, count);
                    }
                }
                if get(&result.counts, "translated") == 0 {
                    continue;
                }
                (result.output, result.counts)
            };
            if package.entries[&hash].compression != 1 {
                total.add("capacity_skipped", get(&counts, "translated"));
                total.add("assets_skipped", 1);
                details.push(Skip {
                    package: package.package_id.clone(),
                    asset: Some(format!("{hash:016X}")),
                    reason: "Unrecognized compression".into(),
                });
                continue;
            }
            if materialize {
                fs::create_dir_all(&replacements).map_err(|e| PyError::os(&e, &replacements))?;
                let path = replacements.join(format!("{hash:016X}.assets"));
                // INFALLIBLE: with materialize set, both branches above built the output.
                let output = translated.unwrap_or_default();
                fs::write(&path, output).map_err(|e| PyError::os(&e, &path))?;
            }
            total.add("translated", get(&counts, "translated"));
            total.add("graphics", get(&counts, "graphics"));
            if materialize {
                per_asset.push((hash, counts));
            }
        }
        if !per_asset.is_empty() {
            report.plans.push(Plan {
                package,
                replacements,
                per_asset,
            });
        }
        if materialize {
            report.fingerprints.extend(before);
        }
    }
    report.total = total.0;
    report.skipped = skipped.into_iter().chain(details).collect();
    Ok(report)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn graphic(value: Value) -> Map<String, Value> {
        match value {
            Value::Object(map) => map,
            _ => Map::new(),
        }
    }

    #[test]
    fn decimal_names_are_ascii_digits_and_others_are_refused() {
        assert_eq!(is_decimal("21"), Ok(true));
        assert_eq!(is_decimal(""), Ok(false));
        assert_eq!(is_decimal("1a"), Ok(false));
        assert_eq!(is_decimal("½x"), Ok(false));
        assert!(is_decimal("١٢").is_err());
    }

    #[test]
    fn patch_ranges_splice_in_order_and_refuse_other_shapes() {
        let payload = b"ENGXY";
        let mut expected = b"older art bytes!!".to_vec();
        expected[2..5].copy_from_slice(b"ENG");
        expected[8..10].copy_from_slice(b"XY");
        let patched = hex(&Sha256::digest(&expected));
        let ok = graphic(json!({"patched_sha256": patched, "patch_ranges": [[2, 3], [8, 2]]}));
        assert_eq!(
            apply_graphic_payload(b"older art bytes!!", payload, &ok),
            Ok(expected)
        );
        for ranges in [json!([[2, 3], [3, 2]]), json!([[2, 0]]), json!([[16, 2]])] {
            let bad = graphic(json!({"patched_sha256": patched, "patch_ranges": ranges}));
            let error = apply_graphic_payload(b"older art bytes!!", payload, &bad).unwrap_err();
            assert_eq!(error.message, "Invalid embedded graphics patch range");
        }
        for ranges in [json!(null), json!([[2]]), json!([["2", 3]])] {
            let bad = graphic(json!({"patched_sha256": patched, "patch_ranges": ranges}));
            let error = apply_graphic_payload(b"older art bytes!!", payload, &bad).unwrap_err();
            assert_eq!(error.class, "TypeError");
        }
    }

    #[test]
    fn python_path_uses_native_separators() {
        let path = python_path(Path::new("game/./WXQ_Data/"));
        assert_eq!(path, Path::new("game").join("WXQ_Data"));
    }
}
