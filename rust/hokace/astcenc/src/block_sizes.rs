//! Block-mode and decimation tables (`astcenc_block_sizes.cpp`, 2D only) and the 2D percentile
//! tables (`astcenc_percentile_tables.cpp`, unpacked by `tables_dump.cpp` into `data/percentile.bin`).

use crate::integer_sequence::get_ise_sequence_bitcount;
use crate::internal::*;
use crate::partition_tables::init_partition_tables;
use crate::vecmath::{astc, round_up_to_simd_multiple_vla};

const LEGAL_2D: [(u32, u32); 14] = [
    (4, 4),
    (5, 4),
    (5, 5),
    (6, 5),
    (6, 6),
    (8, 5),
    (8, 6),
    (8, 8),
    (10, 5),
    (10, 6),
    (10, 8),
    (10, 10),
    (12, 10),
    (12, 12),
];

static PERCENTILES: &[u8] = include_bytes!("../data/percentile.bin");

pub fn is_legal_2d_block_size(xdim: u32, ydim: u32) -> bool {
    LEGAL_2D.contains(&(xdim, ydim))
}

/// `get_2d_percentile_table`: one value per block mode.
fn get_2d_percentile_table(xdim: u32, ydim: u32) -> Vec<f32> {
    let index = LEGAL_2D
        .iter()
        .position(|&s| s == (xdim, ydim))
        .unwrap_or(0);
    let base = index * WEIGHTS_MAX_BLOCK_MODES * 4;
    PERCENTILES[base..base + WEIGHTS_MAX_BLOCK_MODES * 4]
        .as_chunks::<4>()
        .0
        .iter()
        .map(|b| f32::from_le_bytes([b[0], b[1], b[2], b[3]]))
        .collect()
}

struct DecodedMode {
    x_weights: u32,
    y_weights: u32,
    is_dual_plane: bool,
    quant_mode: u32,
    weight_bits: u32,
}

fn decode_block_mode_2d(block_mode: u32) -> Option<DecodedMode> {
    let mut base_quant_mode = (block_mode >> 4) & 1;
    let mut h = (block_mode >> 9) & 1;
    let mut d = (block_mode >> 10) & 1;
    let a = (block_mode >> 5) & 0x3;
    let (x_weights, y_weights);
    if (block_mode & 3) != 0 {
        base_quant_mode |= (block_mode & 3) << 1;
        let mut b = (block_mode >> 7) & 3;
        match (block_mode >> 2) & 3 {
            0 => (x_weights, y_weights) = (b + 4, a + 2),
            1 => (x_weights, y_weights) = (b + 8, a + 2),
            2 => (x_weights, y_weights) = (a + 2, b + 8),
            _ => {
                b &= 1;
                if block_mode & 0x100 != 0 {
                    (x_weights, y_weights) = (b + 2, a + 2);
                } else {
                    (x_weights, y_weights) = (a + 2, b + 6);
                }
            }
        }
    } else {
        base_quant_mode |= ((block_mode >> 2) & 3) << 1;
        if ((block_mode >> 2) & 3) == 0 {
            return None;
        }
        let b = (block_mode >> 9) & 3;
        match (block_mode >> 7) & 3 {
            0 => (x_weights, y_weights) = (12, a + 2),
            1 => (x_weights, y_weights) = (a + 2, 12),
            2 => {
                (x_weights, y_weights) = (a + 6, b + 6);
                d = 0;
                h = 0;
            }
            _ => match (block_mode >> 5) & 3 {
                0 => (x_weights, y_weights) = (6, 10),
                1 => (x_weights, y_weights) = (10, 6),
                _ => return None,
            },
        }
    }
    let weight_count = x_weights * y_weights * (d + 1);
    let quant_mode = (base_quant_mode.wrapping_sub(2)).wrapping_add(6 * h);
    let weight_bits = get_ise_sequence_bitcount(weight_count, quant_mode as usize);
    let valid = weight_count as usize <= BLOCK_MAX_WEIGHTS
        && (BLOCK_MIN_WEIGHT_BITS..=BLOCK_MAX_WEIGHT_BITS).contains(&weight_bits);
    valid.then_some(DecodedMode {
        x_weights,
        y_weights,
        is_dual_plane: d != 0,
        quant_mode,
        weight_bits,
    })
}

struct DtInitWorkingBuffers {
    weight_count_of_texel: [u8; BLOCK_MAX_TEXELS],
    grid_weights_of_texel: [[u8; 4]; BLOCK_MAX_TEXELS],
    weights_of_texel: [[u8; 4]; BLOCK_MAX_TEXELS],
    texel_count_of_weight: [u8; BLOCK_MAX_WEIGHTS],
    texels_of_weight: [[u8; BLOCK_MAX_TEXELS]; BLOCK_MAX_WEIGHTS],
    texel_weights_of_weight: [[u8; BLOCK_MAX_TEXELS]; BLOCK_MAX_WEIGHTS],
}

