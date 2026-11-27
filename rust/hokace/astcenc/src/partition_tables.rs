//! Partition tables (`astcenc_partition_tables.cpp`).

use crate::internal::*;
use crate::vecmath::round_up_to_simd_multiple_vla;

const BIT_PATTERN_WORDS: usize = (BLOCK_MAX_TEXELS * 2).div_ceil(64);

fn generate_canonical_partitioning(
    texel_count: usize,
    partition_of_texel: &[u8],
) -> [u64; BIT_PATTERN_WORDS] {
    let mut bit_pattern = [0u64; BIT_PATTERN_WORDS];
    let mut mapped_index = [-1i32; BLOCK_MAX_PARTITIONS];
    let mut map_weight_count = 0;
    for (i, &p) in partition_of_texel[..texel_count].iter().enumerate() {
        let index = p as usize;
        if mapped_index[index] < 0 {
            mapped_index[index] = map_weight_count;
            map_weight_count += 1;
        }
        let xlat = mapped_index[index] as u64;
        bit_pattern[i >> 5] |= xlat << (2 * (i & 0x1F));
    }
    bit_pattern
}

fn hash52(mut inp: u32) -> u32 {
    inp ^= inp >> 15;
    inp = inp.wrapping_mul(0xEEDE_0891);
    inp ^= inp >> 5;
    inp = inp.wrapping_add(inp << 16);
    inp ^= inp >> 7;
    inp ^= inp >> 3;
    inp ^= inp << 6;
    inp ^= inp >> 17;
    inp
}

fn select_partition(
    seed: i32,
    x: i32,
    y: i32,
    z: i32,
    partition_count: i32,
    small_block: bool,
) -> u8 {
    let (x, y, z) = if small_block {
        (x << 1, y << 1, z << 1)
    } else {
        (x, y, z)
    };
    let seed = seed + (partition_count - 1) * 1024;
    let rnum = hash52(seed as u32);
    let s = |shift: u32| -> u32 {
        let v = ((rnum >> shift) & 0xF) as u8;
        v.wrapping_mul(v) as u32
    };
    let mut seeds = [
        s(0),
        s(4),
        s(8),
        s(12),
        s(16),
        s(20),
        s(24),
        s(28),
        s(18),
        s(22),
        s(26),
        {
            let v = (rnum.rotate_left(2) & 0xF) as u8;
            v.wrapping_mul(v) as u32
        },
    ];
    let (sh1, sh2) = if seed & 1 != 0 {
        (
            if seed & 2 != 0 { 4 } else { 5 },
            if partition_count == 3 { 6 } else { 5 },
        )
    } else {
        (
            if partition_count == 3 { 6 } else { 5 },
            if seed & 2 != 0 { 4 } else { 5 },
        )
    };
    let sh3 = if seed & 0x10 != 0 { sh1 } else { sh2 };
    for (k, seed_k) in seeds.iter_mut().enumerate() {
        let sh = if k >= 8 {
            sh3
        } else if k % 2 == 0 {
            sh1
        } else {
            sh2
        };
        *seed_k >>= sh;
    }
    let (x, y, z) = (x as u32, y as u32, z as u32);
    let lin = |a: u32, b: u32, c: u32, r: u32| {
        a.wrapping_mul(x)
            .wrapping_add(b.wrapping_mul(y))
            .wrapping_add(c.wrapping_mul(z))
            .wrapping_add(r)
    };
    let a = lin(seeds[0], seeds[1], seeds[10], rnum >> 14) & 0x3F;
    let mut b = lin(seeds[2], seeds[3], seeds[11], rnum >> 10) & 0x3F;
    let mut c = lin(seeds[4], seeds[5], seeds[8], rnum >> 6) & 0x3F;
    let mut d = lin(seeds[6], seeds[7], seeds[9], rnum >> 2) & 0x3F;
    if partition_count <= 3 {
        d = 0;
    }
    if partition_count <= 2 {
        c = 0;
    }
    if partition_count <= 1 {
        b = 0;
    }
    if a >= b && a >= c && a >= d {
        0
    } else if b >= c && b >= d {
        1
    } else if c >= d {
        2
    } else {
        3
    }
}

