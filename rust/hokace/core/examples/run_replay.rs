//! Replay `rust/harness/run_tap.py`'s recordings of `adaptive.run` against `hokace_core::run`.
//!
//! Each case's pre-state is rebuilt at the paths it was recorded at; each step runs with a host that
//! hands back the recorded calls in order (checking their arguments and writing the files they
//! wrote), and the report, the error and the tree after the step must match the recording.
//!
//!     cargo run --release -p hokace-core --example run_replay -- <dir>

use std::collections::VecDeque;
use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};

use hokace_core::run::{RunHost, RunPlan, RunScan, run};
use hokace_core::scan::PyError;
use indexmap::IndexMap;
use serde_json::{Map, Value, json};
use sha2::{Digest, Sha256};

fn hex(data: &[u8]) -> String {
    Sha256::digest(data)
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

fn is_receipt_name(name: &str) -> bool {
    let Some((digits, tail)) = name.split_once('-') else {
        return false;
    };
    (16..=20).contains(&digits.len())
        && digits.bytes().all(|b| b.is_ascii_digit())
        && tail.len() == 8
        && tail.bytes().all(|b| matches!(b, b'0'..=b'9' | b'a'..=b'f'))
}

#[derive(Default)]
struct Names {
    map: IndexMap<String, String>,
}

impl Names {
    fn see(&mut self, mut names: Vec<String>) {
        names.sort();
        for name in names {
            let next = format!("receipt-{}", self.map.len());
            self.map.entry(name).or_insert(next);
        }
    }

    fn text(&self, value: &str) -> String {
        let mut out = value.to_owned();
        for (name, label) in &self.map {
            out = out.replace(name.as_str(), label);
        }
        out
    }
}

fn walk(root: &Path, base: &Path, out: &mut Vec<(String, Option<PathBuf>)>) {
    let Ok(entries) = fs::read_dir(root) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        let rel: Vec<String> = path
            .strip_prefix(base)
            .unwrap()
            .components()
            .map(|c| c.as_os_str().to_string_lossy().into_owned())
            .collect();
        let rel = rel.join("/");
        if path.is_dir() {
            out.push((rel, None));
            walk(&path, base, out);
        } else {
            out.push((rel, Some(path)));
        }
    }
}

fn snapshot(base: &Path, names: &mut Names) -> Value {
    let receipts = base.join("receipts");
    if let Ok(entries) = fs::read_dir(&receipts) {
        names.see(
            entries
                .flatten()
                .filter(|e| e.path().is_dir())
                .map(|e| e.file_name().to_string_lossy().into_owned())
                .filter(|n| is_receipt_name(n))
                .collect(),
        );
    }
    let mut found = Vec::new();
    walk(base, base, &mut found);
    let mut rows: Vec<(String, String)> = found
        .into_iter()
        .map(|(rel, path)| {
            let value = match path {
                None => "<dir>".to_owned(),
                Some(path) => hex(&fs::read(path).unwrap()),
            };
            (names.text(&rel), value)
        })
        .collect();
    rows.sort();
    Value::Array(rows.into_iter().map(|(r, v)| json!([r, v])).collect())
}

fn clear(path: &Path) {
    if !path.exists() {
        return;
    }
    let mut found = Vec::new();
    walk(path, path, &mut found);
    for (_, file) in found {
        if let Some(file) = file {
            let mut permissions = fs::metadata(&file).unwrap().permissions();
            #[allow(clippy::permissions_set_readonly_false)]
            permissions.set_readonly(false);
            let _ = fs::set_permissions(&file, permissions);
        }
    }
    fs::remove_dir_all(path).unwrap();
}

fn parse_error(text: &str) -> PyError {
    let (class, message) = text.split_once(": ").unwrap_or((text, ""));
    let class: &'static str = Box::leak(class.to_owned().into_boxed_str());
    PyError::new(class, message)
}

struct Host {
    receipts: PathBuf,
    blobs: PathBuf,
    calls: VecDeque<Value>,
    problems: Vec<String>,
}

