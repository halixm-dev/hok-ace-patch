//! Endpoint quantization (`astcenc_color_quantize.cpp`), LDR formats only: the encoder never picks
//! an HDR format for an LDR block.

use crate::color_unquantize::{rgba_delta_unpack, rgba_unpack};
use crate::internal::*;
use crate::tables::COLOR_UNQUANT_TO_UQUANT;
use crate::vecmath::*;

fn get_rgba_encoding_error(
    uquant0: VFloat4,
    uquant1: VFloat4,
    quant0: VInt4,
    quant1: VInt4,
) -> f32 {
    let error0 = uquant0 - int_to_float(quant0);
    let error1 = uquant1 - int_to_float(quant1);
    hadd_s(error0 * error0 + error1 * error1)
}

#[inline]
fn table(quant_level: usize, index: i32) -> i32 {
    COLOR_UNQUANT_TO_UQUANT[quant_level - QUANT_6][index as usize] as i32
}

/// `quant_color(quant_level, value)`.
#[inline]
fn quant_color(quant_level: usize, value: i32) -> i32 {
    table(quant_level, value * 2 + 1)
}

/// `quant_color(quant_level, value, valuef)`.
#[inline]
fn quant_color_f(quant_level: usize, value: i32, valuef: f32) -> i32 {
    let mut index = value * 2;
    if valuef - value as f32 >= -0.1 {
        index += 1;
    }
    table(quant_level, index)
}

#[inline]
fn quant_color3(quant_level: usize, value: VInt4) -> VInt4 {
    let index = value * VInt4::splat(2) + VInt4::splat(1);
    VInt4::new(
        table(quant_level, index.lane(0)),
        table(quant_level, index.lane(1)),
        table(quant_level, index.lane(2)),
        0,
    )
}

#[inline]
fn quant_color3_f(quant_level: usize, value: VInt4, valuef: VFloat4) -> VInt4 {
    let index = value * VInt4::splat(2);
    let residual = valuef - int_to_float(value);
    let mask = residual.ge(VFloat4::splat(-0.1));
    let index = select_i(index, index + VInt4::splat(1), mask);
    VInt4::new(
        table(quant_level, index.lane(0)),
        table(quant_level, index.lane(1)),
        table(quant_level, index.lane(2)),
        0,
    )
}

fn quantize_rgb(mut color0: VFloat4, mut color1: VFloat4, quant_level: usize) -> (VInt4, VInt4) {
    let nudge = VFloat4::splat(0.2);
    loop {
        let color0q = maxi(float_to_int_rtn(color0), VInt4::splat(0));
        let color0i = quant_color3_f(quant_level, color0q, color0);
        color0 = color0 - nudge;
        let color1q = mini(float_to_int_rtn(color1), VInt4::splat(255));
        let color1i = quant_color3_f(quant_level, color1q, color1);
        color1 += nudge;
        if hadd_rgb_s_i(color0i) <= hadd_rgb_s_i(color1i) {
            return (color0i, color1i);
        }
    }
}

fn quantize_rgba(color0: VFloat4, color1: VFloat4, quant_level: usize) -> (VInt4, VInt4) {
    let (mut c0, mut c1) = quantize_rgb(color0, color1, quant_level);
    let (a0, a1) = (color0.lane(3), color1.lane(3));
    c0.set_lane(3, quant_color_f(quant_level, astc::flt2int_rtn(a0), a0));
    c1.set_lane(3, quant_color_f(quant_level, astc::flt2int_rtn(a1), a1));
    (c0, c1)
}

#[inline]
fn blue_contract_in_range(color0: &mut VFloat4, color1: &mut VFloat4) -> bool {
    *color0 += *color0 - color0.swz4(2, 2, 2, 3);
    *color1 += *color1 - color1.swz4(2, 2, 2, 3);
    let out = |c: VFloat4| c.lt(VFloat4::splat(0.0)) | c.gt(VFloat4::splat(255.0));
    !any(out(*color0) | out(*color1))
}

fn try_quantize_rgb_blue_contract(
    mut color0: VFloat4,
    mut color1: VFloat4,
    quant_level: usize,
) -> Option<(VInt4, VInt4)> {
    if !blue_contract_in_range(&mut color0, &mut color1) {
        return None;
    }
    let color0i = quant_color3_f(quant_level, float_to_int_rtn(color0), color0);
    let color1i = quant_color3_f(quant_level, float_to_int_rtn(color1), color1);
    if hadd_rgb_s_i(color1i) <= hadd_rgb_s_i(color0i) {
        return None;
    }
    Some((color1i, color0i))
}

