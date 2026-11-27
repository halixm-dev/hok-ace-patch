#![expect(
    clippy::too_many_arguments,
    reason = "upstream block copy takes texture geometry"
)]

#[inline]
pub const fn color(r: u8, g: u8, b: u8, a: u8) -> u32 {
    u32::from_le_bytes([b, g, r, a])
}

#[inline]
pub fn copy_block_buffer(
    bx: usize,
    by: usize,
    w: usize,
    h: usize,
    bw: usize,
    bh: usize,
    buffer: &[u32],
    image: &mut [u32],
) {
    let x: usize = bw * bx;
    let copy_width: usize = if bw * (bx + 1) > w { w - bw * bx } else { bw };

    let y_0 = by * bh;
    let copy_height: usize = if bh * (by + 1) > h { h - y_0 } else { bh };
    let mut buffer_offset = 0;

    for y in y_0..y_0 + copy_height {
        let image_offset = y * w + x;
        image[image_offset..image_offset + copy_width]
            .copy_from_slice(&buffer[buffer_offset..buffer_offset + copy_width]);

        buffer_offset += bw;
    }
}
