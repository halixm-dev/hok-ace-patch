//! Partition averages, principal directions and line errors (`astcenc_averages_and_directions.cpp`).

use crate::internal::*;
use crate::vecmath::*;

/// Per-partition channel sums over the first `parts` partitions, as the C++ loops accumulate them
/// (masked lanes, four lanes at a time, summed with the invariant `hadd_s`).
fn partition_sums(
    pi: &PartitionInfo,
    blk: &ImageBlock,
    parts: usize,
    channels: usize,
) -> [[f32; 4]; 3] {
    let texel_count = blk.texel_count as usize;
    let mut acc = [[VFloat4::zero(); 4]; 3];
    let mut lane_id = VInt4::lane_id();
    let mut i = 0;
    while i < texel_count {
        let texel_partition = VInt4::from_u8(&pi.partition_of_texel[i..]);
        let lane_mask = lane_id.lt(VInt4::splat(texel_count as i32));
        lane_id += VInt4::splat(4);
        let masks: [VMask4; 3] =
            core::array::from_fn(|p| lane_mask & texel_partition.eq(VInt4::splat(p as i32)));
        for c in 0..channels {
            let data = VFloat4::load(&blk.channel(c)[i..]);
            for p in 0..parts {
                haccumulate_m(&mut acc[p][c], data, masks[p]);
            }
        }
        i += 4;
    }
    let mut out = [[0.0; 4]; 3];
    for p in 0..parts {
        for c in 0..channels {
            out[p][c] = hadd_s(acc[p][c]);
        }
    }
    out
}

fn compute_partition_averages(
    pi: &PartitionInfo,
    blk: &ImageBlock,
    rgba: bool,
) -> [VFloat4; BLOCK_MAX_PARTITIONS] {
    let partition_count = pi.partition_count as usize;
    let mut averages = [VFloat4::zero(); BLOCK_MAX_PARTITIONS];
    let mean = if rgba {
        blk.data_mean
    } else {
        blk.data_mean.swz3(0, 1, 2)
    };
    if partition_count == 1 {
        averages[0] = mean;
        return averages;
    }
    let sums = partition_sums(pi, blk, partition_count - 1, if rgba { 4 } else { 3 });
    let block_total = mean * blk.texel_count as f32;
    let mut rest = block_total;
    for p in 0..partition_count - 1 {
        let s = sums[p];
        let total = if rgba {
            VFloat4::new(s[0], s[1], s[2], s[3])
        } else {
            vfloat3(s[0], s[1], s[2])
        };
        rest = rest - total;
        averages[p] = total / pi.partition_texel_count[p] as f32;
    }
    averages[partition_count - 1] = rest / pi.partition_texel_count[partition_count - 1] as f32;
    averages
}

/// The direction of most positive variance among `n` axes, as the C++ picks it.
#[inline]
fn best_direction(sums: &[VFloat4]) -> VFloat4 {
    let mut best_vector = sums[0];
    let mut best_sum = dot(sums[0], sums[0]);
    for (k, &s) in sums.iter().enumerate().skip(1) {
        let prod = dot(s, s);
        let mask = prod.gt(best_sum);
        best_vector = select(best_vector, s, mask);
        if k + 1 < sums.len() {
            best_sum = select(best_sum, prod, mask);
        }
    }
    best_vector
}

#[inline]
fn accumulate_positive(sums: &mut [VFloat4], texel_datum: VFloat4) {
    let zero = VFloat4::zero();
    for (k, s) in sums.iter_mut().enumerate() {
        let m = VFloat4::splat(texel_datum.lane(k)).gt(zero);
        *s += select(zero, texel_datum, m);
    }
}

pub fn compute_avgs_and_dirs_4_comp(
    pi: &PartitionInfo,
    blk: &ImageBlock,
    pm: &mut [PartitionMetrics; 4],
) {
    let averages = compute_partition_averages(pi, blk, true);
    for p in 0..pi.partition_count as usize {
        let texel_indexes = &pi.texels_of_partition[p];
        let texel_count = pi.partition_texel_count[p] as usize;
        let average = averages[p];
        pm[p].avg = average;
        let mut sums = [VFloat4::zero(); 4];
        for &iwt in &texel_indexes[..texel_count] {
            accumulate_positive(&mut sums, blk.texel(iwt as usize) - average);
        }
        pm[p].dir = best_direction(&sums);
    }
}

