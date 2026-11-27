//! Endpoint format and quantization choice (`astcenc_pick_best_endpoint_format.cpp`), LDR only:
//! the HDR error model is left out, as `rgb_lns` and `alpha_lns` stay zero.

use crate::averages_and_directions::compute_avgs_and_dirs_3_comp_rgb;
use crate::internal::*;
use crate::tables::QUANT_MODE_TABLE;
use crate::vecmath::*;

type ErrorTable = [[f32; 4]; 21];
type FormatTable = [[u8; 4]; 21];

fn compute_error_squared_rgb_single_partition(
    pi: &PartitionInfo,
    partition_index: usize,
    blk: &ImageBlock,
    uncor_pline: &ProcessedLine,
    samec_pline: &ProcessedLine,
    rgbl_pline: &ProcessedLine,
    l_pline: &ProcessedLine,
) -> [f32; 5] {
    let ews = blk.channel_weight;
    let texel_count = pi.partition_texel_count[partition_index] as usize;
    let texel_indexes = &pi.texels_of_partition[partition_index];
    let default_a = VFloat4::splat(blk.get_default_alpha());
    let lanes = |v: VFloat4| {
        [
            VFloat4::splat(v.lane(0)),
            VFloat4::splat(v.lane(1)),
            VFloat4::splat(v.lane(2)),
        ]
    };
    let (ubs, uam) = (lanes(uncor_pline.bs), lanes(uncor_pline.amod));
    let sbs = lanes(samec_pline.bs);
    let (rbs, ram) = (lanes(rgbl_pline.bs), lanes(rgbl_pline.amod));
    let lbs = lanes(l_pline.bs);
    let (mut a_drop_errv, mut uncor_errv, mut samec_errv, mut rgbl_errv, mut l_errv) = (
        VFloat4::zero(),
        VFloat4::zero(),
        VFloat4::zero(),
        VFloat4::zero(),
        VFloat4::zero(),
    );
    let mut lane_ids = VInt4::lane_id();
    let mut i = 0;
    while i < texel_count {
        let tix = &texel_indexes[i..];
        let mask = lane_ids.lt(VInt4::splat(texel_count as i32));
        lane_ids += VInt4::splat(SIMD_WIDTH as i32);
        let data_a = gatherf_u8(&blk.data_a, tix);
        let alpha_diff = data_a - default_a;
        haccumulate_m(&mut a_drop_errv, alpha_diff * alpha_diff, mask);
        let d = [
            gatherf_u8(&blk.data_r, tix),
            gatherf_u8(&blk.data_g, tix),
            gatherf_u8(&blk.data_b, tix),
        ];
        let err = |dist: [VFloat4; 3]| {
            dist[0] * dist[0] * ews.lane(0)
                + dist[1] * dist[1] * ews.lane(1)
                + dist[2] * dist[2] * ews.lane(2)
        };
        let param = d[0] * ubs[0] + d[1] * ubs[1] + d[2] * ubs[2];
        haccumulate_m(
            &mut uncor_errv,
            err(core::array::from_fn(|k| (uam[k] + param * ubs[k]) - d[k])),
            mask,
        );
        let param = d[0] * sbs[0] + d[1] * sbs[1] + d[2] * sbs[2];
        haccumulate_m(
            &mut samec_errv,
            err(core::array::from_fn(|k| (param * sbs[k]) - d[k])),
            mask,
        );
        let param = d[0] * rbs[0] + d[1] * rbs[1] + d[2] * rbs[2];
        haccumulate_m(
            &mut rgbl_errv,
            err(core::array::from_fn(|k| (ram[k] + param * rbs[k]) - d[k])),
            mask,
        );
        let param = d[0] * lbs[0] + d[1] * lbs[1] + d[2] * lbs[2];
        haccumulate_m(
            &mut l_errv,
            err(core::array::from_fn(|k| (param * lbs[k]) - d[k])),
            mask,
        );
        i += SIMD_WIDTH;
    }
    [
        hadd_s(a_drop_errv) * ews.lane(3),
        hadd_s(uncor_errv),
        hadd_s(samec_errv),
        hadd_s(rgbl_errv),
        hadd_s(l_errv),
    ]
}

