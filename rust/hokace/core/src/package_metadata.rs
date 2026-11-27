//! Reads package hashes from the PC edition's internal index.

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