pub fn compute_avgs_and_dirs_3_comp(
    pi: &PartitionInfo,
    blk: &ImageBlock,
    omitted_component: u32,
    pm: &mut [PartitionMetrics; 4],
) {
    let mut averages = compute_partition_averages(pi, blk, true);
    let (sw, chans): ([usize; 3], [usize; 3]) = match omitted_component {
        0 => ([1, 2, 3], [1, 2, 3]),
        1 => ([0, 2, 3], [0, 2, 3]),
        2 => ([0, 1, 3], [0, 1, 3]),
        _ => ([0, 1, 2], [0, 1, 2]),
    };
    for a in &mut averages {
        *a = a.swz3(sw[0], sw[1], sw[2]);
    }
    let (dr, dg, db) = (
        blk.channel(chans[0]),
        blk.channel(chans[1]),
        blk.channel(chans[2]),
    );
    for p in 0..pi.partition_count as usize {
        let texel_indexes = &pi.texels_of_partition[p];
        let texel_count = pi.partition_texel_count[p] as usize;
        let average = averages[p];
        pm[p].avg = average;
        let mut sums = [VFloat4::zero(); 3];
        for &iwt in &texel_indexes[..texel_count] {
            let i = iwt as usize;
            accumulate_positive(&mut sums, vfloat3(dr[i], dg[i], db[i]) - average);
        }
        pm[p].dir = best_direction(&sums);
    }
}

pub fn compute_avgs_and_dirs_3_comp_rgb(
    pi: &PartitionInfo,
    blk: &ImageBlock,
    pm: &mut [PartitionMetrics; 4],
) {
    let averages = compute_partition_averages(pi, blk, false);
    for p in 0..pi.partition_count as usize {
        let texel_indexes = &pi.texels_of_partition[p];
        let texel_count = pi.partition_texel_count[p] as usize;
        let average = averages[p];
        pm[p].avg = average;
        let mut sums = [VFloat4::zero(); 3];
        for &iwt in &texel_indexes[..texel_count] {
            accumulate_positive(&mut sums, blk.texel3(iwt as usize) - average);
        }
        pm[p].dir = best_direction(&sums);
    }
}

pub fn compute_avgs_and_dirs_2_comp(
    pt: &PartitionInfo,
    blk: &ImageBlock,
    component1: u32,
    component2: u32,
    pm: &mut [PartitionMetrics; 4],
) {
    let (mut average, dr, dg) = match (component1, component2) {
        (0, 1) => (blk.data_mean.swz2(0, 1), &blk.data_r, &blk.data_g),
        (0, 2) => (blk.data_mean.swz2(0, 2), &blk.data_r, &blk.data_b),
        _ => (blk.data_mean.swz2(1, 2), &blk.data_g, &blk.data_b),
    };
    let partition_count = pt.partition_count as usize;
    for p in 0..partition_count {
        let texel_indexes = &pt.texels_of_partition[p];
        let texel_count = pt.partition_texel_count[p] as usize;
        if partition_count > 1 {
            average = VFloat4::zero();
            for &iwt in &texel_indexes[..texel_count] {
                let i = iwt as usize;
                average += vfloat2(dr[i], dg[i]);
            }
            average = average / texel_count as f32;
        }
        pm[p].avg = average;
        let mut sums = [VFloat4::zero(); 2];
        for &iwt in &texel_indexes[..texel_count] {
            let i = iwt as usize;
            accumulate_positive(&mut sums, vfloat2(dr[i], dg[i]) - average);
        }
        pm[p].dir = best_direction(&sums);
    }
}

pub fn compute_error_squared_rgba(
    pi: &PartitionInfo,
    blk: &ImageBlock,
    uncor_plines: &[ProcessedLine; 4],
    samec_plines: &[ProcessedLine; 4],
    line_lengths: &mut [f32; 4],
    uncor_error: &mut f32,
    samec_error: &mut f32,
) {
    let mut uncor_errorsumv = VFloat4::zero();
    let mut samec_errorsumv = VFloat4::zero();
    for p in 0..pi.partition_count as usize {
        let texel_indexes = &pi.texels_of_partition[p];
        let l_uncor = uncor_plines[p];
        let l_samec = samec_plines[p];
        let texel_count = pi.partition_texel_count[p] as usize;
        let ub: [VFloat4; 4] = core::array::from_fn(|k| VFloat4::splat(l_uncor.bs.lane(k)));
        let ua: [VFloat4; 4] = core::array::from_fn(|k| VFloat4::splat(l_uncor.amod.lane(k)));
        let sb: [VFloat4; 4] = core::array::from_fn(|k| VFloat4::splat(l_samec.bs.lane(k)));
        let mut lo = VFloat4::splat(1e10);
        let mut hi = VFloat4::splat(-1e10);
        let ew: [VFloat4; 4] = core::array::from_fn(|k| VFloat4::splat(blk.channel_weight.lane(k)));
        let mut lane_ids = VInt4::lane_id();
        let mut i = 0;
        while i < texel_count {
            let mask = lane_ids.lt(VInt4::splat(texel_count as i32));
            let idx = &texel_indexes[i..];
            let d = [
                gatherf_u8(&blk.data_r, idx),
                gatherf_u8(&blk.data_g, idx),
                gatherf_u8(&blk.data_b, idx),
                gatherf_u8(&blk.data_a, idx),
            ];
            let uncor_param = (d[0] * ub[0]) + (d[1] * ub[1]) + (d[2] * ub[2]) + (d[3] * ub[3]);
            lo = min(uncor_param, lo);
            hi = max(uncor_param, hi);
            let ud: [VFloat4; 4] = core::array::from_fn(|k| (ua[k] - d[k]) + (uncor_param * ub[k]));
            let uncor_err = (ew[0] * ud[0] * ud[0])
                + (ew[1] * ud[1] * ud[1])
                + (ew[2] * ud[2] * ud[2])
                + (ew[3] * ud[3] * ud[3]);
            haccumulate_m(&mut uncor_errorsumv, uncor_err, mask);
            let samec_param = (d[0] * sb[0]) + (d[1] * sb[1]) + (d[2] * sb[2]) + (d[3] * sb[3]);
            let sd: [VFloat4; 4] = core::array::from_fn(|k| samec_param * sb[k] - d[k]);
            let samec_err = (ew[0] * sd[0] * sd[0])
                + (ew[1] * sd[1] * sd[1])
                + (ew[2] * sd[2] * sd[2])
                + (ew[3] * sd[3] * sd[3]);
            haccumulate_m(&mut samec_errorsumv, samec_err, mask);
            lane_ids += VInt4::splat(4);
            i += 4;
        }
        let uncor_linelen = hmax_s(hi) - hmin_s(lo);
        line_lengths[p] = astc::max(uncor_linelen, 1e-7);
    }
    *uncor_error = hadd_s(uncor_errorsumv);
    *samec_error = hadd_s(samec_errorsumv);
}

