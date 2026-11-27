//! `tools/unity_text.py`: replace display strings inside Unity 2022.3 SerializedFiles whose type trees
//! were stripped. Not used by the pipeline (`extra_text.UNITY_TEXT_PACKAGES` is empty); kept as the one
//! reader of the format.
//!
//! The parser reads offsets as Python's unbounded ints, so a corrupt type entry can move the position
//! backwards or below zero; the reads then fail, or index from the end, as `struct` and `bytes` do.

use crate::axml::PyErr;

pub const MONO_BEHAVIOUR: i32 = 114;
pub const OBJECT_ALIGN: i64 = 8;
pub const UNSUPPORTED_FILE: &str = "UnsupportedFile";

fn unsupported(message: impl Into<String>) -> PyErr {
    PyErr::new(UNSUPPORTED_FILE, message)
}

fn struct_error(message: String) -> PyErr {
    PyErr::new("error", message)
}

pub(crate) fn align(value: i64, to: i64) -> i64 {
    (value + to - 1).div_euclid(to) * to
}

/// `struct.unpack_from`'s bounds, negative offsets included.
pub(crate) fn unpack(data: &[u8], size: usize, offset: i64) -> Result<&[u8], PyErr> {
    let (len, size_i) = (data.len() as i64, size as i64);
    let mut offset = offset;
    if offset < 0 {
        if offset + size_i > 0 {
            return Err(struct_error(format!(
                "not enough data to unpack {size} bytes at offset {offset}"
            )));
        }
        if offset + len < 0 {
            return Err(struct_error(format!(
                "offset {offset} out of range for {len}-byte buffer"
            )));
        }
        offset += len;
    }
    if len - offset < size_i {
        return Err(struct_error(format!(
            "unpack_from requires a buffer of at least {} bytes for unpacking {size} bytes at offset {offset} \
             (actual buffer size is {len})",
            size_i + offset
        )));
    }
    Ok(&data[offset as usize..offset as usize + size])
}

/// `struct.pack_into`'s bounds, negative offsets included.
pub(crate) fn pack(data: &mut [u8], offset: i64, bytes: &[u8]) -> Result<(), PyErr> {
    let (len, size) = (data.len() as i64, bytes.len() as i64);
    let mut offset = offset;
    if offset < 0 {
        if offset + size > 0 {
            return Err(struct_error(format!(
                "no space to pack {size} bytes at offset {offset}"
            )));
        }
        if offset + len < 0 {
            return Err(struct_error(format!(
                "offset {offset} out of range for {len}-byte buffer"
            )));
        }
        offset += len;
    }
    if len - offset < size {
        return Err(struct_error(format!(
            "pack_into requires a buffer of at least {} bytes for packing {size} bytes at offset {offset} \
             (actual buffer size is {len})",
            size + offset
        )));
    }
    data[offset as usize..(offset + size) as usize].copy_from_slice(bytes);
    Ok(())
}

fn byte_at(data: &[u8], pos: i64) -> Result<u8, PyErr> {
    let len = data.len() as i64;
    let at = if pos < 0 { pos + len } else { pos };
    if at < 0 || at >= len {
        return Err(PyErr::new("IndexError", "index out of range"));
    }
    Ok(data[at as usize])
}

fn i32_at(data: &[u8], pos: i64) -> Result<i32, PyErr> {
    Ok(i32::from_le_bytes(
        unpack(data, 4, pos)?.try_into().expect("4 bytes"),
    ))
}

/// One object table entry: `[table offset, path id, byte start, byte size, type index]`.
#[derive(Debug, Clone)]
pub struct Object {
    pub table: i64,
    pub path_id: i64,
    pub start: u64,
    pub size: u32,
    pub type_index: i32,
}

pub struct SerializedFile<'a> {
    pub data: &'a [u8],
    pub metadata_size: u32,
    pub file_size: u64,
    pub data_offset: u64,
    pub class_ids: Vec<i32>,
    pub objects: Vec<Object>,
}

