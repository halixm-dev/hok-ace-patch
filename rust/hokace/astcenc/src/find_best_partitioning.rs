//! Partitioning candidates by k-means and line fits (`astcenc_find_best_partitioning.cpp`).

use crate::averages_and_directions::*;
use crate::internal::*;
use crate::vecmath::*;

fn kmeans_init(
    blk: &ImageBlock,
    texel_count: usize,
    partition_count: usize,
    cluster_centers: &mut [VFloat4; 4],
) {
    let mut clusters_selected = 0usize;
    let mut distances = [0.0f32; BLOCK_MAX_TEXELS];
    let mut sample = 145_897 % texel_count;
    let mut center_color = blk.texel(sample);
    cluster_centers[clusters_selected] = center_color;
    clusters_selected += 1;
    let mut distance_sum = 0.0f32;
    for (i, d) in distances[..texel_count].iter_mut().enumerate() {
        let diff = blk.texel(i) - center_color;
        let distance = dot_s(diff * diff, blk.channel_weight);
        distance_sum += distance;
        *d = distance;
    }
    const CLUSTER_CUTOFFS: [f32; 9] = [
        0.626220, 0.932770, 0.275454, 0.318558, 0.240113, 0.009190, 0.347661, 0.731960, 0.156391,
    ];
    let mut cutoff = (clusters_selected - 1) + 3 * (partition_count - 2);
    loop {
        let mut summa = 0.0f32;
        let distance_cutoff = distance_sum * CLUSTER_CUTOFFS[cutoff];
        cutoff += 1;
        sample = 0;
        while sample < texel_count {
            summa += distances[sample];
            if summa >= distance_cutoff {
                break;
            }
            sample += 1;
        }
        sample = astc::min(sample, texel_count - 1);
        center_color = blk.texel(sample);
        cluster_centers[clusters_selected] = center_color;
        clusters_selected += 1;
        if clusters_selected >= partition_count {
            break;
        }
        distance_sum = 0.0;
        for (i, d) in distances[..texel_count].iter_mut().enumerate() {
            let diff = blk.texel(i) - center_color;
            let distance = astc::min(dot_s(diff * diff, blk.channel_weight), *d);
            distance_sum += distance;
            *d = distance;
        }
    }
}

fn kmeans_assign(
    blk: &ImageBlock,
    texel_count: usize,
    partition_count: usize,
    cluster_centers: &[VFloat4; 4],
    partition_of_texel: &mut [u8; BLOCK_MAX_TEXELS],
) {
    let mut partition_texel_count = [0u8; BLOCK_MAX_PARTITIONS];
    for (i, pot) in partition_of_texel[..texel_count].iter_mut().enumerate() {
        let mut best_distance = f32::MAX;
        let mut best_partition = 0;
        let color = blk.texel(i);
        for (j, &center) in cluster_centers[..partition_count].iter().enumerate() {
            let diff = color - center;
            let distance = dot_s(diff * diff, blk.channel_weight);
            if distance < best_distance {
                best_distance = distance;
                best_partition = j;
            }
        }
        *pot = best_partition as u8;
        partition_texel_count[best_partition] =
            partition_texel_count[best_partition].wrapping_add(1);
    }
    loop {
        let mut problem_case = false;
        for i in 0..partition_count {
            if partition_texel_count[i] == 0 {
                let p = partition_of_texel[i] as usize;
                partition_texel_count[p] = partition_texel_count[p].wrapping_sub(1);
                partition_texel_count[i] = partition_texel_count[i].wrapping_add(1);
                partition_of_texel[i] = i as u8;
                problem_case = true;
            }
        }
        if !problem_case {
            break;
        }
    }
}

fn kmeans_update(
    blk: &ImageBlock,
    texel_count: usize,
    partition_count: usize,
    cluster_centers: &mut [VFloat4; 4],
    partition_of_texel: &[u8; BLOCK_MAX_TEXELS],
) {
    let mut color_sum = [VFloat4::zero(); BLOCK_MAX_PARTITIONS];
    let mut partition_texel_count = [0u8; BLOCK_MAX_PARTITIONS];
    for (i, &p) in partition_of_texel[..texel_count].iter().enumerate() {
        let p = p as usize;
        color_sum[p] += blk.texel(i);
        partition_texel_count[p] = partition_texel_count[p].wrapping_add(1);
    }
    for i in 0..partition_count {
        let scale = 1.0 / partition_texel_count[i] as f32;
        cluster_centers[i] = color_sum[i] * scale;
    }
}