pub fn compute_error_squared_rgb(
    pi: &PartitionInfo,
    blk: &ImageBlock,
    plines: &mut [PartitionLines3; 4],
    uncor_error: &mut f32,
    samec_error: &mut f32,
) {
    let mut uncor_errorsumv = VFloat4::zero();
    let mut samec_errorsumv = VFloat4::zero();
    for p in 0..pi.partition_count as usize {
        let pl = &mut plines[p];
        let texel_indexes = &pi.texels_of_partition[p];
        let texel_count = pi.partition_texel_count[p] as usize;
        let l_uncor = pl.uncor_pline;
        let l_samec = pl.samec_pline;
        let ub: [VFloat4; 3] = core::array::from_fn(|k| VFloat4::splat(l_uncor.bs.lane(k)));
        let ua: [VFloat4; 3] = core::array::from_fn(|k| VFloat4::splat(l_uncor.amod.lane(k)));
        let sb: [VFloat4; 3] = core::array::from_fn(|k| VFloat4::splat(l_samec.bs.lane(k)));
        let mut lo = VFloat4::splat(1e10);
        let mut hi = VFloat4::splat(-1e10);
        let ew: [VFloat4; 3] = core::array::from_fn(|k| VFloat4::splat(blk.channel_weight.lane(k)));
        let mut lane_ids = VInt4::lane_id();
        let mut i = 0;
        while i < texel_count {
            let mask = lane_ids.lt(VInt4::splat(texel_count as i32));
            let idx = &texel_indexes[i..];
            let d = [
                gatherf_u8(&blk.data_r, idx),
                gatherf_u8(&blk.data_g, idx),
                gatherf_u8(&blk.data_b, idx),
            ];
            let uncor_param = (d[0] * ub[0]) + (d[1] * ub[1]) + (d[2] * ub[2]);
            lo = min(uncor_param, lo);
            hi = max(uncor_param, hi);
            let ud: [VFloat4; 3] = core::array::from_fn(|k| (ua[k] - d[k]) + (uncor_param * ub[k]));
            let uncor_err =
                (ew[0] * ud[0] * ud[0]) + (ew[1] * ud[1] * ud[1]) + (ew[2] * ud[2] * ud[2]);
            haccumulate_m(&mut uncor_errorsumv, uncor_err, mask);
            let samec_param = (d[0] * sb[0]) + (d[1] * sb[1]) + (d[2] * sb[2]);
            let sd: [VFloat4; 3] = core::array::from_fn(|k| samec_param * sb[k] - d[k]);
            let samec_err =
                (ew[0] * sd[0] * sd[0]) + (ew[1] * sd[1] * sd[1]) + (ew[2] * sd[2] * sd[2]);
            haccumulate_m(&mut samec_errorsumv, samec_err, mask);
            lane_ids += VInt4::splat(4);
            i += 4;
        }
        let uncor_linelen = hmax_s(hi) - hmin_s(lo);
        pl.line_length = astc::max(uncor_linelen, 1e-7);
    }
    *uncor_error = hadd_s(uncor_errorsumv);
    *samec_error = hadd_s(samec_errorsumv);
}