fn compute_encoding_choice_errors(
    blk: &ImageBlock,
    pi: &PartitionInfo,
    ep: &Endpoints,
    eci: &mut [EncodingChoiceErrors; 4],
) {
    let mut pms = [PartitionMetrics::default(); 4];
    compute_avgs_and_dirs_3_comp_rgb(pi, blk, &mut pms);
    for i in 0..pi.partition_count as usize {
        let pm = pms[i];
        let uncor_b = normalize_safe(pm.dir, unit3());
        let samec_b = normalize_safe(pm.avg, unit3());
        let luma_b = unit3();
        let uncor = ProcessedLine {
            amod: pm.avg - uncor_b * dot3(pm.avg, uncor_b),
            bs: uncor_b,
        };
        let samec = ProcessedLine {
            amod: VFloat4::zero(),
            bs: samec_b,
        };
        let luma = ProcessedLine {
            amod: pm.avg - luma_b * dot3(pm.avg, luma_b),
            bs: luma_b,
        };
        let lum = ProcessedLine {
            amod: VFloat4::zero(),
            bs: unit3(),
        };
        let [
            alpha_drop_error,
            uncorr_rgb_error,
            samechroma_rgb_error,
            rgb_luma_error,
            luminance_rgb_error,
        ] = compute_error_squared_rgb_single_partition(pi, i, blk, &uncor, &samec, &luma, &lum);
        let endpt_diff = abs(ep.endpt1[i] - ep.endpt0[i]);
        let endpt_can_offset = endpt_diff.lt(VFloat4::splat(0.12 * 65535.0));
        eci[i].rgb_scale_error = (samechroma_rgb_error - uncorr_rgb_error) * 0.7;
        eci[i].rgb_luma_error = (rgb_luma_error - uncorr_rgb_error) * 1.5;
        eci[i].luminance_error = (luminance_rgb_error - uncorr_rgb_error) * 3.0;
        eci[i].alpha_drop_error = alpha_drop_error * 3.0;
        eci[i].can_offset_encode = (mask(endpt_can_offset) & 0x7) == 0x7;
        eci[i].can_blue_contract = !blk.is_luminance();
    }
}

const BQE: f32 = 65536.0 * 65536.0 / 18.0;
const BASELINE_QUANT_ERROR: [f32; 17] = [
    BQE / 25.0,
    BQE / 49.0,
    BQE / 81.0,
    BQE / 121.0,
    BQE / 225.0,
    BQE / 361.0,
    BQE / 529.0,
    BQE / 961.0,
    BQE / 1521.0,
    BQE / 2209.0,
    BQE / 3969.0,
    BQE / 6241.0,
    BQE / 9025.0,
    BQE / 16129.0,
    BQE / 25281.0,
    BQE / 36481.0,
    BQE / 65025.0,
];

