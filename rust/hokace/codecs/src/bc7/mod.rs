//! PC atlas BC7 block encoding, including the fallback search in `tools/bc7_mode6.py`.

use std::sync::LazyLock;

mod rustbcx;
mod search;

pub use search::encode_mode;

use rustbcx::{Bc7Enc, CompressBlockParams};

const NATIVE_GOOD_ENOUGH: f64 = 6.0;
static ENCODER: LazyLock<Bc7Enc> = LazyLock::new(Bc7Enc::new);

/// Encode one 4×4 block of row-order RGBA8 pixels.
pub fn encode_block(rgba: &[u8; 64]) -> Result<[u8; 16], String> {
    let pixels = rgba.as_chunks::<4>().0;
    let pixels = std::array::from_fn(|index| pixels[index]);
    let params = CompressBlockParams {
        uber_level: 2,
        ..Default::default()
    };
    let mut block = [0; 16];
    ENCODER
        .compress_block(&mut block, &pixels, &params)
        .map_err(|error| error.to_string())?;

    let mut decoded = [0; 16];
    texture2ddecoder::decode_bc7_block(&block, &mut decoded);
    let decoded = decoded.map(|pixel| {
        let [b, g, r, a] = pixel.to_le_bytes();
        [i32::from(r), i32::from(g), i32::from(b), i32::from(a)]
    });
    let error = f64::from(search::mismatch_total(&search::rgba_pixels(rgba), &decoded)) / 16.0;
    if error > NATIVE_GOOD_ENOUGH
        && let Some(better) = search::search(rgba, error).0
    {
        return Ok(better);
    }
    Ok(block)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn solid_opaque_block_decodes_exactly() {
        let rgba = [255; 64];
        let encoded = encode_block(&rgba).unwrap();
        assert_eq!(crate::texture::decode_bc7(&encoded, 4, 4).unwrap(), rgba);
    }

    #[test]
    fn fallback_search_reaches_mode_7() {
        // The Python patcher's smoketest fixture.
        let rgba = [
            0xc6, 0xe1, 0xb5, 0x37, 0x73, 0x4f, 0xd5, 0xac, 0xb4, 0x47, 0x67, 0x8d, 0x30, 0xf3,
            0x89, 0x41, 0xd3, 0x34, 0x02, 0xd2, 0x3c, 0xfe, 0xcb, 0x4c, 0xd5, 0x8f, 0x38, 0xc2,
            0xe7, 0xea, 0x93, 0xb4, 0x95, 0xb4, 0xc8, 0xc4, 0xa4, 0x03, 0xff, 0xc2, 0xe3, 0x99,
            0x5e, 0x9b, 0x4a, 0xdf, 0xc1, 0x76, 0x2d, 0xa9, 0xa5, 0x7c, 0xa6, 0x68, 0xda, 0x05,
            0x0d, 0x18, 0x83, 0xfe, 0x99, 0x9f, 0xdf, 0xdc,
        ];
        let expected = [
            0x80, 0xa4, 0x27, 0x9c, 0x70, 0x60, 0x7e, 0xad, 0x81, 0x47, 0x9f, 0x8d, 0xf3, 0x1c,
            0x99, 0x7e,
        ];
        assert_eq!(encode_block(&rgba).unwrap(), expected);
    }
}
