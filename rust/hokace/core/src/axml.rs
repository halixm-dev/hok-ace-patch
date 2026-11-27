//! `tools/axml_set_debuggable.py` and `tools/axml_label.py`: the two edits to a binary
//! AndroidManifest.xml, setting or clearing `android:debuggable` and writing the app's own name.
//!
//! The failures are Python's, in the same place, because the callers tell them apart:
//! `apk_preparation.manifest_to_install` leaves the name as it is on a `ValueError` (which includes
//! `UnicodeDecodeError`) and lets `struct.error` and `IndexError` fail the run.

use std::fmt;

pub const RES_STRING_POOL: u16 = 0x0001;
pub const RES_XML: u16 = 0x0003;
pub const RES_XML_START_NAMESPACE: u16 = 0x0100;
pub const RES_XML_END_NAMESPACE: u16 = 0x0101;
pub const RES_XML_START_ELEMENT: u16 = 0x0102;
pub const RES_XML_END_ELEMENT: u16 = 0x0103;
pub const RES_XML_CDATA: u16 = 0x0104;
pub const RES_XML_RESOURCE_MAP: u16 = 0x0180;
pub const UTF8_FLAG: u32 = 0x100;
pub const TYPE_REFERENCE: u8 = 0x01;
pub const TYPE_STRING: u8 = 0x03;
pub const TYPE_INT_BOOLEAN: u8 = 0x12;
pub const DEBUGGABLE_RES_ID: u32 = 0x0101_000F;
pub const LABEL_RES_ID: u32 = 0x0101_0001;
pub const ANDROID_NS: &str = "http://schemas.android.com/apk/res/android";
pub const NO_INDEX: u32 = 0xFFFF_FFFF;
const COMPONENTS: &[&str] = &[
    "activity",
    "activity-alias",
    "service",
    "receiver",
    "provider",
];

/// A Python exception: its class and `str()`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PyErr {
    pub class: &'static str,
    pub message: String,
}

impl PyErr {
    pub fn new(class: &'static str, message: impl Into<String>) -> Self {
        Self {
            class,
            message: message.into(),
        }
    }

    fn value(message: impl Into<String>) -> Self {
        Self::new("ValueError", message)
    }

    /// `ValueError` or a subclass: what `manifest_to_install` catches.
    pub fn is_value_error(&self) -> bool {
        matches!(self.class, "ValueError" | "UnicodeDecodeError")
    }
}

impl fmt::Display for PyErr {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}: {}", self.class, self.message)
    }
}

type Result<T> = std::result::Result<T, PyErr>;

/// `struct.unpack_from`'s bounds check for a format of <size> bytes.
fn need(data: &[u8], offset: usize, size: usize) -> Result<&[u8]> {
    if data.len() < offset || data.len() - offset < size {
        return Err(PyErr::new(
            "error",
            format!(
                "unpack_from requires a buffer of at least {} bytes for unpacking {size} bytes at offset {offset} \
                 (actual buffer size is {})",
                offset as u128 + size as u128,
                data.len()
            ),
        ));
    }
    Ok(&data[offset..offset + size])
}

/// `struct.pack_into`'s bounds check.
fn room(data: &mut [u8], offset: usize, size: usize) -> Result<&mut [u8]> {
    if data.len() < offset || data.len() - offset < size {
        return Err(PyErr::new(
            "error",
            format!(
                "pack_into requires a buffer of at least {} bytes for packing {size} bytes at offset {offset} \
                 (actual buffer size is {})",
                offset + size,
                data.len()
            ),
        ));
    }
    Ok(&mut data[offset..offset + size])
}

fn u16_at(data: &[u8], at: usize) -> u16 {
    u16::from_le_bytes([data[at], data[at + 1]])
}

fn u32_at(data: &[u8], at: usize) -> u32 {
    u32::from_le_bytes(data[at..at + 4].try_into().expect("four bytes"))
}

fn read_u32(data: &[u8], offset: usize) -> Result<u32> {
    need(data, offset, 4).map(|bytes| u32_at(bytes, 0))
}

fn write_u32(data: &mut [u8], offset: usize, value: u32) -> Result<()> {
    room(data, offset, 4)?.copy_from_slice(&value.to_le_bytes());
    Ok(())
}

