//! Loading an image block (`astcenc_image.cpp`): only `load_image_block_fast_ldr`, the path
//! `compress_image` takes for a 2D RGBA8 image with the identity swizzle.

use crate::internal::*;
use crate::vecmath::*;

/// An RGBA8 image, rows packed with no padding (`astcenc_image` with one `uint8_t` plane).
#[derive(Clone, Copy, Debug)]
pub struct Image<'a> {
    pub dim_x: u32,
    pub dim_y: u32,
    pub data: &'a [u8],
}

pub fn load_image_block_fast_ldr(
    img: &Image<'_>,
    blk: &mut ImageBlock,
    bsd: &BlockSizeDescriptor,
    xpos: u32,
    ypos: u32,
    zpos: u32,
) {
    let _prof = crate::prof::span(12);
    let (xsize, ysize) = (img.dim_x, img.dim_y);
    blk.xpos = xpos;
    blk.ypos = ypos;
    blk.zpos = zpos;
    let mut data_min = VFloat4::splat(1e38);
    let mut data_mean = VFloat4::zero();
    let mut data_max = VFloat4::splat(-1e38);
    let mut grayscalev = VMask4::splat(true);
    let mut idx = 0;
    for y in ypos..ypos + bsd.ydim as u32 {
        let yi = astc::min(y, ysize - 1);
        for x in xpos..xpos + bsd.xdim as u32 {
            let xi = astc::min(x, xsize - 1);
            let o = (4 * xsize * yi + 4 * xi) as usize;
            let datavi = VInt4::from_u8(&img.data[o..o + 4]);
            let datav = int_to_float(datavi) * (65535.0f32 / 255.0f32);
            data_min = min(data_min, datav);
            data_mean += datav;
            data_max = max(data_max, datav);
            grayscalev = grayscalev & datav.swz4(0, 0, 0, 0).eq(datav.swz4(1, 1, 2, 2));
            blk.data_r[idx] = datav.lane(0);
            blk.data_g[idx] = datav.lane(1);
            blk.data_b[idx] = datav.lane(2);
            blk.data_a[idx] = datav.lane(3);
            idx += 1;
        }
    }
    blk.origin_texel = blk.texel(0) / 65535.0;
    blk.rgb_lns[0] = 0;
    blk.alpha_lns[0] = 0;
    blk.data_min = data_min;
    blk.data_mean = data_mean / bsd.texel_count as f32;
    blk.data_max = data_max;
    blk.grayscale = all(grayscalev);
}
