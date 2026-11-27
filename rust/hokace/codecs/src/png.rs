//! PNG label and restore images as straight RGBA8 in top-down row order.

use std::io::Cursor;

use png::{BitDepth, ColorType, Decoder, Transformations};

/// Decode the first image and return its width, height, and RGBA8 pixels.
pub fn decode_rgba(data: &[u8]) -> Result<(u32, u32, Vec<u8>), String> {
    let mut decoder = Decoder::new(Cursor::new(data));
    decoder.set_transformations(
        Transformations::EXPAND | Transformations::ALPHA | Transformations::STRIP_16,
    );
    let mut reader = decoder.read_info().map_err(|error| error.to_string())?;
    let size = reader
        .output_buffer_size()
        .ok_or("PNG output is too large")?;
    let mut pixels = vec![0; size];
    let info = reader
        .next_frame(&mut pixels)
        .map_err(|error| error.to_string())?;
    pixels.truncate(info.buffer_size());
    if info.bit_depth != BitDepth::Eight {
        return Err("expected 8-bit PNG output".into());
    }
    let rgba = match info.color_type {
        ColorType::Rgba => pixels,
        ColorType::Rgb => pixels
            .as_chunks::<3>()
            .0
            .iter()
            .flat_map(|p| [p[0], p[1], p[2], 255])
            .collect(),
        ColorType::GrayscaleAlpha => pixels
            .as_chunks::<2>()
            .0
            .iter()
            .flat_map(|p| [p[0], p[0], p[0], p[1]])
            .collect(),
        ColorType::Grayscale => pixels.into_iter().flat_map(|p| [p, p, p, 255]).collect(),
        ColorType::Indexed => return Err("PNG palette was not expanded".into()),
    };
    Ok((info.width, info.height, rgba))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_grayscale_alpha_as_rgba() {
        let mut data = Vec::new();
        let mut encoder = png::Encoder::new(&mut data, 1, 2);
        encoder.set_color(ColorType::GrayscaleAlpha);
        let mut writer = encoder.write_header().unwrap();
        writer.write_image_data(&[42, 48, 200, 255]).unwrap();
        writer.finish().unwrap();
        assert_eq!(
            decode_rgba(&data).unwrap(),
            (1, 2, vec![42, 42, 42, 48, 200, 200, 200, 255])
        );
    }
}
