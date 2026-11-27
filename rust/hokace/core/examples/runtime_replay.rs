//! Compares the Rust wire readers against rust/harness/runtime_tap.py.

use hokace_core::catalog::{self, CatalogData, CatalogError};
use hokace_core::package_metadata::{self, LookupError};
use hokace_core::protobuf::{self, Error, Record, Value};
use hokace_core::qts;
use hokace_core::scan;
use hokace_core::translation::{self, Catalog};
use serde_json::{Value as Json, json};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, HashMap};
use std::io::{BufRead, BufReader};
use std::path::Path;
use std::{env, fs};

fn bytes(hash: &mut Sha256, data: &[u8]) {
    hash.update((data.len() as u64).to_le_bytes());
    hash.update(data);
}

fn hex(data: &[u8]) -> String {
    use std::fmt::Write;
    let mut output = String::with_capacity(data.len() * 2);
    for byte in data {
        write!(output, "{byte:02x}").expect("writing to a String is infallible");
    }
    output
}

fn hash_result(hash: Sha256, result: Result<(), Error>) -> Json {
    let digest = hex(&hash.finalize());
    match result {
        Ok(()) => json!({"ok": digest}),
        Err(err) => json!({"error": error(&err), "partial": digest}),
    }
}

fn error(err: &Error) -> String {
    format!("{}: {err}", err.python_class())
}

fn walk(data: &[u8], hash: &mut Sha256, outer: bool) -> Result<(), Error> {
    for field in protobuf::localization_fields(data) {
        let field = field?;
        hash.update(if outer { b"O" } else { b"I" });
        hash.update(u128::from(field.tag).to_le_bytes());
        bytes(hash, field.payload);
        bytes(hash, field.raw);
        if outer {
            walk(field.payload, hash, false)?;
        }
    }
    Ok(())
}

fn wire_fields(data: &[u8], hash: &mut Sha256) -> Result<(), Error> {
    for field in protobuf::fields(data) {
        let field = field?;
        hash.update(b"F");
        hash.update(field.number.to_le_bytes());
        hash.update([field.wire]);
        match field.value {
            Value::Varint(value) => {
                hash.update(b"V");
                hash.update(value.to_le_bytes());
            }
            Value::Bytes(value) => {
                hash.update(b"B");
                bytes(hash, value);
            }
        }
    }
    Ok(())
}

fn read_string<'a>(input: &mut &'a [u8]) -> Result<&'a str, Box<dyn std::error::Error>> {
    let (size, rest) = input.split_at_checked(8).ok_or("missing string size")?;
    let size = usize::try_from(u64::from_le_bytes(size.try_into()?))?;
    let (value, rest) = rest.split_at_checked(size).ok_or("truncated string")?;
    *input = rest;
    Ok(std::str::from_utf8(value)?)
}