/// `data[pos]` on `bytes`.
fn byte(data: &[u8], pos: usize) -> Result<u8> {
    data.get(pos)
        .copied()
        .ok_or_else(|| PyErr::new("IndexError", "index out of range"))
}

/// `strings[index]`.
fn string(strings: &[String], index: u64) -> Result<&str> {
    usize::try_from(index)
        .ok()
        .and_then(|index| strings.get(index))
        .map(String::as_str)
        .ok_or_else(|| PyErr::new("IndexError", "list index out of range"))
}

/// `struct.unpack_from(f"<{count}I", data, offset)`, with Python's error for a negative count.
fn u32_array(data: &[u8], offset: usize, count: i128) -> Result<Vec<u32>> {
    if count < 0 {
        return Err(PyErr::new("error", "bad char in struct format"));
    }
    let size = usize::try_from(count * 4)
        .map_err(|_| PyErr::new("error", "total struct size too long"))?;
    let bytes = need(data, offset, size)?;
    Ok(bytes
        .as_chunks::<4>()
        .0
        .iter()
        .map(|word| u32::from_le_bytes(*word))
        .collect())
}

fn decode_message(codec: &str, data: &[u8], start: usize, end: usize, reason: &str) -> PyErr {
    let message = if end - start == 1 {
        format!(
            "'{codec}' codec can't decode byte 0x{:02x} in position {start}: {reason}",
            data[start]
        )
    } else {
        format!(
            "'{codec}' codec can't decode bytes in position {start}-{}: {reason}",
            end - 1
        )
    };
    PyErr::new("UnicodeDecodeError", message)
}

/// `bytes.decode("utf-8")`, with CPython's error text.
pub fn decode_utf8(data: &[u8]) -> Result<String> {
    match std::str::from_utf8(data) {
        Ok(text) => Ok(text.to_owned()),
        Err(error) => {
            let start = error.valid_up_to();
            Err(match error.error_len() {
                None => decode_message("utf-8", data, start, data.len(), "unexpected end of data"),
                Some(length) => {
                    let lead = data[start];
                    let reason = if (0x80..=0xc1).contains(&lead) || lead >= 0xf5 {
                        "invalid start byte"
                    } else {
                        "invalid continuation byte"
                    };
                    decode_message("utf-8", data, start, start + length, reason)
                }
            })
        }
    }
}

/// `bytes.decode("utf-16-le")`, with CPython's error text.
pub fn decode_utf16le(data: &[u8]) -> Result<String> {
    let mut out = String::with_capacity(data.len() / 2);
    let mut pos = 0;
    while pos + 1 < data.len() {
        let unit = u16_at(data, pos);
        match unit {
            0xd800..=0xdbff => {
                if pos + 3 >= data.len() {
                    // A high surrogate cut short reports from it to the end of the data.
                    return Err(decode_message(
                        "utf-16-le",
                        data,
                        pos,
                        data.len(),
                        "unexpected end of data",
                    ));
                }
                let low = u16_at(data, pos + 2);
                if !(0xdc00..=0xdfff).contains(&low) {
                    return Err(decode_message(
                        "utf-16-le",
                        data,
                        pos,
                        pos + 2,
                        "illegal UTF-16 surrogate",
                    ));
                }
                let code = 0x10000 + ((u32::from(unit) - 0xd800) << 10) + (u32::from(low) - 0xdc00);
                out.push(char::from_u32(code).expect("a surrogate pair is a scalar"));
                pos += 4;
            }
            0xdc00..=0xdfff => {
                return Err(decode_message(
                    "utf-16-le",
                    data,
                    pos,
                    pos + 2,
                    "illegal encoding",
                ));
            }
            _ => {
                out.push(
                    char::from_u32(u32::from(unit)).expect("a non-surrogate unit is a scalar"),
                );
                pos += 2;
            }
        }
    }
    if pos < data.len() {
        return Err(decode_message(
            "utf-16-le",
            data,
            pos,
            data.len(),
            "truncated data",
        ));
    }
    Ok(out)
}

