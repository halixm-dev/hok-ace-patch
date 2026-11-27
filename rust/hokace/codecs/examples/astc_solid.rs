//! Replay solid blocks byte for byte against ASTC encoder taps.
//!
//!     cargo run --release -p hokace-codecs --example astc_solid -- <tap-dir> ...

use std::fs;
use std::io::{BufRead, BufReader};
use std::path::Path;

use hokace_codecs::astc_encode::encode_solid_block;
use serde_json::Value;

fn check_solid_blocks(
    dir: &Path,
    record: &Value,
) -> Result<(usize, usize), Box<dyn std::error::Error>> {
    let mut dimensions = [0; 4];
    for (value, field) in dimensions.iter_mut().zip(0..4) {
        *value = usize::try_from(record["args"][field].as_u64().ok_or("invalid dimension")?)?;
        if *value == 0 {
            return Err("zero ASTC dimension".into());
        }
    }
    let [width, height, bx, by] = dimensions;
    let load = |key| -> Result<Vec<u8>, Box<dyn std::error::Error>> {
        let hash = record[key].as_str().ok_or("missing blob name")?;
        Ok(fs::read(dir.join("blobs").join(hash))?)
    };
    let input = load("input")?;
    let reference = load("output")?;

    if width.checked_mul(height).and_then(|n| n.checked_mul(4)) != Some(input.len()) {
        return Err("invalid input byte count".into());
    }
    let columns = width.div_ceil(bx);
    let rows = height.div_ceil(by);
    let blocks = columns * rows;
    if blocks.checked_mul(16) != Some(reference.len()) {
        return Err("invalid ASTC byte count".into());
    }

    let mut solid = 0;
    for (block_y, y) in (0..height).step_by(by).enumerate() {
        for (block_x, x) in (0..width).step_by(bx).enumerate() {
            let offset = (y * width + x) * 4;
            let rgba: [u8; 4] = input[offset..offset + 4].try_into()?;
            // The encoder pads partial blocks by clamping to the edge, so
            // checking the pixels inside the texture also checks the padding.
            let is_solid = (y..y + by.min(height - y)).all(|row| {
                let start = (row * width + x) * 4;
                let end = start + bx.min(width - x) * 4;
                input[start..end]
                    .as_chunks::<4>()
                    .0
                    .iter()
                    .all(|&pixel| pixel == rgba)
            });
            if is_solid {
                let base = (block_y * columns + block_x) * 16;
                if encode_solid_block(rgba) != reference[base..base + 16] {
                    let hash = &record["input"];
                    return Err(
                        format!("{hash}: solid {bx}x{by} block at ({x}, {y}) differs").into(),
                    );
                }
                solid += 1;
            }
        }
    }
    Ok((solid, blocks))
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = std::env::args_os().skip(1).peekable();
    if args.peek().is_none() {
        return Err("usage: astc_solid <tap-dir> ...".into());
    }
    for arg in args {
        let dir = Path::new(&arg);
        let calls = BufReader::new(fs::File::open(dir.join("calls.jsonl"))?);
        let mut solid = 0;
        let mut blocks = 0;
        for line in calls.lines() {
            let record: Value = serde_json::from_str(&line?)?;
            if record["fn"] == "encode_astc" {
                let (matching, total) = check_solid_blocks(dir, &record)?;
                solid += matching;
                blocks += total;
            }
        }
        if solid == 0 {
            return Err(format!("{}: no solid ASTC blocks", dir.display()).into());
        }
        println!(
            "{}: {solid} solid blocks match, {} non-solid",
            dir.display(),
            blocks - solid
        );
    }
    Ok(())
}
