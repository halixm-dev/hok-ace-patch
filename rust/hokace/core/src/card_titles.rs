//! `tools/card_titles.py`: re-lay the Secret Technique card titles in LordSkillCardAtlas, so each English
//! title gets its own box. A move rewrites floats in place in three kinds of package-19 asset: the Sprite
//! table, the TimiAtlas and each card prefab's `Title` RectTransform (ADR 0009).
//!
//! Offsets are Python ints: a corrupt length can move a read backwards or below zero, and `struct` then
//! indexes from the end. `relayout` turns `UnsupportedFile`, `ValueError` and `struct.error` from a move
//! into a refusal (`None`), as `_guarded` does; any other error (a `KeyError` from the layout, an
//! `IndexError` from the SerializedFile header) is returned. The layout is the JSON `load_layout` reads;
//! its dicts, lists and numbers are taken at their shipped types.

use std::path::Path;

use serde_json::{Map, Value};

use crate::axml::PyErr;
use crate::catalog::py_repr;
use crate::unity_text::{SerializedFile, UNSUPPORTED_FILE, pack, unpack};

pub const TITLE_ATLAS: u64 = 0x0B4D_A7A8_5D27_E87A;
pub const LAYOUT_FILE: &str = "layout.json";
pub const SPRITE_ART: &str = "sprites";
pub const SPRITE_CLASS: i32 = 213;
pub const RECT_TRANSFORM_CLASS: i32 = 224;
pub const PIXELS_PER_UNIT: f64 = 100.0;

/// `load_layout`: the shipped title layout beside the catalogs, or None.
pub fn load_layout(catalog_dir: &Path) -> Result<Option<Value>, PyErr> {
    let parent = catalog_dir.parent().unwrap_or(catalog_dir);
    let path = parent
        .join(SPRITE_ART)
        .join(format!("{TITLE_ATLAS:016X}"))
        .join(LAYOUT_FILE);
    if !path.is_file() {
        return Ok(None);
    }
    let text = std::fs::read_to_string(&path).map_err(|e| PyErr::new("OSError", e.to_string()))?;
    serde_json::from_str(&text)
        .map(Some)
        .map_err(|e| PyErr::new("JSONDecodeError", e.to_string()))
}

/// Python's `data[start:end]`.
pub(crate) fn py_slice(data: &[u8], start: i64, end: i64) -> &[u8] {
    let len = data.len() as i64;
    let clamp = |at: i64| {
        if at < 0 {
            (at + len).max(0)
        } else {
            at.min(len)
        }
    };
    let (start, end) = (clamp(start), clamp(end));
    if end <= start {
        &[]
    } else {
        &data[start as usize..end as usize]
    }
}

/// `_Reader`: little-endian reads over one serialized Unity object.
struct Reader<'a> {
    data: &'a [u8],
    at: i64,
}

impl<'a> Reader<'a> {
    fn take(&mut self, size: usize) -> Result<&'a [u8], PyErr> {
        let values = unpack(self.data, size, self.at)?;
        self.at += size as i64;
        Ok(values)
    }

    fn i32(&mut self) -> Result<i64, PyErr> {
        Ok(i64::from(i32::from_le_bytes(
            self.take(4)?.try_into().expect("4 bytes"),
        )))
    }

    fn u32(&mut self) -> Result<i64, PyErr> {
        Ok(i64::from(u32::from_le_bytes(
            self.take(4)?.try_into().expect("4 bytes"),
        )))
    }

    fn align(&mut self) {
        self.at = (self.at + 3) & !3;
    }

    fn string(&mut self) -> Result<String, PyErr> {
        let length = self.i32()?;
        let text =
            String::from_utf8_lossy(py_slice(self.data, self.at, self.at + length)).into_owned();
        self.at += length;
        self.align();
        Ok(text)
    }

    fn skip_bytes(&mut self) -> Result<i64, PyErr> {
        let length = self.i32()?;
        let start = self.at;
        self.at += length;
        self.align();
        Ok(start)
    }
}

fn floats(raw: &[u8]) -> Vec<f64> {
    raw.as_chunks::<4>()
        .0
        .iter()
        .map(|b| f64::from(f32::from_le_bytes(*b)))
        .collect()
}

/// Offsets within a Sprite object of the fields a move rewrites.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct SpriteOffsets {
    pub rect: i64,
    pub vertices: i64,
    pub texture_rect: i64,
    pub uv_transform: i64,
}