fn read_length8(data: &[u8], pos: usize) -> Result<(usize, usize)> {
    let value = byte(data, pos)?;
    if value & 0x80 != 0 {
        let low = byte(data, pos + 1)?;
        return Ok(((usize::from(value & 0x7f) << 8) | usize::from(low), pos + 2));
    }
    Ok((usize::from(value), pos + 1))
}

fn read_length16(data: &[u8], pos: usize) -> Result<(usize, usize)> {
    let value = usize::from(u16_at(need(data, pos, 2)?, 0));
    if value & 0x8000 != 0 {
        let low = usize::from(u16_at(need(data, pos + 2, 2)?, 0));
        return Ok((((value & 0x7fff) << 16) | low, pos + 4));
    }
    Ok((value, pos + 2))
}

/// `parse_string_pool`: the pool's strings and flags.
pub fn parse_string_pool(chunk: &[u8]) -> Result<(Vec<String>, u32)> {
    let header = need(chunk, 0, 28)?;
    let header_size = usize::from(u16_at(header, 2));
    let (count, style_count, flags, strings_start) = (
        u32_at(header, 8),
        u32_at(header, 12),
        u32_at(header, 16),
        u32_at(header, 20),
    );
    if style_count != 0 {
        return Err(PyErr::value("string pools with styles are not supported"));
    }
    let offsets = u32_array(chunk, header_size, i128::from(count))?;
    let mut strings = Vec::with_capacity(offsets.len());
    for offset in offsets {
        let pos = strings_start as usize + offset as usize;
        if flags & UTF8_FLAG != 0 {
            let (_, pos) = read_length8(chunk, pos)?;
            let (length, pos) = read_length8(chunk, pos)?;
            strings.push(decode_utf8(slice(chunk, pos, pos + length))?);
        } else {
            let (length, pos) = read_length16(chunk, pos)?;
            strings.push(decode_utf16le(slice(chunk, pos, pos + length * 2))?);
        }
    }
    Ok((strings, flags))
}

/// `data[start:end]`, clamped as Python slices are.
fn slice(data: &[u8], start: usize, end: usize) -> &[u8] {
    let end = end.min(data.len());
    &data[start.min(end)..end]
}

fn encode_length8(value: usize, out: &mut Vec<u8>) -> Result<()> {
    if value > 0x7f {
        let high = (value >> 8) | 0x80;
        let high =
            u8::try_from(high).map_err(|_| PyErr::value("bytes must be in range(0, 256)"))?;
        out.extend_from_slice(&[high, (value & 0xff) as u8]);
    } else {
        out.push(value as u8);
    }
    Ok(())
}

fn encode_length16(value: usize, out: &mut Vec<u8>) {
    if value > 0x7fff {
        out.extend_from_slice(&(((value >> 16) | 0x8000) as u16).to_le_bytes());
        out.extend_from_slice(&((value & 0xffff) as u16).to_le_bytes());
    } else {
        out.extend_from_slice(&(value as u16).to_le_bytes());
    }
}

/// `build_string_pool`: a fresh pool chunk holding <strings>, styles dropped.
pub fn build_string_pool(strings: &[String], flags: u32) -> Result<Vec<u8>> {
    let mut data = Vec::new();
    let mut offsets = Vec::with_capacity(strings.len());
    for text in strings {
        offsets.push(data.len() as u32);
        if flags & UTF8_FLAG != 0 {
            encode_length8(text.chars().count(), &mut data)?;
            encode_length8(text.len(), &mut data)?;
            data.extend_from_slice(text.as_bytes());
            data.push(0);
        } else {
            let units: Vec<u16> = text.encode_utf16().collect();
            // Python's len() counts code points, not UTF-16 units.
            encode_length16(text.chars().count(), &mut data);
            units
                .iter()
                .for_each(|unit| data.extend_from_slice(&unit.to_le_bytes()));
            data.extend_from_slice(&[0, 0]);
        }
    }
    while data.len() % 4 != 0 {
        data.push(0);
    }
    let header_size = 28u32;
    let strings_start = header_size + 4 * strings.len() as u32;
    let size = strings_start + data.len() as u32;
    let mut out = Vec::with_capacity(size as usize);
    out.extend_from_slice(&RES_STRING_POOL.to_le_bytes());
    out.extend_from_slice(&(header_size as u16).to_le_bytes());
    for word in [size, strings.len() as u32, 0, flags, strings_start, 0] {
        out.extend_from_slice(&word.to_le_bytes());
    }
    offsets
        .iter()
        .for_each(|offset| out.extend_from_slice(&offset.to_le_bytes()));
    out.extend_from_slice(&data);
    Ok(out)
}

