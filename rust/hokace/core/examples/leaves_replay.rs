//! Compares the Wave 3 leaf ports against rust/harness/leaves_tap.py.
//!
//!     cargo run --release -p hokace-core --example leaves_replay -- <dir>

use hokace_core::axml::{self, PyErr};
use hokace_core::catalog_supplement::{self, Supplement};
use hokace_core::languages::{self, Language};
use hokace_core::resource_tokens::{self, NotMessage};
use hokace_core::{broken_list, catalog_updates, terminology};
use indexmap::IndexMap;
use serde_json::{Map, Value, json};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::io::{BufRead, BufReader, Read};
use std::path::{Path, PathBuf};
use std::{env, fs};

#[path = "leaves_replay/lineup.rs"]
mod lineup;
#[path = "leaves_replay/titles.rs"]
mod titles;

fn repo() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../../..")
}

fn hex(data: &[u8]) -> String {
    data.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn unhex(text: &str) -> Vec<u8> {
    (0..text.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&text[i..i + 2], 16).unwrap())
        .collect()
}

fn read_gz_json(path: &Path) -> Value {
    let mut text = String::new();
    flate2::read::GzDecoder::new(fs::File::open(path).unwrap())
        .read_to_string(&mut text)
        .unwrap();
    serde_json::from_str(&text).unwrap()
}

fn language(code: &str) -> &'static Language {
    languages::get(code).unwrap()
}

fn terms_of(name: &str) -> &'static [terminology::Term] {
    language(name).terms()
}

fn ok(value: Value) -> Value {
    json!({"ok": value})
}

fn err(class: &str, message: impl std::fmt::Display) -> Value {
    json!({"error": format!("{class}: {message}")})
}

fn pairs(map: IndexMap<String, String>) -> Value {
    Value::Array(
        map.into_iter()
            .map(|(zh, text)| json!([zh, text]))
            .collect(),
    )
}

fn map_of(list: &Value) -> Map<String, Value> {
    list.as_array()
        .unwrap()
        .iter()
        .map(|pair| (pair[0].as_str().unwrap().to_owned(), pair[1].clone()))
        .collect()
}

fn expanded(result: Result<(Vec<u8>, u64), NotMessage>) -> Value {
    match result {
        Ok((out, count)) => ok(json!([hex(&out), count])),
        Err(NotMessage) => err("NotMessage", ""),
    }
}

fn digest(data: &[u8]) -> String {
    hex(&Sha256::digest(data))
}

fn py(result: Result<Value, PyErr>) -> Value {
    match result {
        Ok(value) => ok(value),
        Err(error) => err(error.class, error.message),
    }
}

/// `apk_preparation.manifest_to_install` without its log, as axml_cases._install records it.
fn install(mut data: Vec<u8>) -> Result<Value, PyErr> {
    if axml::is_debuggable(&data)? {
        data = axml::patch(&data, false)?;
    }
    match axml::set_label(&data, "Honor of Kings: ACE") {
        Ok(named) => Ok(json!([digest(&named), null])),
        Err(error) if error.is_value_error() => Ok(json!([digest(&data), error.to_string()])),
        Err(error) => Err(error),
    }
}

struct Replay {
    supplement: Supplement,
    dir: PathBuf,
    sources: BTreeMap<String, Value>,
}

impl Replay {
    fn source(&mut self, catalog: &str) -> Value {
        self.sources
            .entry(catalog.to_owned())
            .or_insert_with(|| {
                read_gz_json(
                    &repo()
                        .join("resources")
                        .join(catalog)
                        .join("catalog.json.gz"),
                )
            })
            .clone()
    }

