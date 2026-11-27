//! `tools/config_bin.py`: a config bin's protobuf framing and the two digests the game stores beside
//! its rows (field 1, the rows' MD5 as upper-case hex; field 4, `PBDatabinLoader`'s 32-bit fold).
//!
//! A field's value is an int for wire type 0 and bytes otherwise, as in Python, and `reseal` swaps in
//! bytes for field 1 and an int for field 4 whatever their wire type. The `TypeError` and
//! `OverflowError` Python raises on a value of the other kind are kept, with their text, because a
//! caller of `lineup_codes` lets them through.

use crate::axml::PyErr;
use md5::{Digest, Md5};

pub const FOLD_SEED: u32 = 0x0123_4567;
pub const FOLD_MULTIPLIER: u32 = 0x89AB_CDEF;
pub const DIGEST_FIELD: u128 = 1;
pub const ROW_FIELD: u128 = 2;
pub const INDEX_FIELD: u128 = 3;
pub const CHECKSUM_FIELD: u128 = 4;

/// The class `NotConfigBin` errors carry.
pub const NOT_CONFIG_BIN: &str = "NotConfigBin";

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Value {
    Int(u128),
    Bytes(Vec<u8>),
}

/// `(field number, wire type, value)`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Field {
    pub number: u128,
    pub wire: u8,
    pub value: Value,
}

fn not_config_bin(message: impl Into<String>) -> PyErr {
    PyErr::new(NOT_CONFIG_BIN, message)
}

fn type_error(message: impl Into<String>) -> PyErr {
    PyErr::new("TypeError", message)
}

fn varint(data: &[u8], mut pos: usize) -> Result<(u128, usize), PyErr> {
    let (mut value, mut shift) = (0u128, 0u32);
    loop {
        if pos >= data.len() || shift > 63 {
            return Err(not_config_bin(format!("varint runs past byte {pos}")));
        }
        let byte = data[pos];
        pos += 1;
        value |= u128::from(byte & 0x7F) << shift;
        shift += 7;
        if byte < 0x80 {
            return Ok((value, pos));
        }
    }
}

pub fn put_varint(mut value: u128, out: &mut Vec<u8>) {
    loop {
        let byte = (value & 0x7F) as u8;
        value >>= 7;
        if value != 0 {
            out.push(byte | 0x80);
        } else {
            out.push(byte);
            return;
        }
    }
}

fn clip(data: &[u8], start: u128, size: u128) -> Vec<u8> {
    let len = data.len() as u128;
    let (start, end) = (
        start.min(len) as usize,
        start.saturating_add(size).min(len) as usize,
    );
    data[start..end].to_vec()
}

/// `fields`: every field in stored order; length-delimited values stay bytes.
pub fn fields(data: &[u8]) -> Result<Vec<Field>, PyErr> {
    let len = data.len() as u128;
    let (mut pos, mut found) = (0u128, Vec::new());
    while pos < len {
        let (key, after) = varint(data, pos as usize)?;
        pos = after as u128;
        let (number, wire) = (key >> 3, (key & 7) as u8);
        let value = match wire {
            0 => {
                let (value, after) = varint(data, pos as usize)?;
                pos = after as u128;
                Value::Int(value)
            }
            2 => {
                let (size, after) = varint(data, pos as usize)?;
                pos = after as u128;
                let value = clip(data, pos, size);
                pos += size;
                Value::Bytes(value)
            }
            1 | 5 => {
                let size = if wire == 1 { 8 } else { 4 };
                let value = clip(data, pos, size);
                pos += size;
                Value::Bytes(value)
            }
            _ => return Err(not_config_bin(format!("wire type {wire} at byte {pos}"))),
        };
        if pos > len || number == 0 {
            return Err(not_config_bin("field runs past the end"));
        }
        found.push(Field {
            number,
            wire,
            value,
        });
    }
    Ok(found)
}

/// `encode`: minimal varints and lengths, in the order given.
pub fn encode(entries: &[Field]) -> Result<Vec<u8>, PyErr> {
    let mut out = Vec::new();
    for field in entries {
        put_varint(field.number << 3 | u128::from(field.wire), &mut out);
        match (field.wire, &field.value) {
            (0, Value::Int(value)) => put_varint(*value, &mut out),
            (0, Value::Bytes(_)) => {
                return Err(type_error(
                    "unsupported operand type(s) for &: 'bytes' and 'int'",
                ));
            }
            (2, Value::Bytes(value)) => {
                put_varint(value.len() as u128, &mut out);
                out.extend_from_slice(value);
            }
            (2, Value::Int(_)) => return Err(type_error("object of type 'int' has no len()")),
            (_, Value::Bytes(value)) => out.extend_from_slice(value),
            (_, Value::Int(_)) => return Err(type_error("can't concat int to bytearray")),
        }
    }
    Ok(out)
}

fn fold(mut state: u32, data: &[u8]) -> u32 {
    for &byte in data {
        state = (state ^ u32::from(byte)).wrapping_mul(FOLD_MULTIPLIER);
    }
    state
}