/// `sprite_fields`: a Unity 2022 Sprite's name, the offsets a move rewrites, and its `m_Rect`.
pub fn sprite_fields(obj: &[u8]) -> Result<(String, SpriteOffsets, [f64; 4]), PyErr> {
    let mut r = Reader { data: obj, at: 0 };
    let name = r.string()?;
    let rect_at = r.at;
    let rect: [f64; 4] = floats(r.take(16)?).try_into().expect("4 floats");
    r.take(40)?; // offset, border, pixelsToUnits, pivot, extrude
    r.at += 1; // isPolygon
    r.align();
    r.at += 24; // render data key
    for _ in 0..r.i32()? {
        r.string()?; // atlas tags
    }
    r.take(12)?; // sprite atlas
    r.take(24)?; // texture, alpha texture
    for _ in 0..r.i32()? {
        r.take(12)?;
        r.string()?; // secondary textures
    }
    let submeshes = r.i32()?;
    r.at += submeshes * 48;
    r.skip_bytes()?; // index buffer
    let vertices = r.u32()?;
    let channels = r.i32()?;
    r.at += channels * 4;
    let data_at = r.skip_bytes()?;
    if vertices != 4 || r.at - data_at < 4 * 12 {
        return Err(PyErr::new(
            "ValueError",
            format!("{name}: {vertices} vertices, not the quad a move rewrites"),
        ));
    }
    let bind_poses = r.i32()?;
    r.at += 64 * bind_poses;
    let offsets = SpriteOffsets {
        rect: rect_at,
        vertices: data_at,
        texture_rect: r.at,
        uv_transform: r.at + 36,
    };
    Ok((name, offsets, rect))
}

// --- the layout's Python values ---------------------------------------------------------------------

fn key_error(key: &str) -> PyErr {
    PyErr::new("KeyError", py_repr(key))
}

fn dict(value: &Value) -> Result<&Map<String, Value>, PyErr> {
    value
        .as_object()
        .ok_or_else(|| PyErr::new("TypeError", "the layout is not shaped as shipped"))
}

fn get<'v>(value: &'v Value, key: &str) -> Result<&'v Value, PyErr> {
    dict(value)?.get(key).ok_or_else(|| key_error(key))
}

fn number(value: &Value) -> Result<f64, PyErr> {
    value
        .as_f64()
        .ok_or_else(|| PyErr::new("TypeError", "the layout is not shaped as shipped"))
}

/// Python's `float == <json number>`, exact for ints past 2**53.
fn num_eq(float: f64, value: &Value) -> bool {
    if let Some(int) = value.as_i64() {
        float == int as f64 && float.fract() == 0.0 && float as i128 == i128::from(int)
    } else if let Some(int) = value.as_u64() {
        float == int as f64 && float.fract() == 0.0 && float as i128 == i128::from(int)
    } else {
        value.as_f64() == Some(float)
    }
}

/// Python's `[floats] == <json value>`.
fn list_eq(floats: &[f64], value: &Value) -> bool {
    value.as_array().is_some_and(|items| {
        items.len() == floats.len() && floats.iter().zip(items).all(|(f, v)| num_eq(*f, v))
    })
}

/// `x, y, w, h = <json list>`.
fn four(value: &Value) -> Result<[f64; 4], PyErr> {
    let items = value
        .as_array()
        .ok_or_else(|| PyErr::new("TypeError", "the layout is not shaped as shipped"))?;
    if items.len() < 4 {
        return Err(PyErr::new(
            "ValueError",
            format!(
                "not enough values to unpack (expected 4, got {})",
                items.len()
            ),
        ));
    }
    if items.len() > 4 {
        return Err(PyErr::new(
            "ValueError",
            "too many values to unpack (expected 4)",
        ));
    }
    Ok([
        number(&items[0])?,
        number(&items[1])?,
        number(&items[2])?,
        number(&items[3])?,
    ])
}

/// `int(<text>, 16)` for the hex hashes the layout names.
fn hex_hash(value: &Value) -> Result<u64, PyErr> {
    let text = value.as_str().ok_or_else(|| {
        PyErr::new(
            "TypeError",
            "int() can't convert non-string with explicit base",
        )
    })?;
    let trimmed = crate::pystr::strip(text);
    let digits = trimmed
        .strip_prefix("0x")
        .or_else(|| trimmed.strip_prefix("0X"))
        .unwrap_or(trimmed);
    if !digits.is_empty()
        && digits.bytes().all(|b| b.is_ascii_hexdigit())
        && let Ok(hash) = u64::from_str_radix(digits, 16)
    {
        return Ok(hash);
    }
    Err(PyErr::new(
        "ValueError",
        format!("invalid literal for int() with base 16: {}", py_repr(text)),
    ))
}