    fn call(&mut self, function: &str, args: &Value) -> Value {
        let s = |key: &str| args[key].as_str().unwrap_or_default().to_owned();
        match function {
            "load_edits" => {
                let mut data = self.source(&s("catalog"));
                let code = s("code");
                let supplemented =
                    catalog_supplement::apply(&self.supplement, &mut data, &code).unwrap();
                let admitted = catalog_updates::admit_tables(&mut data).unwrap();
                let changed = terminology::apply(&mut data, language(&code).terms()).unwrap();
                let updates = catalog_updates::apply(&mut data, &code).unwrap();
                let want = read_gz_json(&self.dir.join(format!("{}.json.gz", s("catalog"))));
                if serde_json::to_string(&data).unwrap() != serde_json::to_string(&want).unwrap() {
                    report_catalog(&data, &want);
                    return err("Mismatch", "edited catalog");
                }
                let changed: Vec<Value> = changed
                    .into_iter()
                    .map(|(term, count)| json!([term, count]))
                    .collect();
                ok(
                    json!({"supplement": supplemented, "admit": admitted, "terminology": changed, "updates": updates}),
                )
            }
            "entries" => {
                let data = self.source(&s("catalog"));
                ok(pairs(catalog_supplement::entries(
                    &self.supplement,
                    data["unique"].as_object().unwrap(),
                    &s("code"),
                )))
            }
            "derived" => {
                let data = self.source(&s("catalog"));
                ok(pairs(catalog_supplement::derived(
                    data["unique"].as_object().unwrap(),
                )))
            }
            "entries_synthetic" => {
                let unique = map_of(&args["unique"]);
                ok(pairs(catalog_supplement::entries(
                    &self.supplement,
                    &unique,
                    &s("code"),
                )))
            }
            "check" => {
                let pairs: IndexMap<String, String> = map_of(&args["pairs"])
                    .into_iter()
                    .map(|(zh, text)| (zh, text.as_str().unwrap().to_owned()))
                    .collect();
                ok(json!(catalog_supplement::check(&pairs)))
            }
            "chinese_number" => ok(json!(
                (1..=100)
                    .map(catalog_supplement::chinese_number)
                    .collect::<Vec<_>>()
            )),
            "supplement_load" => {
                match catalog_supplement::load(
                    &self.dir.join("supplement-fixtures").join(s("file")),
                ) {
                    Ok(loaded) => ok(Value::Array(
                        loaded
                            .into_iter()
                            .map(|(zh, (en, id))| json!([zh, [en, id]]))
                            .collect(),
                    )),
                    Err(message) => err("ValueError", message),
                }
            }
            "rewrite" => {
                let term = &terms_of(&s("terms"))[args["index"].as_u64().unwrap() as usize];
                ok(json!(
                    term.rewrite(&format!("{}x", term.source), &s("target"))
                ))
            }
            "apply_terms_empty" => {
                let mut data = json!({"unique": {"夺取": "plunder"}});
                let changed = terminology::apply(&mut data, &[]).unwrap();
                ok(Value::Array(
                    changed
                        .into_iter()
                        .map(|(term, count)| json!([term, count]))
                        .collect(),
                ))
            }
            "updates" => {
                let mut data = args["data"].clone();
                let admitted = catalog_updates::admit_tables(&mut data).unwrap();
                let added = catalog_updates::apply(&mut data, &s("code")).unwrap();
                ok(json!([admitted, added, data]))
            }
            "expand_resource_tokens_all" => {
                let terms = language(&s("code")).resource_terms;
                let out: Vec<String> = args["texts"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|text| {
                        resource_tokens::expand_resource_tokens(text.as_str().unwrap(), terms)
                    })
                    .collect();
                ok(json!(out))
            }
            "expand_resource_tokens" => ok(json!(resource_tokens::expand_resource_tokens(
                &s("text"),
                language(&s("code")).resource_terms
            ))),
            "expand_tokens_in_message" => expanded(resource_tokens::expand_tokens_in_message(
                &unhex(&s("data")),
                language(&s("code")).resource_terms,
            )),
            "expand_file" => {
                let raw = fs::read(s("path")).unwrap();
                let cut = args["cut"].as_u64().unwrap() as usize;
                match resource_tokens::expand_tokens_in_message(
                    &raw[..cut],
                    language(&s("code")).resource_terms,
                ) {
                    Ok((out, count)) => ok(json!([hex(&Sha256::digest(&out)), count])),
                    Err(NotMessage) => err("NotMessage", ""),
                }
            }
            "expand_tokens" => {
                let mut lines = Vec::new();
                let mut log = |line: &str| lines.push(line.to_owned());
                let out = resource_tokens::expand_tokens(
                    &unhex(&s("data")),
                    Some(&mut log),
                    language(&s("code")).resource_terms,
                );
                ok(json!([hex(&out), lines]))
            }
            "expand_staged" => {
                let root =
                    env::temp_dir().join(format!("hokace-leaves-staged-{}", std::process::id()));
                let _ = fs::remove_dir_all(&root);
                for (name, content) in args["before"].as_object().unwrap() {
                    let path = root.join(name.replace('\\', "/"));
                    fs::create_dir_all(path.parent().unwrap()).unwrap();
                    fs::write(path, unhex(content.as_str().unwrap())).unwrap();
                }
                let folders: Vec<PathBuf> = args["folders"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|f| root.join(f.as_str().unwrap()))
                    .collect();
                let mut lines = Vec::new();
                let mut log = |line: &str| lines.push(line.to_owned());
                let changed = resource_tokens::expand_staged(
                    &folders,
                    &mut log,
                    language(&s("code")).resource_terms,
                )
                .unwrap();
                let mut after = BTreeMap::new();
                for name in args["before"].as_object().unwrap().keys() {
                    after.insert(
                        name.clone(),
                        hex(&fs::read(root.join(name.replace('\\', "/"))).unwrap()),
                    );
                }
                fs::remove_dir_all(&root).unwrap();
                ok(json!([changed, lines, after]))
            }
            "languages_get" => match languages::get(&s("code")) {
                Ok(language) => ok(json!(language.catalog)),
                Err(message) => err("ValueError", message),
            },
            "for_catalog" => ok(json!(languages::for_catalog(Path::new(&s("path"))).code)),
            "axml_patch" => {
                let data = fs::read(self.dir.join(s("file"))).unwrap();
                py(axml::patch(&data, args["debuggable"].as_bool().unwrap())
                    .map(|out| json!(digest(&out))))
            }
            "axml_is_debuggable" => {
                let data = fs::read(self.dir.join(s("file"))).unwrap();
                py(axml::is_debuggable(&data).map(|flag| json!(flag)))
            }
            "axml_set_label" => {
                let data = fs::read(self.dir.join(s("file"))).unwrap();
                py(axml::set_label(&data, &s("label")).map(|out| json!(digest(&out))))
            }
            "axml_install" => {
                let data = fs::read(self.dir.join(s("file"))).unwrap();
                py(install(data))
            }
            "axml_build_pool" => {
                let strings: Vec<String> = args["strings"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|t| t.as_str().unwrap().to_owned())
                    .collect();
                let flags = args["flags"].as_u64().unwrap() as u32;
                py(axml::build_string_pool(&strings, flags).map(|out| json!(hex(&out))))
            }
            "broken_list" => {
                let listed = broken_list::read(&self.dir.join(s("file"))).unwrap();
                let assets: Map<String, Value> = listed
                    .assets
                    .iter()
                    .map(|(package, assets)| (package.clone(), json!(assets)))
                    .collect();
                ok(
                    json!({"assets": assets, "unreadable": listed.unreadable, "empty": listed.empty()}),
                )
            }
            "payload_path" => {
                let root = self.dir.join("payload-fixture");
                let path = languages::payload_path(&root.join(s("catalog")), &s("name"));
                let relative = path
                    .strip_prefix(&root)
                    .unwrap()
                    .to_string_lossy()
                    .replace('\\', "/");
                ok(json!(relative))
            }
            other => lineup::call(&self.dir, other, args)
                .or_else(|| titles::call(&self.dir, other, args))
                .unwrap_or_else(|| panic!("no replay for {other}")),
        }
    }
}

