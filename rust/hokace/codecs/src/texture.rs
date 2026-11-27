//! RGBA8 texture decoding in the input's row order, as in `tools/mobile_graphics.py`.

use std::panic::catch_unwind;

use crate::astc;

/// Decode an ASTC texture, including partial blocks at the right and bottom edges.
pub fn decode_astc(
    raw: &[u8],
    width: usize,
    height: usize,
    bx: usize,
    by: usize,
) -> Result<Vec<u8>, String> {
    if bx == 0 || by == 0 || bx > 12 || by > 12 {
        return Err("invalid ASTC block dimensions".into());
    }
    decode_blocks(raw, [width, height], [bx, by], |image| {
        astc::decode_astc(raw, width, height, bx, by, image)
    })
}

/// Decode a BC7 texture or copy the available RGBA32 bytes, as `decode_pc` does.
pub fn decode_pc(raw: &[u8], width: usize, height: usize, fmt: &str) -> Result<Vec<u8>, String> {
    match fmt {
        "bc7" => decode_bc7(raw, width, height),
        "rgba32" => Ok(raw[..raw.len().min(rgba_size(width, height)?)].to_vec()),
        _ => Err(format!("unsupported PC format {fmt}")),
    }
}

/// Decode a BC7 texture to RGBA8.
pub fn decode_bc7(raw: &[u8], width: usize, height: usize) -> Result<Vec<u8>, String> {
    decode_blocks(raw, [width, height], [4, 4], |image| {
        texture2ddecoder::decode_bc7(raw, width, height, image)
    })
}

fn rgba_size(width: usize, height: usize) -> Result<usize, String> {
    width
        .checked_mul(height)
        .and_then(|pixels| pixels.checked_mul(4))
        .ok_or_else(|| "texture dimensions overflow".into())
}

fn decode_blocks(
    raw: &[u8],
    [width, height]: [usize; 2],
    [bx, by]: [usize; 2],
    decode: impl FnOnce(&mut [u32]) -> Result<(), &'static str> + std::panic::UnwindSafe,
) -> Result<Vec<u8>, String> {
    let size = rgba_size(width, height)?;
    if size == 0 {
        return Ok(Vec::new());
    }
    let required = width
        .div_ceil(bx)
        .checked_mul(height.div_ceil(by))
        .and_then(|blocks| blocks.checked_mul(16))
        .ok_or("compressed texture size overflows")?;
    if raw.len() < required {
        return Err("not enough data to decode texture".into());
    }

    // Some malformed ASTC blocks cause the decoder to panic instead of returning an error.
    catch_unwind(|| {
        let mut image = vec![0; size / 4];
        decode(&mut image)?;
        Ok(image
            .into_iter()
            .flat_map(|pixel| {
                let [b, g, r, a] = pixel.to_le_bytes();
                [r, g, b, a]
            })
            .collect())
    })
    .map_err(|_| "invalid compressed texture")?
    .map_err(str::to_owned)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn astc_void_extent_crops_edges_and_preserves_rgba_order() {
        let block = [
            0xfc, 0xfd, 255, 255, 255, 255, 255, 255, 0, 18, 0, 52, 0, 86, 0, 120,
        ];
        assert_eq!(
            decode_astc(&block, 3, 2, 4, 4).unwrap(),
            [18, 52, 86, 120].repeat(6)
        );
    }

    #[test]
    fn astc_hdr_void_extent_matches_python_rounding() {
        let block = [
            0xfc, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0x00, 0x38, 0x00, 0x3a, 0x00, 0x3c,
            0x00, 0xb8,
        ];
        assert_eq!(
            decode_astc(&block, 4, 4, 4, 4).unwrap(),
            [128, 191, 255, 0].repeat(16)
        );
    }

    #[test]
    fn astc_hdr_endpoints_keep_negative_deltas() {
        let block = [
            0xce, 0xc9, 0x09, 0x7e, 0x3c, 0x83, 0x2e, 0x9b, 0xee, 0x53, 0x18, 0x64, 0x09, 0x7f,
            0x05, 0x1c,
        ];
        let expected = [
            [56, 0, 32, 17, 80, 0, 37, 23, 101, 0, 42, 26, 118, 0, 46, 29],
            [92, 5, 52, 28, 92, 5, 52, 28, 92, 5, 52, 28, 92, 5, 52, 28],
            [
                108, 12, 48, 29, 108, 12, 48, 29, 108, 12, 48, 29, 108, 12, 48, 29,
            ],
            [
                118, 17, 46, 29, 118, 17, 46, 29, 118, 17, 46, 29, 118, 17, 46, 29,
            ],
        ];
        assert_eq!(decode_astc(&block, 4, 4, 4, 4).unwrap(), expected.concat());
    }

    #[test]
    fn malformed_geometry_and_short_blocks_are_errors() {
        assert!(decode_astc(&[], 1, 1, 0, 4).is_err());
        assert!(decode_astc(&[0; 16], 5, 4, 4, 4).is_err());
        assert!(decode_bc7(&[], usize::MAX, 2).is_err());
    }

    #[test]
    fn rgba32_returns_at_most_the_declared_size() {
        assert_eq!(decode_pc(b"12345", 1, 1, "rgba32").unwrap(), b"1234");
        assert_eq!(decode_pc(b"123", 1, 1, "rgba32").unwrap(), b"123");
    }
}