/// `struct.pack_into("<Nf", out, at, *values)`: the bounds first, then each float's range.
fn pack_floats(out: &mut [u8], at: i64, values: &[f64]) -> Result<(), PyErr> {
    pack(out, at, &vec![0; values.len() * 4])?;
    let mut bytes = Vec::with_capacity(values.len() * 4);
    for &value in values {
        let single = value as f32;
        if single.is_infinite() && value.is_finite() {
            return Err(PyErr::new(
                "OverflowError",
                "float too large to pack with f format",
            ));
        }
        bytes.extend_from_slice(&single.to_le_bytes());
    }
    pack(out, at, &bytes)
}

/// `(path_id, start, size)` of every object of <class_id>.
fn objects(raw: &[u8], class_id: i32) -> Result<Vec<(i64, usize, usize)>, PyErr> {
    let parsed = SerializedFile::parse(raw)?;
    Ok(parsed
        .objects
        .iter()
        .filter(|o| parsed.class_ids[o.type_index as usize] == class_id)
        .map(|o| {
            (
                o.path_id,
                (parsed.data_offset + o.start) as usize,
                o.size as usize,
            )
        })
        .collect())
}

/// `_rect_size_at`: offset of a RectTransform's `sizeDelta` within the object.
fn rect_size_at(obj: &[u8]) -> Result<i64, PyErr> {
    let at = 12 + 16 + 12 + 12;
    let children = i64::from(i32::from_le_bytes(
        unpack(obj, 4, at)?.try_into().expect("4 bytes"),
    ));
    Ok(at + 4 + 12 * children + 12 + 24)
}

fn move_sprites(table: &[u8], layout: &Value) -> Result<Option<Vec<u8>>, PyErr> {
    let (titles, art) = (dict(get(layout, "titles")?)?, dict(get(layout, "art")?)?);
    let mut out = table.to_vec();
    let mut seen: Vec<String> = Vec::new();
    for (_path_id, start, size) in objects(table, SPRITE_CLASS)? {
        let (name, at, rect) = sprite_fields(&table[start..start + size])?;
        if let Some(recorded) = art.get(&name) {
            if !list_eq(&rect, recorded) {
                return Ok(None);
            }
            if !seen.contains(&name) {
                seen.push(name);
            }
            continue;
        }
        let Some(title) = titles.get(&name) else {
            return Ok(None);
        };
        let (was, now) = (get(title, "was")?, get(title, "now")?);
        if !list_eq(&rect, was) && !list_eq(&rect, now) {
            return Ok(None);
        }
        let [x, y, w, h] = four(now)?;
        let (half_w, half_h) = (w / 2.0 / PIXELS_PER_UNIT, h / 2.0 / PIXELS_PER_UNIT);
        let start = start as i64;
        pack_floats(&mut out, start + at.rect, &[x, y, w, h])?;
        pack_floats(
            &mut out,
            start + at.vertices,
            &[
                -half_w, half_h, 0.0, half_w, half_h, 0.0, -half_w, -half_h, 0.0, half_w, -half_h,
                0.0,
            ],
        )?;
        pack_floats(&mut out, start + at.texture_rect, &[x, y, w, h])?;
        pack_floats(
            &mut out,
            start + at.uv_transform,
            &[PIXELS_PER_UNIT, x + w / 2.0, PIXELS_PER_UNIT, y + h / 2.0],
        )?;
        if !seen.contains(&name) {
            seen.push(name);
        }
    }
    let expected: Vec<&String> = titles.keys().chain(art.keys()).collect();
    let same = seen.iter().all(|name| expected.contains(&name))
        && expected.iter().all(|name| seen.contains(name));
    Ok(same.then_some(out))
}

fn count(haystack: &[u8], needle: &[u8]) -> usize {
    let (mut found, mut at) = (0, 0);
    while at + needle.len() <= haystack.len() {
        if &haystack[at..at + needle.len()] == needle {
            found += 1;
            at += needle.len();
        } else {
            at += 1;
        }
    }
    found
}

fn move_index(index: &[u8], layout: &Value) -> Result<Option<Vec<u8>>, PyErr> {
    let mut out = index.to_vec();
    for (name, title) in dict(get(layout, "titles")?)? {
        let mut key = (name.chars().count() as i32).to_le_bytes().to_vec();
        key.extend_from_slice(name.as_bytes());
        if count(index, &key) != 1 {
            return Ok(None);
        }
        let first = index
            .windows(key.len())
            .position(|w| w == key.as_slice())
            .expect("counted once") as i64;
        let at = (first + key.len() as i64 + 3) & !3;
        let rect = floats(unpack(index, 16, at)?);
        let pivot = floats(unpack(index, 8, at + 32)?);
        let (was, now) = (get(title, "was")?, get(title, "now")?);
        if (!list_eq(&rect, was) && !list_eq(&rect, now))
            || pivot[0] != rect[2] / 2.0
            || pivot[1] != rect[3] / 2.0
        {
            return Ok(None);
        }
        let [x, y, w, h] = four(now)?;
        pack_floats(&mut out, at, &[x, y, w, h])?;
        pack_floats(&mut out, at + 32, &[w / 2.0, h / 2.0])?;
    }
    Ok(Some(out))
}

