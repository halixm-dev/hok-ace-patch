//! `tools/lineup_codes.py`: translate the text inside a lineup bin's share codes, and reseal the bin.
//!
//! A share code is padded base64 of raw deflate of an `OSProto.OneLineup`; `rewrite_code` decodes it,
//! translates the schema's text fields with each message's field order kept, re-deflates it the way
//! zlib does at its default settings (`pyzlib`) and checks it reads back. `rewrite_bin` does that for
//! every row's code and text fields, then reseals fields 1 and 4. Errors keep Python's class
//! (`NotLineupBin`, `NotConfigBin` or what Python lets through) and text.

use crate::axml::PyErr;
use crate::config_bin::{self, Field, NOT_CONFIG_BIN, ROW_FIELD, Value};
use crate::pb_text::is_cjk;
use crate::pyzlib;

pub const NOT_LINEUP_BIN: &str = "NotLineupBin";

/// A message's text fields by number; `Some` is a submessage's schema.
pub struct Schema(pub &'static [(u128, Option<&'static Schema>)]);

impl Schema {
    fn get(&self, number: u128) -> Option<Option<&'static Schema>> {
        self.0
            .iter()
            .find(|(field, _)| *field == number)
            .map(|(_, inner)| *inner)
    }
}

pub static HERO: Schema = Schema(&[(7, None)]);
pub static OPERATION: Schema = Schema(&[(6, None), (4, Some(&HERO)), (5, Some(&HERO))]);
pub static LORD: Schema = Schema(&[(2, None)]);
pub static ONE_LINEUP: Schema = Schema(&[
    (1, None),
    (2, None),
    (5, None),
    (6, None),
    (7, None),
    (12, None),
    (13, None),
    (3, Some(&HERO)),
    (8, Some(&OPERATION)),
    (9, Some(&LORD)),
]);

/// `LineupBin`: the row field holding the share code and the rows' own text fields.
pub struct LineupBin {
    pub code_field: u128,
    pub text_fields: &'static [u128],
}

pub const LINEUP_BINS: &[(u64, LineupBin)] = &[
    (
        0xF79F_B1A2_13A9_DA90,
        LineupBin {
            code_field: 4,
            text_fields: &[9, 19],
        },
    ),
    (
        0x6A2B_886E_5DCF_22DC,
        LineupBin {
            code_field: 11,
            text_fields: &[],
        },
    ),
    (
        0xC0C5_6FEF_DCA0_EA5D,
        LineupBin {
            code_field: 5,
            text_fields: &[7],
        },
    ),
];

pub fn lineup_bin(file_hash: u64) -> Option<&'static LineupBin> {
    LINEUP_BINS
        .iter()
        .find(|(hash, _)| *hash == file_hash)
        .map(|(_, bin)| bin)
}

pub type Translate<'a> = &'a mut dyn FnMut(&str) -> Option<String>;

fn not_lineup_bin(message: impl Into<String>) -> PyErr {
    PyErr::new(NOT_LINEUP_BIN, message)
}

/// `NOT_BASE64.sub(b"", code)`.
fn base64_only(code: &[u8]) -> Vec<u8> {
    code.iter()
        .copied()
        .filter(|&b| b.is_ascii_alphanumeric() || matches!(b, b'+' | b'/' | b'='))
        .collect()
}

/// `decode_code`: the `OneLineup` bytes of a share code, by the game's steps.
pub fn decode_code(code: &[u8]) -> Result<Vec<u8>, PyErr> {
    pyzlib::b64decode(&base64_only(code))
        .and_then(|packed| pyzlib::inflate_raw(&packed))
        .map_err(|error| not_lineup_bin(format!("share code does not decode ({})", error.message)))
}

/// `encode_code`: raw deflate at zlib's default settings, then padded base64.
pub fn encode_code(message: &[u8]) -> Vec<u8> {
    pyzlib::b64encode(&pyzlib::deflate_raw(message))
}

fn bytes(value: &Value) -> &[u8] {
    match value {
        Value::Bytes(bytes) => bytes,
        Value::Int(_) => unreachable!("a wire-2 field holds bytes"),
    }
}

fn translated(value: &[u8], translate: Translate<'_>) -> Option<Vec<u8>> {
    let text = std::str::from_utf8(value).ok()?;
    if !text.chars().any(is_cjk) {
        return None;
    }
    let target = translate(text)?;
    (!target.is_empty() && target != text).then(|| target.into_bytes())
}

fn parsed(data: &[u8]) -> Result<Vec<Field>, PyErr> {
    let entries = config_bin::fields(data)?;
    if config_bin::encode(&entries)? != data {
        return Err(not_lineup_bin("framing does not re-serialize identically"));
    }
    Ok(entries)
}

