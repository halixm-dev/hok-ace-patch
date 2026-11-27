//! `tools/broken_list.py`: the game's own record of package assets its updater could not patch
//! (`Watchdog/BrokenList.db`), a QtsVFS shard of `u32` self offset, `-1`, `u32` payload size, `u64`
//! key and payload. A slot that does not read as a record is counted, never guessed at.

use std::collections::{BTreeMap, BTreeSet};
use std::io;
use std::path::Path;

pub const HEADER_MARK: &[u8] = b"qtsvfs-watchdog";
const SLOT: usize = 20;
const NAME_AT: usize = 64;

/// The assets the updater gave up on, by package name, and the slots that did not read.
#[derive(Debug, Default, PartialEq, Eq)]
pub struct BrokenList {
    pub assets: BTreeMap<String, BTreeSet<String>>,
    pub unreadable: u64,
}

impl BrokenList {
    pub fn empty(&self) -> bool {
        self.assets.is_empty() && self.unreadable == 0
    }
}

fn u32_at(data: &[u8], at: usize) -> u32 {
    u32::from_le_bytes(data[at..at + 4].try_into().expect("four bytes"))
}

/// `_record`: (package name, asset hash as 16 hex digits) of one record payload.
fn record(payload: &[u8]) -> Option<(String, String)> {
    if payload.len() < NAME_AT + 4 {
        return None;
    }
    let (header, body, length) = (
        u32_at(payload, 0),
        u32_at(payload, 4),
        u32_at(payload, NAME_AT) as usize,
    );
    let start = NAME_AT + 4;
    let name = &payload[start..(start + length).min(payload.len())];
    if header != 8
        || !(1..=10).contains(&length)
        || body as usize != 60 + length
        || name.len() != length
        || !name.iter().all(u8::is_ascii_digit)
    {
        return None;
    }
    let hash = u64::from_le_bytes(payload[16..24].try_into().expect("eight bytes"));
    Some((
        String::from_utf8(name.to_vec()).expect("ASCII digits"),
        format!("{hash:016X}"),
    ))
}

/// `read`: the records of <data>.
pub fn parse(data: &[u8]) -> BrokenList {
    let mut result = BrokenList::default();
    let mut offset = 0;
    while offset + SLOT <= data.len() {
        let (self_offset, marker, size) = (
            u32_at(data, offset),
            u32_at(data, offset + 4),
            u32_at(data, offset + 8),
        );
        let room = data.len() - offset - SLOT;
        if self_offset as usize == offset
            && marker == u32::MAX
            && size != 0
            && size as usize <= room
        {
            let payload = &data[offset + SLOT..offset + SLOT + size as usize];
            if !payload
                .windows(HEADER_MARK.len())
                .any(|window| window == HEADER_MARK)
            {
                match record(payload) {
                    Some((package, asset)) => {
                        result.assets.entry(package).or_default().insert(asset);
                    }
                    None => result.unreadable += 1,
                }
            }
        }
        offset += 4;
    }
    result
}

/// `read`: the records of <path>; an absent file reads as an empty list.
pub fn read(path: &Path) -> io::Result<BrokenList> {
    if !path.is_file() {
        return Ok(BrokenList::default());
    }
    Ok(parse(&std::fs::read(path)?))
}
