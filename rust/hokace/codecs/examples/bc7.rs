//! Replay all PC atlas encoder calls recorded by `rust/harness/bc7_case.py`.
//!
//!     cargo run --release -p hokace-codecs --example bc7 -- <bc7-en.bin> <bc7-id.bin>

use std::{fs, path::Path};

use hokace_codecs::{bc7::encode_block, texture::decode_bc7};

const RECORD_SIZE: usize = 80;
const MAX_MEAN: f64 = 2.0;
const MAX_CHANNEL: u8 = 48;

fn replay(path: &Path) -> Result<bool, Box<dyn std::error::Error>> {
    let input = fs::read(path)?;
    let (records, remainder) = input.as_chunks::<RECORD_SIZE>();
    if records.is_empty() || !remainder.is_empty() {
        return Err(format!("{}: invalid BC7 recording size", path.display()).into());
    }
    let (mut exact, mut outside_limits) = (0, 0);
    let (mut worst_mean, mut worst_channel) = (0.0_f64, 0);
    for record in records {
        let (rgba, expected) = record.split_at(64);
        let actual = encode_block(rgba.try_into()?)?;
        if actual == expected {
            exact += 1;
            continue;
        }
        let python = decode_bc7(expected, 4, 4)?;
        let rust = decode_bc7(&actual, 4, 4)?;
        let (sum, max) = python.iter().zip(rust).fold((0, 0), |(sum, max), (a, b)| {
            let difference = a.abs_diff(b);
            (sum + u32::from(difference), max.max(difference))
        });
        let mean = f64::from(sum) / 64.0;
        outside_limits += usize::from(mean > MAX_MEAN || max > MAX_CHANNEL);
        worst_mean = worst_mean.max(mean);
        worst_channel = worst_channel.max(max);
    }
    println!(
        "{}: {exact}/{} byte-identical, {outside_limits} outside pixel limits (worst mean {worst_mean:.3}, max {worst_channel})",
        path.display(),
        records.len()
    );
    Ok(outside_limits == 0)
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut cases = std::env::args_os().skip(1).peekable();
    if cases.peek().is_none() {
        return Err("usage: bc7 <bc7-en.bin> [bc7-id.bin]".into());
    }
    let mut passed = true;
    for case in cases {
        passed &= replay(Path::new(&case))?;
    }
    if !passed {
        return Err("BC7 replay exceeded ADR-027 pixel limits".into());
    }
    Ok(())
}
