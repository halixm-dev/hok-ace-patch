//! The per-block search (`astcenc_compress_symbolic.cpp`): every trial the scalar build runs, in
//! its order, with its early outs. The HDR, RGBM and trace paths are left out.

use std::sync::OnceLock;

use crate::color_quantize::pack_color_endpoints;
use crate::color_unquantize::unpack_color_endpoints;
use crate::decompress_symbolic::*;
use crate::find_best_partitioning::find_best_partition_candidates;
use crate::ideal_endpoints_and_weights::*;
use crate::internal::*;
use crate::pick_best_endpoint_format::{Candidates, compute_ideal_endpoint_formats};
use crate::symbolic_physical::symbolic_to_physical;
use crate::tables::QUANT_AND_XFER_TABLES;
use crate::vecmath::*;
use crate::weight_align::{compute_angular_endpoints_1plane, compute_angular_endpoints_2planes};

/// `compress_block`'s `static const float errorval_overshoot`: set by the first block the process
/// compresses, from that context's config, and kept for every later context, as upstream does.
static ERRORVAL_OVERSHOOT: OnceLock<f32> = OnceLock::new();

fn merge_endpoints(ep1: &Endpoints, ep2: &Endpoints, component_plane2: u32) -> Endpoints {
    let sep_mask = VInt4::lane_id().eq(VInt4::splat(component_plane2 as i32));
    let mut result = *ep1;
    result.partition_count = ep1.partition_count;
    result.endpt0[0] = select(ep1.endpt0[0], ep2.endpt0[0], sep_mask);
    result.endpt1[0] = select(ep1.endpt1[0], ep2.endpt1[0], sep_mask);
    result
}

/// The endpoints and per-weight colour steps of every partition, for one plane.
fn realign_setup(
    endpnt0: &[VInt4; 4],
    endpnt1: &[VInt4; 4],
    partition_count: usize,
    plane_mask: VMask4,
) -> ([VFloat4; 4], [VFloat4; 4]) {
    let mut endpnt0f = [VFloat4::zero(); 4];
    let mut offset = [VFloat4::zero(); 4];
    for p in 0..partition_count {
        let epd = select_i(endpnt1[p] - endpnt0[p], VInt4::zero(), plane_mask);
        endpnt0f[p] = int_to_float(endpnt0[p]);
        offset[p] = int_to_float(epd) * (1.0 / 64.0);
    }
    (endpnt0f, offset)
}

fn unpack_all(decode_mode: u32, scb: &SymbolicCompressedBlock) -> ([VInt4; 4], [VInt4; 4]) {
    let mut e0 = [VInt4::zero(); 4];
    let mut e1 = [VInt4::zero(); 4];
    for p in 0..scb.partition_count as usize {
        (e0[p], e1[p]) =
            unpack_color_endpoints(decode_mode, scb.color_formats[p], &scb.color_values[p]);
    }
    (e0, e1)
}

#[inline]
fn step(uqw: i32, up: i32, down: i32, e_base: f32, e_up: f32, e_down: f32) -> Option<i32> {
    if e_up < e_base && e_up < e_down && uqw < 64 {
        Some(up)
    } else if e_down < e_base && uqw > 0 {
        Some(down)
    } else {
        None
    }
}

fn realign_weights_undecimated(
    decode_mode: u32,
    bsd: &BlockSizeDescriptor,
    blk: &ImageBlock,
    scb: &mut SymbolicCompressedBlock,
) -> bool {
    let partition_count = scb.partition_count as usize;
    let pi = bsd.get_partition_info(partition_count as u32, scb.partition_index as u32);
    let bm = bsd.get_block_mode(scb.block_mode as u32);
    let qat = &QUANT_AND_XFER_TABLES[bm.quant_mode as usize];
    let max_plane = bm.is_dual_plane as usize;
    let mut plane_mask = VInt4::lane_id().eq(VInt4::splat(scb.plane2_component as i32));
    let (endpnt0, endpnt1) = unpack_all(decode_mode, scb);
    let mut adjustments = false;
    for pl in 0..=max_plane {
        let base = pl * WEIGHTS_PLANE2_OFFSET;
        let (endpnt0f, offset) = realign_setup(&endpnt0, &endpnt1, partition_count, plane_mask);
        for texel in 0..bsd.texel_count as usize {
            let uqw = scb.weights[base + texel] as i32;
            let pn = qat.prev_next_values[uqw as usize] as u32;
            let uqw_down = (pn & 0xFF) as i32;
            let uqw_up = ((pn >> 8) & 0xFF) as i32;
            let weight_base = uqw as f32;
            let weight_down = (uqw_down - uqw) as f32;
            let weight_up = (uqw_up - uqw) as f32;
            let partition = pi.partition_of_texel[texel] as usize;
            let color_offset = offset[partition];
            let color = endpnt0f[partition] + color_offset * weight_base;
            let error_weight = blk.channel_weight;
            let color_diff = color - blk.texel(texel);
            let color_diff_down = color_diff + color_offset * weight_down;
            let color_diff_up = color_diff + color_offset * weight_up;
            let e_base = dot_s(color_diff * color_diff, error_weight);
            let e_down = dot_s(color_diff_down * color_diff_down, error_weight);
            let e_up = dot_s(color_diff_up * color_diff_up, error_weight);
            if let Some(w) = step(uqw, uqw_up, uqw_down, e_base, e_up, e_down) {
                scb.weights[base + texel] = w as u8;
                adjustments = true;
            }
        }
        plane_mask = !plane_mask;
    }
    adjustments
}