fn shift(value: u32, index: u32) -> u32 {
    if value != NO_INDEX && value >= index {
        value + 1
    } else {
        value
    }
}

/// The file header and its chunks, as both edits split them.
/// Each chunk's type and bytes.
type Chunks = Vec<(u16, Vec<u8>)>;

fn chunks(manifest: &[u8]) -> Result<(usize, Chunks)> {
    let header = need(manifest, 0, 8)?;
    if u16_at(header, 0) != RES_XML {
        return Err(PyErr::value("not a binary XML file"));
    }
    let header_size = usize::from(u16_at(header, 2));
    let mut out = Vec::new();
    let mut pos = header_size;
    while pos < manifest.len() {
        let head = need(manifest, pos, 8)?;
        let (kind, size) = (u16_at(head, 0), u32_at(head, 4) as usize);
        if size == 0 {
            // Python's loop never advances here; the port refuses instead of spinning.
            return Err(PyErr::value("a chunk of size 0 would never end the walk"));
        }
        out.push((kind, slice(manifest, pos, pos + size).to_vec()));
        pos += size;
    }
    Ok((header_size, out))
}

fn join(header_size: usize, chunks: &[(u16, Vec<u8>)]) -> Vec<u8> {
    let length: usize = chunks.iter().map(|(_, body)| body.len()).sum();
    let mut out = Vec::with_capacity(header_size + length);
    out.extend_from_slice(&RES_XML.to_le_bytes());
    out.extend_from_slice(&(header_size as u16).to_le_bytes());
    out.extend_from_slice(&((header_size + length) as u32).to_le_bytes());
    chunks
        .iter()
        .for_each(|(_, body)| out.extend_from_slice(body));
    out
}

fn resource_ids(map: &[u8]) -> Result<Vec<u32>> {
    u32_array(map, 8, (map.len() as i128 - 8).div_euclid(4))
}

/// One attribute record, `<IIIHBBI>`.
#[derive(Clone, Copy, Debug)]
struct Attribute {
    namespace: u32,
    name: u32,
    raw: u32,
    value_size: u16,
    res0: u8,
    value_type: u8,
    data: u32,
}

impl Attribute {
    fn read(body: &[u8], offset: usize) -> Result<Self> {
        let bytes = need(body, offset, 20)?;
        Ok(Self {
            namespace: u32_at(bytes, 0),
            name: u32_at(bytes, 4),
            raw: u32_at(bytes, 8),
            value_size: u16_at(bytes, 12),
            res0: bytes[14],
            value_type: bytes[15],
            data: u32_at(bytes, 16),
        })
    }

    fn bytes(&self) -> [u8; 20] {
        let mut out = [0u8; 20];
        out[0..4].copy_from_slice(&self.namespace.to_le_bytes());
        out[4..8].copy_from_slice(&self.name.to_le_bytes());
        out[8..12].copy_from_slice(&self.raw.to_le_bytes());
        out[12..14].copy_from_slice(&self.value_size.to_le_bytes());
        out[14] = self.res0;
        out[15] = self.value_type;
        out[16..20].copy_from_slice(&self.data.to_le_bytes());
        out
    }
}

/// The element header at <ext>: (namespace, name, attribute start, size, count), `<IIHHH>`.
fn element(body: &[u8], ext: usize) -> Result<(u32, u32, usize, usize, usize)> {
    let bytes = need(body, ext, 14)?;
    Ok((
        u32_at(bytes, 0),
        u32_at(bytes, 4),
        usize::from(u16_at(bytes, 8)),
        usize::from(u16_at(bytes, 10)),
        usize::from(u16_at(bytes, 12)),
    ))
}

fn header_size(body: &[u8]) -> Result<usize> {
    Ok(usize::from(u16_at(need(body, 2, 2)?, 0)))
}

