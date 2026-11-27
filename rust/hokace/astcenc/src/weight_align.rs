//! Angular weight-range search (`astcenc_weight_align.cpp`). The sin and cos tables come from
//! `data/sincos.bin`, written by `tables_dump.cpp` with the scalar build's own `sinf` and `cosf`,
//! so no platform's libm enters the encoding.

use std::sync::OnceLock;

use crate::internal::*;
use crate::vecmath::*;

const ANGULAR_STEPS: usize = 32;
const SINCOS_STEPS: usize = 64;
const STEPS_FOR_QUANT_LEVEL: [u8; 12] = [2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24, 32];

type Table = [[f32; ANGULAR_STEPS]; SINCOS_STEPS];

static SINCOS_BIN: &[u8] = include_bytes!("../data/sincos.bin");

/// `prepare_angular_tables`: (sin, cos), each indexed `[sample][angular step]`.
fn tables() -> &'static (Table, Table) {
    static TABLES: OnceLock<Box<(Table, Table)>> = OnceLock::new();
    TABLES.get_or_init(|| {
        let mut t = Box::new((
            [[0.0; ANGULAR_STEPS]; SINCOS_STEPS],
            [[0.0; ANGULAR_STEPS]; SINCOS_STEPS],
        ));
        let mut v = SINCOS_BIN
            .as_chunks::<4>()
            .0
            .iter()
            .map(|b| f32::from_le_bytes([b[0], b[1], b[2], b[3]]));
        for table in [&mut t.0, &mut t.1] {
            for row in table.iter_mut() {
                for x in row.iter_mut() {
                    *x = v.next().unwrap_or(0.0);
                }
            }
        }
        t
    })
}

fn compute_angular_offsets(
    weight_count: usize,
    dec_weight_ideal_value: &[f32],
    max_angular_steps: usize,
    offsets: &mut [f32],
) {
    let (sin_table, cos_table) = tables();
    let mut isamplev = [0i32; BLOCK_MAX_WEIGHTS];
    let mut i = 0;
    while i < weight_count {
        let ideal_weight = clampzo(VFloat4::load(&dec_weight_ideal_value[i..]));
        let sample = ideal_weight * (SINCOS_STEPS as f32 - 1.0);
        float_to_int_rtn(sample).store(&mut isamplev[i..]);
        i += SIMD_WIDTH;
    }
    let mult = VFloat4::splat(1.0 / (2.0 * PI));
    let mut i = 0;
    while i < max_angular_steps {
        let mut anglesum_x = VFloat4::zero();
        let mut anglesum_y = VFloat4::zero();
        for &isample in &isamplev[..weight_count] {
            let s = isample as usize;
            anglesum_x += VFloat4::load(&cos_table[s][i..]);
            anglesum_y += VFloat4::load(&sin_table[s][i..]);
        }
        let angle = atan2(anglesum_y, anglesum_x);
        (angle * mult).store(&mut offsets[i..]);
        i += SIMD_WIDTH;
    }
}

struct LowHigh {
    lowest_weight: [f32; ANGULAR_STEPS],
    weight_span: [i32; ANGULAR_STEPS],
    error: [f32; ANGULAR_STEPS],
    cut_low_weight_error: [f32; ANGULAR_STEPS],
    cut_high_weight_error: [f32; ANGULAR_STEPS],
}

fn compute_lowest_and_highest_weight(
    weight_count: usize,
    dec_weight_ideal_value: &[f32],
    max_angular_steps: usize,
    max_quant_steps: u32,
    offsets: &[f32],
    out: &mut LowHigh,
) {
    let mut rcp_stepsize = int_to_float(VInt4::lane_id()) + VFloat4::splat(1.0);
    let mut sp = 0;
    while sp < max_angular_steps {
        let mut minidx = VFloat4::splat(128.0);
        let mut maxidx = VFloat4::splat(-128.0);
        let mut errval = VFloat4::zero();
        let mut cut_low_weight_err = VFloat4::zero();
        let mut cut_high_weight_err = VFloat4::zero();
        let offset = VFloat4::load(&offsets[sp..]);
        for &w in &dec_weight_ideal_value[..weight_count] {
            let sval = VFloat4::splat(w) * rcp_stepsize - offset;
            let svalrte = round(sval);
            let diff = sval - svalrte;
            errval += diff * diff;
            let mask = svalrte.lt(minidx);
            minidx = select(minidx, svalrte, mask);
            cut_low_weight_err = select(cut_low_weight_err, VFloat4::zero(), mask);
            let mask = svalrte.eq(minidx);
            let accum = cut_low_weight_err + VFloat4::splat(1.0) - VFloat4::splat(2.0) * diff;
            cut_low_weight_err = select(cut_low_weight_err, accum, mask);
            let mask = svalrte.gt(maxidx);
            maxidx = select(maxidx, svalrte, mask);
            cut_high_weight_err = select(cut_high_weight_err, VFloat4::zero(), mask);
            let mask = svalrte.eq(maxidx);
            let accum = cut_high_weight_err + VFloat4::splat(1.0) + VFloat4::splat(2.0) * diff;
            cut_high_weight_err = select(cut_high_weight_err, accum, mask);
        }
        let mut span = float_to_int(maxidx - minidx + VFloat4::splat(1.0));
        span = mini(span, VInt4::splat(max_quant_steps as i32 + 3));
        span = maxi(span, VInt4::splat(2));
        minidx.store(&mut out.lowest_weight[sp..]);
        span.store(&mut out.weight_span[sp..]);
        let ssize = 1.0 / rcp_stepsize;
        let errscale = ssize * ssize;
        (errval * errscale).store(&mut out.error[sp..]);
        (cut_low_weight_err * errscale).store(&mut out.cut_low_weight_error[sp..]);
        (cut_high_weight_err * errscale).store(&mut out.cut_high_weight_error[sp..]);
        rcp_stepsize += VFloat4::splat(SIMD_WIDTH as f32);
        sp += SIMD_WIDTH;
    }
}