fn replay(name: &str, args: &Json, mut data: &[u8]) -> Result<Json, Box<dyn std::error::Error>> {
    Ok(match name {
        "package_metadata.find" => {
            let path = args[0].as_str().ok_or("missing metadata path")?;
            let name = args[1].as_str().ok_or("missing package name")?;
            match package_metadata::find_package_hash_entry(data, name) {
                Ok(entry) => json!({"ok": {
                    "name": entry.name, "offset": entry.offset, "hash_offset": entry.hash_offset,
                    "next_offset": entry.next_offset, "hash": entry.hash,
                }}),
                Err(err) => {
                    let error = match err {
                        LookupError::EmptyName => "Package name is empty".into(),
                        LookupError::MissingMarker => {
                            format!("QtsVFS package metadata is missing from {path}")
                        }
                        LookupError::MissingTable => {
                            format!("QtsVFS package metadata table is missing from {path}")
                        }
                        LookupError::EntryCount(count) => {
                            format!("QtsVFS package metadata has {count} entries for '{name}'")
                        }
                    };
                    json!({"error": format!("ValueError: {error}")})
                }
            }
        }
        "qts.find_positions" => {
            let positions = serde_json::from_value(args[0].clone())?;
            let wanted: Vec<u32> = serde_json::from_value(args[1].clone())?;
            json!({"ok": qts::find_position_references(data, &positions, wanted)})
        }
        "qts.insert_positions" => {
            let positions = |arg: &Json| -> Result<Vec<qts::Position>, serde_json::Error> {
                let rows: Vec<(u32, u32)> = serde_json::from_value(arg.clone())?;
                Ok(rows
                    .into_iter()
                    .map(|(offset, key)| qts::Position { offset, key })
                    .collect())
            };
            let mut trial = data.to_vec();
            let result = qts::insert_position_references(
                &mut trial,
                &positions(&args[0])?,
                &positions(&args[1])?,
            );
            let digest = hex(&Sha256::digest(trial));
            match result {
                Ok(updates) => {
                    let updates: Vec<_> = updates
                        .iter()
                        .map(|update| {
                            json!({
                                "slot_offset": update.position.offset,
                                "position_key": format!("{:08X}", update.position.key),
                                "reference_offsets": update.reference_offsets,
                            })
                        })
                        .collect();
                    json!({"ok": updates, "bytes": digest})
                }
                Err(err) => json!({"error": format!("RuntimeError: {err}"), "bytes": digest}),
            }
        }
        "qts.live_replacements" => {
            let path = args[0].as_str().ok_or("missing shard path")?;
            let (rows, remaining) = data.as_chunks::<24>();
            if !remaining.is_empty() {
                return Err("truncated stock slot row".into());
            }
            let stock = rows
                .iter()
                .map(|row| {
                    Ok((
                        u64::from_le_bytes(row[..8].try_into()?),
                        u32::from_le_bytes(row[8..12].try_into()?),
                        u64::from_le_bytes(row[12..20].try_into()?),
                        u32::from_le_bytes(row[20..].try_into()?),
                    ))
                })
                .collect::<Result<Vec<_>, std::array::TryFromSliceError>>()?;
            let slots = qts::live_replacements(fs::File::open(path)?, stock)?;
            row_hash(slots.iter().map(qts::ChunkSlot::fields))
        }
        "qts.extract" => {
            let asset = args[0].as_u64().ok_or("missing asset hash")?;
            let compression = u16::try_from(args[1].as_u64().ok_or("missing compression")?)?;
            let coords: HashMap<u32, (String, u64, u32, u32)> =
                serde_json::from_value(args[2].clone())?;
            let chunks = coords
                .into_iter()
                .map(|(id, (path, offset, compressed_size, uncompressed_size))| {
                    (
                        id,
                        qts::Payload {
                            path: path.into(),
                            offset,
                            compressed_size,
                            uncompressed_size,
                        },
                    )
                })
                .collect();
            let error = match qts::extract(compression, &chunks) {
                Ok(raw) => return Ok(json!({"ok": [raw.len(), hex(&Sha256::digest(raw))]})),
                Err(qts::ExtractError::MissingChunks) => {
                    format!("ValueError: No chunks found for {asset:016X}")
                }
                Err(qts::ExtractError::ShortRead(path)) => {
                    format!("OSError: Short read from {}", path.display())
                }
                Err(qts::ExtractError::UnsupportedCompression(codec)) => {
                    format!("ValueError: Unsupported compression {codec} for {asset:016X}")
                }
                Err(qts::ExtractError::UnexpectedSize(chunk)) => {
                    format!("ValueError: Chunk {chunk} decompressed to an unexpected size")
                }
                Err(err) => return Err(format!("{err:?}").into()),
            };
            json!({"error": error})
        }
        "qts.index" | "qts.slots" => {
            let path = args[0].as_str().ok_or("missing database path")?;
            let reader = fs::File::open(path)?;
            if name == "qts.index" {
                match qts::parse_index(reader) {
                    Ok(entries) => row_hash(entries.iter().map(qts::IndexEntry::fields)),
                    Err(qts::Error::SmallIndex) => {
                        json!({"error": format!("ValueError: QtsVFS index is too small: {path}")})
                    }
                    Err(qts::Error::MissingEntries) => {
                        json!({"error": format!("ValueError: No QtsVFS entries found in {path}")})
                    }
                    Err(err) => return Err(err.into()),
                }
            } else {
                let reserved = args[1].as_bool().ok_or("missing reserved flag")?;
                match qts::chunk_slots(reader, reserved) {
                    Ok(slots) => row_hash(slots.iter().map(qts::ChunkSlot::fields)),
                    Err(qts::Error::EmptyShard) => {
                        json!({"error": "ValueError: cannot mmap an empty file"})
                    }
                    Err(err) => return Err(err.into()),
                }
            }
        }
        "validate_translation" => {
            let source = args[0].as_str().ok_or("missing source string")?;
            json!({"ok": hokace_core::translation::validate_translation(source, args[1].as_str())})
        }
        "adaptive.fields" | "protobuf_i18n._fields" => {
            let mut hash = Sha256::new();
            let result = if name == "adaptive.fields" {
                walk(data, &mut hash, true)
            } else {
                wire_fields(data, &mut hash)
            };
            hash_result(hash, result)
        }
        "protobuf_i18n.parse_i18n" => {
            match protobuf::parse_i18n(data, args[0].as_bool().ok_or("missing strict flag")?) {
                Ok(records) => {
                    let mut hash = Sha256::new();
                    for record in &records {
                        bytes(&mut hash, record.key.as_bytes());
                        bytes(&mut hash, record.translation.as_bytes());
                    }
                    json!({"ok": [records.len(), hex(&hash.finalize())]})
                }
                Err(err) => json!({"error": error(&err)}),
            }
        }
        "protobuf_i18n.serialize_i18n" => {
            let mut records = Vec::new();
            while !data.is_empty() {
                records.push(Record {
                    key: read_string(&mut data)?,
                    translation: read_string(&mut data)?,
                });
            }
            let hash = Sha256::digest(protobuf::serialize_i18n(records));
            json!({"ok": hex(&hash)})
        }
        "protobuf_i18n.decode_varint" => {
            let offset = args[0].as_i64().ok_or("missing offset")?;
            match protobuf::decode_varint_at(data, offset.into()) {
                Ok((value, end)) => json!({"ok": [value.to_string(), i64::try_from(end)?]}),
                Err(err) => json!({"error": error(&err)}),
            }
        }
        "protobuf_i18n.encode_varint" => {
            let number = args[0].as_str().ok_or("missing integer")?;
            if number.starts_with('-') {
                json!({"error": error(&Error::NegativeVarint)})
            } else {
                let result = hex(&protobuf::encode_varint(number.parse()?));
                json!({"ok": result})
            }
        }
        _ => return Err(format!("unknown operation {name}").into()),
    })
}

