//! zstd frames, as python-zstandard's `ZstdDecompressor().decompress(frame, max_output_size=n)` reads
//! them (`rust/research/compression-codecs.md` 1.2 and T2), on `ruzstd`'s decoder.
//!
//! The pipeline only decodes zstd; the game's frames all carry their content size, which then wins
//! over `max_output_size`. Bytes after the first frame are ignored, as python-zstandard ignores them.

use std::io::Read;

use ruzstd::decoding::StreamingDecoder;

/// The four bytes every zstd frame opens with (`qts_relocate.ZSTD_MAGIC`).
pub const MAGIC: [u8; 4] = [0x28, 0xB5, 0x2F, 0xFD];

const INCOMPLETE: &str = "decompression error: did not decompress full frame";

/// The frame header's content size, when it carries one.
fn content_size(frame: &[u8]) -> Option<u64> {
    let descriptor = *frame.get(4)?;
    let (flag, single) = (descriptor >> 6, descriptor & 0x20 != 0);
    let field = match flag {
        0 if single => 1,
        0 => return None,
        1 => 2,
        2 => 4,
        _ => 8,
    };
    let start = 5 + usize::from(!single) + [0, 1, 2, 4][usize::from(descriptor & 3)];
    let bytes = frame.get(start..start + field)?;
    let value = bytes
        .iter()
        .rev()
        .fold(0u64, |acc, b| acc << 8 | u64::from(*b));
    Some(if field == 2 { value + 256 } else { value })
}

/// Decode the first frame of `frame`; `max_output_size` bounds it only when the header has no size.
pub fn decompress(frame: &[u8], max_output_size: usize) -> Result<Vec<u8>, String> {
    let size = content_size(frame);
    let limit = match size {
        Some(size) => usize::try_from(size).map_err(|_| "content size too large".to_owned())?,
        None if max_output_size == 0 => {
            return Err("could not determine content size in frame header".into());
        }
        None => max_output_size,
    };
    let mut decoder =
        StreamingDecoder::new(frame).map_err(|e| format!("decompression error: {e}"))?;
    let mut out = Vec::new();
    (&mut decoder)
        .take((limit as u64).saturating_add(1))
        .read_to_end(&mut out)
        .map_err(|e| format!("decompression error: {e}"))?;
    if out.len() > limit
        || (size.is_some() && out.len() != limit)
        || !decoder.into_frame_decoder().is_finished()
    {
        return Err(INCOMPLETE.into());
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// `zstandard.ZstdCompressor().compress(b"abc" * 400)`, with and without `write_content_size`.
    const SIZED: &str = "28b52ffd60b003550000186162630100aaf8bb21";
    const UNSIZED: &str = "28b52ffd0008550000186162630100aaf8bb21";

    fn bytes(hex: &str) -> Vec<u8> {
        (0..hex.len())
            .step_by(2)
            .map(|i| u8::from_str_radix(&hex[i..i + 2], 16).unwrap())
            .collect()
    }

    #[test]
    fn content_size_wins_over_the_limit() {
        let data = b"abc".repeat(400);
        let packed = bytes(SIZED);
        assert_eq!(content_size(&packed), Some(1200));
        assert_eq!(decompress(&packed, 10).unwrap(), data);
        let mut trailing = packed.clone();
        trailing.extend_from_slice(b"xx");
        assert_eq!(decompress(&trailing, 0).unwrap(), data);
    }

    #[test]
    fn without_a_size_the_limit_bounds_it() {
        let packed = bytes(UNSIZED);
        assert_eq!(content_size(&packed), None);
        assert_eq!(
            decompress(&packed, 0).unwrap_err(),
            "could not determine content size in frame header"
        );
        assert_eq!(decompress(&packed, 100).unwrap_err(), INCOMPLETE);
        assert_eq!(decompress(&packed, 5000).unwrap().len(), 1200);
        assert_eq!(decompress(&packed, 1200).unwrap().len(), 1200);
    }

    #[test]
    fn a_cut_frame_fails() {
        let packed = bytes(SIZED);
        assert!(decompress(&packed[..packed.len() - 3], 0).is_err());
    }

    #[test]
    fn smoke_test_frame_round_trips() {
        use ruzstd::encoding::{CompressionLevel, compress_to_vec};

        let data = b"abc".repeat(400);
        let frame = compress_to_vec(data.as_slice(), CompressionLevel::Fastest);
        assert_eq!(decompress(&frame, data.len()).unwrap(), data);
    }
}
