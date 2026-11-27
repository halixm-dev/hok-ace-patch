//! QtsVFS index and shard readers for the runtime's package format.

use std::collections::{BTreeMap, HashMap, HashSet};
use std::fs::File;
use std::io::{self, BufReader, Read, Seek, SeekFrom};
use std::path::PathBuf;

const BASE_DATA_OFFSET: u64 = 106_496;
const MIN_ENTRY_SIZE: u64 = 48;

#[derive(Debug, PartialEq, Eq, Hash)]
pub struct IndexEntry {
    pub file_hash: u64,
    pub compression: u16,
    pub chunk_size: u32,
    pub entry_offset: u64,
    pub entry_size: u32,
    pub head_size: u32,
}

#[derive(Debug, PartialEq, Eq, Hash)]
pub struct ChunkSlot {
    pub file_hash: u64,
    pub chunk_id: u32,
    pub uncompressed_size: u32,
    pub compressed_size: u32,
    pub slot_offset: u64,
    pub slot_size: u32,
    pub payload_offset: u64,
    pub trailer_offset: u64,
    pub hash1: u64,
    pub header_flags: u32,
    pub reserved: u32,
}

#[derive(Debug)]
pub enum Error {
    Io(io::Error),
    SmallIndex,
    MissingEntries,
    EmptyShard,
}

impl From<io::Error> for Error {
    fn from(err: io::Error) -> Self {
        Self::Io(err)
    }
}

impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Io(err) => err.fmt(f),
            Self::SmallIndex => f.write_str("QtsVFS index is too small"),
            Self::MissingEntries => f.write_str("No QtsVFS entries found"),
            Self::EmptyShard => f.write_str("cannot mmap an empty file"),
        }
    }
}

impl std::error::Error for Error {}

impl IndexEntry {
    pub fn fields(&self) -> [u64; 6] {
        [
            self.file_hash,
            self.compression.into(),
            self.chunk_size.into(),
            self.entry_offset,
            self.entry_size.into(),
            self.head_size.into(),
        ]
    }
}

impl ChunkSlot {
    pub fn fields(&self) -> [u64; 11] {
        [
            self.file_hash,
            self.chunk_id.into(),
            self.uncompressed_size.into(),
            self.compressed_size.into(),
            self.slot_offset,
            self.slot_size.into(),
            self.payload_offset,
            self.trailer_offset,
            self.hash1,
            self.header_flags.into(),
            self.reserved.into(),
        ]
    }
}

struct Database<R> {
    reader: BufReader<R>,
    len: u64,
    position: u64,
}

impl<R: Read + Seek> Database<R> {
    fn new(mut reader: R) -> io::Result<Self> {
        let len = reader.seek(SeekFrom::End(0))?;
        Ok(Self {
            reader: BufReader::with_capacity(64 * 1024, reader),
            len,
            position: len,
        })
    }

    fn read<const N: usize>(&mut self, offset: u64) -> io::Result<[u8; N]> {
        let mut bytes = [0; N];
        let diff = offset as i128 - self.position as i128;
        if let Ok(diff) = i64::try_from(diff) {
            self.reader.seek_relative(diff)?;
        } else {
            self.reader.seek(SeekFrom::Start(offset))?;
        }
        self.reader.read_exact(&mut bytes)?;
        self.position = offset + N as u64;
        Ok(bytes)
    }

    fn stopper(&mut self) -> io::Result<u64> {
        Ok(u64::from(u32::from_le_bytes(self.read(8)?)).min(self.len))
    }

    fn header(&mut self, pos: u64) -> io::Result<Option<u32>> {
        let [a, b, c, d, e, f, g, h, i, j, k, l] = self.read(pos)?;
        let offset = u32::from_le_bytes([a, b, c, d]);
        let marker = i32::from_le_bytes([e, f, g, h]);
        let size = u32::from_le_bytes([i, j, k, l]);
        Ok((u64::from(offset) == pos && marker == -1).then_some(size))
    }