fn packed(value: &Value, wire: u8) -> Result<Vec<u128>, PyErr> {
    match (wire, value) {
        (0, Value::Int(value)) => Ok(vec![*value]),
        (_, Value::Bytes(bytes)) => {
            let (mut found, mut pos) = (Vec::new(), 0);
            while pos < bytes.len() {
                let (number, after) = varint(bytes, pos)?;
                found.push(number);
                pos = after;
            }
            Ok(found)
        }
        (_, Value::Int(_)) => Err(type_error("'int' object is not iterable")),
    }
}

fn index_fields(value: &Value) -> Result<Vec<Field>, PyErr> {
    match value {
        Value::Bytes(bytes) => fields(bytes),
        Value::Int(_) => Err(type_error("object of type 'int' has no len()")),
    }
}

fn fold_number(state: u32, number: u128) -> Result<u32, PyErr> {
    let number =
        u32::try_from(number).map_err(|_| PyErr::new("OverflowError", "int too big to convert"))?;
    Ok(fold(state, &number.to_le_bytes()))
}

/// `rows_md5`: field 1, the MD5 of the rows' bytes as upper-case hex.
pub fn rows_md5(entries: &[Field]) -> Result<Vec<u8>, PyErr> {
    let mut hasher = Md5::new();
    for (item, field) in entries
        .iter()
        .filter(|field| field.number == ROW_FIELD)
        .enumerate()
    {
        match &field.value {
            Value::Bytes(bytes) => hasher.update(bytes),
            Value::Int(_) => {
                return Err(type_error(format!(
                    "sequence item {item}: expected a bytes-like object, int found"
                )));
            }
        }
    }
    let digest = hasher.finalize();
    Ok(digest
        .iter()
        .flat_map(|byte| format!("{byte:02X}").into_bytes())
        .collect())
}

/// `checksum`: field 4, as `DecodeFromStream` computes it.
pub fn checksum(entries: &[Field]) -> Result<u32, PyErr> {
    let mut state = FOLD_SEED;
    for field in entries.iter().filter(|field| field.number == ROW_FIELD) {
        match &field.value {
            Value::Bytes(bytes) => state = fold(state, bytes),
            Value::Int(_) => return Err(type_error("'int' object is not iterable")),
        }
    }
    let (mut keys, mut index_entries) = (Vec::new(), Vec::new());
    for field in entries.iter().filter(|field| field.number == INDEX_FIELD) {
        for inner in index_fields(&field.value)? {
            if inner.number == 1 {
                keys.extend(packed(&inner.value, inner.wire)?);
            } else if inner.number == 2 {
                index_entries.push(inner.value);
            }
        }
    }
    for key in keys {
        state = fold_number(state, key)?;
    }
    for entry in &index_entries {
        for inner in index_fields(entry)? {
            if inner.number == 1 || inner.number == 2 {
                for number in packed(&inner.value, inner.wire)? {
                    state = fold_number(state, number)?;
                }
            }
        }
    }
    Ok(state)
}

/// `reseal`: fields 1 and 4 recomputed, everything else and the order kept.
pub fn reseal(entries: &[Field]) -> Result<Vec<Field>, PyErr> {
    let digest = rows_md5(entries)?;
    let sum = checksum(entries)?;
    Ok(entries
        .iter()
        .map(|field| Field {
            number: field.number,
            wire: field.wire,
            value: match field.number {
                DIGEST_FIELD => Value::Bytes(digest.clone()),
                CHECKSUM_FIELD => Value::Int(u128::from(sum)),
                _ => field.value.clone(),
            },
        })
        .collect())
}

/// `is_sealed`: <raw>'s stored fields 1 and 4 are the values its rows and index give.
pub fn is_sealed(raw: &[u8]) -> Result<bool, PyErr> {
    let entries = fields(raw)?;
    let stored = |number| {
        entries
            .iter()
            .rev()
            .find(|field| field.number == number)
            .map(|field| &field.value)
    };
    let digest = rows_md5(&entries)?;
    if stored(DIGEST_FIELD) != Some(&Value::Bytes(digest)) {
        return Ok(false);
    }
    Ok(stored(CHECKSUM_FIELD) == Some(&Value::Int(u128::from(checksum(&entries)?))))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_resealed_bin_is_sealed() {
        let row = Field {
            number: 2,
            wire: 2,
            value: Value::Bytes(b"\x08\x01".to_vec()),
        };
        let entries = vec![
            Field {
                number: 1,
                wire: 2,
                value: Value::Bytes(vec![b'0'; 32]),
            },
            row,
            Field {
                number: 4,
                wire: 0,
                value: Value::Int(0),
            },
        ];
        let raw = encode(&reseal(&entries).unwrap()).unwrap();
        assert!(is_sealed(&raw).unwrap());
        assert_eq!(
            fields(&raw[..raw.len() - 1]).unwrap_err().message,
            format!("varint runs past byte {}", raw.len() - 1)
        );
    }
}