fn realign_weights_decimated(
    decode_mode: u32,
    bsd: &BlockSizeDescriptor,
    blk: &ImageBlock,
    scb: &mut SymbolicCompressedBlock,
) -> bool {
    let partition_count = scb.partition_count as usize;
    let pi = bsd.get_partition_info(partition_count as u32, scb.partition_index as u32);
    let bm = bsd.get_block_mode(scb.block_mode as u32);
    let qat = &QUANT_AND_XFER_TABLES[bm.quant_mode as usize];
    let di = bsd.get_decimation_info(bm.decimation_mode as u32);
    let weight_count = di.weight_count as usize;
    let max_plane = bm.is_dual_plane as usize;
    let mut plane_mask = VInt4::lane_id().eq(VInt4::splat(scb.plane2_component as i32));
    let (endpnt0, endpnt1) = unpack_all(decode_mode, scb);
    let mut adjustments = false;
    for pl in 0..=max_plane {
        let base = pl * WEIGHTS_PLANE2_OFFSET;
        let (endpnt0f, offset) = realign_setup(&endpnt0, &endpnt1, partition_count, plane_mask);
        let mut uq = [0.0f32; BLOCK_MAX_WEIGHTS];
        let mut w = 0;
        while w < weight_count {
            int_to_float(VInt4::from_u8(&scb.weights[base + w..])).store(&mut uq[w..]);
            w += SIMD_WIDTH;
        }
        for we in 0..weight_count {
            let uqw = scb.weights[base + we] as i32;
            let pn = qat.prev_next_values[uqw as usize] as u32;
            let uqw_base = uq[we];
            let uqw_down = (pn & 0xFF) as f32;
            let uqw_up = ((pn >> 8) & 0xFF) as f32;
            let diff_down = uqw_down - uqw_base;
            let diff_up = uqw_up - uqw_base;
            let mut e_basev = VFloat4::zero();
            let mut e_downv = VFloat4::zero();
            let mut e_upv = VFloat4::zero();
            for te in 0..di.weight_texel_count[we] as usize {
                let texel = di.weight_texels_tr[te][we] as usize;
                let tw_base = di.texel_contrib_for_weight[te][we];
                let tw = |k: usize| {
                    uq[di.texel_weights_tr[k][texel] as usize]
                        * di.texel_weight_contribs_float_tr[k][texel]
                };
                let weight_base = (tw(0) + tw(1)) + (tw(2) + tw(3));
                let weight_down = weight_base + diff_down * tw_base - weight_base;
                let weight_up = weight_base + diff_up * tw_base - weight_base;
                let partition = pi.partition_of_texel[texel] as usize;
                let color_offset = offset[partition];
                let color = endpnt0f[partition] + color_offset * weight_base;
                let color_diff = color - blk.texel(texel);
                let color_down_diff = color_diff + color_offset * weight_down;
                let color_up_diff = color_diff + color_offset * weight_up;
                e_basev += color_diff * color_diff;
                e_downv += color_down_diff * color_down_diff;
                e_upv += color_up_diff * color_up_diff;
            }
            let ew = blk.channel_weight;
            let e_base = hadd_s(e_basev * ew);
            let e_down = hadd_s(e_downv * ew);
            let e_up = hadd_s(e_upv * ew);
            if let Some(v) = step(uqw, uqw_up as i32, uqw_down as i32, e_base, e_up, e_down) {
                uq[we] = v as f32;
                scb.weights[base + we] = v as u8;
                adjustments = true;
            }
        }
        plane_mask = !plane_mask;
    }
    adjustments
}