    fn first(&mut self, stopper: u64, max_size: u64) -> io::Result<Option<u64>> {
        let limit = stopper.min(BASE_DATA_OFFSET + 16_384);
        for pos in (BASE_DATA_OFFSET..limit.saturating_sub(32)).step_by(4) {
            if let Some(size) = self.header(pos)?.map(u64::from)
                && (MIN_ENTRY_SIZE..=max_size).contains(&size)
                && pos + size <= self.len
            {
                return Ok(Some(pos));
            }
        }
        Ok(None)
    }

    fn next_entry(&mut self, mut pos: u64, stopper: u64) -> io::Result<Option<(u64, u32)>> {
        while pos + MIN_ENTRY_SIZE <= stopper {
            if let Some(size) = self.header(pos)?
                && u64::from(size) >= MIN_ENTRY_SIZE
                && pos + u64::from(size) <= stopper
            {
                return Ok(Some((pos, size)));
            }
            pos += 4;
        }
        Ok(None)
    }
}

/// Reads entries in Python dictionary order. Repeated hashes replace their earlier value.
pub fn parse_index(reader: impl Read + Seek) -> Result<Vec<IndexEntry>, Error> {
    let mut db = Database::new(reader)?;
    if db.len < BASE_DATA_OFFSET {
        return Err(Error::SmallIndex);
    }
    let stopper = db.stopper()?;
    let start = db.first(stopper, 4096)?.ok_or(Error::MissingEntries)?;
    let mut entries = Vec::new();
    let mut by_hash = HashMap::new();
    scan_entries(&mut db, start, stopper, |db, pos, entry_size| {
        let head_size = u32::from_le_bytes(db.read(pos + 24)?);
        let hash_offset = 28 + u64::from(head_size);
        if (48..=96).contains(&head_size) && hash_offset + 8 <= u64::from(entry_size) {
            let at = pos + hash_offset;
            let file_hash = u64::from_le_bytes(db.read(at)?);
            if file_hash != 0 {
                let entry = IndexEntry {
                    file_hash,
                    compression: u16::from_le_bytes(db.read(at - 8)?),
                    chunk_size: u32::from_le_bytes(db.read(at - 4)?),
                    entry_offset: pos,
                    entry_size,
                    head_size,
                };
                let index = *by_hash.entry(file_hash).or_insert(entries.len());
                if index == entries.len() {
                    entries.push(entry);
                } else {
                    entries[index] = entry;
                }
            }
        }
        Ok(())
    })?;
    Ok(entries)
}

fn scan_entries<R: Read + Seek>(
    db: &mut Database<R>,
    mut pos: u64,
    stopper: u64,
    mut visit: impl FnMut(&mut Database<R>, u64, u32) -> io::Result<()>,
) -> io::Result<()> {
    while let Some((offset, size)) = db.next_entry(pos, stopper)? {
        visit(db, offset, size)?;
        pos = offset + u64::from(size);
    }
    Ok(())
}

/// Records the chosen trailer for each shard slot. The payload stays on disk.
pub fn chunk_slots(
    reader: impl Read + Seek,
    include_reserved: bool,
) -> Result<Vec<ChunkSlot>, Error> {
    let mut db = Database::new(reader)?;
    if db.len == 0 {
        return Err(Error::EmptyShard);
    }
    if db.len < BASE_DATA_OFFSET {
        return Ok(Vec::new());
    }
    let stopper = db.stopper()?;
    let Some(start) = db.first(stopper, db.len)? else {
        return Ok(Vec::new());
    };
    let mut slots = Vec::new();
    scan_entries(&mut db, start, stopper, |db, pos, slot_size| {
        let compressed_size_raw = u32::from_le_bytes(db.read(pos + 24)?);
        let Some(compressed_size) = compressed_size_raw.checked_sub(4) else {
            return Ok(());
        };
        let payload_offset = pos + 32;
        let aligned_trailer = (payload_offset + u64::from(compressed_size)).next_multiple_of(4);
        let end_trailer = pos + u64::from(slot_size) - 16;
        for trailer_offset in [aligned_trailer, end_trailer] {
            if !(payload_offset..=end_trailer).contains(&trailer_offset) {
                continue;
            }
            let file_hash = u64::from_le_bytes(db.read(trailer_offset)?);
            let reserved = u32::from_le_bytes(db.read(trailer_offset + 8)?);
            if file_hash != 0 && (reserved == 0 || (include_reserved && reserved == 1)) {
                slots.push(ChunkSlot {
                    file_hash,
                    chunk_id: u32::from_le_bytes(db.read(trailer_offset + 12)?),
                    uncompressed_size: u32::from_le_bytes(db.read(pos + 28)?),
                    compressed_size,
                    slot_offset: pos,
                    slot_size,
                    payload_offset,
                    trailer_offset,
                    hash1: u64::from_le_bytes(db.read(pos + 12)?),
                    header_flags: u32::from_le_bytes(db.read(pos + 20)?),
                    reserved,
                });
                break;
            }
        }
        Ok(())
    })?;
    Ok(slots)
}