fn try_quantize_rgba_blue_contract(
    color0: VFloat4,
    color1: VFloat4,
    quant_level: usize,
) -> Option<(VInt4, VInt4)> {
    let (mut c0, mut c1) = try_quantize_rgb_blue_contract(color0, color1, quant_level)?;
    let (a0, a1) = (color0.lane(3), color1.lane(3));
    c0.set_lane(3, quant_color_f(quant_level, astc::flt2int_rtn(a1), a1));
    c1.set_lane(3, quant_color_f(quant_level, astc::flt2int_rtn(a0), a0));
    Some((c0, c1))
}

/// The shared body of `try_quantize_rgb_delta` and its blue-contracted twin; `contracted` picks
/// which sign of the offset sum the encoding needs.
fn rgb_delta_body(
    color0: VFloat4,
    color1: VFloat4,
    quant_level: usize,
    contracted: bool,
) -> Option<(VInt4, VInt4)> {
    let color0a = float_to_int_rtn(color0).lsl(1);
    let color0b = color0a & 0xFF;
    let color0be = quant_color3(quant_level, color0b);
    let color0b = color0be | (color0a & 0x100);
    let mut color1d = float_to_int_rtn(color1).lsl(1) - color0b;
    color1d.set_lane(3, 0);
    if any(color1d.gt(VInt4::splat(63)) | color1d.lt(VInt4::splat(-64))) {
        return None;
    }
    color1d = (color1d & 0x7F) | (color0b & 0x100).lsr(1);
    let color1de = quant_color3(quant_level, color1d);
    let mut color_flips = (color1d ^ color1de) & 0xC0;
    color_flips.set_lane(3, 0);
    if any(color_flips.ne(VInt4::zero())) {
        return None;
    }
    let mut ep0 = color0be;
    let mut ep1 = color1de;
    bit_transfer_signed(&mut ep1, &mut ep0);
    if (hadd_rgb_s_i(ep1) < 0) != contracted {
        return None;
    }
    let ep0 = ep0 + ep1;
    if any(ep0.lt(VInt4::splat(0)) | ep0.gt(VInt4::splat(0xFF))) {
        return None;
    }
    Some((color0be, color1de))
}

fn try_quantize_rgb_delta(
    color0: VFloat4,
    color1: VFloat4,
    quant_level: usize,
) -> Option<(VInt4, VInt4)> {
    rgb_delta_body(color0, color1, quant_level, false)
}

fn try_quantize_rgb_delta_blue_contract(
    color0: VFloat4,
    color1: VFloat4,
    quant_level: usize,
) -> Option<(VInt4, VInt4)> {
    let (mut color0, mut color1) = (color1, color0);
    if !blue_contract_in_range(&mut color0, &mut color1) {
        return None;
    }
    rgb_delta_body(color0, color1, quant_level, true)
}

/// `try_quantize_alpha_delta`: the alpha lanes of a delta encoding, written into `out`.
fn try_quantize_alpha_delta(
    color0: VFloat4,
    color1: VFloat4,
    out: &mut (VInt4, VInt4),
    quant_level: usize,
) -> bool {
    let (a0, a1) = (color0.lane(3), color1.lane(3));
    let a0a = astc::flt2int_rtn(a0) << 1;
    let a0be = quant_color(quant_level, a0a & 0xFF);
    let a0b = a0be | (a0a & 0x100);
    let mut a1d = (astc::flt2int_rtn(a1) << 1) - a0b;
    if !(-64..=63).contains(&a1d) {
        return false;
    }
    a1d = (a1d & 0x7F) | ((a0b & 0x100) >> 1);
    let a1de = quant_color(quant_level, a1d);
    let mut a1du = a1de;
    if (a1d ^ a1du) & 0xC0 != 0 {
        return false;
    }
    a1du &= 0x7F;
    if a1du & 0x40 != 0 {
        a1du -= 0x80;
    }
    a1du += a0b;
    if !(0..=0x1FF).contains(&a1du) {
        return false;
    }
    out.0.set_lane(3, a0be);
    out.1.set_lane(3, a1de);
    true
}