fn message(
    data: &[u8],
    schema: &Schema,
    translate: Translate<'_>,
) -> Result<(Vec<u8>, u64), PyErr> {
    let mut entries = parsed(data)?;
    let mut changed = 0;
    for entry in &mut entries {
        let Some(inner) = schema.get(entry.number) else {
            continue;
        };
        if entry.wire != 2 {
            continue;
        }
        let (new, count) = match inner {
            None => match translated(bytes(&entry.value), translate) {
                Some(new) => (new, 1),
                None => continue,
            },
            Some(inner) => message(bytes(&entry.value), inner, translate)?,
        };
        if count != 0 {
            entry.value = Value::Bytes(new);
            changed += count;
        }
    }
    if changed == 0 {
        return Ok((data.to_vec(), 0));
    }
    Ok((config_bin::encode(&entries)?, changed))
}

/// `rewrite_code`: (<code> with its text translated, strings replaced); <code> itself when nothing changes.
pub fn rewrite_code(code: &[u8], translate: Translate<'_>) -> Result<(Vec<u8>, u64), PyErr> {
    let decoded = decode_code(code)?;
    let (new, changed) = message(&decoded, &ONE_LINEUP, translate).map_err(|error| {
        if error.class == NOT_CONFIG_BIN {
            not_lineup_bin(format!("share code is not a OneLineup ({})", error.message))
        } else {
            error
        }
    })?;
    if changed == 0 {
        return Ok((code.to_vec(), 0));
    }
    let new_code = encode_code(&new);
    if decode_code(&new_code)? != new {
        return Err(not_lineup_bin("re-encoded share code does not read back"));
    }
    Ok((new_code, changed))
}

fn wrap(file_hash: u64) -> impl Fn(PyErr) -> PyErr {
    move |error| {
        if error.class == NOT_CONFIG_BIN {
            not_lineup_bin(format!(
                "{file_hash:016X} is not a config bin ({})",
                error.message
            ))
        } else {
            error
        }
    }
}

fn rewrite_rows(
    bin: &LineupBin,
    raw: &[u8],
    translate: Translate<'_>,
) -> Result<(Vec<u8>, u64), PyErr> {
    let mut entries = parsed(raw)?;
    let mut changed = 0;
    for entry in &mut entries {
        if entry.number != ROW_FIELD || entry.wire != 2 {
            continue;
        }
        let mut row = parsed(bytes(&entry.value))?;
        let mut row_changed = 0;
        for slot in &mut row {
            if slot.wire != 2 {
                continue;
            }
            let (new, count) = if slot.number == bin.code_field {
                rewrite_code(bytes(&slot.value), translate)?
            } else if bin.text_fields.contains(&slot.number) {
                match translated(bytes(&slot.value), translate) {
                    Some(new) => (new, 1),
                    None => continue,
                }
            } else {
                continue;
            };
            if count != 0 {
                slot.value = Value::Bytes(new);
                row_changed += count;
            }
        }
        if row_changed != 0 {
            entry.value = Value::Bytes(config_bin::encode(&row)?);
            changed += row_changed;
        }
    }
    if changed == 0 {
        return Ok((raw.to_vec(), 0));
    }
    let new_raw = config_bin::encode(&config_bin::reseal(&entries)?)?;
    if !config_bin::is_sealed(&new_raw)? {
        return Err(not_lineup_bin(
            "resealed bin does not pass its own checksum",
        ));
    }
    Ok((new_raw, changed))
}

/// `rewrite_bin`: (<raw> with its codes' and rows' text translated and the bin resealed, strings replaced).
///
/// Panics on a hash outside `LINEUP_BINS`, where Python raises `KeyError`.
pub fn rewrite_bin(
    file_hash: u64,
    raw: &[u8],
    translate: Translate<'_>,
) -> Result<(Vec<u8>, u64), PyErr> {
    let bin = lineup_bin(file_hash).expect("a lineup bin");
    rewrite_rows(bin, raw, translate).map_err(wrap(file_hash))
}

fn collect_rows(bin: &LineupBin, raw: &[u8], found: &mut Vec<String>) -> Result<(), PyErr> {
    let mut collect = |text: &str| {
        found.push(text.to_owned());
        None
    };
    for entry in config_bin::fields(raw)? {
        if entry.number != ROW_FIELD || entry.wire != 2 {
            continue;
        }
        for slot in config_bin::fields(bytes(&entry.value))? {
            if slot.wire != 2 {
                continue;
            }
            if slot.number == bin.code_field {
                message(&decode_code(bytes(&slot.value))?, &ONE_LINEUP, &mut collect)?;
            } else if bin.text_fields.contains(&slot.number) {
                translated(bytes(&slot.value), &mut collect);
            }
        }
    }
    Ok(())
}

/// `strings`: every Chinese string the pass would offer to translate in <raw>, in stored order.
pub fn strings(file_hash: u64, raw: &[u8]) -> Result<Vec<String>, PyErr> {
    let bin = lineup_bin(file_hash).expect("a lineup bin");
    let mut found = Vec::new();
    collect_rows(bin, raw, &mut found).map_err(wrap(file_hash))?;
    Ok(found)
}
