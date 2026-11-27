//! Hold the Rust codecs to the Python ones on a dump's chunks (`rust/harness/codec_corpus.py` writes the index).
//!
//!     cargo run --release -p hokace-codecs --example corpus -- <corpus.jsonl> [kind ...]
//!
//! For each chunk of the named kinds (all when none is named) it decodes the shard's bytes and compares
//! the SHA-256 with the Python decode, a failed decode included; for LZ4 it also re-encodes the decoded
//! bytes at HC 12 and compares the length and SHA-256 with python-lz4's. Exit 1 on any difference.

use std::collections::BTreeMap;
use std::fs::File;
use std::io::{BufRead, BufReader, Read, Seek, SeekFrom};
use std::sync::Mutex;

use rayon::prelude::*;
use serde_json::Value;
use sha2::{Digest, Sha256};

fn hex(data: &[u8]) -> String {
    Sha256::digest(data)
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

fn decode(kind: &str, payload: &[u8], raw: usize) -> Option<Result<Vec<u8>, String>> {
    Some(match kind {
        "stored" => Ok(payload.to_vec()),
        "lz4" => hokace_codecs::lz4::decompress(payload, raw).map_err(|e| e.to_string()),
        "zstd" => hokace_codecs::zstd::decompress(payload, raw),
        _ => return None,
    })
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let index = args
        .first()
        .expect("usage: corpus <corpus.jsonl> [kind ...]");
    let kinds: Vec<&str> = args[1..].iter().map(String::as_str).collect();
    let mut lines = BufReader::new(File::open(index).expect("open the index")).lines();
    let head: Value =
        serde_json::from_str(&lines.next().expect("a header line").expect("read")).expect("json");
    let shards: Vec<String> = head["shards"]
        .as_array()
        .expect("shards")
        .iter()
        .map(|s| s.as_str().expect("path").to_owned())
        .collect();
    let records: Vec<Value> = lines
        .map(|line| serde_json::from_str(&line.expect("read")).expect("json"))
        .filter(|r: &Value| kinds.is_empty() || kinds.contains(&r["kind"].as_str().unwrap_or("")))
        .collect();
    let tally: Mutex<BTreeMap<String, [u64; 3]>> = Mutex::default();
    let problems: Mutex<Vec<String>> = Mutex::default();
    records.par_iter().for_each(|record| {
        let kind = record["kind"].as_str().unwrap_or("other");
        let (offset, size, raw) = (
            record["offset"].as_u64().unwrap(),
            record["size"].as_u64().unwrap() as usize,
            record["raw"].as_u64().unwrap() as usize,
        );
        let mut payload = vec![0u8; size];
        let mut shard =
            File::open(&shards[record["shard"].as_u64().unwrap() as usize]).expect("open shard");
        shard.seek(SeekFrom::Start(offset)).expect("seek");
        shard.read_exact(&mut payload).expect("read chunk");
        let Some(result) = decode(kind, &payload, raw) else {
            return;
        };
        let expected = record["decoded"].as_str();
        let mut bad = Vec::new();
        match (&result, expected) {
            (Ok(bytes), Some(sha)) if hex(bytes) == sha => {}
            (Err(_), None) => {}
            (got, want) => bad.push(format!(
                "decode: rust {} vs python {}",
                got.as_ref()
                    .map(|b| hex(b))
                    .unwrap_or_else(|e| format!("error {e}")),
                want.unwrap_or("error")
            )),
        }
        if let (Ok(bytes), Some(hc)) = (&result, record.get("hc12")) {
            let packed = hokace_codecs::lz4::compress_hc12(bytes).expect("hc12");
            let (len, sha) = (hc[0].as_u64().unwrap() as usize, hc[1].as_str().unwrap());
            if packed.len() != len || hex(&packed) != sha {
                bad.push(format!("hc12: rust {} bytes vs python {len}", packed.len()));
            }
        }
        let mut tally = tally.lock().unwrap();
        let entry = tally.entry(kind.to_owned()).or_default();
        entry[0] += 1;
        if !bad.is_empty() {
            entry[1] += 1;
            problems.lock().unwrap().push(format!(
                "{kind} shard {} @{offset}: {}",
                record["shard"],
                bad.join("; ")
            ));
        }
        entry[2] += raw as u64;
    });
    let problems = problems.into_inner().unwrap();
    for line in problems.iter().take(20) {
        println!("{line}");
    }
    for (kind, [count, differ, bytes]) in tally.into_inner().unwrap() {
        println!(
            "{kind}: {count} chunks, {differ} differ, {:.1} MB decoded",
            bytes as f64 / 1e6
        );
    }
    std::process::exit(i32::from(!problems.is_empty()));
}
