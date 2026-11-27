//! Replay exact codecs recorded by `rust/harness/codec_tap.py`.
//!
//!     cargo run --release -p hokace-codecs --example tap -- <tap-dir> ...

use std::collections::BTreeMap;
use std::fs;
use std::io::{BufRead, BufReader};
use std::path::Path;
use std::process::ExitCode;

use hokace_codecs::astc_encode::AstcEncoder;
use hokace_codecs::{lz4, png, texture};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

fn hex_digest(data: &[u8]) -> String {
    Sha256::digest(data)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn replay(record: &Value, input: &[u8], astc: &mut AstcEncoder) -> Result<Option<Vec<u8>>, String> {
    let args = &record["args"];
    let size = |index: usize| {
        args[index]
            .as_u64()
            .and_then(|n| usize::try_from(n).ok())
            .ok_or_else(|| format!("invalid dimension at argument {index}"))
    };
    let output = match record["fn"].as_str() {
        Some("decode_astc") => texture::decode_astc(input, size(0)?, size(1)?, size(2)?, size(3)?)?,
        Some("decode_pc") => texture::decode_pc(
            input,
            size(0)?,
            size(1)?,
            args[2].as_str().ok_or("invalid PC format")?,
        )?,
        Some("decode_png") => {
            let (width, height, rgba) = png::decode_rgba(input)?;
            if args != &json!([width, height]) {
                return Err(format!("PNG dimensions differ: {width}x{height}"));
            }
            rgba
        }
        Some("lz4.compress") => {
            if args
                != &json!([
                    [],
                    [
                        ["compression", 12],
                        ["mode", "high_compression"],
                        ["store_size", false]
                    ]
                ])
            {
                return Err(format!("unsupported LZ4 arguments: {args}"));
            }
            lz4::compress_hc12(input).map_err(|error| error.to_string())?
        }
        Some("encode_astc") => {
            let dim = |index: usize| {
                size(index).and_then(|n| u32::try_from(n).map_err(|error| error.to_string()))
            };
            astc.encode(input, dim(0)?, dim(1)?, dim(2)?, dim(3)?)?
        }
        _ => return Err(format!("unknown codec: {}", record["fn"])),
    };
    Ok(Some(output))
}

fn main() -> Result<ExitCode, Box<dyn std::error::Error>> {
    let mut dirs = std::env::args_os().skip(1).peekable();
    if dirs.peek().is_none() {
        return Err("usage: tap <tap-dir> ...".into());
    }
    let mut failed = false;
    for dir in dirs {
        let dir = Path::new(&dir);
        let calls = BufReader::new(fs::File::open(dir.join("calls.jsonl"))?);
        let mut counts: BTreeMap<String, [usize; 3]> = BTreeMap::new();
        // One encoder per tap, as one app run; calls replay in the tap's order.
        let threads = std::thread::available_parallelism().map_or(1, usize::from);
        let mut astc = AstcEncoder::new(threads);
        for line in calls.lines() {
            let record: Value = serde_json::from_str(&line?)?;
            let name = record["fn"].as_str().ok_or("missing codec name")?;
            let hash = record["input"].as_str().ok_or("missing input hash")?;
            let expected = record["output"].as_str().ok_or("missing output hash")?;
            let input = fs::read(dir.join("blobs").join(hash))?;
            let result = match replay(&record, &input, &mut astc) {
                Ok(Some(output)) if hex_digest(&output) == expected => 0,
                Ok(Some(_)) => {
                    eprintln!("{name} {hash}: output differs");
                    1
                }
                Err(error) => {
                    eprintln!("{name} {hash}: {error}");
                    1
                }
                Ok(None) => 2,
            };
            counts.entry(name.to_owned()).or_default()[result] += 1;
        }
        if counts.is_empty() {
            return Err(format!("{}: no codec calls", dir.display()).into());
        }
        for (name, [matching, differing, skipped]) in counts {
            println!(
                "{} {name}: {matching} match, {differing} differ, {skipped} skipped",
                dir.display()
            );
            failed |= differing != 0;
        }
    }
    Ok(ExitCode::from(u8::from(failed)))
}
