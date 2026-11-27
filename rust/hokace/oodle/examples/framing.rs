//! Decode every Oodle chunk in a codec corpus and compare its hash with Python.
//!
//!     cargo run --release -p hokace-oodle --example framing -- <corpus.jsonl>

use std::fs::File;
use std::io::{BufRead, BufReader, Read, Seek, SeekFrom};

use hokace_oodle::decode;
use serde_json::Value;
use sha2::{Digest, Sha256};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let path = std::env::args_os()
        .nth(1)
        .ok_or("usage: framing <corpus.jsonl>")?;
    let mut lines = BufReader::new(File::open(path)?).lines();
    let header: Value = serde_json::from_str(&lines.next().ok_or("missing corpus header")??)?;
    let shards = header["shards"].as_array().ok_or("missing shards")?;
    let mut current = None;
    let mut input = Vec::new();
    let (mut chunks, mut matched_errors) = (0, 0);
    for line in lines {
        let entry: Value = serde_json::from_str(&line?)?;
        if entry["kind"] != "oodle" {
            continue;
        }
        let number = |key: &str| entry[key].as_u64().ok_or_else(|| format!("invalid {key}"));
        let index = usize::try_from(number("shard")?)?;
        let offset = number("offset")?;
        if !matches!(current, Some((open, _)) if open == index) {
            let shard = shards
                .get(index)
                .and_then(Value::as_str)
                .ok_or("invalid shard")?;
            current = Some((index, File::open(shard)?));
        }
        let (_, shard) = current.as_mut().ok_or("missing open shard")?;
        shard.seek(SeekFrom::Start(offset))?;
        input.resize(usize::try_from(number("size")?)?, 0);
        shard.read_exact(&mut input)?;

        chunks += 1;
        let result = decode(&input, usize::try_from(number("raw")?)?);
        match (result, entry["decoded"].as_str()) {
            (Ok(bytes), Some(expected)) if matches_hash(&bytes, expected) => {}
            (Err(_), None) => matched_errors += 1,
            (Err(error), Some(_)) => return Err(format!("shard {index} @{offset}: {error}").into()),
            _ => return Err(format!("shard {index} @{offset}: decoded output differs").into()),
        }
    }
    if chunks == 0 {
        return Err("no Oodle chunks in corpus".into());
    }
    println!("{chunks} Oodle chunks match Python ({matched_errors} matched decoding errors)");
    Ok(())
}

fn matches_hash(bytes: &[u8], expected: &str) -> bool {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let digest = Sha256::digest(bytes);
    let encoded: [u8; 64] = std::array::from_fn(|index| {
        let byte = digest[index / 2];
        let nibble = if index % 2 == 0 { byte >> 4 } else { byte & 15 };
        HEX[usize::from(nibble)]
    });
    expected.as_bytes() == encoded
}