fn realign(
    decode_mode: u32,
    bsd: &BlockSizeDescriptor,
    di: &DecimationInfo,
    blk: &ImageBlock,
    scb: &mut SymbolicCompressedBlock,
) -> bool {
    let _prof = crate::prof::span(9);
    if di.weight_count != bsd.texel_count {
        realign_weights_decimated(decode_mode, bsd, blk, scb)
    } else {
        realign_weights_undecimated(decode_mode, bsd, blk, scb)
    }
}

/// What one trial error says to do next, shared by the pre- and post-realign checks.
enum Verdict {
    Continue,
    Break,
    Stop,
}

/// The bookkeeping after each trial error: the C++ repeats it four times.
struct Search<'a> {
    best_in_mode: f32,
    best_in_scb: f32,
    threshold: f32,
    scb: &'a mut SymbolicCompressedBlock,
}

impl Search<'_> {
    fn judge(
        &mut self,
        workscb: &mut SymbolicCompressedBlock,
        mut errorval: f32,
        iters_remaining: u32,
        base: f32,
    ) -> Verdict {
        if errorval == -ERROR_CALC_DEFAULT {
            errorval = -errorval;
            workscb.block_type = SYM_BTYPE_ERROR;
        }
        self.best_in_mode = astc::min(errorval, self.best_in_mode);
        let threshold = (0.045 * iters_remaining as f32) + base;
        if errorval > threshold * self.best_in_scb {
            return Verdict::Break;
        }
        if errorval < self.best_in_scb {
            self.best_in_scb = errorval;
            workscb.errorval = errorval;
            *self.scb = *workscb;
            if errorval < self.threshold {
                return Verdict::Stop;
            }
        }
        Verdict::Continue
    }
}

fn min_weight_cutoff(ep: &Endpoints, partition: usize, min_ep: VFloat4) -> VFloat4 {
    let e = (VFloat4::splat(1.0) - ep.endpt0[partition])
        / (ep.endpt1[partition] - ep.endpt0[partition]);
    let use_ep = e.gt(VFloat4::splat(0.5)) & e.lt(min_ep);
    select(min_ep, e, use_ep)
}