fn compute_angular_endpoints_for_quant_levels(
    weight_count: usize,
    dec_weight_ideal_value: &[f32],
    max_quant_level: usize,
    low_value: &mut [f32; TUNE_MAX_ANGULAR_QUANT + 1],
    high_value: &mut [f32; TUNE_MAX_ANGULAR_QUANT + 1],
) {
    let max_quant_steps = STEPS_FOR_QUANT_LEVEL[max_quant_level] as u32;
    let max_angular_steps = STEPS_FOR_QUANT_LEVEL[max_quant_level] as usize;
    let mut angular_offsets = [0.0f32; ANGULAR_STEPS];
    compute_angular_offsets(
        weight_count,
        dec_weight_ideal_value,
        max_angular_steps,
        &mut angular_offsets,
    );
    let mut lh = LowHigh {
        lowest_weight: [0.0; ANGULAR_STEPS],
        weight_span: [0; ANGULAR_STEPS],
        error: [0.0; ANGULAR_STEPS],
        cut_low_weight_error: [0.0; ANGULAR_STEPS],
        cut_high_weight_error: [0.0; ANGULAR_STEPS],
    };
    compute_lowest_and_highest_weight(
        weight_count,
        dec_weight_ideal_value,
        max_angular_steps,
        max_quant_steps,
        &angular_offsets,
        &mut lh,
    );
    let mut best_results = [VFloat4::zero(); 36];
    for r in &mut best_results[..max_quant_steps as usize + 4] {
        *r = VFloat4::new(ERROR_CALC_DEFAULT, -1.0, 0.0, 0.0);
    }
    for i in 0..max_angular_steps {
        let i_flt = i as f32;
        let idx_span = lh.weight_span[i] as usize;
        let error = lh.error[i];
        let error_cut_low = error + lh.cut_low_weight_error[i];
        let error_cut_high = error + lh.cut_high_weight_error[i];
        let error_cut_low_high = error + lh.cut_low_weight_error[i] + lh.cut_high_weight_error[i];
        let better = |best: VFloat4, e: f32| VFloat4::splat(best.lane(0)).gt(VFloat4::splat(e));

        let best_result = best_results[idx_span];
        let new_result = VFloat4::new(error, i_flt, 0.0, 0.0);
        best_results[idx_span] = select(best_result, new_result, better(best_result, error));

        let mut best_result = best_results[idx_span - 1];
        let new_result = VFloat4::new(error_cut_low, i_flt, 1.0, 0.0);
        best_result = select(best_result, new_result, better(best_result, error_cut_low));
        let new_result = VFloat4::new(error_cut_high, i_flt, 0.0, 0.0);
        best_results[idx_span - 1] =
            select(best_result, new_result, better(best_result, error_cut_high));

        let best_result = best_results[idx_span - 2];
        let new_result = VFloat4::new(error_cut_low_high, i_flt, 1.0, 0.0);
        best_results[idx_span - 2] = select(
            best_result,
            new_result,
            better(best_result, error_cut_low_high),
        );
    }
    for i in 0..=max_quant_level {
        let q = STEPS_FOR_QUANT_LEVEL[i] as usize;
        let bsi = astc::max(0, f2i(best_results[q].lane(1))) as usize;
        let lwi = lh.lowest_weight[bsi] + best_results[q].lane(2);
        let hwi = lwi + q as f32 - 1.0;
        let stepsize = 1.0 / (1.0 + bsi as f32);
        low_value[i] = (angular_offsets[bsi] + lwi) * stepsize;
        high_value[i] = (angular_offsets[bsi] + hwi) * stepsize;
    }
}