fn partition_mismatch2(a: &[u64], b: &[u64]) -> u8 {
    let v1 = popcount(a[0] ^ b[0]) + popcount(a[1] ^ b[1]);
    let v2 = popcount(a[0] ^ b[1]) + popcount(a[1] ^ b[0]);
    (astc::min(v1, v2) / 2) as u8
}

fn partition_mismatch3(a: &[u64], b: &[u64]) -> u8 {
    let p = |i: usize, j: usize| popcount(a[i] ^ b[j]);
    let v0 = astc::min(p(1, 1) + p(2, 2), p(1, 2) + p(2, 1)) + p(0, 0);
    let v1 = astc::min(p(1, 0) + p(2, 2), p(1, 2) + p(2, 0)) + p(0, 1);
    let v2 = astc::min(p(1, 0) + p(2, 1), p(1, 1) + p(2, 0)) + p(0, 2);
    (astc::min3(v0, v1, v2) / 2) as u8
}

fn partition_mismatch4(a: &[u64], b: &[u64]) -> u8 {
    let p = |i: usize, j: usize| popcount(a[i] ^ b[j]);
    let mx23 = astc::min(p(2, 2) + p(3, 3), p(2, 3) + p(3, 2));
    let mx13 = astc::min(p(2, 1) + p(3, 3), p(2, 3) + p(3, 1));
    let mx12 = astc::min(p(2, 1) + p(3, 2), p(2, 2) + p(3, 1));
    let mx03 = astc::min(p(2, 0) + p(3, 3), p(2, 3) + p(3, 0));
    let mx02 = astc::min(p(2, 0) + p(3, 2), p(2, 2) + p(3, 0));
    let mx01 = astc::min(p(2, 1) + p(3, 0), p(2, 0) + p(3, 1));
    let v0 = p(0, 0) + astc::min3(p(1, 1) + mx23, p(1, 2) + mx13, p(1, 3) + mx12);
    let v1 = p(0, 1) + astc::min3(p(1, 0) + mx23, p(1, 2) + mx03, p(1, 3) + mx02);
    let v2 = p(0, 2) + astc::min3(p(1, 1) + mx03, p(1, 0) + mx13, p(1, 3) + mx01);
    let v3 = p(0, 3) + astc::min3(p(1, 1) + mx02, p(1, 2) + mx01, p(1, 0) + mx12);
    (astc::min4(v0, v1, v2, v3) / 2) as u8
}

fn count_partition_mismatch_bits(
    bsd: &BlockSizeDescriptor,
    partition_count: usize,
    bitmaps: &[u64; 4],
    mismatch_counts: &mut [u8; BLOCK_MAX_PARTITIONINGS],
) {
    let active_count = bsd.partitioning_count_selected[partition_count - 1] as usize;
    for (i, m) in mismatch_counts[..active_count].iter_mut().enumerate() {
        *m = match partition_count {
            2 => partition_mismatch2(bitmaps, &bsd.coverage_bitmaps_2[i]),
            3 => partition_mismatch3(bitmaps, &bsd.coverage_bitmaps_3[i]),
            _ => partition_mismatch4(bitmaps, &bsd.coverage_bitmaps_4[i]),
        };
    }
}

fn get_partition_ordering_by_mismatch_bits(
    texel_count: usize,
    partitioning_count: usize,
    mismatch_count: &[u8; BLOCK_MAX_PARTITIONINGS],
    partition_ordering: &mut [u16; BLOCK_MAX_PARTITIONINGS],
) -> usize {
    let mut mscount = [0u16; BLOCK_MAX_KMEANS_TEXELS];
    for &m in &mismatch_count[..partitioning_count] {
        mscount[m as usize] += 1;
    }
    let mut sum = 0u16;
    for m in &mut mscount[..texel_count] {
        let cnt = *m;
        *m = sum;
        sum = sum.wrapping_add(cnt);
    }
    for (i, &m) in mismatch_count[..partitioning_count].iter().enumerate() {
        let idx = mscount[m as usize] as usize;
        mscount[m as usize] += 1;
        partition_ordering[idx] = i as u16;
    }
    partitioning_count
}

