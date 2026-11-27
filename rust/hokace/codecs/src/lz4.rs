//! LZ4 raw blocks, as python-lz4's `lz4.block` handles them in the pipeline
//! (`rust/research/compression-codecs.md` 1.1, T2 and T5).
//!
//! Decoding is `lz4_flex`'s checked block decoder. Encoding is liblz4 1.9.4's high-compression level 12
//! through `lz4-pure-rs`, held to python-lz4's bytes on the dump's whole LZ4 corpus (ADR-022), because
//! the compressed length decides whether the runtime stages a table in place.

use std::fmt;

/// The high-compression level every pipeline LZ4 write uses.
pub const HC_LEVEL: i32 = 12;

/// Why a block did not decode or encode; python-lz4 raises `LZ4BlockError` for the same cases.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Lz4Error(pub String);

impl fmt::Display for Lz4Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for Lz4Error {}

/// `lz4.block.decompress(block, uncompressed_size=size)`: a block that decodes to fewer bytes than
/// `size` comes back shorter, one that needs more is an error.
pub fn decompress(block: &[u8], size: usize) -> Result<Vec<u8>, Lz4Error> {
    let mut out = vec![0u8; size];
    let written =
        lz4_flex::block::decompress_into(block, &mut out).map_err(|e| Lz4Error(e.to_string()))?;
    out.truncate(written);
    Ok(out)
}

/// `lz4.block.compress(data, mode="high_compression", compression=12, store_size=False)`.
pub fn compress_hc12(data: &[u8]) -> Result<Vec<u8>, Lz4Error> {
    lz4::block::compress(
        data,
        Some(lz4::block::CompressionMode::HIGHCOMPRESSION(HC_LEVEL)),
        false,
    )
    .map_err(|e| Lz4Error(e.to_string()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn round_trip() {
        let data: Vec<u8> = (0..20_000u32)
            .map(|i| (i % 251) as u8 ^ (i / 97) as u8)
            .collect();
        let packed = compress_hc12(&data).unwrap();
        assert!(packed.len() < data.len());
        assert_eq!(decompress(&packed, data.len()).unwrap(), data);
    }

    #[test]
    fn larger_size_returns_shorter_smaller_size_fails() {
        let data = b"hello hello hello hello hello hello".repeat(10);
        let packed = compress_hc12(&data).unwrap();
        assert_eq!(decompress(&packed, data.len() + 100).unwrap(), data);
        assert!(decompress(&packed, data.len() - 1).is_err());
    }

    #[test]
    fn empty_input() {
        let packed = compress_hc12(b"").unwrap();
        assert_eq!(decompress(&packed, 0).unwrap(), b"");
    }
}