fn row_hash<const N: usize>(rows: impl ExactSizeIterator<Item = [u64; N]>) -> Json {
    let mut hash = Sha256::new();
    let count = rows.len();
    for row in rows {
        for field in row {
            hash.update(field.to_le_bytes());
        }
    }
    json!({"ok": [count, hex(&hash.finalize())]})
}

fn check(dir: &Path) -> Result<usize, Box<dyn std::error::Error>> {
    let calls = BufReader::new(fs::File::open(dir.join("calls.jsonl"))?);
    let mut counts = BTreeMap::new();
    let mut mismatches = 0;
    let mut catalogs = HashMap::new();
    let mut loaded = HashMap::new();
    for (index, line) in calls.lines().enumerate() {
        let call: Json = serde_json::from_str(&line?)?;
        let name = call["fn"].as_str().ok_or("missing operation")?;
        let data = call["input"]
            .as_str()
            .map(|file| fs::read(dir.join("blobs").join(file)))
            .transpose()?
            .unwrap_or_default();
        let args = &call["args"];
        let actual = if let Some(result) = scan_case(name, args, &data, &mut loaded)? {
            result
        } else if let Some(result) = catalog_case(name, args, &data, &mut loaded)? {
            result
        } else if name == "translate_table" {
            let snapshot = args[1].as_str().ok_or("missing catalog snapshot")?;
            if !catalogs.contains_key(snapshot) {
                let (unique, context, updates) =
                    serde_json::from_slice(&fs::read(dir.join("blobs").join(snapshot))?)?;
                let context: Vec<_> = context;
                let updates: Vec<_> = updates;
                catalogs.insert(
                    snapshot.to_owned(),
                    Catalog::from_entries(unique, context, updates),
                );
            }
            let asset = args[0].as_str().ok_or("missing asset")?.parse()?;
            let build = args[2].as_bool().ok_or("missing build flag")?;
            match translation::translate_table(&data, asset, &catalogs[snapshot], build) {
                Ok(result) => {
                    let digest = result.output.map(|out| hex(&Sha256::digest(out)));
                    json!({"ok": [digest, json!(result.counts)]})
                }
                Err(err) => json!({"error": format!("{}: {err}", err.python_class())}),
            }
        } else {
            replay(name, args, &data)?
        };
        if actual == call["result"] {
            *counts.entry(name.to_owned()).or_insert(0) += 1;
        } else {
            if mismatches < 15 {
                eprintln!(
                    "{}:{} {name} expected {}, got {actual}",
                    dir.display(),
                    index + 1,
                    call["result"]
                );
            }
            mismatches += 1;
        }
    }
    println!("{}: {counts:?}, {mismatches} mismatches", dir.display());
    if counts.is_empty() && mismatches == 0 {
        return Err("recording contains no cases".into());
    }
    Ok(mismatches)
}