#[expect(clippy::too_many_arguments, reason = "mirrors the C++ signature")]
fn compress_symbolic_block_for_partition_1plane(
    config: &Config,
    bsd: &BlockSizeDescriptor,
    blk: &ImageBlock,
    only_always: bool,
    tune_errorval_threshold: f32,
    partition_count: u32,
    partition_index: u32,
    scb: &mut SymbolicCompressedBlock,
    tmpbuf: &mut CompressionWorkingBuffers,
    quant_limit: usize,
) -> f32 {
    let _prof = crate::prof::span(14);
    let max_weight_quant = astc::min(QUANT_32, quant_limit);
    let compute_difference = if partition_count == 1 {
        compute_symbolic_block_difference_1plane_1partition
    } else {
        compute_symbolic_block_difference_1plane
    };
    let pi = bsd.get_partition_info(partition_count, partition_index);
    let mut ei = EndpointsAndWeights::ZERO;
    compute_ideal_colors_and_weights_1plane(blk, pi, &mut ei);
    let max_decimation_modes = if only_always {
        bsd.decimation_mode_count_always
    } else {
        bsd.decimation_mode_count_selected
    };
    for i in 0..max_decimation_modes as usize {
        if !bsd.decimation_modes[i].is_ref_1plane(max_weight_quant) {
            continue;
        }
        let di = bsd.get_decimation_info(i as u32);
        compute_ideal_weights_for_decimation(
            &ei,
            di,
            &mut tmpbuf.dec_weights_ideal[i * BLOCK_MAX_WEIGHTS..],
        );
    }
    let mut min_ep = VFloat4::splat(10.0);
    for i in 0..partition_count as usize {
        min_ep = min_weight_cutoff(&ei.ep, i, min_ep);
    }
    let min_wt_cutoff = hmin_s(min_ep);
    compute_angular_endpoints_1plane(only_always, bsd, max_weight_quant, tmpbuf);
    const FREE_BITS: [i32; 4] = [
        115 - 4,
        111 - 4 - PARTITION_INDEX_BITS as i32,
        108 - 4 - PARTITION_INDEX_BITS as i32,
        105 - 4 - PARTITION_INDEX_BITS as i32,
    ];
    let max_block_modes = if only_always {
        bsd.block_mode_count_1plane_always
    } else {
        bsd.block_mode_count_1plane_selected
    };
    for i in 0..max_block_modes as usize {
        let bm = &bsd.block_modes[i];
        if bm.quant_mode as usize > max_weight_quant {
            tmpbuf.qwt_errors[i] = 1e38;
            continue;
        }
        let bitcount = FREE_BITS[partition_count as usize - 1] - bm.weight_bits as i32;
        if bitcount <= 0 {
            tmpbuf.qwt_errors[i] = 1e38;
            continue;
        }
        if tmpbuf.weight_high_value1[i] > 1.02 * min_wt_cutoff {
            tmpbuf.weight_high_value1[i] = 1.0;
        }
        let dm = bm.decimation_mode as usize;
        let di = bsd.get_decimation_info(dm as u32);
        tmpbuf.qwt_bitcounts[i] = bitcount as i8;
        let mut uquantf = [0.0f32; BLOCK_MAX_WEIGHTS];
        compute_quantized_weights_for_decimation(
            di,
            tmpbuf.weight_low_value1[i],
            tmpbuf.weight_high_value1[i],
            &tmpbuf.dec_weights_ideal[BLOCK_MAX_WEIGHTS * dm..],
            &mut uquantf,
            &mut tmpbuf.dec_weights_uquant[BLOCK_MAX_WEIGHTS * i..],
            bm.get_weight_quant_mode(),
        );
        tmpbuf.qwt_errors[i] = compute_error_of_weight_set_1plane(&ei, di, &uquantf);
    }
    let mut cand = Candidates::ZERO;
    let candidate_count = compute_ideal_endpoint_formats(
        pi,
        blk,
        &ei.ep,
        config.tune_candidate_limit,
        0,
        max_block_modes,
        &mut cand,
        tmpbuf,
    );
    let best_in_scb = scb.errorval;
    let mut search = Search {
        best_in_mode: ERROR_CALC_DEFAULT,
        best_in_scb,
        threshold: tune_errorval_threshold,
        scb,
    };
    let pc = partition_count as usize;
    'candidates: for i in 0..candidate_count as usize {
        let qw_bm = &bsd.block_modes[cand.block_mode[i] as usize];
        let di = bsd.get_decimation_info(qw_bm.decimation_mode as u32);
        let mut rgbs_colors = [VFloat4::zero(); 4];
        let mut workscb = SymbolicCompressedBlock::default();
        let mut workep = ei.ep;
        let src = BLOCK_MAX_WEIGHTS * cand.block_mode[i] as usize;
        let wc = di.weight_count as usize;
        workscb.weights[..wc].copy_from_slice(&tmpbuf.dec_weights_uquant[src..src + wc]);
        for l in 0..config.tune_refinement_limit {
            recompute_ideal_colors_1plane(
                blk,
                pi,
                di,
                &workscb.weights,
                &mut workep,
                &mut rgbs_colors,
            );
            let (ql, ql_mod) = (cand.quant_level[i], cand.quant_level_mod[i]);
            let mut all_same = ql != ql_mod;
            for j in 0..pc {
                let spec = cand.partition_format_specifiers[i][j];
                workscb.color_formats[j] = pack_color_endpoints(
                    workep.endpt0[j],
                    workep.endpt1[j],
                    rgbs_colors[j],
                    spec,
                    &mut workscb.color_values[j],
                    ql,
                );
                all_same = all_same && workscb.color_formats[j] == workscb.color_formats[0];
            }
            workscb.color_formats_matched = 0;
            if pc >= 2 && all_same {
                let mut colorvals = [[0u8; 8]; BLOCK_MAX_PARTITIONS];
                let mut formats_mod = [0u8; BLOCK_MAX_PARTITIONS];
                let mut all_same_mod = true;
                for j in 0..pc {
                    let spec = cand.partition_format_specifiers[i][j];
                    formats_mod[j] = pack_color_endpoints(
                        workep.endpt0[j],
                        workep.endpt1[j],
                        rgbs_colors[j],
                        spec,
                        &mut colorvals[j],
                        ql_mod,
                    );
                    if formats_mod[j] != formats_mod[0] {
                        all_same_mod = false;
                        break;
                    }
                }
                if all_same_mod {
                    workscb.color_formats_matched = 1;
                    workscb.color_values = colorvals;
                    workscb.color_formats = formats_mod;
                }
            }
            workscb.partition_count = partition_count as u8;
            workscb.partition_index = partition_index as u16;
            workscb.plane2_component = -1;
            workscb.quant_mode = if workscb.color_formats_matched != 0 {
                ql_mod
            } else {
                ql
            };
            workscb.block_mode = qw_bm.mode_index;
            workscb.block_type = SYM_BTYPE_NONCONST;
            if l == 0 {
                let errorval = compute_difference(config, bsd, &workscb, blk);
                match search.judge(
                    &mut workscb,
                    errorval,
                    config.tune_refinement_limit - l,
                    1.08,
                ) {
                    Verdict::Break => break,
                    Verdict::Stop => break 'candidates,
                    Verdict::Continue => {}
                }
            }
            let adjustments = realign(config.profile, bsd, di, blk, &mut workscb);
            let errorval = compute_difference(config, bsd, &workscb, blk);
            match search.judge(
                &mut workscb,
                errorval,
                config.tune_refinement_limit - 1 - l,
                1.0,
            ) {
                Verdict::Break => break,
                Verdict::Stop => break 'candidates,
                Verdict::Continue => {}
            }
            if !adjustments {
                break;
            }
        }
    }
    search.best_in_mode
}