/// The first catalog entries that differ, for a mismatch.
fn report_catalog(got: &Value, want: &Value) {
    let (got, want) = (got.as_object().unwrap(), want.as_object().unwrap());
    if got.keys().collect::<Vec<_>>() != want.keys().collect::<Vec<_>>() {
        eprintln!("  top-level keys differ");
    }
    for (key, value) in want {
        if got.get(key) == Some(value) {
            if serde_json::to_string(&got[key]).unwrap() != serde_json::to_string(value).unwrap() {
                eprintln!("  {key}: same entries, other order");
            }
            continue;
        }
        let mut shown = 0;
        if let (Some(Value::Object(left)), Value::Object(right)) = (got.get(key), value) {
            for (zh, text) in right {
                if left.get(zh) != Some(text) && shown < 5 {
                    eprintln!("  {key}[{zh:?}]: got {:?}, want {text}", left.get(zh));
                    shown += 1;
                }
            }
        } else {
            eprintln!("  {key} differs");
        }
    }
}

/// Results compare as Python's JSON does, except a map of files, which compares by key.
fn same(got: &Value, want: &Value) -> bool {
    serde_json::to_string(got).unwrap() == serde_json::to_string(want).unwrap() || got == want
}

fn main() {
    let dir = PathBuf::from(env::args().nth(1).expect("usage: leaves_replay <dir>"));
    let supplement = Supplement::load(&repo().join("resources/catalog_supplement")).unwrap();
    let mut replay = Replay {
        supplement,
        dir: dir.clone(),
        sources: BTreeMap::new(),
    };
    let file = fs::File::open(dir.join("calls.jsonl")).unwrap();
    let (mut total, mut failed) = (0, 0);
    let mut by_fn: BTreeMap<String, (u32, u32)> = BTreeMap::new();
    for line in BufReader::new(file).lines() {
        let call: Value = serde_json::from_str(&line.unwrap()).unwrap();
        let function = call["fn"].as_str().unwrap();
        let got = replay.call(function, &call["args"]);
        let entry = by_fn.entry(function.to_owned()).or_default();
        entry.0 += 1;
        total += 1;
        if !same(&got, &call["result"]) {
            failed += 1;
            entry.1 += 1;
            if entry.1 <= 3 {
                let args = serde_json::to_string(&call["args"]).unwrap();
                eprintln!("MISMATCH {function} {}", &args[..args.len().min(300)]);
                let (got, want) = (got.to_string(), call["result"].to_string());
                eprintln!("  got  {}", &got[..got.len().min(600)]);
                eprintln!("  want {}", &want[..want.len().min(600)]);
            }
        }
    }
    for (function, (count, bad)) in &by_fn {
        println!("{function}: {}/{count}", count - bad);
    }
    println!("{}/{total} matched", total - failed);
    std::process::exit(i32::from(failed != 0));
}