fn init_decimation_info_2d(
    x_texels: u32,
    y_texels: u32,
    x_weights: u32,
    y_weights: u32,
    di: &mut DecimationInfo,
    wb: &mut DtInitWorkingBuffers,
) {
    let texels_per_block = (x_texels * y_texels) as usize;
    let weights_per_block = (x_weights * y_weights) as usize;
    let mut max_texel_count_of_weight: u8 = 0;
    wb.texel_count_of_weight[..weights_per_block].fill(0);
    wb.weight_count_of_texel[..texels_per_block].fill(0);

    for y in 0..y_texels {
        for x in 0..x_texels {
            let texel = (y * x_texels + x) as usize;
            let x_weight =
                (((1024 + x_texels / 2) / (x_texels - 1)) * x * (x_weights - 1) + 32) >> 6;
            let y_weight =
                (((1024 + y_texels / 2) / (y_texels - 1)) * y * (y_weights - 1) + 32) >> 6;
            let x_weight_frac = x_weight & 0xF;
            let y_weight_frac = y_weight & 0xF;
            let x_weight_int = x_weight >> 4;
            let y_weight_int = y_weight >> 4;
            let mut qweight = [0u32; 4];
            qweight[0] = x_weight_int + y_weight_int * x_weights;
            qweight[1] = qweight[0] + 1;
            qweight[2] = qweight[0] + x_weights;
            qweight[3] = qweight[2] + 1;
            let prod = x_weight_frac * y_weight_frac;
            let mut weight = [0u32; 4];
            weight[3] = (prod + 8) >> 4;
            weight[1] = x_weight_frac.wrapping_sub(weight[3]);
            weight[2] = y_weight_frac.wrapping_sub(weight[3]);
            weight[0] = (16 - x_weight_frac - y_weight_frac).wrapping_add(weight[3]);
            for i in 0..4 {
                if weight[i] != 0 {
                    let q = qweight[i] as usize;
                    let wct = wb.weight_count_of_texel[texel] as usize;
                    wb.grid_weights_of_texel[texel][wct] = q as u8;
                    wb.weights_of_texel[texel][wct] = weight[i] as u8;
                    wb.weight_count_of_texel[texel] += 1;
                    let tcw = wb.texel_count_of_weight[q] as usize;
                    wb.texels_of_weight[q][tcw] = texel as u8;
                    wb.texel_weights_of_weight[q][tcw] = weight[i] as u8;
                    wb.texel_count_of_weight[q] += 1;
                    max_texel_count_of_weight =
                        astc::max(max_texel_count_of_weight, wb.texel_count_of_weight[q]);
                }
            }
        }
    }

    let mut max_texel_weight_count: u8 = 0;
    for i in 0..texels_per_block {
        di.texel_weight_count[i] = wb.weight_count_of_texel[i];
        max_texel_weight_count = astc::max(max_texel_weight_count, di.texel_weight_count[i]);
        let n = wb.weight_count_of_texel[i] as usize;
        for j in 0..n {
            di.texel_weight_contribs_int_tr[j][i] = wb.weights_of_texel[i][j];
            di.texel_weight_contribs_float_tr[j][i] =
                wb.weights_of_texel[i][j] as f32 * (1.0 / WEIGHTS_TEXEL_SUM);
            di.texel_weights_tr[j][i] = wb.grid_weights_of_texel[i][j];
        }
        for j in n..4 {
            di.texel_weight_contribs_int_tr[j][i] = 0;
            di.texel_weight_contribs_float_tr[j][i] = 0.0;
            di.texel_weights_tr[j][i] = 0;
        }
    }
    di.max_texel_weight_count = max_texel_weight_count;

    for i in 0..weights_per_block {
        let texel_count_wt = wb.texel_count_of_weight[i] as usize;
        di.weight_texel_count[i] = texel_count_wt as u8;
        for j in 0..texel_count_wt {
            let texel = wb.texels_of_weight[i][j] as usize;
            di.weight_texels_tr[j][i] = texel as u8;
            di.weights_texel_contribs_tr[j][i] = wb.texel_weights_of_weight[i][j] as f32;
            di.texel_contrib_for_weight[j][i] = 0.0;
            for k in 0..4 {
                let dttw = di.texel_weights_tr[k][texel];
                let dttwf = di.texel_weight_contribs_float_tr[k][texel];
                if dttw as usize == i && dttwf != 0.0 {
                    di.texel_contrib_for_weight[j][i] = di.texel_weight_contribs_float_tr[k][texel];
                    break;
                }
            }
        }
        let last_texel = di.weight_texels_tr[texel_count_wt - 1][i];
        for j in texel_count_wt..max_texel_count_of_weight as usize {
            di.weight_texels_tr[j][i] = last_texel;
            di.weights_texel_contribs_tr[j][i] = 0.0;
        }
    }

    let texels_per_block_simd = round_up_to_simd_multiple_vla(texels_per_block as u32) as usize;
    for i in texels_per_block..texels_per_block_simd {
        di.texel_weight_count[i] = 0;
        for j in 0..4 {
            di.texel_weight_contribs_float_tr[j][i] = 0.0;
            di.texel_weights_tr[j][i] = 0;
            di.texel_weight_contribs_int_tr[j][i] = 0;
        }
    }

    let last_texel_count_wt = wb.texel_count_of_weight[weights_per_block - 1] as usize;
    let last_texel = di.weight_texels_tr[last_texel_count_wt - 1][weights_per_block - 1];
    let weights_per_block_simd = round_up_to_simd_multiple_vla(weights_per_block as u32) as usize;
    for i in weights_per_block..weights_per_block_simd {
        di.weight_texel_count[i] = 0;
        for j in 0..max_texel_count_of_weight as usize {
            di.weight_texels_tr[j][i] = last_texel;
            di.weights_texel_contribs_tr[j][i] = 0.0;
        }
    }

    di.texel_count = texels_per_block as u8;
    di.weight_count = weights_per_block as u8;
    di.weight_x = x_weights as u8;
    di.weight_y = y_weights as u8;
    di.weight_z = 1;
}