const KEYS_TO_POSITIONS: usize = 2040;
const LEAF_FOOTER: usize = 4092;
const LEAF_TAG: u32 = 3 << 16;
const PAGE_SIZE: usize = 4096;

/// The payload coordinates used by the runtime's package extraction method.
pub struct Payload {
    pub path: PathBuf,
    pub offset: u64,
    pub compressed_size: u32,
    pub uncompressed_size: u32,
}

#[derive(Debug)]
pub enum ExtractError {
    Io(io::Error),
    MissingChunks,
    ShortRead(PathBuf),
    UnsupportedCompression(u16),
    Decompression,
    UnexpectedSize(u32),
}

/// Read consecutive chunks starting at zero, using the entry's declared codec.
pub fn extract(compression: u16, chunks: &HashMap<u32, Payload>) -> Result<Vec<u8>, ExtractError> {
    if !chunks.contains_key(&0) {
        return Err(ExtractError::MissingChunks);
    }
    let mut result = Vec::new();
    for chunk_id in 0..=u32::MAX {
        let Some(chunk) = chunks.get(&chunk_id) else {
            break;
        };
        let mut file = File::open(&chunk.path).map_err(ExtractError::Io)?;
        file.seek(SeekFrom::Start(chunk.offset))
            .map_err(ExtractError::Io)?;
        let mut payload = Vec::new();
        file.take(chunk.compressed_size.into())
            .read_to_end(&mut payload)
            .map_err(ExtractError::Io)?;
        if payload.len() != chunk.compressed_size as usize {
            return Err(ExtractError::ShortRead(chunk.path.clone()));
        }
        let size = chunk.uncompressed_size as usize;
        let raw = match compression {
            0 => payload,
            1 => hokace_codecs::lz4::decompress(&payload, size)
                .map_err(|_| ExtractError::Decompression)?,
            other => return Err(ExtractError::UnsupportedCompression(other)),
        };
        if raw.len() != size {
            return Err(ExtractError::UnexpectedSize(chunk_id));
        }
        result.extend(raw);
    }
    Ok(result)
}

fn live_offsets(db: &mut Database<impl Read + Seek>) -> io::Result<HashMap<u32, HashSet<u32>>> {
    let table = u64::from(u32::from_le_bytes(db.read(0x30)?));
    let rows = u64::from(u32::from_le_bytes(db.read(table + 4)?));
    let mut offsets = HashMap::<u32, HashSet<u32>>::new();
    let mut found_leaf = false;
    for row in 0..rows {
        let at = table + 24 + row * 24;
        let logical = u32::from_le_bytes(db.read(at)?);
        let active = u64::from(u32::from_le_bytes(db.read(at + 4)?));
        let page = db.read::<PAGE_SIZE>(active)?;
        let tag = word_at(&page, LEAF_FOOTER).unwrap_or_default();
        if tag & 0xffff_0000 != LEAF_TAG || word_at(&page, PAGE_SIZE - 16) != Some(logical) {
            continue;
        }
        found_leaf = true;
        let count = (tag & 0xffff) as usize;
        if KEYS_TO_POSITIONS + count * 4 > PAGE_SIZE {
            return Err(io::Error::other("invalid B-tree leaf count"));
        }
        for (key, value) in words(&page)
            .zip(words(&page[KEYS_TO_POSITIONS..]))
            .take(count)
        {
            offsets.entry(key).or_default().insert(value);
        }
    }
    if !found_leaf {
        return Err(io::Error::other("no active B-tree leaf pages found"));
    }
    Ok(offsets)
}

