//! A byte dump of a context's config and block-size descriptor, laid out as
//! `rust/harness/astcenc_oracle/oracle.cpp --dump` writes it, so the two can be compared whole.

use crate::entry::Context;
use crate::internal::*;
use crate::vecmath::round_up_to_simd_multiple_vla;

struct W(Vec<u8>);

impl W {
    fn u8(&mut self, v: u8) {
        self.0.push(v);
    }
    fn u16(&mut self, v: u16) {
        self.0.extend_from_slice(&v.to_le_bytes());
    }
    fn u32(&mut self, v: u32) {
        self.0.extend_from_slice(&v.to_le_bytes());
    }
    fn f32(&mut self, v: f32) {
        self.u32(v.to_bits());
    }
    fn u64(&mut self, v: u64) {
        self.0.extend_from_slice(&v.to_le_bytes());
    }
}

pub fn dump_context(ctx: &Context) -> Vec<u8> {
    let mut w = W(Vec::new());
    let c = &ctx.config;
    for v in [
        c.tune_partition_count_limit,
        c.tune_2partition_index_limit,
        c.tune_3partition_index_limit,
        c.tune_4partition_index_limit,
        c.tune_block_mode_limit,
        c.tune_refinement_limit,
        c.tune_candidate_limit,
        c.tune_2partitioning_candidate_limit,
        c.tune_3partitioning_candidate_limit,
        c.tune_4partitioning_candidate_limit,
    ] {
        w.u32(v);
    }
    for v in [
        c.tune_db_limit,
        c.tune_mse_overshoot,
        c.tune_2partition_early_out_limit_factor,
        c.tune_3partition_early_out_limit_factor,
        c.tune_2plane_early_out_limit_correlation,
        c.tune_search_mode0_enable,
        c.cw_r_weight,
        c.cw_g_weight,
        c.cw_b_weight,
        c.cw_a_weight,
    ] {
        w.f32(v);
    }
    let b = &ctx.bsd;
    for v in [b.xdim, b.ydim, b.zdim, b.texel_count] {
        w.u8(v);
    }
    for v in [
        b.decimation_mode_count_always,
        b.decimation_mode_count_selected,
        b.decimation_mode_count_all,
        b.block_mode_count_1plane_always,
        b.block_mode_count_1plane_selected,
        b.block_mode_count_1plane_2plane_selected,
        b.block_mode_count_all,
    ] {
        w.u32(v);
    }
    for i in 0..4 {
        w.u32(b.partitioning_count_selected[i]);
        w.u32(b.partitioning_count_all[i]);
    }
    for dm in &b.decimation_modes[..b.decimation_mode_count_all as usize] {
        w.u8(dm.maxprec_1plane as u8);
        w.u8(dm.maxprec_2planes as u8);
        w.u16(dm.refprec_1plane);
        w.u16(dm.refprec_2planes);
    }
    for di in &b.decimation_tables[..b.decimation_mode_count_all as usize] {
        for v in [
            di.texel_count,
            di.max_texel_weight_count,
            di.weight_count,
            di.weight_x,
            di.weight_y,
            di.weight_z,
        ] {
            w.u8(v);
        }
        let tcs = round_up_to_simd_multiple_vla(di.texel_count as u32) as usize;
        let wcs = round_up_to_simd_multiple_vla(di.weight_count as u32) as usize;
        for i in 0..tcs {
            w.u8(di.texel_weight_count[i]);
        }
        for j in 0..4 {
            for i in 0..tcs {
                w.u8(di.texel_weights_tr[j][i]);
                w.u8(di.texel_weight_contribs_int_tr[j][i]);
                w.f32(di.texel_weight_contribs_float_tr[j][i]);
            }
        }
        let max_tcw = di.weight_texel_count[..di.weight_count as usize]
            .iter()
            .copied()
            .max()
            .unwrap_or(0) as usize;
        for i in 0..wcs {
            w.u8(di.weight_texel_count[i]);
            for j in 0..max_tcw {
                w.u8(di.weight_texels_tr[j][i]);
                w.f32(di.weights_texel_contribs_tr[j][i]);
            }
            let n = if i < di.weight_count as usize {
                di.weight_texel_count[i] as usize
            } else {
                0
            };
            for j in 0..n {
                w.f32(di.texel_contrib_for_weight[j][i]);
            }
        }
    }
    for &v in &b.block_mode_packed_index {
        w.u16(v);
    }
    for bm in &b.block_modes[..b.block_mode_count_all as usize] {
        w.u16(bm.mode_index);
        w.u8(bm.decimation_mode);
        w.u8(bm.quant_mode);
        w.u8(bm.weight_bits);
        w.u8(bm.is_dual_plane as u8);
    }
    for pc in 1..=4u32 {
        for k in 0..b.partitioning_count_all[pc as usize - 1] {
            let pi = b.get_raw_partition_info(pc, k);
            w.u16(pi.partition_count);
            w.u16(pi.partition_index);
            for v in pi.partition_texel_count {
                w.u8(v);
            }
            for &v in &pi.partition_of_texel[..b.texel_count as usize] {
                w.u8(v);
            }
            for p in 0..pi.partition_count as usize {
                let n = round_up_to_simd_multiple_vla(pi.partition_texel_count[p] as u32) as usize;
                for &v in &pi.texels_of_partition[p][..n] {
                    w.u8(v);
                }
            }
            match pc {
                2 => b.coverage_bitmaps_2[k as usize]
                    .iter()
                    .for_each(|&v| w.u64(v)),
                3 => b.coverage_bitmaps_3[k as usize]
                    .iter()
                    .for_each(|&v| w.u64(v)),
                4 => b.coverage_bitmaps_4[k as usize]
                    .iter()
                    .for_each(|&v| w.u64(v)),
                _ => {}
            }
        }
    }
    for row in &b.partitioning_packed_index {
        for &v in row {
            w.u16(v);
        }
    }
    for &v in &b.kmeans_texels[..(b.texel_count as usize).min(BLOCK_MAX_KMEANS_TEXELS)] {
        w.u8(v);
    }
    w.0
}