fn shift_word(body: &mut [u8], offset: usize, inserted: u32) -> Result<()> {
    let value = read_u32(body, offset)?;
    write_u32(body, offset, shift(value, inserted))
}

/// `axml_set_debuggable.patch`: <manifest> with `android:debuggable` set to <debuggable>.
pub fn patch(manifest: &[u8], debuggable: bool) -> Result<Vec<u8>> {
    let value = if debuggable { 0xFFFF_FFFF } else { 0 };
    let (file_header_size, mut chunks) = chunks(manifest)?;
    let stop = || PyErr::new("StopIteration", "");
    let pool_at = chunks
        .iter()
        .position(|(kind, _)| *kind == RES_STRING_POOL)
        .ok_or_else(stop)?;
    let map_at = chunks
        .iter()
        .position(|(kind, _)| *kind == RES_XML_RESOURCE_MAP)
        .ok_or_else(stop)?;
    let (mut strings, flags) = parse_string_pool(&chunks[pool_at].1)?;
    let mut res_ids = resource_ids(&chunks[map_at].1)?;

    let (name_index, inserted) = match res_ids.iter().position(|id| *id == DEBUGGABLE_RES_ID) {
        Some(index) => (index, None),
        None => {
            let index = res_ids.len();
            // `list.insert` past the end appends.
            strings.insert(index.min(strings.len()), "debuggable".to_owned());
            res_ids.push(DEBUGGABLE_RES_ID);
            (index, Some(index as u32))
        }
    };
    let android_ns = strings
        .iter()
        .position(|text| text == ANDROID_NS)
        .ok_or_else(|| {
            PyErr::value(format!(
                "{} is not in list",
                crate::catalog::py_repr(ANDROID_NS)
            ))
        })? as u32;

    chunks[pool_at].1 = build_string_pool(&strings, flags)?;
    let mut map = Vec::with_capacity(8 + 4 * res_ids.len());
    map.extend_from_slice(&RES_XML_RESOURCE_MAP.to_le_bytes());
    map.extend_from_slice(&8u16.to_le_bytes());
    map.extend_from_slice(&((8 + 4 * res_ids.len()) as u32).to_le_bytes());
    res_ids
        .iter()
        .for_each(|id| map.extend_from_slice(&id.to_le_bytes()));
    chunks[map_at].1 = map;

    let nodes = [
        RES_XML_START_NAMESPACE,
        RES_XML_END_NAMESPACE,
        RES_XML_START_ELEMENT,
        RES_XML_END_ELEMENT,
        RES_XML_CDATA,
    ];
    let mut patched_application = false;
    for (kind, body) in &mut chunks {
        let kind = *kind;
        if !nodes.contains(&kind) {
            continue;
        }
        let header = header_size(body)?;
        if let Some(inserted) = inserted {
            shift_word(body, 12, inserted)?;
            if matches!(
                kind,
                RES_XML_START_NAMESPACE | RES_XML_END_NAMESPACE | RES_XML_END_ELEMENT
            ) {
                for offset in [header, header + 4] {
                    shift_word(body, offset, inserted)?;
                }
            } else if kind == RES_XML_CDATA {
                shift_word(body, header, inserted)?;
                // The chunk body is a `bytearray` here, which words its IndexError so.
                let value_type = body
                    .get(header + 7)
                    .copied()
                    .ok_or_else(|| PyErr::new("IndexError", "bytearray index out of range"))?;
                if value_type == TYPE_STRING {
                    shift_word(body, header + 8, inserted)?;
                }
            }
        }
        if kind != RES_XML_START_ELEMENT {
            continue;
        }
        let ext = header;
        let (ns, name, attr_start, attr_size, attr_count) = element(body, ext)?;
        if let Some(inserted) = inserted {
            room(body, ext, 8)?;
            write_u32(body, ext, shift(ns, inserted))?;
            write_u32(body, ext + 4, shift(name, inserted))?;
        }
        let mut attrs = Vec::with_capacity(attr_count + 1);
        for i in 0..attr_count {
            let mut attribute = Attribute::read(body, ext + attr_start + i * attr_size)?;
            if let Some(inserted) = inserted {
                attribute.namespace = shift(attribute.namespace, inserted);
                attribute.name = shift(attribute.name, inserted);
                attribute.raw = shift(attribute.raw, inserted);
                if attribute.value_type == TYPE_STRING {
                    attribute.data = shift(attribute.data, inserted);
                }
            }
            attrs.push(attribute);
        }
        let element_name = string(
            &strings,
            u64::from(inserted.map_or(name, |inserted| shift(name, inserted))),
        )?;
        if element_name == "application" {
            let sort_key =
                |a: &Attribute| res_ids.get(a.name as usize).copied().unwrap_or(0xFFFF_FFFF);
            let mut existing = false;
            for attribute in attrs
                .iter_mut()
                .filter(|a| sort_key(a) == DEBUGGABLE_RES_ID)
            {
                (attribute.raw, attribute.value_type, attribute.data) =
                    (NO_INDEX, TYPE_INT_BOOLEAN, value);
                existing = true;
            }
            if !existing {
                attrs.push(Attribute {
                    namespace: android_ns,
                    name: name_index as u32,
                    raw: NO_INDEX,
                    value_size: 8,
                    res0: 0,
                    value_type: TYPE_INT_BOOLEAN,
                    data: value,
                });
            }
            attrs.sort_by_key(sort_key);
            patched_application = true;
            let (mut id_index, mut class_index, mut style_index) = (0usize, 0usize, 0usize);
            for (i, attribute) in attrs.iter().enumerate() {
                let attr_name = string(&strings, u64::from(attribute.name))?;
                if attribute.namespace == NO_INDEX {
                    match attr_name {
                        "id" => id_index = i + 1,
                        "class" => class_index = i + 1,
                        "style" => style_index = i + 1,
                        _ => {}
                    }
                }
            }
            let mut fixed = slice(body, 0, ext + 12).to_vec();
            for value in [attrs.len(), id_index, class_index, style_index] {
                let value = u16::try_from(value)
                    .map_err(|_| PyErr::new("error", "'H' format requires 0 <= number <= 65535"))?;
                fixed.extend_from_slice(&value.to_le_bytes());
            }
            fixed.extend_from_slice(slice(body, ext + 20, ext + attr_start));
            for attribute in &attrs {
                let mut record = attribute.bytes().to_vec();
                if record.len() < attr_size {
                    record.resize(attr_size, 0);
                }
                fixed.extend_from_slice(&record);
            }
            let length = fixed.len() as u32;
            write_u32(&mut fixed, 4, length)?;
            *body = fixed;
        } else {
            for (i, attribute) in attrs.iter().enumerate() {
                room(body, ext + attr_start + i * attr_size, 20)?
                    .copy_from_slice(&attribute.bytes());
            }
        }
    }
    if !patched_application {
        return Err(PyErr::value("<application> element not found"));
    }
    Ok(join(file_header_size, &chunks))
}