fn compute_color_error_for_every_integer_count_and_quant_level(
    partition_index: usize,
    pi: &PartitionInfo,
    eci: &EncodingChoiceErrors,
    ep: &Endpoints,
    error_weight: VFloat4,
    best_error: &mut ErrorTable,
    format_of_choice: &mut FormatTable,
) {
    let partition_size = pi.partition_texel_count[partition_index] as f32;
    let ep0 = ep.endpt0[partition_index];
    let ep1 = ep.endpt1[partition_index];
    let error_weight_rgbsum = hadd_rgb_s(error_weight);
    let offset = VFloat4::splat(65535.0);
    let ep0_range_error_high = max_s(ep0 - offset, 0.0);
    let ep1_range_error_high = max_s(ep1 - offset, 0.0);
    let ep0_range_error_low = min_s(ep0, 0.0);
    let ep1_range_error_low = min_s(ep1, 0.0);
    let sum_range_error = (ep0_range_error_low * ep0_range_error_low)
        + (ep1_range_error_low * ep1_range_error_low)
        + (ep0_range_error_high * ep0_range_error_high)
        + (ep1_range_error_high * ep1_range_error_high);
    let rgb_range_error = dot3_s(sum_range_error, error_weight) * 0.5 * partition_size;
    let alpha_range_error = sum_range_error.lane(3) * error_weight.lane(3) * 0.5 * partition_size;
    for i in QUANT_2..QUANT_6 {
        best_error[i] = [ERROR_CALC_DEFAULT; 4];
        format_of_choice[i] = [FMT_LUMINANCE, FMT_RGB_SCALE, FMT_RGB, FMT_RGBA];
    }
    let base_quant_error_rgb = error_weight_rgbsum * partition_size;
    let base_quant_error_a = error_weight.lane(3) * partition_size;
    let base_quant_error_rgba = base_quant_error_rgb + base_quant_error_a;
    let error_scale_bc_rgba = if eci.can_blue_contract { 0.625 } else { 1.0 };
    let mut error_scale_oe_rgba = if eci.can_offset_encode { 0.5 } else { 1.0 };
    let error_scale_bc_rgb = if eci.can_blue_contract { 0.5 } else { 1.0 };
    let mut error_scale_oe_rgb = if eci.can_offset_encode { 0.25 } else { 1.0 };
    for i in QUANT_6..=QUANT_256 {
        if i >= QUANT_192 {
            error_scale_oe_rgba = 1.0;
            error_scale_oe_rgb = 1.0;
        }
        let base_quant_error = BASELINE_QUANT_ERROR[i - QUANT_6];
        let quant_error_rgb = base_quant_error_rgb * base_quant_error;
        let quant_error_rgba = base_quant_error_rgba * base_quant_error;
        best_error[i][3] = quant_error_rgba * error_scale_bc_rgba * error_scale_oe_rgba
            + rgb_range_error
            + alpha_range_error;
        format_of_choice[i][3] = FMT_RGBA;
        let full_ldr_rgb_error = quant_error_rgb * error_scale_bc_rgb * error_scale_oe_rgb
            + rgb_range_error
            + eci.alpha_drop_error;
        let rgbs_alpha_error =
            quant_error_rgba + eci.rgb_scale_error + rgb_range_error + alpha_range_error;
        if rgbs_alpha_error < full_ldr_rgb_error {
            best_error[i][2] = rgbs_alpha_error;
            format_of_choice[i][2] = FMT_RGB_SCALE_ALPHA;
        } else {
            best_error[i][2] = full_ldr_rgb_error;
            format_of_choice[i][2] = FMT_RGB;
        }
        let ldr_rgbs_error =
            quant_error_rgb + rgb_range_error + eci.alpha_drop_error + eci.rgb_scale_error;
        let lum_alpha_error =
            quant_error_rgba + rgb_range_error + alpha_range_error + eci.luminance_error;
        if ldr_rgbs_error < lum_alpha_error {
            best_error[i][1] = ldr_rgbs_error;
            format_of_choice[i][1] = FMT_RGB_SCALE;
        } else {
            best_error[i][1] = lum_alpha_error;
            format_of_choice[i][1] = FMT_LUMINANCE_ALPHA;
        }
        best_error[i][0] =
            quant_error_rgb + rgb_range_error + eci.alpha_drop_error + eci.luminance_error;
        format_of_choice[i][0] = FMT_LUMINANCE;
    }
}

#[inline]
fn qmt(integer_count: usize, bits: usize) -> i32 {
    QUANT_MODE_TABLE[integer_count][bits] as i32
}

fn one_partition_find_best_combination_for_bitcount(
    best_combined_error: &ErrorTable,
    best_combined_format: &FormatTable,
    bits_available: usize,
    best_quant_level: &mut u8,
    best_format: &mut u8,
) -> f32 {
    let mut best_integer_count = 0;
    let mut best_integer_count_error = ERROR_CALC_DEFAULT;
    for integer_count in 1..=4 {
        let quant_level = qmt(integer_count, bits_available);
        if quant_level < QUANT_6 as i32 {
            continue;
        }
        let integer_count_error = best_combined_error[quant_level as usize][integer_count - 1];
        if integer_count_error < best_integer_count_error {
            best_integer_count_error = integer_count_error;
            best_integer_count = integer_count - 1;
        }
    }
    let ql = qmt(best_integer_count + 1, bits_available);
    *best_quant_level = ql as u8;
    *best_format = FMT_LUMINANCE;
    if ql >= QUANT_6 as i32 {
        *best_format = best_combined_format[ql as usize][best_integer_count];
    }
    best_integer_count_error
}