fn max_precision(maxprec: i8, max_weight_quant: usize) -> usize {
    // The C++ compares as unsigned: a negative `maxprec` (no mode) becomes the largest value.
    let mut p = maxprec as i32 as u32 as usize;
    if p > TUNE_MAX_ANGULAR_QUANT {
        p = TUNE_MAX_ANGULAR_QUANT;
    }
    if p > max_weight_quant {
        p = max_weight_quant;
    }
    p
}

pub fn compute_angular_endpoints_1plane(
    only_always: bool,
    bsd: &BlockSizeDescriptor,
    max_weight_quant: usize,
    tmpbuf: &mut CompressionWorkingBuffers,
) {
    let _prof = crate::prof::span(2);
    let max_decimation_modes = if only_always {
        bsd.decimation_mode_count_always
    } else {
        bsd.decimation_mode_count_selected
    } as usize;
    for i in 0..max_decimation_modes {
        let dm = &bsd.decimation_modes[i];
        if !dm.is_ref_1plane(max_weight_quant) {
            continue;
        }
        let weight_count = bsd.get_decimation_info(i as u32).weight_count as usize;
        let p = max_precision(dm.maxprec_1plane, max_weight_quant);
        compute_angular_endpoints_for_quant_levels(
            weight_count,
            &tmpbuf.dec_weights_ideal[i * BLOCK_MAX_WEIGHTS..],
            p,
            &mut tmpbuf.weight_low_values1[i],
            &mut tmpbuf.weight_high_values1[i],
        );
    }
    let max_block_modes = if only_always {
        bsd.block_mode_count_1plane_always
    } else {
        bsd.block_mode_count_1plane_selected
    } as usize;
    for i in 0..max_block_modes {
        let bm = &bsd.block_modes[i];
        let quant_mode = bm.quant_mode as usize;
        let decim_mode = bm.decimation_mode as usize;
        if quant_mode <= TUNE_MAX_ANGULAR_QUANT {
            tmpbuf.weight_low_value1[i] = tmpbuf.weight_low_values1[decim_mode][quant_mode];
            tmpbuf.weight_high_value1[i] = tmpbuf.weight_high_values1[decim_mode][quant_mode];
        } else {
            tmpbuf.weight_low_value1[i] = 0.0;
            tmpbuf.weight_high_value1[i] = 1.0;
        }
    }
}

pub fn compute_angular_endpoints_2planes(
    bsd: &BlockSizeDescriptor,
    max_weight_quant: usize,
    tmpbuf: &mut CompressionWorkingBuffers,
) {
    let _prof = crate::prof::span(2);
    for i in 0..bsd.decimation_mode_count_selected as usize {
        let dm = &bsd.decimation_modes[i];
        if !dm.is_ref_2plane(max_weight_quant) {
            continue;
        }
        let weight_count = bsd.get_decimation_info(i as u32).weight_count as usize;
        let p = max_precision(dm.maxprec_2planes, max_weight_quant);
        let base = i * BLOCK_MAX_WEIGHTS;
        compute_angular_endpoints_for_quant_levels(
            weight_count,
            &tmpbuf.dec_weights_ideal[base..],
            p,
            &mut tmpbuf.weight_low_values1[i],
            &mut tmpbuf.weight_high_values1[i],
        );
        compute_angular_endpoints_for_quant_levels(
            weight_count,
            &tmpbuf.dec_weights_ideal[base + WEIGHTS_PLANE2_OFFSET..],
            p,
            &mut tmpbuf.weight_low_values2[i],
            &mut tmpbuf.weight_high_values2[i],
        );
    }
    let start = bsd.block_mode_count_1plane_selected as usize;
    let end = bsd.block_mode_count_1plane_2plane_selected as usize;
    for i in start..end {
        let bm = &bsd.block_modes[i];
        let quant_mode = bm.quant_mode as usize;
        let decim_mode = bm.decimation_mode as usize;
        if quant_mode <= TUNE_MAX_ANGULAR_QUANT {
            tmpbuf.weight_low_value1[i] = tmpbuf.weight_low_values1[decim_mode][quant_mode];
            tmpbuf.weight_high_value1[i] = tmpbuf.weight_high_values1[decim_mode][quant_mode];
            tmpbuf.weight_low_value2[i] = tmpbuf.weight_low_values2[decim_mode][quant_mode];
            tmpbuf.weight_high_value2[i] = tmpbuf.weight_high_values2[decim_mode][quant_mode];
        } else {
            tmpbuf.weight_low_value1[i] = 0.0;
            tmpbuf.weight_high_value1[i] = 1.0;
            tmpbuf.weight_low_value2[i] = 0.0;
            tmpbuf.weight_high_value2[i] = 1.0;
        }
    }
}
