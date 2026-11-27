//! `tools/hand_card_titles.py`: apply the measured title edits to the mobile edition's captured Secret
//! Technique cards (package 15), by the SHA-256 of the capture before and after.

use std::path::Path;

use serde_json::Value;
use sha2::{Digest, Sha256};

use crate::axml::PyErr;
use crate::card_titles::{SPRITE_ART, TITLE_ATLAS, py_slice};

pub const PACKAGE: &str = "15";
pub const WIDTH: i64 = 404;
pub const HEIGHT: i64 = 564;
pub const BLOCK_SIDE: i64 = 4;
pub const BLOCK_BYTES: i64 = 16;
pub const ROW_BYTES: i64 = WIDTH / BLOCK_SIDE * BLOCK_BYTES;
pub const RAW_SIZE: i64 = ROW_BYTES * (HEIGHT / BLOCK_SIDE);

fn sha256_hex(data: &[u8]) -> String {
    Sha256::digest(data)
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

/// One card's title edit; `box_` is in ASTC blocks, in the texture's stored (bottom-up) order.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TitleEdit {
    pub source: String,
    pub target: String,
    pub box_: [i64; 4],
    pub blocks: Vec<u8>,
}

impl TitleEdit {
    /// `apply`: the title blocks replaced on a known capture, the capture itself when already edited, or
    /// None for an unmeasured revision.
    pub fn apply(&self, raw: &[u8]) -> Option<Vec<u8>> {
        let digest = sha256_hex(raw);
        if digest == self.target {
            return Some(raw.to_vec());
        }
        if raw.len() as i64 != RAW_SIZE || digest != self.source {
            return None;
        }
        let [x0, y0, x1, y1] = self.box_;
        let span = (x1 - x0) * BLOCK_BYTES;
        if !(0 <= x0
            && x0 < x1
            && x1 <= WIDTH / BLOCK_SIDE
            && 0 <= y0
            && y0 < y1
            && y1 <= HEIGHT / BLOCK_SIDE
            && self.blocks.len() as i64 == (y1 - y0) * span)
        {
            return None;
        }
        let mut patched = raw.to_vec();
        let span = span as usize;
        for row in y0..y1 {
            let start = (row * ROW_BYTES + x0 * BLOCK_BYTES) as usize;
            let offset = ((row - y0) as usize) * span;
            patched[start..start + span].copy_from_slice(&self.blocks[offset..offset + span]);
        }
        (sha256_hex(&patched) == self.target).then_some(patched)
    }
}

fn shape() -> PyErr {
    PyErr::new("TypeError", "hand_titles.json is not shaped as shipped")
}

fn field<'v>(record: &'v Value, key: &str) -> Result<&'v Value, PyErr> {
    record
        .as_object()
        .ok_or_else(shape)?
        .get(key)
        .ok_or_else(|| PyErr::new("KeyError", crate::catalog::py_repr(key)))
}

fn int(value: &Value) -> Result<i64, PyErr> {
    value.as_i64().ok_or_else(shape)
}

/// `load_edits`: the shared English title art both patch languages use on these cards, by asset hash in
/// the manifest's order; empty when the manifest is missing.
pub fn load_edits(catalog_dir: &Path) -> Result<Vec<(u64, TitleEdit)>, PyErr> {
    let folder = catalog_dir
        .parent()
        .unwrap_or(catalog_dir)
        .join(SPRITE_ART)
        .join(format!("{TITLE_ATLAS:016X}"));
    let manifest = folder.join("hand_titles.json");
    if !manifest.is_file() {
        return Ok(Vec::new());
    }
    let os = |e: std::io::Error| PyErr::new("OSError", e.to_string());
    let records: Value = serde_json::from_str(&std::fs::read_to_string(&manifest).map_err(os)?)
        .map_err(|e| PyErr::new("JSONDecodeError", e.to_string()))?;
    let blocks = std::fs::read(folder.join("hand_titles.blocks")).map_err(os)?;
    let mut edits = Vec::new();
    for (asset, record) in records.as_object().ok_or_else(shape)? {
        let offset = int(field(record, "offset")?)?;
        let size = int(field(record, "size")?)?;
        let source = field(record, "source")?.as_str().ok_or_else(shape)?;
        let target = field(record, "target")?.as_str().ok_or_else(shape)?;
        let box_: Vec<i64> = field(record, "box")?
            .as_array()
            .ok_or_else(shape)?
            .iter()
            .map(int)
            .collect::<Result<_, _>>()?;
        let hash = u64::from_str_radix(asset, 16).map_err(|_| {
            PyErr::new(
                "ValueError",
                format!(
                    "invalid literal for int() with base 16: {}",
                    crate::catalog::py_repr(asset)
                ),
            )
        })?;
        edits.push((
            hash,
            TitleEdit {
                source: source.to_owned(),
                target: target.to_owned(),
                box_: box_.try_into().map_err(|_| shape())?,
                blocks: py_slice(&blocks, offset, offset + size).to_vec(),
            },
        ));
    }
    Ok(edits)
}