impl Host {
    fn take(&mut self, fn_name: &str, args: Value) -> Result<Value, PyError> {
        let Some(call) = self.calls.pop_front() else {
            self.problems.push(format!("extra call {fn_name} {args}"));
            return Err(PyError::new("ReplayMismatch", "no recorded call left"));
        };
        if call["fn"] != fn_name || call["args"] != args {
            self.problems.push(format!(
                "call {fn_name} {args}\n      recorded {} {}",
                call["fn"], call["args"]
            ));
            return Err(PyError::new("ReplayMismatch", "call differs"));
        }
        for write in call["writes"].as_array().unwrap() {
            let path = PathBuf::from(write[0].as_str().unwrap());
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            fs::copy(self.blobs.join(write[1].as_str().unwrap()), &path).unwrap();
        }
        match call["result"].get("error") {
            Some(error) => Err(parse_error(error.as_str().unwrap())),
            None => Ok(call["result"]["ok"].clone()),
        }
    }
}

fn s(path: &Path) -> Value {
    Value::String(path.display().to_string())
}

fn pairs<V: Into<Value> + Clone>(map: impl IntoIterator<Item = (String, V)>) -> Value {
    Value::Array(map.into_iter().map(|(k, v)| json!([k, v.into()])).collect())
}

impl RunHost for Host {
    type Replacements = String;

    fn receipt_root(&mut self, _game: &Path) -> PathBuf {
        self.receipts.clone()
    }

    fn assert_game_stopped(&mut self) -> Result<(), PyError> {
        self.take("assert_game_stopped", json!([])).map(|_| ())
    }

    fn scan(
        &mut self,
        game: &Path,
        assets: &Path,
        work: &Path,
        materialize: bool,
    ) -> Result<RunScan<String>, PyError> {
        let result = self.take("scan", json!([s(game), s(assets), s(work), materialize]))?;
        let paths = |v: &Value| PathBuf::from(v.as_str().unwrap());
        Ok(RunScan {
            plans: result["plans"]
                .as_array()
                .unwrap()
                .iter()
                .map(|p| RunPlan {
                    package_id: p["package_id"].as_str().unwrap().to_owned(),
                    package_dir: paths(&p["package_dir"]),
                    index_path: paths(&p["index_path"]),
                    shard_paths: p["shard_paths"]
                        .as_array()
                        .unwrap()
                        .iter()
                        .map(paths)
                        .collect(),
                    replacements: p["replacements"].as_str().unwrap().to_owned(),
                })
                .collect(),
            fingerprints: result["fingerprints"]
                .as_array()
                .unwrap()
                .iter()
                .map(|p| {
                    (
                        p[0].as_str().unwrap().to_owned(),
                        p[1].as_str().unwrap().to_owned(),
                    )
                })
                .collect(),
            counts: result["counts"].as_object().unwrap().clone(),
            skipped: result["skipped"].clone(),
        })
    }

    fn stage_unity_package(
        &mut self,
        game: &Path,
        replacements: &String,
        stage: &Path,
        source_package_dir: &Path,
        source_hashes: &IndexMap<String, String>,
    ) -> Result<Value, PyError> {
        let hashes = pairs(source_hashes.clone());
        self.take(
            "stage_unity_package",
            json!([
                s(game),
                replacements,
                s(stage),
                s(source_package_dir),
                true,
                false,
                hashes
            ]),
        )
    }

    fn query_package_hash(&mut self, game: &Path, package_dir: &Path) -> Result<Value, PyError> {
        self.take("query_package_hash", json!([s(game), s(package_dir)]))
    }

    fn stage_package_hash_metadata_batch(
        &mut self,
        game: &Path,
        package_hashes: &Map<String, Value>,
        output: &Path,
    ) -> Result<Value, PyError> {
        let hashes = pairs(package_hashes.clone());
        self.take(
            "stage_package_hash_metadata_batch",
            json!([s(game), hashes, s(output)]),
        )
    }
}

fn hold_lock(receipts: &Path) -> File {
    fs::create_dir_all(receipts).unwrap();
    let mut file = OpenOptions::new()
        .read(true)
        .append(true)
        .create(true)
        .open(receipts.join("operation.lock"))
        .unwrap();
    if file.metadata().unwrap().len() == 0 {
        file.write_all(b"0").unwrap();
    }
    file.try_lock().unwrap();
    file
}

