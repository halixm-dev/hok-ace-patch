//! Ideal endpoints and weights (`astcenc_ideal_endpoints_and_weights.cpp`). The HDR-only RGBO
//! vectors are left out: an LDR block never sets `rgb_lns` or `alpha_lns`.

use crate::averages_and_directions::*;
use crate::internal::*;
use crate::tables::QUANT_AND_XFER_TABLES;
use crate::vecmath::*;

/// One of a texel's weight taps: the decimated weight times its contribution.
#[inline(always)]
fn infill_tap(di: &DecimationInfo, weights: &[f32], index: usize, k: usize) -> VFloat4 {
    gatherf_u8(weights, &di.texel_weights_tr[k][index..])
        * VFloat4::load(&di.texel_weight_contribs_float_tr[k][index..])
}

#[inline(always)]
fn bilinear_infill_vla(di: &DecimationInfo, weights: &[f32], index: usize) -> VFloat4 {
    (infill_tap(di, weights, index, 0) + infill_tap(di, weights, index, 1))
        + (infill_tap(di, weights, index, 2) + infill_tap(di, weights, index, 3))
}

#[inline(always)]
fn bilinear_infill_vla_2(di: &DecimationInfo, weights: &[f32], index: usize) -> VFloat4 {
    infill_tap(di, weights, index, 0) + infill_tap(di, weights, index, 1)
}

/// The weights of a partition's texels along its line, scaled to 0..1, as every `_N_comp`
/// variant writes them; returns the partition's squared length.
#[expect(
    clippy::too_many_arguments,
    reason = "the four `_N_comp` variants share it"
)]
fn scale_partition_weights(
    pi: &PartitionInfo,
    i: usize,
    ei: &mut EndpointsAndWeights,
    lowparam: &mut f32,
    highparam: &mut f32,
    error_weight: f32,
    is_constant_wes: &mut bool,
    partition0_len_sq: &mut f32,
) {
    if *highparam <= *lowparam {
        *lowparam = 0.0;
        *highparam = 1e-7;
    }
    let length = *highparam - *lowparam;
    let length_squared = length * length;
    let scale = 1.0 / length;
    if i == 0 {
        *partition0_len_sq = length_squared;
    } else {
        *is_constant_wes = *is_constant_wes && length_squared == *partition0_len_sq;
    }
    for &t in &pi.texels_of_partition[i][..pi.partition_texel_count[i] as usize] {
        let tix = t as usize;
        let idx = astc::clamp1f((ei.weights[tix] - *lowparam) * scale);
        ei.weights[tix] = idx;
        ei.weight_error_scale[tix] = length_squared * error_weight;
    }
}

fn finish(ei: &mut EndpointsAndWeights, texel_count: u32, is_constant_wes: bool) {
    for i in texel_count..round_up_to_simd_multiple_vla(texel_count) {
        ei.weights[i as usize] = 0.0;
        ei.weight_error_scale[i as usize] = 0.0;
    }
    ei.is_constant_weight_error_scale = is_constant_wes;
}

fn compute_ideal_colors_and_weights_1_comp(
    blk: &ImageBlock,
    pi: &PartitionInfo,
    ei: &mut EndpointsAndWeights,
    component: u32,
) {
    let partition_count = pi.partition_count as usize;
    ei.ep.partition_count = partition_count as u32;
    let c = component as usize;
    let error_weight = blk.channel_weight.lane(c);
    let data_vr = blk.channel(c);
    let sep_mask = VInt4::lane_id().eq(VInt4::splat(component as i32));
    let mut is_constant_wes = true;
    let mut partition0_len_sq = 0.0;
    for i in 0..partition_count {
        let mut lowvalue = 1e10f32;
        let mut highvalue = -1e10f32;
        let texels = &pi.texels_of_partition[i][..pi.partition_texel_count[i] as usize];
        for &t in texels {
            let value = data_vr[t as usize];
            lowvalue = astc::min(value, lowvalue);
            highvalue = astc::max(value, highvalue);
        }
        if highvalue <= lowvalue {
            lowvalue = 0.0;
            highvalue = 1e-7;
        }
        let length = highvalue - lowvalue;
        let length_squared = length * length;
        let scale = 1.0 / length;
        if i == 0 {
            partition0_len_sq = length_squared;
        } else {
            is_constant_wes = is_constant_wes && length_squared == partition0_len_sq;
        }
        for &t in texels {
            let tix = t as usize;
            let value = astc::clamp1f((data_vr[tix] - lowvalue) * scale);
            ei.weights[tix] = value;
            ei.weight_error_scale[tix] = length_squared * error_weight;
        }
        ei.ep.endpt0[i] = select(blk.data_min, VFloat4::splat(lowvalue), sep_mask);
        ei.ep.endpt1[i] = select(blk.data_max, VFloat4::splat(highvalue), sep_mask);
    }
    finish(ei, blk.texel_count as u32, is_constant_wes);
}