/// The best format per partition for every quant level and total integer count, for `n`
/// partitions (the C++ `two/three/four_partitions_find_best_combination_for_every_...`): every
/// tuple of per-partition counts no more than one apart, in the C++ loop order.
fn combine(
    n: usize,
    best_error: &[ErrorTable; 4],
    best_format: &[FormatTable; 4],
) -> (Vec<[f32; 13]>, Vec<[[u8; 4]; 13]>) {
    let mut err = vec![[ERROR_CALC_DEFAULT; 13]; 21];
    let mut fmt = vec![[[0u8; 4]; 13]; 21];
    for quant in QUANT_6..=QUANT_256 {
        for t in 0..4usize.pow(n as u32) {
            let idx: [usize; 4] = core::array::from_fn(|p| {
                if p < n {
                    (t / 4usize.pow((n - 1 - p) as u32)) % 4
                } else {
                    0
                }
            });
            let ks = &idx[..n];
            let (lo, hi) = (
                ks.iter().min().copied().unwrap_or(0),
                ks.iter().max().copied().unwrap_or(0),
            );
            if hi - lo > 1 {
                continue;
            }
            let intcnt: usize = ks.iter().sum();
            let mut sum = best_error[0][quant][ks[0]];
            for p in 1..n {
                sum += best_error[p][quant][ks[p]];
            }
            let errorterm = astc::min(sum, 1e10);
            if errorterm <= err[quant][intcnt] {
                err[quant][intcnt] = errorterm;
                for p in 0..n {
                    fmt[quant][intcnt][p] = best_format[p][quant][ks[p]];
                }
            }
        }
    }
    (err, fmt)
}

/// `two/three/four_partitions_find_best_combination_for_bitcount`.
fn n_partitions_find_best_combination_for_bitcount(
    n: usize,
    best_combined_error: &[[f32; 13]],
    best_combined_format: &[[[u8; 4]; 13]],
    bits_available: usize,
    best_quant_level: &mut u8,
    best_quant_level_mod: &mut u8,
    best_formats: &mut [u8; 4],
) -> f32 {
    let (last, mod_offset) = match n {
        2 => (8, 2),
        3 => (9, 5),
        _ => (9, 8),
    };
    let mut best_integer_count = 0;
    let mut best_integer_count_error = ERROR_CALC_DEFAULT;
    for integer_count in n..=last {
        let quant_level = qmt(integer_count, bits_available);
        if quant_level < QUANT_6 as i32 {
            break;
        }
        let integer_count_error = best_combined_error[quant_level as usize][integer_count - n];
        if integer_count_error < best_integer_count_error {
            best_integer_count_error = integer_count_error;
            best_integer_count = integer_count;
        }
    }
    let ql = qmt(best_integer_count, bits_available);
    let ql_mod = qmt(best_integer_count, bits_available + mod_offset);
    *best_quant_level = ql as u8;
    *best_quant_level_mod = ql_mod as u8;
    for i in 0..n {
        best_formats[i] = if ql >= QUANT_6 as i32 {
            best_combined_format[ql as usize][best_integer_count - n][i]
        } else {
            FMT_LUMINANCE
        };
    }
    best_integer_count_error
}

/// The chosen candidates: block mode, quant level, quant level for the mod, and formats.
pub struct Candidates {
    pub block_mode: [i32; TUNE_MAX_TRIAL_CANDIDATES],
    pub quant_level: [usize; TUNE_MAX_TRIAL_CANDIDATES],
    pub quant_level_mod: [usize; TUNE_MAX_TRIAL_CANDIDATES],
    pub partition_format_specifiers: [[u8; BLOCK_MAX_PARTITIONS]; TUNE_MAX_TRIAL_CANDIDATES],
}

impl Candidates {
    pub const ZERO: Self = Self {
        block_mode: [0; TUNE_MAX_TRIAL_CANDIDATES],
        quant_level: [0; TUNE_MAX_TRIAL_CANDIDATES],
        quant_level_mod: [0; TUNE_MAX_TRIAL_CANDIDATES],
        partition_format_specifiers: [[0; 4]; TUNE_MAX_TRIAL_CANDIDATES],
    };
}

