//! ASTC encoding as `tools/mobile_graphics._encode_astc` runs it: Arm astcenc `631fb04e1c4b`
//! (`hokace-astcenc`, ADR-026), LDR, quality 85, no flags, identity swizzle, RGBA8 input, and one
//! context per footprint kept for the encoder's lifetime, as the Python module keeps `_contexts`.
//!
//! The bytes are the Windows wheel's on every platform. Upstream's `compress_block` keeps its
//! MSE overshoot in a function `static` that the first block of the process sets; the port keeps
//! that quirk process-wide, so the encoder gives the app's bytes when its calls run in the app's
//! order.

use std::collections::HashMap;

use hokace_astcenc::image::Image;
use hokace_astcenc::{Context, PRF_LDR, config_init};

/// `ASTCConfig(ASTCProfile.LDR, bx, by, 1, 85)`.
pub const QUALITY: f32 = 85.0;

/// The pipeline's ASTC encoder, with its contexts cached by footprint.
pub struct AstcEncoder {
    threads: usize,
    contexts: HashMap<(u32, u32), Context>,
}

impl AstcEncoder {
    /// An encoder whose contexts each run `threads` workers (at least one). The app passes
    /// `os.cpu_count()`; the bytes do not depend on it.
    pub fn new(threads: usize) -> Self {
        Self {
            threads: threads.max(1),
            contexts: HashMap::new(),
        }
    }

    /// The blocks of a `width` by `height` RGBA8 image in row order, 16 bytes each, with no file
    /// header. `rgba` must hold exactly `width * height * 4` bytes.
    pub fn encode(
        &mut self,
        rgba: &[u8],
        width: u32,
        height: u32,
        bx: u32,
        by: u32,
    ) -> Result<Vec<u8>, String> {
        let expected = width as usize * height as usize * 4;
        if width == 0 || height == 0 || rgba.len() != expected {
            return Err(format!(
                "ASTC input: {} bytes for {width}x{height}, expected {expected}",
                rgba.len()
            ));
        }
        let threads = self.threads;
        let context = match self.contexts.entry((bx, by)) {
            std::collections::hash_map::Entry::Occupied(entry) => entry.into_mut(),
            std::collections::hash_map::Entry::Vacant(entry) => {
                let config = config_init(PRF_LDR, bx, by, QUALITY, 0)
                    .map_err(|error| format!("ASTC config {bx}x{by}: {error:?}"))?;
                entry.insert(
                    Context::with_threads(&config, threads)
                        .map_err(|error| format!("ASTC context {bx}x{by}: {error:?}"))?,
                )
            }
        };
        context
            .compress_image(&Image {
                dim_x: width,
                dim_y: height,
                data: rgba,
            })
            .map_err(|error| format!("ASTC compress {width}x{height} {bx}x{by}: {error:?}"))
    }
}

/// Encode a solid 2D block as LDR UNORM16, for any ASTC block footprint: the encoder's
/// early-return path (`compress_block`, `symbolic_to_physical`).
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
    use super::{AstcEncoder, encode_solid_block};
    use crate::texture::decode_astc;

    #[test]
    fn solid_block_round_trips_all_u8_values_at_partial_edges() {
        for value in 0..=u8::MAX {
            let rgba = [value, u8::MAX - value, 0, value];
            let encoded = encode_solid_block(rgba);
            assert_eq!(decode_astc(&encoded, 3, 2, 4, 4).unwrap(), rgba.repeat(6));
        }
    }

    #[test]
    fn solid_images_take_the_void_extent_path() {
        let mut encoder = AstcEncoder::new(2);
        for (bx, by) in [(4, 4), (6, 6), (8, 8)] {
            let rgba = [12, 200, 7, 255].repeat(17 * 9);
            let blocks = encoder.encode(&rgba, 17, 9, bx, by).unwrap();
            let count = 17u32.div_ceil(bx) * 9u32.div_ceil(by);
            assert_eq!(
                blocks,
                encode_solid_block([12, 200, 7, 255]).repeat(count as usize)
            );
        }
    }

    #[test]
    fn wrong_input_sizes_are_refused() {
        let mut encoder = AstcEncoder::new(1);
        assert!(encoder.encode(&[0; 15], 2, 2, 4, 4).is_err());
        assert!(encoder.encode(&[0; 17], 2, 2, 4, 4).is_err());
        assert!(encoder.encode(&[], 0, 0, 4, 4).is_err());
        assert!(encoder.encode(&[0; 16], 2, 2, 5, 3).is_err());
    }
}