/// `runtime_tap.catalog_state`: each map in its order, each set sorted.
fn catalog_state(catalog: &CatalogData) -> Result<String, Box<dyn std::error::Error>> {
    fn section(hash: &mut Sha256, tag: &[u8], items: Vec<Vec<u8>>) {
        hash.update(tag);
        hash.update((items.len() as u64).to_le_bytes());
        for item in items {
            hash.update(item);
        }
    }
    fn texts(parts: &[&str]) -> Vec<u8> {
        let mut out = Vec::new();
        for part in parts {
            out.extend((part.len() as u64).to_le_bytes());
            out.extend(part.as_bytes());
        }
        out
    }
    let mut hash = Sha256::new();
    section(
        &mut hash,
        b"U",
        catalog.unique.iter().map(|(k, v)| texts(&[k, v])).collect(),
    );
    section(
        &mut hash,
        b"C",
        catalog
            .context
            .iter()
            .map(|((a, k, s), t)| texts(&[a, k, s, t]))
            .collect(),
    );
    section(
        &mut hash,
        b"E",
        catalog
            .english_updates
            .iter()
            .map(|(id, t)| texts(&[&id.0, &id.1, &id.2, t, &catalog.english_sources[id]]))
            .collect(),
    );
    let mut known: Vec<_> = catalog.known.iter().copied().collect();
    known.sort_unstable();
    section(
        &mut hash,
        b"K",
        known.iter().map(|h| h.to_le_bytes().to_vec()).collect(),
    );
    let mut graphics = Vec::new();
    for (h, entry) in &catalog.graphics {
        let mut item = h.to_le_bytes().to_vec();
        item.extend(texts(&[&serde_json::to_string(entry)?]));
        graphics.push(item);
    }
    section(&mut hash, b"G", graphics);
    let mut targets: Vec<_> = catalog.targets.iter().collect();
    targets.sort_unstable();
    section(
        &mut hash,
        b"T",
        targets.iter().map(|t| texts(&[t])).collect(),
    );
    Ok(hex(&hash.finalize()))
}

fn py_error(error: &scan::PyError) -> Json {
    json!({"error": error.to_string()})
}

fn skips(skipped: &[scan::Skip]) -> Json {
    skipped
        .iter()
        .map(|skip| match &skip.asset {
            None => json!({"package": skip.package, "reason": skip.reason}),
            Some(asset) => json!({"package": skip.package, "asset": asset, "reason": skip.reason}),
        })
        .collect()
}

fn files_under(root: &Path, dir: &Path, out: &mut Vec<(String, String)>) -> std::io::Result<()> {
    if !dir.is_dir() {
        return Ok(());
    }
    for item in fs::read_dir(dir)? {
        let path = item?.path();
        if path.is_dir() {
            files_under(root, &path, out)?;
        } else {
            let relative = path
                .strip_prefix(root)
                .unwrap_or(&path)
                .display()
                .to_string();
            out.push((relative, hex(&Sha256::digest(fs::read(&path)?))));
        }
    }
    Ok(())
}

