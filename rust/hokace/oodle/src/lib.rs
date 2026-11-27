//! Oodle Leviathan decoding for the game's package shards.
//!
//! The reader follows `Kraken_ParseHeader`, `Kraken_ParseQuantumHeader`, and the
//! block dispatch in [ooz](https://github.com/powzix/ooz/blob/master/kraken.cpp).
//! Ooz copyright (C) 2016, Powzix. GPL-3.0-or-later, see
//! `android/native/licenses/GPL-3.0.txt` in this repository.

mod decoder;
mod error;
mod leviathan;

use decoder::Core;

const BLOCK_SIZE: usize = 256 * 1024;
const LEVIATHAN: u8 = 12;

/// An invalid Oodle chunk or a failed output allocation.
#[derive(Debug)]
pub struct DecodeError(String);

impl std::fmt::Display for DecodeError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for DecodeError {}

impl From<&'static str> for DecodeError {
    fn from(message: &'static str) -> Self {
        Self(message.into())
    }
}

/// The payload of one Oodle block, decoded separately from its headers.
#[derive(Debug, PartialEq, Eq)]
pub enum Block<'a> {
    Raw(&'a [u8]),
    Fill(u8),
    Compressed(&'a [u8]),
}

/// Visit each checksum-free Leviathan block with its expected output length.
pub fn visit_blocks<'a>(
    input: &'a [u8],
    raw_size: usize,
    visit: impl FnMut(Block<'a>, usize) -> Result<(), &'static str>,
) -> Result<(), &'static str> {
    walk_blocks(input, raw_size, visit)
}

fn walk_blocks<'a, E: From<&'static str>>(
    mut input: &'a [u8],
    mut remaining: usize,
    mut visit: impl FnMut(Block<'a>, usize) -> Result<(), E>,
) -> Result<(), E> {
    while remaining != 0 {
        let size = remaining.min(BLOCK_SIZE);
        let block = read_block(&mut input, size)?;
        visit(block, size)?;
        remaining -= size;
    }
    if !input.is_empty() {
        return Err("trailing data after Oodle blocks".into());
    }
    Ok(())
}

/// Decode a checksum-free Leviathan chunk to the exact size in its QTS slot.
pub fn decode(input: &[u8], raw_size: usize) -> Result<Vec<u8>, DecodeError> {
    if raw_size.div_ceil(BLOCK_SIZE) > input.len() / 2 {
        return Err("missing Oodle block headers for the requested size".into());
    }
    let mut output = Vec::new();
    output
        .try_reserve_exact(raw_size)
        .map_err(|_| "could not allocate Oodle output")?;
    output.resize(raw_size, 0);
    let mut buffers = None;
    let mut offset = 0;
    walk_blocks(input, raw_size, |block, size| {
        let end = offset + size;
        match block {
            Block::Raw(bytes) => output[offset..end].copy_from_slice(bytes),
            Block::Fill(value) => output[offset..end].fill(value),
            Block::Compressed(payload) => {
                let (scratch, tmp) =
                    buffers.get_or_insert_with(|| (vec![0; BLOCK_SIZE], vec![0; BLOCK_SIZE]));
                // The dictionary includes earlier blocks in the same QTS chunk.
                let consumed = Core::new(payload, &mut output, scratch, tmp, offset, size)
                    .decode_quantum()
                    .map_err(|error| DecodeError(error.to_string()))?;
                if consumed != payload.len() {
                    return Err(DecodeError::from(
                        "Leviathan quantum did not consume its payload",
                    ));
                }
            }
        }
        offset = end;
        Ok(())
    })?;
    Ok(output)
}

fn take<'a>(input: &mut &'a [u8], len: usize) -> Result<&'a [u8], &'static str> {
    let (bytes, rest) = input.split_at_checked(len).ok_or("truncated Oodle block")?;
    *input = rest;
    Ok(bytes)
}

fn read_block<'a>(input: &mut &'a [u8], raw_size: usize) -> Result<Block<'a>, &'static str> {
    let [flags, codec] = *input
        .split_first_chunk::<2>()
        .ok_or("truncated Oodle header")?
        .0;
    *input = &input[2..];
    if flags & 0x3f != 0x0c || codec != LEVIATHAN {
        return Err("expected a checksum-free Leviathan header");
    }
    if flags & 0x40 != 0 {
        return Ok(Block::Raw(take(input, raw_size)?));
    }

    let header = take(input, 3)?;
    let value = u32::from_be_bytes([0, header[0], header[1], header[2]]) as usize;
    let size = (value & (BLOCK_SIZE - 1)) + 1;
    if size == BLOCK_SIZE {
        if value >> 18 == 1 {
            return Ok(Block::Fill(take(input, 1)?[0]));
        }
        return Err("unsupported Oodle special quantum");
    }
    if size > raw_size {
        return Err("Oodle quantum exceeds block output size");
    }
    let payload = take(input, size)?;
    if size == raw_size {
        Ok(Block::Raw(payload))
    } else {
        Ok(Block::Compressed(payload))
    }
}

/// Keep the Oodle container around relocated bytes without compressing them.
pub fn encode_stored(raw: &[u8]) -> Vec<u8> {
    let mut encoded = Vec::with_capacity(raw.len() + 2 * raw.len().div_ceil(BLOCK_SIZE));
    for block in raw.chunks(BLOCK_SIZE) {
        encoded.extend_from_slice(&[0xcc, LEVIATHAN]);
        encoded.extend_from_slice(block);
    }
    encoded
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stored_blocks_end_at_the_requested_size() {
        let raw: Vec<u8> = (0..BLOCK_SIZE + 3)
            .map(|index| (index % 251) as u8)
            .collect();
        let encoded = encode_stored(&raw);
        assert_eq!(&encoded[..2], &[0xcc, 12]);
        assert_eq!(&encoded[BLOCK_SIZE + 2..BLOCK_SIZE + 4], &[0xcc, 12]);
        let mut blocks = raw.chunks(BLOCK_SIZE);
        visit_blocks(&encoded, raw.len(), |block, size| {
            let expected = blocks.next().unwrap();
            assert_eq!(size, expected.len());
            assert_eq!(block, Block::Raw(expected));
            Ok(())
        })
        .unwrap();
        assert!(blocks.next().is_none());
        assert!(visit_blocks(&encoded, raw.len() - 1, |_, _| Ok(())).is_err());
        assert!(visit_blocks(&encoded, raw.len() + 1, |_, _| Ok(())).is_err());
    }

    #[test]
    fn quantum_header_distinguishes_fill_raw_and_compressed() {
        for (input, expected) in [
            (&[0x8c, 12, 7, 255, 255, 12][..], Block::Fill(12)),
            (&[0x0c, 12, 0, 0, 2, 1, 2, 3], Block::Raw(&[1, 2, 3])),
            (&[0x8c, 12, 0, 0, 1, 1, 2], Block::Compressed(&[1, 2])),
        ] {
            visit_blocks(input, 3, |block, size| {
                assert_eq!(size, 3);
                assert_eq!(block, expected);
                Ok(())
            })
            .unwrap();
        }
    }

    #[test]
    fn decodes_an_entropy_only_quantum() {
        // The RLE stream stores one byte and expands it to 64 bytes.
        let input = [0x8c, 12, 0, 0, 5, 0x30, 0, 0xfc, 0, 1, 42];
        assert_eq!(decode(&input, 64).unwrap(), [42; 64]);
        for len in 0..input.len() {
            assert!(decode(&input[..len], 64).is_err());
        }
        for size in [0, 1, 63, 65, usize::MAX] {
            assert!(decode(&input, size).is_err());
        }
    }
}