#[expect(clippy::too_many_arguments, reason = "mirrors the C++ signature")]
fn compress_symbolic_block_for_partition_2planes(
    config: &Config,
    bsd: &BlockSizeDescriptor,
    blk: &ImageBlock,
    tune_errorval_threshold: f32,
    plane2_component: u32,
    scb: &mut SymbolicCompressedBlock,
    tmpbuf: &mut CompressionWorkingBuffers,
    quant_limit: usize,
) -> f32 {
    let _prof = crate::prof::span(15);
    let max_weight_quant = astc::min(QUANT_32, quant_limit);
    let mut ei1 = EndpointsAndWeights::ZERO;
    let mut ei2 = EndpointsAndWeights::ZERO;
    compute_ideal_colors_and_weights_2planes(bsd, blk, plane2_component, &mut ei1, &mut ei2);
    for i in 0..bsd.decimation_mode_count_selected as usize {
        if !bsd.decimation_modes[i].is_ref_2plane(max_weight_quant) {
            continue;
        }
        let di = bsd.get_decimation_info(i as u32);
        let o = i * BLOCK_MAX_WEIGHTS;
        compute_ideal_weights_for_decimation(&ei1, di, &mut tmpbuf.dec_weights_ideal[o..]);
        compute_ideal_weights_for_decimation(
            &ei2,
            di,
            &mut tmpbuf.dec_weights_ideal[o + WEIGHTS_PLANE2_OFFSET..],
        );
    }
    let min_ep1 = min_weight_cutoff(&ei1.ep, 0, VFloat4::splat(10.0));
    let min_ep2 = min_weight_cutoff(&ei2.ep, 0, VFloat4::splat(10.0));
    let err_max = VFloat4::splat(ERROR_CALC_DEFAULT);
    let err_mask = VInt4::lane_id().eq(VInt4::splat(plane2_component as i32));
    let min_wt_cutoff1 = hmin_s(select(min_ep1, err_max, err_mask));
    let min_wt_cutoff2 = hmin_s(select(err_max, min_ep2, err_mask));
    compute_angular_endpoints_2planes(bsd, max_weight_quant, tmpbuf);
    let start_2plane = bsd.block_mode_count_1plane_selected;
    let end_2plane = bsd.block_mode_count_1plane_2plane_selected;
    for i in start_2plane as usize..end_2plane as usize {
        let bm = &bsd.block_modes[i];
        if bm.quant_mode as usize > max_weight_quant {
            tmpbuf.qwt_errors[i] = 1e38;
            continue;
        }
        tmpbuf.qwt_bitcounts[i] = (109 - bm.weight_bits as i32) as i8;
        if tmpbuf.weight_high_value1[i] > 1.02 * min_wt_cutoff1 {
            tmpbuf.weight_high_value1[i] = 1.0;
        }
        if tmpbuf.weight_high_value2[i] > 1.02 * min_wt_cutoff2 {
            tmpbuf.weight_high_value2[i] = 1.0;
        }
        let dm = bm.decimation_mode as usize;
        let di = bsd.get_decimation_info(dm as u32);
        let mut uquantf = [0.0f32; BLOCK_MAX_WEIGHTS];
        let (p1, p2) = uquantf.split_at_mut(WEIGHTS_PLANE2_OFFSET);
        let (ideal, uq) = (BLOCK_MAX_WEIGHTS * dm, BLOCK_MAX_WEIGHTS * i);
        compute_quantized_weights_for_decimation(
            di,
            tmpbuf.weight_low_value1[i],
            tmpbuf.weight_high_value1[i],
            &tmpbuf.dec_weights_ideal[ideal..],
            p1,
            &mut tmpbuf.dec_weights_uquant[uq..],
            bm.get_weight_quant_mode(),
        );
        compute_quantized_weights_for_decimation(
            di,
            tmpbuf.weight_low_value2[i],
            tmpbuf.weight_high_value2[i],
            &tmpbuf.dec_weights_ideal[ideal + WEIGHTS_PLANE2_OFFSET..],
            p2,
            &mut tmpbuf.dec_weights_uquant[uq + WEIGHTS_PLANE2_OFFSET..],
            bm.get_weight_quant_mode(),
        );
        tmpbuf.qwt_errors[i] = compute_error_of_weight_set_2planes(&ei1, &ei2, di, p1, p2);
    }
    let epm = merge_endpoints(&ei1.ep, &ei2.ep, plane2_component);
    let pi = bsd.get_partition_info(1, 0);
    let mut cand = Candidates::ZERO;
    let candidate_count = compute_ideal_endpoint_formats(
        pi,
        blk,
        &epm,
        config.tune_candidate_limit,
        start_2plane,
        end_2plane,
        &mut cand,
        tmpbuf,
    );
    let best_in_scb = scb.errorval;
    let mut search = Search {
        best_in_mode: ERROR_CALC_DEFAULT,
        best_in_scb,
        threshold: tune_errorval_threshold,
        scb,
    };
    'candidates: for i in 0..candidate_count as usize {
        let qw_bm = &bsd.block_modes[cand.block_mode[i] as usize];
        let di = bsd.get_decimation_info(qw_bm.decimation_mode as u32);
        let mut rgbs_color = VFloat4::zero();
        let mut workscb = SymbolicCompressedBlock::default();
        let mut workep = epm;
        let src = BLOCK_MAX_WEIGHTS * cand.block_mode[i] as usize;
        let wc = di.weight_count as usize;
        workscb.weights[..wc].copy_from_slice(&tmpbuf.dec_weights_uquant[src..src + wc]);
        workscb.weights[WEIGHTS_PLANE2_OFFSET..WEIGHTS_PLANE2_OFFSET + wc].copy_from_slice(
            &tmpbuf.dec_weights_uquant
                [src + WEIGHTS_PLANE2_OFFSET..src + WEIGHTS_PLANE2_OFFSET + wc],
        );
        for l in 0..config.tune_refinement_limit {
            let (w1, w2) = workscb.weights.split_at(WEIGHTS_PLANE2_OFFSET);
            recompute_ideal_colors_2planes(
                blk,
                bsd,
                di,
                w1,
                w2,
                &mut workep,
                &mut rgbs_color,
                plane2_component as i32,
            );
            workscb.color_formats[0] = pack_color_endpoints(
                workep.endpt0[0],
                workep.endpt1[0],
                rgbs_color,
                cand.partition_format_specifiers[i][0],
                &mut workscb.color_values[0],
                cand.quant_level[i],
            );
            workscb.partition_count = 1;
            workscb.partition_index = 0;
            workscb.quant_mode = cand.quant_level[i];
            workscb.color_formats_matched = 0;
            workscb.block_mode = qw_bm.mode_index;
            workscb.plane2_component = plane2_component as i8;
            workscb.block_type = SYM_BTYPE_NONCONST;
            if l == 0 {
                let errorval = compute_symbolic_block_difference_2plane(config, bsd, &workscb, blk);
                match search.judge(
                    &mut workscb,
                    errorval,
                    config.tune_refinement_limit - l,
                    1.08,
                ) {
                    Verdict::Break => break,
                    Verdict::Stop => break 'candidates,
                    Verdict::Continue => {}
                }
            }
            let adjustments = realign(config.profile, bsd, di, blk, &mut workscb);
            let errorval = compute_symbolic_block_difference_2plane(config, bsd, &workscb, blk);
            match search.judge(
                &mut workscb,
                errorval,
                config.tune_refinement_limit - 1 - l,
                1.0,
            ) {
                Verdict::Break => break,
                Verdict::Stop => break 'candidates,
                Verdict::Continue => {}
            }
            if !adjustments {
                break;
            }
        }
    }
    search.best_in_mode
}