fn compute_ideal_colors_and_weights_2_comp(
    blk: &ImageBlock,
    pi: &PartitionInfo,
    ei: &mut EndpointsAndWeights,
    component1: u32,
    component2: u32,
) {
    let partition_count = pi.partition_count as usize;
    ei.ep.partition_count = partition_count as u32;
    let (error_weight, data_vr, data_vg) = match (component1, component2) {
        (0, 1) => (
            hadd_s(blk.channel_weight.swz2(0, 1)) / 2.0,
            &blk.data_r,
            &blk.data_g,
        ),
        (0, 2) => (
            hadd_s(blk.channel_weight.swz2(0, 2)) / 2.0,
            &blk.data_r,
            &blk.data_b,
        ),
        _ => (
            hadd_s(blk.channel_weight.swz2(1, 2)) / 2.0,
            &blk.data_g,
            &blk.data_b,
        ),
    };
    let mut pms = [PartitionMetrics::default(); 4];
    compute_avgs_and_dirs_2_comp(pi, blk, component1, component2, &mut pms);
    let mut is_constant_wes = true;
    let mut partition0_len_sq = 0.0;
    let comp1_mask = VInt4::lane_id().eq(VInt4::splat(component1 as i32));
    let comp2_mask = VInt4::lane_id().eq(VInt4::splat(component2 as i32));
    for i in 0..partition_count {
        let mut dir = pms[i].dir;
        if hadd_s(dir) < 0.0 {
            dir = VFloat4::zero() - dir;
        }
        let (la, lb) = (pms[i].avg, normalize_safe(dir, unit2()));
        let mut lowparam = 1e10f32;
        let mut highparam = -1e10f32;
        for &t in &pi.texels_of_partition[i][..pi.partition_texel_count[i] as usize] {
            let tix = t as usize;
            let point = vfloat2(data_vr[tix], data_vg[tix]);
            let param = dot_s(point - la, lb);
            ei.weights[tix] = param;
            lowparam = astc::min(param, lowparam);
            highparam = astc::max(param, highparam);
        }
        scale_partition_weights(
            pi,
            i,
            ei,
            &mut lowparam,
            &mut highparam,
            error_weight,
            &mut is_constant_wes,
            &mut partition0_len_sq,
        );
        let lowvalue = la + lb * lowparam;
        let highvalue = la + lb * highparam;
        let ep0 = select(blk.data_min, VFloat4::splat(lowvalue.lane(0)), comp1_mask);
        let ep1 = select(blk.data_max, VFloat4::splat(highvalue.lane(0)), comp1_mask);
        ei.ep.endpt0[i] = select(ep0, VFloat4::splat(lowvalue.lane(1)), comp2_mask);
        ei.ep.endpt1[i] = select(ep1, VFloat4::splat(highvalue.lane(1)), comp2_mask);
    }
    finish(ei, blk.texel_count as u32, is_constant_wes);
}

fn compute_ideal_colors_and_weights_3_comp(
    blk: &ImageBlock,
    pi: &PartitionInfo,
    ei: &mut EndpointsAndWeights,
    omitted_component: u32,
) {
    let partition_count = pi.partition_count as usize;
    ei.ep.partition_count = partition_count as u32;
    let cw = blk.channel_weight;
    // The C++ weighs an omitted red by red, green and blue (`swz<0, 1, 2>`), not by the three kept.
    let (error_weight, chans) = match omitted_component {
        0 => (hadd_s(cw.swz3(0, 1, 2)), [1, 2, 3]),
        1 => (hadd_s(cw.swz3(0, 2, 3)), [0, 2, 3]),
        2 => (hadd_s(cw.swz3(0, 1, 3)), [0, 1, 3]),
        _ => (hadd_s(cw.swz3(0, 1, 2)), [0, 1, 2]),
    };
    let error_weight = error_weight * (1.0 / 3.0);
    let (data_vr, data_vg, data_vb) = (
        blk.channel(chans[0]),
        blk.channel(chans[1]),
        blk.channel(chans[2]),
    );
    let mut pms = [PartitionMetrics::default(); 4];
    if omitted_component == 3 {
        compute_avgs_and_dirs_3_comp_rgb(pi, blk, &mut pms);
    } else {
        compute_avgs_and_dirs_3_comp(pi, blk, omitted_component, &mut pms);
    }
    let mut is_constant_wes = true;
    let mut partition0_len_sq = 0.0;
    for i in 0..partition_count {
        let mut dir = pms[i].dir;
        if hadd_rgb_s(dir) < 0.0 {
            dir = VFloat4::zero() - dir;
        }
        let (la, lb) = (pms[i].avg, normalize_safe(dir, unit3()));
        let mut lowparam = 1e10f32;
        let mut highparam = -1e10f32;
        for &t in &pi.texels_of_partition[i][..pi.partition_texel_count[i] as usize] {
            let tix = t as usize;
            let point = vfloat3(data_vr[tix], data_vg[tix], data_vb[tix]);
            let param = dot3_s(point - la, lb);
            ei.weights[tix] = param;
            lowparam = astc::min(param, lowparam);
            highparam = astc::max(param, highparam);
        }
        scale_partition_weights(
            pi,
            i,
            ei,
            &mut lowparam,
            &mut highparam,
            error_weight,
            &mut is_constant_wes,
            &mut partition0_len_sq,
        );
        let ep0 = la + lb * lowparam;
        let ep1 = la + lb * highparam;
        let (bmin, bmax) = (blk.data_min, blk.data_max);
        let (e0, e1) = match omitted_component {
            0 => (
                VFloat4::new(bmin.lane(0), ep0.lane(0), ep0.lane(1), ep0.lane(2)),
                VFloat4::new(bmax.lane(0), ep1.lane(0), ep1.lane(1), ep1.lane(2)),
            ),
            1 => (
                VFloat4::new(ep0.lane(0), bmin.lane(1), ep0.lane(1), ep0.lane(2)),
                VFloat4::new(ep1.lane(0), bmax.lane(1), ep1.lane(1), ep1.lane(2)),
            ),
            2 => (
                VFloat4::new(ep0.lane(0), ep0.lane(1), bmin.lane(2), ep0.lane(2)),
                VFloat4::new(ep1.lane(0), ep1.lane(1), bmax.lane(2), ep1.lane(2)),
            ),
            _ => (
                VFloat4::new(ep0.lane(0), ep0.lane(1), ep0.lane(2), bmin.lane(3)),
                VFloat4::new(ep1.lane(0), ep1.lane(1), ep1.lane(2), bmax.lane(3)),
            ),
        };
        ei.ep.endpt0[i] = e0;
        ei.ep.endpt1[i] = e1;
    }
    finish(ei, blk.texel_count as u32, is_constant_wes);
}