/// Fills `bsd.partitionings[slot]` in place, as the C++ reuses one slot until an entry is kept.
fn generate_one_partition_info_entry(
    bsd: &mut BlockSizeDescriptor,
    partition_count: u32,
    partition_index: u32,
    partition_remap_index: usize,
    slot: usize,
) -> bool {
    let small_block = (bsd.texel_count as i32) < 32;
    let (xdim, ydim, zdim) = (bsd.xdim as i32, bsd.ydim as i32, bsd.zdim as i32);
    let texel_count = bsd.texel_count as usize;
    let mut counts = [0usize; BLOCK_MAX_PARTITIONS];
    {
        let pi = &mut bsd.partitionings[slot];
        let mut texel_idx = 0usize;
        for z in 0..zdim {
            for y in 0..ydim {
                for x in 0..xdim {
                    let part = select_partition(
                        partition_index as i32,
                        x,
                        y,
                        z,
                        partition_count as i32,
                        small_block,
                    );
                    let p = part as usize;
                    pi.texels_of_partition[p][counts[p]] = texel_idx as u8;
                    counts[p] += 1;
                    pi.partition_of_texel[texel_idx] = part;
                    texel_idx += 1;
                }
            }
        }
        for i in 0..partition_count as usize {
            let ptex_count = counts[i];
            let simd = round_up_to_simd_multiple_vla(ptex_count as u32) as usize;
            for j in ptex_count..simd {
                pi.texels_of_partition[i][j] = pi.texels_of_partition[i][ptex_count - 1];
            }
        }
        pi.partition_count = if counts[0] == 0 {
            0
        } else if counts[1] == 0 {
            1
        } else if counts[2] == 0 {
            2
        } else if counts[3] == 0 {
            3
        } else {
            4
        };
        pi.partition_index = partition_index as u16;
        for i in 0..BLOCK_MAX_PARTITIONS {
            pi.partition_texel_count[i] = counts[i] as u8;
        }
    }
    let valid = bsd.partitionings[slot].partition_count as u32 == partition_count;
    if partition_count >= 2 {
        let to_process = texel_count.min(BLOCK_MAX_KMEANS_TEXELS);
        let mut bitmaps = [0u64; 4];
        for i in 0..to_process {
            let idx = bsd.kmeans_texels[i] as usize;
            bitmaps[bsd.partitionings[slot].partition_of_texel[idx] as usize] |= 1u64 << i;
        }
        let n = partition_count as usize;
        match partition_count {
            2 => bsd.coverage_bitmaps_2[partition_remap_index].copy_from_slice(&bitmaps[..n]),
            3 => bsd.coverage_bitmaps_3[partition_remap_index].copy_from_slice(&bitmaps[..n]),
            _ => bsd.coverage_bitmaps_4[partition_remap_index].copy_from_slice(&bitmaps[..n]),
        }
    }
    valid
}

fn build_partition_table_for_one_partition_count(
    bsd: &mut BlockSizeDescriptor,
    can_omit_partitionings: bool,
    partition_count_cutoff: u32,
    partition_count: u32,
    canonical_patterns: &mut [[u64; BIT_PATTERN_WORDS]],
) {
    let pc = partition_count as usize;
    let base = BlockSizeDescriptor::partition_table_base(partition_count);
    let mut next_index = 0usize;
    bsd.partitioning_count_selected[pc - 1] = 0;
    bsd.partitioning_count_all[pc - 1] = 0;
    if can_omit_partitionings && partition_count > partition_count_cutoff {
        return;
    }
    let max_iter = if can_omit_partitionings { 1 } else { 2 };
    let mut build = [false; BLOCK_MAX_PARTITIONINGS];
    for x in 0..max_iter {
        for i in 0..BLOCK_MAX_PARTITIONINGS {
            if x == 1 && build[i] {
                continue;
            }
            let keep_useful = generate_one_partition_info_entry(
                bsd,
                partition_count,
                i as u32,
                next_index,
                base + next_index,
            );
            if x == 0 && !keep_useful {
                continue;
            }
            let pattern = generate_canonical_partitioning(
                bsd.texel_count as usize,
                &bsd.partitionings[base + next_index].partition_of_texel,
            );
            canonical_patterns[next_index] = pattern;
            let keep_canonical = !canonical_patterns[..next_index].contains(&pattern);
            if keep_useful && keep_canonical {
                if x == 0 {
                    bsd.partitioning_packed_index[pc - 2][i] = next_index as u16;
                    bsd.partitioning_count_selected[pc - 1] += 1;
                    bsd.partitioning_count_all[pc - 1] += 1;
                    build[i] = true;
                    next_index += 1;
                }
            } else if x == 1 {
                bsd.partitioning_packed_index[pc - 2][i] = next_index as u16;
                bsd.partitioning_count_all[pc - 1] += 1;
                next_index += 1;
            }
        }
    }
}

pub fn init_partition_tables(
    bsd: &mut BlockSizeDescriptor,
    can_omit_partitionings: bool,
    partition_count_cutoff: u32,
) {
    let one = BlockSizeDescriptor::partition_table_base(1);
    generate_one_partition_info_entry(bsd, 1, 0, 0, one);
    bsd.partitioning_count_selected[0] = 1;
    bsd.partitioning_count_all[0] = 1;
    let mut canonical = vec![[0u64; BIT_PATTERN_WORDS]; BLOCK_MAX_PARTITIONINGS];
    for pc in 2..=4 {
        build_partition_table_for_one_partition_count(
            bsd,
            can_omit_partitionings,
            partition_count_cutoff,
            pc,
            &mut canonical,
        );
    }
}
