//! Replays a codec tap's `encode_astc` calls through the port, in the tap's order, with one
//! context per footprint kept across calls as the app's wrapper keeps them, and compares each
//! output byte for byte with the recorded one.
//!
//! `cargo run --release --example replay -- <tap-dir> [--stop] [--threads N] [--limit N]`

use std::collections::HashMap;
use std::io::BufRead;
use std::path::Path;

use hokace_astcenc::image::Image;
use hokace_astcenc::{Context, PRF_LDR, config_init};

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let tap = Path::new(&args[1]);
    let stop = args.iter().any(|a| a == "--stop");
    let limit: usize = args
        .iter()
        .position(|a| a == "--limit")
        .and_then(|i| args.get(i + 1))
        .map_or(usize::MAX, |n| n.parse().expect("--limit N"));
    let threads: usize = args
        .iter()
        .position(|a| a == "--threads")
        .and_then(|i| args.get(i + 1))
        .map_or(1, |n| n.parse().expect("--threads N"));
    let calls = std::fs::File::open(tap.join("calls.jsonl")).expect("calls.jsonl");
    let mut contexts: HashMap<(u32, u32), Context> = HashMap::new();
    let (mut total, mut same, mut blocks, mut bad_blocks) = (0, 0, 0usize, 0usize);
    for line in std::io::BufReader::new(calls).lines() {
        let line = line.expect("line");
        let v: serde_json::Value = serde_json::from_str(&line).expect("json");
        if v["fn"] != "encode_astc" {
            continue;
        }
        if total >= limit {
            break;
        }
        let a = &v["args"];
        let n = |i: usize| a[i].as_u64().expect("int") as u32;
        let (w, h, bx, by) = (n(0), n(1), n(2), n(3));
        let input = std::fs::read(tap.join("blobs").join(v["input"].as_str().expect("input")))
            .expect("input blob");
        let want = std::fs::read(
            tap.join("blobs")
                .join(v["output"].as_str().expect("output")),
        )
        .expect("output blob");
        let ctx = contexts.entry((bx, by)).or_insert_with(|| {
            let config = config_init(PRF_LDR, bx, by, 85.0, 0).expect("config");
            Context::with_threads(&config, threads).expect("context")
        });
        let got = ctx
            .compress_image(&Image {
                dim_x: w,
                dim_y: h,
                data: &input,
            })
            .expect("compress");
        total += 1;
        let nb = want.len() / 16;
        blocks += nb;
        let diff: Vec<usize> = (0..nb)
            .filter(|&b| got.get(b * 16..b * 16 + 16) != Some(&want[b * 16..b * 16 + 16]))
            .collect();
        if diff.is_empty() && got.len() == want.len() {
            same += 1;
        } else {
            bad_blocks += diff.len();
            let xb = w.div_ceil(bx) as usize;
            let first = diff.first().copied().unwrap_or(0);
            println!(
                "call {total}: {w}x{h} {bx}x{by}: {}/{nb} blocks differ, first block {first} (x {}, y {}) got {:02x?} want {:02x?}",
                diff.len(),
                first % xb,
                first / xb,
                got.get(first * 16..first * 16 + 16),
                &want[first * 16..first * 16 + 16]
            );
            if stop {
                break;
            }
        }
    }
    hokace_astcenc::prof::report();
    println!(
        "{same}/{total} calls identical; {}/{blocks} blocks identical",
        blocks - bad_blocks
    );
}