fn prepare_block_statistics(texels_per_block: usize, blk: &ImageBlock) -> f32 {
    let _prof = crate::prof::span(11);
    let (mut rs, mut gs, mut bs, mut a_s) = (0.0f32, 0.0f32, 0.0f32, 0.0f32);
    let (mut rr, mut gg, mut bb, mut aa) = (0.0f32, 0.0f32, 0.0f32, 0.0f32);
    let (mut rg, mut rb, mut ra, mut gb, mut ga, mut ba) =
        (0.0f32, 0.0f32, 0.0f32, 0.0f32, 0.0f32, 0.0f32);
    let mut weight_sum = 0.0f32;
    for i in 0..texels_per_block {
        let weight = hadd_s(blk.channel_weight) / 4.0;
        weight_sum += weight;
        let (r, g, b, a) = (blk.data_r[i], blk.data_g[i], blk.data_b[i], blk.data_a[i]);
        let rw = r * weight;
        rs += rw;
        rr += r * rw;
        rg += g * rw;
        rb += b * rw;
        ra += a * rw;
        let gw = g * weight;
        gs += gw;
        gg += g * gw;
        gb += b * gw;
        ga += a * gw;
        let bw = b * weight;
        bs += bw;
        bb += b * bw;
        ba += a * bw;
        let aw = a * weight;
        a_s += aw;
        aa += a * aw;
    }
    let rpt = 1.0 / astc::max(weight_sum, 1e-7);
    rr -= rs * (rs * rpt);
    rg -= gs * (rs * rpt);
    rb -= bs * (rs * rpt);
    ra -= a_s * (rs * rpt);
    gg -= gs * (gs * rpt);
    gb -= bs * (gs * rpt);
    ga -= a_s * (gs * rpt);
    bb -= bs * (bs * rpt);
    ba -= a_s * (bs * rpt);
    aa -= a_s * (a_s * rpt);
    let cov = |c: f32, v: f32| {
        let x = c * astc::rsqrt(v);
        if x.is_nan() { 1.0 } else { x }
    };
    let covs = [
        cov(rg, rr * gg),
        cov(rb, rr * bb),
        cov(ra, rr * aa),
        cov(gb, gg * bb),
        cov(ga, gg * aa),
        cov(ba, bb * aa),
    ];
    covs[1..]
        .iter()
        .fold(covs[0].abs(), |m, c| astc::min(m, c.abs()))
}