impl<'a> SerializedFile<'a> {
    pub fn parse(data: &'a [u8]) -> Result<Self, PyErr> {
        if data.len() < 48 {
            return Err(unsupported("too small"));
        }
        let be32 = |at: usize| u32::from_be_bytes(data[at..at + 4].try_into().expect("4 bytes"));
        let be64 = |at: usize| u64::from_be_bytes(data[at..at + 8].try_into().expect("8 bytes"));
        let version = be32(8);
        if version != 22 || data[16] != 0 {
            return Err(unsupported(format!("format {version}")));
        }
        let metadata_size = be32(20);
        let (file_size, data_offset) = (be64(24), be64(32));
        if file_size != data.len() as u64 {
            return Err(unsupported("size mismatch"));
        }
        let end = data[48..]
            .iter()
            .position(|&b| b == 0)
            .ok_or_else(|| PyErr::new("ValueError", "subsection not found"))?;
        let mut pos = (48 + end + 1) as i64;
        pos += 4;
        let type_tree = byte_at(data, pos)?;
        pos += 1;
        let type_count = i32_at(data, pos)?;
        pos += 4;
        let mut class_ids = Vec::new();
        for _ in 0..type_count.max(0) {
            let entry = unpack(data, 7, pos)?;
            let class_id = i32::from_le_bytes(entry[..4].try_into().expect("4 bytes"));
            let script_index = i16::from_le_bytes(entry[5..7].try_into().expect("2 bytes"));
            pos += 7;
            if class_id == MONO_BEHAVIOUR || script_index >= 0 {
                pos += 16;
            }
            pos += 16;
            if type_tree != 0 {
                let nodes = i64::from(i32_at(data, pos)?);
                pos += 4;
                if nodes != 0 {
                    let string_size = i64::from(i32_at(data, pos)?);
                    pos += 4 + nodes * 32 + string_size;
                    let dependencies = i64::from(i32_at(data, pos)?);
                    pos += 4 + 4 * dependencies;
                }
            }
            class_ids.push(class_id);
        }
        let object_count = i32_at(data, pos)?;
        pos += 4;
        let mut objects = Vec::new();
        for _ in 0..object_count.max(0) {
            pos = align(pos, 4);
            let entry = unpack(data, 24, pos)?;
            objects.push(Object {
                table: pos,
                path_id: i64::from_le_bytes(entry[..8].try_into().expect("8 bytes")),
                start: u64::from_le_bytes(entry[8..16].try_into().expect("8 bytes")),
                size: u32::from_le_bytes(entry[16..20].try_into().expect("4 bytes")),
                type_index: i32::from_le_bytes(entry[20..24].try_into().expect("4 bytes")),
            });
            pos += 24;
        }
        let valid = |o: &Object| {
            0 <= o.type_index
                && (o.type_index as usize) < class_ids.len()
                && u128::from(data_offset) + u128::from(o.start) + u128::from(o.size)
                    <= data.len() as u128
        };
        if pos > 48 + i64::from(metadata_size) || !objects.iter().all(valid) {
            return Err(unsupported("object table does not validate"));
        }
        Ok(Self {
            data,
            metadata_size,
            file_size,
            data_offset,
            class_ids,
            objects,
        })
    }

    /// `rewrite`: (new file bytes, strings replaced); the input when nothing was replaced.
    pub fn rewrite(
        &self,
        translate: &mut dyn FnMut(&str) -> Option<String>,
    ) -> Result<(Vec<u8>, u64), PyErr> {
        let mut order: Vec<&Object> = self.objects.iter().collect();
        order.sort_by_key(|o| o.start);
        let mut pieces = Vec::with_capacity(order.len());
        let mut replaced = 0;
        for obj in order {
            let start = (self.data_offset + obj.start) as usize;
            let mut body = self.data[start..start + obj.size as usize].to_vec();
            if self.class_ids[obj.type_index as usize] == MONO_BEHAVIOUR {
                let (new, count) = rewrite_strings(&body, translate);
                body = new;
                replaced += count;
            }
            pieces.push((obj, body));
        }
        if replaced == 0 {
            return Ok((self.data.to_vec(), 0));
        }
        let data_offset = self.data_offset as i64;
        let mut out = self.data[..self.data_offset as usize].to_vec();
        for (obj, body) in pieces {
            let offset = align(out.len() as i64, OBJECT_ALIGN) - data_offset;
            out.resize((data_offset + offset) as usize, 0);
            let mut entry = (offset as u64).to_le_bytes().to_vec();
            entry.extend_from_slice(&(body.len() as u32).to_le_bytes());
            pack(&mut out, obj.table + 8, &entry)?;
            out.extend_from_slice(&body);
        }
        let size = (out.len() as u64).to_be_bytes();
        pack(&mut out, 24, &size)?;
        Ok((out, replaced))
    }
}

fn has_cjk(text: &str) -> bool {
    text.chars().any(|c| ('\u{3400}'..='\u{9fff}').contains(&c))
}

/// `_rewrite_strings`: every int32-length UTF-8 string in an object body, padded to 4, offered to <translate>.
pub fn rewrite_strings(
    body: &[u8],
    translate: &mut dyn FnMut(&str) -> Option<String>,
) -> (Vec<u8>, u64) {
    let mut out = Vec::with_capacity(body.len());
    let (mut pos, mut count) = (0usize, 0u64);
    while pos + 4 <= body.len() {
        let length = i32::from_le_bytes(body[pos..pos + 4].try_into().expect("4 bytes")) as i64;
        let end = pos as i64 + 4 + length;
        if 0 < length && length <= (body.len() - pos - 4) as i64 {
            let end = end as usize;
            let padded = align(end as i64, 4) as usize;
            if !body[end..padded.min(body.len())].iter().any(|&b| b != 0) {
                let text = std::str::from_utf8(&body[pos + 4..end]).ok();
                let replacement = match text {
                    Some(text) if !text.is_empty() && has_cjk(text) => translate(text),
                    _ => None,
                };
                if let Some(replacement) = replacement
                    && Some(replacement.as_str()) != text
                {
                    let encoded = replacement.into_bytes();
                    out.extend_from_slice(&(encoded.len() as i32).to_le_bytes());
                    out.extend_from_slice(&encoded);
                    out.resize(
                        out.len() + (align(encoded.len() as i64, 4) as usize - encoded.len()),
                        0,
                    );
                    pos = padded;
                    count += 1;
                    continue;
                }
            }
        }
        out.extend_from_slice(&body[pos..pos + 4]);
        pos += 4;
    }
    out.extend_from_slice(&body[pos.min(body.len())..]);
    (out, count)
}