/// `is_debuggable`: `patch` leaves a manifest byte-identical only when the flag is already on.
pub fn is_debuggable(manifest: &[u8]) -> Result<bool> {
    Ok(patch(manifest, true)? == manifest)
}

/// `axml_label.set_label`: <manifest> with the app's name replaced by <label>, byte-identical when
/// it already reads so.
pub fn set_label(manifest: &[u8], label: &str) -> Result<Vec<u8>> {
    let (file_header_size, mut chunks) = chunks(manifest)?;
    let pool_at = chunks.iter().position(|(kind, _)| *kind == RES_STRING_POOL);
    let map_at = chunks
        .iter()
        .position(|(kind, _)| *kind == RES_XML_RESOURCE_MAP);
    let (Some(pool_at), Some(map_at)) = (pool_at, map_at) else {
        return Err(PyErr::value(
            "the manifest has no string pool or resource map",
        ));
    };
    let (strings, flags) = parse_string_pool(&chunks[pool_at].1)?;
    let res_ids = resource_ids(&chunks[map_at].1)?;
    let name_index = res_ids
        .iter()
        .position(|id| *id == LABEL_RES_ID)
        .ok_or_else(|| PyErr::value("the manifest has no android:label attribute"))?
        as u32;

    let mut targets: Vec<(usize, usize)> = Vec::new();
    let mut shared: Option<u32> = None;
    let mut seen_application = false;
    for (at, (kind, body)) in chunks.iter().enumerate() {
        if *kind != RES_XML_START_ELEMENT {
            continue;
        }
        let ext = usize::from(u16_at(need(body, 2, 2)?, 0));
        let bytes = need(body, ext, 14)?;
        let (name, attr_start, attr_size, attr_count) = (
            u32_at(bytes, 4),
            usize::from(u16_at(bytes, 8)),
            usize::from(u16_at(bytes, 10)),
            usize::from(u16_at(bytes, 12)),
        );
        let mut found = None;
        for i in 0..attr_count {
            let offset = ext + attr_start + i * attr_size;
            let attribute = Attribute::read(body, offset)?;
            if attribute.name == name_index {
                found = Some((offset, attribute.value_type, attribute.data));
                break;
            }
        }
        let element = string(&strings, u64::from(name))?;
        if element == "application" {
            seen_application = true;
            let Some((offset, value_type, data)) = found else {
                return Err(PyErr::value("<application> has no android:label"));
            };
            if value_type == TYPE_REFERENCE {
                shared = Some(data);
                targets.push((at, offset));
            } else if !(value_type == TYPE_STRING
                && (data as usize) < strings.len()
                && strings[data as usize] == label)
            {
                targets.push((at, offset));
            }
        } else if let (Some(shared), true, Some((offset, value_type, data))) =
            (shared, COMPONENTS.contains(&element), found)
            && value_type == TYPE_REFERENCE
            && data == shared
        {
            targets.push((at, offset));
        }
    }
    if !seen_application {
        return Err(PyErr::value("<application> element not found"));
    }
    if targets.is_empty() {
        return Ok(manifest.to_vec());
    }
    let index = match strings.iter().position(|text| text == label) {
        Some(index) => index as u32,
        None => {
            let index = strings.len() as u32;
            let mut grown = strings.clone();
            grown.push(label.to_owned());
            chunks[pool_at].1 = build_string_pool(&grown, flags)?;
            index
        }
    };
    for (at, offset) in targets {
        let body = &mut chunks[at].1;
        let mut attribute = Attribute::read(body, offset)?;
        (attribute.raw, attribute.value_type, attribute.data) = (index, TYPE_STRING, index);
        room(body, offset, 20)?.copy_from_slice(&attribute.bytes());
    }
    Ok(join(file_header_size, &chunks))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn decode_errors_read_as_cpython() {
        let text = |data: &[u8]| decode_utf8(data).unwrap_err().message;
        assert_eq!(
            text(b"\xff"),
            "'utf-8' codec can't decode byte 0xff in position 0: invalid start byte"
        );
        assert_eq!(
            text(b"a\xc3"),
            "'utf-8' codec can't decode byte 0xc3 in position 1: unexpected end of data"
        );
        assert_eq!(
            text(b"\xe2\x28\xa1"),
            "'utf-8' codec can't decode byte 0xe2 in position 0: invalid continuation byte"
        );
        let wide = |data: &[u8]| decode_utf16le(data).unwrap_err().message;
        assert_eq!(
            wide(b"\x00\xd8"),
            "'utf-16-le' codec can't decode bytes in position 0-1: unexpected end of data"
        );
        assert_eq!(
            wide(b"a"),
            "'utf-16-le' codec can't decode byte 0x61 in position 0: truncated data"
        );
        assert_eq!(
            wide(b"\x00\xdc\x00\x00"),
            "'utf-16-le' codec can't decode bytes in position 0-1: illegal encoding"
        );
        assert_eq!(
            wide(b"\x00\xd8a\x00"),
            "'utf-16-le' codec can't decode bytes in position 0-1: illegal UTF-16 surrogate"
        );
    }

    #[test]
    fn pool_round_trips() {
        let strings: Vec<String> = ["a", "王者", ""].map(String::from).to_vec();
        for flags in [0, UTF8_FLAG] {
            let pool = build_string_pool(&strings, flags).unwrap();
            assert_eq!(parse_string_pool(&pool).unwrap(), (strings.clone(), flags));
        }
    }
}