/// Find replacements for stock slots whose B-tree entries point elsewhere.
///
/// Multiple valid replacements depend on Python's set iteration order. Signal those
/// to the caller so it can use the reference selection for that shard.
pub fn live_replacements(
    mut reader: impl Read + Seek,
    stock: impl IntoIterator<Item = (u64, u32, u64, u32)>,
) -> Result<Vec<ChunkSlot>, Error> {
    let live = live_offsets(&mut Database::new(&mut reader)?)?;
    let mut candidates = None;
    let mut replacements = Vec::new();
    for (file_hash, chunk_id, offset, key) in stock {
        let Some(positions) = live.get(&key) else {
            continue;
        };
        if u32::try_from(offset).is_ok_and(|offset| positions.contains(&offset)) {
            continue;
        }
        if candidates.is_none() {
            let slots: HashMap<_, _> = chunk_slots(&mut reader, false)?
                .into_iter()
                .map(|slot| (slot.slot_offset, slot))
                .collect();
            candidates = Some(slots);
        }
        let Some(candidates) = &mut candidates else {
            continue;
        };
        let mut matches = positions.iter().filter_map(|&offset| {
            let offset = u64::from(offset);
            let candidate = candidates.get(&offset)?;
            (candidate.file_hash == file_hash && candidate.chunk_id == chunk_id).then_some(offset)
        });
        if let Some(offset) = matches.next() {
            if matches.next().is_some() {
                return Err(io::Error::other("multiple live slots for one chunk").into());
            }
            if let Some(slot) = candidates.remove(&offset) {
                replacements.push(slot);
            }
        }
    }
    Ok(replacements)
}

fn words(data: &[u8]) -> impl Iterator<Item = u32> {
    data.as_chunks::<4>()
        .0
        .iter()
        .copied()
        .map(u32::from_le_bytes)
}

fn word_at(data: &[u8], offset: usize) -> Option<u32> {
    words(data.get(offset..)?).next()
}

/// Finds the aligned references in runs that have a corresponding sorted, nonzero key array.
pub fn find_position_references(
    data: &[u8],
    positions: &HashSet<u32>,
    wanted: impl IntoIterator<Item = u32>,
) -> BTreeMap<u32, Vec<usize>> {
    let mut references: BTreeMap<_, Vec<_>> = wanted
        .into_iter()
        .map(|value| (value, Vec::new()))
        .collect();
    if positions.len() < 14 || references.is_empty() {
        return references;
    }
    let mut start = None;
    // Include a boundary for a run that reaches the very end.
    for (index, value) in words(data).chain([0]).enumerate() {
        let offset = index * 4;
        if offset + 4 <= data.len() && positions.contains(&value) {
            start.get_or_insert(offset);
            continue;
        }
        let Some(start) = start.take() else { continue };
        let Some(keys) = start.checked_sub(KEYS_TO_POSITIONS) else {
            continue;
        };
        if offset - start < 14 * 4 {
            continue;
        }
        let mut previous = 0;
        let sorted = words(&data[keys..offset - KEYS_TO_POSITIONS]).all(|key| {
            let sorted = key >= previous;
            previous = key;
            sorted
        });
        if sorted && previous != 0 {
            for (index, position) in words(&data[start..offset]).enumerate() {
                if let Some(entries) = references.get_mut(&position) {
                    entries.push(start + index * 4);
                }
            }
        }
    }
    references
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Position {
    pub offset: u32,
    pub key: u32,
}

#[derive(Debug, PartialEq, Eq)]
pub struct PositionUpdate {
    pub position: Position,
    pub reference_offsets: Vec<usize>,
}

fn patch_position_page(
    trial: &mut [u8],
    positions: &HashSet<u32>,
    anchor_ref: usize,
    insert_after: bool,
    position: Position,
) -> Result<usize, &'static str> {
    let mut start = anchor_ref;
    while start >= 4 && word_at(trial, start - 4).is_some_and(|value| positions.contains(&value)) {
        start -= 4;
    }
    let mut end = anchor_ref + 4;
    while word_at(trial, end).is_some_and(|value| positions.contains(&value)) {
        end += 4;
    }
    let count = (end - start) / 4;
    let message = "unsupported or full position index page";
    let footer = start.checked_sub(KEYS_TO_POSITIONS).ok_or(message)? + LEAF_FOOTER;
    if word_at(trial, footer) != Some(LEAF_TAG | count as u32) || count >= 510 {
        return Err(message);
    }
    let mut reference = anchor_ref + if insert_after { 4 } else { 0 };
    let mut key_ref = reference - KEYS_TO_POSITIONS;
    let key_end = end - KEYS_TO_POSITIONS;
    if word_at(trial, end) == Some(0) && word_at(trial, key_end) == Some(0) {
        trial.copy_within(reference..end, reference + 4);
        trial.copy_within(key_ref..key_end, key_ref + 4);
    } else {
        let message = "segment has no insertion capacity";
        let leading_key = start.checked_sub(KEYS_TO_POSITIONS + 4).ok_or(message)?;
        if word_at(trial, start - 4) != Some(0) || word_at(trial, leading_key) != Some(0) {
            return Err(message);
        }
        trial.copy_within(start..reference, start - 4);
        trial.copy_within(start - KEYS_TO_POSITIONS..key_ref, leading_key);
        reference -= 4;
        key_ref -= 4;
    }
    trial[reference..reference + 4].copy_from_slice(&position.offset.to_le_bytes());
    trial[key_ref..key_ref + 4].copy_from_slice(&position.key.to_le_bytes());
    trial[footer..footer + 4].copy_from_slice(&(LEAF_TAG | (count + 1) as u32).to_le_bytes());
    Ok(reference)
}