fn constant_u16(scb: &mut SymbolicCompressedBlock, blk: &ImageBlock) {
    scb.block_type = SYM_BTYPE_CONST_U16;
    let color_u16 = float_to_int_rtn(clamp(0.0, 1.0, blk.origin_texel) * 65535.0);
    for i in 0..4 {
        scb.set_constant_color(i, color_u16.lane(i));
    }
}

/// `compress_block` for the LDR profiles.
pub fn compress_block(
    config: &Config,
    bsd: &BlockSizeDescriptor,
    blk: &ImageBlock,
    pcb: &mut [u8; 16],
    tmpbuf: &mut CompressionWorkingBuffers,
) {
    let mut scb = SymbolicCompressedBlock::default();
    let block_is_l_scale = if blk.is_luminance() { 1.0 / 1.5 } else { 1.0 };
    let block_is_la_scale = if blk.is_luminancealpha() {
        1.0 / 1.05
    } else {
        1.0
    };
    let max_partitions = config.tune_partition_count_limit;
    let requested_partition_indices = [
        config.tune_2partition_index_limit,
        config.tune_3partition_index_limit,
        config.tune_4partition_index_limit,
    ];
    let requested_partition_trials = [
        config.tune_2partitioning_candidate_limit,
        config.tune_3partitioning_candidate_limit,
        config.tune_4partitioning_candidate_limit,
    ];
    if all(blk.data_min.eq(blk.data_max)) {
        scb.partition_count = 0;
        constant_u16(&mut scb, blk);
        symbolic_to_physical(bsd, &scb, pcb);
        return;
    }
    let error_weight_sum = hadd_s(blk.channel_weight) * bsd.texel_count as f32;
    let error_threshold =
        config.tune_db_limit * error_weight_sum * block_is_l_scale * block_is_la_scale;
    scb.errorval = ERROR_CALC_DEFAULT;
    scb.block_type = SYM_BTYPE_ERROR;
    let mut best_errorvals_for_pcount = [ERROR_CALC_DEFAULT; BLOCK_MAX_PARTITIONS];
    let exit_thresholds_for_pcount = [
        0.0,
        config.tune_2partition_early_out_limit_factor,
        config.tune_3partition_early_out_limit_factor,
        0.0,
    ];
    let errorval_mult = [1.0 / config.tune_mse_overshoot, 1.0];
    let errorval_overshoot = *ERRORVAL_OVERSHOOT.get_or_init(|| 1.0 / config.tune_mse_overshoot);
    let start_trial = if config.tune_search_mode0_enable >= TUNE_MIN_SEARCH_MODE0 && bsd.zdim == 1 {
        0
    } else {
        1
    };
    let mut quant_limit = QUANT_32;
    'tests: {
        for i in start_trial..2 {
            let errorval = compress_symbolic_block_for_partition_1plane(
                config,
                bsd,
                blk,
                i == 0,
                error_threshold * errorval_mult[i] * errorval_overshoot,
                1,
                0,
                &mut scb,
                tmpbuf,
                QUANT_32,
            );
            // An unset block mode is uninitialised memory upstream; keep the limit then.
            if let Some(&packed) = bsd.block_mode_packed_index.get(scb.block_mode as usize)
                && let Some(bm) = bsd.block_modes.get(packed as usize)
            {
                quant_limit = bm.get_weight_quant_mode();
            }
            best_errorvals_for_pcount[0] = astc::min(best_errorvals_for_pcount[0], errorval);
            if errorval < error_threshold * errorval_mult[i] {
                break 'tests;
            }
        }
        let lowest_correl = prepare_block_statistics(bsd.texel_count as usize, blk);
        let block_skip_two_plane = lowest_correl > config.tune_2plane_early_out_limit_correlation;
        for i in (0..BLOCK_MAX_COMPONENTS as i32).rev() {
            if block_skip_two_plane || (blk.grayscale && i != 3) || blk.is_constant_channel(i) {
                continue;
            }
            let errorval = compress_symbolic_block_for_partition_2planes(
                config,
                bsd,
                blk,
                error_threshold * errorval_overshoot,
                i as u32,
                &mut scb,
                tmpbuf,
                quant_limit,
            );
            if errorval > best_errorvals_for_pcount[0] * 1.85 {
                break;
            }
            if errorval < error_threshold {
                break 'tests;
            }
        }
        for partition_count in 2..=max_partitions {
            let pc = partition_count as usize;
            let mut partition_indices = [0u32; TUNE_MAX_PARTITIONING_CANDIDATES];
            let requested_indices = requested_partition_indices[pc - 2];
            let requested_trials = astc::min(requested_partition_trials[pc - 2], requested_indices);
            let actual_trials = find_best_partition_candidates(
                bsd,
                blk,
                partition_count,
                requested_indices,
                &mut partition_indices,
                requested_trials,
            );
            let best_error_in_prev = best_errorvals_for_pcount[pc - 2];
            for &index in &partition_indices[..actual_trials as usize] {
                let errorval = compress_symbolic_block_for_partition_1plane(
                    config,
                    bsd,
                    blk,
                    false,
                    error_threshold * errorval_overshoot,
                    partition_count,
                    index,
                    &mut scb,
                    tmpbuf,
                    quant_limit,
                );
                best_errorvals_for_pcount[pc - 1] =
                    astc::min(best_errorvals_for_pcount[pc - 1], errorval);
                let best_error = best_errorvals_for_pcount[pc - 1];
                if best_error > best_error_in_prev * (exit_thresholds_for_pcount[pc - 1] * 1.85) {
                    break 'tests;
                }
                if errorval < error_threshold {
                    break 'tests;
                }
            }
            let best_error = best_errorvals_for_pcount[pc - 1];
            if best_error > best_error_in_prev * exit_thresholds_for_pcount[pc - 1] {
                break 'tests;
            }
        }
    }
    if scb.block_type == SYM_BTYPE_ERROR {
        constant_u16(&mut scb, blk);
    }
    symbolic_to_physical(bsd, &scb, pcb);
}
