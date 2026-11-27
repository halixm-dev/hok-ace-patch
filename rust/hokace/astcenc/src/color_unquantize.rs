//! Endpoint unpacking (`astcenc_color_unquantize.cpp`) for the LDR profiles. An HDR format
//! decodes to the error colour either way, so its own unpacking is left out.

use crate::internal::*;
use crate::vecmath::*;

#[inline]
fn uncontract_color(input: VInt4) -> VInt4 {
    let mask = VMask4::new(true, true, false, false);
    let bc0 = (input + VInt4::splat(input.lane(2))).asr(1);
    select_i(input, bc0, mask)
}

pub fn rgba_delta_unpack(mut input0: VInt4, mut input1: VInt4) -> (VInt4, VInt4) {
    bit_transfer_signed(&mut input1, &mut input0);
    let rgb_sum = hadd_rgb_s_i(input1);
    input1 += input0;
    if rgb_sum < 0 {
        input0 = uncontract_color(input0);
        input1 = uncontract_color(input1);
        core::mem::swap(&mut input0, &mut input1);
    }
    (clampi(0, 255, input0), clampi(0, 255, input1))
}

pub fn rgba_unpack(mut input0: VInt4, mut input1: VInt4) -> (VInt4, VInt4) {
    if hadd_rgb_s_i(input0) > hadd_rgb_s_i(input1) {
        input0 = uncontract_color(input0);
        input1 = uncontract_color(input1);
        core::mem::swap(&mut input0, &mut input1);
    }
    (input0, input1)
}

fn with_alpha(mut v: (VInt4, VInt4), a0: i32, a1: i32) -> (VInt4, VInt4) {
    v.0.set_lane(3, a0);
    v.1.set_lane(3, a1);
    v
}

fn rgb_scale_unpack(input0: VInt4, scale: i32, alpha0: i32, alpha1: i32) -> (VInt4, VInt4) {
    let mut output1 = input0;
    output1.set_lane(3, alpha1);
    let mut output0 = (input0 * VInt4::splat(scale)).asr(8);
    output0.set_lane(3, alpha0);
    (output0, output1)
}

/// `unpack_color_endpoints` for `PRF_LDR` and `PRF_LDR_SRGB`; returns the two endpoints.
pub fn unpack_color_endpoints(decode_mode: u32, format: u8, input: &[u8]) -> (VInt4, VInt4) {
    let i = |k: usize| input[k] as i32;
    let out = match format {
        FMT_LUMINANCE => (
            VInt4::new(i(0), i(0), i(0), 255),
            VInt4::new(i(1), i(1), i(1), 255),
        ),
        FMT_LUMINANCE_DELTA => {
            let l0 = (i(0) >> 2) | (i(1) & 0xC0);
            let l1 = astc::min(l0 + (i(1) & 0x3F), 255);
            (VInt4::new(l0, l0, l0, 255), VInt4::new(l1, l1, l1, 255))
        }
        FMT_LUMINANCE_ALPHA => (
            VInt4::new(i(0), i(0), i(0), i(2)),
            VInt4::new(i(1), i(1), i(1), i(3)),
        ),
        FMT_LUMINANCE_ALPHA_DELTA => {
            let (mut lum0, mut lum1, mut alpha0, mut alpha1) = (i(0), i(1), i(2), i(3));
            lum0 |= (lum1 & 0x80) << 1;
            alpha0 |= (alpha1 & 0x80) << 1;
            lum1 &= 0x7F;
            alpha1 &= 0x7F;
            if lum1 & 0x40 != 0 {
                lum1 -= 0x80;
            }
            if alpha1 & 0x40 != 0 {
                alpha1 -= 0x80;
            }
            lum0 >>= 1;
            lum1 >>= 1;
            alpha0 >>= 1;
            alpha1 >>= 1;
            lum1 = astc::clamp(lum1 + lum0, 0, 255);
            alpha1 = astc::clamp(alpha1 + alpha0, 0, 255);
            (
                VInt4::new(lum0, lum0, lum0, alpha0),
                VInt4::new(lum1, lum1, lum1, alpha1),
            )
        }
        FMT_RGB_SCALE => rgb_scale_unpack(VInt4::new(i(0), i(1), i(2), 0), i(3), 255, 255),
        FMT_RGB_SCALE_ALPHA => {
            rgb_scale_unpack(VInt4::new(i(0), i(1), i(2), i(4)), i(3), i(4), i(5))
        }
        FMT_RGB => with_alpha(
            rgba_unpack(
                VInt4::new(i(0), i(2), i(4), 0),
                VInt4::new(i(1), i(3), i(5), 0),
            ),
            255,
            255,
        ),
        FMT_RGB_DELTA => with_alpha(
            rgba_delta_unpack(
                VInt4::new(i(0), i(2), i(4), 0),
                VInt4::new(i(1), i(3), i(5), 0),
            ),
            255,
            255,
        ),
        FMT_RGBA => rgba_unpack(
            VInt4::new(i(0), i(2), i(4), i(6)),
            VInt4::new(i(1), i(3), i(5), i(7)),
        ),
        FMT_RGBA_DELTA => rgba_delta_unpack(
            VInt4::new(i(0), i(2), i(4), i(6)),
            VInt4::new(i(1), i(3), i(5), i(7)),
        ),
        _ => {
            let e = VInt4::new(0xFF, 0x00, 0xFF, 0xFF);
            (e, e)
        }
    };
    let (o0, o1) = out;
    if decode_mode == PRF_LDR_SRGB {
        let mask = VMask4::new(true, true, true, false);
        let srgb = |o: VInt4| select_i(o * VInt4::splat(257), o.lsl(8) | VInt4::splat(0x80), mask);
        (srgb(o0), srgb(o1))
    } else {
        (o0 * VInt4::splat(257), o1 * VInt4::splat(257))
    }
}