/// Inserts each position into both copies of its leaf. A failed trial never changes the input.
pub fn insert_position_references(
    data: &mut [u8],
    existing: &[Position],
    added: &[Position],
) -> Result<Vec<PositionUpdate>, String> {
    let mut known = existing.to_vec();
    let mut offsets: HashSet<_> = existing.iter().map(|p| p.offset).collect();
    let mut updates = Vec::with_capacity(added.len());
    for &position in added {
        if known.iter().any(|p| p.key == position.key) {
            return Err(format!(
                "QtsVFS position key collision: {:08X}",
                position.key
            ));
        }
        let before = known
            .iter()
            .copied()
            .filter(|p| p.key < position.key)
            .min_by_key(|p| std::cmp::Reverse(p.key));
        let after = known
            .iter()
            .copied()
            .filter(|p| p.key > position.key)
            .min_by_key(|p| p.key);
        if before.is_none() && after.is_none() {
            return Err("Cannot insert into an empty QtsVFS position index".into());
        }
        let mut failures = Vec::new();
        for (anchor, insert_after) in [(before, true), (after, false)] {
            let Some(anchor) = anchor else { continue };
            let anchor_offset = anchor.offset;
            let mut trial = data.to_vec();
            let references = find_position_references(&trial, &offsets, [anchor_offset]);
            let refs = &references[&anchor_offset];
            if refs.len() != 2 {
                failures.push(format!("anchor {anchor_offset} has {} indexes", refs.len()));
                continue;
            }
            let inserted: Result<Vec<_>, _> = refs
                .iter()
                .map(|&reference| {
                    patch_position_page(&mut trial, &offsets, reference, insert_after, position)
                })
                .collect();
            let inserted = match inserted {
                Ok(inserted) => inserted,
                Err(err) => {
                    failures.push(format!("anchor {anchor_offset}: {err}"));
                    continue;
                }
            };
            let introduced = offsets.insert(position.offset);
            let found = find_position_references(&trial, &offsets, [position.offset]);
            if found[&position.offset] == inserted {
                data.copy_from_slice(&trial);
                known.push(position);
                updates.push(PositionUpdate {
                    position,
                    reference_offsets: inserted,
                });
                break;
            }
            if introduced {
                offsets.remove(&position.offset);
            }
            failures.push(format!("anchor {anchor_offset}: verification failed"));
        }
        if updates
            .last()
            .is_none_or(|update| update.position != position)
        {
            return Err(format!(
                "QtsVFS position index has no safe insertion point for slot {} key {:08X}: {}",
                position.offset,
                position.key,
                failures.join("; ")
            ));
        }
    }
    Ok(updates)
}