fn move_box(prefab: &[u8], cell: &Value, size: [f64; 2]) -> Result<Option<Vec<u8>>, PyErr> {
    for (path_id, start, length) in objects(prefab, RECT_TRANSFORM_CLASS)? {
        if !path_eq(path_id, get(cell, "path_id")?) {
            continue;
        }
        let at = start as i64 + rect_size_at(&prefab[start..start + length])?;
        let current = floats(unpack(prefab, 8, at)?);
        if !list_eq(&current, get(cell, "was")?) && current != size {
            return Ok(None);
        }
        let mut out = prefab.to_vec();
        pack_floats(&mut out, at, &size)?;
        return Ok(Some(out));
    }
    Ok(None)
}

/// Python's `int != <json number>` as equality, exact for every i64.
fn path_eq(path_id: i64, value: &Value) -> bool {
    match (value.as_i64(), value.as_u64()) {
        (Some(int), _) => int == path_id,
        (None, Some(_)) => false,
        _ => value.as_f64().is_some_and(|f| {
            f.fract() == 0.0 && f == path_id as f64 && f as i128 == i128::from(path_id)
        }),
    }
}

/// `_guarded`: a move's refusal for the errors that mean the asset is not as the layout expects.
fn guarded(result: Result<Option<Vec<u8>>, PyErr>) -> Result<Option<Vec<u8>>, PyErr> {
    match result {
        Err(error) if matches!(error.class, UNSUPPORTED_FILE | "ValueError" | "error") => Ok(None),
        other => other,
    }
}

fn put(jobs: &mut Vec<(u64, Vec<u8>)>, asset: u64, raw: Vec<u8>) {
    match jobs.iter_mut().find(|(hash, _)| *hash == asset) {
        Some(job) => job.1 = raw,
        None => jobs.push((asset, raw)),
    }
}

/// New raw bytes by asset hash, in Python's dict order.
pub type Jobs = Vec<(u64, Vec<u8>)>;

type Move = fn(&[u8], &Value) -> Result<Option<Vec<u8>>, PyErr>;

/// `relayout`: new raw bytes for every asset the layout changes, by hash in Python's dict order (empty
/// when all already match), or None. <read> returns an asset's raw bytes, or None if the package lacks it.
pub fn relayout(
    read: &mut dyn FnMut(u64) -> Option<Vec<u8>>,
    layout: &Value,
) -> Result<Option<Jobs>, PyErr> {
    let mut jobs = Vec::new();
    let table = hex_hash(get(layout, "sprite_table")?)?;
    let atlas = hex_hash(get(layout, "timi_atlas")?)?;
    let sources: Vec<(u64, Move)> = if table == atlas {
        vec![(table, move_index)]
    } else {
        vec![(table, move_sprites), (atlas, move_index)]
    };
    for (asset, step) in sources {
        let raw = read(asset);
        let new = match &raw {
            Some(raw) if !raw.is_empty() => guarded(step(raw, layout))?,
            _ => None,
        };
        let Some(new) = new else { return Ok(None) };
        if Some(&new) != raw.as_ref() {
            put(&mut jobs, asset, new);
        }
    }
    for (asset, cell) in dict(get(layout, "boxes")?)? {
        let hash = hex_hash(&Value::String(asset.clone()))?;
        let raw = read(hash);
        let sprite = get(cell, "sprite")?;
        let sprite = sprite
            .as_str()
            .ok_or_else(|| PyErr::new("TypeError", "the layout is not shaped as shipped"))?;
        let title = dict(get(layout, "titles")?)?
            .get(sprite)
            .ok_or_else(|| key_error(sprite))?;
        let [_x, _y, w, h] = four(get(title, "now")?)?;
        let new = match &raw {
            Some(raw) if !raw.is_empty() => guarded(move_box(raw, cell, [w, h]))?,
            _ => None,
        };
        let Some(new) = new else { return Ok(None) };
        if Some(&new) != raw.as_ref() {
            put(&mut jobs, hash, new);
        }
    }
    Ok(Some(jobs))
}