fn try_quantize_luminance_alpha_delta(
    color0: VFloat4,
    color1: VFloat4,
    output: &mut [u8],
    quant_level: usize,
) -> bool {
    let l0 = hadd_rgb_s(color0) * (1.0 / 3.0);
    let l1 = hadd_rgb_s(color1) * (1.0 / 3.0);
    let (a0, a1) = (color0.lane(3), color1.lane(3));
    let l0a = astc::flt2int_rtn(l0) << 1;
    let a0a = astc::flt2int_rtn(a0) << 1;
    let l0be = quant_color(quant_level, l0a & 0xFF);
    let a0be = quant_color(quant_level, a0a & 0xFF);
    let l0b = l0be | (l0a & 0x100);
    let a0b = a0be | (a0a & 0x100);
    let mut l1d = (astc::flt2int_rtn(l1) << 1) - l0b;
    let mut a1d = (astc::flt2int_rtn(a1) << 1) - a0b;
    if !(-64..=63).contains(&l1d) || !(-64..=63).contains(&a1d) {
        return false;
    }
    l1d = (l1d & 0x7F) | ((l0b & 0x100) >> 1);
    a1d = (a1d & 0x7F) | ((a0b & 0x100) >> 1);
    let l1de = quant_color(quant_level, l1d);
    let a1de = quant_color(quant_level, a1d);
    if (l1d ^ l1de) & 0xC0 != 0 || (a1d ^ a1de) & 0xC0 != 0 {
        return false;
    }
    let signed = |v: i32| {
        let v = v & 0x7F;
        if v & 0x40 != 0 { v - 0x80 } else { v }
    };
    let l1du = signed(l1de) + l0b;
    let a1du = signed(a1de) + a0b;
    if !(0..=0x1FF).contains(&l1du) || !(0..=0x1FF).contains(&a1du) {
        return false;
    }
    output[..4].copy_from_slice(&[l0be as u8, l1de as u8, a0be as u8, a1de as u8]);
    true
}

fn quantize_rgbs(color: VFloat4, output: &mut [u8], quant_level: usize) {
    let scale = 1.0f32 / 257.0;
    let r = astc::clamp255f(color.lane(0) * scale);
    let g = astc::clamp255f(color.lane(1) * scale);
    let b = astc::clamp255f(color.lane(2) * scale);
    let ri = quant_color_f(quant_level, astc::flt2int_rtn(r), r);
    let gi = quant_color_f(quant_level, astc::flt2int_rtn(g), g);
    let bi = quant_color_f(quant_level, astc::flt2int_rtn(b), b);
    let oldcolorsum = hadd_rgb_s(color) * scale;
    let newcolorsum = (ri + gi + bi) as f32;
    let scalea = astc::clamp1f(color.lane(3) * (oldcolorsum + 1e-10) / (newcolorsum + 1e-10));
    let scale_idx = astc::clamp(astc::flt2int_rtn(scalea * 256.0), 0, 255);
    output[0] = ri as u8;
    output[1] = gi as u8;
    output[2] = bi as u8;
    output[3] = quant_color(quant_level, scale_idx) as u8;
}

fn quantize_luminance(color0: VFloat4, color1: VFloat4, output: &mut [u8], quant_level: usize) {
    let mut lum0 = hadd_rgb_s(color0) * (1.0 / 3.0);
    let mut lum1 = hadd_rgb_s(color1) * (1.0 / 3.0);
    if lum0 > lum1 {
        let avg = (lum0 + lum1) * 0.5;
        lum0 = avg;
        lum1 = avg;
    }
    output[0] = quant_color_f(quant_level, astc::flt2int_rtn(lum0), lum0) as u8;
    output[1] = quant_color_f(quant_level, astc::flt2int_rtn(lum1), lum1) as u8;
}

fn quantize_luminance_alpha(
    color0: VFloat4,
    color1: VFloat4,
    output: &mut [u8],
    quant_level: usize,
) {
    let lum0 = hadd_rgb_s(color0) * (1.0 / 3.0);
    let lum1 = hadd_rgb_s(color1) * (1.0 / 3.0);
    let (a0, a1) = (color0.lane(3), color1.lane(3));
    for (o, v) in output[..4].iter_mut().zip([lum0, lum1, a0, a1]) {
        *o = quant_color_f(quant_level, astc::flt2int_rtn(v), v) as u8;
    }
}

/// Keeps a trial encoding when it beats the best so far (`error < best_error`).
fn consider(
    trial: Option<(VInt4, VInt4)>,
    delta: bool,
    format: u8,
    c: (VFloat4, VFloat4),
    best: &mut (u8, f32, (VInt4, VInt4)),
) {
    if let Some(t) = trial {
        let (u0, u1) = if delta {
            rgba_delta_unpack(t.0, t.1)
        } else {
            rgba_unpack(t.0, t.1)
        };
        let error = get_rgba_encoding_error(c.0, c.1, u0, u1);
        if error < best.1 {
            *best = (format, error, t);
        }
    }
}