fn compute_ideal_colors_and_weights_4_comp(
    blk: &ImageBlock,
    pi: &PartitionInfo,
    ei: &mut EndpointsAndWeights,
) {
    let error_weight = hadd_s(blk.channel_weight) / 4.0;
    let partition_count = pi.partition_count as usize;
    let mut pms = [PartitionMetrics::default(); 4];
    compute_avgs_and_dirs_4_comp(pi, blk, &mut pms);
    let mut is_constant_wes = true;
    let mut partition0_len_sq = 0.0;
    for i in 0..partition_count {
        let mut dir = pms[i].dir;
        if hadd_rgb_s(dir) < 0.0 {
            dir = VFloat4::zero() - dir;
        }
        let (la, lb) = (pms[i].avg, normalize_safe(dir, unit4()));
        let mut lowparam = 1e10f32;
        let mut highparam = -1e10f32;
        for &t in &pi.texels_of_partition[i][..pi.partition_texel_count[i] as usize] {
            let tix = t as usize;
            let param = dot_s(blk.texel(tix) - la, lb);
            ei.weights[tix] = param;
            lowparam = astc::min(param, lowparam);
            highparam = astc::max(param, highparam);
        }
        // The C++ sets the endpoints from the corrected bounds before it scales the weights.
        let (mut lo, mut hi) = (lowparam, highparam);
        if hi <= lo {
            lo = 0.0;
            hi = 1e-7;
        }
        ei.ep.endpt0[i] = la + lb * lo;
        ei.ep.endpt1[i] = la + lb * hi;
        scale_partition_weights(
            pi,
            i,
            ei,
            &mut lowparam,
            &mut highparam,
            error_weight,
            &mut is_constant_wes,
            &mut partition0_len_sq,
        );
    }
    // As in the C++, `ep.partition_count` is left as it was.
    finish(ei, blk.texel_count as u32, is_constant_wes);
}

pub fn compute_ideal_colors_and_weights_1plane(
    blk: &ImageBlock,
    pi: &PartitionInfo,
    ei: &mut EndpointsAndWeights,
) {
    let _prof = crate::prof::span(0);
    if !blk.is_constant_channel(3) {
        compute_ideal_colors_and_weights_4_comp(blk, pi, ei);
    } else {
        compute_ideal_colors_and_weights_3_comp(blk, pi, ei, 3);
    }
}

pub fn compute_ideal_colors_and_weights_2planes(
    bsd: &BlockSizeDescriptor,
    blk: &ImageBlock,
    plane2_component: u32,
    ei1: &mut EndpointsAndWeights,
    ei2: &mut EndpointsAndWeights,
) {
    let _prof = crate::prof::span(0);
    let pi = bsd.get_partition_info(1, 0);
    let uses_alpha = !blk.is_constant_channel(3);
    match plane2_component {
        0 => {
            if uses_alpha {
                compute_ideal_colors_and_weights_3_comp(blk, pi, ei1, 0);
            } else {
                compute_ideal_colors_and_weights_2_comp(blk, pi, ei1, 1, 2);
            }
        }
        1 => {
            if uses_alpha {
                compute_ideal_colors_and_weights_3_comp(blk, pi, ei1, 1);
            } else {
                compute_ideal_colors_and_weights_2_comp(blk, pi, ei1, 0, 2);
            }
        }
        2 => {
            if uses_alpha {
                compute_ideal_colors_and_weights_3_comp(blk, pi, ei1, 2);
            } else {
                compute_ideal_colors_and_weights_2_comp(blk, pi, ei1, 0, 1);
            }
        }
        _ => compute_ideal_colors_and_weights_3_comp(blk, pi, ei1, 3),
    }
    compute_ideal_colors_and_weights_1_comp(blk, pi, ei2, plane2_component);
}

