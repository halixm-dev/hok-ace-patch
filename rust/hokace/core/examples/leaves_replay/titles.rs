//! The `sprite_table`, `card_titles` and `hand_card_titles` calls of rust/harness/title_cases.py.

use hokace_core::axml::PyErr;
use hokace_core::hand_card_titles::{self, TitleEdit};
use hokace_core::{card_titles, sprite_table};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::fs;
use std::path::{Path, PathBuf};

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

fn sha(data: &[u8]) -> String {
    hex(&Sha256::digest(data))
}

fn blob(data: &[u8]) -> Value {
    json!(if data.len() <= 2048 {
        hex(data)
    } else {
        format!("sha256:{}", sha(data))
    })
}

fn py(result: Result<Value, PyErr>) -> Value {
    match result {
        Ok(value) => json!({"ok": value}),
        Err(error) => json!({"error": format!("{}: {}", error.class, error.message)}),
    }
}

/// `_edited`: drop, empty, or cut then flip.
fn edited(data: &[u8], edit: &Value) -> Option<Vec<u8>> {
    if edit["drop"].as_bool() == Some(true) {
        return None;
    }
    if edit["empty"].as_bool() == Some(true) {
        return Some(Vec::new());
    }
    let mut out = match edit["cut"].as_u64() {
        Some(cut) => data[..(cut as usize).min(data.len())].to_vec(),
        None => data.to_vec(),
    };
    for flip in edit["flips"].as_array().into_iter().flatten() {
        let at = flip[0].as_u64().unwrap() as usize;
        if at < out.len() {
            out[at] = flip[1].as_u64().unwrap() as u8;
        }
    }
    Some(out)
}

fn bytes_of(dir: &Path, args: &Value) -> Vec<u8> {
    if let Some(text) = args["bytes"].as_str() {
        return unhex(text);
    }
    let mut data = fs::read(dir.join(args["file"].as_str().unwrap())).unwrap();
    if let (Some(start), Some(size)) = (args["start"].as_u64(), args["size"].as_u64()) {
        data = data[start as usize..(start + size) as usize].to_vec();
    }
    match args.get("edit") {
        Some(edit) if !edit.is_null() => edited(&data, edit).unwrap(),
        _ => data,
    }
}

fn fields(obj: &[u8]) -> Result<Value, PyErr> {
    let (name, at, rect) = card_titles::sprite_fields(obj)?;
    let packed: Vec<u8> = rect
        .iter()
        .flat_map(|v| (*v as f32).to_le_bytes())
        .collect();
    Ok(json!([
        name,
        [at.rect, at.vertices, at.texture_rect, at.uv_transform],
        hex(&packed)
    ]))
}

fn relayout(dir: &Path, args: &Value) -> Result<Value, PyErr> {
    let layout = match &args["layout"] {
        Value::Null => card_titles::load_layout(&repo().join("resources/catalog"))?.unwrap(),
        layout => layout.clone(),
    };
    let folder = dir
        .join("titles")
        .join(args["layer"].as_str().unwrap())
        .join("19");
    let edits = &args["edits"];
    let mut read = |asset: u64| {
        let name = format!("{asset:016X}");
        let data = fs::read(folder.join(format!("{name}.bin"))).ok()?;
        match edits.get(&name) {
            Some(edit) => edited(&data, edit),
            None => Some(data),
        }
    };
    Ok(match card_titles::relayout(&mut read, &layout)? {
        None => Value::Null,
        Some(jobs) => jobs
            .iter()
            .map(|(asset, raw)| json!([format!("{asset:016X}"), blob(raw)]))
            .collect(),
    })
}

fn hand_apply(dir: &Path, args: &Value) -> Value {
    let edits = hand_card_titles::load_edits(&repo().join("resources/catalog")).unwrap();
    let find = |hash: &str| {
        let hash = u64::from_str_radix(hash, 16).unwrap();
        edits
            .iter()
            .find(|(asset, _)| *asset == hash)
            .unwrap()
            .1
            .clone()
    };
    let base = find(
        args["other"]
            .as_str()
            .unwrap_or(args["asset"].as_str().unwrap()),
    );
    let text = |key: &str, default: &str| args[key].as_str().unwrap_or(default).to_owned();
    let edit = TitleEdit {
        source: text("source", &base.source),
        target: text("target", &base.target),
        box_: match args["box"].as_array() {
            Some(items) => [0, 1, 2, 3].map(|i| items[i].as_i64().unwrap()),
            None => base.box_,
        },
        blocks: match args["blocks_cut"].as_u64() {
            Some(cut) => base.blocks[..cut as usize].to_vec(),
            None => base.blocks,
        },
    };
    let raw = bytes_of(dir, args);
    json!({"ok": edit.apply(&raw).map(|out| blob(&out))})
}

pub fn call(dir: &Path, function: &str, args: &Value) -> Option<Value> {
    let catalog = || repo().join(args["catalog"].as_str().unwrap());
    Some(match function {
        "st_rects" => {
            let rects = sprite_table::sprite_rects(
                &bytes_of(dir, args),
                args["width"].as_i64().unwrap(),
                args["height"].as_i64(),
            );
            let list: Vec<Value> = rects
                .into_iter()
                .map(|(name, rect)| json!([name, rect]))
                .collect();
            json!({"ok": list})
        }
        "ct_fields" => py(fields(&bytes_of(dir, args))),
        "ct_relayout" => py(relayout(dir, args)),
        "ct_load_layout" => {
            py(card_titles::load_layout(&catalog()).map(|l| l.unwrap_or(Value::Null)))
        }
        "hc_load" => py(hand_card_titles::load_edits(&catalog()).map(|edits| {
            edits
                .iter()
                .map(|(asset, e)| {
                    json!([
                        format!("{asset:016X}"),
                        e.source,
                        e.target,
                        e.box_,
                        sha(&e.blocks)
                    ])
                })
                .collect()
        })),
        "hc_apply" => hand_apply(dir, args),
        _ => return None,
    })
}