/// `pack_color_endpoints` (the `rgbo_color` argument is HDR-only and left out).
pub fn pack_color_endpoints(
    color0: VFloat4,
    color1: VFloat4,
    rgbs_color: VFloat4,
    format: u8,
    output: &mut [u8],
    quant_level: usize,
) -> u8 {
    let _prof = crate::prof::span(7);
    let color0 = clamp(0.0, 65535.0, color0);
    let color1 = clamp(0.0, 65535.0, color1);
    let color0_ldr = color0 * (1.0 / 257.0);
    let color1_ldr = color1 * (1.0 / 257.0);
    let c = (color0_ldr, color1_ldr);
    match format {
        FMT_RGB | FMT_RGBA => {
            let rgba = format == FMT_RGBA;
            let delta_format = if rgba { FMT_RGBA_DELTA } else { FMT_RGB_DELTA };
            // `color0_out` / `color1_out` start uninitialized in the C++; the plain encoding below
            // always beats ERROR_CALC_DEFAULT, so the zeros here are never written out.
            let mut best = (0u8, ERROR_CALC_DEFAULT, (VInt4::zero(), VInt4::zero()));
            if quant_level <= QUANT_160 {
                let (bc, plain) = if rgba {
                    let bc =
                        try_quantize_rgb_delta_blue_contract(color0_ldr, color1_ldr, quant_level)
                            .and_then(|mut o| {
                                try_quantize_alpha_delta(
                                    color1_ldr,
                                    color0_ldr,
                                    &mut o,
                                    quant_level,
                                )
                                .then_some(o)
                            });
                    let plain = try_quantize_rgb_delta(color0_ldr, color1_ldr, quant_level)
                        .and_then(|mut o| {
                            try_quantize_alpha_delta(color0_ldr, color1_ldr, &mut o, quant_level)
                                .then_some(o)
                        });
                    (bc, plain)
                } else {
                    (
                        try_quantize_rgb_delta_blue_contract(color0_ldr, color1_ldr, quant_level),
                        try_quantize_rgb_delta(color0_ldr, color1_ldr, quant_level),
                    )
                };
                // The first delta trial is taken unconditionally when it encodes.
                if let Some(t) = bc {
                    let (u0, u1) = rgba_delta_unpack(t.0, t.1);
                    best = (delta_format, get_rgba_encoding_error(c.0, c.1, u0, u1), t);
                }
                consider(plain, true, delta_format, c, &mut best);
            }
            if quant_level < QUANT_256 {
                let t = if rgba {
                    try_quantize_rgba_blue_contract(color0_ldr, color1_ldr, quant_level)
                } else {
                    try_quantize_rgb_blue_contract(color0_ldr, color1_ldr, quant_level)
                };
                consider(t, false, format, c, &mut best);
            }
            let t = if rgba {
                quantize_rgba(color0_ldr, color1_ldr, quant_level)
            } else {
                quantize_rgb(color0_ldr, color1_ldr, quant_level)
            };
            consider(Some(t), false, format, c, &mut best);
            let (o0, o1) = best.2;
            let n = if rgba { 4 } else { 3 };
            for k in 0..n {
                output[2 * k] = o0.lane(k) as u8;
                output[2 * k + 1] = o1.lane(k) as u8;
            }
            best.0
        }
        FMT_RGB_SCALE => {
            quantize_rgbs(rgbs_color, output, quant_level);
            FMT_RGB_SCALE
        }
        FMT_RGB_SCALE_ALPHA => {
            let (a0, a1) = (color0_ldr.lane(3), color1_ldr.lane(3));
            output[4] = quant_color_f(quant_level, astc::flt2int_rtn(a0), a0) as u8;
            output[5] = quant_color_f(quant_level, astc::flt2int_rtn(a1), a1) as u8;
            quantize_rgbs(rgbs_color, output, quant_level);
            FMT_RGB_SCALE_ALPHA
        }
        FMT_LUMINANCE => {
            quantize_luminance(color0_ldr, color1_ldr, output, quant_level);
            FMT_LUMINANCE
        }
        FMT_LUMINANCE_ALPHA => {
            if quant_level <= QUANT_160
                && try_quantize_luminance_alpha_delta(color0_ldr, color1_ldr, output, quant_level)
            {
                return FMT_LUMINANCE_ALPHA_DELTA;
            }
            quantize_luminance_alpha(color0_ldr, color1_ldr, output, quant_level);
            FMT_LUMINANCE_ALPHA
        }
        _ => 0,
    }
}