#[inline(always)]
fn infill(di: &DecimationInfo, weights: &[f32], i: usize) -> VFloat4 {
    if di.max_texel_weight_count > 2 {
        bilinear_infill_vla(di, weights, i)
    } else if di.max_texel_weight_count > 1 {
        bilinear_infill_vla_2(di, weights, i)
    } else {
        VFloat4::load(&weights[i..])
    }
}

pub fn compute_error_of_weight_set_1plane(
    eai: &EndpointsAndWeights,
    di: &DecimationInfo,
    dec_weight_quant_uvalue: &[f32],
) -> f32 {
    let _prof = crate::prof::span(4);
    let mut error_summav = VFloat4::zero();
    let mut i = 0;
    while i < di.texel_count as usize {
        let current_values = infill(di, dec_weight_quant_uvalue, i);
        let actual_values = VFloat4::load(&eai.weights[i..]);
        let diff = current_values - actual_values;
        let significance = VFloat4::load(&eai.weight_error_scale[i..]);
        haccumulate(&mut error_summav, diff * diff * significance);
        i += SIMD_WIDTH;
    }
    hadd_s(error_summav)
}

pub fn compute_error_of_weight_set_2planes(
    eai1: &EndpointsAndWeights,
    eai2: &EndpointsAndWeights,
    di: &DecimationInfo,
    plane1: &[f32],
    plane2: &[f32],
) -> f32 {
    let _prof = crate::prof::span(4);
    let mut error_summav = VFloat4::zero();
    let mut i = 0;
    while i < di.texel_count as usize {
        let diff = infill(di, plane1, i) - VFloat4::load(&eai1.weights[i..]);
        let error1 = diff * diff * VFloat4::load(&eai1.weight_error_scale[i..]);
        let diff = infill(di, plane2, i) - VFloat4::load(&eai2.weights[i..]);
        let error2 = diff * diff * VFloat4::load(&eai2.weight_error_scale[i..]);
        haccumulate(&mut error_summav, error1 + error2);
        i += SIMD_WIDTH;
    }
    hadd_s(error_summav)
}

pub fn compute_ideal_weights_for_decimation(
    ei: &EndpointsAndWeights,
    di: &DecimationInfo,
    dec_weight_ideal_value: &mut [f32],
) {
    let _prof = crate::prof::span(1);
    let texel_count = di.texel_count as usize;
    let weight_count = di.weight_count as usize;
    let is_direct = texel_count == weight_count;
    let prev = round_down_to_simd_multiple_vla(weight_count as u32 - 1) as usize;
    VFloat4::zero().store(&mut dec_weight_ideal_value[prev..]);
    if is_direct {
        let mut i = 0;
        while i < texel_count {
            VFloat4::load(&ei.weights[i..]).store(&mut dec_weight_ideal_value[i..]);
            i += SIMD_WIDTH;
        }
        return;
    }
    // Uninitialized on the C++ stack; only lanes the loops below write are read back.
    let mut infilled_weights = [0.0f32; BLOCK_MAX_TEXELS];
    let constant_wes = ei.is_constant_weight_error_scale;
    let mut weight_error_scale = VFloat4::splat(ei.weight_error_scale[0]);
    let mut i = 0;
    while i < weight_count {
        let mut weight_weight = VFloat4::splat(1e-10);
        let mut initial_weight = VFloat4::zero();
        let max_texel_count = hmax_s_i(VInt4::from_u8(&di.weight_texel_count[i..])) as usize;
        for j in 0..max_texel_count {
            let texel = &di.weight_texels_tr[j][i..];
            let weight = VFloat4::load(&di.weights_texel_contribs_tr[j][i..]);
            if !constant_wes {
                weight_error_scale = gatherf_u8(&ei.weight_error_scale, texel);
            }
            let contrib_weight = weight * weight_error_scale;
            weight_weight += contrib_weight;
            initial_weight += gatherf_u8(&ei.weights, texel) * contrib_weight;
        }
        (initial_weight / weight_weight).store(&mut dec_weight_ideal_value[i..]);
        i += SIMD_WIDTH;
    }
    let mut i = 0;
    while i < texel_count {
        let weight = if di.max_texel_weight_count <= 2 {
            bilinear_infill_vla_2(di, dec_weight_ideal_value, i)
        } else {
            bilinear_infill_vla(di, dec_weight_ideal_value, i)
        };
        weight.store(&mut infilled_weights[i..]);
        i += SIMD_WIDTH;
    }
    const STEPSIZE: f32 = 0.25;
    const CHD_SCALE: f32 = -WEIGHTS_TEXEL_SUM;
    let mut i = 0;
    while i < weight_count {
        let weight_val = VFloat4::load(&dec_weight_ideal_value[i..]);
        let mut error_change0 = VFloat4::splat(1e-10);
        let mut error_change1 = VFloat4::splat(0.0);
        let max_texel_count = hmax_s_i(VInt4::from_u8(&di.weight_texel_count[i..])) as usize;
        for j in 0..max_texel_count {
            let texel = &di.weight_texels_tr[j][i..];
            let contrib_weight = VFloat4::load(&di.weights_texel_contribs_tr[j][i..]);
            if !constant_wes {
                weight_error_scale = gatherf_u8(&ei.weight_error_scale, texel);
            }
            let scale = weight_error_scale * contrib_weight;
            let old_weight = gatherf_u8(&infilled_weights, texel);
            let ideal_weight = gatherf_u8(&ei.weights, texel);
            error_change0 += contrib_weight * scale;
            error_change1 += (old_weight - ideal_weight) * scale;
        }
        let step = clamp(
            -STEPSIZE,
            STEPSIZE,
            (error_change1 * CHD_SCALE) / error_change0,
        );
        (weight_val + step).store(&mut dec_weight_ideal_value[i..]);
        i += SIMD_WIDTH;
    }
}