fn assign_kmeans_texels(bsd: &mut BlockSizeDescriptor) {
    let tc = bsd.texel_count as usize;
    if tc <= BLOCK_MAX_KMEANS_TEXELS {
        for i in 0..tc {
            bsd.kmeans_texels[i] = i as u8;
        }
        return;
    }
    let mut rng = astc::rand_init();
    let mut seen = [false; BLOCK_MAX_TEXELS];
    let mut set = 0;
    while set < BLOCK_MAX_KMEANS_TEXELS {
        let texel = (astc::rand(&mut rng) as u8) % bsd.texel_count;
        if !seen[texel as usize] {
            bsd.kmeans_texels[set] = texel;
            set += 1;
            seen[texel as usize] = true;
        }
    }
}

fn construct_dt_entry_2d(
    x_texels: u32,
    y_texels: u32,
    x_weights: u32,
    y_weights: u32,
    bsd: &mut BlockSizeDescriptor,
    wb: &mut DtInitWorkingBuffers,
    index: usize,
) {
    let weight_count = x_weights * y_weights;
    let try_2planes = (2 * weight_count) as usize <= BLOCK_MAX_WEIGHTS;
    init_decimation_info_2d(
        x_texels,
        y_texels,
        x_weights,
        y_weights,
        &mut bsd.decimation_tables[index],
        wb,
    );
    let mut maxprec_1plane = -1i32;
    let mut maxprec_2planes = -1i32;
    for i in 0..12 {
        let bits_1plane = get_ise_sequence_bitcount(weight_count, i);
        if (BLOCK_MIN_WEIGHT_BITS..=BLOCK_MAX_WEIGHT_BITS).contains(&bits_1plane) {
            maxprec_1plane = i as i32;
        }
        if try_2planes {
            let bits_2planes = get_ise_sequence_bitcount(2 * weight_count, i);
            if (BLOCK_MIN_WEIGHT_BITS..=BLOCK_MAX_WEIGHT_BITS).contains(&bits_2planes) {
                maxprec_2planes = i as i32;
            }
        }
    }
    let dm = &mut bsd.decimation_modes[index];
    dm.maxprec_1plane = maxprec_1plane as i8;
    dm.maxprec_2planes = maxprec_2planes as i8;
    dm.refprec_1plane = 0;
    dm.refprec_2planes = 0;
}

