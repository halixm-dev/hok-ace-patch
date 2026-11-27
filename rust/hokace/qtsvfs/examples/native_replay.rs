//! Replay `rust/harness/pc_native_tap.py`'s recording through the port and the game's QtsVFS.
//!
//!     cargo run --release -p hokace-qtsvfs --example native_replay -- <dir>
//!
//! Each `query`, `stage_batch` and `verify` line runs again with the recorded arguments and must
//! give the recorded result: the value, or the exception's class and message. A `verify` reads
//! `staged_copy`, and its work folder is emptied first, as the tap found it. The fixtures the
//! calls name (the fake game, the broken and copied packages) are the tap's own: replay after a
//! fresh tap. The query's temporary folder (`ace-package-hash-<random>`) is compared by its
//! prefix. Exits 1 on any difference.

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

use hokace_core::native_verify::verify_staged_package;
use hokace_core::package_metadata::{query_package_hash, stage_package_hash_metadata_batch};
use hokace_core::scan::PyError;
use hokace_qtsvfs::DllLoader;
use serde_json::{Map, Value, json};

fn outcome(result: Result<Value, PyError>) -> Value {
    match result {
        Ok(value) => json!({ "ok": value }),
        Err(error) => json!({ "error": format!("{}: {}", error.class, error.message) }),
    }
}

/// The result with every `ace-package-hash-<random>` folder name cut to its prefix.
fn masked(result: &Value) -> String {
    const PREFIX: &str = "ace-package-hash-";
    let text = result.to_string();
    let mut out = String::new();
    let mut rest = text.as_str();
    while let Some(at) = rest.find(PREFIX) {
        out.push_str(&rest[..at + PREFIX.len()]);
        rest = rest[at + PREFIX.len()..].trim_start_matches(|c: char| c.is_ascii_alphanumeric() || c == '_');
    }
    out + rest
}

fn text(value: &Value) -> &str {
    value.as_str().expect("a string argument")
}

fn replay(dir: &Path, line: &Value, loader: &mut DllLoader) -> Value {
    let args = line["args"].as_array().expect("args");
    match text(&line["fn"]) {
        "query" => outcome(
            query_package_hash(loader, Path::new(text(&args[0])), Path::new(text(&args[1])))
                .map(Value::from),
        ),
        "stage_batch" => {
            let hashes: Map<String, Value> = args[1]
                .as_array()
                .expect("pairs")
                .iter()
                .map(|pair| (text(&pair[0]).to_owned(), pair[1].clone()))
                .collect();
            let output = PathBuf::from(text(&args[2]));
            let _ = fs::remove_file(&output);
            outcome(stage_package_hash_metadata_batch(
                Path::new(text(&args[0])),
                &hashes,
                &output,
            ))
        }
        "verify" => {
            let replacements: BTreeMap<u64, Vec<u8>> = args[3]
                .as_array()
                .expect("replacements")
                .iter()
                .map(|pair| {
                    let hash = u64::from_str_radix(text(&pair[0]), 16).expect("hex hash");
                    let data = fs::read(dir.join("blobs").join(text(&pair[1]))).expect("blob");
                    (hash, data)
                })
                .collect();
            let work = PathBuf::from(text(&args[4]));
            if work.exists() {
                fs::remove_dir_all(&work).expect("empty the verify folder");
            }
            outcome(verify_staged_package(
                loader,
                Path::new(text(&args[0])),
                Path::new(text(&args[1])),
                Path::new(text(&line["staged_copy"])),
                &replacements,
                &work,
                args[5].as_bool().expect("verify_all_unrelated"),
            ))
        }
        other => panic!("unknown call {other}"),
    }
}

fn main() -> ExitCode {
    let dir = PathBuf::from(std::env::args().nth(1).expect("usage: native_replay <dir>"));
    let calls = fs::read_to_string(dir.join("calls.jsonl")).expect("calls.jsonl");
    let mut loader = DllLoader;
    let (mut passed, mut failed) = (0, 0);
    for (number, raw) in calls.lines().enumerate() {
        let line: Value = serde_json::from_str(raw).expect("a JSON line");
        let actual = replay(&dir, &line, &mut loader);
        if actual == line["result"] || masked(&actual) == masked(&line["result"]) {
            passed += 1;
        } else {
            failed += 1;
            println!(
                "line {} {}: {}\n  recorded {}\n  replayed {}",
                number + 1,
                line["fn"],
                line["args"].to_string().chars().take(160).collect::<String>(),
                line["result"],
                actual
            );
        }
    }
    println!("{passed} passed, {failed} differ");
    if failed == 0 {
        ExitCode::SUCCESS
    } else {
        ExitCode::FAILURE
    }
}