fn compute_kmeans_partition_ordering(
    bsd: &BlockSizeDescriptor,
    blk: &ImageBlock,
    partition_count: usize,
    partition_ordering: &mut [u16; BLOCK_MAX_PARTITIONINGS],
) -> usize {
    let mut cluster_centers = [VFloat4::zero(); 4];
    let mut texel_partitions = [0u8; BLOCK_MAX_TEXELS];
    let texel_count = bsd.texel_count as usize;
    for i in 0..3 {
        if i == 0 {
            kmeans_init(blk, texel_count, partition_count, &mut cluster_centers);
        } else {
            kmeans_update(
                blk,
                texel_count,
                partition_count,
                &mut cluster_centers,
                &texel_partitions,
            );
        }
        kmeans_assign(
            blk,
            texel_count,
            partition_count,
            &cluster_centers,
            &mut texel_partitions,
        );
    }
    let mut bitmaps = [0u64; BLOCK_MAX_PARTITIONS];
    let texels_to_process = astc::min(texel_count, BLOCK_MAX_KMEANS_TEXELS);
    for i in 0..texels_to_process {
        let idx = bsd.kmeans_texels[i] as usize;
        bitmaps[texel_partitions[idx] as usize] |= 1u64 << i;
    }
    let mut mismatch_counts = [0u8; BLOCK_MAX_PARTITIONINGS];
    count_partition_mismatch_bits(bsd, partition_count, &bitmaps, &mut mismatch_counts);
    get_partition_ordering_by_mismatch_bits(
        texels_to_process,
        bsd.partitioning_count_selected[partition_count - 1] as usize,
        &mismatch_counts,
        partition_ordering,
    )
}

fn insert_result(
    max_values: usize,
    this_error: f32,
    this_partition: u32,
    best_errors: &mut [f32],
    best_partitions: &mut [u32],
) {
    if this_error >= best_errors[max_values - 1] {
        return;
    }
    for i in 0..max_values {
        if this_error > best_errors[i] {
            continue;
        }
        for j in (i + 1..max_values).rev() {
            best_errors[j] = best_errors[j - 1];
            best_partitions[j] = best_partitions[j - 1];
        }
        best_errors[i] = this_error;
        best_partitions[i] = this_partition;
        break;
    }
}