const QUANT_LEVELS_M1: [f32; 12] = [
    1.0, 2.0, 3.0, 4.0, 5.0, 7.0, 9.0, 11.0, 15.0, 19.0, 23.0, 31.0,
];

#[inline]
fn table_lookup(table: &[u8; 32], idx: VInt4) -> VInt4 {
    // An index past the table would read the bytes after it in the C++; clampzo keeps it in range.
    let at = |l: usize| table.get(idx.lane(l) as usize).copied().unwrap_or(0) as i32;
    VInt4::new(at(0), at(1), at(2), at(3))
}

pub fn compute_quantized_weights_for_decimation(
    di: &DecimationInfo,
    mut low_bound: f32,
    mut high_bound: f32,
    dec_weight_ideal_value: &[f32],
    weight_set_out: &mut [f32],
    quantized_weight_set: &mut [u8],
    quant_level: usize,
) {
    let _prof = crate::prof::span(3);
    let weight_count = di.weight_count as usize;
    let qat = &QUANT_AND_XFER_TABLES[quant_level];
    let steps_m1 = VInt4::splat(get_quant_level(quant_level) as i32 - 1);
    let quant_level_m1 = QUANT_LEVELS_M1[quant_level];
    if high_bound <= low_bound {
        low_bound = 0.0;
        high_bound = 1.0;
    }
    let mut rscale = high_bound - low_bound;
    let scale = 1.0 / rscale;
    let scaled_low_bound = low_bound * scale;
    rscale *= 1.0 / 64.0;
    let mut i = 0;
    while i < weight_count {
        let ix = clampzo(
            VFloat4::load(&dec_weight_ideal_value[i..]) * scale - VFloat4::splat(scaled_low_bound),
        );
        let ix1 = ix * quant_level_m1;
        let weightl = float_to_int(ix1);
        let weighth = mini(weightl + VInt4::splat(1), steps_m1);
        let ixli = table_lookup(&qat.quant_to_unquant, weightl);
        let ixhi = table_lookup(&qat.quant_to_unquant, weighth);
        let mut ixl = int_to_float(ixli);
        let ixh = int_to_float(ixhi);
        let mask = (ixl + ixh).lt(VFloat4::splat(128.0) * ix);
        let weight = select_i(ixli, ixhi, mask);
        ixl = select(ixl, ixh, mask);
        (ixl * rscale + VFloat4::splat(low_bound)).store(&mut weight_set_out[i..]);
        quantized_weight_set[i..i + 4].copy_from_slice(&pack_low_bytes(weight));
        i += SIMD_WIDTH;
    }
}

/// The per-texel weights, undecimated from the quantized decimated ones.
fn undecimate(
    di: &DecimationInfo,
    dec_weights_uquant: &[u8],
    texel_count: usize,
    out: &mut [f32; BLOCK_MAX_TEXELS],
) {
    let mut dec_weight = [0.0f32; BLOCK_MAX_WEIGHTS];
    let mut i = 0;
    while i < di.weight_count as usize {
        let v = int_to_float(VInt4::from_u8(&dec_weights_uquant[i..])) * VFloat4::splat(1.0 / 64.0);
        v.store(&mut dec_weight[i..]);
        i += SIMD_WIDTH;
    }
    if di.max_texel_weight_count == 1 {
        out[..BLOCK_MAX_WEIGHTS].copy_from_slice(&dec_weight);
        return;
    }
    let mut i = 0;
    while i < texel_count {
        let w = if di.max_texel_weight_count <= 2 {
            bilinear_infill_vla_2(di, &dec_weight, i)
        } else {
            bilinear_infill_vla(di, &dec_weight, i)
        };
        w.store(&mut out[i..]);
        i += SIMD_WIDTH;
    }
}

