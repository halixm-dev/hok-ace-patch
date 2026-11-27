//! Solid LDR RGBA8 blocks, the early-return path in the Arm ASTC encoder.
//!
//! The reference is `compress_block` and `symbolic_to_physical` in astcenc
//! commit `631fb04e1c4b`, used by the patcher's Python encoder.

/// Encode a solid 2D block as LDR UNORM16, for any ASTC block footprint.
///
/// Use this when every texel has the same RGBA8 value. The header selects
/// a 2D void-extent block with no explicit extent. Arm's `astcenc` reference
/// encodes each normalized 8-bit channel as an exact 16-bit value.
pub fn encode_solid_block(rgba: [u8; 4]) -> [u8; 16] {
    let mut block = [0xff; 16];
    block[..2].copy_from_slice(&[0xfc, 0xfd]);
    for (bytes, channel) in block[8..].as_chunks_mut::<2>().0.iter_mut().zip(rgba) {
        *bytes = (u16::from(channel) * 257).to_le_bytes();
    }
    block
}

#[cfg(test)]
mod tests {
    use super::encode_solid_block;
    use crate::texture::decode_astc;

    #[test]
    fn solid_block_round_trips_all_u8_values_at_partial_edges() {
        for value in 0..=u8::MAX {
            let rgba = [value, u8::MAX - value, 0, value];
            let encoded = encode_solid_block(rgba);
            assert_eq!(decode_astc(&encoded, 3, 2, 4, 4).unwrap(), rgba.repeat(6));
        }
    }
}