/// The `--scan-runtime` cases: `adaptive.discover` and `adaptive.scan`.
fn scan_case(
    name: &str,
    args: &Json,
    data: &[u8],
    loaded: &mut HashMap<Vec<u8>, Result<CatalogData, CatalogError>>,
) -> Result<Option<Json>, Box<dyn std::error::Error>> {
    if !matches!(name, "adaptive.discover" | "adaptive.scan") {
        return Ok(None);
    }
    if !loaded.contains_key(data) {
        let value: Json = serde_json::from_slice(data)?;
        loaded.insert(data.to_vec(), CatalogData::from_value(&value));
    }
    let catalog = loaded[data]
        .as_ref()
        .map_err(|err| format!("scan on a refused catalog: {err}"))?;
    let game = Path::new(args[1].as_str().ok_or("missing game")?);
    if name == "adaptive.discover" {
        return Ok(Some(match scan::discover(game, catalog) {
            Ok((packages, skipped)) => {
                let packages: Vec<Json> = packages
                    .iter()
                    .map(|p| {
                        let hashes: Vec<String> =
                            p.entries.keys().map(|h| format!("{h:016X}")).collect();
                        json!([
                            p.package_id,
                            p.index_path.display().to_string(),
                            p.shard_paths
                                .iter()
                                .map(|s| s.display().to_string())
                                .collect::<Vec<_>>(),
                            hex(&Sha256::digest(hashes.join(",")))
                        ])
                    })
                    .collect();
                json!({"ok": [packages, skips(&skipped)]})
            }
            Err(err) => py_error(&err),
        }));
    }
    let assets = Path::new(args[2].as_str().ok_or("missing assets folder")?);
    let materialize = args[3].as_bool().ok_or("missing materialize flag")?;
    let work = env::temp_dir().join(format!("hokace-scan-replay-{}", std::process::id()));
    if work.exists() {
        fs::remove_dir_all(&work)?;
    }
    let text = catalog.text_view();
    let result = match scan::scan(game, assets, catalog, &text, &work, materialize) {
        Ok(report) => {
            let mut written = Vec::new();
            files_under(&work, &work, &mut written)?;
            written.sort();
            let plans: Vec<Json> = report
                .plans
                .iter()
                .map(|plan| {
                    let per_asset: Vec<Json> = plan
                        .per_asset
                        .iter()
                        .map(|(h, counts)| json!([format!("{h:016X}"), counts]))
                        .collect();
                    let replacements = plan
                        .replacements
                        .strip_prefix(&work)
                        .unwrap_or(&plan.replacements);
                    json!([
                        plan.package.package_id,
                        replacements.display().to_string(),
                        per_asset
                    ])
                })
                .collect();
            json!({"ok": {
                "plans": plans,
                "fingerprints": report.fingerprints.iter().map(|(k, v)| json!([k, v])).collect::<Vec<_>>(),
                "total": report.total.iter().map(|(k, v)| json!([k, v])).collect::<Vec<_>>(),
                "skipped": skips(&report.skipped),
                "written": written.iter().map(|(p, h)| json!([p, h])).collect::<Vec<_>>(),
                "fallbacks": report.fallbacks.iter().map(|(p, r)| json!([p, r])).collect::<Vec<_>>(),
            }})
        }
        Err(err) => py_error(&err),
    };
    if work.exists() {
        fs::remove_dir_all(&work)?;
    }
    Ok(Some(result))
}

/// The `--catalog` cases: `adaptive.Catalog`, its `lookup`, and `load_catalog`.
fn catalog_case(
    name: &str,
    args: &Json,
    data: &[u8],
    loaded: &mut HashMap<Vec<u8>, Result<CatalogData, CatalogError>>,
) -> Result<Option<Json>, Box<dyn std::error::Error>> {
    let state =
        |result: &Result<CatalogData, CatalogError>| -> Result<Json, Box<dyn std::error::Error>> {
            Ok(match result {
                Ok(catalog) => json!({"ok": catalog_state(catalog)?}),
                Err(err) => json!({"error": err.to_string()}),
            })
        };
    Ok(Some(match name {
        "adaptive.load_catalog" => state(&catalog::load_catalog(Path::new(
            args[0].as_str().ok_or("missing folder")?,
        )))?,
        "adaptive.Catalog" | "adaptive.Catalog.lookup" => {
            if !loaded.contains_key(data) {
                let value: Json = serde_json::from_slice(data)?;
                loaded.insert(data.to_vec(), CatalogData::from_value(&value));
            }
            let built = &loaded[data];
            if name == "adaptive.Catalog" {
                state(built)?
            } else {
                let catalog = built
                    .as_ref()
                    .map_err(|err| format!("lookup on a refused catalog: {err}"))?;
                let asset: i128 = args[1].as_str().ok_or("missing asset")?.parse()?;
                let (key, source) = (
                    args[2].as_str().ok_or("missing key")?,
                    args[3].as_str().ok_or("missing source")?,
                );
                json!({"ok": catalog.lookup(asset, key, source)})
            }
        }
        _ => return Ok(None),
    }))
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut dirs = env::args_os().skip(1).peekable();
    if dirs.peek().is_none() {
        return Err("usage: runtime_replay <recording> ...".into());
    }
    let mut mismatches = 0;
    for dir in dirs {
        mismatches += check(Path::new(&dir))?;
    }
    if mismatches > 0 {
        return Err(format!("{mismatches} mismatches").into());
    }
    Ok(())
}