pub fn recompute_ideal_colors_1plane(
    blk: &ImageBlock,
    pi: &PartitionInfo,
    di: &DecimationInfo,
    dec_weights_uquant: &[u8],
    ep: &mut Endpoints,
    rgbs_vectors: &mut [VFloat4; 4],
) {
    let _prof = crate::prof::span(6);
    let partition_count = pi.partition_count as usize;
    let mut undec_weight = [0.0f32; BLOCK_MAX_TEXELS];
    undecimate(
        di,
        dec_weights_uquant,
        blk.texel_count as usize,
        &mut undec_weight,
    );
    let mut rgba_sum = blk.data_mean * blk.texel_count as f32;
    for i in 0..partition_count {
        let texel_count = pi.partition_texel_count[i] as usize;
        let texel_indexes = &pi.texels_of_partition[i][..texel_count];
        if partition_count > 1 {
            rgba_sum = VFloat4::zero();
            for &t in texel_indexes {
                rgba_sum += blk.texel(t as usize);
            }
        }
        rgba_sum = rgba_sum * blk.channel_weight;
        let rgba_weight_sum = max_s(blk.channel_weight * texel_count as f32, 1e-17);
        let scale_dir = normalize((rgba_sum / rgba_weight_sum).swz3(0, 1, 2));
        let mut scale_max = 0.0f32;
        let mut scale_min = 1e10f32;
        let mut wmin1 = 1.0f32;
        let mut wmax1 = 0.0f32;
        let (mut left_sum_s, mut middle_sum_s, mut right_sum_s) = (0.0f32, 0.0f32, 0.0f32);
        let mut color_vec_x = VFloat4::zero();
        let mut color_vec_y = VFloat4::zero();
        let mut scale_vec = VFloat4::zero();
        let color_weight = blk.channel_weight;
        let ls_weight = hadd_rgb_s(color_weight);
        for &t in texel_indexes {
            let tix = t as usize;
            let rgba = blk.texel(tix);
            let idx0 = undec_weight[tix];
            let om_idx0 = 1.0 - idx0;
            wmin1 = astc::min(idx0, wmin1);
            wmax1 = astc::max(idx0, wmax1);
            let scale = dot3_s(scale_dir, rgba);
            scale_min = astc::min(scale, scale_min);
            scale_max = astc::max(scale, scale_max);
            left_sum_s += om_idx0 * om_idx0;
            middle_sum_s += om_idx0 * idx0;
            right_sum_s += idx0 * idx0;
            let cwiprod = rgba * VFloat4::splat(idx0);
            color_vec_y += cwiprod;
            color_vec_x += rgba - cwiprod;
            scale_vec += vfloat2(om_idx0, idx0) * (scale * ls_weight);
        }
        let left_sum = VFloat4::splat(left_sum_s) * color_weight;
        let middle_sum = VFloat4::splat(middle_sum_s) * color_weight;
        let right_sum = VFloat4::splat(right_sum_s) * color_weight;
        let lmrs_sum = vfloat3(left_sum_s, middle_sum_s, right_sum_s) * ls_weight;
        color_vec_x = color_vec_x * color_weight;
        color_vec_y = color_vec_y * color_weight;
        let scalediv = astc::clamp1f(scale_min / astc::max(scale_max, 1e-10));
        let sds = scale_dir * scale_max;
        rgbs_vectors[i] = VFloat4::new(sds.lane(0), sds.lane(1), sds.lane(2), scalediv);
        if wmin1 >= wmax1 * 0.999 {
            let avg = (color_vec_x + color_vec_y) / rgba_weight_sum;
            let notnan_mask = avg.eq(avg);
            ep.endpt0[i] = select(ep.endpt0[i], avg, notnan_mask);
            ep.endpt1[i] = select(ep.endpt1[i], avg, notnan_mask);
            rgbs_vectors[i] = VFloat4::new(sds.lane(0), sds.lane(1), sds.lane(2), 1.0);
        } else {
            let color_det1 = (left_sum * right_sum) - (middle_sum * middle_sum);
            let color_rdet1 = 1.0 / color_det1;
            let ls_det1 =
                (lmrs_sum.lane(0) * lmrs_sum.lane(2)) - (lmrs_sum.lane(1) * lmrs_sum.lane(1));
            let ls_rdet1 = 1.0 / ls_det1;
            let color_mss1 =
                (left_sum * left_sum) + (2.0 * middle_sum * middle_sum) + (right_sum * right_sum);
            let ls_mss1 = (lmrs_sum.lane(0) * lmrs_sum.lane(0))
                + (2.0 * lmrs_sum.lane(1) * lmrs_sum.lane(1))
                + (lmrs_sum.lane(2) * lmrs_sum.lane(2));
            let ep0 = (right_sum * color_vec_x - middle_sum * color_vec_y) * color_rdet1;
            let ep1 = (left_sum * color_vec_y - middle_sum * color_vec_x) * color_rdet1;
            let det_mask = abs(color_det1).gt(color_mss1 * 1e-4);
            let notnan_mask = ep0.eq(ep0) & ep1.eq(ep1);
            let full_mask = det_mask & notnan_mask;
            ep.endpt0[i] = select(ep.endpt0[i], ep0, full_mask);
            ep.endpt1[i] = select(ep.endpt1[i], ep1, full_mask);
            let scale_ep0 = (lmrs_sum.lane(2) * scale_vec.lane(0)
                - lmrs_sum.lane(1) * scale_vec.lane(1))
                * ls_rdet1;
            let scale_ep1 = (lmrs_sum.lane(0) * scale_vec.lane(1)
                - lmrs_sum.lane(1) * scale_vec.lane(0))
                * ls_rdet1;
            if ls_det1.abs() > (ls_mss1 * 1e-4)
                && !scale_ep0.is_nan()
                && !scale_ep1.is_nan()
                && scale_ep0 < scale_ep1
            {
                let scalediv2 = scale_ep0 / scale_ep1;
                let sdsm = scale_dir * scale_ep1;
                rgbs_vectors[i] = VFloat4::new(sdsm.lane(0), sdsm.lane(1), sdsm.lane(2), scalediv2);
            }
        }
    }
}