pub fn find_best_partition_candidates(
    bsd: &BlockSizeDescriptor,
    blk: &ImageBlock,
    partition_count: u32,
    partition_search_limit: u32,
    best_partitions: &mut [u32; TUNE_MAX_PARTITIONING_CANDIDATES],
    requested_candidates: u32,
) -> u32 {
    let _prof = crate::prof::span(10);
    let pc = partition_count as usize;
    let texels_per_block = bsd.texel_count;
    let mut weight_imprecision_estim = if texels_per_block <= 20 {
        0.03f32
    } else if texels_per_block <= 31 {
        0.04
    } else if texels_per_block <= 41 {
        0.05
    } else {
        0.055
    };
    weight_imprecision_estim = weight_imprecision_estim * weight_imprecision_estim;
    let mut partition_sequence = [0u16; BLOCK_MAX_PARTITIONINGS];
    let sequence_len = compute_kmeans_partition_ordering(bsd, blk, pc, &mut partition_sequence);
    let partition_search_limit = astc::min(partition_search_limit as usize, sequence_len);
    let requested_candidates = astc::min(partition_search_limit, requested_candidates as usize);
    let uses_alpha = !blk.is_constant_channel(3);
    let mut uncor_best_errors = [ERROR_CALC_DEFAULT; TUNE_MAX_PARTITIONING_CANDIDATES];
    let mut uncor_best_partitions = [0u32; TUNE_MAX_PARTITIONING_CANDIDATES];
    let mut samec_best_errors = [ERROR_CALC_DEFAULT; TUNE_MAX_PARTITIONING_CANDIDATES];
    let mut samec_best_partitions = [0u32; TUNE_MAX_PARTITIONING_CANDIDATES];
    for &partition in &partition_sequence[..partition_search_limit] {
        let partition = partition as u32;
        let pi = bsd.get_raw_partition_info(partition_count, partition);
        let mut pms = [PartitionMetrics::default(); 4];
        let mut uncor_error = 0.0f32;
        let mut samec_error = 0.0f32;
        if uses_alpha {
            compute_avgs_and_dirs_4_comp(pi, blk, &mut pms);
            let mut uncor_b = [VFloat4::zero(); 4];
            let mut samec_b = [VFloat4::zero(); 4];
            let mut uncor_plines = [ProcessedLine::default(); 4];
            let mut samec_plines = [ProcessedLine::default(); 4];
            let mut line_lengths = [0.0f32; 4];
            for j in 0..pc {
                let pm = pms[j];
                let a = pm.avg;
                let b = normalize_safe(pm.dir, unit4());
                uncor_b[j] = b;
                uncor_plines[j].amod = a - b * dot(a, b);
                uncor_plines[j].bs = b;
                samec_b[j] = normalize_safe(pm.avg, unit4());
                samec_plines[j].amod = VFloat4::zero();
                samec_plines[j].bs = samec_b[j];
            }
            compute_error_squared_rgba(
                pi,
                blk,
                &uncor_plines,
                &samec_plines,
                &mut line_lengths,
                &mut uncor_error,
                &mut samec_error,
            );
            for j in 0..pc {
                let tpp = pi.partition_texel_count[j] as f32;
                let error_weights = VFloat4::splat(tpp * weight_imprecision_estim);
                let uncor_vector = uncor_b[j] * line_lengths[j];
                let samec_vector = samec_b[j] * line_lengths[j];
                uncor_error += dot_s(uncor_vector * uncor_vector, error_weights);
                samec_error += dot_s(samec_vector * samec_vector, error_weights);
            }
        } else {
            compute_avgs_and_dirs_3_comp_rgb(pi, blk, &mut pms);
            let mut plines = [PartitionLines3::default(); 4];
            for j in 0..pc {
                let pm = pms[j];
                let pl = &mut plines[j];
                pl.uncor_line.a = pm.avg;
                pl.uncor_line.b = normalize_safe(pm.dir, unit3());
                pl.samec_line.a = VFloat4::zero();
                pl.samec_line.b = normalize_safe(pm.avg, unit3());
                pl.uncor_pline.amod =
                    pl.uncor_line.a - pl.uncor_line.b * dot3(pl.uncor_line.a, pl.uncor_line.b);
                pl.uncor_pline.bs = pl.uncor_line.b;
                pl.samec_pline.amod = VFloat4::zero();
                pl.samec_pline.bs = pl.samec_line.b;
            }
            compute_error_squared_rgb(pi, blk, &mut plines, &mut uncor_error, &mut samec_error);
            for j in 0..pc {
                let pl = &plines[j];
                let tpp = pi.partition_texel_count[j] as f32;
                let error_weights = VFloat4::splat(tpp * weight_imprecision_estim);
                let uncor_vector = pl.uncor_line.b * pl.line_length;
                let samec_vector = pl.samec_line.b * pl.line_length;
                uncor_error += dot3_s(uncor_vector * uncor_vector, error_weights);
                samec_error += dot3_s(samec_vector * samec_vector, error_weights);
            }
        }
        insert_result(
            requested_candidates,
            uncor_error,
            partition,
            &mut uncor_best_errors,
            &mut uncor_best_partitions,
        );
        insert_result(
            requested_candidates,
            samec_error,
            partition,
            &mut samec_best_errors,
            &mut samec_best_partitions,
        );
    }
    let mut interleave = [0u32; 2 * TUNE_MAX_PARTITIONING_CANDIDATES];
    for i in 0..requested_candidates {
        interleave[2 * i] = bsd
            .get_raw_partition_info(partition_count, uncor_best_partitions[i])
            .partition_index as u32;
        interleave[2 * i + 1] = bsd
            .get_raw_partition_info(partition_count, samec_best_partitions[i])
            .partition_index as u32;
    }
    let mut bitmasks = [0u64; 1024 / 64];
    let mut emitted = 0usize;
    for &partition in &interleave[..requested_candidates * 2] {
        let word = (partition / 64) as usize;
        let bit = partition % 64;
        if bitmasks[word] & (1u64 << bit) == 0 {
            best_partitions[emitted] = partition;
            bitmasks[word] |= 1u64 << bit;
            emitted += 1;
            if emitted == requested_candidates {
                break;
            }
        }
    }
    emitted as u32
}