fn construct_block_size_descriptor_2d(
    x_texels: u32,
    y_texels: u32,
    can_omit_modes: bool,
    mode_cutoff: f32,
    bsd: &mut BlockSizeDescriptor,
) {
    const MAX_DMI: usize = 12 * 16 + 12;
    let mut decimation_mode_index = [-1i32; MAX_DMI];
    let mut wb = Box::new(DtInitWorkingBuffers {
        weight_count_of_texel: [0; BLOCK_MAX_TEXELS],
        grid_weights_of_texel: [[0; 4]; BLOCK_MAX_TEXELS],
        weights_of_texel: [[0; 4]; BLOCK_MAX_TEXELS],
        texel_count_of_weight: [0; BLOCK_MAX_WEIGHTS],
        texels_of_weight: [[0; BLOCK_MAX_TEXELS]; BLOCK_MAX_WEIGHTS],
        texel_weights_of_weight: [[0; BLOCK_MAX_TEXELS]; BLOCK_MAX_WEIGHTS],
    });
    bsd.xdim = x_texels as u8;
    bsd.ydim = y_texels as u8;
    bsd.zdim = 1;
    bsd.texel_count = (x_texels * y_texels) as u8;

    let percentiles = get_2d_percentile_table(x_texels, y_texels);
    let always_cutoff = 0.0f32;
    let mut packed_bm_idx = 0usize;
    let mut packed_dm_idx = 0usize;
    let mut bm_counts = [0u32; 4];
    let mut dm_counts = [0u32; 4];
    bsd.block_mode_packed_index.fill(BLOCK_BAD_BLOCK_MODE);

    let limit = if can_omit_modes { 3 } else { 4 };
    for j in 0..limit {
        for i in 0..WEIGHTS_MAX_BLOCK_MODES {
            if bsd.block_mode_packed_index[i] != BLOCK_BAD_BLOCK_MODE {
                continue;
            }
            let Some(m) = decode_block_mode_2d(i as u32) else {
                continue;
            };
            if m.x_weights > x_texels || m.y_weights > y_texels {
                continue;
            }
            if (j <= 1 && m.is_dual_plane) || (j == 2 && !m.is_dual_plane) {
                continue;
            }
            // The C++ tests `(109 - weight_bits) <= 0` on unsigned ints: true only at equality.
            let budget = if m.is_dual_plane { 109u32 } else { 111u32 };
            if budget.wrapping_sub(m.weight_bits) == 0 {
                continue;
            }
            let percentile_hit = if j == 0 {
                percentiles[i] <= always_cutoff
            } else {
                percentiles[i] <= mode_cutoff
            };
            if j != 3 && !percentile_hit {
                continue;
            }
            let key = (m.y_weights * 16 + m.x_weights) as usize;
            let mut decimation_mode = decimation_mode_index[key];
            if decimation_mode < 0 {
                construct_dt_entry_2d(
                    x_texels,
                    y_texels,
                    m.x_weights,
                    m.y_weights,
                    bsd,
                    &mut wb,
                    packed_dm_idx,
                );
                decimation_mode_index[key] = packed_dm_idx as i32;
                decimation_mode = packed_dm_idx as i32;
                dm_counts[j] += 1;
                packed_dm_idx += 1;
            }
            let bm = &mut bsd.block_modes[packed_bm_idx];
            bm.decimation_mode = decimation_mode as u8;
            bm.quant_mode = m.quant_mode as u8;
            bm.is_dual_plane = m.is_dual_plane;
            bm.weight_bits = m.weight_bits as u8;
            bm.mode_index = i as u16;
            let dm = &mut bsd.decimation_modes[decimation_mode as usize];
            if m.is_dual_plane {
                dm.set_ref_2plane(m.quant_mode as usize);
            } else {
                dm.set_ref_1plane(m.quant_mode as usize);
            }
            bsd.block_mode_packed_index[i] = packed_bm_idx as u16;
            packed_bm_idx += 1;
            bm_counts[j] += 1;
        }
    }

    bsd.block_mode_count_1plane_always = bm_counts[0];
    bsd.block_mode_count_1plane_selected = bm_counts[0] + bm_counts[1];
    bsd.block_mode_count_1plane_2plane_selected = bm_counts[0] + bm_counts[1] + bm_counts[2];
    bsd.block_mode_count_all = bm_counts.iter().sum();
    bsd.decimation_mode_count_always = dm_counts[0];
    bsd.decimation_mode_count_selected = dm_counts[0] + dm_counts[1] + dm_counts[2];
    bsd.decimation_mode_count_all = dm_counts.iter().sum();

    for dm in &mut bsd.decimation_modes[bsd.decimation_mode_count_all as usize..] {
        *dm = DecimationMode {
            maxprec_1plane: -1,
            maxprec_2planes: -1,
            refprec_1plane: 0,
            refprec_2planes: 0,
        };
    }
    assign_kmeans_texels(bsd);
}

/// `init_block_size_descriptor` for a 2D footprint.
pub fn init_block_size_descriptor(
    x_texels: u32,
    y_texels: u32,
    can_omit_modes: bool,
    partition_count_cutoff: u32,
    mode_cutoff: f32,
) -> Box<BlockSizeDescriptor> {
    let mut bsd = Box::new(BlockSizeDescriptor::zeroed());
    construct_block_size_descriptor_2d(x_texels, y_texels, can_omit_modes, mode_cutoff, &mut bsd);
    init_partition_tables(&mut bsd, can_omit_modes, partition_count_cutoff);
    bsd
}