#[expect(clippy::too_many_arguments, reason = "mirrors the C++ signature")]
pub fn recompute_ideal_colors_2planes(
    blk: &ImageBlock,
    bsd: &BlockSizeDescriptor,
    di: &DecimationInfo,
    dec_weights_uquant_plane1: &[u8],
    dec_weights_uquant_plane2: &[u8],
    ep: &mut Endpoints,
    rgbs_vector: &mut VFloat4,
    plane2_component: i32,
) {
    let _prof = crate::prof::span(6);
    let total_texel_count = blk.texel_count as usize;
    let mut undec1 = [0.0f32; BLOCK_MAX_TEXELS];
    let mut undec2 = [0.0f32; BLOCK_MAX_TEXELS];
    undecimate(
        di,
        dec_weights_uquant_plane1,
        total_texel_count,
        &mut undec1,
    );
    undecimate(
        di,
        dec_weights_uquant_plane2,
        total_texel_count,
        &mut undec2,
    );
    let texel_count = bsd.texel_count as usize;
    let rgba_weight_sum = max_s(blk.channel_weight * texel_count as f32, 1e-17);
    let scale_dir = normalize(blk.data_mean.swz3(0, 1, 2));
    let mut scale_max = 0.0f32;
    let mut scale_min = 1e10f32;
    let (mut wmin1, mut wmax1, mut wmin2, mut wmax2) = (1.0f32, 0.0f32, 1.0f32, 0.0f32);
    let (mut left1_sum_s, mut middle1_sum_s, mut right1_sum_s) = (0.0f32, 0.0f32, 0.0f32);
    let (mut left2_sum_s, mut middle2_sum_s, mut right2_sum_s) = (0.0f32, 0.0f32, 0.0f32);
    let mut color_vec_x = VFloat4::zero();
    let mut color_vec_y = VFloat4::zero();
    let mut scale_vec = VFloat4::zero();
    let p2_mask = VInt4::lane_id().eq(VInt4::splat(plane2_component));
    let color_weight = blk.channel_weight;
    let ls_weight = hadd_rgb_s(color_weight);
    for j in 0..texel_count {
        let rgba = blk.texel(j);
        let idx0 = undec1[j];
        let om_idx0 = 1.0 - idx0;
        wmin1 = astc::min(idx0, wmin1);
        wmax1 = astc::max(idx0, wmax1);
        let scale = dot3_s(scale_dir, rgba);
        scale_min = astc::min(scale, scale_min);
        scale_max = astc::max(scale, scale_max);
        left1_sum_s += om_idx0 * om_idx0;
        middle1_sum_s += om_idx0 * idx0;
        right1_sum_s += idx0 * idx0;
        let idx1 = undec2[j];
        let om_idx1 = 1.0 - idx1;
        wmin2 = astc::min(idx1, wmin2);
        wmax2 = astc::max(idx1, wmax2);
        left2_sum_s += om_idx1 * om_idx1;
        middle2_sum_s += om_idx1 * idx1;
        right2_sum_s += idx1 * idx1;
        let color_idx = select(VFloat4::splat(idx0), VFloat4::splat(idx1), p2_mask);
        let cwiprod = rgba * color_idx;
        color_vec_y += cwiprod;
        color_vec_x += rgba - cwiprod;
        scale_vec += vfloat2(om_idx0, idx0) * (ls_weight * scale);
    }
    let left1_sum = VFloat4::splat(left1_sum_s) * color_weight;
    let middle1_sum = VFloat4::splat(middle1_sum_s) * color_weight;
    let right1_sum = VFloat4::splat(right1_sum_s) * color_weight;
    let lmrs_sum = vfloat3(left1_sum_s, middle1_sum_s, right1_sum_s) * ls_weight;
    let left2_sum = VFloat4::splat(left2_sum_s) * color_weight;
    let middle2_sum = VFloat4::splat(middle2_sum_s) * color_weight;
    let right2_sum = VFloat4::splat(right2_sum_s) * color_weight;
    color_vec_x = color_vec_x * color_weight;
    color_vec_y = color_vec_y * color_weight;
    let scalediv = astc::clamp1f(scale_min / astc::max(scale_max, 1e-10));
    let sds = scale_dir * scale_max;
    *rgbs_vector = VFloat4::new(sds.lane(0), sds.lane(1), sds.lane(2), scalediv);
    let p1_mask = VInt4::lane_id().ne(VInt4::splat(plane2_component));
    if wmin1 >= wmax1 * 0.999 {
        let avg = (color_vec_x + color_vec_y) / rgba_weight_sum;
        let full_mask = p1_mask & avg.eq(avg);
        ep.endpt0[0] = select(ep.endpt0[0], avg, full_mask);
        ep.endpt1[0] = select(ep.endpt1[0], avg, full_mask);
        *rgbs_vector = VFloat4::new(sds.lane(0), sds.lane(1), sds.lane(2), 1.0);
    } else {
        let color_det1 = (left1_sum * right1_sum) - (middle1_sum * middle1_sum);
        let color_rdet1 = 1.0 / color_det1;
        let ls_det1 = (lmrs_sum.lane(0) * lmrs_sum.lane(2)) - (lmrs_sum.lane(1) * lmrs_sum.lane(1));
        let ls_rdet1 = 1.0 / ls_det1;
        let color_mss1 =
            (left1_sum * left1_sum) + (2.0 * middle1_sum * middle1_sum) + (right1_sum * right1_sum);
        let ls_mss1 = (lmrs_sum.lane(0) * lmrs_sum.lane(0))
            + (2.0 * lmrs_sum.lane(1) * lmrs_sum.lane(1))
            + (lmrs_sum.lane(2) * lmrs_sum.lane(2));
        let ep0 = (right1_sum * color_vec_x - middle1_sum * color_vec_y) * color_rdet1;
        let ep1 = (left1_sum * color_vec_y - middle1_sum * color_vec_x) * color_rdet1;
        let scale_ep0 = (lmrs_sum.lane(2) * scale_vec.lane(0)
            - lmrs_sum.lane(1) * scale_vec.lane(1))
            * ls_rdet1;
        let scale_ep1 = (lmrs_sum.lane(0) * scale_vec.lane(1)
            - lmrs_sum.lane(1) * scale_vec.lane(0))
            * ls_rdet1;
        let det_mask = abs(color_det1).gt(color_mss1 * 1e-4);
        let full_mask = p1_mask & det_mask & (ep0.eq(ep0) & ep1.eq(ep1));
        ep.endpt0[0] = select(ep.endpt0[0], ep0, full_mask);
        ep.endpt1[0] = select(ep.endpt1[0], ep1, full_mask);
        if ls_det1.abs() > (ls_mss1 * 1e-4)
            && !scale_ep0.is_nan()
            && !scale_ep1.is_nan()
            && scale_ep0 < scale_ep1
        {
            let scalediv2 = scale_ep0 / scale_ep1;
            let sdsm = scale_dir * scale_ep1;
            *rgbs_vector = VFloat4::new(sdsm.lane(0), sdsm.lane(1), sdsm.lane(2), scalediv2);
        }
    }
    if wmin2 >= wmax2 * 0.999 {
        let avg = (color_vec_x + color_vec_y) / rgba_weight_sum;
        let full_mask = p2_mask & avg.eq(avg);
        ep.endpt0[0] = select(ep.endpt0[0], avg, full_mask);
        ep.endpt1[0] = select(ep.endpt1[0], avg, full_mask);
    } else {
        let color_det2 = (left2_sum * right2_sum) - (middle2_sum * middle2_sum);
        let color_rdet2 = 1.0 / color_det2;
        let color_mss2 =
            (left2_sum * left2_sum) + (2.0 * middle2_sum * middle2_sum) + (right2_sum * right2_sum);
        let ep0 = (right2_sum * color_vec_x - middle2_sum * color_vec_y) * color_rdet2;
        let ep1 = (left2_sum * color_vec_y - middle2_sum * color_vec_x) * color_rdet2;
        let det_mask = abs(color_det2).gt(color_mss2 * 1e-4);
        let full_mask = p2_mask & det_mask & (ep0.eq(ep0) & ep1.eq(ep1));
        ep.endpt0[0] = select(ep.endpt0[0], ep0, full_mask);
        ep.endpt1[0] = select(ep.endpt1[0], ep1, full_mask);
    }
}