fn main() {
    let dir = PathBuf::from(std::env::args().nth(1).expect("usage: run_replay <dir>"));
    let blobs = dir.join("blobs");
    let text = fs::read_to_string(dir.join("cases.jsonl")).unwrap();
    let (mut steps_total, mut failed) = (0, 0);
    for line in text.lines() {
        let case: Value = serde_json::from_str(line).unwrap();
        let name = case["name"].as_str().unwrap();
        let base = PathBuf::from(case["base"].as_str().unwrap());
        let game = PathBuf::from(case["game"].as_str().unwrap());
        let receipts = PathBuf::from(case["receipts"].as_str().unwrap());
        let assets = PathBuf::from(case["assets"].as_str().unwrap());
        clear(&base);
        fs::create_dir_all(&base).unwrap();
        let mut readonly = Vec::new();
        for row in case["pre"].as_array().unwrap() {
            let path = base.join(row[0].as_str().unwrap());
            match row[1].as_str() {
                None => fs::create_dir_all(&path).unwrap(),
                Some(blob) => {
                    fs::create_dir_all(path.parent().unwrap()).unwrap();
                    fs::copy(blobs.join(blob), &path).unwrap();
                    if row[2] == true {
                        readonly.push(path);
                    }
                }
            }
        }
        for path in readonly {
            let mut permissions = fs::metadata(&path).unwrap().permissions();
            permissions.set_readonly(true);
            fs::set_permissions(&path, permissions).unwrap();
        }
        let extra: Vec<PathBuf> = case
            .get("extra_work")
            .and_then(Value::as_array)
            .map(|a| {
                a.iter()
                    .map(|p| PathBuf::from(p.as_str().unwrap()))
                    .collect()
            })
            .unwrap_or_default();
        let mut names = Names::default();
        snapshot(&base, &mut names);
        for (index, step) in case["steps"].as_array().unwrap().iter().enumerate() {
            steps_total += 1;
            for work in &extra {
                clear(work);
                fs::create_dir_all(work).unwrap();
            }
            let action = step["action"].as_str().unwrap();
            let work = PathBuf::from(step["work"].as_str().unwrap());
            let mut host = Host {
                receipts: receipts.clone(),
                blobs: blobs.clone(),
                calls: step["calls"].as_array().unwrap().iter().cloned().collect(),
                problems: Vec::new(),
            };
            let held = (step["locked"] == true).then(|| hold_lock(&receipts));
            let outcome = run(action, &game, &assets, &work, &mut host);
            drop(held);
            let result = match outcome {
                Ok(mut report) => {
                    report.shift_remove("seconds");
                    json!({ "ok": report })
                }
                Err(error) => json!({ "error": format!("{}: {}", error.class, error.message) }),
            };
            let tree = snapshot(&base, &mut names);
            let result: Value =
                serde_json::from_str(&names.text(&serde_json::to_string(&result).unwrap()))
                    .unwrap();
            let mut problems = std::mem::take(&mut host.problems);
            for left in &host.calls {
                problems.push(format!(
                    "recorded call not made: {} {}",
                    left["fn"], left["args"]
                ));
            }
            let want = serde_json::to_string(&step["result"]).unwrap();
            let got = serde_json::to_string(&result).unwrap();
            if want != got {
                problems.push(format!(
                    "result\n      got      {got}\n      recorded {want}"
                ));
            }
            if tree != step["tree"] {
                let (got, want) = (tree.as_array().unwrap(), step["tree"].as_array().unwrap());
                for row in got.iter().filter(|r| !want.contains(r)) {
                    problems.push(format!("tree has {row}"));
                }
                for row in want.iter().filter(|r| !got.contains(r)) {
                    problems.push(format!("tree lacks {row}"));
                }
            }
            for work in &extra {
                let key = work.display().to_string();
                if snapshot(work, &mut names) != step["extra_tree"][&key] {
                    problems.push(format!("work tree {key} differs"));
                }
            }
            if problems.is_empty() {
                continue;
            }
            failed += 1;
            println!("MISMATCH {name} step {index} ({action}):");
            for problem in problems {
                println!("    {problem}");
            }
        }
    }
    println!("{steps_total} steps, {failed} mismatched");
    if failed > 0 {
        std::process::exit(1);
    }
}