/// `compute_ideal_endpoint_formats`, reading `qwt_bitcounts` and `qwt_errors` from `tmpbuf`.
#[expect(clippy::too_many_arguments, reason = "mirrors the C++ signature")]
pub fn compute_ideal_endpoint_formats(
    pi: &PartitionInfo,
    blk: &ImageBlock,
    ep: &Endpoints,
    tune_candidate_limit: u32,
    start_block_mode: u32,
    end_block_mode: u32,
    out: &mut Candidates,
    tmpbuf: &mut CompressionWorkingBuffers,
) -> u32 {
    let _prof = crate::prof::span(5);
    let partition_count = pi.partition_count as usize;
    let mut eci = [EncodingChoiceErrors::default(); 4];
    compute_encoding_choice_errors(blk, pi, ep, &mut eci);
    let mut best_error = [[[0.0f32; 4]; 21]; 4];
    let mut format_of_choice = [[[0u8; 4]; 21]; 4];
    for i in 0..partition_count {
        compute_color_error_for_every_integer_count_and_quant_level(
            i,
            pi,
            &eci[i],
            ep,
            blk.channel_weight,
            &mut best_error[i],
            &mut format_of_choice[i],
        );
    }
    let t = tmpbuf;
    let (start, end) = (start_block_mode as usize, end_block_mode as usize);
    for packed in [
        round_down_to_simd_multiple_vla(start_block_mode),
        round_down_to_simd_multiple_vla(end_block_mode - 1),
    ] {
        let p = packed as usize;
        VFloat4::splat(ERROR_CALC_DEFAULT).store(&mut t.errors_of_best_combination[p..]);
        t.best_quant_levels[p..p + 4].fill(0);
        t.best_quant_levels_mod[p..p + 4].fill(0);
    }
    let mut error_of_best_combination = ERROR_CALC_DEFAULT;
    let mut index_of_best_combination = -1i32;
    let combined =
        (partition_count > 1).then(|| combine(partition_count, &best_error, &format_of_choice));
    for i in start..end {
        if t.qwt_errors[i] >= ERROR_CALC_DEFAULT {
            t.errors_of_best_combination[i] = ERROR_CALC_DEFAULT;
            continue;
        }
        let bits = t.qwt_bitcounts[i] as usize;
        let error_of_best = match &combined {
            None => {
                let e = one_partition_find_best_combination_for_bitcount(
                    &best_error[0],
                    &format_of_choice[0],
                    bits,
                    &mut t.best_quant_levels[i],
                    &mut t.best_ep_formats[i][0],
                );
                t.best_quant_levels_mod[i] = t.best_quant_levels[i];
                e
            }
            Some((err, fmt)) => n_partitions_find_best_combination_for_bitcount(
                partition_count,
                err,
                fmt,
                bits,
                &mut t.best_quant_levels[i],
                &mut t.best_quant_levels_mod[i],
                &mut t.best_ep_formats[i],
            ),
        };
        let total_error = error_of_best + t.qwt_errors[i];
        t.errors_of_best_combination[i] = total_error;
        if total_error < error_of_best_combination {
            error_of_best_combination = total_error;
            index_of_best_combination = i as i32;
        }
    }
    let mut best_error_weights = [0i32; TUNE_MAX_TRIAL_CANDIDATES];
    best_error_weights[0] = index_of_best_combination;
    if index_of_best_combination >= 0 {
        t.errors_of_best_combination[index_of_best_combination as usize] = ERROR_CALC_DEFAULT;
    }
    let start = round_down_to_simd_multiple_vla(start_block_mode) as usize;
    for i in 1..tune_candidate_limit as usize {
        let mut vbest_error_index = VInt4::splat(-1);
        let mut vbest_ep_error = VFloat4::splat(ERROR_CALC_DEFAULT);
        let mut lane_ids = VInt4::lane_id() + VInt4::splat(start as i32);
        let mut j = start;
        while j < end {
            let err = VFloat4::load(&t.errors_of_best_combination[j..]);
            let m = err.lt(vbest_ep_error);
            vbest_ep_error = select(vbest_ep_error, err, m);
            vbest_error_index = select_i(vbest_error_index, lane_ids, m);
            lane_ids += VInt4::splat(SIMD_WIDTH as i32);
            j += SIMD_WIDTH;
        }
        let lanes_min_error = vbest_ep_error.eq(hmin(vbest_ep_error));
        vbest_error_index = select_i(
            VInt4::splat(0x7FFF_FFFF),
            vbest_error_index,
            lanes_min_error,
        );
        let best_error_index = hmin_s_i(vbest_error_index);
        best_error_weights[i] = best_error_index;
        if best_error_index >= 0 {
            t.errors_of_best_combination[best_error_index as usize] = ERROR_CALC_DEFAULT;
        } else {
            break;
        }
    }
    for i in 0..tune_candidate_limit as usize {
        if best_error_weights[i] < 0 {
            return i as u32;
        }
        let w = best_error_weights[i] as usize;
        out.block_mode[i] = best_error_weights[i];
        out.quant_level[i] = t.best_quant_levels[w] as usize;
        out.quant_level_mod[i] = t.best_quant_levels_mod[w] as usize;
        out.partition_format_specifiers[i][..partition_count]
            .copy_from_slice(&t.best_ep_formats[w][..partition_count]);
    }
    tune_candidate_limit
}
