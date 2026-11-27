//! `tools/sprite_table.py`: the device's Sprite rectangles for a regioned atlas, read from Tencent's
//! modified Unity assets by their length-prefixed `Image_<id>` names.
//!
//! The scan is the module's `NAME` regex, `([\x0c-\x14])\x00\x00\x00(Image_\d{5,10})`, run as
//! `finditer` does: matches never overlap, and a skipped match still moves the search past it.

/// Regioned catalog atlas -> the package-19 asset holding its Sprite objects.
pub const REGION_SPRITE_ASSETS: [(u64, u64); 4] = [
    (0x13C1_9E4E_4486_B31C, 0x4AA2_B26F_F28C_B65D),
    (0xC9F4_9510_F2F6_7402, 0x22BD_565B_3703_EDA9),
    (0xE86D_F431_67CA_2143, 0x9F24_0FDA_0FA5_8988),
    (0x0B4D_A7A8_5D27_E87A, 0xF86A_7241_DD03_9F73),
];

const PREFIX: &[u8] = b"Image_";

/// The next `NAME` match at or after <from>: (start, end, length byte, name).
fn next_name(raw: &[u8], from: usize) -> Option<(usize, usize, u8, &[u8])> {
    let mut at = from;
    while at + 4 + PREFIX.len() + 5 <= raw.len() {
        let length = raw[at];
        if (0x0c..=0x14).contains(&length)
            && raw[at + 1..at + 4] == [0, 0, 0]
            && &raw[at + 4..at + 4 + PREFIX.len()] == PREFIX
        {
            let digits_at = at + 4 + PREFIX.len();
            let digits = raw[digits_at..]
                .iter()
                .take(10)
                .take_while(|b| b.is_ascii_digit())
                .count();
            if digits >= 5 {
                let end = digits_at + digits;
                return Some((at, end, length, &raw[at + 4..end]));
            }
        }
        at += 1;
    }
    None
}

fn f32_at(raw: &[u8], at: usize) -> f64 {
    f64::from(f32::from_le_bytes(
        raw[at..at + 4].try_into().expect("4 bytes"),
    ))
}

/// Python's `0 <= value < limit` (or `0 < value <= limit`) with an int limit.
fn below(value: f64, limit: i64) -> bool {
    0.0 <= value && value < limit as f64
}

fn within(value: f64, limit: i64) -> bool {
    0.0 < value && value <= limit as f64
}

/// `sprite_rects`: sprite boxes `(x0, y0, x1, y1)` in top-down pixels, in the order found.
pub fn sprite_rects(raw: &[u8], width: i64, height: Option<i64>) -> Vec<(String, [i64; 4])> {
    let height = height.unwrap_or(width);
    let mut rects: Vec<(String, [i64; 4])> = Vec::new();
    let mut from = 0;
    while let Some((_start, end, length, name)) = next_name(raw, from) {
        from = end;
        let name = String::from_utf8(name.to_vec()).expect("ASCII name");
        if usize::from(length) != name.len() || rects.iter().any(|(seen, _)| *seen == name) {
            continue;
        }
        let at = (end + 3) & !3;
        if at + 16 > raw.len() {
            continue;
        }
        let (x, y, w, h) = (
            f32_at(raw, at),
            f32_at(raw, at + 4),
            f32_at(raw, at + 8),
            f32_at(raw, at + 12),
        );
        if !(below(x, width) && below(y, height) && within(w, width) && within(h, height)) {
            continue;
        }
        let height = height as f64;
        rects.push((
            name,
            [
                x as i64,
                (height - y - h) as i64,
                (x + w) as i64,
                (height - y) as i64,
            ],
        ));
    }
    rects
}
